"""Fachada única do FREOA Verifica — tipos simples, chaves em português."""

from __future__ import annotations

import hashlib
import hmac
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
from dataclasses import asdict, replace
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
from freoa_verifica.contrato import CONTRATO_VERSAO
from freoa_verifica.courts import normalize_court
from freoa_verifica.search import buscar_and_or, consulta_fts, normalize_fts_query
from freoa_verifica.connectors.guarda import BLOQUEIAM_A_FONTE, GuardaExecucao, da_chamada
from freoa_verifica.connectors.base import (
    AmbiguousCandidates,
    Candidate,
    ParsedDecision,
    Unavailable,
    get_connector,
    registry,
    sob_guarda,
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
from freoa_verifica.temporal import _parse_iso, today_sp
from freoa_verifica.texto_resposta import (ORIGEM_LEGADO, ORIGEM_LEGADO_CONFERIDO, content_type_do_response,
                                           interpretar_legado_padrao)
from freoa_verifica.transport import _CIRCUIT_BREAKERS, Response
from freoa_verifica import situacao  # C2
from freoa_verifica.verify import (
    MemoryResolver,
    ResolvedWork,
    SourceUnavailable,
    SourceAmbiguous,
    _current_redaction,
    _provision_blocking_issues,
    _find_provision,
    _caput_nao_representado,
    _alternativas_caput,
    _reading_blockers,
    _temporal_select,
    _camara_sem_historia,
    _annotations_for_cut,
    INICIO_ATUAL_NAO_DOCUMENTADO,
    _inferir_esfera,
    campos_evidencia,
    campos_evidencia_obra,
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
from freoa_verifica import particao as _particao
from freoa_verifica.registro import politica_atual as _politica_atual

_log = logging.getLogger("freoa_verifica.service")
_ESPERA_CONCORRENCIA = 10.0
_ESPERA_CLOSE = 30.0

from freoa_verifica.sanitizacao import DOC_CLOSE, DOC_OPEN, envolver  # noqa: E402,F401

from freoa_verifica.politica_captura import (  # noqa: E402
    LEGIS_CONNECTORS as _LEGIS_CONNECTORS,
    LEGIS_NOVA_CAPTURA as _LEGIS_NOVA_CAPTURA,
    exigir_nova_captura,
)
# Falha que é da fonte, não do item: o controlador para de consultá-la e a declara indisponível (FIX17/F-23).
_INTERROMPEM_A_FONTE = BLOQUEIAM_A_FONTE | {"fonte_fora"}


_NEGATIVAS_DA_SITUACAO = frozenset({"REVOGADO", "DISPOSITIVO_REVOGADO", situacao.REVOGADO_NA_FONTE})


def _historica(data: str | None) -> bool:
    """D válida e diferente de hoje (America/Sao_Paulo): consulta histórica, passada ou futura."""
    d = _parse_iso(data) if data else None
    return d is not None and d != today_sp()


def _guarda_historica(out: dict[str, Any], data: str | None) -> None:
    """C1: sem fundamento validado (hoje nunca há, IL.2) nenhum estado final para D afirma `verified`,
    `divergent` ou revogação. Mantêm-se `nao_existia`, `ambiguous` e entradas inválidas."""
    if not _historica(data):
        return
    temporal = out.get("temporal") or {}
    if (temporal.get("status") in ("verified", "vigente_na_fonte", "divergent")
            or temporal.get("reason_code") in _NEGATIVAS_DA_SITUACAO):
        out["temporal"] = {**temporal, "status": "unknown", "reason_code": "sem_fundamento_do_periodo"}
    texto = out.get("text") or {}
    if texto.get("status") in ("verified", "divergent") or (
            texto.get("reason_code") in _NEGATIVAS_DA_SITUACAO and (out.get("temporal") or {}).get("status") != "not_found"):
        out["text"] = {**texto, "status": "unknown", "reason_code": "sem_fundamento_do_periodo"}


def _normalizar_aditivos(out: dict[str, Any]) -> dict[str, Any]:
    """C4: `fundamento_temporal` e `correspondencia_textual` presentes em toda resposta de verificação e de obtenção.

    `fundamento_temporal` é sempre nulo (sem resolvedor de versões oficiais, IL.2); `correspondencia_textual` só
    sobrevive com a identidade FINAL `verified`. Chamado no último ponto antes da persistência e da emissão, depois de
    todos os rebaixamentos e decoradores."""
    ident = out.get("identity")
    out["fundamento_temporal"] = None
    out.setdefault("ultima_versao_oficial_anterior", None)
    out.setdefault("cadeia_alteracoes", [])
    out.setdefault("cadeia_completa", False)
    out.setdefault("pendencias_temporais", [])
    if not (isinstance(ident, dict) and ident.get("status") == "verified"):
        out["correspondencia_textual"] = None
    else:
        out.setdefault("correspondencia_textual", None)
    return out


class _InterpretacaoIndisponivel(Exception):
    """Captura sem os dados que reproduzem a interpretação original do corpo (F-22, decisão 0064)."""


def _proveniencia(cap: dict | None, derivado: dict | None = None) -> dict | None:
    """`{interpretacao: "legado_sem_cabecalho" | "legado_padrao_da_fonte_conferido"}` (experimental, 0065 e emenda)
    se o texto vem de captura lida sem Content-Type: prova degradada, declarada em toda resposta pública que o entrega."""
    origem = (cap or {}).get("origem_da_codificacao") or (derivado or {}).get("interpretacao_origem")
    return {"interpretacao": origem} if origem in (ORIGEM_LEGADO, ORIGEM_LEGADO_CONFERIDO) else None


def _hash_modelo(modelo: dict | None) -> str | None:
    """Hash canônico do modelo para a conferência da releitura legada (0065, emenda): título, ementa, texto e, por
    dispositivo, caminho, rótulo, escopo, rubrica, cabeçalhos e redações (texto, riscado). Sem modelo: None."""
    if not isinstance(modelo, dict):
        return None

    def _red(r: dict) -> list:
        return [r.get("text"), bool(r.get("struck"))]

    canon = {
        "title": modelo.get("title"), "ementa": modelo.get("ementa"), "text": modelo.get("text"),
        "provisions": [{
            "path": p.get("path"), "label": p.get("label"), "scope": p.get("scope"), "rubrica": p.get("rubrica"),
            "headings": p.get("headings") or [], "redactions": [_red(r) for r in p.get("redactions") or []],
            "concurrent": [_red(r) for r in p.get("concurrent_redactions") or []],
        } for p in modelo.get("provisions") or []],
    }
    return hashlib.sha256(json.dumps(canon, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


_JANELA_REORDENACAO = 50  # só os 50 primeiros candidatos são reordenados; além deles vale a ordem bm25
_SIGLAS_TRIBUNAL_FILTRO = frozenset({"STJ", "STF", "TCU", "TJDFT", "TJSP", "CVM"})
_JURIS_CONNECTORS = ("stj", "stf", "tcu", "tjsp", "tjdft", "cvm_colegiado")
_JURIS_ID_MAP = {"stj": "stj", "tcu": "tcu", "tjsp": "tjsp", "tjdft": "tjdft",
                 "cvm": "cvm_colegiado", "cvm_colegiado": "cvm_colegiado"}
_DEFAULT_TEXT_LIMIT = 4000
_EMENTA_MAX = 1200
_CLASSES_POR_EXTENSO = (
    ("agravo em recurso especial", "AREsp"), ("recurso especial", "REsp"),
    ("agravo em recurso extraordin[aá]rio", "ARE"), ("recurso extraordin[aá]rio", "RE"),
)


def _tipos_documento(coverage: dict[str, Any]) -> list[str]:
    """Tipos de documento que a fonte entrega, a partir da cobertura declarada do conector."""
    tipos = ["ementa"] if coverage.get("ementa") else []
    it = coverage.get("inteiro_teor")
    if it is True:
        tipos.append("inteiro_teor")
    elif it:
        tipos.append("inteiro_teor_parcial")
    return tipos or ["metadados"]


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
                    "reason_code": exc.reason,
                    **({"fontes_consultadas": exc.fontes_consultadas} if exc.fontes_consultadas else {})}
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


def _trecho_pertinente(text: str, q: str, max_chars: int) -> tuple[str, bool]:
    """Janela do texto em torno do primeiro termo da consulta (sem acento/caixa); sem termo, o início."""
    import unicodedata
    # Texto dobrado (sem acento, minúsculo) com mapa para o índice do original: NFD e ligaduras inclusive.
    dobrado, mapa = [], []
    for i, ch in enumerate(text):
        for c in unicodedata.normalize("NFKD", ch):
            if not unicodedata.combining(c):
                dobrado.append(c.lower())
                mapa.append(i)
    fold = "".join(dobrado)
    termos = ["".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c)).lower()
              for t in re.findall(r"\w{4,}", unicodedata.normalize("NFC", q or ""))]
    achados = [mapa[i] for t in termos if t and (i := fold.find(t)) >= 0]
    inicio = max(0, min(achados) - 80) if achados else 0
    trecho = text[inicio:inicio + max_chars]
    return trecho, inicio > 0 or inicio + max_chars < len(text)


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


def _classe_norm(value: str | None) -> str:
    """Sem acento, caixa nem espaços: "SumulaVinculante" casa "Súmula Vinculante"."""
    import unicodedata
    return "".join("".join(c for c in unicodedata.normalize("NFKD", value or "")
                           if not unicodedata.combining(c)).lower().split())


_DISPOSITIVO_SO = re.compile(
    r"art(?:igo)?\.?\s*\d[\d.]*\s*(?:[º°o]|-[A-Z])?"
    r"(?:\s*,?\s*(?:§\s*\d+\s*[º°o]?|par[aá]grafo\s+[úu]nico|inc(?:iso|\.)?\s*[IVXLCDM]+|[IVXLCDM]+"
    r"|al[ií]nea\s+[a-z]|al\.\s*[a-z]|[a-z]\)))*\s*\.?",
    re.I)


def _dispositivo_posposto(citacao: str) -> str:
    """Consulta isolada "<norma> art. N" (sem vírgula, nada além do dispositivo) recebe a vírgula que a
    extração exige em prosa (decisões 0016/0018). Só na citação avulsa; texto corrido segue a regra geral."""
    m = re.match(r"^\s*(.+?\d{4})\s+(art(?:igo)?\.?\s*\d.*?)\s*$", citacao, re.I)
    if not m or not _DISPOSITIVO_SO.fullmatch(m.group(2)):
        return citacao
    norma = parse_one(m.group(1))
    if norma is None or norma.work is None or norma.path or len(norma.raw.strip()) < len(m.group(1).strip()) - 1:
        return citacao
    return f"{m.group(1)}, {m.group(2)}"


def _classe_compativel(row, key) -> bool:
    if row["court"] == "TCU" and row["class"] is None:
        return True
    if row["class"]:
        return _classe_norm(row["class"]) == _classe_norm(key.class_)
    return row["official_id"] == key.number  # sem classe gravada, só o identificador exato


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
            boot = connect(self._db_path, operacional=True)
            boot.close()
        self._uso = None  # marca de uso do home entre processos (trava.py, A1)
        if self.home.is_dir():
            from freoa_verifica import trava

            try:
                self._uso = trava.registrar(self.home)
            except OSError:  # home somente leitura: sem marca, nada a proteger por este lado
                if not self._read_only:
                    raise
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

    @contextmanager
    def exclusivo_home(self, timeout: float = 60.0):
        """`exclusivo()` + nenhum OUTRO processo usando o home (HomeEmUso); para quem troca o arquivo do banco."""
        from freoa_verifica import trava

        with self.exclusivo(timeout):
            with trava.exclusivo_entre_processos(self.home):
                yield

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
                if self._uso is not None:
                    from freoa_verifica import trava

                    trava.liberar(self._uso)
                    self._uso = None
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
        content_type: str | None = None,
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
            content_type=content_type,
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
        situacao.registrar_do_corpo(self.conn, rw, source_id, body, content_type)  # C2
        if demovida:  # o modelo canônico anterior permanece
            canonica = self._rebuild_from_db(work_key, _exact=True)
            rw = canonica if isinstance(canonica, ResolvedWork) else rw
        self._resolver.add(rw)
        if source_id == "planalto":
            corte = self._acervo_ate_planalto()
            for w in self._resolver.works.values():
                if w.source_id == "planalto" or (w.source_id is None and (w.work_key.authority == "federal" or w.document.profile == "planalto")):
                    w.acervo_ate = corte
            rw.acervo_ate = corte
        if work_key.year <= 0:
            with self.conn:
                self.conn.execute("INSERT OR IGNORE INTO work_year_issue(work_id,reason,capture_id) VALUES (?,?,?)",
                                  (rw.work_id, "ANO_NAO_DECLARADO", rw.capture_id))
        return rw

    # ------------------------------------------------------------------
    # Resolver sob demanda
    # ------------------------------------------------------------------

    def _rebuild_from_db(self, work: WorkKey, *, _exact=False, _capture_id=None) -> ResolvedWork | list[ResolvedWork] | None:
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
        if _capture_id is not None:
            caps = [c for c in caps if c["id"] == _capture_id]
        else:
            caps = [c for c in caps if c.get("profile") != "camara_original"]
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
        source_id = cap.get("source_id") if cap else None
        acervo_ate = None
        if source_id == "planalto" or (source_id is None and (row["authority"] == "federal" or doc.profile == "planalto")):
            acervo_ate = self._acervo_ate_planalto()
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
            proveniencia=_proveniencia(cap, saved),
            source_id=source_id,
            acervo_ate=acervo_ate,
            fontes_consultadas=([{"fonte": "camara_legin", "resultado": "acervo", "motivo": None, "categoria": None}]
                               if source_id == "camara_legin" else []),
            procedencia_tipo=(cap.get("procedencia") if cap else None) or "nao_identificado",
        )
        if source_id == "camara_legin":
            self._revalidar_camara(rw)
        return rw

    def _revalidar_camara(self, rw):
        """Releitura não amplia a política: corpo, página de origem e href recuperáveis."""
        from freoa_verifica.parsers.camara_legin import PARSER_VERSION
        if rw.document.parser_version != PARSER_VERSION:
            raise SourceUnavailable("camara_modelo_requer_reprocessamento", [
                {"fonte": "camara_legin", "resultado": "indisponivel",
                 "motivo": "camara_modelo_requer_reprocessamento", "categoria": None}])
        from freoa_verifica.connectors.camara_policy import validar_url, url_publicada
        from freoa_verifica.connectors.camara_legin import arvore, compacto
        try:
            route = validar_url(rw.url)
            self._authenticate_capture(rw.capture_id)
            inv = next(json.loads(b.text) for b in rw.document.editorial_blocks if b.kind == "camara_inventario")
            origin = inv["pagina"]
            origin_route = validar_url(origin["url"])
            if origin_route["recurso"] != "norma" or any(origin_route[k] != route[k] for k in ("id", "familia", "numero", "ano")):
                raise ValueError("pagina_de_outra_obra")
            page = self.conn.execute("SELECT * FROM capture WHERE url=? AND sha256=? AND source_id='camara_legin'",
                                     (origin["url"], origin["sha256"])).fetchone()
            if page is None:
                raise ValueError("pagina_norma_ausente")
            self._authenticate_capture(page["id"])
            raw = blobs.get_blob(page["sha256"], home=self.home)
            response = Response(page["url"], page["url"], 200, {}, raw, page["sha256"], page["fetched_at"], [],
                                "text/html", content_type=page["content_type"] or "text/html")
            matches = [r for r in inv["recursos"] if r["url"] == rw.url and r["admitido"]]
            if len(matches) != 1 or route["recurso"] not in {"atualizado", "original"}:
                raise ValueError("vinculo_invalido")
            link = matches[0]
            if not any(url_publicada(origin["url"], a.get("href")) == rw.url and compacto(a) == link["rotulo"]
                       for a in arvore(response).xpath('//a[@href]')):
                raise ValueError("link_nao_publicado")
            cursor = rw.url
            visited = set()
            for edge in inv.get("descoberta", []):
                if edge["url"] != cursor or cursor in visited:
                    raise ValueError("cadeia_descoberta_invalida")
                visited.add(cursor)
                validar_url(cursor)
                validar_url(edge["origem_url"])
                cap = self.conn.execute("SELECT * FROM capture WHERE url=? AND sha256=? AND source_id='camara_legin'",
                                        (edge["origem_url"], edge["origem_sha256"])).fetchone()
                if cap is None:
                    raise ValueError("origem_descoberta_ausente")
                self._authenticate_capture(cap["id"])
                body = blobs.get_blob(cap["sha256"], home=self.home)
                source = Response(cap["url"], cap["url"], 200, {}, body, cap["sha256"], cap["fetched_at"], [],
                                  "text/html", content_type=cap["content_type"] or "text/html")
                if not any(a.get("href") == edge["href"] and compacto(a) == edge["rotulo"]
                           and url_publicada(source.url, a.get("href")) == cursor
                           for a in arvore(source).xpath('//a[@href]')):
                    raise ValueError("href_descoberta_invalido")
                cursor = source.url
            if validar_url(cursor)["recurso"] not in {"busca", "portal"}:
                raise ValueError("descoberta_sem_raiz")
        except (ValueError, TypeError, KeyError, StopIteration, OSError) as exc:
            raise SourceUnavailable("camara_releitura_sem_vinculo_validado") from exc

    def _selecionar_camara(self, work, versao="vigente", fonte=None):
        """Seleção por fonte/versão de capturas coexistentes; nunca pelo último cache em memória."""
        rows = self.conn.execute("SELECT id, year FROM work WHERE authority=? AND kind=? AND number=? AND (year=? OR ?=0)",
                                 (work.authority, work.kind, work.number, work.year, work.year)).fetchall()
        if not rows:
            return None
        if len(rows) > 1:
            if fonte is None and versao == "vigente" and not any(
                any(c.get("source_id") == "camara_legin" for c in repo.captures_for_work(self.conn, r["id"])) for r in rows
            ):
                return None  # conservar a resolução legada quando não há captura Câmara
            raise SourceAmbiguous([{"work_id": r["id"], "kind": work.kind, "number": work.number, "year": r["year"]}
                                   for r in rows])
        caps = repo.captures_for_work(self.conn, rows[0]["id"])
        if not any(c.get("source_id") == "camara_legin" for c in caps) and fonte is None and versao == "vigente":
            return None
        selected = {}
        for c in caps:
            if fonte and c["source_id"] != fonte:
                continue
            if c["source_id"] == "camara_legin":
                profile = "camara_original" if versao == "publicacao_original" else "camara_atualizado"
                if c.get("profile") != profile:
                    continue
            elif versao != "vigente":
                continue
            selected.setdefault(c["source_id"], c)
        if not selected:
            raise SourceUnavailable("versao_nao_capturada")
        exact_work = WorkKey(work.authority, work.kind, work.number, int(rows[0]["year"]))
        result = [self._rebuild_from_db(exact_work, _exact=True, _capture_id=c["id"]) for c in selected.values()]
        return result[0] if len(result) == 1 else result

    def _acervo_ate_planalto(self) -> str | None:
        # C7: calculado na emissão, sem cache; vale também para alteração do acervo por outro processo.
        row = self.conn.execute(
            "SELECT MAX(fetched_at) FROM capture WHERE source_id='planalto' AND fetched_at IS NOT NULL"
        ).fetchone()
        return str(row[0])[:10] if (row and row[0]) else None

    def _evidencia_dispositivo(self, rw: ResolvedWork) -> dict[str, Any]:
        is_planalto = (rw.source_id == "planalto" or (rw.source_id is None and (rw.work_key.authority == "federal" or rw.document.profile == "planalto")))
        acervo_ate = self._acervo_ate_planalto() if is_planalto else None
        return campos_evidencia_obra(rw, acervo_ate)

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
        self.reparar_anos()
        rows = self.conn.execute("SELECT c.*, p.work_id, p.work_date, p.amending_texts_json, p.interpretacao_codificacao, p.interpretacao_origem, p.model_json FROM capture c JOIN parsed_document p ON p.capture_id=c.id WHERE p.model_json IS NOT NULL").fetchall()
        counts = {'reprocessados':0, 'divergentes':[], 'falhas':[], 'por_fonte':{}}
        for row in rows:
            if row['source_id'] not in {'planalto','cvm_normas','bcb'}:
                continue
            work = self.conn.execute('SELECT * FROM work WHERE id=?',(row['work_id'],)).fetchone()
            if not work or work['authority'].startswith('invalidated:'):
                continue
            fonte = counts['por_fonte'].setdefault(row['source_id'], {
                'reprocessadas_atuais': 0, 'reprocessadas_legadas': 0, 'reprocessadas_legadas_conferidas': 0,
                'falhas': {}})
            try:
                response, decisao = self._resposta_da_captura(row)
            except Exception as exc:  # noqa: BLE001 — blob ausente ou interpretação indisponível: falha declarada
                counts['falhas'].append({'capture_id': row['id'], 'motivo': str(exc)})
                fonte['falhas'][str(exc)[:80]] = fonte['falhas'].get(str(exc)[:80], 0) + 1
                continue
            try:
                doc = self._get(row['source_id']).parse(response)
                conferencia = None
                if decisao[2] == ORIGEM_LEGADO_CONFERIDO:
                    # Padrão da fonte só com modelo anterior idêntico ao relido; senão, falha (0065, emenda).
                    try:
                        anterior = _hash_modelo(json.loads(row['model_json']))
                    except ValueError:
                        anterior = None
                    novo = _hash_modelo(asdict(doc))
                    if anterior is None or anterior != novo:
                        raise _InterpretacaoIndisponivel('interpretacao_indisponivel')
                    conferencia = json.dumps({'modelo_anterior_sha256': anterior, 'modelo_novo_sha256': novo})
                key = WorkKey(work['authority'],work['kind'],work['number'],work['year'])
                validate_identity(key,doc,row['work_date'])
                # Recibo (imutável) sem decisão: o derivado registra a desta releitura, com o modelo (0065, 0066).
                legada = ((decisao[1], decisao[2], conferencia)
                          if row['content_type'] is None and row['origem_da_codificacao'] is None else None)
                repo.persist_parsed_document(self.conn,capture_id=row['id'],document=doc,work_id=work['id'],work_date=row['work_date'],amending_act_texts=json.loads(row['amending_texts_json'] or '{}'),interpretacao=legada)
                counts['reprocessados'] += 1
                fonte[{ORIGEM_LEGADO: 'reprocessadas_legadas', ORIGEM_LEGADO_CONFERIDO: 'reprocessadas_legadas_conferidas'}
                      .get(decisao[2], 'reprocessadas_atuais')] += 1
            except IdentityMismatch:
                with self.conn:
                    self.conn.execute('UPDATE work SET authority=? WHERE id=?',('invalidated:'+work['authority'],work['id']))
                counts['divergentes'].append(work['id'])
            except Exception as exc:  # noqa: BLE001 - falha da releitura é declarada por captura, não engolida
                counts['falhas'].append({'capture_id':row['id'],'motivo':str(exc)})
                fonte['falhas'][str(exc)[:80]] = fonte['falhas'].get(str(exc)[:80], 0) + 1
        with self.conn:  # 0034: capturas que perdem dispositivos deixam de ser canônicas
            counts['divergentes'] += repo.aplicar_monotonia(self.conn)
        self._resolver = MemoryResolver()
        return counts

    def _resposta_da_captura(self, row) -> tuple["Response", tuple]:
        """(`Response` relido do recibo, decisão de interpretação), pela mesma função única (F-22, 0064, 0065).

        Captura anterior à 014 usa o `content-type` de `headers_json`; sem nenhum, a decisão vem só dos bytes
        (`legado_sem_cabecalho`, sem Content-Type inventado); sem declaração nos bytes e inválida em UTF-8, a
        `CODIFICACAO_LEGADA_POR_FONTE`, cuja conferência com o modelo anterior cabe ao chamador
        (`legado_padrao_da_fonte_conferido`, 0065, emenda). Bytes ininterpretáveis ou decisão registrada (no recibo
        ou, para recibo sem ela, no derivado) que a função atual não reproduz: `_InterpretacaoIndisponivel`, nunca
        outra interpretação, em silêncio.
        """
        from freoa_verifica.transport import Response

        headers = json.loads(row['headers_json'] or '{}')
        recibo = (row['content_type'], row['codificacao'], row['origem_da_codificacao'])
        ctype = recibo[0] or headers.get('content-type')
        body = blobs.get_blob(row['sha256'], home=self.home)
        response = Response(row['url'], row['final_url'], row['status'], headers, body, row['sha256'],
                            row['fetched_at'], [], row['mime'], content_type=ctype or "")
        decisao = repo.interpretacao_do_recibo(response)
        if decisao == (None, None, None) and not ctype:
            padrao = interpretar_legado_padrao(body, row['source_id'])
            if padrao is not None:
                response = replace(response, interpretacao_legada=padrao)
                decisao = (None, padrao.codificacao, padrao.origem)
        if not repo.decisao_registrada(decisao[1], decisao[2]):  # Content-Type sem decisão não basta (F-26)
            raise _InterpretacaoIndisponivel('interpretacao_indisponivel')
        if recibo[0] is not None or recibo[2] is not None:
            divergente = decisao != recibo
        else:
            no_derivado = (row['interpretacao_codificacao'], row['interpretacao_origem'])
            divergente = no_derivado[1] is not None and decisao[1:] != no_derivado
        if divergente:
            raise _InterpretacaoIndisponivel('interpretacao_divergente')
        return response, decisao

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

    def _capture_work(self, work: WorkKey, requested_work_date=None, *, versao="vigente") -> ResolvedWork | list[ResolvedWork] | None:
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
            order = ["camara_legin"]
        else:
            order = list(_LEGIS_CONNECTORS)

        errors: list[str] = []
        consultadas: list[dict] = []
        for cid in dict.fromkeys(order):  # cada fonte uma vez por chamada (0058)
            if cid not in _LEGIS_NOVA_CAPTURA:
                continue
            try:
                conn_obj = self._get(cid)
                cand = conn_obj.resolve(key)
                if cand is None:
                    consultadas.append({"fonte": cid, "resultado": "ausente", "motivo": None, "categoria": None})
                    continue
                if cid == "camara_legin":
                    cand = replace(cand, metadata={**cand.metadata, "versao": versao})
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
                    content_type=content_type_do_response(resp),
                    url=resp.final_url or resp.url,
                    fetched_at=resp.fetched_at,
                    label=label,
                    work_date=declared_identity(parsed)[1] if cid == "camara_legin" else None,
                )
                if cid == "camara_legin":
                    for page in conn_obj.paginas.values():
                        repo.save_capture(self.conn, page, cid, home=self.home)
                    consultadas.append({"fonte": cid, "resultado": "capturada", "motivo": None, "categoria": None})
                if cid == "cvm_normas":  # C2: página do ato sempre capturada como evidência de situação
                    situacao.registrar_cvm(self.conn, self.home, conn_obj, cand, rw_novo)
                rw_novo.fontes_consultadas = consultadas
                return rw_novo
            except AmbiguousCandidates as exc:
                raise SourceAmbiguous([asdict(c) for c in exc.candidates]) from exc
            except IdentityMismatch:
                raise
            except Unavailable as exc:
                # Entre fontes oficiais distintas qualquer Unavailable permite a próxima, declarada em
                # fontes_consultadas; dentro da mesma fonte só ausência explícita autoriza (decisão 0058).
                errors.append(f"{cid}:{exc.reason}")
                consultadas.append({"fonte": cid, "resultado": "indisponivel", "motivo": exc.reason,
                                    "categoria": exc.categoria,
                                    **({"evidencia_indisponibilidade": exc.evidencia} if exc.evidencia else {})})
            except Exception as exc:  # noqa: BLE001 — captura sob demanda
                errors.append(f"{cid}:{type(exc).__name__}")
                consultadas.append({"fonte": cid, "resultado": "erro", "motivo": type(exc).__name__,
                                    "categoria": "regressao"})
                break  # erro de programação ou de parse não passa adiante
        if errors:
            raise SourceUnavailable(";".join(errors[:3]), consultadas)
        return None

    def _resolve(self, work: WorkKey, requested_work_date=None, *, strict: bool = False,
                 versao="vigente", fonte=None) -> ResolvedWork | list[ResolvedWork] | None:
        """strict: obra ausente do acervo sem poder consultar a fonte é lacuna de cobertura, não negativa (A2)."""
        if work.authority == "federal":
            try:
                selected = self._selecionar_camara(work, versao, fonte)
            except SourceUnavailable as exc:
                if exc.reason != "versao_nao_capturada" or self._offline():
                    raise
                selected = self._capture_work(work, requested_work_date, versao=versao)
            if selected is not None:
                if isinstance(selected, ResolvedWork):
                    validate_identity(work, selected.document, requested_work_date)
                return selected
            if fonte is not None and fonte != "camara_legin":
                raise SourceUnavailable("fonte_selecionada_nao_capturada")
            if versao != "vigente" or fonte == "camara_legin":
                got = self._capture_work(work, requested_work_date, versao=versao)
                if got is None:
                    raise SourceUnavailable("versao_nao_capturada")
                return got
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
                        if codes := _reading_blockers(rw, row["path"]):
                            vigencia = {"status": "unknown", "motivo": codes[0], "flags": codes}
                        elif prov:
                            tr = _temporal_select(rw, prov, data, work_date=rw.work_date)
                            vigencia = {
                                "status": tr.status,
                                "regras": tr.rules_applied,
                                "flags": tr.flags,
                            }
                except Unavailable as exc:  # declarada com categoria, nunca vigente por silêncio (FIX18)
                    vigencia = {"status": "unknown", "motivo": exc.reason, **exc.classificacao()}
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
            if cid not in _LEGIS_NOVA_CAPTURA:
                nao_consultada(cid, "acervo_legado_sem_nova_captura")
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
                fontes_status[cid] = {"status": "unavailable", "motivo": exc.reason, "parcial": False,
                                      **exc.classificacao()}
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
        if connector.id not in _LEGIS_NOVA_CAPTURA:
            raise Unavailable("acervo_legado_sem_nova_captura")
        capture_id = None
        work_id = None
        failure = None
        classificacao: dict[str, Any] = {}
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
                if connector.id == "camara_legin":
                    wk, work_date = declared_identity(parsed)
                    if wk is None:
                        raise Unavailable("IDENTIDADE_NAO_DECLARADA")
                else:
                    work_date = None
                # A7: candidato ao vivo é gravado direto no staging, nunca no FTS canônico.
                rw = self.indexar_obra(
                    source_id=connector.id,
                    work_key=wk,
                    document=parsed,
                    body=resp.body,
                    content_type=content_type_do_response(resp),
                    url=resp.final_url or resp.url,
                    fetched_at=resp.fetched_at,
                    label=cand.title,
                    fts_alvo="fts_staging",
                    work_date=work_date,
                )
                capture_id = rw.capture_id
                work_id = rw.work_id
                if connector.id == "camara_legin":
                    for page in connector.paginas.values():
                        repo.save_capture(self.conn, page, connector.id, home=self.home)
                if connector.id == "cvm_normas":  # C2
                    situacao.registrar_cvm(self.conn, self.home, connector, cand, rw)
                if parsed.provisions:
                    path = parsed.provisions[0].path
                    trecho = parsed.provisions[0].redactions[0].text if parsed.provisions[0].redactions else trecho
        except Unavailable as exc:
            if exc.categoria in _INTERROMPEM_A_FONTE:
                raise  # desafio, recusa ou fonte fora: o controlador interrompe a fonte e declara (FIX17/F-23)
            failure, classificacao = exc.reason, exc.classificacao()  # falha do item, com categoria e evidência
        except Exception as exc:  # noqa: BLE001
            failure = getattr(exc, "reason", str(exc)) or type(exc).__name__
        text, trunc = _truncate(trecho, 280)
        return {
            **classificacao,
            "obra": cand.title,
            "caminho": path,
            "rotulo": cand.title,
            "trecho": text,
            "url_oficial": cand.url,
            "capture_id": capture_id,
            "work_id": work_id,
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
            if exc.fontes_consultadas:
                out["fontes_consultadas"] = exc.fontes_consultadas
            return out
        if resolved is None:
            out["status"] = "inexistente"
            return out
        if isinstance(resolved, list):
            out["status"] = "ambigua"
            out["candidatos"] = [r.work_id for r in resolved]
            return out
        if cite.path:
            if codes := _reading_blockers(resolved, cite.path):
                return {**out, "status": "unknown", "caminho": cite.path,
                        **({"alternativas": _alternativas_caput(cite.path)}
                           if codes[0] == "caput_refere_se_ao_artigo" else {}),
                        "motivo": codes[0], "flags": codes, "work_id": resolved.work_id,
                        "identity": {"status": "unknown", "reason_code": codes[0]}}
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
        if resolved.fontes_consultadas:
            out["fontes_consultadas"] = resolved.fontes_consultadas
        return out

    @_authenticated_output
    def obter_dispositivo(
        self,
        citacao: str | None = None,
        work_id: str | None = None,
        caminho: str | None = None,
        data: str | None = None,
        versao: str = "vigente",
        fonte: str | None = None,
    ) -> dict[str, Any]:
        if versao not in {"vigente", "publicacao_original"}:
            return {"status": "formato_invalido", "motivo": "versao_invalida", "versao": versao}
        if fonte is not None and fonte not in registry():
            return {"status": "formato_invalido", "motivo": "fonte_invalida", "versao": versao}
        out = self._obter_dispositivo(citacao, work_id, caminho, data, versao, fonte)
        out["versao"] = versao
        # A2 (IL.3-a): `remissoes[]` só acompanha texto efetivamente devolvido; nos demais estados é lista vazia.
        if out.get("status") != "encontrada" or not isinstance(out.get("texto"), str) or not out["texto"]:
            out["remissoes"] = []
        else:
            out.setdefault("remissoes", [])
        vig = out.get("vigencia")
        if isinstance(vig, dict) and _historica(data) and (
                vig.get("status") in ("verified", "vigente_na_fonte", "revogado")
                or vig.get("reason_code") in _NEGATIVAS_DA_SITUACAO):
            # C1: guarda histórica final (obter_dispositivo não tem trecho nem identidade a rebaixar).
            out["vigencia"] = {**vig, "status": "unknown", "reason_code": "sem_fundamento_do_periodo"}
        return out

    def _obter_dispositivo(self, citacao: str | None, work_id: str | None, caminho: str | None,
                           data: str | None, versao="vigente", fonte=None) -> dict[str, Any]:
        rw: ResolvedWork | None = None
        path = caminho
        if citacao:
            cite = parse_one(citacao)
            if (pend := self._so_conferencia(cite, citacao)) is not None:
                return pend
            if cite and cite.work:
                path = path or cite.path
                try:
                    resolved = self._resolve(cite.work, strict=True, versao=versao, fonte=fonte)
                except SourceUnavailable as exc:
                    return {"status": "indisponivel", "motivo": exc.reason,
                            **({"fontes_consultadas": exc.fontes_consultadas} if exc.fontes_consultadas else {})}
                if isinstance(resolved, list):
                    return {"status": "ambigua", "candidatos": [r.work_id for r in resolved]}
                rw = resolved
            elif cite is None:
                return {"status": "formato_invalido"}
        if rw is None and work_id:
            for cached in self._resolver.works.values():
                if (cached.work_id == work_id and cached.source_id != "camara_legin" and versao == "vigente" and fonte is None
                        and not self.conn.execute("SELECT 1 FROM parsed_document p JOIN capture c ON c.id=p.capture_id "
                                                  "WHERE p.work_id=? AND c.source_id='camara_legin' LIMIT 1", (work_id,)).fetchone()):
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
                            WorkKey(row["authority"], row["kind"], row["number"], int(row["year"])), versao=versao, fonte=fonte
                        )
                        if isinstance(resolved, ResolvedWork):
                            rw = resolved
                        elif isinstance(resolved, list):
                            return {"status": "ambigua", "candidatos": [r.work_id for r in resolved]}
                    except SourceUnavailable as exc:
                        return {"status": "indisponivel", "motivo": exc.reason,
                                **({"fontes_consultadas": exc.fontes_consultadas} if exc.fontes_consultadas else {})}
        if rw is None:
            return {"status": "inexistente"}
        if fonte is not None and rw.source_id != fonte:
            return {"status": "indisponivel", "motivo": "fonte_selecionada_nao_capturada"}
        if rw.source_id == "camara_legin":
            return self._obter_camara(rw, path, data, versao)
        if versao == "publicacao_original":
            return {"status": "unknown", "reason_code": "primeira_publicacao_nao_identificada", "texto": None}
        return self._resposta_dispositivo(rw, path, data)

    def _resposta_dispositivo(self, rw, path, data):
        """Construção comum do contrato de obtenção, inclusive nulidade dos campos."""
        sit = situacao.carregar(self.conn, rw, self.home)  # C2
        if not path:
            return {
                "status": "encontrada",
                "work_id": rw.work_id,
                "situacao_obra": situacao.resumo(sit),  # C2
                "caminho": None,
                "texto": None,
                "aviso": "informe caminho ou citação com dispositivo",
                "evidencia": self._evidencia_dispositivo(rw),
                **({"proveniencia": rw.proveniencia} if rw.proveniencia else {}),
            }
        if rw.persisted_incomplete:
            return {"status": "unknown", "reason_code": "DADOS_PERSISTIDOS_INCOMPLETOS"}
        prov = _find_provision(rw.document, path)
        if prov is None:
            return self._sem_dispositivo(rw, path)

        if codes := _reading_blockers(rw, path):
            return {"status": "unknown", "reason_code": codes[0], "work_id": rw.work_id,
                    "caminho": path, "texto": None, "texto_atual": None, "truncado": False,
                    "redacoes_anteriores": [], "redacao_anterior_ausente_na_fonte": self._anterior_ausente(prov, rw),
                    "situacao_obra": situacao.resumo(sit), "fundamento_temporal": None,
                    "correspondencia_textual": None, "evidencia": self._evidencia_dispositivo(rw),
                    "anotacoes": [asdict(a) for r in prov.redactions for a in r.annotations],
                    "vigencia": {"status": "unknown", "reason_code": codes[0], "regras": [],
                                 "flags": codes, "intervalo": None}}

        tr = _temporal_select(rw, prov, data, work_date=rw.work_date, amending_act_texts=rw.amending_act_texts, fetched_at=rw.fetched_at, quarantined=rw.quarantined)
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
            "remissoes": self._remissoes_dispositivo(rw, path, texto),
            "texto_atual": texto_atual,
            "truncado": trunc,
            "redacao_anterior_ausente_na_fonte": self._anterior_ausente(prov, rw),
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
            "fundamento_temporal": None,
            "correspondencia_textual": None,
            "evidencia": self._evidencia_dispositivo(rw),
            **({"proveniencia": rw.proveniencia} if rw.proveniencia else {}),
        }

    def _remissoes_dispositivo(self, rw, path, texto) -> list[dict[str, Any]]:
        """A2 (IL.3-a): remissões expressas do texto; `resolvida` só com a obra identificada sem ambiguidade e o caminho
        existente no documento da obra alvo já capturado (nunca consulta a rede)."""
        if not isinstance(texto, str) or not texto:
            return []
        from freoa_verifica import remissoes as _rem

        own = rw.work_key
        raiz = (path or "").split(".")[0]
        art = raiz if re.fullmatch(r"art\d+(?:-[A-Z])?", raiz) else None
        documentos: dict[tuple, Any] = {}

        def existe(work, p: str) -> bool:
            chave = (work.kind, work.number, work.year)
            if chave == (own.kind, own.number, own.year):
                doc = rw.document
            else:
                if chave not in documentos:
                    documentos[chave] = self._documento_local(work)
                doc = documentos[chave]
            return doc is not None and _find_provision(doc, p) is not None

        return _rem.remissoes(texto, own, existe, art, implicita="/" not in (path or ""))

    def _documento_local(self, work: WorkKey):
        """Documento já capturado da obra, sem rede e sem escolher entre candidatas (ambígua ou ausente: None)."""
        if not work.year:
            return None
        try:
            hit = self._resolver.resolve(work)
            if not isinstance(hit, ResolvedWork):
                hit = self._rebuild_from_db(work, _exact=True)
            if not isinstance(hit, ResolvedWork) or hit.persisted_incomplete:
                return None
            validate_identity(work, hit.document, hit.work_date)
            return hit.document
        except Exception:  # noqa: BLE001  - fechado: sem conferência, a remissão não é resolvida
            return None

    def _obter_camara(self, rw, path, data, versao):
        self._revalidar_camara(rw)
        if motivo := _caput_nao_representado(rw, path):
            return {"status": "unknown", "reason_code": motivo, "motivo": motivo,
                    **({"alternativas": _alternativas_caput(path)}
                       if motivo == "caput_refere_se_ao_artigo" else {}),
                    "work_id": rw.work_id, "caminho": path, "versao": versao,
                    "texto": None, "texto_atual": None, "redacoes_anteriores": [],
                    "vigencia": {"status": "unknown", "reason_code": motivo,
                                 "regras": [], "flags": [], "intervalo": None},
                    "fundamento_temporal": None, "fontes_consultadas": rw.fontes_consultadas,
                    "evidencia": self._evidencia_dispositivo(rw)}
        out = self._resposta_dispositivo(rw, path, data)
        out.update(versao=versao, fontes_consultadas=rw.fontes_consultadas)
        out.setdefault("texto", None)
        out.setdefault("evidencia", self._evidencia_dispositivo(rw))
        prov = _find_provision(rw.document, path) if path else None
        if path and prov is None:
            out.update(status="unknown", reason_code="primeira_publicacao_do_dispositivo_nao_obtida"
                       if versao == "publicacao_original" else "dispositivo_nao_identificado")
        elif prov:
            issues = [i for i in rw.document.issues if i.blocking_scope == "document"]
            issues += _provision_blocking_issues(rw.document, path)
            if issues or prov.ambiguous:
                out.update(status="unknown", reason_code=issues[0].code if issues else "recorte_ambiguo",
                           texto=None, texto_atual=None, redacoes_anteriores=[],
                           vigencia={"status": "unknown", "reason_code": issues[0].code if issues else "recorte_ambiguo",
                                     "regras": [], "flags": [], "intervalo": None},
                           pendencias=[asdict(i) for i in issues])
            if red := _current_redaction(prov):
                out["evidencia"].update(path=path, span=list(red.span), parser_version=rw.document.parser_version)
                if not red.text.strip():
                    out.update(status="unknown", reason_code="dispositivo_sem_redacao_normativa", texto=None)
                out["anotacoes"] = [asdict(a) for a in _annotations_for_cut(rw, path)]
                for annotation in out["anotacoes"]:
                    annotation["links"] = [ref for block in rw.document.editorial_blocks
                        if block.kind == "nota_camara_links" and rw.document.text[block.span[0]:block.span[1]] == annotation["raw"]
                        for ref in json.loads(block.text)]
        if _camara_sem_historia(rw) and prov:
            vigencia = out.setdefault("vigencia", {})
            vigencia.update(status="unknown", intervalo=None, limites_inferidos=True,
                            needs_judgment=True)
            vigencia["flags"] = list(dict.fromkeys([
                *vigencia.get("flags", []), INICIO_ATUAL_NAO_DOCUMENTADO]))
            vigencia.setdefault("reason_code", INICIO_ATUAL_NAO_DOCUMENTADO)
            out["redacao_anterior_ausente_na_fonte"] = True
        if versao == "publicacao_original":
            out.setdefault("vigencia", {"regras": [], "flags": [], "intervalo": None}).update(
                status="unknown", reason_code="publicacao_nao_prova_aplicabilidade")
        self._material_historico_camara(out, rw, path, data)
        return out

    def _material_historico_camara(self, out, rw, path, data):
        """Material de referência, sem prova de completude e sem habilitar fundamento."""
        if not _historica(data) or rw.source_id != "camara_legin":
            return
        pending = []
        failures = []
        chain = []
        inv = next((json.loads(b.text) for b in rw.document.editorial_blocks if b.kind == "camara_inventario"), {})
        from freoa_verifica.connectors.camara_policy import validar_url
        kinds = {"lei": "lei", "leicom": "lei_complementar", "medpro": "medida_provisoria",
                 "declei": "decreto_lei", "decret": "decreto"}
        if not self._offline():
            con = self._get("camara_legin")
            try:
                candidate = con.resolve({"kind": rw.work_key.kind, "number": rw.work_key.number, "year": rw.work_key.year})
                try:
                    prior = self._selecionar_camara(rw.work_key, "publicacao_original", "camara_legin")
                except SourceUnavailable:
                    prior = None
                if prior is None:
                    try:
                        self._capture_work(rw.work_key, versao="publicacao_original")
                    except SourceUnavailable as exc:
                        failures.extend(exc.fontes_consultadas or [{"motivo": exc.reason, "categoria": None}])
                        pending.append({"motivo": "publicacao_original_indisponivel", "url": candidate.url})
                result = con.capturar_relacoes(candidate)
                pending.extend(result["pendencias"])
                failures.extend(result["indisponibilidades"])
                indexed = set()
                for material in result["materiais"]:
                    resp = material.get("resposta")
                    doc = material.get("documento")
                    if resp is None or doc is None or resp.sha256 in indexed:
                        continue
                    indexed.add(resp.sha256)
                    own_key, own_date = declared_identity(doc)
                    if own_key is None:
                        pending.append({"motivo": "identidade_alterador_nao_confirmada", "url": resp.url})
                        continue
                    self.indexar_obra(source_id="camara_legin", work_key=own_key, document=doc, body=resp.body,
                                      url=resp.final_url, fetched_at=resp.fetched_at, work_date=own_date,
                                      content_type=content_type_do_response(resp), label=doc.title)
                for page in con.paginas.values():
                    repo.save_capture(self.conn, page, "camara_legin", home=self.home)
            except AmbiguousCandidates:
                pending.append({"motivo": "identidade_da_pagina_de_relacoes_ambigua", "url": inv.get("pagina", {}).get("url")})
            except Unavailable as exc:
                failures.append({"motivo": exc.reason, "categoria": exc.categoria, **exc.classificacao()})
                pending.append({"motivo": "relacoes_indisponiveis", "url": inv.get("pagina", {}).get("url")})
        known = {}
        for r in inv.get("recursos", []):
            if not r.get("acao"):
                continue
            try:
                act = validar_url(r["url"])
            except ValueError:
                act = {}
            captured = None
            if act.get("familia") in kinds:
                cache_key = (act["familia"], act["numero"], act["ano"])
                if cache_key not in known:
                    try:
                        key = WorkKey("federal", kinds[act["familia"]], act["numero"], act["ano"])
                        known[cache_key] = self._selecionar_camara(key, "publicacao_original", "camara_legin")
                    except SourceUnavailable as exc:
                        known[cache_key] = None
                        if exc.reason != "versao_nao_capturada":
                            failures.append({"motivo": exc.reason, "categoria": None, "url": r["url"]})
                captured = known[cache_key]
            pub = {"data": None, "veiculo": None, "pagina": None}
            text, evidence = None, None
            if isinstance(captured, ResolvedWork):
                own_inv = next((json.loads(b.text) for b in captured.document.editorial_blocks if b.kind == "camara_inventario"), {})
                publication = next((v.get("publicacao") for v in own_inv.get("recursos", []) if v["recurso"] == "original"), None)
                if publication:
                    pub = {k: publication.get(k) for k in pub}
                text = captured.document.text
                evidence = self._evidencia_dispositivo(captured)
                if captured.quarantined:
                    pending.append({"motivo": "texto_alterador_com_impedimentos_de_parse", "url": r["url"]})
            # Datas desconhecidas não são substituídas pela assinatura ou pelo slug.
            if pub["data"] and pub["data"] > data:
                continue
            chain.append({"ato": {"especie": kinds.get(act.get("familia"), "nao_identificado"),
                                  "numero": act.get("numero"), "ano": act.get("ano"), "url": r["url"]},
                          "publicacao": pub,
                          "dispositivo_atingido": r.get("dispositivo_atingido"), "acao": r["acao"],
                          "texto": text, "evidencia": evidence, "ordem_na_fonte": r["ordem_na_fonte"]})
            if text is None:
                pending.append({"motivo": "publicacao_e_texto_do_alterador_nao_obtidos", "url": r["url"]})
            if pub["data"] is None:
                pending.append({"motivo": "pertinencia_ao_periodo_e_ordenacao_desconhecidas", "url": r["url"]})
        pending.append({"motivo": "completude_e_ordenacao_por_publicacao_nao_demonstradas", "url": inv.get("pagina", {}).get("url")})
        previous = None
        try:
            original = self._selecionar_camara(rw.work_key, "publicacao_original", "camara_legin")
        except SourceUnavailable as exc:
            original = None
            if exc.reason != "versao_nao_capturada":
                failures.append({"motivo": exc.reason, "categoria": None})
        pub = next((r.get("publicacao") for r in inv.get("recursos", []) if r["recurso"] == "original"), None)
        if isinstance(original, ResolvedWork) and pub and pub.get("data") and pub["data"] <= data:
            provision = _find_provision(original.document, path) if path else None
            if provision and not _reading_blockers(original, path, history=True):
                previous = {"data": pub["data"], "texto": provision.redactions[0].text,
                            "caminho": path, "evidencia": self._evidencia_dispositivo(original)}
                previous["evidencia"].update(path=path, span=list(provision.redactions[0].span),
                                             parser_version=original.document.parser_version)
        if previous is None:
            pending.append({"motivo": "versao_anterior_documentada_nao_identificada", "url": None})
        else:
            chain = [item for item in chain if item["publicacao"]["data"] is None
                     or item["publicacao"]["data"] >= previous["data"]]
        chain.sort(key=lambda item: (item["publicacao"]["data"] or "9999-99-99", str(item["ato"]["numero"]), item["ordem_na_fonte"]))
        dated = {}
        for item in chain:
            stamp = item["publicacao"]["data"]
            if stamp is not None:
                dated.setdefault(stamp, set()).add(item["ato"]["url"])
        for stamp, acts in dated.items():
            if len(acts) > 1:
                pending.append({"motivo": "empate_publicacao_sem_precedencia_normativa", "url": None})
        out.update(ultima_versao_oficial_anterior=previous, cadeia_alteracoes=chain,
                   cadeia_completa=False, pendencias_temporais=pending, fundamento_temporal=None)
        if failures:
            out["indisponibilidades_temporais"] = failures
        if "vigencia" in out or "status" in out:
            out.setdefault("vigencia", {}).update(status="unknown", reason_code="sem_versao_oficial_na_data")
        for dim in ("temporal", "text"):
            obj = out.get(dim)
            if isinstance(obj, dict) and (obj.get("reason_code") in {"sem_fundamento_do_periodo", "HISTORICO_ANTERIOR_AUSENTE"}
                                         or obj.get("status") in {"verified", "vigente_na_fonte"}):
                obj.update(status="unknown", reason_code="sem_versao_oficial_na_data")

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
            return {"status": "indisponivel", "motivo": exc.reason,
                    **({"fontes_consultadas": exc.fontes_consultadas} if exc.fontes_consultadas else {})}
        if resolved is None:
            return {"status": "inexistente"}
        if isinstance(resolved, list):
            return {"status": "ambigua"}
        if motivo := _caput_nao_representado(resolved, cite.path):
            return {"status": "unknown", "reason_code": motivo, "motivo": motivo,
                    **({"alternativas": _alternativas_caput(cite.path)}
                       if motivo == "caput_refere_se_ao_artigo" else {}),
                    "citacao": citacao, "caminho": cite.path, "work_id": resolved.work_id,
                    "linha_do_tempo": [], "eventos": [], "regras": [],
                    "needs_judgment": True, "fundamento_temporal": None,
                    "evidencia": self._evidencia_dispositivo(resolved)}
        prov = _find_provision(resolved.document, cite.path)
        if prov is None:
            return self._sem_dispositivo(resolved, cite.path)
        if codes := _reading_blockers(resolved, cite.path, history=True):
            return {"status": "unknown", "citacao": citacao, "caminho": cite.path,
                    "work_id": resolved.work_id, "linha_do_tempo": [], "regras": [],
                    "eventos": [asdict(a) for a in _annotations_for_cut(resolved, cite.path)],
                    "redacao_anterior_ausente_na_fonte": self._anterior_ausente(prov, resolved),
                    "limites_inferidos": True,
                    "flags": codes, "needs_judgment": True, "reason_code": codes[0],
                    "fundamento_temporal": None, "evidencia": self._evidencia_dispositivo(resolved)}
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
                    "limites_inferidos": bool(d.redaction.annotations or fim is not None),
                    "fundamento_temporal": None,
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
            "redacao_anterior_ausente_na_fonte": self._anterior_ausente(prov, resolved),
            "situacao_obra": situacao.resumo(sit),  # C2
        }

    @staticmethod
    def _anterior_ausente(prov: Provision, rw=None) -> bool:
        """A primeira redação conhecida já é 'Redação dada': a anterior não consta da fonte."""
        if rw is not None and _camara_sem_historia(rw):
            return True
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
        citacao = _dispositivo_posposto(citacao)
        cite = parse_one(citacao)
        if _path is not None:
            cite = next((c for c in extract(citacao) if c.path == _path), None)
        if cite and cite.work is None and (cite.decision is not None or cite.kind == "processo") and _cite is None:
            return self._verificar_decisao_avulsa(cite, citacao, trecho, data, modo, proposicao)
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
                        "evidence": ([{"fontes_consultadas": exc.fontes_consultadas}]  # experimental (0058)
                                     if not mismatch and exc.fontes_consultadas else []),
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
                }, _cite or cite, citacao, trecho, data, modo, em_texto=_cite is not None)
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
                }, _cite or cite, citacao, trecho, data, modo, em_texto=_cite is not None)

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

    def _decisao_bruta(self, cite: Citation, judgment_date=None) -> tuple[str, dict | None]:
        """Confirmação de decisão, súmula ou processo (status do acervo e evidência pelo construtor único)."""
        if cite.kind == "processo":
            status, evidencia = self._confirm_cnj(cite, judgment_date=judgment_date)
        else:
            status, evidencia = self._confirm_decision(cite.decision, judgment_date=judgment_date)
        return status, self._ev_captura(evidencia, court=getattr(cite.decision, "court", None))

    @staticmethod
    def _decisao_para_verificacao(cite: Citation, status: str, evidencia: dict | None, trecho, proposicao) -> dict[str, Any]:
        ident = {
            "encontrada": ("verified", "DECISAO_CONFIRMADA_NA_CAPTURA"),
            "processo_confirmado": ("verified", "PROCESSO_CONFIRMADO_MAIS_DE_UM_REGISTRO"),
            "nao_confirmado_no_acervo": ("unknown", "NAO_CONFIRMADO_NO_ACERVO"),
            "indisponivel": ("unavailable", "EVIDENCIA_INDISPONIVEL"),
        }.get(status, ("unknown", str(status).upper()))
        return {
            "identity": {"status": ident[0], "reason_code": ident[1],
                         "evidence": [evidencia] if ident[0] == "verified" and evidencia else [],
                         **({"cobertura": evidencia.get("cobertura")} if isinstance(evidencia, dict) and "cobertura" in evidencia else {})},
            "text": {"status": "not_assessed",
                     "reason_code": "CONFRONTO_DE_DECISAO_NAO_REALIZADO" if trecho else "SEM_TRECHO", "evidence": []},
            "temporal": {"status": "not_assessed", "reason_code": "NAO_APLICAVEL_A_DECISAO", "evidence": []},
            "support": {"status": "not_assessed", "reason_code": "SUPPORT_NOT_ASSESSED", "evidence": []},
            "proposicao": proposicao, "run_id": None, "citation": _citation_to_dict(cite),
        }

    def _verificar_decisao_avulsa(self, cite: Citation, citacao: str, trecho, data, modo, proposicao) -> dict[str, Any]:
        """Decisão ou súmula citada sozinha: mesma confirmação de `verificar_texto` (auditoria comparativa 1.2.0).
        Identidade confirmada só com documento oficial capturado; confronto textual de decisão não é feito."""
        status, evidencia = self._decisao_bruta(cite)
        out = self._decisao_para_verificacao(cite, status, evidencia, trecho, proposicao)
        return self._finalizar(out, cite, citacao, trecho, data, modo)

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
                and out["identity"].get("status") not in ("not_found", "unavailable", "ambiguous")):
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
        # C1 (0075, §2, itens 1, 5 e 6): guarda histórica na saída, defesa em profundidade da guarda da situação.
        _guarda_historica(out, data)
        if (cite is not None and cite.work is not None and _historica(data)
                and out["identity"].get("status") in {"verified", "unknown"}):
            try:
                material_rw = self._resolve(cite.work, strict=True)
            except (SourceUnavailable, IdentityMismatch):
                material_rw = None
            if (isinstance(material_rw, ResolvedWork)
                    and not _caput_nao_representado(material_rw, cite.path)) and (
                out["identity"].get("status") == "verified" or
                out["identity"].get("reason_code") in _reading_blockers(material_rw, cite.path)
            ):
                self._material_historico_camara(out, material_rw, cite.path, data)
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
        # Recalcular acervo_ate nas evidências emitidas caso seja Planalto
        corte_planalto = self._acervo_ate_planalto()
        for dim_name in ("identity", "text", "temporal", "support"):
            for ev in (out.get(dim_name) or {}).get("evidence") or []:
                if isinstance(ev, dict) and (ev.get("acervo_ate") is not None or (ev.get("url") or "").startswith("https://www.planalto.gov.br")):
                    ev["acervo_ate"] = corte_planalto
        # C4: campos aditivos no ponto único, depois de TODOS os rebaixamentos (inclusive ausência de captura e falha de
        # autenticação) e imediatamente antes da persistência e da emissão.
        if (cite is not None and cite.path
                and out["identity"].get("reason_code") == "caput_refere_se_ao_artigo"):
            out["alternativas"] = _alternativas_caput(cite.path)
        _normalizar_aditivos(out)
        if gravar:
            if self._read_only:
                out["registro"] = {"gravado": False, "motivo": "somente_leitura"}  # C11: modo declarado
            else:
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
                corte = outer._acervo_ate_planalto()
                for item in resolved if isinstance(resolved, list) else [resolved]:
                    if isinstance(item, ResolvedWork) and item.capture_id:
                        outer._authenticate_capture(item.capture_id)
                        if item.source_id == "planalto" or (item.source_id is None and (item.work_key.authority == "federal" or item.document.profile == "planalto")):
                            item.acervo_ate = corte
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
            if cite.kind == "processo" or (cite.work is None and cite.decision is not None):
                # C11: processo, decisão e súmula passam pelo mesmo caminho de registro das verificações avulsas
                # (recibo recuperável ou modo somente leitura declarado), com o contexto da data de julgamento do texto.
                status, evidencia = self._decisao_bruta(
                    cite, judgment_date=self._decision_context_date(texto[cite.span[1]:cite.span[1]+240]))
                verif = self._finalizar(self._decisao_para_verificacao(cite, status, evidencia, trecho, None),
                                        cite, cite.raw, trecho, data, "literal", em_texto=True)
                if verif["identity"].get("status") != "verified" and status in ("encontrada", "processo_confirmado"):
                    status = "indisponivel"  # a autenticação da evidência rebaixou a identidade
            elif cite.work is None and cite.decision is None:
                status = "formato_invalido"
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
                    "fundamento_temporal": None,
                    "correspondencia_textual": (verif or {}).get("correspondencia_textual"),
                    "ultima_versao_oficial_anterior": (verif or {}).get("ultima_versao_oficial_anterior"),
                    "cadeia_alteracoes": (verif or {}).get("cadeia_alteracoes", []),
                    "cadeia_completa": (verif or {}).get("cadeia_completa", False),
                    "pendencias_temporais": (verif or {}).get("pendencias_temporais", []),
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
        status, evidence, _ = self._decision_evidence_rows(key, judgment_date)
        return status, evidence

    def _decision_evidence_rows(self, key, judgment_date=None):
        rows = self.conn.execute(
            "SELECT * FROM decision WHERE court=? AND identity_status='confirmed' "
            "AND (official_id=? OR UPPER(REPLACE(REPLACE(number,'.',''),' ',''))=?)",
            (key.court.upper(), key.number, key.number.replace(".","").replace(" ","").upper()),
        ).fetchall()
        # Classe comparada sem acento e sem caixa ("Sumula" casa "Súmula"); coincidência de identificador
        # não supera classe gravada divergente (auditoria 1.2.0).
        rows = [r for r in rows if _classe_compativel(r, key)]
        if key.year:
            rows = [r for r in rows if (r["judgment_date"] or "")[:4] == str(key.year)]
        if key.organ:
            rows = [r for r in rows if self._organ_key(r["organ"]) == self._organ_key(key.organ)]
        uf_nao_conferida = False
        if key.uf:
            # UF divergente exclui; UF ausente no registro (espelhos do STJ não a trazem) não exclui, mas é declarada.
            rows = [r for r in rows if not r["uf"] or r["uf"].upper() == key.uf.upper()]
            uf_nao_conferida = any(not r["uf"] for r in rows)
        if judgment_date:
            rows = [r for r in rows if r["judgment_date"] == judgment_date]
        multiple = len(rows) > 1
        if not rows:
            return "nao_confirmado_no_acervo", self._decision_coverage(key.court), []
        doc = self.conn.execute(
            "SELECT dd.*, c.url, c.fetched_at, c.sha256 AS capture_sha FROM decision_document dd "
            "JOIN capture c ON c.id=dd.capture_id WHERE dd.decision_id=? "
            "ORDER BY dd.created_at DESC LIMIT 1", (rows[0]["id"],),
        ).fetchone()
        if not doc or not doc["sha256"] or not doc["text"]:
            return "indisponivel", None, rows
        try:
            blobs.get_blob(doc["capture_sha"], home=self.home)
            if hashlib.sha256(doc["text"].encode("utf-8")).hexdigest() != doc["sha256"]:
                return "indisponivel", None, rows
        except (OSError, ValueError, blobs.BlobError):
            return "indisponivel", None, rows
        return ("processo_confirmado" if multiple else "encontrada"), self._ev_captura({
            "capture_id": doc["capture_id"], "sha256": doc["capture_sha"], "url": doc["url"], "fetched_at": doc["fetched_at"],
            **({"uf_citada_nao_conferida": key.uf.upper()} if uf_nao_conferida else {})}, court=rows[0]["court"]), rows

    def _ev_captura(self, ev: dict | None, *, court: str | None = None) -> dict | None:
        """C6: evidência de decisão/processo pelo construtor único, com a procedência persistida da captura."""
        if not isinstance(ev, dict) or not ev.get("capture_id"):
            return ev
        cap = self.conn.execute("SELECT source_id, procedencia FROM capture WHERE id=?", (ev["capture_id"],)).fetchone()
        planalto = bool(cap and cap["source_id"] == "planalto")
        ev.update(campos_evidencia(
            ev["capture_id"], ev.get("sha256"), ev.get("url"), ev.get("fetched_at"),
            esfera=_inferir_esfera(WorkKey(court.lower(), "", "", 0)) if court else "nao_identificado",
            procedencia=cap["procedencia"] if cap else None,
            acervo_ate=self._acervo_ate_planalto() if planalto else None,
        ))
        return ev

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
            return 'indisponivel', {**(evidence or {}), 'motivo':exc.reason, **exc.classificacao()}
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
        # TJSP e DataJud são fontes distintas: falha do TJSP não impede o DataJud, mas fica declarada (0058).
        consultadas: list[dict] = []
        try:
            # cjsg pode identificar julgamento; DataJud confirma somente o processo.
            connector = self._get('tjsp')
            try:
                found = connector.search(cite.raw, numero_processo=cite.raw, limite=5) if tribunal == 'tjsp' else []
                for cand in found:
                    response = connector.fetch(cand)
                    parsed = connector.parse(response)
                    if re.sub(r'\D','',parsed.cnj_number or '') != digits:
                        continue
                    if judgment_date and parsed.judgment_date != judgment_date:
                        continue
                    # Reaproveita a resposta já capturada; Unavailable do indexador interrompe a fonte.
                    result = self._index_candidate_juris(connector, cand, captured_response=response)
                    if result and result.get('capture_id'):
                        return 'encontrada', result
            except Unavailable as exc:
                consultadas.append({'fonte':'tjsp','resultado':'indisponivel','motivo':exc.reason,'categoria':exc.categoria})
            declaradas = {'fontes_consultadas':consultadas} if consultadas else {}
            try:
                connector = self._get('datajud')
                cand = connector.resolve({'tribunal':tribunal,'numero':cite.raw})
                if not cand:
                    return 'nao_confirmado_no_acervo', {'escopo':'processo; não julgamento', **declaradas}
                resp = connector.fetch(cand)
                parsed = connector.parse(resp)
                if re.sub(r'\D','', parsed.cnj_number or '') != digits:
                    return 'indisponivel', {'motivo':'identidade_divergente', **declaradas}
                self.conn.execute("INSERT OR IGNORE INTO source(id,authority,profile,hosts_json) VALUES (?,?,?,?)", (connector.id,connector.authority,connector.id,json.dumps(sorted(connector.hosts))))
                self.conn.commit()
                cap = repo.save_capture(self.conn,resp,connector.id,home=self.home)
                return 'processo_confirmado', {'capture_id':cap,'sha256':resp.sha256,'url':resp.final_url,'fetched_at':resp.fetched_at,'escopo':'processo; não julgamento', **declaradas}
            except Unavailable as exc:
                consultadas.append({'fonte':'datajud','resultado':'indisponivel','motivo':exc.reason,'categoria':exc.categoria})
                return 'indisponivel', {'motivo':exc.reason,'escopo':'processo; não julgamento', 'fontes_consultadas':consultadas, **exc.classificacao()}
            except Exception as exc:
                consultadas.append({'fonte':'datajud','resultado':'erro','motivo':type(exc).__name__,'categoria':'regressao'})
                return 'indisponivel', {'motivo':type(exc).__name__,'escopo':'processo; não julgamento', 'fontes_consultadas':consultadas}
        except Unavailable as exc:
            return 'indisponivel', {'motivo':exc.reason,'escopo':'processo; não julgamento', **exc.classificacao()}

        except Exception as exc:
            consultadas.append({'fonte':'tjsp','resultado':'erro','motivo':type(exc).__name__,'categoria':'regressao'})
            return 'indisponivel', {'motivo':type(exc).__name__,'escopo':'processo; não julgamento', 'fontes_consultadas':consultadas}

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
        cnj = re.fullmatch(r"\s*(?:processo\s+(?:n[º°.]?\s*)?)?(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})\s*", q, re.I)
        key = None if cnj else self._chave_processo(q)
        if cnj or key is not None:
            # Modo por identificador: data, autoridade e cursor não se aplicam; tribunal e limite, quando cabem (B2-04).
            nao_aplicados = [{"filtro": f, "motivo": "modo_por_identificador"}
                             for f, v in (("desde", desde), ("ate", ate), ("autoridade_min", autoridade_min),
                                          ("cursor", cursor)) if v]
            tribunais_norm = None if tribunais is None else {normalize_court(t) for t in tribunais}
            limite = max(1, min(int(limite), 50))
            if cnj:
                return self._juris_por_cnj(q, cnj.group(1), tribunais_norm, limite, nao_aplicados)
            return self._juris_por_numero(q, key, tribunais_norm, limite, nao_aplicados)
        filtro_da_consulta = None
        if tribunais is None:
            # Sigla de tribunal solta na consulta ("exclusão de sócio TJDFT") é filtro, não termo: como termo
            # casaria o cabeçalho "Tribunal de Justiça do Distrito Federal" de qualquer decisão (comparativo 1.2.0).
            # Só fora de aspas: frase exata é preservada como o usuário escreveu.
            partes = re.split(r'("[^"]*(?:"|$))', q)  # aspa sem fechamento protege até o fim
            fora = [p for p in partes if not p.startswith('"')]
            siglas = [t for p in fora for t in re.findall(r"(?<![\w/])([A-Za-z]{2,6})(?![\w/])", p)
                      if t.upper() in _SIGLAS_TRIBUNAL_FILTRO]
            if siglas:
                padrao = r"(?<![\w/])(?:" + "|".join(map(re.escape, siglas)) + r")(?![\w/])"
                resto = "".join(p if p.startswith('"') else re.sub(padrao, " ", p) for p in partes).strip()
                filtro_da_consulta = sorted({s.lower() for s in siglas})
                if not re.search(r"\w", resto):
                    return {"status": "entrada_insuficiente", "motivo": "CONSULTA_SO_COM_SIGLA_DE_TRIBUNAL",
                            "consulta": q, "filtro_tribunal_da_consulta": filtro_da_consulta,
                            "itens": [], "resultados": [], "cobertura": [], "truncado": False, "cursor": None}
                q, tribunais = " ".join(resto.split()), filtro_da_consulta
        out = self._juris_textual(q, tribunais, desde, ate, autoridade_min, limite, cursor)
        if filtro_da_consulta:
            out["filtro_tribunal_da_consulta"] = filtro_da_consulta
        return out

    # Segmento J.TR do CNJ -> conector com busca oficial pelo número (só onde existe).
    _CNJ_CONECTORES = {"8.07": "tjdft"}

    def _juris_por_cnj(self, q: str, cnj: str, tribunais=None, limite: int = 10,
                       nao_aplicados: list[dict[str, str]] | None = None) -> dict[str, Any]:
        """Número CNJ isolado: só o próprio processo, nunca outros (auditoria comparativa 1.2.0).

        `tribunais` (siglas normalizadas) e `limite` valem aqui; os demais filtros vêm em `nao_aplicados`."""
        from freoa_verifica.citation import validate_cnj_dv

        base = {"consulta": q, "modo_busca": "numero_cnj", "itens": [], "resultados": [], "relacionados": [],
                "truncado": False, "cursor": None, "fontes": {}, "cobertura": [],
                "filtros_nao_aplicados": list(nao_aplicados or []),
                "rules_version": AUTHORITY_RULES_VERSION}
        if not validate_cnj_dv(cnj):
            return {**base, "status": "formato_invalido", "motivo": "CNJ_DIGITO_VERIFICADOR_INVALIDO"}
        conector_id = self._CNJ_CONECTORES.get(cnj[16:20])
        if tribunais is not None and conector_id and normalize_court(conector_id) not in tribunais:
            return {**base, "status": "nao_confirmado_no_acervo", "escopo": "tribunal fora do filtro",
                    "aviso": "o tribunal do número CNJ está fora do filtro de tribunais; nada foi consultado"}
        fontes: dict[str, Any] = {}
        vivo: dict[str, Any] | None = None
        motivo_vivo: str | None = None
        if conector_id and not self._offline():
            connector = self._get(conector_id)
            try:
                lidas = connector.search(cnj)
                cands = [c for c in lidas if (c.metadata or {}).get("processo") == cnj]
                for cand in cands:
                    self._index_candidate_juris(connector, cand)
                fontes[conector_id] = {"status": "ok", "registros_do_processo": len(cands)}
                vivo = {"lidos": len(lidas), "indexados": len(cands), "total": getattr(lidas, "total", None),
                        "total_exato": getattr(lidas, "total_exato", None)}
            except (SourceUnavailable, Unavailable) as exc:
                fontes[conector_id] = {"status": "indisponivel", "motivo": getattr(exc, "reason", str(exc))}
                motivo_vivo = "falha"
                vivo = {"indisponivel": {"motivo": getattr(exc, "reason", str(exc)),
                                         **(exc.classificacao() if isinstance(exc, Unavailable) else {})}}
        elif conector_id:
            fontes[conector_id] = {"status": "nao_consultada", "motivo": "offline"}
            motivo_vivo = "offline"
        alvo = cnj.replace(".", "").replace("-", "")
        rows = [dict(r) for r in self.conn.execute(
            "SELECT d.id AS decision_id FROM decision d WHERE d.identity_status='confirmed' "
            "AND REPLACE(REPLACE(d.number,'.',''),'-','')=?", (alvo,))]
        itens = []
        tribunal_do_acervo = None
        for r in rows:
            row = self.conn.execute("SELECT court FROM decision WHERE id=?", (r["decision_id"],)).fetchone()
            tribunal_do_acervo = tribunal_do_acervo or row["court"]
            for full in repo.decisions_by_number(self.conn, row["court"], cnj):
                if full["decision_id"] == r["decision_id"]:
                    itens.append({**self._decisao_item(full), "relacao": "exato"})
        if tribunais is not None:
            itens = [i for i in itens if normalize_court(i["tribunal"] or "") in tribunais]
        cortou = len(itens) > limite
        itens = itens[:limite]
        # Tribunal implicado: o do conector do segmento J.TR; senão o do acervo; senão o próprio segmento (sem suporte).
        base["cobertura"] = [self._item_cobertura(
            conector_id or tribunal_do_acervo or f"CNJ {cnj[16:20]}", vivo=vivo, motivo_vivo=motivo_vivo,
            truncado_local=cortou)]
        base["truncado"] = self._truncado_da_cobertura(base["cobertura"])
        if itens:
            return {**base, "status": "encontrada", "itens": itens, "resultados": itens,
                    "total_parcial": len(itens), "fontes": fontes}
        consultada = fontes.get(conector_id or "", {}).get("status") == "ok"
        categorica = consultada and not base["truncado"]  # leitura cortada não sustenta negativa (B2-03)
        return {**base, "fontes": fontes,
                "status": "nao_encontrado_na_fonte" if categorica else "nao_confirmado_no_acervo",
                "escopo": (f"busca oficial {conector_id} pelo número" if consultada else "acervo local"),
                "aviso": ("a fonte oficial não retornou registro com este número" if categorica
                          else "a leitura da fonte oficial foi truncada; ausência não demonstra inexistência" if consultada
                          else "processo não localizado no acervo local; ausência não demonstra inexistência")}

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

    def _juris_por_numero(self, q: str, key, tribunais=None, limite: int = 10,
                          nao_aplicados: list[dict[str, str]] | None = None) -> dict[str, Any]:
        """A6: lookup exato por classe e número no acervo; nunca mistura outros processos.

        `tribunais` (siglas normalizadas) e `limite` valem aqui; os demais filtros vêm em `nao_aplicados`."""
        base = {"consulta": q, "modo_busca": "numero", "status": "nao_confirmado_no_acervo",
                "itens": [], "resultados": [], "relacionados": [], "resultados_textuais": [],
                "truncado": False, "cursor": None, "fontes": {},
                "filtros_nao_aplicados": list(nao_aplicados or []),
                "rules_version": AUTHORITY_RULES_VERSION}
        if tribunais is not None and key.court and normalize_court(key.court) not in tribunais:
            return {**base, "cobertura": [],
                    "aviso": "o tribunal da classe e número está fora do filtro de tribunais; nada foi consultado"}
        status, evidence, filtradas = self._decision_evidence_rows(key)
        base["status"] = status
        ids_ok = {r["id"] for r in filtradas}
        # Só o acervo é consultado por classe e número; a fonte ao vivo, mesmo existindo, não é (nao_suportado).
        cobertura = [self._item_cobertura(key.court, vivo=None, motivo_vivo="nao_suportado")] if key.court else []
        if status == "nao_confirmado_no_acervo":
            cob = dict(evidence["cobertura"])
            cob["tribunais"] = [r[0] for r in self.conn.execute(
                "SELECT DISTINCT court FROM decision ORDER BY court")]
            # `cobertura` já é o objeto do acervo neste estado (contrato 1): a lista por tribunal vai ao lado.
            return {**base, "cobertura": cob, "cobertura_por_tribunal": cobertura,
                    "aviso": "processo não localizado no acervo local; ausência não demonstra inexistência"}
        rows = repo.decisions_by_number(self.conn, key.court, key.number)
        cls = _classe_norm(key.class_)
        # Só os registros que passaram em todos os filtros de identidade (UF, ano, órgão, classe); cada item
        # leva a evidência da própria captura, nunca a de outro registro (auditoria 1.2.0).
        exatas = [r for r in rows if r["decision_id"] in ids_ok]
        incidentes = [r for r in rows if r["decision_id"] not in ids_ok
                      and _classe_norm(r["class"]).endswith(("no" + cls, "nos" + cls))]
        itens = []
        for r in exatas:
            item = self._decisao_item(r)
            item["evidencia"] = {"capture_id": r.get("capture_id"), "sha256": r.get("sha256"), "url": r.get("url_oficial"),
                                 **({k: evidence[k] for k in ("uf_citada_nao_conferida",) if evidence and k in evidence})}
            item["relacao"] = "exato"
            itens.append(item)
        rel = [{**self._decisao_item(r), "relacao": "incidente_do_mesmo_processo"} for r in incidentes]
        if len(itens) > limite:
            itens = itens[:limite]
            cobertura = [dict(c, truncado_local=True) for c in cobertura]
        return {**base, "itens": itens, "resultados": itens, "relacionados": rel, "cobertura": cobertura,
                "truncado": self._truncado_da_cobertura(cobertura),
                "total_parcial": len(itens), "evidencia": evidence}

    def _peso_idf(self):
        """Raridade do termo no acervo de decisões (IDF): "legitimidade" pesa mais que "sociedade" na
        pertinência da complementação OR (comparativo 1.2.0). Determinístico para um mesmo acervo."""
        import math
        n = self.conn.execute("SELECT COUNT(*) FROM fts_decision").fetchone()[0] or 1
        cache: dict[tuple[str, bool], float] = {}

        def peso(termo: str, prefixo: bool) -> float:
            k = (termo, prefixo)
            if k not in cache:
                expr = '{ementa inteiro_teor} : "' + termo.replace('"', '') + '"' + ("*" if prefixo else "")
                try:
                    df = self.conn.execute("SELECT COUNT(*) FROM fts_decision WHERE fts_decision MATCH ?",
                                           (expr,)).fetchone()[0]
                except sqlite3.Error:
                    df = 0
                cache[k] = math.log(1 + n / (1 + df))
            return cache[k]
        return peso

    def _acervo_do_tribunal(self, tribunal: str) -> dict[str, Any]:
        """Recorte e captura mais recente do tribunal no acervo instalado (decisão 0055)."""
        self.conn.create_function("fv_court", 1, normalize_court, deterministic=True)
        n, desde, ate = self.conn.execute(
            "SELECT COUNT(*), MIN(NULLIF(COALESCE(NULLIF(judgment_date,''), publication_date),'')), "
            "MAX(NULLIF(COALESCE(NULLIF(judgment_date,''), publication_date),'')) "
            "FROM decision WHERE fv_court(court)=?", (tribunal,)).fetchone()
        capturado = self.conn.execute(
            "SELECT MAX(c.fetched_at) FROM decision d JOIN decision_document dd ON dd.decision_id=d.id "
            "JOIN capture c ON c.id=dd.capture_id WHERE fv_court(d.court)=?", (tribunal,)).fetchone()[0]
        return {"n": n, "recorte": {"desde": desde, "ate": ate} if n and (desde or ate) else None,
                "capturado_em": capturado}

    def _item_cobertura(self, tribunal: str, *, acervo_consultado: bool = True, vivo: dict[str, Any] | None = None,
                        motivo_vivo: str | None = None, truncado_local: bool = False) -> dict[str, Any]:
        """Um item de `cobertura` (docs/CONTRATO.md). `vivo`: leitura ao vivo concluída (lidos, indexados, total,
        total_exato); `motivo_vivo`: por que a fonte ao vivo não foi (ou não concluiu a ser) consultada.
        `total_remoto` só vem da fonte; sem ela fica nulo, nunca o tamanho lido."""
        t = normalize_court(tribunal)
        cls = registry().get(_JURIS_ID_MAP.get(t, t))
        cov = getattr(cls, "coverage", {"busca_textual": True}) if cls is not None else {}
        ac = self._acervo_do_tribunal(t)
        tem_acervo = bool(ac["n"])
        tem_vivo = cls is not None and bool(cov.get("busca_textual_ao_vivo", cov.get("busca_textual")))
        capacidade = ("ambos" if tem_acervo and tem_vivo else "acervo" if tem_acervo
                      else "ao_vivo" if tem_vivo else "nenhuma")
        fez_acervo = acervo_consultado and tem_acervo
        fez_vivo = tem_vivo and vivo is not None and motivo_vivo is None
        consulta = ("ambos" if fez_acervo and fez_vivo else "acervo" if fez_acervo
                    else "ao_vivo" if fez_vivo else "nenhuma")
        if capacidade == "nenhuma":
            motivo = "nao_suportado"
        elif consulta == capacidade:
            motivo = None
        else:
            motivo = motivo_vivo if tem_vivo and not fez_vivo else "nao_suportado"
        indisponivel = (vivo or {}).get("indisponivel") if motivo == "falha" else None
        vivo = (vivo or {}) if fez_vivo else {}
        total = vivo.get("total")
        lidos = vivo.get("lidos", 0)
        return {
            "tribunal": t.upper(), "capacidade": capacidade, "consulta": consulta, "motivo_nao_consulta": motivo,
            "recorte_acervo": ac["recorte"], "capturado_em": ac["capturado_em"],
            "total_remoto": total, "total_exato": vivo.get("total_exato") if total is not None else None,
            "lidos": lidos, "indexados": vivo.get("indexados", 0),
            "truncado_remoto": total is not None and total > lidos,
            "truncado_local": truncado_local or bool(vivo.get("cortou_no_limite")),
            "indisponivel": indisponivel,
        }

    @staticmethod
    def _truncado_da_cobertura(cobertura) -> bool:
        """Corte registrado em qualquer item de `cobertura` (local ou remoto) torna o topo `truncado` (B2-03)."""
        return isinstance(cobertura, list) and any(c["truncado_remoto"] or c["truncado_local"] for c in cobertura)

    def _juris_textual(self, q, tribunais, desde, ate, autoridade_min, limite, cursor) -> dict[str, Any]:
        # Guarda por pesquisa: candidatos da mesma URL (ata) usam uma única captura, e fonte que desafiou
        # ou recusou não é consultada de novo na mesma pesquisa (FIX10/F-14).
        with da_chamada():
            return self._juris_textual_corpo(q, tribunais, desde, ate, autoridade_min, limite, cursor)

    def _juris_textual_corpo(self, q, tribunais, desde, ate, autoridade_min, limite, cursor) -> dict[str, Any]:
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
            # Candidatos além da página: a reordenação abaixo precisa de margem para promover quem tem a
            # consulta coberta pela ementa (comparativo 1.2.0).
            # Universo estável entre páginas: sempre ao menos 50 candidatos, completados por OR até o alvo, para que
            # a reordenação dos 50 primeiros seja idêntica em qualquer página (auditoria 1.2.0, paginação).
            alvo = max(offset + limite + 1, _JANELA_REORDENACAO)
            res = buscar_and_or(
                q, buscar, lambda r: f"{r.get('ementa') or ''} {r.get('inteiro_teor') or ''}",
                lambda r: r.get("decision_id") or r.get("official_id"),
                alvo, alvo, colunas="ementa inteiro_teor", peso=self._peso_idf())
            modo_busca = "ampliada" if res["fts"] and not res["and"] else "normal"
            tesauro_info = res["tesauro"]
            # Mesma correspondência: primeiro quem tem os termos na ementa (o resumo oficial do julgado), depois
            # quem só os tem espalhados no inteiro teor; a ordem bm25 desempata. Determinístico.
            from freoa_verifica.search import pertinencia
            variantes = consulta_fts(q)[1]
            def forca(r):
                # Termos na ementa contam inteiros; só no inteiro teor (sem ementa ou fora dela), pela metade.
                if r.get("ementa"):
                    h, n = pertinencia(variantes, r["ementa"])
                    return max(h / n, 0.5 * (r.get("pertinencia") or 0))
                return 0.5 * (r.get("pertinencia") or 0)
            cabeca = sorted(enumerate(res["linhas"][:_JANELA_REORDENACAO]),
                            key=lambda p: (-round(forca(p[1]), 2),
                                           p[1].get("correspondencia") != "todos_os_termos", p[0]))
            ordenadas = [r for _, r in cabeca] + res["linhas"][_JANELA_REORDENACAO:]
            return ordenadas[offset:offset + limite + 1]

        local = local_page()
        items: list[dict[str, Any]] = []
        def append_local(rows):
            items.extend(self._decisao_item(row, q) for row in rows)
        append_local(local)

        id_map = _JURIS_ID_MAP
        vivos: dict[str, dict[str, Any]] = {}  # leitura ao vivo por conector (alimenta `cobertura`)
        motivos_vivo: dict[str, str] = {}
        offline = os.environ.get("FV_OFFLINE", "").strip() in {"1", "true", "yes"}
        fontes_status: dict[str, dict[str, Any]] = {}
        filtros_por_fonte: dict[str, dict[str, str]] = {}
        filtros_nao_aplicados: list[dict[str, str]] = []
        for t in tribunais_norm:
            cid = id_map.get(t, t)
            if cid not in registry():
                fontes_status[cid] = {"status": "unavailable", "motivo": "fonte_nao_suportada", "parcial": False}
            elif offline:
                fontes_status[cid] = {"status": "unavailable", "motivo": "offline", "parcial": False}
                motivos_vivo[cid] = "offline"
        # Fonte cujo acervo local é só semente (TJDFT) é consultada ao vivo quando pedida explicitamente.
        sempre_ao_vivo = {id_map.get(t, t) for t in (tribunais_norm if tribunais is not None else [])
                          if id_map.get(t, t) in registry()
                          and getattr(registry()[id_map.get(t, t)], "coverage", {}).get("consultar_ao_vivo_sempre")}
        if (len(items) < limite or sempre_ao_vivo) and tribunais_norm and not offline:
            for t in tribunais_norm:
                cid = id_map.get(t, t)
                if cid not in registry():
                    continue
                if len(items) >= limite and cid not in sempre_ao_vivo:
                    motivos_vivo[cid] = "limite"
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
                    aplicados = getattr(conn_obj, "filtros", {})
                    filtros_por_fonte[cid] = {f: aplicados.get(f, "nao_suportado") for f in filtros}
                    for f in filtros:
                        if f not in aplicados:
                            # Nunca em silêncio: a fonte devolve sem o filtro; o serviço só o aplica (SQL) ao recuperado.
                            filtros_nao_aplicados.append({
                                "fonte": cid, "filtro": f,
                                "compensacao": "filtro_local_sobre_o_recuperado"})
                    cands = conn_obj.search(q, **filtros)
                    got = 0
                    indexados = 0
                    cortou = False
                    for pos, cand in enumerate(cands):
                        item = self._index_candidate_juris(conn_obj, cand)
                        if item:
                            indexados += 1
                            self._authenticate_output(item)
                        if item and normalize_court(item.get("tribunal") or "") in tribunais_norm and _authority_min_ok(
                            item.get("rotulo_autoridade") or "E", autoridade_min
                        ):
                            items.append(item)
                            got += 1
                        if len(items) >= limite and cid not in sempre_ao_vivo:
                            cortou = pos + 1 < len(cands)
                            break
                    # `total` só da fonte (decisão 0055): lista sem o atributo = fonte não informa.
                    vivos[cid] = {"lidos": len(cands), "indexados": indexados, "cortou_no_limite": cortou,
                                  "total": getattr(cands, "total", None),
                                  "total_exato": getattr(cands, "total_exato", None)}
                    fontes_status[cid] = {
                        "status": "ok",
                        "motivo": None,
                        "parcial": got < len(cands) or bool(getattr(cands, "truncado", False)),
                    }
                except SourceUnavailable:
                    raise
                except Unavailable as exc:
                    fontes_status[cid] = {
                        "status": "unavailable",
                        "motivo": exc.reason,
                        "parcial": False,
                        **exc.classificacao(),
                    }
                    motivos_vivo[cid] = "falha"
                    vivos[cid] = {"indisponivel": {"motivo": exc.reason, **exc.classificacao()}}
                except Exception as exc:  # noqa: BLE001
                    fontes_status[cid] = {
                        "status": "unavailable",
                        "motivo": f"{type(exc).__name__}:{exc}"[:200],
                        "parcial": False,
                    }
                    motivos_vivo[cid] = "falha"
                    vivos[cid] = {"indisponivel": {"motivo": fontes_status[cid]["motivo"]}}

        # Candidatos capturados ao vivo passam pelos mesmos filtros e ranking SQL.
        if not offline and any(v.get("status") == "ok" for v in fontes_status.values()):
            items.clear()
            append_local(local_page())
        page = items[:limite]
        truncado_local = len(items) > limite
        for cid, aplicados in filtros_por_fonte.items():
            if cid in fontes_status:
                fontes_status[cid]["filtros"] = aplicados
        # Cobertura por tribunal pedido ou implicado pelos itens (decisão 0055).
        courts_cortados = {normalize_court(i.get("tribunal") or "") for i in items[limite:]}
        implicados = [c for c in dict.fromkeys(normalize_court(i.get("tribunal") or "") for i in page)
                      if c and c not in tribunais_norm]
        cobertura = []
        for t in [*tribunais_norm, *implicados]:
            cid = id_map.get(t, t)
            if cid in registry() and cid not in vivos and cid not in motivos_vivo and not offline:
                motivos_vivo[cid] = "limite"  # a consulta ao vivo nem começou: a página já estava cheia
            cobertura.append(self._item_cobertura(
                t, vivo=vivos.get(cid), motivo_vivo=motivos_vivo.get(cid), truncado_local=t in courts_cortados))
        truncado = truncado_local or self._truncado_da_cobertura(cobertura)  # o cursor só pagina o que é local
        return {
            **_status_com_falhas("parcial" if truncado else "ok", _falhas_de_fonte(fontes_status), len(page)),
            "itens": page,
            "resultados": page,
            "cobertura": cobertura,
            "fontes": fontes_status,
            "filtros_nao_aplicados": filtros_nao_aplicados,  # experimental (docs/FILTROS.md)
            "total_parcial": offset + len(items),
            "truncado": truncado,
            "cursor": _encode_cursor(offset + limite) if truncado_local else None,
            "consulta": q,
            "autoridade_min": autoridade_min,
            "modo_busca": modo_busca,
            "tesauro": tesauro_info,
            "rules_version": AUTHORITY_RULES_VERSION,
        }

    def _decisao_item(self, row: dict[str, Any], q: str | None = None) -> dict[str, Any]:
        text = row.get("ementa") or row.get("inteiro_teor") or ""
        # Sem ementa, um trecho do inteiro teor (em torno do termo pesquisado) sai como `trecho_inteiro_teor`,
        # nunca sob o rótulo `ementa` (0038).
        ementa, trunc = _truncate(text, _EMENTA_MAX)
        trecho_it = None
        if not row.get("ementa") and text:
            trecho_it, trunc = _trecho_pertinente(text, q or "", _EMENTA_MAX)
            ementa = None
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
            **({"trecho_inteiro_teor": trecho_it} if trecho_it else {}),
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
        """Unavailable do conector sobe sempre ao controlador (confirmação, pesquisa, semente), que
        interrompe a fonte e declara a categoria; só falha que não é de indisponibilidade vira candidato
        só com metadados."""
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
                for extra in ("situacao_precedente", "divergencia_na_fonte", "integra_motivo"):
                    if parsed.metadata.get(extra):
                        attrs[extra] = parsed.metadata[extra]
                kind_gravado = ("decisao_monocratica" if parsed.kind == "monocratica" else parsed.kind) if parsed.kind in {
                    "acordao", "decisao_monocratica", "monocratica", "sumula", "tema", "voto",
                    "decisao_colegiado_cvm", "acordao_tcu", "repercussao_geral",
                } else "acordao"
                did = repo.upsert_decision(
                    self.conn,
                    court=court,
                    kind=kind_gravado,
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
                # A espécie também: recaptura validada de identidade preexistente corrige o kind (auditoria 1.2.0).
                self.conn.execute("UPDATE decision SET authority_attrs_json=?, authority_label=?, kind=? WHERE id=?",
                                  (json.dumps(attrs, ensure_ascii=False), auth.label, kind_gravado, did))
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
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, Unavailable):
                raise
            # Download/parse falhou: permanece metadados, sem capture_id.
            capture_id = None
            nivel = "metadados"
            did = repo.upsert_decision(
                self.conn,
                court=court,
                # Falha de download/parse preserva a espécie conhecida pelos metadados do candidato.
                kind="decisao_monocratica" if meta.get("kind") in {"monocratica", "decisao_monocratica"} else "acordao",
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
        max_chars: int | None = None,
        offset: int = 0,
        tribunal: str | None = None,
        parte_idx: int | None = None,
        parte_tamanho: int | None = None,
    ) -> dict[str, Any]:
        """Obtém a parte pedida de uma decisão do acervo (decisão 0038).

        Paginação por `offset` e `max_chars` (padrão 8000, máximo 50.000), com `cursor` para continuar.

        Partição determinística (experimental; decisão 0073, seção 7; PARIDADE-1.4, CH1–CH6): com `parte_idx`
        (inteiro >= 0) a resposta traz a parte `parte_idx` do texto canônico, em partes de até `parte_tamanho`
        pontos de código (500 a 10.000; padrão 2.000), com sobreposição fixa de 200 pontos de código, e o campo
        novo `particao`. O corte é sempre entre pontos de código (nunca no meio de um caractere nem de um par
        substituto) e prefere o fim de parágrafo (`\\n\\n`, depois `\\n`) nos últimos 200 pontos de código da
        janela; sem ele, corta no limite da janela. A regra completa está em `freoa_verifica.particao`.
        `parte_idx` junto com `offset` diferente de 0, com `max_chars` informado, ou fora de 0..partes_total-1,
        é `EntradaInvalida` (a mensagem traz `partes_total` quando conhecido); `parte_tamanho` sem `parte_idx`
        também. Sem `parte_idx`, a resposta é a de sempre e `particao` não aparece.
        """
        if parte not in {"ementa", "inteiro_teor", "voto", "certidao"}:
            raise EntradaInvalida(f"parte inválida: {parte!r} (ementa|inteiro_teor|voto|certidao)")
        particionado = parte_idx is not None
        if particionado:
            if isinstance(parte_idx, bool) or not isinstance(parte_idx, int) or parte_idx < 0:
                raise EntradaInvalida(f"parte_idx inválido: {parte_idx!r} (inteiro >= 0)")
            if offset not in (0, None) or max_chars is not None:
                raise EntradaInvalida("parte_idx não se combina com offset diferente de 0 nem com max_chars: "
                                      "use parte_idx e parte_tamanho, ou offset e max_chars")
            if parte_tamanho is None:
                parte_tamanho = _particao.PARTE_TAMANHO_PADRAO
            if (isinstance(parte_tamanho, bool) or not isinstance(parte_tamanho, int)
                    or not _particao.PARTE_TAMANHO_MIN <= parte_tamanho <= _particao.PARTE_TAMANHO_MAX):
                raise EntradaInvalida(f"parte_tamanho inválido: {parte_tamanho!r} "
                                      f"({_particao.PARTE_TAMANHO_MIN} a {_particao.PARTE_TAMANHO_MAX})")
        elif parte_tamanho is not None:
            raise EntradaInvalida("parte_tamanho só vale junto com parte_idx")
        max_chars = max(1, min(int(8000 if max_chars is None else max_chars), 50_000))
        offset = max(0, int(offset or 0))
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
            try:
                integra_motivo = (json.loads(row["authority_attrs_json"] or "{}").get("integra_motivo")
                                  if parte == "inteiro_teor" else None)
            except ValueError:
                integra_motivo = None
            return {**base, "status": "parte_indisponivel", "motivo": "PARTE_NAO_CAPTURADA",
                    **({"motivo_integra": integra_motivo} if integra_motivo else {}),
                    "parte_entregue": None, "texto": None, "capture_id": None}
        text = doc["text"]
        self._authenticate_capture(doc["capture_id"])
        if particionado:
            try:
                p = _particao.particionar(text, parte_idx, parte_tamanho)
            except IndexError as exc:
                raise EntradaInvalida(str(exc)) from None
            truncado = p.intervalo[1] < len(text)
            return {
                **base,
                "status": "encontrada",
                "parte_entregue": doc["kind"],
                "texto": p.texto_parte,
                "truncado": truncado,
                "offset": p.intervalo[0],
                "max_chars": parte_tamanho,
                "cursor": str(p.intervalo[1]) if truncado else None,
                "capture_id": doc["capture_id"],
                "particao": p.como_dict(),
            }
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
            return {"status": "indisponivel", "motivo": exc.reason, "reason_code": exc.reason, "itens": [],
                    "fonte": {"status": "unavailable", "motivo": exc.reason, **exc.classificacao()},
                    **exc.classificacao()}
        except Exception as exc:  # noqa: BLE001
            motivo = f"{type(exc).__name__}:{exc}"[:200]
            return {"status": "indisponivel", "motivo": motivo, "reason_code": motivo, "itens": []}
        itens = []
        falhas = []
        nao_indexados = 0
        interrompida: Unavailable | None = None
        for n, c in enumerate(cands):
            if interrompida is not None or n >= max_indexar or time.monotonic() >= prazo:  # 0024: parcial declarada
                nao_indexados += 1
                itens.append({"titulo": c.title, "chave": c.key, "url": c.url, "trecho": c.snippet or "",
                              "capture_id": None, "metadados": c.metadata, "nao_indexado": True,
                              **({"motivo": interrompida.reason} if interrompida else {})})
                continue
            try:
                item = _com_prazo(prazo, self._index_candidate_legis, connector, c)
            except Unavailable as exc:
                if exc.reason != "orcamento":
                    # Desafio, recusa ou fonte fora: nenhum pedido a mais à fonte, falha declarada (FIX17/F-23).
                    interrompida = exc
                    falhas.append({"chave": c.key, "url": c.url, "status": "unavailable", "motivo": exc.reason,
                                   **exc.classificacao()})
                    continue
                item = {"capture_id": None, "motivo": "orcamento"}  # abandonada: nada parcial é confirmado
                # A espera pode voltar antes do relógio (Windows): o orçamento declarado esgotado vale como esgotado.
                prazo = min(prazo, time.monotonic())
            if not item.get("capture_id") and time.monotonic() >= prazo:  # orçamento estourou no item
                nao_indexados += 1
                itens.append({"titulo": c.title, "chave": c.key, "url": c.url, "trecho": c.snippet or "",
                              "capture_id": None, "metadados": c.metadata, "nao_indexado": True,
                              "motivo": "orcamento"})
                continue
            if not item.get("capture_id"):
                falhas.append({"chave": c.key, "url": c.url, "status": "unavailable",
                               "motivo": item.get("motivo") or "captura_indisponivel",
                               **{k: item[k] for k in ("categoria", "evidencia_indisponibilidade") if k in item}})
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
        fonte = ({"status": "unavailable", "motivo": interrompida.reason, **interrompida.classificacao()}
                 if interrompida else {"status": "ok", "motivo": None})
        return {"status": status, "itens": itens, "total": getattr(cands, "total", len(cands)),
                "falhas": falhas, "indexados": len(itens) - nao_indexados, "nao_indexados": nao_indexados,
                "truncado": truncado, "fonte": fonte,
                **({"motivo": interrompida.reason, **interrompida.classificacao()} if interrompida else {})}

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
        from freoa_verifica.texto_resposta import texto_para_exibicao

        try:  # mesma interpretação da captura, pelo Content-Type do recibo (0063, 0064); exibição nunca falha
            ctype = cap.get("content_type") or (json.loads(cap.get("headers_json") or "{}") or {}).get("content-type")
        except (ValueError, AttributeError):
            ctype = None
        # Sem Content-Type: só os bytes, como prova degradada declarada (0065); o MIME gravado não é Content-Type.
        # Padrão da fonte só se a reconstrução o conferiu e registrou no derivado (0065, emenda).
        conferida = None
        if not ctype:
            der = self.conn.execute("SELECT interpretacao_origem FROM parsed_document WHERE capture_id=?",
                                    (capture_id,)).fetchone()
            if der is not None and der[0] == ORIGEM_LEGADO_CONFERIDO:
                conferida = interpretar_legado_padrao(body, cap.get("source_id"))
        text = conferida.texto if conferida is not None else texto_para_exibicao(body, ctype)
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
            **({} if ctype else {"proveniencia": {
                "interpretacao": ORIGEM_LEGADO_CONFERIDO if conferida is not None else ORIGEM_LEGADO}}),
        }

    def _capacidade_e_recorte(self, cid: str, coverage: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """Capacidade (acervo/ao_vivo/ambos/nenhuma) e recorte do acervo instalado da fonte (aditivo, experimental).

        Tribunal: decisões do acervo e período; demais fontes: capturas oficiais. `0` é acervo instalado vazio
        (medido), não desconhecido. `ao_vivo` de tribunal é a busca textual ao vivo; consulta pontual por número
        não entra nessa conta."""
        if cid in _JURIS_CONNECTORS:
            ac = self._acervo_do_tribunal(normalize_court(cid))
            n = ac["n"]
            recorte = {"decisoes": n, "desde": (ac["recorte"] or {}).get("desde"),
                       "ate": (ac["recorte"] or {}).get("ate"), "capturado_em": ac["capturado_em"]}
            vivo = bool(coverage.get("busca_textual_ao_vivo", coverage.get("busca_textual")))
        else:
            n, capturado = self.conn.execute(
                "SELECT COUNT(*), MAX(fetched_at) FROM capture WHERE source_id=?", (cid,)).fetchone()
            recorte = {"capturas": n, "capturado_em": capturado}
            vivo = cid not in {"planalto", "camara_legin"}  # legado / ativação pendente
        return ("ambos" if n and vivo else "acervo" if n else "ao_vivo" if vivo else "nenhuma"), recorte

    def obter_registro(
        self,
        run_id: str,
        evidencias: list[dict[str, Any]] | None = None,
        fundamento_temporal: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Registro local da operação de verificação (decisão 0075, 3.4)."""
        from freoa_verifica.registro import hmac_entrada as _hmac, legado_autenticado

        def hmac_entrada(conn, campo, valor, *, leitura=True):
            # C9: leitura da chave sem escrita; chave ilegível ou ausente não confere (nunca levanta).
            try:
                return _hmac(conn, campo, valor, leitura=leitura)
            except (RuntimeError, ValueError, TypeError, OSError):  # OSError: acesso negado, pasta no lugar, falha de leitura
                return None

        def invalido(run, motivo):
            return {
                "status": "encontrada",
                "run_id": run,
                "ferramenta": None,
                "criado_em": None,
                "politica": None,
                "parametros": None,
                "estado": None,
                "evidencias": None,
                "fundamento_temporal": None,
                "integridade": {"algoritmo": "hmac-sha256", "confere": False, "motivo": motivo},
                "confere_evidencias": None,
                "confere_fundamento": None,
            }

        if not run_id or not isinstance(run_id, str):
            return {"status": "inexistente", "run_id": run_id}

        try:
            row = self.conn.execute("SELECT * FROM run WHERE id=?", (run_id,)).fetchone()
        except sqlite3.OperationalError as exc:
            if "decode" not in str(exc).lower():  # texto que não é UTF-8 na linha: adulteração, não falha de acesso
                raise
            existe = self.conn.execute("SELECT 1 FROM run WHERE id=?", (run_id,)).fetchone()
            return invalido(run_id, "ESTRUTURA_INVALIDA") if existe else {"status": "inexistente", "run_id": run_id}
        if row is None:
            return {"status": "inexistente", "run_id": run_id}

        # Tipo SQLite e estrutura de TODAS as colunas lidas, antes de qualquer serialização ou acesso: o que não é
        # texto (ou nulo) ou é JSON inválido vira resposta controlada de integridade inválida, sem montar o documento do
        # MAC a partir de conteúdo não confiável.
        campos = _campos_do_registro(row)
        if campos is None:
            return invalido(run_id, "ESTRUTURA_INVALIDA")
        confere_mac: bool | None = None
        if row["registro_mac"] is None:
            # C8: `null` (legado) só para o que a âncora autenticada lista; novo sem MAC não confere.
            confere_mac = None if legado_autenticado(self.conn, row["id"]) else False
        else:
            doc_mac = {c: row[c] for c in _COLUNAS_DO_MAC}
            recalculado = hmac_entrada(self.conn, "registro", json.dumps(doc_mac, ensure_ascii=False, sort_keys=True))
            confere_mac = bool(recalculado is not None and hmac.compare_digest(
                row["registro_mac"].encode("utf-8"), recalculado.encode("utf-8")))

        if confere_mac is False:
            return invalido(row["id"], "MAC_NAO_CONFERE")
        res_json, req_json = campos["result"], campos["request"]

        if row["evidencias_claro"] is not None:
            politica = "completo"
        elif res_json.get("registro") == "sem_conteudo" or req_json.get("registro") == "sem_conteudo":
            politica = "sem_conteudo"
        else:
            politica = "completo"

        parametros = req_json

        estado = {
            d: {
                "status": (res_json.get(d) or {}).get("status"),
                "reason_code": (res_json.get(d) or {}).get("reason_code"),
            }
            for d in ("identity", "text", "temporal", "support")
        }

        if politica == "completo":
            evidencias_out = campos["evidencias_claro"]
            fundamento_out = campos["fundamento_claro"]
            if "fontes_consultadas" in res_json:
                estado["fontes_consultadas"] = res_json["fontes_consultadas"]
                estado["status"] = res_json.get("status")
                estado["motivo"] = res_json.get("motivo")
        else:
            evidencias_out = None
            fundamento_out = None

        confere_evidencias = None
        if evidencias is not None:
            compromissos = set(campos["compromissos"])
            confere_evidencias = []
            for e in evidencias:
                if not isinstance(e, dict) or not (e.get("capture_id") and e.get("sha256") and e.get("url")):
                    confere_evidencias.append({
                        "capture_id": e.get("capture_id") if isinstance(e, dict) else None,
                        "confere": False,
                    })
                    continue
                tup = {
                    "capture_id": e.get("capture_id"),
                    "sha256": e.get("sha256"),
                    "url": e.get("url"),
                }
                h = hmac_entrada(self.conn, "evidencia", json.dumps(tup, ensure_ascii=False, sort_keys=True))
                confere_evidencias.append({
                    "capture_id": e.get("capture_id"),
                    "confere": bool(h in compromissos),
                })

        confere_fundamento = None
        if fundamento_temporal is not None:
            ft_canon = json.dumps(fundamento_temporal, ensure_ascii=False, sort_keys=True)
            h_ft = hmac_entrada(self.conn, "fundamento_temporal", ft_canon)
            confere_fundamento = bool(row["fundamento_compromisso"] is not None and h_ft == row["fundamento_compromisso"])

        return {
            "status": "encontrada",
            "run_id": row["id"],
            "ferramenta": row["ferramenta"] or "verificar_citacao",
            "criado_em": row["created_at"],
            "politica": politica,
            "parametros": parametros,
            "estado": estado,
            "evidencias": evidencias_out,
            "fundamento_temporal": fundamento_out,
            "integridade": {
                "algoritmo": "hmac-sha256",
                "confere": confere_mac,
            },
            "confere_evidencias": confere_evidencias,
            "confere_fundamento": confere_fundamento,
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
            capacidade, recorte = self._capacidade_e_recorte(cid, coverage)
            fontes.append(
                {
                    "id": cid,
                    "autoridade": getattr(cls, "authority", cid),
                    "capacidade": capacidade,
                    "recorte_acervo": recorte,
                    "tipos_documento": _tipos_documento(coverage),
                    "cobertura": coverage,
                    "ultimo_health": last,
                    "circuito": circuit,
                }
            )
        return {
            "fontes": fontes,
            "total": len(fontes),
            "contrato": CONTRATO_VERSAO,
            "qualificacao": self._carregar_qualificacao(),
            "avisos_incidente": self._carregar_avisos_incidente(),
        }

    def _carregar_qualificacao(self) -> list[dict[str, Any]]:
        try:
            from importlib.resources import files
            raw = files("freoa_verifica").joinpath("data/qualificacao.json").read_text(encoding="utf-8")
            return json.loads(raw)
        except (OSError, ValueError, TypeError):
            _log.warning("falha ao carregar qualificacao.json", exc_info=True)
            return []

    def _carregar_avisos_incidente(self) -> list[dict[str, Any]]:
        avisos: list[dict[str, Any]] = []
        try:
            from importlib.resources import files
            raw = files("freoa_verifica").joinpath("data/avisos_incidente.json").read_text(encoding="utf-8")
            avisos.extend(json.loads(raw))
        except (OSError, ValueError, TypeError):
            _log.warning("falha ao carregar avisos_incidente.json do pacote", exc_info=True)

        if self.home:
            home_avisos_path = Path(self.home) / "avisos_incidente.json"
            if home_avisos_path.is_file():
                try:
                    conteudo = json.loads(home_avisos_path.read_text(encoding="utf-8"))
                    if isinstance(conteudo, list):
                        for item in conteudo:
                            if self._validar_aviso_incidente(item):
                                avisos.append(item)
                            else:
                                _log.warning("aviso de incidente invalido descartado: %r", item)
                    else:
                        _log.warning("<home>/avisos_incidente.json deve ser uma lista JSON")
                except (OSError, ValueError, TypeError):
                    _log.warning("falha ao ler <home>/avisos_incidente.json", exc_info=True)
        return avisos

    @staticmethod
    def _validar_aviso_incidente(item: Any) -> bool:
        if not isinstance(item, dict):
            return False
        if not isinstance(item.get("id"), str) or not item["id"]:
            return False
        if not isinstance(item.get("data"), str) or not item["data"]:
            return False
        if not isinstance(item.get("versoes_afetadas"), list) or not all(
            isinstance(v, str) for v in item["versoes_afetadas"]
        ):
            return False
        if item.get("acao") not in ("retirada", "correcao"):
            return False
        if not isinstance(item.get("descricao"), str):
            return False
        if not isinstance(item.get("referencia"), str):
            return False
        return True

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
                exigir_nova_captura(cid)
                conn_obj = self._get(cid)
                if hasattr(conn_obj, "sync"):
                    kwargs: dict[str, Any] = {}
                    if desde and cid == "stj":
                        kwargs["desde"] = desde
                    if max_itens is not None and cid == "tcu":
                        kwargs["quantidade"] = min(100, max_itens)
                        kwargs["max_pages"] = max(1, (max_itens + 99) // 100)
                    result = conn_obj.sync(**kwargs)
                    # Com estado de sincronização (semente anterior na mesma instância), a falha por recurso fica
                    # em last_failures: a fonte não é declarada "ok" por silêncio (FIX17/F-23).
                    falhas = list(getattr(conn_obj, "last_failures", None) or [])
                    relatorio.append({"fonte": cid, "status": "parcial" if falhas else "ok",
                                      "resultado": str(result)[:200],
                                      **({"falhas": [{"chave": k, "motivo": m} for k, m in falhas[:20]]}
                                         if falhas else {})})
                else:
                    # busca índice leve
                    cands = conn_obj.search(desde or "lei",)
                    relatorio.append(
                        {"fonte": cid, "status": "ok", "candidatos": len(cands)}
                    )
            except Unavailable as exc:
                relatorio.append({"fonte": cid, "status": "indisponivel", "motivo": exc.reason,
                                  **exc.classificacao()})
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
                # Uma guarda por fonte: as sondas dela compartilham o bloqueio após desafio/recusa (FIX16/F-17).
                with GuardaExecucao().ativar():
                    exigir_nova_captura(cid)
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
                    {"nome": f"fonte:{cid}", "status": "falha", "detalhe": str(exc)[:200],
                     **(exc.classificacao() if isinstance(exc, Unavailable) else {})}
                )
        provenance = _acervo.installed_provenance(self.home)
        checks.append({"nome": "snapshot_proveniencia",
                       "status": "ok" if provenance.get("vinculado") else "alerta",
                       "detalhe": provenance})
        checks.append(_acervo.verificar_digest_instalado(provenance))
        checks.append(_acervo.attestation_instalacao(provenance))
        aviso = self.acervo_status()
        checks.append({"nome": "acervo", "status": "alerta" if aviso else "ok",
                       "detalhe": aviso or "atende ao manifesto/mínimo"})
        ok = all(c["status"] in {"ok", "alerta"} for c in checks)
        from freoa_verifica.connectors.stj import resumo_atualizacao

        stj_atual = resumo_atualizacao(self.conn)
        return {"status": "ok" if ok else "falha", "verificacoes": checks,
                **({"acervo_incompleto": aviso} if aviso else {}),
                **({"stj_atualizacao": stj_atual} if stj_atual else {})}

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

    def purgar_execucoes(self, antes: str, apagar_original: bool = False) -> dict[str, Any]:
        """Reconstrói o banco sem as execuções anteriores a `antes` (AAAA-MM-DD)."""
        from freoa_verifica import registro as reg

        if self._read_only:
            return {"status": "erro", "motivo": "somente_leitura"}
        try:
            with self.exclusivo_home():
                self._close_all_conns(strict=True)
                try:
                    return reg.purgar(self.home, antes, apagar_original)
                finally:
                    self._clear_caches()
        except (ValueError, TimeoutError, RuntimeError, OSError) as exc:
            return {"status": "erro", "motivo": str(exc)[:200]}

    def snapshot_install(
        self,
        origem: str | Path | None = None,
        *,
        url: str | None = None,
        aceitar_nao_vinculado: bool = False,
    ) -> dict[str, Any]:
        from freoa_verifica import snapshot as snap

        return snap.install_snapshot(self, origem, url=url, aceitar_nao_vinculado=aceitar_nao_vinculado)

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
    "obter_evidencia", "obter_registro", "listar_fontes", "doctor", "sincronizar", "bench", "snapshot_export",
    "snapshot_info", "indexar_obra", "reparar_anos", "reprocessar_capturas",
    "restaurar_identidades_validadas", "reparar_identidades",
})


def _json_tipado(valor: Any, tipo: type | tuple, vazio: Any) -> tuple[bool, Any]:
    """(ok, valor) de uma coluna JSON persistida: ausente/vazia vale `vazio`; inválida ou de outro tipo, não ok."""
    if valor is None or valor == "":
        return True, vazio
    try:
        lido = json.loads(valor)
    except (ValueError, TypeError, RecursionError):
        return False, None
    return (True, lido) if isinstance(lido, tipo) else (False, None)


_COLUNAS_DO_MAC = ("id", "ferramenta", "created_at", "request_hash", "request_json", "result_json",
                   "evidencias_compromissos", "fundamento_compromisso", "evidencias_claro", "fundamento_claro")
_COLUNAS_DO_REGISTRO = _COLUNAS_DO_MAC + ("registro_mac",)
_OBRIGATORIAS_DO_REGISTRO = ("id", "created_at", "request_hash", "request_json")


def _campos_do_registro(row) -> dict[str, Any] | None:
    """Estrutura validada das colunas de `run` lidas pela conferência; `None` se qualquer uma tem tipo SQLite
    inesperado (BLOB, inteiro, real), falta, ou carrega JSON inválido ou malformado."""
    for coluna in _COLUNAS_DO_REGISTRO:
        valor = row[coluna]
        if valor is None and coluna in _OBRIGATORIAS_DO_REGISTRO:
            return None
        if valor is not None and not isinstance(valor, str):
            return None
    ok_res, res = _json_tipado(row["result_json"], dict, {})
    ok_req, req = _json_tipado(row["request_json"], dict, {})
    ok_ev, ev = _json_tipado(row["evidencias_claro"], list, [])
    ok_ft, ft = _json_tipado(row["fundamento_claro"], dict, None)
    ok_co, co = _json_tipado(row["evidencias_compromissos"], list, [])
    if not (ok_res and ok_req and ok_ev and ok_ft and ok_co):
        return None
    if not all(isinstance(e, dict) for e in ev) or not all(isinstance(c, str) for c in co):
        return None
    if any(res.get(d) is not None and not isinstance(res[d], dict) for d in ("identity", "text", "temporal", "support")):
        return None
    return {"result": res, "request": req, "evidencias_claro": ev,
            "fundamento_claro": ft, "compromissos": co}


_COM_ADITIVOS = frozenset({"obter_dispositivo", "verificar_citacao"})
_COM_RECIBO = frozenset({"verificar_citacao", "verificar_texto", "obter_dispositivo"})


def _recibo_da_obtencao(self, out, entrada):
    """Recibo da seleção efetivamente emitida, depois da autenticação e dos decoradores."""
    _final_da_fachada("obter_dispositivo", out, entrada.get("versao", "vigente"))
    if self._read_only:
        out.update(run_id=None, registro={"gravado": False, "motivo": "somente_leitura"})
        return out
    vig = out.get("vigencia") or {}
    identity = {"status": "unknown", "reason_code": "OBTENCAO_SEM_CONFRONTO", "evidence": []}
    if out.get("status") in {"indisponivel", "unavailable"}:
        identity = {"status": "unavailable", "reason_code": out.get("reason_code", out.get("motivo"))}
    recibo = {**out,
        "identity": identity,
        "text": {"status": "not_assessed", "reason_code": "OBTENCAO_SEM_CONFRONTO", "evidence": []},
        "temporal": {"status": vig.get("status", "unknown"), "reason_code": vig.get("reason_code", out.get("motivo")), "evidence": []},
        "support": {"status": "not_assessed", "reason_code": "SUPPORT_NOT_ASSESSED", "evidence": []}}
    out["run_id"] = persistir_resultado(self.conn, entrada.get("citacao"), None, entrada.get("data"), "literal", recibo,
        ferramenta="obter_dispositivo", parametros={k: entrada.get(k, "vigente" if k == "versao" else None)
                                                   for k in ("work_id", "caminho", "versao", "fonte")})
    return out


def _final_da_fachada(nome: str, out: Any, versao="vigente") -> Any:
    """Último ponto antes da emissão de toda operação da fachada (Python, MCP e REST): campos aditivos de C4 em todo
    estado de `obter_dispositivo` e `verificar_citacao` (inclusive `formato_invalido`, `indisponivel`, `unknown` e a
    recusa pelos derivados)."""
    if isinstance(out, dict) and nome in _COM_ADITIVOS:
        _normalizar_aditivos(out)
        if nome == "obter_dispositivo":
            out.setdefault("versao", versao)
    return out


def _recibo_da_recusa(self, nome: str, out: dict[str, Any], entrada: dict[str, Any]) -> dict[str, Any]:
    """C11: a recusa por derivados incompatíveis é conclusão de verificação (`indisponivel/ACERVO_DESATUALIZADO`).
    Em serviço gravável grava o recibo, com a política de minimização vigente, e devolve o `run_id`; em somente leitura
    declara o modo, como o restante da finalização. Independe da compatibilidade dos derivados (só toca `run`)."""
    if nome not in _COM_RECIBO or not isinstance(out, dict):
        return out
    if nome == "obter_dispositivo":
        return _recibo_da_obtencao(self, out, entrada)
    if self._read_only:
        out.update(run_id=None, registro={"gravado": False, "motivo": "somente_leitura"})
        return out
    indisponivel = {"status": "unavailable", "reason_code": out.get("reason_code")}
    recibo = {**{k: v for k, v in out.items() if k != "acervo_incompleto"},
              "identity": dict(indisponivel), "text": {"status": "not_assessed", "reason_code": out.get("reason_code")},
              "temporal": {"status": "unknown", "reason_code": out.get("reason_code")},
              "support": {"status": "not_assessed", "reason_code": "SUPPORT_NOT_ASSESSED"}}
    texto = nome == "verificar_texto"
    out["run_id"] = persistir_resultado(
        self.conn, entrada["texto" if texto else "citacao"], None if texto else entrada.get("trecho"),
        entrada.get("data"), "literal" if texto else entrada.get("modo", "literal"), recibo, ferramenta=nome)
    return out


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
            # Guarda da chamada (FIX17/F-23): toda operação pública, inclusive as que a CLI, o MCP e o REST expõem,
            # tem identidade efetiva e bloqueio por host; aninhadas compartilham a da chamada externa.
            with self._operacao(caro), da_chamada():
                if fn.__name__ in _DEPENDENTES and not _derivados.compativel(self.conn):
                    recusa = _derivados.indisponivel(self.acervo_status())
                    return _final_da_fachada(fn.__name__, _recibo_da_recusa(self, fn.__name__, recusa, entrada), entrada.get("versao", "vigente"))
                try:
                    resposta = fn(self, *args, **kwargs)
                except SourceAmbiguous as exc:
                    resposta = {"status": "ambigua", "candidatos": exc.candidates,
                                "motivo": "IDENTIDADE_AMBIGUA"}
                    if fn.__name__ == "verificar_citacao":
                        texto = entrada.get("citacao", "")
                        cite = parse_one(texto)
                        resposta = self._finalizar({
                            "identity": {"status": "ambiguous", "reason_code": "IDENTIDADE_AMBIGUA", "evidence": []},
                            "text": {"status": "not_assessed", "reason_code": "IDENTIDADE_AMBIGUA", "evidence": []},
                            "temporal": {"status": "unknown", "reason_code": "IDENTIDADE_AMBIGUA", "evidence": []},
                            "support": {"status": "not_assessed", "reason_code": "SUPPORT_NOT_ASSESSED", "evidence": []},
                            "candidatos": exc.candidates, "citation": _citation_to_dict(cite), "run_id": None,
                        }, cite, texto, entrada.get("trecho"), entrada.get("data"), entrada.get("modo", "literal"))
                out = _final_da_fachada(fn.__name__, resposta, entrada.get("versao", "vigente"))
                if externa and self.exigir_acervo and isinstance(out, dict):
                    aviso = self.acervo_status()
                    if aviso:
                        out["acervo_incompleto"] = aviso
                if fn.__name__ == "obter_dispositivo" and isinstance(out, dict):
                    _recibo_da_obtencao(self, out, entrada)
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

# Fora da fachada contada, mas podem chegar à rede: só a guarda da chamada (FIX17/F-23).
for _nome in ("ressincronizar_situacao", "reconstruir_acervo", "snapshot_install"):
    setattr(Verifica, _nome, sob_guarda(getattr(Verifica, _nome)))
