"""FIX10/F-12: o README descreve `snapshot install` conforme a decisão 0051 (só a release da versão instalada)."""

from __future__ import annotations

from pathlib import Path

import pytest

README = Path(__file__).resolve().parents[1] / "README.md"

pytestmark = pytest.mark.repositorio


def test_snapshot_install_so_a_release_da_versao_instalada():
    texto = README.read_text(encoding="utf-8")
    assert "mais recente cujo snapshot" not in texto
    paragrafo = next(p for p in texto.split("\n") if "fv snapshot install" in p and "versao_pacote_min" in p)
    for termo in ("somente a release", "SNAPSHOT_OUTRA_VERSAO", "SNAPSHOT_NAO_VINCULADO", "--aceitar-nao-vinculado"):
        assert termo in paragrafo
