"""Executor da Porta L (IL.3-a, A1): os predicados das seções 1 a 4 da matriz IL.1 (`il1-matriz-porta-l.md`, congelada).

Uso:
  python scripts/porta_l.py --conjunto <jsonl> --mutantes <jsonl> --home <home> --modo local|remoto --saida <relatorio.json>
                            [--somente-tabela] [--sintetico [--congelamento <outro.md>]]

Sem rede própria: chama só a fachada pública Python (`obter_dispositivo`, `verificar_citacao`, `obter_evidencia`), nunca
função interna. No modo `local` o processo bloqueia a rede e FALHA FECHADO ao detectar qualquer tentativa (código 3); no
modo `remoto` a federação ao vivo é a do serviço; o bloqueio cobre o ciclo completo (construção, uso e fechamento do
serviço) e as primitivas de saída (connect, send, sendall, sendto, resolução), com autoteste que falha se alguma escapar.
O executor não lê a reserva por caminho fixo: recebe os arquivos por argumento, lê cada um UMA vez, confere o SHA-256 desses
bytes contra `il1-congelamento.md` e analisa e declara os mesmos bytes, recusando arquivo divergente (código 2). Só a
execução com o congelamento normativo do repositório, o serviço real e sem `--sintetico` é QUALIFICANTE; qualquer outra
(`--sintetico` com outro congelamento, serviço injetado) sai marcada NÃO QUALIFICANTE no relatório.

A comparação textual (seção 7) é a do validador congelado, importada, não copiada: `norm` daqui é o mesmo objeto de
`scripts/porta_l/validar_gabaritos_porta_l.py`. Denominador por unidade de independência (seção 2); confirmação indevida
pelos quatro itens da seção 2 em todos os casos e mutantes (eliminatória, reprova todas as capacidades); mutantes da
seção 3 pela chamada declarada no próprio mutante, examinando TODAS as passadas medidas; veto comum de indisponibilidade
(`unavailable`, `indisponivel`, `parcial` em qualquer dimensão) antes de qualquer acerto; cadeia e predecessor confrontados
sem tolerância com `gabarito.cadeia` e `gabarito.ultima_versao_anterior`; p95 da seção 4 (uma passada de aquecimento descartada e três medidas,
posto mais próximo). Relatório por capacidade; `--somente-tabela` emite só aprovado/reprovado (guardião na reserva, D6).

Código de saída: 0 todas as capacidades aprovadas; 1 alguma reprovada; 2 entrada ou hash recusados; 3 falha fechada
(rede detectada no modo local, ou erro interno do executor); 4 modo local recusado por haver socket preexistente.

Garantia do modo local (RED2/F2): iniciado pela CLI (`python scripts/porta_l.py`), o gancho de auditoria é a primeira
instrução efetiva do processo, antes de importar `freoa_verifica` ou qualquer módulo de rede, e a CLI recusa executar (código
4, sem relatório) se um socket já existir na instalação da guarda. Logo nenhum socket nasce sem passar pelo evento
`socket.__new__`, auditado e barrado. Fora da garantia: `send`/`sendall` sobre socket criado antes do gancho ou fora do
processo do executor, e o uso do módulo como biblioteca (importado por outro processo, sem gancho precoce).
"""

from __future__ import annotations

import sys

# Mecanismo PRINCIPAL (R3-5): gancho de auditoria do CPython (PEP 578). O interpretador dispara o evento em TODA operação de
# rede, qualquer que seja o nome, alias ou referência usada para chegar ao tipo C (`socket.socket`, `socket.SocketType`,
# `_socket.socket`, referência guardada antes da guarda): o gancho é por EVENTO. `sys.addaudithook` não tem remoção; por
# isso o gancho é instalado uma vez e só age enquanto há uma guarda ativa (fora dela é inerte). Registra a tentativa e
# aborta (`RedeBloqueada`); `verificar()` falha o executor mesmo que o chamador tenha engolido a exceção. A substituição
# de métodos abaixo é camada adicional (também barra a chamada de módulo antes do evento) e não é a garantia.
EVENTOS_DE_REDE = ("socket.__new__", "socket.bind", "socket.connect", "socket.sendto", "socket.sendmsg",
                   "socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr", "socket.getnameinfo",
                   "http.client.connect", "http.client.send", "urllib.Request")
_EVENTO_COM_SOCKET_NO_ARG0 = ("socket.__new__", "socket.bind", "socket.connect", "socket.sendto", "socket.sendmsg")
_EVENTOS_BARRADOS = EVENTOS_DE_REDE  # o que o gancho barra (variável própria: o teste de mutante a reduz num subprocesso)
_GUARDAS_ATIVAS: list[Any] = []
_gancho_instalado = False
_GANCHO_PRECOCE = False  # verdadeiro só quando o gancho foi instalado como primeira instrução efetiva do processo (CLI)
_CRIADOS_ANTES: list[str] = []  # eventos `socket.__new__` vistos fora de qualquer guarda desde a instalação do gancho


def _gancho_de_auditoria(evento: str, args: tuple) -> None:
    if not _GUARDAS_ATIVAS:
        if evento == "socket.__new__" and len(_CRIADOS_ANTES) < 8:
            _CRIADOS_ANTES.append(repr(args[1:])[:80])  # criação observada antes de qualquer guarda (F2)
        return
    if evento not in _EVENTOS_BARRADOS:
        return
    # `sys.modules`, não `socket`: o gancho pode estar instalado antes de o módulo ser importado (F2)
    af_unix = getattr(sys.modules.get("socket"), "AF_UNIX", None)
    if evento == "socket.__new__" and len(args) > 1 and af_unix is not None and args[1] == af_unix:
        return  # soquete local do sistema (sem rede): a criação de AF_INET/AF_INET6/outros é que é barrada
    resto = args[1:] if evento in _EVENTO_COM_SOCKET_NO_ARG0 else args
    for guarda in list(_GUARDAS_ATIVAS):
        guarda.tentativas.append(f"audit:{evento}:{resto!r}"[:200])
    raise RedeBloqueada(f"rede bloqueada no modo local (evento de auditoria {evento})")


def _instalar_gancho() -> None:
    global _gancho_instalado
    if not _gancho_instalado:
        sys.addaudithook(_gancho_de_auditoria)
        _gancho_instalado = True


def _instalar_gancho_precoce() -> None:
    """RED2/F2. Chamada ANTES de importar `freoa_verifica` ou qualquer módulo de rede (só `sys` foi importado). Desde aqui
    todo evento `socket.__new__` do processo passa pelo gancho: sem guarda ativa ele é só registrado em `_CRIADOS_ANTES`; com
    guarda é barrado. `main` recusa o modo local (código 4, sem relatório) se algum foi registrado ou se, na instalação da
    guarda, o coletor de lixo ainda enxerga objeto de socket com descritor aberto (detecção sem criar socket)."""
    global _GANCHO_PRECOCE
    _instalar_gancho()
    _GANCHO_PRECOCE = True


if __name__ == "__main__":  # primeira instrução efetiva da CLI: antes dos demais imports (F2)
    _instalar_gancho_precoce()

import argparse  # noqa: E402
import datetime  # noqa: E402
import hashlib  # noqa: E402
import importlib  # noqa: E402
import importlib.util  # noqa: E402
import inspect  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import socket  # noqa: E402
import time  # noqa: E402
from collections import defaultdict  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402
from urllib.parse import urlsplit  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
VERSAO_EXECUTOR = "1"
CAPS = ("a", "b", "c", "d", "e")
MOTIVO_CONFERENCIA_MATERIAL_NAO_IMPLEMENTADA = "conferencia_material_da_cadeia_nao_implementada"
FUNCOES = {"obter_dispositivo", "verificar_citacao", "obter_evidencia"}
PISO_ACERTO = {"a": 0.95, "b": 0.95, "c": 0.80, "d": 0.90, "e": 0.90}
LIMITE_P95_S = {"local": 5.0, "remoto": 20.0}
MIN_UNIDADES, MIN_NORMAS = 8, 4
PASSADAS_AQUECIMENTO, PASSADAS_MEDIDAS = 1, 3
CONGELAMENTO_PADRAO = RAIZ / "docs" / "auditoria" / "1.4.0" / "il1-congelamento.md"
CONGELAMENTO_SHA256 = "ec8702b7af393958877393b6a539a076c69e9539ffcd04fb148f0b0453264d5b"  # il1-congelamento.md (LF)


# --------------------------------------------------------------------------------------------------------------
# Comparação textual única: a do validador congelado, importada (matriz, seção 7; il3-especificacao A1.1)
# --------------------------------------------------------------------------------------------------------------
def _carregar_validador():
    caminho = Path(__file__).resolve().parent / "porta_l" / "validar_gabaritos_porta_l.py"
    spec = importlib.util.spec_from_file_location("validar_gabaritos_porta_l", caminho)
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("validar_gabaritos_porta_l", mod)
    spec.loader.exec_module(mod)
    return mod


VALIDADOR = _carregar_validador()
norm = VALIDADOR.norm  # o mesmo objeto: nada de cópia da normalização


def igual_texto(a: Any, b: Any) -> bool:
    return isinstance(a, str) and isinstance(b, str) and norm(a) == norm(b)


# --------------------------------------------------------------------------------------------------------------
# Rede: bloqueio no processo, com falha fechada (matriz, seção 4; il3-especificacao A1.6)
# --------------------------------------------------------------------------------------------------------------
class RedeBloqueada(OSError):
    """Levantada dentro do processo quando algo tenta usar a rede no modo local."""


class ViolacaoDeRede(RuntimeError):
    """Tentativa de rede detectada no modo local: o executor aborta (falha fechada)."""


def _modulo_opcional(nome: str) -> Any:
    try:
        return importlib.import_module(nome)
    except ImportError:  # plataforma sem o módulo: não há primitiva a barrar
        return None


class BloqueioDeRede:
    """Bloqueia no processo toda operação de saída (criação de soquete de rede, bind, conexão, envio, resolução de nomes)
    pelo gancho de auditoria e, em camada adicional, pela substituição das primitivas; guarda cada tentativa.
    `verificar()` levanta se houve alguma, mesmo que o código chamado tenha engolido a exceção. O autoteste exerce cada
    evento e cada primitiva, sem criar soquete nem produzir tráfego, e falha se qualquer uma escapar."""

    # primitivas de saída bloqueadas: métodos de socket (inclusive os herdados do tipo C), funções de módulo e SSL
    _SOCKET = ("connect", "connect_ex", "send", "sendall", "sendto", "sendmsg", "sendfile")
    _MODULO = ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "getnameinfo")
    _SSL = ("send", "sendall", "sendto", "write")

    def __init__(self) -> None:
        self.tentativas: list[str] = []
        self._orig: list[tuple[Any, str, Any, bool]] = []

    def _barrar(self, nome: str):
        def barreira(*a, **k):
            alvo = a[1] if nome.endswith(("connect", "connect_ex", "sendto")) and len(a) > 1 else (a[0] if a else "")
            self.tentativas.append(f"{nome}:{alvo!r}"[:200])
            raise RedeBloqueada(f"rede bloqueada no modo local ({nome})")
        return barreira

    def _alvos(self) -> list[tuple[Any, str]]:
        alvos: list[tuple[Any, str]] = [(socket.socket, n) for n in self._SOCKET]
        alvos += [(socket, n) for n in self._MODULO]
        _socket, ssl = _modulo_opcional("_socket"), _modulo_opcional("ssl")
        if _socket is not None:
            alvos += [(_socket, n) for n in self._MODULO if n != "create_connection" and hasattr(_socket, n)]
        if ssl is not None:
            alvos += [(ssl.SSLSocket, n) for n in self._SSL if hasattr(ssl.SSLSocket, n)]
        return [(o, n) for o, n in alvos if hasattr(o, n)]

    def __enter__(self):
        _instalar_gancho()
        _GUARDAS_ATIVAS.append(self)
        for obj, atributo in self._alvos():
            self._orig.append((obj, atributo, getattr(obj, atributo), atributo in vars(obj)))
            setattr(obj, atributo, self._barrar(f"{getattr(obj, '__name__', 'socket')}.{atributo}"))
        _socket = _modulo_opcional("_socket")
        if _socket is not None and hasattr(_socket, "socket"):
            # `_socket.socket` é tipo C imutável: o nome do módulo passa a apontar para uma subclasse cujos métodos de
            # conexão e envio são as barreiras; quem constrói `_socket.socket(...)` na guarda recebe o tipo guardado
            base = _socket.socket
            barreiras = {n: self._barrar(f"_socket.socket.{n}") for n in self._SOCKET if hasattr(base, n)}
            self._orig.append((_socket, "socket", base, True))
            _socket.socket = type("socket", (base,), barreiras)
        return self

    def __exit__(self, *exc):
        if self in _GUARDAS_ATIVAS:
            _GUARDAS_ATIVAS.remove(self)
        for obj, atributo, original, proprio in reversed(self._orig):
            if proprio:
                setattr(obj, atributo, original)
            else:  # herdado do tipo base: volta a herdar em vez de fixar a cópia na subclasse
                delattr(obj, atributo)
        self._orig.clear()
        return False

    def verificar(self) -> None:
        if self.tentativas:
            raise ViolacaoDeRede(f"tentativa de rede no modo local: {self.tentativas[0]}")

    def provas(self) -> list[tuple[str, Any]]:
        """Uma prova por entrada protegida: (nome, chamada). Os argumentos são inválidos de propósito: se a barreira
        faltar, a primitiva real falha sozinha antes de qualquer envio ou consulta (nenhum tráfego, nem local)."""
        nada = object()  # endereço/nome inválido: TypeError na primitiva real, antes de qualquer saída
        _socket, ssl = _modulo_opcional("_socket"), _modulo_opcional("ssl")

        def em(tipo, metodo, *args):
            def chamar():
                # `__new__` sem `__init__`: objeto sem descritor de arquivo (nenhum soquete do sistema é criado)
                getattr(tipo.__new__(tipo), metodo)(*args)
            return chamar

        args_socket = {"connect": (nada,), "connect_ex": (nada,), "send": (b"x",), "sendall": (b"x",),
                       "sendto": (b"x", nada), "sendmsg": ([b"x"], [], 0, nada),
                       "sendfile": (__import__("io").BytesIO(b"x"),)}
        provas: list[tuple[str, Any]] = []
        for n in self._SOCKET:
            if hasattr(socket.socket, n):  # primitiva inexistente nesta plataforma: nada a barrar
                provas.append((f"socket.{n}", em(socket.socket, n, *args_socket[n])))
            if _socket is not None and hasattr(_socket, "socket") and hasattr(_socket.socket, n):
                provas.append((f"_socket.socket.{n}", lambda n=n: em(_socket.socket, n, *args_socket[n])()))
        args_modulo = {"create_connection": (nada,), "getaddrinfo": (nada, 80), "gethostbyname": (nada,),
                       "gethostbyname_ex": (nada,), "gethostbyaddr": (nada,), "getnameinfo": (nada, 0)}
        for n in self._MODULO:
            if hasattr(socket, n):
                provas.append((f"socket.{n}", lambda n=n: getattr(socket, n)(*args_modulo[n])))
            if _socket is not None and n != "create_connection" and hasattr(_socket, n):
                provas.append((f"_socket.{n}", lambda n=n: getattr(_socket, n)(*args_modulo[n])))
        if ssl is not None:
            for n in self._SSL:
                if hasattr(ssl.SSLSocket, n):
                    provas.append((f"ssl.{n}", lambda n=n: getattr(ssl.SSLSocket, n)(nada, b"x")))
        # gancho de auditoria: cada evento é disparado de forma sintética (`sys.audit`), sem soquete e sem tráfego
        sintetico = {"socket.__new__": (None, socket.AF_INET, socket.SOCK_STREAM, 0),
                     "socket.bind": (None, ("203.0.113.1", 9)), "socket.connect": (None, ("203.0.113.1", 9)),
                     "socket.sendto": (None, ("203.0.113.1", 9)), "socket.sendmsg": (None, ("203.0.113.1", 9)),
                     "socket.getaddrinfo": ("example.invalid", 80, 0, 0, 0, 0), "socket.gethostbyname": ("example.invalid",),
                     "socket.gethostbyaddr": ("203.0.113.1",), "socket.getnameinfo": (("203.0.113.1", 9), 0),
                     "http.client.connect": (None, "example.invalid", 80), "http.client.send": (None, b"x"),
                     "urllib.Request": ("http://example.invalid/", None, {}, "GET")}
        for evento in EVENTOS_DE_REDE:
            provas.append((f"auditoria:{evento}", lambda e=evento: sys.audit(e, *sintetico[e])))
        # o evento de criação dispara pelo tipo C, qualquer que seja o alias; a família inválida faz o sistema recusar
        # a criação, de modo que nenhum soquete existe com ou sem o gancho
        for rotulo, tipo in (("socket.socket", socket.socket), ("socket.SocketType", getattr(socket, "SocketType", None)),
                             ("_socket.socket", getattr(_socket, "socket", None))):
            if tipo is not None:
                provas.append((f"auditoria:{rotulo}(familia inválida)", lambda t=tipo: t(65535, socket.SOCK_STREAM)))
        return provas

    def autoteste(self) -> None:
        """Falha fechada: exerce CADA entrada bloqueada (`provas`) e levanta, nomeando-a, se qualquer uma não for barrada."""
        escaparam: list[str] = []
        for nome, prova in self.provas():
            try:
                prova()
            except RedeBloqueada:
                continue
            except Exception as exc:  # noqa: BLE001 - outra coisa que não a barreira: a primitiva escapou
                nome = f"{nome} ({type(exc).__name__})"
            escaparam.append(nome)
        self.tentativas.clear()
        if escaparam:
            raise ViolacaoDeRede(f"o bloqueio de rede não está efetivo ({', '.join(escaparam)}); o executor não roda no "
                                 f"modo local")


# --------------------------------------------------------------------------------------------------------------
# Congelamento: o executor confere os arquivos recebidos contra il1-congelamento.md (A1.8)
# --------------------------------------------------------------------------------------------------------------
def _papeis(texto: str) -> dict[str, str]:
    papeis: dict[str, str] = {}
    for linha in texto.splitlines():
        cel = [c.strip() for c in linha.strip().strip("|").split("|")]
        if len(cel) < 3 or not re.fullmatch(r"`[0-9a-f]{64}`", cel[2]):
            continue
        rotulo = cel[0].lower()
        if rotulo.startswith("mutantes do desenvolvimento"):
            papeis["desenvolvimento/mutantes"] = cel[2].strip("`")
        elif rotulo.startswith("mutantes da reserva"):
            papeis["reserva/mutantes"] = cel[2].strip("`")
        elif rotulo.startswith("desenvolvimento ("):
            papeis["desenvolvimento/conjunto"] = cel[2].strip("`")
        elif rotulo.startswith("reserva ("):
            papeis["reserva/conjunto"] = cel[2].strip("`")
    faltam = {"desenvolvimento/conjunto", "desenvolvimento/mutantes", "reserva/conjunto", "reserva/mutantes"} - set(papeis)
    if faltam:
        raise ValueError(f"congelamento sem os hashes de {sorted(faltam)}")
    return papeis


def hashes_congelados(md: Path) -> dict[str, str]:
    """Papel -> SHA-256 das linhas da tabela do congelamento: conjunto e mutantes do desenvolvimento e da reserva."""
    return _papeis(Path(md).read_bytes().decode("utf-8"))


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_arquivo(p: Path) -> str:
    return sha256_bytes(Path(p).read_bytes())


def congelamento_normativo(md: Path, dados: bytes | None = None) -> bool:
    """O congelamento é o normativo do repositório: o mesmo caminho E os mesmos bytes (fins de linha normalizados) que o
    hash fixado aqui. Qualquer outro Markdown de hashes é só ferramenta de teste e nunca qualifica. Com `dados`, autentica
    os bytes JÁ lidos (o chamador lê o manifesto uma única vez)."""
    try:
        md = Path(md)
        if md.resolve() != CONGELAMENTO_PADRAO.resolve():
            return False
        dados = md.read_bytes() if dados is None else dados
        return sha256_bytes(dados.replace(b"\r\n", b"\n")) == CONGELAMENTO_SHA256
    except OSError:
        return False


@dataclass
class Entradas:
    """As entradas lidas UMA vez: os bytes conferidos contra o congelamento são os analisados e os do relatório."""
    conjunto: str
    casos: list[dict]
    mutantes: list[dict]
    conjunto_sha256: str
    mutantes_sha256: str
    congelamento_sha256: str


def _jsonl_bytes(nome: str, dados: bytes) -> list[dict]:
    out = []
    for n, linha in enumerate(dados.decode("utf-8").splitlines(), 1):
        if linha.strip():
            try:
                obj = json.loads(linha)
            except ValueError as exc:
                raise ValueError(f"{nome}:{n}: JSON inválido ({exc})") from exc
            if not isinstance(obj, dict):
                raise ValueError(f"{nome}:{n}: registro não é objeto")
            out.append(obj)
    return out


def carregar_entradas(conjunto: Path, mutantes: Path, md: Path | bytes) -> Entradas:
    """Lê cada arquivo uma única vez, confere os bytes lidos contra o congelamento e interpreta esses mesmos bytes.
    `md` pode ser o manifesto já lido (bytes), para que quem o autenticou seja quem o consome. Levanta se não são os
    arquivos congelados do MESMO conjunto."""
    dmd = md if isinstance(md, bytes) else Path(md).read_bytes()
    papeis = _papeis(dmd.decode("utf-8"))
    bc, bm = Path(conjunto).read_bytes(), Path(mutantes).read_bytes()
    hc, hm = sha256_bytes(bc), sha256_bytes(bm)
    for nome in ("desenvolvimento", "reserva"):
        if hc == papeis[f"{nome}/conjunto"] and hm == papeis[f"{nome}/mutantes"]:
            return Entradas(nome, _jsonl_bytes(str(conjunto), bc), _jsonl_bytes(str(mutantes), bm), hc, hm,
                            sha256_bytes(dmd))
    raise ValueError("arquivo divergente do congelamento (il1-congelamento.md): o conjunto e os mutantes têm de ser os "
                     "congelados do mesmo conjunto")


def conferir_congelamento(conjunto: Path, mutantes: Path, md: Path) -> str:
    """Devolve 'desenvolvimento' ou 'reserva' se os dois arquivos são os congelados do MESMO conjunto; senão levanta."""
    return carregar_entradas(conjunto, mutantes, md).conjunto


# --------------------------------------------------------------------------------------------------------------
# Unidade de independência e denominador (matriz, seção 2)
# --------------------------------------------------------------------------------------------------------------
def unidade(caso: dict) -> str:
    """O EVENTO normativo da redação do gabarito (identificador canônico); sem evento válido, o caso é sua própria
    unidade (falha fechado: nunca some do denominador)."""
    ev = VALIDADOR.evento_do_caso(caso)
    return ev if ev is not None else f"caso:{caso.get('id')}"


def representantes(casos: list[dict]) -> dict[str, str]:
    """Unidade -> id do caso que conta no denominador: o de menor id em ordem lexicográfica (seleção determinística)."""
    por: dict[str, list[str]] = defaultdict(list)
    for c in casos:
        por[unidade(c)].append(c["id"])
    return {u: min(ids) for u, ids in por.items()}


def eh_acerto(resultado: str) -> bool:
    """Só `acerto` entra no numerador; `unavailable`, `indisponivel` e `parcial` ficam no denominador (seção 2)."""
    return resultado == "acerto"


# --------------------------------------------------------------------------------------------------------------
# Predicados por capacidade (seções 1 e 1.1) e confirmação indevida (seção 2)
# --------------------------------------------------------------------------------------------------------------
def _dim(resp: dict, nome: str) -> dict:
    d = resp.get(nome) if isinstance(resp, dict) else None
    return d if isinstance(d, dict) else {}


ESTADOS_NAO_NUMERADOR = ("unavailable", "indisponivel", "parcial")  # matriz, seção 2: nunca no numerador


def _declara_indisponibilidade(x: Any, prof: int = 0) -> bool:
    """`status` indisponível em qualquer dicionário, em qualquer profundidade (dimensões, predecessor, elos da cadeia,
    evidências), ou `indisponibilidades_temporais` não vazia (a lista que o serviço emite quando a obtenção do material
    temporal falha). Profundidade excessiva: falha fechado."""
    if prof > 16:
        return True
    if isinstance(x, dict):
        if x.get("status") in ESTADOS_NAO_NUMERADOR or x.get("indisponibilidades_temporais") not in (None, [], ()):
            return True
        return any(_declara_indisponibilidade(v, prof + 1) for v in x.values())
    if isinstance(x, (list, tuple)):
        return any(_declara_indisponibilidade(v, prof + 1) for v in x)
    return False


def indisponivel(resp: dict) -> bool:
    """Veto comum (matriz, seção 2): `unavailable`, `indisponivel` ou `parcial` no estado agregado ou em QUALQUER
    ponto da resposta, e `indisponibilidades_temporais` não vazia, tiram o caso do numerador: operação que declara
    falha na obtenção do seu material não é entrega integral."""
    return not isinstance(resp, dict) or _declara_indisponibilidade(resp)


def _verificado(resp: dict) -> bool:
    return any(_dim(resp, n).get("status") == "verified" for n in ("text", "temporal", "vigencia"))


def _data_iso(s: Any) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(s) if isinstance(s, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) else None
    except ValueError:
        return None


def fundamento_ok(fund: Any, data_d: Any, svc: Any) -> tuple[bool, str]:
    """1.1, `verificado_para_D`: tipo `versao_oficial_na_data`, `capture_id` recuperável por `obter_evidencia` (status
    `encontrada`) cujo `sha256` confere, e data menor ou igual a D."""
    if not isinstance(fund, dict):
        return False, "fundamento_temporal ausente"
    if fund.get("tipo") != "versao_oficial_na_data":
        return False, "fundamento_temporal.tipo diferente de versao_oficial_na_data"
    cid = fund.get("capture_id")
    if not isinstance(cid, str) or not cid:
        return False, "fundamento_temporal sem capture_id"
    try:
        ev = svc.obter_evidencia(cid)
    except Exception as exc:  # noqa: BLE001
        return False, f"capture_id não recuperável ({type(exc).__name__})"
    if not isinstance(ev, dict) or ev.get("status") != "encontrada":
        return False, "capture_id não recuperável por obter_evidencia"
    sha = fund.get("sha256")
    if not isinstance(sha, str) or not sha or sha != _dim(ev, "metadados").get("sha256"):
        return False, "sha256 do fundamento não confere com a captura"
    d, f = _data_iso(data_d), _data_iso(fund.get("data"))
    if d is None or f is None or f > d:
        return False, "data do fundamento ausente ou posterior a D"
    return True, ""


def _ato_canonico(ato: Any) -> str | None:
    if isinstance(ato, str):
        return VALIDADOR.canon_fam(ato)
    if isinstance(ato, dict):
        esp, num, ano = ato.get("especie"), str(ato.get("numero") or "").replace(".", ""), ato.get("ano")
        return VALIDADOR.canon(esp, num, ano) if esp and num and ano else None
    return None


def _tem_texto(x: Any) -> bool:
    return isinstance(x, str) and bool(x.strip())


def _evidencia_valida(ev: Any, svc: Any) -> tuple[bool, str]:
    """Evidência efetiva: `capture_id` recuperável por `obter_evidencia` no serviço avaliado (status `encontrada`) e
    `sha256` (64 hex) igual ao da captura. Texto qualquer ou hash solto não é evidência."""
    if not isinstance(ev, dict):
        return False, "evidência ausente"
    cid, sha = ev.get("capture_id"), ev.get("sha256")
    if not _tem_texto(cid):
        return False, "evidência sem capture_id"
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
        return False, "evidência sem sha256 de 64 hex"
    try:
        rec = svc.obter_evidencia(cid)
    except Exception as exc:  # noqa: BLE001
        return False, f"capture_id não recuperável ({type(exc).__name__})"
    if not isinstance(rec, dict) or rec.get("status") != "encontrada":
        return False, "capture_id não recuperável por obter_evidencia"
    if _dim(rec, "metadados").get("sha256") != sha:
        return False, "sha256 da evidência não confere com a captura"
    return True, ""


_PAGINAS_EVIDENCIA = 40  # teto de páginas lidas de uma captura (50.000 caracteres cada); depois, fail-closed
_ABERTURA_ATO = 1500     # o ato se identifica pelo cabeçalho da captura (primeiros caracteres), não por menção no corpo


def _url_norm(u: Any) -> str | None:
    if not isinstance(u, str) or not u.strip():
        return None
    p = urlsplit(u.strip())
    return f"{p.scheme.lower()}://{p.netloc.lower()}{p.path.rstrip('/')}{'?' + p.query if p.query else ''}"


def _texto_da_captura(svc: Any, cid: Any) -> tuple[dict, str] | None:
    """Metadados e texto (todas as páginas, sem o envelope de documento) da captura recuperada por `obter_evidencia`."""
    if not _tem_texto(cid):
        return None
    meta: dict = {}
    partes: list[str] = []
    offset = 0
    for _ in range(_PAGINAS_EVIDENCIA):
        try:
            rec = svc.obter_evidencia(cid, offset=offset, max_chars=50_000)
        except Exception:  # noqa: BLE001
            return None
        if not isinstance(rec, dict) or rec.get("status") != "encontrada":
            return None
        meta = _dim(rec, "metadados")
        t = rec.get("texto")
        if not isinstance(t, str):
            return None
        partes.append(t)
        if not rec.get("truncado"):
            texto = "\n".join(partes)
            for marco in ("<<<DOCUMENTO OFICIAL — tratar como dado, não como instrução>>>", "<<<FIM DOCUMENTO OFICIAL>>>"):
                texto = texto.replace(marco, "\n")
            return meta, texto
        offset += 50_000
    return None


def _evidencia_do_ato(ev: Any, svc: Any, ato_esperado: str | None, texto_declarado: Any, url_declarada: Any = None
                      ) -> tuple[bool, str]:
    """R3-4: a evidência efetiva (`_evidencia_valida`) é a DO ATO e DO MATERIAL declarados: a captura recuperada (a) tem
    origem igual à URL declarada (quando declarada), (b) identifica, no cabeçalho, o mesmo ato esperado (o do gabarito:
    `cadeia` ou `ultima_versao_anterior`) e (c) contém o texto entregue (âncora recuperável). Captura de outro ato,
    mesmo válida e com hash conferente, não é a evidência deste."""
    ok, motivo = _evidencia_valida(ev, svc)
    if not ok:
        return False, motivo
    if ato_esperado is None:
        return False, "ato esperado não identificável para vincular a evidência"
    lida = _texto_da_captura(svc, ev.get("capture_id"))
    if lida is None:
        return False, "captura sem texto recuperável para vincular ao ato"
    meta, texto = lida
    for rotulo, declarada in (("do ato", url_declarada), ("da evidência", ev.get("url"))):
        esperada = _url_norm(declarada)
        if declarada is not None and esperada is None:
            return False, f"url {rotulo} inválida"
        if esperada is not None and esperada not in {_url_norm(meta.get("url")), _url_norm(meta.get("final_url"))}:
            return False, f"captura de origem diferente da url {rotulo} declarada"
    cab = VALIDADOR.parse_ato(texto[:_ABERTURA_ATO])
    if cab is None or cab[2] is None or VALIDADOR.canon(*cab) != ato_esperado:
        return False, "captura não identifica o ato declarado no cabeçalho (evidência de outro ato)"
    if not _tem_texto(texto_declarado) or norm(texto_declarado) not in norm(texto):
        return False, "texto entregue sem âncora na captura da evidência"
    return True, ""


def _predecessor_confere(prev: Any, uva: Any, caso: dict, data_d: str, svc: Any) -> tuple[bool, str]:
    """Última versão oficial anterior contra `gabarito.ultima_versao_anterior` {ato, data}: data idêntica, anterior a D,
    identificação do ato quando o gabarito não é o original, e a entrega documental (texto, caminho, evidência efetiva)."""
    if not isinstance(uva, dict) or _data_iso(uva.get("data")) is None or not _tem_texto(uva.get("ato")):
        return False, "gabarito sem ultima_versao_anterior {ato, data}"
    if not isinstance(prev, dict):
        return False, "ultima_versao_oficial_anterior ausente"
    d, dp = _data_iso(data_d), _data_iso(prev.get("data"))
    if dp is None:
        return False, "ultima_versao_oficial_anterior sem data"
    if d is None or dp >= d:
        return False, "ultima_versao_oficial_anterior não é anterior a D"
    if prev.get("data") != uva.get("data"):
        return False, f"ultima_versao_oficial_anterior com data {prev.get('data')!r}; esperada {uva.get('data')!r}"
    esperado = VALIDADOR.canon_norma(caso["norma"]) if uva["ato"] == "original" else _ato_canonico(uva["ato"])
    if "ato" in prev or uva["ato"] != "original":
        obtido = _ato_canonico(prev.get("ato")) if prev.get("ato") != "original" else VALIDADOR.canon_norma(caso["norma"])
        if obtido is None or obtido != esperado:
            return False, f"ato da última versão anterior {prev.get('ato')!r} diferente do esperado {uva['ato']!r}"
    if not _tem_texto(prev.get("texto")):
        return False, "ultima_versao_oficial_anterior sem texto"
    cam = prev.get("caminho")
    pc = VALIDADOR.parse_caminho(cam) if isinstance(cam, str) else None
    pe = VALIDADOR.parse_caminho(caso.get("caminho")) if isinstance(caso.get("caminho"), str) else None
    if pc is None or pe is None or VALIDADOR.chave_caminho(pc) != VALIDADOR.chave_caminho(pe):
        return False, "ultima_versao_oficial_anterior sem o caminho do dispositivo pedido"
    ok, motivo = _evidencia_do_ato(prev.get("evidencia"), svc, esperado, prev.get("texto"))
    if not ok:
        return False, f"ultima_versao_oficial_anterior: {motivo}"
    return True, ""


def _cadeia_confere(resp: dict, caso: dict, data_d: str, svc: Any) -> tuple[bool, str]:
    """Última versão oficial anterior e cadeia ordenada de atos alteradores, contra `gabarito.ultima_versao_anterior` e
    `gabarito.cadeia` (1.1), sem tolerância de data. Cada elo entrega o ato (espécie, número, ano, URL), a publicação,
    o `dispositivo_atingido`, a `acao`, o texto e a evidência efetiva do próprio ato; ausência de qualquer um não é acerto."""
    gab = caso.get("gabarito") or {}
    ok, motivo = _predecessor_confere(resp.get("ultima_versao_oficial_anterior"), gab.get("ultima_versao_anterior"),
                                      caso, data_d, svc)
    if not ok:
        return False, motivo
    cadeia = resp.get("cadeia_alteracoes")
    obtida = []
    for item in cadeia if isinstance(cadeia, list) else []:
        item = item if isinstance(item, dict) else {}
        obtida.append((_ato_canonico(item.get("ato")), _dim(item, "publicacao").get("data"), item))
    esperada = [(_ato_canonico(x.get("ato")), x.get("data")) for x in gab.get("cadeia") or [] if isinstance(x, dict)]
    if not esperada:
        return False, "gabarito sem cadeia"
    if len(obtida) != len(esperada):
        return False, f"cadeia com {len(obtida)} atos; esperados {len(esperada)}"
    capturas = {(resp["ultima_versao_oficial_anterior"].get("evidencia") or {}).get("capture_id")}
    for (ao, do, item), (ae, de) in zip(obtida, esperada):
        if ao is None or ao != ae:
            return False, f"ato da cadeia {ao!r} diferente do esperado {ae!r} (ou fora de ordem)"
        if _data_iso(de) is None or do != de:
            return False, f"data de publicação do ato {ae!r} é {do!r}; esperada {de!r}"
        ato = item.get("ato") if isinstance(item.get("ato"), dict) else {}
        faltas = [n for n, v in (("url do ato", ato.get("url")), ("texto", item.get("texto")),
                                 ("dispositivo_atingido", item.get("dispositivo_atingido")), ("acao", item.get("acao")))
                  if not _tem_texto(v)]
        if faltas:
            return False, f"entrega documental incompleta do ato {ae!r}: {', '.join(faltas)}"
        ok, motivo = _evidencia_do_ato(item.get("evidencia"), svc, ae, item.get("texto"), ato.get("url"))
        if not ok:
            return False, f"ato {ae!r}: {motivo}"
        cid = (item.get("evidencia") or {}).get("capture_id")
        if isinstance(cid, str) and cid in capturas:  # o ato alterador tem captura própria: não reaproveita a do predecessor nem a de outro elo
            return False, f"ato {ae!r} com evidência que não é a sua (capture_id repetido)"
        capturas.add(cid)
    return True, ""


def _par_alvo(obra: Any, caminho: Any):
    ob = VALIDADOR.canon_obra(obra) if isinstance(obra, str) else None
    pc = VALIDADOR.parse_caminho(caminho) if isinstance(caminho, str) else None
    return (ob, VALIDADOR.chave_caminho(pc)) if ob is not None and pc is not None else None


def alvos_esperados(gab: dict) -> dict[tuple, tuple]:
    """Chave canônica (obra, caminho) -> chave do alvo do gabarito, incluindo as formas de `alvos_equivalentes`."""
    mapa: dict[tuple, tuple] = {}
    for a in gab.get("alvos") or []:
        k = _par_alvo(a.get("obra"), a.get("caminho")) if isinstance(a, dict) else None
        if k is not None:
            mapa[k] = k
    for chave, formas in (gab.get("alvos_equivalentes") or {}).items():
        m = re.search(r",\s*(art(?:igo)?\.?\s.*)$", chave, re.I) if isinstance(chave, str) else None
        alvo = _par_alvo(chave[:m.start()], m.group(1)) if m else None
        if alvo is None or alvo not in mapa:
            continue
        for f in formas if isinstance(formas, list) else []:
            mf = re.search(r",\s*(art(?:igo)?\.?\s.*)$", f, re.I) if isinstance(f, str) else None
            kf = _par_alvo(f[:mf.start()], mf.group(1)) if mf else None
            if kf is not None:
                mapa[kf] = alvo
    return mapa


def avaliar_resposta(caso: dict, resp: Any, svc: Any) -> dict:
    """Resultado de um caso: {resultado: acerto|erro|parcial|indisponivel, motivo, indevidas: [{item, detalhe}], extra}."""
    gab = caso.get("gabarito") or {}
    cap, tipo = caso.get("capacidade"), gab.get("tipo")
    out: dict[str, Any] = {"resultado": "erro", "motivo": "", "indevidas": [], "extra": {}}
    if not isinstance(resp, dict):
        out["motivo"] = "resposta não é objeto"
        return out
    status = resp.get("status")
    indisp = indisponivel(resp)
    gab_texto = gab.get("texto")
    # (ii) status encontrada com texto diferente do gabarito (qualquer chamada de obtenção)
    if cap != "c" and status == "encontrada" and isinstance(gab_texto, str) and not igual_texto(resp.get("texto"), gab_texto):
        out["indevidas"].append({"item": "ii", "detalhe": "encontrada com texto diferente do gabarito"})
    # (i) verified fora de verificado_para_D
    if tipo != "verificado_para_D" and _verificado(resp):
        out["indevidas"].append({"item": "i", "detalhe": "verified onde o gabarito não é verificado_para_D"})

    if cap == "a":
        ok = (status == "encontrada" and _dim(resp, "evidencia").get("natureza_texto") == "publicacao_original"
              and igual_texto(resp.get("texto"), gab_texto))
        out.update(resultado="acerto" if ok else ("indisponivel" if indisp else "erro"),
                   motivo="" if ok else f"status={status}")
    elif cap == "b":
        if tipo == "revogado_vigente":
            ok = status == "encontrada" and _dim(resp, "vigencia").get("status") == "revogado"
        else:
            ok = status == "encontrada" and igual_texto(resp.get("texto"), gab_texto) and resp.get("truncado") is False
        out["extra"]["truncado"] = resp.get("truncado")
        out.update(resultado="acerto" if ok else ("indisponivel" if indisp else "erro"),
                   motivo="" if ok else f"status={status}")
    elif cap == "d":
        ok = status == "encontrada" and igual_texto(resp.get("texto"), gab_texto)
        out.update(resultado="acerto" if ok else ("indisponivel" if indisp else "erro"),
                   motivo="" if ok else f"status={status}")
    elif cap == "e":
        esperado = alvos_esperados(gab)
        resolvidos: set[tuple] = set()
        excedentes = []
        remissoes = resp.get("remissoes") if isinstance(resp.get("remissoes"), list) else []
        for r in remissoes:  # afirmações de resolução são inspecionadas qualquer que seja o estado agregado
            if not isinstance(r, dict) or r.get("resolvida") is not True:
                continue
            alvo = r.get("alvo") if isinstance(r.get("alvo"), dict) else {}
            k = _par_alvo(alvo.get("obra"), alvo.get("caminho"))
            if k is None or k not in esperado:
                excedentes.append(f"{alvo.get('obra')} {alvo.get('caminho')}")
            else:
                resolvidos.add(esperado[k])
        for e in excedentes:  # (iii) alvo resolvido fora de `alvos` e de seus equivalentes
            out["indevidas"].append({"item": "iii", "detalhe": f"alvo resolvido fora do gabarito: {e}"})
        total = set(esperado.values())
        faltam = total - resolvidos
        if status == "encontrada" and not faltam and not excedentes:
            out.update(resultado="acerto")
        elif status == "encontrada" and resolvidos and not excedentes:
            out.update(resultado="parcial", motivo=f"faltam {len(faltam)} de {len(total)} alvos")
        else:
            out.update(resultado="indisponivel" if indisp else "erro",
                       motivo=f"status={status}; faltam {len(faltam)}; excedentes {len(excedentes)}")
    elif cap == "c":
        _avaliar_c(caso, resp, svc, out, indisp)
    else:
        out["motivo"] = f"capacidade desconhecida: {cap!r}"
    if indisp and out["resultado"] == "acerto":  # veto comum, depois da decisão e sem tocar nas `indevidas`
        out.update(resultado="indisponivel", motivo="indisponibilidade em alguma dimensão: nunca no numerador")
    return out


def _avaliar_c(caso: dict, resp: dict, svc: Any, out: dict, indisp: bool) -> None:
    gab, tipo, d = caso["gabarito"], caso["gabarito"].get("tipo"), caso.get("data")
    t, tm = _dim(resp, "text"), _dim(resp, "temporal")
    if tipo == "verificado_para_D":
        tv, mv = t.get("status") == "verified", tm.get("status") == "verified"
        if tv or mv:
            ok_f, motivo_f = fundamento_ok(resp.get("fundamento_temporal"), d, svc)
            if not ok_f:  # (i) verified com fundamento que não cumpre 1.1
                out["indevidas"].append({"item": "i", "detalhe": f"verified sem fundamento_temporal válido: {motivo_f}"})
        if tv and mv and ok_f:
            out.update(resultado="acerto")
        elif tv or mv:
            out.update(resultado="parcial", motivo="apenas uma das dimensões verified, ou fundamento inválido")
        else:
            out.update(resultado="indisponivel" if indisp else "erro", motivo=f"text={t.get('status')} temporal={tm.get('status')}")
        # `verified` deste tipo não é indevido quando o fundamento cumpre 1.1 (o (i) acima só dispara sem ele)
    elif tipo == "nao_verificado_para_D":
        aceitos = set(gab.get("motivos_aceitos") or [])
        unk = t.get("status") == "unknown" and tm.get("status") == "unknown"
        motivos = {t.get("reason_code"), tm.get("reason_code")}
        com_motivo = unk and all(m in aceitos for m in motivos if m is not None) and None not in motivos
        out["extra"]["nao_verificado_com_motivo"] = bool(com_motivo)
        if com_motivo and "sem_versao_oficial_na_data" in motivos:
            # Segunda redução de escopo (F1, decisão do supervisor): o executor não confere materialmente o texto, a ação
            # e o dispositivo atingido entregues no predecessor e na cadeia; logo o acerto, que depende dessa entrega
            # (matriz IL.1, 1.1), nunca é concedido. `_cadeia_confere` fica preservada, sem uso, para a retomada.
            out.update(resultado="parcial", motivo=MOTIVO_CONFERENCIA_MATERIAL_NAO_IMPLEMENTADA)
        elif com_motivo:
            out.update(resultado="acerto")
        else:
            out.update(resultado="indisponivel" if indisp else "erro", motivo=f"text={t.get('status')} temporal={tm.get('status')}")
    elif tipo == "nao_existia_em_D":
        ok = tm.get("status") == "not_found" and tm.get("reason_code") == "NAO_EXISTIA" and t.get("status") != "verified"
        out.update(resultado="acerto" if ok else ("indisponivel" if indisp else "erro"),
                   motivo="" if ok else f"temporal={tm.get('status')}/{tm.get('reason_code')}")
    else:
        out["motivo"] = f"tipo de gabarito desconhecido: {tipo!r}"


def avaliar_mutante(mut: dict, caso: dict | None, resp: Any) -> dict:
    """Seção 3: rejeitado ou não; mutante não rejeitado é confirmação indevida (seção 2, iv)."""
    tipo = mut.get("tipo")
    if caso is None or not isinstance(resp, dict):
        return {"rejeitado": False, "motivo": "sem caso de origem ou resposta inválida"}
    t, tm = _dim(resp, "text"), _dim(resp, "temporal")
    if tipo == "renumerado":
        texto_orig = (caso.get("gabarito") or {}).get("texto")
        if resp.get("status") == "encontrada" and isinstance(texto_orig, str) and igual_texto(resp.get("texto"), texto_orig):
            return {"rejeitado": False, "motivo": "encontrada com o texto do original"}
        if _verificado(resp):
            return {"rejeitado": False, "motivo": "verified"}
        return {"rejeitado": True, "motivo": ""}
    if tipo == "caractere":
        return {"rejeitado": t.get("status") != "verified", "motivo": "" if t.get("status") != "verified" else "text verified"}
    if tipo == "data_trocada":
        ok = t.get("status") != "verified" and tm.get("status") != "verified"
        return {"rejeitado": ok, "motivo": "" if ok else "text ou temporal verified"}
    return {"rejeitado": False, "motivo": f"tipo de mutante desconhecido: {tipo!r}"}


# --------------------------------------------------------------------------------------------------------------
# Chamadas, p95 e execução
# --------------------------------------------------------------------------------------------------------------
def chamada_do_caso(caso: dict) -> tuple[str, dict]:
    """A chamada pública fixa de cada capacidade (matriz, seção 1)."""
    cap, gab = caso["capacidade"], caso.get("gabarito") or {}
    if cap == "a":
        return "obter_dispositivo", {"citacao": caso["citacao"], "versao": "publicacao_original"}
    if cap in ("b", "d", "e"):
        return "obter_dispositivo", {"citacao": caso["citacao"]}
    trecho = gab.get("texto") if isinstance(gab.get("texto"), str) else caso.get("trecho")
    params = {"citacao": caso["citacao"], "trecho": trecho, "data": caso.get("data")}
    return "verificar_citacao", {k: v for k, v in params.items() if v is not None}


def p95(latencias: list[float]) -> float | None:
    """Posto mais próximo sobre todas as latências medidas: o menor valor com pelo menos 95% das medidas até ele."""
    if not latencias:
        return None
    xs = sorted(latencias)
    return xs[max(0, math.ceil(0.95 * len(xs)) - 1)]


def _chamar(svc: Any, funcao: str, params: dict, bloqueio: BloqueioDeRede | None):
    if funcao not in FUNCOES:
        raise ValueError(f"função fora da fachada pública: {funcao!r}")
    metodo = getattr(svc, funcao)
    permitidos = set(inspect.signature(metodo).parameters)
    estranhos = set(params) - permitidos
    if estranhos:
        raise ValueError(f"parâmetros que a fachada não conhece: {sorted(estranhos)}")
    ini = time.perf_counter()
    try:
        resp = metodo(**params)
    except ViolacaoDeRede:
        raise
    except Exception as exc:  # noqa: BLE001  - falha da chamada: resultado indisponível, nunca acerto
        resp = {"status": "indisponivel", "motivo": f"excecao_na_chamada:{type(exc).__name__}"}
    dt = time.perf_counter() - ini
    if bloqueio is not None:
        bloqueio.verificar()
    return resp, dt


def executar(casos: list[dict], mutantes: list[dict], svc: Any, modo: str, *, conjunto: str | None = None,
             bloqueio: BloqueioDeRede | None = None, aquecimento: int = PASSADAS_AQUECIMENTO,
             medidas: int = PASSADAS_MEDIDAS, min_unidades: int = MIN_UNIDADES, min_normas: int = MIN_NORMAS) -> dict:
    por_id = {c["id"]: c for c in casos}
    avaliacoes: dict[str, dict] = {}
    latencias: dict[str, list[float]] = defaultdict(list)
    for p in range(aquecimento + medidas):
        for c in casos:
            funcao, params = chamada_do_caso(c)
            resp, dt = _chamar(svc, funcao, params, bloqueio)
            if p < aquecimento:
                continue  # passada de aquecimento: descartada
            latencias[c["capacidade"]].append(dt)
            av = avaliar_resposta(c, resp, svc)  # TODAS as passadas medidas são examinadas (itens eliminatórios)
            if c["id"] not in avaliacoes:  # o resultado principal do caso é o da primeira passada medida
                av["latencias_s"] = []
                av["passadas"] = []
                avaliacoes[c["id"]] = av
            else:
                avaliacoes[c["id"]]["indevidas"].extend(
                    {**x, "detalhe": f"passada {p - aquecimento + 1}: {x['detalhe']}"} for x in av["indevidas"])
                ex0 = avaliacoes[c["id"]]["extra"]  # as condições por caso valem para todas as passadas medidas
                if "truncado" in av["extra"] and av["extra"]["truncado"] is not False:
                    ex0["truncado"] = av["extra"]["truncado"]
                if av["extra"].get("nao_verificado_com_motivo") is False:
                    ex0["nao_verificado_com_motivo"] = False
            avaliacoes[c["id"]]["passadas"].append(av["resultado"])
            avaliacoes[c["id"]]["latencias_s"].append(round(dt, 6))
    res_mut: dict[str, dict] = {}
    for m in mutantes:
        caso = por_id.get(m.get("caso"))
        try:
            funcao, params = m["chamada"]["funcao"], dict(m["chamada"]["parametros"])
            resp, _ = _chamar(svc, funcao, params, bloqueio)
            res_mut[m["id"]] = avaliar_mutante(m, caso, resp)
        except ViolacaoDeRede:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            res_mut[m["id"]] = {"rejeitado": False, "motivo": f"mutante inexecutável: {exc}"}
    return consolidar(casos, mutantes, avaliacoes, res_mut, latencias, modo, conjunto, min_unidades, min_normas)


def consolidar(casos, mutantes, avaliacoes, res_mut, latencias, modo, conjunto, min_unidades=MIN_UNIDADES,
               min_normas=MIN_NORMAS) -> dict:
    por_id = {c["id"]: c for c in casos}
    indevidas_total = sum(len(a["indevidas"]) for a in avaliacoes.values())
    indevidas_total += sum(1 for r in res_mut.values() if not r["rejeitado"])
    relatorio: dict[str, Any] = {"versao_executor": VERSAO_EXECUTOR, "modo": modo, "conjunto": conjunto,
                                 "confirmacoes_indevidas_total": indevidas_total, "capacidades": {}}
    for cap in CAPS:
        cs = [c for c in casos if c["capacidade"] == cap]
        reps = representantes(cs)
        rep_ids = set(reps.values())
        den = len(reps)
        acertos = sum(1 for u, i in reps.items() if eh_acerto(avaliacoes[i]["resultado"]))
        normas = {VALIDADOR.canon_norma(c["norma"]) for c in cs if c["id"] in rep_ids}
        indevidas = [{"caso": c["id"], **x} for c in cs for x in avaliacoes[c["id"]]["indevidas"]]
        ms = [m for m in mutantes if por_id.get(m.get("caso"), {}).get("capacidade") == cap]
        rej = sum(1 for m in ms if res_mut[m["id"]]["rejeitado"])
        indevidas += [{"caso": m["caso"], "item": "iv", "detalhe": f"mutante {m['id']}: {res_mut[m['id']]['motivo']}"}
                      for m in ms if not res_mut[m["id"]]["rejeitado"]]
        lat = latencias.get(cap, [])
        p = p95(lat)
        lim = LIMITE_P95_S[modo]
        extras: dict[str, Any] = {}
        motivos: list[str] = []
        acerto = acertos / den if den else 0.0
        if acerto < PISO_ACERTO[cap]:
            motivos.append(f"acerto {acerto:.2f} abaixo do piso {PISO_ACERTO[cap]:.2f}")
        if den < min_unidades or len(normas) < min_normas:
            motivos.append(f"{den} unidades e {len(normas)} normas (mínimo {min_unidades} e {min_normas})")
        if indevidas_total:
            motivos.append(f"confirmação indevida no conjunto avaliado ({indevidas_total}): eliminatório")
        if len(ms) != rej or not ms:
            motivos.append(f"mutantes rejeitados {rej}/{len(ms)} (todos devem ser rejeitados)")
        if p is None or p > lim:
            motivos.append(f"p95 {p} s acima de {lim} s")
        if cap == "b":
            grandes = [c for c in cs if c.get("norma_grande") and (c.get("gabarito") or {}).get("tipo") == "texto"]
            sem_trunc = sum(1 for c in grandes if avaliacoes[c["id"]]["extra"].get("truncado") is False)
            extras["norma_grande_sem_truncamento"] = f"{sem_trunc}/{len(grandes)}"
            if sem_trunc != len(grandes):
                motivos.append("truncamento em caso de norma grande")
        if cap == "c":
            sem = [c for c in cs if c["gabarito"].get("tipo") == "nao_verificado_para_D"]
            ok_sem = sum(1 for c in sem if avaliacoes[c["id"]]["extra"].get("nao_verificado_com_motivo") is True)
            extras["sem_fundamento_devolvidos_como_nao_verificados"] = f"{ok_sem}/{len(sem)}"
            if ok_sem != len(sem):
                motivos.append("caso sem fundamento da data não devolvido como não verificado, com motivo")
            pos = sum(1 for c in cs if c["gabarito"].get("tipo") == "verificado_para_D")
            extras["verificado_para_D"] = f"{pos}/{len(cs)}"
            if conjunto == "reserva" and (not cs or pos * 100 < 40 * len(cs)):
                motivos.append("menos de 40% dos casos (c) da reserva são verificado_para_D (abstenção sistemática)")
        relatorio["capacidades"][cap] = {
            "denominador": den, "acertos": acertos, "acerto": round(acerto, 4), "normas": len(normas),
            "confirmacoes_indevidas": indevidas, "mutantes_rejeitados": rej, "mutantes_total": len(ms),
            "p95_s": None if p is None else round(p, 6), "limite_p95_s": lim, "piso_acerto": PISO_ACERTO[cap],
            "extras": extras, "aprovada": not motivos, "motivos_reprovacao": motivos,
            "casos": [{"id": c["id"], "unidade": unidade(c), "conta_no_denominador": c["id"] in rep_ids,
                       "resultado": avaliacoes[c["id"]]["resultado"], "motivo": avaliacoes[c["id"]]["motivo"],
                       "passadas": avaliacoes[c["id"]].get("passadas", []),
                       "indevidas": avaliacoes[c["id"]]["indevidas"], "latencias_s": avaliacoes[c["id"]]["latencias_s"]}
                      for c in cs],
            "mutantes": [{"id": m["id"], "caso": m["caso"], "tipo": m["tipo"],
                          "rejeitado": res_mut[m["id"]]["rejeitado"], "motivo": res_mut[m["id"]]["motivo"]} for m in ms],
        }
    # mutante cujo caso de origem não existe: não pertence a capacidade alguma e reprova tudo (fail closed)
    orfaos = [m["id"] for m in mutantes if m.get("caso") not in por_id]
    if orfaos:
        relatorio["mutantes_orfaos"] = orfaos
        for cap in CAPS:
            relatorio["capacidades"][cap]["aprovada"] = False
            relatorio["capacidades"][cap]["motivos_reprovacao"].append(f"mutante sem caso de origem: {orfaos[:3]}")
    return relatorio


def tabela(relatorio: dict) -> dict[str, str]:
    return {cap: ("aprovado" if relatorio["capacidades"][cap]["aprovada"] else "reprovado") for cap in CAPS}


# --------------------------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------------------------
def socket_preexistente() -> str | None:
    """RED2/F2. Motivo da recusa se já existe socket no processo quando a guarda vai ser instalada; `None` se não. Só vale
    com o gancho precoce (CLI): (1) algum evento `socket.__new__` registrado desde a instalação do gancho; (2) objeto de
    socket com descritor aberto visto pelo coletor de lixo (`gc.get_objects`, sem criar socket). Limitação documentada:
    objeto criado por `SocketType.__new__` sem `__init__` não tem descritor e CPython só dispara o evento na inicialização;
    ele não é detectado, mas também não pode enviar (sem descritor, `send` falha no sistema)."""
    if not _GANCHO_PRECOCE:
        return None
    if _CRIADOS_ANTES:
        return f"socket criado antes da guarda ({_CRIADOS_ANTES[0]})"
    tipo = getattr(sys.modules.get("_socket"), "socket", None)
    if tipo is not None:
        import gc

        for obj in gc.get_objects():
            if isinstance(obj, tipo) and obj.fileno() != -1:
                return "descritor de socket aberto no processo antes da guarda"
    return None


def _recusar(msg: str, somente_tabela: bool, rotulo: str = "RECUSADO") -> None:
    print(f"{rotulo}: {msg}" if not somente_tabela else rotulo, file=sys.stderr)


def main(argv: list[str] | None = None, *, _servico: Any = None) -> int:
    ap = argparse.ArgumentParser(description="Executor da Porta L (IL.3-a)")
    ap.add_argument("--conjunto", required=True, type=Path)
    ap.add_argument("--mutantes", required=True, type=Path)
    ap.add_argument("--home", required=True, type=Path)
    ap.add_argument("--modo", required=True, choices=("local", "remoto"))
    ap.add_argument("--saida", required=True, type=Path)
    ap.add_argument("--somente-tabela", action="store_true",
                    help="emite só a tabela aprovado/reprovado (uso do guardião na reserva, D6)")
    ap.add_argument("--congelamento", type=Path, default=CONGELAMENTO_PADRAO,
                    help="só com --sintetico: outro Markdown de hashes (ferramenta de teste; nunca qualifica)")
    ap.add_argument("--sintetico", action="store_true",
                    help="modo sintético: aceita outro congelamento; o relatório sai marcado NÃO QUALIFICANTE")
    a = ap.parse_args(argv)
    if a.modo == "local":
        pre = socket_preexistente()
        if pre is not None:  # F2: sem relatório; código próprio (4), distinto de recusa de entrada (2) e falha fechada (3)
            _recusar(f"modo local recusado: {pre}", a.somente_tabela, "RECUSADO (socket preexistente)")
            return 4
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    try:
        manifesto = Path(a.congelamento).read_bytes()  # UMA leitura: autenticada, interpretada e declarada como lida
    except OSError as exc:
        _recusar(f"congelamento ilegível ({type(exc).__name__})", a.somente_tabela)
        return 2
    normativo = congelamento_normativo(a.congelamento, manifesto)
    if not normativo and not a.sintetico:
        _recusar("congelamento que não é o normativo do repositório (il1-congelamento.md); só --sintetico o aceita, "
                 "como execução NÃO QUALIFICANTE", a.somente_tabela)
        return 2
    qualificante = normativo and not a.sintetico and _servico is None  # serviço injetado = teste, nunca qualifica
    try:
        entradas = carregar_entradas(a.conjunto, a.mutantes, manifesto)
    except (OSError, ValueError) as exc:
        _recusar(str(exc), a.somente_tabela)
        return 2
    casos, mutantes = entradas.casos, entradas.mutantes
    try:
        guarda = None
        if a.modo == "local":
            os.environ["FV_OFFLINE"] = "1"
            guarda = BloqueioDeRede()
        svc = _servico
        try:
            if guarda is not None:
                guarda.__enter__()  # o bloqueio cobre o ciclo completo: construção, uso e fechamento do serviço
                guarda.autoteste()
            if svc is None:
                sys.path.insert(0, str(RAIZ))
                from freoa_verifica.service import Verifica

                svc = Verifica(home=a.home)
            try:
                relatorio = executar(casos, mutantes, svc, a.modo, conjunto=entradas.conjunto, bloqueio=guarda)
            finally:
                if _servico is None and hasattr(svc, "close"):
                    svc.close()
            if guarda is not None:
                guarda.verificar()  # inclui o que a construção e o fechamento tentaram
                relatorio["tentativas_de_rede"] = list(guarda.tentativas)
            relatorio["rede_bloqueada"] = guarda is not None
        finally:
            if guarda is not None:
                guarda.__exit__(None, None, None)
    except ViolacaoDeRede as exc:
        _recusar(str(exc), a.somente_tabela, "FALHA FECHADA")
        return 3
    except Exception as exc:  # noqa: BLE001
        _recusar(f"erro interno do executor ({type(exc).__name__})", a.somente_tabela, "FALHA FECHADA")
        return 3
    relatorio["hashes_conferidos"] = True
    relatorio["conjunto_sha256"] = entradas.conjunto_sha256  # os mesmos bytes conferidos e executados
    relatorio["mutantes_sha256"] = entradas.mutantes_sha256
    relatorio["congelamento"] = {"caminho": a.congelamento.name, "sha256": entradas.congelamento_sha256,
                                 "normativo": normativo}
    relatorio["qualificante"] = qualificante
    if not qualificante:
        relatorio["aviso"] = ("NÃO QUALIFICANTE: execução sintética, com serviço injetado ou com congelamento que não é o "
                              "normativo; o resultado não vale como apuração")
    relatorio["gerado_em"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    saida = {"tabela": tabela(relatorio), "qualificante": qualificante} if a.somente_tabela else relatorio
    a.saida.write_text(json.dumps(saida, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not qualificante:
        print("NÃO QUALIFICANTE (execução sintética)")
    for cap, v in tabela(relatorio).items():
        print(f"({cap}) {v}")
    return 0 if all(v == "aprovado" for v in tabela(relatorio).values()) else 1


if __name__ == "__main__":
    sys.exit(main())
