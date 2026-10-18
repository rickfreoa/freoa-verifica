"""Caminho canônico de dispositivos normativos."""

from __future__ import annotations

import re

_ROMAN_MAP = {
    "M": 1000,
    "CM": 900,
    "D": 500,
    "CD": 400,
    "C": 100,
    "XC": 90,
    "L": 50,
    "XL": 40,
    "X": 10,
    "IX": 9,
    "V": 5,
    "IV": 4,
    "I": 1,
}

_ARABIC_TO_ROMAN = [
    (1000, "M"),
    (900, "CM"),
    (500, "D"),
    (400, "CD"),
    (100, "C"),
    (90, "XC"),
    (50, "L"),
    (40, "XL"),
    (10, "X"),
    (9, "IX"),
    (5, "V"),
    (4, "IV"),
    (1, "I"),
]


def roman_to_int(text: str) -> int:
    s = text.strip().upper()
    if not s or not re.fullmatch(r"[IVXLCDM]+", s):
        raise ValueError(f"romano inválido: {text!r}")
    i = 0
    total = 0
    while i < len(s):
        if i + 1 < len(s) and s[i : i + 2] in _ROMAN_MAP:
            total += _ROMAN_MAP[s[i : i + 2]]
            i += 2
        else:
            total += _ROMAN_MAP[s[i]]
            i += 1
    return total


def int_to_roman(n: int) -> str:
    if n <= 0:
        raise ValueError(n)
    out: list[str] = []
    for value, numeral in _ARABIC_TO_ROMAN:
        while n >= value:
            out.append(numeral)
            n -= value
    return "".join(out)


def _art_num_label(num: str, letter: str | None) -> str:
    if letter:
        return f"{num}-{letter}"
    try:
        n = int(num)
    except ValueError:
        return num
    if n < 10:
        return f"{n}º"
    return str(n)


def path_to_label(path: str) -> str:
    """Converte caminho canônico em rótulo legível (ex.: art. 254-A, § 1º)."""
    scope_parts: list[str] = []
    rest = path
    while "/" in rest:
        head, rest = rest.split("/", 1)
        scope_parts.append(head)

    parts = rest.split(".")
    chunks: list[str] = []
    for part in parts:
        if part.startswith("art"):
            body = part[3:]
            m = re.fullmatch(r"(\d+)(?:-([A-Z]))?", body)
            if not m:
                chunks.append(part)
                continue
            chunks.append(f"art. {_art_num_label(m.group(1), m.group(2))}")
        elif part == "parunico":
            chunks.append("parágrafo único")
        elif part == "caput":
            chunks.append("caput")
        elif part.startswith("par"):
            n = part[3:]
            m = re.fullmatch(r"(\d+)(?:-([A-Z]))?", n)
            if m:
                label = m.group(1) + (f"-{m.group(2)}" if m.group(2) else "")
                chunks.append(f"§ {label}º" if not m.group(2) else f"§ {label}")
            else:
                chunks.append(part)
        elif part.startswith("inc"):
            body = part[3:]
            m = re.fullmatch(r"(\d+)(?:-([A-Z]))?", body)
            if m:
                roman = int_to_roman(int(m.group(1)))
                if m.group(2):
                    roman = f"{roman}-{m.group(2)}"
                chunks.append(f"inciso {roman}")
            else:
                chunks.append(part)
        elif part.startswith("ali-"):
            chunks.append(f"alínea {part[4:]}")
        elif part.startswith("item"):
            chunks.append(f"item {part[4:]}")
        else:
            chunks.append(part)

    label = ", ".join(chunks)
    for sc in reversed(scope_parts):
        if sc.startswith("anexo-"):
            token = sc[6:].upper()
            label = f"anexo {token}, {label}"
        elif sc.startswith("suplemento-"):
            token = sc[11:].upper()
            label = f"suplemento {token}, {label}"
    return label


_LETTER_SEP = r"[-–—]"

_ART_RE = re.compile(
    rf"^[Aa]rt\s*\.?\s*((?:\d{{1,3}}(?:\.\d{{3}})+)|\d+)[oa]?(?:{_LETTER_SEP}([A-Za-z]))?\s*\.?",
)
_PAR_RE = re.compile(
    rf"^(?:§|Par[aá]grafo)\s*(\d+)[oa]?(?:{_LETTER_SEP}([A-Za-z]))?\s*\.?",
    re.I,
)
_PAR_UNICO_RE = re.compile(r"^Par[aá]grafo\s+[uú]nico\b", re.I)
_INC_RE = re.compile(rf"^([IVXLCDM]+)(?:{_LETTER_SEP}([A-Za-z]))?\s*", re.I)
_ALI_RE = re.compile(r"^([a-z])\)\s*", re.I)
_ITEM_RE = re.compile(r"^(\d+)[.)]\s*")
_CAPUT_RE = re.compile(r"^caput\b", re.I)
_FULL_CITATION_SPLIT = re.compile(r",\s*")


def _normalize_label_text(label: str) -> str:
    t = label.replace("\xa0", " ")
    t = re.sub(r"\s+", " ", t).strip()
    t = t.replace("º", "o").replace("°", "o").replace("ª", "a")
    return t


def _article_num(num: str) -> int:
    """Converte número de artigo, inclusive com ponto de milhar (2.002 → 2002)."""
    return int(num.replace(".", ""))


def _article_path(num: str, letter: str | None) -> str:
    letter_u = letter.upper() if letter else None
    n = _article_num(num)
    if letter_u:
        return f"art{n}-{letter_u}"
    return f"art{n}"


def _paragraph_seg(num: str, letter: str | None) -> str:
    if letter:
        return f"par{int(num)}-{letter.upper()}"
    return f"par{int(num)}"


def _inciso_seg(roman: str, letter: str | None) -> str:
    n = roman_to_int(roman)
    if letter:
        return f"inc{n}-{letter.upper()}"
    return f"inc{n}"


def label_to_path(
    label: str,
    *,
    parent: str | None = None,
    scope: str = "",
) -> str:
    """Converte rótulo textual (absoluto ou relativo) em caminho canônico.

    Exemplos:
      label_to_path("Art. 254-A") -> art254-A
      label_to_path("§ 1º", parent="art254-A") -> art254-A.par1
      label_to_path("Art. 254-A, § 1º") -> art254-A.par1
    """
    prefix = f"{scope}/" if scope else ""
    raw = label.strip()
    # Citação composta: "Art. 254-A, § 1º" / "art. 2º, inciso XVI"
    if "," in raw and re.search(r"[Aa]rt", raw):
        pieces = _FULL_CITATION_SPLIT.split(raw)
        path = label_to_path(pieces[0], scope=scope)
        for piece in pieces[1:]:
            path = label_to_path(piece.strip(), parent=path, scope="")
        return path if not scope else (
            path if path.startswith(prefix) else prefix + path
        )

    text = _normalize_label_text(raw)
    # Remove leading ordinal markers noise
    text = re.sub(r"^[•\-\u2013\u2014]\s*", "", text)

    m = _ART_RE.match(text)
    if m:
        letter = m.group(2)
        path = _article_path(m.group(1), letter)
        return prefix + path

    _SCOPE_ART = r"((?:(?:anexo|suplemento)-[^/]+/)*)(art[\d]+(?:-[A-Z])?)"

    if _PAR_UNICO_RE.match(text) or text.lower().startswith("paragrafo unico"):
        if not parent:
            raise ValueError("parágrafo único exige parent")
        art_m = re.match(_SCOPE_ART, parent)
        if art_m:
            return f"{art_m.group(1)}{art_m.group(2)}.parunico"
        return f"{parent}.parunico"

    m = _PAR_RE.match(text)
    if m or text.startswith("§"):
        if not m:
            m = re.match(r"^§\s*(\d+)[oa]?(?:-([A-Za-z]))?", text)
        if not m:
            raise ValueError(f"parágrafo inválido: {label!r}")
        if not parent:
            raise ValueError("parágrafo exige parent")
        art_m = re.match(_SCOPE_ART, parent)
        if not art_m:
            raise ValueError(f"parent sem artigo: {parent!r}")
        letter = m.group(2) if m.lastindex and m.lastindex >= 2 else None
        num = m.group(1)
        return f"{art_m.group(1)}{art_m.group(2)}.{_paragraph_seg(num, letter)}"

    if _CAPUT_RE.match(text):
        if not parent:
            raise ValueError("caput exige parent")
        art_m = re.match(_SCOPE_ART, parent)
        if not art_m:
            raise ValueError(f"parent sem artigo: {parent!r}")
        return f"{art_m.group(1)}{art_m.group(2)}.caput"

    # inciso por extenso
    m = re.match(rf"^[Ii]nciso\s+([IVXLCDM]+)(?:{_LETTER_SEP}([A-Za-z]))?\b", text)
    if m:
        if not parent:
            raise ValueError("inciso exige parent")
        return _attach_inciso(parent, m.group(1), m.group(2))

    m = _INC_RE.match(text)
    if m and (parent is not None):
        # Only treat as romano if it looks like an inciso line (followed by dash or end)
        rest = text[m.end() :]
        if rest == "" or rest[:1] in "-–—." or rest.startswith(" "):
            # Avoid matching lone "I" in prose when no separator — require separator
            # when rest is non-empty unless called as bare roman from citation
            if rest == "" or rest.lstrip()[:1] in "-–—" or rest.startswith("-"):
                return _attach_inciso(parent, m.group(1), m.group(2))
            if re.match(r"^[IVXLCDM]+(?:-[A-Za-z])?\s*$", text, re.I):
                return _attach_inciso(parent, m.group(1), m.group(2))

    m = re.match(r"^[Aa]l[ií]nea\s+([a-z])\b", text, re.I)
    if m:
        if not parent:
            raise ValueError("alínea exige parent")
        return _attach_alinea(parent, m.group(1))

    m = _ALI_RE.match(text)
    if m and parent is not None:
        return _attach_alinea(parent, m.group(1))

    m = re.match(r"^[Ii]tem\s+(\d+)\b", text)
    if m:
        if not parent:
            raise ValueError("item exige parent")
        return _attach_item(parent, m.group(1))

    m = _ITEM_RE.match(text)
    if m and parent is not None:
        return _attach_item(parent, m.group(1))

    raise ValueError(f"rótulo não reconhecido: {label!r}")


def _attach_inciso(parent: str, roman: str, letter: str | None) -> str:
    # inciso hangs off article or paragraph (strip deeper alinea/item/inciso)
    base = re.sub(r"\.(inc|ali|item)[\w-]+$", "", parent)
    # if parent already ends with inciso, replace
    base = re.sub(r"\.inc[\d]+(?:-[A-Z])?$", "", base)
    return f"{base}.{_inciso_seg(roman, letter)}"


def _attach_alinea(parent: str, letter: str) -> str:
    base = re.sub(r"\.(ali|item)[\w-]+$", "", parent)
    return f"{base}.ali-{letter.lower()}"


def _attach_item(parent: str, num: str) -> str:
    base = re.sub(r"\.item[\d]+(?:-[A-Z])?$", "", parent)
    return f"{base}.item{int(num)}"


def parse_article_key(path: str) -> tuple[int, str] | None:
    """Extrai (número, letra) do artigo raiz de um path, ou None."""
    m = re.search(r"(?:^|/)art(\d+)(?:-([A-Z]))?(?:\.|$)", path)
    if not m:
        return None
    return int(m.group(1)), m.group(2) or ""


def article_sort_key(path: str) -> tuple[int, str] | None:
    return parse_article_key(path)


def is_article_path(path: str) -> bool:
    return bool(
        re.fullmatch(
            r"(?:(?:anexo|suplemento)-[^/]+/)*art\d+(?:-[A-Z])?",
            path,
        )
    )


def _heading_token(raw: str) -> str:
    token = raw.strip()
    if re.fullmatch(r"[IVXLCDM]+", token, re.I):
        return token.lower()
    return token.lower()


def annex_scope_from_heading(text: str) -> str | None:
    """Se o texto for cabeçalho de anexo, devolve escopo canônico (anexo-i, anexo-a).

    Aceita "ANEXO I", "ANEXO A", "ANEXO NORMATIVO I" (com ou sem travessão/título).
    """
    t = " ".join(text.split())
    # Remove dígitos de página colados no fim (sumário DOCX: "...FINANCEIRO85")
    t = re.sub(r"(?<=\D)\d{1,4}\s*$", "", t).strip()
    m = re.match(
        r"^ANEXO\s+(?:NORMATIVO\s+)?([IVXLCDM]+|[A-Z])\b",
        t,
        re.I,
    )
    if not m:
        return None
    return f"anexo-{_heading_token(m.group(1))}"


def supplement_scope_from_heading(text: str) -> str | None:
    """Cabeçalho de suplemento → suplemento-a / suplemento-b."""
    t = " ".join(text.split())
    t = re.sub(r"(?<=\D)\d{1,4}\s*$", "", t).strip()
    m = re.match(
        r"^SUPLEMENTO\s+([A-Z]|[IVXLCDM]+)\b",
        t,
        re.I,
    )
    if not m:
        return None
    return f"suplemento-{_heading_token(m.group(1))}"


def nest_supplement_scope(current_scope: str, supplement: str) -> str:
    """Aninha suplemento ao anexo corrente, se houver."""
    if not current_scope:
        return supplement
    parts = current_scope.split("/")
    annex_parts = [p for p in parts if p.startswith("anexo-")]
    if annex_parts:
        return f"{annex_parts[0]}/{supplement}"
    return supplement
