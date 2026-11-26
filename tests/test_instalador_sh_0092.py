"""0092: instalador para Linux e macOS, com as mesmas garantias do instalador do Windows."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

import freoa_verifica

pytestmark = pytest.mark.repositorio  # lê scripts/ do checkout; o job da wheel só leva o instalador do Windows

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/instalar-freoa-verifica.sh"
PS1 = SCRIPT.with_suffix(".ps1")
CURL_200 = '#!/bin/sh\n# curl falso: grava um lock sintético e responde 200\nwhile [ $# -gt 0 ]; do [ "$1" = -o ] && { echo "# lock" > "$2"; shift; }; shift; done\nprintf 200\n'


def test_versao_padrao_igual_a_do_pacote_e_a_do_ps1():
    texto = SCRIPT.read_text(encoding="utf-8")
    assert re.search(r'^VERSAO="([^"]+)"', texto, re.M).group(1) == freoa_verifica.__version__
    assert re.search(r'\[string\]\$Versao = "([^"]+)"', PS1.read_text(encoding="utf-8-sig")).group(1) == freoa_verifica.__version__


def test_ordem_das_etapas_e_registro_final():
    texto = SCRIPT.read_text(encoding="utf-8")
    ordem = ["verificar proveniencia", "baixar lock", "criar venv", "instalar wheel", "validar versao",
             "preservar acervo anterior", "instalar snapshot", "validar acervo", "doctor offline", "agendar manutencao"]
    posicoes = [texto.index(f'ETAPA="{e}"') for e in ordem]
    assert posicoes == sorted(posicoes)
    assert texto.rindex('"$AGENDAMENTO" 1') > posicoes[-1]  # concluida=1 só depois do agendamento
    assert "export PIP_DISABLE_PIP_VERSION_CHECK=1" in texto
    assert "fv_json acervo agendar --instalar" in texto and "--sem-agendamento" in texto


@pytest.mark.skipif(shutil.which("bash") is None or os.name == "nt", reason="bash de Linux/macOS")
def test_sintaxe_bash():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def _rodar(tmp_path, *args, gh=None, uid="1000", curl=CURL_200):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for nome in ("python3", "sed", "cut", "grep", "mkdir", "cp", "date", "mv", "rm", "dirname", "cat", "sha256sum",
                 "shasum", "printf"):
        real = shutil.which(nome)
        if real:
            (bin_dir / nome).symlink_to(real)
    (bin_dir / "curl").write_text(curl)
    (bin_dir / "curl").chmod(0o755)
    (bin_dir / "id").write_text(f"#!/bin/sh\necho {uid}\n")  # a sessão de teste pode rodar como root
    (bin_dir / "id").chmod(0o755)
    if gh is not None:
        (bin_dir / "gh").write_text(gh)
        (bin_dir / "gh").chmod(0o755)
    script = tmp_path / SCRIPT.name
    shutil.copyfile(SCRIPT, script)
    (tmp_path / f"freoa_verifica-{freoa_verifica.__version__}-py3-none-any.whl").write_bytes(b"wheel falso")
    env = {"HOME": str(tmp_path / "user"), "PATH": str(bin_dir)}
    run = subprocess.run([shutil.which("bash"), str(script), *args], env=env, capture_output=True, text=True,
                         timeout=300)
    registro = tmp_path / "user/.local/share/freoa-verifica/instalacao.json"
    dados = json.loads(registro.read_text(encoding="utf-8")) if registro.exists() else None
    if registro.exists():
        assert registro.stat().st_mode & 0o077 == 0  # umask 077: registro sem acesso de terceiros
    return run, run.stdout + run.stderr, dados


@pytest.mark.skipif(shutil.which("bash") is None or os.name == "nt", reason="bash de Linux/macOS")
def test_sem_gh_interrompe_sem_registro(tmp_path):
    run, saida, registro = _rodar(tmp_path)
    assert run.returncode != 0 and "FALHOU na etapa: verificar proveniencia" in saida and "attestation obrigatoria" in saida
    assert registro is None and not (tmp_path / "user/freoa-verifica/.venv").exists()


@pytest.mark.skipif(shutil.which("bash") is None or os.name == "nt", reason="bash de Linux/macOS")
def test_gh_recusando_interrompe(tmp_path):
    run, saida, registro = _rodar(tmp_path, gh="#!/bin/sh\nexit 1\n")
    assert run.returncode != 0 and "FALHOU na etapa: verificar proveniencia" in saida and registro is None


@pytest.mark.skipif(shutil.which("bash") is None or os.name == "nt", reason="bash de Linux/macOS")
def test_attestation_verificada_grava_commit_e_para_no_wheel_falso(tmp_path):
    gh = ('#!/bin/sh\necho \'[{"verificationResult":{"signature":{"certificate":'
          '{"sourceRepositoryDigest":"abc123"}}}}]\'\n')
    run, saida, registro = _rodar(tmp_path, gh=gh)
    assert "FALHOU na etapa: instalar wheel" in saida  # passou por attestation, lock e venv
    assert registro["attestation_verificada"] is True and registro["commit"] == "abc123"
    assert registro["versao"] == freoa_verifica.__version__ and registro["concluida"] is False
    assert registro["digest_snapshot"] is None


@pytest.mark.skipif(shutil.which("bash") is None or os.name == "nt", reason="bash de Linux/macOS")
def test_sem_attestation_registra_false(tmp_path):
    run, saida, registro = _rodar(tmp_path, "--sem-attestation")
    assert "PROVENIENCIA NAO VERIFICADA" in saida and "FALHOU na etapa: instalar wheel" in saida
    assert registro["attestation_verificada"] is False and registro["concluida"] is False


@pytest.mark.skipif(shutil.which("bash") is None or os.name == "nt", reason="bash de Linux/macOS")
def test_root_e_recusado_antes_de_gravar(tmp_path):
    run, saida, registro = _rodar(tmp_path, "--sem-attestation", uid="0")
    assert run.returncode != 0 and "nao como root" in saida
    assert registro is None and not (tmp_path / "user/freoa-verifica").exists()


@pytest.mark.skipif(shutil.which("bash") is None or os.name == "nt", reason="bash de Linux/macOS")
def test_lock_ausente_interrompe_sem_renuncia(tmp_path):
    gh = ('#!/bin/sh\necho \'[{"verificationResult":{"signature":{"certificate":'
          '{"sourceRepositoryDigest":"abc123"}}}}]\'\n')
    bin_404 = '#!/bin/sh\nwhile [ $# -gt 0 ]; do [ "$1" = -o ] && { : > "$2"; shift; }; shift; done\nprintf 404\n'
    run, saida, registro = _rodar(tmp_path, gh=gh, curl=bin_404)
    assert "FALHOU na etapa: baixar lock" in saida and "sem hash" in saida
    assert registro["concluida"] is False and not (tmp_path / "user/freoa-verifica/.venv").exists()


@pytest.mark.skipif(shutil.which("bash") is None or os.name == "nt", reason="bash de Linux/macOS")
def test_instalacao_anterior_com_escrita_de_terceiros_e_corrigida_ou_recusada(tmp_path):
    destino = tmp_path / "user/freoa-verifica"
    destino.mkdir(parents=True)
    (destino / "velho.txt").write_text("x")
    (destino / "velho.txt").chmod(0o666)
    destino.chmod(0o777)
    run, saida, registro = _rodar(tmp_path, "--sem-attestation")
    assert "FALHOU na etapa: instalar wheel" in saida  # passou da conferência
    assert destino.stat().st_mode & 0o022 == 0 and (destino / "velho.txt").stat().st_mode & 0o022 == 0


@pytest.mark.skipif(shutil.which("bash") is None or os.name == "nt", reason="bash de Linux/macOS")
def test_destino_link_simbolico_e_recusado(tmp_path):
    alheio = tmp_path / "alheio"
    alheio.mkdir()
    (tmp_path / "user").mkdir()
    (tmp_path / "user/freoa-verifica").symlink_to(alheio)
    run, saida, registro = _rodar(tmp_path, "--sem-attestation")
    assert "FALHOU na etapa: conferir permissoes" in saida and "link simbolico" in saida and registro is None


@pytest.mark.skipif(shutil.which("bash") is None or os.name == "nt", reason="bash de Linux/macOS")
def test_link_interno_para_arvore_gravavel_por_terceiros_e_recusado(tmp_path):
    externo = tmp_path / "externo"
    (externo / "bin").mkdir(parents=True)
    externo.chmod(0o777)
    destino = tmp_path / "user/freoa-verifica"
    destino.mkdir(parents=True)
    (destino / ".venv").symlink_to(externo)
    run, saida, registro = _rodar(tmp_path, "--sem-attestation")
    assert "FALHOU na etapa: conferir permissoes" in saida and "gravavel por grupo ou outros" in saida
    assert registro is None


def _funcao(texto: str, nome: str) -> str:
    inicio = texto.index(f"{nome}() {{")
    fim = texto.index("\n}\n", inicio) + 3
    return texto[inicio:fim]


@pytest.mark.skipif(shutil.which("bash") is None or os.name == "nt", reason="bash de Linux/macOS")
def test_falha_do_fv_mostra_o_motivo_e_nao_a_linha(tmp_path):
    """Teste em Debian (0092): snapshot recusado aparecia como "comando com erro (linha 210)"."""
    texto = SCRIPT.read_text(encoding="utf-8")
    fv = tmp_path / "fv"
    fv.write_text('#!/bin/sh\necho \'{"status": "erro", "motivo": "snapshot_http_404"}\'\necho rastro >&2\nexit 1\n')
    fv.chmod(0o755)
    trecho = "\n".join([
        "set -euo pipefail",
        'ETAPA="instalar snapshot"',
        [linha for linha in texto.splitlines() if linha.startswith("falhou() {")][0],
        [linha for linha in texto.splitlines() if linha.startswith("ao_erro() {")][0],
        "trap 'ao_erro $LINENO' ERR",
        _funcao(texto, "fv_json"),
        f'FV="{fv}"; PY="{shutil.which("python3")}"',
        'INST="$(fv_json snapshot install)"',
        "echo nao_deveria_chegar",
    ])
    run = subprocess.run(["bash", "-c", trecho], capture_output=True, text=True, timeout=30)
    assert run.returncode == 3
    assert "FALHOU na etapa: instalar snapshot - fv snapshot install saiu com 1: erro snapshot_http_404" in run.stderr
    assert "comando com erro" not in run.stderr and "nao_deveria_chegar" not in run.stdout
