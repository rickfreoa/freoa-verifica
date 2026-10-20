"""Detecção de desafios WAF/CAPTCHA em respostas de fontes oficiais."""

from __future__ import annotations

import hashlib
import re
from typing import Mapping

from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.texto_resposta import normalizar_para_busca, texto_da_resposta
from freoa_verifica.transport import (
    ChallengeDetected,
    EmptyBody,
    HTTPStatusError,
    RespostaInvalida,
    Timeout,
    TransportError,
)

# Tabela de assinaturas de desafio (decisão 0045). Mudar uma linha exige subir a versão,
# registrar na decisão e cobrir com teste em tests/test_categorias_indisponibilidade.py.
ASSINATURAS_VERSAO = 1

# Marcadores de corpo, comparados sobre o texto normalizado (NFKC, casefold, sem acentos; decisão 0061).
_BODY_MARKERS: tuple[tuple[str, str], ...] = (
    ("verificacao de seguranca", "f5"),
    ("tspd", "tspd"),
    ("bobcmn", "bobcmn"),
    ("cf-chl", "cloudflare"),
    ("captcha", "captcha"),
    ("recaptcha", "captcha"),
    ("hcaptcha", "captcha"),
    ("x-amzn-waf-action", "aws_waf"),
    ("awswafintegration", "aws_waf"),
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
    parcial: bool = False,
    content_type: str | None = None,
) -> ChallengeDetected | None:
    """Retorna ChallengeDetected se a resposta for desafio; senão None.

    Nunca resolve CAPTCHA — só classifica. Corpo em bytes é interpretado por `texto_da_resposta`
    (BOM/charset do Content-Type); corpo não interpretável levanta `RespostaInvalida`.
    """
    hdrs = {str(k).lower(): str(v) for k, v in (headers or {}).items()}

    for name, kind in _HEADER_MARKERS:
        if name in hdrs:
            return ChallengeDetected(kind)

    text = texto_da_resposta(body, content_type or hdrs.get("content-type"), parcial=parcial)
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


def _evidencia(status, headers, body, url, content_type=None) -> dict:
    """Evidência do que foi visto: status, marcador, cabeçalho, sha256 do corpo e url."""
    hdrs = {str(k).lower() for k in (headers or {})}
    ev: dict = {}
    if status is not None:
        ev["status"] = status
    cab = next((n for n, _ in _HEADER_MARKERS if n in hdrs), None)
    if cab:
        ev["cabecalho"] = cab
    try:
        cab = {str(k).lower(): v for k, v in (headers or {}).items()}
        text = texto_da_resposta(body, content_type or cab.get("content-type"))
    except RespostaInvalida:
        text = ""
    if text:
        lower = normalizar_para_busca(_sem_biblioteca_lateral(text))
        marcador = next((m for m, _ in _BODY_MARKERS if m in lower), None)
        if marcador is None and "/tspd/" in lower:
            marcador = "/tspd/"
        if marcador:
            ev["marcador"] = marcador
    raw = body.encode("utf-8") if isinstance(body, str) else body
    if raw:
        ev["sha256"] = hashlib.sha256(raw).hexdigest()
    if url:
        ev["url"] = url
    return ev


def unavailable_from_challenge(
    exc: ChallengeDetected, *, status=None, headers=None, body=None, url=None, content_type=None
) -> Unavailable:
    kind = str(exc.args[0]) if exc.args else "desconhecido"
    return Unavailable(
        f"desafio_{kind}", "ambiental_desafio", _evidencia(status, headers, body, url, content_type)
    )


def map_transport_error(exc: BaseException, url: str | None = None) -> Unavailable | None:
    """Converte erro de transporte em Unavailable classificado; None se não for de transporte."""
    if isinstance(exc, ChallengeDetected):
        return unavailable_from_challenge(exc, url=url)
    http = getattr(exc, "http", None)
    status = getattr(http, "status_code", None)
    base = {"url": url} if url else {}
    if getattr(exc, "saltos", None):
        base["saltos"] = [dict(salto) for salto in exc.saltos]
    if isinstance(exc, HTTPStatusError):
        ev = {"status": exc.status, **base}
        headers = dict(getattr(http, "headers", ()) or ())
        if "retry-after" in headers:
            ev["retry_after"] = headers["retry-after"]
        if getattr(exc, "desafio", None):
            return Unavailable(f"desafio_{exc.desafio}", "ambiental_desafio", {**ev, "marcador": exc.desafio})
        for nome, kind in _HEADER_MARKERS:  # hoje o transporte só retém 4 cabeçalhos; vale se reter mais
            if nome in headers:
                return Unavailable(f"desafio_{kind}", "ambiental_desafio", {**ev, "cabecalho": nome})
        if exc.status == 202:
            # Sem corpo nem cabeçalho de borda não há prova de desafio: motivo legado, categoria honesta.
            return Unavailable("desafio_aws_waf", "resposta_inesperada", ev)
        if exc.status in (401, 403):
            return Unavailable(f"http_{exc.status}", "recusa_identificado", ev)
        if 500 <= exc.status <= 599:
            return Unavailable(f"http_{exc.status}", "fonte_fora", ev)
        return Unavailable(f"http_{exc.status}", None, ev)
    if isinstance(exc, EmptyBody):
        return Unavailable("corpo_vazio", "resposta_inesperada", {"status": status or 200, **base})
    if isinstance(exc, RespostaInvalida):
        # Resposta recebida, mas inválida (MIME, framing, tamanho): não é indisponibilidade da fonte.
        nome = type(exc).__name__
        ev = {"marcador": f"transporte:{nome}", **base}
        if status:
            ev["status"] = status
        return Unavailable(f"transporte_{nome}", "resposta_inesperada", ev)
    if isinstance(exc, Timeout) or type(exc) is TransportError:
        # Falha de conexão, TLS ou leitura registrada pelo transporte.
        nome = type(exc).__name__
        ev = {"marcador": f"transporte:{nome}", **base}
        if status:
            ev["status"] = status
        return Unavailable(f"transporte_{nome}", "fonte_fora", ev)
    return None


def _sem_biblioteca_lateral(text: str) -> str:
    # Biblioteca de um formulário lateral não é uma página de desafio.
    return re.sub(
        r'''<script\b[^>]*\bsrc\s*=\s*(?:"[^"]*(?:recaptcha|hcaptcha)[^"]*"|'[^']*(?:recaptcha|hcaptcha)[^']*'|[^\s>]*(?:recaptcha|hcaptcha)[^\s>]*)[^>]*>\s*</script\s*>''',
        '', text, flags=re.I,
    )


def _kind_from_text(text: str) -> str | None:
    lower = normalizar_para_busca(_sem_biblioteca_lateral(text))
    for marker, kind in _BODY_MARKERS:
        if marker in lower:
            return kind
    if re.search(r"/tspd/", lower):
        return "tspd"
    return None
