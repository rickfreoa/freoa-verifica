"""FIX9/F-12: o README traz as instruções correntes da 1.3.0 e a exigência de attestation."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from freoa_verifica import __version__

README = Path(__file__).resolve().parents[1] / "README.md"

pytestmark = pytest.mark.repositorio


def test_instalacao_aponta_para_a_versao_corrente():
    texto = README.read_text(encoding="utf-8")
    secao = texto.split("## Instalação", 1)[1].split("## ", 1)[0]
    assert __version__ == "1.3.0"
    versoes = set(re.findall(r"v(\d+\.\d+\.\d+)", secao))
    assert versoes == {__version__}
    assert f"## Estado atual ({__version__})" in texto


def test_attestation_obrigatoria_com_excecao_explicita():
    texto = README.read_text(encoding="utf-8")
    assert "-SemAttestation" in texto
    assert "quando instalado" not in texto
    assert "exige e confere a attestation" in texto
