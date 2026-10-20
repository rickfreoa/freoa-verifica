"""FIX15/F-19: uma única interpretação textual (BOM → charset → meta → UTF-8) para desafio e sucesso.

Matriz com servidor TCP real: codificação × status × marcador. Marcador ("CAPTCHA" ou "verificação de
segurança") em qualquer codificação reconhecida é `ambiental_desafio` com 1 pedido e host bloqueado na guarda
(também em 200, que nunca é sucesso); charset desconhecido ou bytes inválidos no charset declarado são
`resposta_inesperada` com 1 pedido; sem marcador vale o comportamento por status.
"""

from __future__ import annotations

import pytest

from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.guarda import GuardaExecucao
from freoa_verifica.connectors.httputil import connector_fetch
from freoa_verifica.texto_resposta import normalizar_para_busca, texto_da_resposta
from freoa_verifica.transport import RespostaInvalida
from tests.test_fix12_sintaxe_estrita import ALLOWED, _buscar, _servidor
from tests.test_transport import _fast_guards, _wire_local

pytest_plugins = ["pytester"]
_CONFTEST = "from tests.live.conftest import pytest_runtest_makereport  # noqa: F401\n"

MARCADORES = {"captcha": "CAPTCHA", "verificacao": "verificação de segurança"}
SEM = "ação concluída sem problema"


def _html(texto: str) -> str:
    return f"<html><body><p>{texto}</p></body></html>"


def _meta(texto: str) -> str:
    return f'<html><head><meta charset="iso-8859-1"></head><body><p>{texto}</p></body></html>'


# nome -> (Content-Type, função texto -> bytes, o charset é reconhecido?)
CODIFICACOES = {
    "utf8": ("text/html; charset=utf-8", lambda t: _html(t).encode("utf-8"), True),
    "utf8_bom": ("text/html", lambda t: b"\xef\xbb\xbf" + _html(t).encode("utf-8"), True),
    "utf16_bom": ("text/html; charset=utf-16", lambda t: _html(t).encode("utf-16"), True),
    "utf16le_sem_bom": ("text/html; charset=utf-16le", lambda t: _html(t).encode("utf-16-le"), True),
    "iso_8859_1": ("text/html; charset=iso-8859-1", lambda t: _html(t).encode("iso-8859-1"), True),
    "windows_1252": ("text/html; charset=windows-1252", lambda t: _html(t).encode("cp1252"), True),
    "meta_sem_header": ("text/html", lambda t: _meta(t).encode("iso-8859-1"), True),
    "charset_desconhecido": ("text/html; charset=x-foo", lambda t: _html(t).encode("utf-8"), False),
    "bytes_invalidos": ("text/html; charset=utf-8", lambda t: _html(t).encode("utf-8") + b"\xff\xfe\xfa", False),
}


def _enviar(monkeypatch, status, ctype, corpo):
    cab = b"Content-Type: " + ctype.encode() + b"\r\nContent-Length: %d\r\n" % len(corpo)
    bruto = b"HTTP/1.1 %d X\r\nConnection: close\r\n" % status + cab + b"\r\n" + corpo
    server, pedidos = _servidor(bruto)
    try:
        try:
            return _buscar(monkeypatch, server), pedidos
        except Unavailable as exc:
            return exc, pedidos
    finally:
        server.shutdown()


@pytest.mark.parametrize("marcador", ["captcha", "verificacao", "nenhum"])
@pytest.mark.parametrize("status", [200, 403, 503])
@pytest.mark.parametrize("caso", sorted(CODIFICACOES))
def test_matriz_charset_status_marcador(monkeypatch, caso, status, marcador):
    ctype, codificar, reconhecido = CODIFICACOES[caso]
    texto = SEM if marcador == "nenhum" else MARCADORES[marcador]
    resultado, pedidos = _enviar(monkeypatch, status, ctype, codificar(texto))
    if not reconhecido:
        assert isinstance(resultado, Unavailable) and resultado.categoria == "resposta_inesperada", resultado
        assert len(pedidos) == 1
    elif marcador != "nenhum":
        assert isinstance(resultado, Unavailable) and resultado.categoria == "ambiental_desafio", resultado
        assert len(pedidos) == 1
    elif status == 200:
        assert not isinstance(resultado, Unavailable) and resultado.status == 200
        assert len(pedidos) == 1
    elif status == 403:
        assert isinstance(resultado, Unavailable) and resultado.categoria == "recusa_identificado"
        assert len(pedidos) == 1
    else:
        assert isinstance(resultado, Unavailable) and resultado.categoria == "fonte_fora"
        assert len(pedidos) > 1


@pytest.mark.parametrize("marcador", ["captcha", "verificacao"])
@pytest.mark.parametrize("status", [200, 403, 503])
@pytest.mark.parametrize("caso", [c for c, v in sorted(CODIFICACOES.items()) if v[2]])
def test_desafio_em_qualquer_charset_bloqueia_o_host_na_guarda(monkeypatch, caso, status, marcador):
    ctype, codificar, _ = CODIFICACOES[caso]
    cab = b"Content-Type: " + ctype.encode() + b"\r\nContent-Length: %d\r\n"
    corpo = codificar(MARCADORES[marcador])
    server, pedidos = _servidor(b"HTTP/1.1 %d X\r\nConnection: close\r\n" % status + cab % len(corpo) + b"\r\n" + corpo)
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    try:
        with GuardaExecucao().ativar():
            for url in ("https://example.com/a", "https://example.com/b"):
                with pytest.raises(Unavailable) as ei:
                    connector_fetch(
                        url, hosts=ALLOWED, path_prefixes=None, mimes=frozenset({"text/html"}), timeout=5
                    )
                assert ei.value.categoria == "ambiental_desafio"
    finally:
        server.shutdown()
    assert len(pedidos) == 1


@pytest.mark.parametrize("caso", ["charset_desconhecido", "bytes_invalidos"])
@pytest.mark.parametrize("status", [200, 503])
def test_hook_mantem_falha_nos_nao_ambientais(monkeypatch, pytester, caso, status):
    ctype, codificar, _ = CODIFICACOES[caso]
    u, _ = _enviar(monkeypatch, status, ctype, codificar(MARCADORES["captcha"]))
    assert isinstance(u, Unavailable)
    pytester.makeconftest(_CONFTEST)
    pytester.makeini("[pytest]\nmarkers =\n    live: x\n")
    pytester.makepyfile(
        "import pytest\nfrom freoa_verifica.connectors.base import Unavailable\n"
        "@pytest.mark.live\ndef test_x():\n"
        f"    raise Unavailable({u.reason!r}, {u.categoria!r}, {u.evidencia!r})\n"
    )
    pytester.runpytest("-p", "no:cacheprovider").assert_outcomes(failed=1)


# --- função única ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "corpo, ctype",
    [
        ("ação".encode("utf-32"), "text/html"),
        ("ação".encode("utf-16-be"), "text/html; charset=utf-16be"),
        (b"\xef\xbb\xbf" + "ação".encode(), "text/html; charset=iso-8859-1"),  # BOM vence o cabeçalho
        ('<meta http-equiv="Content-Type" content="text/html; charset=windows-1252">'.encode() + "ação".encode("cp1252"), "text/html"),
        ("ação".encode("cp1252"), 'text/html; charset="windows-1252"'),
    ],
)
def test_texto_da_resposta_ordem(corpo, ctype):
    assert "ação" in texto_da_resposta(corpo, ctype)


@pytest.mark.parametrize(
    "corpo, ctype",
    [(b"\xff\xfe\xfa", "text/html"), (b"abc", "text/html; charset=x-foo"), (b"abc", "text/html; charset=hex"),
     (b"abc", "text/html; charset=rot13")],
)
def test_texto_da_resposta_recusa_o_que_nao_interpreta(corpo, ctype):
    with pytest.raises(RespostaInvalida):
        texto_da_resposta(corpo, ctype)


def test_amostra_parcial_aceita_multibyte_cortado_no_fim():
    cortado = "aç".encode("utf-8")[:-1]
    with pytest.raises(RespostaInvalida):
        texto_da_resposta(cortado, "text/html")
    assert texto_da_resposta(cortado, "text/html", parcial=True) == "a"


def test_mime_nao_textual_nao_e_recusado():
    assert "captcha" in texto_da_resposta(b"%PDF\xff\xfe captcha", "application/pdf")


def test_normalizacao_de_marcadores():
    assert normalizar_para_busca("VERIFICAÇÃO de Segurança") == "verificacao de seguranca"
    assert normalizar_para_busca("ＣＡＰＴＣＨＡ") == "captcha"
