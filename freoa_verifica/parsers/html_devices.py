"""Extração de dispositivos a partir de HTML genérico (Planalto / BCB)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from lxml import etree
from lxml import html as lhtml

from freoa_verifica.texto_resposta import codec_html_declarado
from freoa_verifica.parsers.model import (
    Annotation,
    EditorialBlock,
    Issue,
    Provision,
    QuotedAmendment,
    Redaction,
)
from freoa_verifica.parsers.paths import (
    adct_scope_from_heading,
    annex_scope_from_heading,
    nest_supplement_scope,
    roman_to_int,
    supplement_scope_from_heading,
)

PARSER_VERSION = "1.2.3"

DEFAULT_MAX_INPUT_BYTES = 30 * 1024 * 1024
DEFAULT_MAX_NESTING = 200

# Hífen / meia-risca / travessão entre número e letra do rótulo
_LETTER_SEP = r"[-–—]"

_ORDINAL_SUP = re.compile(
    r"(\d)\s*<sup[^>]*>\s*<u?>\s*o\s*</u?>\s*</sup>",
    re.I,
)

_ANNOT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "redacao_dada",
        re.compile(
            r"\(\s*(?:Redação|Redacao)\s+(?:dada\s+)?pel[ao]\s+(.+?)\s*\)",
            re.I | re.S,
        ),
    ),
    (
        "incluido",
        re.compile(
            r"\(\s*(?:Incluído|Incluida|Incluído|Incluída|Incluido|Artigo\s+incluído|"
            r"Inciso\s+incluído|Parágrafo\s+incluído|Alínea\s+incluída|"
            r"Parágrafo\s+incluído)"
            r"[^)]*?pel[ao]\s+(.+?)\s*\)",
            re.I | re.S,
        ),
    ),
    (
        "incluido",
        re.compile(
            r"\(\s*(?:Incluído|Incluída|Incluido|Incluida)\s+pel[ao]\s+(.+?)\s*\)",
            re.I | re.S,
        ),
    ),
    (
        "revogado",
        re.compile(
            r"\(\s*(?:Revogado|Revogada|Revogados|Revogadas)\s+pel[ao]\s+(.+?)\s*\)",
            re.I | re.S,
        ),
    ),
    (
        "revogado",
        re.compile(r"\(\s*(?:Revogado|Revogada)\s*\)", re.I),
    ),
    ("vide", re.compile(r"\(\s*Vide\s+(.+?)\s*\)", re.I | re.S)),
    ("vigencia", re.compile(r"\(\s*Vigência\s*\)", re.I)),
    (
        "producao_efeitos",
        re.compile(r"\(\s*Produção\s+de\s+efeitos?\s*\)", re.I),
    ),
    ("veto", re.compile(r"\(\s*VETADO\s*\)", re.I)),
    (
        "renumerado",
        re.compile(r"\(\s*Renumerado\s+.+?\)", re.I | re.S),
    ),
]

_ACT_REF_CLEAN = re.compile(r"\s+", re.S)
_DATE_FULL = re.compile(
    r"(\d{1,2})\s+de\s+"
    r"(janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|"
    r"setembro|outubro|novembro|dezembro)\s+de\s+(\d{4})",
    re.I,
)
_DATE_SHORT = re.compile(r"(\d{1,2})[./](\d{1,2})[./](\d{4})")
_DATE_YEAR = re.compile(r"\bde\s+(\d{4})\b")

_MONTHS = {
    "janeiro": "01",
    "fevereiro": "02",
    "marco": "03",
    "março": "03",
    "abril": "04",
    "maio": "05",
    "junho": "06",
    "julho": "07",
    "agosto": "08",
    "setembro": "09",
    "outubro": "10",
    "novembro": "11",
    "dezembro": "12",
}

_HEADING_RE = re.compile(
    r"^(T[ÍI]TULO|CAP[ÍI]TULO|SE[ÇC][ÃA]O|SUBSE[ÇC][ÃA]O|LIVRO|PARTE)\b",
    re.I,
)

_AMEND_TRIGGER = re.compile(
    r"passam?\s+a\s+vigorar\s+(?:"
    r"com\s+a\s+seguinte\s+reda[cç][aã]o|"
    r"com\s+a\s+seguinte\s+altera[cç][aã]o|"
    r"com\s+as\s+seguintes\s+altera[cç][oõ]es|"
    r"acrescid[oa]"
    r")|"
    r"acrescid[oa]\s+d[oa]s?\s+seguintes?",
    re.I,
)

_TARGET_REF = re.compile(
    r"((?:Lei|Decreto(?:-Lei)?|Medida\s+Provis[oó]ria)\s+n[ºo°]\s*[\d.]+"
    r"(?:,\s*de\s+\d{1,2}\s+de\s+[a-zç]+\s+de\s+\d{4})?)",
    re.I,
)

_QUOTE_OPEN = "\"\u201c\u201e«"
_QUOTE_CLOSE = "\"\u201d\u201f»"


def decode_html_bytes(data: bytes) -> tuple[str, list[Issue]]:
    """Decodifica bytes HTML; nunca propaga UnicodeDecodeError.

    Ordem: charset declarado → utf-8 → cp1252 strict → latin-1.
    Fallbacks registram Issue ENCODING_FALLBACK.
    """
    issues: list[Issue] = []
    declarado = codec_html_declarado(data)  # prescan WHATWG: só `<meta>` efetivo, nunca "charset" solto no texto
    if declarado is not None:
        try:
            return data.decode(declarado), issues
        except UnicodeDecodeError:
            pass
    try:
        return data.decode("utf-8"), issues
    except UnicodeDecodeError:
        pass
    try:
        text = data.decode("cp1252", errors="strict")
        issues.append(
            Issue("ENCODING_FALLBACK", None, "decodificado como cp1252")
        )
        return text, issues
    except UnicodeDecodeError:
        text = data.decode("latin-1")
        issues.append(
            Issue("ENCODING_FALLBACK", None, "decodificado como latin-1")
        )
        return text, issues


def _normalize_ws(text: str, *, fold_ordinals: bool = True) -> str:
    t = text.replace("\xa0", " ").replace("\r", "\n")
    if fold_ordinals:
        t = t.replace("º", "o").replace("°", "o").replace("ª", "a")
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n+", " ", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()


def _preserve_numero_symbol(text: str) -> str:
    """Restaura 'nº' em referências a atos (Lei nº …), sem tocar em 'no mínimo'."""
    return re.sub(
        r"\b(Lei|Decreto(?:-lei)?|Medida\s+Provis[oó]ria|Resolu[cç][aã]o(?:\s+CVM)?|"
        r"Instru[cç][aã]o\s+Normativa|Portaria|Complementar)\s+no\b",
        lambda m: m.group(0)[:-2] + "nº",
        text,
        flags=re.I,
    )


def _is_strike_element(el) -> bool:
    if el.tag in {"strike", "s", "del"}:
        return True
    style = (el.get("style") or "").lower()
    return "line-through" in style


def walk_text_parts(el, in_strike: bool = False) -> list[tuple[bool, str]]:
    """Devolve fragmentos (struck, text) preservando ordem."""
    parts: list[tuple[bool, str]] = []
    struck_here = in_strike or _is_strike_element(el)
    if el.text:
        parts.append((struck_here, el.text))
    for child in el:
        parts.extend(walk_text_parts(child, struck_here))
        if child.tail:
            parts.append((struck_here, child.tail))
    return parts


def paragraph_struck(el) -> bool:
    parts = walk_text_parts(el)
    text_parts = [(s, t) for s, t in parts if t and t.strip()]
    if not text_parts:
        return False
    return all(s for s, _ in text_parts)


def paragraph_mixed_strike(el) -> tuple[str, str] | None:
    """Se há segmentos riscados e não riscados, devolve (riscado, vigente)."""
    parts = walk_text_parts(el)
    text_parts = [(s, t) for s, t in parts if t and t.strip()]
    if not text_parts:
        return None
    # Pontuação riscada isolada não constitui redação anterior.
    if not any(re.search(r"[\w]", t) for s, t in text_parts if s):
        return None
    has_struck = any(s for s, _ in text_parts)
    has_live = any(not s for s, _ in text_parts)
    if not (has_struck and has_live):
        return None
    struck = _normalize_ws("".join(t for s, t in parts if s))
    live = _normalize_ws("".join(t for s, t in parts if not s))
    return struck, live


def paragraph_plain_text(el) -> str:
    return _normalize_ws("".join(t for _, t in walk_text_parts(el)))


def extract_annotations_from_element(
    el,
    *,
    base_url: str | None,
) -> tuple[str, list[Annotation]]:
    """Texto do parágrafo sem notas entre parênteses de alteração + annotations."""
    href_by_raw: dict[str, str] = {}
    for a in el.xpath(".//a[@href]"):
        raw = _normalize_ws("".join(a.itertext()))
        href = a.get("href") or ""
        if base_url:
            href = urljoin(base_url, href)
        if raw.startswith("(") and raw.endswith(")"):
            href_by_raw[raw] = href

    full = paragraph_plain_text(el)
    annotations: list[Annotation] = []
    cleaned = full

    for kind, pat in _ANNOT_PATTERNS:
        for m in list(pat.finditer(full)):
            raw = _normalize_ws(m.group(0))
            act_ref = None
            if m.lastindex:
                act_ref = _normalize_ws(m.group(1), fold_ordinals=True)
                act_ref = re.sub(r"\s+", " ", act_ref).strip(" .;")
                act_ref = _preserve_numero_symbol(act_ref)
            raw = _preserve_numero_symbol(raw)
            act_date = _parse_act_date(act_ref or raw)
            href = href_by_raw.get(raw) or href_by_raw.get(m.group(0))
            if href is None:
                for k, v in href_by_raw.items():
                    if raw in k or k in raw or raw.replace("nº", "no") in k:
                        href = v
                        break
            annotations.append(
                Annotation(
                    kind=kind,
                    raw=raw,
                    act_ref=act_ref,
                    act_href=href,
                    act_date=act_date,
                )
            )
            cleaned = cleaned.replace(m.group(0), " ")

    cleaned = _normalize_ws(cleaned)
    seen: set[tuple[str, str]] = set()
    uniq: list[Annotation] = []
    for ann in annotations:
        key = (ann.kind, ann.raw)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(ann)
    return cleaned, uniq


def extract_annotations_from_text(full: str) -> tuple[str, list[Annotation]]:
    """Variante sem elemento (texto já plano)."""
    annotations: list[Annotation] = []
    cleaned = full
    for kind, pat in _ANNOT_PATTERNS:
        for m in list(pat.finditer(full)):
            raw = _preserve_numero_symbol(_normalize_ws(m.group(0)))
            act_ref = None
            if m.lastindex:
                act_ref = _preserve_numero_symbol(
                    _normalize_ws(m.group(1), fold_ordinals=True).strip(" .;")
                )
            annotations.append(
                Annotation(
                    kind=kind,
                    raw=raw,
                    act_ref=act_ref,
                    act_href=None,
                    act_date=_parse_act_date(act_ref or raw),
                )
            )
            cleaned = cleaned.replace(m.group(0), " ")
    cleaned = _normalize_ws(cleaned)
    seen: set[tuple[str, str]] = set()
    uniq: list[Annotation] = []
    for ann in annotations:
        key = (ann.kind, ann.raw)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(ann)
    return cleaned, uniq


def _parse_act_date(text: str) -> str | None:
    m = _DATE_FULL.search(text)
    if m:
        day = int(m.group(1))
        month = _MONTHS.get(m.group(2).lower().replace("ç", "c"))
        if month is None:
            month = _MONTHS.get(m.group(2).lower())
        year = m.group(3)
        if month:
            return f"{year}-{month}-{day:02d}"
    m = _DATE_SHORT.search(text)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
        return f"{y}-{mo:02d}-{d:02d}"
    return None


def _art_num_int(num: str) -> int:
    return int(num.replace(".", ""))


@dataclass
class _Ctx:
    scope: str = ""
    headings: list[str] = field(default_factory=list)
    art_path: str | None = None
    par_path: str | None = None
    inc_path: str | None = None
    ali_path: str | None = None
    provisions: dict[str, Provision] = field(default_factory=dict)
    doc_parts: list[str] = field(default_factory=list)
    doc_len: int = 0
    issues: list[Issue] = field(default_factory=list)
    last_device_path: str | None = None
    amendments: list[QuotedAmendment] = field(default_factory=list)
    editorial_blocks: list[EditorialBlock] = field(default_factory=list)
    # Modo citação de lei alterada
    in_quote: bool = False
    quote_host_path: str | None = None
    quote_target_ref: str = ""
    quote_label: str | None = None
    quote_chunks: list[str] = field(default_factory=list)
    last_amend_host: str | None = None
    pending_rubrica: str | None = None


def _is_rubrica(el, texto: str) -> bool:
    """Linha curta e centrada, sem ponto final, que o Planalto usa como rubrica do artigo seguinte."""
    return ((el.get("align") or "").lower() == "center" and 3 <= len(texto) <= 100
            and not texto.endswith((".", ":", ";")) and not re.match(r"(?i)art\b", texto))


def _prefix(ctx: _Ctx, path: str) -> str:
    if ctx.scope:
        return f"{ctx.scope}/{path}"
    return path


def _ensure_prov(ctx: _Ctx, path: str, label: str) -> Provision:
    if path not in ctx.provisions:
        ctx.provisions[path] = Provision(
            path=path,
            label=label,
            scope=ctx.scope,
            headings=list(ctx.headings),
            redactions=[],
        )
    return ctx.provisions[path]


def _append_redaction(
    ctx: _Ctx,
    path: str,
    label: str,
    text: str,
    struck: bool,
    annotations: list[Annotation],
    full_chunk: str,
) -> None:
    start = ctx.doc_len
    ctx.doc_parts.append(full_chunk)
    ctx.doc_len += len(full_chunk)
    ctx.doc_parts.append("\n")
    ctx.doc_len += 1
    end = start + len(full_chunk)
    prov = _ensure_prov(ctx, path, label)
    order = len(prov.redactions)
    prov.redactions.append(
        Redaction(
            text=text,
            struck=struck,
            order=order,
            annotations=annotations,
            span=(start, end),
            scope=ctx.scope,
        )
    )
    ctx.last_device_path = path


def _attach_annotations_to_last(ctx: _Ctx, annotations: list[Annotation]) -> bool:
    if not annotations or not ctx.last_device_path:
        return False
    prov = ctx.provisions.get(ctx.last_device_path)
    if not prov or not prov.redactions:
        return False
    # Anota a redação vigente mais recente; se só houver riscadas, a última
    target = None
    for red in reversed(prov.redactions):
        if not red.struck:
            target = red
            break
    if target is None:
        target = prov.redactions[-1]
    for ann in annotations:
        if not any(a.kind == ann.kind and a.raw == ann.raw for a in target.annotations):
            target.annotations.append(ann)
    return True


def _flush_quote(ctx: _Ctx) -> None:
    if ctx.quote_label and ctx.quote_chunks and ctx.quote_host_path:
        text = _normalize_ws(" ".join(ctx.quote_chunks))
        ctx.amendments.append(
            QuotedAmendment(
                host_path=ctx.quote_host_path,
                target_ref_text=ctx.quote_target_ref,
                target_label=ctx.quote_label,
                text=text,
            )
        )
    ctx.quote_label = None
    ctx.quote_chunks = []


def _exit_quote_mode(ctx: _Ctx) -> None:
    _flush_quote(ctx)
    ctx.in_quote = False
    ctx.quote_host_path = None
    ctx.quote_target_ref = ""


def _starts_with_quote(text: str) -> bool:
    t = text.lstrip()
    return bool(t) and t[0] in _QUOTE_OPEN


def _in_blockquote(el) -> bool:
    parent = el.getparent()
    while parent is not None:
        if isinstance(parent.tag, str) and parent.tag.lower() == "blockquote":
            return True
        parent = parent.getparent()
    return False


def _is_veto_stub(text: str) -> bool:
    body = re.sub(
        rf"^[Aa]rt\s*\.?\s*(?:(?:\d{{1,3}}(?:\.\d{{3}})+)|\d+)[oaº°]?(?:{_LETTER_SEP}[A-Za-z])?\s*\.?\s*",
        "",
        text.strip(),
    )
    body = _normalize_ws(body)
    return bool(re.match(r"^\(?\s*VETADO\s*\)?\.?$", body, re.I))


def _looks_like_host_article(text: str) -> bool:
    """Artigo da lei alteradora (encerra citação), não dispositivo citado."""
    if _AMEND_TRIGGER.search(text):
        return True
    if re.search(r"\bFicam\s+revogad", text, re.I):
        return True
    if re.search(r"\bEsta\s+Lei\b", text, re.I):
        return True
    # (VETADO) próprio da alteradora também encerra o bloco citado
    if _is_veto_stub(text):
        return True
    return False


def _strip_quotes(text: str) -> str:
    t = text.strip()
    if t and t[0] in _QUOTE_OPEN:
        t = t[1:]
    t = t.rstrip()
    # remove fecho e (NR)
    t = re.sub(r'["\u201d\u201f»]\s*\(NR\)\s*$', "", t, flags=re.I)
    t = re.sub(r'["\u201d\u201f»]\s*$', "", t)
    t = re.sub(r"\(NR\)\s*$", "", t, flags=re.I)
    return t.strip()


def _extract_target_ref(host_text: str) -> str:
    m = _TARGET_REF.search(host_text)
    if not m:
        return ""
    return _preserve_numero_symbol(_normalize_ws(m.group(1), fold_ordinals=False))


def _quote_art_label(text: str) -> str | None:
    """Se o texto citado inicia artigo, devolve rótulo 'Art. N-X'."""
    t = _strip_quotes(text)
    m = re.match(
        rf"^[Aa]rt\s*\.?\s*((?:\d{{1,3}}(?:\.\d{{3}})+)|\d+)[oaº°]?(?:{_LETTER_SEP}([A-Za-z]))?",
        t,
    )
    if not m:
        return None
    n = _art_num_int(m.group(1))
    letter = (m.group(2) or "").upper()
    if letter:
        return f"Art. {n}-{letter}"
    return f"Art. {n}"


def _classify_line(text: str) -> tuple[str, dict] | None:
    """Identifica tipo de dispositivo no início da linha já normalizada."""
    t = text.strip()
    if not t:
        return None
    # Remove aspas iniciais para classificar texto citado
    t_unq = _strip_quotes(t) if _starts_with_quote(t) else t

    m = re.match(
        rf"^[Aa]rt\s*\.?\s*((?:\d{{1,3}}(?:\.\d{{3}})+)|\d+)[oaº°]?(?:{_LETTER_SEP}([A-Za-z]))?\s*\.?\s*(.*)$",
        t_unq,
        re.S,
    )
    if m:
        return (
            "art",
            {
                "num": m.group(1),
                "letter": (m.group(2) or "").upper() or None,
                "rest": (m.group(3) or "").strip(),
            },
        )

    m = re.match(r"^Par[aá]grafo\s+[uú]nico\.?\s*(.*)$", t_unq, re.I | re.S)
    if m:
        return ("parunico", {"rest": m.group(1).strip()})

    m = re.match(
        rf"^§\s*((?:\d{{1,3}}(?:\.\d{{3}})+)|\d+)[oaº°]?(?:{_LETTER_SEP}([A-Za-z]))?\s*\.?\s*(.*)$",
        t_unq,
        re.S,
    )
    if m:
        return (
            "par",
            {
                "num": m.group(1),
                "letter": (m.group(2) or "").upper() or None,
                "rest": (m.group(3) or "").strip(),
            },
        )

    m = re.match(
        rf"^([IVXLCDM]+)(?:{_LETTER_SEP}([A-Za-z]))?\s*[-–—]\s*(.*)$",
        t_unq,
        re.S,
    )
    if m:
        try:
            roman_to_int(m.group(1))
        except ValueError:
            return None
        return (
            "inc",
            {
                "roman": m.group(1).upper(),
                "letter": (m.group(2) or "").upper() or None,
                "rest": m.group(3).strip(),
            },
        )

    m = re.match(r"^([a-z])\)\s+(.*)$", t_unq, re.S)
    if m:
        return ("ali", {"letter": m.group(1).lower(), "rest": m.group(2).strip()})

    m = re.match(r"^(\d+)[.)]\s+(.*)$", t_unq, re.S)
    if m:
        return ("item", {"num": m.group(1), "rest": m.group(2).strip()})

    return None


def _iter_device_blocks(root) -> tuple[list, dict[int, str]]:
    """Parágrafos + fontes órfãs 'Art N' sob body (markup quebrado do Planalto).

    Só inclui //body/font cujo texto é rótulo de artigo sem corpo (ex.: "Art 9º"),
    mesclado com a fonte irmã seguinte — evita duplicar conteúdo já presente em <p>.

    Retorna (blocos, merged_by_id) — texto mesclado fica no mapa (elementos lxml
    Cython não aceitam atributos Python arbitrários).
    """
    blocks: list = list(root.xpath("//p"))
    merged_by_id: dict[int, str] = {}
    # Insere fonts órfãs na posição documental correta
    orphan_fonts: list = []
    for el in root.xpath("//body/font"):
        plain = paragraph_plain_text(el)
        kind = _classify_line(plain)
        if not (kind and kind[0] == "art" and not (kind[1].get("rest") or "").strip()):
            continue
        nxt = el.getnext()
        while nxt is not None and getattr(nxt, "tag", None) != "font":
            if getattr(nxt, "tag", None) == "p":
                nxt = None
                break
            nxt = nxt.getnext()
        if nxt is None or getattr(nxt, "tag", None) != "font":
            continue
        extra_plain = paragraph_plain_text(nxt)
        extra_clean, anns = extract_annotations_from_text(extra_plain)
        # Corpo do artigo até o primeiro inciso/alínea de linha nova (após . ou :)
        extra = re.split(
            r"(?<=[:.])\s+(?=(?:[IVXLCDM]+(?:-[A-Za-z])?\s*[-–—]|§\s*\d|Par[aá]grafo\s|[a-z]\)))",
            extra_clean,
            maxsplit=1,
        )[0]
        # Mantém a 1ª anotação editorial no texto para o extrator principal
        suffix = (" " + anns[0].raw) if anns else ""
        merged_by_id[id(el)] = _normalize_ws(plain + " " + extra + suffix)
        orphan_fonts.append(el)

    if not orphan_fonts:
        return blocks, merged_by_id

    # Reconstroi na ordem do documento
    wanted = {id(el) for el in blocks + orphan_fonts}
    ordered: list = []
    for el in root.iter():
        if id(el) in wanted:
            ordered.append(el)
    return (ordered if ordered else blocks), merged_by_id


def extract_title_ementa(paragraphs: list) -> tuple[str, str | None]:
    title = ""
    ementa = None
    for el in paragraphs[:40]:
        t = paragraph_plain_text(el)
        if not t:
            continue
        if not title and re.match(r"CONSTITUI[ÇC][ÃA]O\s+DA\s+REP[ÚU]BLICA", t, re.I):
            title = t
            continue
        if not title and re.search(
            r"\b(LEI|DECRETO|MEDIDA\s+PROVIS[ÓO]RIA|RESOLU[ÇC][ÃA]O)\b",
            t,
            re.I,
        ) and re.search(r"\bDE\s+\d", t, re.I):
            title = t.rstrip(".")
            title = re.sub(r"\bNo\b", "Nº", title)
            title = re.sub(r"\bNº\b", "Nº", title)
            continue
        if title and ementa is None:
            if re.match(r"^(Disp[oõ]e|Institui|Altera|Cria|Regulamenta)\b", t, re.I):
                ementa = t
                break
            if t.startswith("(") or t.lower().startswith("mensagem"):
                continue
            if re.match(r"^O\s+PRESIDENTE", t, re.I):
                break
    return title, ementa


def _max_element_depth(el, depth: int = 0) -> int:
    kids = [c for c in el if isinstance(getattr(c, "tag", None), str)]
    if not kids:
        return depth
    return max(_max_element_depth(c, depth + 1) for c in kids)


_EDITORIAL_START = re.compile(
    r"^(?:Nota(?:\s+editorial)?|Obs(?:ervação|\.)?|N\.?\s*B\.?|"
    r"Nota\s+do\s+(?:editor|autor)|Nota\s+explicativa)\b",
    re.I,
)
_CONTINUATION_PUNCT_START = re.compile(r"^[,;:\-–—)\]]")
_ALINEA_OR_ITEM_START = re.compile(
    r"^(?:[a-z]\)|\d+[.)]|[IVXLCDM]+\s*[-–—])",
    re.I,
)


def _classify_unlabeled_paragraph(text: str) -> str:
    """Classifica parágrafo sem rótulo após dispositivo.

    Retorna: 'continuation' | 'editorial' | 'uncertain' | 'skip'
    """
    t = text.strip()
    if not t:
        return "skip"
    # Cabeçalhos curtos Title Case sem pontuação
    if len(t) < 80 and not re.search(r"[.:;]", t):
        words = [w for w in t.split() if w[:1].isalpha() and w.lower() not in {"de", "da", "do", "das", "dos", "e", "em", "para", "a", "o"}]
        if 1 <= len(words) <= 6 and all(w[:1].isupper() for w in words):
            return "skip"
    if _EDITORIAL_START.match(t) or t.startswith("("):
        return "editorial"
    if t[0].islower() or _CONTINUATION_PUNCT_START.match(t) or _ALINEA_OR_ITEM_START.match(
        t
    ):
        return "continuation"
    # Maiúscula inicial: pode ser prosa normativa ("A alienação…") ou editorial
    # sem marcador — incerto se curto/parece nota; prosa longa com verbo → continuation
    if t[0].isupper():
        if _EDITORIAL_START.match(t):
            return "editorial"
        # Frase normativa típica (artigos, deveres) — continua
        if len(t) >= 40 and re.search(
            r"\b(?:deve|deverá|fica|é|são|observa|aplica|vedad|permit)\w*\b",
            t,
            re.I,
        ):
            return "continuation"
        if len(t) >= 80:
            return "continuation"
        return "uncertain"
    return "uncertain"


def _looks_like_prose_continuation(text: str) -> bool:
    """Evita agregar cabeçalhos curtos (ex.: 'Sociedade Controladora') ao caput."""
    return _classify_unlabeled_paragraph(text) == "continuation"


def _record_editorial(ctx: _Ctx, text: str, full_chunk: str, *, uncertain: bool) -> None:
    start = ctx.doc_len
    ctx.doc_parts.append(full_chunk)
    ctx.doc_len += len(full_chunk)
    ctx.doc_parts.append("\n")
    ctx.doc_len += 1
    end = start + len(full_chunk)
    ctx.editorial_blocks.append(
        EditorialBlock(
            text=_normalize_ws(text),
            span=(start, end),
            kind="uncertain" if uncertain else "editorial",
        )
    )
    if uncertain and ctx.last_device_path:
        ctx.issues.append(
            Issue(
                "UNCERTAIN_CONTINUATION",
                ctx.last_device_path,
                full_chunk[:160],
                blocking_scope="provision",
            )
        )


def _append_continuation(ctx: _Ctx, text: str, full_chunk: str) -> bool:
    """Agrega parágrafo sem rótulo ao dispositivo anterior, estendendo o span.

    Retorna True se o parágrafo foi consumido (continuação, editorial ou incerto).
    """
    if not ctx.last_device_path:
        return False
    kind = _classify_unlabeled_paragraph(text)
    if kind == "skip":
        return False
    if kind == "editorial":
        _record_editorial(ctx, text, full_chunk, uncertain=False)
        return True
    if kind == "uncertain":
        _record_editorial(ctx, text, full_chunk, uncertain=True)
        return True
    # continuation
    prov = ctx.provisions.get(ctx.last_device_path)
    if not prov or not prov.redactions:
        return False
    target = None
    for red in reversed(prov.redactions):
        if not red.struck:
            target = red
            break
    if target is None:
        target = prov.redactions[-1]
    start = ctx.doc_len
    ctx.doc_parts.append(full_chunk)
    ctx.doc_len += len(full_chunk)
    ctx.doc_parts.append("\n")
    ctx.doc_len += 1
    end = start + len(full_chunk)
    extra = _normalize_ws(text)
    if extra:
        target.text = _normalize_ws(f"{target.text} {extra}")
    target.span = (target.span[0], end)
    return True


def parse_html_devices(
    html_text: str,
    *,
    base_url: str | None = None,
    collect_orphans: bool = True,
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
    max_nesting: int = DEFAULT_MAX_NESTING,
) -> tuple[
    str,
    str | None,
    str,
    list[Provision],
    list[Issue],
    list[QuotedAmendment],
    list[EditorialBlock],
]:
    """Parseia HTML em título, ementa, texto, provisions, issues, emendas e editoriais."""
    early_issues: list[Issue] = []
    raw_size = len(html_text.encode("utf-8", errors="surrogateescape"))
    if raw_size > max_input_bytes:
        early_issues.append(
            Issue(
                "TRUNCATED",
                None,
                f"entrada {raw_size} bytes excede max_input_bytes={max_input_bytes}",
                blocking_scope="document",
            )
        )
        return "", None, "", [], early_issues, [], []

    html_text = _ORDINAL_SUP.sub(r"\1o", html_text)
    # lxml recusa str com `<?xml encoding?>`; a codificação já foi decidida antes (FIX17, como `arvore_html`).
    html_text = re.sub(r"^﻿?\s*<\?xml[^>]*\?>", "", html_text)
    # HTMLParser: huge_tree/no_network (resolve_entities só existe no XMLParser).
    parser = etree.HTMLParser(huge_tree=False, no_network=True, recover=True)
    root = lhtml.fromstring(html_text, parser=parser)
    depth = _max_element_depth(root)
    if depth > max_nesting:
        early_issues.append(
            Issue(
                "TRUNCATED",
                None,
                f"profundidade {depth} excede max_nesting={max_nesting}",
                blocking_scope="document",
            )
        )
        return "", None, "", [], early_issues, [], []

    paragraphs = root.xpath("//p")
    title, ementa = extract_title_ementa(paragraphs)
    # Planalto às vezes quebra <p> com </font> órfão: "Art 9º" fica em
    # //body/font fora de qualquer <p>. Inclui esses blocos na ordem do documento.
    blocks, merged_by_id = _iter_device_blocks(root)
    ctx = _Ctx()
    ctx.issues.extend(early_issues)
    prev_in_bq = False

    for el in blocks:
        merged = merged_by_id.get(id(el))
        full_plain = merged or paragraph_plain_text(el)
        if not full_plain:
            continue

        in_bq = _in_blockquote(el)
        # Fim estrutural do bloco de emenda: saiu do </blockquote>
        if ctx.in_quote and prev_in_bq and not in_bq:
            _exit_quote_mode(ctx)
        prev_in_bq = in_bq

        # Anexos / suplementos
        scope = annex_scope_from_heading(full_plain)
        # ADCT: só no corpo, depois do primeiro dispositivo (o sumário não abre escopo)
        if scope is None and ctx.provisions and not ctx.scope:
            scope = adct_scope_from_heading(full_plain)
        sup = supplement_scope_from_heading(full_plain)
        if scope or sup:
            if ctx.in_quote:
                _exit_quote_mode(ctx)
            if scope:
                ctx.scope = scope
            elif sup:
                ctx.scope = nest_supplement_scope(ctx.scope, sup)
            ctx.headings = [full_plain]
            ctx.art_path = None
            ctx.par_path = None
            ctx.inc_path = None
            ctx.ali_path = None
            ctx.last_device_path = None
            ctx.doc_parts.append(full_plain)
            ctx.doc_len += len(full_plain) + 1
            ctx.doc_parts.append("\n")
            continue

        if _HEADING_RE.match(full_plain) or (
            len(full_plain) < 80
            and full_plain == full_plain.upper()
            and not full_plain.startswith("ART")
            and not re.match(r"^[IVXLC]+\b", full_plain)
        ):
            if _HEADING_RE.match(full_plain) or (
                len(full_plain) < 60
                and not re.search(r"\d", full_plain)
                and full_plain.upper() == full_plain
            ):
                if ctx.in_quote and _HEADING_RE.match(full_plain):
                    # Capítulos citados dentro da emenda — mantém no texto da emenda
                    if ctx.quote_label:
                        ctx.quote_chunks.append(full_plain)
                    ctx.doc_parts.append(full_plain)
                    ctx.doc_len += len(full_plain) + 1
                    ctx.doc_parts.append("\n")
                    continue
                # TÍTULO / CAPÍTULO limpa alvo de anotação (esp. em anexo)
                if _HEADING_RE.match(full_plain):
                    ctx.last_device_path = None
                ctx.headings.append(full_plain)
                ctx.doc_parts.append(full_plain)
                ctx.doc_len += len(full_plain) + 1
                ctx.doc_parts.append("\n")
                continue

        mixed = None if merged else paragraph_mixed_strike(el)
        struck = paragraph_struck(el) if mixed is None else False
        if merged:
            cleaned, annotations = extract_annotations_from_text(full_plain)
            # Hrefs da fonte seguinte (onde costuma estar a nota)
            nxt = el.getnext()
            while nxt is not None and nxt.tag != "font":
                if nxt.tag == "p":
                    break
                nxt = nxt.getnext()
            if nxt is not None and nxt.tag == "font":
                _c2, anns2 = extract_annotations_from_element(nxt, base_url=base_url)
                for a in anns2:
                    if not any(x.kind == a.kind and x.raw == a.raw for x in annotations):
                        annotations.append(a)
        else:
            cleaned, annotations = extract_annotations_from_element(el, base_url=base_url)
        class_text = cleaned or full_plain
        kind = _classify_line(class_text)

        # Aspas tipográficas no início: dispositivo citado, nunca provision própria.
        # Retoma citação sob o último anfitrião de emenda (republicações com "Art.…").
        if (
            _starts_with_quote(full_plain)
            and kind is not None
            and not ctx.in_quote
            and ctx.last_amend_host
        ):
            ctx.in_quote = True
            ctx.quote_host_path = ctx.last_amend_host
            if ctx.last_amend_host in ctx.provisions:
                last = ctx.provisions[ctx.last_amend_host].redactions
                if last:
                    ctx.quote_target_ref = _extract_target_ref(last[-1].text)
            ctx.quote_label = None
            ctx.quote_chunks = []

        # Parágrafo só com anotação editorial → associa ao último dispositivo
        if kind is None and annotations and not cleaned:
            if _attach_annotations_to_last(ctx, annotations):
                ctx.doc_parts.append(full_plain)
                ctx.doc_len += len(full_plain) + 1
                ctx.doc_parts.append("\n")
                continue
            if collect_orphans:
                ctx.issues.append(
                    Issue(
                        "ORPHAN_ANNOTATION",
                        None,
                        full_plain[:160],
                    )
                )
            ctx.doc_parts.append(full_plain)
            ctx.doc_len += len(full_plain) + 1
            ctx.doc_parts.append("\n")
            continue

        # --- Modo citação de lei alterada ---
        if ctx.in_quote:
            closes_quote = bool(
                re.search(r'["\u201d\u201f»]\s*(?:\(NR\))?\s*$', full_plain)
                or re.search(r"\(NR\)\s*$", full_plain, re.I)
            )
            # VETADO só continua citação se ainda dentro de aspas/blockquote
            veto_in_quote = _is_veto_stub(full_plain) and (
                in_bq or _starts_with_quote(full_plain)
            )
            is_quoted = (
                _starts_with_quote(full_plain)
                or in_bq
                or veto_in_quote
                or closes_quote
                or (
                    kind is not None
                    and kind[0] != "art"
                    and ctx.quote_label is not None
                )
            )
            # Novo artigo da lei alteradora (fora de aspas/blockquote) encerra
            host_art = (
                kind is not None
                and kind[0] == "art"
                and not _starts_with_quote(full_plain)
                and not in_bq
            )
            if host_art:
                _exit_quote_mode(ctx)
                # cai no fluxo normal abaixo
            elif is_quoted or (kind is not None and ctx.quote_label):
                label = _quote_art_label(full_plain)
                if label:
                    _flush_quote(ctx)
                    ctx.quote_label = label
                    ctx.quote_chunks = [_strip_quotes(full_plain)]
                elif ctx.quote_label:
                    ctx.quote_chunks.append(_strip_quotes(full_plain))
                elif _starts_with_quote(full_plain) or veto_in_quote:
                    ctx.quote_label = _quote_art_label(full_plain) or "texto"
                    ctx.quote_chunks = [_strip_quotes(full_plain)]
                ctx.doc_parts.append(full_plain)
                ctx.doc_len += len(full_plain) + 1
                ctx.doc_parts.append("\n")
                if closes_quote:
                    _flush_quote(ctx)
                    if not in_bq:
                        _exit_quote_mode(ctx)
                continue
            else:
                # prosa / reticências dentro do bloco
                if ctx.quote_label and (
                    "..." in full_plain
                    or "…" in full_plain
                    or "(NR)" in full_plain
                    or in_bq
                ):
                    ctx.quote_chunks.append(_strip_quotes(full_plain))
                    if re.search(r"\(NR\)", full_plain, re.I):
                        _flush_quote(ctx)
                        if not in_bq:
                            _exit_quote_mode(ctx)
                    ctx.doc_parts.append(full_plain)
                    ctx.doc_len += len(full_plain) + 1
                    ctx.doc_parts.append("\n")
                    continue
                _exit_quote_mode(ctx)
                # e processa normalmente

        if kind is None and not annotations and _is_rubrica(el, full_plain):
            ctx.pending_rubrica = full_plain  # a última linha centrada antes do "Art." vale
            ctx.doc_parts.append(full_plain)
            ctx.doc_len += len(full_plain) + 1
            ctx.doc_parts.append("\n")
            continue

        if kind is None:
            # Continuação sem rótulo → agrega ao dispositivo anterior
            if cleaned and ctx.last_device_path and not annotations:
                if _append_continuation(ctx, cleaned, full_plain):
                    continue
            if cleaned and ctx.last_device_path and annotations:
                if _append_continuation(ctx, cleaned, full_plain):
                    _attach_annotations_to_last(ctx, annotations)
                    continue
            ctx.doc_parts.append(full_plain)
            ctx.doc_len += len(full_plain) + 1
            ctx.doc_parts.append("\n")
            continue

        dtype, info = kind
        rubrica, ctx.pending_rubrica = ctx.pending_rubrica, None
        rest = info.get("rest", "")
        body = rest
        if cleaned:
            k2 = _classify_line(cleaned)
            if k2 is not None:
                body = k2[1].get("rest", body)
        body = _normalize_ws(body)

        if dtype == "art":
            letter = info["letter"]
            num = info["num"]
            n = _art_num_int(num)
            path = _prefix(ctx, f"art{n}" + (f"-{letter}" if letter else ""))
            label = f"Art. {n}" + (f"-{letter}" if letter else "")
            ctx.art_path = path
            ctx.par_path = None
            ctx.inc_path = None
            ctx.ali_path = None
            if rubrica and not ctx.in_quote:
                prov_art = _ensure_prov(ctx, path, label)
                prov_art.rubrica = prov_art.rubrica or rubrica
            if mixed is not None:
                struck_txt, live_txt = mixed
                # Extrai corpo sem rótulo dos segmentos
                sk = _classify_line(struck_txt)
                lk = _classify_line(live_txt)
                s_body = _normalize_ws(sk[1]["rest"] if sk else struck_txt)
                l_body = _normalize_ws(lk[1]["rest"] if lk else live_txt)
                # Anotações vão na redação vigente
                s_clean, _ = extract_annotations_from_text(s_body)
                l_clean, l_anns = extract_annotations_from_text(l_body)
                anns = annotations or l_anns
                _append_redaction(ctx, path, label, s_clean, True, [], full_plain)
                _append_redaction(ctx, path, label, l_clean or body, False, anns, full_plain)
                ctx.issues.append(
                    Issue(
                        "MIXED_STRIKE",
                        path,
                        "parágrafo com segmentos riscados e não riscados",
                        blocking_scope="provision",
                    )
                )
            else:
                _append_redaction(ctx, path, label, body, struck, annotations, full_plain)
            # Dispara modo citação se o artigo hospeda redação de outra lei
            host_src = cleaned or full_plain
            if _AMEND_TRIGGER.search(host_src):
                ctx.in_quote = True
                ctx.quote_host_path = path
                ctx.last_amend_host = path
                ctx.quote_target_ref = _extract_target_ref(host_src)
                ctx.quote_label = None
                ctx.quote_chunks = []
            continue

        if dtype == "parunico":
            if not ctx.art_path:
                ctx.issues.append(Issue("UNPARSED_LABEL", None, full_plain[:120]))
                continue
            path = f"{ctx.art_path}.parunico"
            ctx.par_path = path
            ctx.inc_path = None
            ctx.ali_path = None
            if mixed is not None:
                _append_mixed(ctx, path, "Parágrafo único", mixed, annotations, full_plain)
            else:
                _append_redaction(
                    ctx, path, "Parágrafo único", body, struck, annotations, full_plain
                )
            continue

        if dtype == "par":
            if not ctx.art_path:
                ctx.issues.append(Issue("UNPARSED_LABEL", None, full_plain[:120]))
                continue
            letter = info["letter"]
            num = info["num"]
            seg = f"par{_art_num_int(num)}" + (f"-{letter}" if letter else "")
            path = f"{ctx.art_path}.{seg}"
            ctx.par_path = path
            ctx.inc_path = None
            ctx.ali_path = None
            label = f"§ {_art_num_int(num)}" + (f"-{letter}" if letter else "")
            if mixed is not None:
                _append_mixed(ctx, path, label, mixed, annotations, full_plain)
            else:
                _append_redaction(ctx, path, label, body, struck, annotations, full_plain)
            continue

        if dtype == "inc":
            parent = ctx.par_path or ctx.art_path
            if not parent:
                ctx.issues.append(Issue("UNPARSED_LABEL", None, full_plain[:120]))
                continue
            roman = info["roman"]
            letter = info["letter"]
            n = roman_to_int(roman)
            seg = f"inc{n}" + (f"-{letter}" if letter else "")
            base = re.sub(r"\.(inc|ali|item)[\w-]+$", "", parent)
            path = f"{base}.{seg}"
            ctx.inc_path = path
            ctx.ali_path = None
            label = f"Inciso {roman}" + (f"-{letter}" if letter else "")
            if mixed is not None:
                _append_mixed(ctx, path, label, mixed, annotations, full_plain)
            else:
                _append_redaction(ctx, path, label, body, struck, annotations, full_plain)
            continue

        if dtype == "ali":
            parent = ctx.inc_path or ctx.par_path or ctx.art_path
            if not parent:
                ctx.issues.append(Issue("UNPARSED_LABEL", None, full_plain[:120]))
                continue
            letter = info["letter"]
            base = re.sub(r"\.(ali|item)[\w-]+$", "", parent)
            path = f"{base}.ali-{letter}"
            ctx.ali_path = path
            label = f"Alínea {letter}"
            if mixed is not None:
                _append_mixed(ctx, path, label, mixed, annotations, full_plain)
            else:
                _append_redaction(ctx, path, label, body, struck, annotations, full_plain)
            continue

        if dtype == "item":
            parent = ctx.ali_path or ctx.inc_path
            if not parent:
                ctx.doc_parts.append(full_plain)
                ctx.doc_len += len(full_plain) + 1
                ctx.doc_parts.append("\n")
                continue
            num = info["num"]
            base = re.sub(r"\.item[\d]+(?:-[A-Z])?$", "", parent)
            path = f"{base}.item{int(num)}"
            label = f"Item {int(num)}"
            if mixed is not None:
                _append_mixed(ctx, path, label, mixed, annotations, full_plain)
            else:
                _append_redaction(ctx, path, label, body, struck, annotations, full_plain)
            continue

    if ctx.in_quote:
        _exit_quote_mode(ctx)

    doc_text = "".join(ctx.doc_parts)
    provisions = list(ctx.provisions.values())
    return (
        title,
        ementa,
        doc_text,
        provisions,
        ctx.issues,
        ctx.amendments,
        ctx.editorial_blocks,
    )


def _append_mixed(
    ctx: _Ctx,
    path: str,
    label: str,
    mixed: tuple[str, str],
    annotations: list[Annotation],
    full_plain: str,
) -> None:
    struck_txt, live_txt = mixed
    sk = _classify_line(struck_txt)
    lk = _classify_line(live_txt)
    s_body = _normalize_ws(sk[1].get("rest", struck_txt) if sk else struck_txt)
    l_body = _normalize_ws(lk[1].get("rest", live_txt) if lk else live_txt)
    s_clean, _ = extract_annotations_from_text(s_body)
    l_clean, l_anns = extract_annotations_from_text(l_body)
    anns = annotations or l_anns
    _append_redaction(ctx, path, label, s_clean, True, [], full_plain)
    _append_redaction(ctx, path, label, l_clean, False, anns, full_plain)
    ctx.issues.append(
        Issue(
            "MIXED_STRIKE",
            path,
            "parágrafo com segmentos riscados e não riscados",
            blocking_scope="provision",
        )
    )
