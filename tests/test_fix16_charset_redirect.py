"""FIX16 (auditoria r12): F-19 charset por algoritmos padronizados, F-21 desafio em salto, F-22 parser sobre texto.

F-19: Content-Type como media type (só o parâmetro `charset` conta) e prescan HTML do WHATWG (§13.2.3.2).
F-21: antes de seguir `Location` o transporte examina cabeçalhos e corpo do salto.
F-22: conectores entregam ao parser o texto da interpretação única, nunca os bytes de novo.
"""

from __future__ import annotations

import hashlib
import json
import re
import socketserver
import threading

import pytest

from freoa_verifica.connectors import cvm_colegiado
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.cvm_colegiado import CvmColegiadoConnector, _parse_rss
from freoa_verifica.connectors.guarda import GuardaExecucao
from freoa_verifica.connectors.httputil import connector_fetch
from freoa_verifica.service import Verifica
from freoa_verifica.texto_resposta import arvore_html, texto_da_resposta
from freoa_verifica.transport import Response, RespostaInvalida
from tests.test_fix12_sintaxe_estrita import ALLOWED, _buscar, _servidor
from tests.test_fix15_charset import _CONFTEST, _enviar
from tests.test_transport import _fast_guards, _wire_local

pytest_plugins = ["pytester"]

# --- F-19: função única --------------------------------------------------------------------------------------

CAPTCHA = "<p>CAPTCHA</p> "  # comprimento par: lido como UTF-16 viraria lixo


@pytest.mark.parametrize(
    "corpo, ctype",
    [
        # as quatro reproduções do auditor
        (b'<meta data-charset="utf-16le">' + CAPTCHA.encode(), "text/html"),
        (b'<!-- <meta charset="utf-16le"> -->' + CAPTCHA.encode(), "text/html"),
        (b'<p title="x charset=utf-16le">' + CAPTCHA.encode(), "text/html"),
        (b"<meta name='x' content='charset=utf-16le'>" + CAPTCHA.encode(), "text/html"),  # sem http-equiv
        (CAPTCHA.encode(), "text/html; x-charset=utf-16le"),
        # variantes
        (b'<meta http-equiv="refresh" content="0; charset=utf-16le">' + CAPTCHA.encode(), "text/html"),
        (b'<meta charset="utf-16le">' + CAPTCHA.encode(), "text/html"),  # UTF-16 em meta vale UTF-8 (WHATWG)
        (b'<meta charset="utf-16be">' + CAPTCHA.encode(), "text/html"),
        (b"<meta charset=utf-16le" + b" " * 1100 + b">" + CAPTCHA.encode(), "text/html"),  # além de 1024 bytes
        (b'<meta charset="utf-8" charset="utf-16le">' + CAPTCHA.encode(), "text/html"),  # 1º atributo vale
        (b"<script>var s='<meta charset=utf-16le>'</script>" + CAPTCHA.encode(), "text/html"),
        (CAPTCHA.encode(), 'text/html; foocharset=utf-16le; charset="utf-8"'),
        (b'<?xml version="1.0" encoding="utf-16"?><a>CAPTCHA</a> ', "application/xml"),
    ],
)
def test_declaracao_falsa_nao_muda_a_interpretacao(corpo, ctype):
    assert "CAPTCHA" in texto_da_resposta(corpo, ctype)


@pytest.mark.parametrize(
    "corpo, ctype, esperado",
    [
        (b'<meta charset=" ISO-8859-1 "><p>a\xe7\xe3o</p>', "text/html", "ação"),
        (b"<META CHARSET=iso-8859-1><p>a\xe7\xe3o</p>", "text/html", "ação"),
        (b'<meta http-equiv="Content-Type" content="text/html; charset=windows-1252"><p>a\xe7\xe3o', "text/html", "ação"),
        (b"<meta content='text/html;charset=latin1' http-equiv=content-type><p>a\xe7\xe3o", "text/html", "ação"),
        (b"<!-- x --><meta charset=latin1><p>a\xe7\xe3o", "text/html", "ação"),
        (b"<meta charset=utf-8><p>a\xc3\xa7\xc3\xa3o", "text/html", "ação"),
        (b"<p>a\xe7\xe3o", "text/html;charset=ISO-8859-1", "ação"),  # rótulo latin1 → windows-1252
        (b'<?xml version="1.0" encoding="ISO-8859-1"?><t>a\xe7\xe3o</t>', "application/xml", "ação"),
        (b'<?xml version="1.0" encoding="ISO-8859-1"?><t>a\xc3\xa7\xc3\xa3o</t>', "application/xml; charset=utf-8", "ação"),
        (b"<p>\x81</p>", "text/html; charset=windows-1252", "\x81"),  # byte indefinido: U+0081 (WHATWG)
    ],
)
def test_declaracoes_efetivas(corpo, ctype, esperado):
    assert esperado in texto_da_resposta(corpo, ctype)


def test_parametro_charset_repetido_divergente_e_invalido():  # FIX17: nenhum "primeiro vale"
    with pytest.raises(RespostaInvalida):
        texto_da_resposta(b"<p>a\xe7\xe3o</p>", "text/html; charset=utf-8; charset=latin1")


def test_header_vence_meta_e_xml():
    assert "ação" in texto_da_resposta("ação".encode("utf-8"), "text/html; charset=utf-8")
    corpo = b'<meta charset="iso-8859-1"><p>a\xc3\xa7\xc3\xa3o</p>'
    assert "ação" in texto_da_resposta(corpo, "text/html; charset=utf-8")


@pytest.mark.parametrize("rotulo", ["x-foo", "replacement", "iso-2022-kr", "x-user-defined"])
def test_rotulo_fora_da_tabela_ou_substituto_e_recusado(rotulo):
    with pytest.raises(RespostaInvalida):
        texto_da_resposta(b"<p>x</p>", f"text/html; charset={rotulo}")


# --- F-19: matriz com servidor real ----------------------------------------------------------------------------

FALSAS = {
    "data_charset": ("text/html", b'<meta data-charset="utf-16le"><p>CAPTCHA</p>'),
    "comentario": ("text/html", b'<!-- <meta charset="utf-16le"> --><p>CAPTCHA</p> '),
    "charset_em_outro_atributo": ("text/html", b'<p title="charset=utf-16le">CAPTCHA</p> '),
    "x_charset_http": ("text/html; x-charset=utf-16le", b"<p>CAPTCHA</p> "),
    "content_sem_pragma": ("text/html", b"<meta name=x content='charset=utf-16le'><p>CAPTCHA</p> "),
    "meta_utf16_vale_utf8": ("text/html", b'<meta charset="utf-16le"><p>CAPTCHA</p> '),
}


@pytest.mark.parametrize("status", [200, 403, 503])
@pytest.mark.parametrize("caso", sorted(FALSAS))
def test_declaracao_falsa_ainda_e_desafio(monkeypatch, caso, status):
    ctype, corpo = FALSAS[caso]
    u, pedidos = _enviar(monkeypatch, status, ctype, corpo)
    assert isinstance(u, Unavailable) and u.categoria == "ambiental_desafio", u
    assert len(pedidos) == 1


@pytest.mark.parametrize("caso", sorted(FALSAS))
def test_declaracao_falsa_bloqueia_o_host_na_guarda(monkeypatch, caso):
    ctype, corpo = FALSAS[caso]
    cab = b"Content-Type: " + ctype.encode() + b"\r\nContent-Length: %d\r\n" % len(corpo)
    server, pedidos = _servidor(b"HTTP/1.1 503 X\r\nConnection: close\r\n" + cab + b"\r\n" + corpo)
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    try:
        with GuardaExecucao().ativar():
            for url in ("https://example.com/a", "https://example.com/b"):
                with pytest.raises(Unavailable) as ei:
                    connector_fetch(url, hosts=ALLOWED, path_prefixes=None, mimes=frozenset({"text/html"}), timeout=5)
                assert ei.value.categoria == "ambiental_desafio"
    finally:
        server.shutdown()
    assert len(pedidos) == 1


def test_hook_converte_desafio_de_declaracao_falsa_em_xfail(monkeypatch, pytester):
    ctype, corpo = FALSAS["data_charset"]
    u, _ = _enviar(monkeypatch, 503, ctype, corpo)
    assert isinstance(u, Unavailable)
    pytester.makeconftest(_CONFTEST)
    pytester.makeini("[pytest]\nmarkers =\n    live: x\n")
    pytester.makepyfile(
        "import pytest\nfrom freoa_verifica.connectors.base import Unavailable\n"
        "@pytest.mark.live\ndef test_x():\n"
        f"    raise Unavailable({u.reason!r}, {u.categoria!r}, {u.evidencia!r})\n"
    )
    pytester.runpytest("-p", "no:cacheprovider").assert_outcomes(xfailed=1)


# --- F-21: desafio em salto de redirecionamento ---------------------------------------------------------------


def _servidor_de_saltos(salto: bytes, final: bytes):
    """GET /a responde `salto`; qualquer outro caminho responde `final`."""
    pedidos: list[str] = []

    class H(socketserver.BaseRequestHandler):
        def handle(self):
            dados = b""
            while b"\r\n\r\n" not in dados:
                parte = self.request.recv(4096)
                if not parte:
                    return
                dados += parte
            alvo = dados.split(b" ", 2)[1].decode()
            pedidos.append(alvo)
            self.request.sendall(salto if alvo == "/a" else final)

    class S(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    server = S(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, pedidos


def _resp(status: int, cabecalhos: bytes, corpo: bytes) -> bytes:
    return (
        b"HTTP/1.1 %d X\r\nConnection: close\r\nContent-Type: text/html; charset=utf-8\r\n" % status
        + cabecalhos
        + b"Content-Length: %d\r\n\r\n" % len(corpo)
        + corpo
    )


_OK = _resp(200, b"", b"<html><body>ok</body></html>")
_LOC = b"Location: /b\r\n"
_SALTOS = (301, 302, 303, 307, 308)


def _seguir(monkeypatch, salto, final=_OK, *, guarda=False):
    server, pedidos = _servidor_de_saltos(salto, final)
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    try:
        def buscar(caminho="a"):
            return connector_fetch(
                f"https://example.com/{caminho}", hosts=ALLOWED, path_prefixes=None,
                mimes=frozenset({"text/html"}), timeout=5,
            )

        if not guarda:
            try:
                return buscar(), pedidos
            except Unavailable as exc:
                return exc, pedidos
        resultados = []
        with GuardaExecucao().ativar():
            for caminho in ("a", "a"):
                try:
                    resultados.append(buscar(caminho))
                except Unavailable as exc:
                    resultados.append(exc)
        return resultados, pedidos
    finally:
        server.shutdown()


@pytest.mark.parametrize("status", _SALTOS)
@pytest.mark.parametrize(
    "variante, cabecalhos, corpo",
    [
        ("captcha_no_corpo", _LOC, b"<html><p>CAPTCHA</p></html>"),
        ("cf_mitigated", _LOC + b"cf-mitigated: challenge\r\n", b""),
    ],
)
def test_desafio_no_salto_nao_segue_location(monkeypatch, status, variante, cabecalhos, corpo):
    resultado, pedidos = _seguir(monkeypatch, _resp(status, cabecalhos, corpo))
    assert isinstance(resultado, Unavailable) and resultado.categoria == "ambiental_desafio", resultado
    assert pedidos == ["/a"]  # nunca pediu /b
    (salto,) = resultado.evidencia["saltos"]
    assert salto["status"] == status and salto["url"].endswith("/a")


@pytest.mark.parametrize("status", _SALTOS)
def test_desafio_no_salto_bloqueia_o_host_na_guarda(monkeypatch, status):
    resultados, pedidos = _seguir(
        monkeypatch, _resp(status, _LOC, b"<p>CAPTCHA</p>"), guarda=True
    )
    assert all(isinstance(r, Unavailable) and r.categoria == "ambiental_desafio" for r in resultados), resultados
    assert pedidos == ["/a"]  # a segunda chamada não chega à rede


@pytest.mark.parametrize("status", _SALTOS)
def test_redirecionamento_limpo_continua_sendo_seguido(monkeypatch, status):
    resultado, pedidos = _seguir(monkeypatch, _resp(status, _LOC, b""))
    assert not isinstance(resultado, Unavailable) and resultado.status == 200
    assert pedidos == ["/a", "/b"]
    assert resultado.final_url.endswith("/b")


def test_redirecionamento_com_corpo_ilegivel_e_resposta_inesperada(monkeypatch):
    salto = (
        b"HTTP/1.1 302 X\r\nConnection: close\r\nContent-Type: text/html; charset=x-foo\r\n"
        + _LOC + b"Content-Length: 3\r\n\r\nabc"
    )
    resultado, pedidos = _seguir(monkeypatch, salto)
    assert isinstance(resultado, Unavailable) and resultado.categoria == "resposta_inesperada"
    assert pedidos == ["/a"]


# --- F-22: parser recebe o texto, nunca os bytes -------------------------------------------------------------

INDEX = (
    "<html><head><title>Decisões</title></head><body>"
    '<a href="/decisoes/2024/20240131_R05.html">Ação de responsabilidade</a>'
    '<a href="/decisoes/2024/20240215_R06.html">Outra matéria</a>'
    "</body></html>"
).encode("utf-8")
CT_UTF8 = "text/html; charset=utf-8"


def _resposta(url: str, corpo: bytes, ctype: str = CT_UTF8) -> Response:
    # `headers` sem charset, como o transporte (só retém o recibo): o Content-Type cru está em `content_type`
    return Response(url, url, 200, {}, corpo, hashlib.sha256(corpo).hexdigest(), "2026-10-20T00:00:00Z", [],
                    "text/html", content_type=ctype)


def test_busca_por_titulo_acentuado_encontra_o_item(monkeypatch):
    monkeypatch.setattr(cvm_colegiado, "connector_fetch", lambda url, **kw: _resposta(url, INDEX))
    conn = CvmColegiadoConnector()
    assert len(conn.search("", ano=2024)) == 2
    achados = conn.search("Ação", ano=2024)
    assert [c.title for c in achados] == ["Ação de responsabilidade"]


def test_api_publica_busca_acentuada_nao_devolve_vazio_ok(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    ata = (
        "<html><body><h2>Ata da 5ª reunião</h2><article><p class='text-uppercase'>PROC. 19957.000123/2024-11 "
        "Ação de responsabilidade contra administrador</p></article></body></html>"
    ).encode("utf-8")
    monkeypatch.setattr(
        cvm_colegiado, "connector_fetch",
        lambda url, **kw: _resposta(url, ata if re.search(r"_R\d+\.html", url) else INDEX),
    )
    with Verifica(tmp_path / "h") as svc:
        svc._connectors["cvm_colegiado"] = CvmColegiadoConnector()
        r = svc.pesquisar_jurisprudencia("Ação", tribunais=["cvm"], desde="2024-01-01")
    cvm = [c for c in r["cobertura"] if c["tribunal"] == "CVM_COLEGIADO"]
    assert r["itens"], json.dumps(r, ensure_ascii=False, default=str)  # zero falso: título "Ação" existe na fonte
    assert cvm and cvm[0]["indisponivel"] is None and cvm[0]["indexados"] == 1


@pytest.mark.parametrize(
    "corpo, ctype",
    [
        (INDEX, "text/html"),  # sem charset: UTF-8 por omissão
        (INDEX.replace(b"<head>", b'<head><meta charset="utf-8">'), "text/html"),
        (INDEX.decode().encode("iso-8859-1"), "text/html; charset=iso-8859-1"),
        (INDEX.decode().encode("cp1252"), 'text/html; charset="windows-1252"'),
        (INDEX.decode().encode("utf-16"), "text/html"),  # BOM
        (INDEX.decode().encode("utf-16-le"), "text/html; charset=utf-16le"),
    ],
)
def test_busca_acentuada_em_qualquer_codificacao_declarada(monkeypatch, corpo, ctype):
    monkeypatch.setattr(cvm_colegiado, "connector_fetch", lambda url, **kw: _resposta(url, corpo, ctype))
    assert [c.title for c in CvmColegiadoConnector().search("Ação", ano=2024)] == ["Ação de responsabilidade"]


def test_corpo_ilegivel_na_busca_e_indisponivel_nunca_lista_vazia(monkeypatch):
    ruim = INDEX + b"\xff\xfe"
    monkeypatch.setattr(cvm_colegiado, "connector_fetch", lambda url, **kw: _resposta(url, ruim))
    with pytest.raises(RespostaInvalida):
        CvmColegiadoConnector().search("Ação", ano=2024)


def test_parse_da_ata_usa_o_texto_da_interpretacao_unica():
    html = "<html><body><h2>Ata</h2><article><p class='text-uppercase'>PROC. 19957.000123/2024-11 Ação</p></article></body></html>"
    resp = _resposta("https://conteudo.cvm.gov.br/decisoes/2024/20240131_R05.html", html.encode("utf-8"))
    parsed = CvmColegiadoConnector().parse(resp)
    assert "Ação" in parsed.metadata["decisoes"][0]["assunto"]
    assert "Ã§" not in parsed.metadata["decisoes"][0]["assunto"]


def test_rss_xml_regra_rfc_7303_cabecalho_vence_declaracao():
    # declaração diz iso-8859-1, mas os bytes são UTF-8 e o cabeçalho diz utf-8: vale o cabeçalho
    rss = (
        '<?xml version="1.0" encoding="iso-8859-1"?><rss><channel><item><title>Ação</title>'
        "<link>https://www.cvm.gov.br/x</link><description>Ação</description></item></channel></rss>"
    )
    texto = texto_da_resposta(rss.encode("utf-8"), "application/xml; charset=utf-8")
    assert _parse_rss(texto)[0]["title"] == "Ação"
    # sem charset no cabeçalho, vale a declaração (RFC 7303 §3)
    texto = texto_da_resposta(rss.encode("iso-8859-1"), "application/rss+xml")
    assert _parse_rss(texto)[0]["title"] == "Ação"
    # parse() recebe o Response e decide pelo Content-Type cru
    resp = Response("https://www.cvm.gov.br/feed.xml", "https://www.cvm.gov.br/feed.xml", 200, {},
                    rss.encode("utf-8"), "0" * 64, "2026-10-20T00:00:00Z", [], "application/xml",
                    content_type="application/xml; charset=utf-8")
    assert CvmColegiadoConnector().parse(resp).ementa == "Ação"


def test_arvore_html_aceita_declaracao_xml_em_texto():
    corpo = '<?xml version="1.0" encoding="utf-8"?><html><body>Ação</body></html>'.encode("utf-8")
    arv = arvore_html(corpo, "text/html; charset=utf-8")
    assert "Ação" in arv.text_content()


# --- F-17: diagnóstico não repete contra fonte que desafiou -----------------------------------------------------


def test_doctor_nao_repete_sonda_apos_desafio(tmp_path, monkeypatch):
    from freoa_verifica import service
    from freoa_verifica.connectors.planalto import PlanaltoConnector

    monkeypatch.delenv("FV_OFFLINE", raising=False)
    corpo = b"<html><p>CAPTCHA</p></html>"
    cab = b"Content-Type: text/html; charset=utf-8\r\nContent-Length: %d\r\n" % len(corpo)
    server, pedidos = _servidor(b"HTTP/1.1 403 X\r\nConnection: close\r\n" + cab + b"\r\n" + corpo)
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    monkeypatch.setattr(service, "registry", lambda: {"planalto": PlanaltoConnector})
    try:
        with Verifica(tmp_path / "h") as svc:
            check = next(c for c in svc.doctor()["verificacoes"] if c["nome"] == "fonte:planalto")
    finally:
        server.shutdown()
    assert len(pedidos) == 1, pedidos  # as demais sondas encontraram o host bloqueado pela guarda
    assert {p["status"] for p in check["detalhe"]} == {"unavailable"}
