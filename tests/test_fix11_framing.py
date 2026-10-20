"""FIX11/F-13: o framing é validado em toda resposta, qualquer status (decisão 0059, emenda FIX11).

Servidor TCP cru: os bytes da resposta são exatamente os do caso. Framing inválido é
`resposta_inesperada`, um único pedido, sem repetição — em 200 e em 503.
"""

from __future__ import annotations

import socketserver
import threading

import pytest

from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.httputil import connector_fetch
from tests.test_transport import ALLOWED, _fast_guards, _wire_local

_CHUNK_OK = b"5\r\nhello\r\n0\r\n\r\n"

# (cabeçalhos extras de framing, corpo cru)
VARIANTES = {
    "cl_nao_numerico": (["Content-Length: xyz"], b"hello"),
    "cl_negativo": (["Content-Length: -5"], b"hello"),
    "cl_com_sinal": (["Content-Length: +5"], b"hello"),
    "cl_duplicado_distinto": (["Content-Length: 5", "Content-Length: 6"], b"hello"),
    "cl_duplicado_igual": (["Content-Length: 5", "Content-Length: 5"], b"hello"),
    "cl_com_chunked": (["Content-Length: 5", "Transfer-Encoding: chunked"], _CHUNK_OK),
    "te_desconhecido": (["Transfer-Encoding: gzip"], b"hello"),
    "te_duplicado": (["Transfer-Encoding: chunked", "Transfer-Encoding: chunked"], _CHUNK_OK),
    "chunk_dados_alem": (["Transfer-Encoding: chunked"], b"5\r\nhelloXX0\r\n\r\n"),
    "chunk_sem_crlf_final_de_dados": (["Transfer-Encoding: chunked"], b"5\r\nhello\n\n0\r\n\r\n"),
    "chunk_tamanho_invalido": (["Transfer-Encoding: chunked"], b"zz\r\nxx\r\n0\r\n\r\n"),
    "chunk_tamanho_negativo": (["Transfer-Encoding: chunked"], b"-5\r\nhello\r\n0\r\n\r\n"),
    "chunk_tamanho_sublinhado": (["Transfer-Encoding: chunked"], b"5_0\r\nhello\r\n0\r\n\r\n"),
    "chunk_tamanho_com_espaco": (["Transfer-Encoding: chunked"], b" 5\r\nhello\r\n0\r\n\r\n"),
    "chunk_tamanho_com_0x": (["Transfer-Encoding: chunked"], b"0x5\r\nhello\r\n0\r\n\r\n"),
    "chunk_truncado": (["Transfer-Encoding: chunked"], b"a\r\nhello"),
    "sem_chunk_final": (["Transfer-Encoding: chunked"], b"5\r\nhello\r\n"),
    "chunk_final_sem_crlf": (["Transfer-Encoding: chunked"], b"5\r\nhello\r\n0\r\n"),
    "cl_curto": (["Content-Length: 10"], b"hello"),
}


def _servidor(status: int, framing: list[str], corpo: bytes):
    pedidos: list[bytes] = []

    class H(socketserver.BaseRequestHandler):
        def handle(self):
            dados = b""
            while b"\r\n\r\n" not in dados:
                parte = self.request.recv(4096)
                if not parte:
                    return
                dados += parte
            pedidos.append(dados)
            cab = [f"HTTP/1.1 {status} X", "Content-Type: text/html", "Connection: close", *framing]
            self.request.sendall(("\r\n".join(cab) + "\r\n\r\n").encode() + corpo)

    class S(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    server = S(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, pedidos


def _buscar(monkeypatch, server):
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    return connector_fetch(
        "https://example.com/", hosts=ALLOWED, path_prefixes=None,
        mimes=frozenset({"text/html"}), timeout=5,
    )


@pytest.mark.parametrize("status", [200, 503])
@pytest.mark.parametrize("variante", sorted(VARIANTES))
def test_framing_invalido_e_resposta_inesperada_sem_repeticao(monkeypatch, variante, status):
    framing, corpo = VARIANTES[variante]
    server, pedidos = _servidor(status, framing, corpo)
    try:
        with pytest.raises(Unavailable) as ei:
            _buscar(monkeypatch, server)
    finally:
        server.shutdown()
    assert ei.value.categoria == "resposta_inesperada", ei.value.reason
    assert ei.value.evidencia["status"] == status
    assert len(pedidos) == 1


def test_framing_valido_continua_aceito(monkeypatch):
    server, pedidos = _servidor(200, ["Transfer-Encoding: chunked"], b"5;ext=1\r\nhello\r\n0\r\nX-T: 1\r\n\r\n")
    try:
        resp = _buscar(monkeypatch, server)
    finally:
        server.shutdown()
    assert resp.body == b"hello" and len(pedidos) == 1
