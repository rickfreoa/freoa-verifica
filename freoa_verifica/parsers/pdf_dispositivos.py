"""Estrutura inferida de PDF normativo (CVM): texto do pypdf -> parágrafos -> html_devices.

O PDF não marca dispositivos; a estrutura é inferida pelos mesmos rótulos que o
parser HTML reconhece (Art., §, Parágrafo único, incisos, alíneas).

Cabeçalho e rodapé saem pela geometria, não pelo texto: só se descarta a linha que
está na faixa superior ou inferior da página E se repete, com o mesmo texto e na
mesma altura, em pelo menos metade das páginas (ou é o número da própria página
nessa faixa). Sem coordenadas, nada é descartado.
"""
from __future__ import annotations

import html
import re
from collections import Counter, defaultdict

from freoa_verifica.parsers.html_devices import _classify_line

_FAIXA_SUP, _FAIXA_INF = 0.75, 0.12  # fração da altura; o cabeçalho da CVM desce até 0,79
_SUMARIO = re.compile(r"^(CAP[IÍ]TULO|T[IÍ]TULO|SE[CÇ][AÃ]O|SUBSE[CÇ][AÃ]O|ANEXO)\b.*\.{5,}\s*\d{0,4}$", re.I)
_TITULO = re.compile(r"^(CAP[IÍ]TULO|T[IÍ]TULO|LIVRO|SE[CÇ][AÃ]O|SUBSE[CÇ][AÃ]O|ANEXO)\b", re.I)
_MARCA_NOTA = ("•", "\uf0b7", "\u25aa")


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()


def textos_de_corpo(pages) -> list[str]:
    """Texto de cada página sem cabeçalho/rodapé, decidido por posição e repetição."""
    frags: list[list[tuple[float, str]]] = []
    alturas: list[float] = []
    for page in pages:
        parts: list[tuple[float, str]] = []

        def vis(text, cm, tm, _font, _size, parts=parts):
            parts.append((float(tm[5]) * float(cm[3]) + float(cm[5]), text))

        page.extract_text(visitor_text=vis)
        frags.append(parts)
        alturas.append(float(page.mediabox.height) or 1.0)
    linhas_por_pagina = []
    for parts, h in zip(frags, alturas):
        linhas: dict[int, str] = defaultdict(str)
        for y, t in parts:
            linhas[round(y)] += t
        linhas_por_pagina.append({y: _norm(t) for y, t in linhas.items()
                                  if _norm(t) and not (_FAIXA_INF * h < y < _FAIXA_SUP * h)})
    cont = Counter((y, t) for ls in linhas_por_pagina for y, t in ls.items())
    minimo = max(3, (len(frags) + 1) // 2)
    out = []
    for n, (parts, ls, h) in enumerate(zip(frags, linhas_por_pagina, alturas), 1):
        def repetida(y, ls=ls, n=n):
            return cont[(y, ls[y])] >= minimo or _numero_da_pagina(ls[y], n, len(frags))
        # Só sai o bloco contíguo a partir da borda: linha repetida com texto mantido acima
        # (ou abaixo, no rodapé) é corpo, não cabeçalho (auditoria 1.1.0, rodada 3).
        linhas_pag = sorted({round(y) for y, t in parts if _norm(t)}, reverse=True)
        fora: set[int] = set()
        for ordem, na_faixa in ((linhas_pag, lambda y: y >= _FAIXA_SUP * h),
                                (linhas_pag[::-1], lambda y: y <= _FAIXA_INF * h)):
            for y in ordem:
                if not na_faixa(y) or y not in ls or not repetida(y):
                    break
                fora.add(y)
        out.append("".join(t for y, t in parts if round(y) not in fora))
    return out


def _numero_da_pagina(linha: str, n: int, total: int) -> bool:
    m = re.fullmatch(r"(?:p[aá]gina\s+)?(\d{1,4})(?:\s*(?:de|/)\s*(\d{1,4}))?", linha, re.I)
    return bool(m) and int(m.group(1)) == n and (m.group(2) is None or int(m.group(2)) == total)


def paragrafos(textos_pagina: list[str]) -> list[str]:
    out: list[str] = []
    for texto in textos_pagina:
        for l in (_norm(x) for x in texto.splitlines()):
            if not l or _SUMARIO.search(l):
                continue
            # "• Inciso VI com redação dada pela..." é nota de alteração: parágrafo próprio, nunca texto do dispositivo.
            if not out or _classify_line(l) is not None or _TITULO.match(l) or l.startswith(_MARCA_NOTA):
                out.append(l)
            elif out[-1].endswith("-") and l[:1].islower():
                out[-1] += l  # PDFs da CVM vêm do Word, sem hifenização: o hífen é do termo
            else:
                out[-1] += " " + l
    return out


_NOTA = re.compile(r"^[•\uf0b7\u25aa]\s*(?:.+?\s)?(com\s+reda[cç][aã]o\s+dada|inclu[ií]d[oa]s?|revogad[oa]s?|acrescid[oa]s?|renumerad[oa]s?)\s+(pel[ao]s?\s+.+?)\.?$", re.I)


def _notas_como_anotacoes(ps: list[str]) -> list[str]:
    """Nota da CVM ("• Inciso VI com redação dada pela Resolução CVM nº 187, de ...") vira a anotação
    entre parênteses que o parser já reconhece no Planalto, presa ao dispositivo que a antecede."""
    out: list[str] = []
    for p in ps:
        m = _NOTA.match(p)
        if m and out:
            verbo = m.group(1).lower()
            verbo = "Redação dada" if verbo.startswith("com") else verbo.capitalize()
            out[-1] += f" ({verbo} {m.group(2)})"
        else:
            out.append(p)
    return out


def como_html(textos_pagina: list[str]) -> str:
    # Texto que outro ato passa a ter ("...com a seguinte redação:" até "(N.R.)") é citação, não dispositivo desta norma.
    # Só vale o trecho que fecha com (N.R.) em até 60 parágrafos; sem fecho, nada é tratado como citação.
    ps = _notas_como_anotacoes(paragrafos(textos_pagina))
    citado: set[int] = set()
    for i, p in enumerate(ps):
        if re.search(r"reda[cç][aã]o:\s*$", p) and i not in citado:
            fim = next((j for j in range(i + 1, min(len(ps), i + 61)) if re.search(r"\(N\.R\.\)\s*$", ps[j])), None)
            if fim is not None:
                citado.update(range(i + 1, fim + 1))
    corpo = (f"<blockquote><p>{html.escape(p)}</p></blockquote>" if i in citado else f"<p>{html.escape(p)}</p>"
             for i, p in enumerate(ps))
    return "<html><body>\n" + "\n".join(corpo) + "\n</body></html>"
