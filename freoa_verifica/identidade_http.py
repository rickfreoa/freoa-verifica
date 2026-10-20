"""Identidade HTTP do pacote: fonte única do User-Agent (decisão 0048).

Não importa transporte nem conectores, para que todos possam importá-lo.
"""

from __future__ import annotations

from freoa_verifica import __version__

USER_AGENT_IDENTIFICADO = f"freoa-verifica/{__version__} (+https://github.com/rickfreoa/freoa-verifica)"

MODO_IDENTIFICADO = "identified"

_USER_AGENT_POR_MODO = {
    MODO_IDENTIFICADO: USER_AGENT_IDENTIFICADO,
}

UA_POR_CONECTOR = {
    "bcb": MODO_IDENTIFICADO,
    "cvm_colegiado": MODO_IDENTIFICADO,
    "cvm_normas": MODO_IDENTIFICADO,
    "datajud": MODO_IDENTIFICADO,
    "planalto": MODO_IDENTIFICADO,
    "senado": MODO_IDENTIFICADO,
    "stf": MODO_IDENTIFICADO,
    "stj": MODO_IDENTIFICADO,
    "tcu": MODO_IDENTIFICADO,
    "tjdft": MODO_IDENTIFICADO,
    "tjsp": MODO_IDENTIFICADO,
}


def user_agent_do_modo(modo: str) -> str:
    """UA do modo; modo desconhecido é erro, nunca troca silenciosa de identidade."""
    try:
        return _USER_AGENT_POR_MODO[modo]
    except KeyError:
        raise ValueError(f"modo de User-Agent inválido: {modo}") from None
