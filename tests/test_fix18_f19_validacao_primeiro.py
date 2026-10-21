"""FIX18 (auditoria r14, F-19): a validação do Content-Type roda PRIMEIRO, para toda resposta.

BOM decide a codificação, nunca dispensa a validação; MIME binário (`application/pdf`) também não. Corpo com BOM ou
marcador HTML sob MIME binário é examinado como texto: um desafio HTML servido como PDF é desafio.
Reproduções do auditor × {200, 503} × {transporte, guarda, hook}, com servidor TCP real.
"""

from __future__ import annotations

import pytest

from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.guarda import GuardaExecucao
from freoa_verifica.connectors.httputil import connector_fetch
from freoa_verifica.texto_resposta import interpretar
from freoa_verifica.transport import RespostaInvalida
from tests.test_fix12_sintaxe_estrita import ALLOWED, _servidor
from tests.test_fix15_charset import _CONFTEST
from tests.test_transport import _fast_guards, _wire_local

pytest_plugins = ["pytester"]

BOM8 = b"\xef\xbb\xbf"
MIMES = frozenset({"text/html", "application/pdf"})

# nome -> (Content-Type, corpo): Content-Type inválido; o corpo não importa (nem o BOM, nem o MIME binário)
INVALIDOS = {
    "bom_charset_estendido": ("text/html; charset*=x", BOM8 + b"<p>ok</p>"),
    "bom_charset_estendido_captcha": ("text/html; charset*=x", BOM8 + b"<p>CAPTCHA</p>"),
    "bom_charset_duplicado": ("text/html; charset=utf-8; charset=utf-16", BOM8 + b"<p>ok</p>"),
    "bom_utf16_charset_continuacao": ("text/html; charset*0=utf; charset*1=-8", "<p>ok</p>".encode("utf-16")),
    "pdf_charset_estendido_utf16_captcha": ("application/pdf; charset*=x", "<p>CAPTCHA</p>".encode("utf-16")),
    "pdf_charset_duplicado": ("application/pdf; charset=a; charset=b", b"%PDF-1.4\n"),
    "pdf_malformado": ("application/pdf; x", b"%PDF-1.4\n"),
}

# Content-Type válido e binário, corpo HTML com desafio: é desafio
DESAFIOS_BINARIOS = {
    "pdf_bom_utf16_captcha": ("application/pdf", "<html><p>CAPTCHA</p></html>".encode("utf-16")),
    "pdf_bom_utf8_captcha": ("application/pdf", BOM8 + b"<p>CAPTCHA</p>"),
    "pdf_doctype_captcha": ("application/pdf", b"<!DOCTYPE html><p>Verifica\xc3\xa7\xc3\xa3o de seguran\xc3\xa7a</p>"),
    "pdf_html_utf16le_meta": ("application/pdf; charset=utf-16le", "<html><p>CAPTCHA</p>".encode("utf-16-le")),
}


def _bruto(status: int, ctype: str, corpo: bytes) -> bytes:
    return (b"HTTP/1.1 %d X\r\nConnection: close\r\nContent-Type: " % status + ctype.encode()
            + b"\r\nContent-Length: %d\r\n\r\n" % len(corpo) + corpo)


def _duas_urls(monkeypatch, status, ctype, corpo, *, guarda: bool):
    server, pedidos = _servidor(_bruto(status, ctype, corpo))
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    falhas = []
    try:
        ctx = GuardaExecucao().ativar() if guarda else _nulo()
        with ctx:
            for url in ("https://example.com/a", "https://example.com/b"):
                try:
                    connector_fetch(url, hosts=ALLOWED, path_prefixes=None, mimes=MIMES, timeout=5)
                    falhas.append(None)
                except Unavailable as exc:
                    falhas.append(exc)
    finally:
        server.shutdown()
    return falhas, pedidos


class _nulo:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.mark.parametrize("caso", sorted(INVALIDOS))
def test_funcao_unica_valida_antes_de_bom_e_mime(caso):
    ctype, corpo = INVALIDOS[caso]
    with pytest.raises(RespostaInvalida):
        interpretar(corpo, ctype)


@pytest.mark.parametrize("guarda", [False, True], ids=["transporte", "guarda"])
@pytest.mark.parametrize("status", [200, 503])
@pytest.mark.parametrize("caso", sorted(INVALIDOS))
def test_content_type_invalido_nunca_sucesso_nem_repeticao(monkeypatch, caso, status, guarda):
    ctype, corpo = INVALIDOS[caso]
    falhas, pedidos = _duas_urls(monkeypatch, status, ctype, corpo, guarda=guarda)
    assert all(isinstance(f, Unavailable) and f.categoria == "resposta_inesperada" for f in falhas), falhas
    assert len(pedidos) == 2  # um por URL: sem repetição interna (o auditor viu seis em 503)


@pytest.mark.parametrize("status", [200, 503])
@pytest.mark.parametrize("caso", sorted(DESAFIOS_BINARIOS))
def test_desafio_html_sob_mime_binario_e_desafio(monkeypatch, caso, status):
    ctype, corpo = DESAFIOS_BINARIOS[caso]
    falhas, pedidos = _duas_urls(monkeypatch, status, ctype, corpo, guarda=True)
    assert all(isinstance(f, Unavailable) and f.categoria == "ambiental_desafio" for f in falhas), falhas
    assert len(pedidos) == 1  # a guarda bloqueia o host depois do primeiro desafio


def test_pdf_verdadeiro_continua_binario():
    i = interpretar(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj", "application/pdf")
    assert i.origem == "binario" and i.codificacao is None


@pytest.mark.parametrize("caso", sorted(INVALIDOS))
def test_hook_nao_converte_em_xfail(monkeypatch, pytester, caso):
    ctype, corpo = INVALIDOS[caso]
    falhas, _ = _duas_urls(monkeypatch, 503, ctype, corpo, guarda=True)
    u = falhas[0]
    assert isinstance(u, Unavailable)
    pytester.makeconftest(_CONFTEST)
    pytester.makeini("[pytest]\nmarkers =\n    live: x\n")
    pytester.makepyfile(
        "import pytest\nfrom freoa_verifica.connectors.base import Unavailable\n"
        "@pytest.mark.live\ndef test_x():\n"
        f"    raise Unavailable({u.reason!r}, {u.categoria!r}, {u.evidencia!r})\n"
    )
    pytester.runpytest("-p", "no:cacheprovider").assert_outcomes(failed=1)
