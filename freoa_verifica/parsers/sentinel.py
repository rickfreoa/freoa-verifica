"""Sentinelas independentes sobre a árvore parseada."""

from __future__ import annotations

import re

from freoa_verifica.parsers.model import Issue, ParsedDocument, Provision, Redaction
from freoa_verifica.parsers.paths import article_sort_key, is_article_path


def run_sentinels(
    doc: ParsedDocument,
    *,
    raw: bytes | str | None = None,
    expected_min_articles: int | None = None,
) -> list[Issue]:
    issues: list[Issue] = []
    issues.extend(_duplicate_current(doc.provisions))
    issues.extend(_article_order(doc.provisions))
    issues.extend(_ocr_like(doc))
    issues.extend(_orphan_annotations(doc))
    issues.extend(_truncated(doc, raw=raw, expected_min_articles=expected_min_articles))
    _apply_ambiguity(doc, issues)
    return issues


def _has_substitution(r: Redaction) -> bool:
    return any(a.kind in {"redacao_dada", "incluido"} for a in r.annotations)


def _norm_text(r: Redaction) -> str:
    return re.sub(r"\s+", " ", r.text).strip()


def _apply_editorial_chain(currents: list[Redaction]) -> bool:
    """Cadeia editorial só se cada anterior tem substituição explícita na seguinte
    (Redação dada / Incluído) com texto distinto, na ordem do documento.
    Marca superseded_without_strike nas anteriores. Retorna True se a cadeia vale.
    """
    if len(currents) < 2:
        return True
    ordered = sorted(currents, key=lambda r: r.order)
    for prev, nxt in zip(ordered, ordered[1:]):
        if not _has_substitution(nxt):
            return False
        if _norm_text(prev) == _norm_text(nxt):
            return False
    for prev in ordered[:-1]:
        prev.superseded_without_strike = True
    return True


def _apply_ambiguity(doc: ParsedDocument, issues: list[Issue]) -> None:
    """Marca provisions afetadas por issues de escopo provision (+ descendentes).

    MIXED_STRIKE reporta o caso mas não torna o accessor ambíguo — as redações
    já foram cindidas em riscada + vigente.
    """
    by_path = {p.path: p for p in doc.provisions}
    for issue in issues:
        if issue.blocking_scope != "provision" or not issue.path:
            continue
        if issue.code == "MIXED_STRIKE":
            continue
        root = issue.path
        affected = [
            p
            for p in doc.provisions
            if p.path == root or p.path.startswith(root + ".") or p.path.startswith(root + "/")
        ]
        if not affected and root in by_path:
            affected = [by_path[root]]
        for prov in affected:
            prov.ambiguous = True
            if issue.code == "DUPLICATE_CURRENT" and prov.path == root:
                prov.concurrent_redactions = [
                    r for r in prov.redactions if _is_active_current(r)
                ]


def _is_active_current(r: Redaction) -> bool:
    if r.struck or r.superseded_without_strike:
        return False
    if any(a.kind == "revogado" for a in r.annotations):
        return False
    # Stub (VETADO) sem corpo não compete com redação posterior do mesmo path
    if any(a.kind == "veto" for a in r.annotations) and not r.text.strip():
        return False
    return True


def _duplicate_current(provisions: list[Provision]) -> list[Issue]:
    out: list[Issue] = []
    for prov in provisions:
        currents = [r for r in prov.redactions if _is_active_current(r)]
        if len(currents) < 2:
            continue
        if _apply_editorial_chain(currents):
            continue
        out.append(
            Issue(
                "DUPLICATE_CURRENT",
                prov.path,
                f"{len(currents)} redações não riscadas para o mesmo caminho",
                blocking_scope="provision",
            )
        )
    return out


def _article_order(provisions: list[Provision]) -> list[Issue]:
    out: list[Issue] = []
    last_by_scope: dict[str, tuple[int, str]] = {}
    seen_paths: set[str] = set()
    for prov in provisions:
        if not is_article_path(prov.path):
            continue
        # Só a primeira ocorrência do artigo (evita reentrada por anexo)
        if prov.path in seen_paths:
            continue
        seen_paths.add(prov.path)
        key = article_sort_key(prov.path)
        if key is None:
            continue
        scope = prov.scope or ""
        prev = last_by_scope.get(scope)
        if prev is not None and key < prev:
            out.append(
                Issue(
                    "ORDER",
                    prov.path,
                    f"artigo {prov.path} após art{prev[0]}"
                    + (f"-{prev[1]}" if prev[1] else ""),
                    blocking_scope="provision",
                )
            )
        last_by_scope[scope] = key
    return out


_OCR_PATTERNS = [
    re.compile(r"\blº\b"),
    re.compile(r"\bl°\b"),
    re.compile(r"(?<!\d)1°(?!\d)"),  # 1° ambíguo (grau vs ordinal)
]


def _ocr_like(doc: ParsedDocument) -> list[Issue]:
    out: list[Issue] = []
    for prov in doc.provisions:
        for red in prov.redactions:
            sample = red.text
            for pat in _OCR_PATTERNS:
                if pat.search(sample):
                    out.append(
                        Issue(
                            "OCR_LIKE_DIGIT",
                            prov.path,
                            f"padrão suspeito {pat.pattern!r} no texto",
                        )
                    )
                    break
    return out


def _orphan_annotations(doc: ParsedDocument) -> list[Issue]:
    """Anotações órfãs já são emitidas durante o parse; aqui só revalida flag."""
    return [i for i in doc.issues if i.code == "ORPHAN_ANNOTATION"]


def _truncated(
    doc: ParsedDocument,
    *,
    raw: bytes | str | None,
    expected_min_articles: int | None,
) -> list[Issue]:
    out: list[Issue] = []
    if raw is not None:
        if isinstance(raw, bytes):
            raw_l = raw.lower()
            has_close = b"</html>" in raw_l
            text_tail = raw[-2000:].decode("utf-8", errors="ignore").lower()
        else:
            has_close = "</html>" in raw.lower()
            text_tail = raw[-2000:].lower()
        if doc.profile in {"planalto", "bcb_json", "html"} and not has_close:
            out.append(
                Issue(
                    "TRUNCATED",
                    None,
                    "ausência de fecho </html>",
                    blocking_scope="document",
                )
            )
        # Assinatura final típica de leis Planalto
        if doc.profile == "planalto" and has_close:
            if not re.search(r"bras[ií]lia", text_tail) and not re.search(
                r"</html>", text_tail
            ):
                # só alerta se o documento parece muito curto
                arts = sum(1 for p in doc.provisions if is_article_path(p.path))
                if arts < 5:
                    out.append(
                        Issue(
                            "TRUNCATED",
                            None,
                            "documento sem assinatura final",
                            blocking_scope="document",
                        )
                    )

    arts = [p for p in doc.provisions if is_article_path(p.path)]
    if expected_min_articles is not None and len(arts) < expected_min_articles:
        out.append(
            Issue(
                "TRUNCATED",
                None,
                f"apenas {len(arts)} artigos (mínimo esperado {expected_min_articles})",
                blocking_scope="document",
            )
        )

    # Índice declarado via âncoras vs artigos parseados.
    # Âncoras Planalto às vezes concatenam artigo+parágrafo (art501.0 = art. 50 § 1º);
    # só contam números plausíveis (<= 999) com terminador de âncora.
    if raw is not None and doc.profile == "planalto":
        if isinstance(raw, str):
            blob = raw
        else:
            try:
                blob = raw.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    blob = raw.decode("cp1252", errors="strict")
                except UnicodeDecodeError:
                    blob = raw.decode("latin-1")
        nums = [
            int(n)
            for n in re.findall(
                r'name="art(\d{1,3})(?:[a-z]|§|\.|")',
                blob,
                flags=re.I,
            )
            if int(n) <= 400
        ]
        if nums:
            max_anchor = max(nums)
            n_art = len(arts)
            if max_anchor >= 50 and n_art < max_anchor * 0.3:
                out.append(
                    Issue(
                        "TRUNCATED",
                        None,
                        f"artigos parseados ({n_art}) << índice (max art{max_anchor})",
                        blocking_scope="document",
                    )
                )
    return out
