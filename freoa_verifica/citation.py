"""Extrator determinístico de citações jurídicas brasileiras."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from freoa_verifica.aliases import (
    ALIASES,
    ALIAS_SURFACES,
    CONTEXT_REQUIRED_ALIASES,
    WorkKey,
    fold_alias,
    lookup_alias,
    lookup_lrf,
)
from freoa_verifica.parsers.paths import label_to_path

# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DecisionKey:
    court: str  # stf|stj|tcu|cvm|…
    class_: str  # REsp|RE|ADI|…
    number: str
    uf: str | None = None
    organ: str | None = None
    year: int | None = None  # obrigatório na chave de acórdão TCU


@dataclass
class Citation:
    kind: str  # norma|decisao|sumula|tema|processo
    raw: str
    span: tuple[int, int]
    work: WorkKey | None = None
    path: str | None = None
    decision: DecisionKey | None = None
    confidence: str = "exata"  # exata|provavel
    flags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------

_MONTHS = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "março": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}


def _fold(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def expand_year(y: int) -> int:
    if y >= 100:
        return y
    return 1900 + y if y >= 30 else 2000 + y


def normalize_number(raw: str) -> str:
    """Remove pontos de milhar; preserva sufixo tipo 2.200-2 → 2200-2."""
    raw = raw.strip()
    m = re.fullmatch(r"([\d.]+)(-[\dA-Za-z]+)?", raw)
    if not m:
        return raw.replace(".", "")
    body = m.group(1).replace(".", "")
    suffix = m.group(2) or ""
    return body + suffix


def validate_cnj_dv(number: str) -> bool:
    """Valida dígito verificador CNJ (Res. CNJ 65/2008) — mod 97."""
    m = re.fullmatch(
        r"(\d{7})-(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})",
        number.strip(),
    )
    if not m:
        return False
    nnnnnnn, dd, aaaa, j, tr, oooo = m.groups()
    # NNNNNNNAAAAJTROOOO + DD deve ser ≡ 1 (mod 97)
    # Equivalente: DV = 98 - (NNNNNNNAAAAJTROOOO * 100 mod 97)
    base = int(nnnnnnn + aaaa + j + tr + oooo)
    expected = 98 - ((base * 100) % 97)
    if expected == 98:
        expected = 1
    return int(dd) == expected


# ---------------------------------------------------------------------------
# Dispositivos (art./§/inciso/alínea)
# ---------------------------------------------------------------------------

_ART_NUM = r"\d+(?:\.\d{3})?(?:-[A-Za-z])?[ºªo°]?(?!\w|\.\w|[-/]\w)"
_ART_TOKEN = rf"(?:arts?\.?|artigos?)\s*{_ART_NUM}(?:\s*(?:,|e)\s*{_ART_NUM})*"
_PAR_TOKEN = r"(?:§|par[aá]grafo)\s*(?:[uú]nico|\d+[ºªo°]?)"
_INC_TOKEN = r"(?:(?:inciso|inc\.)\s+)?[IVXLCDM]+(?:-[A-Za-z])?\b"
_ALI_TOKEN = r"(?:(?:al[ií]nea|al\.)\s+[\"'“‘(]?[a-z](?!\w)[\"'”’)]?|[\"'“‘(][a-z][\"'”’)]|[a-z](?!\w)(?=\s*(?:,|do\b|da\b|$)))"
_ITEM_TOKEN = r"item\s+\d+[ºªo°]?(?!\w|\.\d)"
_DEVICE_ATOM = rf"(?<!\w)(?:{_ART_TOKEN}|{_PAR_TOKEN}|{_ITEM_TOKEN}|caput\b|{_ALI_TOKEN}|{_INC_TOKEN})(?!\w|\.\w|[-/]\w)"
_DEVICE_CORE = (rf"(?:(?:anexo)\s+(?:[IVXLCDM]+|\d+|[A-Z])\b\s*,?\s*)?"
                rf"{_DEVICE_ATOM}(?:\s*(?:,\s*(?:(?:do|da|dos|das)\s+)?|(?:do|da|dos|das|e)\s+){_DEVICE_ATOM})*"
                rf"(?:\s+do\s+(?:anexo\s+(?:[IVXLCDM]+|\d+|[A-Z])|cap[ií]tulo\s+(?:[IVXLCDM]+|\d+))\b)?")
_DEVICE_RE = re.compile(_DEVICE_CORE, re.I)

# Gramática posterior fechada: não reutiliza a gramática anterior, que admite
# complementos de pertença e divisões expressamente ligadas à obra.
_POST_ROMAN = r"(?<![^\W\d_])[IVXLCDM]+(?![^\W\d_])"
_POST_ALINEA = r"(?:(?:al[ií]nea|al\.)\s+[\"'“‘]?[a-z](?!\w)[\"'”’]?|[\"'“‘][a-z][\"'”’]|[a-z](?!\w)(?=\s*(?:[,.;:)\"“«‘]|$)))"
_POST_ATOM = (
    rf"(?:{_ART_TOKEN}(?!\w)|{_PAR_TOKEN}(?!\w)|{_ITEM_TOKEN}(?!\w)"
    rf"|caput\b|(?:(?:inciso|inc\.)\s+)?{_POST_ROMAN}|{_POST_ALINEA})(?!\w|\.\w|[-/]\w)"
)
_POST_DEVICE_RE = re.compile(
    rf"[^\S\r\n]*[,–—][^\S\r\n]*(?:\r?\n(?![^\S\n]*\r?\n))?[^\S\r\n]*"
    rf"({_POST_ATOM}(?:\s*(?:,\s*|\be\s+){_POST_ATOM})*"
    rf"(?:\s+do\s+(?:anexo\s+(?:[IVXLCDM]+|\d+|[A-Z])|cap[ií]tulo\s+(?:[IVXLCDM]+|\d+)|caput)\b)?)", re.I,
)
# Marcadores gramaticais de pertença, sem catálogo de instrumentos ou verbos.
_POST_OWNER = re.compile(
    r"(?:pertencente\b|constante\b|inserid\w*|previst\w*|integrante\b)", re.I,
)
_CANONICAL_POST = re.compile(
    rf"arts?\.\s*{_ART_NUM}(?:\s*(?:,|e)\s*{_ART_NUM})*"
    rf"(?:\s*,\s*{_PAR_TOKEN})?(?:\s*,\s*(?:(?:inciso|inc\.)\s+)?{_POST_ROMAN})?",
    re.I,
)

# Ampliação exclusiva de propostas: não participa da gramática exata.
_POST_DETERMINER = r"(?:o|os|a|as|um|uns|uma|umas|seu|seus|sua|suas|ess[ea]s?|est[ea]s?|aquel[ea]s?|tais|tal|referid[oa]s?|mencionad[oa]s?)\b"
_PROBABLE_POST = re.compile(
    rf"(?:\bcuj[oa]s?\b|[:;\n]|\bnotadamente\b|\bespecialmente\b|"
    rf"\bem\s+especial\b|\bno\b|\bem\s+seu\b|\A\s*(?:lemos|consultamos|examinamos)\b|"
    rf":\s*\r?\n[ \t]*[-•]|\A\s*,?\s*{_POST_DETERMINER})\s*"
    rf"(?:{_POST_DETERMINER}\s+)*"
    rf"((?:{_ART_TOKEN}|{_PAR_TOKEN}|{_ITEM_TOKEN})"
    rf"(?:\s*(?:,\s*|\be\s+){_POST_ATOM})*"
    rf"(?:\s+do\s+(?:anexo\s+(?:[IVXLCDM]+|\d+|[A-Z])|cap[ií]tulo\s+(?:[IVXLCDM]+|\d+)|caput)\b)?)",
    re.I,
)
_PROBABLE_OWNER = re.compile(
    r"\b(?:pertence|extra[ií]d\w*|oriund\w*|estabelecid\w*|redigid\w*|"
    r"contid\w*|atribu[ií]d\w*|veiculad\w*|estipulad\w*)\b|"
    r"\bque\s+integra\b|\bcuj[oa]s?\s+(?:sede|origem)\b|\b[eé]\s+(?:parte|objeto)\s+(?:do|da)\b|"
    r"\b(?:relativ\w*|situad\w*|localizad\w*)\s+(?:ao|aos|à|às|no|na|nos|nas)\b|"
    r"\b(?:registrad\w*|consta|prev[eê])\s+(?:no|na|do|da)\b", re.I,
)


def _posterior_romans_valid(chain: str) -> bool:
    from freoa_verifica.parsers.paths import int_to_roman, roman_to_int

    # A conversão aritmética é permissiva; exigir também a grafia canônica
    # impede promover siglas como ICVM e CVM a números de inciso.
    return all(int_to_roman(roman_to_int(token)) == token.upper()
               for token in re.findall(r"(?<!\w)[IVXLCDM]+(?!\w)", chain, re.I))


def _posterior_labels(chain: str) -> str:
    """Normaliza romanos sem alterar letras de alínea ou a superfície citada."""
    def normalize(match: re.Match[str]) -> str:
        atom = match.group(0)
        if re.fullmatch(r"(?:inciso|inc\.)\s+[IVXLCDM]+", atom, re.I):
            return "inciso " + atom.split()[-1].upper()
        if re.fullmatch(r"[IVXLCDM]{2,}", atom, re.I):
            return atom.upper()
        return atom

    return re.sub(_POST_ATOM, normalize, chain, flags=re.I)


def _posterior_terminated(text: str, position: int, norm_start: int, cites: list[Citation]) -> bool:
    tail = text[position:]
    stripped = tail.lstrip()
    if not stripped or stripped[0] in '.;:"“”«»‘’':
        return True
    if stripped[0] == ')':
        stack = []
        for offset, char in enumerate(text[:position]):
            if char == '(':
                stack.append(offset)
            elif char == ')' and stack:
                stack.pop()
        return bool(stack and stack[-1] < norm_start)
    # Prosa e justaposição são propostas, nunca associações exatas.
    return bool(re.match(r",?\s+[^\W\d_]", tail)) or bool(re.match(r",\s*[“\"«‘]", tail))


def _split_article_numbers(chunk: str) -> list[str]:
    """Extrai números de artigo de 'arts. 116 e 117' ou 'art. 254-A'."""
    m = re.match(
        r"(?:arts?\.?|artigos?)\s+(.+)",
        chunk.strip(),
        re.I,
    )
    if not m:
        return []
    body = m.group(1)
    # corta em §/inciso/alínea/caput
    body = re.split(
        r"\s*,\s*(?:§|par[aá]grafo|inciso|al[ií]nea|caput)\b",
        body,
        maxsplit=1,
        flags=re.I,
    )[0]
    parts = re.split(r"\s*,\s*|\s+e\s+", body, flags=re.I)
    nums: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        nm = re.match(r"(\d+(?:\.\d{3})?(?:-[A-Za-z])?)[ºªo°]?", p)
        if nm:
            nums.append(nm.group(1))
    return nums


def _anexo_token_to_scope(token: str) -> str:
    if re.fullmatch(r"[IVXLCDM]+", token, re.I):
        from freoa_verifica.parsers.paths import int_to_roman, roman_to_int

        try:
            return f"anexo-{int_to_roman(roman_to_int(token)).lower()}"
        except ValueError:
            return f"anexo-{token.lower()}"
    return f"anexo-{token.lower()}"


def _anexo_scope(text: str) -> tuple[str, str]:
    """Extrai prefixo/sufixo de anexo e devolve (scope_path, resto sem anexo)."""
    t = text.strip()
    # "art. 1º do Anexo A"
    m_suf = re.match(
        r"(.+?)\s+do\s+(?:anexo|Anexo)\s+([IVXLCDM]+|\d+|[A-Za-z])\s*$",
        t,
        re.I,
    )
    if m_suf:
        return _anexo_token_to_scope(m_suf.group(2)), m_suf.group(1).strip()
    m = re.match(
        r"(?:anexo|Anexo)\s+([IVXLCDM]+|\d+|[A-Za-z])\s*,?\s*(.*)$",
        t,
        re.I | re.S,
    )
    if not m:
        return "", text
    token = m.group(1)
    rest = m.group(2).strip().lstrip(",").strip()
    scope = _anexo_token_to_scope(token)
    return scope, rest if rest else text


def _device_to_paths(device_text: str) -> list[str]:
    """Converte texto de dispositivo em um ou mais caminhos canônicos."""
    text = " ".join(device_text.split())
    text = re.sub(r"\binc\.", "inciso", text, flags=re.I)
    text = re.sub(r"\bal\.", "alínea", text, flags=re.I)
    text = re.sub(r"\s+do\s+cap[ií]tulo\s+[IVXLCDM\d]+$", "", text, flags=re.I)
    scope, body = _anexo_scope(text)
    # "Anexo II" sem artigo → só o escopo
    if scope and not re.search(
        r"art|§|inciso|caput|par[aá]grafo", body, re.I
    ):
        return [scope]

    text = body if scope else text

    def _scoped(paths: list[str]) -> list[str]:
        if not scope:
            return paths
        return [f"{scope}/{p}" if not p.startswith("anexo-") else p for p in paths]

    # Tokenização independente da ordem textual; hierarquia canônica explícita.
    from freoa_verifica.parsers.paths import roman_to_int
    art = re.search(r"(?:arts?\.?|artigos?)\s*(\d+(?:\.\d{3})?(?:-[A-Za-z])?)[ºªo°]?", text, re.I)
    if art and len(_split_article_numbers(text)) <= 1:
        path = "art" + str(int(art.group(1).split("-")[0].replace(".", "")))
        if "-" in art.group(1):
            path += "-" + art.group(1).split("-")[1].upper()
        rest = text[:art.start()] + text[art.end():]
        par = re.search(r"(?:§|par[aá]grafo)\s*([uú]nico|\d+)[ºªo°]?", rest, re.I)
        if par:
            path += ".par" + ("unico" if not par.group(1).isdigit() else str(int(par.group(1))))
            rest = rest[:par.start()] + rest[par.end():]
        if re.search(r"\bcaput\b", rest, re.I):
            path += ".caput"
        inc = re.search(r"(?:inciso\s+)?\b([IVXLCDM]+)(?:-([A-Za-z]))?\b", rest)
        if inc:
            try:
                path += ".inc" + str(roman_to_int(inc.group(1))) + ("-" + inc.group(2).upper() if inc.group(2) else "")
            except ValueError:
                return []
            rest = rest[:inc.start()] + rest[inc.end():]
        ali = re.search(r"al[ií]nea\s+[\"'“‘(]?([a-z])|[\"'“‘(]([a-z])[\"'”’)]|(?:^|,)\s*([a-z])(?=\s*(?:,|do\b|da\b|$))", rest, re.I)
        if ali:
            path += ".ali-" + next(g for g in ali.groups() if g).lower()
        item = re.search(r"\bitem\s+(\d+)", rest, re.I)
        if item:
            path += ".item" + str(int(item.group(1)))
        return _scoped([path])

    # arts. 116 e 117 → dois caminhos; com sufixos compartilhados só no 1º
    art_nums = _split_article_numbers(text)
    if len(art_nums) > 1:
        m = re.match(
            r"(?:arts?\.?|artigos?)\s+"
            r"(?:\d+(?:\.\d{3})?(?:-[A-Za-z])?[ºªo°]?"
            r"(?:\s*[,e]\s*\d+(?:\.\d{3})?(?:-[A-Za-z])?[ºªo°]?)*"
            r"(?:\s+e\s+\d+(?:\.\d{3})?(?:-[A-Za-z])?[ºªo°]?)?)"
            r"(.*)$",
            text,
            re.I,
        )
        suffix = (m.group(1) if m else "").strip().lstrip(",").strip()
        # Sufixo romano só se token completo (não prefixo de palavra)
        if suffix and not re.match(
            r"^(?:§|par[aá]grafo|inciso|al[ií]nea|caput|[IVXLCDM]+\b)",
            suffix,
            re.I,
        ):
            suffix = ""
        paths: list[str] = []
        for num in art_nums:
            label = f"art. {num}"
            if suffix:
                label = f"{label}, {suffix}"
            try:
                paths.append(label_to_path(label))
            except ValueError:
                try:
                    paths.append(label_to_path(f"art. {num}"))
                except ValueError:
                    pass
        return _scoped(paths)

    # Citação única composta — romano só com fronteira de palavra
    cleaned = text
    if re.search(r",\s*([IVXLCDM]+)\b", text) and "inciso" not in text.lower():
        cleaned = re.sub(
            r",\s*([IVXLCDM]+)(?:-([A-Za-z]))?\b",
            r", inciso \1",
            text,
            count=1,
        )
        cleaned = re.sub(
            r",\s*['\"]([a-z])['\"]",
            r", alínea \1",
            cleaned,
            flags=re.I,
        )
    else:
        cleaned = re.sub(
            r"\b([IVXLCDM]+)(?:-[A-Za-z])?\b",
            r"inciso \1",
            cleaned,
            count=1,
        )
        cleaned = re.sub(r"inciso\s+inciso\s+", "inciso ", cleaned, flags=re.I)
        cleaned = re.sub(
            r",\s*['\"]([a-z])['\"]",
            r", alínea \1",
            cleaned,
            flags=re.I,
        )
    # Não promover palavra comum a inciso (ex.: "disciplina" já barrado pelo \b)
    try:
        return _scoped([label_to_path(cleaned)])
    except ValueError:
        m = re.match(
            r"((?:arts?\.?|artigos?)\s+\d+(?:-[A-Za-z])?[ºªo°]?)", text, re.I
        )
        if m:
            try:
                return _scoped([label_to_path(m.group(1))])
            except ValueError:
                return []
        return []


# ---------------------------------------------------------------------------
# Obras (leis, resoluções, …)
# ---------------------------------------------------------------------------

_NUM = r"(\d+(?:\.\d+)*(?:-[\dA-Za-z]+)?)"
_YEAR = r"(\d{2,4})"

_WORK_PATTERNS: list[tuple[re.Pattern[str], str, str]] = []


def _compile_work_patterns() -> None:
    global _WORK_PATTERNS
    if _WORK_PATTERNS:
        return
    specs: list[tuple[str, str, str]] = [
        # Lei Complementar / LC
        (
            rf"\b(?:Lei\s+Complementar|LC)\s*(?:n\.?[º°o]?\.?\s*)?{_NUM}"
            rf"(?:\s*/\s*{_YEAR}|\s*,?\s*de\s+\d{{1,2}}\s+de\s+\w+\s+de\s+{_YEAR}|\s*,?\s*de\s+\d{{1,2}}/\d{{1,2}}/{_YEAR}|\s*,?\s*de\s+{_YEAR})?",
            "federal",
            "lei_complementar",
        ),
        # Decreto-Lei
        (
            rf"\bDecreto-Lei\s*(?:n\.?[º°o]?\.?\s*)?{_NUM}"
            rf"(?:\s*/\s*{_YEAR}|\s*,?\s*de\s+\d{{1,2}}\s+de\s+\w+\s+de\s+{_YEAR}|\s*,?\s*de\s+\d{{1,2}}/\d{{1,2}}/{_YEAR}|\s*,?\s*de\s+{_YEAR})?",
            "federal",
            "decreto_lei",
        ),
        # Medida Provisória / MP
        (
            rf"\b(?:Medida\s+Provis[oó]ria|MP)\s*(?:n\.?[º°o]?\.?\s*)?{_NUM}"
            rf"(?:\s*/\s*{_YEAR}|\s*,?\s*de\s+\d{{1,2}}\s+de\s+\w+\s+de\s+{_YEAR}|\s*,?\s*de\s+\d{{1,2}}/\d{{1,2}}/{_YEAR}|\s*,?\s*de\s+{_YEAR})?",
            "federal",
            "medida_provisoria",
        ),
        # Decreto (não Decreto-Lei)
        (
            rf"\bDecreto\s*(?:n\.?[º°o]?\.?\s*)?{_NUM}"
            rf"(?:\s*/\s*{_YEAR}|\s*,?\s*de\s+\d{{1,2}}\s+de\s+\w+\s+de\s+{_YEAR}|\s*,?\s*de\s+\d{{1,2}}/\d{{1,2}}/{_YEAR}|\s*,?\s*de\s+{_YEAR})?",
            "federal",
            "decreto",
        ),
        # Lei ordinária
        (
            rf"\bLei\s*(?:n\.?[º°o]?\.?\s*)?{_NUM}"
            rf"(?:\s*/\s*{_YEAR}|\s*,?\s*de\s+\d{{1,2}}\s+de\s+\w+\s+de\s+{_YEAR}|\s*,?\s*de\s+\d{{1,2}}/\d{{1,2}}/{_YEAR}|\s*,?\s*de\s+{_YEAR})?",
            "federal",
            "lei",
        ),
        # Constituição / CF/88
        (r"\bConstitui[cç][aã]o(?:\s+Federal)?\b", "federal", "constituicao"),
        # CVM
        (
            rf"\b(?:Resolu[cç][aã]o\s+CVM|RCVM|Res\.?\s*CVM)\s*(?:n\.?[º°o]?\.?\s*)?{_NUM}"
            rf"(?:\s*/\s*{_YEAR})?",
            "cvm",
            "resolucao",
        ),
        (
            rf"\b(?:Instru[cç][aã]o\s+CVM|ICVM|Instr?\.\s*CVM|IN\s+CVM)\s*(?:n\.?[º°o]?\.?\s*)?{_NUM}"
            rf"(?:\s*/\s*{_YEAR})?",
            "cvm",
            "instrucao",
        ),
        (
            rf"\b(?:Parecer\s+de\s+Orienta[cç][aã]o\s+CVM|PO\s+CVM)\s*(?:n\.?[º°o]?\.?\s*)?{_NUM}",
            "cvm",
            "parecer_orientacao",
        ),
        (
            rf"\bOf[ií]cio-Circular\s+CVM(?:/[A-Z]+)?\s*(?:n\.?[º°o]?\.?\s*)?{_NUM}"
            rf"(?:\s*/\s*{_YEAR})?",
            "cvm",
            "oficio_circular",
        ),
        # CMN
        (
            rf"\b(?:Resolu[cç][aã]o\s+CMN|Res\.?\s*CMN)\s*(?:n\.?[º°o]?\.?\s*)?{_NUM}"
            rf"(?:\s*/\s*{_YEAR})?",
            "cmn",
            "resolucao",
        ),
        # BCB
        (
            rf"\bResolu[cç][aã]o\s+BCB\s*(?:n\.?[º°o]?\.?\s*)?{_NUM}"
            rf"(?:\s*/\s*{_YEAR})?",
            "bcb",
            "resolucao_bcb",
        ),
        (
            rf"\bCircular\s*(?:n\.?[º°o]?\.?\s*)?{_NUM}"
            rf"(?:\s*/\s*{_YEAR})?",
            "bcb",
            "circular",
        ),
        (
            rf"\bCarta-Circular\s*(?:n\.?[º°o]?\.?\s*)?{_NUM}"
            rf"(?:\s*/\s*{_YEAR})?",
            "bcb",
            "carta_circular",
        ),
    ]
    _WORK_PATTERNS = [
        (re.compile(pat, re.I), auth, kind) for pat, auth, kind in specs
    ]


def _year_from_match(m: re.Match[str]) -> int | None:
    groups = [g for g in m.groups() if g is not None]
    # último grupo que parece ano
    years = []
    for g in groups[1:]:
        if re.fullmatch(r"\d{2,4}", g):
            years.append(expand_year(int(g)))
    return years[-1] if years else None


def _number_from_match(m: re.Match[str], kind: str) -> str:
    if kind == "constituicao":
        return "1988"
    groups = [g for g in m.groups() if g is not None]
    if not groups:
        return ""
    return normalize_number(groups[0])


# ---------------------------------------------------------------------------
# Decisões / súmulas / temas / processo
# ---------------------------------------------------------------------------

_DECISION_CLASSES = (
    r"(?:AgInt\s+no\s+)?(?:AREsp|REsp|EREsp|ARE|RE|ADI|ADC|ADPF|HC|MS|Rcl|AI)"
)

_DECISION_RE = re.compile(
    rf"\b({_DECISION_CLASSES})\s*(?:n\.?[º°o]?\.?\s*)?([\d.]+)"
    rf"(?:\s*/\s*(STF|STJ|[A-Z]{{2}}))?"
    rf"(?:\s+(?:do|da)\s+(STF|STJ))?",
    re.I,
)

_SUMULA_RE = re.compile(
    r"\bS[uú]mula\s+(Vinculante\s+)?(?:n\.?[º°o]?\.?\s*)?(\d+)"
    r"(?:\s*(?:/|do|da)\s*(STF|STJ))?",
    re.I,
)

_TEMA_RE = re.compile(
    r"\bTema\s+(Repetitivo\s+)?(?:n\.?[º°o]?\.?\s*)?([\d.]+)"
    r"(?:\s*(?:/|do|da)\s*(STF|STJ))?",
    re.I,
)

_ACORDAO_TCU_RE = re.compile(
    r"\bAc[oó]rd[aã]o\s+(?:TCU\s+)?(?:n\.?[º°o]?\.?\s*)?([\d.]+)\s*/\s*(\d{4})"
    r"(?:\s*[-–—]?\s*(?:TCU\s*)?[-–—]?\s*(Plen[aá]rio|1[ªa]\s*C[aâ]mara|2[ªa]\s*C[aâ]mara|[A-Za-z0-9/-]+))?",
    re.I,
)

_COURT_CTX_RE = re.compile(
    r"(?:/|,|\s)(?:do\s+|da\s+)?(STF|STJ)\b",
    re.I,
)

_NORMATIVE_CTX_RE = re.compile(
    r"(?:art\.?|artigos?|§|par[aá]grafo|inciso|al[ií]nea|caput|"
    r"\bdo\b|\bda\b|\bdos\b|\bdas\b|\bnos\s+termos\b|\bconforme\b|"
    r"\bsegundo\b|\bcom\s+base\b)",
    re.I,
)

_PAS_CVM_RE = re.compile(
    r"\b(?:PAS(?:\s+CVM)?|Processo(?:\s+Administrativo\s+Sancionador)?\s+CVM|CVM\s*[,–-]?\s*Processo)\s*(?:n\.?[º°o]?\.?\s*)?((?:\d{5}\.\d{6}/\d{4}-\d{2})|(?:RJ\s*\d{4}/\d+))",
    re.I,
)

_CNJ_RE = re.compile(
    r"\b(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})\b",
)

# Superfícies com/sem acento, mais longas primeiro
_ALIAS_SURFACES_SORTED = sorted(ALIAS_SURFACES, key=lambda x: len(x[0]), reverse=True)
_ALIAS_RE = re.compile(
    r"\b(?:"
    + "|".join(re.escape(surface).replace(r"\ ", r"\s+") for surface, _ in _ALIAS_SURFACES_SORTED if "/" not in surface)
    + r")(?!\w)",
    re.I,
)
_ALIAS_SURFACE_MAP: dict[str, WorkKey] = {
    fold_alias(surface): work for surface, work in ALIAS_SURFACES
}


_FALSE_FRIENDS = re.compile(
    r"\b(?:artigo\s+de\s+opini[aã]o|lei\s+de\s+murphy|lei\s+de\s+moore"
    r"|lei\s+seca\b|lei\s+do\s+retorno)\b",
    re.I,
)


def _court_of_class(cls: str) -> str:
    c = cls.upper().replace(" ", "")
    if c.startswith("AGINT"):
        c = re.sub(r"^AGINTNO", "", c)
    stj = {"RESP", "ARESP", "ERESP", "AGINTNOARESP", "AGINTNORESP"}
    stf = {"RE", "ARE", "ADI", "ADC", "ADPF", "HC", "MS", "RCL", "AI"}
    base = c
    for prefix in ("AGINTNO",):
        if base.startswith(prefix):
            base = base[len(prefix) :]
    if base in stj or c in stj:
        return "stj"
    if base in stf:
        return "stf"
    return "stj"


def _court_from_context(text: str, start: int, end: int, default: str) -> str:
    """Tribunal contextual explícito ('do STJ', '/STJ', 'STJ,') prevalece."""
    window = text[max(0, start - 5) : min(len(text), end + 24)]
    m = _COURT_CTX_RE.search(window)
    if m:
        return m.group(1).lower()
    # Também checa imediatamente após o match (já incluído no regex de decisão)
    return default


def _has_normative_context(text: str, start: int, end: int) -> bool:
    """CC/CF só com contexto normativo adjacente (não 'do' remoto)."""
    before = text[max(0, start - 40) : start]
    after = text[end : min(len(text), end + 40)]
    after = re.sub(r"^\s*/\s*\d{2,4}\b", "", after)
    # Imediatamente antes: "... do/da CF" ou "... art. … da "
    if re.search(
        r"(?:art\.?|artigos?|§|par[aá]grafo|inciso|al[ií]nea|caput|"
        r"\bdo|\bda|\bdos|\bdas)\s*$",
        before,
        re.I,
    ):
        return True
    # Imediatamente depois: "CF, art." / "CC art." / "CF/88" já coberto por outro padrão
    if re.match(
        r"\s*[,:]?\s*(?:art\.?|artigos?|§|par[aá]grafo|inciso|al[ií]nea|caput)\b",
        after,
        re.I,
    ):
        return True
    # Janela curta com "nos termos" / "conforme" antes
    if re.search(
        r"\b(?:nos\s+termos|conforme|segundo|com\s+base)\b",
        before,
        re.I,
    ):
        return True
    return False


def _reference_boundary(text: str, start: int, end: int) -> bool:
    """Pontuação de frase delimita; conectores de identificadores não delimitam."""
    # Parênteses e vírgulas dentro de endereços não são pontuação de frase.
    left = start
    right = end
    while left and not text[left - 1].isspace():
        left -= 1
    while right < len(text) and not text[right].isspace():
        right += 1
    envelope = text[left:right]
    if "://" in envelope or "@" in envelope or re.search(
        r"\.[A-Za-z][A-Za-z0-9]{1,9}(?:[?#]\S*)?$", envelope.rstrip(".,;:!?\"'”’»")
    ):
        return False
    if start and (text[start - 1].isalnum() or text[start - 1] in "_-/\\.@+%#‐‑"):
        return False
    if end < len(text):
        char = text[end]
        if char.isalnum() or char in "_-/\\@+%#‐‑":
            return False
        if char == "." and end + 1 < len(text) and (text[end + 1].isalnum() or text[end + 1] == "_"):
            return False
    return True


def _parse_work_match(
    m: re.Match[str], authority: str, kind: str, text: str
) -> Citation | None:
    raw = m.group(0)
    if not _reference_boundary(text, m.start(), m.end()):
        return None
    # Abreviações exigem caixa original e separação do número da norma.
    for token in re.finditer(r"\b(?:LC|MP|RCVM|ICVM|CF|CVM|CMN|BCB)\b", raw, re.I):
        if token[0] != token[0].upper():
            return None
    if re.search(r"[A-Za-zÀ-ÿ]\d", raw) or (m.end() < len(text) and text[m.end()].isalnum()):
        return None
    # Evitar Decreto-Lei casar como Decreto
    if kind == "decreto" and re.match(r"Decreto-Lei", raw, re.I):
        return None
    # Evitar "Lei Complementar" casar como Lei
    if kind == "lei" and re.match(r"Lei\s+Complementar", raw, re.I):
        return None
    # "lei de Murphy" etc.
    if kind == "lei" and _FALSE_FRIENDS.search(text[max(0, m.start() - 20) : m.end() + 20]):
        return None
    # Circular genérica sem contexto BCB — ainda authority=bcb conforme spec
    number = _number_from_match(m, kind)
    year = _year_from_match(m)
    if kind == "constituicao":
        year = 1988
        number = "1988"
    conf = "exata"
    if year is None:
        year = 0
        conf = "provavel"
    work = WorkKey(authority, kind, number, year)
    return Citation(
        kind="norma",
        raw=raw,
        span=(m.start(), m.end()),
        work=work,
        confidence=conf,
        flags=["apelido"] if kind == "constituicao" else [],
    )


# Pertença é estrutural: dispensa vocabulário de instrumentos privados.
_BELONGING = re.compile(
    r"\s*,?\s*(?:do|da|dos|das|de|no|na|nos|nas|"
    r"deste|desta|destes|destas|desse|dessa|desses|dessas|"
    r"daquele|daquela|daqueles|daquelas|neste|nesta|nesse|nessa)\b\s+(?=\w)", re.I,
)
_SAME_SCOPE = re.compile(
    r"(?:anexo\s+(?:[IVXLCDM]+|\d+|[A-Z])|cap[ií]tulo\s+(?:[IVXLCDM]+|\d+)|caput)\b", re.I,
)


def _foreign_complement(text: str, position: int, target: Citation) -> bool:
    """Só a própria referência ou sua divisão pode completar o dispositivo."""
    while complement := _BELONGING.match(text, position):
        position = complement.end()
        if position == target.span[0]:
            return False
        scope = _SAME_SCOPE.match(text, position)
        if scope is None:
            return True
        position = scope.end()
    return False


def _attach_devices(text: str, cites: list[Citation]) -> list[Citation]:
    """Associa dispositivos antes/depois da norma; expande arts. múltiplos."""
    result: list[Citation] = []
    for cite in cites:
        if cite.kind != "norma" or cite.work is None:
            result.append(cite)
            continue
        start, end = cite.span
        # Dispositivo ANTES: "... do/da <norma>" ou "..., da <norma>"
        before = text[max(0, start - 120) : start]
        # O complemento pertence ao dispositivo inteiro, inclusive em listas
        # longas; uma janela curta poderia cortar "do contrato" e inventar vínculo.
        after = text[end:]
        device_m = None
        confidence = cite.confidence
        # "art. X ... da Lei" / "arts. X e Y da LSA"
        m_before = re.search(
            rf"({_DEVICE_CORE})\s*,?\s*(?:do|da|dos|das)?\s*$",
            before,
            re.I,
        )
        # Uma letra isolada antes da obra pode ser artigo ou preposição.
        # Alíneas exigem rótulo, aspas ou um dispositivo composto.
        if m_before and re.fullmatch(r"[a-z]", m_before.group(1), re.I):
            m_before = None
        if m_before and _foreign_complement(text, start - len(before) + m_before.end(1), cite):
            m_before = None
        if m_before:
            device_start = start - len(before) + m_before.start(1)
            if any(previous.span[0] <= device_start < previous.span[1] for previous in result):
                m_before = None
            elif not re.search(r"\b(?:do|da|dos|das)\s*$", m_before.group(0), re.I):
                # Sem pertença explícita, não tomar a cadeia que segue outra obra.
                if any(other.span[1] <= device_start and not text[other.span[1]:device_start].strip(' ,')
                       for other in cites if other is not cite):
                    m_before = None
                else:
                    confidence = "provavel"
        if m_before:
            device_m = m_before
            device_text = m_before.group(1)
            abs_start = start - len(before) + m_before.start(1)
            abs_end = end
        else:
            # Abertura/fecho devem envolver somente a cadeia, sem texto extra.
            paired = re.match(r"\s*([(–—-])\s*", after)
            m_after = _POST_DEVICE_RE.match(after)
            possessive = re.match(rf"\s*,?\s*em\s+seu\s+({_DEVICE_CORE})", after, re.I)
            if possessive:
                m_after = possessive
            paired_end = None
            if paired:
                atom = re.match(rf"({_DEVICE_CORE})", after[paired.end():], re.I)
                if atom:
                    closing = ')' if paired[1] == '(' else paired[1]
                    close = re.match(rf"\s*{re.escape(closing)}", after[paired.end()+atom.end():])
                    if close:
                        m_after = re.match(rf"\s*{re.escape(paired[1])}\s*({_DEVICE_CORE})", after, re.I)
                        paired_end = paired.end() + atom.end() + close.end()
            if m_after:
                chain_end = end + m_after.end(1)
                chain = m_after.group(1)
                invalid = (
                    not _posterior_romans_valid(chain)
                    or any(end + m_after.start(1) <= other.span[0] < chain_end for other in cites if other is not cite)
                    or re.search(r"\n[ \t]*\n|\r\n[ \t]*\r\n", chain)
                    or _foreign_complement(text, chain_end, cite)
                )
                tail = text[chain_end:]
                predicate = re.split(r"[.;\n]", tail, maxsplit=1)[0]
                if _POST_OWNER.search(predicate):
                    invalid = True
                if paired and paired_end is None:
                    invalid = True
                if not paired_end and not _posterior_terminated(text, chain_end, start, cites):
                    invalid = True
                if invalid:
                    m_after = None
            if m_after:
                device_m = m_after
                device_text = _posterior_labels(m_after.group(1))
                abs_start = start
                abs_end = end + (paired_end or m_after.end(1))
                terminator = text[end + m_after.end(1):].lstrip()
                canonical = (not paired and after.lstrip().startswith(',')
                             and _CANONICAL_POST.fullmatch(m_after.group(1))
                             and (not terminator or terminator[0] in '.;:"“”«»‘’)' ))
                if not canonical:
                    confidence = "provavel"
                if (confidence == "provavel" and not paired_end
                        and not re.search(r"\bdo\s+(?:anexo|cap[ií]tulo|caput)\b", chain, re.I)
                        and _PROBABLE_OWNER.search(predicate)):
                    cite.flags.append("preferir_outro_referente")
            else:
                device_text = None
                abs_start, abs_end = start, end

            if device_text is None:
                # Não atravessar outra norma, nem recuperar delimitador sem par.
                limit = min([other.span[0] - end for other in cites
                             if other.span[0] >= end and other is not cite] or [len(after)])
                proposal = _PROBABLE_POST.search(after, 0, limit)
                proposal_end = None
                # Pares podem aparecer depois de prosa intermediária na janela.
                # Reutilizar só a cadeia, sem tornar essa busca canônica.
                if proposal is None and not paired:
                    for opening in re.finditer(r"[(–—]", after[:limit]):
                        if opening.end() > 120:
                            break
                        atom = re.compile(rf"\s*({_DEVICE_CORE})", re.I).match(after, opening.end())
                        if atom is None or atom.start(1) > 120:
                            continue
                        closing = ')' if opening[0] == '(' else opening[0]
                        close = re.match(rf"\s*{re.escape(closing)}", after[atom.end(1):limit])
                        if close:
                            proposal = atom
                            proposal_end = atom.end(1) + close.end()
                            break
                if proposal and proposal.start(1) <= 120 and not paired:
                    chain_end = end + proposal.end(1)
                    belonging = _BELONGING.match(text, chain_end)
                    other_owner = belonging and any(
                        belonging.end() == other.span[0] for other in cites if other is not cite
                    )
                    if (_posterior_romans_valid(proposal.group(1))
                            and not other_owner
                            and (proposal_end or _posterior_terminated(text, chain_end, start, cites))):
                        device_text = _posterior_labels(proposal.group(1))
                        abs_end = end + (proposal_end or proposal.end(1))
                        confidence = "provavel"
                        predicate = re.split(r"[.;\n]", text[chain_end:], maxsplit=1)[0]
                        if (not proposal_end and (_foreign_complement(text, chain_end, cite)
                                or _POST_OWNER.search(predicate)
                                or _PROBABLE_OWNER.search(predicate))):
                            cite.flags.append("preferir_outro_referente")

        if not device_text:
            invalid = re.search(r"((?:art(?:igo)?s?\.?|§|inciso|al[ií]nea|item)\s+[^.;:\n]{1,100}?)\s+(?:do|da)\s*$", before, re.I)
            if invalid and any(_foreign_complement(text, start - len(before) + invalid.start(1) + m.start(), cite) for m in _BELONGING.finditer(invalid.group(1))):
                invalid = None
            if invalid:
                a = start-len(before)+invalid.start(1)
                b = end
                cite.raw = text[a:b]
                cite.span = (a,b)
                cite.flags.append("dispositivo_invalido")
            result.append(cite)
            continue

        paths = _device_to_paths(device_text)
        if not paths:
            result.append(
                Citation(
                    kind=cite.kind,
                    raw=text[abs_start:abs_end],
                    span=(abs_start, abs_end),
                    work=cite.work,
                    path=None,
                    confidence=confidence,
                    flags=[*cite.flags, "dispositivo_invalido"],
                )
            )
            continue
        for path in paths:
            result.append(
                Citation(
                    kind=cite.kind,
                    raw=text[abs_start:abs_end],
                    span=(abs_start, abs_end),
                    work=cite.work,
                    path=path,
                    confidence=confidence,
                    flags=list(cite.flags),
                )
            )
    return result


_EXPLICIT_DEVICE_LABEL = re.compile(
    r"(?<!\w)(?:arts?\.?|artigos?|inciso|inc\.|al[ií]nea|al\.|item|par[aá]grafo|§)"
    r"(?=\s|\d|[_-])", re.I,
)
_NONLEGAL_FIELD = re.compile(
    r"\b(?:etiqueta|SKU|c[oó]digo|lote|chave|arquivo|ticker|placa)\b"
    r"[\"'”’`»]?\s*(?::\s*[\"'“‘`«]?|"
    r"(?:(?:tem\s+o\s+texto|[eé]|tem|cont[eé]m)\s+)?[\"'“‘`«])\s*$", re.I,
)


def _unattached_device_nearby(text: str, cite: Citation, cites: list[Citation]) -> bool:
    """Rótulo explícito sem vínculo: reter a dúvida, sem inventar caminho.

    Outra citação delimita a janela e conserva a pertença já reconhecida.
    """
    start, end = cite.span
    left = max([0, start - 120] + [c.span[1] for c in cites if c.span[1] <= start and c is not cite])
    right = min([len(text), end + 120] + [c.span[0] for c in cites if c.span[0] >= end and c is not cite])
    before, after = text[left:start], text[end:right]
    boundary = r"[.!?]\s+(?=[A-ZÀ-Ý])|\n\s*\n"
    before = re.split(boundary, before)[-1]
    after = re.split(boundary, after)[0]
    return bool(_EXPLICIT_DEVICE_LABEL.search(before) or _EXPLICIT_DEVICE_LABEL.search(after)
                or _EXPLICIT_DEVICE_LABEL.search(cite.raw))


def extract(texto: str) -> list[Citation]:
    """Extrai todas as citações reconhecidas em `texto`, sem sobreposição preferindo o mais longo."""
    if not texto:
        return []
    _compile_work_patterns()
    text = texto
    occupied = [False] * len(text)
    raw_cites: list[Citation] = []

    def _free(a: int, b: int) -> bool:
        return not any(occupied[a:b])

    def _mark(a: int, b: int) -> None:
        for i in range(a, b):
            occupied[i] = True

    # 1) CNJ
    for m in _CNJ_RE.finditer(text):
        if not _free(m.start(), m.end()):
            continue
        num = m.group(1)
        ok = validate_cnj_dv(num)
        flags = [] if ok else ["cnj_dv_invalido"]
        raw_cites.append(
            Citation(
                kind="processo",
                raw=num,
                span=(m.start(), m.end()),
                confidence="exata" if ok else "provavel",
                flags=flags,
            )
        )
        _mark(m.start(), m.end())

    # 2) PAS CVM
    for m in _PAS_CVM_RE.finditer(text):
        if not _free(m.start(), m.end()):
            continue
        raw_cites.append(
            Citation(
                kind="decisao",
                raw=m.group(0),
                span=(m.start(), m.end()),
                decision=DecisionKey("cvm", "PAS", m.group(1)),
                confidence="exata",
            )
        )
        _mark(m.start(), m.end())

    # 3) Acórdão TCU — chave inclui número, ano e colegiado
    for m in _ACORDAO_TCU_RE.finditer(text):
        if not _free(m.start(), m.end()):
            continue
        organ = m.group(3)
        year = int(m.group(2))
        raw_cites.append(
            Citation(
                kind="decisao",
                raw=m.group(0),
                span=(m.start(), m.end()),
                decision=DecisionKey(
                    "tcu",
                    "Acordao",
                    normalize_number(m.group(1)),
                    organ=organ.strip() if organ else None,
                    year=year,
                ),
                confidence="exata",
            )
        )
        _mark(m.start(), m.end())

    # 4) Súmula
    for m in _SUMULA_RE.finditer(text):
        if not _free(m.start(), m.end()):
            continue
        vinculante = bool(m.group(1))
        num = m.group(2)
        court = (m.group(3) or ("STF" if vinculante else "")).lower()
        if not court:
            court = "stf" if vinculante else "stj"
            conf = "provavel"
        else:
            conf = "exata"
        cls = "SumulaVinculante" if vinculante else "Sumula"
        raw_cites.append(
            Citation(
                kind="sumula",
                raw=m.group(0),
                span=(m.start(), m.end()),
                decision=DecisionKey(court, cls, num),
                confidence=conf,
            )
        )
        _mark(m.start(), m.end())

    # 5) Tema
    for m in _TEMA_RE.finditer(text):
        if not _free(m.start(), m.end()):
            continue
        repetitivo = bool(m.group(1))
        num = normalize_number(m.group(2))
        court = (m.group(3) or "").lower()
        conf = "exata" if court else "provavel"
        if not court:
            court = "stj" if repetitivo else "stf"
        raw_cites.append(
            Citation(
                kind="tema",
                raw=m.group(0),
                span=(m.start(), m.end()),
                decision=DecisionKey(court, "TemaRepetitivo" if repetitivo else "Tema", num),
                confidence=conf,
            )
        )
        _mark(m.start(), m.end())

    # 6) Decisões judiciais
    for m in _DECISION_RE.finditer(text):
        if not _free(m.start(), m.end()):
            continue
        cls = re.sub(r"\s+", " ", m.group(1)).strip()
        if cls.upper() == "RE" and m.start() > 0 and text[m.start() - 1].isalpha():
            continue
        num = normalize_number(m.group(2))
        # grupo 3 = /STJ|/STF|/UF; grupo 4 = "do STJ"
        token = m.group(3) or m.group(4)
        uf = None
        court = _court_of_class(cls)
        if token:
            tok = token.upper()
            if tok in ("STF", "STJ"):
                court = tok.lower()
            elif len(tok) == 2:
                uf = tok
        court = _court_from_context(text, m.start(), m.end(), court)
        raw_cites.append(
            Citation(
                kind="decisao",
                raw=m.group(0),
                span=(m.start(), m.end()),
                decision=DecisionKey(court, cls, num, uf=uf),
                confidence="exata",
            )
        )
        _mark(m.start(), m.end())

    # 7) Obras formais
    work_cites: list[Citation] = []
    for pat, auth, kind in _WORK_PATTERNS:
        for m in pat.finditer(text):
            if not _free(m.start(), m.end()):
                continue
            # Decreto-Lei: padrão Decreto não deve engolir
            if kind == "decreto" and text[m.start() : m.start() + 12].lower().startswith(
                "decreto-lei"
            ):
                continue
            c = _parse_work_match(m, auth, kind, text)
            if c is None:
                continue
            work_cites.append(c)
            _mark(m.start(), m.end())

    # 8) Apelidos
    for m in _ALIAS_RE.finditer(text):
        if not _free(m.start(), m.end()):
            continue
        token = m.group(0)
        if not _reference_boundary(text, m.start(), m.end()):
            continue
        if token.isalpha() and len(token) <= 5 and token != token.upper():
            continue
        folded = fold_alias(token)
        # LRF ambíguo
        if folded == "lrf":
            surrounding = text[max(0, m.start() - 80) : min(len(text), m.end() + 80)]
            candidates = lookup_lrf(token, surrounding)
            # Se o texto já citou LC 101 / Lei 11.101 formalmente, não duplicar LRF
            if len(candidates) == 1:
                # Preferir a obra explícita já marcada; senão emitir LRF desambiguado
                already = any(
                    c.work == candidates[0]
                    for c in work_cites
                    if c.work is not None
                )
                if already:
                    _mark(m.start(), m.end())
                    continue
                work_cites.append(
                    Citation(
                        kind="norma",
                        raw=m.group(0),
                        span=(m.start(), m.end()),
                        work=candidates[0],
                        confidence="exata",
                        flags=["apelido"],
                    )
                )
            else:
                for cand in candidates:
                    work_cites.append(
                        Citation(
                            kind="norma",
                            raw=m.group(0),
                            span=(m.start(), m.end()),
                            work=cand,
                            confidence="provavel",
                            flags=["alias_ambiguo"],
                        )
                    )
            _mark(m.start(), m.end())
            continue
        # CC / CF curtos exigem contexto normativo
        if folded in CONTEXT_REQUIRED_ALIASES:
            if (not _has_normative_context(text, m.start(), m.end())
                    and not _NONLEGAL_FIELD.search(text[max(0, m.start() - 100):m.start()])):
                continue
        work = (
            _ALIAS_SURFACE_MAP.get(folded)
            or lookup_alias(token)
            or ALIASES.get(folded)
        )
        if work is None:
            continue
        alias_end = m.end()
        work_cites.append(
            Citation(
                kind="norma",
                raw=text[m.start():alias_end],
                span=(m.start(), alias_end),
                work=work,
                confidence="exata",
                flags=["apelido"],
            )
        )
        _mark(m.start(), alias_end)

    # Campo rotulado delimita uso técnico da sigla, mesmo com artigo ao lado.
    for cite in work_cites:
        if "apelido" in cite.flags or "alias_ambiguo" in cite.flags:
            if _NONLEGAL_FIELD.search(text[max(0, cite.span[0] - 100):cite.span[0]]):
                cite.confidence = "provavel"
                cite.flags.append("campo_nao_juridico")

    # Anexar dispositivos às normas
    work_cites = _attach_devices(text, work_cites)
    for cite in work_cites:
        if cite.path is None and _unattached_device_nearby(text, cite, work_cites):
            cite.confidence = "provavel"
        if "apelido" in cite.flags:
            cite.flags.remove("apelido")
            if cite.path is None:
                cite.confidence = "provavel"
    raw_cites.extend(work_cites)

    # Ordenar por posição
    raw_cites.sort(key=lambda c: (c.span[0], -c.span[1]))
    return raw_cites


def parse_one(texto: str) -> Citation | None:
    """Parseia uma única citação (texto curto). Devolve a primeira ou None."""
    cites = extract(texto.strip())
    if not cites:
        return None
    # Preferir a que cobre mais do texto
    return max(cites, key=lambda c: c.span[1] - c.span[0])
