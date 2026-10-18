"""Funções finas de persistência sobre o esquema v2."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from freoa_verifica.ids import new_ulid
from freoa_verifica.store import blobs
from freoa_verifica.store.db import data_home
from freoa_verifica.transport import Response


class IdentityConflict(Exception):
    """Identidade já existe com atributos incompatíveis."""


def save_capture(
    conn: sqlite3.Connection,
    resp: Response,
    source_id: str,
    *,
    home: Path | None = None,
    edition_id: str | None = None,
    outcome: str | None = None,
) -> str:
    """Persiste blob e linha de capture; mesma tripla (sha256, url, fetched_at) não duplica."""
    digest = hashlib.sha256(resp.body).hexdigest()
    if digest != resp.sha256:
        raise ValueError("sha256 da resposta diverge do corpo")
    size = len(resp.body)
    blobs.put_blob(resp.body, home=home or data_home())
    capture_id = new_ulid()
    conn.execute(
        "INSERT INTO capture("
        "id, source_id, edition_id, url, final_url, fetched_at, status, "
        "headers_json, redirects_json, sha256, mime, size, outcome"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(sha256, url, fetched_at) DO NOTHING",
        (
            capture_id,
            source_id,
            edition_id,
            resp.url,
            resp.final_url,
            resp.fetched_at,
            resp.status,
            json.dumps(resp.headers, ensure_ascii=False, sort_keys=True),
            json.dumps(resp.redirects, ensure_ascii=False),
            digest,
            resp.mime,
            size,
            outcome,
        ),
    )
    row = conn.execute(
        "SELECT id, source_id FROM capture WHERE sha256=? AND url=? AND fetched_at=?",
        (digest, resp.url, resp.fetched_at),
    ).fetchone()
    if row is None:
        raise RuntimeError("capture ausente após INSERT")
    if row["source_id"] != source_id:
        conn.rollback()
        raise IdentityConflict(
            f"captura {digest} já registrada sob fonte {row['source_id']}"
        )
    conn.commit()
    return row["id"]


def get_capture(conn: sqlite3.Connection, capture_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM capture WHERE id=?", (capture_id,)).fetchone()
    return dict(row) if row else None


def upsert_work(
    conn: sqlite3.Connection,
    *,
    jurisdiction: str,
    authority: str,
    kind: str,
    number: str,
    year: int,
    label: str | None = None,
    work_id: str | None = None,
) -> str:
    wid = work_id or new_ulid()
    conn.execute(
        "INSERT INTO work(id, jurisdiction, authority, kind, number, year, label) "
        "VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(jurisdiction, authority, kind, number, year) DO NOTHING",
        (wid, jurisdiction, authority, kind, number, year, label),
    )
    row = conn.execute(
        "SELECT id, label FROM work WHERE jurisdiction=? AND authority=? AND kind=? AND number=? AND year=?",
        (jurisdiction, authority, kind, number, year),
    ).fetchone()
    if row is None:
        raise RuntimeError("work ausente após INSERT")
    if label is not None and row["label"] != label:
        conn.execute("UPDATE work SET label=? WHERE id=?", (label, row["id"]))
    conn.commit()
    return row["id"]


def add_alias(
    conn: sqlite3.Connection,
    work_id: str,
    *,
    scheme: str,
    value: str,
    origin: str | None = None,
    resolution_status: str = "generated",
) -> str:
    alias_id = new_ulid()
    conn.execute(
        "INSERT INTO alias(id, work_id, scheme, value, origin, resolution_status) "
        "VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(scheme, value) DO NOTHING",
        (alias_id, work_id, scheme, value, origin, resolution_status),
    )
    row = conn.execute(
        "SELECT id, work_id FROM alias WHERE scheme=? AND value=?",
        (scheme, value),
    ).fetchone()
    if row is None:
        raise RuntimeError("alias ausente após INSERT")
    if row["work_id"] != work_id:
        conn.rollback()
        raise IdentityConflict(
            f"alias {scheme}:{value} já aponta para obra {row['work_id']}"
        )
    conn.commit()
    return row["id"]


def upsert_provision(
    conn: sqlite3.Connection,
    work_id: str,
    *,
    scope: str,
    path: str,
    parent_id: str | None = None,
    provision_id: str | None = None,
) -> str:
    pid = provision_id or new_ulid()
    conn.execute(
        "INSERT INTO provision(id, work_id, scope, path, parent_id) VALUES (?,?,?,?,?) "
        "ON CONFLICT(work_id, scope, path) DO NOTHING",
        (pid, work_id, scope, path, parent_id),
    )
    row = conn.execute(
        "SELECT id FROM provision WHERE work_id=? AND scope=? AND path=?",
        (work_id, scope, path),
    ).fetchone()
    if row is None:
        raise RuntimeError("provision ausente após INSERT")
    conn.commit()
    return row["id"]


def add_redaction(conn: sqlite3.Connection, provision_id: str, text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    rid = new_ulid()
    conn.execute(
        "INSERT INTO redaction(id, provision_id, text, text_sha256) VALUES (?,?,?,?)",
        (rid, provision_id, text, digest),
    )
    conn.commit()
    return rid


def add_event(
    conn: sqlite3.Connection,
    *,
    kind: str,
    provision_id: str,
    state: str,
    redaction_id: str | None = None,
    source_work_id: str | None = None,
    publication_date: str | None = None,
    effective_date: str | None = None,
    effects_date: str | None = None,
    scope_json: str | None = None,
    rule: str | None = None,
    evidence_occurrence_id: str | None = None,
) -> str:
    eid = new_ulid()
    conn.execute(
        "INSERT INTO event("
        "id, kind, provision_id, redaction_id, source_work_id, publication_date, "
        "effective_date, effects_date, scope_json, rule, evidence_occurrence_id, state"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            eid,
            kind,
            provision_id,
            redaction_id,
            source_work_id,
            publication_date,
            effective_date,
            effects_date,
            scope_json,
            rule,
            evidence_occurrence_id,
            state,
        ),
    )
    conn.commit()
    return eid


def upsert_decision(
    conn: sqlite3.Connection,
    *,
    court: str,
    kind: str,
    identity_status: str = "provisional",
    proceeding_id: str | None = None,
    class_: str | None = None,
    number: str | None = None,
    uf: str | None = None,
    organ: str | None = None,
    rapporteur: str | None = None,
    judgment_date: str | None = None,
    publication_date: str | None = None,
    official_id: str | None = None,
    authority_attrs_json: str | None = None,
    authority_label: str | None = None,
    decision_id: str | None = None,
) -> str:
    did = decision_id or new_ulid()
    if official_id is not None:
        conn.execute(
            "INSERT INTO decision("
            "id, proceeding_id, court, class, number, uf, organ, rapporteur, "
            "judgment_date, publication_date, kind, official_id, identity_status, "
            "authority_attrs_json, authority_label"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(court, official_id) DO NOTHING",
            (
                did,
                proceeding_id,
                court,
                class_,
                number,
                uf,
                organ,
                rapporteur,
                judgment_date,
                publication_date,
                kind,
                official_id,
                identity_status,
                authority_attrs_json,
                authority_label,
            ),
        )
        row = conn.execute(
            "SELECT id FROM decision WHERE court=? AND official_id=?",
            (court, official_id),
        ).fetchone()
        if row is None:
            raise RuntimeError("decision ausente após INSERT")
        conn.commit()
        return row["id"]
    conn.execute(
        "INSERT INTO decision("
        "id, proceeding_id, court, class, number, uf, organ, rapporteur, "
        "judgment_date, publication_date, kind, official_id, identity_status, "
        "authority_attrs_json, authority_label"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            did,
            proceeding_id,
            court,
            class_,
            number,
            uf,
            organ,
            rapporteur,
            judgment_date,
            publication_date,
            kind,
            official_id,
            identity_status,
            authority_attrs_json,
            authority_label,
        ),
    )
    conn.commit()
    return did


def index_redaction(
    conn: sqlite3.Connection,
    *,
    text: str,
    work_label: str,
    path: str,
) -> None:
    conn.execute(
        "INSERT INTO fts_redaction(text, work_label, path) VALUES (?,?,?)",
        (text, work_label, path),
    )
    conn.commit()


def index_decision(
    conn: sqlite3.Connection,
    *,
    ementa: str = "",
    inteiro_teor: str = "",
    court: str = "",
    class_: str = "",
    official_id: str | None = None,
) -> None:
    if official_id is not None:
        conn.execute("DELETE FROM fts_decision WHERE court=? AND official_id=?",
                     (court, official_id))
    conn.execute(
        "INSERT INTO fts_decision(ementa, inteiro_teor, court, class, official_id) VALUES (?,?,?,?,?)",
        (ementa, inteiro_teor, court, class_, official_id),
    )
    conn.commit()


def search_redactions(conn: sqlite3.Connection, q: str, limit: int = 10) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT text, work_label, path, bm25(fts_redaction) AS score "
        "FROM fts_redaction WHERE fts_redaction MATCH ? "
        "ORDER BY score LIMIT ?",
        (q, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def search_decisions(
    conn: sqlite3.Connection,
    q: str,
    filtros: dict[str, str] | None = None,
    limit: int = 10,
    courts: list[str] | None = None,
) -> list[dict[str, Any]]:
    filtros = filtros or {}
    clauses = ["fts_decision MATCH ?"]
    params: list[Any] = [q]
    if courts is not None:
        from freoa_verifica.courts import normalize_court

        conn.create_function("fv_court", 1, normalize_court, deterministic=True)
        clauses.append("fv_court(court) IN (" + ",".join("?" for _ in courts) + ")")
        params.extend(normalize_court(court) for court in courts)
    if court := filtros.get("court"):
        clauses.append("court = ?")
        params.append(court)
    if class_ := filtros.get("class"):
        clauses.append("class = ?")
        params.append(class_)
    params.append(limit)
    sql = (
        "SELECT ementa, inteiro_teor, court, class, official_id, bm25(fts_decision) AS score "
        f"FROM fts_decision WHERE {' AND '.join(clauses)} "
        "ORDER BY score LIMIT ?"
    )
    rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def rebuild_decision_index(conn: sqlite3.Connection) -> None:
    """Reconstitui o índice derivado dos documentos, uma entrada por decisão."""
    conn.execute("DELETE FROM fts_decision")
    conn.execute("""
        WITH latest AS (
            SELECT dd.*, ROW_NUMBER() OVER (
                PARTITION BY decision_id, kind ORDER BY created_at DESC, id DESC
            ) AS rn FROM decision_document dd
        ), texts AS (
            SELECT decision_id,
                MAX(CASE WHEN kind='ementa' THEN text END) AS ementa,
                MAX(CASE WHEN kind='inteiro_teor' THEN text END) AS inteiro_teor
            FROM latest WHERE rn=1 GROUP BY decision_id
        )
        INSERT INTO fts_decision(ementa, inteiro_teor, court, class, official_id)
        SELECT COALESCE(t.ementa,''), COALESCE(t.inteiro_teor,''),
               d.court, COALESCE(d.class,''), d.official_id
        FROM decision d JOIN texts t ON t.decision_id=d.id
        WHERE COALESCE(NULLIF(t.ementa,''),t.inteiro_teor,'') != ''
    """)


def search_local_decisions(
    conn: sqlite3.Connection, q: str, *, courts: list[str] | None,
    desde: str | None, ate: str | None, autoridade_min: str | None,
    limit: int, offset: int,
) -> list[dict[str, Any]]:
    from freoa_verifica.courts import normalize_court

    conn.create_function("fv_court", 1, normalize_court, deterministic=True)
    clauses = ["fts_decision MATCH ?"]
    params: list[Any] = [q]
    if courts is not None:
        clauses.append("fv_court(fts_decision.court) IN (" + ",".join("?" for _ in courts) + ")")
        params.extend(courts)
    date = "COALESCE(NULLIF(d.judgment_date,''), d.publication_date)"
    authority = "fv_authority(fts_decision.court, fts_decision.class, d.organ)"
    for bound, op in [(desde, ">="), (ate, "<=")]:
        if bound:
            clauses.append(f"{date} {op} ?")
            params.append(bound)
    minimum = (autoridade_min or "").strip().upper()[:1]
    if minimum in "ABCDE" and minimum:
        clauses.append(f"{authority} <= ?")
        params.append(minimum)
    params.extend([limit, offset])
    rows = conn.execute(f"""
        SELECT fts_decision.ementa, fts_decision.inteiro_teor,
               fts_decision.court, fts_decision.class, fts_decision.official_id,
               bm25(fts_decision) AS score, d.id AS decision_id,
               d.organ, d.rapporteur, d.number, d.judgment_date, d.publication_date,
               dd.capture_id, dd.sha256, dd.nivel_prova, c.url AS url_oficial,
               (SELECT capture_id FROM decision_document
                WHERE decision_id=d.id AND kind='inteiro_teor'
                ORDER BY created_at DESC, id DESC LIMIT 1) AS full_capture_id
        FROM fts_decision
        LEFT JOIN decision d ON d.court=fts_decision.court
                            AND d.official_id=fts_decision.official_id
        LEFT JOIN decision_document dd ON dd.id=(
            SELECT id FROM decision_document
            WHERE decision_id=d.id
              AND (kind='inteiro_teor' OR (kind='ementa' AND COALESCE(text,'')!=''))
            ORDER BY CASE WHEN kind='ementa' THEN 0 ELSE 1 END,
                     created_at DESC, id DESC LIMIT 1)
        LEFT JOIN capture c ON c.id=dd.capture_id
        WHERE {' AND '.join(clauses)}
        ORDER BY score, {authority}, {date} DESC, d.id, fts_decision.rowid
        LIMIT ? OFFSET ?
    """, params).fetchall()
    return [dict(row) for row in rows]


def _issue_to_dict(issue: Any) -> dict[str, Any]:
    return {
        "code": issue.code,
        "path": issue.path,
        "detail": issue.detail,
        "blocking_scope": issue.blocking_scope,
    }


def _editorial_to_dict(block: Any) -> dict[str, Any]:
    return {
        "text": block.text,
        "span": list(block.span),
        "kind": block.kind,
    }


def persist_parsed_document(
    conn: sqlite3.Connection,
    *,
    capture_id: str,
    document: Any,
    work_id: str,
    work_date: str | None = None,
    amending_act_texts: dict[str, str] | None = None,
) -> str:
    """Persiste parsed_document, extract e occurrences (redaction → extract/capture)."""
    text_sha = hashlib.sha256((document.text or "").encode("utf-8")).hexdigest()
    extract_id = new_ulid()
    conn.execute(
        "INSERT INTO extract(id, capture_id, parser_version, text_sha256, quality) "
        "VALUES (?,?,?,?,?)",
        (extract_id, capture_id, document.parser_version, text_sha, None),
    )
    issues_json = json.dumps(
        [_issue_to_dict(i) for i in document.issues],
        ensure_ascii=False,
    )
    ambiguous_json = json.dumps(list(document.ambiguous_paths), ensure_ascii=False)
    editorial_json = json.dumps(
        [_editorial_to_dict(b) for b in document.editorial_blocks],
        ensure_ascii=False,
    )
    quarantined = 1 if document.quarantined else 0
    conn.execute(
        "INSERT INTO parsed_document("
        "capture_id, profile, parser_version, quarantined, "
        "issues_json, ambiguous_paths_json, editorial_json"
        ") VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(capture_id) DO UPDATE SET "
        "profile=excluded.profile, "
        "parser_version=excluded.parser_version, "
        "quarantined=excluded.quarantined, "
        "issues_json=excluded.issues_json, "
        "ambiguous_paths_json=excluded.ambiguous_paths_json, "
        "editorial_json=excluded.editorial_json",
        (
            capture_id,
            document.profile,
            document.parser_version,
            quarantined,
            issues_json,
            ambiguous_json,
            editorial_json,
        ),
    )
    from dataclasses import asdict
    from freoa_verifica.temporal import build_intervals

    events = {}
    for prov in document.provisions:
        dated, rules, judgment, flags = build_intervals(
            prov, work_date=work_date, amending_act_texts=amending_act_texts,
        )
        events[prov.path] = {
            "intervals": [asdict(d) for d in dated], "rules": rules,
            "needs_judgment": judgment, "flags": flags,
        }
    conn.execute(
        "UPDATE parsed_document SET model_json=?, work_id=?, work_date=?, "
        "amending_texts_json=?, events_json=? WHERE capture_id=?",
        (json.dumps(asdict(document), ensure_ascii=False), work_id, work_date,
         json.dumps(amending_act_texts or {}, ensure_ascii=False),
         json.dumps(events, ensure_ascii=False), capture_id),
    )
    for prov in document.provisions:
        prow = conn.execute(
            "SELECT id FROM provision WHERE work_id=? AND scope=? AND path=?",
            (work_id, prov.scope, prov.path),
        ).fetchone()
        if prow is None:
            continue
        reds = conn.execute(
            "SELECT id, text_sha256 FROM redaction WHERE provision_id=? ORDER BY rowid",
            (prow["id"],),
        ).fetchall()
        captured_hashes = {hashlib.sha256(r.text.encode("utf-8")).hexdigest() for r in prov.redactions}
        for red in reds:
            if red["text_sha256"] not in captured_hashes:
                continue
            existing = conn.execute(
                "SELECT id FROM occurrence WHERE redaction_id=? AND extract_id=?",
                (red["id"], extract_id),
            ).fetchone()
            if existing:
                continue
            conn.execute(
                "INSERT INTO occurrence("
                "id, redaction_id, extract_id, anchor_json, editorial_json"
                ") VALUES (?,?,?,?,?)",
                (new_ulid(), red["id"], extract_id, None, None),
            )
    conn.commit()
    return extract_id


def get_parsed_document(
    conn: sqlite3.Connection, capture_id: str
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM parsed_document WHERE capture_id=?", (capture_id,)
    ).fetchone()
    return dict(row) if row else None


def captures_for_work(conn: sqlite3.Connection, work_id: str) -> list[dict[str, Any]]:
    """Capturas ligadas à obra via redaction → occurrence → extract."""
    rows = conn.execute(
        "SELECT c.*, pd.profile, pd.parser_version, pd.quarantined, "
        "pd.issues_json, pd.ambiguous_paths_json, pd.editorial_json "
        "FROM capture c LEFT JOIN parsed_document pd ON pd.capture_id=c.id "
        "WHERE pd.work_id=? OR c.id IN ("
        "SELECT e.capture_id FROM extract e JOIN occurrence o ON o.extract_id=e.id "
        "JOIN redaction r ON r.id=o.redaction_id JOIN provision p ON p.id=r.provision_id "
        "WHERE p.work_id=?) ORDER BY c.fetched_at DESC, c.id DESC",
        (work_id, work_id),
    ).fetchall()
    return [dict(row) for row in rows]


def set_decision_nivel_prova(
    conn: sqlite3.Connection,
    decision_id: str,
    nivel: str,
) -> None:
    if nivel not in {"metadados", "ementa_capturada", "inteiro_teor_capturado"}:
        raise ValueError(f"nível de prova inválido: {nivel}")
    conn.execute(
        "UPDATE decision SET nivel_prova=? WHERE id=?",
        (nivel, decision_id),
    )
    conn.commit()


def proof_level_for_capture(
    *,
    capture_id: str | None,
    sha256: str | None,
    kind_doc: str,
) -> str:
    """metadados sem captura; níveis capturados só com capture_id e sha256."""
    if not capture_id or not sha256:
        return "metadados"
    if kind_doc == "inteiro_teor":
        return "inteiro_teor_capturado"
    return "ementa_capturada"
