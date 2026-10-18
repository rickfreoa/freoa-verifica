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
    ancora_motivo: str | None = None  # preenchido quando a âncora foi recusada


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


def _map_norm_to_orig(original: str, mode: str) -> list[tuple[int, int]] | None:
    """Para cada caractere do texto normalizado, o intervalo (início, fim) no original.

    O mapa é construído durante a normalização, por grupo base+combinantes (NFC
    pode fundir ou expandir). Devolve None se o resultado não reproduzir
    `normalize(original, mode)`: nesse caso nenhuma âncora é confiável.
    """
    chars: list[str] = []
    spans: list[tuple[int, int]] = []
    i, n = 0, len(original)
    while i < n:
        j = i + 1
        while j < n and unicodedata.combining(original[j]):
            j += 1
        for ch in unicodedata.normalize("NFC", original[i:j]):
            if ch in "\xa0\u202f\u2007\t\r\n\f\v":
                ch = " "
            if ch == " " and chars and chars[-1] == " " and spans[-1][1] == i:
                spans[-1] = (spans[-1][0], j)  # colapso: o espaço cobre toda a corrida
                continue
            if mode == "normalizado":
                ch = _QUOTE_MAP.get(ch, _DASH_MAP.get(ch, ch))
            chars.append(ch)
            spans.append((i, j))
        i = j
    if mode == "normalizado":
        keep = [
            k for k, ch in enumerate(chars)
            if not (ch == " " and k + 1 < len(chars) and chars[k + 1] in ",.;:!?%")
        ]
        chars = [chars[k].lower() for k in keep]
        spans = [spans[k] for k in keep]
    if "".join(chars) != normalize(original, mode)[0]:
        return None
    return spans


def _anchor(original: str, mode: str, b: int, size: int, expected: str) -> tuple[int | None, int | None, str | None]:
    """Intervalo no original para norm[b:b+size]; recusa se não reproduzir `expected`."""
    spans = _map_norm_to_orig(original, mode)
    if not spans or size <= 0 or b + size > len(spans):
        return None, None, "mapa_indisponivel"
    start, end = spans[b][0], spans[b + size - 1][1]
    if normalize(original[start:end], mode)[0] != expected:
        return None, None, "intervalo_nao_reproduz_trecho"
    return start, end, None


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
        start, end, why = _anchor(texto_oficial, mode, idx, len(norm_t), norm_t)
        return CmpResult("match", start, end, transforms, None, why)

    if exact_only:
        return CmpResult("no_match", None, None, transforms, None)

    # Partial: maior subsequência comum (ratio) via difflib
    matcher = difflib.SequenceMatcher(a=norm_t, b=norm_o, autojunk=False)
    blocks = matcher.get_matching_blocks()
    # maior bloco contínuo
    best = max(blocks, key=lambda b: b.size) if blocks else None
    if best and best.size >= 0.85 * len(norm_t) and best.size > 0:
        start, end, why = _anchor(
            texto_oficial, mode, best.b, best.size, norm_o[best.b : best.b + best.size]
        )
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
        return CmpResult("partial", start, end, transforms, diff[:2000], why)

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
