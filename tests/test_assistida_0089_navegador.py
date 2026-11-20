"""0089: integração real restrita ao servidor HTTPS local; nenhuma fonte real."""

import time

import pytest
from freoa_verifica.assistida import ambiente as a

from tests.harness_assistida_0089 import CORPOS, navegador_pipe, origem_https
from tests.harness_assistida_0089_cenarios import (
    SondaEventos,
    bombear,
    capturas,
    conferir_condicao_item1,
)

pytestmark = pytest.mark.navegador_assistido


def test_item8_brave_pipe_e_acl_reais(tmp_path, monkeypatch):
    with navegador_pipe(tmp_path, monkeypatch) as (ad, proc, vigia):
        assert proc.poll() is None
        assert ad.fase == 3
        assert vigia.inventario_lido and vigia.linha_base is not None
        assert any(x.pronto for x in ad.alvos.values())
        assert vigia.erro is None


@pytest.mark.parametrize(
    "caso",
    [
        *CORPOS,
        "gzip",
        "deflate",
        "encoding",
        "bomba",
        "304",
        "cl21",
        "sem_cabecalhos",
        "sem_termino",
        "parcial",
    ],
)
def test_item1_https_adaptador_real(tmp_path, monkeypatch, caso):
    try:
        a.proteger_diretorio(tmp_path)
    except a.RecusaSessao as exc:
        pytest.skip("pré-requisito de navegador/pipe: " + str(exc))
    estado = {}
    with origem_https(tmp_path, caso, estado=estado) as (spki, vistos):
        with navegador_pipe(
            tmp_path,
            monkeypatch,
            spki=spki,
            caso=caso,
            script="location.href='https://127.0.0.1/driver';"
            if caso == "304"
            else None,
        ) as (
            ad,
            _,
            vigia,
        ):
            sonda = SondaEventos(ad)
            limite = time.monotonic() + 48
            while time.monotonic() < limite:
                ad.passo()
                if caso == "304":
                    chaves = [
                        k
                        for k, u in sonda.pedidos.items()
                        if u == "https://127.0.0.1/case/304"
                    ]
                    if len(chaves) == 2 and ad.pedidos[chaves[-1]].recusada:
                        # Drena os eventos da segunda troca, inclusive 200 aparente.
                        bombear(
                            ad,
                            vigia,
                            ate=lambda: any(p == "/done" for p, _ in vistos),
                            prazo=10,
                        )
                        break
                elif any(c.admitida for c in ad.pedidos.values()) or ad.recusas:
                    break
            if caso in {"304", "sem_cabecalhos", "parcial", "sem_termino"}:
                assert vistos
                conferir_condicao_item1(ad, sonda, caso, estado)
                return
            capturas = [c.admitida for c in ad.pedidos.values() if c.admitida]
            if caso in {
                "utf8",
                "meta",
                "latin1",
                "cp1252",
                "ufffd",
                "bom16",
                "gzip",
                "deflate",
            }:
                assert len(capturas) == 1
                assert capturas[0].resposta.body == CORPOS.get(caso, CORPOS["utf8"])[1]
            else:
                assert not capturas
                esperado = {
                    "utf8_invalido": "INTERPRETACAO_ASSISTIDA_INVALIDA",
                    "encoding": "CONTENT_ENCODING_ASSISTIDO_INVALIDO",
                    "bomba": "TAMANHO_ASSISTIDO_EXCEDIDO",
                    "cl21": "CABECALHOS_ASSISTIDOS_INVALIDOS",
                }.get(caso)
                if caso == "cl21":
                    assert any(
                        m in {esperado, "EVENTO_ASSISTIDO_RECUSADO"}
                        for _, m in ad.motivos_recusas
                    )
                    if any(
                        m == "EVENTO_ASSISTIDO_RECUSADO" for _, m in ad.motivos_recusas
                    ):
                        assert any(
                            e["erro_rede"] == "net::ERR_INVALID_RESPONSE"
                            for e in sonda.eventos
                        )
                else:
                    assert any(m == esperado for _, m in ad.motivos_recusas)
                assert all(url for url, _ in ad.recusas)
            assert vistos


def test_redirect_de_rede_recusa_cadeia_cdp_ambigua(tmp_path, monkeypatch):
    # §2.3(2): redirecionamento de rede não é positivo; só HSTS interno provado.
    with origem_https(tmp_path, "redirect") as (spki, vistos):
        with navegador_pipe(tmp_path, monkeypatch, spki=spki, caso="redirect") as (
            ad,
            _,
            vigia,
        ):
            with pytest.raises(a.RecusaSessao, match="^CADEIA_CDP_AMBIGUA$"):
                bombear(ad, vigia, ate=lambda: False, prazo=10)
            assert not capturas(ad)
            assert any(p == "/case/redirect" for p, _ in vistos)


def test_consumidor_tardio_fim_antes_da_resposta_streaming(tmp_path, monkeypatch):
    # Defeito 49: só fim anterior à resposta (ou erro do comando) prova atraso.
    # Mantém os 150 ms da origem e atrasa exclusivamente o consumidor do teste.
    with origem_https(tmp_path, "utf8") as (spki, vistos):
        with navegador_pipe(tmp_path, monkeypatch, spki=spki) as (ad, _, vigia):
            ordem = []
            comandos = {}
            processar = ad.processar
            enviar = ad.canal.enviar

            def observar_comando(obj):
                if obj["method"] == "Network.streamResourceContent":
                    comandos[obj["id"]] = (
                        obj.get("sessionId"),
                        obj["params"]["requestId"],
                    )
                return enviar(obj)

            def observar(obj):
                if obj.get("method") == "Network.loadingFinished":
                    chave = (obj.get("sessionId"), obj["params"]["requestId"])
                    ordem.append((chave, "fim"))
                chave = comandos.get(obj.get("id"))
                if chave:
                    ordem.append((chave, "erro" if "error" in obj else "resposta"))
                return processar(obj)

            monkeypatch.setattr(ad, "processar", observar)
            monkeypatch.setattr(ad.canal, "enviar", observar_comando)
            limite = time.monotonic() + 5
            while not vistos and time.monotonic() < limite:
                time.sleep(0.01)
            assert vistos
            time.sleep(0.5)  # inclui os 150 ms da origem e 300 ms entre partes
            bombear(ad, vigia, ate=lambda: bool(ad.recusas), prazo=10)
            assert not capturas(ad)
            assert len(ad.motivos_recusas) == 1
            url, motivo = ad.motivos_recusas[0]
            assert url == "https://127.0.0.1/case/utf8"
            chaves = [chave for chave, curso in ad.pedidos.items() if curso.url == url]
            assert len(chaves) == 1
            eventos = [evento for chave, evento in ordem if chave == chaves[0]]
            if motivo == "STREAMING_ASSISTIDO_TARDIO":
                assert eventos[0] == "fim"
                assert any(evento in {"resposta", "erro"} for evento in eventos)
            else:
                assert motivo == "COMANDO_STREAMING_RECUSADO"
                assert "erro" in eventos
