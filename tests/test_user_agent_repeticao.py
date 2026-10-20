"""T2 (decisão 0048): User-Agent identificado de fonte única. T1: repetição limitada do transporte."""

from __future__ import annotations

import ast
import hashlib
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

import pytest

from freoa_verifica import __version__
from freoa_verifica import identidade_http as ih
from freoa_verifica import transport as tr
from freoa_verifica.connectors import challenge, httputil
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.bcb import BcbConnector
from freoa_verifica.connectors.cvm_colegiado import CvmColegiadoConnector
from freoa_verifica.connectors.cvm_normas import CvmNormasConnector
from freoa_verifica.connectors.datajud import DatajudConnector
from freoa_verifica.connectors.planalto import PlanaltoConnector
from freoa_verifica.connectors.senado import SenadoConnector
from freoa_verifica.connectors.stf import StfConnector
from freoa_verifica.connectors.stj import StjConnector
from freoa_verifica.connectors.tcu import TcuConnector
from freoa_verifica.connectors.tjdft import TjdftConnector
from freoa_verifica.connectors.tjsp import TjspConnector

CLASSES = [
    BcbConnector, CvmColegiadoConnector, CvmNormasConnector, DatajudConnector, PlanaltoConnector,
    SenadoConnector, StfConnector, StjConnector, TcuConnector, TjdftConnector, TjspConnector,
]
UA_1_2_0 = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
HOST = "example.org"
URL = f"https://{HOST}/x"
HOSTS = frozenset({HOST})


# ---------- T2: User-Agent ----------

def test_string_identificada_contem_versao_e_repositorio():
    assert ih.USER_AGENT_IDENTIFICADO == f"freoa-verifica/{__version__} (+https://github.com/rickfreoa/freoa-verifica)"
    assert __version__ in ih.USER_AGENT_IDENTIFICADO


def test_ua_de_navegador_e_exatamente_o_da_1_2_0():
    assert ih.USER_AGENT_NAVEGADOR_1_2_0 == UA_1_2_0


def test_tabela_cobre_todos_os_conectores_e_so_planalto_e_excecao():
    assert set(ih.UA_POR_CONECTOR) == {c.id for c in CLASSES}
    assert {k for k, v in ih.UA_POR_CONECTOR.items() if v != ih.MODO_IDENTIFICADO} == {"planalto"}
    assert ih.UA_POR_CONECTOR["planalto"] == "navegador_1_2_0"


def test_defaults_vem_da_fonte_unica():
    assert tr._contact_headers()["User-Agent"] == ih.USER_AGENT_IDENTIFICADO
    assert not hasattr(tr, "DEFAULT_USER_AGENT")
    with pytest.raises(ValueError):
        httputil.ua_header("browser")  # sem fallback silencioso de identidade


@pytest.mark.parametrize("cls", CLASSES, ids=lambda c: c.id)
def test_cada_conector_envia_o_ua_da_tabela(cls, monkeypatch):
    assert cls.user_agent == ih.UA_POR_CONECTOR[cls.id]
    vistos = []

    def falso(url, **kw):
        vistos.append(kw["headers"]["User-Agent"])
        return tr.Response(url, url, 200, {}, b"ok", hashlib.sha256(b"ok").hexdigest(), "2026-01-01T00:00:00+00:00", [], "text/plain")

    monkeypatch.setattr(httputil, "transport_fetch", falso)
    httputil.connector_fetch(URL, hosts=HOSTS, path_prefixes=None, mimes=frozenset({"text/plain"}), user_agent=cls.user_agent)
    esperado = UA_1_2_0 if cls.id == "planalto" else ih.USER_AGENT_IDENTIFICADO
    assert vistos == [esperado]


def test_todo_connector_fetch_dos_conectores_passa_user_agent():
    raiz = Path(__file__).resolve().parents[1] / "freoa_verifica" / "connectors"
    sem_ua = []
    for arq in sorted(raiz.glob("*.py")):
        if arq.name == "httputil.py":
            continue
        for no in ast.walk(ast.parse(arq.read_text(encoding="utf-8"))):
            if isinstance(no, ast.Call) and getattr(no.func, "id", None) == "connector_fetch":
                if "user_agent" not in {k.arg for k in no.keywords}:
                    sem_ua.append(f"{arq.name}:{no.lineno}")
    assert sem_ua == []


def test_403_nao_provoca_segundo_pedido_com_outro_ua(monkeypatch):
    pedidos = []

    def recusa(url, **kw):
        pedidos.append(kw["headers"]["User-Agent"])
        raise tr.HTTPStatusError(403)

    monkeypatch.setattr(httputil, "transport_fetch", recusa)
    with pytest.raises(Unavailable) as ei:
        httputil.connector_fetch(URL, hosts=HOSTS, path_prefixes=None, mimes=frozenset({"text/plain"}), user_agent="identified")
    assert pedidos == [ih.USER_AGENT_IDENTIFICADO]
    assert ei.value.categoria == "recusa_identificado"


def test_401_sem_marcador_e_recusa_identificado():
    u = challenge.map_transport_error(tr.HTTPStatusError(401), URL)
    assert u.categoria == "recusa_identificado"


def test_403_com_marcador_de_desafio_e_ambiental():
    u = challenge.map_transport_error(tr.HTTPStatusError(403, desafio="captcha"), URL)
    assert u.categoria == "ambiental_desafio" and u.reason == "desafio_captcha"


# ---------- T1: repetição ----------

class _Balde:
    def __init__(self):
        self.tokens = 0

    def acquire(self, *, timeout=30.0):
        self.tokens += 1


@pytest.fixture
def mundo(monkeypatch):
    """Relógio (sono) e servidor simulados: `roteiro` é a lista de respostas/erros por tentativa."""
    tr.reset_guards()
    m = type("Mundo", (), {})()
    m.balde, m.chamadas, m.sonos, m.roteiro = _Balde(), [], [], []
    monkeypatch.setattr(tr, "_rate_limiter", lambda host: m.balde)
    monkeypatch.setattr(tr, "_dormir", m.sonos.append)
    monkeypatch.setattr(tr, "_sortear", lambda a, b: 0.0)

    def uma_vez(url, **kw):
        m.chamadas.append(kw["method"])
        item = m.roteiro[len(m.chamadas) - 1]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(tr, "_fetch_once", uma_vez)
    m.fetch = lambda **kw: tr.fetch(URL, allowed_hosts=HOSTS, **kw)
    m.falhas = lambda: tr._circuit_breaker(HOST).failures
    yield m
    tr.reset_guards()


def _ok():
    return tr.Response(URL, URL, 200, {}, b"ok", hashlib.sha256(b"ok").hexdigest(), "2026-01-01T00:00:00+00:00", [], "text/plain")


def _com_retry_after(status, valor):
    return tr.HTTPStatusError(status, http=tr.HTTPMetadata(status, (("retry-after", valor),)))


def test_503_depois_200_sucesso_com_duas_tentativas(mundo):
    mundo.roteiro = [tr.HTTPStatusError(503), _ok()]
    assert mundo.fetch().body == b"ok"
    assert mundo.chamadas == ["GET", "GET"]
    assert mundo.balde.tokens == 2  # cada tentativa consome o balde
    assert mundo.sonos == [1.0]
    assert mundo.falhas() == 0


def test_backoff_1s_2s_e_esgota_em_duas_repeticoes(mundo):
    mundo.roteiro = [tr.HTTPStatusError(502), tr.HTTPStatusError(504), tr.HTTPStatusError(503)]
    with pytest.raises(tr.HTTPStatusError) as ei:
        mundo.fetch()
    assert ei.value.status == 503
    assert len(mundo.chamadas) == 3 and mundo.sonos == [1.0, 2.0]


def test_breaker_conta_uma_falha_logica_apos_a_ultima_tentativa(mundo):
    mundo.roteiro = [tr.HTTPStatusError(503)] * 3
    with pytest.raises(tr.HTTPStatusError):
        mundo.fetch()
    assert len(mundo.chamadas) == 3 and mundo.falhas() == 1


def test_503_com_pagina_de_waf_nao_repete(mundo):
    mundo.roteiro = [tr.HTTPStatusError(503, desafio="aws_waf")]
    with pytest.raises(tr.HTTPStatusError):
        mundo.fetch()
    assert len(mundo.chamadas) == 1 and mundo.sonos == [] and mundo.falhas() == 1


@pytest.mark.parametrize("status", [403, 429, 401, 500])
def test_status_nao_repetiveis(mundo, status):
    mundo.roteiro = [tr.HTTPStatusError(status), _ok()]
    with pytest.raises(tr.HTTPStatusError):
        mundo.fetch()
    assert len(mundo.chamadas) == 1 and mundo.sonos == []


def test_retry_after_maior_que_o_orcamento_nao_dorme(mundo):
    mundo.roteiro = [_com_retry_after(503, "3600"), _ok()]
    with pytest.raises(tr.HTTPStatusError) as ei:
        mundo.fetch(timeout=5)
    assert len(mundo.chamadas) == 1 and mundo.sonos == []
    assert challenge.map_transport_error(ei.value, URL).categoria == "fonte_fora"
    assert challenge.map_transport_error(ei.value, URL).evidencia["retry_after"] == "3600"


def test_retry_after_em_segundos_e_respeitado(mundo):
    mundo.roteiro = [_com_retry_after(503, "3"), _ok()]
    mundo.fetch(timeout=30)
    assert mundo.sonos == [3.0]


def test_retry_after_em_data_http(mundo):
    data = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=10), usegmt=True)
    mundo.roteiro = [_com_retry_after(503, data), _ok()]
    mundo.fetch(timeout=30)
    assert len(mundo.sonos) == 1 and 5.0 < mundo.sonos[0] <= 10.0


def test_retry_after_em_data_maior_que_o_orcamento(mundo):
    data = format_datetime(datetime.now(timezone.utc) + timedelta(hours=1), usegmt=True)
    mundo.roteiro = [_com_retry_after(503, data), _ok()]
    with pytest.raises(tr.HTTPStatusError):
        mundo.fetch(timeout=5)
    assert mundo.sonos == []


def test_post_sem_idempotente_nao_repete(mundo):
    mundo.roteiro = [tr.HTTPStatusError(503), _ok()]
    with pytest.raises(tr.HTTPStatusError):
        mundo.fetch(method="POST", body=b"a=1")
    assert mundo.chamadas == ["POST"]


def test_post_idempotente_repete(mundo):
    mundo.roteiro = [tr.HTTPStatusError(503), _ok()]
    assert mundo.fetch(method="POST", body=b"a=1", idempotente=True).body == b"ok"
    assert mundo.chamadas == ["POST", "POST"]


def test_falha_de_conexao_em_get_repete(mundo):
    mundo.roteiro = [tr.TransportError("reset"), _ok()]
    assert mundo.fetch().body == b"ok" and len(mundo.chamadas) == 2


def test_falha_de_conexao_em_post_nao_repete(mundo):
    mundo.roteiro = [tr.TransportError("reset"), _ok()]
    with pytest.raises(tr.TransportError):
        mundo.fetch(method="POST", body=b"a=1")
    assert len(mundo.chamadas) == 1


@pytest.mark.parametrize("erro", [tr.RespostaInvalida("x"), tr.BlockedHost("x"), tr.TransporteLento("x"), tr.EmptyBody("x")])
def test_erros_de_resposta_nao_repetem(mundo, erro):
    mundo.roteiro = [erro, _ok()]
    with pytest.raises(tr.TransportError):
        mundo.fetch()
    assert len(mundo.chamadas) == 1


def test_repeticao_zero_desliga_e_invalida_e_recusada(mundo):
    mundo.roteiro = [tr.HTTPStatusError(503), _ok()]
    with pytest.raises(tr.HTTPStatusError):
        mundo.fetch(repeticao=0)
    assert len(mundo.chamadas) == 1
    for ruim in (-1, True, "2"):
        with pytest.raises(ValueError):
            mundo.fetch(repeticao=ruim)


def test_espera_que_nao_cabe_no_prazo_encerra_sem_dormir(mundo):
    mundo.roteiro = [tr.HTTPStatusError(503), _ok()]
    with pytest.raises(tr.HTTPStatusError):
        mundo.fetch(timeout=0.5)  # backoff de 1s excede o orçamento
    assert mundo.sonos == [] and len(mundo.chamadas) == 1


# ---------- cabeçalho Retry-After e detecção de desafio em erro ----------

class _RespostaFalsa:
    def __init__(self, status, headers, corpo=b""):
        self.status, self._h, self._corpo = status, headers, corpo

    def getheaders(self):
        return list(self._h)

    def getheader(self, nome, default=None):
        return dict((k.lower(), v) for k, v in self._h).get(nome.lower(), default)

    def read1(self, n):
        corpo, self._corpo = self._corpo[:n], b""
        return corpo


def test_retry_after_preservado_nos_cabecalhos_registrados():
    meta = tr.observe_http_response(_RespostaFalsa(503, [("Retry-After", "7"), ("X-Outro", "a")]))
    assert dict(meta.headers) == {"retry-after": "7"}
    data = format_datetime(datetime(2030, 1, 1, tzinfo=timezone.utc), usegmt=True)
    assert dict(tr.observe_http_response(_RespostaFalsa(503, [("Retry-After", data)])).headers) == {"retry-after": data}
    assert tr.observe_http_response(_RespostaFalsa(503, [("Retry-After", "logo")])).headers == ()


def test_desafio_na_resposta_de_erro_por_corpo_e_por_cabecalho():
    assert tr._desafio_na_resposta(_RespostaFalsa(503, [], b"<html>Please solve this CAPTCHA</html>")) == "captcha"
    assert tr._desafio_na_resposta(_RespostaFalsa(403, [("X-Amzn-Waf-Action", "challenge")])) == "aws_waf"
    assert tr._desafio_na_resposta(_RespostaFalsa(503, [], b"Service Unavailable")) is None
