"""I1.5: manifesto de aceite (validar, registrar, item, reducao, rotulo, fechar), invariantes a a e,
escrita atômica e o manifesto do repositório. Os testes carregam o script do checkout; por isso o módulo
é `repositorio` (fora da wheel instalada, o CI nunca os executaria, já que a wheel não traz scripts/)."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.repositorio

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ / "scripts" / "manifesto_aceite.py"
MANIFESTO_REPO = RAIZ / "release" / "acceptance_manifest.json"
SCHEMA = RAIZ / "release" / "acceptance_manifest.schema.json"
if not SCRIPT.exists():  # job da wheel: sem checkout
    pytest.skip("exige o checkout (scripts/)", allow_module_level=True)
_spec = importlib.util.spec_from_file_location("manifesto_aceite", SCRIPT)
ma = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ma)

ETAPAS = ma.ETAPAS
SHA = "a" * 64
DATA = "2026-10-28T00:00:00+00:00"


def _ev(tipo, ref="ref", sha=None, data=DATA):
    return {"tipo": tipo, "ref": ref, "sha256": sha, "data": data}


def _etapa(estado="pendente", evidencias=None, nota=""):
    return {"estado": estado, "evidencias": evidencias or [], "nota": nota}


def _etapas_padrao():
    return {n: _etapa() for n in ETAPAS}


def _inc(id_="I1", estado="aberto", rotulo=None, itens=None, reducoes=None, etapas=None):
    return {
        "id": id_, "versao": "1.4.0a1", "estado": estado, "rotulo": rotulo,
        "itens": itens if itens is not None else [{"id": "I1.1", "estado": "pendente", "nota": ""}],
        "etapas": etapas if etapas is not None else _etapas_padrao(),
        "reducoes_de_escopo": reducoes or [],
    }


def _manifesto(incrementos=None, excecoes=None):
    return {
        "plano": "1.4.0", "atualizado_em": DATA,
        "incrementos": incrementos if incrementos is not None else [_inc()],
        "excecoes": excecoes or [],
    }


def _concluido(tmp_path, parecer_texto="Achados: nenhum.\nSEM BLOQUEADOR\n"):
    parecer = tmp_path / "parecer-r2.md"
    parecer.write_text(parecer_texto, encoding="utf-8")
    etapas = {
        "1_desenvolvimento": _etapa("concluida", [_ev("commit", "7cf2b7c")]),
        "2_teste": _etapa("concluida", [_ev("run_ci", "run 1")]),
        "3_commit": _etapa("concluida", [_ev("commit", "7cf2b7c")]),
        "4_incorporacao": _etapa("concluida", [_ev("parecer", str(parecer))]),
        "5_publicacao": _etapa("concluida", [_ev("tag", "v1"), _ev("release", "v1"), _ev("pypi", "pypi 1")]),
        "6_distribuicao": _etapa("concluida", [_ev("snapshot", "snap", SHA)]),
        "7_instalacao": _etapa("concluida", [_ev("instalacao", "instalacao.json")]),
        "8_execucao": _etapa("concluida", [_ev("doctor", "doctor"), _ev("bateria_live", "bateria")]),
    }
    itens = [{"id": "I1.1", "estado": "concluido", "nota": ""}]
    return _inc(estado="aberto", itens=itens, etapas=etapas)


@pytest.fixture
def arq(tmp_path):
    def cria(m=None):
        p = tmp_path / "release" / "acceptance_manifest.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(m if m is not None else _manifesto(), ensure_ascii=False, indent=1) + "\n",
                     encoding="utf-8")
        return p

    return cria


def run(caminho, *args):
    return ma.main(["--manifesto", str(caminho), *args])


def erros_com_etapa(etapa, nome="1_desenvolvimento"):
    m = _manifesto([_inc(etapas={**_etapas_padrao(), nome: etapa})])
    return ma.erros_do_manifesto(m)


# ---------------------------------------------------------------- estrutura e validar


def test_manifesto_minimo_e_valido():
    assert ma.erros_do_manifesto(_manifesto()) == []


def test_validar_retorna_zero_e_imprime_resumo(arq, capsys):
    assert run(arq(), "validar") == 0
    assert "manifesto válido: 1 incrementos, 0 exceções" in capsys.readouterr().out


def test_arquivo_ausente_sai_com_1(tmp_path, capsys):
    assert run(tmp_path / "nao-existe.json", "validar") == 1
    assert "manifesto não encontrado" in capsys.readouterr().err


def test_json_invalido_sai_com_1(tmp_path, capsys):
    p = tmp_path / "x.json"
    p.write_text("{", encoding="utf-8")
    assert run(p, "validar") == 1
    assert "JSON inválido" in capsys.readouterr().err


def test_uso_invalido_sai_com_2(arq):
    with pytest.raises(SystemExit) as exc:
        run(arq(), "item", "--incremento", "I1")
    assert exc.value.code == 2


@pytest.mark.parametrize("campo", ["plano", "atualizado_em", "incrementos", "excecoes"])
def test_campo_raiz_ausente_e_reprovado(campo):
    m = _manifesto()
    del m[campo]
    assert any(campo in e for e in ma.erros_do_manifesto(m))


def test_campo_extra_e_reprovado():
    m = _manifesto()
    m["extra"] = 1
    assert any("não previsto 'extra'" in e for e in ma.erros_do_manifesto(m))


def test_estado_de_incremento_invalido():
    m = _manifesto([_inc(estado="feito")])
    assert any("não é valor válido" in e for e in ma.erros_do_manifesto(m))


# ---------------------------------------------------------------- invariante a


def test_a_concluida_sem_evidencia_e_reprovada():
    erros = erros_com_etapa(_etapa("concluida"))
    assert any("exige ao menos uma evidência" in e for e in erros)


def test_a_nao_aplicavel_sem_nota_e_reprovada():
    assert any("exige nota" in e for e in erros_com_etapa(_etapa("nao_aplicavel", nota="  ")))
    assert erros_com_etapa(_etapa("nao_aplicavel", nota="sem instalador neste ramo")) == []


# ---------------------------------------------------------------- invariante b


def test_b_etapa_4_concluida_exige_parecer():
    erros = erros_com_etapa(_etapa("concluida", [_ev("commit")]), "4_incorporacao")
    assert any("exige evidência 'parecer'" in e for e in erros)


def test_b_parecer_local_com_sem_bloqueador_na_ultima_linha_aprova(tmp_path, arq):
    p = arq(_manifesto([_concluido(tmp_path, "linha\nSEM BLOQUEADOR\n\n\n")]))
    assert run(p, "validar") == 0


@pytest.mark.parametrize(
    "ultima",
    ["COM BLOQUEADOR", "TETO DE 3 RODADAS ATINGIDO", "SEM BLOQUEADOR (ressalvas nao corrigidas)"],
)
def test_b_ultima_linha_diferente_de_sem_bloqueador_e_reprovada(tmp_path, arq, capsys, ultima):
    p = arq(_manifesto([_concluido(tmp_path, f"SEM BLOQUEADOR\n{ultima}\n")]))
    assert run(p, "validar") == 1
    assert "a última linha não vazia do parecer não é 'SEM BLOQUEADOR'" in capsys.readouterr().err


def test_b_linha_vazia_depois_nao_conta_como_ultima(tmp_path):
    m = _manifesto([_concluido(tmp_path, "SEM BLOQUEADOR\nCOM BLOQUEADOR\n\n")])
    assert any("não é 'SEM BLOQUEADOR'" in e for e in ma.erros_do_manifesto(m))


def test_b_parecer_url_exige_sha256():
    ev = _ev("parecer", "https://exemplo.invalido/parecer-r2")
    assert any("exige sha256" in e for e in erros_com_etapa(_etapa("concluida", [ev]), "4_incorporacao"))
    ev["sha256"] = SHA
    assert erros_com_etapa(_etapa("concluida", [ev]), "4_incorporacao") == []


def test_b_parecer_inexistente_exige_sha256(tmp_path):
    ev = _ev("parecer", str(tmp_path / "nao-existe.md"))
    assert any("exige sha256" in e for e in erros_com_etapa(_etapa("concluida", [ev]), "4_incorporacao"))
    ev["sha256"] = SHA
    assert erros_com_etapa(_etapa("concluida", [ev]), "4_incorporacao") == []


def test_b_um_parecer_com_bloqueador_invalida_a_etapa(tmp_path):
    ruim = tmp_path / "r1.md"
    ruim.write_text("COM BLOQUEADOR\n", encoding="utf-8")
    ev_ruim = _ev("parecer", str(ruim))
    ev_ok = _ev("parecer", "https://exemplo.invalido/r2", SHA)
    assert erros_com_etapa(_etapa("concluida", [ev_ruim, ev_ok]), "4_incorporacao")


# ---------------------------------------------------------------- invariante c


@pytest.mark.parametrize("ausente", ["tag", "release", "pypi"])
def test_c_publicacao_exige_tag_release_e_pypi(ausente):
    evs = [_ev(t) for t in ("tag", "release", "pypi") if t != ausente]
    assert any(f"exige evidência '{ausente}'" in e for e in erros_com_etapa(_etapa("concluida", evs), "5_publicacao"))


def test_c_pypi_dispensado_so_com_nota_de_nao_aplicavel():
    evs = [_ev("tag"), _ev("release")]
    sem_nota = _etapa("concluida", evs, nota="")
    com_nota = _etapa("concluida", evs, nota="PyPI não aplicável: pré-release só no GitHub")
    assert any("exige evidência 'pypi'" in e for e in erros_com_etapa(sem_nota, "5_publicacao"))
    assert erros_com_etapa(com_nota, "5_publicacao") == []


def test_c_distribuicao_exige_snapshot_com_sha256():
    sem_sha = _etapa("concluida", [_ev("snapshot", "snap")])
    assert any("snapshot' com sha256" in e for e in erros_com_etapa(sem_sha, "6_distribuicao"))
    assert erros_com_etapa(_etapa("concluida", [_ev("snapshot", "snap", SHA)]), "6_distribuicao") == []


def test_c_instalacao_exige_instalacao():
    assert any("exige evidência 'instalacao'" in e
               for e in erros_com_etapa(_etapa("concluida", [_ev("doctor")]), "7_instalacao"))


@pytest.mark.parametrize("ausente", ["doctor", "bateria_live"])
def test_c_execucao_exige_doctor_e_bateria_live(ausente):
    evs = [_ev(t) for t in ("doctor", "bateria_live") if t != ausente]
    assert any(f"exige evidência '{ausente}'" in e for e in erros_com_etapa(_etapa("concluida", evs), "8_execucao"))


# ---------------------------------------------------------------- invariante d


def test_d_incremento_concluido_com_etapa_pendente_e_reprovado(tmp_path):
    m = _manifesto([_concluido(tmp_path)])
    m["incrementos"][0]["estado"] = "concluido"
    m["incrementos"][0]["etapas"]["8_execucao"] = _etapa()
    assert any("etapa 8_execucao pendente" in e for e in ma.erros_do_manifesto(m))


def test_d_incremento_concluido_com_item_pendente_e_reprovado(tmp_path):
    inc = _concluido(tmp_path)
    inc["estado"] = "concluido"
    inc["itens"].append({"id": "I1.2", "estado": "pendente", "nota": ""})
    assert any("item I1.2 pendente" in e for e in ma.erros_do_manifesto(_manifesto([inc])))


def test_d_item_reduzido_exige_reducao_e_rotulo():
    inc = _inc(itens=[{"id": "I1.2", "estado": "reduzido", "nota": ""}])
    erros = ma.erros_do_manifesto(_manifesto([inc]))
    assert any("exige entrada em reducoes_de_escopo" in e for e in erros)
    assert any("exige rotulo não nulo" in e for e in erros)


def test_d_item_adiado_exige_rotulo_nao_nulo():
    red = {"item": "I1.2", "data": "2026-10-28", "decisao": "D5", "registro": "docs/x.md", "motivo": "prazo"}
    inc = _inc(itens=[{"id": "I1.2", "estado": "adiado", "nota": ""}], reducoes=[red])
    assert any("exige rotulo" in e for e in ma.erros_do_manifesto(_manifesto([inc])))
    inc["rotulo"] = "1.4.0a1 parcial"
    assert ma.erros_do_manifesto(_manifesto([inc])) == []


def test_d_reducao_de_item_inexistente_e_reprovada():
    red = {"item": "I9.9", "data": "2026-10-28", "decisao": "D5", "registro": "docs/x.md", "motivo": "m"}
    inc = _inc(rotulo="r", reducoes=[red])
    assert any("item inexistente" in e for e in ma.erros_do_manifesto(_manifesto([inc])))


def test_d_fechar_so_com_invariantes_e_depois_marca_concluido(tmp_path, arq):
    p = arq(_manifesto([_inc(etapas=_etapas_padrao())]))
    assert run(p, "fechar", "--incremento", "I1") == 1
    assert json.loads(p.read_text(encoding="utf-8"))["incrementos"][0]["estado"] == "aberto"

    p = arq(_manifesto([_concluido(tmp_path)]))
    assert run(p, "fechar", "--incremento", "I1") == 0
    assert json.loads(p.read_text(encoding="utf-8"))["incrementos"][0]["estado"] == "concluido"
    assert run(p, "fechar", "--incremento", "I1") == 0  # já concluído: no-op


def test_fechar_incremento_adiado_e_recusado(arq, capsys):
    p = arq(_manifesto([_inc(estado="adiado")]))
    assert run(p, "fechar", "--incremento", "I1") == 1
    assert "não pode ser fechado" in capsys.readouterr().err


# ---------------------------------------------------------------- invariante e


@pytest.mark.parametrize("valor", ["2026-13-01T00:00:00+00:00", "ontem", "2026-10-28"])
def test_e_data_hora_invalida_em_atualizado_em(valor):
    m = _manifesto()
    m["atualizado_em"] = valor
    assert any("data-hora ISO inválida" in e for e in ma.erros_do_manifesto(m))


def test_e_data_de_evidencia_invalida():
    erros = erros_com_etapa(_etapa("concluida", [_ev("commit", data="31/10/2026")]))
    assert any("data-hora ISO inválida" in e for e in erros)


def test_e_data_de_reducao_invalida():
    red = {"item": "I1.1", "data": "2026-02-30", "decisao": "D5", "registro": "r", "motivo": "m"}
    inc = _inc(rotulo="r", reducoes=[red], itens=[{"id": "I1.1", "estado": "reduzido", "nota": ""}])
    assert any("data ISO inválida" in e for e in ma.erros_do_manifesto(_manifesto([inc])))


def test_e_revisar_em_invalido_e_aceito_null():
    m = _manifesto(excecoes=[{"alvo": "TJAP", "tipo": "tribunal", "estado": "bloqueio_externo_documentado",
                              "revisar_em": "31/01/2027", "registro": "r"}])
    assert any("revisar_em" in e for e in ma.erros_do_manifesto(m))
    m["excecoes"][0]["revisar_em"] = None
    assert ma.erros_do_manifesto(m) == []


@pytest.mark.parametrize("sha", ["A" * 64, "a" * 63, "g" * 64, "a" * 65])
def test_e_sha256_fora_do_formato_e_reprovado(sha):
    assert any("sha256" in e for e in erros_com_etapa(_etapa("concluida", [_ev("snapshot", "s", sha)]),
                                                      "6_distribuicao"))


def test_e_ids_de_etapa_exatamente_os_oito():
    faltando = _etapas_padrao()
    del faltando["8_execucao"]
    assert any("falta o campo '8_execucao'" in e for e in ma.erros_do_manifesto(_manifesto([_inc(etapas=faltando)])))
    extra = _etapas_padrao()
    extra["9_extra"] = _etapa()
    assert any("não previsto '9_extra'" in e for e in ma.erros_do_manifesto(_manifesto([_inc(etapas=extra)])))


def test_e_tipo_de_evidencia_fora_da_lista():
    assert any("'selfie' não é valor válido" in e
               for e in erros_com_etapa(_etapa("concluida", [_ev("selfie")])))


# ---------------------------------------------------------------- escrita e comandos


def test_registrar_grava_evidencia_com_campos_na_ordem(arq):
    p = arq()
    assert run(p, "registrar", "--incremento", "I1", "--etapa", "1_desenvolvimento", "--tipo", "commit",
               "--ref", "7cf2b7c", "--estado", "concluida", "--nota", "feito") == 0
    etapa = json.loads(p.read_text(encoding="utf-8"))["incrementos"][0]["etapas"]["1_desenvolvimento"]
    assert etapa["estado"] == "concluida" and etapa["nota"] == "feito"
    ev = etapa["evidencias"][0]
    assert list(ev) == ["tipo", "ref", "sha256", "data"]
    assert ev["sha256"] is None
    dt.datetime.fromisoformat(ev["data"])


def test_registrar_recusa_e_nao_grava_quando_invariante_falha(arq, capsys):
    p = arq()
    antes = p.read_bytes()
    assert run(p, "registrar", "--incremento", "I1", "--etapa", "4_incorporacao", "--tipo", "parecer",
               "--ref", "https://exemplo.invalido/r2", "--estado", "concluida") == 1
    assert p.read_bytes() == antes
    assert "exige sha256" in capsys.readouterr().err


def test_registrar_incremento_inexistente(arq, capsys):
    assert run(arq(), "registrar", "--incremento", "I9", "--etapa", "1_desenvolvimento", "--tipo", "commit",
               "--ref", "x") == 1
    assert "incremento 'I9' não existe" in capsys.readouterr().err


def test_fluxo_reducao_rotulo_e_item(arq):
    p = arq(_manifesto([_inc(itens=[{"id": "I1.2", "estado": "pendente", "nota": ""}])]))
    assert run(p, "item", "--incremento", "I1", "--id", "I1.2", "--estado", "reduzido") == 1  # sem redução
    assert run(p, "reducao", "--incremento", "I1", "--item", "I1.2", "--registro", "docs/x.md",
               "--decisao", "D5", "--motivo", "limite de auditoria") == 0
    assert run(p, "rotulo", "--incremento", "I1", "--texto", "STJ parcial") == 0
    assert run(p, "item", "--incremento", "I1", "--id", "I1.2", "--estado", "reduzido",
               "--nota", "íntegras do STJ reduzidas") == 0
    dados = json.loads(p.read_text(encoding="utf-8"))
    inc = dados["incrementos"][0]
    assert inc["rotulo"] == "STJ parcial"
    assert inc["itens"][0] == {"id": "I1.2", "estado": "reduzido", "nota": "íntegras do STJ reduzidas"}
    assert inc["reducoes_de_escopo"][0]["data"] == dt.datetime.now(dt.timezone.utc).date().isoformat()


def test_rotulo_vazio_e_recusado(arq, capsys):
    assert run(arq(), "rotulo", "--incremento", "I1", "--texto", "   ") == 1
    assert "rótulo vazio" in capsys.readouterr().err


def test_item_inexistente_e_recusado(arq, capsys):
    assert run(arq(), "item", "--incremento", "I1", "--id", "I1.99", "--estado", "concluido") == 1
    assert "item 'I1.99' não existe" in capsys.readouterr().err


def test_formato_da_gravacao_e_canonico(arq):
    p = arq()
    assert run(p, "rotulo", "--incremento", "I1", "--texto", "ação e índice") == 0
    texto = p.read_text(encoding="utf-8")
    assert texto.endswith("}\n") and "\r" not in texto
    assert "ação e índice" in texto  # ensure_ascii=False
    assert json.dumps(json.loads(texto), ensure_ascii=False, indent=1) + "\n" == texto
    assert list(json.loads(texto)) == ["plano", "atualizado_em", "incrementos", "excecoes"]


def test_falha_no_fsync_nao_corrompe_o_arquivo_nem_deixa_temporario(arq, monkeypatch):
    p = arq()
    antes = p.read_bytes()

    def falha(_fd):
        raise OSError("falha simulada no meio da escrita")

    monkeypatch.setattr(ma.os, "fsync", falha)
    with pytest.raises(OSError, match="falha simulada"):
        run(p, "rotulo", "--incremento", "I1", "--texto", "novo")
    assert p.read_bytes() == antes
    assert sorted(x.name for x in p.parent.iterdir()) == ["acceptance_manifest.json"]


def test_falha_no_os_replace_nao_corrompe_o_arquivo(arq, monkeypatch):
    p = arq()
    antes = p.read_bytes()

    def falha(_origem, _destino):
        raise OSError("falha simulada na troca")

    monkeypatch.setattr(ma.os, "replace", falha)
    with pytest.raises(OSError, match="falha simulada"):
        run(p, "rotulo", "--incremento", "I1", "--texto", "novo")
    assert p.read_bytes() == antes
    assert sorted(x.name for x in p.parent.iterdir()) == ["acceptance_manifest.json"]


# ---------------------------------------------------------------- manifesto e schema do repositório


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
    assert all(i["estado"] == "aberto" and i["rotulo"] is None for i in incs.values())
    estados = {it["id"]: it["estado"] for it in incs["I1"]["itens"]}
    assert estados == {"I1.1": "concluido", "I1.2": "pendente", "I1.3": "concluido", "I1.4": "pendente",
                       "I1.5": "pendente", "I1.6": "concluido", "S0": "pendente"}
    assert "I2.6" in {it["id"] for it in incs["I2"]["itens"]}
    assert all(e["estado"] == "pendente" for i in incs.values() for e in i["etapas"].values())
    assert all(e["evidencias"] == [] for i in incs.values() for e in i["etapas"].values())
    assert {(e["alvo"], e["tipo"], e["estado"], e["revisar_em"], e["registro"]) for e in m["excecoes"]} == {
        ("TJAP", "tribunal", "bloqueio_externo_documentado", "2027-01-31", "docs/PLANO-1.4.0.md D4"),
        ("pedidos de autos", "funcao", "excluida_pelo_titular", None, "docs/PLANO-1.4.0.md seção 9 item 4"),
    }


def test_schema_documental_bate_com_as_constantes_do_script():
    s = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert s["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    d = s["$defs"]
    assert d["estado_etapa"]["enum"] == list(ma.ESTADOS_ETAPA)
    assert d["tipo_evidencia"]["enum"] == list(ma.TIPOS_EVIDENCIA)
    assert d["incremento"]["properties"]["estado"]["enum"] == list(ma.ESTADOS_INCREMENTO)
    assert d["item"]["properties"]["estado"]["enum"] == list(ma.ESTADOS_ITEM)
    assert d["excecao"]["properties"]["tipo"]["enum"] == list(ma.TIPOS_EXCECAO)
    assert d["excecao"]["properties"]["estado"]["enum"] == list(ma.ESTADOS_EXCECAO)
    assert d["incremento"]["properties"]["etapas"]["required"] == list(ETAPAS)
