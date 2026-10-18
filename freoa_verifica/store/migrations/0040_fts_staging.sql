-- Candidatos indexados ao vivo ficam fora do FTS canônico (decisão 0025, A7).
CREATE VIRTUAL TABLE fts_staging USING fts5(
    text,
    work_label,
    path,
    tokenize='unicode61 remove_diacritics 2'
);
