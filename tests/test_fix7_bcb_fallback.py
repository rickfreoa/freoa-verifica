"""FIX7/F-07: BCB só segue para o endpoint de conteúdo diante de ausência explícita na busca.

`resolve → fetch` contra servidor local real: desafio, recusa, `fonte_fora` e resposta inválida na
busca propagam com a categoria original e um único pedido; busca vazia estruturada ou 404 permitem
o fallback.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from freoa_verifica import transport
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.bcb import BcbConnector
from tests.test_transport import _fast_guards, _wire_local

_CONTEUDO = json.dumps({"conteudo": [{"Texto": "Art. 1 Texto."}]}).encode()


def _servidor(status: int, corpo: bytes, retry_after: str | None = None):
    """A busca responde `status`/`corpo`; o endpoint de conteúdo sempre responde 200."""

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            return

        def do_GET(self):  # noqa: N802
            self.server.pedidos.append(self.path)
            if "/api/search/" in self.path:
                st, data = status, corpo
            else:
                st, data = 200, _CONTEUDO
            self.send_response(st)
            if retry_after is not None and st != 200:
                self.send_header("Retry-After", retry_after)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), H)
    server.pedidos = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _resolve_fetch(monkeypatch, server):
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    monkeypatch.setattr(transport, "_dormir", lambda s: None)
    c = BcbConnector()
    try:
        cand = c.resolve({"tipo": "Resolução CMN", "numero": "4557"})
        return c.fetch(cand)
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize(
    "status,corpo,retry,categoria",
    [
        (403, b"<html>captcha</html>", None, "ambiental_desafio"),
        (403, b"{}", None, "recusa_identificado"),
        (503, b"{}", "3600", "fonte_fora"),
        (200, b"nao e json", None, "resposta_inesperada"),
    ],
    ids=["captcha", "403", "503_retry_after", "resposta_invalida"],
)
def test_falha_na_busca_propaga_sem_consultar_o_endpoint_de_conteudo(monkeypatch, status, corpo, retry, categoria):
    server = _servidor(status, corpo, retry)
    with pytest.raises(Unavailable) as ei:
        _resolve_fetch(monkeypatch, server)
    assert len(server.pedidos) == 1
    assert ei.value.categoria == categoria


def test_busca_vazia_estruturada_permite_o_fallback(monkeypatch):
    server = _servidor(200, json.dumps({"TotalRows": 0, "Rows": []}).encode())
    resp = _resolve_fetch(monkeypatch, server)
    assert resp.status == 200
    assert len(server.pedidos) == 2


def test_404_na_busca_permite_o_fallback(monkeypatch):
    server = _servidor(404, b"{}")
    resp = _resolve_fetch(monkeypatch, server)
    assert resp.status == 200
    assert len(server.pedidos) == 2
