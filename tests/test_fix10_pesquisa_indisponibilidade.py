"""FIX10/F-14: a pesquisa textual não engole desafio do indexador e não repete a mesma captura.

Dois candidatos da mesma ata CVM, conector e transporte reais, servidor local. Mesmo resultado pelas
três portas (Python, MCP, REST): uma única requisição, status de topo diferente de `ok` e a categoria
declarada em `cobertura[].indisponivel`.
"""

from __future__ import annotations

import asyncio

import pytest

from freoa_verifica.connectors.base import Candidate
from freoa_verifica.connectors.cvm_colegiado import CvmColegiadoConnector
from freoa_verifica.service import Verifica
from tests.test_fix9_guarda_execucao import ATA, CAPTCHA, ambiente  # noqa: F401  (fixture)
from tests.test_mcp import _tool_payload

LOCAL = ("127.0.0.1", 50000)
CAMINHO = "/decisoes/2024/20240105_R1.html"
URL = f"https://conteudo.cvm.gov.br{CAMINHO}"
ARGS = {"q": "controle acionario", "tribunais": ["cvm"], "limite": 10}


@pytest.fixture
def dois_candidatos(monkeypatch):
    def busca(self, q, **filtros):
        return [
            Candidate(source_id="cvm_colegiado", key=f"reuniao=20240105-R1#{i}", title="Reuniao", url=URL,
                      metadata={"kind": "ata_colegiado_cvm", "item": i, "court": "CVM"})
            for i in (1, 2)
        ]

    monkeypatch.setattr(CvmColegiadoConnector, "search", busca)


def _cobertura_cvm(saida):
    return next(c for c in saida["cobertura"] if c["tribunal"] == "CVM_COLEGIADO")


def _confere_desafio(saida, server, incrementos):
    assert [p[1] for p in server.pedidos] == [CAMINHO]  # 1 GET, não 2
    assert len(incrementos) == 1
    assert saida["status"] != "ok"
    assert saida["fontes"]["cvm_colegiado"]["status"] == "unavailable"
    assert saida["fontes"]["cvm_colegiado"]["categoria"] == "ambiental_desafio"
    indisponivel = _cobertura_cvm(saida)["indisponivel"]
    assert indisponivel and indisponivel["categoria"] == "ambiental_desafio"


def test_python_desafio_interrompe_a_fonte_e_e_declarado(ambiente, dois_candidatos, tmp_path):
    server, incrementos = ambiente({CAMINHO: [(403, "text/html", CAPTCHA)]})
    with Verifica(tmp_path) as svc:
        saida = svc.pesquisar_jurisprudencia(**ARGS)
    _confere_desafio(saida, server, incrementos)


def test_mcp_desafio_interrompe_a_fonte_e_e_declarado(ambiente, dois_candidatos, tmp_path, monkeypatch):
    pytest.importorskip("mcp")
    from mcp import Client

    from freoa_verifica import mcp_server as ms

    server, incrementos = ambiente({CAMINHO: [(403, "text/html", CAPTCHA)]})
    with Verifica(tmp_path) as svc:
        monkeypatch.setitem(ms._servicos, str(svc.home), svc)
        mcp = ms.create_mcp(home=str(svc.home))

        async def _run():
            async with Client(mcp) as client:
                r = await client.call_tool("pesquisar_jurisprudencia", ARGS)
                assert not r.is_error
                return _tool_payload(r)

        saida = asyncio.run(_run())
    _confere_desafio(saida, server, incrementos)


def test_rest_desafio_interrompe_a_fonte_e_e_declarado(ambiente, dois_candidatos, tmp_path):
    pytest.importorskip("fastapi")
    from starlette.testclient import TestClient

    from freoa_verifica.rest import create_app

    server, incrementos = ambiente({CAMINHO: [(403, "text/html", CAPTCHA)]})
    with TestClient(create_app(home=str(tmp_path), token="t"), client=LOCAL) as c:
        r = c.get("/v1/jurisprudencia", params={"q": ARGS["q"], "tribunais": "cvm"},
                  headers={"Authorization": "Bearer t"})
    assert r.status_code == 200
    _confere_desafio(r.json(), server, incrementos)


def test_candidatos_da_mesma_ata_usam_uma_unica_captura(ambiente, dois_candidatos, tmp_path):
    server, incrementos = ambiente({CAMINHO: [(200, "text/html", ATA), (403, "text/html", CAPTCHA)]})
    with Verifica(tmp_path) as svc:
        saida = svc.pesquisar_jurisprudencia(**ARGS)
        # o conector marca a URL com o item (#1, #2), logo há um registro por item, mas sobre os mesmos bytes
        capturas = svc.conn.execute("SELECT COUNT(DISTINCT sha256) FROM capture").fetchone()[0]
    assert [p[1] for p in server.pedidos] == [CAMINHO]
    assert len(incrementos) == 0
    assert _cobertura_cvm(saida)["indexados"] == 2
    assert _cobertura_cvm(saida)["indisponivel"] is None
    assert capturas == 1


def test_pesquisas_seguidas_nao_compartilham_a_guarda(ambiente, dois_candidatos, tmp_path):
    """O bloqueio vale para uma pesquisa; a seguinte tenta a fonte de novo."""
    server, _ = ambiente({CAMINHO: [(403, "text/html", CAPTCHA)]})
    with Verifica(tmp_path) as svc:
        svc.pesquisar_jurisprudencia(**ARGS)
        svc.pesquisar_jurisprudencia(**ARGS)
    assert len(server.pedidos) == 2
