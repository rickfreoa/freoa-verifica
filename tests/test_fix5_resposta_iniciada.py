"""FIX5/F-01: interrupção (taxa, tamanho, prazo) depois do status é `resposta_inesperada`, sem repetição.

Ponta a ponta: servidor local real (200, byte parcial, gotejamento abaixo da taxa mínima) → transporte →
conector Planalto e TJDFT → hook live: FALHA, uma única tentativa.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from freoa_verifica import transport
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.planalto import PlanaltoConnector
from freoa_verifica.connectors.tjdft import TjdftConnector
from tests.test_transport import _fast_guards, _wire_local

pytest_plugins = ["pytester"]
_CONFTEST = "from tests.live.conftest import pytest_runtest_makereport  # noqa: F401\n"


def _servidor(content_type: str):
    parar = threading.Event()

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            return

        def _gotejar(self):
            self.server.pedidos += 1
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", "1000")
            self.end_headers()
            self.wfile.write(b"x")  # 1 byte e pausa: taxa abaixo do mínimo, resposta já iniciada
            self.wfile.flush()
            parar.wait(10)
            self.close_connection = True

        def do_GET(self):  # noqa: N802
            self._gotejar()

        def do_POST(self):  # noqa: N802
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            self._gotejar()

    server = ThreadingHTTPServer(("127.0.0.1", 0), H)
    server.pedidos = 0
    server.parar = parar
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _planalto():
    c = PlanaltoConnector()
    return c.fetch(c.resolve({"tipo": "LEI", "numero": 6404, "ano": 1976}))


def _tjdft():
    return TjdftConnector().search("0001234-56.2024.8.07.0001")


@pytest.mark.parametrize("conector,tipo", [(_planalto, "text/html"), (_tjdft, "application/json")], ids=["planalto", "tjdft"])
def test_gotejamento_apos_status_e_resposta_inesperada_uma_tentativa_e_hook_falha(monkeypatch, pytester, conector, tipo):
    server = _servidor(tipo)
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    monkeypatch.setattr(transport, "SLOW_WINDOW", 0.05)
    monkeypatch.setattr(transport, "_dormir", lambda s: None)
    try:
        with pytest.raises(Unavailable) as ei:
            conector()
    finally:
        server.parar.set()
        server.shutdown()
        server.server_close()
    u = ei.value
    assert server.pedidos == 1
    assert u.categoria == "resposta_inesperada"
    assert u.evidencia["marcador"] == "transporte:TransporteLento"
    pytester.makeconftest(_CONFTEST)
    pytester.makeini("[pytest]\nmarkers =\n    live: x\n")
    pytester.makepyfile(
        "import pytest\nfrom freoa_verifica.connectors.base import Unavailable\n"
        "@pytest.mark.live\ndef test_x():\n"
        f"    raise Unavailable({u.reason!r}, {u.categoria!r}, {u.evidencia!r})\n"
    )
    pytester.runpytest("-p", "no:cacheprovider").assert_outcomes(failed=1)


def test_transporte_lento_e_resposta_invalida():
    assert issubclass(transport.TransporteLento, transport.RespostaInvalida)
