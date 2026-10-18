from __future__ import annotations

import pytest

from freoa_verifica.connectors.bcb import BcbConnector

pytestmark = pytest.mark.live


def test_live_bcb_positivo():
    found = BcbConnector().search("", tipo="Resolução CMN", numero=4966, limite=2)
    assert found


def test_live_bcb_negativo():
    found = BcbConnector().search("FV_TERM_INEXISTENTE_XYZ_999", limite=5)
    assert found == []


def test_live_bcb_documento():
    c = BcbConnector()
    cand = c.resolve({"tipo": "Resolução CMN", "numero": 4966})
    assert cand is not None
    resp = c.fetch(cand)
    assert b"4966" in resp.body
    assert b"conteudo" in resp.body or b"Titulo" in resp.body
