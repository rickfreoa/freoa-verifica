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
(rede detectada no modo local, ou erro interno do executor).
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import inspect
import json
import math
import os
import re
import socket
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
VERSAO_EXECUTOR = "1"
CAPS = ("a", "b", "c", "d", "e")
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


class BloqueioDeRede:
    """Bloqueia no processo toda primitiva de saída (conexão, envio, resolução de nomes); guarda cada tentativa.
    `verificar()` levanta se houve alguma, mesmo que o código chamado tenha engolido a exceção. O autoteste exerce
    cada primitiva e falha se qualquer uma escapar."""

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
        try:
            import _socket
            alvos += [(_socket, n) for n in self._MODULO if n != "create_connection" and hasattr(_socket, n)]
        except ImportError:  # pragma: no cover
            pass
        try:
            import ssl
            alvos += [(ssl.SSLSocket, n) for n in self._SSL if hasattr(ssl.SSLSocket, n)]
        except ImportError:  # pragma: no cover
            pass
        return [(o, n) for o, n in alvos if hasattr(o, n)]

    def __enter__(self):
        for obj, atributo in self._alvos():
            self._orig.append((obj, atributo, getattr(obj, atributo), atributo in vars(obj)))
            setattr(obj, atributo, self._barrar(f"{getattr(obj, '__name__', 'socket')}.{atributo}"))
        return self

    def __exit__(self, *exc):
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

    def autoteste(self) -> None:
        """Falha fechada: exerce CADA primitiva bloqueada e levanta se qualquer uma não for barrada (a barreira age antes
        de qualquer pacote; nada sai)."""
        alvo = ("127.0.0.1", 9)
        provas: list[tuple[str, Any]] = [
            ("socket.connect", lambda s: s.connect(alvo)), ("socket.connect_ex", lambda s: s.connect_ex(alvo)),
            ("socket.send", lambda s: s.send(b"x")), ("socket.sendall", lambda s: s.sendall(b"x")),
            ("socket.sendto", lambda s: s.sendto(b"x", alvo)),
            ("socket.sendmsg", lambda s: s.sendmsg([b"x"], [], 0, alvo)),  # não existe em todas as plataformas
            ("socket.sendfile", lambda s: s.sendfile(__import__("io").BytesIO(b"x"))),
            ("socket.create_connection", lambda s: socket.create_connection(alvo, timeout=0.2)),
            ("socket.getaddrinfo", lambda s: socket.getaddrinfo("example.invalid", 80)),
            ("socket.gethostbyname", lambda s: socket.gethostbyname("example.invalid")),
            ("socket.gethostbyname_ex", lambda s: socket.gethostbyname_ex("example.invalid")),
            ("socket.gethostbyaddr", lambda s: socket.gethostbyaddr("127.0.0.1")),
            ("socket.getnameinfo", lambda s: socket.getnameinfo(alvo, 0)),
        ]
        try:
            import _socket
            provas.append(("_socket.getaddrinfo", lambda s: _socket.getaddrinfo("example.invalid", 80)))
        except ImportError:  # pragma: no cover
            pass
        try:
            import ssl
            for n in self._SSL:
                if hasattr(ssl.SSLSocket, n):
                    provas.append((f"ssl.{n}", lambda s, n=n: getattr(ssl.SSLSocket, n)(s, b"x")))
        except ImportError:  # pragma: no cover
            pass
        escaparam: list[str] = []
        for nome, prova in provas:
            if nome.startswith("socket.") and not hasattr(socket.socket, nome.split(".", 1)[1])                     and not hasattr(socket, nome.split(".", 1)[1]):
                continue  # primitiva inexistente nesta plataforma: nada a barrar
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                try:
                    prova(s)
                except RedeBloqueada:
                    continue
                except Exception:  # noqa: BLE001 - qualquer outra coisa é uma primitiva que escapou da barreira
                    pass
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


def congelamento_normativo(md: Path) -> bool:
    """O congelamento é o normativo do repositório: o mesmo caminho E os mesmos bytes (fins de linha normalizados) que o
    hash fixado aqui. Qualquer outro Markdown de hashes é só ferramenta de teste e nunca qualifica."""
    try:
        md = Path(md)
        if md.resolve() != CONGELAMENTO_PADRAO.resolve():
            return False
        return sha256_bytes(md.read_bytes().replace(b"\r\n", b"\n")) == CONGELAMENTO_SHA256
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


def carregar_entradas(conjunto: Path, mutantes: Path, md: Path) -> Entradas:
    """Lê cada arquivo uma única vez, confere os bytes lidos contra o congelamento e interpreta esses mesmos bytes.
    Levanta se não são os arquivos congelados do MESMO conjunto."""
    dmd = Path(md).read_bytes()
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


def indisponivel(resp: dict) -> bool:
    """Veto comum (matriz, seção 2): `unavailable`, `indisponivel` ou `parcial` no estado agregado ou em QUALQUER
    dimensão da resposta (identidade, texto, temporal, vigência, evidência...) tira o caso do numerador."""
    if not isinstance(resp, dict):
        return True
    if resp.get("status") in ESTADOS_NAO_NUMERADOR:
        return True
    return any(isinstance(v, dict) and v.get("status") in ESTADOS_NAO_NUMERADOR for v in resp.values())


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


def _evidencia_identificavel(ev: Any) -> bool:
    """Evidência entregue com a versão ou o ato: objeto com captura recuperável (`capture_id`) ou hash do documento."""
    if not isinstance(ev, dict):
        return False
    return _tem_texto(ev.get("capture_id")) or _tem_texto(ev.get("sha256")) or _tem_texto(
        _dim(ev, "metadados").get("sha256"))


def _predecessor_confere(prev: Any, uva: Any, caso: dict, data_d: str) -> tuple[bool, str]:
    """Última versão oficial anterior contra `gabarito.ultima_versao_anterior` {ato, data}: data idêntica, anterior a D,
    identificação do ato quando o gabarito não é o original, e a entrega documental (texto, caminho, evidência)."""
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
    if not _evidencia_identificavel(prev.get("evidencia")):
        return False, "ultima_versao_oficial_anterior sem evidência identificável"
    return True, ""


def _cadeia_confere(resp: dict, caso: dict, data_d: str) -> tuple[bool, str]:
    """Última versão oficial anterior e cadeia ordenada de atos alteradores, contra `gabarito.ultima_versao_anterior` e
    `gabarito.cadeia` (1.1), sem tolerância de data e exigindo a entrega documental de cada elo."""
    gab = caso.get("gabarito") or {}
    ok, motivo = _predecessor_confere(resp.get("ultima_versao_oficial_anterior"), gab.get("ultima_versao_anterior"),
                                      caso, data_d)
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
    for (ao, do, item), (ae, de) in zip(obtida, esperada):
        if ao is None or ao != ae:
            return False, f"ato da cadeia {ao!r} diferente do esperado {ae!r} (ou fora de ordem)"
        if _data_iso(de) is None or do != de:
            return False, f"data de publicação do ato {ae!r} é {do!r}; esperada {de!r}"
        ato = item.get("ato") if isinstance(item.get("ato"), dict) else {}
        if not (_tem_texto(ato.get("url")) and _tem_texto(item.get("texto"))
                and _evidencia_identificavel(item.get("evidencia"))):
            return False, f"entrega documental incompleta do ato {ae!r} (url, texto ou evidência)"
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
            ok_c, motivo_c = _cadeia_confere(resp, caso, d)
            if ok_c:
                out.update(resultado="acerto")
            else:
                out.update(resultado="parcial", motivo=motivo_c)
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
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    normativo = congelamento_normativo(a.congelamento)
    if not normativo and not a.sintetico:
        _recusar("congelamento que não é o normativo do repositório (il1-congelamento.md); só --sintetico o aceita, "
                 "como execução NÃO QUALIFICANTE", a.somente_tabela)
        return 2
    qualificante = normativo and not a.sintetico and _servico is None  # serviço injetado = teste, nunca qualifica
    try:
        entradas = carregar_entradas(a.conjunto, a.mutantes, a.congelamento)
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
