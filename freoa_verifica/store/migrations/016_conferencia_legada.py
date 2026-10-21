"""FIX19b (decisão 0065, emenda): evidência da conferência da releitura legada pelo padrão da fonte.

`parsed_document.interpretacao_conferencia` guarda, em JSON, o hash canônico do modelo anterior e do relido
(`modelo_anterior_sha256`, `modelo_novo_sha256`); só é preenchida com `interpretacao_origem` =
`legado_padrao_da_fonte_conferido`. Idempotente, como a 015.
"""


def migrar(conn):
    if "interpretacao_conferencia" not in {r[1] for r in conn.execute("PRAGMA table_info(parsed_document)")}:
        conn.execute("ALTER TABLE parsed_document ADD COLUMN interpretacao_conferencia TEXT")
