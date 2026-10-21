"""Contrato C2: situação cadastral da obra (decisão 0021).

A situação vem de evidência própria capturada pelo transporte (página do ato CVM;
campos Revogado/Cancelado do BCB/CMN), nunca do texto normativo selecionado.
Ausência ou falha de leitura é `ilegivel`, jamais "vigente".
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

from freoa_verifica.connectors.base import Unavailable

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

def ler_bcb(body: bytes | str) -> dict[str, Any]:
    """Campos Revogado/Cancelado do JSON oficial. Qualquer ausência é ilegivel.

    `str` é o texto da interpretação única do `Response`; `bytes` (captura relida, sem Content-Type) é JSON.
    """
    from freoa_verifica.parsers.bcb_json import _pick_item
    from freoa_verifica.texto_resposta import texto_da_resposta
    from freoa_verifica.transport import RespostaInvalida

    try:
        item = _pick_item(json.loads(texto_da_resposta(body, "application/json")))
        revogado, cancelado = item["Revogado"], item["Cancelado"]
        if not isinstance(revogado, bool) or not isinstance(cancelado, bool):
            raise TypeError
    except (ValueError, KeyError, TypeError, AttributeError, RespostaInvalida):
        return {"situacao": "ilegivel", "texto_oficial": "campos Revogado/Cancelado ausentes ou ilegíveis"}
    titulo = str(item.get("Titulo") or "").strip()
    texto = f"{titulo}: Revogado={str(revogado).lower()}; Cancelado={str(cancelado).lower()}"
    situacao = "revogada" if revogado else ("cancelada" if cancelado else "vigente_declarada")
    ato, efeito = (_revogacao_declarada(item.get("Atualizacoes")) if revogado else (None, None))
    if ato:
        texto += f"; Atualizacoes: {ato}" + (f" a partir de {efeito}" if efeito else "")
    return {"situacao": situacao, "texto_oficial": texto, "ato_revogador": ato, "data_efeito": efeito}


_REVOGACAO = re.compile(
    r"^\s*(?P<ato>(?:Resolu[cç][aã]o|Circular|Carta Circular|Instru[cç][aã]o Normativa)\s+(?:CMN|BCB)?\s*n[ºo°]\s*[\d.]+/\d{4})"
    r"\s*[-,–]\s*revoga[cç][aã]o total(?:\s*,?\s*a partir de\s+(?P<d>\d{1,2})[ºo°]?/(?P<m>\d{1,2})/(?P<a>\d{4}))?\.?\s*$",
    re.I)


def _revogacao_declarada(atualizacoes: Any) -> tuple[str | None, str | None]:
    """Decisão 0035: só a entrada única e inequívoca de "Revogação total [a partir de D/M/AAAA]" vale.
    Sem data declarada, o ato revogador é registrado e a data de efeito continua desconhecida."""
    # Unicidade conta toda entrada que fale em revogação, em qualquer formato; só depois vem o padrão estrito.
    mencoes = [a for a in str(atualizacoes or "").split(";#") if re.search(r"revoga", a, re.I)]
    m = _REVOGACAO.match(mencoes[0]) if len(mencoes) == 1 else None
    if m is None:
        return None, None
    efeito = None
    if m["a"]:
        try:
            efeito = date(int(m["a"]), int(m["m"]), int(m["d"])).isoformat()
        except ValueError:
            efeito = None
    return re.sub(r"\s+", " ", m["ato"]).strip(), efeito


def registrar_do_corpo(conn: sqlite3.Connection, rw: Any, source_id: str, body: bytes,
                       content_type: str | None = None) -> None:
    """BCB: a própria captura normativa traz os campos de situação, lidos pelo Content-Type da resposta (F-22)."""
    from freoa_verifica.texto_resposta import texto_da_resposta
    from freoa_verifica.transport import RespostaInvalida

    if source_id != "bcb":
        return
    try:  # sem Content-Type (registro sintético), o JSON da fonte: UTF-8/BOM, nunca `<meta>` do HTML embutido
        lida = ler_bcb(texto_da_resposta(body, content_type or "application/json"))
    except RespostaInvalida:
        lida = {"situacao": "ilegivel", "texto_oficial": "corpo não interpretável"}
    gravar(conn, WorkStatus(rw.work_id, lida["situacao"], lida.get("texto_oficial"),
                            lida.get("ato_revogador"), lida.get("data_efeito"), rw.capture_id, rw.sha256,
                            rw.fetched_at))


def interrompe_a_fonte(exc: Unavailable) -> bool:
    """Falha que é da fonte, não do item: desafio, recusa, fonte fora, resposta inesperada ou orçamento (FIX18/F-23).

    Item ausente (`http_404`, sem categoria) é do item: a ressincronização segue para o próximo.
    """
    return exc.categoria is not None or exc.reason == "orcamento"


def registrar_cvm(conn: sqlite3.Connection, home: Any, connector: Any, cand: Any, rw: Any, *,
                  propagar: bool = False) -> WorkStatus:
    """Captura a página do ato (sempre) e grava a situação lida; falha vira ilegivel.

    `propagar`: o controlador (ressincronização) recebe a indisponibilidade estruturada que é da fonte, depois de
    gravada a falha de leitura, para interromper a fonte e declará-la (FIX18/F-23). Sem ele (página do ato como
    evidência acessória de uma obra já capturada), a falha fica como `ilegivel`, com motivo e categoria.
    """
    from freoa_verifica.connectors.cvm_normas import ler_situacao_pagina
    from freoa_verifica.store import repo
    from freoa_verifica.texto_resposta import texto_do_response

    try:
        resp = connector.fetch_situacao(cand)
        captura = repo.save_capture(conn, resp, "cvm_normas", home=home)
        from freoa_verifica.connectors.cvm_normas import _parse_key
        lida = ler_situacao_pagina(texto_do_response(resp), _parse_key(cand.key))
        if lida is None:
            ws = WorkStatus(rw.work_id, "ilegivel", "pagina_do_ato_ilegivel", None, None,
                            captura, resp.sha256, resp.fetched_at)
        else:
            ws = WorkStatus(rw.work_id, lida["situacao"], lida["texto_oficial"], lida["ato_revogador"],
                            None, captura, resp.sha256, resp.fetched_at)
    except Unavailable as exc:
        ws = _falha_de_leitura(conn, WorkStatus(rw.work_id, "ilegivel", _motivo("pagina_do_ato_indisponivel", exc)),
                               home)
        if propagar and interrompe_a_fonte(exc):
            raise
        return ws
    except Exception as exc:  # noqa: BLE001 — qualquer outra falha (parse, banco) é ilegivel, nunca vigente
        return _falha_de_leitura(conn, WorkStatus(rw.work_id, "ilegivel", f"pagina_do_ato_indisponivel: {getattr(exc, 'reason', type(exc).__name__)}"[:200]), home)
    gravar(conn, ws)
    return ws


def _motivo(prefixo: str, exc: Exception) -> str:
    """Motivo gravado da falha de leitura: código estável e, se provada, a categoria (decisão 0045)."""
    categoria = getattr(exc, "categoria", None)
    return f"{prefixo}: {getattr(exc, 'reason', type(exc).__name__)}{f' [{categoria}]' if categoria else ''}"[:200]


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
    out = {"lidas": 0, "ilegiveis": 0, "revogadas": 0, "canceladas": 0, "obras": 0, "falhas_com_leitura_preservada": 0,
           "nao_consultadas": 0}
    inicio = datetime.now().astimezone()
    rows = svc.conn.execute(
        "SELECT * FROM work WHERE authority IN ('cvm','bcb','cmn') AND authority NOT LIKE 'invalidated:%' "
        "ORDER BY authority, kind, number, year").fetchall()
    # Falha que é da fonte interrompe a fonte: nenhuma obra seguinte a consulta, e a fonte sai declarada (F-23).
    interrompidas: dict[str, dict[str, Any]] = {}
    for row in rows[:max_obras]:
        fonte = "cvm_normas" if row["authority"] == "cvm" else "bcb"
        if fonte not in fontes:
            continue
        out["obras"] += 1
        if fonte in interrompidas:
            out["nao_consultadas"] += 1
            continue
        caps = repo.captures_for_work(svc.conn, row["id"])
        rw = type("W", (), {"work_id": row["id"]})()
        try:
            if fonte == "cvm_normas":
                ws = _reler_cvm(svc, row, rw)
            else:
                ws = _reler_bcb(svc, row, caps, rw)
        except Unavailable as exc:
            interrompidas[fonte] = {"status": "unavailable", "motivo": exc.reason, **exc.classificacao()}
            out["nao_consultadas"] += 1
            continue
        if ws.situacao != "ilegivel" and _anterior(ws.lido_em, inicio):
            out["falhas_com_leitura_preservada"] += 1  # tentativa frustrada; vale a leitura anterior
            continue
        out["lidas"] += 1
        out["ilegiveis"] += ws.situacao == "ilegivel"
        out["revogadas"] += ws.situacao == "revogada"
        out["canceladas"] += ws.situacao == "cancelada"
    svc._resolver = type(svc._resolver)()
    if not interrompidas:
        return {"status": "ok", **out}
    primeira = {k: v for k, v in next(iter(interrompidas.values())).items() if k != "status"}
    return {"status": "parcial" if out["lidas"] else "indisponivel", **out, **primeira, "fontes": interrompidas}


def _reler_cvm(svc: Any, row: Any, rw: Any) -> WorkStatus:
    """Página do ato CVM; a indisponibilidade que é da fonte (inclusive no `resolve`) sobe ao controlador."""
    tipo = _KIND_TIPO.get(row["kind"])
    if not tipo:
        return _ilegivel(svc.conn, row["id"], "especie_sem_pagina")
    conector = svc._get("cvm_normas")
    try:
        cand = conector.resolve({"tipo": tipo, "numero": int(row["number"])})
    except Unavailable as exc:
        ws = _falha_de_leitura(svc.conn, WorkStatus(row["id"], "ilegivel", _motivo("pagina_do_ato_indisponivel", exc)),
                               svc.home)
        if interrompe_a_fonte(exc):
            raise
        return ws
    if cand is None:
        return _ilegivel(svc.conn, row["id"], "especie_sem_pagina")
    return registrar_cvm(svc.conn, svc.home, conector, cand, rw, propagar=True)


def _anterior(lido_em: str | None, inicio: datetime) -> bool:
    try:
        lido = datetime.fromisoformat(str(lido_em))
    except ValueError:
        return True
    return (lido if lido.tzinfo else lido.astimezone()) < inicio


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
        from freoa_verifica.texto_resposta import texto_do_response

        lida = ler_bcb(texto_do_response(resp))
        ws = WorkStatus(row["id"], lida["situacao"], lida.get("texto_oficial"), lida.get("ato_revogador"),
                        lida.get("data_efeito"), captura, resp.sha256, resp.fetched_at)
    except Unavailable as exc:
        ws = _falha_de_leitura(svc.conn, WorkStatus(row["id"], "ilegivel", _motivo("bcb_indisponivel", exc)), svc.home)
        if interrompe_a_fonte(exc):
            raise  # o controlador interrompe a fonte e a declara (F-23)
        return ws
    except Exception as exc:  # noqa: BLE001 — parse ou banco: ilegivel, nunca vigente
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
