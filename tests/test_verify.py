"""Verificação ponta a ponta — LSA e RCVM 160; mutantes críticos."""

from __future__ import annotations

import pytest

from freoa_verifica.aliases import WorkKey
from freoa_verifica.parsers.cvm_docx import parse_cvm_docx
from freoa_verifica.parsers.planalto import parse_planalto
from freoa_verifica.store.db import connect
from freoa_verifica.verify import MemoryResolver, populate_from_parsed, verificar
from tests.fixture_util import load_fixture, load_meta

LSA_KEY = WorkKey("federal", "lei", "6404", 1976)
RCVM160_KEY = WorkKey("cvm", "resolucao", "160", 2022)
WORK_DATE_LSA = "1976-12-15"
WORK_DATE_RCVM160 = "2022-07-13"


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "fv"
    home.mkdir()
    monkeypatch.setenv("FV_HOME", str(home))
    conn = connect(home / "verifica.sqlite3")
    resolver = MemoryResolver()
    meta = load_meta()

    # LSA
    body_lsa = load_fixture("planalto_lei_6404_1976")
    doc_lsa = parse_planalto(
        body_lsa,
        base_url="https://www.planalto.gov.br/ccivil_03/leis/",
    )
    entry = meta["planalto_lei_6404_1976"]
    rw_lsa = populate_from_parsed(
        conn,
        source_id="planalto",
        work_key=LSA_KEY,
        document=doc_lsa,
        body=body_lsa,
        url=entry["url"],
        fetched_at=entry.get("capturado_em"),
        work_date=WORK_DATE_LSA,
        label="Lei nº 6.404/1976",
    )
    resolver.add(rw_lsa)

    # RCVM 160
    body_160 = load_fixture("cvm_resol_160_consolid_docx")
    doc_160 = parse_cvm_docx(body_160)
    entry160 = meta["cvm_resol_160_consolid_docx"]
    rw_160 = populate_from_parsed(
        conn,
        source_id="cvm",
        work_key=RCVM160_KEY,
        document=doc_160,
        body=body_160,
        url=entry160["url"],
        fetched_at=entry160.get("capturado_em"),
        work_date=WORK_DATE_RCVM160,
        label="Resolução CVM nº 160/2022",
    )
    # também sob year=0 para citações sem ano
    resolver.add(
        type(rw_160)(
            **{
                **rw_160.__dict__,
                "work_key": WorkKey("cvm", "resolucao", "160", 0),
            }
        )
    )
    resolver.add(rw_160)

    yield conn, resolver, doc_lsa, doc_160
    conn.close()


def test_positivo_art254a_literal(env):
    conn, resolver, doc_lsa, _ = env
    trecho = doc_lsa.current_text("art254-A")
    assert trecho
    # Prefixo em fronteira lexical (item 7: não cortar no meio da palavra)
    cut = trecho[:180]
    trecho = cut.rsplit(" ", 1)[0] if " " in cut else cut
    res = verificar(
        "art. 254-A da Lei 6.404/76",
        trecho=trecho,
        data=None,
        modo="literal",
        repo=conn,
        resolver=resolver,
    )
    assert res.identity.status == "verified"
    assert res.text.status == "verified"
    assert res.support.status == "not_assessed"
    assert res.run_id is not None


def test_mutante_digito(env):
    conn, resolver, doc_lsa, _ = env
    trecho = doc_lsa.current_text("art254-A")
    assert trecho
    # Mutação no prefixo enviado: "80%"→"70%" se houver; senão troca letra por dígito
    sample = trecho[:240]
    if "companhia" in sample:
        mut = sample.replace("companhia", "companh1a", 1)
    else:
        mut = sample.replace("alienação", "alienaçã0", 1)
    assert mut != sample
    res = verificar(
        "art. 254-A da Lei 6.404/76",
        trecho=mut,
        repo=conn,
        resolver=resolver,
    )
    assert res.text.status != "verified"


def test_mutante_nao(env):
    conn, resolver, doc_lsa, _ = env
    trecho = doc_lsa.current_text("art254-A")
    assert trecho
    assert "poder" in trecho.lower()
    # Inserção de negação no trecho comparado
    anchor = "somente poder"
    idx = trecho.lower().find(anchor)
    assert idx >= 0
    # preserva capitalização original ao inserir "não "
    mut = trecho[: idx + len("somente ")] + "não " + trecho[idx + len("somente ") :]
    res = verificar(
        "art. 254-A da Lei 6.404/76",
        trecho=mut[:240],
        repo=conn,
        resolver=resolver,
    )
    assert res.text.status != "verified"


def test_mutante_suspensiva_resolutiva(env):
    conn, resolver, doc_lsa, _ = env
    trecho = doc_lsa.current_text("art254-A")
    assert trecho and "suspensiva" in trecho
    mut = trecho.replace("suspensiva ou resolutiva", "resolutiva", 1)
    res = verificar(
        "art. 254-A da Lei 6.404/76",
        trecho=mut[:240],
        repo=conn,
        resolver=resolver,
    )
    assert res.text.status != "verified"


def test_mutante_outro_paragrafo(env):
    conn, resolver, doc_lsa, _ = env
    par1 = doc_lsa.current_text("art254-A.par1")
    if par1 is None:
        # fallback: outro dispositivo da mesma obra
        par1 = doc_lsa.current_text("art116")
    assert par1
    res = verificar(
        "art. 254-A da Lei 6.404/76",
        trecho=par1[:200],
        repo=conn,
        resolver=resolver,
    )
    assert res.text.status != "verified"
    assert res.text.status in ("divergent", "not_found")


def test_mutante_redacao_riscada_data_atual(env):
    conn, resolver, _, doc_160 = env
    prov = doc_160.provision("art2.inc16")
    struck = next(r for r in prov.redactions if r.struck)
    res = verificar(
        "art. 2º, XVI, da Resolução CVM nº 160",
        trecho=struck.text,
        data="2023-01-01",  # vigente ≠ riscada
        repo=conn,
        resolver=resolver,
    )
    assert res.text.status != "verified"
    assert res.text.reason_code in (
        "TRECHO_DE_OUTRA_REDACAO",
        "TEXTO_DIVERGENTE",
        "TEXTO_PARCIAL",
    )


def test_mutante_caminho_inexistente(env):
    conn, resolver, _, _ = env
    res = verificar(
        "art. 254-Z da Lei 6.404/76",
        trecho="qualquer",
        repo=conn,
        resolver=resolver,
    )
    assert res.identity.status == "not_found"
    assert res.text.status != "verified"


def test_mutante_obra_inexistente(env):
    conn, resolver, _, _ = env
    res = verificar(
        "art. 1º da Lei 99.999/2099",
        trecho="qualquer",
        repo=conn,
        resolver=resolver,
    )
    assert res.identity.status == "not_found"
    assert res.text.status != "verified"


def test_rcvm160_temporal_causal(env):
    conn, resolver, _, doc_160 = env
    prov = doc_160.provision("art2.inc16")
    struck = next(r for r in prov.redactions if r.struck)
    current = next(r for r in prov.redactions if not r.struck)
    # C2: obra CVM sem situação lida seria `ilegivel`; aqui a página do ato declara vigente.
    from freoa_verifica import situacao
    from freoa_verifica.aliases import WorkKey
    rw160 = resolver.resolve(WorkKey("cvm", "resolucao", "160", 2022))
    situacao.gravar(conn, situacao.WorkStatus(rw160.work_id, "vigente_declarada"))

    r1 = verificar(
        "art. 2º, XVI da RCVM 160",
        trecho=struck.text,
        data="2022-08-01",
        repo=conn,
        resolver=resolver,
    )
    r2 = verificar(
        "art. 2º, XVI da RCVM 160",
        trecho=current.text,
        data="2023-01-01",
        repo=conn,
        resolver=resolver,
    )
    assert r1.text.status == "verified"
    assert r2.text.status == "verified"
    # redação original (R3) com limites conhecidos → verified;
    # redação alterada com vacatio → unknown (não verified)
    assert r1.temporal.status == "verified"
    assert r2.temporal.status == "unknown"
    assert "vacatio_nao_verificada" in (
        r2.temporal.reason_code or ""
    ) or r2.temporal.status == "unknown"

    # trocar datas → texto deixa de verified
    bad = verificar(
        "art. 2º, XVI da RCVM 160",
        trecho=struck.text,
        data="2023-01-01",
        repo=conn,
        resolver=resolver,
    )
    assert bad.text.status != "verified"
