"""Helpers HTTP compartilhados pelos conectores."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlencode

from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.challenge import (
    detect_challenge,
    map_transport_error,
    unavailable_from_challenge,
)
from freoa_verifica.connectors.guarda import ativa as guarda_ativa
from freoa_verifica.identidade_http import user_agent_do_modo
from freoa_verifica.limites import restante
from freoa_verifica.transport import (
    Response,
    Session,
    fetch as transport_fetch,
    revalidar_captura,
)

_MAX_BYTES = 10 * 1024 * 1024
_MAX_REDIRECTS = 3


def ua_header(mode: str) -> dict[str, str]:
    return {"User-Agent": user_agent_do_modo(mode)}


def connector_fetch(
    url: str, *, reclassificar: Callable[[Unavailable], Unavailable] | None = None, **kw: Any
) -> Response:
    """fetch + detecção de desafio; propaga Unavailable.

    `reclassificar` é a regra do conector que dá o desfecho final à falha (ex.: Planalto, decisão 0048);
    a guarda registra esse desfecho, não o intermediário do transporte (FIX11/F-11).

    Dentro de uma guarda de execução (`connectors.guarda`), a mesma requisição efetiva não se repete
    e uma fonte que desafiou ou recusou não é consultada de novo.
    """
    def baixar(**extra: Any) -> Response:
        try:
            return _connector_fetch(url, **extra, **kw)
        except Unavailable as exc:
            final = reclassificar(exc) if reclassificar is not None else exc
            if final is exc:
                raise
            raise final from exc

    guarda = guarda_ativa()
    if guarda is None:
        return baixar()
    return guarda.executar(
        kw.get("method", "GET"),
        url,
        kw.get("body"),
        cacheavel=kw.get("session") is None and kw.get("sink") is None,
        baixar=lambda: baixar(antes_do_salto=guarda.antes_do_salto),
        revalidar=lambda resp: _revalidar(resp, url, **kw),
        politica=_politica(kw),
    )


def _politica(kw: Mapping[str, Any]) -> tuple:
    """Parâmetros da chamada que decidem aceitar ou recusar uma resposta (não entram na chave do cache)."""
    prefixos = kw.get("path_prefixes") or {}
    return (
        kw["hosts"], tuple(sorted(prefixos.items())), kw["mimes"],
        kw.get("max_bytes", _MAX_BYTES), kw.get("max_redirects", _MAX_REDIRECTS),
        kw.get("check_challenge", True), kw.get("ignore_challenge_kinds") or frozenset(),
        kw.get("expected_content"),
    )


def _revalidar(resp: Response, url: str, *, hosts, path_prefixes, mimes, max_bytes=_MAX_BYTES,
               max_redirects=_MAX_REDIRECTS, **kw: Any) -> None:
    """Política da chamada atual sobre captura guardada, sem rede: levanta o que a chamada receberia sem cache."""
    try:
        revalidar_captura(
            resp, allowed_hosts=hosts, allowed_path_prefixes=path_prefixes, allowed_mimes=mimes,
            max_bytes=max_bytes, max_redirects=max_redirects,
        )
    except Exception as exc:
        raise _mapear_erro(exc, url) from exc
    _checar_desafio(resp, url, **{k: kw[k] for k in _CHAVES_DESAFIO if k in kw})


def _mapear_erro(exc: Exception, url: str) -> Unavailable:
    return map_transport_error(exc, url) or Unavailable(f"transporte_{type(exc).__name__}")


def _connector_fetch(
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
    max_bytes: int = _MAX_BYTES,
    max_redirects: int = _MAX_REDIRECTS,
    session: Session | None = None,
    sink: str | Path | None = None,
    check_challenge: bool = True,
    ignore_challenge_kinds: frozenset[str] | None = None,
    expected_content: str | None = None,
    antes_do_salto: Any = None,
) -> Response:
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
            **({"antes_do_salto": antes_do_salto} if antes_do_salto is not None else {}),
        )
    except Unavailable:
        raise  # recusa de salto pela guarda: já classificada
    except Exception as exc:
        raise _mapear_erro(exc, url) from exc

    _checar_desafio(
        resp, url, sink=sink, check_challenge=check_challenge,
        ignore_challenge_kinds=ignore_challenge_kinds, expected_content=expected_content,
    )
    return resp


_CHAVES_DESAFIO = ("check_challenge", "ignore_challenge_kinds", "expected_content")


def _checar_desafio(
    resp: Response,
    url: str,
    *,
    sink: str | Path | None = None,
    check_challenge: bool = True,
    ignore_challenge_kinds: frozenset[str] | None = None,
    expected_content: str | None = None,
) -> None:
    if not check_challenge:
        return
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
            desafio = unavailable_from_challenge(
                found, status=resp.status, headers=resp.headers, body=sample, url=url
            )
            if resp.final_url != url:
                desafio.evidencia["url_final"] = resp.final_url  # host que de fato desafiou
            raise desafio


def form_body(fields: Mapping[str, Any]) -> bytes:
    return urlencode({k: "" if v is None else str(v) for k, v in fields.items()}).encode(
        "utf-8"
    )


def ensure_not_challenge_bytes(data: bytes, *, status: int = 200) -> None:
    found = detect_challenge(status=status, body=data)
    if found is not None:
        raise unavailable_from_challenge(found, status=status, body=data)
