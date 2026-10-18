"""Perfil CVM — DOCX consolidado (zipfile + lxml)."""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field

from lxml import etree

from freoa_verifica.parsers.html_devices import (
    DEFAULT_MAX_INPUT_BYTES,
    DEFAULT_MAX_NESTING,
    PARSER_VERSION as HTML_PARSER_VERSION,
    _LETTER_SEP,
    _normalize_ws,
    _parse_act_date,
    _preserve_numero_symbol,
)
from freoa_verifica.parsers.model import Annotation, Issue, ParsedDocument, Provision, Redaction
from freoa_verifica.parsers.paths import (
    annex_scope_from_heading,
    nest_supplement_scope,
    roman_to_int,
    supplement_scope_from_heading,
)
from freoa_verifica.parsers.sentinel import run_sentinels

PARSER_VERSION = HTML_PARSER_VERSION + "-cvm-editorial4"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}

DEFAULT_MAX_UNCOMPRESSED = 60 * 1024 * 1024
DEFAULT_MAX_COMPRESSION_RATIO = 100

_ART_RE = re.compile(
    rf"^Art\s*\.?\s*((?:\d{{1,3}}(?:\.\d{{3}})+)|\d+)[oaº°]?(?:{_LETTER_SEP}([A-Za-z]))?\s*\.?\s*(.*)$",
    re.S,
)
_PAR_RE = re.compile(
    rf"^§\s*((?:\d{{1,3}}(?:\.\d{{3}})+)|\d+)[oaº°]?(?:{_LETTER_SEP}([A-Za-z]))?\s*\.?\s*(.*)$",
    re.S,
)
_PAR_UNICO_RE = re.compile(r"^Par[aá]grafo\s+[uú]nico\.?\s*(.*)$", re.I | re.S)
_INC_RE = re.compile(
    rf"^([IVXLCDM]+)(?:{_LETTER_SEP}([A-Za-z]))?\s*[-–—]\s*(.*)$",
    re.S,
)
_ALI_RE = re.compile(r"^([a-z])\)\s*(.*)$", re.S)
_ITEM_RE = re.compile(r"^(\d+)[.)]\s+(.*)$", re.S)
_HEADING_RE = re.compile(
    r"^(T[ÍI]TULO|CAP[ÍI]TULO|SE[ÇC][ÃA]O|SUBSE[ÇC][ÃA]O|ANEXO|SUPLEMENTO)\b",
    re.I,
)

# Notas editoriais CVM (alvo + verbo de alteração)
_NOTE_KIND = [
    ("redacao_dada", re.compile(r"com\s+reda[cç][aã]o\s+dada\s+pela?\s+(.+)$", re.I | re.S)),
    ("incluido", re.compile(r"inclu[ií]d[oa]s?\s+pela?\s+(.+)$", re.I | re.S)),
    ("revogado", re.compile(r"revogad[oa]s?\s+pela?\s+(.+)$", re.I | re.S)),
]

_NOTE_TARGET_PREFIX = re.compile(
    rf"^(?P<target>"
    rf"Caput|Item\s+\d+|Anexo(?:\s+[IVXLCDM\dA-Z]+)?|Art(?:igo)?\.?\s*\d+[oaº°]?(?:{_LETTER_SEP}[A-Za-z])?"
    rf"|§\s*\d+[oaº°]?"
    rf"|Par[aá]grafo\s+[uú]nico"
    rf"|Inciso\s+[IVXLCDM]+(?:{_LETTER_SEP}[A-Za-z])?"
    rf"|Al[ií]nea\s+[\"“”'‘’]?[a-z][\"“”'‘’]?"
    rf")"
    rf"(?:\s+do\s+(?:inciso\s+[IVXLCDM]+(?:{_LETTER_SEP}[A-Za-z])?"
    rf"(?:\s+do\s+§\s*\d+[oaº°]?)?"
    rf"|§\s*\d+[oaº°]?"
    rf"|par[aá]grafo\s+[uú]nico"
    rf"|art(?:igo)?\.?\s*\d+[oaº°]?(?:{_LETTER_SEP}[A-Za-z])?"
    rf"))*"
    rf"\s+(?P<body>.+)$",
    re.I | re.S,
)


@dataclass
class _Para:
    text: str
    struck: bool
    struck_text: str = ""
    live_text: str = ""
    mixed: bool = False


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
    started: bool = False
    last_path: str | None = None


def parse_cvm_docx(
    data: bytes | str,
    *,
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
    max_uncompressed: int = DEFAULT_MAX_UNCOMPRESSED,
    max_compression_ratio: float = DEFAULT_MAX_COMPRESSION_RATIO,
    max_nesting: int = DEFAULT_MAX_NESTING,
) -> ParsedDocument:
    if isinstance(data, str):
        raw = open(data, "rb").read()
    else:
        raw = data
    if len(raw) > max_input_bytes:
        return ParsedDocument(
            profile="cvm_docx",
            parser_version=PARSER_VERSION,
            title="",
            ementa=None,
            text="",
            provisions=[],
            issues=[
                Issue(
                    "TRUNCATED",
                    None,
                    f"entrada {len(raw)} bytes excede max_input_bytes={max_input_bytes}",
                    blocking_scope="document",
                )
            ],
        )
    try:
        paras = _read_paragraphs(
            raw,
            max_uncompressed=max_uncompressed,
            max_compression_ratio=max_compression_ratio,
            max_nesting=max_nesting,
        )
    except _DocxLimitError as exc:
        return ParsedDocument(
            profile="cvm_docx",
            parser_version=PARSER_VERSION,
            title="",
            ementa=None,
            text="",
            provisions=[],
            issues=[
                Issue("TRUNCATED", None, str(exc), blocking_scope="document")
            ],
        )
    pending_scopes = []
    title, ementa = _title_ementa(paras)
    ctx = _Ctx()

    for para in paras:
        text = para.text
        if not text:
            continue

        if not ctx.started:
            if re.match(rf"^Art\s*\.?\s*1[oaº°]?(?:\s|{_LETTER_SEP}|\.|$)", text):
                ctx.started = True
            else:
                continue

        note = _parse_note(text)
        if note is not None:
            if re.match(r"^(?:Anexo|Suplemento|Subse[çc][ãa]o|Se[çc][ãa]o|T[ií]tulo|Cap[ií]tulo)\b", note["target"], re.I):
                pending_scopes.append((note, ctx.scope))
                _push_text(ctx, text)
                continue
            target_path = _resolve_note_target(ctx, note["target"])
            if target_path and target_path in ctx.provisions:
                prov = ctx.provisions[target_path]
                for red in reversed(prov.redactions):
                    if not red.struck:
                        red.annotations.append(note["annotation"])
                        break
                else:
                    if prov.redactions:
                        prov.redactions[-1].annotations.append(note["annotation"])
                _push_text(ctx, text)
            else:
                ctx.issues.append(
                    Issue("ORPHAN_ANNOTATION", ctx.art_path or ctx.scope or None, text[:160], blocking_scope="provision" if (ctx.art_path or ctx.scope) else "document")
                )
                _push_text(ctx, text)
            continue

        scope = annex_scope_from_heading(text)
        sup = supplement_scope_from_heading(text)
        if scope or sup:
            if scope:
                ctx.scope = scope
            else:
                ctx.scope = nest_supplement_scope(ctx.scope, sup)  # type: ignore[arg-type]
            ctx.headings = [text]
            ctx.art_path = ctx.par_path = ctx.inc_path = ctx.ali_path = None
            ctx.last_path = None
            _push_text(ctx, text)
            continue

        if _HEADING_RE.match(text) and not re.match(
            r"^(ANEXO|SUPLEMENTO)\b", text, re.I
        ):
            ctx.headings.append(text)
            ctx.last_path = None
            _push_text(ctx, text)
            continue

        kind = _classify(text)
        if kind is None:
            if ctx.last_path and text.strip():
                _append_continuation(ctx, text)
            else:
                _push_text(ctx, text)
            continue

        dtype, info = kind
        body = _normalize_ws(info.get("rest", ""))
        struck = para.struck

        if dtype == "art":
            letter = info["letter"]
            num = info["num"]
            n = int(str(num).replace(".", ""))
            path = _pref(ctx, f"art{n}" + (f"-{letter}" if letter else ""))
            label = f"Art. {n}" + (f"-{letter}" if letter else "")
            ctx.art_path = path
            ctx.par_path = ctx.inc_path = ctx.ali_path = None
            if para.mixed:
                _add_mixed(ctx, path, label, para, text)
            else:
                _add_red(ctx, path, label, body, struck, text)
            continue

        if dtype == "parunico":
            if not ctx.art_path:
                continue
            path = f"{ctx.art_path}.parunico"
            ctx.par_path = path
            ctx.inc_path = ctx.ali_path = None
            if para.mixed:
                _add_mixed(ctx, path, "Parágrafo único", para, text)
            else:
                _add_red(ctx, path, "Parágrafo único", body, struck, text)
            continue

        if dtype == "par":
            if not ctx.art_path:
                continue
            letter = info["letter"]
            num = info["num"]
            n = int(str(num).replace(".", ""))
            path = f"{ctx.art_path}.par{n}" + (f"-{letter}" if letter else "")
            ctx.par_path = path
            ctx.inc_path = ctx.ali_path = None
            if para.mixed:
                _add_mixed(ctx, path, f"§ {n}", para, text)
            else:
                _add_red(ctx, path, f"§ {n}", body, struck, text)
            continue

        if dtype == "inc":
            parent = ctx.par_path or ctx.art_path
            if not parent:
                continue
            roman = info["roman"]
            letter = info["letter"]
            n = roman_to_int(roman)
            base = re.sub(r"\.(inc|ali|item)[\w-]+$", "", parent)
            path = f"{base}.inc{n}" + (f"-{letter}" if letter else "")
            ctx.inc_path = path
            ctx.ali_path = None
            if para.mixed:
                _add_mixed(ctx, path, f"Inciso {roman}", para, text)
            else:
                _add_red(ctx, path, f"Inciso {roman}", body, struck, text)
            continue

        if dtype == "ali":
            parent = ctx.inc_path or ctx.par_path or ctx.art_path
            if not parent:
                continue
            letter = info["letter"]
            base = re.sub(r"\.(ali|item)[\w-]+$", "", parent)
            path = f"{base}.ali-{letter}"
            ctx.ali_path = path
            if para.mixed:
                _add_mixed(ctx, path, f"Alínea {letter}", para, text)
            else:
                _add_red(ctx, path, f"Alínea {letter}", body, struck, text)
            continue

        if dtype == "item":
            parent = ctx.ali_path or ctx.inc_path
            if not parent:
                _push_text(ctx, text)
                continue
            num = info["num"]
            base = re.sub(r"\.item[\d]+(?:-[A-Z])?$", "", parent)
            path = f"{base}.item{int(num)}"
            if para.mixed:
                _add_mixed(ctx, path, f"Item {int(num)}", para, text)
            else:
                _add_red(ctx, path, f"Item {int(num)}", body, struck, text)
            continue

    for note, scope in pending_scopes:
        target = re.split(r"\s+e\s+art", note["target"], maxsplit=1, flags=re.I)[0]
        pattern = re.compile(r"^" + re.escape(target) + r"(?=\s|$|[.:–—])", re.I)
        family = target.split()[0]
        family_pattern = re.compile(r"^" + re.escape(family) + r"\b", re.I)
        affected = [p for p in ctx.provisions.values()
                    if (p.scope == scope or re.match(r"^(?:Anexo|Suplemento)\b", target, re.I))
                    and pattern.search(next((h for h in reversed(p.headings) if family_pattern.search(h)), ""))]
        if affected:
            for prov in affected:
                if prov.redactions:
                    prov.redactions[-1].annotations.append(note["annotation"])
        else:
            # Sem correspondência de título: bloqueia todo o escopo possível.
            for prov in ctx.provisions.values():
                if prov.scope == scope:
                    ctx.issues.append(Issue("ORPHAN_ANNOTATION", prov.path, note["annotation"].raw, "provision"))
    doc = ParsedDocument(
        profile="cvm_docx",
        parser_version=PARSER_VERSION,
        title=title,
        ementa=ementa,
        text="".join(ctx.doc_parts),
        provisions=list(ctx.provisions.values()),
        issues=list(ctx.issues),
    )
    doc.issues.extend(run_sentinels(doc, raw=None))
    return doc


class _DocxLimitError(Exception):
    pass


def _read_paragraphs(
    raw: bytes,
    *,
    max_uncompressed: int,
    max_compression_ratio: float,
    max_nesting: int,
) -> list[_Para]:
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        total_uncompressed = 0
        for info in zf.infolist():
            if info.file_size < 0:
                raise _DocxLimitError("ZipInfo.file_size inválido")
            total_uncompressed += info.file_size
            if total_uncompressed > max_uncompressed:
                raise _DocxLimitError(
                    f"descompactação {total_uncompressed} excede "
                    f"max_uncompressed={max_uncompressed}"
                )
            if info.compress_size > 0:
                ratio = info.file_size / info.compress_size
                if ratio > max_compression_ratio:
                    raise _DocxLimitError(
                        f"razão de compressão {ratio:.1f} > {max_compression_ratio}"
                    )
        # Leitura limitada do document.xml
        info = zf.getinfo("word/document.xml")
        remaining = max_uncompressed
        chunks: list[bytes] = []
        with zf.open(info) as fp:
            while remaining > 0:
                block = fp.read(min(65536, remaining))
                if not block:
                    break
                chunks.append(block)
                remaining -= len(block)
            leftover = fp.read(1)
            if leftover:
                raise _DocxLimitError(
                    f"word/document.xml excede max_uncompressed={max_uncompressed}"
                )
        xml = b"".join(chunks)
    parser = etree.XMLParser(
        huge_tree=False,
        resolve_entities=False,
        no_network=True,
        recover=False,
    )
    root = etree.fromstring(xml, parser=parser)
    depth = _max_depth(root)
    if depth > max_nesting:
        raise _DocxLimitError(
            f"profundidade {depth} excede max_nesting={max_nesting}"
        )
    out: list[_Para] = []
    for p in root.xpath("//w:p", namespaces=NS):
        texts: list[str] = []
        struck_flags: list[bool] = []
        for r in p.xpath(".//w:r", namespaces=NS):
            t_nodes = r.xpath("./w:t", namespaces=NS)
            if not t_nodes:
                continue
            piece = "".join(t.text or "" for t in t_nodes)
            if not piece:
                continue
            strike = bool(
                r.xpath("./w:rPr/w:strike|./w:rPr/w:dstrike", namespaces=NS)
            )
            texts.append(piece)
            struck_flags.append(strike)
        if not texts:
            continue
        text = _normalize_ws("".join(texts))
        has_s = any(struck_flags)
        has_u = any(not s for s in struck_flags)
        if has_s and has_u:
            struck_text = _normalize_ws(
                "".join(t for t, s in zip(texts, struck_flags) if s)
            )
            live_text = _normalize_ws(
                "".join(t for t, s in zip(texts, struck_flags) if not s)
            )
            out.append(
                _Para(
                    text=text,
                    struck=False,
                    struck_text=struck_text,
                    live_text=live_text,
                    mixed=True,
                )
            )
        else:
            struck = bool(struck_flags) and all(struck_flags)
            out.append(_Para(text=text, struck=struck))
    return out


def _max_depth(el, depth: int = 0) -> int:
    kids = [c for c in el if isinstance(getattr(c, "tag", None), str)]
    if not kids:
        return depth
    return max(_max_depth(c, depth + 1) for c in kids)


def _title_ementa(paras: list[_Para]) -> tuple[str, str | None]:
    title = ""
    ementa = None
    for para in paras[:60]:
        t = para.text
        if not t:
            continue
        if not title and re.search(r"(?:RESOLU[ÇC][ÃA]O|INSTRU[ÇC][ÃA]O|PARECER(?:\s+DE\s+ORIENTA[ÇC][ÃA]O)?|DELIBERA[ÇC][ÃA]O)\s+CVM", t, re.I):
            title = t
            continue
        if title and ementa is None and re.match(
            r"^(Disp[oõ]e|Altera|Institui|Regulamenta)\b", t, re.I
        ):
            ementa = t
            break
        if _ART_RE.match(t):
            break
    return title, ementa


def _classify(text: str) -> tuple[str, dict] | None:
    m = _ART_RE.match(text)
    if m:
        return (
            "art",
            {
                "num": m.group(1),
                "letter": (m.group(2) or "").upper() or None,
                "rest": (m.group(3) or "").strip(),
            },
        )
    m = _PAR_UNICO_RE.match(text)
    if m:
        return ("parunico", {"rest": (m.group(1) or "").strip()})
    m = _PAR_RE.match(text)
    if m:
        return (
            "par",
            {
                "num": m.group(1),
                "letter": (m.group(2) or "").upper() or None,
                "rest": (m.group(3) or "").strip(),
            },
        )
    m = _INC_RE.match(text)
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
                "rest": (m.group(3) or "").strip(),
            },
        )
    m = _ALI_RE.match(text)
    if m:
        return ("ali", {"letter": m.group(1).lower(), "rest": (m.group(2) or "").strip()})
    m = _ITEM_RE.match(text)
    if m:
        return ("item", {"num": m.group(1), "rest": (m.group(2) or "").strip()})
    return None


def _normalize_quotes(text: str) -> str:
    return (
        text.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("«", '"')
        .replace("»", '"')
    )


def _parse_note(text: str) -> dict | None:
    t = _normalize_quotes(text).lstrip("• \uf0a7").strip()
    m = re.match(r"^(?P<target>.+?)\s*(?P<body>com\s+reda[cç][aã]o\s+dada\s+pel[ao]|inclu[ií]d[oa]s?\s+pel[ao]|revogad[oa]s?\s+pel[ao])\s+.+$", t, re.I)
    if not m:
        return None
    target = m["target"].strip()
    # Somente um rótulo editorial, nunca uma oração normativa.
    if not re.match(r"^(?:Caput|Art(?:igo)?s?\.?|§|Par[aá]grafos?|Subite(?:m|ns)|Pre[aâ]mbulo|Participante|Incisos?|Al[ií]neas?|Item|Itens|Anexo|Suplemento|Subse[çc][ãa]o|Se[çc][ãa]o|T[ií]tulo|Cap[ií]tulo)\b|^§", target, re.I):
        if not re.fullmatch(r"[IVXLCDM]+(?:-[A-Z])?", target, re.I):
            return None
    if re.search(r"\b(?:esta|este|fica|passa|entra|será|deve|pode|mediante|dispõe)\b", target, re.I):
        return None
    if len(target) > 110 or re.search(r"[.;:]\s+[A-ZÀ-Úa-zà-ú]{3}", target):
        return None
    body = t[m.start("body"):]

    kind = None
    act_ref = None
    for k, pat in _NOTE_KIND:
        mm = pat.search(body)
        if mm:
            kind = k
            act_ref = _normalize_ws(mm.group(1)).strip(" .;")
            break
    # Sem verbo editorial (redação/incluído/revogado) não é nota — evita
    # engolir "Art. 1º Este Anexo Normativo II à Resolução CVM…" como órfã.
    if kind is None:
        return None
    if act_ref:
        act_ref = _preserve_numero_symbol(act_ref)
    act_date = _parse_act_date(act_ref or body)
    return {
        "target": target,
        "annotation": Annotation(
            kind=kind,
            raw=_preserve_numero_symbol(text),
            act_ref=act_ref,
            act_href=None,
            act_date=act_date,
        ),
    }


def _resolve_note_target(ctx: _Ctx, target: str) -> str | None:
    """Resolve alvo editorial relativo ao artigo/parágrafo/inciso corrente."""
    if not ctx.last_path and not ctx.art_path:
        return None
    t = _normalize_quotes(_normalize_ws(target))
    t = re.sub(r"\s+", " ", t).strip()

    if re.match(r"^Anexo\b", t, re.I):
        return None  # nota de escopo: exige associação explícita
    if re.match(r"^Item\b", t, re.I):
        m = re.fullmatch(r"Item\s+(\d+)", t, re.I)
        parent = ctx.ali_path or ctx.inc_path
        return f"{parent}.item{int(m[1])}" if m and parent else None

    if re.match(r"^(?:Incisos|Al[ií]neas|Itens|§§|Subse[çc][ãa]o|Se[çc][ãa]o|T[ií]tulo|Cap[ií]tulo|Suplemento)\b|^§§", t, re.I):
        return None
    if re.match(r"^Par[aá]grafo\s+\d", t, re.I):
        t = re.sub(r"^Par[aá]grafo\s+", "§ ", t, flags=re.I)
    if re.search(r"\s+(?:e|a|ao)\s+|[\da-z]\.\d|§\s*\d+[oaº°]?\s*[-–—]", t, re.I):
        return None
    # Caminho composto: "Alínea b do inciso II do § 1º"
    ali_m = re.search(r"Al[ií]nea\s+[\"']?([a-z])[\"']?", t, re.I)
    inc_m = re.search(rf"[Ii]nciso\s+([IVXLCDM]+)(?:{_LETTER_SEP}([A-Za-z]))?", t)
    par_m = re.search(r"§\s*(\d+)", t)
    par_u = re.search(r"Par[aá]grafo\s+[uú]nico", t, re.I)
    art_m = re.search(
        rf"Art(?:igo)?\.?\s*((?:\d{{1,3}}(?:\.\d{{3}})+)|\d+)[oaº°]?(?:{_LETTER_SEP}([A-Za-z]))?",
        t,
        re.I,
    )

    # Base: artigo explícito ou corrente
    if art_m:
        letter = (art_m.group(2) or "").upper()
        n = int(art_m.group(1).replace(".", ""))
        base = _pref(ctx, f"art{n}" + (f"-{letter}" if letter else ""))
        # Se só Art. N… sem descendentes no alvo, retorna o artigo
        if not ali_m and not inc_m and not par_m and not par_u:
            return base
    else:
        base = ctx.art_path
        if not base:
            return None

    if par_u:
        base = f"{_art_root(base)}.parunico"
    elif par_m:
        base = f"{_art_root(base)}.par{int(par_m.group(1))}"

    if inc_m:
        n = roman_to_int(inc_m.group(1))
        letter = (inc_m.group(2) or "").upper() or None
        parent = base if (par_m or par_u or ".par" in base) else (ctx.par_path or base)
        # Se o alvo cita inciso sob § já resolvido, use base; senão contexto
        if par_m or par_u:
            parent = base
        else:
            parent = ctx.par_path or base
        parent = re.sub(r"\.(inc|ali|item)[\w-]+$", "", parent)
        base = f"{parent}.inc{n}" + (f"-{letter}" if letter else "")

    if ali_m:
        letter = ali_m.group(1).lower()
        parent = base if inc_m else (ctx.inc_path or base)
        parent = re.sub(r"\.(ali|item)[\w-]+$", "", parent)
        return f"{parent}.ali-{letter}"

    # Alvo só "Inciso VI" / "§ 1º" / "Parágrafo único" / "Alínea a"
    if re.match(r"^Inciso\s+", t, re.I) and inc_m:
        return base if ".inc" in base else None
    if re.match(r"^§\s*", t) and par_m:
        return f"{_art_root(ctx.art_path or '')}.par{int(par_m.group(1))}" if ctx.art_path else None
    if re.match(r"^Par[aá]grafo\s+[uú]nico", t, re.I) and ctx.art_path:
        return f"{ctx.art_path}.parunico"
    if re.match(r"^Al[ií]nea\s+", t, re.I) and ali_m:
        parent = ctx.inc_path or ctx.par_path or ctx.art_path
        if not parent:
            return None
        parent = re.sub(r"\.(ali|item)[\w-]+$", "", parent)
        return f"{parent}.ali-{ali_m.group(1).lower()}"

    return base if re.match(r"^(?:Art|Caput)", t, re.I) else None


def _art_root(path: str) -> str:
    m = re.match(r"^((?:(?:anexo|suplemento)-[^/]+/)*)(art\d+(?:-[A-Z])?)", path)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    return path.split(".")[0]


def _pref(ctx: _Ctx, path: str) -> str:
    return f"{ctx.scope}/{path}" if ctx.scope else path


def _push_text(ctx: _Ctx, text: str) -> None:
    ctx.doc_parts.append(text)
    ctx.doc_parts.append("\n")
    ctx.doc_len += len(text) + 1


def _append_continuation(ctx: _Ctx, text: str) -> None:
    if not ctx.last_path or ctx.last_path not in ctx.provisions:
        _push_text(ctx, text)
        return
    prov = ctx.provisions[ctx.last_path]
    if not prov.redactions:
        _push_text(ctx, text)
        return
    target = None
    for red in reversed(prov.redactions):
        if not red.struck:
            target = red
            break
    if target is None:
        target = prov.redactions[-1]
    start = ctx.doc_len
    _push_text(ctx, text)
    end = start + len(text)
    extra = _normalize_ws(text)
    if extra:
        target.text = _normalize_ws(f"{target.text} {extra}")
    target.span = (target.span[0], end)


def _add_red(
    ctx: _Ctx,
    path: str,
    label: str,
    body: str,
    struck: bool,
    full: str,
) -> None:
    start = ctx.doc_len
    _push_text(ctx, full)
    end = start + len(full)
    if path not in ctx.provisions:
        ctx.provisions[path] = Provision(
            path=path,
            label=label,
            scope=ctx.scope,
            headings=list(ctx.headings),
            redactions=[],
        )
    prov = ctx.provisions[path]
    prov.redactions.append(
        Redaction(
            text=body,
            struck=struck,
            order=len(prov.redactions),
            annotations=[],
            span=(start, end),
        )
    )
    ctx.last_path = path


def _add_mixed(
    ctx: _Ctx,
    path: str,
    label: str,
    para: _Para,
    full: str,
) -> None:
    sk = _classify(para.struck_text)
    lk = _classify(para.live_text)
    s_body = _normalize_ws(sk[1]["rest"] if sk else para.struck_text)
    l_body = _normalize_ws(lk[1]["rest"] if lk else para.live_text)
    _add_red(ctx, path, label, s_body, True, full)
    _add_red(ctx, path, label, l_body, False, full)
    ctx.issues.append(
        Issue(
            "MIXED_STRIKE",
            path,
            "parágrafo com segmentos riscados e não riscados",
            blocking_scope="provision",
        )
    )
