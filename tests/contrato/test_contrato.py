"""P3: compatibilidade das respostas públicas com as respostas congeladas da 1.2.0 (docs/CONTRATO.md).

Para (re)congelar, só sobre o código 1.2.0: `pytest tests/contrato --congelar-contrato -p no:cacheprovider`.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest

pytest.importorskip("mcp")
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from freoa_verifica import CONTRATO_VERSAO, mcp_server as ms  # noqa: E402
from freoa_verifica.contrato import DEPRECATED, EXPERIMENTAL  # noqa: E402
from freoa_verifica.mcp_server import create_mcp  # noqa: E402
from freoa_verifica.rest import create_app  # noqa: E402
from tests.contrato import harness as h  # noqa: E402

CONTRATO_MD = Path(__file__).resolve().parents[2] / "docs" / "CONTRATO.md"


@pytest.fixture
def ambiente(verifica_populada, monkeypatch):
    svc, rw, _ = verifica_populada
    ctx = {**h.semear(svc), "capture_lsa": rw.capture_id}
    monkeypatch.setenv("FV_HOME", str(svc.home))
    monkeypatch.delenv("FV_API_TOKEN", raising=False)
    monkeypatch.setitem(ms._servicos, str(svc.home), svc)
    mcp = create_mcp(home=str(svc.home))
    app = create_app(home=str(svc.home), token=None)
    for cached in svc._resolver.works.values():
        app.state.verifica.registrar(cached)
    with TestClient(app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1") as rest:
        yield {"python": svc, "mcp": mcp, "rest": rest, "ctx": ctx}


def _responder(ambiente, adaptador, ferramenta, args):
    chamar = {"python": h.chamar_python, "mcp": h.chamar_mcp, "rest": h.chamar_rest}[adaptador]
    return chamar(ambiente[adaptador], ferramenta, h.resolver_args(args, ambiente["ctx"]))


@pytest.mark.parametrize("adaptador", h.ADAPTADORES)
@pytest.mark.parametrize("caso,ferramenta,args", h.CASOS, ids=[c[0] for c in h.CASOS])
def test_resposta_compativel_com_a_congelada(ambiente, request, adaptador, caso, ferramenta, args):
    atual = _responder(ambiente, adaptador, ferramenta, args)
    if request.config.getoption("--congelar-contrato"):
        h.gravar(adaptador, caso, ferramenta, args, atual)
        return
    congelado = h.carregar(adaptador, caso)
    assert congelado["_proveniencia"]["commit"] == h.COMMIT_1_2_0
    assert congelado["_proveniencia"]["adaptador"] == adaptador
    erros = h.incompatibilidades(ferramenta, congelado["resposta"], h.normalizar(atual), DEPRECATED | EXPERIMENTAL)
    assert not erros, "\n".join(erros)


def test_todo_caso_tem_arquivo_congelado():
    esperados = {h.nome_arquivo(a, c[0]).name for a in h.ADAPTADORES for c in h.CASOS}
    existentes = {p.name for p in h.ESPERADO.glob("*.json")}
    assert existentes == esperados


# ----------------------------------------------------------------------------------------------
# O teste de contrato precisa reprovar
# ----------------------------------------------------------------------------------------------

def _congelada(adaptador="python", caso="verificar_citacao_verified"):
    return h.carregar(adaptador, caso)["resposta"]


def test_negativo_campo_stable_removido_reprova():
    c = _congelada()
    adulterada = copy.deepcopy(c)
    del adulterada["identity"]["status"]
    erros = h.incompatibilidades("verificar_citacao", c, adulterada)
    assert any("campo removido: identity.status" in e for e in erros)


def test_negativo_tipo_mudado_reprova():
    c = _congelada()
    adulterada = copy.deepcopy(c)
    adulterada["identity"] = "verified"
    assert h.incompatibilidades("verificar_citacao", c, adulterada)


def test_negativo_estado_diferente_reprova():
    c = _congelada()
    adulterada = copy.deepcopy(c)
    adulterada["identity"]["status"] = "unknown"
    erros = h.incompatibilidades("verificar_citacao", c, adulterada)
    assert any("estados mudaram em identity.status" in e for e in erros)


def test_negativo_campo_removido_de_um_unico_item_reprova():
    c = _congelada(caso="pesquisar_jurisprudencia_textual")
    assert len(c["itens"]) >= 2 and all("ementa" in i for i in c["itens"])
    adulterada = copy.deepcopy(c)
    del adulterada["itens"][0]["ementa"]  # os outros itens ainda têm `ementa`
    erros = h.incompatibilidades("pesquisar_jurisprudencia", c, adulterada, DEPRECATED | EXPERIMENTAL)
    assert any("campo removido: itens[].ementa (elemento 0)" in e for e in erros)
    assert h.incompatibilidades("pesquisar_jurisprudencia", c, copy.deepcopy(c), DEPRECATED | EXPERIMENTAL) == []


@pytest.mark.parametrize("valor", [42, None], ids=["numero", "null"])
def test_negativo_tipo_ou_nulidade_de_um_unico_item_reprova(valor):
    """B3-07: o agregado por caminho encobria `itens[0].ementa` com outro tipo ou null."""
    c = _congelada(caso="pesquisar_jurisprudencia_textual")
    assert len(c["itens"]) >= 2 and all(isinstance(i["ementa"], str) for i in c["itens"])
    adulterada = copy.deepcopy(c)
    adulterada["itens"][0]["ementa"] = valor
    erros = h.incompatibilidades("pesquisar_jurisprudencia", c, adulterada, DEPRECATED | EXPERIMENTAL)
    assert any(e.startswith("tipo mudou em itens[].ementa") for e in erros), erros


def test_tipo_por_elemento_respeita_variantes_e_isencoes():
    c = {"itens": [{"id": 1, "x": None}, {"id": 2, "x": "a"}]}
    assert h.incompatibilidades("t", c, {"itens": [{"id": 1, "x": "agora com valor"}, {"id": 2, "x": "a"}]}) == []
    mudou = {"itens": [{"id": 1, "x": None}, {"id": 2, "x": 5}]}
    assert h.incompatibilidades("t", c, mudou)
    assert h.incompatibilidades("t", c, mudou, frozenset({"t:itens[].x"})) == []


def test_listas_heterogeneas_preservam_variantes_legitimas():
    c = {"itens": [{"id": 1, "ementa": "x"}, {"id": 2, "trecho_inteiro_teor": "y"}]}
    atual = {"itens": [{"id": 1, "ementa": "x", "novo": 1}, {"id": 2, "trecho_inteiro_teor": "y"}]}
    assert h.incompatibilidades("t", c, atual) == []
    trocado = {"itens": [{"id": 1, "trecho_inteiro_teor": "x"}, {"id": 2, "trecho_inteiro_teor": "y"}]}
    assert any("itens[].ementa (elemento 0)" in e for e in h.incompatibilidades("t", c, trocado))


def test_campo_novo_e_permitido():
    c = _congelada()
    ampliada = copy.deepcopy(c)
    ampliada["campo_novo"] = {"qualquer": 1}
    ampliada["identity"]["extra"] = True
    assert h.incompatibilidades("verificar_citacao", c, ampliada) == []


def test_campo_deprecated_pode_sumir():
    c = _congelada()
    adulterada = copy.deepcopy(c)
    del adulterada["proposicao"]
    assert h.incompatibilidades("verificar_citacao", c, adulterada)
    assert h.incompatibilidades("verificar_citacao", c, adulterada, frozenset({"verificar_citacao:proposicao"})) == []


def test_isencao_vale_para_o_que_esta_sob_o_caminho():
    c = _congelada(caso="verificar_citacao_verified")
    adulterada = copy.deepcopy(c)
    del adulterada["identity"]["evidence"]
    assert h.incompatibilidades("verificar_citacao", c, adulterada)
    assert h.incompatibilidades("verificar_citacao", c, adulterada, frozenset({"verificar_citacao:identity.evidence"})) == []
    # prefixo textual sem fronteira de caminho não isenta outro campo
    assert h.incompatibilidades("verificar_citacao", c, adulterada, frozenset({"verificar_citacao:identity.evid"}))


# ----------------------------------------------------------------------------------------------
# Documento e versão do contrato
# ----------------------------------------------------------------------------------------------

@pytest.mark.repositorio
def test_volateis_do_codigo_estao_no_documento():
    md = CONTRATO_MD.read_text(encoding="utf-8")
    secao = md.split("## Voláteis", 1)[1].split("\n## ", 1)[0]
    declarados = set(re.findall(r"`([a-z0-9_]+)`", secao))
    assert declarados >= h.VOLATEIS_CHAVES | h.VOLATEIS_HASH_CHAVES


@pytest.mark.repositorio
def test_estados_congelados_estao_enumerados_no_documento():
    md = CONTRATO_MD.read_text(encoding="utf-8")
    faltando = set()
    for a in h.ADAPTADORES:
        for caso, _, _ in h.CASOS:
            for valores in h.estados(h.carregar(a, caso)["resposta"]).values():
                faltando |= {v for v in valores if f"`{v}`" not in md}
    assert not faltando, f"estados fora de docs/CONTRATO.md: {sorted(faltando)}"


@pytest.mark.parametrize("adaptador", h.ADAPTADORES)
def test_contrato_versao_em_listar_fontes(ambiente, adaptador):
    assert CONTRATO_VERSAO == "1"
    r = _responder(ambiente, adaptador, "listar_fontes", {})
    assert r["contrato"] == CONTRATO_VERSAO
    assert r["total"] == len(r["fontes"])


def test_listar_fontes_congelado_da_1_2_0_nao_tem_contrato():
    # a chave é aditiva: o arquivo congelado é o da 1.2.0 e não a traz; a atual a traz sem reprovar
    c = h.carregar("python", "listar_fontes")["resposta"]
    assert "contrato" not in c
    assert h.incompatibilidades("listar_fontes", c, {**c, "contrato": "1"}) == []


# ----------------------------------------------------------------------------------------------
# P1: `cobertura` (experimental) em pesquisar_jurisprudencia
# ----------------------------------------------------------------------------------------------

_CAMPOS_COBERTURA = {"tribunal", "capacidade", "consulta", "motivo_nao_consulta", "recorte_acervo", "capturado_em",
                     "total_remoto", "total_exato", "lidos", "indexados", "truncado_remoto", "truncado_local",
                     "indisponivel"}


@pytest.mark.parametrize("adaptador", h.ADAPTADORES)
def test_cobertura_nos_tres_adaptadores(ambiente, adaptador):
    r = _responder(ambiente, adaptador, "pesquisar_jurisprudencia", {"q": "ementa sintética", "tribunais": ["STJ"]})
    assert [set(c) for c in r["cobertura"]] == [_CAMPOS_COBERTURA]
    c = r["cobertura"][0]
    assert c["tribunal"] == "STJ" and c["total_remoto"] is None  # acervo só: nunca zero inventado


@pytest.mark.repositorio
def test_cobertura_e_experimental_e_documentada():
    assert "pesquisar_jurisprudencia:cobertura[]" in EXPERIMENTAL
    md = CONTRATO_MD.read_text(encoding="utf-8")
    secao = md.split("### `pesquisar_jurisprudencia`", 1)[1].split("\n### ", 1)[0]
    assert "cobertura" in secao and "experimental" in secao
    for campo in _CAMPOS_COBERTURA:
        assert f"`{campo}`" in md


def test_cobertura_experimental_nao_isenta_o_objeto_estavel_do_acervo():
    congelada = {"cobertura": {"desde": "2020-01-01", "tribunais": ["STJ"]}}
    sem_objeto = {"cobertura": []}
    assert h.incompatibilidades("pesquisar_jurisprudencia", congelada, sem_objeto, EXPERIMENTAL)


# ----------------------------------------------------------------------------------------------
# Decisão 0073, seção 1, item 2: entrada `"<ferramenta>:"` isenta a ferramenta inteira
# ----------------------------------------------------------------------------------------------

def test_prefixo_de_ferramenta_isenta_todo_campo_dela():
    c = {"a": {"b": 1}, "itens": [{"x": "s"}], "status": "ok"}
    sumiu = {"itens": [{"x": 5}], "status": "erro"}
    assert h.incompatibilidades("ferramenta_x", c, sumiu)
    assert h.incompatibilidades("ferramenta_x", c, sumiu, frozenset({"ferramenta_x:"})) == []


def test_prefixo_de_ferramenta_nao_isenta_outra_ferramenta_nem_nome_parecido():
    c = {"campo": "s", "status": "ok"}
    adulterada = {"campo": 1, "status": "erro"}
    isentos = frozenset({"obter_decisao:"})
    for outra in ("obter_decisao_x", "obter_decisao_", "obter_decisa", "x_obter_decisao", "pesquisar_jurisprudencia"):
        erros = h.incompatibilidades(outra, c, adulterada, isentos)
        assert any("tipo mudou em campo" in e for e in erros), (outra, erros)
        assert any("estados mudaram em status" in e for e in erros), (outra, erros)
    assert h.incompatibilidades("obter_decisao", c, adulterada, isentos) == []


def test_isencoes_por_caminho_continuam_iguais():
    c = {"particao": {"x": 1}, "texto": "s"}
    isentos = frozenset({"obter_decisao:particao"})
    assert h.incompatibilidades("obter_decisao", c, {"texto": "s"}, isentos) == []
    assert h.incompatibilidades("obter_decisao", c, {"particao": 1, "texto": "s"}, isentos) == []
    assert h.incompatibilidades("obter_decisao", c, {"particao": {"x": 1}}, isentos)  # `texto` segue exigido
    assert h.incompatibilidades("obter_decisao", {"particaox": 1}, {}, isentos)  # nome parecido não é descendente
    assert h.incompatibilidades("obter_decisao_x", c, {"texto": "s"}, isentos)
