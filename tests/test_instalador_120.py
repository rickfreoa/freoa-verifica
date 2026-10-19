"""A10: execução real no PowerShell e inventário AST das chamadas nativas."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/instalar-freoa-verifica.ps1"


@pytest.mark.skipif(os.name != "nt", reason="PowerShell Windows")
def test_installer_native_failure_stops(tmp_path):
    powershell = shutil.which("powershell")
    if not powershell:
        pytest.skip("PowerShell não disponível")
    script = tmp_path / SCRIPT.name
    shutil.copyfile(SCRIPT, script)
    (tmp_path / "freoa_verifica-1.2.0-py3-none-any.whl").write_bytes(b"wheel falso")
    (tmp_path / "gh.cmd").write_text("@echo off\r\nexit /b 37\r\n")
    env = dict(os.environ, USERPROFILE=str(tmp_path / "user"), LOCALAPPDATA=str(tmp_path / "local"))
    env["PATH"] = str(tmp_path) + os.pathsep + env["PATH"]
    run = subprocess.run([powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                         env=env, capture_output=True, text=True, timeout=30)
    assert run.returncode != 0
    output = run.stdout + run.stderr
    assert "FALHOU na etapa: verificar proveniencia" in output
    assert "exit=37" in output
    assert "Pronto" not in output
    assert not (tmp_path / "user/freoa-verifica/.venv").exists()


@pytest.mark.skipif(os.name != "nt", reason="AST do PowerShell Windows")
def test_all_native_invocations_guarded(tmp_path):
    powershell = shutil.which("powershell")
    if not powershell:
        pytest.skip("PowerShell não disponível")
    # Só uma chamada & no AST inteiro, dentro do guard que confere o exit.
    code = """
param($Source)
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($Source,[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw $errors }
$calls=$ast.FindAll({param($n) $n -is [System.Management.Automation.Language.CommandAst] -and $n.InvocationOperator -eq 'Ampersand'},$true)
if ($calls.Count -ne 1) { throw 'chamadas nativas sem guard' }
$parent=$calls[0].Parent
while ($parent -and $parent -isnot [System.Management.Automation.Language.FunctionDefinitionAst]) { $parent=$parent.Parent }
if ($parent.Name -ne 'Invoke-NativeChecked') { throw 'guard ausente' }
"""
    check = tmp_path / "check.ps1"
    check.write_text(code, encoding="utf-8-sig")
    run = subprocess.run([powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(check), str(SCRIPT)],
                         capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stdout + run.stderr
    text = SCRIPT.read_text(encoding="utf-8-sig")
    assert '$resultado = & $Comando @Argumentos\n    $codigo = $LASTEXITCODE' in text


@pytest.mark.skipif(os.name != "nt", reason="PowerShell Windows")
def test_without_gh_records_warning_and_python_failure(tmp_path):
    import json
    powershell = shutil.which("powershell")
    if not powershell:
        pytest.skip("PowerShell não disponível")
    script = tmp_path / SCRIPT.name
    shutil.copyfile(SCRIPT, script)
    (tmp_path / "freoa_verifica-1.2.0-py3-none-any.whl").write_bytes(b"wheel falso")
    (tmp_path / "python.cmd").write_text("@echo off\r\nexit /b 23\r\n")
    wrapper = tmp_path / "wrapper.ps1"
    wrapper.write_text("""
param($Installer)
function Invoke-WebRequest {
    param($Uri, $OutFile, [switch]$UseBasicParsing)
    Set-Content -LiteralPath $OutFile -Value '# lock sintetico'
}
& $Installer -SemAttestation
exit $LASTEXITCODE
""", encoding="utf-8-sig")
    env = dict(os.environ, USERPROFILE=str(tmp_path / "user"), LOCALAPPDATA=str(tmp_path / "local"))
    env["PATH"] = str(tmp_path)  # nenhum gh; somente python.cmd falso
    run = subprocess.run([powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(wrapper), str(script)],
                         env=env, capture_output=True, text=True, timeout=30)
    output = run.stdout + run.stderr
    assert run.returncode != 0 and "Pronto" not in output
    assert "FALHOU na etapa: criar venv" in output and "exit=23" in output
    record = json.loads((tmp_path / "local/freoa-verifica/instalacao.json").read_text(encoding="utf-8-sig"))
    expected = "PROVENIENCIA NAO VERIFICADA (-SemAttestation)"
    assert expected in output and record["proveniencia"] == expected
    assert record["attestation_verificada"] is False
    assert record["concluida"] is False
