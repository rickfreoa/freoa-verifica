"""Estrutura inferida de PDF normativo (CVM): linhas do pypdf -> parágrafos -> html_devices.

O PDF não marca dispositivos; a estrutura é inferida pelos mesmos rótulos que o
parser HTML reconhece (Art., §, Parágrafo único, incisos, alíneas). Cabeçalhos e
rodapés repetidos em metade ou mais das páginas são descartados antes da junção.
"""
from __future__ import annotations

import html
import re
from collections import Counter

from freoa_verifica.parsers.html_devices import _classify_line

_NUM_PAGINA = re.compile(r"^\s*(p[aá]gina\s+)?\d{1,4}(\s*(de|/)\s*\d{1,4})?\s*$", re.I)
_TITULO = re.compile(r"^(CAP[IÍ]TULO|T[IÍ]TULO|LIVRO|SE[CÇ][AÃ]O|SUBSE[CÇ][AÃ]O|ANEXO)\b", re.I)


def _repetidas(paginas: list[list[str]]) -> set[str]:
    if len(paginas) < 3:
        return set()
    cont = Counter(l for p in paginas for l in {x for x in p[:3] + p[-3:] if x})
    return {l for l, n in cont.items() if n >= max(3, len(paginas) // 2)}


def paragrafos(textos_pagina: list[str]) -> list[str]:
    paginas = [[re.sub(r"\s+", " ", l).strip() for l in t.splitlines()] for t in textos_pagina]
    lixo = _repetidas(paginas)
    out: list[str] = []
    for linhas in paginas:
        for l in linhas:
            if not l or l in lixo or _NUM_PAGINA.match(l):
                continue
            novo = not out or _classify_line(l) is not None or _TITULO.match(l)
            if novo:
                out.append(l)
            elif out[-1].endswith("-") and l[:1].islower():
                out[-1] += l  # PDFs da CVM vêm do Word, sem hifenização: o hífen é do termo
            else:
                out[-1] += " " + l
    return out


def como_html(textos_pagina: list[str]) -> str:
    corpo = "".join(f"<p>{html.escape(p)}</p>\n" for p in paragrafos(textos_pagina))
    return f"<html><body>\n{corpo}</body></html>"
