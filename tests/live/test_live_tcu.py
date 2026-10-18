from __future__ import annotations

import pytest

from freoa_verifica.connectors.tcu import TcuConnector

pytestmark = pytest.mark.live


def test_live_tcu_positivo():
    found = TcuConnector().search("", inicio=0, quantidade=2)
    assert found


def test_live_tcu_negativo():
    found = TcuConnector().search("FV_TERM_INEXISTENTE_TCU_XYZ_999991", quantidade=5)
    assert found == []


def test_live_tcu_documento():
    c = TcuConnector()
    found = c.search("", inicio=0, quantidade=1)
    assert found
    parsed = c.parse(c.fetch(found[0]))
    assert parsed.court == "TCU"
