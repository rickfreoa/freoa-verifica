"""Verificação de citação: identidade, texto, tempo e suporte."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from freoa_verifica.citation import Citation, extract, parse_one
from freoa_verifica.ids import new_ulid
from freoa_verifica.limites import cancelado
from freoa_verifica.parsers.model import (
    AmbiguousProvision,
    ParsedDocument,
    PROVISION_BLOCKING_CODES,
    Provision,
    RevokedProvision,
)
from freoa_verifica.store import repo as store_repo
from freoa_verifica.temporal import select as temporal_select
from freoa_verifica.textcmp import ALGO_VERSION as TEXTCMP_VERSION
from freoa_verifica.textcmp import compare
from freoa_verifica.aliases import WorkKey

POLICY_VERSION = "verify-r5-1"
ALGO_VERSIONS = {
    "textcmp": TEXTCMP_VERSION,
    "verify": POLICY_VERSION,
    "citation": "citation-3",
    "temporal": "temporal-1",
}

_MAX_TRECHO = 1500


@dataclass
class Evidence:
    capture_id: str | None = None
    sha256: str | None = None
    url: str | None = None
    fetched_at: str | None = None
    path: str | None = None
    span: tuple[int, int] | None = None
    trecho_oficial: str | None = None


@dataclass
class Dimension:
    status: str  # verified|vigente_na_fonte|divergent|not_found|unavailable|unknown|not_assessed|ambiguous
    reason_code: str | None = None
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class VerificationResult:
    identity: Dimension
    text: Dimension
    temporal: Dimension
    support: Dimension
    algo_versions: dict[str, str] = field(default_factory=lambda: dict(ALGO_VERSIONS))
    citation: Citation | None = None
    run_id: str | None = None


@dataclass
class ResolvedWork:
    """Obra capturada e parseada, pronta para verificação."""

    work_id: str
    work_key: WorkKey
    document: ParsedDocument
    work_date: str | None
    capture_id: str | None
    sha256: str | None
    url: str | None
    fetched_at: str | None
    quarantined: bool
    amending_act_texts: dict[str, str] = field(default_factory=dict)
    persisted_incomplete: bool = False


class Resolver(Protocol):
    """Interface M4: garante obra capturada e parseada."""

    def resolve(self, work: WorkKey) -> ResolvedWork | list[ResolvedWork] | None:
        """None = not_found; lista >1 = ambiguous; Unavailable via exceção tipada."""
        ...


class SourceUnavailable(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass
class MemoryResolver:
    """Resolver M3: mapa WorkKey → ResolvedWork (fixtures pré-carregadas)."""

    works: dict[tuple[str, str, str, int], ResolvedWork] = field(default_factory=dict)

    def add(self, rw: ResolvedWork) -> None:
        k = (rw.work_key.authority, rw.work_key.kind, rw.work_key.number, rw.work_key.year)
        self.works[k] = rw

    def resolve(self, work: WorkKey) -> ResolvedWork | list[ResolvedWork] | None:
        k = (work.authority, work.kind, work.number, work.year)
        hit = self.works.get(k)
        if hit:
            return hit
        # Ano 0 / desconhecido: buscar por authority+kind+number
        if work.year == 0:
            matches = [
                rw
                for (a, ki, n, y), rw in self.works.items()
                if a == work.authority and ki == work.kind and n == work.number
            ]
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                return matches
        # Número sem pontos alternativo
        matches = [
            rw
            for (a, ki, n, y), rw in self.works.items()
            if a == work.authority
            and ki == work.kind
            and n == work.number
            and (work.year == 0 or y == work.year)
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return matches
        return None


def _ev_from_resolved(rw: ResolvedWork, path: str | None, trecho: str | None, span=None) -> Evidence:
    t = trecho
    if t and len(t) > _MAX_TRECHO:
        t = t[:_MAX_TRECHO]
    return Evidence(
        capture_id=rw.capture_id,
        sha256=rw.sha256,
        url=rw.url,
        fetched_at=rw.fetched_at,
        path=path,
        span=span,
        trecho_oficial=t,
    )


_INCOMPLETE_CODES = frozenset({"TRUNCATED", "EXTRACAO_INCOMPLETA"})


def _scope_of(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else ""


def pode_negar(rw: ResolvedWork | None, path: str) -> str | None:
    """C1 (decisão 0023): None autoriza DISPOSITIVO_INEXISTENTE; senão, o motivo que o impede."""
    if rw is None or not rw.capture_id:
        return "COBERTURA"
    scope = _scope_of(path)
    doc = rw.document
    if any(i.code in _INCOMPLETE_CODES and (i.path is None or _scope_of(i.path) == scope)
           for i in doc.issues):
        return "ESTRUTURA_INCOMPLETA"
    if rw.quarantined:
        return "DOCUMENTO_QUARENTENADO"
    if not any(_scope_of(p.path) == scope for p in doc.provisions):
        return "DOCUMENTO_SEM_ESTRUTURA"
    return None


def negativa_dimension(rw: ResolvedWork | None, path: str) -> Dimension:
    """Identidade de dispositivo ausente: not_found só se pode_negar autoriza."""
    motivo = pode_negar(rw, path)
    ev = [_ev_from_resolved(rw, path, None)] if rw is not None else []
    if motivo is None:
        return Dimension("not_found", "DISPOSITIVO_INEXISTENTE", ev)
    return Dimension("unavailable" if motivo == "COBERTURA" else "unknown", motivo, ev)


def _find_provision(doc: ParsedDocument, path: str) -> Provision | None:
    prov = doc.provision(path)
    if prov:
        return prov
    # tenta sem caput explícito
    if path.endswith(".caput"):
        return doc.provision(path[: -len(".caput")])
    return None


def _redaction_by_id(prov: Provision, redaction_id: str | None):
    if redaction_id is None:
        return None
    for r in prov.redactions:
        if f"r{r.order}" == redaction_id:
            return r
    # índice
    if redaction_id.startswith("r"):
        try:
            order = int(redaction_id[1:])
            for r in prov.redactions:
                if r.order == order:
                    return r
        except ValueError:
            pass
    return None


def _current_redaction(prov: Provision):
    for r in reversed(sorted(prov.redactions, key=lambda x: x.order)):
        if r.struck or r.superseded_without_strike:
            continue
        return r
    return prov.redactions[-1] if prov.redactions else None


def _provision_blocking_issues(doc: ParsedDocument, path: str | None) -> list:
    if not path:
        return []
    return [
        i
        for i in doc.issues
        if i.path and (i.path == path or path.startswith(i.path + ".") or path.startswith(i.path + "/"))
        and (
            i.blocking_scope == "provision"
            or i.code in PROVISION_BLOCKING_CODES
        )
    ]


def _search_text_in_work(
    doc: ParsedDocument, trecho: str, mode: str, exclude_path: str | None
) -> tuple[str, str] | None:
    """Se trecho casa em outro dispositivo, devolve (path, redacao_tag)."""
    for prov in doc.provisions:
        if exclude_path and prov.path == exclude_path:
            continue
        for r in prov.redactions:
            cmp = compare(trecho, r.text, mode, exact_only=True)
            if cmp.status == "match":
                tag = "struck" if r.struck else "current"
                return prov.path, tag
    return None


def verificar(
    citacao: str,
    trecho: str | None = None,
    data: str | None = None,
    modo: str = "literal",
    repo: sqlite3.Connection | None = None,
    resolver: Resolver | None = None,
    *,
    _path: str | None = None,
    persistir: bool = True,
) -> VerificationResult:
    """Verifica citação nas dimensões identity/text/temporal/support.

    `persistir=False` (fachada) devolve sem gravar recibo: quem finaliza grava (C4).
    """
    if resolver is None:
        raise ValueError("resolver é obrigatório")
    if not persistir:
        repo = None

    cite = parse_one(citacao)
    if _path is not None:
        cite = next((c for c in extract(citacao) if c.path == _path), None)
    if cite is None:
        # tenta extract e pega norma
        cites = extract(citacao)
        if _path is None:
            cite = next((c for c in cites if c.kind == "norma"), cites[0] if cites else None)

    support = Dimension(status="not_assessed", reason_code="SUPPORT_NOT_IN_M3")

    if cite is None or cite.work is None:
        result = VerificationResult(
            identity=Dimension("not_found", "CITACAO_NAO_RECONHECIDA"),
            text=Dimension("not_assessed", "SEM_IDENTIDADE"),
            temporal=Dimension("not_assessed", "SEM_IDENTIDADE"),
            support=support,
            citation=cite,
        )
        return _persist(repo, citacao, trecho, data, modo, result)

    if "dispositivo_invalido" in cite.flags:
        return _persist(repo, citacao, trecho, data, modo, VerificationResult(
            identity=Dimension("not_found", "formato_invalido"),
            text=Dimension("not_assessed", "SEM_DISPOSITIVO"),
            temporal=Dimension("not_assessed", "SEM_DISPOSITIVO"), support=support, citation=cite))

    # Resolver obra
    try:
        resolved = resolver.resolve(cite.work)
    except SourceUnavailable as exc:
        result = VerificationResult(
            identity=Dimension("unavailable", exc.reason),
            text=Dimension("not_assessed", "FONTE_INDISPONIVEL"),
            temporal=Dimension("not_assessed", "FONTE_INDISPONIVEL"),
            support=support,
            citation=cite,
        )
        return _persist(repo, citacao, trecho, data, modo, result)

    if resolved is None:
        result = VerificationResult(
            identity=Dimension("not_found", "OBRA_NAO_ENCONTRADA"),
            text=Dimension("not_assessed", "SEM_OBRA"),
            temporal=Dimension("not_assessed", "SEM_OBRA"),
            support=support,
            citation=cite,
        )
        return _persist(repo, citacao, trecho, data, modo, result)

    if isinstance(resolved, list):
        if len(resolved) == 0:
            result = VerificationResult(
                identity=Dimension("not_found", "OBRA_NAO_ENCONTRADA"),
                text=Dimension("not_assessed", "SEM_OBRA"),
                temporal=Dimension("not_assessed", "SEM_OBRA"),
                support=support,
                citation=cite,
            )
            return _persist(repo, citacao, trecho, data, modo, result)
        if len(resolved) > 1:
            result = VerificationResult(
                identity=Dimension("ambiguous", "MULTIPLAS_OBRAS"),
                text=Dimension("not_assessed", "AMBIGUO"),
                temporal=Dimension("not_assessed", "AMBIGUO"),
                support=support,
                citation=cite,
            )
            return _persist(repo, citacao, trecho, data, modo, result)
        resolved = resolved[0]

    rw: ResolvedWork = resolved
    from freoa_verifica.identity import IdentityMismatch, validate_identity, requested_date
    try:
        declared = validate_identity(cite.work, rw.document, requested_date(cite.raw))
        if declared is None and rw.document.profile in {"planalto","cvm_docx","cvm_pdf","cvm_html","bcb_json","senado_norma"}:
            return _persist(repo,citacao,trecho,data,modo,VerificationResult(
                identity=Dimension("unknown","IDENTIDADE_NAO_DECLARADA"),
                text=Dimension("not_assessed","IDENTIDADE_NAO_DECLARADA"),
                temporal=Dimension("not_assessed","IDENTIDADE_NAO_DECLARADA"),
                support=support,citation=cite))
    except IdentityMismatch:
        return _persist(repo, citacao, trecho, data, modo, VerificationResult(
            identity=Dimension('not_found','IDENTIDADE_DIVERGENTE'),
            text=Dimension('not_assessed','IDENTIDADE_DIVERGENTE'),
            temporal=Dimension('not_assessed','IDENTIDADE_DIVERGENTE'),
            support=support,citation=cite))
    if rw.persisted_incomplete:
        return _persist(repo, citacao, trecho, data, modo, VerificationResult(
            identity=Dimension("unknown", "DADOS_PERSISTIDOS_INCOMPLETOS"),
            text=Dimension("unknown", "DADOS_PERSISTIDOS_INCOMPLETOS"),
            temporal=Dimension("unknown", "DADOS_PERSISTIDOS_INCOMPLETOS"),
            support=support, citation=cite,
        ))
    path = cite.path
    prov = _find_provision(rw.document, path) if path else None
    blocking = _provision_blocking_issues(rw.document, path)

    # Bloqueios documentais/por dispositivo ANTES de seleção/comparação
    if rw.quarantined:
        # C1: documento quarentenado nunca nega outro dispositivo; motivo vem de pode_negar.
        motivo = (pode_negar(rw, path) if path and prov is None else None) or "DOCUMENTO_QUARENTENADO"
        identity = Dimension("unknown", motivo, [_ev_from_resolved(rw, path, None)])
        result = VerificationResult(
            identity=identity,
            text=Dimension(
                "unknown",
                motivo,
                [_ev_from_resolved(rw, path, None)],
            )
            if trecho is not None
            else Dimension("not_assessed", "SEM_TRECHO"),
            temporal=Dimension("unknown", motivo),
            support=support,
            citation=cite,
        )
        return _persist(repo, citacao, trecho, data, modo, result)

    if prov is not None and prov.ambiguous:
        identity = Dimension(
            "ambiguous",
            "DISPOSITIVO_AMBIGUO",
            [_ev_from_resolved(rw, path, None)],
        )
        result = VerificationResult(
            identity=identity,
            text=Dimension("unknown", "DISPOSITIVO_AMBIGUO")
            if trecho is not None
            else Dimension("not_assessed", "SEM_TRECHO"),
            temporal=Dimension("ambiguous", "DISPOSITIVO_AMBIGUO"),
            support=support,
            citation=cite,
        )
        return _persist(repo, citacao, trecho, data, modo, result)

    if prov is not None:
        try:
            prov.current_redaction()
        except AmbiguousProvision:
            identity = Dimension(
                "ambiguous",
                "DISPOSITIVO_AMBIGUO",
                [_ev_from_resolved(rw, path, None)],
            )
            result = VerificationResult(
                identity=identity,
                text=Dimension("unknown", "DISPOSITIVO_AMBIGUO")
                if trecho is not None
                else Dimension("not_assessed", "SEM_TRECHO"),
                temporal=Dimension("ambiguous", "DISPOSITIVO_AMBIGUO"),
                support=support,
                citation=cite,
            )
            return _persist(repo, citacao, trecho, data, modo, result)
        except RevokedProvision:
            identity = Dimension(
                "unknown",
                "DISPOSITIVO_REVOGADO",
                [_ev_from_resolved(rw, path, None)],
            )
            # temporal ainda avalia revogado; text nunca verified
            temporal_res = temporal_select(
                prov,
                data,
                work_date=rw.work_date,
                amending_act_texts=rw.amending_act_texts,
                fetched_at=rw.fetched_at,
            )
            temporal_dim = _map_temporal(temporal_res, rw, path)
            text_dim = (
                Dimension("unknown", "DISPOSITIVO_REVOGADO")
                if trecho is not None
                else Dimension("not_assessed", "SEM_TRECHO")
            )
            result = VerificationResult(
                identity=identity,
                text=text_dim,
                temporal=temporal_dim,
                support=support,
                citation=cite,
            )
            return _persist(repo, citacao, trecho, data, modo, result)

    # --- identity ---
    if path is None:
        identity = Dimension(
            "verified",
            "OBRA_OK_SEM_CAMINHO",
            [_ev_from_resolved(rw, None, None)],
        )
    elif prov is None:
        identity = negativa_dimension(rw, path)
    else:
        identity = Dimension(
            "verified",
            "OBRA_E_CAMINHO_OK",
            [_ev_from_resolved(rw, path, None)],
        )

    # --- temporal ---
    if prov is None:
        temporal_dim = Dimension("not_assessed", "SEM_DISPOSITIVO")
        temporal_res = None
    else:
        temporal_res = temporal_select(
            prov,
            data,
            work_date=rw.work_date,
            amending_act_texts=rw.amending_act_texts,
            fetched_at=rw.fetched_at,
        )
        temporal_dim = _map_temporal(temporal_res, rw, path)

    # --- text ---
    uncertain = any(i.code == "UNCERTAIN_CONTINUATION" for i in blocking)
    if trecho is None:
        text_dim = Dimension("not_assessed", "SEM_TRECHO")
    elif prov is None:
        text_dim = (Dimension("not_found", "SEM_DISPOSITIVO") if identity.status == "not_found"
                    else Dimension("unknown", identity.reason_code))
    elif temporal_res and temporal_res.status in ("revogado", "nao_existia", "ambiguous"):
        text_dim = Dimension("unknown", temporal_res.reason or temporal_res.status.upper())
    elif temporal_res and temporal_res.reason in {"INICIO_SUCESSOR_DESCONHECIDO", "CAPTURA_DATA_INVALIDA"}:
        text_dim = Dimension("unknown", temporal_res.reason)
    elif (temporal_res and not temporal_res.redaction_id
          and temporal_res.status not in ("verified", "vigente_na_fonte")):
        # C3: sem redação selecionada para a data pedida, não confrontar a atual.
        text_dim = Dimension("unknown", temporal_res.reason or "HISTORICO_ANTERIOR_AUSENTE")
    else:
        if temporal_res and temporal_res.redaction_id:
            red = _redaction_by_id(prov, temporal_res.redaction_id)
        else:
            red = _current_redaction(prov)
        if red is None:
            text_dim = Dimension("not_found", "SEM_REDACAO")
        elif red.superseded_without_strike and (
            temporal_res is None or temporal_res.status not in {"verified", "vigente_na_fonte"}
        ):
            # Não afirmar texto sobre redação superada sem rasura fora de verified
            text_dim = Dimension(
                "unknown",
                "REDACAO_SUPERADA",
                [_ev_from_resolved(rw, path, red.text)],
            )
        else:
            cmp = compare(trecho, red.text, modo)
            ev = _ev_from_resolved(
                rw,
                path,
                red.text,
                span=(cmp.start, cmp.end) if cmp.start is not None else None,
            )
            if cmp.status == "match":
                if uncertain:
                    text_dim = Dimension("unknown", "UNCERTAIN_CONTINUATION", [ev])
                else:
                    text_dim = Dimension("verified", "TEXTO_OK", [ev])
            elif cmp.status == "partial":
                text_dim = Dimension(
                    "divergent",
                    "TEXTO_PARCIAL",
                    [ev],
                )
                text_dim.evidence[0].trecho_oficial = red.text[:_MAX_TRECHO]
                text_dim.reason_code = "TEXTO_PARCIAL"
            else:
                other_hit = None
                for r2 in prov.redactions:
                    if r2 is red:
                        continue
                    c2 = compare(trecho, r2.text, modo, exact_only=True)
                    if c2.status == "match":
                        other_hit = r2
                        break
                if other_hit is not None:
                    text_dim = Dimension(
                        "divergent",
                        "TRECHO_DE_OUTRA_REDACAO",
                        [
                            ev,
                            _ev_from_resolved(
                                rw,
                                path,
                                other_hit.text,
                            ),
                        ],
                    )
                else:
                    elsewhere = _search_text_in_work(rw.document, trecho, modo, path)
                    if elsewhere:
                        text_dim = Dimension(
                            "divergent",
                            "TRECHO_EM_OUTRO_DISPOSITIVO",
                            [
                                ev,
                                _ev_from_resolved(rw, elsewhere[0], None),
                            ],
                        )
                    else:
                        text_dim = Dimension("divergent", "TEXTO_DIVERGENTE", [ev])

    result = VerificationResult(
        identity=identity,
        text=text_dim,
        temporal=temporal_dim,
        support=support,
        citation=cite,
    )
    return _persist(repo, citacao, trecho, data, modo, result)


def _map_temporal(temporal_res, rw: ResolvedWork, path: str | None) -> Dimension:
    ev = [_ev_from_resolved(rw, path, None)]
    reason = temporal_res.reason or (
        ",".join(temporal_res.rules_applied) if temporal_res.rules_applied else None
    )
    if temporal_res.status == "verified":
        return Dimension("verified", reason, ev)
    if temporal_res.status == "vigente_na_fonte":
        return Dimension("vigente_na_fonte", reason or "VIGENTE_NA_FONTE", ev)
    if temporal_res.status == "revogado":
        return Dimension("divergent", "REVOGADO", ev)
    if temporal_res.status == "nao_existia":
        return Dimension("not_found", "NAO_EXISTIA", ev)
    if temporal_res.status == "ambiguous":
        return Dimension("ambiguous", reason or "AMBIGUO", ev)
    return Dimension("unknown", reason or "UNKNOWN", ev)


def _result_to_json(result: VerificationResult) -> dict[str, Any]:
    def dim(d: Dimension) -> dict:
        return {
            "status": d.status,
            "reason_code": d.reason_code,
            "evidence": [{**asdict(e), "span": list(e.span) if e.span is not None else None}
                         for e in d.evidence],
        }

    out: dict[str, Any] = {
        "identity": dim(result.identity),
        "text": dim(result.text),
        "temporal": dim(result.temporal),
        "support": dim(result.support),
        "algo_versions": result.algo_versions,
    }
    if result.citation is not None:
        c = result.citation
        out["citation"] = {
            "kind": c.kind,
            "raw": c.raw,
            "span": list(c.span),
            "path": c.path,
            "confidence": c.confidence,
            "flags": c.flags,
            "work": asdict(c.work) if c.work else None,
            "decision": asdict(c.decision) if c.decision else None,
        }
    return out


def _persist(
    conn: sqlite3.Connection | None,
    citacao: str,
    trecho: str | None,
    data: str | None,
    modo: str,
    result: VerificationResult,
) -> VerificationResult:
    if conn is not None:
        result.run_id = persistir_resultado(conn, citacao, trecho, data, modo, _result_to_json(result))
    return result


def persistir_resultado(conn, citacao, trecho, data, modo, resultado: dict[str, Any]) -> str:
    """Grava o recibo (C4): chamado só depois da finalização, com a conclusão devolvida.

    Política `sem_conteudo` (C5): só hashes, política e dimensões; sem citação, trecho nem evidência.
    """
    from freoa_verifica.registro import politica_atual

    request = {"citacao": citacao, "trecho": trecho, "data": data, "modo": modo}
    request_json = json.dumps(request, ensure_ascii=False, sort_keys=True)
    request_hash = hashlib.sha256(request_json.encode("utf-8")).hexdigest()
    if politica_atual.get() == "sem_conteudo":
        h = lambda v: None if v is None else hashlib.sha256(str(v).encode("utf-8")).hexdigest()  # noqa: E731
        request_json = json.dumps(
            {"registro": "sem_conteudo", **{f"{k}_sha256": h(v) for k, v in request.items()}},
            sort_keys=True,
        )
        result_json = json.dumps(
            {
                "registro": "sem_conteudo",
                **{d: {"status": (resultado.get(d) or {}).get("status"),
                       "reason_code": (resultado.get(d) or {}).get("reason_code")}
                   for d in ("identity", "text", "temporal", "support")},
                "algo_versions": resultado.get("algo_versions"),
            },
            ensure_ascii=False, sort_keys=True,
        )
    else:
        result_json = json.dumps(resultado, ensure_ascii=False, sort_keys=True)
    run_id = new_ulid()
    conn.execute(
        "INSERT INTO run(id, request_hash, request_json, policy_version, result_json) "
        "VALUES (?,?,?,?,?)",
        (run_id, request_hash, request_json, POLICY_VERSION, result_json),
    )
    conn.commit()
    return run_id


def populate_from_parsed(
    conn: sqlite3.Connection,
    *,
    source_id: str,
    work_key: WorkKey,
    document: ParsedDocument,
    body: bytes,
    url: str,
    fetched_at: str | None = None,
    work_date: str | None = None,
    label: str | None = None,
    home=None,
    fts_alvo: str = "fts_redaction",
) -> ResolvedWork:
    """Persiste obra parseada no repositório e devolve ResolvedWork.

    `fts_alvo="fts_staging"`: candidato ao vivo (A7) é indexado direto no staging, nunca no canônico.
    """
    if fts_alvo not in ("fts_redaction", "fts_staging"):
        raise ValueError(f"fts_alvo inválido: {fts_alvo}")
    from freoa_verifica.transport import Response

    from freoa_verifica.identity import validate_identity
    validate_identity(work_key, document, work_date)

    # garante source
    conn.execute(
        "INSERT OR IGNORE INTO source(id, authority, profile, hosts_json) VALUES (?,?,?,?)",
        (source_id, work_key.authority, document.profile, "[]"),
    )
    work_id = store_repo.upsert_work(
        conn,
        jurisdiction="br",
        authority=work_key.authority,
        kind=work_key.kind,
        number=work_key.number,
        year=work_key.year,
        label=label,
    )
    fetched = fetched_at or datetime.now(timezone.utc).isoformat()
    digest = hashlib.sha256(body).hexdigest()
    resp = Response(
        url=url,
        final_url=url,
        status=200,
        headers={},
        body=body,
        sha256=digest,
        fetched_at=fetched,
        redirects=[],
        mime="application/octet-stream",
    )
    capture_id = store_repo.save_capture(conn, resp, source_id, home=home)
    with conn:
        for prov in document.provisions:
            pid = new_ulid()
            conn.execute(
                "INSERT INTO provision(id, work_id, scope, path) VALUES (?,?,?,?) "
                "ON CONFLICT(work_id, scope, path) DO NOTHING",
                (pid, work_id, prov.scope, prov.path),
            )
            pid = conn.execute("SELECT id FROM provision WHERE work_id=? AND scope=? AND path=?",
                               (work_id, prov.scope, prov.path)).fetchone()[0]
            for red in prov.redactions:
                digest_text = hashlib.sha256(red.text.encode("utf-8")).hexdigest()
                exists = conn.execute("SELECT id FROM redaction WHERE provision_id=? AND text_sha256=?",
                                      (pid, digest_text)).fetchone()
                if exists:
                    continue
                conn.execute("INSERT INTO redaction(id, provision_id, text, text_sha256) VALUES (?,?,?,?)",
                             (new_ulid(), pid, red.text, digest_text))
                if red.struck:
                    continue
                if fts_alvo == "fts_staging":
                    conn.execute("INSERT INTO fts_staging(text, work_label, path) VALUES (?,?,?)",
                                 (red.text, label or work_key.number, prov.path))
                else:
                    conn.execute("INSERT INTO fts_redaction(text, rubrica, work_label, path) VALUES (?,?,?,?)",
                                 (red.text, prov.rubrica, label or work_key.number, prov.path))
        if cancelado():  # orçamento estourou: levanta dentro do `with conn` e desfaz a transação
            from freoa_verifica.connectors.base import Unavailable
            raise Unavailable("orcamento")

    return ResolvedWork(
        work_id=work_id,
        work_key=work_key,
        document=document,
        work_date=work_date,
        capture_id=capture_id,
        sha256=digest,
        url=url,
        fetched_at=fetched,
        quarantined=document.quarantined,
    )
