"""IL.0-R (decisão 0075, §3.2 e §3.4): esquema final único do incremento.

Consolida as migrações 017 a 019 do ramo, que nunca foram incorporadas nem publicadas: nenhum banco real
tem estado intermediário delas, e o único ponto de partida admitido é o banco da `main` (versão 16).

1. `run`: colunas de comprovação e conferência do registro (`ferramenta`, compromissos e fundamento por HMAC,
   cópia em claro conforme a política, `registro_mac`).
2. `capture.procedencia`: marca por captura; as anteriores ficam sem ela (NULL, publicadas como `nao_identificado`).
3. Legado autenticado: o conjunto dos `run.id` existentes antes desta migração é selado por HMAC do home, com a
   âncora fora do banco (arquivo da chave do home; conexão gerenciada em banco sem home). A distinção entre
   legado e novo não depende de `registro_mac IS NULL`. Sem chave recuperável (home com histórico e chave ausente),
   não sela: nenhum registro sem MAC passa por legado. Sem âncora e com indício de fronteira já estabelecida,
   não recompõe o conjunto: falha fechada (`selar_legado`).

Idempotente nas colunas; o selo é fixado uma única vez.
"""

_COLUNAS_RUN = (
    ("ferramenta", "TEXT"),
    ("evidencias_compromissos", "TEXT"),
    ("fundamento_compromisso", "TEXT"),
    ("evidencias_claro", "TEXT"),
    ("fundamento_claro", "TEXT"),
    ("registro_mac", "TEXT"),
)


def migrar(conn):
    existentes = {r[1] for r in conn.execute("PRAGMA table_info(run)")}
    for coluna, tipo in _COLUNAS_RUN:
        if coluna not in existentes:
            conn.execute(f"ALTER TABLE run ADD COLUMN {coluna} {tipo}")
    existentes = {r[1] for r in conn.execute("PRAGMA table_info(capture)")}
    if "procedencia" not in existentes:
        conn.execute("ALTER TABLE capture ADD COLUMN procedencia TEXT")

    from freoa_verifica.registro import ARQUIVO_CHAVE, _home_da_conexao, selar_legado

    home = _home_da_conexao(conn)
    if home is not None and not (home / ARQUIVO_CHAVE).exists():
        # Migração nunca cria a chave (abre bancos de exportação e de teste em qualquer pasta): sem chave, o selo
        # é gravado na criação dela (`chave_do_home`), antes de qualquer registro autenticado.
        return
    try:
        selar_legado(conn)
    except (RuntimeError, OSError):
        pass  # sem chave recuperável ou sem como gravar a âncora: nenhum registro sem MAC passa por legado
