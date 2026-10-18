-- Persistência do parse por captura, nível de prova e vínculos via occurrence

CREATE TABLE parsed_document (
    capture_id TEXT PRIMARY KEY REFERENCES capture(id),
    profile TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    quarantined INTEGER NOT NULL DEFAULT 0,
    issues_json TEXT NOT NULL DEFAULT '[]',
    ambiguous_paths_json TEXT NOT NULL DEFAULT '[]',
    editorial_json TEXT NOT NULL DEFAULT '[]'
);

ALTER TABLE decision ADD COLUMN nivel_prova TEXT NOT NULL DEFAULT 'metadados';

ALTER TABLE decision_document ADD COLUMN nivel_prova TEXT;

CREATE INDEX idx_parsed_document_capture ON parsed_document(capture_id);
CREATE INDEX idx_occurrence_extract ON occurrence(extract_id);
CREATE INDEX idx_decision_nivel_prova ON decision(nivel_prova);
