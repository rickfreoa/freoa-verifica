"""B3-01: timeout depois do status/primeiro byte do corpo é resposta inválida, nunca `fonte_fora`.

Ponta a ponta: servidor local real (200, chunk parcial, pausa) → transporte → classificação → hook live.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from freoa_verifica import transport
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.httputil import connector_fetch
from tests.test_transport import ALLOWED, _fast_guards, _wire_local  # noqa: F401

pytest_plugins = ["pytester"]
_CONFTEST = "from tests.live.conftest import pytest_runtest_makereport  # noqa: F401\n"


def _servidor(*, enviar_corpo: bool, enviar_cabecalhos: bool = True):
    parar = threading.Event()

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            return

        def do_GET(self):  # noqa: N802
            if enviar_cabecalhos:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Transfer-Encoding", "chunked")
                self.send_header("Connection", "close")
                self.end_headers()
                if enviar_corpo:
                    self.wfile.write(b"6\r\n{\"a\":1\r\n")
                self.wfile.flush()
            parar.wait(10)
            self.close_connection = True

    server = ThreadingHTTPServer(("127.0.0.1", 0), H)
    server.parar = parar
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _buscar(monkeypatch, server, timeout=1.0):
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    try:
        with pytest.raises(Unavailable) as ei:
            connector_fetch(
                "https://example.com/", hosts=ALLOWED, path_prefixes=None,
                mimes=frozenset({"application/json"}), timeout=timeout,
            )
    finally:
        server.parar.set()
        server.shutdown()
    return ei.value


@pytest.mark.parametrize("enviar_corpo", [True, False], ids=["chunk_parcial", "so_cabecalhos"])
def test_timeout_apos_resposta_iniciada_e_resposta_inesperada_e_hook_falha(monkeypatch, pytester, enviar_corpo):
    u = _buscar(monkeypatch, _servidor(enviar_corpo=enviar_corpo))
    assert u.categoria == "resposta_inesperada"
    assert u.evidencia["marcador"] == "transporte:RespostaInvalida"
    pytester.makeconftest(_CONFTEST)
    pytester.makeini("[pytest]\nmarkers =\n    live: x\n")
    pytester.makepyfile(
        "import pytest\nfrom freoa_verifica.connectors.base import Unavailable\n"
        "@pytest.mark.live\ndef test_x():\n"
        f"    raise Unavailable({u.reason!r}, {u.categoria!r}, {u.evidencia!r})\n"
    )
    pytester.runpytest("-p", "no:cacheprovider").assert_outcomes(failed=1)


def test_prazo_vencido_na_thread_externa_apos_cabecalhos_e_resposta_invalida(monkeypatch):
    # O controlador de prazo (thread externa) vence primeiro: o worker ainda bloqueado no corpo.
    _fast_guards(monkeypatch)
    server = _servidor(enviar_corpo=True)
    _wire_local(monkeypatch, server.server_address[1])
    try:
        with pytest.raises(transport.TransportError) as ei:
            transport.fetch(
                "https://example.com/", allowed_hosts=ALLOWED,
                allowed_mimes=frozenset({"application/json"}), timeout=0.8,
                min_bytes_per_second=1, repeticao=0,
            )
    finally:
        server.parar.set()
        server.shutdown()
    assert type(ei.value) is transport.RespostaInvalida


def test_timeout_sem_status_continua_fonte_fora(monkeypatch):
    u = _buscar(monkeypatch, _servidor(enviar_corpo=False, enviar_cabecalhos=False), timeout=0.8)
    assert u.categoria == "fonte_fora"
