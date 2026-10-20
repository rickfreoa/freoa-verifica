"""FIX8/F-06: o progresso de resposta é da chamada lógica, não de cada salto.

302 /start -> /target e o destino fecha sem bytes: o status do primeiro salto já foi recebido,
logo a falha é `resposta_inesperada`, sem repetição, com a cadeia na evidência.
"""

from __future__ import annotations

import socketserver
import threading

import pytest

from freoa_verifica import transport
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.httputil import connector_fetch
from tests.test_transport import _fast_guards, _wire_local

pytest_plugins = ["pytester"]
_CONFTEST = "from tests.live.conftest import pytest_runtest_makereport  # noqa: F401\n"


def _servidor_redireciona_e_fecha():
    class H(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(2)
            try:
                dados = self.request.recv(65536)
            except OSError:
                return
            caminho = dados.split(b"\r\n", 1)[0].decode("latin-1").split(" ")[1]
            self.server.percursos.append(caminho)
            if caminho == "/start":
                self.request.sendall(
                    b"HTTP/1.1 302 Found\r\nLocation: /target\r\nContent-Length: 0\r\n\r\n"
                )
            # /target: fecha sem enviar byte algum

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), H)
    server.daemon_threads = True
    server.percursos = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_redirecionamento_seguido_de_fechamento_sem_bytes_e_resposta_inesperada(monkeypatch, pytester):
    server = _servidor_redireciona_e_fecha()
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    esperas: list[float] = []
    monkeypatch.setattr(transport, "_dormir", esperas.append)
    try:
        with pytest.raises(Unavailable) as ei:
            connector_fetch(
                "https://www.planalto.gov.br/start",
                hosts=frozenset({"www.planalto.gov.br"}),
                path_prefixes=None,
                mimes=frozenset({"text/html"}),
            )
    finally:
        server.shutdown()
        server.server_close()
    u = ei.value
    assert server.percursos == ["/start", "/target"]
    assert esperas == []
    assert u.categoria == "resposta_inesperada"
    assert u.evidencia["saltos"] == [{"url": "https://www.planalto.gov.br/start", "status": 302}]
    pytester.makeconftest(_CONFTEST)
    pytester.makeini("[pytest]\nmarkers =\n    live: x\n")
    pytester.makepyfile(
        "import pytest\nfrom freoa_verifica.connectors.base import Unavailable\n"
        "@pytest.mark.live\ndef test_x():\n"
        f"    raise Unavailable({u.reason!r}, {u.categoria!r}, {u.evidencia!r})\n"
    )
    pytester.runpytest("-p", "no:cacheprovider").assert_outcomes(failed=1)
