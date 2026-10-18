-- A7: marca persistida de captura obtida por busca ao vivo e ainda não confirmada.
-- Derivados (reindexar_fts, snapshots) mandam estas obras ao fts_staging, nunca ao canônico.
-- Homes anteriores não têm marca (0 = canônico): não há critério verificável retroativo.
ALTER TABLE parsed_document ADD COLUMN candidato_ao_vivo INTEGER NOT NULL DEFAULT 0;
