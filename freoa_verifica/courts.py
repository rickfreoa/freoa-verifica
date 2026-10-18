"""Identificadores canônicos para filtros de jurisprudência."""

import unicodedata


def normalize_court(value: str) -> str:
    key = " ".join("".join(
        c for c in unicodedata.normalize("NFKD", value.strip().lower())
        if not unicodedata.combining(c)
    ).split())
    return {
        "superior tribunal de justica": "stj",
        "supremo tribunal federal": "stf",
        "tribunal de contas da uniao": "tcu",
        "tribunal de justica de sao paulo": "tjsp",
        "tjdft": "tjdft",
        "tjdf": "tjdft",
        "tribunal de justica do distrito federal e dos territorios": "tjdft",
        "tribunal de justica do distrito federal": "tjdft",
        "comissao de valores mobiliarios": "cvm_colegiado",
        "cvm": "cvm_colegiado",
    }.get(key, key)
