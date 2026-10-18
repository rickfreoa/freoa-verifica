"""Estrutura inferida de PDF normativo (CVM): linhas do pypdf -> parágrafos -> html_devices.

O PDF não marca dispositivos; a estrutura é inferida pelos mesmos rótulos que o
parser HTML reconhece (Art., §, Parágrafo único, incisos, alíneas). Só se descarta
o que está na margem da página (oito primeiras e oito últimas linhas): linha
repetida em metade ou mais das páginas, ou o número da própria página. Números e
textos no corpo nunca são descartados.
"""
from __future__ import annotations

import html
import re
from collections import Counter

from freoa_verifica.parsers.html_devices import _classify_line

_MARGEM = 8  # cabeçalho da CVM: órgão, três endereços, sítio, epígrafe e número
_SUMARIO = re.compile(r"^(CAP[IÍ]TULO|T[IÍ]TULO|SE[CÇ][AÃ]O|SUBSE[CÇ][AÃ]O|ANEXO)\b.*\.{5,}\s*\d{0,4}$", re.I)  # linha de sumário: pontilhado e página
_TITULO = re.compile(r"^(CAP[IÍ]TULO|T[IÍ]TULO|LIVRO|SE[CÇ][AÃ]O|SUBSE[CÇ][AÃ]O|ANEXO)\b", re.I)


def _margem(linhas: list[str]) -> set[int]:
    idx = [i for i, l in enumerate(linhas) if l]
    return set(idx[:_MARGEM] + idx[-_MARGEM:])


def _numero_da_pagina(linha: str, n: int, total: int) -> bool:
    m = re.fullmatch(r"(?:p[aá]gina\s+)?(\d{1,4})(?:\s*(?:de|/)\s*(\d{1,4}))?", linha, re.I)
    return bool(m) and int(m.group(1)) == n and (m.group(2) is None or int(m.group(2)) == total)


def paragrafos(textos_pagina: list[str]) -> list[str]:
    paginas = [[re.sub(r"\s+", " ", l).strip() for l in t.splitlines()] for t in textos_pagina]
    margens = [_margem(p) for p in paginas]
    cont = Counter(l for p, m in zip(paginas, margens) for l in {p[i] for i in m})
    # Cabeçalho/rodapé é texto (nome do órgão, endereço); dispositivo e número sozinho nunca são.
    lixo = {l for l, n in cont.items() if len(paginas) >= 3 and n >= max(3, len(paginas) // 2)
            and len(re.findall(r"[^\W\d_]", l)) >= 8 and _classify_line(l) is None}
    out: list[str] = []
    for n, (linhas, margem) in enumerate(zip(paginas, margens), 1):
        for i, l in enumerate(linhas):
            if not l or _SUMARIO.search(l) or (i in margem and (l in lixo or _numero_da_pagina(l, n, len(paginas)))):
                continue
            # "• Inciso VI com redação dada pela..." é nota de alteração: parágrafo próprio, nunca texto do dispositivo.
            if not out or _classify_line(l) is not None or _TITULO.match(l) or l.startswith(("•", "", "▪")):
                out.append(l)
            elif out[-1].endswith("-") and l[:1].islower():
                out[-1] += l  # PDFs da CVM vêm do Word, sem hifenização: o hífen é do termo
            else:
                out[-1] += " " + l
    return out


_NOTA = re.compile(r"^[•▪]\s*(?:.+?\s)?(com\s+reda[cç][aã]o\s+dada|inclu[ií]d[oa]s?|revogad[oa]s?|acrescid[oa]s?|renumerad[oa]s?)\s+(pel[ao]s?\s+.+?)\.?$", re.I)


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
