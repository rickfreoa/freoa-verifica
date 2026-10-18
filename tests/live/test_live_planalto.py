from __future__ import annotations

import pytest

from freoa_verifica.connectors.base import Candidate, Unavailable
from freoa_verifica.connectors.planalto import PlanaltoConnector

pytestmark = pytest.mark.live


def test_live_planalto_positivo():
    c = PlanaltoConnector()
    cand = c.resolve({"tipo": "LEI", "numero": 6404, "ano": 1976})
    assert cand is not None
    resp = c.fetch(cand)
    assert resp.status == 200
    assert len(resp.body) > 1000


def test_live_planalto_negativo():
    c = PlanaltoConnector()
    cand = Candidate(
        source_id="planalto",
        key="LEI:999999:2099",
        title="LEI 999999/2099",
        url="https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2099/lei/l999999.htm",
        metadata={
            "urls": [
                "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2099/lei/l999999.htm"
            ]
        },
    )
    with pytest.raises(Unavailable) as ei:
        c.fetch(cand)
    assert "404" in ei.value.reason


def test_live_planalto_documento():
    c = PlanaltoConnector()
    cand = c.resolve({"tipo": "LEI", "numero": 6404, "ano": 1976})
    assert cand is not None
    resp = c.fetch(cand)
    # corpo HTML da LSA; parse completo depende do perfil (M2/M3)
    assert b"6.404" in resp.body or b"6404" in resp.body
    assert len(resp.body) > 50_000
