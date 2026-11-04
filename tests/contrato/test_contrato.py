"""P3: compatibilidade das respostas públicas com as respostas congeladas da 1.2.0 (docs/CONTRATO.md).

Para (re)congelar, só sobre o código 1.2.0: `pytest tests/contrato --congelar-contrato -p no:cacheprovider`.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

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
FREOA_JSON = Path(__file__).resolve().parent / "consumidores" / "freoa.json"
FREOA_NAO_EXERCITADOS_JSON = Path(__file__).resolve().parent / "consumidores" / "freoa_nao_exercitados.json"


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
    esperado_commit = h.commit_do_caso(caso)
    assert congelado["_proveniencia"]["commit"] == esperado_commit
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


# ----------------------------------------------------------------------------------------------
# Decisão 0075, seção 3.5: Contrato do consumidor FREOA
# ----------------------------------------------------------------------------------------------


def _obter_caminho_val(obj: Any, caminho: str) -> list[Any]:
    partes = caminho.split(".")
    atual = [obj]
    for p in partes:
        prox = []
        is_list = p.endswith("[]")
        campo = p[:-2] if is_list else p
        for item in atual:
            if isinstance(item, dict) and campo in item:
                val = item[campo]
                if is_list:
                    if isinstance(val, list):
                        prox.extend(val)
                else:
                    prox.append(val)
            elif isinstance(item, list) and is_list:
                for sub in item:
                    if isinstance(sub, dict) and campo in sub:
                        val = sub[campo]
                        prox.append(val)
        atual = prox
    return atual


def _condicao_satisfeita(resposta: dict[str, Any], condicao: dict[str, Any] | None) -> bool:
    if not condicao:
        return True
    for campo, esperado in condicao.items():
        valores = _obter_caminho_val(resposta, campo)
        if not valores:
            return False
        if esperado == "@nao_nulo":  # variante legítima: campo presente e não nulo (ex.: obtenção sem caminho)
            if not any(v is not None for v in valores):
                return False
        elif isinstance(esperado, list):
            if not any(v in esperado for v in valores):
                return False
        else:
            if not any(v == esperado for v in valores):
                return False
    return True


def _validar_caminho_elemento(
    atual: Any,
    partes: list[str],
    caminho: str,
    tipos_esperados: set[str],
    prefixo: str = "",
) -> list[str]:
    if not partes:
        t = h._tipo(atual)
        if t not in tipos_esperados:
            return [f"tipo incompatível em {caminho}: esperado {tipos_esperados}, observado {t}"]
        return []

    p = partes[0]
    resto = partes[1:]
    is_list = p.endswith("[]")
    campo = p[:-2] if is_list else p
    passo = f"{prefixo}.{p}" if prefixo else p

    if not isinstance(atual, dict) or campo not in atual:
        return [f"caminho ausente: {caminho}"]

    val = atual[campo]
    if not is_list:
        return _validar_caminho_elemento(val, resto, caminho, tipos_esperados, passo)

    if not isinstance(val, list):
        return [f"tipo incompatível em {passo}: esperado array, observado {h._tipo(val)}"]

    if len(val) == 0:
        return [f"caminho ausente: {caminho}"]

    erros: list[str] = []
    for i, item in enumerate(val):
        passo_i = f"{passo[:-2]}[{i}]"
        if resto:
            if not isinstance(item, dict):
                erros.append(f"tipo incompatível no elemento {i} de {passo}: esperado object, observado {h._tipo(item)}")
            else:
                sub_erros = _validar_caminho_elemento(item, resto, caminho, tipos_esperados, passo_i)
                for se in sub_erros:
                    if se.startswith("caminho ausente:") and f"elemento {i}" not in se:
                        erros.append(f"{se} (elemento {i})")
                    else:
                        erros.append(se)
        else:
            t = h._tipo(item)
            if t not in tipos_esperados:
                erros.append(f"tipo incompatível no elemento {i} de {caminho}: esperado {tipos_esperados}, observado {t}")
    return erros


def validar_resposta_consumidor(
    ferramenta: str,
    spec: dict[str, Any],
    resposta: dict[str, Any],
    isentos: frozenset[str] = frozenset(),
) -> list[str]:
    """Valida uma resposta contra a especificação de um consumidor (ex.: FREOA)."""
    erros: list[str] = []
    norm = h.normalizar(resposta)
    mapa_estados = h.estados(norm)

    # 1. Caminhos e tipos por elemento aplicável
    caminhos_spec = spec.get("caminhos", {})
    for caminho, def_caminho in caminhos_spec.items():
        if f"{ferramenta}:{caminho}" in DEPRECATED or h._isento(ferramenta, caminho, isentos):
            continue

        if isinstance(def_caminho, dict):
            tipo_expr = def_caminho["tipo"]
            condicao = def_caminho.get("condicao")
        else:
            tipo_expr = def_caminho
            condicao = None

        if not _condicao_satisfeita(resposta, condicao):
            continue

        tipos_esperados = set(tipo_expr.split("|"))
        partes = caminho.split(".")
        erros.extend(_validar_caminho_elemento(norm, partes, caminho, tipos_esperados))

    # 2. Literais e conformidade de estados na resposta
    estados_spec = spec.get("estados", {})
    for caminho_estado, permitidos in estados_spec.items():
        if f"{ferramenta}:{caminho_estado}" in DEPRECATED or h._isento(ferramenta, caminho_estado, isentos):
            continue
        permitidos_set = set(permitidos)
        observados = set(mapa_estados.get(caminho_estado, []))
        fora = observados - permitidos_set
        if fora:
            erros.append(
                f"estados não suportados pelo consumidor em {caminho_estado}: {fora}"
            )

    return erros


def conferir_literais_observados(
    ferramenta: str,
    spec: dict[str, Any],
    respostas: list[dict[str, Any]],
    isentos: frozenset[str] = frozenset(),
    nao_exercitados: list[dict[str, str]] | None = None,
) -> list[str]:
    """Para cada (ferramenta, caminho, literal) em estados do freoa.json,

    exige que:
    (a) todo literal consumido fora de freoa_nao_exercitados.json seja observado em pelo
        menos uma resposta atual da implementação;
    (b) a lista freoa_nao_exercitados.json seja exata: literal da lista que passe a ser
        observado reprova (obriga a retirá-lo da lista), e literal consumido não observado
        e fora da lista reprova.
    """
    erros: list[str] = []
    estados_spec = spec.get("estados", {})
    if not estados_spec:
        return []

    if nao_exercitados is None:
        nao_exercitados = json.loads(FREOA_NAO_EXERCITADOS_JSON.read_text(encoding="utf-8"))

    nao_exercitados_map: set[tuple[str, str]] = {
        (item["caminho"], item["literal"])
        for item in nao_exercitados
        if item.get("ferramenta") == ferramenta
    }

    # Valida se os itens em nao_exercitados realmente constam na especificação consumida
    for caminho_ne, literal_ne in nao_exercitados_map:
        if caminho_ne not in estados_spec or literal_ne not in estados_spec[caminho_ne]:
            erros.append(
                f"literal {literal_ne!r} em {caminho_ne} consta de freoa_nao_exercitados.json mas não é consumido em freoa.json"
            )

    observados_por_caminho: dict[str, set[str]] = {}
    for resp in respostas:
        norm = h.normalizar(resp)
        mapa_est = h.estados(norm)
        for caminho_est, vals in mapa_est.items():
            observados_por_caminho.setdefault(caminho_est, set()).update(vals)

    for caminho_estado, permitidos in estados_spec.items():
        if f"{ferramenta}:{caminho_estado}" in DEPRECATED or h._isento(ferramenta, caminho_estado, isentos):
            continue
        observados = observados_por_caminho.get(caminho_estado, set())
        for literal in permitidos:
            chave = (caminho_estado, literal)
            is_nao_exercitado = chave in nao_exercitados_map
            is_observado = literal in observados

            if is_nao_exercitado and is_observado:
                erros.append(
                    f"literal {literal!r} em {caminho_estado} consta de freoa_nao_exercitados.json mas foi observado nas respostas (deve ser retirado da lista)"
                )
            elif not is_nao_exercitado and not is_observado:
                erros.append(
                    f"literal {literal!r} em {caminho_estado} não foi observado em nenhuma resposta da implementação"
                )
    return erros


@pytest.mark.parametrize("adaptador", h.ADAPTADORES)
def test_contrato_consumidor_freoa_satisfeito(ambiente, adaptador):
    contrato_consumidor = json.loads(FREOA_JSON.read_text(encoding="utf-8"))
    casos_por_ferramenta = {
        "verificar_citacao": [
            "verificar_citacao_verified",
            "verificar_citacao_trecho_divergente",
            "verificar_citacao_obra_inexistente",
            "verificar_citacao_historica_riscada",
            "verificar_citacao_dispositivo_inexistente",
            "verificar_citacao_fonte_indisponivel",
            "verificar_citacao_requer_conferencia",
        ],
        "obter_dispositivo": [
            "obter_dispositivo",
            "obter_dispositivo_revogado_corrente",
            "obter_dispositivo_nao_existia",
            "obter_dispositivo_historica",
            "obter_dispositivo_sem_caminho",
            "obter_dispositivo_requer_conferencia",
            "obter_dispositivo_formato_invalido",
            "obter_dispositivo_inexistente",
            "obter_dispositivo_indisponivel",
        ],
        "listar_fontes": ["listar_fontes"],
        "obter_registro": ["obter_registro_encontrada", "obter_registro_inexistente"],
    }
    casos_map = {c[0]: c for c in h.CASOS}

    for ferramenta, spec in contrato_consumidor["ferramentas"].items():
        nomes_casos = casos_por_ferramenta[ferramenta]
        respostas = []
        for nome_caso in nomes_casos:
            _, _, args = casos_map[nome_caso]
            resp = _responder(ambiente, adaptador, ferramenta, args)
            erros = validar_resposta_consumidor(ferramenta, spec, resp, DEPRECATED)
            assert not erros, f"[{adaptador}] {ferramenta} ({nome_caso}):\n" + "\n".join(erros)
            respostas.append(resp)

        # 1.a / D5: Preservação de literais pela IMPLEMENTAÇÃO com verificação exata
        erros_literais = conferir_literais_observados(ferramenta, spec, respostas, DEPRECATED)
        assert not erros_literais, f"[{adaptador}] {ferramenta} literais não observados / divergentes da lista:\n" + "\n".join(erros_literais)


@pytest.mark.repositorio
def test_contrato_consumidor_freoa_estados_no_documento():
    contrato_consumidor = json.loads(FREOA_JSON.read_text(encoding="utf-8"))
    md = CONTRATO_MD.read_text(encoding="utf-8")
    for ferramenta, spec in contrato_consumidor["ferramentas"].items():
        for caminho_estado, permitidos in spec.get("estados", {}).items():
            faltando_doc = [v for v in permitidos if f"`{v}`" not in md]
            assert not faltando_doc, f"estados fora de docs/CONTRATO.md em {caminho_estado}: {faltando_doc}"


def test_gate_mutante_remocao_caminho():
    contrato_consumidor = json.loads(FREOA_JSON.read_text(encoding="utf-8"))
    spec = contrato_consumidor["ferramentas"]["verificar_citacao"]
    congelado = copy.deepcopy(h.carregar("python", "verificar_citacao_verified")["resposta"])
    del congelado["identity"]["status"]
    erros = validar_resposta_consumidor("verificar_citacao", spec, congelado)
    assert any("caminho ausente: identity.status" in e for e in erros)


def test_gate_mutante_troca_de_tipo():
    contrato_consumidor = json.loads(FREOA_JSON.read_text(encoding="utf-8"))
    spec = contrato_consumidor["ferramentas"]["verificar_citacao"]
    congelado = copy.deepcopy(h.carregar("python", "verificar_citacao_verified")["resposta"])
    congelado["identity"]["status"] = 42
    erros = validar_resposta_consumidor("verificar_citacao", spec, congelado)
    assert any("tipo incompatível em identity.status" in e for e in erros)


def test_gate_mutante_retirada_de_literal():
    contrato_consumidor = json.loads(FREOA_JSON.read_text(encoding="utf-8"))
    spec = copy.deepcopy(contrato_consumidor["ferramentas"]["verificar_citacao"])
    congelado = h.carregar("python", "verificar_citacao_verified")["resposta"]
    spec["estados"]["identity.status"] = [e for e in spec["estados"]["identity.status"] if e != "verified"]
    erros = validar_resposta_consumidor("verificar_citacao", spec, congelado)
    assert any("identity.status" in e for e in erros)


@pytest.mark.repositorio
def test_gate_mutante_retirada_de_literal_do_documento():
    contrato_consumidor = json.loads(FREOA_JSON.read_text(encoding="utf-8"))
    md_sem_literal = CONTRATO_MD.read_text(encoding="utf-8").replace("`verified`", "removido")
    faltando = [v for v in contrato_consumidor["ferramentas"]["verificar_citacao"]["estados"]["identity.status"]
                if f"`{v}`" not in md_sem_literal]
    assert "verified" in faltando


def test_gate_mutante_literal_novo():
    contrato_consumidor = json.loads(FREOA_JSON.read_text(encoding="utf-8"))
    spec = contrato_consumidor["ferramentas"]["verificar_citacao"]
    congelado = copy.deepcopy(h.carregar("python", "verificar_citacao_verified")["resposta"])
    congelado["identity"]["status"] = "literal_novo_nao_documentado"
    erros = validar_resposta_consumidor("verificar_citacao", spec, congelado)
    assert any("identity.status" in e and "literal_novo_nao_documentado" in e for e in erros)


def test_gate_mutante_campo_por_elemento_lista():
    """Mutante obrigatório (item 1.b): resposta real de verificar_citacao com

    a evidência duplicada e capture_id removido só do segundo elemento deve REPROVAR.
    """
    contrato_consumidor = json.loads(FREOA_JSON.read_text(encoding="utf-8"))
    spec = contrato_consumidor["ferramentas"]["verificar_citacao"]
    resposta_real = copy.deepcopy(h.carregar("python", "verificar_citacao_verified")["resposta"])
    assert len(resposta_real["identity"]["evidence"]) >= 1

    ev0 = copy.deepcopy(resposta_real["identity"]["evidence"][0])
    ev1 = copy.deepcopy(ev0)
    del ev1["capture_id"]
    resposta_real["identity"]["evidence"] = [ev0, ev1]

    erros = validar_resposta_consumidor("verificar_citacao", spec, resposta_real)
    assert any("capture_id" in e for e in erros), f"Esperava reprovação por capture_id ausente no elemento 1, obteve: {erros}"


@pytest.mark.parametrize("adaptador", h.ADAPTADORES)
def test_gate_mutante_preservacao_literais_implementacao(ambiente, adaptador):
    """Mutante obrigatório (item 1.a): monkeypatch que troca, nas respostas,

    todo identity.status == "verified" por "unknown" (sem mexer em especificação
    nem documentação) deve REPROVAR o gate nos três adaptadores.
    """
    contrato_consumidor = json.loads(FREOA_JSON.read_text(encoding="utf-8"))
    spec = contrato_consumidor["ferramentas"]["verificar_citacao"]
    casos = [
        "verificar_citacao_verified",
        "verificar_citacao_trecho_divergente",
        "verificar_citacao_obra_inexistente",
        "verificar_citacao_historica_riscada",
    ]
    casos_map = {c[0]: c for c in h.CASOS}

    respostas_mutadas = []
    for nome_caso in casos:
        _, _, args = casos_map[nome_caso]
        resp = _responder(ambiente, adaptador, "verificar_citacao", args)
        resp_mutada = copy.deepcopy(resp)
        if isinstance(resp_mutada.get("identity"), dict) and resp_mutada["identity"].get("status") == "verified":
            resp_mutada["identity"]["status"] = "unknown"
        respostas_mutadas.append(resp_mutada)

    erros = conferir_literais_observados("verificar_citacao", spec, respostas_mutadas, DEPRECATED)
    assert any("verified" in e and "identity.status" in e for e in erros), (
        f"[{adaptador}] Esperava reprovação por ausência de 'verified' em identity.status, obteve: {erros}"
    )


@pytest.mark.parametrize("adaptador", h.ADAPTADORES)
def test_gate_mutante_esvaziar_evidence_mantendo_verified(ambiente, adaptador):
    """Mutante obrigatório (item 3): resposta com identity.evidence=[] mantendo

    identity.status == "verified" deve REPROVAR nos três adaptadores por caminho ausente.
    """
    contrato_consumidor = json.loads(FREOA_JSON.read_text(encoding="utf-8"))
    spec = contrato_consumidor["ferramentas"]["verificar_citacao"]
    casos_map = {c[0]: c for c in h.CASOS}
    _, _, args = casos_map["verificar_citacao_verified"]
    resp = _responder(ambiente, adaptador, "verificar_citacao", args)
    resp_mutada = copy.deepcopy(resp)
    assert resp_mutada["identity"]["status"] == "verified"
    assert len(resp_mutada["identity"]["evidence"]) >= 1
    resp_mutada["identity"]["evidence"] = []

    erros = validar_resposta_consumidor("verificar_citacao", spec, resp_mutada)
    assert any("identity.evidence" in e and "caminho ausente" in e for e in erros), (
        f"[{adaptador}] Esperava reprovação por identity.evidence[] ausente quando vazia em verified, obteve: {erros}"
    )


def test_gate_mutante_acrescentar_literal_exercitado_a_lista_reprova():
    """Mutante de (2) / item 4: acrescentar à lista freoa_nao_exercitados.json um literal

    que é efetivamente exercitado (ex.: 'verified' em identity.status) deve REPROVAR.
    """
    contrato_consumidor = json.loads(FREOA_JSON.read_text(encoding="utf-8"))
    spec = contrato_consumidor["ferramentas"]["verificar_citacao"]
    casos = [
        "verificar_citacao_verified",
        "verificar_citacao_trecho_divergente",
        "verificar_citacao_obra_inexistente",
        "verificar_citacao_historica_riscada",
    ]
    respostas = [h.carregar("python", c)["resposta"] for c in casos]

    nao_exercitados = json.loads(FREOA_NAO_EXERCITADOS_JSON.read_text(encoding="utf-8"))
    nao_exercitados_mutados = list(nao_exercitados) + [{
        "ferramenta": "verificar_citacao",
        "caminho": "identity.status",
        "literal": "verified",
        "motivo": "sem caso no harness; cobertura pendente do IL.0b",
    }]

    erros = conferir_literais_observados(
        "verificar_citacao", spec, respostas, DEPRECATED, nao_exercitados=nao_exercitados_mutados
    )
    assert any("verified" in e and "consta de freoa_nao_exercitados.json mas foi observado" in e for e in erros), (
        f"Esperava reprovação por acrescentar literal exercitado à lista, obteve: {erros}"
    )


def test_gate_mutante_retirar_literal_exercitado_reprova():
    """Mutante de (2) / item 4: retirar um literal exercitado (ex.: 'verified' em identity.status)

    das respostas da implementação deve REPROVAR o teste de preservação.
    """
    contrato_consumidor = json.loads(FREOA_JSON.read_text(encoding="utf-8"))
    spec = contrato_consumidor["ferramentas"]["verificar_citacao"]
    casos = [
        "verificar_citacao_verified",
        "verificar_citacao_trecho_divergente",
        "verificar_citacao_obra_inexistente",
        "verificar_citacao_historica_riscada",
    ]
    respostas = []
    for caso_nome in casos:
        resp = copy.deepcopy(h.carregar("python", caso_nome)["resposta"])
        if isinstance(resp.get("identity"), dict) and resp["identity"].get("status") == "verified":
            resp["identity"]["status"] = "not_found"
        respostas.append(resp)

    erros = conferir_literais_observados("verificar_citacao", spec, respostas, DEPRECATED)
    assert any("verified" in e and "não foi observado" in e for e in erros), (
        f"Esperava reprovação por retirada de literal exercitado 'verified', obteve: {erros}"
    )


def test_contrato_consumidor_freoa_nao_exercitados_valido():
    """Garante que freoa_nao_exercitados.json é exato, válido contra freoa.json e preserva a regra do D5."""
    contrato_consumidor = json.loads(FREOA_JSON.read_text(encoding="utf-8"))
    nao_exercitados = json.loads(FREOA_NAO_EXERCITADOS_JSON.read_text(encoding="utf-8"))
    assert isinstance(nao_exercitados, list)
    # IL.0-R, C12: 23 -> 19 (quatro literais de `vigencia.status` passaram a ser exercitados ou saíram do contrato,
    # e `ambiguous` ganhou motivo próprio). Rodada 2: sete casos novos exercitam cinco literais; entram cinco variantes
    # legítimas que só testes dedicados provocam (lista exata: 19). Alteração do arquivo do consumidor sujeita a auditoria.
    assert len(nao_exercitados) == 19
    motivos = {"sem caso no harness; cobertura pendente do IL.0b",
               "sem caso no harness; dispositivo ambíguo exige fixture própria (IL.0-R, C12)",
               "sem caso no harness; exige falha forçada da autenticação da evidência (IL.0-R, rodada 2); variante coberta por teste dedicado",
               "sem caso no harness; recusa pelos derivados exige home de versão antiga (IL.0-R, rodada 2); variante coberta por teste dedicado",
               "sem caso no harness; exige fixture própria (IL.0-R, rodada 2); variante coberta por teste dedicado"}
    for item in nao_exercitados:
        assert set(item.keys()) == {"ferramenta", "caminho", "literal", "motivo"}
        assert item["motivo"] in motivos
        ferr = item["ferramenta"]
        cam = item["caminho"]
        lit = item["literal"]
        spec = contrato_consumidor["ferramentas"][ferr]
        assert cam in spec["estados"], f"{cam} não está em estados de {ferr}"
        assert lit in spec["estados"][cam], f"{lit} não está em estados de {ferr}:{cam}"


def test_gate_vigencia_status_publicado_esta_no_contrato_do_consumidor():
    """IL.0-R, C12: os literais que `obter_dispositivo` publica (congelados) estão em `vigencia.status` do consumidor."""
    spec = json.loads(FREOA_JSON.read_text(encoding="utf-8"))["ferramentas"]["obter_dispositivo"]
    casos = ("obter_dispositivo", "obter_dispositivo_revogado_corrente", "obter_dispositivo_nao_existia",
             "obter_dispositivo_historica", "obter_dispositivo_sem_caminho")
    respostas = [h.carregar("python", c)["resposta"] for c in casos]
    for r in respostas[1:]:  # o primeiro é o congelado da 1.2.0, anterior aos eixos de evidência
        assert not validar_resposta_consumidor("obter_dispositivo", spec, r, DEPRECATED), r["status"]
    observados = {r["vigencia"]["status"] for r in respostas if r.get("vigencia")}
    assert {"revogado", "nao_existia", "unknown", "vigente_na_fonte"} <= observados
    assert observados <= set(spec["estados"]["vigencia.status"])
    sem_caminho = h.carregar("python", "obter_dispositivo_sem_caminho")["resposta"]
    assert sem_caminho["caminho"] is None and "vigencia" not in sem_caminho


@pytest.mark.parametrize("literal", ["divergent", "not_found", "verified"])
def test_gate_mutante_literal_nunca_publicado_em_vigencia_reprova(literal):
    """Os literais errados do passe final (`divergent`, `not_found`, `verified`) não voltam em silêncio."""
    spec = copy.deepcopy(json.loads(FREOA_JSON.read_text(encoding="utf-8"))["ferramentas"]["obter_dispositivo"])
    spec["estados"]["vigencia.status"].append(literal)
    casos = ("obter_dispositivo", "obter_dispositivo_revogado_corrente", "obter_dispositivo_nao_existia",
             "obter_dispositivo_historica", "obter_dispositivo_sem_caminho")
    respostas = [h.carregar("python", c)["resposta"] for c in casos]
    erros = conferir_literais_observados("obter_dispositivo", spec, respostas, DEPRECATED)
    assert any(literal in e and "não foi observado" in e for e in erros), erros


def test_gate_mutante_resposta_com_literal_fora_do_contrato_reprova():
    spec = json.loads(FREOA_JSON.read_text(encoding="utf-8"))["ferramentas"]["obter_dispositivo"]
    resp = copy.deepcopy(h.carregar("python", "obter_dispositivo_revogado_corrente")["resposta"])
    spec_antigo = copy.deepcopy(spec)
    spec_antigo["estados"]["vigencia.status"] = ["verified", "vigente_na_fonte", "unknown", "divergent", "not_found",
                                                  "ambiguous"]  # lista errada do passe final
    erros = validar_resposta_consumidor("obter_dispositivo", spec_antigo, resp, DEPRECATED)
    assert any("revogado" in e for e in erros), erros


# ----------------------------------------------------------------------------------------------
# IL.0-R, rodada 2 (C12): todas as variantes legítimas da fachada satisfazem o contrato do consumidor
# ----------------------------------------------------------------------------------------------

def _servicos_dos_adaptadores(ambiente):
    return [ambiente["python"], ambiente["rest"].app.state.verifica]  # o MCP compartilha o serviço do Python


def _spec(ferramenta):
    return json.loads(FREOA_JSON.read_text(encoding="utf-8"))["ferramentas"][ferramenta]


def _falha_de_autenticacao_so_na_finalizacao(monkeypatch):
    import sys

    from freoa_verifica.service import Verifica
    from freoa_verifica.verify import SourceUnavailable

    original = Verifica._authenticate_capture

    def seletivo(self, capture_id):
        f = sys._getframe(1)
        while f is not None:
            if f.f_code.co_name == "_finalizar":
                raise SourceUnavailable("EVIDENCIA_CORROMPIDA")
            f = f.f_back
        return original(self, capture_id)

    monkeypatch.setattr(Verifica, "_authenticate_capture", seletivo)


@pytest.mark.parametrize("adaptador", h.ADAPTADORES)
def test_c12_obter_dispositivo_variantes_ambigua_unknown_e_unavailable(ambiente, monkeypatch, adaptador):
    import dataclasses

    from freoa_verifica.service import Verifica
    from freoa_verifica.verify import SourceUnavailable

    rw = next(iter(ambiente["python"]._resolver.works.values()))
    args = {"citacao": h.CITACAO_LSA}
    spec = _spec("obter_dispositivo")
    for esperado, preparar in (
        ("ambigua", lambda m: m.setattr(Verifica, "_resolve", lambda self, *a, **k: [rw, rw])),
        ("unknown", lambda m: m.setattr(
            Verifica, "_resolve", lambda self, *a, **k: dataclasses.replace(rw, persisted_incomplete=True))),
        ("unavailable", lambda m: m.setattr(
            Verifica, "_authenticate_output",
            lambda self, valor: (_ for _ in ()).throw(SourceUnavailable("EVIDENCIA_CORROMPIDA")))),
    ):
        with monkeypatch.context() as m:
            preparar(m)
            resp = _responder(ambiente, adaptador, "obter_dispositivo", args)
        assert resp["status"] == esperado, (adaptador, resp)
        assert resp["fundamento_temporal"] is None and resp["correspondencia_textual"] is None
        assert not validar_resposta_consumidor("obter_dispositivo", spec, resp, DEPRECATED), (adaptador, esperado)


@pytest.mark.parametrize("adaptador", h.ADAPTADORES)
def test_c12_verificar_citacao_rebaixamento_final_publica_unavailable(ambiente, monkeypatch, adaptador):
    spec = _spec("verificar_citacao")
    with monkeypatch.context() as m:
        _falha_de_autenticacao_so_na_finalizacao(m)
        resp = _responder(ambiente, adaptador, "verificar_citacao",
                          {"citacao": h.CITACAO_LSA, "trecho": h.TRECHO_LSA})
    assert resp["identity"]["status"] == "unavailable" and resp["text"]["status"] == "unavailable"
    assert resp["correspondencia_textual"] is None
    erros = validar_resposta_consumidor("verificar_citacao", spec, resp, DEPRECATED)
    assert not erros, (adaptador, erros)
    # mutante: o contrato anterior (sem `unavailable` em `text.status`) reprova a variante legítima
    antigo = copy.deepcopy(spec)
    antigo["estados"]["text.status"] = ["verified", "divergent", "not_assessed", "unknown"]
    assert any("text.status" in e and "unavailable" in e for e in validar_resposta_consumidor(
        "verificar_citacao", antigo, resp, DEPRECATED))


@pytest.mark.parametrize("adaptador", h.ADAPTADORES)
def test_c12_run_id_nulo_no_modo_somente_leitura_satisfaz_o_contrato(ambiente, monkeypatch, adaptador):
    for svc in _servicos_dos_adaptadores(ambiente):
        monkeypatch.setattr(svc, "_read_only", True)
    spec = _spec("verificar_citacao")
    resp = _responder(ambiente, adaptador, "verificar_citacao", {"citacao": h.CITACAO_LSA, "trecho": h.TRECHO_LSA})
    assert resp["run_id"] is None and resp["registro"] == {"gravado": False, "motivo": "somente_leitura"}
    assert not validar_resposta_consumidor("verificar_citacao", spec, resp, DEPRECATED), adaptador
    antigo = copy.deepcopy(spec)
    antigo["caminhos"]["run_id"] = "string"
    assert any("run_id" in e for e in validar_resposta_consumidor("verificar_citacao", antigo, resp, DEPRECATED))


@pytest.mark.parametrize("adaptador", h.ADAPTADORES)
def test_c12_recusa_pelos_derivados_satisfaz_o_contrato(ambiente, monkeypatch, adaptador):
    from freoa_verifica import service as modulo

    monkeypatch.setattr(modulo._derivados, "compativel", lambda conn: False)
    vc = _responder(ambiente, adaptador, "verificar_citacao", {"citacao": h.CITACAO_LSA, "trecho": h.TRECHO_LSA})
    od = _responder(ambiente, adaptador, "obter_dispositivo", {"citacao": h.CITACAO_LSA})
    assert vc["status"] == "indisponivel" and vc["run_id"] is None
    assert vc["registro"] == {"gravado": False, "motivo": "acervo_desatualizado"}
    assert od["status"] == "indisponivel"
    assert not validar_resposta_consumidor("verificar_citacao", _spec("verificar_citacao"), vc, DEPRECATED), adaptador
    assert not validar_resposta_consumidor("obter_dispositivo", _spec("obter_dispositivo"), od, DEPRECATED), adaptador
    for r in (vc, od):
        assert r["fundamento_temporal"] is None and r["correspondencia_textual"] is None


@pytest.mark.parametrize("adaptador", h.ADAPTADORES)
def test_c12_obter_dispositivo_requer_conferencia_era_rejeitado_pelo_contrato_antigo(ambiente, adaptador):
    resp = _responder(ambiente, adaptador, "obter_dispositivo", {"citacao": "Lei 6.404, art. 254-A"})
    assert resp["status"] == "requer_conferencia"
    spec = _spec("obter_dispositivo")
    assert not validar_resposta_consumidor("obter_dispositivo", spec, resp, DEPRECATED)
    antigo = copy.deepcopy(spec)
    antigo["estados"]["status"] = ["encontrada", "inexistente", "indisponivel", "unknown", "formato_invalido"]
    erros = validar_resposta_consumidor("obter_dispositivo", antigo, resp, DEPRECATED)
    assert any("requer_conferencia" in e for e in erros), erros


def test_c12_todo_literal_de_obter_dispositivo_status_e_exercitado_ou_declarado():
    """Lista exata: o que o harness não exercita está em `freoa_nao_exercitados.json`, com motivo e teste dedicado."""
    spec = _spec("obter_dispositivo")["estados"]["status"]
    nao = {i["literal"] for i in json.loads(FREOA_NAO_EXERCITADOS_JSON.read_text(encoding="utf-8"))
           if i["ferramenta"] == "obter_dispositivo" and i["caminho"] == "status"}
    observados = {h.carregar("python", c[0])["resposta"]["status"] for c in h.CASOS if c[1] == "obter_dispositivo"}
    assert set(spec) == observados | nao and not (observados & nao)
    assert nao == {"unknown", "ambigua", "unavailable"}
