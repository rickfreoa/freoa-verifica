"""B2-04: nos modos por número e CNJ, filtro não aplicável é declarado; tribunal e limite valem (decisão 0053)."""
import pytest

pytest.importorskip("mcp")
pytest.importorskip("fastapi")

from tests.contrato import harness as h  # noqa: E402
from tests.contrato.test_contrato import _responder, ambiente  # noqa: E402,F401
from tests.test_p1_cobertura import _cnj  # noqa: E402

FILTROS = {"desde": "2099-01-01", "ate": "2099-02-01", "autoridade_min": "A", "cursor": "x"}
DECLARADOS = [{"filtro": f, "motivo": "modo_por_identificador"} for f in FILTROS]


@pytest.mark.parametrize("adaptador", h.ADAPTADORES)
def test_numero_declara_o_que_nao_aplica_e_aplica_tribunal(ambiente, adaptador):
    r = _responder(ambiente, adaptador, "pesquisar_jurisprudencia",
                   {"q": "REsp 900.001", "tribunais": ["stj"], "limite": 1, **FILTROS})
    assert r["modo_busca"] == "numero" and len(r["itens"]) == 1  # data futura não zera o identificador
    assert r["filtros_nao_aplicados"] == DECLARADOS
    sem = _responder(ambiente, adaptador, "pesquisar_jurisprudencia", {"q": "REsp 900.001"})
    assert sem["filtros_nao_aplicados"] == []
    fora = _responder(ambiente, adaptador, "pesquisar_jurisprudencia",
                      {"q": "REsp 900.001", "tribunais": ["tjdft"], "desde": "2099-01-01"})
    assert fora["itens"] == [] and fora["status"] == "nao_confirmado_no_acervo"
    assert fora["filtros_nao_aplicados"] == [{"filtro": "desde", "motivo": "modo_por_identificador"}]


@pytest.mark.parametrize("adaptador", h.ADAPTADORES)
def test_cnj_declara_o_que_nao_aplica_e_aplica_tribunal(ambiente, adaptador):
    cnj = _cnj("0713166", "2018", "807", "0000")
    r = _responder(ambiente, adaptador, "pesquisar_jurisprudencia",
                   {"q": cnj, "tribunais": ["tjdft"], "limite": 1, **FILTROS})
    assert r["modo_busca"] == "numero_cnj" and r["filtros_nao_aplicados"] == DECLARADOS
    fora = _responder(ambiente, adaptador, "pesquisar_jurisprudencia", {"q": cnj, "tribunais": ["stj"]})
    assert fora["escopo"] == "tribunal fora do filtro" and fora["cobertura"] == [] and fora["itens"] == []
    assert fora["filtros_nao_aplicados"] == []
