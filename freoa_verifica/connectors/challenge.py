"""Detecção de desafios WAF/CAPTCHA em respostas de fontes oficiais."""

from __future__ import annotations

import re
from typing import Mapping

from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.transport import ChallengeDetected, EmptyBody, HTTPStatusError

# Marcadores de corpo (case-insensitive).
_BODY_MARKERS: tuple[tuple[str, str], ...] = (
    ("verificação de segurança", "f5"),
    ("verificacao de seguranca", "f5"),
    ("tspd", "tspd"),
    ("bobcmn", "bobcmn"),
    ("cf-chl", "cloudflare"),
    ("captcha", "captcha"),
    ("recaptcha", "captcha"),
    ("hcaptcha", "captcha"),
    ("x-amzn-waf-action", "aws_waf"),
)

_HEADER_MARKERS: tuple[tuple[str, str], ...] = (
    ("x-amzn-waf-action", "aws_waf"),
    ("cf-mitigated", "cloudflare"),
)


def detect_challenge(
    *,
    status: int | None = None,
    headers: Mapping[str, str] | None = None,
    body: bytes | str | None = None,
    expected_content: str | None = None,
) -> ChallengeDetected | None:
    """Retorna ChallengeDetected se a resposta for desafio; senão None.

    Nunca resolve CAPTCHA — só classifica.
    """
    hdrs = {str(k).lower(): str(v) for k, v in (headers or {}).items()}

    for name, kind in _HEADER_MARKERS:
        if name in hdrs:
            return ChallengeDetected(kind)

    if status == 202:
        empty = body is None or (isinstance(body, (bytes, bytearray)) and len(body) == 0) or (
            isinstance(body, str) and not body.strip()
        )
        if empty or hdrs.get("x-amzn-waf-action"):
            return ChallengeDetected("aws_waf")

    if status == 403:
        text = _as_text(body)
        if text and ("<html" in text.lower() or "html" in (hdrs.get("content-type") or "").lower()):
            # 403 HTML: tente classificar pelo corpo; senão genérico.
            kind = _kind_from_text(text) or "http_403"
            return ChallengeDetected(kind)

    text = _as_text(body)
    if text:
        if status in (None, 200) and expected_content and re.search(expected_content, text, re.I):
            return None
        kind = _kind_from_text(text)
        if kind:
            return ChallengeDetected(kind)

    return None


def raise_if_challenge(
    *,
    status: int | None = None,
    headers: Mapping[str, str] | None = None,
    body: bytes | str | None = None,
) -> None:
    found = detect_challenge(status=status, headers=headers, body=body)
    if found is not None:
        raise found


def unavailable_from_challenge(exc: ChallengeDetected) -> Unavailable:
    kind = str(exc.args[0]) if exc.args else "desconhecido"
    return Unavailable(f"desafio_{kind}")


def map_transport_error(exc: BaseException) -> Unavailable | None:
    """Converte erros de transporte tipicamente ligados a desafio em Unavailable."""
    if isinstance(exc, ChallengeDetected):
        return unavailable_from_challenge(exc)
    if isinstance(exc, HTTPStatusError):
        if exc.status == 202:
            return Unavailable("desafio_aws_waf")
        if exc.status == 403:
            return Unavailable("desafio_http_403")
        return Unavailable(f"http_{exc.status}")
    if isinstance(exc, EmptyBody):
        return Unavailable("desafio_corpo_vazio")
    return None


def _as_text(body: bytes | str | None) -> str:
    if body is None:
        return ""
    if isinstance(body, str):
        return body
    try:
        return body.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _kind_from_text(text: str) -> str | None:
    # Biblioteca de um formulário lateral não é uma página de desafio.
    text = re.sub(
        r'''<script\b[^>]*\bsrc\s*=\s*(?:"[^"]*(?:recaptcha|hcaptcha)[^"]*"|'[^']*(?:recaptcha|hcaptcha)[^']*'|[^\s>]*(?:recaptcha|hcaptcha)[^\s>]*)[^>]*>\s*</script\s*>''',
        '', text, flags=re.I,
    )
    lower = text.lower()
    for marker, kind in _BODY_MARKERS:
        if marker in lower:
            return kind
    if re.search(r"/tspd/", lower):
        return "tspd"
    return None
