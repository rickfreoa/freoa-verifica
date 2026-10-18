-- Rubrica de artigo como coluna própria do índice de redações (M11).
-- FTS5 não aceita ALTER TABLE ADD COLUMN: recria a tabela preservando rowid e conteúdo.
-- Linhas antigas ficam com rubrica NULL até o parser gravar o campo e o acervo ser reindexado.
ALTER TABLE fts_redaction RENAME TO fts_redaction_old;
CREATE VIRTUAL TABLE fts_redaction USING fts5(
    text,
    rubrica,
    work_label,
    path,
    tokenize='unicode61 remove_diacritics 2'
);
INSERT INTO fts_redaction(rowid, text, rubrica, work_label, path)
SELECT rowid, text, NULL, work_label, path FROM fts_redaction_old;
DROP TABLE fts_redaction_old;
