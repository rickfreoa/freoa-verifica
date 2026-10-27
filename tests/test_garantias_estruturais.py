"""FIX18: garantias estruturais por AST sobre `freoa_verifica/` (decisão 0064).

As correções de F-19, F-22 e F-23 cobriam os caminhos encontrados, não todos. Estes meta-testes tornam a classe
inteira verificável: um caminho novo que escape falha aqui, até ser corrigido ou justificado linha a linha.

1. Toda chamada que chega à rede (método de rede de conector, `connector_fetch`, `transport.fetch`) ocorre em função
   coberta pela guarda da chamada: a própria função é entrada guardada (`@sob_guarda`, método de conector em
   `ENTRADAS_DE_REDE`, método da fachada envolvido por `_guardar`/`sob_guarda`), a chamada está dentro de
   `with da_chamada()`/`.ativar()`, ou TODO chamador da função (por nome, no pacote) é coberto.
2. Em função que chega à rede, nenhum `except` que alcance `Unavailable` (o próprio, `Exception`, `BaseException`,
   nu) sem `raise` ou registro estruturado com categoria (`exc.categoria`, `exc.classificacao()`, ou `exc` passado a
   função do pacote que lê um deles).
3. Nenhum `.decode(` fora de `texto_resposta.py`, salvo as linhas justificadas em `DECODE_JUSTIFICADOS` (nenhuma
   sobre corpo de resposta).
4. Nenhum parser recebe `.body` (ou bytes de blob) diretamente, nem por variável atribuída a partir deles na mesma
   função: o caminho é o texto da interpretação única ou `corpo_binario(resp)`.

`FV_GARANTIAS_RAIZ` aponta para outra árvore `freoa_verifica/` (prova contra o código da rodada 13).
"""

from __future__ import annotations

import ast
import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pytest

pytestmark = pytest.mark.repositorio

RAIZ = Path(os.environ.get("FV_GARANTIAS_RAIZ") or Path(__file__).resolve().parents[1] / "freoa_verifica")

# --- exceções justificadas, linha a linha -----------------------------------------------------------------------

# (arquivo relativo, função) -> justificativa. Nenhuma é corpo de resposta HTTP.
DECODE_JUSTIFICADOS = {
    ("connectors/stj_integras.py", "_decodificar"): "membro de ZIP do pacote CKAN (corpo binário), UTF-8 estrito sem BOM alternativo; recusa conforme decisão 0044 item 5",
    ("captura.py", "_ler_manifesto"): "lê tests/fixtures/FIXTURES.json do disco (manifesto local, não resposta)",
    ("fronteira.py", "validar"): "cabeçalhos da requisição ASGI recebida pelo servidor local (latin-1, RFC 9110)",
    ("mcp_server.py", "__call__"): "cabeçalho Authorization da requisição recebida pelo servidor MCP",
    ("rotulos.py", "corrigir_mojibake"): "desfaz mojibake de str já decodificada (latin-1 -> utf-8), sem bytes de resposta",
    ("semente.py", "<modulo>"): "dobra ASCII de nomes de meses (str -> NFKD -> ascii), sem bytes de resposta",
    ("semente.py", "data_da_epigrafe"): "dobra ASCII de nome de mês da epígrafe (str), sem bytes de resposta",
    ("transport.py", "_campos_estritos"): "nomes/valores de campos de cabeçalho HTTP (RFC 9110: ASCII/obs-text)",
    ("transport.py", "_host_canonico"): "rótulo IDNA do host, não corpo",
    ("parsers/isolated.py", "parse_isolated"): "stderr do subprocesso de parse (diagnóstico)",
    ("parsers/isolated.py", "_main"): "texto já decidido pelo pai, transportado ao filho em UTF-8 (`--texto`)",
    ("parsers/bcb_json.py", "parse_bcb_json"): "API do parser para bytes de fixture; resposta nunca chega em bytes (4)",
    ("parsers/html_devices.py", "decode_html_bytes"): "API do parser para bytes de fixture; idem (garantia 4)",
    ("parsers/sentinel.py", "_truncated"): "sentinela sobre a entrada do parser (bytes só de fixture; garantia 4)",
}

# (arquivo, função) -> justificativa: função que chega à rede sem guarda provada estaticamente.
REDE_SEM_GUARDA_JUSTIFICADOS: dict[tuple[str, str], str] = {
    ("connectors/httputil.py", "_connector_fetch"): "implementação da primitiva `connector_fetch` (que consulta a "
    "guarda ativa); a garantia vale para cada chamador de `connector_fetch`, verificado aqui",
}

# (arquivo, função) -> justificativa, para todos os `except` daquela função
_HEALTH = ("sonda de diagnóstico de três probes fixos (positivo, negativo, documento), não controlador de itens: a "
           "falha vira HealthProbe('unavailable', motivo), nunca saudável; a guarda da chamada impede repetir o host "
           "que desafiou/recusou. Sem categoria no probe: questão aberta da FIX18")
EXCEPT_JUSTIFICADOS: dict[tuple[str, str], str] = {
    (f"connectors/{m}.py", f"{c}Connector.health"): _HEALTH
    for m, c in (("bcb", "Bcb"), ("cvm_colegiado", "CvmColegiado"), ("cvm_normas", "CvmNormas"),
                 ("datajud", "Datajud"), ("planalto", "Planalto"), ("senado", "Senado"), ("stf", "Stf"),
                 ("stj", "Stj"), ("tcu", "Tcu"), ("tjdft", "Tjdft"), ("tjsp", "Tjsp"))
}

# --- coleta AST -------------------------------------------------------------------------------------------------

_REDE_FUNCOES = frozenset({"connector_fetch", "transport_fetch"})
_GUARDA_WITH = frozenset({"da_chamada", "ativar"})
_PARSERS_EXTRA = frozenset({
    "loads", "fromstring", "XML", "HTML", "document_fromstring", "parseString", "iterparse", "BytesIO", "ZipFile",
    "_pdf_text", "pdf_texto", "ler_bcb", "ler_situacao_pagina", "parse_ou_indisponivel", "parse_isolated",
    "decode_html_bytes", "run_sentinels",
})
_CAPTURA_EXC = frozenset({"Unavailable", "Exception", "BaseException"})


@dataclass
class Funcao:
    arquivo: str
    nome: str
    qual: str
    classe: str | None
    no: ast.AST
    bases_classe: tuple[str, ...] = ()
    decoradores: tuple[str, ...] = ()
    chamadas: list[tuple[str, ast.Call, bool]] = field(default_factory=list)  # (nome, nó, dentro de with-guarda)
    dono: "Funcao | None" = None  # função que define esta (closure ou método de classe local)


def _nome_chamada(no: ast.Call) -> str | None:
    f = no.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _nome_decorador(d: ast.AST) -> str:
    d = d.func if isinstance(d, ast.Call) else d
    return d.attr if isinstance(d, ast.Attribute) else getattr(d, "id", "")


def _with_guarda(no: ast.With) -> bool:
    return any(isinstance(i.context_expr, ast.Call) and _nome_chamada(i.context_expr) in _GUARDA_WITH
               for i in no.items)


def _chamadas(corpo, guardado: bool, saida: list) -> None:
    """Chamadas do corpo, sem entrar em funções aninhadas (que são coletadas à parte)."""
    for no in corpo:
        _visitar(no, guardado, saida)


def _visitar(no: ast.AST, guardado: bool, saida: list) -> None:
    if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)) and not isinstance(
            no, ast.Lambda):
        return
    if isinstance(no, ast.With) and _with_guarda(no):
        guardado = True
    if isinstance(no, ast.Call):
        nome = _nome_chamada(no)
        if nome:
            saida.append((nome, no, guardado))
    for filho in ast.iter_child_nodes(no):
        _visitar(filho, guardado, saida)


def _modulos() -> dict[str, ast.Module]:
    out = {}
    for p in sorted(RAIZ.rglob("*.py")):
        rel = p.relative_to(RAIZ).as_posix()
        out[rel] = ast.parse(p.read_text(encoding="utf-8-sig"), filename=str(p))
    return out


def _funcoes(mods: dict[str, ast.Module]) -> list[Funcao]:
    out: list[Funcao] = []

    def definicoes(nos):
        """Classes e funções definidas no bloco, inclusive dentro de `for`/`if`/`with`/`try`, sem entrar nelas."""
        for no in nos:
            if isinstance(no, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                yield no
            else:
                yield from definicoes(n for n in ast.iter_child_nodes(no) if isinstance(n, ast.stmt))

    def andar(arquivo, nos, prefixo, classe, bases, dono):
        for no in definicoes(nos):
            if isinstance(no, ast.ClassDef):
                nb = tuple(getattr(b, "id", getattr(b, "attr", "")) for b in no.bases)
                andar(arquivo, no.body, f"{prefixo}{no.name}.", no.name, nb, dono)
            elif isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                f = Funcao(arquivo, no.name, prefixo + no.name, classe, no, bases,
                           tuple(_nome_decorador(d) for d in no.decorator_list), dono=dono)
                _chamadas(no.body, False, f.chamadas)
                out.append(f)
                andar(arquivo, no.body, f"{prefixo}{no.name}.", classe, bases, f)

    for arquivo, mod in mods.items():
        andar(arquivo, mod.body, "", None, (), None)
        modulo = Funcao(arquivo, "<modulo>", "<modulo>", None, mod)
        _chamadas([n for n in mod.body if not isinstance(n, (ast.FunctionDef, ast.ClassDef))], False,
                  modulo.chamadas)
        out.append(modulo)
    return out


def _homonimo(no: ast.Call, regex: set[str]) -> bool:
    """Chamada de mesmo nome que não é de conector: `Path.resolve()` (sem argumento posicional), `re.search`,
    padrão compilado (`_PADRAO.search`, `m.search` ligado a `re.compile`)."""
    alvo = no.func.value
    if no.func.attr == "resolve" and not no.args:
        return True
    if no.func.attr == "search":
        nome = alvo.id if isinstance(alvo, ast.Name) else getattr(alvo, "attr", "")
        return nome in {"re", "regex"} or nome in regex or nome.strip("_").isupper() or (
            isinstance(alvo, ast.Call) and _nome_chamada(alvo) == "compile")
    return False


def _literais_str(no: ast.AST, nomes: dict[str, set[str]]) -> set[str]:
    """Conjunto de strings de `frozenset({...})`, tupla, conjunto, `A | B` ou nome já resolvido."""
    if isinstance(no, ast.Call) and _nome_chamada(no) in {"frozenset", "set", "tuple"} and no.args:
        return _literais_str(no.args[0], nomes)
    if isinstance(no, (ast.Set, ast.Tuple, ast.List)):
        return {e.value for e in no.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    if isinstance(no, ast.BinOp) and isinstance(no.op, ast.BitOr):
        return _literais_str(no.left, nomes) | _literais_str(no.right, nomes)
    if isinstance(no, ast.Name):
        return set(nomes.get(no.id, set()))
    return set()


class Indice:
    def __init__(self) -> None:
        self.mods = _modulos()
        self.funcoes = _funcoes(self.mods)
        self.por_nome: dict[str, list[Funcao]] = defaultdict(list)
        for f in self.funcoes:
            self.por_nome[f.nome].append(f)
        self.entradas = self._entradas_de_rede()
        self.classes_conector = self._classes_conector()
        self.metodos_rede = self._metodos_rede()
        self.fachada = self._fachada_guardada()
        # nomes ligados a `re.compile(...)`, ou variável de laço sobre constante (`for k, pat in _NOTE_KIND`), em cada
        # módulo: `.search` neles é regex, não busca de conector
        self.regex = {arquivo: {t.id for n in ast.walk(mod) if isinstance(n, ast.Assign)
                                and isinstance(n.value, ast.Call) and _nome_chamada(n.value) == "compile"
                                for t in n.targets if isinstance(t, ast.Name)}
                      | {t.id for n in ast.walk(mod) if isinstance(n, ast.For) and isinstance(n.iter, ast.Name)
                         and n.iter.id.strip("_").isupper() for t in ast.walk(n.target) if isinstance(t, ast.Name)}
                      for arquivo, mod in self.mods.items()}
        # decoradores que abrem a guarda: `sob_guarda` e todo decorador do pacote cujo invólucro usa `with da_chamada()`
        self.decoradores_guarda = {"sob_guarda"} | {
            f.nome for f in self.funcoes if f.nome != "<modulo>" and any(isinstance(n, ast.With) and _with_guarda(n) for n in ast.walk(f.no))
            and any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in ast.walk(f.no) if n is not f.no)}

    # -- conectores ----------------------------------------------------------------------------------------------

    def _entradas_de_rede(self) -> set[str]:
        base = self.mods.get("connectors/base.py")
        nomes: set[str] = set()
        for no in ast.walk(base) if base else ():
            if isinstance(no, ast.Assign) and any(getattr(t, "id", "") == "ENTRADAS_DE_REDE" for t in no.targets):
                nomes = _literais_str(no.value, {})
        # só valem se `__init_subclass__` as envolve em `sob_guarda`
        envolve = base is not None and any(
            isinstance(n, ast.FunctionDef) and n.name == "__init_subclass__"
            and any(isinstance(c, ast.Call) and _nome_chamada(c) == "sob_guarda" for c in ast.walk(n))
            for n in ast.walk(base))
        return nomes if envolve else set()

    def _classes_conector(self) -> set[str]:
        classes = {"Connector"}
        mudou = True
        while mudou:
            mudou = False
            for mod in self.mods.values():
                for no in ast.walk(mod):
                    if isinstance(no, ast.ClassDef) and no.name not in classes and any(
                            getattr(b, "id", getattr(b, "attr", "")) in classes for b in no.bases):
                        classes.add(no.name)
                        mudou = True
        return classes

    def _metodos_rede(self) -> set[str]:
        """Métodos de conector que chegam à rede: os de `ENTRADAS_DE_REDE` e todo método de classe de conector que
        chama, direta ou transitivamente (por nome, dentro dos conectores), `connector_fetch`/`transport_fetch`."""
        metodos = [f for f in self.funcoes if f.classe in self.classes_conector]
        rede = set(self.entradas)
        mudou = True
        while mudou:
            mudou = False
            for f in metodos:
                if f.nome not in rede and any(n in _REDE_FUNCOES or n in rede for n, _, _ in f.chamadas):
                    rede.add(f.nome)
                    mudou = True
        return rede

    # -- fachada -------------------------------------------------------------------------------------------------

    def _fachada_guardada(self) -> set[str]:
        """Métodos de `Verifica` que o módulo da fachada envolve em `_guardar`/`sob_guarda` (laços `setattr`)."""
        mod = self.mods.get("service.py")
        if mod is None:
            return set()
        nomes: dict[str, set[str]] = {}
        guardados: set[str] = set()
        for no in mod.body:
            if isinstance(no, ast.Assign) and len(no.targets) == 1 and isinstance(no.targets[0], ast.Name):
                nomes[no.targets[0].id] = _literais_str(no.value, nomes)
            if isinstance(no, ast.For) and any(
                    isinstance(c, ast.Call) and _nome_chamada(c) in {"_guardar", "sob_guarda"} for c in ast.walk(no)):
                guardados |= _literais_str(no.iter, nomes)
        return guardados

    # -- guarda --------------------------------------------------------------------------------------------------

    def chamada_de_rede(self, nome: str, no: ast.Call, arquivo: str) -> bool:
        if nome in _REDE_FUNCOES:
            return True
        if nome not in self.metodos_rede or not isinstance(no.func, ast.Attribute):
            return False
        return not _homonimo(no, self.regex.get(arquivo, set()))

    def entrada_guardada(self, f: Funcao) -> bool:
        if set(f.decoradores) & self.decoradores_guarda:
            return True
        if f.classe in self.classes_conector and f.nome in self.entradas:
            return True
        return f.classe == "Verifica" and f.nome in self.fachada

    def coberta(self, f: Funcao, pilha: frozenset = frozenset()) -> bool:
        """A função só roda sob guarda: é entrada guardada, ou todo chamador (por nome) a chama sob guarda."""
        if self.entrada_guardada(f):
            return True
        if f.qual in pilha or f.nome == "<modulo>":
            return False
        if f.dono is not None:  # closure/método de classe local: roda na extensão de quem a define
            return self.coberta(f.dono, pilha | {f.qual})
        chamadores = [(g, guardado) for g in self.funcoes for n, _, guardado in g.chamadas
                      if n == f.nome and g is not f]
        if not chamadores:
            return False
        return all(guardado or self.coberta(g, pilha | {f.qual}) for g, guardado in chamadores)

    def alcanca(self, nome: str, no: ast.Call, arquivo: str, alcance: set[str]) -> bool:
        return self.chamada_de_rede(nome, no, arquivo) or (nome in alcance and not (
            isinstance(no.func, ast.Attribute) and _homonimo(no, self.regex.get(arquivo, set()))))

    def chega_a_rede(self) -> set[str]:
        """Nomes de funções do pacote que chamam a rede, direta ou transitivamente (por nome)."""
        alcance = set(self.metodos_rede) | set(_REDE_FUNCOES)
        mudou = True
        while mudou:
            mudou = False
            for f in self.funcoes:
                if f.nome not in alcance and f.nome != "<modulo>" and any(
                        self.alcanca(n, c, f.arquivo, alcance) for n, c, _ in f.chamadas):
                    alcance.add(f.nome)
                    mudou = True
        return alcance


@pytest.fixture(scope="module")
def indice() -> Indice:
    assert RAIZ.is_dir(), RAIZ
    return Indice()


# --- 1. guarda ----------------------------------------------------------------------------------------------------


def test_lista_de_metodos_de_rede_derivada_do_codigo(indice):
    """A lista não é escrita à mão: vem de `ENTRADAS_DE_REDE` (envolvidas por `__init_subclass__`) e do código."""
    assert {"fetch", "search", "resolve", "health"} <= indice.entradas
    assert indice.entradas <= indice.metodos_rede


def violacoes_guarda(indice: Indice) -> list[str]:
    out = []
    for f in indice.funcoes:
        if (f.arquivo, f.qual) in REDE_SEM_GUARDA_JUSTIFICADOS:
            continue
        soltas = [(n, c) for n, c, guardado in f.chamadas
                  if not guardado and indice.chamada_de_rede(n, c, f.arquivo)]
        if soltas and not indice.coberta(f):
            out += [f"{f.arquivo}:{c.lineno} {f.qual} chama {n} fora da guarda" for n, c in soltas]
    return out


def test_1_toda_chamada_de_rede_sob_guarda(indice):
    assert violacoes_guarda(indice) == []


# --- 2. except em controlador -------------------------------------------------------------------------------------


def _tipos(h: ast.ExceptHandler) -> set[str]:
    if h.type is None:
        return {"BaseException"}
    nos = h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]
    return {getattr(n, "id", getattr(n, "attr", "")) for n in nos}


def _registradoras(indice: Indice) -> set[str]:
    return {f.nome for f in indice.funcoes
            if any(isinstance(n, ast.Attribute) and n.attr in {"categoria", "classificacao"} for n in ast.walk(f.no))}


def _handler_ok(h: ast.ExceptHandler, registradoras: set[str]) -> bool:
    corpo = ast.Module(body=h.body, type_ignores=[])
    if any(isinstance(n, ast.Raise) for n in ast.walk(corpo)):
        return True
    if h.name is None:
        return False
    for n in ast.walk(corpo):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == h.name and n.attr in {
                "categoria", "classificacao"}:
            return True
        if isinstance(n, ast.Call) and _nome_chamada(n) == "getattr" and len(n.args) >= 2 and isinstance(
                n.args[0], ast.Name) and n.args[0].id == h.name and isinstance(n.args[1], ast.Constant) and \
                n.args[1].value in {"categoria", "classificacao"}:
            return True
        if isinstance(n, ast.Call) and _nome_chamada(n) in registradoras and any(
                isinstance(a, ast.Name) and a.id == h.name for a in [*n.args, *(k.value for k in n.keywords)]):
            return True
    return False


def _trys_em_laco(funcao: ast.AST):
    """`try` dentro de `for`/`while` da própria função (não de funções aninhadas): o padrão de controlador, que
    segue para o próximo item depois de uma falha."""
    def andar(no, em_laco):
        for filho in ast.iter_child_nodes(no):
            if isinstance(filho, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            if isinstance(filho, ast.Try) and em_laco:
                yield filho
            yield from andar(filho, em_laco or isinstance(filho, (ast.For, ast.AsyncFor, ast.While)))
    yield from andar(funcao, False)


def _chamadas_em_laco(funcao: ast.AST) -> set[str]:
    """Nomes chamados dentro de `for`/`while` da própria função: o trabalho por item de um controlador."""
    nomes: set[str] = set()

    def andar(no, em_laco):
        for filho in ast.iter_child_nodes(no):
            if isinstance(filho, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if em_laco and isinstance(filho, ast.Call) and _nome_chamada(filho):
                nomes.add(_nome_chamada(filho))
            andar(filho, em_laco or isinstance(filho, (ast.For, ast.AsyncFor, ast.While)))
    andar(funcao, False)
    return nomes


def _todos_os_trys(funcao: ast.AST):
    for no in ast.walk(funcao):
        if isinstance(no, ast.Try):
            yield no


def violacoes_except(indice: Indice) -> list[str]:
    alcance = indice.chega_a_rede()
    registradoras = _registradoras(indice)
    # trabalho por item: funções que algum controlador (laço que chega à rede) chama dentro do laço
    por_item: set[str] = set()
    for f in indice.funcoes:
        em_laco = _chamadas_em_laco(f.no)
        if em_laco & alcance:
            por_item |= em_laco & alcance
    out = []
    for f in indice.funcoes:
        if f.nome == "<modulo>":
            continue
        trys = _todos_os_trys(f.no) if f.nome in por_item else _trys_em_laco(f.no)
        for no in trys:
            chamadas: list = []
            _chamadas(no.body, False, chamadas)
            if not any(indice.alcanca(n, c, f.arquivo, alcance) for n, c, _ in chamadas):
                continue
            ja_capturou = False
            for h in no.handlers:
                tipos = _tipos(h)
                alcanca = "Unavailable" in tipos or (bool(tipos & _CAPTURA_EXC) and not ja_capturou)
                ja_capturou = ja_capturou or bool(tipos & _CAPTURA_EXC)
                if not alcanca or (f.arquivo, f.qual) in EXCEPT_JUSTIFICADOS:
                    continue
                if not _handler_ok(h, registradoras):
                    out.append(f"{f.arquivo}:{h.lineno} {f.qual} engole Unavailable ({', '.join(sorted(tipos))})")
    return out


def test_2_controlador_nao_engole_indisponibilidade(indice):
    assert violacoes_except(indice) == []


# --- 3. decode ------------------------------------------------------------------------------------------------------


def violacoes_decode(indice: Indice) -> list[str]:
    out = []
    for f in indice.funcoes:
        if f.arquivo == "texto_resposta.py":
            continue
        for nome, c, _ in f.chamadas:
            if nome == "decode" and isinstance(c.func, ast.Attribute) and (f.arquivo, f.qual.split(".")[-1]) not in \
                    DECODE_JUSTIFICADOS:
                out.append(f"{f.arquivo}:{c.lineno} {f.qual}: {ast.unparse(c)[:80]}")
    return out


def test_3_decode_so_na_interpretacao_unica(indice):
    assert violacoes_decode(indice) == []


def test_3_justificativas_nao_sobram(indice):
    """Justificativa sem `.decode(` correspondente é lixo que esconderia um caminho futuro."""
    usados = {(f.arquivo, f.qual.split(".")[-1]) for f in indice.funcoes
              for n, c, _ in f.chamadas if n == "decode" and isinstance(c.func, ast.Attribute)}
    if RAIZ == Path(__file__).resolve().parents[1] / "freoa_verifica":
        assert set(DECODE_JUSTIFICADOS) <= usados, set(DECODE_JUSTIFICADOS) - usados


# --- 4. parser não recebe bytes de resposta ----------------------------------------------------------------------


def _parsers(indice: Indice) -> set[str]:
    nomes = {f.nome for f in indice.funcoes if f.arquivo.startswith("parsers/") and f.nome != "<modulo>"}
    nomes |= {f.nome for f in indice.funcoes if f.nome.lstrip("_").startswith("parse")}
    return nomes | _PARSERS_EXTRA


def _bytes_crus(no: ast.AST, contaminados: set[str]) -> bool:
    """A expressão PODE ser os próprios bytes de resposta/blob (fluxo de valor, sem atravessar chamadas)."""
    if isinstance(no, ast.Attribute) and no.attr == "body":
        return True
    if isinstance(no, ast.Name):
        return no.id in contaminados
    if isinstance(no, ast.Call):
        return _nome_chamada(no) in {"get_blob", "read_bytes", "bytes", "bytearray"} and (
            _nome_chamada(no) in {"get_blob", "read_bytes"} or any(_bytes_crus(a, contaminados) for a in no.args))
    if isinstance(no, ast.Subscript):
        return _bytes_crus(no.value, contaminados)
    if isinstance(no, ast.IfExp):
        return _bytes_crus(no.body, contaminados) or _bytes_crus(no.orelse, contaminados)
    if isinstance(no, ast.BoolOp):
        return any(_bytes_crus(v, contaminados) for v in no.values)
    if isinstance(no, ast.NamedExpr):
        return _bytes_crus(no.value, contaminados)
    return False


def violacoes_parser(indice: Indice) -> list[str]:
    parsers = _parsers(indice)
    out = []
    for f in indice.funcoes:
        if f.arquivo == "texto_resposta.py" or f.arquivo.startswith("parsers/"):
            continue  # a função única e os próprios parsers (entrada já decidida pelo chamador)
        contaminados: set[str] = set()
        for no in ast.walk(f.no):
            if isinstance(no, ast.Assign) and _bytes_crus(no.value, contaminados):
                contaminados |= {t.id for t in no.targets if isinstance(t, ast.Name)}
        for nome, c, _ in f.chamadas:
            eh_parser = nome in parsers or nome.lstrip("_").startswith("parse")
            if eh_parser and any(_bytes_crus(a, contaminados) for a in [*c.args, *(k.value for k in c.keywords)]):
                out.append(f"{f.arquivo}:{c.lineno} {f.qual}: {ast.unparse(c)[:90]}")
    return out


def test_4_parser_nunca_recebe_bytes_de_resposta(indice):
    assert violacoes_parser(indice) == []


# --- os detectores detectam (negativos sintéticos) ----------------------------------------------------------------


def test_detectores_acusam_padroes_proibidos(tmp_path):
    """Cada regra acusa o padrão que proíbe numa árvore sintética mínima (sem isto, um detector mudo passaria)."""
    raiz = tmp_path / "freoa_verifica"
    (raiz / "connectors").mkdir(parents=True)
    (raiz / "connectors" / "base.py").write_text(
        "ENTRADAS_DE_REDE = ('fetch', 'search', 'resolve', 'health')\n"
        "class Connector:\n"
        "    def __init_subclass__(cls):\n"
        "        sob_guarda(cls)\n", encoding="utf-8")
    (raiz / "connectors" / "x.py").write_text(
        "class X(Connector):\n"
        "    def fetch(self, c):\n        return connector_fetch(c)\n"
        "    def _lista(self):\n        return connector_fetch('u')\n", encoding="utf-8")
    (raiz / "ctrl.py").write_text(
        "def solto(conn, cands):\n"
        "    for c in cands:\n"
        "        try:\n            conn.fetch(c)\n"
        "        except Exception:\n            continue\n"
        "def le(resp):\n"
        "    dados = resp.body if resp else None\n"
        "    parse_x(dados)\n"
        "    return resp.body.decode('utf-8')\n", encoding="utf-8")
    global RAIZ
    antiga, RAIZ = RAIZ, raiz
    try:
        ind = Indice()
        assert any("solto chama fetch" in v for v in violacoes_guarda(ind))
        assert any("_lista" in v for v in violacoes_guarda(ind))  # método de rede privado sem chamador guardado
        assert any("solto engole" in v for v in violacoes_except(ind))
        assert any("ctrl.py" in v for v in violacoes_decode(ind))
        assert any("parse_x(dados)" in v for v in violacoes_parser(ind))
    finally:
        RAIZ = antiga
