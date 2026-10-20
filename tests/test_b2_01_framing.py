"""B2-01: falha depois de recebido o status/cabeçalho é resposta inválida, nunca `fonte_fora`.

Ponta a ponta: servidor local real com framing quebrado → transporte → classificação → hook live.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.httputil import connector_fetch
from tests.test_transport import ALLOWED, _fast_guards, _wire_local  # noqa: F401

pytest_plugins = ["pytester"]
_CONFTEST = "from tests.live.conftest import pytest_runtest_makereport  # noqa: F401\n"


def _servidor(corpo: bytes):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            return

        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Transfer-Encoding", "chunked")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(corpo)
            self.wfile.flush()
            self.close_connection = True

    server = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.mark.parametrize(
    "corpo",
    [b"zz\r\nxx\r\n0\r\n\r\n", b"a\r\n{}", b"ff\r\n{}"],
    ids=["tamanho_invalido", "chunk_truncado", "incompleto_sem_fim"],
)
def test_framing_invalido_em_200_e_resposta_inesperada_e_hook_falha(monkeypatch, pytester, corpo):
    server = _servidor(corpo)
    try:
        _fast_guards(monkeypatch)
        _wire_local(monkeypatch, server.server_address[1])
        with pytest.raises(Unavailable) as ei:
            connector_fetch(
                "https://example.com/", hosts=ALLOWED, path_prefixes=None,
                mimes=frozenset({"application/json"}), timeout=5,
            )
    finally:
        server.shutdown()
    u = ei.value
    assert u.categoria == "resposta_inesperada"
    assert u.evidencia["status"] == 200
    pytester.makeconftest(_CONFTEST)
    pytester.makeini("[pytest]\nmarkers =\n    live: x\n")
    pytester.makepyfile(
        "import pytest\nfrom freoa_verifica.connectors.base import Unavailable\n"
        "@pytest.mark.live\ndef test_x():\n"
        f"    raise Unavailable({u.reason!r}, {u.categoria!r}, {u.evidencia!r})\n"
    )
    pytester.runpytest("-p", "no:cacheprovider").assert_outcomes(failed=1)
