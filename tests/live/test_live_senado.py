from __future__ import annotations

import pytest

from freoa_verifica.connectors.senado import SenadoConnector

pytestmark = pytest.mark.live


def test_live_senado_positivo():
    found = SenadoConnector().search("", tipo="LEI", numero=10303, ano=2001)
    assert found
    assert found[0].metadata.get("dataassinatura_iso")


def test_live_senado_negativo():
    found = SenadoConnector().search("", tipo="LEI", numero=999999, ano=2099)
    assert found == []


def test_live_senado_documento():
    c = SenadoConnector()
    cand = c.resolve({"tipo": "LEI", "numero": 10303, "ano": 2001})
    assert cand is not None
    doc = c.parse(c.fetch(cand))
    assert doc.title
