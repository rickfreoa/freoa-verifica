-- Esquema inicial FREOA Verifica v2

CREATE TABLE source (
    id TEXT PRIMARY KEY,
    authority TEXT NOT NULL,
    profile TEXT NOT NULL,
    hosts_json TEXT NOT NULL,
    reuse_policy TEXT,
    policy_version TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE work (
    id TEXT PRIMARY KEY,
    jurisdiction TEXT NOT NULL,
    authority TEXT NOT NULL,
    kind TEXT NOT NULL,
    number TEXT NOT NULL,
    year INTEGER NOT NULL,
    label TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (jurisdiction, authority, kind, number, year)
);

CREATE TABLE alias (
    id TEXT PRIMARY KEY,
    work_id TEXT NOT NULL REFERENCES work(id),
    scheme TEXT NOT NULL,
    value TEXT NOT NULL,
    origin TEXT,
    resolution_status TEXT NOT NULL DEFAULT 'generated',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (scheme, value)
);

CREATE TABLE edition (
    id TEXT PRIMARY KEY,
    work_id TEXT NOT NULL REFERENCES work(id),
    kind TEXT NOT NULL,
    publication_date TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE capture (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES source(id),
    edition_id TEXT REFERENCES edition(id),
    url TEXT NOT NULL,
    final_url TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    status INTEGER NOT NULL,
    headers_json TEXT NOT NULL,
    redirects_json TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    mime TEXT,
    size INTEGER NOT NULL,
    outcome TEXT,
    UNIQUE (sha256, url, fetched_at)
);

CREATE TABLE extract (
    id TEXT PRIMARY KEY,
    capture_id TEXT NOT NULL REFERENCES capture(id),
    parser_version TEXT NOT NULL,
    text_sha256 TEXT NOT NULL,
    quality TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE provision (
    id TEXT PRIMARY KEY,
    work_id TEXT NOT NULL REFERENCES work(id),
    scope TEXT NOT NULL DEFAULT '',
    path TEXT NOT NULL,
    parent_id TEXT REFERENCES provision(id),
    UNIQUE (work_id, scope, path)
);

CREATE TABLE redaction (
    id TEXT PRIMARY KEY,
    provision_id TEXT NOT NULL REFERENCES provision(id),
    text TEXT NOT NULL,
    text_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE occurrence (
    id TEXT PRIMARY KEY,
    redaction_id TEXT NOT NULL REFERENCES redaction(id),
    extract_id TEXT NOT NULL REFERENCES extract(id),
    anchor_json TEXT,
    editorial_json TEXT
);

CREATE TABLE event (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    provision_id TEXT NOT NULL REFERENCES provision(id),
    redaction_id TEXT REFERENCES redaction(id),
    source_work_id TEXT REFERENCES work(id),
    publication_date TEXT,
    effective_date TEXT,
    effects_date TEXT,
    scope_json TEXT,
    rule TEXT,
    evidence_occurrence_id TEXT REFERENCES occurrence(id),
    state TEXT NOT NULL CHECK (state IN ('declared', 'derived', 'conflict', 'unknown')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE relation (
    id TEXT PRIMARY KEY,
    from_edition TEXT NOT NULL REFERENCES edition(id),
    to_edition TEXT NOT NULL REFERENCES edition(id),
    kind TEXT NOT NULL,
    evidence_occurrence_id TEXT REFERENCES occurrence(id)
);

CREATE TABLE proceeding (
    id TEXT PRIMARY KEY,
    court TEXT,
    number TEXT,
    cnj_number TEXT,
    uf TEXT,
    class TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE decision (
    id TEXT PRIMARY KEY,
    proceeding_id TEXT REFERENCES proceeding(id),
    court TEXT NOT NULL,
    class TEXT,
    number TEXT,
    uf TEXT,
    organ TEXT,
    rapporteur TEXT,
    judgment_date TEXT,
    publication_date TEXT,
    kind TEXT NOT NULL CHECK (kind IN (
        'acordao', 'decisao_monocratica', 'sumula', 'tema', 'voto',
        'decisao_colegiado_cvm', 'acordao_tcu'
    )),
    official_id TEXT,
    identity_status TEXT NOT NULL DEFAULT 'provisional'
        CHECK (identity_status IN ('confirmed', 'provisional')),
    authority_attrs_json TEXT,
    authority_label TEXT CHECK (authority_label IS NULL OR authority_label IN ('A', 'B', 'C', 'D', 'E')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (court, official_id)
);

CREATE TABLE decision_document (
    id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL REFERENCES decision(id),
    capture_id TEXT REFERENCES capture(id),
    extract_id TEXT REFERENCES extract(id),
    kind TEXT NOT NULL CHECK (kind IN ('ementa', 'inteiro_teor', 'voto', 'certidao')),
    text TEXT,
    sha256 TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE theme (
    id TEXT PRIMARY KEY,
    court TEXT,
    number TEXT,
    title TEXT,
    thesis TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE run (
    id TEXT PRIMARY KEY,
    request_hash TEXT NOT NULL,
    request_json TEXT NOT NULL,
    policy_version TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    result_json TEXT
);

CREATE VIRTUAL TABLE fts_redaction USING fts5(
    text,
    work_label,
    path,
    tokenize='unicode61 remove_diacritics 2'
);

CREATE VIRTUAL TABLE fts_decision USING fts5(
    ementa,
    inteiro_teor,
    court,
    class,
    tokenize='unicode61 remove_diacritics 2'
);

CREATE INDEX idx_alias_work ON alias(work_id);
CREATE INDEX idx_edition_work ON edition(work_id);
CREATE INDEX idx_capture_source ON capture(source_id);
CREATE INDEX idx_capture_sha ON capture(sha256);
CREATE INDEX idx_extract_capture ON extract(capture_id);
CREATE INDEX idx_provision_work ON provision(work_id);
CREATE INDEX idx_redaction_provision ON redaction(provision_id);
CREATE INDEX idx_occurrence_redaction ON occurrence(redaction_id);
CREATE INDEX idx_event_provision ON event(provision_id);
CREATE INDEX idx_event_kind ON event(kind);
CREATE INDEX idx_decision_proceeding ON decision(proceeding_id);
CREATE INDEX idx_decision_court ON decision(court);
CREATE INDEX idx_decision_kind ON decision(kind);
CREATE INDEX idx_decision_document_decision ON decision_document(decision_id);
CREATE INDEX idx_run_hash ON run(request_hash);

CREATE TRIGGER capture_no_update BEFORE UPDATE ON capture
BEGIN
    SELECT RAISE(ABORT, 'imutavel');
END;

CREATE TRIGGER capture_no_delete BEFORE DELETE ON capture
BEGIN
    SELECT RAISE(ABORT, 'imutavel');
END;

CREATE TRIGGER extract_no_update BEFORE UPDATE ON extract
BEGIN
    SELECT RAISE(ABORT, 'imutavel');
END;

CREATE TRIGGER extract_no_delete BEFORE DELETE ON extract
BEGIN
    SELECT RAISE(ABORT, 'imutavel');
END;

CREATE TRIGGER redaction_no_update BEFORE UPDATE ON redaction
BEGIN
    SELECT RAISE(ABORT, 'imutavel');
END;

CREATE TRIGGER redaction_no_delete BEFORE DELETE ON redaction
BEGIN
    SELECT RAISE(ABORT, 'imutavel');
END;

CREATE TRIGGER run_no_update BEFORE UPDATE ON run
BEGIN
    SELECT RAISE(ABORT, 'imutavel');
END;

CREATE TRIGGER run_no_delete BEFORE DELETE ON run
BEGIN
    SELECT RAISE(ABORT, 'imutavel');
END;
