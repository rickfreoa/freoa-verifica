"""FIX14/F-18: Content-Encoding validado antes de qualquer desvio por status (servidor TCP real).

O transporte só aceita corpo sem codificação ou `identity`. Qualquer outra (gzip, deflate, br, desconhecida,
corrompida, com expansão excessiva) é `resposta_inesperada` em QUALQUER status, com 1 pedido: corpo que não
foi examinado nunca equivale a "sem marcador".
"""

from __future__ import annotations

import gzip
import zlib

import pytest

from freoa_verifica.connectors.base import Unavailable
from tests.test_fix12_sintaxe_estrita import _buscar, _resposta, _servidor

COM = b"<html>captcha</html>"
SEM = b"<html>ok</html>"
EXCESSO = b"\x00" * (20 * 1024 * 1024)

CODIFICACOES = {
    "gzip": (b"gzip", gzip.compress),
    "deflate": (b"deflate", zlib.compress),
    "br": (b"br", lambda b: b),
    "x_desconhecida": (b"x-desconhecida", lambda b: b),
    "gzip_corrompido": (b"gzip", lambda b: b"\x1f\x8b\x08\x00corrompido" + b),
    "gzip_expandindo": (b"gzip", lambda b: gzip.compress(EXCESSO)),
    "gzip_e_identity": (b"gzip, identity", gzip.compress),
}


def _enviar(monkeypatch, status, cabecalho, corpo):
    extra = b"Content-Encoding: " + cabecalho + b"\r\n" if cabecalho else b""
    server, pedidos = _servidor(_resposta(status, None, extra + b"Content-Length: %d\r\n" % len(corpo), corpo))
    try:
        try:
            return _buscar(monkeypatch, server), pedidos
        except Unavailable as exc:
            return exc, pedidos
    finally:
        server.shutdown()


@pytest.mark.parametrize("marcador", [COM, SEM], ids=["com_marcador", "sem_marcador"])
@pytest.mark.parametrize("status", [200, 403, 429, 502, 503, 504])
@pytest.mark.parametrize("caso", sorted(CODIFICACOES))
def test_codificacao_nao_suportada_e_resposta_inesperada_sem_repeticao(monkeypatch, caso, status, marcador):
    nome, codificar = CODIFICACOES[caso]
    resultado, pedidos = _enviar(monkeypatch, status, nome, codificar(marcador))
    assert isinstance(resultado, Unavailable)
    assert resultado.categoria == "resposta_inesperada", resultado.reason
    assert len(pedidos) == 1


@pytest.mark.parametrize("cabecalho", [None, b"identity"], ids=["sem_codificacao", "identity"])
@pytest.mark.parametrize("status", [403, 429, 502, 503, 504])
def test_identity_com_marcador_continua_desafio(monkeypatch, cabecalho, status):
    resultado, pedidos = _enviar(monkeypatch, status, cabecalho, COM)
    assert isinstance(resultado, Unavailable) and resultado.categoria == "ambiental_desafio"
    assert len(pedidos) == 1


@pytest.mark.parametrize("cabecalho", [None, b"identity"], ids=["sem_codificacao", "identity"])
def test_identity_sem_marcador_503_continua_repetivel(monkeypatch, cabecalho):
    resultado, pedidos = _enviar(monkeypatch, 503, cabecalho, SEM)
    assert isinstance(resultado, Unavailable) and resultado.categoria == "fonte_fora"
    assert len(pedidos) > 1


@pytest.mark.parametrize("cabecalho", [None, b"identity"], ids=["sem_codificacao", "identity"])
def test_200_identity_aceito(monkeypatch, cabecalho):
    resposta, pedidos = _enviar(monkeypatch, 200, cabecalho, SEM)
    assert resposta.body == SEM and len(pedidos) == 1
