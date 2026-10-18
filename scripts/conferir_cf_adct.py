"""Conferência do escopo ADCT na captura real da Constituição (aceite de B1).

Uso: python scripts/conferir_cf_adct.py <home>
Reprocessa, sem gravar, a captura mais recente da CF com o parser atual e conta
caminhos do ADCT e colisões de escopo. Somente leitura.
"""
import json
import sys
from collections import Counter
from pathlib import Path

from freoa_verifica.service import Service
from freoa_verifica.store import blobs
from freoa_verifica.transport import Response

home = Path(sys.argv[1])
svc = Service(home=home)
row = svc.conn.execute(
    "SELECT c.* FROM capture c JOIN parsed_document p ON p.capture_id=c.id "
    "JOIN work w ON w.id=p.work_id WHERE c.url LIKE '%onstituicao%' "
    "ORDER BY c.fetched_at DESC LIMIT 1"
).fetchone()
print("captura:", row["url"])
body = blobs.get_blob(row["sha256"], home=home)
resp = Response(row["url"], row["final_url"], row["status"], json.loads(row["headers_json"]),
                body, row["sha256"], row["fetched_at"], [], row["mime"])
doc = svc._get("planalto").parse(resp)
paths = [p.path for p in doc.provisions]
issues = Counter(i.code for i in doc.issues)
print("parser_version:", doc.parser_version)
print("dispositivos:", len(paths), "| adct:", sum(p.startswith("adct/") for p in paths))
print("colisoes de escopo:", issues.get("SCOPE_COLLISION", 0), "| quarentena:", doc.quarantined)
print("issues:", dict(issues))
