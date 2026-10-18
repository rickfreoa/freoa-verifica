"""Homes já na 012 (build de desenvolvimento) com staging e sem marca: origem não publicada (idempotente)."""


def migrar(conn):
    from freoa_verifica.derivados import marcar_origem_nao_publicada

    marcar_origem_nao_publicada(conn)
