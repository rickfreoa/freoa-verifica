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

def test_volateis_do_codigo_estao_no_documento():
    md = CONTRATO_MD.read_text(encoding="utf-8")
    secao = md.split("## Voláteis", 1)[1].split("\n## ", 1)[0]
    declarados = set(re.findall(r"`([a-z0-9_]+)`", secao))
    assert declarados >= h.VOLATEIS_CHAVES | h.VOLATEIS_HASH_CHAVES


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
