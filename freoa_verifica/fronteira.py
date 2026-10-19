"""Validação de Host/Origin das interfaces HTTP locais (decisão 0040).

Função única, usada pelo REST e pelo MCP HTTP. Opera sobre os cabeçalhos brutos do ASGI
(`scope["headers"]`) para ver cabeçalhos duplicados, que `dict()` esconderia.
"""

from __future__ import annotations

import hmac
import os
import re
from collections.abc import Iterable

_HOST_LOCAL = r"(?:127\.0\.0\.1|localhost|\[::1\])"
_PORTA = r"(?::([0-9]{1,5}))?"
_RE_HOST = re.compile(rf"{_HOST_LOCAL}{_PORTA}")
_RE_ORIGEM = re.compile(rf"http://{_HOST_LOCAL}{_PORTA}")


def _porta_ok(m: re.Match[str] | None) -> bool:
    return m is not None and (m.group(1) is None or int(m.group(1)) <= 65535)


def host_local(valor: str) -> bool:
    return _porta_ok(_RE_HOST.fullmatch(valor.lower()))


def origem_local(valor: str) -> bool:
    return _porta_ok(_RE_ORIGEM.fullmatch(valor.lower()))


_RE_ORIGEM_EXTRA = re.compile(
    r"[a-z][a-z0-9+.\-]*://(?:[a-z0-9](?:[a-z0-9.\-]*[a-z0-9])?|\[[0-9a-f:.]+\])(?::([0-9]{1,5}))?")


def origens_permitidas(env: str | None = None) -> frozenset[str]:
    """FV_API_ORIGENS: origens exatas (esquema://host[:porta]), separadas por vírgula, aceitas além das locais
    (modo com token). Normaliza (strip, minúsculas, sem `/` final); formato inválido é erro na inicialização.
    Não é CORS: serve a clientes não-navegador que enviam `Origin`; não há resposta a preflight.
    """
    raw = os.environ.get("FV_API_ORIGENS", "") if env is None else env
    saida = set()
    for o in raw.split(","):
        o = o.strip().lower().rstrip("/")
        if not o:
            continue
        if not _porta_ok(_RE_ORIGEM_EXTRA.fullmatch(o)):
            raise ValueError(f"FV_API_ORIGENS inválida: {o!r} (use esquema://host[:porta], sem caminho)")
        saida.add(o)
    return frozenset(saida)


def token_ok(recebido: str, esperado: str) -> bool:
    """Comparação em bytes em tempo constante; caractere não-ASCII no token recebido não levanta."""
    return hmac.compare_digest(recebido.encode("utf-8", "surrogateescape"), esperado.encode("utf-8", "surrogateescape"))


MOTIVO_ENCAMINHADO = "cabeçalho de encaminhamento (X-Forwarded-For/Forwarded) recusado sem token"


def validar(headers: Iterable[tuple[bytes, bytes]], *, com_token: bool,
            extras: frozenset[str] = frozenset()) -> str | None:
    """None se a requisição passa; senão o motivo da recusa (403)."""
    vistos: dict[bytes, list[str]] = {}
    for k, v in headers:
        vistos.setdefault(k.lower(), []).append(v.decode("latin-1"))
    if not com_token and (vistos.keys() & {b"x-forwarded-for", b"forwarded"}):
        return MOTIVO_ENCAMINHADO
    origem = vistos.get(b"origin", [])
    if len(origem) > 1:
        return "Origin duplicado"
    if origem and not origem_local(origem[0]) and not (com_token and origem[0].strip().lower() in extras):
        return "Origin não permitida"
    if com_token:
        return None
    host = vistos.get(b"host", [])
    if len(host) != 1 or not host_local(host[0]):
        return "Host não permitido"
    if any(v.strip().lower() == "cross-site" for v in vistos.get(b"sec-fetch-site", [])):
        return "requisição cross-site recusada"
    return None
