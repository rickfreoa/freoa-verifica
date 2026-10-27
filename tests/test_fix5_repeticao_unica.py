"""FIX5/F-02: a política de repetição vive só no transporte (um prazo, um teto, um incremento no breaker)."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from freoa_verifica import transport
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.planalto import PlanaltoConnector
from tests.test_transport import _fast_guards, _wire_local
from tests.esperas_util import so_desta_thread




def _servidor_503(retry_after: str | None = None):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            return

        def do_GET(self):  # noqa: N802
            self.server.pedidos += 1
            self.send_response(503)
            if retry_after is not None:
                self.send_header("Retry-After", retry_after)
            self.send_header("Content-Length", "0")
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), H)
    server.pedidos = 0
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _executar(monkeypatch, server):
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    esperas: list[float] = []
    monkeypatch.setattr(transport, "_dormir", esperas.append)
    monkeypatch.setattr("time.sleep", so_desta_thread(esperas))  # nenhum laço externo pode dormir de verdade
    c = PlanaltoConnector()
    cand = c.resolve({"tipo": "LEI", "numero": 6404, "ano": 1976})
    breaker = None
    try:
        with pytest.raises(Unavailable) as ei:
            c.fetch(cand)
        breaker = transport._circuit_breaker("www.planalto.gov.br")
    finally:
        server.shutdown()
        server.server_close()
    return ei.value, breaker, esperas


def test_503_persistente_no_planalto_faz_no_maximo_tres_tentativas_e_um_incremento_no_breaker(monkeypatch):
    server = _servidor_503()
    u, breaker, esperas = _executar(monkeypatch, server)
    assert u.reason == "http_503" and u.categoria == "fonte_fora"
    assert server.pedidos == 3  # 1 + 2 repetições do transporte
    assert len(esperas) == 2
    assert breaker.failures == 1


def test_retry_after_longo_no_planalto_nao_gera_nova_requisicao(monkeypatch):
    server = _servidor_503("3600")
    u, breaker, esperas = _executar(monkeypatch, server)
    assert u.reason == "http_503"
    assert server.pedidos == 1
    assert esperas == []
    assert breaker.failures == 1
