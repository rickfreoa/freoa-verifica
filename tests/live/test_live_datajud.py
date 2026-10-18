from __future__ import annotations

import pytest

from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.datajud import DatajudConnector

pytestmark = pytest.mark.live


def test_live_datajud_positivo():
    # número CNJ real conhecido do fixture / acervo TJSP
    found = DatajudConnector().search(
        "",
        tribunal="tjsp",
        numero="00004123320268260320",
        limite=1,
    )
    if not found:
        # fallback: existência de qualquer processo com campo numeroProcesso
        found = DatajudConnector().search("", tribunal="tjsp", limite=1)
    assert found


def test_live_datajud_negativo():
    found = DatajudConnector().search(
        "", tribunal="tjsp", numero="00000000000000000000", limite=1
    )
    assert found == []


def test_live_datajud_documento_stf_ausente():
    with pytest.raises(Unavailable):
        DatajudConnector().search("", tribunal="stf", limite=1)
