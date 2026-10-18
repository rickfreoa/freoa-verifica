from __future__ import annotations

import pytest

from freoa_verifica.connectors.cvm_colegiado import CvmColegiadoConnector

pytestmark = pytest.mark.live


def test_live_cvm_colegiado_positivo():
    found = CvmColegiadoConnector().search("", limite=3)
    assert found


def test_live_cvm_colegiado_negativo():
    found = CvmColegiadoConnector().search("FV_TERM_INEXISTENTE_COLEGIADO_XYZ_999", limite=5)
    assert found == []


def test_live_cvm_colegiado_documento():
    c = CvmColegiadoConnector()
    found = c.search("", limite=1)
    assert found
    parsed = c.parse(c.fetch(found[0]))
    assert parsed.court == "CVM"
    assert parsed.official_id
    assert parsed.text
