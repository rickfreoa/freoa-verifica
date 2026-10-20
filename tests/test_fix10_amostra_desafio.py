"""FIX10/F-13: a amostra do corpo de erro é lida em laço e o framing é validado até o limite."""

from __future__ import annotations

import socketserver
import threading

import pytest

from freoa_verifica import transport
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.httputil import connector_fetch
from tests.test_transport import _fast_guards, _wire_local

HOST = "www.planalto.gov.br"
CAB = "HTTP/1.1 {status} X\r\nContent-Type: text/html\r\n"


def _chunked(*blocos: bytes, fim: bool = True) -> bytes:
    corpo = b"".join(f"{len(b):x}\r\n".encode() + b + b"\r\n" for b in blocos)
    return corpo + (b"0\r\n\r\n" if fim else b"")


def _resposta(status: int, extra: str, corpo: bytes) -> bytes:
    return (CAB.format(status=status) + extra + "\r\n").encode() + corpo


CHUNKED = "Transfer-Encoding: chunked\r\n"
GRANDE = b"x" * (70 * 1024)

CASOS = {
    "marcador_no_1o_chunk": (503, CHUNKED, _chunked(b"<html>captcha</html>", b"ok"), "ambiental_desafio"),
    "marcador_no_2o_chunk": (503, CHUNKED, _chunked(b"hello", b"<html>captcha</html>"), "ambiental_desafio"),
    "marcador_atravessa_fronteira": (403, CHUNKED, _chunked(b"<html>capt", b"cha</html>"), "ambiental_desafio"),
    "marcador_em_varios_blocos_minusculos": (
        503, CHUNKED, _chunked(*[bytes([c]) for c in b"hello captcha"]), "ambiental_desafio"),
    "chunk_valido_e_depois_invalido": (503, CHUNKED, b"5\r\nhello\r\nZZ\r\n", "resposta_inesperada"),
    "chunk_valido_sem_fim": (503, CHUNKED, _chunked(b"hello", fim=False), "resposta_inesperada"),
    "content_length_nao_satisfeito": (503, "Content-Length: 100\r\n", b"hello", "resposta_inesperada"),
    "content_length_nao_satisfeito_403": (403, "Content-Length: 100\r\n", b"hello", "resposta_inesperada"),
    "content_length_ok_com_marcador": (503, "Content-Length: 7\r\n", b"captcha", "ambiental_desafio"),
}


def _servidor(bruto: bytes):
    class H(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(3)
            try:
                self.request.recv(65536)
                self.server.pedidos += 1
                self.request.sendall(bruto)
            except OSError:
                pass

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), H)
    server.daemon_threads = True
    server.pedidos = 0
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _pedir(monkeypatch, bruto: bytes):
    server = _servidor(bruto)
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    esperas: list[float] = []
    monkeypatch.setattr(transport, "_dormir", esperas.append)
    try:
        with pytest.raises(Unavailable) as ei:
            connector_fetch(
                f"https://{HOST}/x", hosts=frozenset({HOST}), path_prefixes=None, mimes=frozenset({"text/html"})
            )
    finally:
        server.shutdown()
        server.server_close()
    return ei.value, server.pedidos, esperas


@pytest.mark.parametrize("nome", list(CASOS))
def test_amostra_e_framing_um_percurso_sem_espera(monkeypatch, nome):
    status, extra, corpo, categoria = CASOS[nome]
    exc, pedidos, esperas = _pedir(monkeypatch, _resposta(status, extra, corpo))
    assert exc.categoria == categoria
    assert pedidos == 1 and esperas == []


@pytest.mark.parametrize("framing", ["chunked", "content_length"])
def test_corpo_acima_de_64_kib_sem_marcador_mantem_classificacao_por_status(monkeypatch, framing):
    if framing == "chunked":
        bruto = _resposta(503, CHUNKED, _chunked(GRANDE))
    else:
        bruto = _resposta(503, f"Content-Length: {len(GRANDE)}\r\n", GRANDE)
    exc, pedidos, esperas = _pedir(monkeypatch, bruto)
    assert exc.categoria == "fonte_fora"  # 503 sem desafio: repetível
    assert pedidos > 1 and esperas


def test_marcador_depois_dos_64_kib_nao_e_examinado(monkeypatch):
    """Limite documentado: só os primeiros 64 KiB são examinados."""
    exc, pedidos, _ = _pedir(monkeypatch, _resposta(503, CHUNKED, _chunked(GRANDE, b"captcha")))
    assert exc.categoria == "fonte_fora" and pedidos > 1


def test_marcador_ate_o_limite_da_amostra_e_visto(monkeypatch):
    corpo = b"x" * (64 * 1024 - 7) + b"captcha"
    exc, pedidos, esperas = _pedir(monkeypatch, _resposta(503, CHUNKED, _chunked(corpo)))
    assert exc.categoria == "ambiental_desafio" and pedidos == 1 and esperas == []
