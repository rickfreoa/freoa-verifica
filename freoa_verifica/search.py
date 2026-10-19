"""Montagem literal e determinística de consultas locais FTS5."""
import json
import re
import unicodedata


_STOPWORDS = frozenset(
    "de da do das dos e a o as os em no na nos nas por para com que ao aos".split()
)


def normalize_fts_query(query: str, *, expanded: bool = False) -> str:
    """Preserva frases e aplica prefixos conservadores aos termos livres.

    Operadores e pontuação fornecidos pelo usuário nunca são sintaxe FTS.
    Aspa sem fechamento protege o restante como frase literal.
    """
    parts = []
    for match in re.finditer(r'"([^"]*)(?:"|$)|([^"\s]+)', query):
        phrase, free = match.groups()
        if phrase is not None:
            if re.search(r'[^\W_]', phrase):
                parts.append('"' + phrase + '"')
            continue
        folded = ''.join(c for c in unicodedata.normalize('NFD', free.lower())
                         if not unicodedata.combining(c))
        for term in re.findall(r'[^\W_]+', folded):
            if term in _STOPWORDS:
                continue
            root = term
            if term.isalpha() and len(term) >= 4:
                if term.endswith(('oes', 'aes')):
                    root = term[:-3]
                elif term.endswith(('ais', 'eis')):
                    root = term[:-2]
                elif term.endswith(('res', 'zes', 'ses', 'ns')):
                    root = term[:-2]
                elif term.endswith('s'):
                    root = term[:-1]
                if len(root) >= 4:
                    parts.append('"' + root + '"*')
                    continue
            parts.append('"' + term + '"')
    return (' OR ' if expanded else ' AND ').join(parts)


# ---------------------------------------------------------------------------
# Tesauro, pertinência e consulta AND completada por OR (decisão 0025)
# ---------------------------------------------------------------------------

_TESAURO: dict | None = None


def tesauro() -> dict:
    global _TESAURO
    if _TESAURO is None:
        from importlib import resources
        raw = resources.files("freoa_verifica").joinpath("data", "tesauro-1.json")
        _TESAURO = json.loads(raw.read_text(encoding="utf-8"))
    return _TESAURO


def _fold(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower())
                   if not unicodedata.combining(c))


def expandir_tesauro(query: str) -> tuple[list[str], list[dict]]:
    """Variantes da consulta com um termo do tesauro trocado pelo par; a original vem primeiro."""
    variantes, usados = [query], []
    folded = _fold(query)
    for a, b in tesauro()["pares"]:
        for termo, par in ((a, b), (b, a)):
            padrao = r'"?(?<!\w)' + re.escape(_fold(termo)) + r'(?!\w)"?'
            if re.search(padrao, folded) and len(variantes) < 12:
                variantes.append(re.sub(padrao, lambda _: f'"{par}"', folded, count=1))
                usados.append({"termo": termo, "alternativa": par})
    return variantes, usados


def consulta_fts(query: str, *, expanded: bool = False,
                 colunas: str | None = None) -> tuple[str, list[str], list[dict]]:
    """FTS com tesauro, `(Q1) OR (Q2)...`; devolve também as variantes e as expansões usadas."""
    variantes, usados = expandir_tesauro(query)
    partes = [p for p in (normalize_fts_query(v, expanded=expanded) for v in variantes) if p]
    fts = partes[0] if len(partes) == 1 else " OR ".join(f"({p})" for p in partes)
    if fts and colunas:
        fts = "{" + colunas + "} : (" + fts + ")"
    return fts, variantes, usados


def pertinencia(variantes: list[str], texto: str, peso=None) -> tuple[float, float]:
    """(peso dos termos encontrados, peso total) da melhor variante; palavra inteira ou prefixo conforme a
    consulta. Sem `peso`, cada termo vale 1; com `peso(termo, prefixo)`, vale a raridade no acervo (IDF)."""
    folded, melhor = _fold(texto or ""), (0, 1)
    for v in variantes:
        units = re.findall(r'"([^"]*)"(\*?)', normalize_fts_query(v))
        if not units:
            continue
        pesos = [peso(u, bool(star)) if peso else 1 for u, star in units]
        hits = sum(w for (u, star), w in zip(units, pesos)
                   if re.search(r'(?<!\w)' + re.escape(_fold(u)) + ('' if star else r'(?!\w)'), folded))
        total = sum(pesos) or 1
        if hits * melhor[1] > melhor[0] * total:
            melhor = (hits, total)
    return melhor


def passa_corte(hits: float, n: float) -> bool:
    # shortcut: até dois termos basta um (preserva a ampliação da 0010); acima, dois terços.
    return hits > 0 and (n <= 2 or hits * 3 >= 2 * n)


def buscar_and_or(q: str, buscar, texto, chave, total: int, minimo: int | None = None,
                  colunas: str | None = None, peso=None) -> dict:
    """AND primeiro (até `total` linhas); com menos de `minimo` (padrão `total`), completa com OR de pertinência acima do corte.

    `buscar(fts, limite)` devolve dicts por relevância; `texto(linha)` e `chave(linha)` extraem
    o texto e a identidade. Cada linha ganha `pertinencia` e `correspondencia`.
    """
    fts, variantes, usados = consulta_fts(q, colunas=colunas)
    out = {"linhas": [], "and": 0, "fts": fts,
           "tesauro": {"versao": tesauro()["versao"], "expansoes": usados}}
    if not fts:
        return out

    def marcar(rows, corr):
        for r in rows:
            h, n = pertinencia(variantes, texto(r))
            r["pertinencia"], r["correspondencia"] = round(h / n, 2), corr
            r["_corte"] = passa_corte(h, n)
            # IDF só ordena (termo raro pesa mais); corte e pertinência exibida seguem a contagem de termos.
            if peso:
                hp, np_ = pertinencia(variantes, texto(r), peso)
                r["_peso"] = hp / np_
        return rows
    rows = marcar(buscar(fts, total), "todos_os_termos")
    out["linhas"], out["and"] = rows, len(rows)
    if len(rows) < (total if minimo is None else minimo):
        vistos = {chave(r) for r in rows}
        # shortcut: o OR olha os 200 melhores por bm25; mais recall exige consulta mais específica.
        ou = marcar(buscar(consulta_fts(q, expanded=True, colunas=colunas)[0], 200), "parcial")
        extra = [r for r in ou if chave(r) not in vistos and r["_corte"]]
        extra.sort(key=lambda r: (-r["pertinencia"], -r.get("_peso", 0)))
        out["linhas"] = rows + extra[: total - len(rows)]
    return out
