"""FIX12/F-13: linha de status, cabeçalhos e trailers validados por gramática estrita (RFC 9112 §2–§5).

Servidor TCP cru: os bytes da resposta são exatamente os do caso. Qualquer violação é
`resposta_inesperada`, um único pedido, sem repetição — em 200 e em 503. Casos válidos continuam aceitos.
"""

from __future__ import annotations

import socketserver
import threading

import pytest

from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.httputil import connector_fetch
from tests.test_transport import ALLOWED, _fast_guards, _wire_local

_CHUNK_OK = b"5\r\nhello\r\n0\r\n\r\n"
_CL5 = b"Content-Length: 5\r\n"
_TE = b"Transfer-Encoding: chunked\r\n"
_BASE = b"Content-Type: text/html\r\nConnection: close\r\n"


def _resposta(status: int, linha_status: bytes | None, cabecalhos: bytes, corpo: bytes) -> bytes:
    return (linha_status or b"HTTP/1.1 %d X\r\n" % status) + _BASE + cabecalhos + b"\r\n" + corpo


# (linha de status ou None, cabeçalhos extras crus, corpo cru)
INVALIDAS = {
    "cl_espaco_antes_dos_dois_pontos": (None, b"Content-Length : 100\r\n", b"hello"),
    "te_espaco_antes_dos_dois_pontos": (None, b"Transfer-Encoding : chunked\r\n", _CHUNK_OK),
    "cabecalho_sem_dois_pontos": (None, b"SemDoisPontos\r\n" + _CL5, b"hello"),
    "trailer_sem_dois_pontos": (None, _TE, b"5\r\nhello\r\n0\r\nTrailerSemDoisPontos\r\n\r\n"),
    "trailer_com_espaco_antes_dos_dois_pontos": (None, _TE, b"5\r\nhello\r\n0\r\nX-T : 1\r\n\r\n"),
    "trailer_obs_fold": (None, _TE, b"5\r\nhello\r\n0\r\nX-T: 1\r\n  continua\r\n\r\n"),
    "obs_fold": (None, b"X-A: um\r\n dois\r\n" + _CL5, b"hello"),
    "nome_com_caractere_invalido": (None, b"X(A): 1\r\n" + _CL5, b"hello"),
    "nome_vazio": (None, b": 1\r\n" + _CL5, b"hello"),
    "cr_sem_lf_no_valor": (None, b"X-A: um\rdois\r\n" + _CL5, b"hello"),
    "lf_sem_cr": (None, b"X-A: um\n" + _CL5, b"hello"),
    "versao_http_1_2": (b"HTTP/1.2 200 X\r\n", _CL5, b"hello"),
    "status_sem_espaco_e_razao": (b"HTTP/1.1 200\r\n", _CL5, b"hello"),
    "status_com_dois_digitos": (b"HTTP/1.1 20 X\r\n", _CL5, b"hello"),
    "status_com_lf_sem_cr": (b"HTTP/1.1 200 X\n", _CL5, b"hello"),
    "status_em_minusculas": (b"http/1.1 200 X\r\n", _CL5, b"hello"),
}


def _servidor(bytes_resposta: bytes):
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
            self.request.sendall(bytes_resposta)

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
@pytest.mark.parametrize("variante", sorted(INVALIDAS))
def test_sintaxe_invalida_e_resposta_inesperada_sem_repeticao(monkeypatch, variante, status):
    linha, cabecalhos, corpo = INVALIDAS[variante]
    server, pedidos = _servidor(_resposta(status, linha, cabecalhos, corpo))
    try:
        with pytest.raises(Unavailable) as ei:
            _buscar(monkeypatch, server)
    finally:
        server.shutdown()
    assert ei.value.categoria == "resposta_inesperada", ei.value.reason
    assert len(pedidos) == 1


VALIDAS = {
    "content_length": (None, _CL5 + b"X-Ok:   valor com  espacos \t\r\n", b"hello"),
    "chunked_com_trailer_valido": (None, _TE, b"5;ext=1\r\nhello\r\n0\r\nX-T: 1\r\nX-U:\r\n\r\n"),
    "chunked_sem_trailer": (None, _TE, _CHUNK_OK),
    "versao_http_1_0": (b"HTTP/1.0 200 OK\r\n", _CL5, b"hello"),
    "razao_vazia_com_espaco": (b"HTTP/1.1 200 \r\n", _CL5, b"hello"),
    "nome_com_tchar": (None, b"X-A_b.c~1!#$%&'*+^`|: 1\r\n" + _CL5, b"hello"),
}


@pytest.mark.parametrize("caso", sorted(VALIDAS))
def test_sintaxe_valida_continua_aceita(monkeypatch, caso):
    linha, cabecalhos, corpo = VALIDAS[caso]
    server, pedidos = _servidor(_resposta(200, linha, cabecalhos, corpo))
    try:
        resp = _buscar(monkeypatch, server)
    finally:
        server.shutdown()
    assert resp.body == b"hello" and len(pedidos) == 1


def test_resposta_100_continue_antes_da_final_e_validada(monkeypatch):
    bruto = b"HTTP/1.1 100 Continue\r\n\r\n" + _resposta(200, None, _CL5, b"hello")
    server, pedidos = _servidor(bruto)
    try:
        assert _buscar(monkeypatch, server).body == b"hello"
    finally:
        server.shutdown()
    invalida = b"HTTP/1.1 100 Continue\r\nSem-Dois-Pontos\r\n\r\n" + _resposta(200, None, _CL5, b"hello")
    server, _ = _servidor(invalida)
    try:
        with pytest.raises(Unavailable) as ei:
            _buscar(monkeypatch, server)
    finally:
        server.shutdown()
    assert ei.value.categoria == "resposta_inesperada"
