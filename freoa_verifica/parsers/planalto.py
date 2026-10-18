"""Perfil Planalto — HTML consolidado de leis."""

from __future__ import annotations

from freoa_verifica.parsers.html_devices import (
    DEFAULT_MAX_INPUT_BYTES,
    DEFAULT_MAX_NESTING,
    PARSER_VERSION,
    decode_html_bytes,
    parse_html_devices,
)
from freoa_verifica.parsers.model import Issue, ParsedDocument
from freoa_verifica.parsers.sentinel import run_sentinels

DEFAULT_BASE = "https://www.planalto.gov.br/ccivil_03/leis/"


def parse_planalto(
    data: bytes | str,
    *,
    base_url: str | None = DEFAULT_BASE,
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
    max_nesting: int = DEFAULT_MAX_NESTING,
) -> ParsedDocument:
    encoding_issues: list[Issue] = []
    raw_bytes: bytes | None
    if isinstance(data, bytes):
        if len(data) > max_input_bytes:
            return ParsedDocument(
                profile="planalto",
                parser_version=PARSER_VERSION,
                title="",
                ementa=None,
                text="",
                provisions=[],
                issues=[
                    Issue(
                        "TRUNCATED",
                        None,
                        f"entrada {len(data)} bytes excede max_input_bytes={max_input_bytes}",
                        blocking_scope="document",
                    )
                ],
            )
        raw_bytes = data
        text, encoding_issues = decode_html_bytes(data)
    else:
        raw_bytes = data.encode("utf-8", errors="surrogateescape")
        text = data

    (
        title,
        ementa,
        doc_text,
        provisions,
        local_issues,
        amendments,
        editorial_blocks,
    ) = parse_html_devices(
        text,
        base_url=base_url,
        max_input_bytes=max_input_bytes,
        max_nesting=max_nesting,
    )
    doc = ParsedDocument(
        profile="planalto",
        parser_version=PARSER_VERSION,
        title=title,
        ementa=ementa,
        text=doc_text,
        provisions=provisions,
        issues=list(encoding_issues) + list(local_issues),
        amendments=amendments,
        editorial_blocks=editorial_blocks,
    )
    doc.issues.extend(
        run_sentinels(doc, raw=raw_bytes if raw_bytes is not None else text)
    )
    # Dedup issues
    seen: set[tuple[str, str | None, str]] = set()
    uniq = []
    for iss in doc.issues:
        key = (iss.code, iss.path, iss.detail)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(iss)
    doc.issues = uniq
    return doc
