-- Modelo completo e contexto temporal por captura; identidade no índice de decisões.
ALTER TABLE parsed_document ADD COLUMN model_json TEXT;
ALTER TABLE parsed_document ADD COLUMN work_id TEXT REFERENCES work(id);
ALTER TABLE parsed_document ADD COLUMN work_date TEXT;
ALTER TABLE parsed_document ADD COLUMN amending_texts_json TEXT;
ALTER TABLE parsed_document ADD COLUMN events_json TEXT;
ALTER TABLE fts_decision RENAME TO fts_decision_old;
CREATE VIRTUAL TABLE fts_decision USING fts5(
    ementa, inteiro_teor, court, class, official_id UNINDEXED,
    tokenize='unicode61 remove_diacritics 2'
);
INSERT INTO fts_decision(ementa, inteiro_teor, court, class)
SELECT ementa, inteiro_teor, court, class FROM fts_decision_old;
DROP TABLE fts_decision_old;
