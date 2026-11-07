"""Remissões expressas de um dispositivo (IL.3-a, A2; matriz IL.1, seção 1, capacidade e).

Determinístico, sem rede e sem modelo. Reconhece, no texto do dispositivo, a remissão com obra explícita ("art. 14 da
Lei Complementar nº 101, de 2000"), com obra na própria obra ("arts. 151, 205 e 206 desta Lei") e sem qualificação de
obra no mesmo trecho ("artigos 166 e 170, § 2º"), no caminho mais profundo que o texto der. Devolve um alvo por
dispositivo citado; `resolvida` só vale quando a obra é identificada sem ambiguidade e o caminho existe no documento
capturado da obra alvo (decisão do chamador, por `existe`). Na dúvida, `resolvida: false` com o texto preservado.

Não são remissões: anotação e nota editorial (Redação dada, Incluído, Vide, NR, "[Nota editorial: ...]"), remissão
anafórica ou genérica ("do artigo anterior", "na forma da lei", "da mesma Lei", "dessa Lei": ficam em
`referencias_nao_resolvidas`), referência a inciso ou alínea sem artigo (o caminho dependeria do contexto) e rubrica do
próprio dispositivo ("Art. 14." no início).

Resolução por classe, não por exemplo: a expressão só é resolvida depois de consumida e validada por inteiro. Qualificador
não reconhecido depois ou antes do artigo (inciso abreviado ou fora de caixa, faixa de incisos, alínea, item), âmbito de
anexo, obra externa no contexto da frase ("Conforme a lei 10.406/2002, art. 5"), `dessa/desse`, nota editorial e texto
cortado no limite do que foi devolvido => `resolvida: false` (na dúvida, abstenção).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from itertools import product
from typing import Any, Callable

from freoa_verifica.aliases import WorkKey
from freoa_verifica.citation import extract
from freoa_verifica.parsers.paths import int_to_roman, roman_to_int

_ORD = r"(?:\s*[ºo°ª](?![A-Za-zÀ-ú]))?"
_ROMANO = r"[IVXLCDM]+(?:-[A-Z])?"
_MAX_FAIXA = 50

_ART_KW = re.compile(r"(?<![A-Za-zÀ-ú])(?P<kw>arts?\.?|artigos?)\s*(?=\d)")
_ART_ITEM = re.compile(
    rf"(?P<n>\d{{1,3}}(?:\.\d{{3}})+|\d+){_ORD}(?:\s*-\s*(?P<s>[A-Z])(?![A-Za-zÀ-ú]))?")
_UNIDADE = re.compile(r"\s*(?:\((?:[a-zçãé ]+)\)|dias?\b|meses\b|m[êe]s\b|anos?\b|horas?\b|%|por\s+cento|vezes\b|"
                      r"sal[áa]rios\b|reais\b)", re.I)
_LISTA = re.compile(r"\s*,\s*|\s+e\s+|\s+ou\s+")
_FAIXA = re.compile(r"\s+(?:a|at[ée])\s+")
_ABERTA = re.compile(r"\s*,?\s*(?:e\s+seguintes|e\s+ss\b\.?|ss\b\.?)", re.I)

_PAR = re.compile(
    rf"(?:§§?|par[áa]grafos?)\s*(?:(?P<u>[uú]nico)|(?P<n>\d+){_ORD}(?:-(?P<s>[A-Z]))?"
    rf"(?P<mais>(?:\s*(?:,|\be)\s*\d+{_ORD}(?:-[A-Z])?)*))", re.I)
_INC = re.compile(rf"incisos?\s+(?P<r>{_ROMANO})(?P<mais>(?:\s*(?:,|\be)\s*{_ROMANO}\b)*)")
_ALI = re.compile(r"al[ií]neas?\s+[\"“]?(?P<a>[a-z])[\"”]?(?P<mais>(?:\s*(?:,|\be)\s*[\"“]?[a-z][\"”]?(?![\wÀ-ú]))*)")
_CAPUT = re.compile(r"caput\b", re.I)
_FAIXA_SUB = re.compile(r"\s+(?:a|at[ée])\s+(?:\d|[IVXLCDM]+\b)")
_SEP_SUB = re.compile(r"\s*,\s*(?:e\s+)?|\s+e\s+")
_SEP_VIRGULA = re.compile(r"\s*,\s*")

_PREP = r"(?:no|nos|na|nas|do|dos|da|das|ao|aos|pelo|pelos|neste|nesse|nestes|nesses)"
_PAR_SOLTO = re.compile(rf"(?<![A-Za-zÀ-ú])(?:{_PREP})\s+(?=(?:§|par[áa]grafo|caput\b))", re.I)

_PREFIXO = re.compile(
    rf"(?<![A-Za-zÀ-ú])(?:(?:o|a|os|as|no|na|nos|nas)\s+)?(?:(?:§§?|par[áa]grafos?)\s*(?:[uú]nico|\d+{_ORD}(?:-[A-Z])?"
    rf"(?:\s*(?:,|\be)\s*\d+{_ORD}(?:-[A-Z])?)*)|incisos?\s+{_ROMANO}(?:\s*(?:,|\be)\s*{_ROMANO}\b)*|"
    rf"al[ií]neas?\s+[\"“]?[a-z][\"”]?|caput)\s+d[oa]s?\s+$", re.I)

_PROPRIA = re.compile(
    r"\s*,?\s*(?:d[aeo]s?\s+)?(?:(?:presente)|(?:desta|deste|nesta|neste))\s+"
    r"(?P<nome>Lei\s+Complementar|Lei|C[óo]digo|Decreto-Lei|Decreto|Medida\s+Provis[óo]ria|Constitui[çc][ãa]o|"
    r"Emenda\s+Constitucional|Resolu[çc][ãa]o|Regulamento|Estatuto|Consolida[çc][ãa]o)\b", re.I)
_DESTE_ARTIGO = re.compile(r"\s*,?\s*(?:d[eo]ste|neste)\s+artigo\b", re.I)
_DEMONSTRATIVO = re.compile(r"\s*,?\s*(?:d|n)ess[ae]s?\s+[A-Za-zÀ-ú]", re.I)  # "dessa Lei", "desse artigo": anafórico
_ANEXO_DEPOIS = re.compile(r"\s*,?\s*(?:d|n)[oa]s?\s+anexos?(?![A-Za-zÀ-ú])(?:\s+(?:[IVXLCDM]+(?![A-Za-zÀ-ú])|\d+|[úu]nico))?",
                           re.I)
# qualificador estrutural que a leitura do grupo não consumiu (inciso abreviado ou com outra caixa, faixa, alínea, item)
_RESIDUO = re.compile(
    r"\s*,?\s*(?:(?:[Ii]ncisos?|inc\.|[Aa]l[ií]neas?|al\.|[Ll]etras?|[Ii]t(?:em|ens)|[Pp]ar[áa]grafos?|par\.|§§?|[Cc]aput)"
    r"(?![A-Za-zÀ-ú])|[IVXLCDM]+(?![A-Za-zÀ-ú0-9])|[a-z]\)|\d+\))")
_PREFIXO_RESIDUAL = re.compile(
    r"(?:(?<![A-Za-zÀ-ú])(?:[Ii]ncisos?|inc\.|[Aa]l[ií]neas?|al\.|[Ll]etras?|[Ii]t(?:em|ens)|[Cc]aput|[Pp]ar[áa]grafos?|par\.)"
    r"(?![A-Za-zÀ-ú])[^;:.]{0,25}|§§?\s*\S{1,12}|(?<![A-Za-zÀ-ú])[IVXLCDM]{1,6}(?![A-Za-zÀ-ú0-9]))"
    r"\s*,?\s*(?:d[oa]s?|n[oa]s?)\s+$")
_OBRA_NUMERADA = re.compile(
    r"(?<![A-Za-zÀ-ú])(?:lei(?:\s+complementar)?|decreto(?:-lei)?|medida\s+provis[óo]ria|emenda\s+constitucional|"
    r"resolu[çc][ãa]o|instru[çc][ãa]o\s+normativa|portaria)\s+(?:n[ºo°.]{0,2}\s*)?\d", re.I)
_ANEXO = re.compile(r"(?<![A-Za-zÀ-ú])anexos?(?![A-Za-zÀ-ú])", re.I)
_NOTA_COLCHETES = re.compile(r"\[[^\[\]]*\]")
_ANAFORICA = re.compile(r"\s*,?\s*(?:d|n)[oa]s?\s+(?:mesm[oa]|referid[oa]|citad[oa]|supracitad[oa]|aludid[oa]|dit[oa]|"
                        r"anterior)\b", re.I)
_OUTRA_OBRA = re.compile(r"\s*,?\s*d[aeo]s?\s+(?:Lei|Decreto|Medida|C[óo]digo|Constitui|Resolu|Instru|Portaria|"
                         r"Regulamento|Estatuto|Emenda|Conven|Tratado|Consolida|Ato|Norma)", re.I)
_REFERENCIA_OBRA = re.compile(r"(?<![A-Za-zÀ-ú])(?:Lei|Decreto|Medida\s+Provis|C[óo]digo|Constitui[çc]|Resolu[çc]|"
                              r"Instru[çc]|Portaria|Regulamento|Estatuto|Emenda\s+Constitucional|Consolida[çc])")  # com inicial maiuscula: "constituicao" e "lei" em prosa nao qualificam obra
_LIGACAO = re.compile(r"\s*(?:,|\be\b|\bou\b)\s*(?:(?:o|a|os|as)\s+)?")
_FRONTEIRA = re.compile(r";|:|(?<=[a-zà-ú0-9\)])\.\s+(?=[A-ZÀ-Ú§])|\s[IVXLCDM]+\s*[-–—]\s")

_ANOTACAO = re.compile(
    r"\(\s*(?:Reda[çc][ãa]o\s+dada|Inclu[ií]d[oa]s?|Acrescid[oa]s?|Acrescentad[oa]s?|Revogad[oa]s?|Vide|"
    r"Vig[êe]ncia|Produ[çc][ãa]o\s+de\s+efeitos?|Renumerad[oa]s?|Vetad[oa]s?)\b[^()]*(?:\([^()]*\)[^()]*)*\)"
    r"|\(\s*\"?(?:Caput|Artigo|Par[aá]grafo(?:\s+[uú]nico)?|§\s*\d+\S*|Inciso(?:s)?(?:\s+[IVXLCDM]+)?|"
    r"Al[ií]nea(?:s)?(?:\s+\w)?|Item|Express[ãa]o|Palavra|Texto|Anexo|Tabela)\"?\b[^()]*?"
    r"\b(?:acrescid|inclu[ií]d|acrescentad|revogad|reda[çc][ãa]o\s+dada|renumerad|vetad|alterad|suprimid|substitu[ií]d)"
    r"\w*\b[^()]*(?:\([^()]*\)[^()]*)*\)"
    r"|\(\s*(?:Nota|N\.\s?E\.|Obs\.?|Observa[çc][ãa]o|Coment[áa]rio)(?![A-Za-zÀ-ú])[^()]*(?:\([^()]*\)[^()]*)*\)"
    r"|\(\s*NR\s*\)", re.I)

# Natureza da expressão "desta X" por espécie da obra própria: X tem de ser a espécie da obra (ou código/estatuto da lei).
_PROPRIA_POR_ESPECIE = {
    "lei": {"lei", "codigo", "estatuto", "consolidacao"},
    "lei_complementar": {"lei complementar", "lei"},
    "decreto": {"decreto", "regulamento"},
    "decreto_lei": {"decreto-lei", "decreto"},
    "medida_provisoria": {"medida provisoria"},
    "constituicao": {"constituicao"},
    "emenda_constitucional": {"emenda constitucional"},
}
_NIVEL = {"caput": 0, "par": 1, "inc": 2, "ali": 3}


def _dobra(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


def _mascarar_anotacoes(texto: str, notas: tuple[str, ...] = ()) -> str:
    """Notas editoriais saem da leitura (viram espaços; as posições do texto se mantêm): as anotações que a estrutura do
    documento já identificou (`notas`), os padrões textuais e todo trecho entre colchetes (nota do editor)."""
    for nota in notas:
        if isinstance(nota, str) and nota.strip():
            texto = texto.replace(nota, " " * len(nota))
    texto = _ANOTACAO.sub(lambda m: " " * len(m.group(0)), texto)
    return _NOTA_COLCHETES.sub(lambda m: " " * len(m.group(0)), texto)


def _contexto_externo(frase: str) -> bool:
    """A frase (antes da remissão) já fala de outra obra ou de anexo: a remissão sem obra não herda a própria."""
    return bool(_REFERENCIA_OBRA.search(frase) or _OBRA_NUMERADA.search(frase) or _ANEXO.search(frase))


def _milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _rotulo_art(n: int, suf: str | None) -> str:
    base = f"{n}º" if n < 10 else _milhar(n)
    return f"art. {base}" + (f"-{suf}" if suf else "")


def rotulo_obra(w: WorkKey) -> str | None:
    """Rótulo canônico da obra (o mesmo de `alvos` da matriz IL.1): 'Lei 6.404/1976', 'Constituição Federal'."""
    if w.kind == "constituicao":
        return "Constituição Federal"
    nomes = {"lei": "Lei", "lei_complementar": "Lei Complementar", "decreto": "Decreto", "decreto_lei": "Decreto-Lei",
             "medida_provisoria": "Medida Provisória", "emenda_constitucional": "Emenda Constitucional"}
    nome = nomes.get(w.kind)
    if nome is None or not w.year:
        return None
    m = re.fullmatch(r"(\d+)(-\d+)?", w.number)
    if not m:
        return None
    return f"{nome} {_milhar(int(m.group(1)))}{m.group(2) or ''}/{w.year}"


@dataclass
class _Grupo:
    ini: int
    fim: int
    artigos: list[tuple[int, str | None]]
    subs: list[tuple[str, list[Any]]] = field(default_factory=list)
    duvida: bool = False
    obra: WorkKey | None = None
    proprio: bool = False
    explicita: bool = False
    anafora: bool = False
    nome_propria: str = ""


def _artigos(t: str, p: int, plural: bool) -> tuple[list[tuple[int, str | None]], int, bool, bool] | None:
    """Lista, faixa ou artigo único a partir de `p`; (itens, fim, dúvida, houve faixa)."""
    m = _ART_ITEM.match(t, p)
    if not m or _UNIDADE.match(t, m.end()):
        return None
    itens = [(int(m["n"].replace(".", "")), m["s"])]
    fim, duvida, faixa = m.end(), False, False
    while plural:
        f = _FAIXA.match(t, fim)
        if f and (m2 := _ART_ITEM.match(t, f.end())):
            (a, sa), (b, sb) = itens[-1], (int(m2["n"].replace(".", "")), m2["s"])
            if sa or sb or not (0 < b - a <= _MAX_FAIXA):
                duvida = True  # faixa com sufixo, invertida ou grande demais: não se expande
                itens.append((b, sb))
            else:
                itens.extend((k, None) for k in range(a + 1, b + 1))
            fim, faixa = m2.end(), True
            continue
        s = _LISTA.match(t, fim)
        if s and (m2 := _ART_ITEM.match(t, s.end())) and not _UNIDADE.match(t, m2.end()):
            itens.append((int(m2["n"].replace(".", "")), m2["s"]))
            fim = m2.end()
            continue
        break
    if t[fim:fim + 1] == "/" and t[fim + 1:fim + 2].isdigit():
        duvida = True  # "arts. 4º/5º": lista por barra, não resolvida
    return itens, fim, duvida, faixa


def _valores_par(m: re.Match) -> list[str]:
    if m["u"]:
        return ["parunico"]
    primeiro = f"par{int(m['n'])}" + (f"-{m['s'].upper()}" if m["s"] else "")
    outros = re.findall(rf"(\d+){_ORD}(?:-([A-Z]))?", m["mais"] or "")
    return [primeiro] + [f"par{int(n)}" + (f"-{s}" if s else "") for n, s in outros]


def _valores_inc(m: re.Match) -> list[str]:
    def um(r: str) -> str:
        base, _, suf = r.partition("-")
        return f"inc{roman_to_int(base)}" + (f"-{suf}" if suf else "")
    return [um(m["r"])] + [um(r) for r in re.findall(rf"({_ROMANO})\b", m["mais"] or "")]


def _valores_ali(m: re.Match) -> list[str]:
    return [f"ali-{m['a']}"] + [f"ali-{a}" for a in re.findall(r"[\"“]?([a-z])[\"”]?(?![\wÀ-ú])", m["mais"] or "")]


def _elemento(t: str, p: int) -> tuple[str, list[str], int] | None:
    for nome, rx, fn in (("par", _PAR, _valores_par), ("inc", _INC, _valores_inc), ("ali", _ALI, _valores_ali)):
        m = rx.match(t, p)
        if m:
            return nome, fn(m), m.end()
    m = _CAPUT.match(t, p)
    return ("caput", ["caput"], m.end()) if m else None


def _subs_depois(t: str, p: int) -> tuple[list[tuple[str, list[str]]], int, bool]:
    """Subdispositivos depois do artigo (', § 2º, inciso III'); níveis estritamente crescentes, senão dúvida."""
    subs: list[tuple[str, list[str]]] = []
    duvida = False
    fim = p
    while True:
        # o primeiro subdispositivo vem depois de vírgula ("art. 7º e incisos I..." não o qualifica)
        s = (_SEP_SUB if subs else _SEP_VIRGULA).match(t, fim)
        if not s:
            break
        e = _elemento(t, s.end())
        if not e:
            break
        nome, vals, fim_e = e
        if subs and _NIVEL[nome] <= _NIVEL[subs[-1][0]]:
            duvida = True
        subs.append((nome, vals))
        fim = fim_e
        if _FAIXA_SUB.match(t, fim):
            duvida = True
    if len(subs) > 1 and any(n == "caput" for n, _ in subs):
        duvida = True  # "caput e inciso X": o inciso não é o do caput sem mais
    return subs, fim, duvida


def _subs_antes(t: str, ini: int) -> tuple[list[tuple[str, list[str]]], int]:
    """Qualificadores antes do artigo ('o inciso I do § 1º do art. 5º'); o mais próximo do artigo vem primeiro."""
    subs: list[tuple[str, list[str]]] = []
    corte = ini
    while True:
        m = _PREFIXO.search(t[:corte])
        if not m:
            break
        # o casamento pode trazer artigo/preposição antes do elemento
        base = re.sub(r"^(?:o|a|os|as|no|na|nos|nas)\s+", "", m.group(0), flags=re.I)
        e = _elemento(base, 0)
        if not e:
            break
        subs.append((e[0], e[1]))
        corte = m.start()
    return subs, corte


def _obra_explicita(t: str, p: int) -> tuple[WorkKey | None, int, bool] | None:
    """Obra explícita depois do grupo: (obra|None, fim, identificada); None se não há qualificação de obra."""
    m = _OUTRA_OBRA.match(t, p)
    if not m:
        return None
    ini = re.compile(r"\s*,?\s*").match(t, p).end()
    resto = t[ini:ini + 200]
    sintetico = "art. 1 " + resto
    for c in extract(sintetico):
        if c.span[0] == 0 and c.work is not None and c.raw.startswith("art. 1 d"):
            return c.work, ini + len(c.raw) - len("art. 1 "), True
    return None, m.end(), False


def _grupos(t: str, art_proprio: str | None) -> list[_Grupo]:
    grupos: list[_Grupo] = []
    for km in _ART_KW.finditer(t):
        if grupos and km.start() < grupos[-1].fim:
            continue
        plural = km["kw"].lower().startswith(("arts", "artigos"))
        lido = _artigos(t, km.end(), plural)
        if lido is None:
            continue
        itens, fim, duvida, faixa = lido
        g = _Grupo(ini=km.start(), fim=fim, artigos=itens, duvida=duvida)
        if not duvida:
            # em lista, o subdispositivo qualifica o último artigo ("arts. 166 e 170, § 2º"); depois de faixa, é dúvida
            subs, fim2, d2 = _subs_depois(t, fim)
            g.subs, g.fim, g.duvida = subs, fim2, g.duvida or d2 or (faixa and bool(subs))
        antes, ini = _subs_antes(t, km.start())
        if antes:
            g.ini = ini
            if g.subs or len(itens) != 1 or faixa:
                g.duvida = True
            else:
                g.subs = antes
        if _PREFIXO_RESIDUAL.search(t[max(0, g.ini - 60):g.ini]):
            g.duvida = True  # qualificador antes do artigo que a leitura não reconheceu ("inc. I do art. 5")
        if _RESIDUO.match(t, g.fim):
            g.duvida = True  # qualificador depois do artigo que a leitura não consumiu ("art. 5, I", "art. 5, inc. I")
        if (am := _ANEXO_DEPOIS.match(t, g.fim)):
            g.duvida, g.fim = True, am.end()  # âmbito de anexo: o caminho não é o do corpo da obra
        if _ABERTA.match(t, g.fim):
            g.duvida = True
            g.fim = _ABERTA.match(t, g.fim).end()
        if _ANAFORICA.match(t, g.fim) or _DEMONSTRATIVO.match(t, g.fim):
            g.anafora = True
        elif (pm := _PROPRIA.match(t, g.fim)):
            g.proprio, g.fim = True, pm.end()
            g.nome_propria = pm["nome"]
        elif (ex := _obra_explicita(t, g.fim)) is not None:
            g.obra, g.fim, ident = ex
            g.explicita = True
            if not ident:
                g.duvida = True
        grupos.append(g)
    return grupos


def _inicio_da_frase(t: str, pos: int) -> int:
    ult = 0
    for m in _FRONTEIRA.finditer(t, 0, pos):
        ult = m.end()
    return ult


def _caminhos(g: _Grupo) -> list[tuple[str, str]]:
    """(caminho canônico, rótulo) de cada dispositivo do grupo."""
    niveis = [vals for _, vals in g.subs]
    if g.subs and any(len(v) > 1 for v in niveis[:-1]):
        g = _Grupo(g.ini, g.fim, g.artigos, [], True)  # produto ambíguo: só o artigo, não resolvido
        niveis = []
    out: list[tuple[str, str]] = []
    for k, (n, suf) in enumerate(g.artigos):
        art = f"art{n}" + (f"-{suf}" if suf else "")
        rot = _rotulo_art(n, suf)
        ultimo = k == len(g.artigos) - 1
        for combo in (product(*niveis) if niveis and ultimo else [()]):
            path = ".".join((art, *combo))
            partes = [rot]
            for c in combo:
                if c == "caput":
                    partes.append("caput")
                elif c == "parunico":
                    partes.append("parágrafo único")
                elif c.startswith("par"):
                    base, _, suf2 = c[3:].partition("-")
                    partes.append(f"§ {int(base)}º" + (f"-{suf2}" if suf2 else "") if int(base) < 10 and not suf2
                                  else f"§ {int(base)}" + (f"-{suf2}" if suf2 else ""))
                elif c.startswith("inc"):
                    base, _, suf2 = c[3:].partition("-")
                    partes.append(f"inciso {int_to_roman(int(base))}" + (f"-{suf2}" if suf2 else ""))
                elif c.startswith("ali-"):
                    partes.append(f"alínea {c[4:]}")
            out.append((path, ", ".join(partes)))
    return out


def _mesma_obra(a: WorkKey | None, b: WorkKey | None) -> bool:
    return (a is not None and b is not None and a.kind == b.kind and a.number == b.number and a.year == b.year)


def extrair(texto: str, obra_propria: WorkKey | None, art_proprio: str | None = None,
            *, implicita: bool = True, notas: tuple[str, ...] = (), truncado: bool = False) -> list[dict[str, Any]]:
    """Remissões do texto, em ordem de aparição, antes da decisão de existência.

    Cada item: texto, obra (WorkKey|None), obra_rotulo, caminho (rótulo), path (canônico) e `duvida` (True quando a
    leitura não basta para resolver). `art_proprio` (ex.: 'art14') habilita "no caput", "§ 1º deste artigo" e
    "no § 2º" como referência ao artigo do próprio dispositivo; `implicita` autoriza a remissão sem qualificação de
    obra a valer como a própria obra (desligada em dispositivo de anexo). `notas` são as anotações editoriais que a
    estrutura do documento já identificou; `truncado` marca texto cortado no limite: remissão que toca o corte não
    resolve (o que veio depois dele não foi devolvido)."""
    if not texto or not isinstance(texto, str):
        return []
    t = _mascarar_anotacoes(texto, tuple(notas))
    itens: list[dict[str, Any]] = []
    inicio_rubrica = re.match(r"\s*\"?Art\.?\s*\d", t)
    grupos = [g for g in _grupos(t, art_proprio) if not (inicio_rubrica and g.ini == 0)]

    def vizinho_explicito(i: int) -> bool:
        if i + 1 >= len(grupos) or not grupos[i + 1].explicita:
            return False
        return _LIGACAO.fullmatch(t[grupos[i].fim:grupos[i + 1].ini]) is not None

    for i, g in enumerate(grupos):
        if g.anafora:
            continue
        obra, duvida = None, g.duvida or (bool(g.subs) and any(len(v) > 1 for _, v in g.subs[:-1]))
        if g.proprio:
            especies = _PROPRIA_POR_ESPECIE.get(obra_propria.kind if obra_propria else "", set())
            if obra_propria is not None and _dobra(re.sub(r"\s+", " ", g.nome_propria)) in especies:
                obra = obra_propria
            else:
                duvida = True
        elif g.explicita:
            obra = g.obra
            if obra is not None and not obra.year:
                duvida = True
        else:
            fr = t[_inicio_da_frase(t, g.ini):g.ini]
            if (not implicita or obra_propria is None or _contexto_externo(fr) or vizinho_explicito(i)):
                duvida = True
            else:
                obra = obra_propria
        for path, rotulo in _caminhos(g):
            itens.append({"texto": texto[g.ini:g.fim].strip(), "obra": obra,
                          "obra_rotulo": rotulo_obra(obra) if obra is not None else None,
                          "caminho": rotulo, "path": path, "duvida": duvida or obra is None, "fim": g.fim})
    if art_proprio:
        itens.extend(_do_proprio_artigo(texto, t, art_proprio, obra_propria, [(g.ini, g.fim) for g in grupos]))
    if truncado:  # remissão que toca o corte, ou a que o corte deixa sem o que viria depois ("§ 2o do" + "art. 15")
        corte = len(texto.rstrip())
        for it in itens:
            resto = texto[it["fim"]:corte]
            if it["fim"] >= corte or (len(resto.strip()) <= 12 and not re.search(r"[.;:]", resto)):
                it["duvida"] = True
    return itens


def _do_proprio_artigo(texto: str, t: str, art_proprio: str, obra: WorkKey | None,
                       ocupados: list[tuple[int, int]]) -> list[dict[str, Any]]:
    """'no caput', 'no § 2º', 'do parágrafo único', '§ 1º deste artigo': o artigo do próprio dispositivo."""
    if obra is None or not re.fullmatch(r"art\d+(?:-[A-Z])?", art_proprio):
        return []
    n = int(re.match(r"art(\d+)", art_proprio).group(1))
    suf = art_proprio.partition("-")[2] or None
    out = []
    inicios = {m.end() for m in _PAR_SOLTO.finditer(t)}
    inicios |= {m.start() for m in re.finditer(r"§|[Pp]ar[áa]grafo\s+[uú]nico", t)
                if _elemento(t, m.start()) and _DESTE_ARTIGO.match(t, _elemento(t, m.start())[2])}
    for ini in sorted(inicios):
        if any(a <= ini < b for a, b in ocupados):
            continue
        e = _elemento(t, ini)
        if not e or e[0] not in ("par", "caput") or len(e[1]) != 1:
            continue
        nome, vals, fim = e
        resto = t[fim:]
        if re.match(r"\s*d[oa]s?\s+(?:art|artigos?)\b", resto, re.I) or _FAIXA_SUB.match(t, fim):
            continue  # a qualificação por artigo pertence ao grupo do artigo (ou é faixa não resolvida)
        if _DEMONSTRATIVO.match(t, fim):
            continue  # "§ 1º desse artigo": anafórico, nunca o artigo do próprio dispositivo
        explicito = False
        if (m := _DESTE_ARTIGO.match(t, fim)):
            fim, explicito = m.end(), True
        elif nome == "caput" and re.match(r"\s*d[oa]\s+(?:mesm|referid)", resto, re.I):
            continue
        externo = bool(_OUTRA_OBRA.match(t, fim) or _ANEXO_DEPOIS.match(t, fim))  # "do parágrafo único da Lei X"
        externo = externo or (not explicito and _contexto_externo(t[_inicio_da_frase(t, ini):ini]))  # "Na Lei X, ... caput"
        duvida = externo or bool(_RESIDUO.match(t, fim))  # "§ 2º, I": o inciso não foi consumido
        for p in _caminhos(_Grupo(ini, fim, [(n, suf)], [(nome, vals)])):
            out.append({"texto": texto[ini:fim].strip(), "obra": None if externo else obra,
                        "obra_rotulo": None if externo else rotulo_obra(obra),
                        "caminho": p[1], "path": p[0], "duvida": duvida, "fim": fim})
    return out


def remissoes(texto: str, obra_propria: WorkKey | None, existe: Callable[[WorkKey, str], bool],
              art_proprio: str | None = None, *, implicita: bool = True, notas: tuple[str, ...] = (),
              truncado: bool = False) -> list[dict[str, Any]]:
    """`remissoes[]` do contrato: {texto, alvo: {obra, caminho}, resolvida}. `existe(obra, path)` consulta só o que já
    está capturado (sem rede) e nunca levanta; falha dela é inexistência."""
    saida: list[dict[str, Any]] = []
    vistos: set[tuple] = set()
    for it in extrair(texto, obra_propria, art_proprio, implicita=implicita, notas=notas, truncado=truncado):
        resolvida = False
        if not it["duvida"] and it["obra"] is not None and it["obra_rotulo"] is not None:
            try:
                resolvida = bool(existe(it["obra"], it["path"]))
            except (LookupError, ValueError, TypeError, AttributeError):  # fechado: não afirma o que não pôde conferir
                resolvida = False
        chave = (it["obra_rotulo"], it["caminho"], resolvida)
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append({"texto": it["texto"], "alvo": {"obra": it["obra_rotulo"], "caminho": it["caminho"]},
                      "resolvida": resolvida})
    return saida
