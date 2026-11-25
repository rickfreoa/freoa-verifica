"""Confere que os testes rodam contra o pacote instalado, não o checkout."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import sysconfig

import pytest

import freoa_verifica


def test_installed_package():
    """Com FV_TEST_INSTALLED=1, __file__ não pode estar sob o checkout do repo."""
    if os.environ.get("FV_TEST_INSTALLED") != "1":
        return
    repo_root = Path(__file__).resolve().parents[1]
    installed = Path(freoa_verifica.__file__).resolve()
    try:
        installed.relative_to(repo_root)
        in_checkout = True
    except ValueError:
        in_checkout = False
    assert not in_checkout, (
        f"freoa_verifica.__file__={installed} ainda sob o checkout {repo_root}; "
        "o CI deve instalar o wheel e rodar pytest fora do repositório "
        "(PYTHONSAFEPATH=1)."
    )


@pytest.mark.skipif(sys.platform != "win32", reason="launcher instalado Windows")
def test_fv_sessao_instalado_recusa_pipe_indisponivel(tmp_path):
    """§3(16): launcher real; só as pré-condições e o pipe são simulados, sem navegador."""
    fv = Path(sysconfig.get_path("scripts")) / "fv.exe"
    assert fv.is_file(), "entry point fv não foi instalado"
    env = {
        **os.environ,
        "FV_HOME": str(tmp_path / "home"),
        "FV_OFFLINE": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    ajuda = subprocess.run(
        [str(fv), "sessao", "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert (
        ajuda.returncode == 0
        and "planalto" in ajuda.stdout
        and "normas_leg" in ajuda.stdout
    )
    # Python do launcher instalado carrega este cenário de falha de infraestrutura.
    # Nenhuma API do adaptador/transporte nem o despachante CLI é substituída.
    (tmp_path / "sitecustomize.py").write_text(
        """
import builtins
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from freoa_verifica import transport
from freoa_verifica.assistida import ambiente as a, sessao as s

def pipe_indisponivel(*args, **kwargs):
    raise OSError(5, "pipe indisponivel sintetico", None, 5)

def rede_vedada(*args, **kwargs):
    raise AssertionError("rede vedada no teste de instalacao")

s.conferir_terminal = lambda: None
builtins.input = lambda _: "INICIAR"
a.navegador_instalado = lambda _: ("brave", Path("navegador-sintetico.exe"))
a.conferir_politicas = lambda _: None
a.proteger_diretorio = lambda _: None
a.lock_sessao = lambda _: nullcontext()
a._processos_do_perfil = lambda *args: set()
a.ObservadorWindows = lambda _: SimpleNamespace(fechar=lambda: None)
a.subprocess.Popen = pipe_indisponivel
transport.fetch = rede_vedada
""",
        encoding="utf-8",
    )
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, (str(tmp_path), env.get("PYTHONPATH")))
    )
    run = subprocess.run(
        [str(fv), "sessao", "planalto"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert run.returncode == 2, run.stdout + run.stderr
    assert "Sessão recusada: PIPE_ASSISTIDO_INDISPONIVEL" in run.stdout
    assert "Capturas gravadas" not in run.stdout
    assert not (tmp_path / "home" / "verifica.sqlite3").exists()
    assert not list(
        (tmp_path / "home" / "staging" / "sessoes-assistidas").glob("sessao-0089-*")
    )
