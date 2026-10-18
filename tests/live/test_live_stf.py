from __future__ import annotations

import pytest

from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.stf import StfConnector

pytestmark = pytest.mark.live


def test_live_stf_positivo():
    cand = StfConnector().resolve({"classe": "ADI", "numero": 7000})
    assert cand is not None
    assert cand.metadata.get("incidente")


def test_live_stf_negativo_busca_waf():
    with pytest.raises(Unavailable) as ei:
        StfConnector().search("liberdade de expressão", forcar_textual=True)
    assert "stf_busca_textual_sob_waf" in ei.value.reason or "desafio" in ei.value.reason


def test_live_stf_documento():
    c = StfConnector()
    cand = c.resolve({"classe": "ADI", "numero": 7000})
    assert cand is not None
    items = c.list_decisoes(cand.metadata["incidente"])
    assert items
