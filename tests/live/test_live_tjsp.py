from __future__ import annotations

import pytest

from freoa_verifica.connectors.tjsp import TjspConnector

pytestmark = pytest.mark.live


def test_live_tjsp_positivo():
    found = TjspConnector().search("acordo de acionistas", limite=3)
    assert found


def test_live_tjsp_negativo():
    found = TjspConnector().search("FVXYZTERMOSINTETICO99991QWERTY", limite=5)
    assert found == []


def test_live_tjsp_documento():
    c = TjspConnector()
    found = c.search("acordo de acionistas", limite=1)
    assert found
    resp = c.fetch(found[0])
    assert resp.body[:4] == b"%PDF"
