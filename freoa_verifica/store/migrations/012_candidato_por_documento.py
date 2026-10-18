"""A7 por documento (idempotente): parsed_document é candidato ao vivo quando alguma redação não riscada
do seu modelo está no fts_staging (texto+path+rótulo) e não no fts_redaction. Só marca (0 -> 1)."""
import json


def migrar(conn):
    try:
        staging = {tuple(r) for r in conn.execute("SELECT text, path, work_label FROM fts_staging")}
    except Exception:
        return
    if not staging:
        return
    canon = {tuple(r) for r in conn.execute("SELECT text, path, work_label FROM fts_redaction")}
    rows = conn.execute(
        "SELECT pd.capture_id, pd.model_json, COALESCE(w.label, w.number) FROM parsed_document pd "
        "JOIN work w ON w.id=pd.work_id WHERE pd.candidato_ao_vivo=0 AND pd.model_json IS NOT NULL").fetchall()
    for cid, raw, rotulo in map(tuple, rows):
        try:
            provs = json.loads(raw)["provisions"]
        except (ValueError, KeyError, TypeError):
            continue
        chaves = {(r["text"], p["path"], rotulo) for p in provs for r in p["redactions"] if not r.get("struck")}
        if chaves & staging - canon:
            conn.execute("UPDATE parsed_document SET candidato_ao_vivo=1 WHERE capture_id=?", (cid,))
