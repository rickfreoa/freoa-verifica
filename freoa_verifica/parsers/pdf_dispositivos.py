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
MARCA_CORTE = " \u27e6margem\u27e7"  # fim de linha seguido de margem descartada em fronteira limpa


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()


def textos_de_corpo(pages, descartadas: set[str] | None = None) -> list[str]:
    """Texto de cada página sem cabeçalho/rodapé, decidido por posição e repetição."""
    frags: list[list[tuple[float, str]]] = []
    alturas: list[float] = []
    imagens: list[list[tuple[float, float]]] = []  # (base, topo) de cada imagem desenhada na página
    for page in pages:
        parts: list[tuple[float, str]] = []
        imgs: list[tuple[float, float]] = []

        def vis(text, cm, tm, _font, _size, parts=parts):
            parts.append((float(tm[5]) * float(cm[3]) + float(cm[5]), text))

        def op(operador, args, cm, _tm, imgs=imgs, page=page):
            if operador == b"Do" and args and _e_imagem(page, args[0]) or operador in (b"BI", b"INLINE IMAGE"):
                base, alto = float(cm[5]), float(cm[3])
                imgs.append((min(base, base + alto), max(base, base + alto)))

        page.extract_text(visitor_text=vis, visitor_operand_before=op)
        frags.append(parts)
        imagens.append(imgs)
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
    fora_por_pagina = []
    for n, (parts, ls, h) in enumerate(zip(frags, linhas_por_pagina, alturas), 1):
        def repetida(y, ls=ls, n=n):
            t = ls[y]
            return _numero_da_pagina(t, n, len(frags)) or (cont[(y, t)] >= minimo and _forma_de_margem(t))
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
        fora_por_pagina.append(fora)
    marcar = _manter_cortes_ambiguos(frags, fora_por_pagina)
    # Imagem no corpo pode conter texto normativo que o pypdf não extrai (auditoria 1.1.0, rodada 9):
    # as linhas mantidas imediatamente acima e abaixo dela ficam marcadas.
    for p, (parts, fora, imgs, h) in enumerate(zip(frags, fora_por_pagina, imagens, alturas)):
        ys = sorted({round(y) for y, t in parts if _norm(t) and round(y) not in fora})
        for base, topo in imgs:
            acima = [y for y in ys if y >= topo]
            abaixo = [y for y in ys if y <= base]
            lado = [y for y in ys if base - 2 < y < topo + 2]  # linha que divide a altura com a imagem
            if not lado and ((base >= _FAIXA_SUP * h and not acima) or (topo <= _FAIXA_INF * h and not abaixo)):
                continue  # logotipo na margem, sem texto mantido do lado de fora nem na mesma altura
            for y in ([min(acima)] if acima else []) + ([max(abaixo)] if abaixo else []) + lado:
                marcar.add((p, y))
            if not acima and p > 0:  # imagem no alto do corpo: fecho do dispositivo da página anterior
                ant = sorted({round(y) for y, t in frags[p - 1] if _norm(t) and round(y) not in fora_por_pagina[p - 1]})
                if ant:
                    marcar.add((p - 1, ant[0]))
    if descartadas is not None:
        descartadas.update(t for ls, fora in zip(linhas_por_pagina, fora_por_pagina) for y, t in ls.items() if y in fora)
    out = []
    for p, (parts, fora) in enumerate(zip(frags, fora_por_pagina)):
        ultimo = {round(y): i for i, (y, t) in enumerate(parts) if _norm(t)}
        alvo = {ultimo[y] for (pp, y) in marcar if pp == p and y in ultimo}
        out.append("".join(t.rstrip("\n") + MARCA_CORTE + "\n" if i in alvo else t
                           for i, (y, t) in enumerate(parts) if round(y) not in fora))
    return out


_FECHO = re.compile(r"[.;:!?)\]”\"»]$|[;,]\s+(e|ou)$")  # "...; e" fecha inciso


def _forma_de_margem(linha: str) -> bool:
    """Cabeçalho/rodapé tem forma de rótulo (órgão, endereço, sítio, epígrafe em caixa alta),
    não de texto normativo: nunca dispositivo, nunca frase em caixa mista terminada em ponto."""
    if _abre_paragrafo(linha):
        return False
    letras = [c for c in linha if c.isalpha()]
    caixa_alta = bool(letras) and sum(c.isupper() for c in letras) >= 0.8 * len(letras)
    return caixa_alta or not re.search(r"[.;]$", linha)


def _abre_paragrafo(linha: str) -> bool:
    return _classify_line(linha) is not None or bool(_TITULO.match(linha)) or linha.startswith(_MARCA_NOTA)


def _manter_cortes_ambiguos(frags, fora_por_pagina) -> set[tuple[int, int]]:
    """Corte que separa um parágrafo aberto (sem pontuação final) de um novo dispositivo
    (ou do fim do documento) não se distingue de texto normativo: o bloco é mantido.
    Cabeçalho legítimo cai entre o fim e a continuação do mesmo parágrafo, ou após fecho."""
    seq: list[tuple[int, int, str]] = []  # (página, y, linha) em ordem de leitura
    for p, parts in enumerate(frags):
        linhas: dict[int, str] = {}
        for y, t in parts:
            linhas[round(y)] = linhas.get(round(y), "") + t
        seq += [(p, y, _norm(t)) for y, t in linhas.items() if _norm(t)]
    def fora(k):
        return seq[k][1] in fora_por_pagina[seq[k][0]]

    marcar: set[tuple[int, int]] = set()
    i = 0
    while i < len(seq):
        if not fora(i):
            i += 1
            continue
        j = i  # bloco de uma só página (rodapé e cabeçalho seguinte são blocos distintos)
        while j < len(seq) and seq[j][0] == seq[i][0] and fora(j):
            j += 1
        antes = next((seq[k][2] for k in range(i - 1, -1, -1) if not fora(k)), None)
        depois = next((seq[k][2] for k in range(j, len(seq)) if not fora(k)), None)
        k_antes = next((k for k in range(i - 1, -1, -1) if not fora(k)), None)
        aberto = antes is not None and not _FECHO.search(antes)
        if aberto and (depois is None or _abre_paragrafo(depois)):
            for p, y, _ in seq[i:j]:
                fora_por_pagina[p].discard(y)
        elif k_antes is not None and not all(_numero_da_pagina(t, p + 1, len(frags)) for p, _, t in seq[i:j]):
            # Todo descarte de texto (não só número da página) pode ter levado parte do dispositivo
            # que o antecede, na fronteira limpa ou no meio do parágrafo: ele fica impedido de
            # conclusão textual (auditoria 1.1.0, rodadas 6 e 8).
            marcar.add((seq[k_antes][0], seq[k_antes][1]))
        i = j
    return marcar


def _e_imagem(page, nome) -> bool:
    try:
        xo = page["/Resources"]["/XObject"]
        obj = xo[nome].get_object()
        return obj.get("/Subtype") == "/Image"
    except (KeyError, TypeError, AttributeError):
        return True  # sem como saber: tratar como imagem é o lado seguro


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
