"""0089: integração real restrita ao servidor HTTPS local; nenhuma fonte real."""

import time

import pytest
from freoa_verifica.assistida import ambiente as a

from tests.harness_assistida_0089 import CORPOS, navegador_pipe, origem_https
from tests.harness_assistida_0089_cenarios import SondaEventos, bombear, capturas

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
        "parcial",
    ],
)
def test_item1_https_adaptador_real(tmp_path, monkeypatch, caso):
    try:
        a.proteger_diretorio(tmp_path)
    except a.RecusaSessao as exc:
        pytest.skip("pré-requisito de navegador/pipe: " + str(exc))
    with origem_https(tmp_path, caso) as (spki, vistos):
        with navegador_pipe(tmp_path, monkeypatch, spki=spki, caso=caso) as (
            ad,
            _,
            vigia,
        ):
            sonda = SondaEventos(ad)
            limite = time.monotonic() + 48
            while time.monotonic() < limite:
                ad.passo()
                if any(c.admitida for c in ad.pedidos.values()) or ad.recusas:
                    break
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
                    "sem_cabecalhos": "PRAZO_ASSISTIDO_SEM_RESPOSTA",
                    "parcial": "PRAZO_ASSISTIDO_SEM_RESPOSTA",
                }.get(caso)
                if caso == "304":
                    assert any(e["status"] == 304 for e in sonda.eventos)
                    assert any(
                        m
                        in {
                            "STATUS_ASSISTIDO_DIVERGENTE",
                            "CONTENT_LENGTH_ASSISTIDO_DIVERGENTE",
                            "CORPO_ASSISTIDO_VAZIO",
                            "HTTPStatusError",
                        }
                        for _, m in ad.motivos_recusas
                    )
                elif caso == "cl21":
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


def test_atraso_zero_consumidor_tardio_recusa_streaming_tardio(tmp_path, monkeypatch):
    # LAB, nota final: uma origem rápida pode vencer o cliente. Faz a condição
    # reproduzível atrasando só o consumidor do teste, sem alterar eventos/CDP.
    with origem_https(tmp_path, "utf8", atraso_primeiro_byte=0) as (spki, vistos):
        with navegador_pipe(tmp_path, monkeypatch, spki=spki) as (ad, _, vigia):
            limite = time.monotonic() + 5
            while not vistos and time.monotonic() < limite:
                time.sleep(0.01)
            assert vistos
            time.sleep(0.5)  # primeiro dataReceived já deve estar na fila do pipe
            bombear(ad, vigia, ate=lambda: bool(ad.recusas), prazo=10)
            assert not capturas(ad)
            assert ad.motivos_recusas == [
                ("https://127.0.0.1/case/utf8", "STREAMING_ASSISTIDO_TARDIO")
            ]
