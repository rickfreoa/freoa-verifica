"""FIX17 (auditoria r13, F-19): Content-Type é media type estrito (RFC 9110 §5.6.6/§8.3.1), sem RFC 2231.

Só o parâmetro de nome exatamente `charset` conta; `charset*`, `charset*N` e `charset` duplicado divergente são
`RespostaInvalida`, no transporte, na guarda e no hook.
"""

from __future__ import annotations

import pytest

from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.guarda import GuardaExecucao
from freoa_verifica.connectors.httputil import connector_fetch
from freoa_verifica.texto_resposta import parametros_media_type, texto_da_resposta
from freoa_verifica.transport import RespostaInvalida
from tests.test_fix12_sintaxe_estrita import ALLOWED, _servidor
from tests.test_fix15_charset import _CONFTEST, _enviar
from tests.test_transport import _fast_guards, _wire_local

pytest_plugins = ["pytester"]

CAPTCHA = b"<p>CAPTCHA</p>"  # 14 bytes, ASCII: lido como UTF-16 viraria lixo

INVALIDOS = {
    "estendido": "text/html; charset*=us-ascii''utf-16le",
    "continuacao_0_1": "text/html; charset*0=utf-16; charset*1=le",
    "continuacao_codificada": "text/html; charset*0*=utf-16%2; charset*1*=Ele",
    "estendido_maiusculas": "text/html; CHARSET*=utf-16le",
    "duplicado_divergente": "text/html; charset=utf-8; charset=utf-16",
    "duplicado_divergente_aspas": 'text/html; charset="utf-8"; CharSet=utf-16',
    "sem_valor": "text/html; charset",
    "valor_vazio": "text/html; charset=",
    "valor_vazio_aspas": 'text/html; charset=""',
    "malformado_sem_ponto_e_virgula": "text/html charset=utf-8",
    "malformado_espaco_no_igual": "text/html; charset = utf-8",
    "malformado_aspas_abertas": 'text/html; charset="utf-8',
    "malformado_sem_subtipo": "text/; charset=utf-8",
    "malformado_sem_barra": "html; charset=utf-8",
    "malformado_parametro_solto": "text/html; charset=utf-8; xyz",
    "malformado_virgula": "text/html, text/plain; charset=utf-8",
    "malformado_valor_com_espaco": "text/html; charset=utf 8",
}


@pytest.mark.parametrize("ctype", sorted(INVALIDOS.values()))
def test_invalidos_na_funcao_unica(ctype):
    with pytest.raises(RespostaInvalida):
        texto_da_resposta(CAPTCHA, ctype)


@pytest.mark.parametrize(
    "corpo, ctype, esperado",
    [
        ("ação".encode("utf-16-le"), 'text/html; charset="utf-16le"', "ação"),
        ("ação".encode("utf-8"), "text/html; CharSet=UTF-8", "ação"),
        ("ação".encode("latin-1"), 'text/html;charset="ISO-8859-1"', "ação"),
        ("ação".encode("utf-8"), "text/html; charset=utf-8; charset=UTF-8", "ação"),  # duplicata igual
        ("ação".encode("utf-8"), "text/html; charset=utf-8;", "ação"),  # parâmetro vazio
        ("ação".encode("utf-8"), "text/html ;\tcharset=utf-8", "ação"),
        ("ação".encode("utf-8"), "TEXT/HTML; x-charset*=foo; charset=utf-8", "ação"),  # outro nome, não é charset
        ("ação".encode("utf-8"), 'text/html; foo="a;b\\"c"; charset=utf-8', "ação"),  # ';' e aspas em valor
        ("ação".encode("utf-8"), 'text/html; charset=utf-8; boundary="charset*=utf-16"', "ação"),
    ],
)
def test_validos(corpo, ctype, esperado):
    assert esperado in texto_da_resposta(corpo, ctype)


def test_parametros_nao_aplicam_rfc2231():
    assert parametros_media_type("text/html; charset*=us-ascii''utf-16le") == [("charset*", "us-ascii''utf-16le")]
    nomes = [n for n, _ in parametros_media_type("text/html; charset*0=a; Charset=b")]
    assert nomes == ["charset*0", "charset"]


def test_nao_textual_tambem_valida_charset():
    """FIX18/F-19: MIME binário não dispensa a validação (esta asserção, na FIX17, afirmava o contrário)."""
    with pytest.raises(RespostaInvalida):
        texto_da_resposta(b"%PDF", "application/pdf; charset*=x''y")


# --- matriz: transporte, guarda e hook ------------------------------------------------------------------------


@pytest.mark.parametrize("status", [200, 403, 503])
@pytest.mark.parametrize("caso", sorted(INVALIDOS))
def test_transporte_recusa_content_type_invalido(monkeypatch, caso, status):
    """O corpo é CAPTCHA mas ninguém pode afirmar: 1 pedido, `resposta_inesperada`, nunca sucesso nem repetição."""
    u, pedidos = _enviar(monkeypatch, status, INVALIDOS[caso], CAPTCHA)
    assert isinstance(u, Unavailable) and u.categoria == "resposta_inesperada", u
    assert len(pedidos) == 1


@pytest.mark.parametrize("caso", sorted(INVALIDOS))
def test_guarda_nunca_repete_nem_aprova_content_type_invalido(monkeypatch, caso):
    cab = b"Content-Type: " + INVALIDOS[caso].encode() + b"\r\nContent-Length: %d\r\n" % len(CAPTCHA)
    server, pedidos = _servidor(b"HTTP/1.1 503 X\r\nConnection: close\r\n" + cab + b"\r\n" + CAPTCHA)
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    try:
        with GuardaExecucao().ativar():
            for url in ("https://example.com/a", "https://example.com/b"):
                with pytest.raises(Unavailable) as ei:
                    connector_fetch(url, hosts=ALLOWED, path_prefixes=None, mimes=frozenset({"text/html"}), timeout=5)
                assert ei.value.categoria == "resposta_inesperada"
    finally:
        server.shutdown()
    assert len(pedidos) == 2  # um por URL: sem repetição interna; resposta_inesperada não bloqueia o host


@pytest.mark.parametrize("caso", ["estendido", "continuacao_0_1", "duplicado_divergente", "sem_valor"])
def test_hook_nao_converte_content_type_invalido_em_xfail(monkeypatch, pytester, caso):
    u, _ = _enviar(monkeypatch, 503, INVALIDOS[caso], CAPTCHA)
    assert isinstance(u, Unavailable)
    pytester.makeconftest(_CONFTEST)
    pytester.makeini("[pytest]\nmarkers =\n    live: x\n")
    pytester.makepyfile(
        "import pytest\nfrom freoa_verifica.connectors.base import Unavailable\n"
        "@pytest.mark.live\ndef test_x():\n"
        f"    raise Unavailable({u.reason!r}, {u.categoria!r}, {u.evidencia!r})\n"
    )
    pytester.runpytest("-p", "no:cacheprovider").assert_outcomes(failed=1)
