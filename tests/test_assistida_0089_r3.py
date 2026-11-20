"""Auditoria Codex r3: projeções CDP sintéticas, sem navegador ou rede."""

from copy import deepcopy
from itertools import product

import pytest

from freoa_verifica.assistida.ambiente import RecusaSessao
from freoa_verifica.assistida.cdp import Alvo
from tests.assistida_0089_util import (
    BODY,
    URL,
    adapter,
    entregar,
    request,
    sessao as sessao,
)
from tests.test_transport_assistida_0089 import eventos, pedido


PEDIDO = {
    "request": {"url": URL, "method": "GET"},
    "type": "Document",
    "frameId": "raiz",
    "documentURL": URL,
    "timestamp": 100.0,
    "wallTime": 1_700_000_000.0,
    "initiator": {"type": "other"},
}
PROJECOES = {
    "requestWillBeSent": PEDIDO,
    "requestWillBeSentExtraInfo": {"headers": {}, "associatedCookies": []},
    **{
        e.metodo: e.dados
        for e in eventos(pedido(), body=BODY)
        if e.metodo in {"responseReceived", "responseReceivedExtraInfo"}
    },
}
AUSENCIAS = {
    "requestWillBeSent": [
        ("initiator",),
        ("initiator", "type"),
        ("frameId",),
        ("documentURL",),
        ("timestamp",),
        ("wallTime",),
    ],
    "requestWillBeSentExtraInfo": [("headers",), ("associatedCookies",)],
    "responseReceivedExtraInfo": [("headers",), ("blockedCookies",), ("statusCode",)],
    "responseReceived": [
        ("response", k)
        for k in (
            "securityDetails",
            "fromDiskCache",
            "fromServiceWorker",
            "fromPrefetchCache",
            "url",
            "status",
            "protocol",
            "securityState",
            "remoteIPAddress",
            "remotePort",
        )
    ]
    + [("response", "securityDetails", k) for k in ("protocol", "issuer")],
}
DEFEITOS = {
    "requestWillBeSent": [
        (("initiator",), None),
        (("initiator", "type"), None),
        (("frameId",), []),
        (("documentURL",), None),
        (("timestamp",), None),
        (("wallTime",), None),
    ],
    "requestWillBeSentExtraInfo": [
        (("headers",), None),
        (("headers",), {"Authorization": None}),
        (("associatedCookies",), None),
        (("associatedCookies",), [None]),
        (("associatedCookies",), [{"cookie": None, "blockedReasons": []}]),
        (("associatedCookies",), [{"cookie": {"name": None}, "blockedReasons": []}]),
        (("associatedCookies",), [{"cookie": {"name": "x"}, "blockedReasons": [None]}]),
    ],
    "responseReceivedExtraInfo": [
        (("headers",), None),
        (("headers",), {"Content-Type": None}),
        (("statusCode",), "bad"),
        (("statusCode",), True),
        (("blockedCookies",), None),
        (("blockedCookies",), [None]),
        (("blockedCookies",), [{"cookieLine": None, "blockedReasons": []}]),
        (("blockedCookies",), [{"cookieLine": "x", "blockedReasons": [None]}]),
        (
            ("blockedCookies",),
            [{"cookieLine": "x", "blockedReasons": [], "cookie": None}],
        ),
        (
            ("blockedCookies",),
            [{"cookieLine": "x", "blockedReasons": [], "cookie": {"name": None}}],
        ),
        (("headersText",), None),
    ],
    "responseReceived": [
        (("response",), None),
        *[
            (("response", k), None)
            for k in (
                "securityDetails",
                "fromDiskCache",
                "fromServiceWorker",
                "fromPrefetchCache",
                "url",
                "status",
                "protocol",
                "securityState",
                "remoteIPAddress",
                "remotePort",
            )
        ],
        (("response", "status"), True),
        (("response", "remotePort"), True),
        *[(("response", "securityDetails", k), None) for k in ("protocol", "issuer")],
    ],
}


def alterar(dados, caminho, valor=None, *, remover=False):
    for k in caminho[:-1]:
        dados = dados[k]
    if remover:
        del dados[caminho[-1]]
    else:
        dados[caminho[-1]] = deepcopy(valor)


def enviar(ad, metodo, dados, *, sid="cdp", rid="ruim"):
    ad.processar(
        {
            "sessionId": sid,
            "method": "Network." + metodo,
            "params": {"requestId": rid, **dados},
        }
    )


def preparar(sessao, metodo):
    ad = adapter(sessao)
    if metodo != "requestWillBeSent":
        request(ad, rid="ruim")
    return ad


def conferir_encerramento(ad, sessao):
    assert ad.fechado and sessao._encerrada
    assert all(c.admitida is None for c in ad.pedidos.values())
    with pytest.raises(RecusaSessao, match="SESSAO_ASSISTIDA_ENCERRADA"):
        request(ad, rid="posterior")
    ad.descartar()


@pytest.mark.parametrize(
    "metodo,dados",
    [
        ("requestWillBeSentExtraInfo", {"associatedCookies": [None]}),
        ("responseReceivedExtraInfo", {"statusCode": "bad", "blockedCookies": []}),
    ],
)
def test_reproducoes_parecer_r3_encerram(sessao, metodo, dados):
    ad = preparar(sessao, metodo)
    with pytest.raises(RecusaSessao, match="EVENTO_CDP_INVALIDO"):
        enviar(ad, metodo, dados)
    conferir_encerramento(ad, sessao)


@pytest.mark.parametrize(
    "metodo,caminho", [(m, c) for m, caminhos in AUSENCIAS.items() for c in caminhos]
)
def test_ausencia_pura_recusa_so_candidata(sessao, metodo, caminho):
    ad = preparar(sessao, metodo)
    dados = deepcopy(PROJECOES[metodo])
    alterar(dados, caminho, remover=True)
    enviar(ad, metodo, dados)
    assert not ad.fechado and not sessao._encerrada
    assert ad.motivos_recusas == [(URL, "METADADOS_SEGURANCA_ASSISTIDOS_AUSENTES")]
    if metodo == "requestWillBeSent":
        assert not ad.pedidos and not ad.canal.comandos
    else:
        curso = ad.pedidos["cdp", "ruim"]
        assert curso.recusada and curso.admitida is None
        entregar(ad, rid="ruim")
        assert curso.admitida is None
    request(ad, rid="boa")
    entregar(ad, rid="boa")
    assert ad.pedidos["cdp", "boa"].admitida.resposta.body == BODY
    ad.descartar()


@pytest.mark.parametrize(
    "metodo,caminho,valor",
    [(m, c, v) for m, defeitos in DEFEITOS.items() for c, v in defeitos],
)
def test_malformacao_pura_encerra(sessao, metodo, caminho, valor):
    ad = preparar(sessao, metodo)
    dados = deepcopy(PROJECOES[metodo])
    alterar(dados, caminho, valor)
    with pytest.raises(RecusaSessao, match="EVENTO_CDP_INVALIDO"):
        enviar(ad, metodo, dados)
    conferir_encerramento(ad, sessao)


@pytest.mark.parametrize(
    "metodo,ausente,malformado,valor",
    [
        (m, a, c, v)
        for m in PROJECOES
        for a, (c, v) in product(AUSENCIAS[m], DEFEITOS[m])
        if a[: len(c)] != c and c[: len(a)] != a
    ],
)
def test_ausencia_nao_mascara_malformacao(sessao, metodo, ausente, malformado, valor):
    ad = preparar(sessao, metodo)
    dados = deepcopy(PROJECOES[metodo])
    alterar(dados, ausente, remover=True)
    alterar(dados, malformado, valor)
    with pytest.raises(RecusaSessao, match="EVENTO_CDP_INVALIDO"):
        enviar(ad, metodo, dados)
    conferir_encerramento(ad, sessao)


@pytest.mark.parametrize("tipo", ["worker", "service_worker", "iframe"])
@pytest.mark.parametrize(
    "metodo,caminho,valor",
    [(m, c, v) for m, defeitos in DEFEITOS.items() for c, v in defeitos],
)
def test_alvo_nao_candidato_nao_invalida(sessao, tipo, metodo, caminho, valor):
    ad = adapter(sessao)
    ad.alvos["outro"] = Alvo("nao-candidato", tipo, "")
    dados = deepcopy(PROJECOES[metodo])
    alterar(dados, caminho, valor)
    # Combina também com ausência, sem destruir o caminho malformado.
    ausente = next(
        (
            a
            for a in AUSENCIAS[metodo]
            if a[: len(caminho)] != caminho and caminho[: len(a)] != a
        ),
        None,
    )
    if ausente is not None:
        alterar(dados, ausente, remover=True)
    enviar(ad, metodo, dados, sid="outro")
    assert not ad.fechado and not sessao._encerrada and not ad.pedidos
    request(ad, rid="boa")
    entregar(ad, rid="boa")
    assert ad.pedidos["cdp", "boa"].admitida is not None
    ad.descartar()


@pytest.mark.parametrize(
    "flag", ["fromDiskCache", "fromServiceWorker", "fromPrefetchCache"]
)
@pytest.mark.parametrize(
    "campo", ["securityDetails", "securityState", "remotePort", "status"]
)
def test_origem_derivada_nao_mascara_malformacao(sessao, flag, campo):
    ad = preparar(sessao, "responseReceived")
    dados = deepcopy(PROJECOES["responseReceived"])
    dados["response"][flag] = True
    dados["response"][campo] = None
    with pytest.raises(RecusaSessao, match="EVENTO_CDP_INVALIDO"):
        enviar(ad, "responseReceived", dados)
    conferir_encerramento(ad, sessao)


@pytest.mark.parametrize(
    "ausente,malformado",
    [
        ("id", "url"),
        ("url", "id"),
        ("id", "parentId"),
        ("url", "parentId"),
    ],
)
def test_quadro_de_controle_incompleto_e_malformado_encerra(
    sessao, ausente, malformado
):
    ad = adapter(sessao)
    frame = {"id": "raiz", "url": URL, "parentId": "pai"}
    del frame[ausente]
    frame[malformado] = None
    with pytest.raises(RecusaSessao, match="EVENTO_CDP_INVALIDO"):
        ad.processar(
            {
                "sessionId": "cdp",
                "method": "Page.frameNavigated",
                "params": {"frame": frame},
            }
        )
    conferir_encerramento(ad, sessao)
