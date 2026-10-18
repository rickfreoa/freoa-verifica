"""Testes do armazenamento SQLite + blobs."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from freoa_verifica.store import blobs
from freoa_verifica.store.db import apply_migrations, connect, split_sql_statements
from freoa_verifica.store import repo
from freoa_verifica.transport import Response


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    home = tmp_path / "fv-home"
    home.mkdir()
    monkeypatch.setenv("FV_HOME", str(home))
    return home / "verifica.sqlite3"


@pytest.fixture
def conn(db_path):
    c = connect(db_path)
    yield c
    c.close()


def _response(
    body: bytes = b"payload",
    *,
    url: str = "https://example.com/a",
    fetched_at: str | None = None,
    sha256: str | None = None,
) -> Response:
    digest = sha256 if sha256 is not None else hashlib.sha256(body).hexdigest()
    return Response(
        url=url,
        final_url=url,
        status=200,
        headers={"content-type": "text/plain"},
        body=body,
        sha256=digest,
        fetched_at=fetched_at or datetime.now(timezone.utc).isoformat(),
        redirects=[],
        mime="text/plain",
    )


def test_migration_from_scratch(conn):
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    expected = {
        "schema_version",
        "source",
        "work",
        "alias",
        "edition",
        "capture",
        "extract",
        "provision",
        "redaction",
        "occurrence",
        "event",
        "relation",
        "proceeding",
        "decision",
        "decision_document",
        "theme",
        "run",
        "parsed_document",
    }
    assert expected <= tables
    versions = {row[0] for row in conn.execute("SELECT version FROM schema_version")}
    assert {1, 2} <= versions


def test_reopen_idempotent(db_path):
    c1 = connect(db_path)
    c1.execute(
        "INSERT INTO source(id, authority, profile, hosts_json) VALUES ('s1','x','p','[]')"
    )
    c1.commit()
    c1.close()
    c2 = connect(db_path)
    apply_migrations(c2)  # segunda passagem
    row = c2.execute("SELECT id FROM source WHERE id='s1'").fetchone()
    assert row is not None
    versions = {row[0] for row in c2.execute("SELECT version FROM schema_version")}
    assert versions == {1, 2, 3, 4, 5}
    c2.close()


def test_migration_rollback_on_bad_sql(tmp_path, monkeypatch):
    """SQL defeituoso no meio da migração não deixa tabelas sem versão."""
    from freoa_verifica.store import db as dbmod

    good = """
CREATE TABLE source (
    id TEXT PRIMARY KEY,
    authority TEXT NOT NULL,
    profile TEXT NOT NULL,
    hosts_json TEXT NOT NULL
);
CREATE TABLE work (
    id TEXT PRIMARY KEY,
    jurisdiction TEXT NOT NULL,
    authority TEXT NOT NULL,
    kind TEXT NOT NULL,
    number TEXT NOT NULL,
    year INTEGER NOT NULL,
    UNIQUE (jurisdiction, authority, kind, number, year)
);
"""
    bad = good + "\nCREATE TABLE broken (id TEXT PRIMARY KEY);\nTHIS IS NOT SQL;\n"
    monkeypatch.setattr(dbmod, "_migration_files", lambda: [(1, bad)])
    path = tmp_path / "bad.sqlite3"
    with pytest.raises(sqlite3.Error):
        connect(path)
    conn = sqlite3.connect(str(path))
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        assert "source" not in tables
        assert "work" not in tables
        if "schema_version" in tables:
            assert conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 0
    finally:
        conn.close()

    # Nova tentativa com SQL válido deve funcionar (sem 'table already exists')
    monkeypatch.setattr(dbmod, "_migration_files", lambda: [(1, good)])
    c2 = connect(path)
    try:
        assert c2.execute("SELECT COUNT(*) FROM source").fetchone()[0] == 0
        assert 1 in [r[0] for r in c2.execute("SELECT version FROM schema_version")]
    finally:
        c2.close()


def test_split_sql_statements_skips_comments():
    stmts = split_sql_statements("-- c\nCREATE TABLE t(id INT);\n-- x\nCREATE TABLE u(id INT);")
    assert len(stmts) == 2


def test_repeated_capture(conn, tmp_path, monkeypatch):
    monkeypatch.setenv("FV_HOME", str(tmp_path / "home2"))
    (tmp_path / "home2").mkdir()
    conn.execute(
        "INSERT INTO source(id, authority, profile, hosts_json) VALUES ('src','planalto','html','[]')"
    )
    conn.commit()
    resp = _response(b"same-bytes", fetched_at="2026-01-01T00:00:00+00:00")
    home = Path(tmp_path / "home2")
    id1 = repo.save_capture(conn, resp, "src", home=home)
    id2 = repo.save_capture(conn, resp, "src", home=home)
    assert id1 == id2
    count = conn.execute("SELECT COUNT(*) FROM capture").fetchone()[0]
    assert count == 1


def test_capture_identity_conflict_different_source(conn, tmp_path, monkeypatch):
    home = tmp_path / "home-id"
    home.mkdir()
    monkeypatch.setenv("FV_HOME", str(home))
    conn.execute(
        "INSERT INTO source(id, authority, profile, hosts_json) VALUES ('s1','a','p','[]')"
    )
    conn.execute(
        "INSERT INTO source(id, authority, profile, hosts_json) VALUES ('s2','b','p','[]')"
    )
    conn.commit()
    resp = _response(b"shared", fetched_at="2026-01-01T00:00:00+00:00")
    repo.save_capture(conn, resp, "s1", home=home)
    with pytest.raises(repo.IdentityConflict):
        repo.save_capture(conn, resp, "s2", home=home)


def test_save_capture_validates_sha_before_blob(conn, tmp_path, monkeypatch):
    home = tmp_path / "home-sha"
    home.mkdir()
    monkeypatch.setenv("FV_HOME", str(home))
    conn.execute(
        "INSERT INTO source(id, authority, profile, hosts_json) VALUES ('src','a','p','[]')"
    )
    conn.commit()
    resp = _response(b"bytes", sha256="0" * 64)
    with pytest.raises(ValueError, match="sha256"):
        repo.save_capture(conn, resp, "src", home=home)
    assert list(home.joinpath("blobs").glob("*/*/*")) == [] or not (home / "blobs").exists()


def test_capture_immutable(conn, tmp_path, monkeypatch):
    home = tmp_path / "home-imm"
    home.mkdir()
    monkeypatch.setenv("FV_HOME", str(home))
    conn.execute(
        "INSERT INTO source(id, authority, profile, hosts_json) VALUES ('src','a','p','[]')"
    )
    conn.commit()
    cid = repo.save_capture(conn, _response(b"imm"), "src", home=home)
    with pytest.raises(sqlite3.IntegrityError, match="imutavel"):
        conn.execute("UPDATE capture SET mime='x' WHERE id=?", (cid,))
    with pytest.raises(sqlite3.IntegrityError, match="imutavel"):
        conn.execute("DELETE FROM capture WHERE id=?", (cid,))


def test_decision_unique_per_court_official_id(conn):
    d1 = repo.upsert_decision(conn, court="STJ", kind="acordao", official_id="OID-1")
    d2 = repo.upsert_decision(conn, court="STJ", kind="acordao", official_id="OID-1")
    assert d1 == d2
    d3 = repo.upsert_decision(conn, court="STF", kind="acordao", official_id="OID-1")
    assert d3 != d1
    count = conn.execute(
        "SELECT COUNT(*) FROM decision WHERE official_id='OID-1'"
    ).fetchone()[0]
    assert count == 2


def test_alias_identity_conflict(conn):
    w1 = repo.upsert_work(
        conn, jurisdiction="BR", authority="planalto", kind="lei", number="1", year=2000
    )
    w2 = repo.upsert_work(
        conn, jurisdiction="BR", authority="planalto", kind="lei", number="2", year=2000
    )
    repo.add_alias(conn, w1, scheme="urn", value="lei:1")
    with pytest.raises(repo.IdentityConflict):
        repo.add_alias(conn, w2, scheme="urn", value="lei:1")


def test_corrupted_blob_detected(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_HOME", str(tmp_path))
    digest = blobs.put_blob(b"integro", home=tmp_path)
    path = blobs.blob_path(digest, home=tmp_path)
    path.write_bytes(b"corrompido")
    with pytest.raises(blobs.BlobCorruption):
        blobs.get_blob(digest, home=tmp_path)


def test_fk_violation(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO capture("
            "id, source_id, url, final_url, fetched_at, status, headers_json, "
            "redirects_json, sha256, size"
            ") VALUES ('c1','missing','u','u','t',200,'{}','[]','abc',0)"
        )
        conn.commit()


def test_fts_with_and_without_accent(conn):
    repo.index_redaction(
        conn,
        text="O Código Civil estabelece a boa-fé objetiva.",
        work_label="CC",
        path="art-422",
    )
    repo.index_decision(
        conn,
        ementa="Recurso especial sobre responsabilidade civil.",
        inteiro_teor="Voto do relator.",
        court="STJ",
        class_="REsp",
    )
    hits = repo.search_redactions(conn, "Código", limit=5)
    assert hits
    assert "boa-fé" in hits[0]["text"] or "Código" in hits[0]["text"]
    hits2 = repo.search_redactions(conn, "codigo", limit=5)
    assert hits2
    dec = repo.search_decisions(conn, "responsabilidade", filtros={"court": "STJ"}, limit=5)
    assert dec
    assert dec[0]["court"] == "STJ"


def test_integrity_check(conn):
    result = conn.execute("PRAGMA integrity_check").fetchone()[0]
    assert result == "ok"


def test_upsert_work_and_provision_unique(conn):
    wid = repo.upsert_work(
        conn,
        jurisdiction="BR",
        authority="planalto",
        kind="lei",
        number="10406",
        year=2002,
        label="Código Civil",
    )
    wid2 = repo.upsert_work(
        conn,
        jurisdiction="BR",
        authority="planalto",
        kind="lei",
        number="10406",
        year=2002,
    )
    assert wid == wid2
    p1 = repo.upsert_provision(conn, wid, scope="", path="art-1")
    p2 = repo.upsert_provision(conn, wid, scope="", path="art-1")
    assert p1 == p2
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO provision(id, work_id, scope, path) VALUES ('x', ?, '', 'art-1')",
            (wid,),
        )
        conn.commit()
