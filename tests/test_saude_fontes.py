"""S3: relatório de saúde das fontes (conftest live) e script que mantém a issue viva. Offline, `gh` simulado."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytest_plugins = ["pytester"]
pytestmark = pytest.mark.repositorio

RAIZ = Path(__file__).resolve().parent.parent
if not (RAIZ / "scripts" / "saude_fontes.py").exists():  # job da wheel: sem checkout
    pytest.skip("exige o checkout (scripts/)", allow_module_level=True)
_spec =importlib.util.spec_from_file_location("saude_fontes", RAIZ / "scripts" / "saude_fontes.py")
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


def test_junit_solicitado_e_ausente_sai_3_antes_da_api(tmp_path):
    gh = FakeGh(corpo_de(OK))
    assert rodar(tmp_path, relatorio(OK), gh, "--junit", str(tmp_path / "ausente.xml")) == 3
    assert gh.chamadas == []


def _com_testes(fonte_estado, *testes_estados):
    rel = relatorio({"bcb": ("ok", None)})
    rel["fontes"]["bcb"]["estado"] = fonte_estado
    rel["fontes"]["bcb"]["testes"] = [{"nome": f"t{i}", "estado": e} for i, e in enumerate(testes_estados)]
    return rel


@pytest.mark.parametrize("rel", [
    relatorio({"bcb": ("not_run", None)}),                 # completa: true com fonte not_run
    _com_testes("ok", "ok", "not_run"),                    # teste sem fase final
    _com_testes("ok", "ok", "regressao"),                  # fonte verde com teste vermelho (B2-06)
    _com_testes("ok", "ok", None),                         # teste sem estado
], ids=["fonte_not_run", "teste_not_run", "fonte_ignora_teste", "teste_sem_estado"])
def test_contradicoes_do_relatorio_saem_3_sem_chamar_a_api(tmp_path, rel):
    gh = FakeGh(corpo_de(OK))
    assert rel["completa"] is True
    assert rodar(tmp_path, rel, gh) == 3
    assert gh.chamadas == []


def test_relatorio_coerente_com_testes_passa(tmp_path):
    assert rodar(tmp_path, _com_testes("regressao", "ok", "regressao"), FakeGh(corpo_de(OK))) == 1


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


def test_inicio_preenchido_com_conftest_de_subdiretorio(pytester):
    """`pytest_sessionstart` não roda em conftest de subdiretório (carregado na coleta): `inicio` saía `null`.

    Reproduz o layout real (`tests/live/conftest.py` com a execução da raiz) com a cópia literal do conftest.
    """
    from datetime import datetime

    live = pytester.mkdir("live")
    (live / "conftest.py").write_text((RAIZ / "tests" / "live" / "conftest.py").read_text(encoding="utf-8"),
                                      encoding="utf-8")
    pytester.makeini("[pytest]\nmarkers =\n    live: x\n")
    (live / "test_live_bcb.py").write_text(
        "import time\nimport pytest\npytestmark = pytest.mark.live\n"
        "def test_a():\n    time.sleep(0.05)\n",
        encoding="utf-8",
    )
    r = pytester.runpytest("-p", "no:cacheprovider")
    r.assert_outcomes(passed=1)
    rel = json.loads((pytester.path / "saude-fontes.json").read_text(encoding="utf-8"))
    assert rel["inicio"] is not None
    inicio, fim = datetime.fromisoformat(rel["inicio"]), datetime.fromisoformat(rel["fim"])
    assert inicio.tzinfo is not None and inicio < fim
    assert rel["completa"] is True and rel["fontes"]["bcb"]["estado"] == "ok"


# --- B2-08: serialização e estado antigo ----------------------------------------------------

def test_workflow_serializa_as_execucoes_sem_cancelar():
    yml = (RAIZ / ".github" / "workflows" / "fontes-saude.yml").read_text(encoding="utf-8")
    assert "concurrency:" in yml and "group: saude-das-fontes" in yml and "cancel-in-progress: false" in yml


def _rel_em(inicio, run_id, fontes):
    return {**relatorio(fontes), "inicio": inicio, "run_id": run_id}


def test_estado_grava_run_id_e_inicio(tmp_path):
    gh = FakeGh()
    rodar(tmp_path, _rel_em("2026-10-19T09:00:00+00:00", "11", OK), gh)
    assert sf._execucao(gh.issue["body"]) == {"inicio": "2026-10-19T09:00:00+00:00", "run_id": "11"}


def test_execucao_antiga_nao_apaga_a_regressao_da_mais_nova(tmp_path):
    nova = _rel_em("2026-10-19T10:00:00+00:00", "12", REGRESSAO)
    gh = FakeGh(sf.corpo(nova, sf.conjunto(nova)))
    antigo = gh.issue["body"]
    # A (mais antiga, sucesso) chega depois de B (mais nova, regressão) ter gravado
    assert rodar(tmp_path, _rel_em("2026-10-19T09:00:00+00:00", "11", OK), gh) == 0
    assert gh.escritas() == [] and gh.issue["body"] == antigo and gh.comentarios == []
    assert sf._anterior(gh.issue["body"]) == sf.conjunto(nova)


def test_execucao_mais_nova_substitui_a_antiga_e_corpo_sem_marcador_e_sobrescrito(tmp_path):
    antiga = _rel_em("2026-10-19T09:00:00+00:00", "11", OK)
    gh = FakeGh(sf.corpo(antiga, sf.conjunto(antiga)))
    assert rodar(tmp_path, _rel_em("2026-10-19T10:00:00+00:00", "12", REGRESSAO), gh) == 1
    assert sf._execucao(gh.issue["body"])["run_id"] == "12" and len(gh.comentarios) == 1
    legado = FakeGh(corpo_de(OK).split("<!-- execucao")[0])  # corpo da versão anterior: sem marcador
    assert rodar(tmp_path, _rel_em("2026-10-19T10:00:00+00:00", "12", OK), legado) == 0
    assert sf._execucao(legado.issue["body"])["run_id"] == "12"
