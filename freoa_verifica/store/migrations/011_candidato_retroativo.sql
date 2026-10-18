-- A7 (retroativo, idempotente): obra cujas redações estão só no fts_staging (home pré-010) é candidata ao vivo.
UPDATE parsed_document SET candidato_ao_vivo=1
WHERE candidato_ao_vivo=0 AND work_id IN (
    SELECT w.id FROM work w
    WHERE COALESCE(w.label, w.number) IN (SELECT work_label FROM fts_staging)
      AND COALESCE(w.label, w.number) NOT IN (SELECT work_label FROM fts_redaction));
