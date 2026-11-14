"""IL.3-a, A3: matriz de capacidades por rota como dado, tudo `nao_apurada` (il3-especificacao A3; emenda IL, seção 6)."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from freoa_verifica import qualificacao as q
from freoa_verifica.connectors.base import registry
from freoa_verifica.service import Verifica


# oráculo escrito à mão (rótulos da emenda IL, seção 6; capacidades (a)-(e) e transversais da seção 5, IL.3)
CAPS_ESPERADAS = {
    "identificacao": "Porta L: identificação",
    "texto_publicado": "Porta L: texto publicado",
    "texto_consolidado_vigente": "Porta L: texto consolidado vigente",
    "redacao_em_data": "Porta L: redação em data",
    "anexos": "Porta L: anexos",
    "remissoes": "Porta L: remissões",
    "vigencia_declarada": "Porta L: vigência declarada",
}
ROTAS_ESPERADAS = {("camara_atualizado", "camara_legin", "camara_atualizado"),
                   ("camara_original", "camara_legin", "camara_original"),
                   ("planalto_acervo", "planalto", "planalto"),
                   ("normas_leg", "normas_leg", "normas_leg")}


def _dados():
    from importlib.resources import files  # o dado do pacote instalado, sem caminho do checkout
    return json.loads(files("freoa_verifica").joinpath("data/qualificacao_rotas.json").read_text(encoding="utf-8"))


def test_dado_cobre_rotas_e_capacidades_todas_nao_apuradas():
    d = _dados()
    assert {(r["rota"], r["fonte"], r["perfil"]) for r in d["rotas"]} == ROTAS_ESPERADAS
    for r in d["rotas"]:
        assert {k: v["rotulo"] for k, v in r["capacidades"].items()} == CAPS_ESPERADAS
        for item in r["capacidades"].values():
            assert item["estado"] == "nao_apurada"
            assert item["versao"] is None and item["relatorio"] is None and item["relatorio_sha256"] is None
    assert q.validar(d) == []


def test_fontes_das_rotas_existem_no_registro():
    assert {r["fonte"] for r in _dados()["rotas"]} <= set(registry())


def test_listar_fontes_expoe_rotas_sem_quebrar_o_bloco_existente(tmp_path):
    s = Verifica(home=tmp_path)
    lf = s.listar_fontes()
    s.close()
    assert len(lf["qualificacao"]) == 6  # o bloco de portas continua o da 0075
    assert {(r["rota"], r["fonte"], r["perfil"]) for r in lf["qualificacao_rotas"]} == ROTAS_ESPERADAS
    por_rotulo = {i["rotulo"]: i for i in lf["qualificacao"] if i["porta"] == "L"}
    assert set(por_rotulo) == {v for k, v in CAPS_ESPERADAS.items() if k not in ("identificacao", "vigencia_declarada")}
    for item in por_rotulo.values():
        assert item["estado"] == "nao_apurada"
        assert {x["rota"] for x in item["rotas"]} == {r[0] for r in ROTAS_ESPERADAS}
        assert all(x["estado"] == "nao_apurada" and x["versao"] is None and x["relatorio_sha256"] is None
                   for x in item["rotas"])
    assert "rotas" not in next(i for i in lf["qualificacao"] if i["porta"] == "stj_1_4_0")


def _relatorio(rota="camara_atualizado", cap="remissoes", versao="1.4.0a3", resultado="aprovada", **troca):
    """Relatório de apuração válido (esquema próprio) para o item (rota, cap); `troca` altera campos para as negativas."""
    rel = {"esquema": q.ESQUEMA_RELATORIO, "rota": rota, "capacidade": cap, "capacidade_porta_l": q.LETRA_DA_CAPACIDADE[cap],
           "versao": versao, "resultado": resultado,
           "executor": {"versao_executor": "1", "qualificante": True, "conjunto": "desenvolvimento",
                        "gerado_em": "2026-11-07T12:00:00Z"},
           "bytes_conferidos": {"conjunto_sha256": "1" * 64, "mutantes_sha256": "2" * 64, "congelamento_sha256": "3" * 64}}
    rel.update(troca)
    return json.dumps(rel, sort_keys=True).encode("utf-8")


def _com_estado(d, estado, dados, caminho="apuracoes/camara-atualizado-remissoes.json", versao="1.4.0a3"):
    """Cópia de `d` com a capacidade (camara_atualizado, remissoes) no estado dado, apontando `dados` como relatório."""
    d = copy.deepcopy(d)
    d["rotas"][0]["capacidades"]["remissoes"].update(estado=estado, versao=versao, relatorio=caminho,
                                                     relatorio_sha256=hashlib.sha256(dados).hexdigest())
    return d, (lambda c: dados if c == caminho else None)


def test_estado_diferente_de_nao_apurada_exige_relatorio_de_apuracao_identificavel():
    d = _dados()
    ruim = copy.deepcopy(d)
    ruim["rotas"][0]["capacidades"]["remissoes"].update(estado="aprovada")
    assert any("sem relatório" in e for e in q.validar(ruim))
    ruim["rotas"][0]["capacidades"]["remissoes"].update(versao="1.4.0a3", relatorio="relatorios/x.md", relatorio_sha256="abc")
    assert any("sem relatório" in e for e in q.validar(ruim))  # hash que não é SHA-256 não vale
    ruim["rotas"][0]["capacidades"]["remissoes"].update(relatorio_sha256="a" * 64)
    assert q.validar(ruim) != []  # hash bem formado de arquivo que não existe nem é relatório de apuração
    assert q.validar(ruim, lambda c: None) != []
    for estado in ("reprovada", "nao_aplicavel"):
        ruim["rotas"][0]["capacidades"]["remissoes"].update(estado=estado, relatorio_sha256=None)
        assert any("sem relatório" in e for e in q.validar(ruim))
    ok, leitor = _com_estado(d, "aprovada", _relatorio())
    assert q.validar(ok, leitor) == []  # só o relatório de apuração coerente promove
    assert q.validar(ok) != []  # sem como ler o relatório, o estado não é demonstrável
    for estado in ("reprovada", "nao_aplicavel"):
        ok, leitor = _com_estado(d, estado, _relatorio(resultado=estado))
        assert q.validar(ok, leitor) == [], estado


def test_b9_arquivo_qualquer_com_hash_real_nao_e_relatorio_de_apuracao():
    """A contraprova do auditor: `relatorio = AGENTS.md` com o hash real do arquivo passava em validar e em carregar."""
    raiz = Path(__file__).resolve().parents[1]
    alvo = raiz / "AGENTS.md"
    if not alvo.exists():
        pytest.skip("exige o checkout")
    dados = alvo.read_bytes()
    d, _ = _com_estado(_dados(), "aprovada", dados, caminho="AGENTS.md")

    def leitor_raiz(c):  # leitor que alcançaria o arquivo, se a regra deixasse
        return (raiz / c).read_bytes()
    erros = q.validar(d, leitor_raiz)
    assert erros and any("fora do esquema" in e or "não é JSON" in e for e in erros)
    assert q.carregar(json.dumps(d), leitor_raiz)[0]["capacidades"]["remissoes"]["estado"] == "nao_apurada"
    # o leitor do pacote nem tenta caminho fora de data/apuracoes
    assert q.leitor_do_pacote("AGENTS.md") is None and q.leitor_do_pacote("../x.json") is None
    assert q.leitor_do_pacote("apuracoes/../qualificacao.json") is None and q.leitor_do_pacote("C:/x.json") is None
    assert q.leitor_do_pacote("apuracoes/inexistente.json") is None
    assert q.carregar(json.dumps(d))[0]["capacidades"]["remissoes"]["estado"] == "nao_apurada"  # leitor padrão


@pytest.mark.parametrize("troca", [
    {"rota": "camara_original"}, {"capacidade": "anexos", "capacidade_porta_l": "d"}, {"capacidade_porta_l": "a"},
    {"versao": "9.9.9"}, {"resultado": "reprovada"}, {"esquema": "outro/1"},
    {"executor": {"versao_executor": "1", "qualificante": False, "conjunto": "desenvolvimento", "gerado_em": "x"}},
    {"executor": {"versao_executor": "1", "qualificante": True, "conjunto": "outro", "gerado_em": "x"}},
    {"executor": "x"}, {"bytes_conferidos": {"conjunto_sha256": "1" * 64}},
    {"bytes_conferidos": {"conjunto_sha256": "1" * 64, "mutantes_sha256": "zz", "congelamento_sha256": "3" * 64}},
    {"bytes_conferidos": {"conjunto_sha256": "0" * 64, "mutantes_sha256": "2" * 64, "congelamento_sha256": "3" * 64}},
    {"extra": 1},
], ids=lambda t: next(iter(t)) + "-" + str(next(iter(t.values())))[:20])
def test_b9_relatorio_incoerente_com_o_item_nao_promove(troca):
    d = _dados()
    dados = _relatorio(**troca)
    ok, leitor = _com_estado(d, "aprovada", dados)
    assert q.validar(ok, leitor) != []
    assert q.carregar(json.dumps(ok), leitor)[0]["capacidades"]["remissoes"]["estado"] == "nao_apurada"


def test_b9_hash_que_nao_confere_com_os_bytes_nao_promove():
    d = _dados()
    ok, leitor = _com_estado(d, "aprovada", _relatorio())
    ok["rotas"][0]["capacidades"]["remissoes"]["relatorio_sha256"] = "f" * 64
    assert any("não conferem" in e for e in q.validar(ok, leitor))
    assert q.carregar(json.dumps(ok), leitor)[0]["capacidades"]["remissoes"]["estado"] == "nao_apurada"
    assert q.validar(ok, lambda c: b"nao e json") != []


def test_b9_relatorio_coerente_promove_so_o_proprio_item():
    d = _dados()
    ok, leitor = _com_estado(d, "aprovada", _relatorio())
    rotas = q.carregar(json.dumps(ok), leitor)
    assert rotas[0]["capacidades"]["remissoes"]["estado"] == "aprovada"
    assert all(i["estado"] == "nao_apurada" for r in rotas for n, i in r["capacidades"].items()
               if not (r["rota"] == "camara_atualizado" and n == "remissoes"))


def test_b9_estado_fora_do_vocabulario_e_estrutura_invalida_reprovam():
    d = _dados()
    ruim = copy.deepcopy(d)
    ruim["rotas"][0]["capacidades"]["anexos"]["estado"] = "suspensa"
    assert any("fora de" in e for e in q.validar(ruim))
    ruim = copy.deepcopy(d)
    del ruim["rotas"][1]["capacidades"]["anexos"]
    assert any("capacidades devem ser" in e for e in q.validar(ruim))
    ruim = copy.deepcopy(d)
    ruim["rotas"][0]["capacidades"]["anexos"]["rotulo"] = "outra coisa"
    assert any("rótulo" in e for e in q.validar(ruim))
    ruim = copy.deepcopy(d)
    ruim["rotas"].append(copy.deepcopy(ruim["rotas"][0]))
    assert any("repetida" in e for e in q.validar(ruim))
    assert q.validar({}) and q.validar({"rotas": []})


def test_b9_carregar_aplica_validar_por_inteiro_e_fecha_sem_levantar():
    """Estrutura incompleta alcançava `anexar_rotas` e falhava por chave ausente; agora fecha em lista vazia."""
    d = _dados()
    assert q.carregar("{") == [] and q.carregar("[]") == [] and q.carregar('{"rotas": [{"capacidades": 1}]}') == []
    incompletos = []
    for mexer in (lambda x: x["rotas"][0]["capacidades"].pop("anexos"),
                  lambda x: x["rotas"][0]["capacidades"]["anexos"].pop("estado"),
                  lambda x: x["rotas"][1].pop("fonte"),
                  lambda x: x["rotas"][0]["capacidades"]["remissoes"].update(rotulo="outro"),
                  lambda x: x["rotas"].append(copy.deepcopy(x["rotas"][0])),
                  lambda x: x["rotas"][2]["capacidades"]["identificacao"].update(extra=1)):
        c = copy.deepcopy(d)
        mexer(c)
        incompletos.append(c)
    itens = [{"porta": "L", "rotulo": "Porta L: remissões", "estado": "nao_apurada"}]
    for c in incompletos:
        assert q.validar(c) != []
        rotas = q.carregar(json.dumps(c))
        assert rotas == []  # nada é publicado
        assert q.anexar_rotas(itens, rotas)[0]["rotas"] == []  # e a exposição não levanta
    # `anexar_rotas` também não levanta com rota ou capacidade ausente em dado que lhe chegue por outro caminho
    parcial = [{"rota": "x", "capacidades": {}}, {"capacidades": None}, "lixo"]
    saida = q.anexar_rotas(itens, parcial)[0]["rotas"]
    assert all(r["estado"] == "nao_apurada" for r in saida)


@pytest.mark.repositorio
def test_estado_publicado_so_com_relatorio_de_apuracao_do_pacote_conferido():
    """No checkout: todo estado diferente de nao_apurada aponta um relatório de apuração de `data/apuracoes/`, de esquema
    próprio, que confere por hash e com a rota, a capacidade, a versão e o resultado do item."""
    raiz = Path(__file__).resolve().parents[1] / "freoa_verifica" / "data"
    for r in _dados()["rotas"]:
        for nome, item in r["capacidades"].items():
            if item["estado"] == "nao_apurada":
                continue
            assert item["relatorio"].startswith(q.PREFIXO_RELATORIOS), f"{r['rota']}.{nome}: fora de data/apuracoes"
            rel = raiz / item["relatorio"]
            assert rel.is_file(), f"{r['rota']}.{nome}: relatório ausente"
            assert q.erros_do_relatorio(r["rota"], nome, item, rel.read_bytes()) == [], f"{r['rota']}.{nome}"


def test_b9_pacote_empacota_relatorios_de_apuracao():
    """O relatório de apuração é dado do pacote: o `pyproject` empacota `data/apuracoes/*.json`."""
    raiz = Path(__file__).resolve().parents[1]
    if not (raiz / "pyproject.toml").exists():
        pytest.skip("exige o checkout")
    assert "data/apuracoes/*.json" in (raiz / "pyproject.toml").read_text(encoding="utf-8")
