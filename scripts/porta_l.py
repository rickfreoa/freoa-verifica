"""Executor da Porta L (IL.3-a, A1): os predicados das seções 1 a 4 da matriz IL.1 (`il1-matriz-porta-l.md`, congelada).

Uso:
  python scripts/porta_l.py --conjunto <jsonl> --mutantes <jsonl> --home <home> --modo local|remoto --saida <relatorio.json>
                            [--somente-tabela] [--congelamento <il1-congelamento.md>]

Sem rede própria: chama só a fachada pública Python (`obter_dispositivo`, `verificar_citacao`, `obter_evidencia`), nunca
função interna. No modo `local` o processo bloqueia a rede e FALHA FECHADO ao detectar qualquer tentativa (código 3); no
modo `remoto` a federação ao vivo é a do serviço. O executor não lê a reserva por caminho fixo: recebe os arquivos por
argumento e confere o SHA-256 contra `il1-congelamento.md` antes de rodar, recusando arquivo divergente (código 2).

A comparação textual (seção 7) é a do validador congelado, importada, não copiada: `norm` daqui é o mesmo objeto de
`scripts/porta_l/validar_gabaritos_porta_l.py`. Denominador por unidade de independência (seção 2); confirmação indevida
pelos quatro itens da seção 2 em todos os casos e mutantes (eliminatória, reprova todas as capacidades); mutantes da
seção 3 pela chamada declarada no próprio mutante; p95 da seção 4 (uma passada de aquecimento descartada e três medidas,
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
TOLERANCIA_DATA_DIAS = 45  # folga entre a data do ato e a da publicação, a mesma do validador (cadeia)
CONGELAMENTO_PADRAO = RAIZ / "docs" / "auditoria" / "1.4.0" / "il1-congelamento.md"


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
    """Bloqueia conexão e resolução de nomes no processo; guarda cada tentativa. `verificar()` levanta se houve alguma,
    mesmo que o código chamado tenha engolido a exceção."""

    def __init__(self) -> None:
        self.tentativas: list[str] = []
        self._orig: list[tuple[Any, str, Any]] = []

    def _barrar(self, nome: str):
        def barreira(*a, **k):
            alvo = a[1] if nome.endswith("connect") and len(a) > 1 else (a[0] if a else "")
            self.tentativas.append(f"{nome}:{alvo!r}"[:200])
            raise RedeBloqueada(f"rede bloqueada no modo local ({nome})")
        return barreira

    def __enter__(self):
        for obj, atributo in ((socket.socket, "connect"), (socket.socket, "connect_ex"),
                              (socket, "create_connection"), (socket, "getaddrinfo"),
                              (socket, "gethostbyname"), (socket, "gethostbyname_ex")):
            self._orig.append((obj, atributo, getattr(obj, atributo)))
            setattr(obj, atributo, self._barrar(f"{getattr(obj, '__name__', 'socket')}.{atributo}"))
        return self

    def __exit__(self, *exc):
        for obj, atributo, original in reversed(self._orig):
            setattr(obj, atributo, original)
        self._orig.clear()
        return False

    def verificar(self) -> None:
        if self.tentativas:
            raise ViolacaoDeRede(f"tentativa de rede no modo local: {self.tentativas[0]}")

    def autoteste(self) -> None:
        """Falha fechada: se o bloqueio não funciona, não se roda."""
        try:
            socket.create_connection(("127.0.0.1", 9), timeout=0.2)
        except RedeBloqueada:
            self.tentativas.clear()
            return
        except OSError:
            pass
        raise ViolacaoDeRede("o bloqueio de rede não está efetivo; o executor não roda no modo local")


# --------------------------------------------------------------------------------------------------------------
# Congelamento: o executor confere os arquivos recebidos contra il1-congelamento.md (A1.8)
# --------------------------------------------------------------------------------------------------------------
def hashes_congelados(md: Path) -> dict[str, str]:
    """Papel -> SHA-256 das linhas da tabela do congelamento: conjunto e mutantes do desenvolvimento e da reserva."""
    papeis: dict[str, str] = {}
    for linha in md.read_text(encoding="utf-8").splitlines():
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


def sha256_arquivo(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def conferir_congelamento(conjunto: Path, mutantes: Path, md: Path) -> str:
    """Devolve 'desenvolvimento' ou 'reserva' se os dois arquivos são os congelados do MESMO conjunto; senão levanta."""
    papeis = hashes_congelados(md)
    hc, hm = sha256_arquivo(conjunto), sha256_arquivo(mutantes)
    for nome in ("desenvolvimento", "reserva"):
        if hc == papeis[f"{nome}/conjunto"] and hm == papeis[f"{nome}/mutantes"]:
            return nome
    raise ValueError("arquivo divergente do congelamento (il1-congelamento.md): o conjunto e os mutantes têm de ser os "
                     "congelados do mesmo conjunto")


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


def _cadeia_confere(resp: dict, gab: dict, data_d: str) -> tuple[bool, str]:
    """Última versão oficial anterior e cadeia ordenada de atos alteradores, contra `gabarito.cadeia` (1.1)."""
    prev = resp.get("ultima_versao_oficial_anterior")
    if not isinstance(prev, dict) or _data_iso(prev.get("data")) is None:
        return False, "ultima_versao_oficial_anterior ausente"
    d = _data_iso(data_d)
    if d is None or _data_iso(prev["data"]) >= d:
        return False, "ultima_versao_oficial_anterior não é anterior a D"
    obtida = []
    for item in resp.get("cadeia_alteracoes") or []:
        item = item if isinstance(item, dict) else {}
        obtida.append((_ato_canonico(item.get("ato")), _dim(item, "publicacao").get("data")))
    esperada = [(_ato_canonico(x.get("ato")), x.get("data")) for x in gab.get("cadeia") or [] if isinstance(x, dict)]
    if len(obtida) != len(esperada):
        return False, f"cadeia com {len(obtida)} atos; esperados {len(esperada)}"
    for (ao, do), (ae, de) in zip(obtida, esperada):
        if ao is None or ao != ae:
            return False, f"ato da cadeia {ao!r} diferente do esperado {ae!r} (ou fora de ordem)"
        a, b = _data_iso(do), _data_iso(de)
        if a is None or b is None or abs((a - b).days) > TOLERANCIA_DATA_DIAS:
            return False, "data do ato da cadeia fora da tolerância"
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
    indisp = status in ("indisponivel", "unavailable") or any(
        _dim(resp, n).get("status") == "unavailable" for n in ("identity", "text", "temporal"))
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
        remissoes = (resp.get("remissoes") or []) if status == "encontrada" else []
        for r in remissoes:
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
            ok_c, motivo_c = _cadeia_confere(resp, gab, d)
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
            if c["id"] not in avaliacoes:  # o resultado do caso é o da primeira passada medida
                av = avaliar_resposta(c, resp, svc)
                av["latencias_s"] = []
                avaliacoes[c["id"]] = av
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
def _ler_jsonl(p: Path) -> list[dict]:
    out = []
    for n, linha in enumerate(Path(p).read_text(encoding="utf-8").splitlines(), 1):
        if linha.strip():
            try:
                obj = json.loads(linha)
            except ValueError as exc:
                raise ValueError(f"{p}:{n}: JSON inválido ({exc})") from exc
            if not isinstance(obj, dict):
                raise ValueError(f"{p}:{n}: registro não é objeto")
            out.append(obj)
    return out


def main(argv: list[str] | None = None, *, _servico: Any = None) -> int:
    ap = argparse.ArgumentParser(description="Executor da Porta L (IL.3-a)")
    ap.add_argument("--conjunto", required=True, type=Path)
    ap.add_argument("--mutantes", required=True, type=Path)
    ap.add_argument("--home", required=True, type=Path)
    ap.add_argument("--modo", required=True, choices=("local", "remoto"))
    ap.add_argument("--saida", required=True, type=Path)
    ap.add_argument("--somente-tabela", action="store_true",
                    help="emite só a tabela aprovado/reprovado (uso do guardião na reserva, D6)")
    ap.add_argument("--congelamento", type=Path, default=CONGELAMENTO_PADRAO)
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    try:
        conjunto = conferir_congelamento(a.conjunto, a.mutantes, a.congelamento)
        casos, mutantes = _ler_jsonl(a.conjunto), _ler_jsonl(a.mutantes)
    except (OSError, ValueError) as exc:
        print(f"RECUSADO: {exc}" if not a.somente_tabela else "RECUSADO", file=sys.stderr)
        return 2
    try:
        if a.modo == "local":
            os.environ["FV_OFFLINE"] = "1"
        svc = _servico
        if svc is None:
            sys.path.insert(0, str(RAIZ))
            from freoa_verifica.service import Verifica

            svc = Verifica(home=a.home)
        try:
            if a.modo == "local":
                with BloqueioDeRede() as bloq:
                    bloq.autoteste()
                    relatorio = executar(casos, mutantes, svc, "local", conjunto=conjunto, bloqueio=bloq)
                    relatorio["rede_bloqueada"] = True
                    relatorio["tentativas_de_rede"] = list(bloq.tentativas)
            else:
                relatorio = executar(casos, mutantes, svc, "remoto", conjunto=conjunto)
                relatorio["rede_bloqueada"] = False
        finally:
            if _servico is None and hasattr(svc, "close"):
                svc.close()
    except ViolacaoDeRede as exc:
        print(f"FALHA FECHADA: {exc}" if not a.somente_tabela else "FALHA FECHADA", file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001
        print(f"FALHA FECHADA: erro interno do executor ({type(exc).__name__})", file=sys.stderr)
        return 3
    relatorio["hashes_conferidos"] = True
    relatorio["conjunto_sha256"] = sha256_arquivo(a.conjunto)
    relatorio["mutantes_sha256"] = sha256_arquivo(a.mutantes)
    relatorio["gerado_em"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    saida = {"tabela": tabela(relatorio)} if a.somente_tabela else relatorio
    a.saida.write_text(json.dumps(saida, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for cap, v in tabela(relatorio).items():
        print(f"({cap}) {v}")
    return 0 if all(v == "aprovado" for v in tabela(relatorio).values()) else 1


if __name__ == "__main__":
    sys.exit(main())
