"""S3: relatório de saúde das fontes (conftest live) e script que mantém a issue viva. Offline, `gh` simulado."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytest_plugins = ["pytester"]

RAIZ = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("saude_fontes", RAIZ / "scripts" / "saude_fontes.py")
sf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sf)

REPO = "o/r"


class FakeGh:
    """Simula a API de issues."""

    def __init__(self, body=None, falha_em=None):
        self.issue = None if body is None else {"number": 7, "body": body}
        self.comentarios, self.chamadas, self.falha_em = [], [], falha_em

    def __call__(self, metodo, caminho, corpo=None):
        self.chamadas.append((metodo, caminho))
        if self.falha_em == metodo:
            raise sf.GhErro("api fora")
        if metodo == "GET" and "?" in caminho:
            return [dict(self.issue)] if self.issue else []
        if metodo == "GET":
            return dict(self.issue)
        if metodo == "POST" and caminho.endswith("/comments"):
            self.comentarios.append(corpo["body"])
        elif metodo == "POST":
            assert corpo["labels"] == [sf.ROTULO]
            self.issue = {"number": 7, "body": corpo["body"]}
        elif metodo == "PATCH":
            self.issue["body"] = corpo["body"]

    def escritas(self):
        return [c for c in self.chamadas if c[0] != "GET"]


def relatorio(fontes, completa=True):
    return {"commit": "abc", "inicio": "t0", "fim": "t1", "completa": completa, "fontes": {
        n: {"estado": e, "categoria": c, "motivo": "m", "testes": []} for n, (e, c) in fontes.items()}}


def rodar(tmp_path, rel, gh, *extra, texto=None):
    arq = tmp_path / "saude-fontes.json"
    if texto is not None:
        arq.write_text(texto, encoding="utf-8")
    elif rel is not None:
        arq.write_text(json.dumps(rel), encoding="utf-8")
    return sf.main(["--json", str(arq), "--issue", "--repo", REPO, *extra], gh=gh)


OK = {"bcb": ("ok", None), "tjdft": ("ok", None)}
AMBIENTAL = {"bcb": ("ok", None), "tjdft": ("unavailable", "ambiental_desafio")}
REGRESSAO = {"bcb": ("regressao", "regressao"), "tjdft": ("ok", None)}


def corpo_de(fontes):
    r = relatorio(fontes)
    return sf.corpo(r, sf.conjunto(r))


def test_regressao_sai_1_e_comenta(tmp_path):
    gh = FakeGh(corpo_de(OK))
    assert rodar(tmp_path, relatorio(REGRESSAO), gh) == 1
    assert len(gh.comentarios) == 1 and "bcb" in gh.comentarios[0]
    assert sf.conjunto(relatorio(REGRESSAO)) == sf._anterior(gh.issue["body"])


def test_recusa_identificado_sai_1(tmp_path):
    rel = relatorio({"stf": ("unavailable", "recusa_identificado")})
    assert rodar(tmp_path, rel, FakeGh()) == 1


def test_xfail_ambiental_sai_0_sem_comentario_se_nada_mudou(tmp_path):
    gh = FakeGh(corpo_de(AMBIENTAL))
    assert rodar(tmp_path, relatorio(AMBIENTAL), gh) == 0
    assert gh.comentarios == []
    assert [c[0] for c in gh.escritas()] == ["PATCH"]  # corpo reescrito, sem notificar


def test_issue_inexistente_e_criada_sem_comentario(tmp_path):
    gh = FakeGh()
    assert rodar(tmp_path, relatorio(OK), gh) == 0
    assert gh.issue and gh.comentarios == []


@pytest.mark.parametrize("modo", ["ausente", "truncado", "incompleta", "vazio", "junit_trunc"])
def test_execucao_incompleta_sai_3_e_nao_toca_a_issue(tmp_path, modo):
    gh = FakeGh(corpo_de(OK))
    extra = ()
    if modo == "ausente":
        rel, texto = None, None
    elif modo == "truncado":
        rel, texto = None, json.dumps(relatorio(OK))[:40]
    elif modo == "incompleta":
        rel, texto = relatorio(OK, completa=False), None
    elif modo == "vazio":
        rel, texto = relatorio({}), None
    else:
        junit = tmp_path / "live.xml"
        junit.write_text("<testsuites><testsuite", encoding="utf-8")
        rel, texto, extra = relatorio(OK), None, ("--junit", str(junit))
    assert rodar(tmp_path, rel, gh, *extra, texto=texto) == 3
    assert gh.chamadas == []


def test_junit_com_falha_que_o_json_nao_registra_sai_3(tmp_path):
    junit = tmp_path / "live.xml"
    junit.write_text('<testsuites><testsuite tests="2" failures="1" errors="0"/></testsuites>', encoding="utf-8")
    gh = FakeGh(corpo_de(OK))
    assert rodar(tmp_path, relatorio(OK), gh, "--junit", str(junit)) == 3
    assert gh.chamadas == []


@pytest.mark.parametrize("falha", ["GET", "POST", "PATCH"])
def test_falha_da_api_sai_2_sem_perder_estado(tmp_path, falha):
    antigo = corpo_de(OK)
    gh = FakeGh(antigo, falha_em=falha)
    assert rodar(tmp_path, relatorio(REGRESSAO), gh) == 2
    assert gh.issue["body"] == antigo


def test_mudanca_de_conjunto_gera_um_comentario_e_igual_nenhum(tmp_path):
    gh = FakeGh(corpo_de(OK))
    rodar(tmp_path, relatorio(AMBIENTAL), gh)
    assert len(gh.comentarios) == 1
    rodar(tmp_path, relatorio(AMBIENTAL), gh)
    assert len(gh.comentarios) == 1  # mesmo conjunto: nenhum novo


def test_motivo_diferente_com_mesmo_conjunto_nao_comenta(tmp_path):
    gh = FakeGh(corpo_de(AMBIENTAL))
    rel = relatorio(AMBIENTAL)
    rel["fontes"]["tjdft"]["motivo"] = "outro"
    rodar(tmp_path, rel, gh)
    assert gh.comentarios == [] and "outro" in gh.issue["body"]


def test_execucao_concorrente_a_segunda_rele_o_corpo_antes_de_escrever(tmp_path):
    gh = FakeGh(corpo_de(OK))
    novo = relatorio(AMBIENTAL)

    gets = []

    def corrida(metodo, caminho, corpo=None):
        gets.append(metodo)
        r = gh(metodo, caminho, corpo)
        if metodo == "GET" and "?" in caminho:  # a outra execução grava logo após a listagem
            gh.issue["body"] = sf.corpo(novo, sf.conjunto(novo))
        return r

    # Sem a releitura comentaria (OK -> AMBIENTAL); com ela vê o estado já gravado e não comenta.
    assert rodar(tmp_path, novo, corrida) == 0
    assert gets.count("GET") == 2  # listagem + releitura
    assert gh.comentarios == []


# --- conftest live: relatório gravado pela sessão --------------------------------------------

_CONFTEST = "from tests.live.conftest import *  # noqa: F401,F403\n"


def _sessao(pytester, corpos, extra=()):
    pytester.makeconftest(_CONFTEST)
    pytester.makeini("[pytest]\nmarkers =\n    live: x\n")
    pytester.makepyfile(test_live_bcb=(
        "import pytest\nfrom freoa_verifica.connectors.base import Unavailable\npytestmark = pytest.mark.live\n"
        + "".join(f"def test_{i}():\n    {c}\n" for i, c in enumerate(corpos))
    ))
    pytester.runpytest("-p", "no:cacheprovider", *extra)
    return json.loads((pytester.path / "saude-fontes.json").read_text(encoding="utf-8"))


def test_conftest_grava_ok_unavailable_e_regressao(pytester):
    amb = "raise Unavailable('http_503', 'fonte_fora', {'status': 503})"
    rel = _sessao(pytester, ["pass", amb])
    assert rel["completa"] is True and set(rel) >= {"commit", "inicio", "fim", "fontes"}
    f = rel["fontes"]["bcb"]
    assert (f["estado"], f["categoria"], f["motivo"]) == ("unavailable", "fonte_fora", "http_503")
    assert [t["estado"] for t in f["testes"]] == ["ok", "unavailable"]

    red = _sessao(pytester, ["raise Unavailable('http_403', 'recusa_identificado', {'status': 403})"])
    assert red["fontes"]["bcb"]["estado"] == "regressao"
    assert red["fontes"]["bcb"]["categoria"] == "recusa_identificado"


def test_conftest_skip_comum_e_sessao_interrompida_nao_sao_completas(pytester):
    rel = _sessao(pytester, ["pytest.skip('x')"])
    assert rel["completa"] is False and rel["fontes"]["bcb"]["estado"] == "not_run"
    int_ = _sessao(pytester, ["assert False", "pass"], extra=("-x",))
    assert int_["completa"] is False  # o segundo teste não rodou
    assert int_["fontes"]["bcb"]["estado"] == "regressao"
