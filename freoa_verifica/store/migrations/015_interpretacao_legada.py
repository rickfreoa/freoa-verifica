"""FIX19/F-24 (decisão 0065): decisão de interpretação sob a qual o modelo derivado foi produzido, para captura cujo
recibo não a tem (anterior à 014, gravada pela 1.2.0 com `headers_json={}`).

O recibo (`capture`) é imutável; a decisão da releitura fica no derivado. `interpretacao_origem` nulo com recibo sem
decisão = derivado sem decisão registrada: `derivados.compativel` é False. Idempotente, como a 014.
"""

_COLUNAS = ("interpretacao_codificacao", "interpretacao_origem")


def migrar(conn):
    existentes = {r[1] for r in conn.execute("PRAGMA table_info(parsed_document)")}
    for coluna in _COLUNAS:
        if coluna not in existentes:
            conn.execute(f"ALTER TABLE parsed_document ADD COLUMN {coluna} TEXT")
