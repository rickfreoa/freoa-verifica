"""Fachada única do FREOA Verifica — tipos simples, chaves em português."""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import threading
from dataclasses import asdict
from contextlib import contextmanager
from functools import wraps
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from freoa_verifica.aliases import WorkKey
from freoa_verifica.authority import RULES_VERSION as AUTHORITY_RULES_VERSION
from freoa_verifica.authority import as_dict as authority_as_dict
from freoa_verifica.authority import classify_authority
from freoa_verifica.citation import Citation, extract, parse_one
from freoa_verifica.courts import normalize_court
from freoa_verifica.search import buscar_and_or, consulta_fts, normalize_fts_query
from freoa_verifica.connectors.base import (
    Candidate,
    ParsedDecision,
    Unavailable,
    get_connector,
    registry,
)
from freoa_verifica.identity import IdentityMismatch, validate_identity, requested_date, declared_identity
from freoa_verifica.ids import new_ulid
from freoa_verifica.parsers.model import (
    document_from_dict,
    EditorialBlock,
    Issue,
    ParsedDocument,
    Provision,
    Redaction,
)
from freoa_verifica.store import blobs, repo
from freoa_verifica.store.db import connect, data_home
from freoa_verifica.temporal import select as temporal_select
from freoa_verifica.transport import _CIRCUIT_BREAKERS
from freoa_verifica import situacao  # C2
from freoa_verifica.verify import (
    MemoryResolver,
    ResolvedWork,
    SourceUnavailable,
    _current_redaction,
    _find_provision,
    _redaction_by_id,
    _result_to_json,
    persistir_resultado,
    pode_negar,
    populate_from_parsed,
    verificar,
)

from freoa_verifica import acervo as _acervo
from freoa_verifica.limites import CANCELADO, PRAZO, EntradaInvalida, cancelado, Sobrecarga, validar as _validar
from freoa_verifica.registro import normalizar as normalizar_registro
from freoa_verifica import derivados as _derivados
from freoa_verifica.registro import politica_atual as _politica_atual

_log = logging.getLogger("freoa_verifica.service")
_ESPERA_CONCORRENCIA = 10.0
_ESPERA_CLOSE = 30.0

from freoa_verifica.sanitizacao import DOC_CLOSE, DOC_OPEN, envolver  # noqa: E402,F401

_LEGIS_CONNECTORS = ("planalto", "cvm_normas", "bcb", "senado")
_JURIS_CONNECTORS = ("stj", "stf", "tcu", "tjsp", "cvm_colegiado")
_DEFAULT_TEXT_LIMIT = 4000
_EMENTA_MAX = 1200
_CLASSES_POR_EXTENSO = (
    ("agravo em recurso especial", "AREsp"), ("recurso especial", "REsp"),
    ("agravo em recurso extraordin[aá]rio", "ARE"), ("recurso extraordin[aá]rio", "RE"),
)


def _authenticated_output(method):
    """Consultas auxiliares obedecem à mesma autenticação das verificações."""
    @wraps(method)
    def checked(self, *args, **kwargs):
        try:
            result = method(self, *args, **kwargs)
            self._authenticate_output(result)
            return result
        except SourceUnavailable as exc:
            return {"status": "unavailable", "motivo": exc.reason,
                    "reason_code": exc.reason}
    return checked


_ANAFORA = re.compile(
    r"\b(?:art(?:igo)?s?\.?|§+|par[áa]grafos?|incisos?|inc\.|al[íi]neas?)[^.;\n]{0,60}?"
    r"\b(?:d|n)[oa]\s+(?:mesm[oa]|referid[oa]|citad[oa]|supracitad[oa]|aludid[oa]|dit[oa]|anterior)\s+"
    r"(?:lei|norma|resolu[çc][ãa]o|decreto|c[óo]digo|diploma|instru[çc][ãa]o|ato|regulamento|estatuto)\b",
    re.IGNORECASE,
)


def _remissoes_anaforicas(texto: str) -> list[dict[str, Any]]:
    """A5 (decisão 0012 mantida): a remissão sem obra explícita é listada, nunca herda obra."""
    return [{"citacao": m.group(0), "span": [m.start(), m.end()],
             "status": "referencia_nao_resolvida", "motivo": "REMISSAO_ANAFORICA"}
            for m in _ANAFORA.finditer(texto)]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate(text: str | None, max_chars: int) -> tuple[str, bool]:
    if not text:
        return "", False
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def _highlight(text: str, q: str, max_chars: int = 280) -> str:
    raw = (text or "").replace("\n", " ").strip()
    if not raw:
        return ""
    terms = [t for t in re.split(r"\s+", q.strip()) if len(t) > 2]
    lower = raw.lower()
    pos = 0
    for term in terms:
        i = lower.find(term.lower())
        if i >= 0:
            pos = max(0, i - 40)
            break
    snippet = raw[pos : pos + max_chars]
    for term in terms:
        snippet = re.sub(
            re.escape(term),
            lambda m: f"«{m.group(0)}»",
            snippet,
            count=1,
            flags=re.IGNORECASE,
        )
    return snippet


def _citation_to_dict(c: Citation | None) -> dict[str, Any] | None:
    if c is None:
        return None
    return {
        "kind": c.kind,
        "raw": c.raw,
        "span": list(c.span),
        "path": c.path,
        "confidence": c.confidence,
        "flags": list(c.flags),
        "work": asdict(c.work) if c.work else None,
        "decision": asdict(c.decision) if c.decision else None,
    }


def _encode_cursor(offset: int) -> str:
    return str(int(offset))


def _decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        return max(0, int(cursor))
    except ValueError:
        return 0


_KIND_ESPECIE = {"decisao_monocratica": "monocratica", "monocratica": "monocratica",
                 "repercussao_geral": "repercussao_geral"}
# Perfis cujo `text` é o documento integral declarado pela fonte (decisão 0038); comprimento não decide.
_PERFIS_INTEIRO_TEOR = frozenset({"stf_pdf", "tjsp_pdf", "cvm_colegiado", "tjdft_inteiro_teor"})


def _species_from_meta(court: str, class_name: str | None, organ: str | None, kind: str | None = None) -> str:
    # Espécie declarada pela fonte prevalece sobre a inferência por classe/órgão (decisão 0038).
    if kind in _KIND_ESPECIE:
        return _KIND_ESPECIE[kind]
    cls = (class_name or "").lower()
    if "súmula vinculante" in cls or "sumula vinculante" in cls or cls == "sv":
        return "sumula_vinculante"
    if cls in {"adi", "adc", "adpf", "ado"}:
        return "controle_concentrado"
    if "repetitivo" in cls or "rr" == cls:
        return "repetitivo"
    if "irdr" in cls or "iac" in cls:
        return "irdr_iac"
    if "súmula" in cls or "sumula" in cls:
        return "sumula"
    if court.upper() in {"CVM", "TCU", "BCB", "CMN"}:
        return "administrativa"
    if organ and any(x in organ.lower() for x in ("pleno", "seção", "secao", "corte especial")):
        return "orgao_cupula"
    return "acordao"


_ESPECIES_PRECEDENTE = frozenset({"sumula", "sumula_vinculante", "repetitivo", "irdr_iac", "repercussao_geral"})
_NAO_VIGENTE = frozenset({"cancelada", "superada", "revisada"})


def _situacao_precedente(attrs_json: str | None, species: str | None) -> dict[str, Any]:
    """Situação estruturada (decisão 0036): ausente = desconhecida, nunca vigente; rótulo A/B segue sendo espécie."""
    if species not in _ESPECIES_PRECEDENTE:
        return {}
    try:
        attrs = json.loads(attrs_json) if attrs_json else {}
    except ValueError:
        attrs = {}
    sit = attrs.get("situacao_precedente") or {"valor": "desconhecida", "texto_oficial": None}
    alertas = []
    if sit.get("valor") in _NAO_VIGENTE:
        alertas.append("PRECEDENTE_NAO_VIGENTE_NA_FONTE")
    if attrs.get("divergencia_na_fonte"):
        alertas.append("LINHAS_DIVERGENTES_NA_FONTE")
    return {"situacao_precedente": sit, **({"alertas": alertas} if alertas else {})}


def _especie_gravada(attrs_json: str | None) -> str | None:
    try:
        return ((json.loads(attrs_json) if attrs_json else {}).get("attributes") or {}).get("species")
    except ValueError:
        return None


def _authority_min_ok(label: str, minimo: str | None) -> bool:
    if not minimo:
        return True
    order = "ABCDE"
    m = minimo.strip().upper()[:1]
    lab = label.strip().upper()[:1]
    if m not in order or lab not in order:
        return True
    return order.index(lab) <= order.index(m)


def _com_prazo(prazo: float, fn, *args, **kwargs):
    """Executa a busca inicial do conector sob o orçamento: PRAZO propagado e espera limitada.
    shortcut: conector bloqueante não é interrompido, só abandonado (thread daemon); sem cancelamento real."""
    import contextvars
    import threading

    restam = prazo - time.monotonic()
    if restam <= 0:
        raise Unavailable("orcamento")
    ctx, box, cancel = contextvars.copy_context(), {}, threading.Event()

    def corpo():
        PRAZO.set(prazo)
        CANCELADO.set(cancel)
        try:
            box["v"] = fn(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001
            box["e"] = exc
    t = threading.Thread(target=ctx.run, args=(corpo,), daemon=True)
    t.start()
    t.join(restam)
    if t.is_alive():
        cancel.set()  # a thread abandonada não confirma gravação (verify.populate_from_parsed / indexar_obra)
        raise Unavailable("orcamento")
    if "e" in box:
        raise box["e"]
    return box["v"]


def _falhas_de_fonte(fontes_status: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Fontes consultadas que falharam (regra 2): nunca viram `ok` com zero itens."""
    return {c: v.get("motivo") or "indisponivel" for c, v in fontes_status.items()
            if v.get("status") == "unavailable" and v.get("motivo") != "offline"}


def _status_com_falhas(status: str, falhas: dict[str, str], n_itens: int) -> dict[str, Any]:
    if not falhas:
        return {"status": status}
    if n_itens:
        return {"status": "parcial", "fontes_indisponiveis": falhas}
    motivo = next(iter(falhas.values()))
    return {"status": "indisponivel", "motivo": motivo, "reason_code": motivo, "fontes_indisponiveis": falhas}


class Verifica:
    """Fachada de serviço: store + conectores + verificação."""

    def __init__(
        self,
        home: str | Path | None = None,
        *,
        registro: str | None = None,
        max_concorrencia: int | None = None,
        exigir_acervo: bool = False,
    ) -> None:
        self.home = Path(home).expanduser().resolve() if home else data_home()
        self.registro = normalizar_registro(registro)
        self.exigir_acervo = exigir_acervo  # servidores: aviso acervo_incompleto nas respostas
        self._acervo_cache: tuple[bool, dict | None] | None = None
        self._read_only = os.environ.get("FV_READ_ONLY", "").strip().lower() in {"1", "true", "yes"}
        if not self._read_only:
            self.home.mkdir(parents=True, exist_ok=True)
        self._db_path = self.home / "verifica.sqlite3"
        if not self._read_only:
            from freoa_verifica.registro import recuperar_purga

            recuperar_purga(self.home)  # purga interrompida entre os dois renames
            boot = connect(self._db_path)
            boot.close()
        self._local = threading.local()
        self._conn_lock = threading.Lock()
        # (conexão, thread dona): cada conexão é fechada na própria thread quando possível.
        self._all_conns: list[tuple[sqlite3.Connection, threading.Thread]] = []
        self._cv = threading.Condition()
        self._ops = 0
        self._excl_owner: int | None = None
        # F02: o limite protege servidores expostos (REST/MCP passam max_concorrencia);
        # uso em processo pela biblioteca ou pela CLI só é limitado se FV_MAX_CONCORRENCIA for definido.
        env_n = os.environ.get("FV_MAX_CONCORRENCIA")
        n = max_concorrencia if max_concorrencia is not None else (int(env_n) if env_n else None)
        self._caro = threading.BoundedSemaphore(max(1, n)) if n is not None else None
        self._resolver = MemoryResolver()
        self._connectors: dict[str, Any] = {}
        self._last_health: dict[str, dict[str, Any]] = {}

    # -- operações ativas / acesso exclusivo (F06) -------------------------

    @contextmanager
    def _operacao(self, caro: bool = False):
        """Conta a operação ativa (só a mais externa de cada thread) e limita as caras."""
        me = threading.get_ident()
        if getattr(self._local, "prof", 0) or self._excl_owner == me:
            self._local.prof = getattr(self._local, "prof", 0) + 1
            try:
                yield
            finally:
                self._local.prof -= 1
            return
        caro = caro and self._caro is not None
        if caro and not self._caro.acquire(timeout=_ESPERA_CONCORRENCIA):
            raise Sobrecarga("operações simultâneas em excesso; tente novamente")
        try:
            with self._cv:
                self._cv.wait_for(lambda: self._excl_owner is None)
                self._ops += 1
            self._local.prof = 1
            try:
                yield
            finally:
                self._local.prof = 0
                with self._cv:
                    self._ops -= 1
                    self._cv.notify_all()
        finally:
            if caro:
                self._caro.release()

    @contextmanager
    def exclusivo(self, timeout: float = 60.0):
        """Bloqueia novas operações e espera as ativas terminarem (troca de banco)."""
        me = threading.get_ident()
        with self._cv:
            if self._excl_owner == me:
                yield
                return
            ok = self._cv.wait_for(lambda: self._ops == 0 and self._excl_owner is None, timeout)
            if not ok:
                raise TimeoutError("operacoes_ativas: há operações em andamento")
            self._excl_owner = me
        try:
            yield
        finally:
            with self._cv:
                self._excl_owner = None
                self._cv.notify_all()

    def _open_conn(self) -> sqlite3.Connection:
        if not self._read_only and not self._db_path.exists():
            from freoa_verifica.registro import recuperar_purga

            recuperar_purga(self.home)  # nunca abrir banco vazio por cima de uma troca pela metade
        target = self._db_path.as_uri() + "?mode=ro" if self._read_only else str(self._db_path)
        # check_same_thread=False só para permitir o fechamento coordenado (lock + exclusivo).
        conn = sqlite3.connect(target, timeout=30.0, uri=self._read_only, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        if self._read_only:
            conn.execute("PRAGMA query_only=ON")
        else:
            conn.execute("PRAGMA journal_mode=WAL")
        with self._conn_lock:
            self._all_conns.append((conn, threading.current_thread()))
        return conn

    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._open_conn()
            self._local.conn = conn
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        return self._get_conn()

    @conn.setter
    def conn(self, value: sqlite3.Connection | None) -> None:
        self._close_all_conns()
        if value is not None:
            file = value.execute("PRAGMA database_list").fetchone()[2]
            if file and Path(file).resolve() == self._db_path.resolve() and not self._read_only:
                # conexão do mesmo banco: troca por uma aberta pelo serviço (fechável por outra thread)
                value.close()
                value = self._open_conn()
                self._local.conn = value
                return
            self._local.conn = value
            with self._conn_lock:
                self._all_conns.append((value, threading.current_thread()))

    def _close_all_conns(self, strict: bool = False) -> None:
        """Fecha todas as conexões; falhas são registradas e a conexão fica na lista."""
        falhas: list[str] = []
        with self._conn_lock:
            restantes = []
            for c, dono in self._all_conns:
                try:
                    c.close()
                except Exception as exc:  # noqa: BLE001
                    _log.error("falha ao fechar conexão SQLite (dono=%s): %s", dono.name, exc)
                    falhas.append(f"{dono.name}: {exc}")
                    restantes.append((c, dono))
            self._all_conns[:] = restantes
        self._local = threading.local()
        if falhas and strict:
            raise RuntimeError("conexoes_nao_fechadas: " + "; ".join(falhas)[:200])

    def close(self) -> None:
        """Fecha as conexões; com operação ativa após o prazo, NÃO fecha (F06) e levanta TimeoutError."""
        try:
            with self.exclusivo(timeout=_ESPERA_CLOSE):
                self._close_all_conns()
        except TimeoutError:
            _log.error("close(): operações ainda ativas após %ss; conexões mantidas abertas", _ESPERA_CLOSE)
            raise

    def __enter__(self) -> Verifica:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _clear_caches(self) -> None:
        self._acervo_cache = None
        self._resolver = MemoryResolver()
        self._connectors.clear()
        self._last_health.clear()
        self._last_juris_capture = None

    # ------------------------------------------------------------------
    # Conectores / registro
    # ------------------------------------------------------------------

    def _get(self, connector_id: str):
        if connector_id not in self._connectors:
            self._connectors[connector_id] = get_connector(connector_id)
            if connector_id == "stj":
                self._connectors[connector_id].db_path = self.home / "stj_fts.sqlite"
                self._connectors[connector_id].resource_dir = self.home / "stj-resources"
        return self._connectors[connector_id]

    def registrar(self, rw: ResolvedWork) -> None:
        """Registra obra já resolvida no resolver em memória (testes/fixtures)."""
        self._resolver.add(rw)

    def indexar_obra(
        self,
        *,
        source_id: str,
        work_key: WorkKey,
        document: ParsedDocument,
        body: bytes,
        url: str,
        fetched_at: str | None = None,
        work_date: str | None = None,
        label: str | None = None,
        fts_alvo: str = "fts_redaction",
    ) -> ResolvedWork:
        if cancelado():
            raise Unavailable("orcamento")
        declared = validate_identity(work_key, document, work_date)
        if not work_key.year and declared and declared.year:
            work_key = declared
            work_date = work_date or declared_identity(document)[1]
        demovida = False
        if fts_alvo == "fts_redaction" and source_id in repo.FONTES_COMPILADAS:
            existente = self.conn.execute(
                "SELECT id FROM work WHERE authority=? AND kind=? AND number=? AND year=?",
                (work_key.authority, work_key.kind, work_key.number, work_key.year)).fetchone()
            if existente:  # 0034: perda de dispositivos => captura não canônica (staging + candidato)
                vigente = repo.avaliar_monotonia(self.conn, existente["id"])[0]
                if not vigente <= {(p.scope or "", p.path) for p in document.provisions}:
                    fts_alvo, demovida = "fts_staging", True
        rw = populate_from_parsed(
            self.conn,
            source_id=source_id,
            work_key=work_key,
            document=document,
            body=body,
            url=url,
            fetched_at=fetched_at,
            work_date=work_date,
            label=label,
            home=self.home,
            fts_alvo=fts_alvo,
        )
        if cancelado():
            raise Unavailable("orcamento")
        if rw.capture_id:
            repo.persist_parsed_document(
                self.conn,
                capture_id=rw.capture_id,
                document=document,
                work_id=rw.work_id,
                work_date=work_date,
                amending_act_texts=rw.amending_act_texts,
                candidato_ao_vivo=(True if fts_alvo == "fts_staging" else None),
            )
        situacao.registrar_do_corpo(self.conn, rw, source_id, body)  # C2
        if demovida:  # o modelo canônico anterior permanece
            canonica = self._rebuild_from_db(work_key, _exact=True)
            rw = canonica if isinstance(canonica, ResolvedWork) else rw
        self._resolver.add(rw)
        if work_key.year <= 0:
            with self.conn:
                self.conn.execute("INSERT OR IGNORE INTO work_year_issue(work_id,reason,capture_id) VALUES (?,?,?)",
                                  (rw.work_id, "ANO_NAO_DECLARADO", rw.capture_id))
        return rw

    # ------------------------------------------------------------------
    # Resolver sob demanda
    # ------------------------------------------------------------------

    def _rebuild_from_db(self, work: WorkKey, *, _exact=False) -> ResolvedWork | list[ResolvedWork] | None:
        if not self._read_only and self.conn.execute("SELECT 1 FROM work WHERE authority=? AND kind=? AND number=? AND year=0",
                             (work.authority, work.kind, work.number)).fetchone():
            self.reparar_anos()
        rows = self.conn.execute(
            "SELECT * FROM work WHERE authority=? AND kind=? AND number=? AND (year=? OR (?=0 AND ?=0))",
            (work.authority, work.kind, work.number, work.year, work.year, int(_exact)),
        ).fetchall()
        if len(rows) > 1:
            return [self._rebuild_from_db(WorkKey(r["authority"], r["kind"], r["number"], r["year"]), _exact=True)
                    for r in rows]
        row = rows[0] if rows else None
        if row is None:
            return None
        work_id = row["id"]
        caps = repo.captures_for_work(self.conn, work_id)
        _, perdas, conhecidos = repo.avaliar_monotonia(self.conn, work_id)  # 0034
        rebaixadas = {d["capture_id"] for d in perdas}
        # captura canônica mais recente: nem candidata ao vivo nem rebaixada por perda estrutural
        cap = next((c for c in caps if not c.get("candidato_ao_vivo") and c["id"] not in rebaixadas),
                   caps[0] if caps else None)
        saved = repo.get_parsed_document(self.conn, cap["id"]) if cap else None
        incomplete = False
        try:
            if not saved or not saved["model_json"] or not saved["events_json"]:
                raise ValueError("modelo ausente")
            doc = document_from_dict(json.loads(saved["model_json"]))
            events = json.loads(saved["events_json"])
            if not isinstance(events, dict) or set(events) != {p.path for p in doc.provisions}:
                raise ValueError("eventos ausentes")
            amending_texts = json.loads(saved["amending_texts_json"])
            if not isinstance(amending_texts, dict):
                raise ValueError("contexto ausente")
        except (ValueError, TypeError, KeyError):
            incomplete = True
            doc = ParsedDocument(
                profile="store", parser_version="incomplete", title=row["label"] or "",
                ementa=None, text="", issues=[Issue(
                    "DADOS_PERSISTIDOS_INCOMPLETOS", None, "modelo completo ausente", "document",
                )],
            )
            amending_texts = {}
        declared = validate_identity(work, doc, saved["work_date"] if saved else None)
        if declared is None and doc.profile in {"planalto","cvm_docx","cvm_pdf","cvm_html","bcb_json","senado_norma"}:
            raise SourceUnavailable("IDENTIDADE_NAO_DECLARADA")
        wk = WorkKey(row["authority"], row["kind"], row["number"], int(row["year"]))
        rw = ResolvedWork(
            work_id=work_id,
            work_key=wk,
            document=doc,
            work_date=saved["work_date"] if saved else None,
            capture_id=cap["id"] if cap else None,
            sha256=cap["sha256"] if cap else None,
            url=cap["url"] if cap else None,
            fetched_at=cap["fetched_at"] if cap else None,
            quarantined=doc.quarantined,
            amending_act_texts=amending_texts,
            persisted_incomplete=incomplete,
            caminhos_conhecidos=frozenset(conhecidos),
        )
        return rw

    def reparar_anos(self) -> dict:
        """Repara projeção de identidade a partir de modelos de capturas autenticadas.

        Recibos, bytes, extrações e ocorrências permanecem intactos. Uma pendência
        explícita acompanha cada obra sem ano demonstrável; repetir é seguro.
        """
        repaired, pending = [], []
        rows = self.conn.execute("SELECT * FROM work WHERE year<=0").fetchall()
        for row in rows:
            evidence, reason = [], "ANO_NAO_DECLARADO"
            for cap in repo.captures_for_work(self.conn, row["id"]):
                saved = repo.get_parsed_document(self.conn, cap["id"])
                if not saved or not saved["model_json"]:
                    continue
                try:
                    self._authenticate_capture(cap["id"])
                    doc = document_from_dict(json.loads(saved["model_json"]))
                    key = WorkKey(row["authority"], row["kind"], row["number"], 0)
                    declared = validate_identity(key, doc)
                    if declared and declared.year > 0:
                        evidence.append((declared.year, cap["id"]))
                except (SourceUnavailable, IdentityMismatch, ValueError) as exc:
                    reason = getattr(exc, "reason", str(exc))
            years = {year for year, _ in evidence}
            if len(years) > 1:
                reason = "ANO_DECLARADO_CONFLITANTE"
            elif len(years) == 1:
                year, capture = evidence[0]
                try:
                    with self.conn:
                        self.conn.execute("UPDATE work SET year=? WHERE id=?", (year, row["id"]))
                        self.conn.execute("DELETE FROM work_year_issue WHERE work_id=?", (row["id"],))
                    repaired.append({"work_id": row["id"], "year": year, "capture_id": capture})
                    continue
                except sqlite3.IntegrityError:
                    reason = "IDENTIDADE_ANO_DUPLICADA"
            with self.conn:
                self.conn.execute("INSERT INTO work_year_issue(work_id,reason,capture_id) VALUES (?,?,?) "
                                  "ON CONFLICT(work_id) DO UPDATE SET reason=excluded.reason,capture_id=excluded.capture_id",
                                  (row["id"], reason, evidence[0][1] if evidence else None))
            pending.append({"work_id": row["id"], "reason": reason})
        self._resolver = MemoryResolver()
        return {"reparados": repaired, "pendentes": pending}

    def ressincronizar_situacao(self, **kw) -> dict:  # C2
        """Relê a situação dos atos CVM/BCB/CMN do acervo (antes de gerar snapshot)."""
        return situacao.ressincronizar(self, **kw)

    def reprocessar_capturas(self) -> dict:
        """Recalcula modelos derivados dos mesmos bytes, preservando recibos de captura."""
        from freoa_verifica.transport import Response
        self.reparar_anos()
        rows = self.conn.execute("SELECT c.*, p.work_id, p.work_date, p.amending_texts_json FROM capture c JOIN parsed_document p ON p.capture_id=c.id WHERE p.model_json IS NOT NULL").fetchall()
        counts = {'reprocessados':0, 'divergentes':[], 'falhas':[]}
        for row in rows:
            if row['source_id'] not in {'planalto','cvm_normas','bcb'}:
                continue
            work = self.conn.execute('SELECT * FROM work WHERE id=?',(row['work_id'],)).fetchone()
            if not work or work['authority'].startswith('invalidated:'):
                continue
            try:
                body = blobs.get_blob(row['sha256'],home=self.home)
                response = Response(row['url'],row['final_url'],row['status'],json.loads(row['headers_json']),body,row['sha256'],row['fetched_at'],[],row['mime'])
                doc = self._get(row['source_id']).parse(response)
                key = WorkKey(work['authority'],work['kind'],work['number'],work['year'])
                validate_identity(key,doc,row['work_date'])
                repo.persist_parsed_document(self.conn,capture_id=row['id'],document=doc,work_id=work['id'],work_date=row['work_date'],amending_act_texts=json.loads(row['amending_texts_json'] or '{}'))
                counts['reprocessados'] += 1
            except IdentityMismatch:
                with self.conn:
                    self.conn.execute('UPDATE work SET authority=? WHERE id=?',('invalidated:'+work['authority'],work['id']))
                counts['divergentes'].append(work['id'])
            except Exception as exc:
                counts['falhas'].append({'capture_id':row['id'],'motivo':str(exc)})
        with self.conn:  # 0034: capturas que perdem dispositivos deixam de ser canônicas
            counts['divergentes'] += repo.aplicar_monotonia(self.conn)
        self._resolver = MemoryResolver()
        return counts

    def _identity_rows(self, invalidated=False):
        predicate = "LIKE" if invalidated else "NOT LIKE"
        return self.conn.execute(
            "SELECT w.*,p.capture_id,p.work_date,json_extract(p.model_json,'$.profile') AS p_profile,"
            "json_extract(p.model_json,'$.title') AS p_title,substr(json_extract(p.model_json,'$.text'),1,10000) AS p_text "
            "FROM work w JOIN parsed_document p ON p.work_id=w.id WHERE p.model_json IS NOT NULL "
            f"AND w.authority {predicate} 'invalidated:%'").fetchall()

    def restaurar_identidades_validadas(self) -> list[str]:
        restored = []
        for row in self._identity_rows(invalidated=True):
            authority = row['authority'].removeprefix('invalidated:')
            key = WorkKey(authority,row['kind'],row['number'],row['year'])
            doc = ParsedDocument(row['p_profile'],'identity',row['p_title'],None,row['p_text'] or '')
            if key.kind == 'constituicao':
                titles = [line for line in doc.text.splitlines()[:4] if re.match(r'CONSTITUI[ÇC][ÃA]O DA REP',line,re.I)]
                if titles:
                    doc.title = titles[0]
            try:
                if validate_identity(key,doc,row['work_date']) is None:
                    continue
            except IdentityMismatch:
                continue
            with self.conn:
                self.conn.execute('UPDATE work SET authority=? WHERE id=?',(authority,row['id']))
                if doc.title != row['p_title']:
                    self.conn.execute("UPDATE parsed_document SET model_json=json_set(model_json,'$.title',?) WHERE capture_id=?",(doc.title,row['capture_id']))
            restored.append(row['id'])
        self._resolver = MemoryResolver()
        return restored

    def reparar_identidades(self) -> list[dict]:
        repairs = []
        with self.conn:
            self.conn.execute("UPDATE decision SET class='Acordao' WHERE court='TCU' AND class IS NULL AND EXISTS (SELECT 1 FROM decision_document dd JOIN capture c ON c.id=dd.capture_id WHERE dd.decision_id=decision.id AND c.source_id='tcu')")
            self.conn.execute("UPDATE decision_document SET kind='ementa',nivel_prova='ementa_capturada' WHERE capture_id IN (SELECT id FROM capture WHERE source_id='tcu' AND mime='application/json') AND sha256 IS NOT NULL AND text IS NOT NULL")
            self.conn.execute("UPDATE decision SET nivel_prova='ementa_capturada' WHERE court='TCU' AND EXISTS (SELECT 1 FROM decision_document dd WHERE dd.decision_id=decision.id AND dd.nivel_prova='ementa_capturada')")
        for row in self._identity_rows():
            key = WorkKey(row['authority'],row['kind'],row['number'],row['year'])
            doc = ParsedDocument(row['p_profile'],'identity',row['p_title'],None,row['p_text'] or '')
            try:
                validate_identity(key,doc,row['work_date'])
            except IdentityMismatch:
                with self.conn:
                    self.conn.execute("UPDATE work SET authority=? WHERE id=?", ('invalidated:' + key.authority, row['id']))
                repairs.append({'work_id':row['id'], 'requested':asdict(key), 'reason':'IDENTIDADE_DIVERGENTE'})
        with self.conn:
            self.conn.execute("DELETE FROM fts_redaction WHERE work_label IN (SELECT label FROM work WHERE authority LIKE 'invalidated:%') AND work_label NOT IN (SELECT label FROM work WHERE authority NOT LIKE 'invalidated:%' AND label IS NOT NULL)")
        self._resolver = MemoryResolver()
        return repairs

    def _offline(self) -> bool:
        return self._read_only or os.environ.get("FV_OFFLINE", "").strip() in {"1", "true", "yes"}

    def _capture_work(self, work: WorkKey, requested_work_date=None) -> ResolvedWork | list[ResolvedWork] | None:
        if self._offline():
            return None
        key = {
            "authority": work.authority,
            "kind": work.kind,
            "number": work.number,
            "year": work.year or None,
            "tipo": {"lei_complementar":"LCP", "decreto_lei":"DEL", "medida_provisoria":"MPV", "constituicao":"CF", "resolucao_bcb":"Resolução BCB", "circular":"Circular", "carta_circular":"Carta Circular"}.get(work.kind, "Resolução CMN" if work.authority == "cmn" else work.kind.upper()),
            "numero": work.number,
            "ano": work.year or None,
        }
        order = []
        if work.authority == "cvm":
            order = ["cvm_normas"]
        elif work.authority in {"bcb", "cmn"}:
            order = ["bcb"]
        elif work.authority == "federal":
            order = ["planalto", "senado"]
        else:
            order = list(_LEGIS_CONNECTORS)

        errors: list[str] = []
        for cid in order:
            try:
                conn_obj = self._get(cid)
                cand = conn_obj.resolve(key)
                if cand is None:
                    continue
                resp = conn_obj.fetch(cand)
                parsed = conn_obj.parse(resp)
                if isinstance(parsed, ParsedDecision):
                    continue
                if validate_identity(work, parsed, requested_work_date) is None:
                    raise Unavailable("IDENTIDADE_NAO_DECLARADA")
                label = cand.title or f"{work.kind} {work.number}/{work.year}"
                rw_novo = self.indexar_obra(
                    source_id=cid,
                    work_key=work,
                    document=parsed,
                    body=resp.body,
                    url=resp.final_url or resp.url,
                    fetched_at=resp.fetched_at,
                    label=label,
                )
                if cid == "cvm_normas":  # C2: página do ato sempre capturada como evidência de situação
                    situacao.registrar_cvm(self.conn, self.home, conn_obj, cand, rw_novo)
                return rw_novo
            except IdentityMismatch:
                raise
            except Unavailable as exc:
                errors.append(f"{cid}:{exc.reason}")
            except Exception as exc:  # noqa: BLE001 — captura sob demanda
                errors.append(f"{cid}:{type(exc).__name__}")
        if errors:
            raise SourceUnavailable(";".join(errors[:3]))
        return None

    def _resolve(self, work: WorkKey, requested_work_date=None, *, strict: bool = False) -> ResolvedWork | list[ResolvedWork] | None:
        """strict: obra ausente do acervo sem poder consultar a fonte é lacuna de cobertura, não negativa (A2)."""
        hit = self._resolver.resolve(work)
        if isinstance(hit, ResolvedWork):
            declared = validate_identity(work, hit.document, requested_work_date or hit.work_date)
            if declared is None and hit.document.profile in {"planalto","cvm_docx","cvm_pdf","cvm_html","bcb_json","senado_norma"}:
                raise SourceUnavailable("IDENTIDADE_NAO_DECLARADA")
        if hit is not None:
            return hit
        rebuilt = self._rebuild_from_db(work)
        if isinstance(rebuilt, list):
            return rebuilt
        if rebuilt is not None:
            validate_identity(work, rebuilt.document, requested_work_date)
            self._resolver.add(rebuilt)
            return rebuilt
        got = self._capture_work(work, requested_work_date)
        if got is None and strict and self._offline():
            raise SourceUnavailable("COBERTURA")
        return got

    @staticmethod
    def _sem_dispositivo(rw: ResolvedWork, path: str, **extra) -> dict[str, Any]:
        """C1: dispositivo ausente só vira inexistente se pode_negar autoriza."""
        motivo = pode_negar(rw, path)
        if motivo is None:
            return {"status": "inexistente", "work_id": rw.work_id, "caminho": path, **extra}
        if motivo == "COBERTURA":
            return {"status": "indisponivel", "motivo": motivo, "reason_code": motivo, **extra}
        return {"status": "unknown", "motivo": motivo, "reason_code": motivo,
                "work_id": rw.work_id, "caminho": path, **extra}

    # ------------------------------------------------------------------
    # Busca legislação
    # ------------------------------------------------------------------

    @_authenticated_output
    def buscar_legislacao(
        self,
        q: str,
        fonte: str | None = None,
        data: str | None = None,
        limite: int = 10,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        offset = _decode_cursor(cursor)
        limite = max(1, min(int(limite), 50))
        offline = os.environ.get("FV_OFFLINE", "").strip() in {"1", "true", "yes"}
        ao_vivo = fonte != "__somente_local__" and not offline
        filtro_fonte = fonte if fonte and fonte != "__somente_local__" else None
        total = limite + offset + 5

        def buscar_em(tabela):
            return lambda fts, n: repo.search_redactions(
                self.conn, fts, n, source_id=filtro_fonte, table=tabela)
        args = (lambda r: r["text"], lambda r: (r["work_label"], r["path"], r["text"]), total, limite + offset)
        res = buscar_and_or(q, buscar_em("fts_redaction"), *args)
        local = res["linhas"]
        modo_busca = "ampliada" if res["fts"] and not res["and"] else "normal"
        if ao_vivo:  # staging só é consultado quando a busca pede candidatos ao vivo (A7)
            for r in buscar_and_or(q, buscar_em("fts_staging"), *args)["linhas"]:
                r["_staging"] = True
                local.append(r)
        items: list[dict[str, Any]] = []
        for row in local:
            receipts = self.conn.execute(
                "SELECT DISTINCT e.capture_id FROM redaction r JOIN provision p ON p.id=r.provision_id "
                "JOIN occurrence o ON o.redaction_id=r.id JOIN extract e ON e.id=o.extract_id "
                "WHERE r.text=? AND p.path=?", (row["text"], row["path"])).fetchall()
            rebaixo = None
            try:
                if not receipts:
                    raise SourceUnavailable("EVIDENCIA_AUSENTE")
                for receipt in receipts:
                    self._authenticate_capture(receipt[0])
            except SourceUnavailable as exc:
                rebaixo = exc.reason
            work_row = self.conn.execute(
                "SELECT id, label, authority, kind, number, year FROM work WHERE label=? LIMIT 1",
                (row["work_label"],),
            ).fetchone()
            if work_row is None:
                work_row = self.conn.execute(
                    "SELECT id, label, authority, kind, number, year FROM work WHERE number=? LIMIT 1",
                    (row["work_label"],),
                ).fetchone()
            vigencia = None
            if work_row and data and not rebaixo:
                wk = WorkKey(
                    work_row["authority"],
                    work_row["kind"],
                    work_row["number"],
                    int(work_row["year"]),
                )
                try:
                    rw = self._resolve(wk)
                    if isinstance(rw, ResolvedWork):
                        prov = rw.document.provision(row["path"])
                        if prov:
                            tr = temporal_select(prov, data, work_date=rw.work_date)
                            vigencia = {
                                "status": tr.status,
                                "regras": tr.rules_applied,
                                "flags": tr.flags,
                            }
                except Exception:  # noqa: BLE001
                    vigencia = {"status": "unknown"}
            items.append(
                {
                    "obra": row["work_label"],
                    "caminho": row["path"],
                    "rotulo": row["work_label"],
                    "trecho": _highlight(row["text"], q),
                    "url_oficial": None,
                    "capture_id": None,
                    "vigencia": vigencia,
                    "work_id": work_row["id"] if work_row and not rebaixo else None,
                    "pertinencia": row["pertinencia"],
                    "correspondencia": row["correspondencia"],
                    "candidato_ao_vivo": bool(row.get("_staging")),
                    **({"nao_indexado": True, "motivo": rebaixo} if rebaixo else {}),
                }
            )

        fontes = [fonte] if fonte and fonte != "__somente_local__" else list(_LEGIS_CONNECTORS)
        fontes_status: dict[str, dict[str, Any]] = {}

        def nao_consultada(cid, motivo):
            fontes_status[cid] = {"status": "nao_consultada", "motivo": motivo, "parcial": False}
        cite = parse_one(q)
        for cid in fontes:
            if cid not in registry():
                continue
            if not ao_vivo:
                nao_consultada(cid, "offline" if offline else "somente_local")
                continue
            if len(items) >= limite:
                nao_consultada(cid, "limite_atingido_no_acervo_local")
                continue
            try:
                conn_obj = self._get(cid)
                lookup = bool(cite and cite.work)
                if not lookup and not getattr(conn_obj, "coverage", {}).get("busca_textual", True):
                    nao_consultada(cid, "busca_textual_nao_suportada")
                    continue
                filtros: dict[str, Any] = {}
                if lookup:
                    filtros["numero"] = cite.work.number
                    if cite.work.year:
                        filtros["ano"] = cite.work.year
                    filtros["tipo"] = cite.work.kind
                cands = conn_obj.search(q, **filtros)
                got = 0
                for cand in cands[: max(0, limite - len(items))]:
                    it = self._index_candidate_legis(conn_obj, cand)
                    if not it.get("capture_id"):
                        it["nao_indexado"] = True
                    items.append(self._rebaixar_busca(it))
                    got += 1
                fontes_status[cid] = {
                    "status": "ok",
                    "motivo": None,
                    "parcial": got < len(cands),
                    # contrato com os conectores: lista com .total/.truncado quando a fonte informa mais.
                    "total": getattr(cands, "total", len(cands)),
                    "truncado": bool(getattr(cands, "truncado", False)) or got < len(cands),
                }
            except Unavailable as exc:
                fontes_status[cid] = {"status": "unavailable", "motivo": exc.reason, "parcial": False}
            except Exception as exc:  # noqa: BLE001
                fontes_status[cid] = {
                    "status": "unavailable",
                    "motivo": f"{type(exc).__name__}:{exc}"[:200],
                    "parcial": False,
                }

        page = items[offset:offset + limite]
        truncado = len(items) > offset + limite or any(v.get("truncado") for v in fontes_status.values())
        parcial = truncado or any(i.get("nao_indexado") for i in page)
        return {
            **_status_com_falhas("parcial" if parcial else "ok", _falhas_de_fonte(fontes_status), len(page)),  # 0024
            "itens": page,
            "resultados": page,
            "fontes": fontes_status,
            "total_parcial": offset + len(items),
            "total": max(len(items), sum(v.get("total") or 0 for v in fontes_status.values())),
            "truncado": truncado,
            "cursor": _encode_cursor(offset + limite) if len(items) > offset + limite else None,
            "consulta": q,
            "data": data,
            "modo_busca": modo_busca,
            "tesauro": res["tesauro"],
        }

    def _index_candidate_legis(self, connector, cand: Candidate) -> dict[str, Any]:
        capture_id = None
        failure = None
        path = None
        trecho = cand.snippet or ""
        try:
            resp = connector.fetch(cand)
            parse_candidate = getattr(connector, "parse_candidate", None)
            parsed = parse_candidate(resp, cand) if parse_candidate else connector.parse(resp)
            if isinstance(parsed, ParsedDocument):
                meta = cand.metadata or {}
                number = str(meta.get("numero") or meta.get("number") or cand.key)
                year = int(meta.get("ano") or meta.get("year") or 0)
                source_kind = str(meta.get("tipo") or meta.get("kind") or "lei")
                kind = source_kind.lower()
                authority = "cvm" if connector.id.startswith("cvm") else (
                    "bcb" if connector.id == "bcb" else "federal"
                )
                if connector.id == "cvm_normas":
                    kind = {"resolucoes": "resolucao", "instrucoes": "instrucao",
                            "pareceres": "parecer_orientacao"}.get(kind, kind)
                elif connector.id == "bcb":
                    candidate_cite = parse_one(f"{source_kind} {number}")
                    if candidate_cite and candidate_cite.work:
                        authority = candidate_cite.work.authority
                        kind = candidate_cite.work.kind
                wk = WorkKey(authority, kind, re.sub(r"\D", "", number) or number, year)
                # A7: candidato ao vivo é gravado direto no staging, nunca no FTS canônico.
                rw = self.indexar_obra(
                    source_id=connector.id,
                    work_key=wk,
                    document=parsed,
                    body=resp.body,
                    url=resp.final_url or resp.url,
                    fetched_at=resp.fetched_at,
                    label=cand.title,
                    fts_alvo="fts_staging",
                )
                capture_id = rw.capture_id
                if connector.id == "cvm_normas":  # C2
                    situacao.registrar_cvm(self.conn, self.home, connector, cand, rw)
                if parsed.provisions:
                    path = parsed.provisions[0].path
                    trecho = parsed.provisions[0].redactions[0].text if parsed.provisions[0].redactions else trecho
        except Exception as exc:  # noqa: BLE001
            failure = getattr(exc, "reason", str(exc)) or type(exc).__name__
        text, trunc = _truncate(trecho, 280)
        return {
            "obra": cand.title,
            "caminho": path,
            "rotulo": cand.title,
            "trecho": text,
            "url_oficial": cand.url,
            "capture_id": capture_id,
            "motivo": failure,
            "vigencia": None,
            "fonte": connector.id,
            "truncado": trunc,
        }

    # ------------------------------------------------------------------
    # Citação / dispositivo
    # ------------------------------------------------------------------

    @_authenticated_output
    def resolver_citacao(self, citacao: str) -> dict[str, Any]:
        cite = parse_one(citacao)
        out: dict[str, Any] = {
            "citacao": citacao,
            "parseada": _citation_to_dict(cite),
            "work_id": None,
            "caminho": None,
            "status": "formato_invalido",
        }
        if cite is None:
            return out
        if "dispositivo_invalido" in cite.flags:
            out["identity"] = {"status": "not_found", "reason_code": "formato_invalido"}
            return out
        if cite.work is None:
            out["status"] = "formato_invalido" if cite.kind == "norma" else "encontrada"
            return out
        if (pend := self._so_conferencia(cite, citacao)) is not None:
            return {**out, **pend}
        try:
            resolved = self._resolve(cite.work, strict=True)
        except SourceUnavailable as exc:
            out["status"] = "indisponivel"
            out["motivo"] = exc.reason
            return out
        if resolved is None:
            out["status"] = "inexistente"
            return out
        if isinstance(resolved, list):
            out["status"] = "ambigua"
            out["candidatos"] = [r.work_id for r in resolved]
            return out
        if cite.path:
            provision = _find_provision(resolved.document, cite.path)
            if provision is None:
                neg = self._sem_dispositivo(resolved, cite.path)
                if neg["status"] == "inexistente":
                    out.update(status="inexistente", caminho=cite.path,
                               motivo="DISPOSITIVO_INEXISTENTE",
                               identity={"status": "not_found", "reason_code": "DISPOSITIVO_INEXISTENTE"})
                else:
                    out.update(status="indisponivel" if neg["status"] == "indisponivel" else "unknown",
                               caminho=cite.path, motivo=neg["motivo"],
                               identity={"status": "unavailable" if neg["status"] == "indisponivel" else "unknown",
                                         "reason_code": neg["motivo"]})
                return out
        out["status"] = "encontrada"
        out["work_id"] = resolved.work_id
        out["caminho"] = cite.path
        out["url_oficial"] = resolved.url
        out["capture_id"] = resolved.capture_id
        return out

    @_authenticated_output
    def obter_dispositivo(
        self,
        citacao: str | None = None,
        work_id: str | None = None,
        caminho: str | None = None,
        data: str | None = None,
    ) -> dict[str, Any]:
        rw: ResolvedWork | None = None
        path = caminho
        if citacao:
            cite = parse_one(citacao)
            if (pend := self._so_conferencia(cite, citacao)) is not None:
                return pend
            if cite and cite.work:
                path = path or cite.path
                try:
                    resolved = self._resolve(cite.work, strict=True)
                except SourceUnavailable as exc:
                    return {"status": "indisponivel", "motivo": exc.reason}
                if isinstance(resolved, list):
                    return {"status": "ambigua", "candidatos": [r.work_id for r in resolved]}
                rw = resolved
            elif cite is None:
                return {"status": "formato_invalido"}
        if rw is None and work_id:
            for cached in self._resolver.works.values():
                if cached.work_id == work_id:
                    rw = cached
                    break
            if rw is None:
                row = self.conn.execute(
                    "SELECT authority, kind, number, year FROM work WHERE id=?",
                    (work_id,),
                ).fetchone()
                if row:
                    try:
                        resolved = self._resolve(
                            WorkKey(row["authority"], row["kind"], row["number"], int(row["year"]))
                        )
                        if isinstance(resolved, ResolvedWork):
                            rw = resolved
                    except SourceUnavailable as exc:
                        return {"status": "indisponivel", "motivo": exc.reason}
        if rw is None:
            return {"status": "inexistente"}
        sit = situacao.carregar(self.conn, rw, self.home)  # C2
        if not path:
            return {
                "status": "encontrada",
                "work_id": rw.work_id,
                "situacao_obra": situacao.resumo(sit),  # C2
                "caminho": None,
                "texto": None,
                "aviso": "informe caminho ou citação com dispositivo",
                "evidencia": {
                    "capture_id": rw.capture_id,
                    "url": rw.url,
                    "fetched_at": rw.fetched_at,
                    "sha256": rw.sha256,
                },
            }
        if rw.persisted_incomplete:
            return {"status": "unknown", "reason_code": "DADOS_PERSISTIDOS_INCOMPLETOS"}
        prov = _find_provision(rw.document, path)
        if prov is None:
            return self._sem_dispositivo(rw, path)

        tr = temporal_select(prov, data, work_date=rw.work_date, amending_act_texts=rw.amending_act_texts, fetched_at=rw.fetched_at, quarantined=rw.quarantined)
        tr = situacao.aplicar_situacao_tr(tr, sit, data)  # C2
        red = _redaction_by_id(prov, tr.redaction_id) if tr.redaction_id else None
        # C3: com data pedida e sem redação selecionada, a atual não substitui a resposta.
        if red is None and data is None and tr.reason not in {"INICIO_SUCESSOR_DESCONHECIDO", "CAPTURA_DATA_INVALIDA"}:
            red = _current_redaction(prov)
        texto = red.text if red else None
        vigente = _current_redaction(prov)
        texto_atual = None
        if red is None and vigente is not None and not vigente.struck:
            texto_atual = {
                "rotulo": "redação atual da fonte; não é a redação da data pedida",
                "texto": _truncate(vigente.text, _DEFAULT_TEXT_LIMIT)[0],
            }

        anteriores = []
        for i, red in enumerate(prov.redactions):
            if red is vigente and not red.struck and not red.superseded_without_strike:
                continue  # M1: a vigente não é redação anterior
            anteriores.append(
                {
                    "rotulo": f"redação {i + 1}",
                    "intervalo": None,
                    "riscada": red.struck,
                    "trecho": _truncate(red.text, 200)[0],
                }
            )
        anotacoes = []
        for red in prov.redactions:
            for ann in red.annotations:
                anotacoes.append(
                    {
                        "kind": ann.kind,
                        "raw": ann.raw,
                        "act_ref": ann.act_ref,
                        "act_date": ann.act_date,
                    }
                )
        text_out, trunc = _truncate(texto, _DEFAULT_TEXT_LIMIT) if texto is not None else (None, False)
        return {
            "status": "encontrada",
            "work_id": rw.work_id,
            "situacao_obra": situacao.resumo(sit),  # C2
            "caminho": path,
            "texto": text_out,
            "texto_atual": texto_atual,
            "truncado": trunc,
            "redacao_anterior_ausente_na_fonte": self._anterior_ausente(prov),
            "vigencia": {
                "status": tr.status,
                "reason_code": tr.reason,
                "regras": tr.rules_applied,
                "flags": tr.flags,
                "intervalo": (
                    {"inicio": tr.interval.start, "fim": tr.interval.end}
                    if tr.interval
                    else None
                ),
            },
            "redacoes_anteriores": anteriores,
            "anotacoes": anotacoes,
            "evidencia": {
                "capture_id": rw.capture_id,
                "url": rw.url,
                "fetched_at": rw.fetched_at,
                "sha256": rw.sha256,
            },
        }

    @_authenticated_output
    def historico_dispositivo(self, citacao: str) -> dict[str, Any]:
        cite = parse_one(citacao)
        if cite is None or cite.work is None or not cite.path:
            return {"status": "formato_invalido", "citacao": citacao}
        if (pend := self._so_conferencia(cite, citacao)) is not None:
            return pend
        try:
            resolved = self._resolve(cite.work, strict=True)
        except SourceUnavailable as exc:
            return {"status": "indisponivel", "motivo": exc.reason}
        if resolved is None:
            return {"status": "inexistente"}
        if isinstance(resolved, list):
            return {"status": "ambigua"}
        prov = _find_provision(resolved.document, cite.path)
        if prov is None:
            return self._sem_dispositivo(resolved, cite.path)
        from freoa_verifica.temporal import build_intervals

        dated, rules, needs_judgment, gflags = build_intervals(
            prov,
            work_date=resolved.work_date,
            amending_act_texts=resolved.amending_act_texts,
        )
        sit = situacao.carregar(self.conn, resolved, self.home)
        linha = []
        for d in dated:
            fim, fim_desc = d.end, d.end_unknown
            fl = list(d.flags)
            if fim is None and not fim_desc and sit is not None:  # C2 sobre o intervalo aberto
                if sit.situacao in ("revogada", "cancelada"):
                    if situacao._iso(sit.data_efeito) is not None:
                        fim = sit.data_efeito[:10]
                        fl.append(situacao.REVOGADO_NA_FONTE)
                    else:
                        fim_desc = True
                        fl += ["fim_desconhecido", situacao.DATA_DESCONHECIDA]
                elif sit.situacao == "ilegivel":
                    fl.append(situacao.INDISPONIVEL)
            linha.append(
                {
                    "redaction_id": d.redaction_id,
                    "inicio": d.start,
                    "fim": fim,
                    "fim_desconhecido": fim_desc,
                    "regra": d.rule,
                    "flags": fl,
                    "riscada": d.redaction.struck,
                    "trecho": _truncate(d.redaction.text, 160)[0],
                }
            )
        eventos = []
        for red in prov.redactions:
            for ann in red.annotations:
                eventos.append(
                    {
                        "kind": ann.kind,
                        "raw": ann.raw,
                        "act_ref": ann.act_ref,
                        "act_date": ann.act_date,
                    }
                )
        return {
            "status": "encontrada",
            "citacao": citacao,
            "caminho": cite.path,
            "work_id": resolved.work_id,
            "linha_do_tempo": linha,
            "eventos": eventos,
            "regras": rules,
            "flags": gflags,
            "needs_judgment": needs_judgment,
            "redacao_anterior_ausente_na_fonte": self._anterior_ausente(prov),
            "situacao_obra": situacao.resumo(sit),  # C2
        }

    @staticmethod
    def _anterior_ausente(prov: Provision) -> bool:
        """A primeira redação conhecida já é 'Redação dada': a anterior não consta da fonte."""
        if not prov.redactions:
            return False
        first = min(prov.redactions, key=lambda r: r.order)
        return any(a.kind == "redacao_dada" for a in first.annotations)

    # ------------------------------------------------------------------
    # Verificação
    # ------------------------------------------------------------------

    def verificar_citacao(
        self,
        citacao: str,
        trecho: str | None = None,
        data: str | None = None,
        modo: str = "literal",
        proposicao: str | None = None,
        *,
        _path: str | None = None,
        _cite: Citation | None = None,
    ) -> dict[str, Any]:
        cite = parse_one(citacao)
        if _path is not None:
            cite = next((c for c in extract(citacao) if c.path == _path), None)
        if cite and cite.work is not None:
            try:
                resolved = self._resolve(cite.work, requested_date(cite.raw), strict=True)
                if isinstance(resolved, ResolvedWork):
                    validate_identity(cite.work, resolved.document, requested_date(cite.raw))
                    if resolved.capture_id:
                        self._authenticate_capture(resolved.capture_id)
            except (SourceUnavailable, IdentityMismatch) as exc:
                mismatch = isinstance(exc, IdentityMismatch)
                return self._finalizar({
                    "identity": {
                        "status": "not_found" if mismatch else "unavailable",
                        "reason_code": "IDENTIDADE_DIVERGENTE" if mismatch else exc.reason,
                        "evidence": [],
                    },
                    "text": {
                        "status": "not_assessed",
                        "reason_code": "FONTE_INDISPONIVEL",
                        "evidence": [],
                    },
                    "temporal": {
                        "status": "not_assessed",
                        "reason_code": "FONTE_INDISPONIVEL",
                        "evidence": [],
                    },
                    "support": {
                        "status": "not_assessed",
                        "reason_code": "SUPPORT_NOT_ASSESSED",
                        "evidence": [],
                    },
                    "proposicao": proposicao,
                    "run_id": None,
                    "citation": _citation_to_dict(cite),
                }, _cite or cite, citacao, trecho, data, modo, gravar=False, em_texto=_cite is not None)
            if isinstance(resolved, ResolvedWork) and not resolved.capture_id:
                return self._finalizar({
                    "identity": {
                        "status": "unknown",
                        "reason_code": "SEM_EVIDENCIA_CAPTURADA",
                        "evidence": [],
                    },
                    "text": {
                        "status": "not_assessed" if trecho is None else "unknown",
                        "reason_code": "SEM_EVIDENCIA_CAPTURADA",
                        "evidence": [],
                    },
                    "temporal": {
                        "status": "unknown",
                        "reason_code": "SEM_EVIDENCIA_CAPTURADA",
                        "evidence": [],
                    },
                    "support": {
                        "status": "not_assessed",
                        "reason_code": "SUPPORT_NOT_ASSESSED",
                        "evidence": [],
                    },
                    "proposicao": proposicao,
                    "run_id": None,
                    "citation": _citation_to_dict(cite),
                }, _cite or cite, citacao, trecho, data, modo, gravar=False, em_texto=_cite is not None)

        result = verificar(
            citacao,
            trecho=trecho,
            data=data,
            modo=modo,
            repo=None,
            resolver=self._resolver_adapter(),
            _path=_path,
            persistir=False,  # C4: só _finalizar grava o recibo
        )
        out = _result_to_json(result)
        out["proposicao"] = proposicao
        out["run_id"] = None
        return self._finalizar(out, _cite or cite, citacao, trecho, data, modo, em_texto=_cite is not None)

    # Séries de numeração única: o número sozinho identifica o ato (decisão 0016, adendo).
    _SERIES_UNICAS = frozenset({("cmn", "resolucao"), ("bcb", "resolucao_bcb"), ("cvm", "resolucao"), ("cvm", "instrucao")})

    def _promover_sem_ano(self, cite: Citation) -> bool:
        """Norma de série única sem ano vira exata se o acervo tem exatamente uma obra com o número."""
        w = cite.work
        if "so_sem_ano" not in cite.flags or w is None or w.year or (w.authority, w.kind) not in self._SERIES_UNICAS:
            return False
        rows = self.conn.execute(
            "SELECT year FROM work WHERE authority=? AND kind=? AND number=?", (w.authority, w.kind, w.number)).fetchall()
        if len(rows) != 1 or not rows[0][0]:
            return False
        # Decisão 0031: a obra única precisa vir da fonte oficial da série, com identidade validada
        # (authority sem prefixo `invalidated:`, garantido pela consulta acima) e documento não quarentenado.
        fonte = "cvm_normas" if w.authority == "cvm" else "bcb"
        if not self.conn.execute(
                "SELECT 1 FROM work wk JOIN parsed_document pd ON pd.work_id=wk.id JOIN capture c ON c.id=pd.capture_id "
                "WHERE wk.authority=? AND wk.kind=? AND wk.number=? AND c.source_id=? AND pd.quarantined=0 LIMIT 1",
                (w.authority, w.kind, w.number, fonte)).fetchone():
            return False
        cite.work = WorkKey(w.authority, w.kind, w.number, int(rows[0][0]))
        cite.confidence = "exata"
        cite.flags = [f for f in cite.flags if f not in ("sem_ano", "so_sem_ano")] + ["numero_unico_no_acervo"]
        return True

    @staticmethod
    def _requer_conferencia(cite: Citation | None) -> bool:
        """Decisão 0016: extração provável ou referente alternativo nunca produz conclusão definitiva."""
        return cite is not None and (cite.confidence == "provavel" or "preferir_outro_referente" in cite.flags)

    @staticmethod
    def _bloco_conferencia(cite: Citation, evidencia=None, confronto=None) -> dict[str, Any]:
        return {
            "interpretacao_proposta": _citation_to_dict(cite),
            "interpretacao_preferida": (
                "dispositivo de outro referente" if "preferir_outro_referente" in cite.flags
                else "norma+dispositivo" if cite.path else "norma sem dispositivo"
            ),
            "alternativas": ["norma sem dispositivo", "dispositivo de outro referente"],
            "evidencia_disponivel": evidencia,
            "confronto_proposto": confronto,
        }

    def _so_conferencia(self, cite: Citation | None, citacao: str) -> dict[str, Any] | None:
        """Consumidores diretos (resolver/obter/histórico): associação provável não decide identidade nem vigência."""
        if cite is None or cite.work is None:
            return None
        self._promover_sem_ano(cite)
        if not self._requer_conferencia(cite):
            return None
        return {"status": "requer_conferencia", "citacao": citacao,
                "identity": {"status": "unknown", "reason_code": "ASSOCIACAO_REQUER_CONFERENCIA"},
                "conferencia": self._bloco_conferencia(cite)}

    def _finalizar(self, out: dict[str, Any], cite: Citation | None, citacao: str,
                   trecho: str | None, data: str | None, modo: str, *, gravar: bool = True, em_texto: bool = False) -> dict[str, Any]:
        """C4 (decisão 0027): todos os rebaixamentos, nesta ordem, e só então o recibo."""
        if cite is not None and self._promover_sem_ano(cite):
            out["citation"] = _citation_to_dict(cite)
        # C1: negativa de dispositivo só com pode_negar.
        ident = out["identity"]
        if (ident.get("status") == "not_found" and ident.get("reason_code") == "DISPOSITIVO_INEXISTENTE"
                and cite is not None and cite.work is not None and cite.path):
            try:
                rw = self._resolve(cite.work, strict=True)
            except SourceUnavailable:
                rw = None
            motivo = pode_negar(rw if isinstance(rw, ResolvedWork) else None, cite.path)
            if motivo:
                ident.update(status="unavailable" if motivo == "COBERTURA" else "unknown", reason_code=motivo)
                if out["text"].get("status") == "not_found":
                    out["text"].update(status="unknown", reason_code=motivo)
        # C2: aplicar_situacao (única aplicação para verificar_citacao e verificar_texto)
        # só com a identidade da obra confirmada: divergente/indisponível não é mascarado pela situação
        if (cite is not None and cite.work is not None
                and out["identity"].get("status") not in ("not_found", "unavailable")):
            try:
                rw = self._resolve(cite.work, strict=True)
            except (SourceUnavailable, IdentityMismatch):
                rw = None
            if isinstance(rw, ResolvedWork):
                out["temporal"] = situacao.aplicar_situacao_dict(
                    out["temporal"], situacao.carregar(self.conn, rw, self.home), data)
        # Confiança de extração (decisão 0016): provável ou referente alternativo nunca é definitivo.
        if (self._requer_conferencia(cite)
                # citação avulsa de formato inválido mantém o veredito; em texto, provável sempre pede conferência
                and (em_texto or out["identity"].get("reason_code") not in {"formato_invalido", "CITACAO_NAO_RECONHECIDA"})):
            confronto = json.loads(json.dumps({k: out.get(k) for k in ("identity", "text", "temporal")}))
            evidencia = (confronto["identity"].get("evidence") or [None])[0]
            out["conferencia"] = self._bloco_conferencia(cite, evidencia, confronto)
            out["identity"] = {"status": "unknown", "reason_code": "ASSOCIACAO_REQUER_CONFERENCIA"}
            out["text"] = {"status": "not_assessed", "reason_code": "ASSOCIACAO_REQUER_CONFERENCIA"}
            out["temporal"] = {"status": "unknown", "reason_code": "ASSOCIACAO_REQUER_CONFERENCIA"}
        # Nunca verified sem capture_id correspondente.
        for dim_name in ("identity", "text", "temporal"):
            dim = out.get(dim_name) or {}
            if dim.get("status") != "verified":
                continue
            evid = dim.get("evidence") or []
            if not any(e.get("capture_id") for e in evid if isinstance(e, dict)):
                dim["status"] = "unknown"
                dim["reason_code"] = "SEM_EVIDENCIA_CAPTURADA"
                out[dim_name] = dim
        # Autenticação da evidência.
        for dim_name in ("identity", "text", "temporal"):
            dim = out.get(dim_name) or {}
            if dim.get("status") == "verified":
                try:
                    for ev in dim.get("evidence", []):
                        if ev.get("capture_id"):
                            self._authenticate_capture(ev["capture_id"])
                            cap = repo.get_capture(self.conn, ev["capture_id"])
                            if ev.get("sha256") != cap["sha256"]:
                                raise SourceUnavailable("EVIDENCIA_CORROMPIDA")
                except SourceUnavailable as exc:
                    dim.update(status="unavailable", reason_code=exc.reason)
        # support permanece not_assessed
        out["support"] = {
            "status": "not_assessed",
            "reason_code": out.get("support", {}).get("reason_code") or "SUPPORT_NOT_ASSESSED",
            "evidence": out.get("support", {}).get("evidence") or [],
        }
        if gravar and not self._read_only:
            recibo = {k: v for k, v in out.items() if k not in ("run_id", "proposicao")}
            out["run_id"] = persistir_resultado(self.conn, citacao, trecho, data, modo, recibo)
        return out

    def _authenticate_capture(self, capture_id):
        cap = repo.get_capture(self.conn, capture_id)
        if not cap or not cap["sha256"]:
            raise SourceUnavailable("EVIDENCIA_AUSENTE")
        try:
            blobs.authenticate_blob(cap["sha256"], home=self.home)
        except FileNotFoundError:
            raise SourceUnavailable("EVIDENCIA_AUSENTE")
        except (blobs.BlobCorruption, ValueError, OSError):
            raise SourceUnavailable("EVIDENCIA_CORROMPIDA")

    def _rebaixar_busca(self, item: dict[str, Any]) -> dict[str, Any]:
        """Item indexado com evidência inválida vira candidato de metadados; a busca não cai por ele."""
        if item.get("nao_indexado"):
            return item
        try:
            self._authenticate_output(item)
            return item
        except SourceUnavailable as exc:
            for k in ("vigencia", "work_id", "identity", "text", "temporal"):
                item.pop(k, None)
            item.update(capture_id=None, nao_indexado=True, motivo=exc.reason)
            return item

    def _authenticate_output(self, value):
        if isinstance(value, list):
            for item in value:
                self._authenticate_output(item)
        elif isinstance(value, dict):
            if value.get("nao_indexado"):  # candidato de metadados: não afirma identidade/texto/vigência
                return
            capture = value.get("capture_id")
            if capture:
                self._authenticate_capture(capture)
            work_id = value.get("work_id")
            if ("capture_id" in value and not capture and not work_id
                    and (value.get("trecho") or value.get("ementa") or value.get("texto")
                         or value.get("obra") or value.get("titulo"))):
                raise SourceUnavailable("EVIDENCIA_AUSENTE")
            if work_id:
                caps = repo.captures_for_work(self.conn, work_id)
                if not caps:
                    raise SourceUnavailable("EVIDENCIA_AUSENTE")
                self._authenticate_capture(caps[0]["id"])
            for child in value.values():
                if isinstance(child, (list, dict)):
                    self._authenticate_output(child)

    def _resolver_adapter(self):
        outer = self

        class _Adapter:
            def resolve(self, work: WorkKey):
                resolved = outer._resolve(work, strict=True)
                for item in resolved if isinstance(resolved, list) else [resolved]:
                    if isinstance(item, ResolvedWork) and item.capture_id:
                        outer._authenticate_capture(item.capture_id)
                return resolved

        return _Adapter()

    def verificar_texto(self, texto: str, data: str | None = None) -> dict[str, Any]:
        """Extrai todas as citações e verifica identidade (+ trecho entre aspas)."""
        if len(texto) > 100_000:
            return {
                "status": "erro",
                "motivo": "texto_excede_limite",
                "limite": 100_000,
                "texto_tamanho": len(texto),
                "citacoes": [],
                "total": 0,
                "data": data,
            }
        cites = extract(texto)
        total_detectado = len(cites)
        truncado = total_detectado > 200  # A8: nunca cortar calado
        if truncado:
            cites = cites[:200]
        resultados: list[dict[str, Any]] = []
        for cite in cites:
            status = "formato_invalido"
            evidencia: dict[str, Any] | None = None
            verif: dict[str, Any] | None = None
            next_start = min([c.span[0] for c in cites if c.span[0] >= cite.span[1]] or [len(texto)])
            trecho = self._trecho_apos_aspas(texto[:next_start], cite.span[1])
            if cite.kind == "processo":
                status, evidencia = self._confirm_cnj(cite, judgment_date=self._decision_context_date(texto[cite.span[1]:cite.span[1]+240]))
            elif cite.work is None and cite.decision is None:
                status = "formato_invalido"
            elif cite.work is None and cite.decision is not None:
                # Reconhecimento só sintático — nunca "encontrada".
                status, evidencia = self._confirm_decision(cite.decision, judgment_date=self._decision_context_date(texto[cite.span[1]:cite.span[1]+240]))
            else:
                verif = self.verificar_citacao(cite.raw, trecho=trecho, data=data, modo="literal", _path=cite.path, _cite=cite)
                identity = verif.get("identity", {})
                status = {"verified":"encontrada", "ambiguous":"ambigua", "unavailable":"indisponivel", "unknown":"indisponivel"}.get(identity.get("status"), "indisponivel")
                if identity.get("reason_code") in {"formato_invalido", "CITACAO_NAO_RECONHECIDA"}:
                    status = "formato_invalido"
                elif identity.get("status") == "not_found":
                    # Ausência no acervo ou identidade divergente não são negativa oficial.
                    evidence = identity.get("evidence") or []
                    negative = identity.get("reason_code") in {"DISPOSITIVO_INEXISTENTE", "NEGATIVA_OFICIAL"}
                    if any((verif.get(dim) or {}).get("reason_code") == "DOCUMENTO_QUARENTENADO" for dim in ("text", "temporal")):
                        negative = False
                    if negative and any(e.get("capture_id") and e.get("sha256") and e.get("url") for e in evidence):
                        try:
                            for ev in evidence:
                                if ev.get("capture_id"):
                                    self._authenticate_capture(ev["capture_id"])
                                    cap = repo.get_capture(self.conn, ev["capture_id"])
                                    if ev.get("sha256") != cap["sha256"]:
                                        raise SourceUnavailable("EVIDENCIA_CORROMPIDA")
                            status = "inexistente"
                        except SourceUnavailable:
                            status = "indisponivel"
                evidence = identity.get("evidence") or []
                evidencia = evidence[0] if evidence else None
            if cite.confidence == "provavel":
                status = "requer_conferencia"  # verif já foi rebaixada em _finalizar
                evidencia = (verif or {}).get("conferencia", {}).get("evidencia_disponivel")
            resultados.append(
                {
                    "citacao": cite.raw,
                    "span": list(cite.span),
                    "kind": cite.kind,
                    "confidence": cite.confidence,
                    "conferencia": verif.get("conferencia") if verif else None,
                    "caminho": cite.path,
                    "status": status,
                    "identity": verif.get("identity") if verif else {"status": status},
                    "text": verif.get("text") if verif else {"status": "not_assessed", "reason_code": "TRECHO_NAO_ASSOCIADO" if trecho is None else "SEM_CONFRONTO"},
                    "aspas_nao_associadas": trecho is None and any(ch in texto[cite.span[1]:next_start] for ch in ('"', "'", '“', '«', '‘')),
                    "trecho_conferido": trecho,
                    "verificacao": verif,
                    "evidencia": evidencia,
                    "parseada": _citation_to_dict(cite),
                }
            )
        return {
            "texto_tamanho": len(texto),
            "citacoes": resultados,
            "total": len(resultados),
            "total_detectado": total_detectado,
            "total_processado": len(cites),
            "truncado": truncado,
            "referencias_nao_resolvidas": _remissoes_anaforicas(texto),
            "data": data,
        }

    def _decision_evidence(self, key, judgment_date=None) -> tuple[str, dict | None]:
        rows = self.conn.execute(
            "SELECT * FROM decision WHERE court=? AND identity_status='confirmed' "
            "AND (official_id=? OR ((class=? COLLATE NOCASE OR (court='TCU' AND class IS NULL)) AND UPPER(REPLACE(REPLACE(number,'.',''),' ',''))=?))",
            (key.court.upper(), key.number, key.class_, key.number.replace(".","").replace(" ","").upper()),
        ).fetchall()
        if key.year:
            rows = [r for r in rows if (r["judgment_date"] or "")[:4] == str(key.year)]
        if key.organ:
            rows = [r for r in rows if self._organ_key(r["organ"]) == self._organ_key(key.organ)]
        if key.uf:
            rows = [r for r in rows if (r["uf"] or "").upper() == key.uf.upper()]
        if judgment_date:
            rows = [r for r in rows if r["judgment_date"] == judgment_date]
        multiple = len(rows) > 1
        if not rows:
            return "nao_confirmado_no_acervo", self._decision_coverage(key.court)
        doc = self.conn.execute(
            "SELECT dd.*, c.url, c.fetched_at, c.sha256 AS capture_sha FROM decision_document dd "
            "JOIN capture c ON c.id=dd.capture_id WHERE dd.decision_id=? "
            "ORDER BY dd.created_at DESC LIMIT 1", (rows[0]["id"],),
        ).fetchone()
        if not doc or not doc["sha256"] or not doc["text"]:
            return "indisponivel", None
        try:
            blobs.get_blob(doc["capture_sha"], home=self.home)
            if hashlib.sha256(doc["text"].encode("utf-8")).hexdigest() != doc["sha256"]:
                return "indisponivel", None
        except (OSError, ValueError, blobs.BlobError):
            return "indisponivel", None
        return ("processo_confirmado" if multiple else "encontrada"), {"capture_id": doc["capture_id"], "sha256": doc["capture_sha"],
                              "url": doc["url"], "fetched_at": doc["fetched_at"]}

    @staticmethod
    def _decision_context_date(text):
        m = re.search(r'(?:\bj\.|julgad[oa]\s+em|sess[aã]o\s+de|reuni[aã]o\s+de)\s*(\d{1,2})[/.](\d{1,2})[/.](\d{4})',text,re.I)
        if not m:
            return None
        try:
            return datetime(int(m[3]),int(m[2]),int(m[1])).date().isoformat()
        except ValueError:
            return None

    @staticmethod
    def _organ_key(value):
        import unicodedata
        value = ''.join(c for c in unicodedata.normalize('NFKD', value or '') if not unicodedata.combining(c))
        value = re.sub(r'[^a-z0-9]', '', value.lower()).replace('primeira', '1').replace('segunda', '2')
        return re.sub(r'^([12])a(?=camara)',r'\1',value)

    def _decision_coverage(self, court):
        rows = self.conn.execute("SELECT MIN(judgment_date), MAX(judgment_date), GROUP_CONCAT(DISTINCT organ), COUNT(*) FROM decision WHERE court=?", (court.upper(),)).fetchone()
        return {'cobertura': {'desde':rows[0], 'ate':rows[1], 'orgaos':rows[2], 'registros':rows[3], 'escopo':'acervo local; ausência não demonstra inexistência'}}

    def _confirm_decision(self, key, judgment_date=None):
        status, evidence = self._decision_evidence(key,judgment_date)
        if status != 'nao_confirmado_no_acervo' or self._offline():
            return status, evidence
        connector_id = 'cvm_colegiado' if key.court == 'cvm' else key.court
        connector = self._get(connector_id)
        try:
            selected_response = None
            if key.court == 'stf' and key.class_.lower().startswith('tema'):
                cand = connector.resolve({'tema':key.number})
            elif key.court == 'tcu':
                cand = connector.resolve(f'{key.number}/{key.year}')
            elif key.court == 'cvm':
                found = connector.search(key.number, limite=10)
                matches = []
                for candidate in found:
                    response = connector.fetch(candidate)
                    decision = connector.parse(response)
                    actual = str(decision.metadata.get('processo') or '')
                    if re.sub(r'[^a-z0-9]','',actual.lower()) != re.sub(r'[^a-z0-9]','',key.number.lower()):
                        continue
                    if judgment_date and decision.judgment_date != judgment_date:
                        continue
                    matches.append((candidate,response))
                cand = matches[0][0] if matches else None
                selected_response = matches[0][1] if matches else None
            else:
                cand = connector.resolve({'classe':key.class_, 'numero':key.number, 'uf':key.uf})
            if cand is None:
                negative = getattr(connector,'last_not_found_response',None)
                if key.court == 'stf' and negative is not None:
                    self.conn.execute("INSERT OR IGNORE INTO source(id,authority,profile,hosts_json) VALUES (?,?,?,?)",(connector.id,connector.authority,connector.id,json.dumps(sorted(connector.hosts))))
                    self.conn.commit()
                    cap = self._save_juris_capture(connector,negative)
                    return 'inexistente', {'capture_id':cap,'sha256':negative.sha256,'url':negative.final_url,'fetched_at':negative.fetched_at,'motivo':'NEGATIVA_OFICIAL'}
                return status, evidence
            if key.court == 'stf':
                resp = connector.fetch(cand)
                parsed = connector.parse(resp)
                items = parsed.metadata.get('items', [])
                self.conn.execute("INSERT OR IGNORE INTO source(id,authority,profile,hosts_json) VALUES (?,?,?,?)", (connector.id,connector.authority,connector.id,json.dumps(sorted(connector.hosts))))
                self.conn.commit()
                cap = repo.save_capture(self.conn, resp, connector.id, home=self.home)
                ev = {'capture_id':cap, 'sha256':resp.sha256, 'url':resp.final_url, 'fetched_at':resp.fetched_at, 'classe':key.class_, 'numero':key.number, 'decisoes':items}
                identified = [i for i in items if i.get('data_iso') and i.get('julgador') and i.get('docs') and (not judgment_date or i.get('data_iso') == judgment_date)]
                return ('encontrada' if identified else 'processo_confirmado'), ev
            # Independent source declarations must match the requested identity.
            resp = selected_response or connector.fetch(cand)
            parsed = connector.parse_candidate(resp,cand) if hasattr(connector,'parse_candidate') else connector.parse(resp)
            actual_num = str(parsed.metadata.get('processo') or parsed.metadata.get('numeroProcesso') or parsed.metadata.get('numeroAcordao') or '')
            if re.sub(r'[^a-z0-9]', '', actual_num.lower()) != re.sub(r'[^a-z0-9]', '', key.number.lower()):
                return status, evidence
            if key.court == 'stj' and (parsed.class_name or '').lower() != key.class_.lower():
                return status, evidence
            if judgment_date and parsed.judgment_date != judgment_date:
                return status, evidence
            if key.year and (parsed.judgment_date or '')[:4] != str(key.year):
                return status, evidence
            if key.organ and self._organ_key(parsed.organ) != self._organ_key(key.organ):
                return status, evidence
            indexed = self._index_candidate_juris(connector, cand, captured_response=resp)
            if not indexed or not indexed.get("capture_id"):
                return "indisponivel", evidence
            if key.court == "cvm":
                for candidate,response in matches[1:]:
                    self._index_candidate_juris(connector,candidate,captured_response=response)
            return self._decision_evidence(key,judgment_date)
        except Unavailable as exc:
            if key.court == 'stj' and exc.reason == 'stj_indice_local_ausente':
                return 'nao_confirmado_no_acervo', {**(evidence or {}), 'motivo':exc.reason}
            return 'indisponivel', {**(evidence or {}), 'motivo':exc.reason}
        except Exception as exc:
            return 'indisponivel', {**(evidence or {}), 'motivo':type(exc).__name__}

    def _confirm_cnj(self, cite, judgment_date=None):
        if 'cnj_dv_invalido' in cite.flags:
            return 'formato_invalido', None
        if self._offline():
            return 'nao_confirmado_no_acervo', {'escopo':'processo; não julgamento'}
        digits = re.sub(r'\D', '', cite.raw)
        from freoa_verifica.connectors.datajud import court_from_cnj
        tribunal = court_from_cnj(digits)
        if tribunal is None:
            return 'nao_confirmado_no_acervo', {'escopo':'tribunal sem rota configurada'}
        try:
            # cjsg pode identificar julgamento; DataJud confirma somente o processo.
            connector = self._get('tjsp')
            try:
                found = connector.search(cite.raw, numero_processo=cite.raw, limite=5) if tribunal == 'tjsp' else []
            except Unavailable:
                found = []
            for cand in found:
                response = connector.fetch(cand)
                parsed = connector.parse(response)
                if re.sub(r'\D','',parsed.cnj_number or '') != digits:
                    continue
                if judgment_date and parsed.judgment_date != judgment_date:
                    continue
                result = self._index_candidate_juris(connector,cand)
                if result and result.get('capture_id'):
                    return 'encontrada', result
            connector = self._get('datajud')
            cand = connector.resolve({'tribunal':tribunal,'numero':cite.raw})
            if not cand:
                return 'nao_confirmado_no_acervo', {'escopo':'processo; não julgamento'}
            resp = connector.fetch(cand)
            parsed = connector.parse(resp)
            if re.sub(r'\D','', parsed.cnj_number or '') != digits:
                return 'indisponivel', {'motivo':'identidade_divergente'}
            self.conn.execute("INSERT OR IGNORE INTO source(id,authority,profile,hosts_json) VALUES (?,?,?,?)", (connector.id,connector.authority,connector.id,json.dumps(sorted(connector.hosts))))
            self.conn.commit()
            cap = repo.save_capture(self.conn,resp,connector.id,home=self.home)
            return 'processo_confirmado', {'capture_id':cap,'sha256':resp.sha256,'url':resp.final_url,'fetched_at':resp.fetched_at,'escopo':'processo; não julgamento'}
        except Unavailable as exc:
            return 'indisponivel', {'motivo':exc.reason,'escopo':'processo; não julgamento'}

        except Exception as exc:
            return 'indisponivel', {'motivo':type(exc).__name__,'escopo':'processo; não julgamento'}

    @staticmethod
    def _trecho_apos_aspas(texto: str, start: int) -> str | None:
        rest = texto[start : start + 800]
        m = re.match(r"\s*(?:(?:[:,;—–-]|que\s+dispõe|segundo\s+o\s+qual|in\s+verbis)\s*)*[\"“«'‘]\s*(.+?)[\"”»'’]", rest, re.DOTALL | re.I)
        if not m:
            return None
        return m.group(1).strip()

    # ------------------------------------------------------------------
    # Jurisprudência
    # ------------------------------------------------------------------

    @_authenticated_output
    def pesquisar_jurisprudencia(
        self,
        q: str,
        tribunais: list[str] | None = None,
        desde: str | None = None,
        ate: str | None = None,
        autoridade_min: str | None = None,
        limite: int = 10,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        key = self._chave_processo(q)
        if key is not None:
            return self._juris_por_numero(q, key)
        return self._juris_textual(q, tribunais, desde, ate, autoridade_min, limite, cursor)

    @staticmethod
    def _chave_processo(q: str):
        """Consulta que é só classe e número ("REsp 2.210.785", "Recurso Especial nº ...") vira chave."""
        t = q.strip()
        for pat, sigla in _CLASSES_POR_EXTENSO:
            t = re.sub(r"(?<!\w)" + pat + r"(?!\w)", sigla, t, flags=re.I)
        t = re.sub(r"(?<!\w)n(?:[º°]|\.º|\.)\s*", "", t, flags=re.I)
        cite = parse_one(t)
        if cite and cite.decision and cite.decision.number and len(cite.raw) >= len(t) - 3:
            return cite.decision
        return None

    def _juris_por_numero(self, q: str, key) -> dict[str, Any]:
        """A6: lookup exato por classe e número no acervo; nunca mistura outros processos."""
        status, evidence = self._decision_evidence(key)
        base = {"consulta": q, "modo_busca": "numero", "status": status,
                "itens": [], "resultados": [], "relacionados": [], "resultados_textuais": [],
                "truncado": False, "cursor": None, "fontes": {},
                "rules_version": AUTHORITY_RULES_VERSION}
        if status == "nao_confirmado_no_acervo":
            cob = dict(evidence["cobertura"])
            cob["tribunais"] = [r[0] for r in self.conn.execute(
                "SELECT DISTINCT court FROM decision ORDER BY court")]
            return {**base, "cobertura": cob,
                    "aviso": "processo não localizado no acervo local; ausência não demonstra inexistência"}
        rows = repo.decisions_by_number(self.conn, key.court, key.number)
        cls = key.class_.lower()
        exatas = [r for r in rows if (r["class"] or "").lower() == cls or r["official_id"] == key.number]
        incidentes = [r for r in rows if r not in exatas and (r["class"] or "").lower().endswith((" no " + cls, " nos " + cls))]
        itens = []
        for r in exatas:
            item = self._decisao_item(r)
            item["evidencia"], item["relacao"] = evidence, "exato"
            itens.append(item)
        rel = [{**self._decisao_item(r), "relacao": "incidente_do_mesmo_processo"} for r in incidentes]
        return {**base, "itens": itens, "resultados": itens, "relacionados": rel,
                "total_parcial": len(itens), "evidencia": evidence}

    def _juris_textual(self, q, tribunais, desde, ate, autoridade_min, limite, cursor) -> dict[str, Any]:
        offset = _decode_cursor(cursor)
        limite = max(1, min(int(limite), 50))
        tribunais_norm = (list(_JURIS_CONNECTORS) if tribunais is None else
                          list(dict.fromkeys(normalize_court(t) for t in tribunais)))
        self.conn.create_function(
            "fv_authority", 4,
            lambda court, cls, organ, kind: classify_authority(
                species=_species_from_meta(court, cls, organ, kind), court=court,
                class_name=cls, organ=organ).label,
            deterministic=True,
        )
        modo_busca = "normal"
        tesauro_info: dict[str, Any] = {}
        def local_page():
            nonlocal modo_busca, tesauro_info
            def buscar(fts, n):
                return repo.search_local_decisions(
                    self.conn, fts, courts=tribunais_norm if tribunais is not None else None,
                    desde=desde, ate=ate, autoridade_min=autoridade_min, limit=n, offset=0)
            # AND primeiro; menos de offset+limite resultados completam com OR marcado (decisão 0025).
            res = buscar_and_or(
                q, buscar, lambda r: f"{r.get('ementa') or ''} {r.get('inteiro_teor') or ''}",
                lambda r: r.get("decision_id") or r.get("official_id"),
                offset + limite + 1, offset + limite, colunas="ementa inteiro_teor")
            modo_busca = "ampliada" if res["fts"] and not res["and"] else "normal"
            tesauro_info = res["tesauro"]
            return res["linhas"][offset:]

        local = local_page()
        items: list[dict[str, Any]] = []
        def append_local(rows):
            items.extend(self._decisao_item(row) for row in rows)
        append_local(local)

        id_map = {
            "stj": "stj",
            "tcu": "tcu",
            "tjsp": "tjsp",
            "cvm": "cvm_colegiado",
            "cvm_colegiado": "cvm_colegiado",
        }
        offline = os.environ.get("FV_OFFLINE", "").strip() in {"1", "true", "yes"}
        fontes_status: dict[str, dict[str, Any]] = {}
        for t in tribunais_norm:
            cid = id_map.get(t, t)
            if cid not in registry():
                fontes_status[cid] = {"status": "unavailable", "motivo": "fonte_nao_suportada", "parcial": False}
            elif offline:
                fontes_status[cid] = {"status": "unavailable", "motivo": "offline", "parcial": False}
        if len(items) < limite and tribunais_norm and not offline:
            for t in tribunais_norm:
                cid = id_map.get(t, t)
                if cid not in registry():
                    continue
                try:
                    conn_obj = self._get(cid)
                    coverage = getattr(conn_obj, "coverage", {"busca_textual": True})
                    if not coverage.get("busca_textual_ao_vivo", coverage.get("busca_textual")):
                        fontes_status[cid] = {"status": "unavailable",
                            "motivo": "busca_textual_ao_vivo_nao_suportada", "parcial": False}
                        continue
                    filtros: dict[str, Any] = {}
                    if desde:
                        filtros["desde"] = desde
                    if ate:
                        filtros["ate"] = ate
                    cands = conn_obj.search(q, **filtros)
                    got = 0
                    for cand in cands:
                        item = self._index_candidate_juris(conn_obj, cand)
                        if item:
                            self._authenticate_output(item)
                        if item and normalize_court(item.get("tribunal") or "") in tribunais_norm and _authority_min_ok(
                            item.get("rotulo_autoridade") or "E", autoridade_min
                        ):
                            items.append(item)
                            got += 1
                        if len(items) >= limite:
                            break
                    fontes_status[cid] = {
                        "status": "ok",
                        "motivo": None,
                        "parcial": got < len(cands),
                    }
                except SourceUnavailable:
                    raise
                except Unavailable as exc:
                    fontes_status[cid] = {
                        "status": "unavailable",
                        "motivo": exc.reason,
                        "parcial": False,
                    }
                except Exception as exc:  # noqa: BLE001
                    fontes_status[cid] = {
                        "status": "unavailable",
                        "motivo": f"{type(exc).__name__}:{exc}"[:200],
                        "parcial": False,
                    }

        # Candidatos capturados ao vivo passam pelos mesmos filtros e ranking SQL.
        if not offline and any(v.get("status") == "ok" for v in fontes_status.values()):
            items.clear()
            append_local(local_page())
        page = items[:limite]
        truncado = len(items) > limite
        return {
            **_status_com_falhas("parcial" if truncado else "ok", _falhas_de_fonte(fontes_status), len(page)),
            "itens": page,
            "resultados": page,
            "fontes": fontes_status,
            "total_parcial": offset + len(items),
            "truncado": truncado,
            "cursor": _encode_cursor(offset + limite) if truncado else None,
            "consulta": q,
            "autoridade_min": autoridade_min,
            "modo_busca": modo_busca,
            "tesauro": tesauro_info,
            "rules_version": AUTHORITY_RULES_VERSION,
        }

    def _decisao_item(self, row: dict[str, Any]) -> dict[str, Any]:
        text = row.get("ementa") or row.get("inteiro_teor") or ""
        ementa, trunc = _truncate(text, _EMENTA_MAX)
        court = row.get("court") or ""
        class_name = row.get("class") or ""
        auth = classify_authority(
            species=_species_from_meta(court, class_name, row.get("organ"), row.get("kind")),
            court=court, class_name=class_name or None, organ=row.get("organ"),
        )
        if text:
            self._authenticate_capture(row.get("capture_id"))
            if row.get("inteiro_teor") and row.get("full_capture_id"):
                self._authenticate_capture(row["full_capture_id"])
        return {
            "id": row.get("decision_id"),
            "tribunal": court,
            "classe_numero": f"{class_name} {row.get('number') or ''}".strip(),
            "orgao": row.get("organ"), "relator": row.get("rapporteur"),
            "datas": {"julgamento": row.get("judgment_date"),
                      "publicacao": row.get("publication_date")},
            "ementa": ementa,
            "autoridade": authority_as_dict(auth),
            "rotulo_autoridade": auth.label, "regra_autoridade": auth.rule,
            "rules_version": AUTHORITY_RULES_VERSION,
            "url_oficial": row.get("url_oficial"),
            "capture_id": row.get("capture_id"),
            "nivel_prova": row.get("nivel_prova") or "metadados",
            "truncado": trunc,
            "pertinencia": row.get("pertinencia"),
            "correspondencia": row.get("correspondencia"),
            **_situacao_precedente(row.get("authority_attrs_json"), auth.attributes.species),
        }

    def _save_juris_capture(self, connector, response):
        key = (connector.id,response.url,response.fetched_at,response.sha256)
        previous = getattr(self,'_last_juris_capture',None)
        if previous and previous[0] is response.body and previous[1] == key:
            return previous[2]
        capture_id = repo.save_capture(self.conn,response,connector.id,home=self.home)
        # Apenas bytes imutáveis já autenticados; dados novos passam pelo hash.
        if isinstance(response.body,bytes):
            self._last_juris_capture = (response.body,key,capture_id)
        return capture_id

    def _index_candidate_juris(self, connector, cand: Candidate, captured_response=None) -> dict[str, Any] | None:
        meta = cand.metadata or {}
        court = str(meta.get("court") or connector.authority or connector.id).upper()
        class_name = meta.get("classe") or meta.get("class") or meta.get("class_name")
        organ = meta.get("orgao") or meta.get("organ")
        rapporteur = meta.get("relator") or meta.get("rapporteur")
        ementa = cand.snippet or meta.get("ementa") or ""
        auth = classify_authority(
            species=_species_from_meta(court, class_name, organ, meta.get("kind")),
            court=court,
            organ=organ,
            class_name=class_name,
        )
        capture_id = None
        nivel = "metadados"
        inteiro = ""
        attrs = authority_as_dict(auth)
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO source(id, authority, profile, hosts_json) VALUES (?,?,?,?)",
                (connector.id, court, connector.id, json.dumps(sorted(getattr(connector, "hosts", [])))),
            )
            self.conn.commit()
            resp = captured_response or connector.fetch(cand)
            parse_candidate = getattr(connector, "parse_candidate", None)
            parsed = parse_candidate(resp, cand) if parse_candidate else connector.parse(resp)
            capture_id = self._save_juris_capture(connector,resp)
            if isinstance(parsed, ParsedDecision):
                ementa = parsed.ementa or ementa
                inteiro = parsed.text or ""
                court = (parsed.court or court).upper()
                class_name = parsed.class_name or class_name
                organ = parsed.organ or organ
                rapporteur = parsed.rapporteur or rapporteur
                auth = classify_authority(
                    species=_species_from_meta(court, class_name, organ, parsed.kind),
                    court=court, class_name=class_name, organ=organ,
                )
                attrs = authority_as_dict(auth)
                for extra in ("situacao_precedente", "divergencia_na_fonte"):
                    if parsed.metadata.get(extra):
                        attrs[extra] = parsed.metadata[extra]
                did = repo.upsert_decision(
                    self.conn,
                    court=court,
                    kind=("decisao_monocratica" if parsed.kind == "monocratica" else parsed.kind) if parsed.kind in {
                        "acordao", "decisao_monocratica", "monocratica", "sumula", "tema", "voto",
                        "decisao_colegiado_cvm", "acordao_tcu", "repercussao_geral",
                    } else "acordao",
                    class_=class_name,
                    number=str(parsed.metadata.get("processo") or parsed.metadata.get("numeroProcesso") or parsed.metadata.get("numeroAcordao") or meta.get("numero") or meta.get("number") or parsed.official_id),
                    uf=meta.get("siglaUF") or meta.get("siglaUf") or meta.get("uf"),
                    identity_status="confirmed",
                    organ=organ,
                    rapporteur=rapporteur,
                    judgment_date=parsed.judgment_date,
                    publication_date=parsed.publication_date,
                    official_id=parsed.official_id,
                    authority_attrs_json=json.dumps(attrs, ensure_ascii=False),
                    authority_label=auth.label,
                )
                # upsert não atualiza linha existente: a situação do precedente muda na fonte.
                self.conn.execute("UPDATE decision SET authority_attrs_json=?, authority_label=? WHERE id=?",
                                  (json.dumps(attrs, ensure_ascii=False), auth.label, did))
                integral = parsed.profile in _PERFIS_INTEIRO_TEOR or parsed.metadata.get("documento") == "inteiro_teor"
                kind_doc = "inteiro_teor" if inteiro and integral else "ementa"
                text_doc = inteiro if kind_doc == "inteiro_teor" else (ementa or inteiro)
                digest = (
                    hashlib.sha256(text_doc.encode("utf-8")).hexdigest() if text_doc else None
                )
                nivel = repo.proof_level_for_capture(
                    capture_id=capture_id, sha256=digest, kind_doc=kind_doc
                )
                # Nova captura da mesma decisão substitui o documento do mesmo tipo (texto e captura juntos).
                self.conn.execute("DELETE FROM decision_document WHERE decision_id=? AND kind IN (?, 'ementa')",
                                  (did, kind_doc))
                self.conn.execute(
                    "INSERT INTO decision_document("
                    "id, decision_id, capture_id, kind, text, sha256, nivel_prova"
                    ") VALUES (?,?,?,?,?,?,?)",
                    (new_ulid(), did, capture_id, kind_doc, text_doc, digest, nivel),
                )
                if kind_doc == "inteiro_teor" and ementa:
                    self.conn.execute(
                        "INSERT INTO decision_document("
                        "id, decision_id, capture_id, kind, text, sha256, nivel_prova"
                        ") VALUES (?,?,?,'ementa',?,?,'ementa_capturada')",
                        (new_ulid(), did, capture_id, ementa,
                         hashlib.sha256(ementa.encode("utf-8")).hexdigest()),
                    )
                self.conn.commit()
                repo.set_decision_nivel_prova(self.conn, did, nivel)
                repo.index_decision(
                    self.conn,
                    ementa=ementa or "",
                    inteiro_teor=inteiro or "",
                    court=court,
                    class_=str(class_name or ""),
                    official_id=parsed.official_id,
                )
        except Exception:  # noqa: BLE001
            # Download/parse falhou: permanece metadados, sem capture_id.
            capture_id = None
            nivel = "metadados"
            did = repo.upsert_decision(
                self.conn,
                court=court,
                kind="acordao",
                class_=class_name,
                number=str(meta.get("number") or cand.key),
                organ=organ,
                rapporteur=rapporteur,
                authority_attrs_json=json.dumps(authority_as_dict(auth), ensure_ascii=False),
                authority_label=auth.label,
            )
            repo.set_decision_nivel_prova(self.conn, did, "metadados")
            repo.index_decision(
                self.conn,
                ementa=ementa or "",
                court=court,
                class_=str(class_name or ""),
            )

        ementa_out, trunc = _truncate(ementa, _EMENTA_MAX)
        return {
            "tribunal": court,
            "classe_numero": f"{class_name or ''} {meta.get('number') or cand.key}".strip(),
            "orgao": organ,
            "relator": rapporteur,
            "datas": {
                "julgamento": meta.get("judgment_date"),
                "publicacao": meta.get("publication_date"),
            },
            "ementa": ementa_out,
            "autoridade": authority_as_dict(auth),
            "rotulo_autoridade": auth.label,
            "regra_autoridade": auth.rule,
            "rules_version": AUTHORITY_RULES_VERSION,
            "url_oficial": cand.url,
            "capture_id": capture_id,
            "nivel_prova": nivel,
            "truncado": trunc,
            **_situacao_precedente(json.dumps(attrs, ensure_ascii=False), auth.attributes.species),
        }

    @_authenticated_output
    def obter_decisao(
        self,
        id: str,
        parte: str = "ementa",
        max_chars: int = 8000,
        offset: int = 0,
        tribunal: str | None = None,
    ) -> dict[str, Any]:
        if parte not in {"ementa", "inteiro_teor", "voto", "certidao"}:
            raise EntradaInvalida(f"parte inválida: {parte!r} (ementa|inteiro_teor|voto|certidao)")
        max_chars = max(1, min(int(max_chars), 50_000))
        offset = max(0, int(offset))
        court = normalize_court(tribunal).upper() if tribunal else None
        rows = self.conn.execute("SELECT * FROM decision WHERE id=?", (id,)).fetchall()
        if court:
            rows = [r for r in rows if r["court"] == court]
        if not rows:
            # Identidade = tribunal + identificador oficial (decisão 0038): sem tribunal, colisão é ambiguidade.
            sql, args = "SELECT * FROM decision WHERE official_id=?", [id]
            if court:
                sql, args = sql + " AND court=?", [id, court]
            rows = self.conn.execute(sql + " ORDER BY court, id", args).fetchall()
        if not rows:
            # Ausência no banco local não é inexistência do julgado (decisão 0038).
            return {"status": "nao_encontrado_no_acervo", "escopo": "acervo_local", "id": id,
                    **({"tribunal": court} if court else {})}
        if len(rows) > 1:
            return {"status": "ambiguous", "motivo": "IDENTIFICADOR_EM_MAIS_DE_UM_REGISTRO", "id": id,
                    "candidatos": [{"id": r["id"], "tribunal": r["court"], "classe": r["class"],
                                    "numero": r["number"]} for r in rows]}
        row = rows[0]
        disponiveis = [r[0] for r in self.conn.execute(
            "SELECT DISTINCT kind FROM decision_document WHERE decision_id=? AND COALESCE(text,'')!='' ORDER BY kind",
            (row["id"],))]
        doc = self.conn.execute(
            "SELECT * FROM decision_document WHERE decision_id=? AND kind=? "
            "ORDER BY created_at DESC LIMIT 1",
            (row["id"], parte),
        ).fetchone()
        base = {
            "id": row["id"],
            "tribunal": row["court"],
            "classe": row["class"],
            "numero": row["number"],
            "orgao": row["organ"],
            "relator": row["rapporteur"],
            "parte": parte,
            "parte_solicitada": parte,
            "partes_disponiveis": disponiveis,
            "autoridade_label": row["authority_label"],
            **_situacao_precedente(row["authority_attrs_json"], _especie_gravada(row["authority_attrs_json"])),
        }
        if doc is None or not (doc["text"] or ""):
            # Parte ausente nunca é substituída por outro documento sob o rótulo pedido (decisão 0038, A1).
            return {**base, "status": "parte_indisponivel", "motivo": "PARTE_NAO_CAPTURADA",
                    "parte_entregue": None, "texto": None, "capture_id": None}
        text = doc["text"]
        self._authenticate_capture(doc["capture_id"])
        slice_ = text[offset : offset + max_chars]
        truncado = offset + max_chars < len(text)
        return {
            **base,
            "status": "encontrada",
            "parte_entregue": doc["kind"],
            "texto": slice_,
            "truncado": truncado,
            "offset": offset,
            "max_chars": max_chars,
            "cursor": str(offset + max_chars) if truncado else None,
            "capture_id": doc["capture_id"],
        }

    # ------------------------------------------------------------------
    # CVM / BCB
    # ------------------------------------------------------------------

    @_authenticated_output
    def buscar_normas_cvm(self, q: str, tipo: str | None = None) -> dict[str, Any]:
        return self._rebaixar_resultado(self._buscar_normas("cvm_normas", q, tipo))

    @_authenticated_output
    def buscar_normas_bcb(self, q: str, tipo: str | None = None) -> dict[str, Any]:
        return self._rebaixar_resultado(self._buscar_normas("bcb", q, tipo))

    def _rebaixar_resultado(self, res: dict[str, Any]) -> dict[str, Any]:
        itens = [self._rebaixar_busca(i) for i in res.get("itens") or []]
        ni = sum(1 for i in itens if i.get("nao_indexado"))
        if itens and ni > res.get("nao_indexados", 0):
            res.update(itens=itens, nao_indexados=ni, indexados=len(itens) - ni,
                       status="parcial" if res.get("status") == "ok" else res.get("status"))
        return res

    def _buscar_normas(self, source: str, q: str, tipo: str | None, *,
                       max_indexar: int = 5, orcamento_s: float = 20.0) -> dict[str, Any]:
        if self._offline():
            return {"status": "indisponivel", "motivo": "offline", "itens": [], "total": 0, "truncado": False, "offline": True}
        prazo = time.monotonic() + orcamento_s
        try:
            filtros = {"tipo": tipo} if tipo else {}
            connector = self._get(source)
            cands = _com_prazo(prazo, connector.search, q, **filtros)
        except Unavailable as exc:
            return {"status": "indisponivel", "motivo": exc.reason, "reason_code": exc.reason, "itens": []}
        except Exception as exc:  # noqa: BLE001
            motivo = f"{type(exc).__name__}:{exc}"[:200]
            return {"status": "indisponivel", "motivo": motivo, "reason_code": motivo, "itens": []}
        itens = []
        falhas = []
        nao_indexados = 0
        for n, c in enumerate(cands):
            if n >= max_indexar or time.monotonic() >= prazo:  # decisão 0024: parcial declarada
                nao_indexados += 1
                itens.append({"titulo": c.title, "chave": c.key, "url": c.url, "trecho": c.snippet or "",
                              "capture_id": None, "metadados": c.metadata, "nao_indexado": True})
                continue
            try:
                item = _com_prazo(prazo, self._index_candidate_legis, connector, c)
            except Unavailable:  # abandonada: nada parcial é confirmado (CANCELADO)
                item = {"capture_id": None, "motivo": "orcamento"}
            if not item.get("capture_id") and time.monotonic() >= prazo:  # orçamento estourou no item
                nao_indexados += 1
                itens.append({"titulo": c.title, "chave": c.key, "url": c.url, "trecho": c.snippet or "",
                              "capture_id": None, "metadados": c.metadata, "nao_indexado": True,
                              "motivo": "orcamento"})
                continue
            if not item.get("capture_id"):
                falhas.append({"chave": c.key, "url": c.url, "status": "unavailable",
                               "motivo": item.get("motivo") or "captura_indisponivel"})
                continue
            itens.append({
                "titulo": c.title,
                "chave": c.key,
                "url": c.url,
                "trecho": item["trecho"],
                "capture_id": item["capture_id"],
                "metadados": c.metadata,
            })
        status = ("parcial" if itens else "indisponivel") if falhas else "ok"
        truncado = bool(getattr(cands, "truncado", False))  # A9
        if (nao_indexados or truncado) and status == "ok":  # decisão 0024
            status = "parcial"
        return {"status": status, "itens": itens, "total": getattr(cands, "total", len(cands)),
                "falhas": falhas, "indexados": len(itens) - nao_indexados, "nao_indexados": nao_indexados,
                "truncado": truncado}

    # ------------------------------------------------------------------
    # Evidência / fontes / sync
    # ------------------------------------------------------------------

    @_authenticated_output
    def obter_evidencia(
        self,
        capture_id: str,
        offset: int = 0,
        max_chars: int = 4000,
    ) -> dict[str, Any]:
        offset = max(0, int(offset))
        max_chars = max(1, min(int(max_chars), 50_000))
        cap = repo.get_capture(self.conn, capture_id)
        if cap is None:
            return {"status": "inexistente", "capture_id": capture_id}
        self._authenticate_capture(capture_id)
        try:
            body = blobs.get_blob(cap["sha256"], home=self.home)
        except Exception:  # noqa: BLE001
            return {
                "status": "indisponivel",
                "capture_id": capture_id,
                "motivo": "blob_ausente",
                "metadados": {
                    "url": cap.get("url"),
                    "final_url": cap.get("final_url"),
                    "fetched_at": cap.get("fetched_at"),
                    "sha256": cap.get("sha256"),
                    "mime": cap.get("mime"),
                    "status_http": cap.get("status"),
                    "source_id": cap.get("source_id"),
                    "size": cap.get("size"),
                },
            }
        text = ""
        for enc in ("utf-8", "latin-1"):
            try:
                text = body.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if not text:
            text = f"[binário {cap.get('mime') or 'application/octet-stream'}; {len(body)} bytes]"
        slice_ = text[offset : offset + max_chars]
        truncado = offset + max_chars < len(text)
        envolto = envolver(slice_)
        return {
            "status": "encontrada",
            "capture_id": capture_id,
            "metadados": {
                "url": cap.get("url"),
                "final_url": cap.get("final_url"),
                "fetched_at": cap.get("fetched_at"),
                "sha256": cap.get("sha256"),
                "mime": cap.get("mime"),
                "status_http": cap.get("status"),
                "source_id": cap.get("source_id"),
                "size": cap.get("size"),
            },
            "texto": envolto,
            "truncado": truncado,
            "offset": offset,
            "max_chars": max_chars,
            "cursor": str(offset + max_chars) if truncado else None,
        }

    def listar_fontes(self) -> dict[str, Any]:
        fontes = []
        for cid, cls in registry().items():
            coverage = dict(getattr(cls, "coverage", {}) or {})
            last = self._last_health.get(cid)
            circuit = []
            for host in getattr(cls, "hosts", frozenset()):
                br = _CIRCUIT_BREAKERS.get(host)
                if br is None:
                    circuit.append({"host": host, "estado": "fechado", "falhas": 0})
                else:
                    aberto = br.opened_at is not None
                    circuit.append(
                        {
                            "host": host,
                            "estado": "aberto" if aberto else "fechado",
                            "falhas": br.failures,
                        }
                    )
            fontes.append(
                {
                    "id": cid,
                    "autoridade": getattr(cls, "authority", cid),
                    "cobertura": coverage,
                    "ultimo_health": last,
                    "circuito": circuit,
                }
            )
        return {"fontes": fontes, "total": len(fontes)}

    def sincronizar(
        self,
        fontes: list[str] | None = None,
        desde: str | None = None,
        *,
        semente: bool = False,
        max_itens: int | None = None,
    ) -> dict[str, Any]:
        if semente:
            from freoa_verifica.semente import SementeSync

            def _progress(msg: str) -> None:
                print(f"[sync] {msg}", file=sys.stderr, flush=True)

            engine = SementeSync(
                self,
                max_itens=max_itens,
                fontes=fontes,
                progress=_progress,
            )
            return engine.run()

        alvos = fontes or ["stj", "tcu", "cvm_colegiado", "cvm_normas"]
        relatorio = []
        for cid in alvos:
            if cid not in registry():
                relatorio.append({"fonte": cid, "status": "desconhecida"})
                continue
            try:
                conn_obj = self._get(cid)
                if hasattr(conn_obj, "sync"):
                    kwargs: dict[str, Any] = {}
                    if desde and cid == "stj":
                        kwargs["desde"] = desde
                    if max_itens is not None and cid == "tcu":
                        kwargs["quantidade"] = min(100, max_itens)
                        kwargs["max_pages"] = max(1, (max_itens + 99) // 100)
                    result = conn_obj.sync(**kwargs)
                    relatorio.append({"fonte": cid, "status": "ok", "resultado": str(result)[:200]})
                else:
                    # busca índice leve
                    cands = conn_obj.search(desde or "lei",)
                    relatorio.append(
                        {"fonte": cid, "status": "ok", "candidatos": len(cands)}
                    )
            except Unavailable as exc:
                relatorio.append({"fonte": cid, "status": "indisponivel", "motivo": exc.reason})
            except Exception as exc:  # noqa: BLE001
                relatorio.append({"fonte": cid, "status": "erro", "motivo": str(exc)[:200]})
        return {"sincronizado_em": _now_iso(), "fontes": relatorio}

    def bench(self, gold: str | Path) -> dict[str, Any]:
        from freoa_verifica.bench import run_bench

        return run_bench(self, gold)

    def doctor(self, *, offline: bool = False) -> dict[str, Any]:
        from freoa_verifica import __version__

        checks: list[dict[str, Any]] = [
            {"nome": "versao", "status": "ok", "detalhe": __version__},
            {
                "nome": "home",
                "status": "ok" if self.home.is_dir() else "falha",
                "detalhe": str(self.home),
            },
            {
                "nome": "banco",
                "status": "ok",
                "detalhe": str(self.home / "verifica.sqlite3"),
            },
        ]
        try:
            n = self.conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
            checks.append({"nome": "migracoes", "status": "ok", "detalhe": f"{n} versões"})
        except Exception as exc:  # noqa: BLE001
            checks.append({"nome": "migracoes", "status": "falha", "detalhe": str(exc)})

        for cid, cls in registry().items():
            if offline:
                checks.append(
                    {
                        "nome": f"fonte:{cid}",
                        "status": "ok",
                        "detalhe": "offline — health não executado",
                        "cobertura": dict(getattr(cls, "coverage", {}) or {}),
                    }
                )
                continue
            try:
                report = self._get(cid).health()
                probes = [
                    {"nome": p.name, "status": p.status, "detalhe": p.detail}
                    for p in report.probes
                ]
                self._last_health[cid] = {
                    "probes": probes,
                    "checked_at": report.checked_at,
                    "saudavel": report.healthy,
                }
                checks.append(
                    {
                        "nome": f"fonte:{cid}",
                        "status": "ok" if report.healthy else "alerta",
                        "detalhe": probes,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                checks.append(
                    {"nome": f"fonte:{cid}", "status": "falha", "detalhe": str(exc)[:200]}
                )
        aviso = self.acervo_status()
        checks.append({"nome": "acervo", "status": "alerta" if aviso else "ok",
                       "detalhe": aviso or "atende ao manifesto/mínimo"})
        ok = all(c["status"] in {"ok", "alerta"} for c in checks)
        return {"status": "ok" if ok else "falha", "verificacoes": checks,
                **({"acervo_incompleto": aviso} if aviso else {})}

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    @property
    def _SNAPSHOT_TABLE_COLUMNS(self) -> dict[str, tuple[str, ...]]:
        from freoa_verifica.snapshot import SNAPSHOT_TABLE_COLUMNS

        return SNAPSHOT_TABLE_COLUMNS

    def snapshot_export(self, destino: str | Path) -> dict[str, Any]:
        from freoa_verifica import snapshot as snap

        self.reparar_anos()
        return snap.export_snapshot(self.conn, self.home, destino)

    def acervo_status(self) -> dict[str, Any] | None:
        """Aviso `acervo_incompleto` (C7) ou None quando o acervo atende à referência."""
        if self._acervo_cache is None:
            self._acervo_cache = (True, _acervo.status(self.conn, self.home))
        return self._acervo_cache[1]

    def reconstruir_acervo(self, com_situacao: bool = False) -> dict[str, Any]:
        """Reconstrói os derivados do home numa cópia e troca o banco só se tudo validar (C6)."""
        return _derivados.reconstruir(self, com_situacao=com_situacao)

    def purgar_execucoes(self, antes: str) -> dict[str, Any]:
        """Reconstrói o banco sem as execuções anteriores a `antes` (AAAA-MM-DD)."""
        from freoa_verifica import registro as reg

        if self._read_only:
            return {"status": "erro", "motivo": "somente_leitura"}
        try:
            with self.exclusivo():
                self._close_all_conns(strict=True)
                try:
                    return reg.purgar(self.home, antes)
                finally:
                    self._clear_caches()
        except (ValueError, TimeoutError, RuntimeError, OSError) as exc:
            return {"status": "erro", "motivo": str(exc)[:200]}

    def snapshot_install(
        self,
        origem: str | Path | None = None,
        *,
        url: str | None = None,
    ) -> dict[str, Any]:
        from freoa_verifica import snapshot as snap

        return snap.install_snapshot(self, origem, url=url)

    def snapshot_info(self, origem: str | Path | None = None) -> dict[str, Any]:
        from freoa_verifica import snapshot as snap

        return snap.snapshot_info(self, origem)


# ----------------------------------------------------------------------
# Fachada: validação compartilhada, operações ativas, concorrência, política
# de registro e aviso de acervo. Aplicada a todos os métodos públicos.
# ----------------------------------------------------------------------

_CARAS = frozenset({
    "buscar_legislacao", "resolver_citacao", "obter_dispositivo", "historico_dispositivo",
    "verificar_citacao", "verificar_texto", "pesquisar_jurisprudencia", "obter_decisao",
    "buscar_normas_cvm", "buscar_normas_bcb",
})
_CONTADAS = _CARAS | frozenset({
    "obter_evidencia", "listar_fontes", "doctor", "sincronizar", "bench", "snapshot_export",
    "snapshot_info", "indexar_obra", "reparar_anos", "reprocessar_capturas",
    "restaurar_identidades_validadas", "reparar_identidades",
})


def _guardar(fn):
    sig = inspect.signature(fn)
    caro = fn.__name__ in _CARAS

    @wraps(fn)
    def guardado(self, *args, **kwargs):
        try:
            bound = sig.bind(self, *args, **kwargs)
        except TypeError:
            return fn(self, *args, **kwargs)
        entrada = dict(bound.arguments)
        entrada.pop("self", None)
        _validar(entrada)
        externa = not getattr(self._local, "prof", 0)
        token = _politica_atual.set(self.registro)
        try:
            with self._operacao(caro):
                if fn.__name__ in _DEPENDENTES and not _derivados.compativel(self.conn):
                    return _derivados.indisponivel(self.acervo_status())
                out = fn(self, *args, **kwargs)
                if externa and self.exigir_acervo and isinstance(out, dict):
                    aviso = self.acervo_status()
                    if aviso:
                        out["acervo_incompleto"] = aviso
                return out
        finally:
            _politica_atual.reset(token)

    return guardado


# Consultas que leem derivados (modelo, dispositivos, FTS): recusadas em home de DERIVED_VERSION antiga.
_DEPENDENTES = frozenset({
    "buscar_legislacao", "resolver_citacao", "obter_dispositivo", "historico_dispositivo",
    "verificar_citacao", "verificar_texto",
})

for _nome in _CONTADAS:
    setattr(Verifica, _nome, _guardar(getattr(Verifica, _nome)))
