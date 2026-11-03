"""Decisão 0075, §3.4: colunas para comprovação e conferência de registros na tabela run.

Idempotente: adiciona as colunas caso ainda não existam no esquema da tabela run.
"""

_COLUNAS = (
    ("ferramenta", "TEXT"),
    ("evidencias_compromissos", "TEXT"),
    ("fundamento_compromisso", "TEXT"),
    ("evidencias_claro", "TEXT"),
    ("fundamento_claro", "TEXT"),
    ("registro_mac", "TEXT"),
)


def migrar(conn):
    existentes = {r[1] for r in conn.execute("PRAGMA table_info(run)")}
    for coluna, tipo in _COLUNAS:
        if coluna not in existentes:
            conn.execute(f"ALTER TABLE run ADD COLUMN {coluna} {tipo}")
