"""I1.5: manifesto de aceite (validar, registrar, item, reducao, rotulo, fechar), invariantes a a e,
recibos tipados por etapa, caminhos confinados, escrita atômica e o manifesto do repositório. Os testes
carregam o script do checkout; por isso o módulo é `repositorio` (fora da wheel instalada, o CI nunca os
executaria, já que a wheel não traz scripts/). A raiz do repositório é apontada para um diretório temporário
pelo parâmetro interno `_raiz` de `main`, nunca pela CLI."""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.repositorio

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ / "scripts" / "manifesto_aceite.py"
MANIFESTO_REPO = RAIZ / "release" / "acceptance_manifest.json"
SCHEMA = RAIZ / "release" / "acceptance_manifest.schema.json"
AUDITORIA = RAIZ / "docs" / "auditoria" / "1.4.0" / "i15-manifesto.md"
if not SCRIPT.exists():  # job da wheel: sem checkout
    pytest.skip("exige o checkout (scripts/)", allow_module_level=True)
_spec = importlib.util.spec_from_file_location("manifesto_aceite", SCRIPT)
ma = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ma)

ETAPAS = ma.ETAPAS
DATA = "2026-10-28T00:00:00+00:00"
C_TESTE = "a" * 40  # commit testado e commitado
C_MERGE = "b" * 40
C_LISTA = "c" * 40
SHA_WHEEL = "1" * 64
SHA_SDIST = "2" * 64
SHA_SNAP = "3" * 64
SHA_PACOTE = "4" * 64
URL_RUN = f"{ma.REPO_URL}/actions/runs/123456"
TAG = "v1.4.0a1"
URL_REL = f"{ma.REPO_URL}/releases/tag/{TAG}"
ALERTA = "fonte_fora: TJAP sem resposta em 28/10"

SPEC = "docs/spec.md"
RELATORIO = "docs/relatorio.md"
SAUDE = "docs/saude-fontes.json"
JOBS_OK = [{"nome": n, "conclusao": "success"} for n in ma.JOBS_CI]
AMBIENTE = {"so": "Windows 11", "python": "3.13.1", "pais_ip": "BR"}
# Formato real de tests/live/conftest.py: completa e fontes[fonte].testes[].
SAUDE_OK = {
    "commit": C_TESTE, "run_id": None, "inicio": DATA, "fim": DATA, "completa": True,
    "fontes": {
        "stj": {"estado": "ok", "categoria": None, "motivo": None, "testes": [
            {"nome": "tests/live/test_live_stj.py::test_a", "estado": "ok", "categoria": None, "motivo": None}]},
        "tjap": {"estado": "unavailable", "categoria": "fonte_fora", "motivo": "fora", "testes": [
            {"nome": "tests/live/test_live_tjap.py::test_b", "estado": "unavailable",
             "categoria": "fonte_fora", "motivo": "fora"}]},
    },
}
PARECER = "docs/auditoria/1.4.0/parecer-r2.md"
REGISTRO = "docs/auditoria/1.4.0/pr10-reducao-escopo.md"


def _ev(tipo, **campos):
    return {"tipo": tipo, "campos": campos, "data": DATA}


def _etapa(estado="pendente", evidencias=None, nota=""):
    return {"estado": estado, "evidencias": evidencias or [], "nota": nota}


def _etapas_padrao():
    return {n: _etapa() for n in ETAPAS}


def _itens(id_="I1", padrao="pendente", **estados):
    """Itens do catálogo do plano para o incremento; `estados` troca o estado de itens (I1_2="adiado")."""
    trocas = {k.replace("_", "."): v for k, v in estados.items()}
    return [{"id": i, "estado": trocas.get(i, padrao), "nota": ""} for i in ma.CATALOGO_PLANO[id_]]


def _inc(id_="I1", estado="aberto", rotulo=None, itens=None, reducoes=None, etapas=None):
    return {
        "id": id_, "versao": "1.4.0a1", "estado": estado, "rotulo": rotulo,
        "itens": itens if itens is not None else _itens(id_),
        "etapas": etapas if etapas is not None else _etapas_padrao(),
        "reducoes_de_escopo": reducoes or [],
    }


def _manifesto(incrementos=None, excecoes=None):
    return {
        "plano": "1.4.0", "atualizado_em": DATA,
        "incrementos": incrementos if incrementos is not None else [_inc()],
        "excecoes": excecoes or [],
    }


def _sha_arquivo(raiz, rel):
    return hashlib.sha256((raiz / rel).read_bytes()).hexdigest()


def _bateria(raiz, commit, **trocas):
    campos = {
        "relatorio": RELATORIO, "sha256": _sha_arquivo(raiz, RELATORIO), "commit": commit,
        "aprovados": 5, "xfail": 1, "falhas": 0, "escopo": ["stj"], "ambiente": dict(AMBIENTE),
        "saude_fontes": SAUDE, "saude_fontes_sha256": _sha_arquivo(raiz, SAUDE),
        "falhas_fora_do_escopo": [],
    }
    campos.update(trocas)
    return _ev("bateria_live", **campos)


def _etapas_validas(raiz):
    return {
        "1_desenvolvimento": _etapa("concluida", [_ev("especificacao", especificacao=SPEC, ramo="feat/x")]),
        "2_teste": _etapa("concluida", [
            _ev("run_ci", url=URL_RUN, commit=C_TESTE, conclusao="success", jobs=copy.deepcopy(JOBS_OK)),
            _bateria(raiz, C_TESTE),
        ]),
        "3_commit": _etapa("concluida", [_ev("commit", commit=C_TESTE)]),
        "4_incorporacao": _etapa("concluida", [
            _ev("parecer", parecer=PARECER, sha256=_sha_arquivo(raiz, PARECER), commit_auditado=C_TESTE),
            _ev("merge", commit=C_MERGE),
        ]),
        "5_publicacao": _etapa("concluida", [
            _ev("tag", tag=TAG, commit=C_MERGE),
            _ev("release", url=URL_REL, attestation_verificada=True, sha256_wheel=SHA_WHEEL, sha256_sdist=SHA_SDIST),
            _ev("pypi", versao="1.4.0a1", sha256_wheel=SHA_WHEEL, sha256_sdist=SHA_SDIST),
        ]),
        "6_distribuicao": _etapa("concluida", [
            _ev("snapshot", pacotes=[{"nome": "nucleo", "sha256": SHA_SNAP}, {"nome": "stj", "sha256": SHA_PACOTE}],
                bateria_s4="aprovada", lista_embutida_commit=C_LISTA)]),
        "7_instalacao": _etapa("concluida", [
            _ev("instalacao", concluida=True, commit=C_MERGE, attestation_verificada=True,
                digests=[SHA_SNAP, SHA_PACOTE])]),
        "8_execucao": _etapa("concluida", [
            _ev("doctor", ok=True, alertas=[ALERTA]),
            _bateria(raiz, C_MERGE),
        ]),
    }


def _concluido(raiz, estado="aberto"):
    return _inc(estado=estado, itens=_itens(padrao="concluido"), etapas=_etapas_validas(raiz))


def _muda(raiz, etapa, tipo, campo, valor, estado="aberto"):
    """Incremento válido com um campo de recibo trocado (ou removido, quando valor é ..., a evidência)."""
    inc = _concluido(raiz, estado)
    evs = inc["etapas"][etapa]["evidencias"]
    ev = next(e for e in evs if e["tipo"] == tipo)
    if valor is ...:
        evs.remove(ev)
    else:
        ev["campos"][campo] = valor
    return inc


class Repo:
    def __init__(self, raiz):
        self.raiz = raiz
        (raiz / SAUDE).parent.mkdir(parents=True, exist_ok=True)
        (raiz / SAUDE).write_text(json.dumps(SAUDE_OK, ensure_ascii=False, indent=2), encoding="utf-8")
        for rel, texto in ((SPEC, "especificação\n"), (RELATORIO, "relatório\n"),
                           (PARECER, "Achados: nenhum.\nSEM BLOQUEADOR\n"), (REGISTRO, "redução\n")):
            arq = raiz / rel
            arq.parent.mkdir(parents=True, exist_ok=True)
            arq.write_text(texto, encoding="utf-8")
        self.manifesto = raiz / "release" / "acceptance_manifest.json"

    def cria(self, m=None):
        self.manifesto.parent.mkdir(parents=True, exist_ok=True)
        self.manifesto.write_text(
            json.dumps(m if m is not None else _manifesto(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        return self.manifesto

    def run(self, *args):
        return ma.main(list(args), _raiz=self.raiz)

    def dados(self):
        return json.loads(self.manifesto.read_text(encoding="utf-8"))

    def erros(self, m):
        return ma.erros_do_manifesto(m, self.raiz)


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path)


def _erros_etapa(repo, etapa, nome="1_desenvolvimento"):
    return repo.erros(_manifesto([_inc(etapas={**_etapas_padrao(), nome: etapa})]))


# ---------------------------------------------------------------- estrutura e validar


def test_manifesto_minimo_e_valido(repo):
    assert repo.erros(_manifesto()) == []


def test_manifesto_totalmente_concluido_e_valido(repo):
    assert repo.erros(_manifesto([_concluido(repo.raiz, "concluido")])) == []


def test_validar_retorna_zero_e_imprime_resumo(repo, capsys):
    repo.cria()
    assert repo.run("validar") == 0
    assert "manifesto válido: 1 incrementos, 0 exceções" in capsys.readouterr().out


def test_arquivo_ausente_sai_com_1(repo, capsys):
    assert repo.run("--manifesto", "release/nao-existe.json", "validar") == 1
    assert "manifesto não encontrado" in capsys.readouterr().err


def test_json_invalido_sai_com_1(repo, capsys):
    p = repo.raiz / "x.json"
    p.write_text("{", encoding="utf-8")
    assert repo.run("--manifesto", "x.json", "validar") == 1
    assert "JSON inválido" in capsys.readouterr().err


def test_uso_invalido_sai_com_2(repo):
    repo.cria()
    with pytest.raises(SystemExit) as exc:
        repo.run("item", "--incremento", "I1")
    assert exc.value.code == 2


def test_campo_sem_igual_e_erro_de_uso(repo):
    repo.cria()
    with pytest.raises(SystemExit) as exc:
        repo.run("registrar", "--incremento", "I1", "--etapa", "3_commit", "--tipo", "commit", "--campo", "commit")
    assert exc.value.code == 2


@pytest.mark.parametrize("campo", ["plano", "atualizado_em", "incrementos", "excecoes"])
def test_campo_raiz_ausente_e_reprovado(repo, campo):
    m = _manifesto()
    del m[campo]
    assert any(campo in e for e in repo.erros(m))


def test_campo_extra_e_reprovado(repo):
    m = _manifesto()
    m["extra"] = 1
    assert any("não previsto 'extra'" in e for e in repo.erros(m))


def test_estado_de_incremento_invalido(repo):
    assert any("não é valor válido" in e for e in repo.erros(_manifesto([_inc(estado="feito")])))


# ---------------------------------------------------------------- B1: nao_aplicavel não existe


def test_b1_oito_etapas_nao_aplicavel_com_nota_nao_fecham(repo, capsys):
    """Cenário do parecer: oito etapas `nao_aplicavel` com nota permitiam `fechar` → concluido."""
    etapas = {n: _etapa("nao_aplicavel", nota="não se aplica") for n in ETAPAS}
    repo.cria(_manifesto([_inc(etapas=etapas)]))
    assert repo.run("fechar", "--incremento", "I1") == 1
    assert "'nao_aplicavel' não é valor válido" in capsys.readouterr().err
    assert repo.dados()["incrementos"][0]["estado"] == "aberto"


def test_b1_estado_de_etapa_so_pendente_ou_concluida():
    assert ma.ESTADOS_ETAPA == ("pendente", "concluida")
    assert "nao_aplicavel" not in SCRIPT.read_text(encoding="utf-8")


def test_b1_incremento_concluido_exige_as_oito_etapas_concluidas(repo):
    inc = _concluido(repo.raiz, "concluido")
    inc["etapas"]["8_execucao"] = _etapa()
    assert any("etapa 8_execucao não concluida" in e for e in repo.erros(_manifesto([inc])))


# ---------------------------------------------------------------- invariante a e recibos por etapa


def test_a_concluida_sem_evidencia_e_reprovada(repo):
    assert any("exige evidência 'especificacao'" in e for e in _erros_etapa(repo, _etapa("concluida")))


@pytest.mark.parametrize("nome", ETAPAS)
def test_a_etapa_concluida_exige_cada_tipo_da_etapa(repo, nome):
    inc = _concluido(repo.raiz)
    for tipo in ma.TIPOS_DA_ETAPA[nome]:
        sem = copy.deepcopy(inc)
        sem["etapas"][nome]["evidencias"] = [e for e in sem["etapas"][nome]["evidencias"] if e["tipo"] != tipo]
        assert any(f"exige evidência '{tipo}'" in e for e in repo.erros(_manifesto([sem]))), (nome, tipo)


def test_a_evidencia_de_tipo_alheio_a_etapa_e_reprovada(repo):
    inc = _concluido(repo.raiz)
    inc["etapas"]["3_commit"]["evidencias"].append(_ev("merge", commit=C_MERGE))
    assert any("não pertence a esta etapa" in e for e in repo.erros(_manifesto([inc])))


def test_a_evidencia_repetida_e_reprovada(repo):
    inc = _concluido(repo.raiz)
    inc["etapas"]["3_commit"]["evidencias"].append(_ev("commit", commit=C_TESTE))
    assert any("evidência 'commit' repetida" in e for e in repo.erros(_manifesto([inc])))


def test_a_campo_faltante_ou_extra_no_recibo_e_reprovado(repo):
    inc = _concluido(repo.raiz)
    del inc["etapas"]["3_commit"]["evidencias"][0]["campos"]["commit"]
    inc["etapas"]["1_desenvolvimento"]["evidencias"][0]["campos"]["extra"] = "x"
    erros = repo.erros(_manifesto([inc]))
    assert any("falta o campo 'commit'" in e for e in erros) or any("campos: falta" in e for e in erros)
    assert any("não previsto 'extra'" in e for e in erros)


def test_a_tipo_de_evidencia_fora_da_lista(repo):
    erros = _erros_etapa(repo, _etapa("concluida", [_ev("selfie")]))
    assert any("'selfie' não é valor válido" in e for e in erros)


def test_a_recibos_sao_a_lista_fechada_de_tipos():
    assert set(ma.CAMPOS_POR_TIPO) == {t for ts in ma.TIPOS_DA_ETAPA.values() for t in ts}
    assert "outro" not in ma.TIPOS_EVIDENCIA and "bench" not in ma.TIPOS_EVIDENCIA


# ---------------------------------------------------------------- B3: recibos tipados e igualdades


def test_b3_tipo_outro_nas_etapas_1_a_3_e_reprovado(repo):
    """Cenário do parecer: tipo `outro` com ref livre nas etapas 1 a 3."""
    inc = _concluido(repo.raiz)
    for nome in ("1_desenvolvimento", "2_teste", "3_commit"):
        inc["etapas"][nome]["evidencias"] = [{"tipo": "outro", "campos": {"ref": "x"}, "data": DATA}]
    erros = repo.erros(_manifesto([inc]))
    assert sum("'outro' não é valor válido" in e for e in erros) == 3


@pytest.mark.parametrize(
    ("etapa", "tipo", "campo", "valor", "trecho"),
    [
        ("1_desenvolvimento", "especificacao", "especificacao", "docs/nao-existe.md", "arquivo inexistente"),
        ("1_desenvolvimento", "especificacao", "ramo", "", "texto não vazio"),
        ("2_teste", "run_ci", "url", "https://github.com/outro/repo/actions/runs/1", "actions/runs"),
        ("2_teste", "run_ci", "commit", "abc1234", "40 hex"),
        ("2_teste", "run_ci", "conclusao", "failure", "'success'"),
        ("2_teste", "bateria_live", "relatorio", "docs/nao-existe.md", "arquivo inexistente"),
        ("2_teste", "bateria_live", "commit", "d" * 40, "difere de 2_teste run_ci.commit"),
        ("2_teste", "run_ci", "jobs", "success", "lista de {nome, conclusao}"),
        ("3_commit", "commit", "commit", "d" * 40, "3_commit commit"),
        ("4_incorporacao", "parecer", "commit_auditado", "d" * 40, "commit_auditado"),
        ("4_incorporacao", "parecer", "commit_auditado", "abc", "40 hex"),
        ("4_incorporacao", "merge", "commit", "xyz", "40 hex"),
        ("5_publicacao", "tag", "commit", "d" * 40, "tag.commit"),
        ("5_publicacao", "tag", "tag", "v1.4.0a2", "difere da versão do incremento"),
        ("5_publicacao", "tag", "tag", "1.4.0a1", "vX.Y.Z"),
        ("5_publicacao", "release", "attestation_verificada", False, "true"),
        ("5_publicacao", "release", "attestation_verificada", "true", "true"),
        ("5_publicacao", "release", "url", f"{ma.REPO_URL}/releases/tag/v9.9.9", "não é a da tag"),
        ("5_publicacao", "release", "sha256_wheel", "A" * 64, "64 hex"),
        ("5_publicacao", "pypi", "versao", "1.4.0a2", "difere da versão da tag"),
        ("5_publicacao", "pypi", "sha256_wheel", "9" * 64, "difere de release.sha256_wheel"),
        ("5_publicacao", "pypi", "sha256_sdist", "9" * 64, "difere de release.sha256_sdist"),
        ("6_distribuicao", "snapshot", "pacotes", [{"nome": "nucleo", "sha256": "curto"}], "64 hex"),
        ("6_distribuicao", "snapshot", "pacotes", [], "ao menos um pacote"),
        ("6_distribuicao", "snapshot", "pacotes", [{"nome": "a", "sha256": "1" * 64}, {"nome": "a", "sha256": "2" * 64}],
         "nome de pacote repetido"),
        ("6_distribuicao", "snapshot", "bateria_s4", "reprovada", "'aprovada'"),
        ("6_distribuicao", "snapshot", "bateria_s4", "pendente", "'aprovada'"),
        ("6_distribuicao", "snapshot", "lista_embutida_commit", "", "40 hex"),
        ("7_instalacao", "instalacao", "concluida", False, "true"),
        ("7_instalacao", "instalacao", "commit", C_TESTE, "difere de 4_incorporacao merge.commit"),
        ("7_instalacao", "instalacao", "attestation_verificada", False, "true"),
        ("7_instalacao", "instalacao", "digests", [SHA_SNAP], "difere dos sha256 dos pacotes"),
        ("7_instalacao", "instalacao", "digests", [SHA_SNAP, SHA_PACOTE, "9" * 64], "difere dos sha256 dos pacotes"),
        ("7_instalacao", "instalacao", "digests", ["9" * 64, SHA_PACOTE], "difere dos sha256 dos pacotes"),
        ("7_instalacao", "instalacao", "digests", [], "ao menos um digest"),
        ("8_execucao", "doctor", "ok", False, "true"),
        ("8_execucao", "doctor", "alertas", ["TJAP fora do ar"], "sem categoria de indisponibilidade"),
        ("8_execucao", "doctor", "alertas", ["regressao: algo quebrou"], "sem categoria de indisponibilidade"),
        ("8_execucao", "doctor", "alertas", "fonte_fora: x", "lista de textos"),
        ("8_execucao", "bateria_live", "relatorio", "../fora.md", "escapa da raiz"),
        ("8_execucao", "bateria_live", "commit", C_TESTE, "difere de 4_incorporacao merge.commit"),
    ],
)
def test_b3_cada_campo_do_recibo_e_conferido(repo, etapa, tipo, campo, valor, trecho):
    erros = repo.erros(_manifesto([_muda(repo.raiz, etapa, tipo, campo, valor)]))
    assert any(trecho in e for e in erros), erros


@pytest.mark.parametrize(
    ("etapa", "tipo", "trecho"),
    [
        ("4_incorporacao", "merge", "exige evidência 'merge'"),
        ("5_publicacao", "pypi", "exige evidência 'pypi'"),
        ("2_teste", "run_ci", "exige evidência 'run_ci'"),
        ("2_teste", "bateria_live", "exige evidência 'bateria_live'"),
        ("7_instalacao", "instalacao", "exige evidência 'instalacao'"),
        ("8_execucao", "doctor", "exige evidência 'doctor'"),
    ],
)
def test_b3_evidencia_ausente_reprova_a_etapa_concluida(repo, etapa, tipo, trecho):
    erros = repo.erros(_manifesto([_muda(repo.raiz, etapa, tipo, None, ...)]))
    assert any(trecho in e for e in erros)


def test_b3_pypi_nao_e_dispensada_por_nota(repo):
    """Cenário do parecer: PyPI dispensada por palavra na nota da etapa 5."""
    inc = _muda(repo.raiz, "5_publicacao", "pypi", None, ...)
    inc["etapas"]["5_publicacao"]["nota"] = "PyPI não aplicável: pré-release só no GitHub"
    assert any("exige evidência 'pypi'" in e for e in repo.erros(_manifesto([inc])))


def test_b3_fechar_exige_todos_os_recibos(repo, capsys):
    """Etapas 4 a 7 sem HEAD auditado, merge, attestation, bytes iguais, bateria S4 e instalação concluída:
    o `fechar` recusa e o incremento segue aberto. Erros de formato vêm antes dos de coerência."""
    inc = _concluido(repo.raiz)
    et = inc["etapas"]
    et["4_incorporacao"]["evidencias"] = [e for e in et["4_incorporacao"]["evidencias"] if e["tipo"] == "parecer"]
    et["4_incorporacao"]["evidencias"][0]["campos"]["commit_auditado"] = "e" * 40
    et["5_publicacao"]["evidencias"][2]["campos"]["sha256_wheel"] = "9" * 64
    et["7_instalacao"]["evidencias"][0]["campos"]["digests"] = ["8" * 64]
    repo.cria(_manifesto([inc]))
    assert repo.run("fechar", "--incremento", "I1") == 1
    err = capsys.readouterr().err
    for trecho in ("exige evidência 'merge'", "commit_auditado", "pypi.sha256_wheel", "instalacao.digests"):
        assert trecho in err, trecho

    et["5_publicacao"]["evidencias"][1]["campos"]["attestation_verificada"] = False
    et["6_distribuicao"]["evidencias"][0]["campos"]["bateria_s4"] = "reprovada"
    et["7_instalacao"]["evidencias"][0]["campos"]["concluida"] = False
    repo.cria(_manifesto([inc]))
    assert repo.run("fechar", "--incremento", "I1") == 1
    err = capsys.readouterr().err
    for trecho in ("attestation_verificada", "bateria_s4", "instalacao.campos.concluida"):
        assert trecho in err or trecho.split(".")[-1] in err, trecho
    assert repo.dados()["incrementos"][0]["estado"] == "aberto"


def test_b3_alerta_com_categoria_de_indisponibilidade_e_aceito(repo):
    inc = _muda(repo.raiz, "8_execucao", "doctor", "alertas",
                ["fonte_fora: a", "ambiental_desafio: b", "recusa_identificado: c", "resposta_inesperada: d"])
    assert repo.erros(_manifesto([inc])) == []
    assert repo.erros(_manifesto([_muda(repo.raiz, "8_execucao", "doctor", "alertas", [])])) == []


def test_b3_categorias_de_alerta_estao_entre_as_do_conector():
    from freoa_verifica.connectors.base import CATEGORIAS_INDISPONIBILIDADE

    assert set(ma.CATEGORIAS_ALERTA) <= set(CATEGORIAS_INDISPONIBILIDADE)
    assert set(CATEGORIAS_INDISPONIBILIDADE) - set(ma.CATEGORIAS_ALERTA) == {"regressao"}


# ---------------------------------------------------------------- B2, M1: parecer


def test_b2_parecer_local_com_sem_bloqueador_aprova(repo):
    assert repo.erros(_manifesto([_concluido(repo.raiz)])) == []


@pytest.mark.parametrize("ref", ["https://exemplo.invalido/parecer-r2", "http://x/y.md"])
def test_b2_parecer_por_url_nao_vale_com_qualquer_sha256(repo, ref):
    """Cenário do parecer: URL com qualquer sha256 era aceita."""
    inc = _muda(repo.raiz, "4_incorporacao", "parecer", "parecer", ref)
    inc["etapas"]["4_incorporacao"]["evidencias"][0]["campos"]["sha256"] = "a" * 64
    assert any("parecer" in e and "unidade ou fluxo alternativo" in e for e in repo.erros(_manifesto([inc])))


def test_b2_parecer_inexistente_nao_vale_com_qualquer_sha256(repo):
    """Cenário do parecer: arquivo inexistente com qualquer sha256 era aceito."""
    inc = _muda(repo.raiz, "4_incorporacao", "parecer", "parecer", "docs/auditoria/1.4.0/nao-existe.md")
    inc["etapas"]["4_incorporacao"]["evidencias"][0]["campos"]["sha256"] = "a" * 64
    assert any("arquivo inexistente" in e for e in repo.erros(_manifesto([inc])))


def test_b2_sha256_do_parecer_local_e_reconferido_com_os_bytes(repo):
    """Cenário do parecer: o hash de parecer local não era conferido com os bytes."""
    inc = _muda(repo.raiz, "4_incorporacao", "parecer", "sha256", "a" * 64)
    assert any("sha256 registrado difere do sha256 dos bytes" in e for e in repo.erros(_manifesto([inc])))


def test_b2_parecer_alterado_depois_do_registro_e_reprovado(repo):
    inc = _concluido(repo.raiz)
    assert repo.erros(_manifesto([inc])) == []
    (repo.raiz / PARECER).write_text("SEM BLOQUEADOR\nCOM BLOQUEADOR\nSEM BLOQUEADOR\n", encoding="utf-8")
    assert any("sha256 registrado difere" in e for e in repo.erros(_manifesto([inc])))


@pytest.mark.parametrize(
    "ultima",
    ["COM BLOQUEADOR", "TETO DE 3 RODADAS ATINGIDO", "SEM BLOQUEADOR (ressalvas nao corrigidas)",
     "  SEM BLOQUEADOR", "sem bloqueador"],
)
def test_b_ultima_linha_diferente_de_sem_bloqueador_e_reprovada(repo, ultima):
    (repo.raiz / PARECER).write_text(f"SEM BLOQUEADOR\n{ultima}\n", encoding="utf-8")
    erros = repo.erros(_manifesto([_concluido(repo.raiz)]))
    assert any("a última linha não vazia do parecer não é 'SEM BLOQUEADOR'" in e for e in erros)


def test_b_linhas_vazias_depois_nao_contam_como_ultima(repo):
    (repo.raiz / PARECER).write_text("SEM BLOQUEADOR\nCOM BLOQUEADOR\n\n  \n", encoding="utf-8")
    assert any("não é 'SEM BLOQUEADOR'" in e for e in repo.erros(_manifesto([_concluido(repo.raiz)])))


def test_b_linha_final_com_linhas_vazias_e_espacos_aprova(repo):
    (repo.raiz / PARECER).write_text("x\nSEM BLOQUEADOR   \n\n  \n\n", encoding="utf-8")
    assert repo.erros(_manifesto([_concluido(repo.raiz)])) == []


@pytest.mark.parametrize(
    "dados",
    [
        "\ufeffSEM BLOQUEADOR\n".encode(),
        "\ufeffAchados: nenhum.\r\nSEM BLOQUEADOR\r\n".encode(),
        "\ufeffSEM BLOQUEADOR".encode(),
        b"Achados\rSEM BLOQUEADOR\r",
        "a\r\nSEM BLOQUEADOR \t\r\n\r\n".encode(),
    ],
)
def test_m1_bom_inicial_crlf_e_espacos_finais_nao_reprovam(repo, dados):
    """Cenário do parecer: BOM antes de 'SEM BLOQUEADOR' era rejeitado indevidamente."""
    (repo.raiz / PARECER).write_bytes(dados)
    assert repo.erros(_manifesto([_concluido(repo.raiz)])) == []


def test_m1_bom_no_meio_do_arquivo_nao_e_removido(repo):
    (repo.raiz / PARECER).write_bytes("SEM BLOQUEADOR\n\ufeffSEM BLOQUEADOR\n".encode())
    assert any("não é 'SEM BLOQUEADOR'" in e for e in repo.erros(_manifesto([_concluido(repo.raiz)])))


def test_b_parecer_nao_utf8_e_reprovado(repo):
    (repo.raiz / PARECER).write_bytes(b"\xff\xfe\x00SEM BLOQUEADOR\n")
    assert any("UTF-8" in e for e in repo.erros(_manifesto([_concluido(repo.raiz)])))


def test_registrar_parecer_calcula_o_sha256(repo):
    repo.cria()
    assert repo.run("registrar", "--incremento", "I1", "--etapa", "4_incorporacao", "--tipo", "parecer",
                    "--campo", f"parecer={PARECER}", "--campo", f"commit_auditado={C_TESTE}") == 0
    ev = repo.dados()["incrementos"][0]["etapas"]["4_incorporacao"]["evidencias"][0]
    assert ev["campos"] == {"parecer": PARECER, "sha256": _sha_arquivo(repo.raiz, PARECER),
                            "commit_auditado": C_TESTE}


def test_registrar_parecer_recusa_sha256_informado(repo, capsys):
    repo.cria()
    assert repo.run("registrar", "--incremento", "I1", "--etapa", "4_incorporacao", "--tipo", "parecer",
                    "--campo", f"parecer={PARECER}", "--campo", "sha256=" + "a" * 64,
                    "--campo", f"commit_auditado={C_TESTE}") == 1
    assert "calculado pelo registrar" in capsys.readouterr().err


@pytest.mark.parametrize("ref", ["https://exemplo.invalido/p", "docs/nao-existe.md"])
def test_registrar_parecer_recusa_url_e_inexistente(repo, capsys, ref):
    p = repo.cria()
    antes = p.read_bytes()
    assert repo.run("registrar", "--incremento", "I1", "--etapa", "4_incorporacao", "--tipo", "parecer",
                    "--campo", f"parecer={ref}", "--campo", f"commit_auditado={C_TESTE}") == 1
    assert p.read_bytes() == antes


# ---------------------------------------------------------------- B4: fechar valida sempre


def test_b4_fechar_incremento_concluido_invalido_retorna_1(repo, capsys):
    """Cenário do parecer: `fechar` devolvia 0 para incremento já `concluido` sem validar."""
    inc = _concluido(repo.raiz, "concluido")
    inc["etapas"]["8_execucao"] = _etapa()
    repo.cria(_manifesto([inc]))
    assert repo.run("fechar", "--incremento", "I1") == 1
    assert "etapa 8_execucao não concluida" in capsys.readouterr().err


def test_b4_fechar_concluido_com_parecer_adulterado_retorna_1(repo):
    repo.cria(_manifesto([_concluido(repo.raiz, "concluido")]))
    assert repo.run("fechar", "--incremento", "I1") == 0
    (repo.raiz / PARECER).write_text("COM BLOQUEADOR\n", encoding="utf-8")
    assert repo.run("fechar", "--incremento", "I1") == 1


def test_d_fechar_so_com_invariantes_e_depois_marca_concluido(repo):
    repo.cria(_manifesto([_inc()]))
    assert repo.run("fechar", "--incremento", "I1") == 1
    assert repo.dados()["incrementos"][0]["estado"] == "aberto"

    repo.cria(_manifesto([_concluido(repo.raiz)]))
    assert repo.run("fechar", "--incremento", "I1") == 0
    assert repo.dados()["incrementos"][0]["estado"] == "concluido"
    assert repo.run("fechar", "--incremento", "I1") == 0  # já concluído e válido


def test_fechar_incremento_adiado_e_recusado(repo, capsys):
    repo.cria(_manifesto([_inc(estado="adiado")]))
    assert repo.run("fechar", "--incremento", "I1") == 1
    assert "não pode ser fechado" in capsys.readouterr().err


# ---------------------------------------------------------------- invariante d e B5: reduções


def test_d_incremento_concluido_com_item_pendente_e_reprovado(repo):
    inc = _concluido(repo.raiz, "concluido")
    inc["itens"][1]["estado"] = "pendente"
    assert any("item I1.2 pendente" in e for e in repo.erros(_manifesto([inc])))


def _red(item="I1.2", registro=REGISTRO, **kw):
    return {"item": item, "data": "2026-10-28", "decisao": "D5", "registro": registro, "motivo": "teto", **kw}


def test_b5_reducao_valida_e_aceita(repo):
    inc = _inc(rotulo="1.4.0a1 parcial", itens=_itens(I1_2="reduzido"), reducoes=[_red()])
    assert repo.erros(_manifesto([inc])) == []
    inc["itens"][1]["estado"] = "adiado"
    assert repo.erros(_manifesto([inc])) == []


def test_b5_reducao_de_item_concluido_com_rotulo_nulo_e_reprovada(repo):
    """Cenário do parecer: redução registrada com item `concluido` e rótulo nulo era aceita."""
    inc = _inc(rotulo=None, itens=_itens(I1_2="concluido"), reducoes=[_red()])
    erros = repo.erros(_manifesto([inc]))
    assert any("mas o item está 'concluido'" in e for e in erros)
    assert any("exige rotulo do incremento não nulo" in e for e in erros)


@pytest.mark.parametrize("estado", ["pendente", "concluido"])
def test_b5_reducao_exige_item_reduzido_ou_adiado(repo, estado):
    inc = _inc(rotulo="r", itens=_itens(I1_2=estado), reducoes=[_red()])
    assert any("mas o item está" in e for e in repo.erros(_manifesto([inc])))


def test_b5_registro_inexistente_e_reprovado(repo):
    """Cenário do parecer: registro inexistente passava."""
    inc = _inc(rotulo="r", itens=_itens(I1_2="reduzido"),
               reducoes=[_red(registro="docs/auditoria/1.4.0/nao-existe.md")])
    assert any("registro: arquivo inexistente" in e for e in repo.erros(_manifesto([inc])))


@pytest.mark.parametrize("registro", ["/etc/passwd", "../fora.md", "https://x/y.md", "C:/x.md"])
def test_b5_registro_fora_do_repositorio_e_reprovado(repo, registro):
    inc = _inc(rotulo="r", itens=_itens(I1_2="reduzido"), reducoes=[_red(registro=registro)])
    assert any("registro:" in e for e in repo.erros(_manifesto([inc])))


def test_b5_item_reduzido_exige_entrada_correspondente(repo):
    inc = _inc(rotulo="r", itens=_itens(I1_2="reduzido"))
    assert any("exige entrada em reducoes_de_escopo" in e for e in repo.erros(_manifesto([inc])))


def test_b5_reducao_de_item_inexistente_e_reprovada(repo):
    inc = _inc(rotulo="r", reducoes=[_red(item="I9.9")])
    assert any("item inexistente" in e for e in repo.erros(_manifesto([inc])))


def test_b5_reducao_repetida_e_reprovada(repo):
    inc = _inc(rotulo="r", itens=_itens(I1_2="reduzido"), reducoes=[_red(), _red()])
    assert any("redução repetida" in e for e in repo.erros(_manifesto([inc])))


def test_b5_manifesto_inicial_adia_o_i1_2_e_o_i2_6_incorpora_o_escopo():
    """Cenário do parecer: I1.2 sem redução formal enquanto o I2.6 já incorpora o escopo.

    Estado de fato em 28/10/2026: o PR #10 foi reduzido e, após o passe final com bloqueador, adiado.
    """
    m = json.loads(MANIFESTO_REPO.read_text(encoding="utf-8"))
    i1, i2 = m["incrementos"][0], m["incrementos"][1]
    assert {it["id"]: it["estado"] for it in i1["itens"]}["I1.2"] == "adiado"
    assert i1["reducoes_de_escopo"] == [{
        "item": "I1.2",
        "data": "2026-10-28",
        "decisao": "D5: passe final independente COM BLOQUEADOR sobre o escopo reduzido; I1.2 adiado inteiro para I2.6",
        "registro": "docs/auditoria/1.4.0/pr10-adiamento.md",
        "motivo": i1["reducoes_de_escopo"][0]["motivo"],
    }]
    assert i1["rotulo"] == ("1.4.0a1: sem íntegras do STJ; I1.2 adiado para 1.4.0a2 (I2.6) "
                            "após passe final com bloqueador")
    assert (RAIZ / i1["reducoes_de_escopo"][0]["registro"]).is_file()
    assert (RAIZ / "docs/auditoria/1.4.0/pr10-reducao-escopo.md").is_file()
    assert "I1.2" in next(it for it in i2["itens"] if it["id"] == "I2.6")["nota"]


def test_b5_comando_reducao_marca_item_registra_e_rotula_numa_escrita(repo):
    repo.cria(_manifesto([_inc()]))
    assert repo.run("item", "--incremento", "I1", "--id", "I1.2", "--estado", "reduzido") == 1  # sem redução
    assert repo.run("reducao", "--incremento", "I1", "--item", "I1.2", "--rotulo", "STJ parcial",
                    "--registro", REGISTRO, "--decisao", "D5", "--motivo", "limite de auditoria") == 0
    inc = repo.dados()["incrementos"][0]
    assert inc["rotulo"] == "STJ parcial"
    assert inc["itens"][1]["estado"] == "reduzido"
    assert inc["reducoes_de_escopo"][0]["data"] == dt.datetime.now(dt.timezone.utc).date().isoformat()
    # reenvio substitui a entrada do mesmo item
    assert repo.run("reducao", "--incremento", "I1", "--item", "I1.2", "--estado", "adiado", "--rotulo", "outro",
                    "--registro", REGISTRO, "--decisao", "D5", "--motivo", "m2") == 0
    inc = repo.dados()["incrementos"][0]
    assert len(inc["reducoes_de_escopo"]) == 1 and inc["itens"][1]["estado"] == "adiado"


def test_b5_comando_reducao_com_registro_inexistente_nao_grava(repo):
    p = repo.cria(_manifesto([_inc()]))
    antes = p.read_bytes()
    assert repo.run("reducao", "--incremento", "I1", "--item", "I1.2", "--rotulo", "r",
                    "--registro", "docs/nao-existe.md", "--decisao", "D5", "--motivo", "m") == 1
    assert p.read_bytes() == antes


def test_b5_voltar_item_a_pendente_com_reducao_registrada_e_recusado(repo):
    repo.cria(_manifesto([_inc()]))
    assert repo.run("reducao", "--incremento", "I1", "--item", "I1.2", "--rotulo", "r",
                    "--registro", REGISTRO, "--decisao", "D5", "--motivo", "m") == 0
    assert repo.run("item", "--incremento", "I1", "--id", "I1.2", "--estado", "pendente") == 1


# ---------------------------------------------------------------- invariante e e I1: datas


@pytest.mark.parametrize(
    "valor",
    [
        "2026-10-28T00:00:00+00:60",   # deslocamento com minuto 60
        "2026-10-28T00:00:00+00:99",
        "2026-10-28T00:00:00+24:00",   # hora de deslocamento 24
        "2026-10-28T00:00:00",         # sem fuso
        "2026-10-28T00:00",            # sem segundos
        "2026-10-28T00:00Z",           # sem segundos, com fuso
        "2026-10-28",                  # só data
        "2026-10-28 00:00:00+00:00",   # sem T
        "2026-10-28T00:00:00+0000",    # sem dois-pontos
        "2026-10-28T00:00:00z",        # fuso minúsculo
        "2026-13-01T00:00:00+00:00",   # mês 13
        "2026-02-30T00:00:00Z",        # dia inexistente
        "2026-10-28T25:00:00Z",        # hora 25
        "2026-10-28T00:00:60Z",        # segundo 60
        "٢٠٢٦-10-28T00:00:00Z",        # dígitos não ASCII
        "ontem",
    ],
)
def test_i1_instante_invalido_e_reprovado(repo, valor):
    m = _manifesto()
    m["atualizado_em"] = valor
    assert any("instante RFC 3339 inválido" in e for e in repo.erros(m))
    inc = _concluido(repo.raiz)
    inc["etapas"]["3_commit"]["evidencias"][0]["data"] = valor
    assert any("evidencias[0].data: instante RFC 3339 inválido" in e for e in repo.erros(_manifesto([inc])))


@pytest.mark.parametrize(
    "valor",
    ["2026-10-28T00:00:00Z", "2026-10-28T00:00:00+00:00", "2026-10-28T21:30:59-03:00",
     "2026-10-28T23:59:59+23:59", "2026-10-28T00:00:00.123456Z"],
)
def test_i1_instante_completo_e_aceito(repo, valor):
    m = _manifesto()
    m["atualizado_em"] = valor
    assert repo.erros(m) == []


@pytest.mark.parametrize("valor", ["2026-02-30", "31/10/2026", "2026-10-28T00:00:00Z", "20261028", "٢٠٢٦-10-28"])
def test_i1_data_de_reducao_invalida(repo, valor):
    inc = _inc(rotulo="r", itens=[{"id": "I1.2", "estado": "reduzido", "nota": ""}],
               reducoes=[_red(data=valor)])
    assert any("data ISO inválida" in e for e in repo.erros(_manifesto([inc])))


def test_e_revisar_em_invalido_e_aceito_null(repo):
    exc = {"alvo": "TJAP", "tipo": "tribunal", "estado": "bloqueio_externo_documentado",
           "revisar_em": "31/01/2027", "registro": "r", "nota": "fundamento"}
    m = _manifesto(excecoes=[exc])
    assert any("revisar_em" in e for e in repo.erros(m))
    exc["revisar_em"] = None
    assert repo.erros(m) == []


@pytest.mark.parametrize("sha", ["A" * 64, "a" * 63, "g" * 64, "a" * 65, None, 1])
def test_e_sha256_fora_do_formato_e_reprovado(repo, sha):
    inc = _muda(repo.raiz, "6_distribuicao", "snapshot", "pacotes", [{"nome": "nucleo", "sha256": sha}])
    assert any("sha256" in e for e in repo.erros(_manifesto([inc])))


def test_e_ids_de_etapa_exatamente_os_oito(repo):
    faltando = _etapas_padrao()
    del faltando["8_execucao"]
    assert any("falta o campo '8_execucao'" in e for e in repo.erros(_manifesto([_inc(etapas=faltando)])))
    extra = _etapas_padrao()
    extra["9_extra"] = _etapa()
    assert any("não previsto '9_extra'" in e for e in repo.erros(_manifesto([_inc(etapas=extra)])))


# ---------------------------------------------------------------- M3: nota da exceção


def test_m3_revisar_em_exige_nota_com_o_fundamento(repo):
    exc = {"alvo": "TJAP", "tipo": "tribunal", "estado": "bloqueio_externo_documentado",
           "revisar_em": "2027-01-31", "registro": "r", "nota": " "}
    assert any("revisar_em exige nota" in e for e in repo.erros(_manifesto(excecoes=[exc])))
    exc["nota"] = "fundamento"
    assert repo.erros(_manifesto(excecoes=[exc])) == []


# ---------------------------------------------------------------- I2: caminhos confinados


@pytest.mark.parametrize(
    "ref",
    [
        "../x.json", "../../etc/passwd", "release/../../x.json", "a/../../x", "..",
        "/etc/passwd", "/tmp/x.json", "\\x.json", "C:/x.json", "C:\\x.json", "c:x.json", "D:",
        "\\\\servidor\\share\\x.json", "//servidor/share/x.json", "\\\\?\\C:\\x.json", "\\\\.\\NUL",
        "NUL", "nul.json", "CON", "release/COM1.json", "release/lpt9.txt", "AUX.tar.gz", "prn", "com\u00b9",
        "release/x.json.", "release/x.json ", "arquivo:fluxo", "",  "   ", ".", "release/..",
        "a\x00b",
    ],
)
def test_i2_caminho_nao_confinado_e_recusado_sem_tocar_o_sistema_de_arquivos(tmp_path, monkeypatch, ref):
    def proibido(*_a, **_k):
        raise AssertionError("acesso ao sistema de arquivos antes da recusa")

    for nome in ("resolve", "exists", "is_file", "stat", "read_bytes", "read_text"):
        monkeypatch.setattr(Path, nome, proibido)
    with pytest.raises(ma.ErroAceite):
        ma.confinar(ref, tmp_path)


@pytest.mark.parametrize("ref", ["../x.json", "/etc/passwd", "..", "\\\\srv\\sh\\x.json", "//srv/x.json", "NUL", "C:\\x"])
def test_i2_cli_manifesto_fora_da_raiz_sai_com_1_sem_criar_nada(repo, capsys, ref):
    assert repo.run("--manifesto", ref, "validar") == 1
    assert "manifesto_aceite:" in capsys.readouterr().err
    assert not (repo.raiz.parent / "x.json").exists()


def test_i2_cli_ref_absoluta_ou_com_ponto_ponto_em_campo_de_caminho_e_recusada(repo):
    p = repo.cria()
    antes = p.read_bytes()
    fora = repo.raiz.parent / "fora.md"
    fora.write_text("SEM BLOQUEADOR\n", encoding="utf-8")
    for ref in (str(fora), "../fora.md", f"{repo.raiz.name}/../../fora.md", "//srv/p.md", "\\\\srv\\p.md"):
        assert repo.run("registrar", "--incremento", "I1", "--etapa", "4_incorporacao", "--tipo", "parecer",
                        "--campo", f"parecer={ref}", "--campo", f"commit_auditado={C_TESTE}") == 1, ref
        assert repo.run("registrar", "--incremento", "I1", "--etapa", "1_desenvolvimento", "--tipo",
                        "especificacao", "--campo", f"especificacao={ref}", "--campo", "ramo=feat/x") == 1, ref
    assert p.read_bytes() == antes


@pytest.mark.parametrize("ref", ["release/acceptance_manifest.json", "./release/acceptance_manifest.json",
                                 "release\\acceptance_manifest.json", "release/../release/acceptance_manifest.json"])
def test_i2_caminho_interno_equivalente_e_aceito(repo, ref):
    repo.cria()
    assert repo.run("--manifesto", ref, "validar") == 0


def test_i2_symlink_que_sai_da_raiz_e_recusado(repo, tmp_path_factory):
    fora = tmp_path_factory.mktemp("fora")
    (fora / "x.md").write_text("SEM BLOQUEADOR\n", encoding="utf-8")
    try:
        (repo.raiz / "docs" / "elo").symlink_to(fora, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink indisponível")
    with pytest.raises(ma.ErroAceite, match="por link"):
        ma.arquivo_do_repositorio("docs/elo/x.md", repo.raiz)


def test_i2_o_cli_nao_expoe_a_raiz():
    ajuda = ma._parser().format_help()
    assert "--raiz" not in ajuda and "_raiz" not in ajuda


# ---------------------------------------------------------------- escrita e comandos


def test_registrar_grava_o_recibo_com_campos_na_ordem_e_converte_booleanos(repo):
    repo.cria()
    assert repo.run("registrar", "--incremento", "I1", "--etapa", "7_instalacao", "--tipo", "instalacao",
                    "--campo", f"digests={SHA_SNAP}", "--campo", "concluida=true",
                    "--campo", f"commit={C_MERGE}", "--campo", "attestation_verificada=true",
                    "--estado", "concluida", "--nota", "feito") == 0
    etapa = repo.dados()["incrementos"][0]["etapas"]["7_instalacao"]
    assert etapa["estado"] == "concluida" and etapa["nota"] == "feito"
    ev = etapa["evidencias"][0]
    assert list(ev) == ["tipo", "campos", "data"]
    assert list(ev["campos"]) == ["concluida", "commit", "attestation_verificada", "digests"]
    assert ev["campos"]["concluida"] is True and ev["campos"]["attestation_verificada"] is True
    dt.datetime.fromisoformat(ev["data"])


def test_registrar_false_vira_booleano_e_e_reprovado(repo):
    p = repo.cria()
    antes = p.read_bytes()
    assert repo.run("registrar", "--incremento", "I1", "--etapa", "7_instalacao", "--tipo", "instalacao",
                    "--campo", "concluida=false", "--campo", f"commit={C_MERGE}",
                    "--campo", "attestation_verificada=true", "--campo", f"digests={SHA_SNAP}") == 1
    assert p.read_bytes() == antes


def test_registrar_alertas_acumula_lista_e_aceita_vazia(repo):
    repo.cria()
    args = ("registrar", "--incremento", "I1", "--etapa", "8_execucao", "--tipo", "doctor", "--campo", "ok=true")
    assert repo.run(*args, "--campo", "alertas=fonte_fora: a", "--campo", "alertas=ambiental_desafio: b") == 0
    evs = repo.dados()["incrementos"][0]["etapas"]["8_execucao"]["evidencias"]
    assert evs[0]["campos"] == {"ok": True, "alertas": ["fonte_fora: a", "ambiental_desafio: b"]}
    assert repo.run(*args, "--campo", "alertas=") == 0  # reenvio substitui o doctor anterior
    evs = repo.dados()["incrementos"][0]["etapas"]["8_execucao"]["evidencias"]
    assert len(evs) == 1 and evs[0]["campos"]["alertas"] == []


def test_registrar_campo_repetido_e_recusado(repo, capsys):
    repo.cria()
    assert repo.run("registrar", "--incremento", "I1", "--etapa", "3_commit", "--tipo", "commit",
                    "--campo", f"commit={C_TESTE}", "--campo", f"commit={C_MERGE}") == 1
    assert "campo repetido: commit" in capsys.readouterr().err


def test_registrar_recusa_e_nao_grava_quando_o_recibo_e_invalido(repo, capsys):
    p = repo.cria()
    antes = p.read_bytes()
    assert repo.run("registrar", "--incremento", "I1", "--etapa", "3_commit", "--tipo", "commit",
                    "--campo", "commit=7cf2b7c", "--estado", "concluida") == 1
    assert p.read_bytes() == antes
    assert "40 hex" in capsys.readouterr().err


def test_registrar_tipo_de_outra_etapa_e_recusado(repo, capsys):
    p = repo.cria()
    antes = p.read_bytes()
    assert repo.run("registrar", "--incremento", "I1", "--etapa", "3_commit", "--tipo", "merge",
                    "--campo", f"commit={C_MERGE}") == 1
    assert p.read_bytes() == antes
    assert "não pertence a esta etapa" in capsys.readouterr().err


def test_registrar_incremento_inexistente(repo, capsys):
    repo.cria()
    assert repo.run("registrar", "--incremento", "I9", "--etapa", "3_commit", "--tipo", "commit",
                    "--campo", f"commit={C_TESTE}") == 1
    assert "incremento 'I9' não existe" in capsys.readouterr().err


def _campos_bateria_cli(commit):
    return [f"relatorio={RELATORIO}", f"commit={commit}", "aprovados=5", "xfail=1", "falhas=0", "escopo=stj",
            "ambiente.so=Windows 11", "ambiente.python=3.13.1", "ambiente.pais_ip=BR", f"saude_fontes={SAUDE}",
            "falhas_fora_do_escopo="]


def test_fluxo_completo_pela_cli_fecha_o_incremento(repo):
    repo.cria(_manifesto([_inc()]))
    jobs = [f"jobs={n}=success" for n in ma.JOBS_CI]
    ev = [
        ("1_desenvolvimento", "especificacao", [f"especificacao={SPEC}", "ramo=feat/x"]),
        ("2_teste", "run_ci", [f"url={URL_RUN}", f"commit={C_TESTE}", "conclusao=success", *jobs]),
        ("2_teste", "bateria_live", _campos_bateria_cli(C_TESTE)),
        ("3_commit", "commit", [f"commit={C_TESTE}"]),
        ("4_incorporacao", "parecer", [f"parecer={PARECER}", f"commit_auditado={C_TESTE}"]),
        ("4_incorporacao", "merge", [f"commit={C_MERGE}"]),
        ("5_publicacao", "tag", [f"tag={TAG}", f"commit={C_MERGE}"]),
        ("5_publicacao", "release", [f"url={URL_REL}", "attestation_verificada=true",
                                     f"sha256_wheel={SHA_WHEEL}", f"sha256_sdist={SHA_SDIST}"]),
        ("5_publicacao", "pypi", ["versao=1.4.0a1", f"sha256_wheel={SHA_WHEEL}", f"sha256_sdist={SHA_SDIST}"]),
        ("6_distribuicao", "snapshot", [f"pacotes=nucleo={SHA_SNAP}", f"pacotes=stj={SHA_PACOTE}",
                                        "bateria_s4=aprovada", f"lista_embutida_commit={C_LISTA}"]),
        ("7_instalacao", "instalacao", ["concluida=true", f"commit={C_MERGE}", "attestation_verificada=true",
                                        f"digests={SHA_SNAP}", f"digests={SHA_PACOTE}"]),
        ("8_execucao", "doctor", ["ok=true", f"alertas={ALERTA}"]),
        ("8_execucao", "bateria_live", _campos_bateria_cli(C_MERGE)),
    ]
    for n, (etapa, tipo, campos) in enumerate(ev):
        args = ["registrar", "--incremento", "I1", "--etapa", etapa, "--tipo", tipo]
        for c in campos:
            args += ["--campo", c]
        ultimo = n + 1 == len(ev) or ev[n + 1][0] != etapa  # a etapa fecha no último recibo dela
        if ultimo:
            args += ["--estado", "concluida"]
        if n + 1 == len(ev):
            for it in ma.CATALOGO_PLANO["I1"]:
                assert repo.run("item", "--incremento", "I1", "--id", it, "--estado", "concluido") == 0
            assert repo.run("fechar", "--incremento", "I1") == 1  # etapa 8 ainda pendente
        assert repo.run(*args) == 0, (etapa, tipo)
    bat = repo.dados()["incrementos"][0]["etapas"]["2_teste"]["evidencias"][1]["campos"]
    assert bat["sha256"] == _sha_arquivo(repo.raiz, RELATORIO)
    assert bat["saude_fontes_sha256"] == _sha_arquivo(repo.raiz, SAUDE)
    assert bat["aprovados"] == 5 and bat["escopo"] == ["stj"] and bat["ambiente"] == AMBIENTE
    assert repo.run("fechar", "--incremento", "I1") == 0
    assert repo.dados()["incrementos"][0]["estado"] == "concluido"


def test_fluxo_item_e_rotulo(repo):
    repo.cria()
    assert repo.run("rotulo", "--incremento", "I1", "--texto", "STJ parcial") == 0
    assert repo.run("item", "--incremento", "I1", "--id", "I1.1", "--estado", "concluido", "--nota", "ok") == 0
    inc = repo.dados()["incrementos"][0]
    assert inc["rotulo"] == "STJ parcial"
    assert inc["itens"][0] == {"id": "I1.1", "estado": "concluido", "nota": "ok"}


def test_rotulo_vazio_e_recusado(repo, capsys):
    repo.cria()
    assert repo.run("rotulo", "--incremento", "I1", "--texto", "   ") == 1
    assert "rótulo vazio" in capsys.readouterr().err


def test_item_inexistente_e_recusado(repo, capsys):
    repo.cria()
    assert repo.run("item", "--incremento", "I1", "--id", "I1.99", "--estado", "concluido") == 1
    assert "item 'I1.99' não existe" in capsys.readouterr().err


def test_formato_da_gravacao_e_canonico(repo):
    p = repo.cria()
    assert repo.run("rotulo", "--incremento", "I1", "--texto", "ação e índice") == 0
    texto = p.read_text(encoding="utf-8")
    assert texto.endswith("}\n") and "\r" not in texto
    assert "ação e índice" in texto  # ensure_ascii=False
    assert json.dumps(json.loads(texto), ensure_ascii=False, indent=1) + "\n" == texto
    assert list(json.loads(texto)) == ["plano", "atualizado_em", "incrementos", "excecoes"]
    assert ma.erros_de_estrutura(json.loads(texto)) == []  # atualizado_em gravado já é RFC 3339 completo


def test_falha_no_fsync_nao_corrompe_o_arquivo_nem_deixa_temporario(repo, monkeypatch):
    p = repo.cria()
    antes = p.read_bytes()

    def falha(_fd):
        raise OSError("falha simulada no meio da escrita")

    monkeypatch.setattr(ma.os, "fsync", falha)
    with pytest.raises(OSError, match="falha simulada"):
        repo.run("rotulo", "--incremento", "I1", "--texto", "novo")
    assert p.read_bytes() == antes
    assert sorted(x.name for x in p.parent.iterdir()) == ["acceptance_manifest.json"]


def test_falha_no_os_replace_nao_corrompe_o_arquivo(repo, monkeypatch):
    p = repo.cria()
    antes = p.read_bytes()

    def falha(_origem, _destino):
        raise OSError("falha simulada na troca")

    monkeypatch.setattr(ma.os, "replace", falha)
    with pytest.raises(OSError, match="falha simulada"):
        repo.run("rotulo", "--incremento", "I1", "--texto", "novo")
    assert p.read_bytes() == antes
    assert sorted(x.name for x in p.parent.iterdir()) == ["acceptance_manifest.json"]


# ---------------------------------------------------------------- manifesto, schema e registro do repositório


def test_manifesto_do_repositorio_passa_em_validar():
    assert ma.erros_do_manifesto(json.loads(MANIFESTO_REPO.read_text(encoding="utf-8"))) == []
    assert ma.main(["validar"]) == 0


def test_manifesto_do_repositorio_esta_no_formato_canonico():
    texto = MANIFESTO_REPO.read_text(encoding="utf-8")
    assert json.dumps(json.loads(texto), ensure_ascii=False, indent=1) + "\n" == texto


def test_estado_inicial_do_plano_1_4_0():
    m = json.loads(MANIFESTO_REPO.read_text(encoding="utf-8"))
    incs = {i["id"]: i for i in m["incrementos"]}
    assert list(incs) == ["I1", "I2", "I3", "I4"]
    assert [incs[k]["versao"] for k in incs] == ["1.4.0a1", "1.4.0a2", "1.4.0a3", "1.4.0"]
    assert all(i["estado"] == "aberto" for i in incs.values())
    assert [k for k, i in incs.items() if i["rotulo"] is not None] == ["I1"]
    estados = {it["id"]: it["estado"] for it in incs["I1"]["itens"]}
    assert estados == {"I1.1": "concluido", "I1.2": "adiado", "I1.3": "concluido", "I1.4": "pendente",
                       "I1.5": "pendente", "I1.6": "concluido", "S0": "pendente"}
    assert "I2.6" in {it["id"] for it in incs["I2"]["itens"]}
    assert all(e["estado"] == "pendente" for i in incs.values() for e in i["etapas"].values())
    assert all(e["evidencias"] == [] for i in incs.values() for e in i["etapas"].values())
    assert {(e["alvo"], e["tipo"], e["estado"], e["revisar_em"], e["registro"], e["nota"]) for e in m["excecoes"]} == {
        ("TJAP", "tribunal", "bloqueio_externo_documentado", "2027-01-31", "docs/PLANO-1.4.0.md D4",
         "data fixada pelo supervisor em 28/10/2026; o D4 exige data de revisão e o plano não a fixa"),
        ("pedidos de autos", "funcao", "excluida_pelo_titular", None, "docs/PLANO-1.4.0.md seção 9 item 4", ""),
    }


def test_m3_tjap_mantem_revisar_em_com_fundamento_registrado():
    m = json.loads(MANIFESTO_REPO.read_text(encoding="utf-8"))
    tjap = next(e for e in m["excecoes"] if e["alvo"] == "TJAP")
    assert tjap["revisar_em"] == "2027-01-31"
    assert tjap["nota"] == "data fixada pelo supervisor em 28/10/2026; o D4 exige data de revisão e o plano não a fixa"


def test_schema_documental_bate_com_as_constantes_do_script():
    s = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert s["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    d = s["$defs"]
    assert d["estado_etapa"]["enum"] == list(ma.ESTADOS_ETAPA)
    assert d["tipo_evidencia"]["enum"] == list(ma.TIPOS_EVIDENCIA)
    assert d["campos_por_tipo"]["const"] == {t: list(c) for t, c in ma.CAMPOS_POR_TIPO.items()}
    assert d["tipos_da_etapa"]["const"] == {e: list(t) for e, t in ma.TIPOS_DA_ETAPA.items()}
    assert d["evidencia"]["required"] == list(ma.CHAVES_EVIDENCIA)
    assert d["excecao"]["required"] == list(ma.CHAVES_EXCECAO)
    assert d["incremento"]["properties"]["estado"]["enum"] == list(ma.ESTADOS_INCREMENTO)
    assert d["item"]["properties"]["estado"]["enum"] == list(ma.ESTADOS_ITEM)
    assert d["excecao"]["properties"]["tipo"]["enum"] == list(ma.TIPOS_EXCECAO)
    assert d["excecao"]["properties"]["estado"]["enum"] == list(ma.ESTADOS_EXCECAO)
    assert d["incremento"]["properties"]["etapas"]["required"] == list(ETAPAS)


def test_documento_de_auditoria_declara_o_limite_do_manifesto():
    texto = AUDITORIA.read_text(encoding="utf-8")
    assert "não consulta o GitHub nem a PyPI" in texto
    assert "conferência material é do auditor" in texto


def test_documento_de_auditoria_nao_se_contradiz_sobre_o_ruff():
    texto = AUDITORIA.read_text(encoding="utf-8")
    assert "Ruff, matriz Windows" not in texto
    assert "nao_aplicavel" not in texto.replace("`nao_aplicavel` deixou de existir", "")


# ---------------------------------------------------------------- r2 B1: recibo da bateria live


def _inc_bateria(repo, etapa="2_teste", **trocas):
    inc = _concluido(repo.raiz)
    evs = inc["etapas"][etapa]["evidencias"]
    novo = _bateria(repo.raiz, C_TESTE if etapa == "2_teste" else C_MERGE, **trocas)
    evs[next(i for i, e in enumerate(evs) if e["tipo"] == "bateria_live")] = novo
    return inc


def _inc_ambas(repo, **trocas):
    """Bateria das etapas 2 e 8 com as mesmas trocas (os dois recibos apontam para o mesmo saude-fontes)."""
    inc = _inc_bateria(repo, "2_teste", **trocas)
    evs = inc["etapas"]["8_execucao"]["evidencias"]
    evs[next(i for i, e in enumerate(evs) if e["tipo"] == "bateria_live")] = _bateria(repo.raiz, C_MERGE, **trocas)
    return inc


def _salva_saude(repo, saude):
    (repo.raiz / SAUDE).write_text(json.dumps(saude, ensure_ascii=False), encoding="utf-8")
    return _sha_arquivo(repo.raiz, SAUDE)


def test_r2_b1_recibo_so_com_caminho_e_commit_nao_vale_mais(repo):
    """Cenário do parecer: `bateria_live` só com caminho e commit."""
    inc = _concluido(repo.raiz)
    for etapa in ("2_teste", "8_execucao"):
        evs = inc["etapas"][etapa]["evidencias"]
        c = next(e for e in evs if e["tipo"] == "bateria_live")["campos"]
        c.clear()
        c.update(relatorio=RELATORIO, commit=C_TESTE if etapa == "2_teste" else C_MERGE)
    erros = repo.erros(_manifesto([inc]))
    for campo in ("sha256", "aprovados", "xfail", "falhas", "escopo", "ambiente", "saude_fontes",
                  "saude_fontes_sha256", "falhas_fora_do_escopo"):
        assert any(f"falta o campo '{campo}'" in e for e in erros), campo


@pytest.mark.parametrize("etapa", ["2_teste", "8_execucao"])
def test_r2_b1_relatorio_bateria_nao_executada_reprova(repo, etapa):
    """Cenário do parecer: relatório 'BATERIA NAO EXECUTADA' fechava o incremento."""
    (repo.raiz / RELATORIO).write_text("BATERIA NAO EXECUTADA\n", encoding="utf-8")
    inc = _inc_bateria(repo, etapa, aprovados=0, xfail=0, sha256=_sha_arquivo(repo.raiz, RELATORIO))
    erros = repo.erros(_manifesto([inc]))
    assert any("aprovados + xfail deve ser pelo menos 1" in e for e in erros), erros
    repo.cria(_manifesto([inc]))
    assert repo.run("fechar", "--incremento", "I1") == 1


def test_r2_b1_aprovados_mais_xfail_basta_um_de_cada(repo):
    assert repo.erros(_manifesto([_inc_bateria(repo, aprovados=0, xfail=1)])) == []
    assert repo.erros(_manifesto([_inc_bateria(repo, aprovados=1, xfail=0)])) == []


@pytest.mark.parametrize("campo", ["aprovados", "xfail", "falhas"])
@pytest.mark.parametrize("valor", [-1, "3", 1.5, True, None])
def test_r2_b1_contagens_sao_inteiros_nao_negativos(repo, campo, valor):
    erros = repo.erros(_manifesto([_inc_bateria(repo, **{campo: valor})]))
    assert any(f"campos.{campo}: deve ser inteiro maior ou igual a 0" in e for e in erros), erros


def test_r2_b1_sha256_do_relatorio_e_reconferido(repo):
    inc = _inc_bateria(repo)
    (repo.raiz / RELATORIO).write_text("relatório alterado depois do registro\n", encoding="utf-8")
    assert any("sha256 registrado difere do sha256 dos bytes de relatorio" in e for e in repo.erros(_manifesto([inc])))


def test_r2_b1_sha256_da_saude_e_reconferido(repo):
    inc = _inc_bateria(repo)
    _salva_saude(repo, {**SAUDE_OK, "fim": "2030-01-01T00:00:00+00:00"})
    erros = repo.erros(_manifesto([inc]))
    assert any("saude_fontes_sha256 registrado difere" in e for e in erros)


@pytest.mark.parametrize("campo", ["relatorio", "saude_fontes"])
@pytest.mark.parametrize("ref", ["docs/nao-existe.md", "../fora.json", "/etc/passwd", "https://x/y.json"])
def test_r2_b1_caminhos_da_bateria_sao_confinados_e_existem(repo, campo, ref):
    erros = repo.erros(_manifesto([_inc_bateria(repo, **{campo: ref})]))
    assert any(f"bateria_live: {campo}:" in e or f"bateria_live.campos.{campo}" in e or f"bateria_live.{campo}" in e
               for e in erros), erros


@pytest.mark.parametrize("escopo", [[], "stj", ["stj", "stj"], ["stj", ""], [1]])
def test_r2_b1_escopo_e_lista_nao_vazia_de_fontes(repo, escopo):
    assert any("campos.escopo:" in e for e in repo.erros(_manifesto([_inc_bateria(repo, escopo=escopo)])))


@pytest.mark.parametrize(
    "ambiente",
    [{}, {"so": "Windows"}, {"so": "w", "python": "3.13", "pais_ip": ""}, {"so": "w", "python": "3", "pais_ip": "BR", "x": "y"},
     "Windows 11", None],
)
def test_r2_b1_ambiente_exige_so_python_e_pais_ip(repo, ambiente):
    assert any("campos.ambiente:" in e for e in repo.erros(_manifesto([_inc_bateria(repo, ambiente=ambiente)])))


def test_r2_b1_falhas_igual_ao_tamanho_de_falhas_fora_do_escopo(repo):
    fora = [{"teste": "tests/live/test_live_tjap.py::test_b", "motivo": "WAF", "registro": REGISTRO}]
    assert repo.erros(_manifesto([_inc_bateria(repo, falhas=1, falhas_fora_do_escopo=fora)])) == []
    erros = repo.erros(_manifesto([_inc_bateria(repo, falhas=0, falhas_fora_do_escopo=fora)]))
    assert any("falhas (0) difere de len(falhas_fora_do_escopo) (1)" in e for e in erros)
    erros = repo.erros(_manifesto([_inc_bateria(repo, falhas=2, falhas_fora_do_escopo=fora)]))
    assert any("falhas (2) difere" in e for e in erros)


def test_r2_b1_falha_de_fonte_do_escopo_nao_pode_estar_fora_do_escopo(repo):
    fora = [{"teste": "tests/live/test_live_stj.py::test_a", "motivo": "ignorada", "registro": REGISTRO}]
    erros = repo.erros(_manifesto([_inc_bateria(repo, falhas=1, falhas_fora_do_escopo=fora)]))
    assert any("falha de fonte do escopo em falhas_fora_do_escopo" in e for e in erros)


def test_r2_b1_falha_fora_do_escopo_exige_registro_existente_e_confinado(repo):
    for ref in ("docs/nao-existe.md", "../fora.md", "https://x/y"):
        fora = [{"teste": "tests/live/test_live_tjap.py::test_b", "motivo": "WAF", "registro": ref}]
        erros = repo.erros(_manifesto([_inc_bateria(repo, falhas=1, falhas_fora_do_escopo=fora)]))
        assert any("falhas_fora_do_escopo 'tests/live/test_live_tjap.py::test_b': registro:" in e for e in erros), ref


@pytest.mark.parametrize(
    "fora",
    [[{"teste": "t", "motivo": "m"}], [{"teste": "t", "motivo": "m", "registro": REGISTRO, "x": 1}],
     [{"teste": "", "motivo": "m", "registro": REGISTRO}], ["t"], "t",
     [{"teste": "tests/live/test_live_a.py::t", "motivo": "m", "registro": REGISTRO},
      {"teste": "tests/live/test_live_a.py::t", "motivo": "m", "registro": REGISTRO}]],
)
def test_r2_b1_forma_de_falhas_fora_do_escopo(repo, fora):
    n = len(fora) if isinstance(fora, list) else 0
    erros = repo.erros(_manifesto([_inc_bateria(repo, falhas=n, falhas_fora_do_escopo=fora)]))
    assert any("campos.falhas_fora_do_escopo:" in e for e in erros), erros


def test_r2_b1_saude_incompleta_reprova(repo):
    for completa in (False, None, "true"):
        sha = _salva_saude(repo, {**SAUDE_OK, "completa": completa})
        erros = repo.erros(_manifesto([_inc_bateria(repo, saude_fontes_sha256=sha)]))
        assert any("'completa' deve ser true" in e for e in erros), completa


def test_r2_b1_regressao_precisa_estar_em_falhas_fora_do_escopo(repo):
    nome = "tests/live/test_live_tjap.py::test_b"
    saude = json.loads(json.dumps(SAUDE_OK))
    saude["fontes"]["tjap"]["testes"][0].update(estado="regressao", categoria=None)
    sha = _salva_saude(repo, saude)
    erros = repo.erros(_manifesto([_inc_bateria(repo, saude_fontes_sha256=sha)]))
    assert any(f"regressão fora de falhas_fora_do_escopo: {nome}" in e for e in erros)
    fora = [{"teste": nome, "motivo": "regressão em fonte fora do escopo, registrada", "registro": REGISTRO}]
    assert repo.erros(_manifesto([_inc_ambas(repo, saude_fontes_sha256=sha, falhas=1,
                                             falhas_fora_do_escopo=fora)])) == []


def test_r2_b1_regressao_em_fonte_do_escopo_nunca_passa(repo):
    nome = "tests/live/test_live_stj.py::test_a"
    saude = json.loads(json.dumps(SAUDE_OK))
    saude["fontes"]["stj"]["testes"][0].update(estado="regressao")
    sha = _salva_saude(repo, saude)
    fora = [{"teste": nome, "motivo": "m", "registro": REGISTRO}]
    erros = repo.erros(_manifesto([_inc_bateria(repo, saude_fontes_sha256=sha, falhas=1, falhas_fora_do_escopo=fora)]))
    assert any("falha de fonte do escopo" in e for e in erros)
    assert any("regressão fora" in e for e in repo.erros(_manifesto([_inc_bateria(repo, saude_fontes_sha256=sha)])))


@pytest.mark.parametrize("categoria", [None, ""])
def test_r2_b1_unavailable_exige_categoria(repo, categoria):
    saude = json.loads(json.dumps(SAUDE_OK))
    saude["fontes"]["tjap"]["testes"][0]["categoria"] = categoria
    sha = _salva_saude(repo, saude)
    erros = repo.erros(_manifesto([_inc_bateria(repo, saude_fontes_sha256=sha)]))
    assert any("indisponibilidade sem categoria" in e for e in erros)


@pytest.mark.parametrize("bruto", [b"{", b"[]", b'{"completa": true}', b'{"completa": true, "fontes": []}', b"\xff"])
def test_r2_b1_saude_malformada_reprova(repo, bruto):
    (repo.raiz / SAUDE).write_bytes(bruto)
    sha = _sha_arquivo(repo.raiz, SAUDE)
    assert repo.erros(_manifesto([_inc_bateria(repo, saude_fontes_sha256=sha)])), bruto


def test_r2_b1_a_etapa_8_tambem_confere_a_bateria(repo):
    erros = repo.erros(_manifesto([_inc_bateria(repo, "8_execucao", aprovados=0, xfail=0)]))
    assert any("8_execucao: bateria_live:" in e and "aprovados + xfail" in e for e in erros)


def test_r2_b1_fonte_do_teste_usa_a_regra_do_conftest():
    assert ma._fonte_do_teste("tests/live/test_live_stj.py::test_a[x]") == "stj"
    assert ma._fonte_do_teste("tests\\live\\test_live_tjsp.py::t") == "tjsp"


def test_r2_b1_registrar_bateria_calcula_os_dois_sha256(repo):
    repo.cria()
    args = ["registrar", "--incremento", "I1", "--etapa", "2_teste", "--tipo", "bateria_live",
            *[x for c in _campos_bateria_cli(C_TESTE) for x in ("--campo", c)]]
    assert repo.run(*args) == 0
    campos = repo.dados()["incrementos"][0]["etapas"]["2_teste"]["evidencias"][0]["campos"]
    assert list(campos) == list(ma.CAMPOS_POR_TIPO["bateria_live"])
    assert campos["sha256"] == _sha_arquivo(repo.raiz, RELATORIO)
    assert campos["saude_fontes_sha256"] == _sha_arquivo(repo.raiz, SAUDE)
    assert campos["falhas_fora_do_escopo"] == [] and isinstance(campos["aprovados"], int)


@pytest.mark.parametrize("hash_", ["sha256", "saude_fontes_sha256"])
def test_r2_b1_registrar_bateria_recusa_sha256_informado(repo, capsys, hash_):
    p = repo.cria()
    antes = p.read_bytes()
    args = ["registrar", "--incremento", "I1", "--etapa", "2_teste", "--tipo", "bateria_live",
            *[x for c in (*_campos_bateria_cli(C_TESTE), f"{hash_}={'a' * 64}") for x in ("--campo", c)]]
    assert repo.run(*args) == 1
    assert "calculado pelo registrar" in capsys.readouterr().err
    assert p.read_bytes() == antes


def test_r2_b1_registrar_bateria_nao_executada_e_recusado(repo, capsys):
    p = repo.cria()
    antes = p.read_bytes()
    campos = [c.replace("aprovados=5", "aprovados=0").replace("xfail=1", "xfail=0") for c in _campos_bateria_cli(C_TESTE)]
    assert repo.run("registrar", "--incremento", "I1", "--etapa", "2_teste", "--tipo", "bateria_live",
                    *[x for c in campos for x in ("--campo", c)]) == 1
    assert "aprovados + xfail" in capsys.readouterr().err
    assert p.read_bytes() == antes


def test_r2_b1_registrar_falhas_fora_do_escopo_por_cli(repo):
    repo.cria()
    campos = [c for c in _campos_bateria_cli(C_TESTE) if not c.startswith("falhas_fora")]
    campos = [c.replace("falhas=0", "falhas=1") for c in campos]
    campos.append(f"falhas_fora_do_escopo=tests/live/test_live_tjap.py::test_b|WAF no TJAP|{REGISTRO}")
    assert repo.run("registrar", "--incremento", "I1", "--etapa", "2_teste", "--tipo", "bateria_live",
                    *[x for c in campos for x in ("--campo", c)]) == 0
    c = repo.dados()["incrementos"][0]["etapas"]["2_teste"]["evidencias"][0]["campos"]
    assert c["falhas_fora_do_escopo"] == [
        {"teste": "tests/live/test_live_tjap.py::test_b", "motivo": "WAF no TJAP", "registro": REGISTRO}]


# ---------------------------------------------------------------- r2 B1: jobs do CI e contrato MCP


def test_r2_b1_jobs_exigidos_sao_lint_repositorio_e_oito_test():
    assert len(ma.JOBS_CI) == 10 and len(set(ma.JOBS_CI)) == 10
    assert ma.JOBS_CI[:2] == ("lint", "repositorio")
    assert {j for j in ma.JOBS_CI[2:]} == {
        f"test ({so}, {py})" for so in ("ubuntu-latest", "windows-latest") for py in ("3.11", "3.12", "3.13", "3.14")}


def test_r2_b1_jobs_conferem_com_o_workflow_ci():
    ci = (RAIZ / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "os: [ubuntu-latest, windows-latest]" in ci
    assert 'python-version: ["3.11", "3.12", "3.13", "3.14"]' in ci
    for job in ("  test:", "  repositorio:", "  lint:"):
        assert job in ci


def test_r2_b1_run_ci_sem_jobs_reprova(repo):
    """Cenário do parecer: `run_ci` só com url, commit e conclusão."""
    inc = _concluido(repo.raiz)
    del inc["etapas"]["2_teste"]["evidencias"][0]["campos"]["jobs"]
    assert any("falta o campo 'jobs'" in e for e in repo.erros(_manifesto([inc])))


@pytest.mark.parametrize("faltante", list(ma.JOBS_CI))
def test_r2_b1_cada_job_e_obrigatorio(repo, faltante):
    jobs = [j for j in JOBS_OK if j["nome"] != faltante]
    erros = repo.erros(_manifesto([_muda(repo.raiz, "2_teste", "run_ci", "jobs", jobs)]))
    assert any("campos.jobs:" in e and faltante in e for e in erros), erros


@pytest.mark.parametrize("conclusao", ["failure", "cancelled", "skipped", "success ", ""])
def test_r2_b1_todo_job_precisa_de_success(repo, conclusao):
    jobs = copy.deepcopy(JOBS_OK)
    jobs[4]["conclusao"] = conclusao
    erros = repo.erros(_manifesto([_muda(repo.raiz, "2_teste", "run_ci", "jobs", jobs)]))
    assert any("campos.jobs:" in e for e in erros), erros


def test_r2_b1_job_extra_ou_repetido_reprova(repo):
    extra = [*JOBS_OK, {"nome": "test (macos-latest, 3.12)", "conclusao": "success"}]
    assert any("fora do conjunto" in e for e in repo.erros(_manifesto([_muda(repo.raiz, "2_teste", "run_ci", "jobs", extra)])))
    repetido = [*JOBS_OK, {"nome": "lint", "conclusao": "success"}]
    assert any("repetidos" in e for e in repo.erros(_manifesto([_muda(repo.raiz, "2_teste", "run_ci", "jobs", repetido)])))


@pytest.mark.parametrize("jobs", [[], "lint", [{"nome": "lint"}], [{"nome": "lint", "conclusao": "success", "x": 1}], ["lint"]])
def test_r2_b1_forma_dos_jobs(repo, jobs):
    assert any("campos.jobs:" in e for e in repo.erros(_manifesto([_muda(repo.raiz, "2_teste", "run_ci", "jobs", jobs)])))


def test_r2_b1_registrar_run_ci_por_cli(repo):
    repo.cria()
    campos = [f"url={URL_RUN}", f"commit={C_TESTE}", "conclusao=success",
              *[f"jobs={n}=success" for n in ma.JOBS_CI]]
    assert repo.run("registrar", "--incremento", "I1", "--etapa", "2_teste", "--tipo", "run_ci",
                    *[x for c in campos for x in ("--campo", c)]) == 0
    jobs = repo.dados()["incrementos"][0]["etapas"]["2_teste"]["evidencias"][0]["campos"]["jobs"]
    assert jobs == [{"nome": n, "conclusao": "success"} for n in ma.JOBS_CI]
    assert repo.run("registrar", "--incremento", "I1", "--etapa", "2_teste", "--tipo", "run_ci",
                    *[x for c in campos[:-1] for x in ("--campo", c)]) == 1  # falta um job


# ---------------------------------------------------------------- r2 B2: catálogo fixo


def test_r2_b2_catalogo_do_plano():
    assert ma.CATALOGO_PLANO == {
        "I1": ("I1.1", "I1.2", "I1.3", "I1.4", "I1.5", "I1.6", "S0"),
        "I2": ("I2.1", "I2.2", "I2.3", "I2.4", "I2.5", "I2.6"),
        "I3": ("I3.1", "I3.2", "I3.3", "I3.4", "I3.5", "I3.6", "I3.7", "I3.8"),
        "I4": ("I4.1", "I4.2", "I4.3", "I4.4"),
    }


def test_r2_b2_todo_id_da_secao_6_do_plano_esta_no_catalogo():
    plano = (RAIZ / "docs" / "PLANO-1.4.0.md").read_text(encoding="utf-8")
    secao = plano.split("## 6. Incrementos", 1)[1].split("## 7.", 1)[0]
    ids = {linha.split("|")[1].strip() for linha in secao.splitlines() if linha.startswith("| ")}
    ids -= {"ID", "---"}
    catalogo = {i for itens in ma.CATALOGO_PLANO.values() for i in itens}
    assert ids and ids <= catalogo
    assert catalogo - ids == {"I2.6"}  # item do adiamento do I1.2 (decisão do supervisor, 28/10/2026)


def test_r2_b2_itens_removidos_reprovam(repo, capsys):
    """Cenário do parecer: remover I1.4, I1.5 e S0 e fechar passava."""
    inc = _concluido(repo.raiz)
    inc["itens"] = [it for it in inc["itens"] if it["id"] not in ("I1.4", "I1.5", "S0")]
    erros = repo.erros(_manifesto([inc]))
    for item in ("I1.4", "I1.5", "S0"):
        assert any(f"item {item} do catálogo do plano ausente" in e for e in erros), item
    repo.cria(_manifesto([inc]))
    assert repo.run("fechar", "--incremento", "I1") == 1
    assert repo.dados()["incrementos"][0]["estado"] == "aberto"
    assert "redução ou adiamento" in capsys.readouterr().err


def test_r2_b2_itens_vazios_reprovam(repo, capsys):
    """Cenário do parecer: `itens: []` fechava o incremento."""
    inc = _concluido(repo.raiz)
    inc["itens"] = []
    erros = repo.erros(_manifesto([inc]))
    assert len([e for e in erros if "do catálogo do plano ausente" in e]) == len(ma.CATALOGO_PLANO["I1"])
    repo.cria(_manifesto([inc]))
    assert repo.run("fechar", "--incremento", "I1") == 1
    assert repo.dados()["incrementos"][0]["estado"] == "aberto"


def test_r2_b2_item_fora_do_catalogo_reprova(repo):
    inc = _concluido(repo.raiz)
    inc["itens"].append({"id": "I1.7", "estado": "concluido", "nota": ""})
    assert any("item I1.7 fora do catálogo do plano" in e for e in repo.erros(_manifesto([inc])))


def test_r2_b2_incremento_fora_do_catalogo_reprova(repo):
    inc = _inc(id_="I1")
    inc["id"] = "I9"
    assert any("incremento fora do catálogo do plano" in e for e in repo.erros(_manifesto([inc])))


def test_r2_b2_catalogo_vale_para_cada_incremento(repo):
    for iid, itens in ma.CATALOGO_PLANO.items():
        inc = _inc(id_=iid)
        assert repo.erros(_manifesto([inc])) == []
        inc["itens"] = inc["itens"][:-1]
        assert any(f"item {itens[-1]} do catálogo do plano ausente" in e for e in repo.erros(_manifesto([inc])))


def test_r2_b2_retirada_so_pelo_procedimento_de_reducao(repo):
    repo.cria(_manifesto([_inc()]))
    assert repo.run("reducao", "--incremento", "I1", "--item", "I1.4", "--estado", "adiado", "--rotulo", "sem bench",
                    "--registro", REGISTRO, "--decisao", "D5", "--motivo", "teto") == 0
    inc = repo.dados()["incrementos"][0]
    assert [it["id"] for it in inc["itens"]] == list(ma.CATALOGO_PLANO["I1"])
    assert next(it for it in inc["itens"] if it["id"] == "I1.4")["estado"] == "adiado"
    assert repo.erros(repo.dados()) == []


def test_r2_b2_comando_item_nao_cria_item_fora_do_catalogo(repo):
    repo.cria()
    assert repo.run("item", "--incremento", "I1", "--id", "I1.7", "--estado", "concluido") == 1


# ---------------------------------------------------------------- r2: snapshot em pacotes


def test_r2_snapshot_aceita_um_ou_varios_pacotes(repo):
    um = _muda(repo.raiz, "6_distribuicao", "snapshot", "pacotes", [{"nome": "nucleo", "sha256": SHA_SNAP}])
    um["etapas"]["7_instalacao"]["evidencias"][0]["campos"]["digests"] = [SHA_SNAP]
    assert repo.erros(_manifesto([um])) == []
    assert repo.erros(_manifesto([_concluido(repo.raiz)])) == []


def test_r2_snapshot_unico_antigo_nao_vale(repo):
    inc = _concluido(repo.raiz)
    campos = inc["etapas"]["6_distribuicao"]["evidencias"][0]["campos"]
    del campos["pacotes"]
    campos["sha256"] = SHA_SNAP
    erros = repo.erros(_manifesto([inc]))
    assert any("falta o campo 'pacotes'" in e for e in erros) and any("não previsto 'sha256'" in e for e in erros)


def test_r2_instalacao_com_digest_snapshot_antigo_nao_vale(repo):
    inc = _concluido(repo.raiz)
    campos = inc["etapas"]["7_instalacao"]["evidencias"][0]["campos"]
    del campos["digests"]
    campos["digest_snapshot"] = SHA_SNAP
    erros = repo.erros(_manifesto([inc]))
    assert any("falta o campo 'digests'" in e for e in erros) and any("não previsto 'digest_snapshot'" in e for e in erros)


def test_r2_digests_repetidos_reprovam(repo):
    inc = _muda(repo.raiz, "7_instalacao", "instalacao", "digests", [SHA_SNAP, SHA_SNAP])
    assert any("campos.digests:" in e for e in repo.erros(_manifesto([inc])))


# ---------------------------------------------------------------- r2: regra 8, I2.6 e plano


DECISAO = RAIZ / "docs" / "decisoes" / "0068-manifesto-de-aceite.md"


def test_r2_decisao_0068_registra_a_mudanca_de_regra():
    texto = DECISAO.read_text(encoding="utf-8")
    assert texto.startswith("# 0068 — ")
    for trecho in ("## Contexto", "## Decisão", "## Limites", "seção 5", "D5", "catálogo", "adiament", "SEM BLOQUEADOR",
                   "sha256", "confinad", "não consulta o GitHub nem a PyPI", "conferência material é do auditor"):
        assert trecho in texto, trecho


def test_r2_nota_do_i2_6_e_linha_do_i1_2_no_plano():
    m = json.loads(MANIFESTO_REPO.read_text(encoding="utf-8"))
    nota = next(it for it in m["incrementos"][1]["itens"] if it["id"] == "I2.6")["nota"]
    assert nota == ("segmentação tipada e ligação das íntegras do STJ ao acervo; "
                    "I1.2 adiado inteiro para cá (docs/auditoria/1.4.0/pr10-adiamento.md)")
    plano = (RAIZ / "docs" / "PLANO-1.4.0.md").read_text(encoding="utf-8")
    linha = next(ln for ln in plano.splitlines() if ln.startswith("| I1.2 |"))
    assert linha.endswith(" — adiado para I2.6 em 28/10/2026 (docs/auditoria/1.4.0/pr10-adiamento.md) |")


def test_r2_documento_de_auditoria_registra_a_rodada_3():
    texto = AUDITORIA.read_text(encoding="utf-8")
    assert "## Rodada 3" in texto
    for trecho in ("B1", "B2", "CATALOGO_PLANO", "jobs", "pacotes", "0068", "contrato MCP"):
        assert trecho in texto, trecho
