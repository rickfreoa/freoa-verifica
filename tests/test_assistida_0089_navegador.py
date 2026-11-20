"""0089: integração real restrita ao servidor HTTPS local; nenhuma fonte real."""

import time

import pytest
from freoa_verifica.assistida import ambiente as a

from tests.harness_assistida_0089 import CORPOS, navegador_pipe, origem_https

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
        "redirect",
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
            limite = time.monotonic() + 48
            while time.monotonic() < limite:
                vigia.assentar()
                msg = ad.canal.receber()
                if msg:
                    with msg as obj:
                        ad.processar(obj)
                ad.fiscalizar_capturas()
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
            assert vistos
