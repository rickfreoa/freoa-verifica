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
                   ("planalto_acervo", "planalto", "planalto")}


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


def test_estado_diferente_de_nao_apurada_exige_relatorio_e_versao_por_hash():
    d = _dados()
    ruim = copy.deepcopy(d)
    ruim["rotas"][0]["capacidades"]["remissoes"].update(estado="aprovada")
    assert any("sem relatório" in e for e in q.validar(ruim))
    ruim["rotas"][0]["capacidades"]["remissoes"].update(versao="1.4.0a3", relatorio="relatorios/x.md", relatorio_sha256="abc")
    assert any("sem relatório" in e for e in q.validar(ruim))  # hash que não é SHA-256 não vale
    ruim["rotas"][0]["capacidades"]["remissoes"].update(relatorio_sha256="a" * 64)
    assert q.validar(ruim) == []
    for estado in ("reprovada", "nao_aplicavel"):
        ruim["rotas"][0]["capacidades"]["remissoes"].update(estado=estado, relatorio_sha256=None)
        assert any("sem relatório" in e for e in q.validar(ruim))


def test_estado_fora_do_vocabulario_e_estrutura_invalida_reprovam():
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


def test_carregar_fecha_em_nao_apurada_sem_referencia_verificavel():
    d = _dados()
    d["rotas"][0]["capacidades"]["anexos"].update(estado="aprovada", versao="1.4.0a3")
    d["rotas"][0]["capacidades"]["remissoes"].update(estado="reprovada", versao="1.4.0a3", relatorio="r.md",
                                                     relatorio_sha256="b" * 64)
    rotas = q.carregar(json.dumps(d))
    assert rotas[0]["capacidades"]["anexos"]["estado"] == "nao_apurada"  # afirmação sem hash não é publicada
    assert rotas[0]["capacidades"]["remissoes"]["estado"] == "reprovada"  # com referência completa, valeria
    assert q.carregar("{") == [] and q.carregar("[]") == [] and q.carregar('{"rotas": [{"capacidades": 1}]}') == []


@pytest.mark.repositorio
def test_estado_publicado_so_com_relatorio_do_repositorio_conferido_por_hash():
    """No checkout: todo estado diferente de nao_apurada aponta relatório existente cujo SHA-256 confere."""
    raiz = Path(__file__).resolve().parents[1]
    for r in _dados()["rotas"]:
        for nome, item in r["capacidades"].items():
            if item["estado"] == "nao_apurada":
                continue
            rel = raiz / item["relatorio"]
            assert rel.is_file(), f"{r['rota']}.{nome}: relatório ausente"
            assert hashlib.sha256(rel.read_bytes()).hexdigest() == item["relatorio_sha256"]
