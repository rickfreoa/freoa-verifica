"""0089 (b): cenarios sinteticos offline, sem navegador ou rede."""

from __future__ import annotations

import ast

import io

import time

from pathlib import Path

import pytest

from freoa_verifica import transport as t

from freoa_verifica.assistida import ambiente as a

from freoa_verifica.assistida.cdp import AdaptadorCDP, Alvo, CanalPipe, METODOS

from freoa_verifica.assistida.perfis import PERFIS

from tests.test_transport_assistida_0089 import eventos, pedido

from tests.assistida_0089_util import (
    sessao as sessao,
    VigiaSintetico,
    CanalSintetico,
    adapter,
    request,
    entregar,
    URL,
    BODY,
)


def test_adaptador_real_conectado_porta_unica(sessao, monkeypatch):
    ad = adapter(sessao)
    real = t.capturar_assistida
    chamadas = []

    def porta(s, p):
        chamadas.append(p)
        return real(s, p)

    monkeypatch.setattr(t, "capturar_assistida", porta)
    request(ad)
    entregar(ad)
    c = ad.pedidos["cdp", "pedido"].admitida
    assert c.resposta.body == BODY and chamadas[0].pronto
    assert c.procedencia == c.modalidade_acesso == "sessao_assistida"
    assert "verified" not in repr(c)
    ad.descartar()


def test_inventario_tardio_nao_promove_pedidos_anteriores(tmp_path, sessao):
    relogio = [0.0]
    inicio = time.monotonic() - 31

    def agora():
        return inicio + relogio[0]

    default = tmp_path / "Default"
    (default / "Extensions").mkdir(parents=True)
    vigia = a.Vigilancia(tmp_path, tmp_path / "brave.exe", relogio=agora)
    ad = AdaptadorCDP(
        PERFIS["planalto"], sessao, CanalSintetico(), vigia, relogio=agora
    )
    ad.fase = 3
    ad.alvos["cdp"] = Alvo(
        "aba", "page", "", raiz="raiz", documento=URL, sequencia_concluida=True
    )
    for instante in (1, 10, 29):
        relogio[0] = instante
        request(ad, rid=f"antes-{instante}")
        assert not ad.alvos["cdp"].pronto
        assert not ad.pedidos and not ad.canal.comandos
    for nome in ("Secure Preferences", "Preferences"):
        (default / nome).write_text("{}", encoding="utf-8")
    relogio[0] = 30
    assert ad.atualizar_prontidao() == inicio + 30
    assert ad.alvos["cdp"].pronto
    request(ad, rid="na-linha-base")
    assert not ad.pedidos
    relogio[0] = 31
    ad.processar(
        {
            "method": "Network.responseReceived",
            "sessionId": "cdp",
            "params": {"requestId": "antes-29", "response": {}},
        }
    )
    assert not ad.pedidos and not ad.canal.comandos
    request(ad, rid="posterior")
    entregar(ad, rid="posterior")
    assert set(ad.pedidos) == {("cdp", "posterior")}
    assert ad.pedidos["cdp", "posterior"].admitida.resposta.body == BODY
    ad.descartar()


def test_pedido_que_estabelece_base_nao_e_candidato_com_relogio_avancando(
    tmp_path, sessao
):
    instante = [time.monotonic() - 31]

    def relogio():
        instante[0] += 0.001
        return instante[0]

    (tmp_path / "Default" / "Extensions").mkdir(parents=True)
    vigia = a.Vigilancia(
        tmp_path, tmp_path / "brave.exe", relogio=relogio, inventario=lambda *_: None
    )
    ad = AdaptadorCDP(
        PERFIS["planalto"], sessao, CanalSintetico(), vigia, relogio=relogio
    )
    ad.fase = 3
    ad.alvos["cdp"] = Alvo(
        "aba", "page", "", raiz="raiz", documento=URL, sequencia_concluida=True
    )
    instante[0] += 30
    request(ad, rid="estabelece-base")
    assert vigia.linha_base is not None and ad.alvos["cdp"].pronto
    assert not ad.pedidos and not ad.canal.comandos
    request(ad, rid="posterior")
    assert set(ad.pedidos) == {("cdp", "posterior")}
    ad.descartar()


@pytest.mark.parametrize(
    "tipo,url",
    [
        ("Document", URL + "?token=SEGREDO"),
        ("XHR", URL),
        ("Fetch", URL),
        ("WebSocket", URL),
        ("Document", "https://login.microsoftonline.com/SEGREDO"),
        ("Document", "blob:" + URL),
        ("Document", "data:text/html,SEGREDO"),
        ("Document", URL.replace("l6404", "../l6404")),
    ],
)
def test_filtro_sem_retencao(sessao, tipo, url):
    ad = adapter(sessao)
    request(ad, tipo=tipo, url=url)
    ad.processar(
        {
            "sessionId": "cdp",
            "method": "Network.responseReceivedExtraInfo",
            "params": {"requestId": "pedido", "headers": {"secret": "SEGREDO"}},
        }
    )
    assert not ad.pedidos and not ad.canal.comandos and not ad.recusas


@pytest.mark.parametrize(
    "alteracao",
    [
        "sem_raiz",
        "iframe",
        "sem_prontidao",
        "assentamento",
        "prerender",
        "sem_historico",
    ],
)
def test_prontidao_quadros_e_ambiente(sessao, alteracao):
    ad = adapter(sessao)
    extra = {}
    if alteracao == "sem_raiz":
        ad.alvos["cdp"].raiz = ""
    elif alteracao == "iframe":
        extra["frameId"] = "filho"
    elif alteracao == "sem_prontidao":
        ad.alvos["cdp"].pronto = False
    elif alteracao == "assentamento":
        ad.vigia.linha_base = None
    elif alteracao == "prerender":
        ad.alvos["cdp"].subtipo = "prerender"
    else:
        ad.alvos["cdp"].subtipo = None
    request(ad, **extra)
    assert not ad.pedidos


@pytest.mark.parametrize(
    "mudanca", ["cache", "304", "stream_falha", "dados_antes_stream", "sem_extra"]
)
def test_recusas_na_integracao(sessao, mudanca):
    ad = adapter(sessao)
    request(ad)
    if mudanca == "cache":
        entregar(ad, response={"fromDiskCache": True})
    elif mudanca == "304":
        entregar(ad, status_cru=304)
    elif mudanca == "stream_falha":
        ad.processar(
            {
                "id": ad.numero,
                "error": {"message": "Request with the provided ID does not exist"},
            }
        )
    elif mudanca == "dados_antes_stream":
        ad.processar(
            {
                "method": "Network.dataReceived",
                "sessionId": "cdp",
                "params": {
                    "requestId": "pedido",
                    "dataLength": 1,
                    "encodedDataLength": 1,
                    "data": "YQ==",
                },
            }
        )
    else:
        # A rajada do laboratório sem ExtraInfo nunca é promovida.
        for e in eventos(pedido(), body=BODY):
            if e.metodo == "streamResourceContent":
                ad.processar({"id": ad.numero, "result": e.dados})
            elif e.metodo != "responseReceivedExtraInfo":
                dados = (
                    {"headers": {}, "associatedCookies": []}
                    if e.metodo == "requestWillBeSentExtraInfo"
                    else e.dados
                )
                ad.processar(
                    {
                        "method": "Network." + e.metodo,
                        "sessionId": "cdp",
                        "params": {"requestId": "pedido", **dados},
                    }
                )
    assert ad.pedidos["cdp", "pedido"].admitida is None


def test_ids_iguais_em_alvos_distintos(sessao):
    ad = adapter(sessao)
    ad.alvos["cdp2"] = Alvo("aba2", "page", "", True, "raiz", URL)
    request(ad)
    request(ad, sid="cdp2")
    entregar(ad)
    entregar(ad, sid="cdp2")
    assert len({c.admitida.obtencao_id for c in ad.pedidos.values()}) == 2


@pytest.mark.parametrize(
    "historia,aceita", [("observada", True), ("ausente", False), ("rede_previa", False)]
)
def test_hsts_exige_historia_completa(sessao, historia, aceita):
    ad = adapter(sessao)
    http = URL.replace("https:", "http:")
    salto = {
        "url": http,
        "status": 307,
        "headers": {"Non-Authoritative-Reason": "HSTS"},
    }
    if historia == "observada":
        request(ad, url=http)
    if historia == "rede_previa":
        request(ad, url="https://terceiro.invalid/segredo")
        request(
            ad,
            url=http,
            redirectResponse={"url": "https://terceiro.invalid/segredo", "status": 302},
        )
    request(ad, redirectResponse=salto)
    if aceita:
        entregar(ad)
        assert ad.pedidos["cdp", "pedido"].admitida is not None
    else:
        assert not ad.pedidos


@pytest.mark.parametrize(
    "respondeu,esperado", [(False, "Timeout"), (True, "RespostaInvalida")]
)
def test_prazo_adaptador_sem_novo_evento(sessao, respondeu, esperado):
    ad = adapter(sessao)
    request(ad)
    curso = ad.pedidos["cdp", "pedido"]
    if respondeu:
        curso.vistos.add("responseReceived")
    ad.relogio = lambda: curso.inicio + 31
    ad.fiscalizar_capturas()
    assert curso.recusada and curso.admitida is None
    assert ad.recusas == [(URL, esperado)]


@pytest.mark.parametrize("ambiente_assentado", [True, False])
def test_metodos_parametros_e_sequencia(sessao, ambiente_assentado):
    vigia = VigiaSintetico()
    if not ambiente_assentado:
        vigia.linha_base = None
    ad = AdaptadorCDP(PERFIS["planalto"], sessao, CanalSintetico(), vigia)
    ad.iniciar()

    def responder(result=None):
        ad.processar({"id": ad.numero, "result": result or {}})

    responder()
    responder()
    responder({"product": "Chrome/158.0"})
    responder()
    ad.processar(
        {
            "method": "Target.targetCreated",
            "params": {"targetInfo": {"targetId": "aba", "type": "page"}},
        }
    )
    ad.processar(
        {
            "method": "Target.attachedToTarget",
            "params": {
                "sessionId": "cdp",
                "targetInfo": {"targetId": "aba", "type": "page", "url": "about:blank"},
            },
        }
    )
    responder()
    responder()
    responder({"frameTree": {"frame": {"id": "raiz", "url": "about:blank"}}})
    responder()
    assert ad.alvos["cdp"].sequencia_concluida
    assert ad.alvos["cdp"].pronto is ambiente_assentado
    vigia.linha_base = 1
    ad.atualizar_prontidao()
    assert ad.alvos["cdp"].pronto
    assert [c["method"] for c in ad.canal.comandos] == [
        "Target.setDiscoverTargets",
        "Target.setAutoAttach",
        "Browser.getVersion",
        "Browser.setDownloadBehavior",
        "Network.enable",
        "Page.enable",
        "Page.getFrameTree",
        "Runtime.runIfWaitingForDebugger",
    ]
    assert len(METODOS) == 10
    for metodo in (
        "Network.getResponseBody",
        "Page.navigate",
        "Extensions.loadUnpacked",
        "Network.setCacheDisabled",
    ):
        with pytest.raises(a.RecusaSessao):
            ad.comando(metodo)
    with pytest.raises(a.RecusaSessao):
        ad.comando("Browser.setDownloadBehavior", {"behavior": "allow"})


def test_pipe_fila_reserva_antes_da_leitura(sessao):
    class Leitura(io.BytesIO):
        def read(self, n):
            assert sessao._memoria >= n
            return super().read(n)

    canal = CanalPipe(Leitura(b'{"method":"teste"}\0'), io.BytesIO(), sessao)
    canal.iniciar()
    canal.thread.join(1)
    with canal.receber() as obj:
        assert obj == {"method": "teste"}
    with pytest.raises(a.RecusaSessao, match="CANAL"):
        canal.receber()
    canal.fechar()
    assert sessao._memoria == 0


@pytest.mark.parametrize("tipo", ["fila", "memoria", "truncada"])
def test_pipe_excesso_e_perda_invalidam(sessao, tipo):
    canal = CanalPipe(io.BytesIO(b"{"), io.BytesIO(), sessao)
    if tipo == "fila":
        canal.bytes_fila = 32 * 1024**2
        with pytest.raises(a.RecusaSessao):
            canal._enfileirar(b"a")
    elif tipo == "memoria":
        sessao.reservar(64 * 1024**2)
    canal.iniciar()
    canal.thread.join(1)
    with pytest.raises(a.RecusaSessao):
        canal.receber()
    assert sessao._encerrada


@pytest.mark.parametrize(
    "extra",
    [
        "--load-extension=x",
        "--enable-unsafe-extension-debugging",
        "--ignore-certificate-errors",
        "--ignore-certificate-errors-spki-list=x",
        "--remote-debugging-port=9333",
        "--headless",
        "--proxy-server=x",
    ],
)
def test_produto_recusa_parametros_harness(tmp_path, extra):
    with pytest.raises(a.RecusaSessao):
        a.argumentos(
            tmp_path / "brave.exe", tmp_path, "file:///inicio.html", extras=[extra]
        )
    with pytest.raises(a.RecusaSessao, match="ARGUMENTOS"):
        a.lancar_pipe(
            tmp_path / "brave.exe", tmp_path, "file:///inicio.html", extras=[extra]
        )


@pytest.mark.repositorio
def test_ast_fronteiras():
    raiz = Path(__file__).resolve().parents[1] / "freoa_verifica"
    chamadas = []
    for path in raiz.rglob("*.py"):
        if path.name == "transport.py":
            continue
        arvore = ast.parse(path.read_text(encoding="utf-8-sig"))
        for no in ast.walk(arvore):
            if (
                isinstance(no, ast.Call)
                and isinstance(no.func, ast.Attribute)
                and no.func.attr == "capturar_assistida"
            ):
                chamadas.append(path.relative_to(raiz).as_posix())
    assert chamadas == ["assistida/cdp.py"]
    for arquivo in ("mcp_server.py", "rest.py", "bateria.py", "service.py"):
        texto = (raiz / arquivo).read_text(encoding="utf-8")
        assert (
            "assistida.sessao" not in texto
            and "assistida.cdp" not in texto
            and "capturar_assistida(" not in texto
        )
    arvore = ast.parse((raiz / "assistida" / "cdp.py").read_text(encoding="utf-8"))
    literais = {
        no.args[0].value
        for no in ast.walk(arvore)
        if isinstance(no, ast.Call)
        and isinstance(no.func, ast.Attribute)
        and no.func.attr == "comando"
        and no.args
        and isinstance(no.args[0], ast.Constant)
    }
    assert literais <= set(METODOS)


def test_fechamento_e_queda_sem_reabertura(sessao):
    ad = adapter(sessao)
    ad.aceitou_page = True
    ad.processar(
        {"method": "Target.detachedFromTarget", "params": {"sessionId": "cdp"}}
    )
    assert not ad.normal and not ad.alvos["cdp"].pronto
    ad.processar({"method": "Target.targetDestroyed", "params": {"targetId": "aba"}})
    assert ad.normal
    ad = adapter(sessao)
    ad.processar(
        {"method": "Target.detachedFromTarget", "params": {"sessionId": "cdp"}}
    )
    ad.desanexados["cdp"] = 0
    with pytest.raises(a.RecusaSessao, match="CANAL_ALVO"):
        ad.conferir_canal()
    assert sessao._encerrada
    assert not ad.canal.comandos
