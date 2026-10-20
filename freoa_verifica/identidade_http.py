"""Identidade HTTP do pacote: fonte única do User-Agent (decisão 0048).

Não importa transporte nem conectores, para que todos possam importá-lo.
"""

from __future__ import annotations

from freoa_verifica import __version__

USER_AGENT_IDENTIFICADO = f"freoa-verifica/{__version__} (+https://github.com/rickfreoa/freoa-verifica)"

# String exata usada na 1.2.0; só o Planalto a mantém (decisão 0048). Nenhum outro valor de navegador.
USER_AGENT_NAVEGADOR_1_2_0 = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

MODO_IDENTIFICADO = "identified"
MODO_NAVEGADOR_1_2_0 = "navegador_1_2_0"

_USER_AGENT_POR_MODO = {
    MODO_IDENTIFICADO: USER_AGENT_IDENTIFICADO,
    MODO_NAVEGADOR_1_2_0: USER_AGENT_NAVEGADOR_1_2_0,
}

UA_POR_CONECTOR = {
    "bcb": MODO_IDENTIFICADO,
    "cvm_colegiado": MODO_IDENTIFICADO,
    "cvm_normas": MODO_IDENTIFICADO,
    "datajud": MODO_IDENTIFICADO,
    "planalto": MODO_NAVEGADOR_1_2_0,
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
