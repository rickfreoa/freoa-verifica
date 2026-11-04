"""Validador mecânico v2, redução D5, dos gabaritos da Porta L (independente do código do verificador).

Uso:
  python -I -X utf8 validar_gabaritos_porta_l.py <conjunto.jsonl> <pasta_evidencias>
         [--fontes fontes.csv] [--mutantes mutantes.jsonl] [--cobertura cobertura.json]
         [--gerar-mutantes mutantes.rascunho.jsonl] [--conjunto desenvolvimento|reserva] [--exploratorio]

Redução D5: o validador confere FORMA e coerência mecânica. O juízo de mérito (todos os casos, todos os mutantes e o
vínculo documental da cobertura) é da segunda camada (matriz, seção 7.1). Os mutantes são ESCRITOS pelo pesquisador em
`mutantes.jsonl` e conferidos por `--mutantes`; `--gerar-mutantes` só grava um RASCUNHO (`*.rascunho.jsonl`), nunca o
arquivo congelado.

Normativo: il1-matriz-porta-l.md (versão 2), seções 1 a 7.1. Saída: uma linha `FALHA <id>: ...` por falha;
`REVISAO_HUMANA <id>: [(i)..(vi)] ...` para o que depende de juízo jurídico (segunda camada, seção 7.1; não reprova
sozinha, mas é contada e listada); `ALERTA <id>: ...` para o que não reprova; `INFO ...` para as contagens; e a linha
final `N casos, M falhas`. Código de saída: 0 só sem falha e com resultado completo; 1 com falha; 2 sem falha mas
INCOMPLETO (modo --exploratorio sem cobertura ou sem mutantes).

Princípio: o validador é condição necessária e FALHA FECHADO sempre que não pode decidir (extração inconclusiva, limite
ou ato não identificado, padrão não reconhecido). O validador lê só o conjunto, as evidências gravadas e (opcional)
fontes.csv e cobertura.json. Não importa nem lê o código do verificador.
"""
import argparse
import csv
import datetime
import hashlib
import io
import itertools
import json
import logging
import re
import sys
import unicodedata
from bisect import bisect_right
from collections import Counter, defaultdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

_VENDOR = Path(__file__).resolve().parent / "vendor"
if _VENDOR.is_dir() and str(_VENDOR) not in sys.path:
    sys.path.append(str(_VENDOR))  # no fim: o que o ambiente já tem tem precedência
try:
    import pypdf
    logging.getLogger("pypdf").setLevel(logging.CRITICAL)
except ImportError:  # extração de PDF indisponível => todo caso em PDF reprova (seção 7)
    pypdf = None

# --------------------------------------------------------------------------------------------------------------
# Constantes do esquema (seção 6)
# --------------------------------------------------------------------------------------------------------------
CAPS = ("a", "b", "c", "d", "e")
ESPECIES = ("lei", "lei_complementar", "decreto", "decreto_lei", "medida_provisoria", "emenda_constitucional",
            "constituicao", "resolucao_cvm", "resolucao_cmn")
TIPOS_POR_CAP = {
    "a": {"texto"},
    "b": {"texto", "revogado_vigente"},
    "c": {"verificado_para_D", "nao_verificado_para_D", "nao_existia_em_D"},
    "d": {"texto"},
    "e": {"texto"},
}
MOTIVOS = ("sem_fundamento_do_periodo", "sem_versao_oficial_na_data")
CONDICOES_INEXISTENCIA = ("anterior_a_obra", "anterior_a_inclusao")
HOSTS_OFICIAIS = {"www2.camara.leg.br", "camara.leg.br", "legis.senado.leg.br", "www.lexml.gov.br", "normas.leg.br",
                  "www.in.gov.br", "in.gov.br", "www.planalto.gov.br",
                  "www.normas.leg.br"}  # mesmo órgão, grafia com www (aparece em fontes.csv); ver LEIAME
ESPECIE_PREFIXO = {"lei": "lei", "lei_complementar": "lei-complementar", "decreto": "decreto",
                   "decreto_lei": "decreto-lei", "medida_provisoria": "mp", "emenda_constitucional": "emenda-constitucional",
                   "constituicao": "constituicao", "resolucao_cvm": "resolucao-cvm", "resolucao_cmn": "resolucao-cmn"}
PREFIXO_ESPECIE = {v: k for k, v in ESPECIE_PREFIXO.items()}
CAMPOS_CASO = {"id", "conjunto", "capacidade", "familia_alteracao", "familia_fundamento", "norma", "citacao", "caminho",
               "data", "data_mutante", "trecho", "gabarito", "norma_grande"}
CAMPOS_GABARITO = {"tipo", "texto", "motivos_aceitos", "cadeia", "alvos", "alvos_equivalentes", "fonte_oficial",
                   "fundamento_data", "condicao_inexistencia", "fontes_consultadas", "ultima_versao_anterior",
                   "redacao_alternativa"}
ID_RE = re.compile(r"^([LR])-([a-e])-(\d{3})$")
FAMILIA_RE = re.compile(
    r"^(?:original|(?:lei-complementar|lei|decreto-lei|decreto|emenda-constitucional|resolucao-cvm|resolucao-cmn)-\d+-\d{4}"
    r"|mp-\d+(?:-\d+)?-\d{4}|constituicao-\d{4})$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
DATA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATAHORA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
ROMANO_RE = re.compile(r"^(?=[IVXLCDM])M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})$")
CATS_REVISAO = {"(i)": "documento aceito é a publicação original ou a versão oficial válida em D",
                "(ii)": "lista de remissões completa onde o texto traz remissão que o parser não reconhece",
                "(iii)": "documentação do histórico negativo demonstra o limite afirmado",
                "(iv)": "família atribuída é o evento normativo correto",
                "(v)": "aderência semântica (cobertura, limites ambíguos, extração ou estrutura com leitura alternativa)",
                "(vi)": "mutante escrito pelo pesquisador: validade da expectativa para o conteúdo efetivo da chamada"}


def canon_fam(fam):
    """Identificador canônico normalizado do evento: sem zeros à esquerda no número (mesmo ato, mesma chave)."""
    if not isinstance(fam, str):
        return fam
    m = re.match(r"^(lei-complementar|lei|decreto-lei|decreto|emenda-constitucional|resolucao-cvm|resolucao-cmn)-"
                 r"(\d+)-(\d{4})$", fam)
    if m:
        return f"{m.group(1)}-{int(m.group(2))}-{m.group(3)}"
    m = re.match(r"^mp-(\d+)(?:-(\d+))?-(\d{4})$", fam)
    if m:
        return f"mp-{int(m.group(1))}" + (f"-{int(m.group(2))}" if m.group(2) else "") + f"-{m.group(3)}"
    return fam


# --------------------------------------------------------------------------------------------------------------
# Normalização ÚNICA (seção 7)
# --------------------------------------------------------------------------------------------------------------
_TRANS = str.maketrans({"“": '"', "”": '"', "„": '"', "‟": '"',
                        "‘": "'", "’": "'", "‚": "'", "‛": "'",
                        "º": "o", "°": "o"})
_WS = re.compile(r"[ \t\r\n\f\v\u00a0\u2007\u202f]+")


def norm(s):
    """NFC; espaço, tabulação, NBSP e quebra de linha viram um espaço, com aparas; aspas e apóstrofos tipográficos
    viram retos; º e ° viram o. Nada além (nem caixa, nem pontuação, nem numeração)."""
    s = unicodedata.normalize("NFC", s)
    return _WS.sub(" ", s.translate(_TRANS)).strip()


# --------------------------------------------------------------------------------------------------------------
# Anotações editoriais (seção 7): só da FONTE, só por padrão completo (verbo editorial + referência identificável a ato:
# espécie e número com ano, ou espécie e data)
# --------------------------------------------------------------------------------------------------------------
_ESP_RX = (r"(?:Lei\s+Complementar|Lei|Medida\s+Provis[óo]ria|Decreto-Lei|Decreto|Emenda\s+Constitucional|"
           r"Resolu[çc][ãa]o(?:\s+CVM|\s+CMN)?|Mensagem|Portaria|Ato|Conv[êe]nio|Tratado|MPV|MP|LC|EC)")
_ANO_RX = r"(?:18|19|20)\d{2}"
_DATA_EXT = rf"\d{{1,2}}\s*[ºo°]?\s+de\s+[A-Za-zçãéêóÇ]+\s+de\s+{_ANO_RX}"
_DATA_NUM = rf"\d{{1,2}}\s*[ºo°]?/\d{{1,2}}/{_ANO_RX}"
_REF_ATO_NUM = (rf"(?<![A-Za-zÀ-ú]){_ESP_RX}\s*(?:n[ºo°.]*\s*)?\d[\d.]*(?:-\d+)?\s*"
                rf"(?:/\s*{_ANO_RX}\b|,?\s*(?:de\s+)?(?:{_DATA_EXT}|{_DATA_NUM}|{_ANO_RX}\b))")
_REF_ATO_DATA = rf"(?<![A-Za-zÀ-ú]){_ESP_RX}\s*,?\s*de\s+(?:{_DATA_EXT}|{_DATA_NUM})"
_REF_TEST = re.compile(f"{_REF_ATO_NUM}|{_REF_ATO_DATA}", re.I)
_VERBO = (r"Reda[çc][ãa]o\s+dada|Inclu[ií]d[oa]s?|Acrescid[oa]s?|Acrescentad[oa]s?|Revogad[oa]s?|Vide|Vig[êe]ncia|"
          r"Produ[çc][ãa]o\s+de\s+efeitos?|Renumerad[oa]s?|Vetad[oa]s?")
_VERBO_EDIT = (r"acrescid|inclu[ií]d|acrescentad|revogad|reda[çc][ãa]o\s+dada|renumerad|vetad|alterad|suprimid|substitu[ií]d")
_ALVO_EDIT = (r"\"?(?:Caput|Artigo|Par[aá]grafo(?:\s+[uú]nico)?|§\s*\d+\S*|Inciso(?:s)?(?:\s+[IVXLCDM]+)?|Al[ií]nea(?:s)?"
              r"(?:\s+\w)?|Item|Express[ãa]o|Palavra|Texto|Anexo|Tabela)\"?")
_INNER = r"(?:[^()]|\([^()]*\))*"
_PAREN_EDIT = (rf"\(\s*(?:{_VERBO})\b{_INNER}\)"                                   # (Redação dada pela ...), (Incluído ...)
               rf"|\(\s*{_ALVO_EDIT}\b[^()]*?\b(?:{_VERBO_EDIT})\w*\b{_INNER}\)"     # (Parágrafo único acrescido pela ...)
               r"|\(\s*NR\s*\)")                                                       # marcador (NR)
_PASSO = re.compile(rf"\s?\x00(?P<idx>\d+)\x00|\s?(?P<an>{_PAREN_EDIT})", re.I)
# anotações que DÃO redação (família); as demais (Vide, Vigência, Produção de efeitos, Vetado, Revogado, Renumerado)
# só remetem, ressalvam ou extinguem e nunca definem o evento da redação
_DA_REDACAO = re.compile(r"\breda[çc][ãa]o\s+dada\b|\binclu[ií]d[oa]s?\b|\bacrescid[oa]s?\b|\bacrescentad[oa]s?\b", re.I)
_RESSALVA = re.compile(r"\(\s*(?:Vig[êe]ncia|Produ[çc][ãa]o\s+de\s+efeito|Vetad|Revogad)|\b(?:vetad|revogad)[oa]s?\b",
                       re.I)


def eh_anotacao(txt):
    """Parêntese editorial: marcador (NR), ou verbo editorial listado seguido de referência identificável a ato
    (espécie e número com ano, ou espécie e data)."""
    if re.fullmatch(r"\(\s*NR\s*\)", txt, re.I):
        return True
    return bool(_REF_TEST.search(txt))


def tem_anotacao_editorial(texto):
    """True se o texto (já normalizado) contém algum parêntese editorial reconhecido pelo padrão completo."""
    for m in re.finditer(_PAREN_EDIT, texto, re.I):
        if eh_anotacao(m.group(0)):
            return True
    return False


# --------------------------------------------------------------------------------------------------------------
# Extração: HTML (com riscado e seletores CSS), XML, PDF página a página
# --------------------------------------------------------------------------------------------------------------
class ErroExtracao(Exception):
    pass


_VOID = {"br", "hr", "img", "meta", "link", "input", "area", "base", "col", "embed", "param", "source", "track", "wbr"}
_INLINE = {"a", "span", "i", "b", "em", "strong", "u", "font", "sup", "sub", "small", "big", "abbr", "cite", "code",
           "mark", "o:p", "label"}
_AUTOFECHA = {"p", "li", "tr", "td", "th", "option"}
_CLASSE_RASURA = re.compile(r"strike|tachad|riscad|line-?through|revogad|rasur", re.I)


def _decoracao_inline(style):
    """Rasura efetiva do atributo `style` do PRÓPRIO elemento: vale a última declaração de `text-decoration` ou
    `text-decoration-line` (a declaração com prioridade, `!important`, também com espaços e comentários entre `!` e a
    palavra, vence a que não a tem). Devolve (rasurado, prioridade): `prioridade` é True quando alguma dessas declarações
    traz `!`, isto é, quando a leitura depende de prioridade (REVISAO_HUMANA e leitura alternativa na fonte). Só estilo
    inline; nenhuma folha de estilo é interpretada."""
    efetivo, importante, prioridade = False, False, False
    for decl in re.sub(r"(?s)/\*.*?\*/", " ", style or "").split(";"):
        if ":" not in decl:
            continue
        k, val = decl.split(":", 1)
        if k.strip().lower() not in ("text-decoration", "text-decoration-line"):
            continue
        val = val.strip().lower()
        imp = re.search(r"!\s*important\s*$", val) is not None
        if "!" in val:
            prioridade = True
        val = re.sub(r"!\s*important", " ", val)
        if importante and not imp:
            continue
        efetivo = "line-through" in val.split()
        importante = importante or imp
    return efetivo, prioridade


def _classes_de_rasura(s):
    """Classes de rasura CONHECIDAS: as que a folha de estilo `<style>` do documento associa a `line-through` (qualquer
    seletor com a classe, sem interpretar cascata, combinadores ou sobreposição) e as de nome convencional (tachado,
    riscado, strike...). O texto desses elementos NÃO é removido: vai à revisão humana."""
    nomes = set()
    for bloco in re.findall(r"(?is)<style\b[^>]*>(.*?)</style>", s):
        bloco = re.sub(r"(?s)/\*.*?\*/", " ", bloco)
        for seletores, corpo in re.findall(r"([^{}]+)\{([^}]*)\}", bloco):
            if "line-through" in corpo.lower():
                nomes |= set(re.findall(r"\.([\w-]+)", seletores))
    return nomes


class _ExtratorHTML(HTMLParser):
    def __init__(self, classes_conhecidas, inverter_prioridade=False):
        super().__init__(convert_charrefs=True)
        self.inverter_prioridade = inverter_prioridade
        self.partes, self.segs, self.pilha = [], [], []
        self.n_strike = self.n_skip = self.n_classe = 0
        self.cur = self.cur_c = None
        self.segs_classe = []
        self.conhecidas = classes_conhecidas

    def _emit(self, s):
        (self.cur if self.n_strike else self.partes).append(s)
        if self.n_classe and not self.n_strike:
            self.cur_c.append(s)

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _VOID:
            if tag == "br":
                self._emit(" ")
            return
        if tag in _AUTOFECHA:
            for i in range(len(self.pilha) - 1, -1, -1):
                if self.pilha[i][0] == tag:
                    self._fechar_ate(i)
                    break
                if self.pilha[i][0] in ("table", "ul", "ol", "div", "body"):
                    break
        a = {k.lower(): (v or "") for k, v in attrs}
        classes = set(a.get("class", "").split())
        decor, prioridade = _decoracao_inline(a.get("style", ""))
        if prioridade and self.inverter_prioridade:
            decor = not decor  # leitura alternativa: a outra resolução da prioridade inline
        strike = tag in ("strike", "s", "del") or decor
        classe = (not strike) and any(c in self.conhecidas or _CLASSE_RASURA.search(c) for c in classes)
        skip = tag in ("script", "style", "title")
        if tag not in _INLINE:
            self._emit(" ")
        if strike:
            if self.n_strike == 0:
                self.cur = []
            self.n_strike += 1
        if classe:
            if self.n_classe == 0:
                self.cur_c = []
            self.n_classe += 1
        if skip:
            self.n_skip += 1
        self.pilha.append((tag, strike, skip, classe))

    def _fechar_ate(self, i):
        while len(self.pilha) > i:
            tag, strike, skip, classe = self.pilha.pop()
            if skip:
                self.n_skip -= 1
            if classe:
                self.n_classe -= 1
                if self.n_classe == 0:
                    self.segs_classe.append("".join(self.cur_c))
                    self.cur_c = None
            if strike:
                self.n_strike -= 1
                if self.n_strike == 0:
                    self.segs.append("".join(self.cur))
                    self.cur = None
                    self.partes.append(f"\x00{len(self.segs) - 1}\x00")
            if tag not in _INLINE:
                self._emit(" ")

    def handle_endtag(self, tag):
        tag = tag.lower()
        for i in range(len(self.pilha) - 1, -1, -1):
            if self.pilha[i][0] == tag:
                self._fechar_ate(i)
                return

    def handle_data(self, data):
        if self.n_skip:
            return
        self._emit(data)

    def fim(self):
        self.close()
        self._fechar_ate(0)


def _decodificar(b):
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("latin-1", errors="replace")


def extrair_html(b, inverter_prioridade=False):
    """Devolve (texto com marcadores de riscado, segmentos riscados, segmentos de elementos com classe de rasura conhecida).
    Riscado (removido da fonte): elemento `strike`/`s`/`del` ou estilo inline com `line-through` efetivo. Folha de estilo e
    cascata CSS NÃO são interpretadas: o texto de elemento com classe de rasura conhecida fica no texto e é sinalizado
    para revisão humana (terceiro valor)."""
    s = _decodificar(b)
    p = _ExtratorHTML(_classes_de_rasura(s), inverter_prioridade)
    p.feed(s)
    p.fim()
    return "".join(p.partes), p.segs, p.segs_classe


def extrair_xml(b):
    s = _decodificar(b)
    s = re.sub(r"(?s)<!--.*?-->", " ", s)
    import html as _html
    return _html.unescape(re.sub(r"(?s)<[^>]+>", " ", s)), []


def extrair_pdf(b):
    """Texto por página (pypdf). Qualquer falha de extração é ErroExtracao (o caso reprova)."""
    if pypdf is None:
        raise ErroExtracao("pypdf indisponível: extração de PDF impossível")
    try:
        leitor = pypdf.PdfReader(io.BytesIO(b))
        paginas = []
        for i, pag in enumerate(leitor.pages, 1):
            try:
                # modo layout: o modo simples do pypdf insere espaços espúrios dentro de palavras ("nú mero");
                # o modo simples vale sempre que o texto em layout tiver menos de 60% do comprimento do simples
                # (página vazia ou truncada no layout, comum em PDFs do DOU)
                lay = pag.extract_text(extraction_mode="layout") or ""
                simples = pag.extract_text() or ""
                paginas.append(lay if len(norm(lay)) >= 0.6 * len(norm(simples)) else simples)
            except Exception as e:  # noqa: BLE001
                raise ErroExtracao(f"página {i} do PDF não extraída: {type(e).__name__}: {e}")
    except ErroExtracao:
        raise
    except Exception as e:  # noqa: BLE001
        raise ErroExtracao(f"PDF ilegível: {type(e).__name__}: {e}")
    return paginas


# Limpeza de PDF: cabeçalho/rodapé só sai por identificação POSITIVA e só nas bordas da página: (1) padrão de furniture do
# DOU/Câmara; (2) numeração de página (a linha inteira é o número, e só na linha mais externa); (3) linha da borda com
# contador de página ("Página 2", "pág. 2 de 9") que se repete, com o contador mascarado, na mesma borda de ≥ 2 páginas.
# A REPETIÇÃO, a posição ou a falta de pontuação, sozinhas, NÃO identificam cabeçalho: continuação normativa repetida na
# borda é preservada (nunca se apaga texto normativo). Se a continuidade depender de remoção ambígua, nada é removido e o
# recorte reprova no confronto (ALERTA lista as linhas repetidas mantidas).
_FURNITURA = re.compile(
    r"^(?:Documento assinado digitalmente|Este documento pode ser verificado|http://www\.in\.gov\.br/autenticidade"
    r"|que institui a Infraestrutura de Chaves|N[oº°] \d+(?:-[A-Z])?, \w+-feira.*ISSN|.*ISSN 1677-7042.*"
    r"|www\.in\.gov\.br.*)$")
_NUM_PAGINA = re.compile(r"^(?:(?:P[áa]gina|P[áa]g\.?)\s*\d+(?:\s*(?:de|/)\s*\d+)?|[-–]?\s*\d{1,4}\s*[-–]?|\d{1,4}\s*/\s*\d{1,4})$")
_CONTADOR_PAGINA = re.compile(r"(?<![A-Za-zÀ-ú])(?:P[áa]gina|P[áa]g\.|p\.)\s*\d+(?:\s*(?:de|/)\s*\d+)?\s*$", re.I)
_ESTRUT = re.compile(r'^\s*"?\s*(?:Art\.?\s*\d|§|Par[aá]grafo\s+[uú]nico|[IVXLCDM]+\s*[-–—.]\s|[a-z]\)\s|\d+\s*[.)]\s+\S|'
                     r'ANEXO\b|CAP[IÍ]TULO\b|SE[CÇ][AÃ]O\b|T[IÍ]TULO\b|LIVRO\b|(?:LEI|DECRETO|MEDIDA|EMENDA|RESOLU)\b)')


def _chave_borda(linha):
    return re.sub(r"\d+", "#", _WS.sub(" ", linha.strip()))


def _bordas(linhas):
    bordas = {"topo": Counter(), "base": Counter()}
    for ls in linhas:
        nn = [l for l in ls if l.strip()]
        for lado, sel in (("topo", nn[:3]), ("base", nn[-3:])):
            for k in set(_chave_borda(x) for x in sel):
                bordas[lado][k] += 1
    return bordas


def limpar_paginas_pdf(paginas, preservar_numeracao=False):
    """Remove cabeçalhos/rodapés de página só por identificação positiva (ver acima). Devolve (páginas limpas, nº de linhas
    removidas). Com `preservar_numeracao`, as linhas só de número e os contadores de página NÃO são removidos (leitura
    alternativa: uma célula numérica de tabela não é distinguível de número de página)."""
    linhas = [list(p.split("\n")) for p in paginas]
    bordas = _bordas(linhas)
    limiar = max(2, int(0.2 * len(paginas)))
    removidas = 0
    out = []
    for ls in linhas:
        nn_idx = [i for i, l in enumerate(ls) if l.strip()]
        topo, base = set(nn_idx[:3]), set(nn_idx[-3:])
        externas = {nn_idx[0], nn_idx[-1]} if nn_idx else set()
        novo = []
        for i, l in enumerate(ls):
            if (i in topo or i in base) and l.strip():
                lim = _WS.sub(" ", l.strip())
                k = _chave_borda(l)
                lado = "topo" if i in topo else "base"
                num = bool(_NUM_PAGINA.match(lim)) and (i in externas or not lim.isdigit())
                contador = (bool(_CONTADOR_PAGINA.search(lim)) and len(paginas) >= 2 and bordas[lado][k] >= limiar
                            and not _ESTRUT.match(l))
                if _FURNITURA.match(lim) or ((num or contador) and not preservar_numeracao):
                    removidas += 1
                    continue
            novo.append(l)
        # palavra composta quebrada na linha ("higiênico-\nsanitários"): sem espaço depois do hífen
        out.append(re.sub(r"(?<=[A-Za-zÀ-ú])-[ \t]*\n[ \t]*(?=[a-zà-ú])", "-", "\n".join(novo)))
    return out, removidas


def linhas_repetidas_nas_bordas(paginas):
    """Linhas (já limpas) que ainda se repetem na borda de ≥ 2 páginas: possível cabeçalho NÃO removido (ALERTA)."""
    if len(paginas) < 2:
        return []
    bordas = _bordas([list(p.split("\n")) for p in paginas])
    return sorted({k for c in bordas.values() for k, n in c.items() if n >= 2 and k.strip() and not k.strip().isdigit()})


# --------------------------------------------------------------------------------------------------------------
# Fonte: texto limpo, atos, marcadores estruturais
# --------------------------------------------------------------------------------------------------------------
class Fonte:
    """Documento oficial gravado, já extraído. `clean` é o texto normalizado, sem anotações editoriais e sem riscado;
    `anots` e `risc` guardam onde cada remoção ocorreu (posição em `clean`)."""

    def __init__(self, sha, tipo, paginas, clean, anots, risc, bps, page_starts, removidas):
        self.sha, self.tipo, self.paginas = sha, tipo, paginas
        self.clean, self.anots, self.risc = clean, anots, risc
        self._bps, self._page_starts, self.removidas = bps, page_starts, removidas
        self._atos = None
        self._marc = None
        self.anexo_lax = False
        self.alternativas = []  # [(motivo, Fonte)]: leituras alternativas de uma extração ambígua (REVISAO_HUMANA)
        self.repetidas = []
        self.classe_rasura = []
        self._bp_pos = [x[0] for x in bps]

    def pagina_de(self, pos):
        i = bisect_right(self._bp_pos, pos) - 1
        j = self._bps[i][1] + (pos - self._bps[i][0])
        return max(1, bisect_right(self._page_starts, j))

    def atos(self):
        if self._atos is None:
            self._atos = _achar_atos(self.clean)
        return self._atos

    def marcadores(self):
        if self._marc is None:
            self._marc = _achar_marcadores(self)
        return self._marc

    def variante_lax(self):
        """Mesma fonte, com a rubrica de anexo em caixa mista reconhecida pela posição (início de período), mesmo seguida de
        título que começa por minúscula. Só vale com REVISAO_HUMANA."""
        v = Fonte(self.sha, self.tipo, self.paginas, self.clean, self.anots, self.risc, self._bps, self._page_starts,
                  self.removidas)
        v._atos, v.anexo_lax = self._atos, True
        v.repetidas, v.classe_rasura = self.repetidas, self.classe_rasura
        return v


_MESES = {m: i for i, m in enumerate(
    ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro",
     "dezembro"], 1)}
_ESP_TXT = {"lei complementar": "lei_complementar", "lei": "lei", "decreto-lei": "decreto_lei", "decreto": "decreto",
            "medida provisória": "medida_provisoria", "medida provisoria": "medida_provisoria",
            "emenda constitucional": "emenda_constitucional", "resolução": "resolucao_cvm", "resolucao": "resolucao_cvm",
            "resolução cvm": "resolucao_cvm", "resolucao cvm": "resolucao_cvm", "resolução cmn": "resolucao_cmn",
            "resolucao cmn": "resolucao_cmn"}
_ESP_ALT = (r"LEI COMPLEMENTAR|LEI|DECRETO-LEI|DECRETO|MEDIDA PROVIS[ÓO]RIA|EMENDA CONSTITUCIONAL|"
            r"RESOLU[ÇC][ÃA]O(?: CVM| CMN)?")
_CABECALHO_MAIUSC = re.compile(
    rf"(?<![A-Za-zÀ-ú])({_ESP_ALT})\s+N[o°]?\.?\s*(\d[\d.]*(?:-\d+)?)\s*,\s*DE\s+(\d{{1,2}})\s*o?\s+DE\s+"
    rf"([A-ZÇÃÉÊÍÓÚ]+)\s+DE\s+(\d{{4}})")
_CABECALHO_MISTO = re.compile(
    rf"(?<![A-Za-zÀ-ú])({_ESP_ALT})\s+N[o°]?\.?\s*(\d[\d.]*(?:-\d+)?)\s*,\s*DE\s+(\d{{1,2}})\s*o?\s+DE\s+"
    rf"([A-Za-zÇçÃãÉéÊêÍíÓóÚú]+)\s+DE\s+(\d{{4}})", re.I)
_CABECALHO_CANDIDATO = re.compile(
    rf"(?<![A-Za-zÀ-ú])({_ESP_ALT})\s+N[o°]?\.?\s*(\d[\d.]*(?:-\d+)?)\s*(?:,\s*)?(?:de\s+|/)\s*"
    rf"(?:\d{{1,2}}\s*o?\s*(?:de\s+[A-Za-zÇçÃãÉéÊêÍíÓóÚú]+\s+de\s+|/\d{{1,2}}/)|)(?:{_ANO_RX})", re.I)
_PALAVRAS_DE_CITACAO = {"referida", "citada", "mencionada", "supracitada", "aludida", "mesma", "própria", "propria",
                        "antiga", "nova", "outra", "qualquer", "cada", "tal", "essa", "esta", "esse", "este", "aquela",
                        "aquele", "anterior", "seguinte", "revogada", "revogado", "vigente", "aplicável", "aplicavel"}
_EMENTA_VERBO = re.compile(
    r"(?:disp[õo]e|altera|institui|regulamenta|aprova|abre|autoriza|estabelece|cria|revoga|d[áa]|fixa|concede|estima|"
    r"denomina|declara|torna|acrescenta|modifica|disciplina|reestrutura|prorroga|convalida|ratifica|regula|promulga|"
    r"determina|veda|prop[õo]e|trata|define|aplica)\b", re.I)
_CABECALHO_CF = re.compile(r"(?<![A-Za-zÀ-ú])CONSTITUI[ÇC][ÃA]O DA REP[ÚU]BLICA FEDERATIVA DO BRASIL(?: DE (\d{4}))?")
_PREPOSICAO_ANTES = re.compile(r"\b(?:DA|DO|DE|DAS|DOS|PELA|PELO|NA|NO|EM|COM|À|AOS|AO)\s+$", re.I)
_PONTUACAO_FRONTEIRA = '.;:!?")]”'


def _esp_de_texto(t):
    return _ESP_TXT.get(re.sub(r"\s+", " ", t.strip().lower()), "resolucao_cvm")


def _data_cab(dia, mes, ano):
    m = _MESES.get(mes.lower())
    if not m:
        return None
    try:
        return datetime.date(int(ano), m, int(dia))
    except ValueError:
        return None


def _antes(clean, i):
    """(último caractere antes de i, palavra anterior, caractere antes dessa palavra), pulando uma aspa de abertura."""
    j = i
    if j > 0 and clean[j - 1] == '"':
        j -= 1
    k = j
    while k > 0 and clean[k - 1] == " ":
        k -= 1
    if k == 0:
        return "", "", ""
    ini = k
    while ini > 0 and clean[ini - 1] != " ":
        ini -= 1
    return clean[k - 1], clean[ini:k], (clean[ini - 2] if ini >= 2 else "")


# palavra imediatamente antes de "Art."/"ANEXO"/divisão que revela remissão no meio da frase, não início de dispositivo
_PALAVRAS_DE_REMISSAO = {"do", "da", "dos", "das", "no", "na", "nos", "nas", "ao", "aos", "à", "pelo", "pela", "pelos",
                         "pelas", "e", "ou", "a", "o", "os", "as", "de", "em", "com", "por", "para", "art", "arts",
                         "artigo", "artigos", "neste", "nesta", "deste", "desta", "conforme", "segundo", "vide", "ver",
                         "sob", "constante", "constantes", "previsto", "prevista", "previstos", "previstas", "tabela",
                         "quadro"}


def _limite(clean, i, tipo):
    """O identificador que começa em i está em início de dispositivo/divisão/ato (e não é remissão no meio da frase)?
    Início de texto, ou pontuação de período antes; para artigo, divisão, anexo e ato também uma palavra de título
    (inicial maiúscula) antes; para inciso e alínea também `; e` / `; ou`."""
    ch, palavra, ch2 = _antes(clean, i)
    if ch == "" or ch in _PONTUACAO_FRONTEIRA:
        return True
    if tipo in ("art", "div", "anexo") and ch != "," and palavra.lower().strip('",.;:()') not in _PALAVRAS_DE_REMISSAO:
        return True
    if tipo in ("inc", "ali") and palavra.lower() in ("e", "ou") and ch2 in ";,":
        return True
    return False


def _achar_atos(clean):
    achados = {}
    for m in _CABECALHO_MAIUSC.finditer(clean):
        if _PREPOSICAO_ANTES.search(clean[max(0, m.start() - 8):m.start()]):
            continue  # "REGULAMENTO DA LEI Nº 8.918, DE ...": referência em título, não cabeçalho de ato
        achados[m.start()] = {"pos": m.start(), "esp": _esp_de_texto(m.group(1)), "num": m.group(2).replace(".", ""),
                              "ano": int(m.group(5)), "data": _data_cab(m.group(3), m.group(4), m.group(5)),
                              "txt": m.group(0)}
    # cabeçalho em caixa mista: só em início de período/título (a referência no meio da frase não é cabeçalho); sem
    # essa leitura, um segundo ato em caixa mista seria atribuído ao anterior
    for m in _CABECALHO_MISTO.finditer(clean):
        if m.start() in achados or _PREPOSICAO_ANTES.search(clean[max(0, m.start() - 8):m.start()]):
            continue
        seguinte = clean[m.end():m.end() + 4].lstrip()
        ch_ant = _antes(clean, m.start())[0]
        # título, não citação: depois de ponto final (ou no começo) e seguido de maiúscula (ementa ou `Art.`), nunca de
        # vírgula, ponto e vírgula, parêntese ou travessão (`Lei nº 5.172, de ..., art. 2º;`, `... - Código Tributário`)
        if ch_ant in ("", ".", "!", "?") and (seguinte == "" or seguinte[0].isupper()):
            achados[m.start()] = {"pos": m.start(), "esp": _esp_de_texto(m.group(1)),
                                  "num": m.group(2).replace(".", ""), "ano": int(m.group(5)),
                                  "data": _data_cab(m.group(3), m.group(4), m.group(5)), "txt": m.group(0)}
    # cabeçalho candidato (caixa mista sem a forma completa: ementa em minúscula, data numérica, só o ano, ou sem ponto antes):
    # o que parece cabeçalho de ato e não foi reconhecido acima NUNCA é atribuído ao ato anterior; vira cabeçalho de ato com
    # a identidade que o texto traz (que, diferindo do esperado, reprova o recorte) ou, sem ano legível, identidade vazia
    for m in _CABECALHO_CANDIDATO.finditer(clean):
        if m.start() in achados or _PREPOSICAO_ANTES.search(clean[max(0, m.start() - 8):m.start()]):
            continue
        if any(a < m.start() < a + len(h["txt"]) for a, h in achados.items()):
            continue
        ch, palavra, _ = _antes(clean, m.start())
        seguinte = clean[m.end():m.end() + 80].lstrip()
        if ch in ("", ".", "!", "?"):
            ok = not seguinte[:1] in (",", ";", ")", "-", "–", "—")
        else:
            w = palavra.lower().strip('",.;:()')
            ok = (ch not in ',;:("“-–—/' and w not in _PALAVRAS_DE_REMISSAO and w not in _PALAVRAS_DE_CITACAO
                  and (seguinte[:1].isupper() or bool(_EMENTA_VERBO.match(seguinte))))
        if not ok:
            continue
        ano = None
        mm = re.search(rf"\b({_ANO_RX})\b", clean[m.end(2):m.end()])
        if mm:
            ano = int(mm.group(1))
        achados[m.start()] = {"pos": m.start(), "esp": _esp_de_texto(m.group(1)), "num": m.group(2).replace(".", ""),
                              "ano": ano, "data": None, "txt": m.group(0), "candidato": True}
    for m in _CABECALHO_CF.finditer(clean):
        ano = int(m.group(1) or 1988)
        achados[m.start()] = {"pos": m.start(), "esp": "constituicao", "num": str(ano), "ano": ano,
                              "data": datetime.date(1988, 10, 5) if ano == 1988 else None, "txt": m.group(0)}
    out = [achados[k] for k in sorted(achados)]
    inicial = None
    m = _CABECALHO_MISTO.search(clean[:2500])
    if m:
        inicial = {"pos": 0, "esp": _esp_de_texto(m.group(1)), "num": m.group(2).replace(".", ""),
                   "ano": int(m.group(5)), "data": _data_cab(m.group(3), m.group(4), m.group(5)), "txt": m.group(0)}
    return {"cabecalhos": out, "inicial": inicial}


# Marcadores estruturais: artigo, parágrafo, inciso, alínea, divisão, ato, anexo (rubrica), fim.
_M_ART = re.compile(r'"?Art\.?\s*(\d+(?:\.\d{3})*)\s*[ºo°]?(?:\s*-\s*([A-Z])(?![a-z]))?(?![\dA-Za-z])')
_M_PAR = re.compile(r"(?:§\s*(\d+)\s*[ºo°]?(?![\dA-Za-z]))|(Par[aá]grafo\s+[uú]nico)", re.I)
_M_INC = re.compile(r"([IVXLCDM]+)\s*[-–—]\s")
_M_ALI = re.compile(r"([a-z])\)\s")
_M_DIV = re.compile(
    r"(?:(?:CAP[IÍ]TULO|Cap[ií]tulo|SE[CÇ][AÃ]O|Se[cç][aã]o|SUBSE[CÇ][AÃ]O|Subse[cç][aã]o|T[IÍ]TULO|T[ií]tulo|LIVRO|Livro|"
    r"PARTE|Parte)\s+(?:[IVXLCDM]+|\d+|[ÚU]NICO|[Úú]nic[oa]|GERAL|Geral|ESPECIAL|Especial)(?![A-Za-zÀ-ú])"
    r"|(?:DISPOSI[CÇ][OÕ]ES|Disposi[cç][oõ]es)\s+[A-ZÀ-Ú][A-Za-zÀ-ú]+)")
_M_ANEXO = re.compile(r"(?<![A-Za-zÀ-ú])ANEXO(?:\s+(?P<id>[IVXLCDM]+|\d+|[ÚU]NICO))?(?![A-Za-zÀ-ú])")
_M_ANEXO_MISTO = re.compile(r"(?<![A-Za-zÀ-ú])Anexo(?:\s+(?P<id>[IVXLCDM]+|\d+|[Úú]nico))?(?![A-Za-zÀ-ú])")
_M_FIM = re.compile(r"Bras[ií]lia,\s*\d{1,2}|Este texto n[aã]o substitui")
_NIVEL_M = {"art": 1, "par": 2, "inc": 3, "ali": 4}


def _romano_int(s):
    v = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    s = s.upper()
    tot = 0
    for i, ch in enumerate(s):
        n = v[ch]
        tot += -n if i + 1 < len(s) and v[s[i + 1]] > n else n
    return tot


def _anexo_chave(x):
    """Chave comparável do número de um anexo: `I` e `1` são o mesmo anexo; ausente e `único` são o mesmo."""
    if x is None:
        return "UNICO"
    x = str(x).strip().upper().replace("Ú", "U")
    if x in ("", "UNICO"):
        return "UNICO"
    if x.isdigit():
        return int(x)
    if ROMANO_RE.match(x):
        return _romano_int(x)
    return x


def _achar_marcadores(f):
    clean = f.clean
    M = []

    def add(pos, fim, tipo, val, **kw):
        M.append(dict(pos=pos, fim=fim, tipo=tipo, val=val, **kw))
    for m in _M_ART.finditer(clean):
        pos = m.start() + (1 if clean[m.start()] == '"' else 0)
        if _limite(clean, pos, "art"):
            add(pos, m.end(), "art", (m.group(1).replace(".", ""), m.group(2) or None))
    for m in _M_PAR.finditer(clean):
        if _limite(clean, m.start(), "par"):
            add(m.start(), m.end(), "par", m.group(1) if m.group(1) else "unico")
    for m in _M_INC.finditer(clean):
        if ROMANO_RE.match(m.group(1)) and _limite(clean, m.start(), "inc"):
            add(m.start(), m.end(), "inc", m.group(1))
    for m in _M_ALI.finditer(clean):
        if _limite(clean, m.start(), "ali"):
            add(m.start(), m.end(), "ali", m.group(1))
    for m in _M_DIV.finditer(clean):
        if _limite(clean, m.start(), "div"):
            add(m.start(), m.end(), "div", m.group(0))
    for m in _M_ANEXO.finditer(clean):
        if _limite(clean, m.start(), "anexo"):
            add(m.start(), m.end(), "anexo", m.group("id"))
    # rubrica em caixa mista (`Anexo I`): só em início de período (pontuação de período ou início do texto antes) e seguida
    # de título (maiúscula, algarismo, travessão) ou do fim; remissão no meio da frase (`do Anexo I`) nunca é rubrica
    for m in _M_ANEXO_MISTO.finditer(clean):
        ch, _, _ = _antes(clean, m.start())
        seguinte = clean[m.end():m.end() + 3].lstrip()
        if (ch == "" or ch in _PONTUACAO_FRONTEIRA) and (seguinte == "" or not seguinte[0].islower() or f.anexo_lax):
            ident = m.group("id")
            add(m.start(), m.end(), "anexo", ident.upper() if ident else None)
    for m in _M_FIM.finditer(clean):
        if _limite(clean, m.start(), "fim"):
            add(m.start(), m.end(), "fim", None)
    cab = f.atos()
    for h in cab["cabecalhos"]:
        add(h["pos"], h["pos"] + len(h["txt"]), "ato", None, h=h)
    ordem = {"ato": 0, "anexo": 1, "div": 2, "art": 3, "par": 4, "inc": 5, "ali": 6, "fim": 7}
    M.sort(key=lambda x: (x["pos"], ordem[x["tipo"]]))
    # unicidade por (pos, tipo) e contexto: ato e anexo vigentes em cada marcador
    ato_atual, anexo_atual, vistos, out = cab["inicial"], None, set(), []
    for mk in M:
        k = (mk["pos"], mk["tipo"])
        if k in vistos:
            continue
        vistos.add(k)
        if mk["tipo"] == "ato":
            h = mk["h"]
            if ato_atual is not None and (h["esp"], _sn(h["num"]), h["ano"]) == (
                    ato_atual["esp"], _sn(ato_atual["num"]), ato_atual["ano"]):
                continue  # o mesmo ato repetido (título de página, rodapé): não é limite nem zera o anexo
            ato_atual, anexo_atual = h, None
        elif mk["tipo"] == "anexo":
            anexo_atual = mk
        mk["ato"], mk["anexo"] = ato_atual, anexo_atual
        out.append(mk)
    return out


def _proximo(M, i, tipos, ate=None):
    fim = len(M) if ate is None else ate
    for j in range(i + 1, fim):
        if M[j]["tipo"] in tipos:
            return j
    return None


_LIM_NIVEL = {"par": ("par", "art", "div", "ato", "anexo", "fim"),
              "inc": ("par", "inc", "art", "div", "ato", "anexo", "fim"),
              "ali": ("par", "inc", "ali", "art", "div", "ato", "anexo", "fim")}


def resolver_dispositivo(f, pc):
    """Candidatos estruturais do caminho `pc` na fonte: lista de dict(start, end, ato, anexo, marc). A posição é
    resolvida pela CADEIA de pertencimento (anexo, artigo, parágrafo, inciso, alínea): o § 1º do art. 156 nunca é o
    § 1º do art. 157, o artigo do corpo nunca é o artigo de um anexo e vice-versa."""
    M = f.marcadores()
    n, out = len(f.clean), []

    def pos_de(j):
        return M[j]["pos"] if j is not None and j < len(M) else n
    if pc["art"] is None:  # anexo inteiro ou tabela do anexo
        for i, mk in enumerate(M):
            if mk["tipo"] == "anexo" and _anexo_chave(mk["val"]) == _anexo_chave(pc["anexo"]):
                j = _proximo(M, i, ("ato", "anexo", "fim"))
                out.append(dict(start=mk["pos"], end=pos_de(j), ato=mk["ato"], anexo=mk, marc=mk))
        return out
    for i, mk in enumerate(M):
        if mk["tipo"] != "art" or mk["val"] != (pc["art"], pc["suf"]):
            continue
        if (pc["anexo"] is None) != (mk["anexo"] is None):
            continue
        if pc["anexo"] is not None and _anexo_chave(mk["anexo"]["val"]) != _anexo_chave(pc["anexo"]):
            continue
        j_art = _proximo(M, i, ("art", "div", "ato", "anexo", "fim"))
        janela = (i, j_art if j_art is not None else len(M))   # (marcador inicial, limite exclusivo de índices)
        start, end = mk["pos"], pos_de(j_art)
        partes = list(pc["partes"])
        if partes and partes[0][0] == "caput":
            k = _proximo(M, i, ("par",), janela[1])
            janela = (i, k if k is not None else janela[1])
            end = pos_de(k) if k is not None else end
            partes = partes[1:]
        elif partes and partes[0][0] != "par":   # inciso/alínea direto do caput: janela do caput
            k = _proximo(M, i, ("par",), janela[1])
            janela = (i, k if k is not None else janela[1])
            end = pos_de(k) if k is not None else end
        ok = True
        for tp, val in partes:
            k = None
            for j in range(janela[0] + 1, janela[1]):
                if M[j]["tipo"] == tp and M[j]["val"] == val:
                    k = j
                    break
            if k is None:
                ok = False
                break
            lim_j = _proximo(M, k, _LIM_NIVEL[tp], janela[1])
            fim_janela = lim_j if lim_j is not None else janela[1]
            start, end = M[k]["pos"], (pos_de(lim_j) if lim_j is not None else pos_de(janela[1]))
            janela = (k, fim_janela)
        if ok:
            out.append(dict(start=start, end=end, ato=mk["ato"], anexo=mk["anexo"], marc=mk))
    return out


_PRIORIDADE_HTML = re.compile(r"(?is)text-decoration(?:-line)?\s*:[^;\"'>]*!")


def carregar_fonte(b, sha=None, _variante=None):
    """Extrai e limpa uma evidência. Levanta ErroExtracao se a extração é vazia ou inconclusiva (sem letras, caracteres
    não decodificados, páginas sem texto, CSS de riscado não suportado). Não há tamanho mínimo universal. Quando a
    extração tem uma construção ambígua (linha só de número em PDF; prioridade em estilo inline de HTML), a fonte traz em
    `alternativas` a leitura alternativa (`_variante` é interno)."""
    removidas, repetidas, segs_classe = 0, [], []
    segs = []
    alternativas = []
    if b[:5] == b"%PDF-":
        tipo = "pdf"
        brutas = extrair_pdf(b)
        paginas, removidas = limpar_paginas_pdf(brutas, _variante == "numeros")
        if _variante is None and limpar_paginas_pdf(brutas, True)[1] < removidas:
            alternativas.append(("linhas só de número ou contadores de página removidos como paginação: podem ser células "
                                 "numéricas de tabela ou continuação normativa", "numeros"))
        repetidas = linhas_repetidas_nas_bordas(paginas)
        textos = [norm(p) for p in paginas]
    elif b.lstrip()[:5].lower() == b"<?xml":
        tipo = "xml"
        t, segs = extrair_xml(b)
        textos = [norm(t)]
    else:
        tipo = "html"
        t, segs, segs_classe = extrair_html(b, _variante == "prioridade")
        textos = [norm(t)]
        if _variante is None and _PRIORIDADE_HTML.search(_decodificar(b)):
            alternativas.append(("estilo inline com prioridade (`!important`) em `text-decoration`: a rasura efetiva depende "
                                 "da leitura da prioridade", "prioridade"))
    todo = " ".join(textos)
    if not any(ch.isalpha() for ch in todo):
        raise ErroExtracao("extração vazia ou inconclusiva (nenhuma letra extraída)")
    if tipo == "pdf" and (todo.count("�") + todo.count("(cid:")) > 0.02 * len(todo):
        raise ErroExtracao("extração inconclusiva (caracteres não decodificados no PDF)")
    if tipo == "pdf" and sum(1 for t in textos if not t) > 0.5 * len(textos):
        raise ErroExtracao("extração inconclusiva (mais da metade das páginas sem texto)")
    starts, off = [], 0
    for t in textos:
        starts.append(off)
        off += len(t) + 1
    joined = " ".join(textos)
    out, clean_len, bps, anots, risc, last = [], 0, [(0, 0)], [], [], 0
    for m in _PASSO.finditer(joined):
        if m.group("idx") is not None:
            kind = "r"
        else:
            if not eh_anotacao(m.group("an")):
                continue
            kind = "a"
        piece = joined[last:m.start()]
        out.append(piece)
        clean_len += len(piece)
        if kind == "r":
            risc.append((clean_len, norm(segs[int(m.group("idx"))])))
        else:
            anots.append((clean_len, m.group("an")))
        bps.append((clean_len, m.end()))
        last = m.end()
    out.append(joined[last:])
    clean = "".join(out)
    fonte = Fonte(sha, tipo, textos, clean, anots, risc, bps, starts, removidas)
    fonte.repetidas = repetidas
    fonte.classe_rasura = [x for x in (norm(y) for y in segs_classe) if x]
    fonte.alternativas = [(m, carregar_fonte(b, sha, var)) for m, var in alternativas]
    return fonte


# --------------------------------------------------------------------------------------------------------------
# Identidades: normas, atos, obras, famílias
# --------------------------------------------------------------------------------------------------------------
_REF_NORMA = re.compile(
    r"(Lei\s+Complementar|Lei|Decreto-Lei|Decreto|Medida\s+Provis[óo]ria|Emenda\s+Constitucional|Resolu[çc][ãa]o\s+CVM|"
    r"Resolu[çc][ãa]o\s+CMN)\s*(?:n[ºo°.]*\s*)?(\d{1,3}(?:\.\d{3})+|\d+)(?:-(\d+))?\s*(?:/|,\s*de\s+"
    r"(?:\d{1,2}\s*[ºo°]?\s*de\s+[A-Za-zçãé]+\s+de\s+|\d{1,2}/\d{1,2}/)?)(\d{4})", re.I)
_ESP_DE_REF = {"leicomplementar": "lei_complementar", "lei": "lei", "decreto-lei": "decreto_lei", "decreto": "decreto",
               "medidaprovisória": "medida_provisoria", "medidaprovisoria": "medida_provisoria",
               "emendaconstitucional": "emenda_constitucional", "resoluçãocvm": "resolucao_cvm",
               "resolucaocvm": "resolucao_cvm", "resoluçãocmn": "resolucao_cmn", "resolucaocmn": "resolucao_cmn",
               "mp": "medida_provisoria", "mpv": "medida_provisoria", "lc": "lei_complementar",
               "ec": "emenda_constitucional"}
_CODIGOS = {
    r"c[óo]digo\s+civil": ("lei", "10406", 2002),
    r"c[óo]digo\s+de\s+processo\s+civil": ("lei", "13105", 2015),
    r"c[óo]digo\s+tribut[áa]rio\s+nacional": ("lei", "5172", 1966),
    r"c[óo]digo\s+de\s+defesa\s+do\s+consumidor": ("lei", "8078", 1990),
    r"c[óo]digo\s+penal": ("decreto_lei", "2848", 1940),
    r"c[óo]digo\s+de\s+processo\s+penal": ("decreto_lei", "3689", 1941),
    r"lei\s+das\s+s\.?\s*a\.?|lei\s+das\s+sociedades\s+por\s+a[çc][õo]es": ("lei", "6404", 1976),
    r"constitui[çc][ãa]o(?:\s+federal)?(?:\s+de\s+1988)?|\bCF(?:/88)?\b": ("constituicao", "1988", 1988),
    r"\bCPC\b": ("lei", "13105", 2015), r"\bCTN\b": ("lei", "5172", 1966), r"\bCC\b": ("lei", "10406", 2002),
}


def canon(especie, numero, ano):
    pre = ESPECIE_PREFIXO.get(especie)
    if pre is None:
        return None
    if especie == "constituicao":
        return f"constituicao-{ano}"
    return canon_fam(f"{pre}-{str(numero).replace('.', '')}-{ano}")


def canon_norma(n):
    try:
        return canon(n["especie"], n["numero"], n["ano"])
    except (KeyError, TypeError):
        return None


def referencia_norma(texto):
    """Primeira referência a norma em `texto`: (especie, numero, ano) ou None; reconhece códigos por nome."""
    cands = []
    m = _REF_NORMA.search(texto)
    if m:
        esp = _ESP_DE_REF.get(re.sub(r"\s+", "", m.group(1).lower()))
        num = m.group(2).replace(".", "") + (f"-{m.group(3)}" if m.group(3) else "")
        cands.append((m.start(), (esp, num, int(m.group(4)))))
    for pat, val in _CODIGOS.items():
        mc = re.search(pat, texto, re.I if not pat.startswith(r"\b") else 0)
        if mc:
            cands.append((mc.start(), val))
    return min(cands)[1] if cands else None


def referencias_norma(texto):
    """Todas as normas referidas em `texto` (conjunto de identificadores canônicos)."""
    ids = set()
    for m in _REF_NORMA.finditer(texto):
        esp = _ESP_DE_REF.get(re.sub(r"\s+", "", m.group(1).lower()))
        num = m.group(2).replace(".", "") + (f"-{m.group(3)}" if m.group(3) else "")
        ids.add(canon(esp, num, int(m.group(4))))
    for pat, val in _CODIGOS.items():
        if re.search(pat, texto, re.I if not pat.startswith(r"\b") else 0):
            ids.add(canon(*val))
    return ids


def canon_obra(texto):
    """Identificador canônico de uma obra citada (`Lei 6.404/1976`, `Código Civil`...), ou None se irreconhecível."""
    r = referencia_norma(texto or "")
    return canon(*r) if r else None


_ATO_ANY = re.compile(
    r"(Lei\s+Complementar|Lei|Decreto-Lei|Decreto|Medida\s+Provis[óo]ria|Emenda\s+Constitucional|Constitui[çc][ãa]o"
    r"(?:\s+Federal)?(?:\s+de\s+1988)?|Resolu[çc][ãa]o(?:\s+CVM|\s+CMN)?)\s*(?:n[ºo°.]*\s*)?(\d[\d.]*(?:-\d+)?)?"
    r"(?:\s*(?:/|,)\s*(?:de\s+)?(?:\d{1,2}\s*[ºo°]?\s+de\s+[A-Za-zçãé]+\s+de\s+|\d{1,2}/\d{1,2}/)?(\d{4}))?", re.I)


def parse_ato(texto):
    """(especie, numero, ano|None) do primeiro ato mencionado em `texto`, ou None. `Constituição Federal de 1988` é
    (constituicao, 1988, 1988)."""
    for m in _ATO_ANY.finditer(texto or ""):
        if re.match(r"constitui", m.group(1), re.I):
            my = re.match(r"\s*de\s+(\d{4})", (texto or "")[m.end():])
            ano = int(my.group(1)) if my else 1988
            return "constituicao", str(ano), ano
        if not m.group(2):
            continue
        esp = _ESP_DE_REF.get(re.sub(r"\s+", "", m.group(1).lower()), "lei")
        return esp, m.group(2).replace(".", ""), int(m.group(3)) if m.group(3) else None
    return None


_ATO_DATADO = re.compile(
    rf"({_ESP_RX})\s*(?:n[ºo°.]*\s*)?(\d[\d.]*(?:-\d+)?)\s*(?:,\s*)?(?:de\s+)?(?:(?P<d1>\d{{1,2}})\s*[ºo°]?\s+de\s+"
    rf"(?P<mes>[A-Za-zçãéêó]+)\s+de\s+(?P<a1>{_ANO_RX})|(?P<d2>\d{{1,2}})\s*[ºo°]?/(?P<m2>\d{{1,2}})/(?P<a2>{_ANO_RX})|"
    rf"/\s*(?P<a3>{_ANO_RX})|(?P<a4>{_ANO_RX}))", re.I)


def atos_datados(textos):
    """{identificador canônico: (data mínima, data máxima)} dos atos referidos nas anotações `textos`, com data completa
    (mínima = máxima) ou só ano (1º/jan a 31/dez). Referência sem ano não é reconhecida como anotação."""
    out = {}
    for t in textos:
        for m in _ATO_DATADO.finditer(norm(t)):
            esp = _ESP_DE_REF.get(re.sub(r"\s+", "", m.group(1).lower()))
            if not esp:
                continue
            num = m.group(2).replace(".", "")
            if m.group("a1"):
                d = _data_cab(m.group("d1"), m.group("mes"), m.group("a1"))
                lim = (d, d) if d else None
                ano = int(m.group("a1"))
            elif m.group("a2"):
                try:
                    d = datetime.date(int(m.group("a2")), int(m.group("m2")), int(m.group("d2")))
                except ValueError:
                    d = None
                lim = (d, d) if d else None
                ano = int(m.group("a2"))
            else:
                ano = int(m.group("a3") or m.group("a4"))
                lim = (datetime.date(ano, 1, 1), datetime.date(ano, 12, 31))
            if lim is None:
                continue
            k = canon(esp, num, ano)
            if k not in out or (out[k][0] != out[k][1] and lim[0] == lim[1]):
                out[k] = lim
    return out


def atos_das_anotacoes(textos):
    """Identificadores canônicos dos atos nomeados nas anotações editoriais (conjunto; sempre com ano)."""
    return set(atos_datados(textos))


def datas_de_atos(fontes, anots=()):
    """{identificador: (data mínima, data máxima)}: cabeçalhos de ato das fontes (data exata) e anotações."""
    out = dict(atos_datados(anots))
    for fx in fontes:
        if fx is None:
            continue
        a = fx.atos()
        for h in list(a["cabecalhos"]) + ([a["inicial"]] if a["inicial"] else []):
            if h["data"]:
                out[canon(h["esp"], h["num"], h["ano"])] = (h["data"], h["data"])
    return out


# --------------------------------------------------------------------------------------------------------------
# Caminhos e citações
# --------------------------------------------------------------------------------------------------------------
_NIVEL = {"art": 1, "caput": 1, "par": 2, "inc": 3, "ali": 4, "item": 5}
_COMP_RE = re.compile(
    r"^(?:caput|§\s*(?P<par>\d+)\s*[ºo°]?|par[aá]grafo\s+(?P<unico>[uú]nico)|inciso\s+(?P<inc>[IVXLCDM]+)|"
    r"al[ií]nea\s+(?P<ali>[a-z]))$", re.I)
_ART_CAM = re.compile(r"^art(?:igo)?\.?\s*(?P<num>[1-9]\d*(?:\.\d{3})*)\s*[ºo°]?(?:\s*-\s*(?P<suf>[A-Z]))?$", re.I)
_ANEXO_CAM = re.compile(r"^anexo(?:\s+(?P<anx>[IVXLCDM]+|\d+|[uú]nico))?$", re.I)


def parse_caminho(s):
    """Caminho completo -> dict(anexo, art, suf, partes[(tipo,valor)], nivel); None se sintaxe incompleta ou inválida.
    Hierarquia estrita: artigo, depois `caput` (só no início) ou um § (ou parágrafo único), depois um inciso (algarismo
    romano válido), depois uma alínea; sem repetição de nível nem inversão. Aceita `art. 4º, § 4º, inciso II, alínea a` e,
    em (d), `Anexo I, art. 2º`, `Anexo I` ou `Anexo I, tabela`."""
    if not isinstance(s, str) or not s.strip():
        return None
    pedacos = [p.strip() for p in s.strip().split(",")]
    res = {"anexo": None, "art": None, "suf": None, "partes": [], "nivel": "art"}
    i = 0
    m = _ANEXO_CAM.match(pedacos[0])
    if m:
        res["anexo"] = (m.group("anx") or "").upper() or "UNICO"
        res["nivel"] = "anexo"
        i = 1
        if i < len(pedacos) and pedacos[i].lower() == "tabela" and len(pedacos) == 2:
            res["partes"].append(("tab", ""))
            res["nivel"] = "tabela"
            return res
    if i < len(pedacos):
        m = _ART_CAM.match(pedacos[i])
        if not m:
            return None
        res["art"] = m.group("num").replace(".", "")
        res["suf"] = (m.group("suf") or "").upper() or None
        res["nivel"] = "art"
        i += 1
    elif res["anexo"] is None:
        return None
    ordem = 0
    for p in pedacos[i:]:
        m = _COMP_RE.match(p)
        if not m or res["art"] is None:
            return None
        if p.lower() == "caput":
            if res["partes"]:
                return None
            res["partes"].append(("caput", ""))
            res["nivel"], ordem = "caput", 1
            continue
        if m.group("par"):
            tp, val, nv = "par", m.group("par"), 2
            if int(val) < 1:
                return None
        elif m.group("unico"):
            tp, val, nv = "par", "unico", 2
        elif m.group("inc"):
            tp, val, nv = "inc", m.group("inc").upper(), 3
            if not ROMANO_RE.match(val):
                return None
        else:
            tp, val, nv = "ali", m.group("ali").lower(), 4
        if nv <= ordem:
            return None
        ordem = nv
        res["partes"].append((tp, val))
        res["nivel"] = tp
    return res


def norm_partes(partes):
    """`caput` seguido de sub-dispositivo é o mesmo dispositivo que o sub-dispositivo (inciso do caput); `caput` só é
    distinto de nada quando está sozinho (`art. 10, caput` != `art. 10`)."""
    partes = list(partes)
    if len(partes) > 1 and partes[0] == ("caput", ""):
        partes = partes[1:]
    return tuple(partes)


def chave_caminho(cam):
    """Forma canônica comparável do caminho: (anexo, artigo, partes)."""
    p = parse_caminho(cam) if isinstance(cam, str) else cam
    if not p:
        return None
    base = f"{p['art']}{'-' + p['suf'] if p['suf'] else ''}" if p["art"] else ""
    return (p["anexo"], base, norm_partes(p["partes"]))


_CIT_ART = re.compile(r"\bart(?:igo)?s?\.?\s*(?P<num>\d+(?:\.\d{3})*)\s*(?P<ord>[ºo°])?(?:\s*-\s*(?P<suf>(?-i:[A-Z])))?\b",
                      re.I)


def parse_citacao(cit):
    """Artigo/anexo citado: dict(art, suf, ord, anexo(bool), anexo_id, span, tabela)."""
    cit = cit if isinstance(cit, str) else ""
    r = {"art": None, "suf": None, "ord": False, "anexo": bool(re.search(r"\banexo\b", cit, re.I)),
         "anexo_id": None, "span": None, "tabela": bool(re.search(r"\btabela\b", cit, re.I))}
    m = _CIT_ART.search(cit)
    if m:
        r.update(art=m.group("num").replace(".", ""), suf=m.group("suf"), ord=bool(m.group("ord")), span=m.span())
    ma = re.search(r"(?i:\banexo)\s+(?P<id>[IVXLCDM]+|\d+|(?i:[uú]nico))\b", cit)
    if ma:
        r["anexo_id"] = ma.group("id")
    return r


def _np(num):
    return r"\.?".join(re.escape(d) for d in num)


def re_inicio_artigo(num, suf):
    base = rf'^"?\s*Art\.?\s*{_np(num)}o?'
    if suf:
        return re.compile(base + rf"\s*-\s*{suf}(?![\dA-Za-z])")
    return re.compile(base + r"(?![\dA-Za-z])(?!\s*-\s*[A-Z](?![a-z]))")


def re_inicio_dispositivo(cam):
    """Padrão do identificador COMPLETO do dispositivo de último nível do caminho (None se não há identificador próprio,
    como na tabela de anexo)."""
    p = parse_caminho(cam) if isinstance(cam, str) else cam
    if not p or p["nivel"] == "tabela":
        return None
    if p["nivel"] in ("art", "caput") and p["art"]:
        return re_inicio_artigo(p["art"], p["suf"])
    if p["nivel"] == "anexo":
        return re.compile(r'^\s*(?i:anexo)\b')
    tipo, val = p["partes"][-1]
    if tipo == "par":
        return re.compile(r"^§\s*" + re.escape(val) + r"o?(?![\dA-Za-z])" if val != "unico"
                          else r"^Par[aá]grafo\s+[uú]nico", re.I if val == "unico" else 0)
    if tipo == "inc":
        return re.compile(rf"^{val}\s*[-–—.]\s")
    return re.compile(rf"^{val}\)")


_PROX_ART = re.compile(r'^"?\s*Art\.?\s*\d')
_PROX_PAR = re.compile(r'^"?\s*(?:§\s*\d|Par[aá]grafo\s+[uú]nico)')
_PROX_INC = re.compile(r'^"?\s*[IVXLCDM]+\s*[-–—]\s')
_PROX_ALI = re.compile(r'^"?\s*[a-z]\)\s')
_PROX_ITEM = re.compile(r'^"?\s*\d+\s*[.)]\s+[A-ZÀ-Ú]')
_PROX_DIV = re.compile(r'^"?\s*(?:CAP[IÍ]TULO|Cap[ií]tulo|SE[CÇ][AÃ]O|Se[cç][aã]o|T[IÍ]TULO|T[ií]tulo|LIVRO|Livro|'
                       r'SUBSE[CÇ][AÃ]O|Subse[cç][aã]o|ANEXO|PARTE|Parte|DISPOSI[CÇ][OÕ]ES|Disposi[cç][oõ]es)\b')
_PROX_ATO = re.compile(rf'^"?\s*(?:{_ESP_ALT})\s+N[o°]')
_PROX_FIM = re.compile(r'^"?\s*(?:Bras[ií]lia|Este texto n[aã]o substitui|\*?\s*Este texto)')
# rubrica seguida de dispositivo: só título reconhecível (Da/Do/Das/Dos/De + palavras, ou caixa alta, ou Disposições/Parte)
# até 120 caracteres, sem pontuação de período. Texto qualquer com inicial maiúscula NÃO prova que haja rubrica.
_PROX_RUB = re.compile(
    r'^"?\s*(?:D[aeo]s?\s+[^.;:()"§]{1,110}?|[A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ ,\-–]{3,110}?|'
    r'Disposi[cç][oõ]es\s+[^.;:()"§]{1,100}?|Parte\s+[^.;:()"§]{1,100}?)\s+Art\.?\s*\d')


def classificar_proximo(depois):
    """Classifica o que a fonte traz logo depois do recorte: ('art'|'par'|'inc'|'ali'|'item'|'div'|'ato'|'fim'|
    'rubrica'|'desconhecido')."""
    d = re.sub(r'^[\s"]+', "", depois)  # aspas de fechamento do comando alterador e aspas de abertura do próximo
    if not d:
        return "fim"
    for nome, rx in (("art", _PROX_ART), ("par", _PROX_PAR), ("inc", _PROX_INC), ("ali", _PROX_ALI),
                     ("item", _PROX_ITEM), ("div", _PROX_DIV), ("ato", _PROX_ATO), ("fim", _PROX_FIM)):
        if rx.match(d):
            return nome
    m = re.match(r"(.{1,140}?)\s+Art\.?\s*\d", d)
    if m and _eh_rubrica(m.group(1)):
        return "rubrica"
    return "desconhecido"


_MINUSC_TITULO = {"de", "da", "do", "das", "dos", "e", "ou", "em", "no", "na", "nos", "nas", "a", "o", "as", "os", "para",
                  "por", "com", "ao", "aos", "à", "sobre", "entre", "sem", "sob", "ante", "até", "pelo", "pela"}


def _eh_rubrica(t):
    """Rubrica (título marginal) de dispositivo: sintagma curto, sem pontuação de período, que é (a) `Da/Do/Das/Dos/De...`,
    `Disposições ...` ou `Parte ...`; (b) caixa alta; ou (c) em Title Case (toda palavra significativa com inicial
    maiúscula: `Dever de Informar`, `Resultados de Exercícios Futuros`). Texto comum com só a primeira palavra maiúscula
    (`Continuação normativa obrigatória`) NÃO é rubrica."""
    t = t.strip()
    if not t or len(t) > 140 or re.search(r'[.;:()"§]', t):
        return False
    palavras = t.split()
    if len(palavras) > 14:
        return False
    if re.match(r"(?:D[aeo]s?|Disposi[cç][oõ]es|Parte)\s", t):
        return True
    if t.upper() == t and len(t) >= 4:
        return True
    return all(w[:1].isupper() or w[:1].isdigit() or w.lower() in _MINUSC_TITULO for w in palavras) and palavras[0][:1].isupper()


# --------------------------------------------------------------------------------------------------------------
# Remissões (e)
# --------------------------------------------------------------------------------------------------------------
_RX_ARTS = re.compile(r"(?<![A-Za-zÀ-ú])(?:arts?\.?(?=\s*\d)|artigos?)\s*", re.I)
_RX_PRE_SOLTO = re.compile(
    r"(?:§§?|(?:par[aá]grafos?|incisos?|al[ií]neas?|caput)\b)(?:(?!\b(?:arts?|artigos?|lei|desta|deste)\b)[^.;(),]){0,30}?"
    r"\s+d[aeo]s?\s*$", re.I)
_RX_ABERTA = re.compile(r"\s*,?\s*(?:e\s+seguintes|e\s+ss\b\.?|ss\b\.?)", re.I)
_RX_NUM_ART = re.compile(r"(?P<num>\d+(?:\.\d{3})*)\s*o?(?:\s*-\s*(?P<suf>(?-i:[A-Z]))(?![a-z]))?")
_RX_SUB = re.compile(
    r"\s*,?\s*(?:(?:e|ou)\s+)?(?:(?P<caput>caput)|(?P<ps>§§?)\s*(?P<pn>\d+)\s*o?(?P<pl>(?:\s*(?:,|e|ou)\s*\d+\s*o?)*)|"
    r"(?P<un>par[aá]grafo\s+[uú]nico)|(?P<is>incisos?)\s+(?P<in>[IVXLCDM]+)(?P<il>(?:\s*(?:,|e|ou)\s*[IVXLCDM]+\b)*)|"
    r"(?P<as>al[ií]neas?)\s+\"?(?P<an>[a-z])\)?\"?(?P<al>(?:\s*(?:,|e|ou)\s*\"?[a-z]\)?\"?\b)*))", re.I)
_RX_PRE = re.compile(
    r"(?<![A-Za-zÀ-ú])(?:(?:o|a|os|as)\s+)?(?:(?P<caput>caput)|(?P<ps>§§?)\s*(?P<pn>\d+)\s*o?(?P<pl>(?:\s*(?:,|e|ou)\s*\d+\s*o?)*)|"
    r"(?P<un>par[aá]grafo\s+[uú]nico)|(?P<is>incisos?)\s+(?P<in>[IVXLCDM]+)(?P<il>(?:\s*(?:,|e|ou)\s*[IVXLCDM]+\b)*)|"
    r"(?P<as>al[ií]neas?)\s+\"?(?P<an>[a-z])\)?\"?(?P<al>(?:\s*(?:,|e|ou)\s*\"?[a-z]\)?\"?\b)*))\s*,?\s*d[aeo]s?\s+", re.I)
_RX_OBRA_LOCAL = re.compile(r"\s*,?\s*(?:d[aeo]s?\s+)?(?:desta|deste|dessa|desse)\s+"
                            r"(?:Lei(?:\s+Complementar)?|C[óo]digo|Decreto(?:-Lei)?|Medida\s+Provis[óo]ria|Regulamento)\b", re.I)
_RX_CONECT = re.compile(r"\s*,?\s*d[aeo]s?\s+", re.I)
_CODIGOS_RX = [(re.compile(p, re.I if not p.startswith(r"\b") else 0), v) for p, v in _CODIGOS.items()]
_RX_LEAD = re.compile(r'^"?\s*(?:Art\.?\s*[\d.]+\s*[ºo°]?(?:\s*-\s*[A-Z](?![a-z]))?|§\s*\d+\s*[ºo°]?|Par[aá]grafo\s+[uú]nico|'
                      r'[IVXLCDM]+\s*[-–—]|[a-z]\))')
_RX_DESTE_ARTIGO = re.compile(r"\s*,?\s*(?:d[eo]ste|neste)\s+artigo\b", re.I)
_PREP_INTERNA = {"no", "nos", "ao", "aos", "do", "dos", "pelo", "pelos", "na", "nas", "à", "e", "ou", "o", "os", "com",
                 "em", "sob", "conforme", "segundo", "nos", "pelas", "pela", "das", "da"}


def _obra_em(texto, pos):
    """Obra nomeada logo depois de uma referência a artigo (`da Lei nº X/AAAA`, `do Código Civil`): (canônico, fim)."""
    mc = _RX_CONECT.match(texto, pos)
    if not mc:
        return None
    p2 = mc.end()
    m = _REF_NORMA.match(texto, p2)
    if m:
        esp = _ESP_DE_REF.get(re.sub(r"\s+", "", m.group(1).lower()))
        num = m.group(2).replace(".", "") + (f"-{m.group(3)}" if m.group(3) else "")
        return canon(esp, num, int(m.group(4))), m.end()
    for rx, v in _CODIGOS_RX:
        m = rx.match(texto, p2)
        if m:
            return canon(*v), m.end()
    return None


def _sub_lista(m):
    """Alternativas de UM nível de um _RX_SUB/_RX_PRE casado -> lista de (tipo, valor)."""
    g = m.groupdict()
    if g.get("caput"):
        return [("caput", "")]
    if g.get("ps"):
        vals = [g["pn"]] + re.findall(r"\d+", g.get("pl") or "")
        return [("par", v) for v in vals]
    if g.get("un"):
        return [("par", "unico")]
    if g.get("is"):
        vals = [g["in"].upper()] + [x.upper() for x in re.findall(r"[IVXLCDM]+\b", g.get("il") or "")]
        return [("inc", v) for v in vals]
    if g.get("as"):
        vals = [g["an"].lower()] + re.findall(r"\b([a-z])\b", (g.get("al") or "").lower())
        return [("ali", v) for v in vals]
    return []


def _cadeias(niveis):
    """Produto cartesiano dos níveis (cada um com alternativas) -> lista de cadeias normalizadas."""
    return [norm_partes(ch) for ch in itertools.product(*niveis)] if niveis else [()]


def cadeia_citacao(cit):
    """Sub-dispositivos da citação (antes e depois do artigo), no formato de parse_caminho: (partes, ambiguo)."""
    cit = norm(cit) if isinstance(cit, str) else ""
    m = _CIT_ART.search(cit)
    niveis = []
    if m:
        pre = []
        pos_pre = m.start()
        while True:
            cand = None
            for mm in _RX_PRE.finditer(cit[:pos_pre]):
                if mm.end() == pos_pre:
                    cand = mm
                    break
            if not cand:
                break
            pre.append(_sub_lista(cand))
            pos_pre = cand.start()
        niveis += pre  # já em ordem hierárquica (o mais próximo do artigo é o mais alto)
        pos = m.end()
        while True:
            ms = _RX_SUB.match(cit, pos)
            if not ms:
                break
            niveis.append(_sub_lista(ms))
            pos = ms.end()
    if re.search(r"\btabela\b", cit, re.I) and not m:
        niveis.append([("tab", "")])
    ambiguo = any(len(n) != 1 for n in niveis)
    return (list(norm_partes(tuple(n[0] for n in niveis if n))), ambiguo)


def confere_citacao_caminho(citacao, caminho):
    """Mensagem de divergência entre a citação e o caminho completo (anexo, artigo, parágrafo, inciso, alínea), ou
    None se coincidem. A citação precisa conter dispositivo."""
    pc = parse_caminho(caminho)
    pcit = parse_citacao(citacao)
    if pc is None:
        return None  # caminho inválido é outra falha
    if pcit["art"] is None and not pcit["anexo"]:
        return f"citação sem dispositivo (artigo ou anexo): {citacao!r}"
    if (pc["anexo"] is None) != (not pcit["anexo"]):
        return f"caminho {caminho!r} e citação {citacao!r} divergem quanto ao anexo"
    if pc["anexo"] is not None and _anexo_chave(pc["anexo"]) != _anexo_chave(pcit["anexo_id"]):
        return f"anexo do caminho ({pc['anexo']}) difere do anexo da citação ({pcit['anexo_id'] or 'único'})"
    if (pc["art"], pc["suf"]) != (pcit["art"], (pcit["suf"] or "").upper() or None):
        return f"caminho {caminho!r} não corresponde ao artigo da citação {citacao!r}"
    partes, ambiguo = cadeia_citacao(citacao)
    if ambiguo:
        return f"citação refere mais de um dispositivo (lista): {citacao!r}"
    if tuple(partes) != norm_partes(pc["partes"]):
        return (f"caminho {caminho!r} não corresponde ao dispositivo citado em {citacao!r} "
                f"(cadeia da citação: {partes or 'artigo inteiro'})")
    return _citacao_nao_interpretada(citacao)


_RX_QUALIF_CIT = re.compile(
    r"§§?\s*\d+\s*[ºo°]?|par[aá]grafo\s+[uú]nico|\bincisos?\s+[IVXLCDM]+\b|\bal[ií]neas?\s+\"?[a-z]\)?\"?|\bcaput\b|"
    r"\banexo(?:\s+(?:[IVXLCDM]+|\d+|[uú]nico))?|\btabela\b|\bartigos?\b", re.I)
_RX_CONECTIVOS = re.compile(
    r"\b(?:d[aeo]s?|n[ao]s?|ao|à|o|a|os|as|e|ou|de|do|da|em|pelo|pela|lei|decreto|decreto-lei|complementar|c[óo]digo|"
    r"constitui[çc][ãa]o|federal|n[ºo°.]|medida|provis[óo]ria|emenda|constitucional|resolu[çc][ãa]o|cvm|cmn)\b", re.I)


def _citacao_nao_interpretada(citacao):
    """Citação inequívoca e integralmente interpretada quanto à identidade e ao dispositivo: dois artigos, duas normas,
    `item`, faixa aberta ou qualquer palavra que sobre depois de lidos artigo, subdispositivos, anexo e obra falham fechado."""
    cit = norm(citacao)
    if len(re.findall(r"(?<![A-Za-zÀ-ú])(?:arts?\.?(?=\s*\d)|artigos?\s*\d)", cit, re.I)) > 1:
        return f"citação refere mais de um artigo: {citacao!r}"
    if len(referencias_norma(cit)) > 1:
        return f"citação refere mais de uma norma (alternativa ou lista): {citacao!r}"
    resto = _REF_NORMA.sub(" ", cit)
    for pat in _CODIGOS:
        resto = re.sub(pat, " ", resto, flags=re.I if not pat.startswith(r"\b") else 0)
    resto = _CIT_ART.sub(" ", resto)
    resto = _RX_QUALIF_CIT.sub(" ", resto)
    resto = _RX_CONECTIVOS.sub(" ", resto)
    resto = re.sub(r"[\d\W_]+", " ", resto).strip()
    if resto:
        return f"citação com texto não interpretado ({resto[:40]!r}): qualificador ou dispositivo não suportado em {citacao!r}"
    return None


def _lead_fim(texto):
    m = _RX_LEAD.match(texto)
    return m.end() if m else 0


def extrair_remissoes(texto, host, art_proprio=None):
    """Remissões expressas no texto do gabarito. Devolve (refs, incertos): refs = lista de dict(obra, chave, expl,
    faixa); incertos = trechos com construção de remissão que o parser NÃO resolve (vão à segunda camada, nunca
    reprovam nem aprovam a lista sozinhos). Resolve: listas de artigos, faixas `arts. 10 a 12` (todos os artigos),
    listas de §§, incisos e alíneas antes ou depois do artigo, `caput`, `§ N deste artigo` e `no § N` (artigo do próprio
    dispositivo, `art_proprio`). A auto-identificação do dispositivo não conta."""
    refs, spans, incertos = [], [], []
    lead_end = _lead_fim(texto)
    for m in _RX_ARTS.finditer(texto):
        if m.start() < lead_end:
            continue
        pre, off_antes = [], max(0, m.start() - 160)
        antes = texto[off_antes:m.start()]
        pos_pre = len(antes)
        while True:  # sub-dispositivos antes do artigo ("o inciso IV do caput do art. 1º")
            cand = None
            for mm in _RX_PRE.finditer(antes):
                if mm.end() == pos_pre:
                    cand = mm
                    break
            if not cand:
                break
            pre.append(_sub_lista(cand))
            pos_pre = cand.start()
        # qualificador antes do artigo que o parser não resolveu ("parágrafo segundo do art. 5", "§§ 1º a 3º do art. 5"):
        # a referência é parcialmente interpretada e não impõe alvo superficial
        incerta = bool(_RX_PRE_SOLTO.search(antes[:pos_pre]))
        pos = m.end()
        arts, faixa, conexa = [], False, False
        while True:
            mn = _RX_NUM_ART.match(texto, pos)
            if not mn:
                break
            num, suf = mn.group("num").replace(".", ""), (mn.group("suf") or "").upper() or None
            pos = mn.end()
            niveis = []
            while True:
                ms = _RX_SUB.match(texto, pos)
                if not ms:
                    break
                niveis.append(_sub_lista(ms))
                pos = ms.end()
            if niveis and re.match(r"\s*a\s+(?:o\s+)?§?\s*\d", texto[pos:], re.I):
                incertos.append(texto[max(0, pos - 25):pos + 25] + " (faixa de sub-dispositivos)")
            if faixa:
                ant = arts[-1]
                if ant[1] or suf or ant[2] or niveis or int(num) < int(ant[0]) or int(num) - int(ant[0]) > 500:
                    incertos.append(f"faixa de artigos não resolvida: arts. {ant[0]} a {num}")
                else:
                    arts += [(str(k), None, []) for k in range(int(ant[0]) + 1, int(num))]
                faixa = False
            arts.append((num, suf, niveis))
            ml = re.match(r"\s*(?:(?P<a>a|at[ée])|,|e|ou)\s+(?=\d)", texto[pos:], re.I)
            if not ml:
                break
            faixa = bool(ml.group("a"))
            conexa = True
            pos += ml.end()
        if not arts:
            continue
        ma = _RX_ABERTA.match(texto, pos)
        if ma:  # "art. 4 e seguintes": faixa aberta, nunca decidida mecanicamente
            incerta = True
            incertos.append(f"remissão aberta: ...{texto[max(0, m.start() - 10):ma.end() + 10]}...")
            pos = ma.end()
        if incerta and not ma:
            incertos.append(f"referência parcialmente interpretada (qualificador antes do artigo): "
                            f"...{texto[max(0, m.start() - 40):pos + 10]}...")
        fim_ref = pos
        expl, obra = False, host
        mo = _RX_OBRA_LOCAL.match(texto, fim_ref)
        if mo:
            expl, fim_ref = True, mo.end()
        else:
            ob = _obra_em(texto, fim_ref)
            if ob:
                obra, expl, fim_ref = ob[0], True, ob[1]
        spans.append((off_antes + pos_pre, fim_ref))
        for num, suf, niveis in arts:
            for cam in _cadeias(pre + niveis):
                refs.append({"obra": obra, "expl": expl, "faixa": conexa and len(arts) > 1,
                             "chave": (None, f"{num}{'-' + suf if suf else ''}", cam),
                             "ini": off_antes + pos_pre, "fim": fim_ref, "incerta": incerta})
    # remissões internas (sem "art."): "no § 1º", "§ 2º deste artigo": artigo do próprio dispositivo
    for m in re.finditer(r"§§?\s*\d|par[aá]grafo\s+[uú]nico", texto, re.I):
        if m.start() < lead_end or any(a <= m.start() < b for a, b in spans):
            continue
        ch, palavra, _ = _antes(texto, m.start())
        if ch == "" or ch in _PONTUACAO_FRONTEIRA:
            continue  # identificador de dispositivo do próprio texto (início de parágrafo)
        niveis, pos = [], m.start()
        while True:
            ms = _RX_SUB.match(texto, pos)
            if not ms:
                break
            niveis.append(_sub_lista(ms))
            pos = ms.end()
        if re.match(r"\s*,?\s*(?:a|at[ée])\s+(?:o\s+)?§?\s*\d", texto[pos:], re.I):
            incertos.append(f"faixa de sub-dispositivos: ...{texto[max(0, m.start() - 15):pos + 25]}...")
            continue  # faixa `§§ 1º a 3º`: nunca lida como remissão ao artigo do próprio dispositivo
        if re.match(r"\s*,?\s*d[aeo]s?\s+(?:arts?\b|artigos?\b)", texto[pos:], re.I):
            continue  # qualificador de um artigo citado: quem decide é a leitura da referência ao artigo
        md = _RX_DESTE_ARTIGO.match(texto, pos)
        if md:
            pos = md.end()
        if not niveis or art_proprio is None or palavra.lower() not in _PREP_INTERNA:
            continue  # o resíduo abaixo o sinaliza
        spans.append((m.start(), pos))
        for cam in _cadeias(niveis):
            refs.append({"obra": host, "expl": False, "faixa": False, "chave": (None, art_proprio, cam),
                         "ini": m.start(), "fim": pos})
    # herança de obra: "... do art. 1º, do parágrafo único do art. 170 e do caput do art. 174 da Constituição Federal"
    # (as alternativas de uma mesma referência formam um grupo e herdam juntas)
    grupos = []
    for r in refs:
        if grupos and grupos[-1][0]["ini"] == r["ini"] and grupos[-1][0]["fim"] == r["fim"]:
            grupos[-1].append(r)
        else:
            grupos.append([r])
    for i in range(len(grupos) - 2, -1, -1):
        a, b = grupos[i][0], grupos[i + 1][0]
        if not a["expl"] and b["expl"] and b["ini"] >= a["fim"] and re.fullmatch(
                r"\s*[,;]?\s*(?:(?:e|ou)\s+)?(?:d[aeo]s?\s*)?", texto[a["fim"]:b["ini"]], re.I):
            for r in grupos[i]:
                r["obra"], r["expl"] = b["obra"], True
    # resíduo: construções de remissão fora dos trechos resolvidos (nunca decididas pelo parser)
    for rx, rot in ((r"(?<![A-Za-zÀ-ú])(?:arts?\.|artigos?)\s*\d", "artigo"), (r"§§?\s*\d", "§"),
                    (r"par[aá]grafo\s+[uú]nico", "parágrafo único"), (r"\bincisos?\s+[IVXLCDM]+\b", "inciso"),
                    (r"\bal[ií]neas?\s+\"?[a-z]\b", "alínea"), (r"\b(?:d[eo]ste|neste)\s+artigo\b", "deste artigo"),
                    (r"\bcaput\b", "caput"),
                    (r"\b(?:artigo|par[aá]grafo|inciso|al[ií]nea|item)s?\s+(?:anterior|seguinte|subsequente|precedente|"
                     r"antecedente|posterior|anteriores|seguintes|subsequentes|precedentes)", "remissão relativa"),
                    (r"\barts?\b\.?\s*\d", "artigo"), (r"\be\s+seguintes\b", "remissão aberta"),
                    (r"(?<![A-Za-zÀ-ú])anexos?\b", "anexo"), (r"\bitens?\s+[\dIVXLCDM]", "item"),
                    (r"\bpar[aá]grafos?\s+(?:primeiro|segundo|terceiro|quarto|quinto|sexto|s[eé]timo|oitavo|nono|d[eé]cimo)",
                     "parágrafo por extenso"),
                    (r"\bincisos?\s+(?:primeiro|segundo|terceiro|quarto|quinto|sexto|s[eé]timo|oitavo|nono|d[eé]cimo)",
                     "inciso por extenso"),
                    (r"(?:arts?\.?|§§?)\s*\d[\d.]*\s*[ºo°]?\s+at[ée]\s+(?:o\s+)?(?:art\.?\s*|§\s*)?\d", "faixa 'até'")):
        for m in re.finditer(rx, texto, re.I):
            if m.start() < lead_end or any(a <= m.start() < b for a, b in spans):
                continue
            if rot in ("§", "parágrafo único"):
                ch, _, _ = _antes(texto, m.start())
                if ch == "" or ch in _PONTUACAO_FRONTEIRA:
                    continue  # identificador do próprio dispositivo
            incertos.append(f"{rot}: ...{texto[max(0, m.start() - 20):m.end() + 25]}...")
    vistos, uniq = set(), []
    for r in refs:
        if r.get("incerta"):
            continue  # parcialmente interpretada: não impõe alvo superficial (já sinalizada em `incertos`)
        k = (r["obra"], r["chave"])
        if k not in vistos:
            vistos.add(k)
            uniq.append(r)
    return uniq, incertos


# --------------------------------------------------------------------------------------------------------------
# Validação
# --------------------------------------------------------------------------------------------------------------
class Resultado:
    def __init__(self):
        self.falhas, self.alertas, self.info, self.revisoes, self.incompleto = [], [], [], [], []
        self.extras = defaultdict(list)

    def falha(self, cid, msg):
        self.falhas.append((cid, msg))

    def alerta(self, cid, msg):
        if (cid, msg) not in self.alertas:
            self.alertas.append((cid, msg))

    def revisao(self, cid, cat, msg):
        """Juízo jurídico para a segunda camada (matriz, seção 7.1): linha própria, não reprova sozinha."""
        if (cid, cat, msg) not in self.revisoes:
            self.revisoes.append((cid, cat, msg))


def _data_valida(s):
    if not isinstance(s, str) or not DATA_RE.match(s):
        return None
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        return None


def _str_ok(v):
    return isinstance(v, str) and v.strip() != ""


def _sn(x):
    """Número de ato sem zeros à esquerda (comparação de `0100` com `100`)."""
    return re.sub(r"^0+(?=\d)", "", str(x).replace(".", ""))


class Contexto:
    def __init__(self, pasta, fontes_csv, res):
        self.pasta = Path(pasta)
        self.res = res
        self.fontes = {}
        if fontes_csv:
            with open(fontes_csv, encoding="utf-8-sig", newline="") as fh:
                for row in csv.DictReader(fh):
                    self.fontes.setdefault((row.get("sha256") or "").strip().lower(), []).append(row)
        self.tem_csv = bool(fontes_csv)
        self._cache = {}
        self._avisadas = set()

    def fonte(self, sha):
        """(Fonte|None, mensagem de erro|None, bytes)"""
        if sha in self._cache:
            return self._cache[sha]
        arqs = sorted(p for p in self.pasta.glob(f"{sha}.*") if p.is_file()) if isinstance(sha, str) and sha else []
        if not arqs:
            r = (None, "arquivo da evidência ausente", None)
        else:
            b = arqs[0].read_bytes()
            if hashlib.sha256(b).hexdigest() != sha:
                r = (None, "sha256 não confere com os bytes da evidência", b)
            else:
                try:
                    r = (carregar_fonte(b, sha), None, b)
                except ErroExtracao as e:
                    r = (None, str(e), b)
        self._cache[sha] = r
        return r


def validar_fonte_meta(cid, fo, ctx, rotulo="fonte_oficial"):
    """Esquema + host + hash + conferência com fontes.csv. Devolve Fonte ou None."""
    res = ctx.res
    if not isinstance(fo, dict):
        res.falha(cid, f"{rotulo} ausente ou não é objeto")
        return None
    ok = True
    for k in ("url", "sha256", "capturado_em", "orgao"):
        if not _str_ok(fo.get(k)):
            res.falha(cid, f"{rotulo}.{k} ausente, vazio ou não é texto")
            ok = False
    url = fo.get("url") if _str_ok(fo.get("url")) else None
    if url:
        pu = urlparse(url)
        host = (pu.hostname or "").lower()
        if pu.scheme not in ("http", "https") or host not in HOSTS_OFICIAIS:
            res.falha(cid, f"{rotulo}.url fora da allowlist de hosts oficiais: {url!r}")
            ok = False
        elif host == "www.planalto.gov.br":
            res.alerta(cid, f"{rotulo}.url do Planalto: só admitida no que o acervo congelado documenta (revisão humana)")
    ce = fo.get("capturado_em")
    if _str_ok(ce):
        try:
            datetime.datetime.strptime(ce, "%Y-%m-%dT%H:%M:%SZ")
            if not DATAHORA_RE.match(ce):
                raise ValueError
        except ValueError:
            res.falha(cid, f"{rotulo}.capturado_em não é data e hora válidas AAAA-MM-DDTHH:MM:SSZ: {ce!r}")
            ok = False
    sha = fo.get("sha256")
    if _str_ok(sha) and not SHA_RE.match(sha):
        res.falha(cid, f"{rotulo}.sha256 malformado: {sha!r}")
        return None
    if not ok or not sha:
        return None
    # fontes.csv
    if ctx.tem_csv:
        linhas = ctx.fontes.get(sha)
        if not linhas:
            res.falha(cid, f"{rotulo}.sha256 ausente de fontes.csv")
        else:
            lu = [l for l in linhas if (l.get("url") or "").strip() == url]
            if not lu:
                res.falha(cid, f"{rotulo}.url não consta em fontes.csv para este sha256")
            else:
                l = lu[0]
                if (l.get("capturado_em") or "").strip() != ce:
                    res.falha(cid, f"{rotulo}.capturado_em diverge de fontes.csv ({l.get('capturado_em')!r})")
                if (l.get("status") or "200").strip() not in ("200", ""):
                    res.falha(cid, f"fontes.csv registra status {l.get('status')!r} para a fonte")
    f, erro, b = ctx.fonte(sha)
    if erro and f is None:
        res.falha(cid, f"{rotulo}: {erro}")
        return None
    if ctx.tem_csv and ctx.fontes.get(sha) and b is not None:
        t = (ctx.fontes[sha][0].get("tamanho") or "").strip()
        if t.isdigit() and int(t) != len(b):
            res.falha(cid, f"{rotulo}: tamanho em fontes.csv ({t}) difere do arquivo ({len(b)})")
    if (f.removidas or f.repetidas) and sha not in ctx._avisadas:
        ctx._avisadas.add(sha)
        if f.removidas:
            res.alerta(cid, f"PDF {sha[:12]}: {f.removidas} linhas de cabeçalho/rodapé removidas por padrão positivo "
                            f"(furniture, numeração de página ou contador de página repetido na borda) para dar "
                            f"continuidade entre páginas")
        if f.repetidas:
            res.alerta(cid, f"PDF {sha[:12]}: linhas repetidas na borda de várias páginas e MANTIDAS (sem identificação "
                            f"positiva de cabeçalho; se atravessarem o recorte, ele reprova): {f.repetidas[:4]}")
    return f


def validar_esquema(c, res, ids_vistos):
    """Esquema da seção 6, com tipos validados ANTES de qualquer processamento. Devolve True se o caso pode seguir para as
    verificações documentais."""
    cid = c.get("id") if _str_ok(c.get("id")) else "<linha-sem-id>"
    ok = True
    for k in ("id", "conjunto", "capacidade", "familia_alteracao", "norma", "citacao", "caminho", "gabarito",
              "norma_grande"):
        if k not in c or c[k] is None or (isinstance(c[k], str) and not c[k].strip()):
            res.falha(cid, f"campo obrigatório ausente ou vazio: {k}")
            if k in ("id", "capacidade", "norma", "citacao", "gabarito"):  # sem eles não há o que conferir na fonte
                ok = False
    for k in ("id", "conjunto", "capacidade", "familia_alteracao", "citacao", "caminho", "familia_fundamento"):
        if c.get(k) is not None and not isinstance(c[k], str):
            res.falha(cid, f"{k} deve ser texto, não {type(c[k]).__name__}")
            if k in ("id", "capacidade", "citacao"):
                ok = False
    for k in c:
        if k not in CAMPOS_CASO:
            res.extras[f"caso.{k}"].append(cid)
    m = ID_RE.match(c["id"]) if isinstance(c.get("id"), str) else None
    if c.get("id") is not None and isinstance(c.get("id"), str) and not m:
        res.falha(cid, f"id fora do padrão L|R-<cap>-NNN: {c.get('id')!r}")
        ok = False
    if m:
        if c.get("id") in ids_vistos:
            res.falha(cid, "id repetido no conjunto")
        ids_vistos.add(c["id"])
        if c.get("capacidade") in CAPS and m.group(2) != c["capacidade"]:
            res.falha(cid, f"capacidade {c.get('capacidade')!r} incoerente com o id")
        conj = {"L": "desenvolvimento", "R": "reserva"}[m.group(1)]
        if c.get("conjunto") != conj:
            res.falha(cid, f"conjunto {c.get('conjunto')!r} incoerente com o id (esperado {conj!r})")
    if c.get("conjunto") not in (None, "desenvolvimento", "reserva") and isinstance(c.get("conjunto"), str):
        res.falha(cid, f"conjunto fora do enum: {c.get('conjunto')!r}")
    cap = c.get("capacidade")
    if isinstance(cap, str) and cap not in CAPS:
        res.falha(cid, f"capacidade fora do enum a..e: {cap!r}")
        ok = False
    elif not isinstance(cap, str):
        cap = None
    n = c.get("norma")
    if isinstance(n, dict):
        if n.get("especie") not in ESPECIES:
            res.falha(cid, f"norma.especie fora do enum: {n.get('especie')!r}")
            ok = False
        num = n.get("numero")
        if not (isinstance(num, str) and re.fullmatch(r"\d+(?:-\d+)?", num)):
            res.falha(cid, f"norma.numero deve ser string de dígitos: {num!r}")
            ok = False
        if not (isinstance(n.get("ano"), int) and not isinstance(n.get("ano"), bool) and 1800 <= n["ano"] <= 2100):
            res.falha(cid, f"norma.ano inválido: {n.get('ano')!r}")
            ok = False
    elif n is not None:
        res.falha(cid, "norma deve ser objeto {especie, numero, ano}")
        ok = False
    if c.get("norma_grande") is not None and not isinstance(c["norma_grande"], bool):
        res.falha(cid, "norma_grande deve ser booleano")
    fam = c.get("familia_alteracao")
    if isinstance(fam, str) and not FAMILIA_RE.match(fam):
        res.falha(cid, f"familia_alteracao fora do padrão (original ou identificador canônico de ato): {fam!r}")
    elif isinstance(fam, str) and fam != "original" and canon_norma(n if isinstance(n, dict) else {}) == canon_fam(fam):
        res.falha(cid, f"familia_alteracao {fam!r} é a da própria norma consultada (use 'original' ou o ato alterador)")
    for k in ("data", "data_mutante"):
        v = c.get(k)
        if v is not None and _data_valida(v) is None:
            res.falha(cid, f"{k} não é data ISO válida: {v!r}")
    if cap == "c" and c.get("data") is None:
        res.falha(cid, "(c) exige `data` (D)")
    if cap != "c" and c.get("data") is not None and cap in CAPS:
        res.alerta(cid, "`data` preenchida fora de (c): ignorada pela apuração")
    if c.get("data_mutante") is not None and cap not in ("b", "c"):
        res.falha(cid, "data_mutante só se aplica a (b) e (c)")
    if c.get("data_mutante") and c.get("data_mutante") == c.get("data"):
        res.falha(cid, "data_mutante igual a data: o mutante não difere do original")
    if c.get("trecho") is not None and not _str_ok(c["trecho"]):
        res.falha(cid, "trecho deve ser null ou texto não vazio")
    cam = c.get("caminho")
    if isinstance(cam, str) and cam.strip():
        pc = parse_caminho(cam)
        if pc is None:
            res.falha(cid, f"caminho incompleto ou inválido (hierarquia artigo, §, inciso, alínea; numerais válidos): {cam!r}")
        else:
            if isinstance(c.get("citacao"), str):
                msg = confere_citacao_caminho(c["citacao"], cam)
                if msg:
                    res.falha(cid, msg)
            if cap == "d" and pc["anexo"] is None:
                res.falha(cid, f"(d) exige caminho iniciado por Anexo: {cam!r}")
            if cap != "d" and pc["anexo"] is not None:
                res.falha(cid, f"caminho com Anexo fora de (d): {cam!r}")
    elif isinstance(c.get("citacao"), str):
        pcit = parse_citacao(c["citacao"])
        if pcit["art"] is None and not pcit["anexo"]:
            res.falha(cid, f"citação sem dispositivo (artigo ou anexo): {c['citacao']!r}")
    g = c.get("gabarito")
    if isinstance(g, dict):
        for k in g:
            if k not in CAMPOS_GABARITO:
                res.extras[f"gabarito.{k}"].append(cid)
        tipo = g.get("tipo")
        if tipo not in {t for ts in TIPOS_POR_CAP.values() for t in ts}:
            res.falha(cid, f"gabarito.tipo fora do enum: {tipo!r}")
            ok = False
        elif cap in CAPS and tipo not in TIPOS_POR_CAP[cap]:
            res.falha(cid, f"gabarito.tipo {tipo!r} incompatível com a capacidade ({cap})")
            ok = False
        for k, t in (("motivos_aceitos", list), ("cadeia", list), ("alvos", list), ("alvos_equivalentes", dict),
                     ("fontes_consultadas", list), ("redacao_alternativa", dict), ("ultima_versao_anterior", dict)):
            if k in g and g[k] is not None and not isinstance(g[k], t):
                res.falha(cid, f"gabarito.{k} deve ser {t.__name__}")
                ok = False
        for k in ("texto", "fundamento_data", "condicao_inexistencia"):
            if g.get(k) is not None and not isinstance(g[k], str):
                res.falha(cid, f"gabarito.{k} deve ser texto")
                ok = False
        if not _str_ok(g.get("fundamento_data")):
            res.falha(cid, "gabarito.fundamento_data ausente ou vazio")
        fo = g.get("fonte_oficial")
        if isinstance(fo, dict):
            if not _str_ok(fo.get("ato_no_documento")):
                res.falha(cid, "fonte_oficial.ato_no_documento ausente ou vazio")
            pg = fo.get("pagina")
            if not (isinstance(pg, int) and not isinstance(pg, bool) and pg >= 1):
                res.falha(cid, f"fonte_oficial.pagina deve ser inteiro >= 1: {pg!r}")
        elif "fonte_oficial" in g:
            res.falha(cid, "fonte_oficial deve ser objeto")
            ok = False
    elif g is not None:
        res.falha(cid, "gabarito deve ser objeto")
        ok = False
    return ok


def _localizar(clean, t):
    out, i = [], clean.find(t)
    while i >= 0:
        out.append(i)
        i = clean.find(t, i + 1)
    return out


def _classe_depois(f, e):
    """O que a fonte traz logo depois da posição e: pelo marcador estrutural que começa ali (se só há espaço até ele), ou
    pela leitura do texto seguinte (rubrica reconhecível, divisão, fim, desconhecido)."""
    M = f.marcadores()
    for mk in M:
        if mk["pos"] >= e:
            if not f.clean[e:mk["pos"]].strip(' "'):
                return {"art": "art", "par": "par", "inc": "inc", "ali": "ali", "div": "div", "ato": "ato",
                        "anexo": "anexo", "fim": "fim"}[mk["tipo"]]
            break
    return classificar_proximo(f.clean[e:e + 240])


def _esperado_ato(c, compilada):
    n = c["norma"]
    norma_t = (n["especie"], str(n["numero"]), n["ano"])
    fam = c.get("familia_alteracao")
    if compilada or not fam or fam == "original":
        return norma_t
    m = re.match(r"^(lei-complementar|lei|decreto-lei|decreto|mp|emenda-constitucional|resolucao-cvm|resolucao-cmn)-"
                 r"(\d+(?:-\d+)?)-(\d{4})$", fam)
    if not m:
        return norma_t
    return PREFIXO_ESPECIE[m.group(1)], m.group(2), int(m.group(3))


def _cabecalho_confere(h, exp):
    return h is not None and (h["esp"], _sn(h["num"]), h["ano"]) == (exp[0], _sn(exp[1]), exp[2])


def _eh_compilada(url, f, s, e):
    u = (url or "").lower()
    if "publicacaooriginal" in u or "publicacao-original" in u:
        return False
    if re.search(r"atualizad|compilad|texto-atualizado|normaatualizada", u):
        return True
    return any(s < p <= e for p, _ in f.anots)


_INT_ART = re.compile(r'(?<![A-Za-zÀ-ú"“])Art\.?\s*\d')
_INT_PAR = re.compile(r"§\s*\d|Par[aá]grafo\s+[uú]nico", re.I)
_INT_INC = re.compile(r"(?<![A-Za-zÀ-ú])[IVXLCDM]+\s*[-–—]\s")
_QUALIFICADOR = {"inciso", "incisos", "alínea", "alíneas", "parágrafo", "paragrafo", "caput", "artigo", "artigos", "art",
                 "arts", "§", "§§"}


_RX_REMISSAO_ADIANTE = re.compile(r"\s*(?:d?[eao]s?t[ae]s?\s|d[aeo]s?\s+(?:lei|decreto|medida|emenda|c[óo]digo|constitui)|"
                                  r"d?[eo]ste\s+artigo)", re.I)
# palavra de remissão FORTE antes do `Art.`; as fracas (conectivos e artigos) só valem com `desta Lei`/`deste artigo` depois
_PALAVRAS_FRACAS = {"e", "ou", "a", "o", "os", "as", "de", "em", "com", "por", "para", "art", "arts"}
_PALAVRAS_REMISSAO_ART = (_PALAVRAS_DE_REMISSAO - _PALAVRAS_FRACAS) | {
    "observado", "observados", "observada", "observadas", "termos", "disposto", "dispõe", "combinado", "cumulado", "inciso",
    "alínea", "parágrafo"}


def _invasao_interior(nivel, t, duvidas=None):
    """Marcador de dispositivo do mesmo nível ou superior no INTERIOR do recorte (sem depender de pontuação antes dele):
    `Art.` capitalizado; `§`/parágrafo único; inciso em romano com travessão. Remissão (precedida de preposição, vírgula ou
    qualificador) não conta. `Art.` capitalizado que se lê como remissão (palavra de remissão antes, ou `desta Lei`,
    `deste artigo` depois) não reprova: entra em `duvidas` (REVISAO_HUMANA)."""
    ordem = {"art": ("art",), "caput": ("art", "par"), "par": ("art", "par"), "inc": ("art", "par", "inc"),
             "ali": ("art", "par", "inc")}
    tipos = ordem.get(nivel)
    if not tipos:
        return None
    rxs = {"art": _INT_ART, "par": _INT_PAR, "inc": _INT_INC}
    for tp in tipos:
        for m in rxs[tp].finditer(t):
            if m.start() == 0:
                continue
            ch, palavra, _ = _antes(t, m.start())
            w = palavra.lower().strip('",.;:()')
            if ch == "," or (tp != "art" and w in _PALAVRAS_DE_REMISSAO) or w in _QUALIFICADOR or ch in "(§":
                continue
            if tp == "art" and duvidas is not None and (
                    w in _PALAVRAS_REMISSAO_ART or _RX_REMISSAO_ADIANTE.match(t, m.end() + _numero_art_len(t, m.end()))):
                duvidas.append(t[max(0, m.start() - 15):m.end() + 15])
                continue
            if tp == "inc" and ROMANO_RE.match(m.group(0).split()[0].rstrip("-–—")) is None:
                continue
            return t[max(0, m.start() - 15):m.end() + 15]
    return None


def _numero_art_len(t, i):
    """Tamanho do número do artigo (e de seu ordinal/sufixo) que começa em `i`, para ler o que vem depois da remissão."""
    m = re.compile(r"[\d.]*\s*[ºo°]?(?:\s*-\s*[A-Z](?![a-z]))?").match(t, i)
    return (m.end() - i) if m else 0


def _rubrica_no_fim(t):
    """Cauda do recorte que é título (rubrica) e não texto normativo: depois do último ponto de período, um sintagma curto
    sem pontuação final, em Title Case/caixa alta/`Da...`, e o recorte não termina em pontuação."""
    if re.search(r'[.;:!?")]\s*$', t):
        return None
    m = list(re.finditer(r"[.;:!?]\s+", t))
    cauda = t[m[-1].end():] if m else ""
    if cauda and len(cauda.split()) <= 14 and _eh_rubrica(cauda) and not re.match(r"[a-zà-ú]", cauda):
        return cauda
    return None


def _avaliar_ocorrencia(c, pc, f, t, s, cands, esperado_ato, revisoes):
    """Verifica o recorte `t` na posição `s`: posição estrutural, identificador, limite, ato. Devolve (falhas, cand)."""
    falhas = []
    nivel = pc["nivel"]
    e = s + len(t)
    if not cands:
        return [f"dispositivo {c['caminho']!r} não localizado estruturalmente na fonte (cadeia de pertencimento: "
                f"anexo, artigo, parágrafo, inciso, alínea)"], None
    if nivel == "tabela":
        cand = next((x for x in cands if x["start"] <= s and e <= x["end"]), None)
        if cand is None:
            return ["tabela: o recorte não está dentro do anexo declarado"], None
        # limite decidível: a tabela é o corpo do anexo, do fim da rubrica (e do título, se houver) até o fim do anexo; recorte
        # que começa ou termina no meio do anexo tem limite inconclusivo e reprova
        antes_t = f.clean[cand["anexo"]["fim"]:s].strip(' "') if cand.get("anexo") else None
        depois_t = f.clean[e:cand["end"]].strip(' "')
        if antes_t is None or (antes_t and not _eh_rubrica(antes_t)):
            falhas.append(f"tabela: o início do recorte não é o início do corpo do anexo (a fonte traz antes "
                          f"{antes_t[:60] if antes_t else antes_t!r}): limite inconclusivo")
        if depois_t:
            falhas.append(f"tabela: o recorte termina antes do fim do anexo (a fonte segue com {depois_t[:60]!r}): "
                          f"limite inconclusivo")
        revisoes.append(("(v)", "recorte declarado de tabela: confirme que o corpo do anexo é a tabela citada"))
    else:
        cand = next((x for x in cands if x["start"] == s), None)
        if cand is None:
            return [f"o recorte começa em posição que não é a do dispositivo {c['caminho']!r} na estrutura da fonte "
                    f"(início do recorte: {t[:40]!r})"], None
        rx = re_inicio_dispositivo(pc)
        if rx and not rx.match(t):
            falhas.append(f"recorte não começa pelo identificador completo do dispositivo {c['caminho']!r}: {t[:40]!r}")
    if nivel != "tabela":
        cls = _classe_depois(f, e)
        depois = f.clean[e:e + 240]
        if cls == "desconhecido":
            falhas.append(f"limite desconhecido: depois do recorte a fonte segue com {depois.strip()[:60]!r} "
                          f"(nem dispositivo, nem divisão, nem rubrica reconhecível)")
        elif nivel == "anexo":
            if cls not in ("ato", "fim", "anexo"):
                falhas.append(f"anexo incompleto: depois do recorte a fonte continua no anexo ({cls}): "
                              f"{depois.strip()[:60]!r}")
        elif cls in ("par", "inc", "ali", "item"):
            nivel_prox = {"par": 2, "inc": 3, "ali": 4, "item": 5}[cls]
            nv = _NIVEL.get(nivel, 1)
            if nivel == "caput" and cls in ("inc", "ali", "item") and t.rstrip().endswith(":"):
                falhas.append(f"caput incompleto: termina em dois-pontos e a fonte continua com {cls} que o completam: "
                              f"{depois.strip()[:60]!r}")
            elif nivel == "caput":
                revisoes.append(("(v)", "caput isolado: confirme se o caput inclui os incisos que seguem"))
            elif nivel_prox > nv:
                falhas.append(f"dispositivo incompleto: a fonte continua com {cls} do mesmo dispositivo: "
                              f"{depois.strip()[:60]!r}")
        # o término do recorte não ultrapassa a região estrutural do dispositivo (irmão, rubrica ou divisão seguinte)
        if cand is not None and e > cand["end"] and f.clean[cand["end"]:e].strip(' "'):
            falhas.append(f"o recorte ultrapassa o dispositivo {c['caminho']!r}: a região estrutural termina antes do fim "
                          f"do recorte, que avança sobre {f.clean[cand['end']:e].strip()[:60]!r}")
        if nivel != "anexo":
            duvidas = []
            inv = _invasao_interior(nivel, t, duvidas)
            for d in duvidas:
                revisoes.append(("(v)", f"`Art.` capitalizado no interior do recorte lido como remissão ({d!r}): confirme "
                                        f"que não é o início de outro dispositivo"))
            if inv:
                falhas.append(f"o recorte contém, no interior, o início de outro dispositivo do mesmo nível ou superior "
                              f"({inv!r}): invade o dispositivo seguinte")
            fim_rub = _rubrica_no_fim(t)
            if fim_rub:
                falhas.append(f"o recorte termina com possível rubrica/título do dispositivo seguinte: {fim_rub!r}")
        # invasão do dispositivo/divisão seguinte dentro do recorte (um anexo inteiro tem vários artigos por natureza)
        if nivel != "anexo":
            if re.search(r"[.;:!?] Art\.\s*\d", t):
                falhas.append("recorte contém outro dispositivo ('Art.' após ponto): invade o dispositivo seguinte")
            if re.search(r"(?:CAP[IÍ]TULO|SE[CÇ][AÃ]O|T[IÍ]TULO|LIVRO|SUBSE[CÇ][AÃ]O)\s+[IVXLCDM\d]+(?:\s*[-–—]?\s*[^.;:]*)?$", t):
                falhas.append("recorte termina com divisão (capítulo/seção/título) do dispositivo seguinte")
            if re.search(r"(?:Art\.?\s*[\d.]+o?(?:-[A-Z])?\.?|§\s*\d+o?\.?|Par[aá]grafo [uú]nico\.?)$", t):
                falhas.append("recorte termina com rótulo do dispositivo seguinte")
    if re.search(r"(?:^|[.;:!?\"] )(?:%s)\s+N[o°]" % _ESP_ALT, t) and not t.startswith(("LEI", "DECRETO")):
        falhas.append("recorte contém cabeçalho de outro ato")
    h = cand["ato"]
    if h is None:
        falhas.append("ato do recorte não identificável no documento (nenhum cabeçalho de ato antes do recorte)")
    elif esperado_ato and not _cabecalho_confere(h, esperado_ato):
        falhas.append(f"o cabeçalho de ato mais próximo antes do recorte é {h['txt']!r}, que não corresponde ao ato "
                      f"esperado ({esperado_ato[0]} {esperado_ato[1]}/{esperado_ato[2]})")
    return falhas, cand


def validar_posicao(c, g, f, fo, ctx, res, s, e, cand, compilada, esp):
    """Controles de identidade e posição, comuns a todos os tipos de gabarito (com ou sem texto): ato declarado, relação
    entre ato alterador e norma consultada, publicação em (a), página e família."""
    cid = c["id"]
    cap = c["capacidade"]
    n = c["norma"]
    fam = c.get("familia_alteracao")
    h = cand["ato"] if cand else None
    decl = parse_ato(fo.get("ato_no_documento") or "")
    if not _str_ok(fo.get("ato_no_documento")):
        pass  # já é FALHA de esquema
    elif decl is None:
        res.falha(cid, f"fonte_oficial.ato_no_documento não identifica um ato: {fo.get('ato_no_documento')!r}")
    elif (decl[0], _sn(decl[1])) != (esp[0], _sn(esp[1])) or (decl[2] and decl[2] != esp[2]):
        res.falha(cid, f"ato_no_documento {fo.get('ato_no_documento')!r} não corresponde ao ato esperado "
                       f"({esp[0]} {esp[1]}/{esp[2]})")
    elif h is not None and (h["esp"], _sn(h["num"]), h["ano"]) != (decl[0], _sn(decl[1]), decl[2] or h["ano"]):
        res.falha(cid, f"ato_no_documento {fo.get('ato_no_documento')!r} difere do cabeçalho mais próximo do recorte "
                       f"({h['txt']!r})")
    if cap == "a" and compilada:
        res.falha(cid, "(a) exige a publicação (do ato original ou do ato que incluiu o dispositivo), mas a fonte é texto "
                       "compilado/atualizado, que não é prova da primeira publicação")
    if (not compilada and isinstance(fam, str) and fam != "original" and h is not None
            and canon_norma(n) not in referencias_norma(f.clean[h["pos"]:s])):
        res.falha(cid, f"publicação do ato alterador {fam!r}: o texto do ato, antes do dispositivo, não menciona a norma "
                       f"consultada ({canon_norma(n)}): não há relação documental entre ato alterador, norma alterada e "
                       f"dispositivo")
    pg = fo.get("pagina")
    if f.tipo == "pdf" and isinstance(pg, int) and f.pagina_de(s) != pg:
        res.falha(cid, f"fonte_oficial.pagina={pg}, mas o recorte começa na página {f.pagina_de(s)} do PDF")
    checar_familia(c, f, s, e, compilada, fo, ctx, res)
    for seg in f.classe_rasura:
        i = f.clean.find(seg)
        while i >= 0 and not (i < e and i + len(seg) > s):
            i = f.clean.find(seg, i + 1)
        if i >= 0:
            res.revisao(cid, "(i)", f"o recorte contém texto de elemento com classe de rasura conhecida ({seg[:40]!r}): "
                                    f"folha de estilo e cascata CSS não são interpretadas; confirme que o texto não é "
                                    f"redação riscada e que vale em D")
            break
    for motivo, _ in f.alternativas:
        res.revisao(cid, "(v)", f"extração com leitura alternativa ({motivo}): confirme na evidência gravada que a leitura "
                                f"usada é a correta para o recorte")
    if isinstance(fam, str) and fam == "original":
        res.revisao(cid, "(iv)", "família 'original': a ausência de anotação reconhecida não prova que a redação seja a "
                                 "original; confirme que nenhum ato posterior deu a redação do gabarito")
    elif isinstance(fam, str):
        res.revisao(cid, "(iv)", f"família {fam!r}: confirme que é o evento normativo que deu a redação do gabarito")
    return {"s": s, "e": e, "compilada": compilada, "ato": h, "cand": cand,
            "anots": [txt for p, txt in f.anots if s < p <= e]}


def _cands_com_variante(c, f, pc, res):
    """Candidatos estruturais do dispositivo. Se a citação é de anexo e a rubrica de anexo em caixa mista não é reconhecida
    porque o título seguinte começa por minúscula, a leitura pela posição documental (`variante_lax`) vale, com
    REVISAO_HUMANA, em vez de FALHA. Devolve (candidatos, fonte usada)."""
    cands = resolver_dispositivo(f, pc)
    if cands or pc is None or pc.get("anexo") is None:
        return cands, f
    fl = f.variante_lax()
    c2 = resolver_dispositivo(fl, pc)
    if c2:
        res.revisao(c["id"], "(v)", "rubrica de anexo em caixa mista seguida de título que começa por minúscula: o anexo foi "
                                    "reconhecido pela posição; confirme que a rubrica é a do anexo declarado")
        return c2, fl
    return cands, f


def validar_texto(c, g, f, fo, ctx, res, t_bruto):
    """Recorte do texto do gabarito na fonte (classe: recorte + fonte + família + anexo)."""
    cid = c["id"]
    cap = c["capacidade"]
    t = norm(t_bruto)
    revisoes = []
    # gabarito não pode conter anotação editorial nem aspas do comando alterador
    if tem_anotacao_editorial(t):
        res.falha(cid, "gabarito contém anotação editorial de alteração (só a fonte pode tê-la)")
    if t.startswith('"'):
        res.falha(cid, "gabarito começa por aspas do comando alterador")
    if t.count('"') % 2 == 1:
        res.falha(cid, "aspas desbalanceadas no gabarito (aspa do comando alterador?)")
    # termos suspeitos e tamanho: alerta contextual
    for termo in ("WhatsApp", "0800", "Atendimento", "Documento assinado", "ICP-Brasil", "Diário Oficial", "http://",
                  "https://", "www."):
        i = t.find(termo)
        if i >= 0:
            res.alerta(cid, f"termo suspeito {termo!r} no gabarito: ...{t[max(0, i - 25):i + 35]!r}")
    for m in re.finditer(r"\bvide\b", t, re.I):
        res.alerta(cid, f"'vide' no gabarito (pode ser remissão normativa legítima): ...{t[max(0, m.start() - 25):m.start() + 35]!r}")
    pc = parse_caminho(c["caminho"])
    anexo_tabela = bool(pc and pc["nivel"] in ("anexo", "tabela"))
    if len(t) < 20:
        res.alerta(cid, f"gabarito curto ({len(t)} caracteres): confirme que é o dispositivo inteiro")
    if len(t) > (40000 if cap == "d" or anexo_tabela else 8000):
        res.alerta(cid, f"gabarito longo ({len(t)} caracteres): confirme o recorte")
    if not re.search(r'[.;:!?")]$', t):
        res.alerta(cid, f"gabarito não termina em pontuação final: ...{t[-40:]!r}")
    if t.endswith(":"):
        res.alerta(cid, "gabarito termina em dois-pontos (incisos podem faltar; o limite é conferido na fonte)")
    ocs = _localizar(f.clean, t)
    if not ocs:
        for motivo, fa in f.alternativas:
            oa = _localizar(fa.clean, t)
            if oa:
                f, ocs = fa, oa
                res.revisao(cid, "(v)", f"o gabarito só é trecho contínuo da leitura alternativa da extração ({motivo}): "
                                        f"confirme na evidência qual leitura é a correta")
                break
    if not ocs:
        for p, rs in f.risc:
            if rs and rs in t:
                res.falha(cid, "gabarito contém texto riscado (redação anterior) da fonte")
                return None
        res.falha(cid, f"gabarito não é trecho contínuo da fonte (após a normalização da seção 7): início {t[:50]!r}")
        return None
    cands, f = _cands_com_variante(c, f, pc, res)
    # várias ocorrências: vale a primeira que passa em todas as checagens; senão, as falhas da primeira
    escolhida, falhas_primeira = None, None
    for s in ocs:
        compilada = _eh_compilada(fo.get("url"), f, s, s + len(t))
        esp = _esperado_ato(c, compilada)
        rev = []
        falhas, cand = _avaliar_ocorrencia(c, pc, f, t, s, cands, esp, rev)
        if not falhas:
            escolhida = (s, compilada, cand, esp, rev)
            falhas_primeira = None
            break
        if falhas_primeira is None:
            falhas_primeira = falhas
            escolhida = (s, compilada, cand, esp, rev)
    if falhas_primeira:
        for m in falhas_primeira:
            res.falha(cid, m)
    s, compilada, cand, esp, rev = escolhida
    for cat, msg in rev:
        res.revisao(cid, cat, msg)
    return validar_posicao(c, g, f, fo, ctx, res, s, s + len(t), cand, compilada, esp)


def validar_posicao_sem_texto(c, g, f, fo, ctx, res):
    """Casos sem texto (revogado_vigente, nao_verificado_para_D, nao_existia_em_D): o dispositivo é localizado
    estruturalmente na fonte oficial e passa pelos mesmos controles de ato, relação, página e família."""
    cid = c["id"]
    pc = parse_caminho(c["caminho"])
    cands, f = _cands_com_variante(c, f, pc, res)
    if not cands:
        res.falha(cid, f"dispositivo {c['caminho']!r} não localizado na fonte oficial (cadeia de pertencimento)")
        return None
    escolha = None
    for cand in cands:
        compilada = _eh_compilada(fo.get("url"), f, cand["start"], cand["end"])
        esp = _esperado_ato(c, compilada)
        if _cabecalho_confere(cand["ato"], esp):
            escolha = (cand, compilada, esp)
            break
        if escolha is None:
            escolha = (cand, compilada, esp)
    cand, compilada, esp = escolha
    if not _cabecalho_confere(cand["ato"], esp):
        h = cand["ato"]
        res.falha(cid, f"o cabeçalho de ato do dispositivo localizado é {h['txt'] if h else None!r}, que não corresponde "
                       f"ao ato esperado ({esp[0]} {esp[1]}/{esp[2]})")
    return validar_posicao(c, g, f, fo, ctx, res, cand["start"], cand["end"], cand, compilada, esp)


def checar_familia(c, f, s, e, compilada, fo, ctx, res):
    cid = c["id"]
    fam = c.get("familia_alteracao")
    if not isinstance(fam, str) or not FAMILIA_RE.match(fam):
        return
    if compilada:
        if not _str_ok(c.get("familia_fundamento")):
            res.falha(cid, "fonte compilada: familia_fundamento ausente")
        anots = [txt for p, txt in f.anots if s < p <= e]
        # só anotações que DÃO redação definem o evento (Redação dada, Incluído, Acrescido); Vide, Vigência, Produção de
        # efeitos e Vetado não; Revogado só no caso de revogação
        dao = [a for a in anots if _DA_REDACAO.search(a)]
        if c["gabarito"].get("tipo") == "revogado_vigente":
            dao += [a for a in anots if re.match(r"\(\s*Revogad", a, re.I)]
        ids = atos_das_anotacoes(dao)
        if fam == "original":
            if ids:
                res.falha(cid, f"família 'original', mas a anotação editorial do dispositivo nomeia {sorted(ids)}")
        else:
            if not ids:
                res.falha(cid, f"família {fam!r}, mas a fonte compilada não traz anotação editorial do dispositivo "
                               "que dê a redação e nomeie o ato (Redação dada/Incluído/Acrescido)")
            elif canon_fam(fam) not in ids:
                mp = re.match(r"^mp-(\d+)(?:-\d+)?-\d{4}$", canon_fam(fam))
                texto_ref = " ".join(anots) + " " + f.clean[e:e + 400]
                if mp and re.search(rf"Medida\s+Provis[óo]ria\s+n[ºo°.]*\s*{mp.group(1)}\b", texto_ref, re.I):
                    # a anotação nomeia a lei de conversão e a própria fonte liga a lei à MP: família = a MP
                    res.revisao(cid, "(iv)", f"família {fam!r} é medida provisória e a anotação nomeia a lei de conversão "
                                             f"({sorted(ids)}): confirme que a redação de D é a da MP, não a da lei")
                else:
                    res.falha(cid, f"família {fam!r} não consta das anotações do dispositivo que dão a redação "
                                   f"(nomeiam {sorted(ids)})")
        if len(ids) > 1:
            res.revisao(cid, "(iv)", f"o dispositivo tem redações de mais de um ato ({sorted(ids)}): confirme o evento "
                                     f"que dá a redação do gabarito")


def _fmt_chave(k):
    anexo, art, partes = k
    nomes = {"par": "§", "inc": "inciso", "ali": "alínea", "caput": "caput", "tab": "tabela"}
    s = (f"Anexo {anexo}" + (", " if art else "")) if anexo else ""
    s += f"art. {art}" if art else ""
    for tp, v in partes:
        s += ", parágrafo único" if (tp, v) == ("par", "unico") else (", caput" if tp == "caput" else f", {nomes[tp]} {v}")
    return s


def _parse_obra_caminho(s):
    """'Lei 6.404/1976, art. 4º, § 4º' -> (obra canônica, chave do caminho) ou None."""
    if not isinstance(s, str):
        return None
    m = re.search(r",\s*(art(?:igo)?\.?\s.*)$", s, re.I)
    if not m:
        return None
    ob = canon_obra(s[:m.start()])
    pc = parse_caminho(m.group(1))
    if ob is None or pc is None:
        return None
    return ob, chave_caminho(pc)


def _valida_alvos(c, g, texto, res):
    cid = c["id"]
    alvos = g.get("alvos")
    if not isinstance(alvos, list) or not alvos:
        res.falha(cid, "(e): `alvos` ausente ou vazio")
        return
    host = canon_norma(c["norma"])
    pcx = parse_caminho(c["caminho"])
    art_proprio = (f"{pcx['art']}{'-' + pcx['suf'] if pcx['suf'] else ''}"
                   if pcx and pcx["art"] and pcx["anexo"] is None else None)
    chaves = {}
    for a in alvos:
        if not isinstance(a, dict) or not _str_ok(a.get("obra")) or not _str_ok(a.get("caminho")):
            res.falha(cid, f"(e): alvo sem obra ou caminho: {a!r}")
            continue
        ob = canon_obra(a["obra"])
        if ob is None:
            res.falha(cid, f"(e): obra do alvo não reconhecida: {a['obra']!r}")
            continue
        pc = parse_caminho(a["caminho"])
        if pc is None:
            res.falha(cid, f"(e): caminho do alvo incompleto ou inválido: {a['caminho']!r}")
            continue
        k = (ob, chave_caminho(pc))
        if k in chaves:
            res.falha(cid, f"(e): alvo repetido: {a!r}")
        chaves[k] = a
    refs, incertos = extrair_remissoes(norm(texto), host, art_proprio)
    do_texto = {}
    for r in refs:
        do_texto.setdefault((r["obra"], r["chave"]), r)
    for k in do_texto:
        if k not in chaves:
            res.falha(cid, f"(e): remissão expressa do texto ausente de `alvos`: {k[0]} {_fmt_chave(k[1])}")
    for k, a in chaves.items():
        if k not in do_texto:
            if k[1][0] is not None:  # alvo de anexo: o parser não resolve remissão a anexo; a lista é da segunda camada
                res.revisao(cid, "(ii)", f"alvo de anexo ({a!r}) não resolvido pelo parser: confirme que aparece como "
                                         f"remissão expressa no texto e que `alvos` é a lista completa")
            elif incertos:
                res.revisao(cid, "(ii)", f"alvo não reconhecido pelo parser, com construção de remissão não resolvida no "
                                         f"texto: {a!r}")
            else:
                res.falha(cid, f"(e): alvo que não aparece como remissão expressa no texto do gabarito: {a!r}")
    for inc in incertos:
        res.revisao(cid, "(ii)", f"construção de remissão que o parser não resolve ({inc[:90]}): confirme que `alvos` é a "
                                 f"lista completa")
    # alvos_equivalentes: só formas canônicas do MESMO alvo (mesma obra, mesmo caminho, outra grafia)
    eq = g.get("alvos_equivalentes") or {}
    for chave, vals in eq.items():
        ok_k = _parse_obra_caminho(chave)
        if ok_k is None or ok_k not in chaves:
            res.falha(cid, f"(e): alvos_equivalentes referencia alvo inexistente: {chave!r}")
        if not isinstance(vals, list) or not vals:
            res.falha(cid, f"(e): alvos_equivalentes[{chave!r}] deve ser lista não vazia")
            continue
        for v in vals:
            pv = _parse_obra_caminho(v)
            if pv is None:
                res.falha(cid, f"(e): equivalente malformado em alvos_equivalentes[{chave!r}]: {v!r}")
            elif ok_k is not None and pv != ok_k:
                res.falha(cid, f"(e): equivalente {v!r} é alvo DISTINTO de {chave!r} (obra ou caminho diferentes): "
                               f"equivalente só pode ser outra grafia do mesmo alvo")


def _fontes_do_caso(f, consultadas):
    return [f] + [x for x in consultadas if x is not None]


def _regioes(c, fontes):
    """[(fonte, start, end)] dos candidatos estruturais do dispositivo do caso em cada fonte."""
    pc = parse_caminho(c["caminho"])
    out = []
    for fx in fontes:
        if fx is None or pc is None:
            continue
        for cand in resolver_dispositivo(fx, pc):
            out.append((fx, cand["start"], cand["end"]))
    return out


def _anots_regioes(regs):
    return [txt for fx, a, b in regs for p, txt in fx.anots if a < p <= b]


def _intervalo_contem(rng, d):
    """`d` cai no intervalo de datas documentado do ato, com a folga de publicação (a versão oficial é a do Diário
    Oficial, que sai até 45 dias depois da data do ato)."""
    return rng is not None and rng[0] <= d <= rng[1] + datetime.timedelta(days=45)


def checa_data_mutante(c, g, fontes):
    """Mensagem de invalidade da data_mutante, ou None. A data só é válida se cair no intervalo de OUTRA redação
    documentada (`gabarito.redacao_alternativa`: ato, inicio, fim, fundamento) que não contenha D, ou for anterior à data
    da obra demonstrada no cabeçalho de uma fonte."""
    dm = _data_valida(c.get("data_mutante"))
    if dm is None:
        return None
    D = _data_valida(c.get("data"))
    n = c["norma"]
    anots = [txt for fx in fontes if fx is not None for p, txt in fx.anots]
    dts = datas_de_atos(fontes, anots)
    alt = g.get("redacao_alternativa")
    if alt is None:
        d_obra = dts.get(canon_norma(n))
        if d_obra is None:
            return ("data_mutante sem redação alternativa documentada (`redacao_alternativa`) e a data da obra não está "
                    "demonstrada no cabeçalho de nenhuma fonte")
        if not dm < d_obra[0]:
            return (f"data_mutante ({dm}) não é anterior à obra ({d_obra[0]}) e o caso não documenta outra redação "
                    f"(`redacao_alternativa`) vigente nessa data: o mutante não é inválido por construção")
        return None
    ev_d = canon_norma(n) if c.get("familia_alteracao") == "original" else canon_fam(c.get("familia_alteracao"))
    ato = alt.get("ato")
    ini, fim = _data_valida(alt.get("inicio")), (None if alt.get("fim") is None else _data_valida(alt.get("fim")))
    if not (_str_ok(ato) and (ato == "original" or FAMILIA_RE.match(ato)) and ini and _str_ok(alt.get("fundamento"))
            and (alt.get("fim") is None or fim)):
        return "redacao_alternativa malformada (ato, inicio, fim, fundamento)"
    ev_a = canon_norma(n) if ato == "original" else canon_fam(ato)
    if ev_a == ev_d:
        return "redacao_alternativa é o mesmo evento da redação de D"
    if not _intervalo_contem(dts.get(ev_a), ini):
        return f"redacao_alternativa: a data de início {ini} não confere com a data documentada do ato {ev_a}"
    if fim is not None and fim < ini:
        return "redacao_alternativa: fim anterior ao início"
    dentro = lambda d: ini <= d and (fim is None or d <= fim)  # noqa: E731
    if not dentro(dm):
        return f"data_mutante ({dm}) fora do intervalo da redação alternativa ({ini} a {fim or 'hoje'})"
    if D is not None and dentro(D):
        return f"D ({D}) está dentro do intervalo da redação alternativa: não é outra redação"
    return _evidencia_alternativa(c, g, alt, ev_a, fontes)


def _evidencia_alternativa(c, g, alt, ev_a, fontes):
    """A redação alternativa tem de ser do PRÓPRIO dispositivo da mesma norma: `redacao_alternativa.texto` (texto integral
    da outra redação, distinto do gabarito) tem de constar, na região estrutural do dispositivo do caso numa fonte do
    caso cujo ato é a norma consultada, ao lado de anotação que nomeie o ato alternativo (ou, sendo a alternativa a
    redação original, sem anotação de outro ato ou riscada). Anotação de outro dispositivo não documenta nada."""
    texto_alt = norm(alt.get("texto")) if _str_ok(alt.get("texto")) else ""
    if not texto_alt:
        return ("redacao_alternativa sem `texto`: a outra redação do próprio dispositivo tem de ser apresentada "
                "(texto integral, distinto do gabarito)")
    base = norm(g.get("texto") or c.get("trecho") or "")
    if texto_alt == base:
        return "redacao_alternativa.texto é igual ao texto do gabarito: não é outra redação"
    pc = parse_caminho(c.get("caminho"))
    if pc is None:
        return "redacao_alternativa: caminho do caso inválido"
    n = c["norma"]
    norma_t = (n["especie"], str(n["numero"]), n["ano"])
    corpo = norm(re.sub(_RX_LEAD, "", texto_alt, count=1)) or texto_alt
    achou = False
    for fx in fontes:
        if fx is None:
            continue
        for cand in resolver_dispositivo(fx, pc):
            if not _cabecalho_confere(cand["ato"], norma_t):
                continue
            a, b = cand["start"], cand["end"]
            regiao = fx.clean[a:b]
            riscados = " ".join(t for p, t in fx.risc if a <= p <= b and t)
            dao = [txt for p, txt in fx.anots if a < p <= b and _DA_REDACAO.search(txt)]
            ids = atos_das_anotacoes(dao)
            no_texto = texto_alt in regiao or corpo in riscados or texto_alt in riscados
            if not no_texto:
                continue
            if ev_a in ids or (ev_a == canon_norma(n) and (riscados or not ids)):
                achou = True
    if not achou:
        return (f"redacao_alternativa: nenhuma fonte do caso traz, no próprio dispositivo {c['caminho']!r} da norma "
                f"consultada, o texto alternativo ao lado de anotação do ato {ev_a}")
    return None


def validar_c(c, g, f, fo, ctx, res, info):
    """Capacidade (c): tipos da seção 1.1, com todos os controles também nos casos sem texto."""
    cid = c["id"]
    tipo = g["tipo"]
    D = _data_valida(c.get("data"))
    consultadas = []
    for i, fc in enumerate(g.get("fontes_consultadas") or []):
        consultadas.append(validar_fonte_meta(cid, fc, ctx, rotulo=f"fontes_consultadas[{i}]"))
    fontes_todas = _fontes_do_caso(f, consultadas)
    regs = _regioes(c, fontes_todas)
    anots_reg = _anots_regioes(regs)
    n = c["norma"]
    fam = c.get("familia_alteracao")
    ev = canon_norma(n) if fam == "original" else canon_fam(fam)
    if c.get("data_mutante"):
        msg = checa_data_mutante(c, g, fontes_todas)
        if msg:
            res.falha(cid, msg)
    if tipo == "verificado_para_D":
        if D is None:
            res.falha(cid, "verificado_para_D exige `data` válida")
        if g.get("motivos_aceitos"):
            res.falha(cid, "verificado_para_D não admite motivos_aceitos")
        # a redação do gabarito tem de estar sustentada, documentalmente, para o intervalo de D: o ato do evento (a obra,
        # se `original`; o ato alterador, se não) tem data demonstrada, e D é igual ou posterior a ela. Uma compilada
        # posterior, sozinha, não sustenta D anterior ao ato.
        if D is not None and info:
            dts = datas_de_atos(fontes_todas, [txt for fx in fontes_todas if fx is not None for _, txt in fx.anots])
            rng = dts.get(ev)
            if rng is None:
                res.falha(cid, f"verificado_para_D: a data do ato do evento ({ev}) não está demonstrada (cabeçalho ou "
                               f"anotação com data) em nenhuma fonte do caso")
            elif D < rng[0]:
                res.falha(cid, f"verificado_para_D: D ({D}) é anterior à data do ato do evento {ev} ({rng[0]}): a redação "
                               "não existia em D")
            elif rng[0] != rng[1] and D < rng[1]:
                res.falha(cid, f"verificado_para_D: a data do ato {ev} só é demonstrada pelo ano e D ({D}) cai nesse ano: "
                               "não há como afirmar que o ato já vigorava em D")
            if info["compilada"] and any(_RESSALVA.search(a) for a in info["anots"]):
                res.revisao(cid, "(i)", "o dispositivo traz anotação de vigência, produção de efeitos, veto ou revogação: "
                                        "confirme que a redação do gabarito valia em D")
        res.revisao(cid, "(i)", "confirme que o documento aceito é a versão oficial válida em D (nenhuma alteração "
                                "intermediária entre o ato do evento e D)")
        return
    if _str_ok(g.get("texto")):
        res.falha(cid, f"{tipo} não admite gabarito.texto")
    if tipo == "nao_verificado_para_D":
        validar_nao_verificado(c, g, fo, res, fontes_todas, regs, anots_reg, D)
        return
    if tipo == "nao_existia_em_D":
        validar_nao_existia(c, g, f, res, fontes_todas, info, D)


def _doc_ato(ident, dts, ids_anotados, fontes, n):
    """O ato `ident` está documentado em relação à norma: nomeado nas anotações do dispositivo ou é o ato (de cabeçalho
    conhecido) de uma fonte que menciona a norma consultada."""
    if ident in ids_anotados:
        return True
    for fx in fontes:
        if fx is None:
            continue
        for h in fx.atos()["cabecalhos"]:
            if canon(h["esp"], h["num"], h["ano"]) == ident and canon_norma(n) in referencias_norma(fx.clean):
                return True
    return False


def validar_nao_verificado(c, g, fo, res, fontes_todas, regs, anots_reg, D):
    cid = c["id"]
    n = c["norma"]
    mot = g.get("motivos_aceitos")
    if not isinstance(mot, list) or not mot:
        res.falha(cid, "nao_verificado_para_D exige motivos_aceitos não vazio")
        mot = []
    for m in mot:
        if m not in MOTIVOS:
            res.falha(cid, f"motivo aceito fora do conjunto permitido {MOTIVOS}: {m!r}")
    if not isinstance(g.get("fontes_consultadas"), list) or not g.get("fontes_consultadas"):
        res.falha(cid, "nao_verificado_para_D exige fontes_consultadas (documentos consultados que demonstram o limite)")
    tr = c.get("trecho")
    if not _str_ok(tr):
        res.falha(cid, "nao_verificado_para_D exige `trecho` normativo real")
    else:
        t = norm(tr)
        if not any(t in fx.clean[a:b] for fx, a, b in regs):
            res.falha(cid, "trecho não é texto do DISPOSITIVO citado em nenhuma fonte gravada do caso (cabeçalho, outro "
                           "artigo ou texto genérico não são trecho normativo do dispositivo)")
        if len(t) < 30:
            res.alerta(cid, "trecho curto (<30 caracteres): confirme que é normativo e não genérico")
    if "sem_versao_oficial_na_data" in mot:
        anots_todos = [txt for fx in fontes_todas if fx is not None for p, txt in fx.anots]
        dts = datas_de_atos(fontes_todas, anots_todos)
        ids_anot = atos_das_anotacoes([a for a in anots_reg if _DA_REDACAO.search(a) or re.match(r"\(\s*Revogad", a, re.I)])
        cad = g.get("cadeia")
        datas = []
        if not isinstance(cad, list) or not cad:
            res.falha(cid, "sem_versao_oficial_na_data exige `cadeia` não vazia de atos alteradores")
        else:
            idents = []
            for x in cad:
                ident = x.get("ato") if isinstance(x, dict) else None
                idents.append(ident)
                if not (isinstance(ident, str) and FAMILIA_RE.match(ident) and ident != "original"):
                    res.falha(cid, f"cadeia: elemento deve ser {{ato: identificador canônico, data}}: {x!r}")
                    continue
                d = _data_valida(x.get("data"))
                if d is None:
                    res.falha(cid, f"cadeia: data ausente ou inválida: {x!r}")
                    continue
                datas.append(d)
                ev = canon_fam(ident)
                if not _doc_ato(ev, dts, ids_anot, fontes_todas, n):
                    res.falha(cid, f"cadeia: o ato {ident!r} não está documentado em relação ao dispositivo (nem nas "
                                   f"anotações do dispositivo, nem como ato de fonte que mencione a norma)")
                elif dts.get(ev) is not None and not _intervalo_contem(dts.get(ev), d):
                    res.falha(cid, f"cadeia: a data {d} de {ident!r} não confere com a data documentada ({dts.get(ev)})")
            if datas != sorted(datas):
                res.falha(cid, "cadeia não está ordenada por data")
            if len({canon_fam(i) for i in idents if isinstance(i, str)}) != len([i for i in idents if isinstance(i, str)]):
                res.falha(cid, "cadeia com ato repetido")
        uva = g.get("ultima_versao_anterior")
        if not isinstance(uva, dict):
            res.falha(cid, "sem_versao_oficial_na_data exige `ultima_versao_anterior` {ato, data}: a última versão oficial "
                           "anterior a D")
        else:
            ato, du = uva.get("ato"), _data_valida(uva.get("data"))
            if not (_str_ok(ato) and (ato == "original" or FAMILIA_RE.match(ato))) or du is None:
                res.falha(cid, f"ultima_versao_anterior malformada (ato canônico ou 'original' e data ISO): {uva!r}")
            else:
                ev = canon_norma(n) if ato == "original" else canon_fam(ato)
                if ato != "original" and not _doc_ato(ev, dts, ids_anot, fontes_todas, n):
                    res.falha(cid, f"ultima_versao_anterior: o ato {ato!r} não está documentado em relação ao dispositivo")
                elif dts.get(ev) is not None and not _intervalo_contem(dts.get(ev), du):
                    res.falha(cid, f"ultima_versao_anterior: a data {du} não confere com a data documentada do ato {ev} "
                                   f"({dts.get(ev)})")
                if D is not None and not du < D:
                    res.falha(cid, f"ultima_versao_anterior ({du}) não é anterior a D ({D})")
                if datas and not du < datas[0]:
                    res.falha(cid, "ultima_versao_anterior não é anterior ao primeiro ato da cadeia")
    res.revisao(cid, "(iii)", "o limite demonstrado pelas fontes (período sem versão oficial identificada, não ausência de "
                              "publicação num dia) e a suficiência da cadeia")


def validar_nao_existia(c, g, f, res, fontes_todas, info, D):
    cid = c["id"]
    cond = g.get("condicao_inexistencia")
    if cond not in CONDICOES_INEXISTENCIA:
        res.falha(cid, f"nao_existia_em_D exige condicao_inexistencia em {CONDICOES_INEXISTENCIA} (seção 1.1)")
        return
    if D is None:
        return
    n = c["norma"]
    anots_todos = [txt for fx in fontes_todas if fx is not None for p, txt in fx.anots]
    datas = datas_de_atos(fontes_todas, anots_todos)
    if cond == "anterior_a_obra":
        d_obra = datas.get(canon_norma(n))
        if d_obra is None:
            res.falha(cid, "anterior_a_obra: a data da obra não está demonstrada no cabeçalho de nenhuma fonte do caso")
        elif not D < d_obra[0]:
            res.falha(cid, f"anterior_a_obra: D ({D}) não é anterior à data da obra ({d_obra[0]})")
        return
    fam = c.get("familia_alteracao")
    if fam == "original":
        res.falha(cid, "anterior_a_inclusao exige familia_alteracao = ato que incluiu o dispositivo")
        return
    ev = canon_fam(fam)
    rng = datas.get(ev)
    if rng is None:
        res.falha(cid, f"anterior_a_inclusao: a data do ato {fam} não está demonstrada no cabeçalho de nenhuma fonte do "
                       "caso nem na anotação com data")
    elif not D < rng[0]:
        res.falha(cid, f"anterior_a_inclusao: D ({D}) não é anterior à data do ato que incluiu ({rng[0]})")
    if not info:
        return
    anots = info["anots"]
    ids = atos_das_anotacoes([a for a in anots if re.search(r"inclu[ií]d|acrescid|acrescentad", a, re.I)])
    if ev not in ids:
        res.falha(cid, f"anterior_a_inclusao: a anotação do dispositivo não registra inclusão pelo ato {fam}")
    # ressalvas de vigência/efeito/veto/revogação, removíveis ou não da fonte (inclusive `(Vigência)` sem ato)
    regiao = f.clean[info["s"]:info["e"]]
    for a in list(anots) + [m.group(0) for m in re.finditer(r"\([^()]*\)", regiao)]:
        if _RESSALVA.search(a):
            res.falha(cid, f"anterior_a_inclusao: ressalva de vigência/efeito/veto/revogação no dispositivo (seção 1.1): "
                           f"{a[:60]!r}")
    for m in re.finditer(r"\b(?:vetad|revogad)[oa]s?\b", regiao, re.I):
        res.falha(cid, f"anterior_a_inclusao: o texto do dispositivo traz {m.group(0)!r} (seção 1.1)")


def validar_revogado(c, g, f, fo, res, info):
    """revogado_vigente: a anotação de revogação está NO dispositivo exato e o dispositivo inteiro está revogado (nada
    de texto vigente na sua extensão); revogação parcial nunca vale como revogação do artigo inteiro."""
    cid = c["id"]
    if _str_ok(g.get("texto")):
        res.falha(cid, "revogado_vigente não admite gabarito.texto (o dispositivo revogado não tem texto vigente)")
    if not info:
        return
    rev = [a for a in info["anots"] if re.match(r"\(\s*Revogad", a, re.I)]
    if not rev:
        res.falha(cid, "revogado_vigente: a fonte não traz anotação de revogação (Revogado pela/pelo ...) no dispositivo "
                       "citado")
        return
    pc = parse_caminho(c["caminho"])
    regiao = f.clean[info["s"]:info["e"]].strip()
    rx = re_inicio_dispositivo(pc)
    m = rx.match(regiao) if rx else None
    if not m or regiao[m.end():].strip(" .;\"") != "":
        res.falha(cid, f"revogado_vigente: revogação parcial — o dispositivo {c['caminho']!r} ainda tem texto vigente além "
                       f"do identificador e da anotação de revogação ({regiao[:60]!r}...)")


def caminho_da_citacao(cit, cap):
    """Caminho inferido da citação, só para que as demais classes sejam conferidas quando `caminho` falta (a falta já
    é FALHA de esquema)."""
    p = parse_citacao(cit)
    if not p["art"]:
        return None
    art = f"art. {p['art']}{'-' + p['suf'] if p['suf'] else ''}"
    return f"Anexo, {art}" if cap == "d" else art


def validar_caso(c, ctx, res):
    if not _str_ok(c.get("caminho")):
        c = dict(c, caminho=caminho_da_citacao(c["citacao"], c["capacidade"]) or "art. 1")
    if parse_caminho(c["caminho"]) is None:
        return  # caminho inválido já é FALHA de esquema; sem caminho não há posição estrutural a conferir
    cid = c["id"]
    g = c["gabarito"]
    cap = c["capacidade"]
    tipo = g["tipo"]
    fo = g.get("fonte_oficial")
    f = validar_fonte_meta(cid, fo, ctx)
    # coerência norma/citação
    ref = referencia_norma(c["citacao"])
    n = c["norma"]
    if ref is None:
        res.falha(cid, f"citação não identifica a norma (número/ano ou código nominal): {c['citacao']!r}")
    elif (ref[0], _sn(ref[1]), ref[2]) != (n["especie"], _sn(n["numero"]), n["ano"]):
        res.falha(cid, f"citação {c['citacao']!r} não corresponde à norma {n['especie']} {n['numero']}/{n['ano']}")
    if cap == "d" and not parse_citacao(c["citacao"])["anexo"]:
        res.falha(cid, "(d): citação sem 'Anexo'")
    if cap != "d" and parse_citacao(c["citacao"])["anexo"]:
        res.alerta(cid, "citação com 'Anexo' fora de (d)")
    if f is None:
        return
    info = None
    if tipo in ("texto", "verificado_para_D"):
        if not _str_ok(g.get("texto")):
            res.falha(cid, f"{tipo} exige gabarito.texto (texto integral do dispositivo)")
        else:
            info = validar_texto(c, g, f, fo, ctx, res, g["texto"])
    else:
        info = validar_posicao_sem_texto(c, g, f, fo, ctx, res)
        if tipo == "revogado_vigente":
            validar_revogado(c, g, f, fo, res, info)
    if cap == "a" and info:
        res.revisao(cid, "(i)", "confirme que o documento aceito é de fato a publicação original do dispositivo "
                                "(primeira redação)")
    if cap == "c":
        validar_c(c, g, f, fo, ctx, res, info)
    elif g.get("motivos_aceitos"):
        res.falha(cid, "motivos_aceitos só se aplica a (c)")
    if cap == "b" and c.get("data_mutante"):
        msg = checa_data_mutante(c, g, [f])
        if msg:
            res.falha(cid, msg)
    if c.get("data_mutante") and isinstance(g.get("redacao_alternativa"), dict):
        res.revisao(cid, "(i)", f"data_mutante {c.get('data_mutante')}: confirme que a redação alternativa documentada "
                                f"vigorava nessa data e é, de fato, outra redação do mesmo dispositivo")
    if cap == "e" and tipo == "texto" and _str_ok(g.get("texto")):
        _valida_alvos(c, g, g["texto"], res)
    elif cap != "e" and g.get("alvos"):
        res.falha(cid, "alvos só se aplica a (e)")


# --------------------------------------------------------------------------------------------------------------
# Independência e contagem (seção 2) e composição dos conjuntos (seção 5)
# --------------------------------------------------------------------------------------------------------------
def evento_do_caso(c):
    """Identidade ÚNICA do evento normativo: o identificador canônico normalizado do ato que deu a redação; para redação
    original, o da própria obra (a publicação da Lei 100 consultada como a obra e a redação que ela deu à Lei 1 são o
    mesmo evento). Grafias diferentes do mesmo ato (zeros à esquerda) são um evento."""
    fam = c.get("familia_alteracao")
    if not (isinstance(fam, str) and FAMILIA_RE.match(fam)):
        return None
    return canon_norma(c["norma"]) if fam == "original" else canon_fam(fam)


def contagem(casos, res, falhos_ids, conjunto=None):
    """Seção 2: unidade = evento; ≥ 8 unidades e ≥ 4 normas por capacidade; o representante da unidade é o de menor id
    entre TODOS os casos da unidade, fixado antes de avaliar resultados (se o representante falha, a unidade não conta:
    não há substituição pelo seguinte). Seção 5: cardinalidades do conjunto (desenvolvimento ≥ 40 casos; reserva ≥ 50 casos,
    ≥ 10 por capacidade) e, na reserva, ≥ 40% dos casos (c) `verificado_para_D` (seção 2)."""
    por_cap = defaultdict(lambda: defaultdict(list))
    caso_por_id = {}
    n_casos_cap = Counter()
    for c in casos:
        if not isinstance(c.get("norma"), dict) or c.get("capacidade") not in CAPS or not isinstance(c.get("id"), str):
            continue
        n_casos_cap[c["capacidade"]] += 1
        ev = evento_do_caso(c)
        if ev is None or canon_norma(c["norma"]) is None:
            continue
        por_cap[c["capacidade"]][ev].append(c["id"])
        caso_por_id[c["id"]] = c
    total_min = 50 if conjunto == "reserva" else 40
    if len(casos) < total_min:
        res.falha("conjunto", f"{len(casos)} casos (mínimo {total_min} no conjunto de {conjunto or 'desenvolvimento'})")
    for cap in CAPS:
        un = por_cap[cap]
        reps = {u: min(v) for u, v in un.items()}
        validas = {u: r for u, r in reps.items() if r not in falhos_ids}
        normas = {canon_norma(caso_por_id[r]["norma"]) for r in validas.values()}
        res.info.append(f"capacidade {cap}: {len(validas)} unidades válidas de {len(un)} ({n_casos_cap[cap]} casos), "
                        f"{len(normas)} normas; representantes (menor id da unidade): {', '.join(sorted(reps.values()))}")
        if len(validas) < 8 or len(normas) < 4:
            res.falha(f"capacidade-{cap}", f"{len(validas)} unidades independentes válidas (mínimo 8) e {len(normas)} "
                                           f"normas (mínimo 4)")
        if conjunto == "reserva" and n_casos_cap[cap] < 10:
            res.falha(f"capacidade-{cap}", f"{n_casos_cap[cap]} casos na reserva (mínimo 10 por capacidade)")
    if conjunto == "reserva":
        cc = [c for c in casos if c.get("capacidade") == "c" and isinstance(c.get("gabarito"), dict)]
        pos = sum(1 for c in cc if c["gabarito"].get("tipo") == "verificado_para_D")
        if not cc or pos * 100 < 40 * len(cc):
            res.falha("capacidade-c", f"{pos} de {len(cc)} casos (c) da reserva são verificado_para_D "
                                      f"({(100 * pos // len(cc)) if cc else 0}%; mínimo 40%): abstenção sistemática não "
                                      f"aprova (c)")


# --------------------------------------------------------------------------------------------------------------
# Cobertura (seção 5)
# --------------------------------------------------------------------------------------------------------------
SITUACOES = {
    "lsa_156": ("lei", "6404", 1976, "156"), "lsa_254a": ("lei", "6404", 1976, "254-A"),
    "lsa_289": ("lei", "6404", 1976, "289"), "cc_421": ("lei", "10406", 2002, "421"),
    "cc_1031": ("lei", "10406", 2002, "1031"), "ctn_185": ("lei", "5172", 1966, "185"),
}
OUTRAS_SITUACOES = ("rasura", "sem_rasura", "revogacao", "mp_reeditada", "mp_convertida", "anexo", "remissao",
                    "data_anterior_a_publicacao")


def validar_cobertura(path, casos, falhos_ids, ctx, res):
    """Só a FORMA (redução D5): situações obrigatórias presentes; `casos` não vazio, `evento` e `esperado` preenchidos;
    casos citados existem e não têm falha de validação (aprovados na triagem). O vínculo documental de cada situação com os
    casos é REVISAO_HUMANA; nenhuma inferência por proximidade textual."""
    try:
        cob = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        res.falha("cobertura", f"cobertura.json ilegível: {e}")
        return
    sit = cob.get("situacoes") if isinstance(cob, dict) else None
    if not isinstance(sit, dict):
        res.falha("cobertura", "cobertura.json deve ter o objeto `situacoes`")
        return
    por_id = {c.get("id"): c for c in casos if isinstance(c, dict) and isinstance(c.get("id"), str)}
    for nome in list(SITUACOES) + list(OUTRAS_SITUACOES):
        if nome not in sit:
            res.falha(f"cobertura:{nome}", "situação obrigatória ausente da cobertura (seção 5)")
    for nome in sit:
        if nome not in SITUACOES and nome not in OUTRAS_SITUACOES:
            res.alerta(f"cobertura:{nome}", "situação fora da lista da seção 5 (ignorada)")
    for nome, ent in sit.items():
        rot = f"cobertura:{nome}"
        if not isinstance(ent, dict):
            res.falha(rot, "entrada deve ser objeto {casos, evento, esperado}")
            continue
        ids = ent.get("casos")
        if not isinstance(ids, list) or not ids:
            res.falha(rot, "`casos` ausente ou vazio")
            continue
        for k in ("evento", "esperado"):
            if not _str_ok(ent.get(k)):
                res.falha(rot, f"`{k}` ausente ou vazio")
        cs = []
        for i in ids:
            if not isinstance(i, str):
                res.falha(rot, f"identificador de caso inválido (deve ser texto): {i!r}")
                continue
            c = por_id.get(i)
            if c is None:
                res.falha(rot, f"caso citado inexistente: {i}")
            elif i in falhos_ids:
                res.falha(rot, f"caso citado tem falha de validação: {i}")
            else:
                cs.append(c)
        if not cs:
            continue
        res.revisao(rot, "(v)", "vínculo documental da situação (casos, evento e resultado esperado): o validador só "
                                "confere a forma; a segunda camada confere se os casos citados exercitam a situação")


# --------------------------------------------------------------------------------------------------------------
# Mutantes (seção 3)
# --------------------------------------------------------------------------------------------------------------
def _numeral(n, com_ordinal, suf=None):
    s = f"{n:,}".replace(",", ".") if n >= 1000 else str(n)
    if com_ordinal and n <= 9:
        s += "º"
    if suf:
        s += f"-{suf}"
    return s


def _int_romano(n):
    out = ""
    for v, s in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
                 (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out += s
            n -= v
    return out


def _chamada(c, citacao, trecho=None, data=None):
    cap = c["capacidade"]
    if cap == "a":
        return {"funcao": "obter_dispositivo", "parametros": {"citacao": citacao, "versao": "publicacao_original"}}
    if cap == "c":
        p = {"citacao": citacao, "trecho": trecho, "data": data if data is not None else c.get("data")}
        return {"funcao": "verificar_citacao", "parametros": p}
    return {"funcao": "obter_dispositivo", "parametros": {"citacao": citacao}}


def _troca_caractere(texto, existe_na_fonte=None):
    """Letra ASCII mais próxima do centro trocada pela vizinha no alfabeto (a→b, ..., z→y). Com `existe_na_fonte`, só vale
    a troca cujo texto resultante NÃO ocorre na fonte (o mutante tem de ser inválido por construção)."""
    centro = len(texto) // 2
    ordem = sorted(range(len(texto)), key=lambda i: (abs(i - centro), i))
    for i in ordem:
        ch = texto[i]
        if ch.isascii() and ch.isalpha():
            viz = chr(ord(ch) + 1) if ch.lower() != "z" else chr(ord(ch) - 1)
            novo = texto[:i] + viz + texto[i + 1:]
            if existe_na_fonte is None or not existe_na_fonte(novo):
                return novo, i, ch, viz
    return None


def _marc_no_ato(f, cand, tipo):
    """Marcadores `tipo` do mesmo ato (e, para artigos, do mesmo anexo) do candidato."""
    ato = cand["ato"]
    return [mk for mk in f.marcadores() if mk["tipo"] == tipo and mk["ato"] is ato]


def _texto_do_destino(f, pc2, cand_origem):
    """Texto normalizado do dispositivo EXATO `pc2` (caminho completo, com subdispositivos) no mesmo ato e no mesmo
    documento do original, ou None se o caminho completo não existe ali."""
    for x in resolver_dispositivo(f, pc2):
        if x["ato"] is cand_origem["ato"]:
            return norm(f.clean[x["start"]:x["end"]])
    return None


def _destino_renumerado(c, f, cand, pcam, pcit, texto):
    """Destino do mutante `renumerado`: (citação alterada, regra, texto normalizado do destino, caminho completo do destino)
    ou None. O destino é o CAMINHO COMPLETO da chamada mutante (anexo, artigo, parágrafo, inciso, alínea), resolvido na
    estrutura do mesmo ato: tem de existir ali e ter texto efetivo diferente do original (do gabarito e do dispositivo
    original na fonte). Regra: citação de anexo, só o número seguinte do anexo (nunca troca de artigo); senão `art. N` →
    `art. N+1`; se o destino de N+1 não existe ou é igual ao original, `art. N-A`."""
    cit = c["citacao"]
    original = {texto, norm(f.clean[cand["start"]:cand["end"]])} - {""}
    candidatos = []
    if pcam["anexo"] is not None:
        key = _anexo_chave(pcam["anexo"])
        key = 1 if key == "UNICO" else key
        if isinstance(key, int):
            prox = key + 1
            estilo = pcit["anexo_id"] or ""
            novo = str(prox) if estilo.isdigit() else _int_romano(prox)
            pc2 = dict(pcam, anexo=_int_romano(prox))
            txt = _texto_do_destino(f, pc2, cand)
            if txt is not None and txt not in original:
                cit2 = re.sub(r"(?i)\banexo\b(?:\s+(?:(?-i:[IVXLCDM]+)|\d+|[uú]nico)\b)?", f"Anexo {novo}", cit, count=1)
                cam2 = re.sub(r"(?i)^\s*anexo(?:\s+[^,\s]+)?", f"Anexo {novo}", c["caminho"], count=1)
                candidatos.append((cit2, f"anexo seguinte (Anexo {novo})", txt, cam2))
    elif pcit["art"]:
        n = int(pcit["art"])
        for (num, suf, regra) in ((n + 1, None, "art. N+1"), (n, "A", "art. N-A")):
            if regra == "art. N-A" and pcit["suf"]:
                continue
            pc2 = dict(pcam, art=str(num), suf=suf)
            txt = _texto_do_destino(f, pc2, cand)
            if txt is None or txt in original:
                continue
            a, b = pcit["span"]
            cit2 = cit[:a] + re.sub(r"(?i)^(art(?:igo)?s?\.?\s*)\S+(?:\s*-\s*[A-Z])?",
                                    lambda m: m.group(1) + _numeral(num, pcit["ord"], suf), cit[a:b], count=1) + cit[b:]
            cam2 = re.sub(r"^(?i:art(?:igo)?\.?\s*)[\d.]+\s*[ºo°]?(?:\s*-\s*[A-Z])?",
                          lambda m: f"art. {_numeral(num, pcit['ord'], suf)}", c["caminho"].strip(), count=1)
            candidatos.append((cit2, regra, txt, cam2))
            break
    return candidatos[0] if candidatos else None


def caminho_rascunho(saida):
    """Destino do rascunho: sempre `<nome>.rascunho.jsonl`. Nenhum caminho do validador grava o `mutantes.jsonl` congelado
    (quem o escreve é o pesquisador)."""
    p = Path(saida)
    if p.name.endswith(".rascunho.jsonl"):
        return p
    return p.with_name(p.stem + ".rascunho.jsonl")


def gerar_mutantes(casos, pasta, saida=None, ctx=None):
    """AJUDA OPCIONAL (redução D5): rascunho de mutantes da seção 3 para o pesquisador revisar e copiar para o seu
    `mutantes.jsonl`. Nunca grava o arquivo congelado: com `saida`, grava só `<saida>.rascunho.jsonl` (UTF-8, LF, chaves
    ordenadas), com `rascunho: true` em cada registro. Devolve (mutantes, avisos, erros); `erros` lista o que o rascunho
    não pôde gerar."""
    res = Resultado()
    ctx = ctx or Contexto(pasta, None, res)
    muts, avisos, erros = [], [], []
    for c in sorted((x for x in casos if isinstance(x, dict)), key=lambda x: str(x.get("id", ""))):
        cid = c.get("id")
        try:
            g = c["gabarito"]
            fo = g.get("fonte_oficial") or {}
            f, erro, _ = ctx.fonte(fo.get("sha256", ""))
            cons = [ctx.fonte(fc.get("sha256", ""))[0] for fc in (g.get("fontes_consultadas") or []) if isinstance(fc, dict)]
            fontes = [x for x in [f] + cons if x is not None]
            cit = c["citacao"]
            texto = norm(g.get("texto") or "")
            trecho = texto or (norm(c["trecho"]) if _str_ok(c.get("trecho")) else None)
            pcam, pcit = parse_caminho(c["caminho"]), parse_citacao(cit)
            # renumerado (todas): obrigatório
            if f is None or pcam is None:
                erros.append(f"{cid}: sem fonte extraível ou caminho inválido, mutante renumerado impossível ({erro})")
            else:
                cands = resolver_dispositivo(f, pcam)
                s_txt = f.clean.find(texto) if texto else -1
                cand = next((x for x in cands if texto and x["start"] == s_txt), None) or \
                    next((x for x in cands if _cabecalho_confere(x["ato"], _esperado_ato(c, True))), None) or \
                    (cands[0] if cands else None)
                dest = _destino_renumerado(c, f, cand, pcam, pcit, texto) if cand else None
                if dest is None:
                    erros.append(f"{cid}: nenhum dispositivo de destino válido existe no ato consultado para o mutante "
                                 f"renumerado (art. N+1, art. N-A ou anexo seguinte, com texto diferente do original): "
                                 f"mutante obrigatório ausente; exige caso substituível ou alteração expressa da matriz")
                else:
                    cit2, regra, txt_dest, cam_dest = dest
                    muts.append({
                        "tipo": "renumerado", "caso": c["id"], "rascunho": True,
                        "id": f"{c['id']}#renumerado", "chamada": _chamada(c, cit2, trecho),
                        "destino": {"citacao": cit2, "caminho": cam_dest},
                        "alteracao": {"de": cit, "para": cit2, "regra": regra},
                        "esperado": {"nenhum_encontrada_com_texto_do_original": True, "nenhum_verified": True}})
            # caractere (todas com texto): obrigatório
            if texto:
                tc = _troca_caractere(texto, lambda t: any(t in fx.clean for fx in fontes))
                if tc is None:
                    erros.append(f"{cid}: nenhuma troca de caractere produz texto ausente da fonte: mutante caractere "
                                 f"obrigatório ausente")
                else:
                    novo_t, i, de, para = tc
                    muts.append({
                        "tipo": "caractere", "caso": c["id"], "rascunho": True,
                        "id": f"{c['id']}#caractere",
                        "chamada": {"funcao": "verificar_citacao", "parametros": {"citacao": cit, "trecho": novo_t}},
                        "alteracao": {"posicao": i, "de": de, "para": para, "contexto": texto[max(0, i - 15):i + 15]},
                        "esperado": {"text.status": "!= verified"}})
            # data_trocada (b) e (c) com data_mutante: obrigatório quando declarada, com data VÁLIDA
            if c["capacidade"] in ("b", "c") and _str_ok(c.get("data_mutante")):
                msg = checa_data_mutante(c, g, fontes)
                if msg:
                    erros.append(f"{cid}: data_mutante inválida, mutante data_trocada não gerado: {msg}")
                elif not trecho:
                    erros.append(f"{cid}: data_mutante declarada, mas o caso não tem texto nem trecho para a chamada")
                else:
                    alt = g.get("redacao_alternativa")
                    muts.append({
                        "tipo": "data_trocada", "caso": c["id"], "rascunho": True,
                        "id": f"{c['id']}#data_trocada",
                        "chamada": {"funcao": "verificar_citacao",
                                    "parametros": {"citacao": cit, "trecho": trecho, "data": c["data_mutante"]}},
                        "data_mutante": c["data_mutante"],
                        "redacao_alternativa": {"ato": alt.get("ato")} if isinstance(alt, dict) else None,
                        "base": "redacao_alternativa" if isinstance(alt, dict) else "anterior_a_obra",
                        "esperado": {"text.status": "!= verified", "temporal.status": "!= verified"}})
            elif c["capacidade"] in ("b", "c") and not c.get("data_mutante"):
                avisos.append(f"{cid}: sem data_mutante, mutante data_trocada não gerado (facultativo)")
        except (KeyError, TypeError, ValueError, AttributeError, IndexError) as e:
            erros.append(f"{cid}: caso malformado, sem mutantes ({type(e).__name__}: {e})")
    muts.sort(key=lambda m: (m["caso"], m["tipo"]))
    if saida:
        corpo = "".join(json.dumps(m, ensure_ascii=False, sort_keys=True) + "\n" for m in muts)
        Path(caminho_rascunho(saida)).write_bytes(corpo.encode("utf-8"))
    return muts, avisos, erros


# --------------------------------------------------------------------------------------------------------------
# Conferência de FORMA dos mutantes escritos pelo pesquisador (seção 3, redução D5)
# --------------------------------------------------------------------------------------------------------------
TIPOS_MUTANTE = ("renumerado", "caractere", "data_trocada")
CAMPOS_MUTANTE = {"id", "caso", "tipo", "chamada", "esperado", "destino", "data_mutante", "redacao_alternativa", "base",
                  "alteracao", "rascunho"}
FUNCOES_CHAMADA = ("obter_dispositivo", "verificar_citacao")


def _diferem_em_um_caractere(a, b):
    return len(a) == len(b) and sum(1 for x, y in zip(a, b) if x != y) == 1


def _fontes_de(c, ctx):
    g = c.get("gabarito") if isinstance(c.get("gabarito"), dict) else {}
    fo = g.get("fonte_oficial") if isinstance(g.get("fonte_oficial"), dict) else {}
    out = [ctx.fonte(fo.get("sha256", ""))[0]]
    out += [ctx.fonte(x.get("sha256", ""))[0] for x in (g.get("fontes_consultadas") or []) if isinstance(x, dict)]
    return [x for x in out if x is not None]


def _confere_mutante(m, c, ctx, res, rot):
    """Coerência mecânica de UM mutante com o seu caso. Não julga se o destino é o conteúdo pedido nem se a expectativa de
    rejeição vale para o conteúdo efetivo da chamada: isso é REVISAO_HUMANA (seção 7.1)."""
    tipo = m["tipo"]
    g = c.get("gabarito") if isinstance(c.get("gabarito"), dict) else {}
    params = m["chamada"]["parametros"]
    funcao = m["chamada"]["funcao"]
    texto = norm(g.get("texto") or "") if isinstance(g.get("texto"), str) else ""
    if tipo == "renumerado":
        dest = m.get("destino")
        if not (isinstance(dest, dict) and _str_ok(dest.get("citacao")) and _str_ok(dest.get("caminho"))):
            res.falha(rot, "renumerado: `destino` (citacao e caminho) ausente ou malformado")
            return
        esperada = _chamada(c, dest["citacao"])["funcao"] if c.get("capacidade") in CAPS else None
        if funcao != esperada:
            res.falha(rot, f"renumerado: a função da chamada ({funcao}) não é a da capacidade {c.get('capacidade')} "
                           f"({esperada})")
        if params.get("citacao") != dest["citacao"]:
            res.falha(rot, "renumerado: a citação da chamada difere da citação do destino declarado")
        if dest["citacao"] == c.get("citacao"):
            res.falha(rot, "renumerado: a citação do destino é igual à do caso (nada foi renumerado)")
        pd, po = parse_caminho(dest["caminho"]), parse_caminho(c.get("caminho"))
        if pd is None:
            res.falha(rot, f"renumerado: caminho do destino inválido ou incompleto: {dest['caminho']!r}")
            return
        if po is not None and chave_caminho(pd) == chave_caminho(po):
            res.falha(rot, f"renumerado: o destino {dest['caminho']!r} é o mesmo dispositivo do original")
        pcit = parse_citacao(dest["citacao"])
        if pcit and pd["art"] and pcit.get("art") and (pcit["art"], pcit.get("suf")) != (pd["art"], pd["suf"]):
            res.falha(rot, "renumerado: o artigo da citação do destino não é o do caminho declarado")
        if pcit and pd["anexo"] is not None and pcit.get("anexo") and \
                _anexo_chave(pcit.get("anexo_id") or "UNICO") != _anexo_chave(pd["anexo"]):
            res.falha(rot, "renumerado: o anexo da citação do destino não é o do caminho declarado")
        fontes = _fontes_de(c, ctx)
        achou = False
        for fx in fontes:
            achou = achou or bool(resolver_dispositivo(fx, pd)) or bool(resolver_dispositivo(fx.variante_lax(), pd))
        if not fontes:
            res.falha(rot, "renumerado: o caso não tem fonte extraível para conferir o destino")
        elif not achou:
            res.falha(rot, f"renumerado: o destino declarado {dest['caminho']!r} não aparece como dispositivo na fonte do caso")
    elif tipo == "caractere":
        if funcao != "verificar_citacao":
            res.falha(rot, "caractere: a chamada deve ser verificar_citacao")
        if params.get("citacao") != c.get("citacao"):
            res.falha(rot, "caractere: a citação da chamada difere da do caso")
        if not texto:
            res.falha(rot, "caractere: o caso não tem gabarito.texto (mutante só se aplica a caso com texto)")
        elif not isinstance(params.get("trecho"), str):
            res.falha(rot, "caractere: `trecho` ausente na chamada")
        elif not _diferem_em_um_caractere(norm(params["trecho"]), texto):
            res.falha(rot, "caractere: o trecho não difere do gabarito em exatamente um caractere")
    else:  # data_trocada
        if funcao != "verificar_citacao":
            res.falha(rot, "data_trocada: a chamada deve ser verificar_citacao")
        if c.get("capacidade") not in ("b", "c") or not _str_ok(c.get("data_mutante")):
            res.falha(rot, "data_trocada: só se aplica a (b) e (c) cujo caso declara `data_mutante`")
            return
        dm = m.get("data_mutante")
        if _data_valida(dm) is None:
            res.falha(rot, f"data_trocada: `data_mutante` deve ser data ISO válida (recebido {dm!r})")
        elif dm != c["data_mutante"]:
            res.falha(rot, f"data_trocada: `data_mutante` ({dm}) difere da declarada no caso ({c['data_mutante']})")
        if params.get("data") != dm:
            res.falha(rot, "data_trocada: a `data` da chamada difere de `data_mutante`")
        if params.get("citacao") != c.get("citacao"):
            res.falha(rot, "data_trocada: a citação da chamada difere da do caso")
        base = texto or (norm(c["trecho"]) if _str_ok(c.get("trecho")) else "")
        if not isinstance(params.get("trecho"), str) or (base and norm(params["trecho"]) != base):
            res.falha(rot, "data_trocada: o `trecho` da chamada deve ser o gabarito do caso")
        alt = g.get("redacao_alternativa")
        ref = m.get("redacao_alternativa")
        if isinstance(alt, dict):
            if not (isinstance(ref, dict) and ref.get("ato") == alt.get("ato")):
                res.falha(rot, "data_trocada: falta a referência (`redacao_alternativa.ato`) à redação alternativa declarada "
                               "no caso")
        elif m.get("base") != "anterior_a_obra":
            res.falha(rot, "data_trocada: o caso não declara `redacao_alternativa`; informe `base: anterior_a_obra`")


def validar_mutantes(path, casos, falhos_ids, ctx, res):
    """Confere FORMA e coerência mecânica de `mutantes.jsonl` (escrito pelo pesquisador): esquema; caso de origem existe;
    todos os casos têm os mutantes obrigatórios da seção 3; renumerado, caractere e data_trocada coerentes (ver
    `_confere_mutante`). TODO mutante vai à segunda camada (REVISAO_HUMANA (vi)). Devolve o nº de mutantes lidos."""
    if Path(path).name.endswith(".rascunho.jsonl"):
        res.falha("mutantes", "o arquivo informado é um rascunho (`*.rascunho.jsonl`), não o `mutantes.jsonl` do pesquisador")
        return 0
    try:
        linhas = Path(path).read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeDecodeError) as e:
        res.falha("mutantes", f"mutantes.jsonl ilegível: {type(e).__name__}: {e}")
        return 0
    por_id = {c.get("id"): c for c in casos if isinstance(c, dict) and isinstance(c.get("id"), str)}
    ids, vistos, n = set(), set(), 0
    for ln, linha in enumerate(linhas, 1):
        if not linha.strip():
            continue
        n += 1
        try:
            m = json.loads(linha)
        except ValueError as e:
            res.falha(f"mutantes:linha-{ln}", f"JSON inválido: {e}")
            continue
        if not isinstance(m, dict):
            res.falha(f"mutantes:linha-{ln}", "linha não é objeto JSON")
            continue
        mid = m.get("id")
        rot = f"mutantes:{mid}" if _str_ok(mid) else f"mutantes:linha-{ln}"
        if not _str_ok(mid):
            res.falha(rot, "`id` ausente ou vazio")
        elif mid in ids:
            res.falha(rot, "id de mutante repetido")
        else:
            ids.add(mid)
        extras = sorted(set(m) - CAMPOS_MUTANTE)
        if extras:
            res.alerta(rot, f"campo fora do esquema do mutante: {', '.join(extras)}")
        if m.get("rascunho"):
            res.falha(rot, "registro marcado `rascunho`: o pesquisador deve revisá-lo e removê-lo antes do congelamento")
        ch = m.get("chamada")
        ok = True
        if m.get("tipo") not in TIPOS_MUTANTE:
            res.falha(rot, f"`tipo` inválido (esperado {', '.join(TIPOS_MUTANTE)}): {m.get('tipo')!r}")
            ok = False
        if not (isinstance(ch, dict) and ch.get("funcao") in FUNCOES_CHAMADA and isinstance(ch.get("parametros"), dict)
                and _str_ok(ch["parametros"].get("citacao"))):
            res.falha(rot, "`chamada` deve ter `funcao` (obter_dispositivo|verificar_citacao) e `parametros` com `citacao`")
            ok = False
        if not (isinstance(m.get("esperado"), dict) and m["esperado"]):
            res.falha(rot, "`esperado` (resultado esperado) ausente ou vazio")
            ok = False
        c = por_id.get(m.get("caso")) if isinstance(m.get("caso"), str) else None
        if c is None:
            res.falha(rot, f"caso de origem inexistente: {m.get('caso')!r}")
            ok = False
        if ok:
            k = (m["caso"], m["tipo"])
            if k in vistos:
                res.falha(rot, f"mais de um mutante `{m['tipo']}` para o caso {m['caso']}")
            vistos.add(k)
            try:
                _confere_mutante(m, c, ctx, res, rot)
            except Exception as e:  # noqa: BLE001  (mutante malformado: falha tipada, nunca traceback)
                res.falha(rot, f"erro ao conferir o mutante (entrada malformada?): {type(e).__name__}: {e}")
        res.revisao(rot, "(vi)", "mutante escrito pelo pesquisador: confirme que a expectativa de rejeição vale para o "
                                 "conteúdo efetivo da chamada (corpo da tabela, `trecho`, redação integral na data) e, no "
                                 "renumerado, que o destino declarado não é o conteúdo pedido")
    for cid, c in sorted(por_id.items()):
        g = c.get("gabarito") if isinstance(c.get("gabarito"), dict) else {}
        obrig = ["renumerado"]
        if isinstance(g.get("texto"), str) and norm(g["texto"]):
            obrig.append("caractere")
        if c.get("capacidade") in ("b", "c") and _str_ok(c.get("data_mutante")):
            obrig.append("data_trocada")
        for t in obrig:
            if (cid, t) not in vistos:
                res.falha(f"mutantes:{cid}", f"mutante obrigatório ausente (seção 3): {t}")
    return n


# --------------------------------------------------------------------------------------------------------------
# Orquestração
# --------------------------------------------------------------------------------------------------------------
def carregar_casos(path, res):
    casos = []
    for n, linha in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        if not linha.strip():
            continue
        try:
            c = json.loads(linha)
        except ValueError as e:
            res.falha(f"linha-{n}", f"JSON inválido: {e}")
            continue
        if not isinstance(c, dict):
            res.falha(f"linha-{n}", "linha não é objeto JSON")
            continue
        casos.append(c)
    return casos


def validar(casos, pasta, fontes=None, cobertura=None, pisos=True, res=None, conjunto=None, exploratorio=False):
    """Valida o conjunto. Devolve Resultado. `pisos=True` (padrão) confere as obrigações globais da matriz: contagens,
    composição do conjunto, cobertura (obrigatória; no modo `exploratorio` a falta vira INCOMPLETO) e, na reserva,
    proporção de verificado_para_D. Os mutantes são conferidos pelo chamador (`main`)."""
    res = res or Resultado()
    nao_objeto = [i for i, c in enumerate(casos, 1) if not isinstance(c, dict)]
    for i in nao_objeto:  # API direta: o mesmo contrato de falha tipada da CLI (registro que não é objeto JSON)
        res.falha(f"registro-{i}", f"registro do conjunto não é objeto JSON ({type(casos[i - 1]).__name__})")
    casos = [c for c in casos if isinstance(c, dict)]
    ctx = Contexto(pasta, fontes, res)
    ids_vistos = set()
    if not fontes:
        res.alerta("conjunto", "sem --fontes: metadados das fontes (url, sha256, capturado_em) não conferidos "
                               "contra fontes.csv")
    conjuntos = {c.get("conjunto") for c in casos if isinstance(c, dict) and isinstance(c.get("conjunto"), str)} - {None}
    if len(conjuntos) > 1:
        res.falha("conjunto", f"arquivo mistura conjuntos: {sorted(conjuntos)}")
    if conjunto is None and len(conjuntos) == 1:
        conjunto = next(iter(conjuntos))
    elif conjunto is not None and conjuntos and conjuntos != {conjunto}:
        res.falha("conjunto", f"--conjunto {conjunto} incoerente com o campo `conjunto` dos casos {sorted(conjuntos)}")
    for c in casos:
        cid = c.get("id") if _str_ok(c.get("id")) else "<linha-sem-id>"
        try:
            ok = validar_esquema(c, res, ids_vistos)
            if ok:
                validar_caso(c, ctx, res)
        except Exception as e:  # noqa: BLE001  (entrada malformada: falha tipada, sem traceback)
            res.falha(cid, f"erro interno ao validar o caso (entrada malformada?): {type(e).__name__}: {e}")
    for k, ids in sorted(res.extras.items()):
        res.alerta("conjunto", f"campo fora do esquema da seção 6: {k} (em {len(ids)} casos: "
                               f"{', '.join(ids[:3])}{'...' if len(ids) > 3 else ''})")
    # norma_grande igual por norma
    gr = defaultdict(set)
    for c in casos:
        if isinstance(c.get("norma"), dict) and isinstance(c.get("norma_grande"), bool):
            k = canon_norma(c["norma"])
            if k:
                gr[k].add(c["norma_grande"])
    for k, vs in gr.items():
        if len(vs) > 1:
            for c in casos:
                if isinstance(c.get("norma"), dict) and canon_norma(c["norma"]) == k:
                    res.falha(c.get("id", "?"), f"norma_grande diverge entre casos da mesma norma ({k})")
    falhos = {cid for cid, _ in res.falhas}
    if cobertura:
        try:
            validar_cobertura(cobertura, casos, falhos, ctx, res)
        except Exception as e:  # noqa: BLE001  (cobertura malformada: reprovação diagnosticada, nunca traceback)
            res.falha("cobertura", f"erro ao conferir a cobertura (entrada malformada?): {type(e).__name__}: {e}")
    if pisos:
        try:
            contagem(casos, res, falhos, conjunto)
        except Exception as e:  # noqa: BLE001
            res.falha("conjunto", f"erro ao contar unidades (entrada malformada?): {type(e).__name__}: {e}")
        if cobertura:
            pass
        elif exploratorio:
            res.incompleto.append("sem --cobertura: situações obrigatórias da seção 5 não conferidas")
        else:
            res.falha("cobertura", "cobertura.json é obrigatório no congelamento (seção 5); sem ele, use --exploratorio "
                                   "(resultado declarado INCOMPLETO)")
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("conjunto")
    ap.add_argument("pasta_evidencias")
    ap.add_argument("--fontes")
    ap.add_argument("--mutantes", help="mutantes.jsonl escrito pelo pesquisador (obrigatório no congelamento)")
    ap.add_argument("--gerar-mutantes", dest="rascunho",
                    help="ajuda opcional: grava só um RASCUNHO (<nome>.rascunho.jsonl), nunca o arquivo congelado")
    ap.add_argument("--cobertura")
    ap.add_argument("--conjunto", dest="tipo_conjunto", choices=("desenvolvimento", "reserva"))
    ap.add_argument("--exploratorio", action="store_true",
                    help="dispensa cobertura e mutantes, mas declara o resultado INCOMPLETO (código de saída 2)")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    res = Resultado()
    try:
        casos = carregar_casos(a.conjunto, res)
    except (OSError, UnicodeDecodeError) as e:
        res.falha("conjunto", f"conjunto ilegível: {type(e).__name__}: {e}")
        casos = []
    try:
        res = validar(casos, a.pasta_evidencias, a.fontes, a.cobertura, True, res, a.tipo_conjunto, a.exploratorio)
    except Exception as e:  # noqa: BLE001
        res.falha("conjunto", f"erro interno na validação (entrada malformada?): {type(e).__name__}: {e}")
    if a.rascunho:
        try:
            muts, avisos, erros = gerar_mutantes(casos, a.pasta_evidencias, a.rascunho)
            destino = caminho_rascunho(a.rascunho)
            res.info.append(f"rascunho de mutantes: {len(muts)} gravados em {destino} (não é o arquivo congelado; "
                            f"{len(erros)} pendências de geração)")
            for er in erros:
                res.alerta("rascunho-mutantes", er)
        except Exception as e:  # noqa: BLE001
            res.alerta("rascunho-mutantes", f"erro ao gerar o rascunho (entrada malformada?): {type(e).__name__}: {e}")
    if a.mutantes:
        try:
            ctx = Contexto(a.pasta_evidencias, a.fontes, Resultado())
            falhos = {cid for cid, _ in res.falhas}
            n = validar_mutantes(a.mutantes, casos, falhos, ctx, res)
            h = hashlib.sha256(Path(a.mutantes).read_bytes()).hexdigest() if Path(a.mutantes).is_file() else "-"
            res.info.append(f"mutantes: {n} conferidos em {a.mutantes} (sha256 {h})")
        except Exception as e:  # noqa: BLE001
            res.falha("mutantes", f"erro ao conferir os mutantes (entrada malformada?): {type(e).__name__}: {e}")
    elif a.exploratorio:
        res.incompleto.append("sem --mutantes: mutantes não conferidos (seção 3)")
    else:
        res.falha("mutantes", "mutantes.jsonl obrigatório no congelamento (seção 3): escrito pelo pesquisador e informado por "
                              "--mutantes (ou --exploratorio, resultado INCOMPLETO)")
    for cid, m in res.falhas:
        print(f"FALHA {cid}: {m}")
    for cid, cat, m in res.revisoes:
        print(f"REVISAO_HUMANA {cid}: {cat} {m}")
    for cid, m in res.alertas:
        print(f"ALERTA {cid}: {m}")
    for m in res.info:
        print(f"INFO {m}")
    if res.revisoes:
        por_cat = Counter(cat for _, cat, _ in res.revisoes)
        casos_rev = {cid for cid, _, _ in res.revisoes}
        print(f"INFO revisao_humana: {len(res.revisoes)} pendências em {len(casos_rev)} itens "
              f"({', '.join(f'{k} {v}' for k, v in sorted(por_cat.items()))}); a segunda camada (seção 7.1) é obrigatória")
    for m in res.incompleto:
        print(f"INCOMPLETO {m}")
    print(f"{len(casos)} casos, {len(res.falhas)} falhas")
    if res.falhas:
        return 1
    return 2 if res.incompleto else 0


if __name__ == "__main__":
    sys.exit(main())
