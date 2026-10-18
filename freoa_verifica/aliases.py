"""Apelidos estáveis de obras normativas brasileiras → WorkKey."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkKey:
    """Chave de obra normativa (autoridade + espécie + número + ano)."""

    authority: str  # federal|cvm|cmn|bcb|stf|stj
    kind: str
    number: str
    year: int


# Apelidos canônicos (chave = fold_alias; valor = WorkKey).
_LSA = WorkKey("federal", "lei", "6404", 1976)
_CVM_LEI = WorkKey("federal", "lei", "6385", 1976)
_CC = WorkKey("federal", "lei", "10406", 2002)
_CPC = WorkKey("federal", "lei", "13105", 2015)
_CDC = WorkKey("federal", "lei", "8078", 1990)
_LRF_FALENCIAS = WorkKey("federal", "lei", "11101", 2005)
_LRF_RESPONSABILIDADE = WorkKey("federal", "lei_complementar", "101", 2000)
_CF = WorkKey("federal", "constituicao", "1988", 1988)

# LRF é ambíguo: Lei 11.101/2005 (falências) vs LC 101/2000 (responsabilidade fiscal).
LRF_CANDIDATES: tuple[WorkKey, WorkKey] = (_LRF_FALENCIAS, _LRF_RESPONSABILIDADE)

# Apelidos curtos que exigem contexto normativo (art., §, inciso, do/da).
CONTEXT_REQUIRED_ALIASES: frozenset[str] = frozenset({"cc", "cf"})

ALIASES: dict[str, WorkKey] = {
    "lei das s.a.": _LSA,
    "lei das s.a": _LSA,
    "lei das sa": _LSA,
    "lsa": _LSA,
    "lei das sociedades por acoes": _LSA,
    "lei do mercado de capitais": _CVM_LEI,
    "lei da cvm": _CVM_LEI,
    "codigo civil": _CC,
    "cc": _CC,
    "cpc": _CPC,
    "codigo de processo civil": _CPC,
    "cdc": _CDC,
    "codigo de defesa do consumidor": _CDC,
    "lei de falencias": _LRF_FALENCIAS,
    # "lrf" tratado à parte (ambíguo) — não entra em ALIASES unívoco
    "lei anticorrupcao": WorkKey("federal", "lei", "12846", 2013),
    "lgpd": WorkKey("federal", "lei", "13709", 2018),
    "marco da securitizacao": WorkKey("federal", "lei", "14430", 2022),
    "lei de arbitragem": WorkKey("federal", "lei", "9307", 1996),
    "constituicao": _CF,
    "cf": _CF,
    "cf/88": _CF,
    "constituicao federal": _CF,
}

# Formas de superfície (com e sem acento) para regex de extração.
ALIAS_SURFACES: list[tuple[str, WorkKey]] = [
    ("Lei das Sociedades por Ações", _LSA),
    ("Lei das Sociedades por Acoes", _LSA),
    ("Lei das S.A.", _LSA),
    ("Lei das S.A", _LSA),
    ("LSA", _LSA),
    ("Lei do Mercado de Capitais", _CVM_LEI),
    ("Lei da CVM", _CVM_LEI),
    ("Código Civil", _CC),
    ("Codigo Civil", _CC),
    ("CC", _CC),
    ("Código de Processo Civil", _CPC),
    ("Codigo de Processo Civil", _CPC),
    ("CPC", _CPC),
    ("Código de Defesa do Consumidor", _CDC),
    ("Codigo de Defesa do Consumidor", _CDC),
    ("CDC", _CDC),
    ("Lei de Falências", _LRF_FALENCIAS),
    ("Lei de Falencias", _LRF_FALENCIAS),
    ("Lei de Recuperação e Falências", _LRF_FALENCIAS),
    ("Lei de Recuperacao e Falencias", _LRF_FALENCIAS),
    ("Lei de Recuperação Judicial e Falências", _LRF_FALENCIAS),
    ("Lei de Recuperacao Judicial e Falencias", _LRF_FALENCIAS),
    ("Lei de Recuperação de Empresas e Falências", _LRF_FALENCIAS),
    ("LRF", _LRF_FALENCIAS),  # ambiguidade resolvida em citation.extract
    ("Lei Anticorrupção", WorkKey("federal", "lei", "12846", 2013)),
    ("Lei Anticorrupcao", WorkKey("federal", "lei", "12846", 2013)),
    ("LGPD", WorkKey("federal", "lei", "13709", 2018)),
    ("Marco da Securitização", WorkKey("federal", "lei", "14430", 2022)),
    ("Marco da Securitizacao", WorkKey("federal", "lei", "14430", 2022)),
    ("Lei de Arbitragem", WorkKey("federal", "lei", "9307", 1996)),
    ("Constituição Federal", _CF),
    ("Constituicao Federal", _CF),
    ("Constituição", _CF),
    ("Constituicao", _CF),
    ("CF/88", _CF),
    ("CF", _CF),
]


def fold_alias(text: str) -> str:
    """Normaliza texto para busca em ALIASES (minúsculas, sem diacríticos)."""
    import unicodedata

    nfkd = unicodedata.normalize("NFKD", text)
    bare = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(bare.lower().split())


def lookup_alias(text: str) -> WorkKey | None:
    key = fold_alias(text)
    if key == "lrf":
        return None  # ambíguo — ver lookup_lrf / citation
    return ALIASES.get(key)


def lookup_lrf(text: str, surrounding: str | None = None) -> list[WorkKey]:
    """Resolve LRF: se o entorno explicita a lei, devolve só ela; senão ambas."""
    ctx = surrounding or text
    folded = fold_alias(ctx)
    # LC 101 / Lei Complementar 101 / responsabilidade fiscal
    if re_search_lc101(folded) or "responsabilidade fiscal" in folded:
        return [_LRF_RESPONSABILIDADE]
    # Lei 11.101 / falências
    if (
        "11.101" in ctx
        or "11101" in folded.replace(".", "")
        or "falenc" in folded
        or "recuperacao judicial" in folded
        or "recuperação judicial" in fold_alias(ctx)
    ):
        return [_LRF_FALENCIAS]
    return list(LRF_CANDIDATES)


def re_search_lc101(folded: str) -> bool:
    import re

    return bool(
        re.search(
            r"\b(?:lc|lei\s+complementar)\s*(?:n[º°o.]?\s*)?101\b",
            folded,
            re.I,
        )
    )
