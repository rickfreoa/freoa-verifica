"""FIX18/F-22 (decisão 0064): o recibo guarda o Content-Type cru e a decisão de interpretação do corpo.

NULL em `content_type` = captura anterior a esta migração (ou sem Content-Type conhecido): a releitura usa o
`content-type` de `headers_json`, se houver, ou falha declarada `interpretacao_indisponivel`. Idempotente: homes de
teste rebaixados de versão reaplicam migrações sobre colunas que já existem.
"""

_COLUNAS = ("content_type", "codificacao", "origem_da_codificacao")


def migrar(conn):
    existentes = {r[1] for r in conn.execute("PRAGMA table_info(capture)")}
    for coluna in _COLUNAS:
        if coluna not in existentes:
            conn.execute(f"ALTER TABLE capture ADD COLUMN {coluna} TEXT")
