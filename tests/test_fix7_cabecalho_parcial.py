"""FIX7/F-06: qualquer byte de resposta recebido torna a interrupção posterior `resposta_inesperada`.

Servidor TCP local real que envia linha de status e cabeçalho parcial e pausa até o prazo: uma
tentativa, sem repetição, hook live falha. Fechar sem enviar byte continua `fonte_fora` (ver
`test_fix6_cabecalho_invalido.py`).
"""

from __future__ import annotations

import socketserver
import threading

import pytest

from freoa_verifica import transport
from freoa_verifica.connectors import planalto as planalto_mod
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.planalto import PlanaltoConnector
from tests.test_transport import _fast_guards, _wire_local

pytest_plugins = ["pytester"]
_CONFTEST = "from tests.live.conftest import pytest_runtest_makereport  # noqa: F401\n"


def _servidor_parcial(bytes_enviados: bytes):
    parar = threading.Event()

    class H(socketserver.BaseRequestHandler):
        def handle(self):
            self.server.pedidos += 1
            self.request.settimeout(2)
            try:
                self.request.recv(65536)
                self.request.sendall(bytes_enviados)
                parar.wait(10)
            except OSError:
                pass

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), H)
    server.daemon_threads = True
    server.pedidos = 0
    server.parar = parar
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.mark.parametrize(
    "enviado",
    [
        b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nX-Parcial: abc",
        b"HTTP/1.1 200 OK\r\n",
        b"HTTP/1.1 20",
    ],
    ids=["cabecalho_parcial", "so_status", "status_cortado"],
)
def test_cabecalho_incompleto_ate_o_prazo_e_resposta_inesperada_e_hook_falha(monkeypatch, pytester, enviado):
    server = _servidor_parcial(enviado)
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    esperas: list[float] = []
    monkeypatch.setattr(transport, "_dormir", esperas.append)
    original = planalto_mod.connector_fetch
    monkeypatch.setattr(planalto_mod, "connector_fetch", lambda *a, **kw: original(*a, **{**kw, "timeout": 1.5}))
    c = PlanaltoConnector()
    try:
        with pytest.raises(Unavailable) as ei:
            c.fetch(c.resolve({"tipo": "LEI", "numero": 6404, "ano": 1976}))
    finally:
        server.parar.set()
        server.shutdown()
        server.server_close()
    u = ei.value
    assert server.pedidos == 1
    assert esperas == []
    assert u.categoria == "resposta_inesperada"
    pytester.makeconftest(_CONFTEST)
    pytester.makeini("[pytest]\nmarkers =\n    live: x\n")
    pytester.makepyfile(
        "import pytest\nfrom freoa_verifica.connectors.base import Unavailable\n"
        "@pytest.mark.live\ndef test_x():\n"
        f"    raise Unavailable({u.reason!r}, {u.categoria!r}, {u.evidencia!r})\n"
    )
    pytester.runpytest("-p", "no:cacheprovider").assert_outcomes(failed=1)
