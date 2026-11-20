"""0089 trilha (a): eventos sintéticos, não simulam garantias de navegador real.

Geradores pedido/eventos/fluxo: exercício da matriz, correlação e limites.
Nenhuma requisição ou dependência de navegador.
"""

from __future__ import annotations

import ast
import base64
import codecs
import gzip
import hashlib
import json
import threading
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from freoa_verifica import transport as t
from freoa_verifica.texto_resposta import texto_do_response
from tests.fixture_util import load_fixture

URL = "https://www.planalto.gov.br/ccivil_03/leis/l6404.htm"
BODY = b"<html><body>Art. 1. Texto publico.</body></html>"
MIMES = frozenset({"text/html", "application/json"})


def perfil(**kw):
    return t.PerfilPortaAssistida(
        origens=frozenset({"www.planalto.gov.br"}),
        recursos=tuple(
            t.RecursoAssistido(
                tipo, r"^/ccivil_03/[A-Za-z0-9_\-/]+\.htm[l]?$", "^$", MIMES
            )
            for tipo in ("Document", "XHR", "Fetch")
        ),
        cookies_admitidos=(r"^TS[0-9a-f]{6,}$",),
        fundamento_publico="Recurso sintético declarado público, sem autenticação.",
        **kw,
    )


def pedido(**kw):
    padrao = dict(
        chave=t.ChaveAssistida("cdp", "aba", "pedido", 0),
        url=URL,
        metodo="GET",
        tipo="Document",
        timestamp=100.0,
        wall_time=1_700_000_000.0,
        observado_em=time.monotonic(),
        frame_id="raiz",
        raiz_id="raiz",
        documento_raiz=URL,
        iniciador={"tipo": "other"},
        pronto=True,
        ambiente_conferido=True,
        posterior_linha_base=True,
        alvo_tipo="page",
        subtipo_desde_criacao="",
    )
    padrao.update(kw)
    return t.PedidoAssistido(**padrao)


@pytest.fixture
def sessao():
    s = t.SessaoPortaAssistida(perfil(), navegador="Brave 1.100 Chromium 158")
    yield s
    s.encerrar()


def evento(p, metodo, **dados):
    return t.EventoAssistido(p.chave, metodo, dados)


def eventos(
    p,
    *,
    body=BODY,
    encoding=None,
    protocolo="http/1.1",
    status=200,
    status_cru=None,
    headers=None,
    response=None,
    data_length=None,
    encoded_length=None,
    declarado=None,
    antes_stream=0,
):
    """Gerador sintético: cada byte do bufferedData foi declarado antes da resposta."""
    campos = {
        "Content-Type": "text/html; charset=utf-8",
        "Content-Length": str(len(body)),
    }
    if headers is not None:
        campos.update(headers)
    if encoding is not None:
        campos["Content-Encoding"] = encoding
    if declarado is not None:
        campos["Content-Length"] = str(declarado)
    campos = {k: v for k, v in campos.items() if v is not None}
    bruto = status if status_cru is None else status_cru
    raw = (
        f"HTTP/1.1 {bruto} OK\r\n"
        + "".join(f"{k}: {v}\r\n" for k, v in campos.items())
        + "\r\n"
    )
    r = dict(
        url=p.url,
        status=status,
        protocol=protocolo,
        fromDiskCache=False,
        fromServiceWorker=False,
        fromPrefetchCache=False,
        remoteIPAddress="8.8.8.8",
        remotePort=443,
        securityState="secure",
        securityDetails={"protocol": "TLS 1.3", "issuer": "AC publica sintetica"},
    )
    r.update(response or {})
    a, b = body[:antes_stream], body[antes_stream:]
    anteriores = (
        [evento(p, "dataReceived", dataLength=len(a), encodedDataLength=0)] if a else []
    )
    return anteriores + [
        evento(p, "streamResourceContent", bufferedData=base64.b64encode(a).decode()),
        evento(
            p,
            "requestWillBeSentExtraInfo",
            authorization_presente=False,
            associatedCookies=[],
        ),
        evento(p, "responseReceived", response=r),
        evento(
            p,
            "responseReceivedExtraInfo",
            statusCode=bruto,
            headersText=raw,
            headers=campos,
        ),
        evento(
            p,
            "dataReceived",
            data=base64.b64encode(b).decode(),
            dataLength=len(b) if data_length is None else data_length,
            encodedDataLength=(len(body) if p.tipo != "Document" else 0)
            if encoded_length is None
            else encoded_length,
        ),
        evento(p, "loadingFinished", timestamp=102.25),
    ]


def fluxo(sessao, p=None, evs=None, **kw):
    p = p or pedido()
    c = t.capturar_assistida(sessao, p)
    for ev in evs if evs is not None else eventos(p, **kw):
        c.observar(ev)
    return c.admitir()


def xhr(**kw):
    return pedido(
        tipo="XHR",
        iniciador={
            "tipo": "script",
            "frame_id": "raiz",
            "documento": URL,
            "alvo": "aba",
        },
        **kw,
    )


def test_linhas_01_22_aceite(sessao):
    c = fluxo(sessao)
    assert c.resposta.body == BODY
    assert c.resposta.sha256 == hashlib.sha256(BODY).hexdigest()
    assert c.resposta.size == len(BODY)
    assert (
        c.resposta.fetched_at
        == datetime.fromtimestamp(1_700_000_002.25, timezone.utc).isoformat()
    )
    assert c.procedencia == c.modalidade_acesso == "sessao_assistida"
    assert c.protocolo == "http/1.1"
    assert c.emissor_certificado == "AC publica sintetica"
    assert c.codificacao == "utf-8"
    assert c.origem_da_codificacao == "header"
    assert c.encoded_data_length is None


@pytest.mark.parametrize(
    "url",
    [
        "http://www.planalto.gov.br/ccivil_03/a.htm",
        "https://malicioso.test/ccivil_03/a.htm",
        "https://www.planalto.gov.br:444/ccivil_03/a.htm",
        "https://www.planalto.gov.br/ccivil_03/../a.htm",
        "https://www.planalto.gov.br/ccivil_03//a.htm",
        "https://www.planalto.gov.br/privado/a.htm",
        URL + "?token=SEGREDO",
        URL.replace("l6404", "ação"),
        URL.replace("l6404", "%6c6404"),
        "data:text/html,a",
        "blob:" + URL,
    ],
)
def test_linha_01_url_recusada(sessao, url):
    with pytest.raises(t.BlockedHost):
        fluxo(sessao, pedido(url=url))


def test_linha_01_fragmento_descartado(sessao):
    c = fluxo(sessao, pedido(url=URL + "#nao-persistir"))
    assert c.resposta.url == URL


@pytest.mark.parametrize(
    "ip,port",
    [
        ("127.0.0.1", 443),
        ("10.0.0.1", 443),
        ("224.0.0.1", 443),
        ("::1", 443),
        ("invalido", 443),
        ("8.8.8.8", 80),
    ],
)
def test_linha_02_ip_porta(sessao, ip, port):
    with pytest.raises(t.BlockedHost):
        fluxo(sessao, response={"remoteIPAddress": ip, "remotePort": port})


@pytest.mark.parametrize(
    "alteracao",
    [
        {"securityState": "insecure"},
        {"securityDetails": {}},
        {"securityDetails": {"protocol": "TLS 1.1", "issuer": "AC"}},
    ],
)
def test_linha_03_tls(sessao, alteracao):
    with pytest.raises(t.RespostaInvalida):
        fluxo(sessao, response=alteracao)


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "HTTP/1.1 200 OK\nContent-Type: text/html\n\n",
        "HTTP/1.1 200 OK\r\ncampo sem dois pontos\r\n\r\n",
        "HTTP/1.1 200 OK\r\nContent-Length: 123456789012345678901\r\n\r\n",
        "HTTP/1.1 200 OK\r\nContent-Length: 1\r\nContent-Length: 1\r\n\r\n",
        "HTTP/1.1 200 OK\r\nContent-Length: 1\r\nContent-Length: 2\r\n\r\n",
        "HTTP/1.1 200 OK\r\nContent-Length: 1\r\nTransfer-Encoding: chunked\r\n\r\n",
        "HTTP/1.1 200 OK\r\nTransfer-Encoding: gzip\r\n\r\n",
        "HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nTransfer-Encoding: chunked\r\n\r\n",
        "HTTP/1.1 206 Partial\r\nContent-Type: text/html\r\n\r\n",
    ],
)
def test_linha_04_http1_bruto(sessao, raw):
    p = pedido()
    evs = eventos(p)
    evs[3].dados["headersText"] = raw
    with pytest.raises(t.RespostaInvalida):
        fluxo(sessao, p, evs)


@pytest.mark.parametrize("proto", ["h2", "h3"])
@pytest.mark.parametrize(
    "headers,aceita",
    [
        ({}, True),
        ({"Content-Length": "1\n1"}, False),
        ({"Content-Length": "123456789012345678901"}, False),
        ({"Transfer-Encoding": "chunked"}, False),
        ({"Content-Type": "text/html\ntext/html"}, False),
    ],
)
def test_linha_04_http2_3(sessao, proto, headers, aceita):
    if aceita:
        assert fluxo(sessao, protocolo=proto, headers=headers).protocolo == proto
    else:
        with pytest.raises(t.RespostaInvalida):
            fluxo(sessao, protocolo=proto, headers=headers)


@pytest.mark.parametrize(
    "fim", ["loadingFailed", "requestServedFromCache", "canalPerdido"]
)
def test_linha_05_fim_obrigatorio(sessao, fim):
    p = pedido()
    evs = eventos(p)
    evs[-1] = evento(p, fim)
    with pytest.raises(t.RespostaInvalida):
        fluxo(sessao, p, evs)


@pytest.mark.parametrize(
    "encoding", [None, "identity", "gzip", "deflate", "br", "zstd"]
)
def test_linha_06_codificacoes_admitidas(sessao, encoding):
    c = fluxo(sessao, encoding=encoding)
    assert c.content_encoding == encoding
    assert c.resposta.body == BODY


@pytest.mark.parametrize("status", [200, 301, 403, 503])
@pytest.mark.parametrize("encoding", ["compress", "gzip, br", "gzip\nbr", ""])
def test_linha_06_todo_status(sessao, status, encoding):
    with pytest.raises(t.RespostaInvalida):
        fluxo(sessao, status=status, encoding=encoding)


@pytest.mark.parametrize("tipo", ["Document", "XHR", "Fetch"])
def test_linha_07_confrontos(sessao, tipo):
    p = pedido() if tipo == "Document" else replace(xhr(), tipo=tipo)
    c = fluxo(
        sessao,
        p,
        encoding="gzip",
        declarado=12,
        encoded_length=12 if tipo != "Document" else 0,
    )
    assert c.resposta.size == len(BODY)
    assert c.encoded_data_length == (12 if tipo != "Document" else None)


@pytest.mark.parametrize(
    "kw,erro",
    [
        ({"declarado": t.MAX_BYTES + 1}, t.TooLarge),
        ({"data_length": t.MAX_BYTES + 1}, t.TooLarge),
        ({"encoded_length": t.MAX_BYTES + 1}, t.TooLarge),
        ({"data_length": len(BODY) + 1}, t.RespostaInvalida),
        ({"declarado": len(BODY) + 1}, t.RespostaInvalida),
        ({"body": b""}, t.EmptyBody),
    ],
)
def test_linha_07_limites(sessao, kw, erro):
    with pytest.raises(erro):
        fluxo(sessao, **kw)


def test_linha_07_xhr_comprimido_incompleto(sessao):
    with pytest.raises(t.RespostaInvalida):
        fluxo(sessao, xhr(), encoding="gzip", declarado=12, encoded_length=11)


def test_linha_07_bomba_descarta():
    s = t.SessaoPortaAssistida(perfil(max_bytes=20), navegador="Brave 158")
    p = pedido()
    c = t.capturar_assistida(s, p)
    try:
        for ev in eventos(p, encoding="gzip", declarado=10):
            c.observar(ev)
    except t.TooLarge:
        assert c._liberada and not c._blocos and s._memoria == 0
    else:
        pytest.fail("bomba admitida")
    finally:
        s.encerrar()


def hsts(**kw):
    d = {
        "url": URL.replace("https:", "http:"),
        "status": 307,
        "headers": {"Non-Authoritative-Reason": "HSTS"},
    }
    d.update(kw)
    return d


def test_linha_08_hsts(sessao):
    p = pedido(
        chave=t.ChaveAssistida("cdp", "aba", "pedido", 1), redirecionamentos=(hsts(),)
    )
    assert fluxo(sessao, p).resposta.final_url == URL


@pytest.mark.parametrize(
    "salto",
    [
        hsts(status=302),
        hsts(remoteIPAddress="8.8.8.8"),
        hsts(headers={}),
        hsts(headers={"Non-Authoritative-Reason": "extension"}),
        hsts(url="http://outro.test/ccivil_03/leis/l6404.htm"),
        hsts(url=URL.replace("https:", "http:") + "?x=1"),
        hsts(url=URL.replace("l6404", "l6385").replace("https:", "http:")),
    ],
)
def test_linha_08_recusa(sessao, salto):
    with pytest.raises(t.BlockedHost):
        fluxo(
            sessao,
            pedido(
                chave=t.ChaveAssistida("cdp", "aba", "pedido", 1),
                redirecionamentos=(salto,),
            ),
        )


@pytest.mark.parametrize("status", [200, 206, 301, 403, 503])
def test_linha_09_desafio_todo_status(sessao, status):
    p = pedido()
    c = t.capturar_assistida(sessao, p)
    for ev in eventos(p, status=status, body=b"<html>CAPTCHA</html>"):
        c.observar(ev)
    for _ in range(2):
        with pytest.raises(t.HTTPStatusError) as exc:
            c.admitir()
        assert exc.value.desafio == "captcha" and exc.value.status == status


def test_linha_09_amostra_fronteira(sessao):
    b = b"<html>" + b"a" * (65536 - 6 - 7) + b"CAPTCHA" + b"x" * 100 + b"</html>"
    with pytest.raises(t.HTTPStatusError) as exc:
        fluxo(sessao, body=b)
    assert exc.value.desafio == "captcha"


@pytest.mark.parametrize(
    "content_type",
    [
        "text/html charset=utf-8",
        "text/html; charset*=x",
        "text/html; token=SEGREDO",
        "text/html; charset=utf-8; charset=utf-16",
        "image/png",
        "application/json-unexpected",
    ],
)
def test_linha_10_content_type(sessao, content_type):
    with pytest.raises(t.RespostaInvalida):
        fluxo(sessao, headers={"Content-Type": content_type})


CASOS = json.loads(load_fixture("0089_streaming_sintetico"))


@pytest.mark.parametrize("caso", CASOS, ids=lambda c: c["nome"])
def test_linha_11_bytes_charset(sessao, caso):
    body = base64.b64decode(caso["base64"])
    if not caso["aceito"]:
        with pytest.raises(t.RespostaInvalida):
            fluxo(sessao, body=body, headers={"Content-Type": caso["content_type"]})
    else:
        c = fluxo(sessao, body=body, headers={"Content-Type": caso["content_type"]})
        assert c.resposta.body == body
        assert c.resposta.sha256 == hashlib.sha256(body).hexdigest()
        assert caso["texto"] in texto_do_response(c.resposta)


@pytest.mark.parametrize(
    "caso,erro",
    [
        ("sem_cabecalhos", t.Timeout),
        ("parcial", t.Timeout),
        ("sem_termino", t.RespostaInvalida),
    ],
)
def test_linha_12_prazo_sem_eventos(sessao, monkeypatch, caso, erro):
    # Timer real com prazo curto; Event.wait evita depender de novos eventos CDP.
    p = pedido()
    c = t.capturar_assistida(sessao, p)
    # Bytes parciais de cabeçalho não geram sinal de resposta completa para a porta.
    if caso == "sem_termino":
        c.observar(eventos(p)[2])
    c._timer.cancel()
    terminou = threading.Event()

    def expirar():
        c._expirar()
        terminou.set()

    c._timer = threading.Timer(0.01, expirar)
    c._timer.start()
    assert terminou.wait(2)
    assert c._erro is erro and c._liberada
    with pytest.raises(erro):
        c.admitir()


def test_linha_12_inclui_admissao(sessao, monkeypatch):
    p = pedido()
    c = t.capturar_assistida(sessao, p)
    for ev in eventos(p):
        c.observar(ev)
    monkeypatch.setattr(t.time, "monotonic", lambda: c._prazo + 0.01)
    with pytest.raises(t.RespostaInvalida):
        c.admitir()


def test_linhas_13_14_16_18_20_sem_efeitos(sessao, monkeypatch):
    def proibido(*a, **kw):
        pytest.fail("porta chamou transporte automático ou rede")

    for nome in (
        "fetch",
        "validate_url",
        "_rate_limiter",
        "_circuit_breaker",
        "_dormir",
        "_contact_headers",
    ):
        monkeypatch.setattr(t, nome, proibido)
    monkeypatch.setattr(t.socket, "getaddrinfo", proibido)
    c1 = fluxo(sessao)
    c2 = fluxo(sessao, pedido(chave=t.ChaveAssistida("cdp", "aba", "outro", 0)))
    assert c1.obtencao_id != c2.obtencao_id
    assert c1.sessao_id == c2.sessao_id
    assert c1.resposta.sha256 == c2.resposta.sha256


def test_linha_15_concorrencia(sessao):
    for n in range(4):
        t.capturar_assistida(
            sessao, pedido(chave=t.ChaveAssistida("cdp", "aba", str(n), 0))
        )
    with pytest.raises(t.RespostaInvalida, match="LIMITE_CANDIDATAS"):
        t.capturar_assistida(
            sessao, pedido(chave=t.ChaveAssistida("cdp", "aba", "5", 0))
        )


def test_linha_15_concorrencia_global(sessao):
    outra = t.SessaoPortaAssistida(perfil(), navegador="Chrome 157")
    try:
        for n in range(4):
            t.capturar_assistida(
                sessao, pedido(chave=t.ChaveAssistida("cdp", "aba", str(n), 0))
            )
        with pytest.raises(t.RespostaInvalida, match="LIMITE_CANDIDATAS"):
            t.capturar_assistida(outra, pedido())
    finally:
        outra.encerrar()


def test_linha_15_pendentes(sessao):
    for n in range(32):
        fluxo(sessao, pedido(chave=t.ChaveAssistida("cdp", "aba", str(n), 0)))
    with pytest.raises(t.RespostaInvalida, match="LIMITE_CANDIDATAS"):
        fluxo(sessao, pedido(chave=t.ChaveAssistida("cdp", "aba", "33", 0)))


def test_linha_15_memoria_invalida_todas(sessao):
    p = pedido()
    c = t.capturar_assistida(sessao, p)
    c.observar(eventos(p)[0])
    sessao.reservar(64 * 1024**2 - sessao._memoria)
    with pytest.raises(t.RespostaInvalida, match="MEMORIA"):
        sessao.reservar(1)
    assert sessao._encerrada and not c._blocos
    with pytest.raises(t.RespostaInvalida):
        c.admitir()


def test_linha_15_blocos_pequenos_contabilizados(sessao):
    p = pedido()
    c = t.capturar_assistida(sessao, p)
    evs = eventos(p)
    evs[0].dados["bufferedData"] = ""
    for ev in evs[:4]:
        c.observar(ev)
    for byte in BODY:
        c.observar(
            evento(
                p,
                "dataReceived",
                data=base64.b64encode(bytes([byte])).decode(),
                dataLength=1,
                encodedDataLength=0,
            )
        )
    assert sessao._memoria >= len(BODY) * 65
    c.observar(evs[-1])
    assert c.admitir().resposta.body == BODY
    assert sessao._memoria == len(BODY) + 64
    c.descartar()
    assert sessao._memoria == 0


def test_linha_15_max_capturas_na_admissao():
    s = t.SessaoPortaAssistida(perfil(max_capturas=1), navegador="Brave 158")
    try:
        p1 = pedido()
        p2 = pedido(chave=t.ChaveAssistida("cdp", "aba", "segundo", 0))
        c1, c2 = t.capturar_assistida(s, p1), t.capturar_assistida(s, p2)
        for c, p in ((c1, p1), (c2, p2)):
            for ev in eventos(p):
                c.observar(ev)
        c1.admitir()
        with pytest.raises(t.RespostaInvalida, match="LIMITE"):
            c2.admitir()
    finally:
        s.encerrar()


@pytest.mark.parametrize(
    "kw",
    [
        {"max_bytes": t.MAX_BYTES + 1},
        {"max_bytes": 0},
        {"max_bytes": True},
        {"max_capturas": 51},
    ],
)
def test_linha_17_perfil_limites(kw):
    with pytest.raises(ValueError, match="PERFIL"):
        perfil(**kw)


@pytest.mark.parametrize(
    "alteracao",
    [
        {"metodo": "POST"},
        {"mimes": frozenset({"application/x-executavel"})},
    ],
)
def test_linha_17_perfil_recurso(alteracao):
    base = perfil()
    with pytest.raises(ValueError, match="PERFIL"):
        replace(base, recursos=(replace(base.recursos[0], **alteracao),))


@pytest.mark.parametrize(
    "cookies,auth,aceita",
    [
        ([], False, True),
        ([{"nome": "TSabcdef", "blockedReasons": []}], False, True),
        ([{"nome": "sessao", "blockedReasons": []}], False, False),
        ([{"nome": "sessao", "blockedReasons": ["SecureOnly"]}], False, True),
        ([], True, False),
    ],
)
def test_linha_19_cookies(sessao, cookies, auth, aceita):
    p = pedido()
    evs = eventos(p)
    evs[1] = evento(
        p,
        "requestWillBeSentExtraInfo",
        authorization_presente=auth,
        associatedCookies=cookies,
    )
    if aceita:
        assert fluxo(sessao, p, evs).resposta.body == BODY
    else:
        with pytest.raises(t.RespostaInvalida):
            fluxo(sessao, p, evs)


def test_linha_21_recibo_mesma_funcao(sessao, monkeypatch):
    observados = []
    original = t.observe_http_response

    def observar(r):
        observados.append(r)
        return original(r)

    monkeypatch.setattr(t, "observe_http_response", observar)
    c = fluxo(
        sessao,
        headers={
            "Set-Cookie": "SECRETO=VALOR",
            "X-Secret": "SEGREDO",
            "Date": "Mon, 01 Jan 2024 00:00:00 GMT",
            "Last-Modified": "Mon, 01 Jan 2024 00:00:00 GMT",
        },
    )
    assert observados
    assert set(c.resposta.headers) <= t.HEADER_NAMES
    assert "SECRETO" not in repr(asdict(c)) and "SEGREDO" not in repr(asdict(c))
    assert c.resposta.headers["date"] == "Mon, 01 Jan 2024 00:00:00 GMT"


@pytest.mark.parametrize(
    "nome", ["fromDiskCache", "fromServiceWorker", "fromPrefetchCache"]
)
@pytest.mark.parametrize("valor", [True, None])
def test_proveniencia_flags_obrigatorios(sessao, nome, valor):
    with pytest.raises(t.RespostaInvalida):
        fluxo(sessao, response={nome: valor})


def test_proveniencia_304_oculto(sessao):
    with pytest.raises(t.RespostaInvalida, match="STATUS"):
        fluxo(sessao, status_cru=304)


@pytest.mark.parametrize(
    "kw",
    [
        {"subtipo_desde_criacao": "prerender"},
        {"subtipo_desde_criacao": None},
        {"pronto": False},
        {"posterior_linha_base": False},
        {"ambiente_conferido": False},
        {"alvo_tipo": "worker"},
        {"frame_id": "iframe"},
        {"metodo": "POST"},
        {"iniciador": {"tipo": "earlyHints"}},
    ],
)
def test_pedido_sem_prova(sessao, kw):
    with pytest.raises(t.RespostaInvalida):
        fluxo(sessao, pedido(**kw))


@pytest.mark.parametrize(
    "headers",
    [
        {"Cache-Control": 'max-age=1, private="X-Test"'},
        {"Vary": "Accept-Encoding, Cookie"},
        {"Vary": "Authorization"},
        {"Vary": "*"},
    ],
)
def test_personalizacao(sessao, headers):
    with pytest.raises(t.RespostaInvalida):
        fluxo(sessao, headers=headers)


def test_streaming_com_data_antes_da_resposta_recusado(sessao):
    p = pedido()
    evs = eventos(p)
    with pytest.raises(t.RespostaInvalida, match="^STREAMING_ASSISTIDO_INVALIDO$"):
        fluxo(sessao, p, evs[1:])


@pytest.mark.parametrize("prefixo", [0, 20, len(BODY)])
def test_streaming_ordem_real_bytes_identicos(sessao, prefixo):
    c = fluxo(sessao, antes_stream=prefixo)
    assert c.resposta.body == BODY
    assert c.resposta.sha256 == hashlib.sha256(BODY).hexdigest()


def test_streaming_soma_varios_eventos_antes_da_resposta(sessao):
    p = pedido()
    evs = eventos(p, antes_stream=20)
    evs[:1] = [
        evento(p, "dataReceived", dataLength=7, encodedDataLength=3),
        evento(p, "dataReceived", dataLength=13, encodedDataLength=5),
    ]
    assert fluxo(sessao, p, evs).resposta.body == BODY


@pytest.mark.parametrize("tipo", ["Fetch", "XHR"])
@pytest.mark.parametrize("encoding", [None, "gzip"])
@pytest.mark.parametrize("violacao", [None, "sem_data_positivo", "codificados"])
def test_streaming_contador_final_sem_data(sessao, tipo, encoding, violacao):
    # Sequência sintética do fetch_identity de diag_trace.txt (quarto ensaio):
    # resposta vazia, dois blocos de 22 bytes, contador final sem data e término.
    # No comprimido, o último evento responde por TODOS os bytes codificados.
    body = b"<html>" + b"a" * 31 + b"</html>"
    assert len(body) == 44
    p = replace(xhr(), tipo=tipo)
    wire = len(gzip.compress(body)) if encoding else len(body)
    evs = eventos(p, body=body, encoding=encoding, declarado=wire)
    evs[-2:-1] = [
        evento(
            p,
            "dataReceived",
            data=base64.b64encode(bloco).decode(),
            dataLength=len(bloco),
            encodedDataLength=0,
        )
        for bloco in (body[:22], body[22:])
    ] + [
        evento(
            p,
            "dataReceived",
            dataLength=1 if violacao == "sem_data_positivo" else 0,
            encodedDataLength=wire + (1 if violacao == "codificados" else 0),
        )
    ]
    if violacao:
        codigo = (
            "STREAMING_ASSISTIDO_INVALIDO"
            if violacao == "sem_data_positivo"
            else "CONTENT_LENGTH_ASSISTIDO_DIVERGENTE"
        )
        if violacao == "codificados" and not encoding:
            # Identity não confronta o contador codificado com Content-Length.
            assert fluxo(sessao, p, evs).encoded_data_length == wire + 1
            return
        with pytest.raises(t.RespostaInvalida, match=f"^{codigo}$"):
            fluxo(sessao, p, evs)
        assert sessao._memoria == 0
    else:
        c = fluxo(sessao, p, evs)
        assert c.resposta.body == body
        assert c.resposta.sha256 == hashlib.sha256(body).hexdigest()
        assert c.encoded_data_length == wire


@pytest.mark.parametrize(
    "caso,codigo",
    [
        ("data_antes", "INVALIDO"),
        ("data_vazio_antes", "INVALIDO"),
        ("buffer_menor", "DIVERGENTE"),
        ("buffer_maior", "DIVERGENTE"),
        ("buffer_vazio_antes", "DIVERGENTE"),
        ("buffer_sem_evento", "DIVERGENTE"),
        ("evento_zero_buffer_vazio", "DIVERGENTE"),
        ("sem_data_depois", "INVALIDO"),
        ("data_menor_depois", "DIVERGENTE"),
        ("data_maior_depois", "DIVERGENTE"),
        ("fim_antes", "TARDIO"),
        ("erro_comando", "INVALIDO"),
    ],
)
def test_streaming_violacoes_ordem_e_tamanho(sessao, caso, codigo):
    p = pedido()
    evs = eventos(p, antes_stream=20)
    if caso in {"data_antes", "data_vazio_antes"}:
        evs[0].dados["data"] = "YQ==" if caso == "data_antes" else ""
    elif caso.startswith("buffer_"):
        evs[1].dados["bufferedData"] = base64.b64encode(
            BODY[:19] if caso == "buffer_menor" else BODY[:21]
        ).decode()
        if caso == "buffer_vazio_antes":
            evs[1].dados["bufferedData"] = ""
        elif caso == "buffer_sem_evento":
            evs.pop(0)
    elif caso == "evento_zero_buffer_vazio":
        evs[0].dados["dataLength"] = 0
        evs[1].dados["bufferedData"] = ""
    elif caso == "sem_data_depois":
        del evs[-2].dados["data"]
    elif caso in {"data_menor_depois", "data_maior_depois"}:
        evs[-2].dados["dataLength"] += 1 if caso == "data_menor_depois" else -1
    elif caso == "fim_antes":
        evs.insert(1, evs.pop())
    else:
        evs[1].dados["erro"] = True
    with pytest.raises(t.RespostaInvalida, match=f"^STREAMING_ASSISTIDO_{codigo}$"):
        fluxo(sessao, p, evs)
    assert sessao._memoria == 0


def test_streaming_divergencias_compensadas_nao_passam(sessao):
    p = pedido()
    evs = eventos(p, antes_stream=20)
    # A soma final seria igual, mas cada trecho tem de conferir isoladamente.
    evs[0].dados["dataLength"] += 1
    evs[-2].dados["dataLength"] -= 1
    with pytest.raises(t.RespostaInvalida, match="^STREAMING_ASSISTIDO_DIVERGENTE$"):
        fluxo(sessao, p, evs)


def test_streaming_reserva_declarada_antes_da_resposta(sessao):
    p = pedido()
    c = t.capturar_assistida(sessao, p)
    evs = eventos(p, antes_stream=20)
    c.observar(evs[0])
    assert sessao._memoria == c._retido == 20
    c.observar(evs[1])
    assert sessao._memoria == c._retido == 20 + 64
    for ev in evs[2:]:
        c.observar(ev)
    assert c.admitir().resposta.body == BODY
    c.descartar()
    assert sessao._memoria == 0


@pytest.mark.parametrize("contador", ["dataLength", "encodedDataLength"])
def test_streaming_limite_conta_eventos_antes_da_resposta(sessao, contador):
    p = pedido()
    c = t.capturar_assistida(sessao, p)
    evs = eventos(p, antes_stream=20)
    evs[0].dados[contador] = sessao.perfil.max_bytes
    c.observar(evs[0])
    excedente = evento(p, "dataReceived", dataLength=0, encodedDataLength=0)
    excedente.dados[contador] = 1
    with pytest.raises(t.TooLarge, match="^TAMANHO_ASSISTIDO_EXCEDIDO$"):
        c.observar(excedente)
    assert sessao._memoria == 0


@pytest.mark.parametrize("contador", ["dataLength", "encodedDataLength"])
def test_streaming_limite_soma_antes_e_depois_da_resposta(contador):
    s = t.SessaoPortaAssistida(perfil(max_bytes=25), navegador="Brave 158")
    try:
        p = pedido()
        c = t.capturar_assistida(s, p)
        dados = {"dataLength": 20, "encodedDataLength": 0}
        dados[contador] = 25
        c.observar(evento(p, "dataReceived", **dados))
        c.observar(
            evento(
                p,
                "streamResourceContent",
                bufferedData=base64.b64encode(BODY[: dados["dataLength"]]).decode(),
            )
        )
        with pytest.raises(t.TooLarge, match="^TAMANHO_ASSISTIDO_EXCEDIDO$"):
            c.observar(
                evento(
                    p, "dataReceived", data="YQ==", dataLength=1, encodedDataLength=1
                )
            )
        assert s._memoria == 0
    finally:
        s.encerrar()


def test_streaming_reserva_declarada_excede_orcamento(sessao):
    p = pedido()
    c = t.capturar_assistida(sessao, p)
    sessao.reservar(64 * 1024**2 - 19)
    with pytest.raises(t.RespostaInvalida, match="MEMORIA"):
        c.observar(eventos(p, antes_stream=20)[0])
    assert sessao._encerrada and c._liberada


def test_correlacao_chave_repetida_invalida(sessao):
    p = pedido()
    c = t.capturar_assistida(sessao, p)
    with pytest.raises(t.RespostaInvalida, match="REPETIDA"):
        t.capturar_assistida(sessao, p)
    assert c._liberada and sessao._encerrada


def test_correlacao_alvos_mesmo_requestid(sessao):
    c1 = fluxo(sessao)
    c2 = fluxo(sessao, pedido(chave=t.ChaveAssistida("cdp2", "aba2", "pedido", 0)))
    assert c1.obtencao_id != c2.obtencao_id


def test_correlacao_evento_de_outro_alvo(sessao):
    c = t.capturar_assistida(sessao, pedido())
    outro = pedido(chave=t.ChaveAssistida("cdp", "terceiro", "pedido", 0))
    with pytest.raises(t.RespostaInvalida, match="CORRELACAO"):
        c.observar(eventos(outro)[0])
    assert sessao._encerrada


def test_extra_info_antes_response(sessao):
    p = pedido()
    evs = eventos(p)
    evs[2], evs[3] = evs[3], evs[2]
    assert fluxo(sessao, p, evs).resposta.body == BODY


def test_extra_info_depois_termino_correlacionado(sessao):
    p = pedido()
    evs = eventos(p)
    extra = evs.pop(3)
    evs.append(extra)
    assert fluxo(sessao, p, evs).resposta.body == BODY


def test_final_apos_103(sessao):
    p = pedido()
    evs = eventos(p)
    evs.insert(
        2, evento(p, "responseReceivedEarlyHints", headers={"link": "</nao-capturado>"})
    )
    assert fluxo(sessao, p, evs).resposta.status == 200


@pytest.mark.parametrize(
    "metodo", ["getResponseBody", "loadingFailed", "requestServedFromCache"]
)
def test_eventos_nao_admitidos(sessao, metodo):
    p = pedido()
    c = t.capturar_assistida(sessao, p)
    with pytest.raises(t.RespostaInvalida):
        c.observar(evento(p, metodo))


def test_linha_21_descarte_duplicatas(sessao):
    p = pedido()
    evs = eventos(p)
    evs[3].dados["headersText"] = (
        evs[3]
        .dados["headersText"]
        .replace(
            "\r\n\r\n",
            "\r\nDate: Mon, 01 Jan 2024 00:00:00 GMT\r\nDate: Mon, 01 Jan 2024 00:00:00 GMT\r\n\r\n",
        )
    )
    c = fluxo(sessao, p, evs)
    assert "date" not in c.resposta.headers


def test_linha_21_limite_recibo(sessao):
    p = pedido()
    evs = eventos(p)
    evs[3].dados["headersText"] = (
        evs[3]
        .dados["headersText"]
        .replace(
            "\r\n\r\n",
            "".join(f"\r\nX-Campo-{n}: a" for n in range(101)) + "\r\n\r\n",
        )
    )
    with pytest.raises(t.RespostaInvalida):
        fluxo(sessao, p, evs)


def test_extra_info_declarado_recusa_imediata(sessao):
    p = pedido()
    c = t.capturar_assistida(sessao, p)
    extra = eventos(p, declarado=t.MAX_BYTES + 1)[3]
    with pytest.raises(t.TooLarge):
        c.observar(extra)
    assert c._liberada


def test_reserva_precede_decodificacao(sessao, monkeypatch):
    original = t.base64.b64decode

    def verificar(valor, **kw):
        assert sessao._memoria >= len(valor) + (len(valor) // 4) * 3
        return original(valor, **kw)

    monkeypatch.setattr(t.base64, "b64decode", verificar)
    assert fluxo(sessao).resposta.body == BODY


@pytest.mark.parametrize("erro_stream", [True, "erro"])
def test_streaming_com_falha(sessao, erro_stream):
    p = pedido()
    evs = eventos(p)
    evs[0].dados["erro"] = erro_stream
    with pytest.raises(t.RespostaInvalida, match="STREAMING"):
        fluxo(sessao, p, evs)


def test_streaming_base64_invalido(sessao):
    p = pedido()
    evs = eventos(p)
    evs[0].dados["bufferedData"] = "!invalido"
    with pytest.raises(t.RespostaInvalida):
        fluxo(sessao, p, evs)
    assert sessao._memoria == 0


@pytest.mark.parametrize(
    "nome", ["responseReceived", "responseReceivedExtraInfo", "loadingFinished"]
)
def test_metadado_ausente_nao_inferido(sessao, nome):
    p = pedido()
    evs = [ev for ev in eventos(p) if ev.metodo != nome]
    with pytest.raises(t.RespostaInvalida):
        fluxo(sessao, p, evs)


@pytest.mark.parametrize("chave", ["alvo", "frame_id", "documento", "tipo"])
def test_xhr_iniciador_sem_prova(sessao, chave):
    p = xhr()
    p.iniciador.pop(chave)
    with pytest.raises(t.RespostaInvalida):
        fluxo(sessao, p)


def test_segredos_erros_sanitizados(sessao):
    p = pedido(url=URL + "?token=SEGREDO")
    with pytest.raises(t.BlockedHost) as exc:
        fluxo(sessao, p)
    assert "SEGREDO" not in str(exc.value)
    assert "SEGREDO" not in repr(p)


@pytest.mark.parametrize(
    "body", [codecs.BOM_UTF8 + BODY, BODY, b'<meta charset="utf-8">' + BODY]
)
@pytest.mark.parametrize(
    "parametro",
    [
        "charset=TOKEN_SECRETO",
        "charset=rot_13",
        "charset=utf-8; charset=utf-8",
        "charset=utf-8; charset=UTF8",
        'charset=" utf-8 "',
        'charset="utf\\-8"',
        "charset='utf-8'",
        "charset=utf-8; token=TOKEN_SECRETO",
        "token=TOKEN_SECRETO",
    ],
)
def test_content_type_assistido_recusa_antes_de_response(
    sessao, monkeypatch, body, parametro
):
    def proibido(*_, **__):
        pytest.fail("cabeçalho recusado não pode construir objeto persistível")

    monkeypatch.setattr(t, "Response", proibido)
    monkeypatch.setattr(t, "CapturaAssistida", proibido)
    with pytest.raises(t.RespostaInvalida) as exc:
        fluxo(sessao, body=body, headers={"Content-Type": "text/html; " + parametro})
    assert str(exc.value) == "CONTENT_TYPE_ASSISTIDO_INVALIDO"
    assert exc.value.http is None
    assert sessao._memoria == 0


@pytest.mark.parametrize(
    "parametro,canonico",
    [
        ("CHARSET=UtF8", "utf-8"),
        ('charset="UTF-8"', "utf-8"),
        ("charset=LaTiN1", "windows-1252"),
        ("charset=WINDOWS-1252", "windows-1252"),
        ("charset=Shift_JIS", "shift_jis"),
    ],
)
def test_content_type_assistido_canonico_independente_do_bom(
    sessao, parametro, canonico
):
    c = fluxo(
        sessao,
        body=codecs.BOM_UTF8 + BODY,
        headers={"Content-Type": "Text/HTML; " + parametro},
    )
    assert c.resposta.content_type == "text/html; charset=" + canonico
    assert c.codificacao == "utf-8-sig"
    assert c.origem_da_codificacao == "bom"
    assert all(v != "Text/HTML; " + parametro for v in c.resposta.headers.values())


def test_conteudo_publico_limite_declarado(sessao):
    # Valor satisfaz a gramática pública: a sintaxe não prova ausência de segredo.
    p = pedido(url=URL.replace("l6404", "SEGREDO"))
    b = b"<html>Nome publicado: Pessoa sintetica</html>"
    c = fluxo(sessao, p, body=b)
    assert "SEGREDO" in c.resposta.url
    assert c.resposta.body == b
    assert not hasattr(c, "dados_pessoais")


def test_sem_verified_ou_renovacao_frescor(sessao):
    c = fluxo(sessao)
    assert "verified" not in asdict(c) and not hasattr(c, "identity")
    assert datetime.fromisoformat(c.resposta.fetched_at).year == 2023
    assert not hasattr(c, "vigente_na_fonte")


def test_cauda_planalto_modelo_literal(sessao):
    modelo = (
        Path(__file__).parents[1] / "freoa_verifica/data/planalto_cauda_0089.bin"
    ).read_bytes()
    assert len(modelo) == 1440
    assert hashlib.sha256(modelo).hexdigest() == t._CAUDA_PLANALTO_SHA256
    a = BODY + modelo.replace(b"<TOKEN>", b"A" * 128)
    b = BODY + modelo.replace(b"<TOKEN>", b"P" * 128)
    c1 = fluxo(sessao, body=a)
    c2 = fluxo(sessao, pedido(chave=t.ChaveAssistida("cdp", "aba", "outra", 0)), body=b)
    assert c1.resposta.sha256 != c2.resposta.sha256
    assert (
        t.comparar_capturas_assistidas(c1, c2, fonte="planalto", extrair=lambda s: s)
        is True
    )
    assert c1.resposta.body == a


@pytest.mark.parametrize(
    "mudanca",
    ["diferente", "duplicada", "deslocada", "ausente", "inserida", "malformada"],
)
def test_cauda_planalto_nao_afirma(sessao, mudanca):
    modelo = (
        Path(__file__).parents[1] / "freoa_verifica/data/planalto_cauda_0089.bin"
    ).read_bytes()
    cauda = modelo.replace(b"<TOKEN>", b"A" * 128)
    orig = BODY + cauda
    corpos = {
        "diferente": orig + b" ",
        "duplicada": orig + cauda,
        "deslocada": BODY[:-7] + cauda + b"</html>",
        "ausente": BODY,
        "inserida": orig + b"Texto",
        "malformada": BODY + cauda.replace(b"A" * 128, b"Z" * 128),
    }
    c = fluxo(sessao, body=corpos[mudanca])
    assert (
        t.comparar_capturas_assistidas(c, c, fonte="planalto", extrair=lambda s: s)
        is None
    )


@pytest.mark.repositorio
def test_porta_unica_ast():
    raiz = Path(__file__).parents[1] / "freoa_verifica"
    for arquivo in raiz.rglob("*.py"):
        if arquivo.name == "transport.py":
            continue
        arvore = ast.parse(arquivo.read_text(encoding="utf-8-sig"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.Attribute):
                assert no.attr not in {
                    "_CapturaAssistidaEmCurso",
                    "streamResourceContent",
                    "getResponseBody",
                }, arquivo
            if isinstance(no, ast.ImportFrom):
                assert all(n.name != "_CapturaAssistidaEmCurso" for n in no.names), (
                    arquivo
                )


@pytest.mark.repositorio
def test_automatico_corpo_das_funcoes_preservado():
    # D5: a prova dinâmica é a suíte anterior sem alteração. Este teste adicional
    # impede referências ao caminho assistido nas primitivas automáticas.
    arvore = ast.parse(Path(t.__file__).read_text(encoding="utf-8"))
    for no in arvore.body:
        if isinstance(no, (ast.FunctionDef, ast.ClassDef)) and no.name in {
            "fetch",
            "_percorrer",
            "_fetch_once",
            "validate_url",
            "revalidar_captura",
        }:
            assert not any(
                isinstance(n, ast.Name) and "assistid" in n.id for n in ast.walk(no)
            )
