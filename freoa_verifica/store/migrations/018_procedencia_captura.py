"""IL.0-R, C6 (decisão 0075, §3.2): `procedencia` persistida por captura.

Capturas anteriores à migração ficam sem a marca (NULL), publicadas como `nao_identificado`.
Idempotente.
"""


def migrar(conn):
    existentes = {r[1] for r in conn.execute("PRAGMA table_info(capture)")}
    if "procedencia" not in existentes:
        conn.execute("ALTER TABLE capture ADD COLUMN procedencia TEXT")
