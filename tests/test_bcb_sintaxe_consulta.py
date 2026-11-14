"""BCB: a borda recusa `Propriedade="valor"` (página HTML "Requisição inválida!", status 200).

A consulta usa `Propriedade:"valor"`, que casa por frase contida; a igualdade de tipo e
número passa a ser conferida no cliente. Fixtures sintéticas, sem rede.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import unquote

import pytest

from freoa_verifica.connectors import bcb
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.transport import Response


def _resp(url: str, corpo: bytes, mime: str = "application/json") -> Response:
    agora = datetime.now(timezone.utc).isoformat()
    return Response(url, url, 200, {}, corpo, hashlib.sha256(corpo).hexdigest(), agora, [], mime)


def _linha(tipo: str, numero: str) -> dict:
    return {"title": f"{tipo} {numero}", "TipodoNormativoOWSCHCS": tipo,
            "NumeroOWSNMBR": f"{numero}.00000000000", "RevogadoOWSBOOL": "0"}


def _captura(monkeypatch, linhas: list[dict]) -> list[str]:
    urls: list[str] = []
    corpo = json.dumps({"TotalRows": len(linhas), "Rows": linhas}).encode()

    def fake(url, **kw):
        urls.append(url)
        return _resp(url, corpo)

    monkeypatch.setattr(bcb, "connector_fetch", fake)
    return urls


@pytest.mark.parametrize("consulta,filtros", [
    ("Resolução CMN 4.966", {}),
    ("", {"tipo": "Circular", "numero": 3978}),
    ("", {"tipo": 'Comunicado"x', "numero": 1}),
    ("crédito rural", {}),
])
def test_consulta_nunca_usa_igual_aspas(monkeypatch, consulta, filtros):
    urls = _captura(monkeypatch, [])
    bcb.BcbConnector().search(consulta, **filtros)
    q = unquote(urls[0])
    assert '="' not in q and "=%22" not in urls[0]
    assert "OWSCHCS=" not in q and "OWSNMBR=" not in q


def test_tipo_e_numero_exatos_conferidos_no_cliente(monkeypatch):
    _captura(monkeypatch, [_linha("Resolução BCB", "4966"), _linha("Comunicado", "4966"),
                           _linha("Resolução CMN", "49660"), _linha("Resolução CMN", "4966")])
    out = bcb.BcbConnector().search("", tipo="Resolução CMN", numero=4966)
    assert [(c.metadata["tipo"], c.metadata["numero"]) for c in out] == [("Resolução CMN", "4966")]
    assert out.total == 1


def test_resolucao_cmn_aceita_tipo_resolucao_anterior_a_2020(monkeypatch):
    _captura(monkeypatch, [_linha("Resolução", "2827"), _linha("Resolução BCB", "2827")])
    out = bcb.BcbConnector().search("", tipo="Resolução CMN", numero=2827)
    assert [c.metadata["tipo"] for c in out] == ["Resolução"]


def test_pagina_de_recusa_da_borda_continua_resposta_invalida(monkeypatch):
    html = ("<?xml version=\"1.0\"?><html><head><title>Requisição inválida!</title></head>"
            "<body>x</body></html>").encode()
    monkeypatch.setattr(bcb, "connector_fetch", lambda url, **kw: _resp(url, html, "text/html"))
    with pytest.raises(Unavailable) as exc:
        bcb.BcbConnector().search("Resolução CMN 4.966")
    assert exc.value.reason == "resposta_invalida"
