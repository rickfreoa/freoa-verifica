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


def interpretacao_do_recibo(resp: Response) -> tuple[str | None, str | None, str | None]:
    """(content_type cru, codec, origem) da interpretação única do corpo, para o recibo (FIX18/F-22, decisão 0064).

    Sem Content-Type conhecido, a decisão vem só dos bytes, como prova degradada (`legado_sem_cabecalho`, decisão
    0065), e o Content-Type fica nulo; bytes ininterpretáveis deixam tudo None. Corpo que a função única recusa
    guarda o Content-Type e decisão None: a releitura chega à mesma recusa.
    """
    from freoa_verifica.texto_resposta import content_type_do_response, interpretar, interpretar_legado
    from freoa_verifica.transport import RespostaInvalida

    content_type = content_type_do_response(resp)
    if content_type is None:
        try:
            legado = interpretar_legado(resp.body)
        except RespostaInvalida:
            return None, None, None
        return None, legado.codificacao, legado.origem
    try:
        decisao = interpretar(resp.body, content_type)
    except RespostaInvalida:
        return content_type, None, None
    return content_type, decisao.codificacao, decisao.origem


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
    content_type, codificacao, origem = interpretacao_do_recibo(resp)
    blobs.put_blob(resp.body, home=home or data_home())
    capture_id = new_ulid()
    conn.execute(
        "INSERT INTO capture("
        "id, source_id, edition_id, url, final_url, fetched_at, status, "
        "headers_json, redirects_json, sha256, mime, size, outcome, "
        "content_type, codificacao, origem_da_codificacao"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
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
            content_type,
            codificacao,
            origem,
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
    if label is not None and authority == "cvm":
        from freoa_verifica.rotulos import corrigir_mojibake

        label = corrigir_mojibake(label)
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
    rubrica: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO fts_redaction(text, rubrica, work_label, path) VALUES (?,?,?,?)",
        (text, rubrica, work_label, path),
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


def search_redactions(conn: sqlite3.Connection, q: str, limit: int = 10, *,
                      source_id: str | None = None, table: str = "fts_redaction") -> list[dict[str, Any]]:
    """`source_id` filtra antes do LIMIT; `table` escolhe o FTS canônico ou o staging (A7)."""
    where, params = f"{table} MATCH ?", [q]
    if source_id:
        where += (" AND work_label IN (SELECT COALESCE(w.label,w.number) FROM work w "
                  "JOIN provision p ON p.work_id=w.id JOIN redaction r ON r.provision_id=p.id "
                  "JOIN occurrence o ON o.redaction_id=r.id JOIN extract e ON e.id=o.extract_id "
                  "JOIN capture c ON c.id=e.capture_id WHERE c.source_id=?)")
        params.append(source_id)
    rows = conn.execute(
        f"SELECT text, work_label, path, bm25({table}) AS score FROM {table} "
        f"WHERE {where} ORDER BY score LIMIT ?", (*params, limit)).fetchall()
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


def decisions_by_number(conn: sqlite3.Connection, court: str, number: str) -> list[dict[str, Any]]:
    """Decisões confirmadas do tribunal com o número (sem pontos), no formato de search_local_decisions."""
    rows = conn.execute("""
        SELECT d.court, d.class, d.official_id, d.id AS decision_id, d.organ, d.rapporteur, d.kind,
               d.number, d.judgment_date, d.publication_date, dd.capture_id, dd.sha256,
               dd.nivel_prova, c.url AS url_oficial,
               (SELECT text FROM decision_document WHERE decision_id=d.id AND kind='ementa'
                ORDER BY created_at DESC, id DESC LIMIT 1) AS ementa,
               (SELECT text FROM decision_document WHERE decision_id=d.id AND kind='inteiro_teor'
                ORDER BY created_at DESC, id DESC LIMIT 1) AS inteiro_teor,
               (SELECT capture_id FROM decision_document
                WHERE decision_id=d.id AND kind='inteiro_teor'
                ORDER BY created_at DESC, id DESC LIMIT 1) AS full_capture_id
        FROM decision d
        LEFT JOIN decision_document dd ON dd.id=(
            SELECT id FROM decision_document
            WHERE decision_id=d.id
              AND (kind='inteiro_teor' OR (kind='ementa' AND COALESCE(text,'')!=''))
            ORDER BY CASE WHEN kind='ementa' THEN 0 ELSE 1 END, created_at DESC, id DESC LIMIT 1)
        LEFT JOIN capture c ON c.id=dd.capture_id
        WHERE d.court=? AND d.identity_status='confirmed'
          AND UPPER(REPLACE(REPLACE(d.number,'.',''),' ',''))=?
        ORDER BY d.judgment_date DESC, d.id
    """, (court.upper(), number.replace(".", "").replace(" ", "").upper())).fetchall()
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
    authority = "fv_authority(fts_decision.court, fts_decision.class, d.organ, d.kind)"
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
               bm25(fts_decision, 5.0, 1.0, 0.0, 0.0, 0.0) AS score, d.id AS decision_id,
               d.organ, d.rapporteur, d.number, d.judgment_date, d.publication_date,
               d.authority_attrs_json, d.kind, dd.capture_id, dd.sha256, dd.nivel_prova, c.url AS url_oficial,
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
    candidato_ao_vivo: bool | None = None,
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
    if candidato_ao_vivo is not None:  # None preserva a marca existente (reprocessamento)
        conn.execute("UPDATE parsed_document SET candidato_ao_vivo=? WHERE capture_id=?",
                     (1 if candidato_ao_vivo else 0, capture_id))
    sincronizar_derivados(conn, capture_id=capture_id, work_id=work_id, document=document, extract_id=extract_id)
    conn.commit()
    return extract_id


def sincronizar_derivados(
    conn: sqlite3.Connection, *, capture_id: str, work_id: str, document: Any, extract_id: str | None,
) -> None:
    """Atômico: DML e DDL de triggers num só SAVEPOINT, sem commit intermediário (C6).

    Falha ou morte do processo desfaz tudo, inclusive a suspensão das triggers (DDL é transacional no SQLite).
    """
    conn.execute("SAVEPOINT sync_derivados")
    try:
        _sincronizar_derivados(conn, capture_id=capture_id, work_id=work_id, document=document,
                               extract_id=extract_id)
    except BaseException:
        conn.execute("ROLLBACK TO sync_derivados")
        conn.execute("RELEASE sync_derivados")
        raise
    conn.execute("RELEASE sync_derivados")


def _sincronizar_derivados(
    conn: sqlite3.Connection, *, capture_id: str, work_id: str, document: Any, extract_id: str | None,
) -> None:
    """Regrava provisions, redações e ocorrências da captura a partir do modelo (C6).

    Remove antes os derivados antigos da captura: ocorrências de suas extrações e as redações e
    dispositivos que só elas sustentavam e que o modelo atual não tem mais. Caminhos novos são criados.
    """
    antigas = conn.execute(
        "SELECT o.id AS oid, o.redaction_id AS rid, r.provision_id AS pid FROM occurrence o "
        "JOIN extract e ON e.id=o.extract_id JOIN redaction r ON r.id=o.redaction_id "
        "WHERE e.capture_id=?", (capture_id,)).fetchall()
    # Ocorrências antigas dão lugar às da extração atual; as de outras capturas não se tocam.
    for r in antigas:
        conn.execute("UPDATE relation SET evidence_occurrence_id=NULL WHERE evidence_occurrence_id=?", (r["oid"],))
        conn.execute("UPDATE event SET evidence_occurrence_id=NULL WHERE evidence_occurrence_id=?", (r["oid"],))
        conn.execute("DELETE FROM occurrence WHERE id=?", (r["oid"],))
    atuais: dict[tuple[str, str], set[str]] = {}
    for prov in document.provisions:
        atuais[(prov.scope, prov.path)] = {
            hashlib.sha256(r.text.encode("utf-8")).hexdigest() for r in prov.redactions}
    for prov in document.provisions:
        conn.execute(
            "INSERT INTO provision(id, work_id, scope, path) VALUES (?,?,?,?) "
            "ON CONFLICT(work_id, scope, path) DO NOTHING", (new_ulid(), work_id, prov.scope, prov.path))
        pid = conn.execute("SELECT id FROM provision WHERE work_id=? AND scope=? AND path=?",
                           (work_id, prov.scope, prov.path)).fetchone()["id"]
        for red in prov.redactions:
            h = hashlib.sha256(red.text.encode("utf-8")).hexdigest()
            row = conn.execute("SELECT id FROM redaction WHERE provision_id=? AND text_sha256=?",
                               (pid, h)).fetchone()
            rid = row["id"] if row else new_ulid()
            if not row:
                conn.execute("INSERT INTO redaction(id, provision_id, text, text_sha256) VALUES (?,?,?,?)",
                             (rid, pid, red.text, h))
            if extract_id and not conn.execute(
                    "SELECT 1 FROM occurrence WHERE redaction_id=? AND extract_id=?", (rid, extract_id)).fetchone():
                conn.execute("INSERT INTO occurrence(id, redaction_id, extract_id, anchor_json, editorial_json) "
                             "VALUES (?,?,?,?,?)", (new_ulid(), rid, extract_id, None, None))
    # Órfãs: redações antigas ausentes do modelo e sem ocorrência em outra captura; depois os dispositivos vazios.
    triggers = [(n, q) for n, q in conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND tbl_name='redaction'").fetchall()]
    orfas = []
    for r in antigas:
        prov = conn.execute("SELECT scope, path FROM provision WHERE id=?", (r["pid"],)).fetchone()
        sha = conn.execute("SELECT text_sha256 FROM redaction WHERE id=?", (r["rid"],)).fetchone()
        if prov is None or sha is None:
            continue
        if sha[0] in atuais.get((prov["scope"], prov["path"]), set()):
            continue
        if conn.execute("SELECT 1 FROM occurrence WHERE redaction_id=?", (r["rid"],)).fetchone():
            continue
        orfas.append((r["rid"], r["pid"]))
    if orfas:
        for n, _ in triggers:
            conn.execute(f'DROP TRIGGER "{n}"')
        for rid, _ in orfas:
            conn.execute("DELETE FROM event WHERE redaction_id=?", (rid,))
            conn.execute("DELETE FROM redaction WHERE id=?", (rid,))
        for pid in {p for _, p in orfas}:
            if not conn.execute("SELECT 1 FROM redaction WHERE provision_id=?", (pid,)).fetchone():
                conn.execute("DELETE FROM event WHERE provision_id=?", (pid,))
                conn.execute("UPDATE provision SET parent_id=NULL WHERE parent_id=?", (pid,))
                conn.execute("DELETE FROM provision WHERE id=?", (pid,))
        for _, q in triggers:
            conn.execute(q)


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
        "SELECT c.*, pd.profile, pd.parser_version, pd.quarantined, pd.candidato_ao_vivo, "
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


FONTES_COMPILADAS = ("planalto", "cvm_normas", "bcb")


def avaliar_monotonia(conn: sqlite3.Connection, work_id: str, *, marcar: bool = False
                      ) -> tuple[set[tuple[str, str]], list[dict[str, Any]], set[str]]:
    """Decisão 0034: texto compilado não apaga dispositivos. Percorre as capturas não candidatas da obra
    da mais antiga à mais nova; a que perde caminhos do modelo canônico vigente não é promovida.

    Devolve (caminhos do canônico vigente, perdas [{capture_id, motivo}], caminhos de qualquer captura
    canônica). `marcar=True` grava `candidato_ao_vivo=1` nas rebaixadas."""
    rows = conn.execute(
        "SELECT pd.capture_id, pd.model_json FROM parsed_document pd JOIN capture c ON c.id=pd.capture_id "
        f"WHERE pd.work_id=? AND pd.model_json IS NOT NULL AND pd.candidato_ao_vivo=0 "
        f"AND c.source_id IN ({','.join('?' * len(FONTES_COMPILADAS))}) ORDER BY c.fetched_at, c.id",
        (work_id, *FONTES_COMPILADAS)).fetchall()
    vigente: set[tuple[str, str]] | None = None
    perdas: list[dict[str, Any]] = []
    todos: set[str] = set()
    for r in rows:
        provs = json.loads(r["model_json"]).get("provisions") or []
        caminhos = {(p.get("scope") or "", p["path"]) for p in provs}
        todos |= {c[1] for c in caminhos}
        if vigente is None or vigente <= caminhos:
            vigente = caminhos
            continue
        perdas.append({"work_id": work_id, "capture_id": r["capture_id"], "motivo": "PERDA_ESTRUTURAL",
                       "perdidos": sorted(c[1] for c in vigente - caminhos)[:20]})
        if marcar:
            conn.execute("UPDATE parsed_document SET candidato_ao_vivo=1 WHERE capture_id=?", (r["capture_id"],))
    return vigente or set(), perdas, todos


def aplicar_monotonia(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Rebaixa, em todas as obras, as capturas que perdem estrutura (idempotente)."""
    out: list[dict[str, Any]] = []
    for r in conn.execute("SELECT work_id FROM parsed_document WHERE work_id IS NOT NULL "
                          "GROUP BY work_id HAVING COUNT(*)>1").fetchall():
        out += avaliar_monotonia(conn, r[0], marcar=True)[1]
    return out
