from __future__ import annotations

import pytest

from freoa_verifica.connectors.cvm_normas import CvmNormasConnector

pytestmark = pytest.mark.live


def test_live_cvm_normas_positivo():
    found = CvmNormasConnector().search("Resolução CVM 80", tipo="resolucoes", numero=80)
    assert found


def test_live_cvm_normas_negativo():
    # resolve de número absurdo ainda gera URL; fetch deve falhar ou página soft
    c = CvmNormasConnector()
    cand = c.resolve({"tipo": "resolucoes", "numero": 99999})
    assert cand is not None
    with pytest.raises(Exception):
        c.fetch(cand)


def test_live_cvm_normas_documento():
    c = CvmNormasConnector()
    cand = c.resolve({"tipo": "resolucoes", "numero": 80})
    assert cand is not None
    doc = c.parse(c.fetch(cand))
    assert doc.title or doc.text
