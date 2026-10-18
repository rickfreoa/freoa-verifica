"""Montagem literal e determinística de consultas locais FTS5."""
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
