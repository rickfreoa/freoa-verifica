"""Confere que os testes rodam contra o pacote instalado, não o checkout."""

from __future__ import annotations

import os
from pathlib import Path

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
