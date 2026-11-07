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

Resolução por GRAMÁTICA FECHADA (lista de permissão), não por padrões negativos: uma remissão só é `resolvida` quando
toda a expressão, do início da referência até um delimitador terminal reconhecido, é consumida por produções explícitas
(artigo, parágrafo, inciso, alínea, caput, listas e faixas simples, obra própria por `desta Lei`/`deste Código`, obra
externa por espécie, número e ano inequívocos) e nada estrutural sobra depois dela (a leitura da cauda é feita sobre o texto
com caixa e acentos normalizados, sem mudar posições). Qualquer token estrutural não consumido (inciso abreviado, romano
solto, alínea, item, anexo, outra obra), contexto externo antes da referência (a frase só termina em ponto final, nunca em
`:` ou `;`), nota editorial na expressão e texto cortado no limite do que foi devolvido => `resolvida: false` (na dúvida,
abstenção). Notas editoriais são localizadas no texto INTEGRAL (parênteses e colchetes, inclusive aninhados e abertos pelo
corte) e projetadas sobre o texto emitido. Obra explicitamente igual à própria obra é a própria obra.
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
# --- leitura fechada sobre o texto normalizado (caixa e acentos dobrados, mesmas posições): o que não foi consumido por
# uma produção e é token estrutural, ou obra, invalida a expressão inteira
_ROMANO_PURO = r"m{0,3}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3})"
_ESTRUTURAL = re.compile(
    r"(?<![a-z0-9])(?:(?:incisos?|incs?\.?|alineas?|als?\.?|letras?|itens?|item|paragrafos?|par\.|caput|anexos?|tabelas?|"
    r"quadros?|apendices?|leis?|decretos?|codigos?|constituicao|emendas?|medidas?|resolucao|instrucao|portarias?|"
    r"regulamento|estatuto|consolidacao|convencao|tratado)(?![a-z0-9])|§§?|[a-z]\)|\d+\)|"
    rf"(?=[ivxlcdm]){_ROMANO_PURO}(?![a-z0-9]))")
_FUNCAO = re.compile(r"(?:d[oa]s?|n[oa]s?|a[os]?|o|os|as|e|ou|em|de|com|por|pelo|pela|pelos|pelas|para|ate)(?![a-z0-9])\s*,?\s*")
_TERMINAL = re.compile(r"\s*(?:$|[.;)\]\"”])")
_SEPARADOR = re.compile(r"[\s,:\-–—]*")
_PREFIXO_RESIDUAL = re.compile(
    r"(?:(?<![a-z0-9])(?:incisos?|incs?\.?|alineas?|als?\.?|letras?|itens?|item|caput|paragrafos?|par\.)(?![a-z0-9])[^;:.]{0,25}"
    rf"|§§?\s*\S{{1,12}}|(?<![a-z0-9])(?=[ivxlcdm]){_ROMANO_PURO}(?![a-z0-9]))"
    r"\s*,?\s*(?:d[oa]s?|n[oa]s?)\s+$")
_OBRA_NUMERADA = re.compile(
    r"(?<![A-Za-zÀ-ú])(?:lei(?:\s+complementar)?|decreto(?:-lei)?|medida\s+provis[óo]ria|emenda\s+constitucional|"
    r"resolu[çc][ãa]o|instru[çc][ãa]o\s+normativa|portaria)\s+(?:n[ºo°.]{0,2}\s*)?\d", re.I)
_NUMERO_ANO = re.compile(r"\d[\d.]*(?:-\d+)?\s*(?:/\s*\d{2,4}\b|,\s*de\s+\d)")  # "10.406/2002", "8.987, de 13 de ..."
_SIGLA_OBRA = re.compile(r"(?<![A-Za-zÀ-ú])(?:LC|MP|EC|DL|CF|CRFB|CC|CP|CPC|CPP|CLT|CTN|CDC|ECA|RCVM|CTB|LRF|LINDB)"
                         r"(?![A-Za-zÀ-ú])")
_ANEXO = re.compile(r"(?<![a-z])anexos?(?![a-z])")
_ANAFORICA = re.compile(r"\s*,?\s*(?:d|n)[oa]s?\s+(?:mesm[oa]|referid[oa]|citad[oa]|supracitad[oa]|aludid[oa]|dit[oa]|"
                        r"anterior)\b", re.I)
_OUTRA_OBRA = re.compile(r"\s*,?\s*d[aeo]s?\s+(?:Lei|Decreto|Medida|C[óo]digo|Constitui|Resolu|Instru|Portaria|"
                         r"Regulamento|Estatuto|Emenda|Conven|Tratado|Consolida|Ato|Norma)", re.I)
_REFERENCIA_OBRA = re.compile(r"(?<![A-Za-zÀ-ú])(?:Lei|Decreto|Medida\s+Provis|C[óo]digo|Constitui[çc]|Resolu[çc]|"
                              r"Instru[çc]|Portaria|Regulamento|Estatuto|Emenda\s+Constitucional|Consolida[çc])")  # com inicial maiuscula: "constituicao" e "lei" em prosa nao qualificam obra
_LIGACAO = re.compile(r"\s*(?:,|\be\b|\bou\b)\s*(?:(?:o|a|os|as)\s+)?")
# a frase só termina em ponto final (ou marcador de inciso): `:` e `;` não mudam a obra de que se fala
_FRONTEIRA = re.compile(r"(?<=[a-zà-ú0-9\)])\.\s+(?=[A-ZÀ-Ú§])|\s[IVXLCDM]+\s*[-–—]\s")

# Início de nota editorial entre parênteses: a nota vai até o parêntese que a fecha (aninhamento contado) ou até o fim do
# que se tem, quando o corte abriu a nota e não a fechou.
_ABRE_NOTA = re.compile(
    r"\(\s*(?:(?:Reda[çc][ãa]o\s+dada|Inclu[ií]d[oa]s?|Acrescid[oa]s?|Acrescentad[oa]s?|Revogad[oa]s?|Vide|Vig[êe]ncia|"
    r"Produ[çc][ãa]o\s+de\s+efeitos?|Renumerad[oa]s?|Vetad[oa]s?|Nota|N\.\s?E\.|Obs\.?|Observa[çc][ãa]o|Coment[áa]rio)"
    r"(?![A-Za-zÀ-ú])|NR\s*\))"
    r"|\(\s*\"?(?:Caput|Artigo|Par[aá]grafo(?:\s+[uú]nico)?|§\s*\d+\S*|Inciso(?:s)?(?:\s+[IVXLCDM]+)?|"
    r"Al[ií]nea(?:s)?(?:\s+\w)?|Item|Express[ãa]o|Palavra|Texto|Anexo|Tabela)\"?\b[^()]*?"
    r"\b(?:acrescid|inclu[ií]d|acrescentad|revogad|reda[çc][ãa]o\s+dada|renumerad|vetad|alterad|suprimid|substitu[ií]d)",
    re.I)
_MIN_NOTA_CORTADA = 6

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


def _dobra_pos(s: str) -> str:
    """Caixa e acentos normalizados SEM mudar o comprimento: as posições do texto normalizado valem para o original."""
    out = []
    for c in s:
        if c in "ºª°§":
            out.append(c)
            continue
        base = unicodedata.normalize("NFD", c)[:1] or c
        low = base.lower()
        out.append(low if len(low) == 1 else base)
    return "".join(out)


def _fecha(txt: str, ini: int, abre: str, fecha: str) -> int:
    """Fim da nota que abre em `ini`, contando o aninhamento; nota não fechada vai até o fim do que se tem."""
    prof = 0
    for k in range(ini, len(txt)):
        if txt[k] == abre:
            prof += 1
        elif txt[k] == fecha:
            prof -= 1
            if prof == 0:
                return k + 1
    return len(txt)


def _spans_notas(txt: str, notas: tuple[str, ...]) -> list[tuple[int, int]]:
    """Posições das notas editoriais em `txt`: anotações que a estrutura do documento já identificou, notas entre
    parênteses reconhecidas e todo trecho entre colchetes, inclusive aninhados e abertos sem fechamento."""
    spans: list[tuple[int, int]] = []
    for nota in notas:
        if isinstance(nota, str) and nota.strip():
            spans.extend((m.start(), m.end()) for m in re.finditer(re.escape(nota), txt))
    spans.extend((m.start(), _fecha(txt, m.start(), "(", ")")) for m in _ABRE_NOTA.finditer(txt))
    i = 0
    while i < len(txt):
        if txt[i] == "[":
            fim = _fecha(txt, i, "[", "]")
            spans.append((i, fim))
            i = fim
        else:
            i += 1
    return spans


def _mascarar_anotacoes(texto: str, notas: tuple[str, ...] = (), integral: str | None = None
                        ) -> tuple[str, list[tuple[int, int]]]:
    """Notas editoriais saem da leitura (viram espaços; as posições se mantêm). Elas são localizadas no texto INTEGRAL,
    quando o emitido é um recorte dele, e projetadas sobre o emitido: a nota aberta no corte continua nota. Sem o
    integral, a nota aberta no fim do emitido e a nota estrutural cortada no fim também valem como nota."""
    base = integral if isinstance(integral, str) and integral.startswith(texto) else texto
    spans = _spans_notas(base, tuple(notas))
    if base is texto:
        for nota in notas:
            if isinstance(nota, str):
                for k in range(len(nota) - 1, _MIN_NOTA_CORTADA - 1, -1):
                    if texto.endswith(nota[:k]):
                        spans.append((len(texto) - k, len(texto)))
                        break
    spans = [(a, min(b, len(texto))) for a, b in spans if a < len(texto)]
    chars = list(texto)
    for a, b in spans:
        for k in range(a, b):
            chars[k] = " "
    return "".join(chars), spans


def _obra_da_mencao(trecho: str) -> WorkKey | None:
    """Obra identificada por uma menção numerada no começo de `trecho` ('lei 6.404/1976, ...'); None se não identifica."""
    sintetico = "art. 1 da " + trecho[:160]
    for c in extract(sintetico):
        if c.span[0] == 0 and c.work is not None and c.work.year:
            return c.work
    return None


def _contexto_externo(frase: str, frase_n: str, propria: WorkKey | None) -> bool:
    """O trecho da frase antes da remissão fala de outra obra, de anexo ou de obra que não se prova ser a própria: a
    remissão sem obra não herda a própria. Menção numerada a obra explicitamente IGUAL à própria não é contexto externo."""
    def propria_da_especie(m: re.Match) -> str:  # "desta Lei" na obra que é lei: a própria obra, não contexto externo
        especies = _PROPRIA_POR_ESPECIE.get(propria.kind if propria else "", set())
        return " " * len(m.group(0)) if _dobra(re.sub(r"\s+", " ", m["nome"])) in especies else m.group(0)
    frase = _PROPRIA.sub(propria_da_especie, frase)
    frase_n = _dobra_pos(frase)
    if _ANEXO.search(frase_n) or _SIGLA_OBRA.search(frase):
        return True
    mencoes = list(_OBRA_NUMERADA.finditer(frase))
    for m in mencoes:
        if not _mesma_obra(_obra_da_mencao(frase[m.start():]), propria):
            return True
    cobertas = [(m.start(), m.start() + 160) for m in mencoes]
    if any(not any(a <= n.start() < b for a, b in cobertas) for n in _NUMERO_ANO.finditer(frase_n)):
        return True  # número com ano que nenhuma menção identificada explica
    inicios = {m.start() for m in mencoes}
    return any(m.start() not in inicios for m in _REFERENCIA_OBRA.finditer(frase))  # obra nomeada sem número


def _cauda_limpa(tn: str, fim: int, consumidos: list[tuple[int, int]] = ()) -> bool:
    """Depois da expressão consumida só pode vir delimitador terminal (fim, `.`, `;`, `)`, `]`, aspas) ou prosa. Token
    estrutural logo adiante (inciso, alínea, item, §, caput, anexo, romano solto, outra obra), mesmo depois de vírgula,
    `:`, travessão ou palavras funcionais, é qualificador que a leitura não consumiu: a expressão não vale por inteiro.
    O que cai dentro de outra expressão já reconhecida (`consumidos`) foi consumido por ela."""
    if _TERMINAL.match(tn, fim):
        return True
    p = _SEPARADOR.match(tn, fim).end()
    for _ in range(4):
        if p >= len(tn) or any(a <= p < b for a, b in consumidos):
            return True
        if _ESTRUTURAL.match(tn, p):
            return False
        f = _FUNCAO.match(tn, p)
        if not f:
            return True
        p = f.end()
    return True


def _toca_nota(ini: int, fim: int, spans: list[tuple[int, int]]) -> bool:
    return any(a < fim and b > ini for a, b in spans)


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


def _grupos(t: str, tn: str, art_proprio: str | None) -> list[_Grupo]:
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
        if _PREFIXO_RESIDUAL.search(tn[max(0, g.ini - 60):g.ini]):
            g.duvida = True  # qualificador antes do artigo que a leitura não reconheceu ("inc. I do art. 5")
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
            *, implicita: bool = True, notas: tuple[str, ...] = (), truncado: bool = False,
            integral: str | None = None) -> list[dict[str, Any]]:
    """Remissões do texto, em ordem de aparição, antes da decisão de existência.

    Cada item: texto, obra (WorkKey|None), obra_rotulo, caminho (rótulo), path (canônico) e `duvida` (True quando a
    leitura não basta para resolver). `art_proprio` (ex.: 'art14') habilita "no caput", "§ 1º deste artigo" e
    "no § 2º" como referência ao artigo do próprio dispositivo; `implicita` autoriza a remissão sem qualificação de
    obra a valer como a própria obra (desligada em dispositivo de anexo). `notas` são as anotações editoriais que a
    estrutura do documento já identificou; `truncado` marca texto cortado no limite: remissão que toca o corte não
    resolve (o que veio depois dele não foi devolvido); `integral` é o texto de que `texto` é o recorte: as notas
    editoriais são localizadas nele e projetadas sobre o emitido."""
    if not texto or not isinstance(texto, str):
        return []
    t, spans_notas = _mascarar_anotacoes(texto, tuple(notas), integral)
    tn = _dobra_pos(t)
    itens: list[dict[str, Any]] = []
    inicio_rubrica = re.match(r"\s*\"?Art\.?\s*\d", t)
    grupos = [g for g in _grupos(t, tn, art_proprio) if not (inicio_rubrica and g.ini == 0)]
    ocupados_grupos = [(g.ini, g.fim) for g in grupos]

    def vizinho_explicito(i: int) -> bool:
        if i + 1 >= len(grupos) or not grupos[i + 1].explicita:
            return False
        return _LIGACAO.fullmatch(t[grupos[i].fim:grupos[i + 1].ini]) is not None

    for i, g in enumerate(grupos):
        if g.anafora:
            continue
        obra, duvida = None, g.duvida or (bool(g.subs) and any(len(v) > 1 for _, v in g.subs[:-1]))
        if _toca_nota(g.ini, g.fim, spans_notas) or not _cauda_limpa(tn, g.fim, ocupados_grupos):
            duvida = True  # nota na expressão, ou qualificador logo depois que nenhuma produção consumiu
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
            ini_f = _inicio_da_frase(t, g.ini)
            if (not implicita or obra_propria is None or _contexto_externo(t[ini_f:g.ini], tn[ini_f:g.ini], obra_propria)
                    or vizinho_explicito(i)):
                duvida = True
            else:
                obra = obra_propria
        for path, rotulo in _caminhos(g):
            itens.append({"texto": texto[g.ini:g.fim].strip(), "obra": obra,
                          "obra_rotulo": rotulo_obra(obra) if obra is not None else None,
                          "caminho": rotulo, "path": path, "duvida": duvida or obra is None, "fim": g.fim})
    if art_proprio:
        itens.extend(_do_proprio_artigo(texto, t, tn, art_proprio, obra_propria, [(g.ini, g.fim) for g in grupos],
                                        spans_notas))
    if truncado:  # remissão que toca o corte, ou a que o corte deixa sem o que viria depois ("§ 2o do" + "art. 15")
        corte = len(texto.rstrip())
        for it in itens:
            resto = texto[it["fim"]:corte]
            if it["fim"] >= corte or (len(resto.strip()) <= 12 and not re.search(r"[.;:]", resto)):
                it["duvida"] = True
    return itens


def _do_proprio_artigo(texto: str, t: str, tn: str, art_proprio: str, obra: WorkKey | None,
                       ocupados: list[tuple[int, int]], spans_notas: list[tuple[int, int]]) -> list[dict[str, Any]]:
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
        if not explicito:
            ini_f = _inicio_da_frase(t, ini)
            externo = externo or _contexto_externo(t[ini_f:ini], tn[ini_f:ini], obra)  # "Na Lei X, ... caput"
        duvida = externo or not _cauda_limpa(tn, fim, ocupados) or _toca_nota(ini, fim, spans_notas)  # "§ 2º: inciso I"
        for p in _caminhos(_Grupo(ini, fim, [(n, suf)], [(nome, vals)])):
            out.append({"texto": texto[ini:fim].strip(), "obra": None if externo else obra,
                        "obra_rotulo": None if externo else rotulo_obra(obra),
                        "caminho": p[1], "path": p[0], "duvida": duvida, "fim": fim})
    return out


def remissoes(texto: str, obra_propria: WorkKey | None, existe: Callable[[WorkKey, str], bool],
              art_proprio: str | None = None, *, implicita: bool = True, notas: tuple[str, ...] = (),
              truncado: bool = False, integral: str | None = None) -> list[dict[str, Any]]:
    """`remissoes[]` do contrato: {texto, alvo: {obra, caminho}, resolvida}. `existe(obra, path)` consulta só o que já
    está capturado (sem rede) e nunca levanta; falha dela é inexistência."""
    saida: list[dict[str, Any]] = []
    vistos: set[tuple] = set()
    for it in extrair(texto, obra_propria, art_proprio, implicita=implicita, notas=notas, truncado=truncado,
                      integral=integral):
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
