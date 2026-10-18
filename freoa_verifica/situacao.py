"""Contrato C2: situação cadastral da obra (decisão 0021).

A situação vem de evidência própria capturada pelo transporte (página do ato CVM;
campos Revogado/Cancelado do BCB/CMN), nunca do texto normativo selecionado.
Ausência ou falha de leitura é `ilegivel`, jamais "vigente".
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

SITUACOES = ("revogada", "cancelada", "vigente_declarada", "ilegivel", "nao_aplicavel")
AUTORIDADES_COM_SITUACAO = frozenset({"cvm", "bcb", "cmn"})
MAX_IDADE_DIAS = 30

REVOGADO_NA_FONTE = "OBRA_REVOGADA_NA_FONTE"
DATA_DESCONHECIDA = "REVOGACAO_DATA_DESCONHECIDA"
INDISPONIVEL = "SITUACAO_INDISPONIVEL"
DESATUALIZADA = "SITUACAO_DESATUALIZADA"
POSTERIOR = "REVOGACAO_POSTERIOR"


@dataclass(frozen=True)
class WorkStatus:
    work_id: str
    situacao: str
    texto_oficial: str | None = None
    ato_revogador: str | None = None
    data_efeito: str | None = None  # nunca a data do ato revogador
    captura_id: str | None = None
    sha256: str | None = None
    lido_em: str | None = None
    url: str | None = None  # da captura; não é coluna


# ----------------------------------------------------------------------
# Persistência
# ----------------------------------------------------------------------

def gravar(conn: sqlite3.Connection, ws: WorkStatus) -> None:
    if ws.situacao not in SITUACOES:
        raise ValueError(f"situacao inválida: {ws.situacao}")
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO work_status(work_id,situacao,texto_oficial,ato_revogador,"
            "data_efeito,captura_id,sha256,lido_em) VALUES (?,?,?,?,?,?,?,?)",
            (ws.work_id, ws.situacao, ws.texto_oficial, ws.ato_revogador, ws.data_efeito,
             ws.captura_id, ws.sha256, ws.lido_em or datetime.now().astimezone().isoformat()),
        )


def _autentico(conn: sqlite3.Connection, ws: WorkStatus, home: Any) -> bool:
    """A captura de situação existe, pertence à situação gravada e o blob confere (sha256)."""
    from freoa_verifica.store import blobs

    if not ws.captura_id:
        return ws.situacao == "ilegivel"  # sem captura só sobra o rebaixamento
    cap = conn.execute("SELECT sha256 FROM capture WHERE id=?", (ws.captura_id,)).fetchone()
    if cap is None or not cap["sha256"] or cap["sha256"] != ws.sha256:
        return False
    try:
        blobs.authenticate_blob(cap["sha256"], home=home)
    except (OSError, ValueError, blobs.BlobCorruption):
        return False
    return True


def carregar(conn: sqlite3.Connection | None, rw: Any, home: Any = None) -> WorkStatus | None:
    """Situação da obra. None = sem efeito (sem banco ou fonte sem situação cadastral).

    CVM/BCB/CMN sem registro valem `ilegivel`: o silêncio não é vigência.
    """
    if conn is None:
        return None
    row = conn.execute(
        "SELECT s.*, c.url AS url FROM work_status s LEFT JOIN capture c ON c.id=s.captura_id "
        "WHERE s.work_id=?", (rw.work_id,)).fetchone()
    if row is not None:
        ws = WorkStatus(row["work_id"], row["situacao"], row["texto_oficial"], row["ato_revogador"],
                        row["data_efeito"], row["captura_id"], row["sha256"], row["lido_em"], row["url"])
        # Captura de situação adulterada ou ausente: a conclusão temporal não pode apoiar-se nela.
        if rw.work_key.authority in AUTORIDADES_COM_SITUACAO and not _autentico(conn, ws, home):
            return WorkStatus(rw.work_id, "ilegivel", "captura_de_situacao_nao_autentica")
        return ws
    if rw.work_key.authority in AUTORIDADES_COM_SITUACAO:
        return WorkStatus(rw.work_id, "ilegivel", "situacao_nao_lida")
    return None


def resumo(ws: WorkStatus | None) -> dict[str, Any] | None:
    if ws is None:
        return None
    return {"situacao": ws.situacao, "texto_oficial": ws.texto_oficial, "ato_revogador": ws.ato_revogador,
            "data_efeito": ws.data_efeito, "capture_id": ws.captura_id, "sha256": ws.sha256,
            "lido_em": ws.lido_em}


# ----------------------------------------------------------------------
# Leitura da evidência
# ----------------------------------------------------------------------

def ler_bcb(body: bytes) -> dict[str, Any]:
    """Campos Revogado/Cancelado do JSON oficial. Qualquer ausência é ilegivel."""
    from freoa_verifica.parsers.bcb_json import _pick_item

    try:
        item = _pick_item(json.loads(body.decode("utf-8")))
        revogado, cancelado = item["Revogado"], item["Cancelado"]
        if not isinstance(revogado, bool) or not isinstance(cancelado, bool):
            raise TypeError
    except (ValueError, KeyError, TypeError, AttributeError):
        return {"situacao": "ilegivel", "texto_oficial": "campos Revogado/Cancelado ausentes ou ilegíveis"}
    titulo = str(item.get("Titulo") or "").strip()
    texto = f"{titulo}: Revogado={str(revogado).lower()}; Cancelado={str(cancelado).lower()}"
    situacao = "revogada" if revogado else ("cancelada" if cancelado else "vigente_declarada")
    return {"situacao": situacao, "texto_oficial": texto, "ato_revogador": None}


def registrar_do_corpo(conn: sqlite3.Connection, rw: Any, source_id: str, body: bytes) -> None:
    """BCB: a própria captura normativa traz os campos de situação."""
    if source_id != "bcb":
        return
    lida = ler_bcb(body)
    gravar(conn, WorkStatus(rw.work_id, lida["situacao"], lida.get("texto_oficial"),
                            lida.get("ato_revogador"), None, rw.capture_id, rw.sha256,
                            rw.fetched_at))


def registrar_cvm(conn: sqlite3.Connection, home: Any, connector: Any, cand: Any, rw: Any) -> WorkStatus:
    """Captura a página do ato (sempre) e grava a situação lida; falha vira ilegivel."""
    from freoa_verifica.connectors.cvm_normas import ler_situacao_pagina
    from freoa_verifica.store import repo

    try:
        resp = connector.fetch_situacao(cand)
        captura = repo.save_capture(conn, resp, "cvm_normas", home=home)
        from freoa_verifica.connectors.cvm_normas import _parse_key
        lida = ler_situacao_pagina(resp.body, _parse_key(cand.key))
        if lida is None:
            ws = WorkStatus(rw.work_id, "ilegivel", "pagina_do_ato_ilegivel", None, None,
                            captura, resp.sha256, resp.fetched_at)
        else:
            ws = WorkStatus(rw.work_id, lida["situacao"], lida["texto_oficial"], lida["ato_revogador"],
                            None, captura, resp.sha256, resp.fetched_at)
    except Exception as exc:  # noqa: BLE001 — qualquer falha é ilegivel, nunca vigente
        return _falha_de_leitura(conn, WorkStatus(rw.work_id, "ilegivel", f"pagina_do_ato_indisponivel: {getattr(exc, 'reason', type(exc).__name__)}"[:200]), home)
    gravar(conn, ws)
    return ws


def _falha_de_leitura(conn: sqlite3.Connection, ws: WorkStatus, home: Any) -> WorkStatus:
    """Falha de transporte não apaga leitura autêntica anterior: ela envelhece sozinha (MAX_IDADE_DIAS)."""
    row = conn.execute("SELECT * FROM work_status WHERE work_id=?", (ws.work_id,)).fetchone()
    if row is not None and row["situacao"] != "ilegivel":
        anterior = WorkStatus(row["work_id"], row["situacao"], row["texto_oficial"], row["ato_revogador"],
                              row["data_efeito"], row["captura_id"], row["sha256"], row["lido_em"])
        if _autentico(conn, anterior, home):
            return anterior
    gravar(conn, ws)
    return ws


_KIND_TIPO = {"resolucao": "resolucoes", "instrucao": "instrucoes",
              "parecer_orientacao": "pareceres-orientacao", "deliberacao": "deliberacoes"}


def ressincronizar(svc: Any, *, fontes: tuple[str, ...] = ("cvm_normas", "bcb"),
                   max_obras: int | None = None) -> dict[str, Any]:
    """Relê a situação dos atos CVM/BCB/CMN já no acervo (insumo do snapshot)."""
    from freoa_verifica.store import repo

    if svc._offline():
        return {"status": "indisponivel", "motivo": "offline"}
    out = {"lidas": 0, "ilegiveis": 0, "revogadas": 0, "canceladas": 0, "obras": 0}
    rows = svc.conn.execute(
        "SELECT * FROM work WHERE authority IN ('cvm','bcb','cmn') AND authority NOT LIKE 'invalidated:%' "
        "ORDER BY authority, kind, number, year").fetchall()
    for row in rows[:max_obras]:
        fonte = "cvm_normas" if row["authority"] == "cvm" else "bcb"
        if fonte not in fontes:
            continue
        caps = repo.captures_for_work(svc.conn, row["id"])
        out["obras"] += 1
        rw = type("W", (), {"work_id": row["id"]})()
        if fonte == "cvm_normas":
            tipo = _KIND_TIPO.get(row["kind"])
            cand = svc._get(fonte).resolve({"tipo": tipo, "numero": int(row["number"])}) if tipo else None
            ws = registrar_cvm(svc.conn, svc.home, svc._get(fonte), cand, rw) if cand else _ilegivel(svc.conn, row["id"], "especie_sem_pagina")
        else:
            ws = _reler_bcb(svc, row, caps, rw)
        out["lidas"] += 1
        out["ilegiveis"] += ws.situacao == "ilegivel"
        out["revogadas"] += ws.situacao == "revogada"
        out["canceladas"] += ws.situacao == "cancelada"
    svc._resolver = type(svc._resolver)()
    return {"status": "ok", **out}


def _ilegivel(conn: sqlite3.Connection, work_id: str, motivo: str) -> WorkStatus:
    ws = WorkStatus(work_id, "ilegivel", motivo)
    gravar(conn, ws)
    return ws


def _reler_bcb(svc: Any, row: Any, caps: list, rw: Any) -> WorkStatus:
    from freoa_verifica.connectors.base import Candidate
    from freoa_verifica.store import repo

    cap = next((c for c in caps if c["source_id"] == "bcb"), None)
    if cap is None:
        return _ilegivel(svc.conn, row["id"], "sem_captura_bcb")
    q = parse_qs(urlparse(cap["url"]).query)
    tipo, numero = (q.get("p1") or [None])[0], (q.get("p2") or [None])[0]
    if not tipo or not numero:
        return _ilegivel(svc.conn, row["id"], "url_sem_chave")
    try:
        conn_obj = svc._get("bcb")
        resp = conn_obj.fetch(Candidate("bcb", f"bcb:{tipo}:{numero}", f"{tipo} {numero}", cap["url"],
                                        metadata={"tipo": tipo, "numero": numero}))
        captura = repo.save_capture(svc.conn, resp, "bcb", home=svc.home)
        lida = ler_bcb(resp.body)
        ws = WorkStatus(row["id"], lida["situacao"], lida.get("texto_oficial"), None, None,
                        captura, resp.sha256, resp.fetched_at)
    except Exception as exc:  # noqa: BLE001
        return _falha_de_leitura(svc.conn, WorkStatus(row["id"], "ilegivel", f"bcb_indisponivel: {getattr(exc, 'reason', type(exc).__name__)}"[:200]), svc.home)
    gravar(svc.conn, ws)
    return ws


# ----------------------------------------------------------------------
# Regras de propagação
# ----------------------------------------------------------------------

def _iso(value: str | None) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def _desatualizada(ws: WorkStatus, hoje: date) -> bool:
    lido = _iso(ws.lido_em)
    return lido is None or (hoje - lido).days > MAX_IDADE_DIAS


def _decidir(cur: str, ws: WorkStatus | None, data: str | None, hoje: date) -> tuple[str, str] | None:
    """cur: bom (verified/vigente_na_fonte) | revogado | preservar | unknown | nao_avaliado.

    Devolve (acao, motivo) com acao em revogado|unknown|flag, ou None (sem efeito).
    """
    if ws is None or ws.situacao in ("nao_aplicavel",) or cur in ("revogado", "preservar"):
        return None
    d = hoje if data is None else _iso(data)
    if d is None:
        return None
    if ws.situacao in ("revogada", "cancelada"):
        efeito = _iso(ws.data_efeito)
        if efeito is not None:
            return ("revogado", REVOGADO_NA_FONTE) if d >= efeito else ("flag", POSTERIOR)
        if d >= hoje:
            return ("revogado", REVOGADO_NA_FONTE)
        return ("unknown", DATA_DESCONHECIDA) if cur == "bom" else None
    if cur != "bom":
        return None
    if ws.situacao == "ilegivel":
        return ("unknown", INDISPONIVEL)
    if _desatualizada(ws, hoje):  # vigente_declarada
        return ("unknown", DESATUALIZADA)
    return None


def _evidencia(ws: WorkStatus):
    from freoa_verifica.verify import Evidence

    return Evidence(capture_id=ws.captura_id, sha256=ws.sha256, url=ws.url, fetched_at=ws.lido_em,
                    trecho_oficial=(ws.texto_oficial or "")[:1500] or None)


def aplicar_situacao(temporal_dim, status: WorkStatus | None, data: str | None, hoje: date | None = None):
    """Aplica C2 a uma Dimension temporal (verify). Devolve nova Dimension."""
    from freoa_verifica.temporal import today_sp

    hoje = hoje or today_sp()
    s, r = temporal_dim.status, temporal_dim.reason_code or ""
    if s in ("verified", "vigente_na_fonte"):
        cur = "bom"
    elif (s == "divergent" and r.startswith("REVOGADO")) or r == REVOGADO_NA_FONTE:
        cur = "revogado"
    elif s in ("not_found", "ambiguous"):
        cur = "preservar"
    elif s == "not_assessed":
        cur = "nao_avaliado"
    else:
        cur = "unknown"
    acao = _decidir(cur, status, data, hoje)
    if acao is None:
        return temporal_dim
    kind, motivo = acao
    ev = list(temporal_dim.evidence) + ([_evidencia(status)] if status.captura_id or status.texto_oficial else [])
    if kind == "revogado":
        return replace(temporal_dim, status="divergent", reason_code=motivo, evidence=ev)
    if kind == "unknown":
        return replace(temporal_dim, status="unknown", reason_code=motivo, evidence=ev)
    return replace(temporal_dim, reason_code=",".join(x for x in (temporal_dim.reason_code, motivo) if x))


def aplicar_situacao_dict(temporal: dict, status: WorkStatus | None, data: str | None,
                          hoje: date | None = None) -> dict:
    """C2 sobre a dimensão temporal já serializada (`_finalizar`). Mesma regra de `aplicar_situacao`."""
    from dataclasses import asdict

    from freoa_verifica.verify import Dimension

    novo = aplicar_situacao(Dimension(temporal.get("status"), temporal.get("reason_code")), status, data, hoje)
    if (novo.status, novo.reason_code) == (temporal.get("status"), temporal.get("reason_code")):
        return temporal
    ev = [{**asdict(e), "span": None} for e in novo.evidence]
    return {**temporal, "status": novo.status, "reason_code": novo.reason_code,
            "evidence": list(temporal.get("evidence") or []) + ev}


def aplicar_situacao_tr(tr, status: WorkStatus | None, data: str | None, hoje: date | None = None):
    """Mesma regra para TemporalResult (service: obter_dispositivo/historico)."""
    from freoa_verifica.temporal import today_sp

    hoje = hoje or today_sp()
    cur = {"verified": "bom", "vigente_na_fonte": "bom", "revogado": "revogado", "nao_existia": "preservar",
           "ambiguous": "preservar"}.get(tr.status, "unknown")
    acao = _decidir(cur, status, data, hoje)
    if acao is None:
        return tr
    kind, motivo = acao
    if kind == "flag":
        return replace(tr, flags=list(tr.flags) + [motivo])
    return replace(tr, status="revogado" if kind == "revogado" else "unknown", reason=motivo,
                   flags=list(tr.flags) + [motivo])
