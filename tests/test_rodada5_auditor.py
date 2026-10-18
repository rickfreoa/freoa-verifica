"""Rodada 5 (auditor Codex): A7 por documento (012), status com falha de fonte, orçamento na busca inicial."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from freoa_verifica import derivados
from freoa_verifica.aliases import WorkKey
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.parsers.model import ParsedDocument, Provision, Redaction
from freoa_verifica.service import Verifica

KEY = WorkKey("federal", "lei", "9999", 2000)


def _doc(*textos):
    provs = [Provision(f"art{i}", f"art{i}", "", redactions=[Redaction(t, False, 0, [])])
             for i, t in enumerate(textos, 1)]
    return ParsedDocument("synthetic", "9999", "Lei 9.999/2000", None, "x", provisions=provs, issues=[])


def _indexar(s, doc, corpo, quando, alvo="fts_redaction", src="planalto"):
    return s.indexar_obra(source_id=src, work_key=KEY, document=doc, body=corpo,
                          url="https://example.invalid/s", label="Lei 9.999/2000",
                          fetched_at=quando, fts_alvo=alvo)


def test_a7_012_marca_por_documento_obra_com_canonica_e_candidata(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()
    t1 = datetime(2026, 2, 1, tzinfo=timezone.utc).isoformat()
    with Verifica(tmp_path) as s:
        a = _indexar(s, _doc("texto A"), b"A", t0)
        b = _indexar(s, _doc("texto A", "texto B exclusivo"), b"B", t1, alvo="fts_staging")
        with s.conn:  # reproduz o home versão 9: sem marca, B só no staging
            s.conn.execute("ALTER TABLE parsed_document DROP COLUMN candidato_ao_vivo")
            s.conn.execute("DELETE FROM schema_version WHERE version>=10")
            s.conn.execute("DELETE FROM fts_redaction")
            s.conn.execute("DELETE FROM fts_staging")
            s.conn.execute("INSERT INTO fts_redaction(text, rubrica, work_label, path) VALUES "
                           "('texto A', NULL, 'Lei 9.999/2000', 'art1')")
            s.conn.execute("INSERT INTO fts_staging(text, work_label, path) VALUES "
                           "('texto B exclusivo', 'Lei 9.999/2000', 'art2')")
    with Verifica(tmp_path) as s:  # migra 010, 011, 012
        marcas = dict(s.conn.execute("SELECT capture_id, candidato_ao_vivo FROM parsed_document").fetchall())
        assert marcas == {a.capture_id: 0, b.capture_id: 1}
        with s.conn:
            derivados.reindexar_fts(s.conn)
        assert s.conn.execute("select count(*) from fts_redaction where text like '%exclusivo%'").fetchone()[0] == 0
        off = s.buscar_legislacao("exclusivo", fonte="__somente_local__")
        assert not [i for i in off["itens"] if not i.get("candidato_ao_vivo")]
        assert s.buscar_legislacao("texto A", fonte="__somente_local__")["itens"][0]["candidato_ao_vivo"] is False
        with s.conn:  # idempotente
            s.conn.execute("DELETE FROM schema_version WHERE version=12")
    with Verifica(tmp_path) as s:
        assert s.conn.execute("select count(*) from parsed_document where candidato_ao_vivo=1").fetchone()[0] == 1


class _Falha:
    id = "cvm_normas"

    def search(self, q, **f):
        raise Unavailable("http_503")


class _Lento:
    id = "cvm_normas"

    def search(self, q, **f):
        time.sleep(0.4)
        return []


def test_legislacao_fonte_falha_nao_volta_ok(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as s:
        monkeypatch.setattr(s, "_get", lambda _id: _Falha())
        out = s.buscar_legislacao("fato relevante", fonte="cvm_normas")
        assert out["status"] == "indisponivel" and out["motivo"] == "http_503" and out["itens"] == []


def test_legislacao_falha_com_itens_locais_e_parcial(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as s:
        _indexar(s, _doc("texto A"), b"A", datetime.now(timezone.utc).isoformat(), src="cvm_normas")
        monkeypatch.setattr(s, "_get", lambda _id: _Falha())
        out = s.buscar_legislacao("texto", fonte="cvm_normas")
        assert out["itens"] and out["status"] == "parcial"


def test_normas_e_juris_fonte_falha(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as s:
        monkeypatch.setattr(s, "_get", lambda _id: _Falha())
        assert s.buscar_normas_cvm("x")["status"] == "indisponivel"
        assert s.buscar_normas_bcb("x")["status"] == "indisponivel"
        j = s.pesquisar_jurisprudencia("acordo de acionistas", tribunais=["stj"])
        assert j["itens"] == [] and j["status"] == "indisponivel" and j["motivo"] == "http_503"


def test_orcamento_cobre_a_busca_inicial(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as s:
        monkeypatch.setattr(s, "_get", lambda _id: _Lento())
        t = time.monotonic()
        out = s._buscar_normas("cvm_normas", "x", None, orcamento_s=0.03)
        assert time.monotonic() - t < 0.2
        assert out["status"] == "indisponivel" and out["motivo"] == "orcamento"


# ---- rodada 6 ----
import json as _json
import sqlite3 as _sq
from freoa_verifica import derivados as _der
from freoa_verifica.store import db as _db


def _home_esquema9(tmp_path, *, marca=False):
    """Home de build não publicado (esquema 8/9) com candidato subconjunto do canônico, sem marca."""
    con = _sq.connect(tmp_path / "verifica.sqlite3")
    con.row_factory = _sq.Row
    for v, sql in _db._migration_files():
        if v <= 9:
            for st in _db.split_sql_statements(sql):
                con.execute(st)
    con.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))")
    for v in range(1, 10):
        con.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (?)", (v,))
    con.execute("INSERT INTO fts_staging(text, work_label, path) VALUES ('texto A','Lei 1','art. 1')")
    con.commit()
    con.close()


def test_esquema9_com_staging_sem_marca_recusa_reconstruir(tmp_path):
    _home_esquema9(tmp_path)
    antes = (tmp_path / "verifica.sqlite3").read_bytes()
    with Verifica(tmp_path) as s:
        out = s.reconstruir_acervo()
        assert out["status"] == "erro" and out["motivo"] == "ACERVO_DE_VERSAO_NAO_PUBLICADA"
        assert _der.REASON_NAO_PUBLICADA in s.acervo_status()["motivos"]
        assert s.snapshot_install(tmp_path / "nada")["motivo"] == "ACERVO_DE_VERSAO_NAO_PUBLICADA"
    assert not list(tmp_path.glob(".reconstruir-*")) and len(antes) > 0


def test_home_v102_sem_staging_reconstroi(tmp_path):
    con = _sq.connect(tmp_path / "verifica.sqlite3")
    for v, sql in _db._migration_files():
        if v <= 5:
            for st in _db.split_sql_statements(sql):
                con.execute(st)
    con.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))")
    for v in range(1, 6):
        con.execute("INSERT INTO schema_version(version) VALUES (?)", (v,))
    con.commit()
    con.close()
    with Verifica(tmp_path) as s:
        assert not _der.origem_nao_publicada(s.conn)
        r = s.reconstruir_acervo(); assert r.get("motivo") != "ACERVO_DE_VERSAO_NAO_PUBLICADA", r


def test_captura_candidata_nao_substitui_canonica(tmp_path):
    with Verifica(tmp_path) as s:
        c = s.conn
        c.execute("INSERT INTO work(id,jurisdiction,authority,kind,number,year,label) VALUES ('w','br','federal','lei','1',2000,'Lei 1')")
        for cid, quando, cand, txt in (("c1", "2026-01-01", 0, "texto canonico completo"), ("c2", "2026-02-01", 1, "subconjunto")):
            c.execute("INSERT INTO capture(id,source_id,url,final_url,sha256,fetched_at,status,headers_json,mime) VALUES (?,?,?,?,?,?,?,?,?)",
                      (cid, "s", "u", "u", cid, quando, 200, "{}", "x")) if False else None
        # usa o caminho normal: indexa canônica e depois candidata
        from freoa_verifica.aliases import WorkKey
        from freoa_verifica.parsers.model import ParsedDocument, Provision, Redaction
        def doc(t):
            return ParsedDocument(profile="x", parser_version="t", title="t", ementa=None, text="t", provisions=[Provision(path="art. 1", label="Art. 1", scope="main", redactions=[Redaction(text=t, struck=False, order=0)])])
        c.execute("DELETE FROM work")
        s.indexar_obra(source_id="s", work_key=WorkKey("federal", "lei", "1", 2000), document=doc("texto canonico completo"),
                       body=b"a", url="u1", fetched_at="2026-01-01T00:00:00+00:00", label="Lei 1")
        s.indexar_obra(source_id="s", work_key=WorkKey("federal", "lei", "1", 2000), document=doc("subconjunto"),
                       body=b"b", url="u2", fetched_at="2026-02-01T00:00:00+00:00", label="Lei 1", fts_alvo="fts_staging")
        _der.reindexar_fts(c)
        textos = [r[0] for r in c.execute("SELECT text FROM fts_redaction")]
        assert textos == ["texto canonico completo"]


def test_indexacao_lenta_que_ignora_prazo_e_abandonada(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)

    class C:
        def search(self, q, **kw):
            from freoa_verifica.connectors.base import Candidate
            return [Candidate(source_id="cvm_normas", key="1", title="Lei 1", url="u", snippet="s", metadata={})]
    with Verifica(tmp_path) as s:
        monkeypatch.setattr(s, "_get", lambda _id: C())
        gravou = []

        def lento(connector, cand):
            time.sleep(1.0)  # ignora PRAZO
            from freoa_verifica.aliases import WorkKey
            from freoa_verifica.parsers.model import ParsedDocument, Provision, Redaction
            try:
                s.indexar_obra(source_id="s", work_key=WorkKey("federal", "lei", "1", 2000),
                               document=ParsedDocument(profile="x", parser_version="t", title="t", ementa=None, text="t", provisions=[Provision(path="art. 1", label="Art. 1", scope="main", redactions=[Redaction(text="zzz", struck=False, order=0)])]),
                               body=b"a", url="u", label="Lei 1", fts_alvo="fts_staging")
                gravou.append(1)
            except Exception:  # noqa: BLE001
                pass
            return {"capture_id": "x", "trecho": ""}
        monkeypatch.setattr(s, "_index_candidate_legis", lento)
        t = time.monotonic()
        # folga para runners lentos (Windows na CI): o que se testa é o abandono do item lento
        out = s._buscar_normas("cvm_normas", "x", None, orcamento_s=0.3)
        assert time.monotonic() - t < 0.9
        assert out["itens"][0]["nao_indexado"] and out["itens"][0]["motivo"] == "orcamento"
        time.sleep(1.2)
        assert not gravou
        assert s.conn.execute("SELECT COUNT(*) FROM fts_staging").fetchone()[0] == 0
