"""IL.0-R, C8 (decisão 0075, §3.4): o conjunto dos registros anteriores à 1.4.0a2 é selado por HMAC do home.

A distinção entre legado e novo deixa de depender de `registro_mac IS NULL`, campo que quem altera o banco
sem a chave pode apagar. Sem chave recuperável (home com histórico e chave ausente), não sela: nenhum
registro sem MAC passa por legado.

A âncora do conjunto vive fora do banco (arquivo da chave do home; memória do processo em banco sem home). Sem ela e
com indício de fronteira já estabelecida, a migração não recompõe o conjunto: falha fechada (`selar_legado`).
"""


def migrar(conn):
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
