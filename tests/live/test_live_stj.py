from __future__ import annotations

import pytest

from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.stj import StjConnector

pytestmark = pytest.mark.live


def test_live_stj_positivo():
    meta = StjConnector().package_show("espelhos-de-acordaos-primeira-turma")
    assert meta.get("resources")


def test_live_stj_negativo():
    with pytest.raises(Unavailable):
        StjConnector().package_show("fv-pacote-inexistente-xyz")


def test_live_stj_documento():
    c = StjConnector()
    meta = c.package_show("espelhos-de-acordaos-primeira-turma")
    resources = meta.get("resources") or []
    jsons = [
        r
        for r in resources
        if str(r.get("format", "")).upper() == "JSON" and str(r.get("name", "")).endswith(".json")
    ]
    assert jsons
    jsons.sort(key=lambda r: str(r.get("name") or ""), reverse=True)
    from freoa_verifica.connectors.httputil import connector_fetch

    resp = connector_fetch(
        jsons[0]["url"],
        hosts=c.hosts,
        path_prefixes=c.path_prefixes,
        mimes=c.mimes,
        user_agent=c.user_agent,
        timeout=120.0,
        max_bytes=30 * 1024 * 1024,
    )
    parsed = c.parse(resp)
    assert parsed.court == "STJ"
