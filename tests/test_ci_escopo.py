"""CI em camadas: só PR de registro dispensa a matriz; nada mais, e nunca por falha (scripts/ci_escopo.py)."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.repositorio

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("ci_escopo", ROOT / "scripts" / "ci_escopo.py")
ce = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ce)


@pytest.mark.parametrize("arquivos", [
    ["docs/decisoes/0087-reordenacao-sessao-assistida.md"],
    ["docs/auditoria/1.4.0/release-1.4.0a5.md", "docs/auditoria/1.4.0/bench/freoa_raw.jsonl"],
])
def test_registro_dispensa(arquivos):
    assert ce.so_registro(arquivos) is True


@pytest.mark.parametrize("arquivos", [
    [],
    ["docs/CONTRATO.md"],
    ["README.md"],
    ["docs/decisoes/0087.md", "freoa_verifica/service.py"],
    ["docs/auditoria/1.4.0/s0-rodada1/s0_runner.py"],
    ["docs/decisoes/../../freoa_verifica/x.md"],
    ["docs\\decisoes\\x.md"],
    ["/docs/decisoes/x.md"],
    [".github/workflows/ci.yml"],
    ["tests/fixtures/FIXTURES.json"],
])
def test_qualquer_outro_caminho_exige_matriz(arquivos):
    assert ce.so_registro(arquivos) is False


@pytest.mark.parametrize("evento", ["push", "workflow_call", "workflow_dispatch", ""])
def test_fora_de_pull_request_sempre_matriz(evento, monkeypatch):
    monkeypatch.setattr(ce.subprocess, "run", lambda *a, **k: pytest.fail("não deveria consultar o git"))
    assert ce.decidir(evento, "a" * 40, "b" * 40) is False


def test_pull_request_sem_shas_exige_matriz():
    assert ce.decidir("pull_request", "", "b" * 40) is False


def test_erro_do_git_derruba_o_job(monkeypatch):
    def falha(*a, **k):
        raise subprocess.CalledProcessError(128, a[0])
    monkeypatch.setattr(ce.subprocess, "run", falha)
    with pytest.raises(subprocess.CalledProcessError):
        ce.decidir("pull_request", "a" * 40, "b" * 40)


def test_diff_por_merge_base_sem_renomeacao(monkeypatch):
    visto = {}

    class R:
        stdout = "docs/decisoes/0088.md\0".encode()

    def run(cmd, **k):
        visto["cmd"], visto["check"] = cmd, k.get("check")
        return R()
    monkeypatch.setattr(ce.subprocess, "run", run)
    assert ce.decidir("pull_request", "a" * 40, "b" * 40) is True
    assert visto["check"] is True and "--no-renames" in visto["cmd"] and f"{'a' * 40}...{'b' * 40}" in visto["cmd"]


def test_workflow_falha_fechada():
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    teste = ci.split("\n  test:\n", 1)[1].split("\n  repositorio:", 1)[0]
    assert "needs: escopo" in teste
    assert "if: ${{ !cancelled() && needs.escopo.outputs.so_registro != 'true' }}" in teste
    repositorio = ci.split("\n  repositorio:\n", 1)[1].split("\n  lint:\n", 1)[0]
    lint = ci.split("\n  lint:\n", 1)[1]
    for bloco in (repositorio, lint):
        assert "needs:" not in bloco and "if:" not in bloco, "repositorio e lint rodam sempre"
    assert "workflow_call" in ci and "fetch-depth: 0" in ci
