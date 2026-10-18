"""M11: rubricas de artigo pesquisáveis no FTS e rótulos CVM com mojibake corrigidos."""

import sqlite3

import pytest

from freoa_verifica.rotulos import corrigir_mojibake, corrigir_rotulos
from freoa_verifica.store import db as dbmod
from freoa_verifica.store import repo
from freoa_verifica.store.db import connect


def _mojibake(texto: str) -> str:
    return texto.encode("utf-8").decode("latin-1")


# --- rubricas no índice ---

def test_rubrica_de_artigo_e_pesquisavel(tmp_path):
    conn = connect(tmp_path / "v.sqlite3")
    repo.index_redaction(conn, text="O administrador deve servir com lealdade à companhia.",
                         work_label="LSA", path="art-155", rubrica="Dever de Lealdade")
    repo.index_redaction(conn, text="Texto sem rubrica sobre companhia.",
                         work_label="LSA", path="art-156")
    hits = repo.search_redactions(conn, "lealdade")
    assert [h["path"] for h in hits] == ["art-155"]
    assert repo.search_redactions(conn, "diligência") == []
    conn.close()


def test_migracao_006_preserva_linhas_existentes(tmp_path):
    path = tmp_path / "antigo.sqlite3"
    raw = sqlite3.connect(str(path))
    raw.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY, "
                "applied_at TEXT NOT NULL DEFAULT (datetime('now')))")
    for version, sql in dbmod._migration_files():
        if version >= 6:
            continue
        for stmt in dbmod.split_sql_statements(sql):
            raw.execute(stmt)
        raw.execute("INSERT INTO schema_version(version) VALUES (?)", (version,))
    raw.execute("INSERT INTO fts_redaction(text, work_label, path) VALUES (?,?,?)",
                ("Dever de lealdade antigo", "LSA", "art-155"))
    raw.commit()
    raw.close()

    conn = connect(path)
    assert conn.execute("SELECT 6 FROM schema_version").fetchone()[0] == 6
    rows = conn.execute("SELECT rowid, text, rubrica, work_label, path FROM fts_redaction").fetchall()
    assert [tuple(r) for r in rows] == [(1, "Dever de lealdade antigo", None, "LSA", "art-155")]
    assert [h["path"] for h in repo.search_redactions(conn, "lealdade")] == ["art-155"]
    conn.close()


# --- mojibake ---

@pytest.mark.parametrize(
    "correto",
    [
        "Resolução CVM nº 80, de 22 de março de 2022",
        "Instrução CVM nº 358, de 3 de janeiro de 2002",
        "Parecer de Orientação CVM nº 37",
        "Ação ordinária do Órgão Ofício-Circular",
        "‘Ativo’ e “passivo” da companhia",
    ],
)
def test_mojibake_real_volta_ao_texto_original(correto):
    assert corrigir_mojibake(_mojibake(correto)) == correto


def test_mojibake_exemplo_literal_do_defeito():
    assert corrigir_mojibake("ResoluÃ§Ã£o CVM nÂº 80, de 22 de marÃ§o de 2022") == (
        "Resolução CVM nº 80, de 22 de março de 2022"
    )
    assert corrigir_mojibake("InstruÃ§Ã£o CVM nÂº 358") == "Instrução CVM nº 358"


@pytest.mark.parametrize(
    "correto",
    [
        "AÇÃO",
        "Ação",
        "Resolução CVM nº 80",
        "Instrução CVM 358/2002",
        "Lei 6.404/1976",
        "câmara de arbitragem",
        "Órgão Ã",
        "",
    ],
)
def test_texto_correto_nao_e_alterado(correto):
    assert corrigir_mojibake(correto) == correto


def test_corrigir_rotulos_so_toca_cvm_e_mantem_fts_coerente(tmp_path):
    conn = connect(tmp_path / "v.sqlite3")
    # Rótulos já gravados antes da correção: inseridos direto, sem passar por upsert_work.
    conn.execute("INSERT INTO work(id, jurisdiction, authority, kind, number, year, label) "
                 "VALUES ('w-cvm','BR','cvm','resolucao','80',2022,?)", (_mojibake("Resolução CVM 80"),))
    conn.execute("INSERT INTO work(id, jurisdiction, authority, kind, number, year, label) "
                 "VALUES ('w-lei','BR','planalto','lei','6404',1976,?)", (_mojibake("Lei Ação"),))
    repo.index_redaction(conn, text="texto", work_label=_mojibake("Resolução CVM 80"), path="art-1")
    assert corrigir_rotulos(conn) == 1
    assert conn.execute("SELECT label FROM work WHERE id='w-cvm'").fetchone()[0] == "Resolução CVM 80"
    assert conn.execute("SELECT label FROM work WHERE id='w-lei'").fetchone()[0] == _mojibake("Lei Ação")
    assert conn.execute("SELECT work_label FROM fts_redaction").fetchone()[0] == "Resolução CVM 80"
    assert corrigir_rotulos(conn) == 0
    conn.close()


def test_upsert_work_cvm_grava_rotulo_corrigido(tmp_path):
    conn = connect(tmp_path / "v.sqlite3")
    wid = repo.upsert_work(conn, jurisdiction="BR", authority="cvm", kind="resolucao",
                           number="44", year=2021, label=_mojibake("Resolução CVM 44"))
    assert conn.execute("SELECT label FROM work WHERE id=?", (wid,)).fetchone()[0] == "Resolução CVM 44"
    conn.close()


# --- rubrica capturada pelo parser (pendência de M11) ---

def _lsa_completa(tmp_path, monkeypatch):
    from freoa_verifica.aliases import WorkKey
    from freoa_verifica.parsers.planalto import parse_planalto
    from freoa_verifica.service import Verifica
    from tests.fixture_util import load_fixture, load_meta

    monkeypatch.setenv("FV_OFFLINE", "1")
    body = load_fixture("planalto_lei_6404_1976")
    doc = parse_planalto(body, base_url="https://www.planalto.gov.br/ccivil_03/leis/")
    svc = Verifica(home=tmp_path)
    svc.indexar_obra(source_id="planalto", work_key=WorkKey("federal", "lei", "6404", 1976), document=doc,
                     body=body, url=load_meta()["planalto_lei_6404_1976"]["url"],
                     fetched_at="2026-10-18T00:00:00+00:00", work_date="1976-12-15", label="Lei nº 6.404/1976")
    return svc, doc


def test_parser_captura_rubrica_do_artigo(tmp_path, monkeypatch):
    svc, doc = _lsa_completa(tmp_path, monkeypatch)
    try:
        assert doc.provision("art153").rubrica == "Dever de Diligência"
        assert doc.provision("art155").rubrica == "Dever de Lealdade"
        assert doc.provision("art155").current_text().startswith("O administrador deve servir com lealdade")
    finally:
        svc.close()


def test_busca_por_rubrica_acha_art_155(tmp_path, monkeypatch):
    svc, _ = _lsa_completa(tmp_path, monkeypatch)
    try:
        # o texto do art. 155 não contém "dever de lealdade": só a rubrica o encontra
        assert "dever de lealdade" not in svc.obter_dispositivo(citacao="Lei 6.404/1976, art. 155")["texto"].lower()
        out = svc.buscar_legislacao("dever de lealdade")
        assert any(i.get("caminho", i.get("path")) == "art155" for i in out["itens"]), out["itens"][:3]
    finally:
        svc.close()


def test_modelo_persistido_sem_rubrica_ainda_carrega():
    from dataclasses import asdict
    from freoa_verifica.parsers.model import ParsedDocument, Provision, Redaction, document_from_dict

    doc = ParsedDocument("planalto", "1", "t", None, "", provisions=[Provision("art1", "Art. 1", "", [], [Redaction("x", False, 0)])])
    legado = asdict(doc)
    for p in legado["provisions"]:
        p.pop("rubrica")
    assert document_from_dict(legado).provisions[0].rubrica is None
