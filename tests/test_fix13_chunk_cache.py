"""FIX13/F-13 e F-16.

F-13: extensões de chunk pela gramática da RFC 9112 §7.1.1 (servidor TCP cru, 200 e 503).
F-16: a identidade do cache preserva a query como enviada e inclui método, corpo e cabeçalhos do chamador;
com cache = sem cache, exceto pelo número de pedidos (servidor local cujo corpo depende da query e de cabeçalhos).
"""

from __future__ import annotations

import http.server
import threading

import pytest

from freoa_verifica import transport
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.guarda import GuardaExecucao
from freoa_verifica.connectors.httputil import connector_fetch
from tests.test_fix12_sintaxe_estrita import _TE, _buscar, _resposta, _servidor
from tests.test_transport import _fast_guards, _wire_local

# --- F-13 ---------------------------------------------------------------------------------------

_FIM = b"\r\nhello\r\n0\r\n\r\n"

INVALIDAS = {
    "ext_nul": b"5;\x00" + _FIM,
    "aspas_sem_fechar": b'5;x="unfinished' + _FIM,
    "ext_sem_nome": b"5;=x" + _FIM,
    "valor_vazio": b"5;x=" + _FIM,
    "ext_sem_nome_e_sem_valor": b"5;" + _FIM,
    "prefixo_0x": b"0x5" + _FIM,
    "tab_depois_do_tamanho": b"5\t" + _FIM,
    "espaco_depois_do_tamanho": b"5 " + _FIM,
    "espaco_final_na_ext": b"5;x " + _FIM,
    "nome_com_separador": b"5;x(y)=1" + _FIM,
    "valor_token_invalido": b"5;x=a b" + _FIM,
    "aspas_com_ctl": b'5;x="a\x01b"' + _FIM,
    "quoted_pair_com_ctl": b'5;x="a\\\x01b"' + _FIM,
    "lixo_depois_do_valor_citado": b'5;x="a"b' + _FIM,
    "sinal_no_tamanho": b"+5" + _FIM,
}

VALIDAS = {
    "ext_simples": b"5;x" + _FIM,
    "ext_com_token": b"5;x=y" + _FIM,
    "quoted_pair": b'5;x="a\\"b"' + _FIM,
    "ext_sem_valor_depois_de_outra": b"5;x=y;z" + _FIM,
    "bws_antes_do_ponto_e_virgula": b"5 ;x" + _FIM,
    "bws_em_volta_do_igual": b"5;x = y" + _FIM,
    "quoted_vazio": b'5;x=""' + _FIM,
    "quoted_com_htab_e_obs_text": b'5;x="a\tb\xe9"' + _FIM,
    "duas_ext": b'5;a=1;b="2"' + _FIM,
    "tamanho_maiusculo": b"5;X=Y" + _FIM,
}


@pytest.mark.parametrize("status", [200, 503])
@pytest.mark.parametrize("variante", sorted(INVALIDAS))
def test_extensao_de_chunk_invalida_e_resposta_inesperada_sem_repeticao(monkeypatch, variante, status):
    server, pedidos = _servidor(_resposta(status, None, _TE, INVALIDAS[variante]))
    try:
        with pytest.raises(Unavailable) as ei:
            _buscar(monkeypatch, server)
    finally:
        server.shutdown()
    assert ei.value.categoria == "resposta_inesperada", ei.value.reason
    assert len(pedidos) == 1


@pytest.mark.parametrize("caso", sorted(VALIDAS))
def test_extensao_de_chunk_valida_continua_aceita(monkeypatch, caso):
    server, pedidos = _servidor(_resposta(200, None, _TE, VALIDAS[caso]))
    try:
        resp = _buscar(monkeypatch, server)
    finally:
        server.shutdown()
    assert resp.body == b"hello" and len(pedidos) == 1


def test_extensao_na_ultima_chunk_e_validada(monkeypatch):
    for corpo, ok in ((b"5\r\nhello\r\n0;fim=1\r\n\r\n", True), (b"5\r\nhello\r\n0;=1\r\n\r\n", False)):
        server, _ = _servidor(_resposta(200, None, _TE, corpo))
        try:
            if ok:
                assert _buscar(monkeypatch, server).body == b"hello"
            else:
                with pytest.raises(Unavailable) as ei:
                    _buscar(monkeypatch, server)
                assert ei.value.categoria == "resposta_inesperada"
        finally:
            server.shutdown()


# --- F-16 ---------------------------------------------------------------------------------------

HOST = "www.planalto.gov.br"


class _Eco(http.server.BaseHTTPRequestHandler):
    """O corpo depende da query CRUA, de X-Representation e de Accept: o servidor diferencia o que o cliente não vê."""

    def do_GET(self):
        self._responder()

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self._responder()

    def _responder(self):
        self.server.pedidos.append(self.path)
        corpo = "|".join(
            (self.command, self.path, self.headers.get("X-Representation", "-"), self.headers.get("Accept", "-"))
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *a):
        pass


@pytest.fixture
def eco(monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    _fast_guards(monkeypatch)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Eco)
    server.daemon_threads = True
    server.pedidos = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _wire_local(monkeypatch, server.server_address[1])
    yield server
    server.shutdown()
    server.server_close()


def _pedir(caminho, headers=None, metodo="GET", corpo=None):
    return connector_fetch(
        f"https://{HOST}{caminho}", hosts=frozenset({HOST}), path_prefixes=None,
        mimes=frozenset({"text/html"}), headers=headers, method=metodo, body=corpo,
    ).body


REQUISICOES = {
    "query_ordem_a": ("/x?a=1&a=2", None, "GET", None),
    "query_ordem_b": ("/x?a=2&a=1", None, "GET", None),
    "query_codificada": ("/x?a=%7e", None, "GET", None),
    "query_decodificada": ("/x?a=~", None, "GET", None),
    "repr_one": ("/x", {"X-Representation": "one"}, "GET", None),
    "repr_two": ("/x", {"X-Representation": "two"}, "GET", None),
    "accept_html":("/x", {"Accept": "text/html"}, "GET", None),
    "accept_outro": ("/x", {"Accept": "text/plain"}, "GET", None),
    "sem_cabecalho": ("/x", None, "GET", None),
    "post": ("/x", None, "POST", b"a=1"),
    "post_outro_corpo": ("/x", None, "POST", b"a=2"),
}


@pytest.mark.parametrize("b", sorted(REQUISICOES))
@pytest.mark.parametrize("a", sorted(REQUISICOES))
def test_com_cache_igual_a_sem_cache_exceto_o_numero_de_pedidos(eco, a, b):
    ra, rb = REQUISICOES[a], REQUISICOES[b]
    sem_cache = [_pedir(*ra), _pedir(*rb)]
    antes = len(eco.pedidos)
    with GuardaExecucao().ativar():
        com_cache = [_pedir(*ra), _pedir(*rb)]
    assert com_cache == sem_cache
    assert len(eco.pedidos) - antes == (1 if a == b else 2)


def test_mesma_requisicao_repetida_e_um_pedido(eco):
    with GuardaExecucao().ativar():
        for _ in range(3):
            _pedir("/x?a=1&a=2", {"X-Representation": "one", "Accept": "text/html"})
    assert len(eco.pedidos) == 1


def test_ordem_e_caixa_dos_cabecalhos_nao_distinguem():
    a = transport.identidade_requisicao("GET", f"https://{HOST}/x", None, {"X-A": "1", "Accept": "t"})
    b = transport.identidade_requisicao("GET", f"https://{HOST}/x", None, {"accept": "t", "x-a": "1"})
    assert a == b
    assert a != transport.identidade_requisicao("GET", f"https://{HOST}/x", None, {"accept": "t", "x-a": "2"})
    assert a != transport.identidade_requisicao("GET", f"https://{HOST}/x")


def test_query_nao_e_reordenada_nem_decodificada():
    ident = lambda q: transport.identidade_requisicao("GET", f"https://{HOST}/x{q}")  # noqa: E731
    assert ident("?a=1&a=2") != ident("?a=2&a=1")
    assert ident("?a=%7e") != ident("?a=~")
    assert ident("?a=%7e") != ident("?a=%7E")
    assert ident("?a=1#frag") == ident("?a=1")
