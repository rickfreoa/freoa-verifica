"""Comparação versionada de trechos com texto oficial."""

from __future__ import annotations

import difflib
import unicodedata
from dataclasses import dataclass, field

ALGO_VERSION = "textcmp-1"

# Aspas tipográficas → retas
_QUOTE_MAP = {
    "\u201c": '"',  # “
    "\u201d": '"',  # ”
    "\u2018": "'",  # ‘
    "\u2019": "'",  # ’
    "\u00ab": '"',  # «
    "\u00bb": '"',  # »
}

# Travessão / meia-risca → hífen
_DASH_MAP = {
    "\u2014": "-",  # —
    "\u2013": "-",  # –
    "\u2212": "-",  # minus
}


@dataclass
class CmpResult:
    status: str  # match|partial|no_match
    start: int | None  # offset no texto_oficial original
    end: int | None
    transforms: list[str] = field(default_factory=list)
    diff: str | None = None


def _collapse_spaces(s: str) -> tuple[str, list[str]]:
    """NFC + colapso de espaços (NBSP, tabs, quebras) → espaço simples."""
    transforms: list[str] = []
    out = unicodedata.normalize("NFC", s)
    if out != s:
        transforms.append("nfc")
    # NBSP e afins → espaço
    replaced = out.replace("\xa0", " ").replace("\u202f", " ").replace("\u2007", " ")
    if replaced != out:
        transforms.append("nbsp")
        out = replaced
    # tabs / quebras → espaço
    import re

    collapsed = re.sub(r"[\t\r\n\f\v]+", " ", out)
    if collapsed != out:
        transforms.append("whitespace_break")
        out = collapsed
    collapsed2 = re.sub(r" {2,}", " ", out)
    if collapsed2 != out:
        transforms.append("space_collapse")
        out = collapsed2
    return out, transforms


def normalize(s: str, mode: str = "literal") -> tuple[str, list[str]]:
    """Normaliza `s` no modo dado. Nunca altera dígitos, diacríticos nem ordem.

    Retorna (texto_normalizado, lista_de_transformações).
    """
    if mode not in ("literal", "normalizado"):
        raise ValueError(f"modo desconhecido: {mode!r}")
    out, transforms = _collapse_spaces(s)
    if mode == "literal":
        return out, transforms

    # aspas tipográficas
    buf: list[str] = []
    quoted = False
    dashed = False
    for ch in out:
        if ch in _QUOTE_MAP:
            buf.append(_QUOTE_MAP[ch])
            quoted = True
        elif ch in _DASH_MAP:
            buf.append(_DASH_MAP[ch])
            dashed = True
        else:
            buf.append(ch)
    if quoted:
        transforms.append("quotes")
    if dashed:
        transforms.append("dashes")
    out = "".join(buf)

    # espaço antes de pontuação
    import re

    cleaned = re.sub(r"\s+([,.;:!?%])", r"\1", out)
    if cleaned != out:
        transforms.append("space_before_punct")
        out = cleaned

    lower = out.lower()
    if lower != out:
        transforms.append("lowercase")
        out = lower
    return out, transforms


def _map_norm_to_orig(original: str, mode: str) -> list[int]:
    """Para cada índice no texto normalizado, o índice correspondente no original.

    Construído reaplicando a mesma lógica caractere a caractere de forma
    aproximada: usamos a normalização do original e alinhamos via varredura.
    """
    # Abordagem: construir normalizado acumulando e registrar origem
    import re

    nfc = unicodedata.normalize("NFC", original)
    # Mapa nfc_index → original_index (NFC pode fundir; usamos proporção simples)
    # Como NFC em PT-BR quase nunca funde graphemes aqui, alinhamos 1:1 se lens iguais
    if len(nfc) == len(original):
        base_map = list(range(len(nfc)))
        text = nfc
    else:
        # fallback: cada char NFC aponta para min(i, len-1) no original
        base_map = [min(i, len(original) - 1) for i in range(len(nfc))]
        text = nfc

    # Substituir NBSP etc. mantendo índice
    chars: list[str] = []
    origins: list[int] = []
    for i, ch in enumerate(text):
        if ch in ("\xa0", "\u202f", "\u2007"):
            chars.append(" ")
        elif ch in "\t\r\n\f\v":
            chars.append(" ")
        else:
            chars.append(ch)
        origins.append(base_map[i] if base_map else i)

    # Colapsar espaços consecutivos
    chars2: list[str] = []
    origins2: list[int] = []
    prev_space = False
    for ch, orig in zip(chars, origins):
        if ch == " ":
            if prev_space:
                continue
            prev_space = True
            chars2.append(ch)
            origins2.append(orig)
        else:
            prev_space = False
            chars2.append(ch)
            origins2.append(orig)

    if mode == "literal":
        return origins2

    # normalizado: aspas, dashes, espaço antes de pontuação, lower
    chars3: list[str] = []
    origins3: list[int] = []
    for ch, orig in zip(chars2, origins2):
        if ch in _QUOTE_MAP:
            chars3.append(_QUOTE_MAP[ch])
            origins3.append(orig)
        elif ch in _DASH_MAP:
            chars3.append(_DASH_MAP[ch])
            origins3.append(orig)
        else:
            chars3.append(ch)
            origins3.append(orig)

    # remover espaço antes de pontuação
    chars4: list[str] = []
    origins4: list[int] = []
    i = 0
    while i < len(chars3):
        if (
            chars3[i] == " "
            and i + 1 < len(chars3)
            and chars3[i + 1] in ",.;:!?%"
        ):
            i += 1
            continue
        chars4.append(chars3[i].lower())
        origins4.append(origins3[i])
        i += 1
    return origins4


def _lexical_boundaries(haystack: str, start: int, length: int) -> bool:
    """Exige fronteira lexical nas duas pontas (não alfanumérico ou início/fim)."""
    if length <= 0:
        return False
    if start > 0 and haystack[start - 1].isalnum():
        return False
    end = start + length
    if end < len(haystack) and haystack[end].isalnum():
        return False
    return True


def _find_with_boundaries(haystack: str, needle: str) -> int:
    """Primeira ocorrência de needle com fronteiras lexicais; -1 se nenhuma."""
    start = 0
    while True:
        idx = haystack.find(needle, start)
        if idx < 0:
            return -1
        if _lexical_boundaries(haystack, idx, len(needle)):
            return idx
        start = idx + 1


def compare(trecho: str, texto_oficial: str, mode: str = "literal", *, exact_only: bool = False) -> CmpResult:
    """Compara `trecho` com `texto_oficial` no modo dado."""
    norm_t, tr_t = normalize(trecho, mode)
    norm_o, tr_o = normalize(texto_oficial, mode)
    transforms = list(dict.fromkeys(tr_t + tr_o))  # únicos, ordem estável

    if not norm_t:
        return CmpResult("no_match", None, None, transforms, None)

    idx = _find_with_boundaries(norm_o, norm_t)
    if idx >= 0:
        origins = _map_norm_to_orig(texto_oficial, mode)
        # idx e idx+len no espaço normalizado → original
        if origins and idx < len(origins):
            start = origins[idx]
            end_idx = idx + len(norm_t) - 1
            end = origins[min(end_idx, len(origins) - 1)] + 1
        else:
            start, end = idx, idx + len(norm_t)
        return CmpResult("match", start, end, transforms, None)

    if exact_only:
        return CmpResult("no_match", None, None, transforms, None)

    # Partial: maior subsequência comum (ratio) via difflib
    matcher = difflib.SequenceMatcher(a=norm_t, b=norm_o, autojunk=False)
    blocks = matcher.get_matching_blocks()
    # maior bloco contínuo
    best = max(blocks, key=lambda b: b.size) if blocks else None
    if best and best.size >= 0.85 * len(norm_t) and best.size > 0:
        origins = _map_norm_to_orig(texto_oficial, mode)
        if origins and best.b < len(origins):
            start = origins[best.b]
            end_idx = best.b + best.size - 1
            end = origins[min(end_idx, len(origins) - 1)] + 1
        else:
            start, end = best.b, best.b + best.size
        diff = "\n".join(
            difflib.unified_diff(
                norm_t.splitlines() or [norm_t],
                norm_o[best.b : best.b + best.size].splitlines()
                or [norm_o[best.b : best.b + best.size]],
                lineterm="",
                n=1,
            )
        )
        if not diff:
            # trecho vs janela maior
            window = norm_o[max(0, best.b - 20) : best.b + best.size + 20]
            diff = "\n".join(
                difflib.unified_diff(
                    [norm_t],
                    [window],
                    fromfile="trecho",
                    tofile="oficial",
                    lineterm="",
                )
            )
        return CmpResult("partial", start, end, transforms, diff[:2000])

    # ratio global como fallback para partial
    ratio = matcher.ratio()
    if ratio >= 0.85:
        diff = "\n".join(
            difflib.unified_diff(
                [norm_t[:500]],
                [norm_o[:500]],
                fromfile="trecho",
                tofile="oficial",
                lineterm="",
            )
        )
        return CmpResult("partial", None, None, transforms, diff[:2000])

    diff = "\n".join(
        difflib.unified_diff(
            [norm_t[:300]],
            [norm_o[:300]],
            fromfile="trecho",
            tofile="oficial",
            lineterm="",
        )
    )
    return CmpResult("no_match", None, None, transforms, diff[:2000] if diff else None)
