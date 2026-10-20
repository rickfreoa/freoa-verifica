"""FIX6/F-06: bytes inválidos na linha de status/cabeçalhos são `resposta_inesperada`, sem repetição.

Servidor TCP local real: cabeçalho de 70 000 bytes, `HTTP/9.9 200 OK`, excesso de cabeçalhos → uma
tentativa e o hook live falha. Conexão fechada antes de qualquer byte continua `fonte_fora` e repetível.
"""

from __future__ import annotations

import socketserver
import threading

import pytest

from freoa_verifica import transport
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.planalto import PlanaltoConnector
from tests.test_transport import _fast_guards, _wire_local

pytest_plugins = ["pytester"]
_CONFTEST = "from tests.live.conftest import pytest_runtest_makereport  # noqa: F401\n"

_CABECALHO_GRANDE = b"HTTP/1.1 200 OK\r\nX-Grande: " + b"a" * 70_000 + b"\r\n\r\n"
_PROTOCOLO_DESCONHECIDO = b"HTTP/9.9 200 OK\r\nContent-Length: 0\r\n\r\n"
_CABECALHOS_EM_EXCESSO = b"HTTP/1.1 200 OK\r\n" + b"".join(b"X-%d: v\r\n" % i for i in range(150)) + b"\r\n"


def _servidor(resposta: bytes | None):
    """`resposta=None`: aceita e fecha sem enviar byte algum."""

    class H(socketserver.BaseRequestHandler):
        def handle(self):
            self.server.pedidos += 1
            self.request.settimeout(2)
            try:
                self.request.recv(65536)
                if resposta is not None:
                    self.request.sendall(resposta)
            except OSError:
                pass

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), H)
    server.daemon_threads = True
    server.pedidos = 0
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _capturar(monkeypatch, resposta):
    server = _servidor(resposta)
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    esperas: list[float] = []
    monkeypatch.setattr(transport, "_dormir", esperas.append)
    c = PlanaltoConnector()
    try:
        with pytest.raises(Unavailable) as ei:
            c.fetch(c.resolve({"tipo": "LEI", "numero": 6404, "ano": 1976}))
    finally:
        server.shutdown()
        server.server_close()
    return ei.value, server.pedidos, esperas


@pytest.mark.parametrize(
    "resposta",
    [_CABECALHO_GRANDE, _PROTOCOLO_DESCONHECIDO, _CABECALHOS_EM_EXCESSO],
    ids=["linha_longa_70000", "http_9_9", "cabecalhos_em_excesso"],
)
def test_bytes_invalidos_no_cabecalho_sao_resposta_inesperada_sem_repeticao(monkeypatch, pytester, resposta):
    u, pedidos, esperas = _capturar(monkeypatch, resposta)
    assert pedidos == 1
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


def test_conexao_fechada_antes_de_qualquer_byte_continua_fonte_fora_e_repetivel(monkeypatch):
    # Direto no transporte: o Planalto reclassifica "sem resposta" como recusa_identificado (B3-05).
    server = _servidor(None)
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    esperas: list[float] = []
    monkeypatch.setattr(transport, "_dormir", esperas.append)
    try:
        with pytest.raises(transport.TransportError) as ei:
            transport.fetch("https://www.planalto.gov.br/x", allowed_hosts=frozenset({"www.planalto.gov.br"}))
    finally:
        server.shutdown()
        server.server_close()
    assert not isinstance(ei.value, transport.RespostaInvalida)
    assert server.pedidos == 3  # 1 + 2 repetições do transporte
    assert len(esperas) == 2
