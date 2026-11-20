"""Provas offline dos guardiões do harness; não abrem navegador nem sockets."""

from pathlib import Path
import io
import os
import runpy
from types import SimpleNamespace

import pytest

from tests.gerar_0089_wire import BODY, gerar
from tests.harness_assistida_0089_cenarios import (
    SondaEventos,
    comparar_passividade,
    conferir_recusa_evento,
    conferir_recusa_streaming,
    diferenca_pedidos,
    exigir_recusa,
    varrer_artefatos,
)
from tests.assistida_0089_util import adapter, entregar, request, sessao as sessao, URL


def _pedido_origem(*headers, caminho="/case/passividade", metodo="GET"):
    return metodo, caminho, tuple(headers)


@pytest.mark.parametrize("campo", ["Priority", "sec-ch-ua", "Accept-Language"])
def test_passividade_exige_controle_do_mesmo_campo_e_valores(campo):
    um = [_pedido_origem(("Host", "127.0.0.1"), (campo, "variante-1"))]
    dois = [_pedido_origem(("Host", "127.0.0.1"), (campo, "variante-2"))]
    assert comparar_passividade(um, dois, dois)["passou"]
    assert comparar_passividade(um, dois, dois)["ruido_declarado"]
    assert not comparar_passividade(um, um, dois)["passou"]
    terceiro = [_pedido_origem(("Host", "127.0.0.1"), (campo, "exclusivo-adaptador"))]
    assert not comparar_passividade(um, dois, terceiro)["passou"]


@pytest.mark.parametrize(
    "mudanca",
    [
        "metodo",
        "caminho",
        "quantidade",
        "favicon",
        "campo_novo",
        "campo_removido",
        "ordem_campos",
    ],
)
def test_passividade_nao_esconde_diferenca_exclusiva_do_adaptador(mudanca):
    controle = [_pedido_origem(("Host", "127.0.0.1"), ("Accept", "*/*"))]
    com = list(controle)
    if mudanca == "metodo":
        com[0] = _pedido_origem(*controle[0][2], metodo="POST")
    elif mudanca == "caminho":
        com[0] = _pedido_origem(*controle[0][2], caminho="/outro")
    elif mudanca in {"quantidade", "favicon"}:
        com.append(
            _pedido_origem(caminho="/favicon.ico")
            if mudanca == "favicon"
            else controle[0]
        )
    elif mudanca == "campo_novo":
        com[0] = _pedido_origem(*controle[0][2], ("Priority", "u=1"))
    elif mudanca == "campo_removido":
        com[0] = _pedido_origem(controle[0][2][0])
    else:
        com[0] = _pedido_origem(*reversed(controle[0][2]))
    assert not comparar_passividade(controle, controle, com)["passou"]


def test_passividade_ordem_so_e_descontada_com_prova_no_controle():
    um = [_pedido_origem(("Host", "127.0.0.1")), _pedido_origem(caminho="/favicon.ico")]
    dois = list(reversed(um))
    assert comparar_passividade(um, dois, dois)["passou"]
    assert not comparar_passividade(um, um, dois)["passou"]
    h1 = [_pedido_origem(("Host", "127.0.0.1"), ("Accept", "*/*"))]
    h2 = [_pedido_origem(*reversed(h1[0][2]))]
    assert comparar_passividade(h1, h2, h2)["passou"]
    assert not comparar_passividade(um, dois[:-1], um)["passou"]


def test_passividade_preserva_multiplicidade_de_campo_variavel():
    um = [_pedido_origem(("Priority", v)) for v in ("a", "b")]
    dois = [_pedido_origem(("Priority", v)) for v in ("b", "c")]
    com = [_pedido_origem(("Priority", "b"))] * 2
    # "b" existia nos controles, mas nunca duas vezes no mesmo conjunto.
    assert not comparar_passividade(um, dois, com)["passou"]


def test_diagnostico_passividade_detalha_campos_contagens_e_ordem():
    um = [_pedido_origem(("Host", "127.0.0.1"), ("Accept", "um"), ("So-A", "a"))]
    dois = [
        _pedido_origem(("Host", "127.0.0.1"), ("Accept", "dois"), ("So-B", "b")),
        _pedido_origem(caminho="/favicon.ico"),
    ]
    delta = diferenca_pedidos(um, dois)
    assert delta["numero_pedidos"] == [1, 2]
    assert delta["pedidos_so_direita"] == [["GET", "/favicon.ico", 1]]
    d = delta["diferencas"][0]
    assert (d["metodo"], d["caminho"]) == ("GET", "/case/passividade")
    assert d["cabecalhos_so_esquerda"] == {"So-A": ("a",)}
    assert d["cabecalhos_so_direita"] == {"So-B": ("b",)}
    assert d["valores_diferentes"] == {"Accept": [("um",), ("dois",)]}
    invertido = [_pedido_origem(*reversed(um[0][2]))]
    assert diferenca_pedidos(um, invertido)["diferencas"][0][
        "mesma_colecao_cabecalhos_ordem_diferente"
    ]


@pytest.mark.parametrize("mecanismo", ["disco", "memoria", "prefetch", "304"])
def test_recusa_derivada_por_requestid_preserva_primeira_captura(sessao, mecanismo):
    ad = adapter(sessao)
    sonda = SondaEventos(ad)
    request(ad, rid="rede")
    entregar(ad, rid="rede")
    assert ad.pedidos["cdp", "rede"].admitida is not None
    request(ad, rid="derivada")
    if mecanismo == "memoria":
        ad.processar(
            {
                "method": "Network.requestServedFromCache",
                "sessionId": "cdp",
                "params": {"requestId": "derivada"},
            }
        )
    else:
        entregar(
            ad,
            rid="derivada",
            **(
                {"status_cru": 304}
                if mecanismo == "304"
                else {
                    "response": {
                        "fromDiskCache"
                        if mecanismo == "disco"
                        else "fromPrefetchCache": True
                    }
                }
            ),
        )
    motivos = {
        "ORIGEM_ASSISTIDA_SEM_PROVA",
        "EVENTO_ASSISTIDO_RECUSADO",
        "STATUS_ASSISTIDO_DIVERGENTE",
    }
    exigir_recusa(ad, URL, motivos, sonda=sonda, chave=("cdp", "derivada"))
    with pytest.raises(AssertionError):
        exigir_recusa(ad, URL, motivos, sonda=sonda, chave=("cdp", "rede"))
    # Mesmo com recusa do pedido correto, admissão indevida jamais pode passar.
    ad.pedidos["cdp", "derivada"].admitida = ad.pedidos["cdp", "rede"].admitida
    with pytest.raises(AssertionError):
        exigir_recusa(ad, URL, motivos, sonda=sonda, chave=("cdp", "derivada"))
    ad.descartar()


@pytest.mark.parametrize("causa", ["cache", "rede", "outro_pedido", "evento_inocuo"])
def test_recusa_evento_exige_causa_do_mesmo_requestid(sessao, causa):
    ad = adapter(sessao)
    sonda = SondaEventos(ad)
    request(ad)
    metodo = (
        "Network.requestServedFromCache"
        if causa == "cache"
        else "Network.loadingFailed"
    )
    ad.processar(
        {
            "method": metodo,
            "sessionId": "cdp",
            "params": {"requestId": "pedido", "errorText": "net::ERR_EMPTY_RESPONSE"},
        }
    )
    assert sonda.recusas[0]["chave"] == ("cdp", "pedido")
    if causa == "outro_pedido":
        sonda.eventos[-1]["chave"] = ("cdp", "outro")
    elif causa == "evento_inocuo":
        sonda.recusas[0]["causa"] = "Network.dataReceived"
    if causa in {"cache", "rede"}:
        conferir_recusa_evento(sonda, URL, {"net::ERR_EMPTY_RESPONSE"})
    else:
        with pytest.raises(pytest.fail.Exception):
            conferir_recusa_evento(sonda, URL, {"net::ERR_EMPTY_RESPONSE"})
    ad.descartar()


def test_sonda_correlaciona_erro_streaming_sem_sessionid(sessao):
    ad = adapter(sessao)
    sonda = SondaEventos(ad)
    request(ad)
    ad.processar(
        {"id": ad.numero, "error": {"code": -32000, "message": "erro sintético"}}
    )
    conferir_recusa_streaming(sonda, URL, "COMANDO_STREAMING_RECUSADO")
    assert sonda.recusas == [
        {
            "chave": ("cdp", "pedido"),
            "url": URL,
            "motivo": "COMANDO_STREAMING_RECUSADO",
            "causa": "resposta_streaming",
        }
    ]
    assert ad.recusas == [(URL, "RespostaInvalida")]
    ad.descartar()


@pytest.mark.skipif(
    os.name != "nt", reason="harness de pipe Windows; sem navegador real"
)
@pytest.mark.parametrize("observar", [False, True])
@pytest.mark.parametrize(
    "fim", ["normal", "erro", "skip", "interrupcao", "falha_fechamento"]
)
def test_harness_limpa_perfil_em_toda_saida(tmp_path, monkeypatch, observar, fim):
    from freoa_verifica.assistida import ambiente as a
    from tests import harness_assistida_0089 as h

    ordem = []
    vigia = SimpleNamespace(linha_base=1, limite_inventario=100, assentar=lambda: 1)
    monkeypatch.setattr(
        a, "navegador_instalado", lambda _: ("brave", tmp_path / "brave.exe")
    )
    monkeypatch.setattr(a, "conferir_politicas", lambda _: None)
    monkeypatch.setattr(a, "proteger_diretorio", lambda _: None)
    monkeypatch.setattr(a, "Vigilancia", lambda *_: vigia)
    monkeypatch.setattr(
        a,
        "ObservadorWindows",
        lambda _: SimpleNamespace(fechar=lambda: ordem.append("observador")),
    )
    monkeypatch.setattr(
        a,
        "lancar_pipe",
        lambda *_: (SimpleNamespace(poll=lambda: None), io.BytesIO(), io.BytesIO()),
    )
    monkeypatch.setattr(
        h,
        "CanalPipe",
        lambda *_: SimpleNamespace(
            iniciar=lambda: None, fechar=lambda: ordem.append("canal")
        ),
    )
    monkeypatch.setattr(
        h,
        "AdaptadorCDP",
        lambda *_: SimpleNamespace(
            fase=3, iniciar=lambda: None, alvos={"sid": SimpleNamespace(pronto=True)}
        ),
    )

    def fechar(_):
        ordem.append("navegador")
        if fim == "falha_fechamento":
            raise OSError("falha sintética de fechamento")

    monkeypatch.setattr(a, "fechar_navegador", fechar)
    limpar = a.limpar_diretorio

    def registrar_limpeza(perfil, raiz):
        ordem.append("limpeza")
        limpar(perfil, raiz)

    monkeypatch.setattr(a, "limpar_diretorio", registrar_limpeza)
    erros = {
        "erro": ValueError,
        "skip": pytest.skip.Exception,
        "interrupcao": KeyboardInterrupt,
        "falha_fechamento": OSError,
    }

    def executar():
        with h.navegador_pipe(tmp_path, monkeypatch, observar=observar):
            perfil = tmp_path / "sessao-0089-harness"
            (perfil / "cache-sintetico").write_bytes(b"cache")
            if fim in {"erro", "skip", "interrupcao"}:
                raise erros[fim]("saída sintética")

    if fim == "normal":
        executar()
    else:
        with pytest.raises(erros[fim]):
            executar()
    assert not (tmp_path / "sessao-0089-harness").exists()
    assert ordem == [
        "navegador",
        *(["canal"] if observar else []),
        "observador",
        "limpeza",
    ]


def test_limpeza_perfil_registra_motivo_da_sobra(tmp_path, monkeypatch, capsys):
    from freoa_verifica.assistida import ambiente as a
    from tests.harness_assistida_0089 import limpar_perfil_harness

    perfil = tmp_path / "sessao-0089-harness"
    perfil.mkdir()

    def falhar(*_):
        raise PermissionError("arquivo sintético em uso")

    with monkeypatch.context() as patch:
        patch.setattr(a, "limpar_diretorio", falhar)
        with pytest.raises(PermissionError):
            limpar_perfil_harness(perfil, tmp_path)
    assert "LIMPEZA_PERFIL_HARNESS_FALHOU" in capsys.readouterr().out
    a.limpar_diretorio(perfil, tmp_path)


def test_fixtures_wire_reproduziveis():
    fixtures = Path(__file__).parent / "fixtures"
    for encoding, data in gerar().items():
        assert (fixtures / f"0089_wire_{encoding}.bin").read_bytes() == data


def test_zstd_decodificado_independentemente():
    zstd = pytest.importorskip(
        "compression.zstd",
        reason="decoder da biblioteca padrão só existe a partir do Python 3.14; nenhuma dependência opcional exigida",
    )
    assert zstd.decompress(gerar()["zstd"]) == BODY


@pytest.mark.parametrize("codec", ["utf-8", "utf-16-le", "utf-16-be"])
def test_varredura_detecta_segredo_inclusive_em_wal(tmp_path, codec):
    pasta = tmp_path / "subdiretorio"
    pasta.mkdir()
    (pasta / "verifica.sqlite3-wal").write_bytes(
        b"prefixo" + "SEGREDO_SINTETICO".encode(codec)
    )
    with pytest.raises(AssertionError):
        varrer_artefatos(tmp_path, ["SEGREDO_SINTETICO"])


def test_varredura_nao_aceita_diretorio_vazio(tmp_path):
    with pytest.raises(AssertionError, match="varredura vazia"):
        varrer_artefatos(tmp_path, ["SEGREDO_SINTETICO"])


@pytest.mark.parametrize("registros", [[], [("publico", "STREAMING_ASSISTIDO_TARDIO")]])
def test_negativo_nao_passa_no_vazio_ou_por_causa_alheia(registros):
    ad = SimpleNamespace(motivos_recusas=registros, pedidos={})
    with pytest.raises(AssertionError):
        exigir_recusa(ad, "publico", {"COOKIE_ASSISTIDO_RECUSADO"})


@pytest.mark.parametrize("valor", [None, "0", "true", "1"])
def test_gesto_humano_exige_opt_in_exato(monkeypatch, valor):
    if valor is None:
        monkeypatch.delenv("FV_0089_GESTO_HUMANO", raising=False)
    else:
        monkeypatch.setenv("FV_0089_GESTO_HUMANO", valor)
    modulo = runpy.run_path(
        str(Path(__file__).with_name("test_assistida_0089_navegador_cenarios.py"))
    )
    for nome in (
        "test_item2_recarga_forcada_humana_vem_da_rede",
        "test_item1_item8_instalacao_manual_desempacotada_recusa",
    ):
        marca = next(m for m in modulo[nome].pytestmark if m.name == "skipif")
        assert marca.args == (valor != "1",)
        assert "FV_0089_GESTO_HUMANO=1" in marca.kwargs["reason"]


@pytest.mark.parametrize(
    "ordem,aceita",
    [
        (["fim", "resposta"], True),
        (["fim"], True),
        (["resposta", "fim"], False),
        (["resposta"], False),
        ([], False),
    ],
)
def test_recusa_tardia_exige_fim_antes_da_resposta(ordem, aceita):
    ad = SimpleNamespace(
        alvos={}, processar=lambda _: None, canal=SimpleNamespace(enviar=lambda _: None)
    )
    sonda = SondaEventos(ad)
    sonda.processar(
        {
            "method": "Network.requestWillBeSent",
            "sessionId": "sid",
            "params": {
                "requestId": "rid",
                "request": {"url": "publico"},
            },
        }
    )
    sonda.enviar(
        {
            "id": 1,
            "method": "Network.streamResourceContent",
            "sessionId": "sid",
            "params": {"requestId": "rid"},
        }
    )
    for passo in ordem:
        sonda.processar(
            {"id": 1, "result": {"bufferedData": ""}}
            if passo == "resposta"
            else {
                "method": "Network.loadingFinished",
                "sessionId": "sid",
                "params": {"requestId": "rid"},
            }
        )
    if aceita:
        conferir_recusa_streaming(sonda, "publico", "STREAMING_ASSISTIDO_TARDIO")
    else:
        with pytest.raises(AssertionError):
            conferir_recusa_streaming(sonda, "publico", "STREAMING_ASSISTIDO_TARDIO")


def test_erro_streaming_exige_erro_do_proprio_comando():
    eventos = [{"url": "outro", "stream_resposta": True, "stream_erro": True}]
    sonda = SimpleNamespace(eventos=eventos)
    with pytest.raises(AssertionError):
        conferir_recusa_streaming(sonda, "publico", "COMANDO_STREAMING_RECUSADO")
    eventos[0]["url"] = "publico"
    conferir_recusa_streaming(sonda, "publico", "COMANDO_STREAMING_RECUSADO")


def test_early_hints_http2_em_memoria():
    pytest.importorskip(
        "h2",
        reason="requer o pacote h2 no ambiente do ensaio; não é dependência do projeto",
    )
    from h2.config import H2Configuration
    from h2.connection import H2Connection
    from h2.events import (
        InformationalResponseReceived,
        ResponseReceived,
        StreamEnded,
        DataReceived,
    )
    from tests.harness_assistida_0089_h2 import responder_h2

    servidor = H2Connection(config=H2Configuration(client_side=False))
    cliente = H2Connection(config=H2Configuration(header_encoding="utf-8"))
    cliente.initiate_connection()
    servidor.initiate_connection()
    servidor.receive_data(cliente.data_to_send())
    cliente.receive_data(servidor.data_to_send())
    cliente.send_headers(
        1,
        [
            (":method", "GET"),
            (":scheme", "https"),
            (":authority", "127.0.0.1"),
            (":path", "/case/early_hints"),
        ],
        end_stream=True,
    )
    servidor.receive_data(cliente.data_to_send())
    estado = {"marcas": [], "erros": []}
    assert responder_h2(servidor, "/case/early_hints", 1, estado, hints=True) is None
    eventos = cliente.receive_data(servidor.data_to_send())
    hints = next(e for e in eventos if isinstance(e, InformationalResponseReceived))
    assert dict(hints.headers) == {
        ":status": "103",
        "link": "</case/hinted>; rel=preload; as=script",
    }
    assert not any(isinstance(e, (ResponseReceived, StreamEnded)) for e in eventos)
    corpo = responder_h2(servidor, "/case/early_hints", 1, estado)
    servidor.send_data(1, corpo, end_stream=True)
    eventos = cliente.receive_data(servidor.data_to_send())
    final = next(e for e in eventos if isinstance(e, ResponseReceived))
    assert dict(final.headers)[":status"] == "200"
    assert b"".join(e.data for e in eventos if isinstance(e, DataReceived)) == corpo
    assert any(isinstance(e, StreamEnded) for e in eventos)
