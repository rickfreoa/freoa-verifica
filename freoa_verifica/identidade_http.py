"""Identidade HTTP do pacote: fonte única do User-Agent (decisão 0048).

Não importa transporte nem conectores, para que todos possam importá-lo.
"""

from __future__ import annotations

import re

from freoa_verifica import __version__

_URL_PROJETO = "https://github.com/rickfreoa/freoa-verifica"
USER_AGENT_IDENTIFICADO = f"freoa-verifica/{__version__} (+{_URL_PROJETO})"
# Mesma identidade de qualquer versão do pacote (versão no formato PEP 440 que o projeto usa: 1.4.0, 1.4.0a7, 1.4.0rc1).
_UA_IDENTIFICADO_DE_QUALQUER_VERSAO = re.compile(
    r"freoa-verifica/[0-9]+(?:\.[0-9]+){1,3}(?:(?:a|b|rc)[0-9]+)?(?:\.post[0-9]+)?(?:\.dev[0-9]+)? \(\+"
    + re.escape(_URL_PROJETO) + r"\)",
    re.ASCII,
)


def eh_user_agent_identificado(valor: object) -> bool:
    """O valor é o User-Agent identificado do pacote, desta ou de outra versão (decisão 0093).

    Recibos persistidos registram o UA que de fato fez a obtenção; uma atualização de versão não os torna falsos."""
    return isinstance(valor, str) and _UA_IDENTIFICADO_DE_QUALQUER_VERSAO.fullmatch(valor) is not None

MODO_IDENTIFICADO = "identified"

_USER_AGENT_POR_MODO = {
    MODO_IDENTIFICADO: USER_AGENT_IDENTIFICADO,
}

UA_POR_CONECTOR = {
    "bcb": MODO_IDENTIFICADO,
    "camara_legin": MODO_IDENTIFICADO,
    "cvm_colegiado": MODO_IDENTIFICADO,
    "cvm_normas": MODO_IDENTIFICADO,
    "datajud": MODO_IDENTIFICADO,
    "planalto": MODO_IDENTIFICADO,
    "normas_leg": MODO_IDENTIFICADO,
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
