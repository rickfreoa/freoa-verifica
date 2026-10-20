"""Helpers HTTP compartilhados pelos conectores."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlencode

from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.challenge import (
    detect_challenge,
    map_transport_error,
    unavailable_from_challenge,
)
from freoa_verifica.identidade_http import user_agent_do_modo
from freoa_verifica.limites import restante
from freoa_verifica.transport import (
    Response,
    Session,
    fetch as transport_fetch,
)


def ua_header(mode: str) -> dict[str, str]:
    return {"User-Agent": user_agent_do_modo(mode)}


def connector_fetch(
    url: str,
    *,
    hosts: frozenset[str],
    path_prefixes: dict[str, tuple[str, ...]] | None,
    mimes: frozenset[str],
    user_agent: str = "identified",
    method: str = "GET",
    body: bytes | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float = 30.0,
    min_bytes_per_second: float | None = None,
    max_bytes: int = 10 * 1024 * 1024,
    max_redirects: int = 3,
    session: Session | None = None,
    sink: str | Path | None = None,
    check_challenge: bool = True,
    ignore_challenge_kinds: frozenset[str] | None = None,
    expected_content: str | None = None,
) -> Response:
    """fetch + detecção de desafio; propaga Unavailable."""
    timeout = restante(timeout)
    if timeout <= 0:
        raise Unavailable("orcamento")
    hdrs = dict(ua_header(user_agent))
    if headers:
        hdrs.update(headers)
    try:
        resp = transport_fetch(
            url,
            method=method,
            body=body,
            headers=hdrs,
            allowed_hosts=hosts,
            allowed_path_prefixes=path_prefixes,
            allowed_mimes=mimes,
            timeout=timeout,
            **({"min_bytes_per_second": min_bytes_per_second} if min_bytes_per_second is not None else {}),
            max_bytes=max_bytes,
            max_redirects=max_redirects,
            session=session,
            **({"sink": sink} if sink is not None else {}),
        )
    except Exception as exc:
        mapped = map_transport_error(exc, url)
        if mapped is not None:
            raise mapped from exc
        raise Unavailable(f"transporte_{type(exc).__name__}") from exc

    if check_challenge:
        sample = resp.body
        if sink is not None:
            with Path(sink).open("rb") as stream:
                sample = stream.read(65536)
        found = detect_challenge(
            status=resp.status, headers=resp.headers, body=sample,
            expected_content=expected_content,
        )
        if found is not None:
            kind = str(found.args[0]) if found.args else ""
            ignored = ignore_challenge_kinds or frozenset()
            if kind not in ignored:
                if sink is not None:
                    Path(sink).unlink(missing_ok=True)
                raise unavailable_from_challenge(
                    found, status=resp.status, headers=resp.headers, body=sample, url=url
                )
    return resp


def form_body(fields: Mapping[str, Any]) -> bytes:
    return urlencode({k: "" if v is None else str(v) for k, v in fields.items()}).encode(
        "utf-8"
    )


def ensure_not_challenge_bytes(data: bytes, *, status: int = 200) -> None:
    found = detect_challenge(status=status, body=data)
    if found is not None:
        raise unavailable_from_challenge(found, status=status, body=data)
