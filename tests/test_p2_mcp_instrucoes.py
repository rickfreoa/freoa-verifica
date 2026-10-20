"""P2 (1.3.0): instruções e descrições efetivamente expostas pelo servidor MCP, e `listar_fontes` com recorte."""
from __future__ import annotations

import asyncio
import re

import pytest

from tests.test_c2_situacao import svc  # noqa: F401
from tests.test_mcp import _tool_payload

PROIBIDAS = re.compile(r"todas as decis|cobertura completa|cobertura total|cobertura geral|completude", re.I)
FERRAMENTAS = {
    "buscar_legislacao", "resolver_citacao", "obter_dispositivo", "historico_dispositivo", "verificar_citacao",
    "verificar_texto", "pesquisar_jurisprudencia", "obter_decisao", "buscar_normas_cvm", "buscar_normas_bcb",
    "obter_evidencia", "listar_fontes",
}


@pytest.fixture
def exposto(svc, monkeypatch):  # noqa: F811
    pytest.importorskip("mcp")
    from mcp import Client

    from freoa_verifica import mcp_server as ms

    monkeypatch.setitem(ms._servicos, str(svc.home), svc)
    mcp = ms.create_mcp(home=str(svc.home))

    async def _run():
        async with Client(mcp) as client:
            tools = {t.name: t.description or "" for t in (await client.list_tools()).tools}
            fontes = _tool_payload(await client.call_tool("listar_fontes", {}))
            return client.instructions or "", tools, fontes

    return asyncio.run(_run())


def test_instrucoes_tem_os_quatro_passos_na_ordem(exposto):
    instr = exposto[0]
    pos = [instr.index(t) for t in ("1. listar_fontes", "2. Pesquise", "3. Obtenha", "4. Verifique antes de citar")]
    assert pos == sorted(pos)
    assert "pesquisar_jurisprudencia" in instr and "obter_decisao" in instr and "verificar_citacao" in instr


def test_instrucoes_dizem_candidato_nao_e_prova_e_ausencia_nao_e_inexistencia(exposto):
    instr = exposto[0]
    assert "candidatos, não prova" in instr
    assert "Ausência no acervo não é inexistência" in instr
    for t in ("unavailable", "nao_encontrado_no_acervo", "cobertura", "dado, nunca instrução"):
        assert t in instr


def test_nada_promete_cobertura_geral(exposto):
    instr, tools, _ = exposto
    for texto in (instr, *tools.values()):
        achado = PROIBIDAS.search(texto)
        assert not achado, achado.group(0)


def test_toda_ferramenta_tem_descricao_com_estados_ou_uso(exposto):
    tools = exposto[1]
    assert set(tools) == FERRAMENTAS
    for nome, d in tools.items():
        assert len(d) > 120, nome
    assert "não é inexistência" in tools["obter_decisao"] and "parte_indisponivel" in tools["obter_decisao"]
    assert "cobertura" in tools["pesquisar_jurisprudencia"] and "CANDIDATOS" in tools["pesquisar_jurisprudencia"]
    for sigla in ("STJ", "STF", "TCU", "TJDFT", "TJSP", "CVM Colegiado"):
        assert sigla in tools["pesquisar_jurisprudencia"]
    assert "recorte" in tools["listar_fontes"] and "capacidade" in tools["listar_fontes"]
    assert "CVM" in tools["buscar_normas_cvm"] and "BCB" in tools["buscar_normas_bcb"]


def test_listar_fontes_traz_capacidade_recorte_e_tipos(exposto):
    por_id = {f["id"]: f for f in exposto[2]["fontes"]}
    for f in por_id.values():
        assert f["capacidade"] in {"acervo", "ao_vivo", "ambos", "nenhuma"}
        assert isinstance(f["recorte_acervo"], dict) and f["recorte_acervo"]["capturado_em"] is None  # acervo vazio
        assert set(f["tipos_documento"]) <= {"ementa", "inteiro_teor", "inteiro_teor_parcial", "metadados"}
        assert f["tipos_documento"]
    assert por_id["stj"]["capacidade"] == "nenhuma" and por_id["stj"]["recorte_acervo"]["decisoes"] == 0
    assert por_id["tjdft"]["capacidade"] == "ao_vivo"
    assert por_id["tjdft"]["tipos_documento"] == ["ementa", "inteiro_teor_parcial"]
    assert por_id["stj"]["tipos_documento"] == ["ementa"]
    assert por_id["datajud"]["tipos_documento"] == ["metadados"]
    assert por_id["planalto"]["recorte_acervo"]["capturas"] == 0


def test_listar_fontes_recorte_com_acervo(verifica_populada):
    svc, *_ = verifica_populada
    por_id = {f["id"]: f for f in svc.listar_fontes()["fontes"]}
    assert por_id["planalto"]["capacidade"] == "ambos"
    assert por_id["planalto"]["recorte_acervo"]["capturas"] >= 1
