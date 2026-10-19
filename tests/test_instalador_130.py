"""D2: attestation obrigatória e versão parametrizada no instalador."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

import freoa_verifica

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/instalar-freoa-verifica.ps1"
WRAPPER = """
param($Installer, [switch]$SemAttestation)
function Invoke-WebRequest {
    param($Uri, $OutFile, [switch]$UseBasicParsing)
    Set-Content -LiteralPath $OutFile -Value '# lock sintetico'
}
if ($SemAttestation) { & $Installer -SemAttestation } else { & $Installer }
exit $LASTEXITCODE
"""
GH_JSON = ('@echo off\r\necho [{"verificationResult":{"signature":{"certificate":'
           '{"sourceRepositoryDigest":"abc123"}}}}]\r\nexit /b 0\r\n')


def rodar(tmp_path, *, gh=None, sem_attestation=False):
    powershell = shutil.which("powershell")
    if not powershell:
        pytest.skip("PowerShell não disponível")
    script = tmp_path / SCRIPT.name
    shutil.copyfile(SCRIPT, script)
    (tmp_path / f"freoa_verifica-{freoa_verifica.__version__}-py3-none-any.whl").write_bytes(b"wheel falso")
    (tmp_path / "python.cmd").write_text("@echo off\r\nexit /b 23\r\n")  # para na etapa seguinte à attestation
    if gh is not None:
        (tmp_path / "gh.cmd").write_text(gh)
    wrapper = tmp_path / "wrapper.ps1"
    wrapper.write_text(WRAPPER, encoding="utf-8-sig")
    env = dict(os.environ, USERPROFILE=str(tmp_path / "user"), LOCALAPPDATA=str(tmp_path / "local"), PATH=str(tmp_path))
    args = [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(wrapper), str(script)]
    run = subprocess.run(args + (["-SemAttestation"] if sem_attestation else []),
                         env=env, capture_output=True, text=True, timeout=60)
    registro = tmp_path / "local/freoa-verifica/instalacao.json"
    record = json.loads(registro.read_text(encoding="utf-8-sig")) if registro.exists() else None
    return run, run.stdout + run.stderr, record


def test_default_version_matches_package():
    text = SCRIPT.read_text(encoding="utf-8-sig")
    assert re.search(r'\[string\]\$Versao = "([^"]+)"', text).group(1) == freoa_verifica.__version__


def test_registro_final_so_ao_fim_com_digest_do_snapshot():
    texto = SCRIPT.read_text(encoding="utf-8-sig")
    assert texto.count("concluida = $true") == 1
    final = texto.index("concluida = $true")
    assert texto.index('$etapa = "doctor offline"') < final
    assert "digest_snapshot = $info.proveniencia.snapshot_sha256" in texto[final - 300:final + 100]
    assert "sha256_wheel = $shaWheel" in texto[final - 300:final + 100]


@pytest.mark.skipif(os.name != "nt", reason="PowerShell Windows")
def test_without_gh_aborts_by_default(tmp_path):
    run, output, record = rodar(tmp_path)
    assert run.returncode != 0 and "Pronto" not in output
    compacto = "".join(output.split())  # o PowerShell quebra linhas do erro no meio das palavras
    assert "FALHOUnaetapa:verificarproveniencia" in compacto and "attestationobrigatoria" in compacto
    assert record is None  # nada gravado nem instalado
    assert not (tmp_path / "user/freoa-verifica/.venv").exists()


@pytest.mark.skipif(os.name != "nt", reason="PowerShell Windows")
def test_failing_gh_aborts_by_default(tmp_path):
    run, output, record = rodar(tmp_path, gh="@echo off\r\nexit /b 1\r\n")
    assert run.returncode != 0 and "exit=1" in output and "Pronto" not in output
    assert record is None


@pytest.mark.skipif(os.name != "nt", reason="PowerShell Windows")
def test_sem_attestation_nao_consulta_gh(tmp_path):
    # -SemAttestation não consulta o gh: mesmo com gh quebrado o instalador segue, marcando false.
    run, output, record = rodar(tmp_path, gh="@echo off\r\nexit /b 1\r\n", sem_attestation=True)
    assert "FALHOU na etapa: criar venv" in output
    assert record["attestation_verificada"] is False and record["concluida"] is False


@pytest.mark.skipif(os.name != "nt", reason="PowerShell Windows")
def test_sem_attestation_proceeds_and_records_false(tmp_path):
    run, output, record = rodar(tmp_path, sem_attestation=True)
    assert "FALHOU na etapa: criar venv" in output  # passou da attestation
    assert record["attestation_verificada"] is False
    assert record["versao"] == freoa_verifica.__version__


@pytest.mark.skipif(os.name != "nt", reason="PowerShell Windows")
def test_verified_attestation_records_true_version_and_commit(tmp_path):
    run, output, record = rodar(tmp_path, gh=GH_JSON)
    assert "FALHOU na etapa: criar venv" in output
    assert record["attestation_verificada"] is True
    assert record["versao"] == freoa_verifica.__version__
    assert record["commit"] == "abc123"
    assert record["proveniencia"] == "VERIFICADA: gh attestation verify"
    # registro parcial (instalação interrompida): ligado ao arquivo baixado, ainda sem digest nem conclusão
    assert record["sha256_wheel"] == hashlib.sha256(b"wheel falso").hexdigest()
    assert record["digest_snapshot"] is None and record["concluida"] is False
