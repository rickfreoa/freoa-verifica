"""Verificação de citação: identidade, texto, tempo e suporte."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass, field, replace
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
from freoa_verifica.temporal import (
    _is_current_query,
    _parse_iso,
    select as temporal_select,
    today_sp,
)
from freoa_verifica.textcmp import ALGO_VERSION as TEXTCMP_VERSION
from freoa_verifica.textcmp import compare
from freoa_verifica.texto_resposta import ORIGEM_LEGADO
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
    fontes_consultadas: list[dict] | None = None  # experimental; só quando fonte anterior ficou indisponível (0058)
    proveniencia: dict | None = None  # experimental; só quando o texto vem de captura sem Content-Type (0065)
    captured_at: str | None = None
    acervo_ate: str | None = None
    source_kind: str = "nao_identificado"
    natureza_texto: str = "nao_identificado"
    procedencia: str = "nao_identificado"
    esfera: str = "nao_identificado"
    atribuicao: dict | None = None  # só origem Câmara (0080, §7); aditivo, omitido quando ausente

    versao_texto: str | None = None
    legislationLegalValue: str | None = None
    license: str | None = None

    def __post_init__(self) -> None:
        if self.captured_at is None and self.fetched_at is not None:
            self.captured_at = self.fetched_at


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
    fundamento_temporal: dict[str, Any] | None = None
    correspondencia_textual: dict[str, Any] | None = None


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
    caminhos_conhecidos: frozenset[str] = frozenset()  # dispositivos de qualquer captura canônica da obra (0034)
    fontes_consultadas: list[dict] = field(default_factory=list)  # fontes anteriores sem resposta na captura (0058)
    proveniencia: dict | None = None  # experimental; `{interpretacao: "legado_sem_cabecalho"}` (0065)
    source_id: str | None = None
    acervo_ate: str | None = None
    procedencia_tipo: str = "nao_identificado"
    atribuicao: dict | None = None  # só origem Câmara (0080, §7); preenchido pelo serviço, com o home dele


class Resolver(Protocol):
    """Interface M4: garante obra capturada e parseada."""

    def resolve(self, work: WorkKey) -> ResolvedWork | list[ResolvedWork] | None:
        """None = not_found; lista >1 = ambiguous; Unavailable via exceção tipada."""
        ...


class SourceUnavailable(Exception):
    def __init__(self, reason: str, fontes_consultadas: list[dict] | None = None):
        self.reason = reason
        self.fontes_consultadas = list(fontes_consultadas or [])  # experimental (0058): fonte, resultado, motivo, categoria
        super().__init__(reason)


class SourceAmbiguous(Exception):
    """Metadados de várias obras candidatas, sem promoção a documento normativo."""

    def __init__(self, candidates):
        self.candidates = list(candidates)
        super().__init__("IDENTIDADE_AMBIGUA")


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


_SOURCE_KINDS = frozenset({
    "lei", "lei_complementar", "decreto", "decreto_lei", "medida_provisoria",
    "emenda_constitucional", "constituicao", "resolucao_cvm", "instrucao_cvm",
    "parecer_orientacao_cvm", "resolucao_cmn", "resolucao_bcb", "circular_bcb",
})


def _inferir_source_kind(wk: WorkKey | None) -> str:
    if wk is None:
        return "nao_identificado"
    auth = (wk.authority or "").lower()
    kind = (wk.kind or "").lower()
    if auth == "federal":
        if kind in ("lei", "lei_complementar", "decreto", "decreto_lei", "medida_provisoria", "emenda_constitucional", "constituicao"):
            return kind
    elif auth == "cvm":
        if kind in ("resolucao", "resolucao_cvm"):
            return "resolucao_cvm"
        if kind in ("instrucao", "instrucao_cvm"):
            return "instrucao_cvm"
        if kind in ("parecer_orientacao", "parecer_orientacao_cvm"):
            return "parecer_orientacao_cvm"
    elif auth == "cmn":
        if kind in ("resolucao", "resolucao_cmn"):
            return "resolucao_cmn"
    elif auth == "bcb":
        if kind in ("resolucao", "resolucao_bcb"):
            return "resolucao_bcb"
        if kind in ("circular", "circular_bcb"):
            return "circular_bcb"
    if kind in _SOURCE_KINDS:
        return kind
    return "nao_identificado"


# Perfis cujo parser só aceita o formato consolidado oficial (docstrings de `parsers/planalto.py` e `parsers/cvm_docx.py`).
# A autoridade da obra não demonstra consolidação (IL.0-R, C6/0075 §3.2): metadados do Senado, HTML/PDF da CVM e o
# JSON do BCB não sustentam a natureza e ficam `nao_identificado`.
_NATUREZA_POR_PERFIL = {"planalto": "consolidacao_oficial", "cvm_docx": "consolidacao_oficial",
                       "camara_atualizado": "consolidacao_oficial", "camara_original": "publicacao_original"}


def _inferir_natureza_texto(rw: ResolvedWork) -> str:
    """Natureza pelo documento capturado (perfil do parser) e nunca pela autoridade; sem texto parseado, não há natureza."""
    doc = rw.document
    if doc is None or not getattr(doc, "provisions", None):
        return "nao_identificado"
    return _NATUREZA_POR_PERFIL.get(getattr(doc, "profile", "") or "", "nao_identificado")


def _inferir_esfera(wk: WorkKey | None) -> str:
    if wk is None:
        return "nao_identificado"
    auth = (wk.authority or "").lower()
    if auth in ("federal", "senado", "cvm", "bcb", "cmn", "stf", "stj"):
        return "federal"
    return "nao_identificado"


def _inferir_procedencia(rw: ResolvedWork) -> str:
    if hasattr(rw, "procedencia_tipo") and rw.procedencia_tipo:
        return rw.procedencia_tipo
    return "nao_identificado"


_PROCEDENCIAS = frozenset({"captura_direta", "snapshot", "cadeia_de_alteracoes", "sessao_assistida", "nao_identificado"})


def campos_evidencia(capture_id: str | None, sha256: str | None, url: str | None, fetched_at: str | None, *,
                     source_kind: str = "nao_identificado", natureza_texto: str = "nao_identificado",
                     procedencia: str | None = None, esfera: str = "nao_identificado",
                     acervo_ate: str | None = None, atribuicao: dict | None = None) -> dict[str, Any]:
    """Construtor único da evidência capturada publicada (0075, §3.2; IL.0-R, C6): os quatro campos
    de captura e os seis eixos. Normas, decisões, `verificar_citacao` e `obter_dispositivo` passam por aqui."""
    return {
        "capture_id": capture_id,
        "sha256": sha256,
        "url": url,
        "fetched_at": fetched_at,
        "captured_at": fetched_at,
        "acervo_ate": acervo_ate,
        "source_kind": source_kind or "nao_identificado",
        "natureza_texto": natureza_texto or "nao_identificado",
        "procedencia": procedencia if procedencia in _PROCEDENCIAS else "nao_identificado",
        "esfera": esfera or "nao_identificado",
        **({"atribuicao": atribuicao} if atribuicao else {}),
    }


def _atribuicao_camara(source_id, home, document, sha256=None, url=None, fetched_at=None) -> dict | None:
    """Atribuição do §7 da 0080 no caminho de captura viva, com o home de quem capturou e o vínculo da captura."""
    if source_id != "camara_legin":
        return None
    from freoa_verifica.connectors.camara_atribuicao import atribuicao, autoria_declarada
    return atribuicao(home, autoria_declarada(getattr(document, "text", None)), sha256=sha256, url=url,
                      fetched_at=fetched_at)


def origem_camara(rw: ResolvedWork) -> bool:
    return rw.source_id == "camara_legin" or str(getattr(rw.document, "profile", "")).startswith("camara")


def campos_evidencia_obra(rw: ResolvedWork, acervo_ate: str | None) -> dict[str, Any]:
    atribuicao = rw.atribuicao
    if atribuicao is None and origem_camara(rw):  # obra montada fora do serviço: home padrão, autoria declarada
        from freoa_verifica.connectors.camara_atribuicao import atribuicao as montar, autoria_declarada
        atribuicao = montar(None, autoria_declarada(getattr(rw.document, "text", None)), sha256=rw.sha256, url=rw.url)
    extra = {}
    if rw.source_id == "normas_leg" or rw.document.profile == "normas_leg":
        from freoa_verifica.connectors.normas_leg import ATRIBUICAO
        meta = next((json.loads(b.text) for b in rw.document.editorial_blocks
                     if b.kind == "normas_leg_metadados"), {})
        atribuicao = {"texto": ATRIBUICAO}
        extra = {"versao_texto": meta.get("version"),
                 "legislationLegalValue": meta.get("legislationLegalValue"), "license": meta.get("license")}
    return {**extra, **campos_evidencia(
        rw.capture_id, rw.sha256, rw.url, rw.fetched_at,
        source_kind=_inferir_source_kind(rw.work_key), natureza_texto=_inferir_natureza_texto(rw),
        procedencia=_inferir_procedencia(rw), esfera=_inferir_esfera(rw.work_key), acervo_ate=acervo_ate,
        atribuicao=atribuicao,
    )}


def _ev_from_resolved(rw: ResolvedWork, path: str | None, trecho: str | None, span=None) -> Evidence:
    t = trecho
    if t and len(t) > _MAX_TRECHO:
        t = t[:_MAX_TRECHO]
    return Evidence(
        path=path,
        span=span,
        trecho_oficial=t,
        fontes_consultadas=rw.fontes_consultadas or None,
        proveniencia=rw.proveniencia,
        **campos_evidencia_obra(rw, rw.acervo_ate),
    )


_INCOMPLETE_CODES = frozenset({"TRUNCATED", "EXTRACAO_INCOMPLETA"})


def _scope_of(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else ""


def pode_negar(rw: ResolvedWork | None, path: str) -> str | None:
    """C1 (decisão 0023): None autoriza DISPOSITIVO_INEXISTENTE; senão, o motivo que o impede."""
    if rw is not None and (motivo := _caput_nao_representado(rw, path)):
        return motivo
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
    if path in rw.caminhos_conhecidos or path.removesuffix(".caput") in rw.caminhos_conhecidos:
        return "ESTRUTURA_DIVERGENTE_ENTRE_CAPTURAS"  # outra captura canônica tinha o dispositivo (0034)
    return None


def negativa_dimension(rw: ResolvedWork | None, path: str) -> Dimension:
    """Identidade de dispositivo ausente: not_found só se pode_negar autoriza."""
    motivo = pode_negar(rw, path)
    ev = [_ev_from_resolved(rw, path, None)] if rw is not None else []
    if motivo is None:
        return Dimension("not_found", "DISPOSITIVO_INEXISTENTE", ev)
    return Dimension("unavailable" if motivo == "COBERTURA" else "unknown", motivo, ev)


def _caput_nao_representado(rw: ResolvedWork, path: str | None) -> str | None:
    """D5: caput é a cabeça do artigo; recorte não resolvido não prova ausência."""
    if rw.source_id != "camara_legin" or not path:
        return None
    parts = path.split(".")
    if "caput" not in parts:
        return None
    index = parts.index("caput")
    # Caput é só a cabeça do artigo (titular): caput abaixo de parágrafo é referência
    # imprópria e prevalece sobre a regra de inciso do caput.
    if any(p.startswith("par") for p in parts[:index]):
        return "caput_refere_se_ao_artigo"
    # F16 inclui os descendentes de incisos.
    if (index + 1 < len(parts) and parts[index + 1].startswith("inc")
            and rw.document.provision(path) is None):
        return "inciso_do_caput_nao_resolvido"
    if rw.document.provision(path) is None:
        return "recorte_caput_nao_representado"
    return None


def _alternativas_caput(path: str) -> list[str]:
    """Duas leituras de uma referência imprópria, sem confirmar nenhuma."""
    parts = path.split(".")
    resto = parts[parts.index("caput") + 1:]
    return [".".join([parts[0], "caput", *resto]), path.replace(".caput", "")]


def _find_provision(doc: ParsedDocument, path: str) -> Provision | None:
    prov = doc.provision(path)
    if prov:
        return prov
    # O fallback exige prova estrutural de texto exclusivamente do caput.
    if path.endswith(".caput"):
        article = path.removesuffix(".caput")
        candidate = doc.provision(article)
        if (candidate and not any(p.path.startswith(article + ".") for p in doc.provisions)
                and not any(re.search(r"(?:§|Parágrafo único|(?:^|\n)\s*[IVXLCDM]+\s*[-–—])", r.text, re.I)
                            for r in candidate.redactions)):
            return candidate
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
        if i.path and (i.path == path or path.startswith(i.path + ".") or path.startswith(i.path + "/")
                       or i.path.startswith(path + ".") or i.path.startswith(path + "/"))
        and (
            i.blocking_scope == "provision"
            or i.code in PROVISION_BLOCKING_CODES
        )
    ]


INICIO_ATUAL_NAO_DOCUMENTADO = "inicio_redacao_atual_nao_documentado"


def _camara_sem_historia(rw):
    return rw.source_id == "camara_legin" and rw.document.profile == "camara_atualizado"


def _annotations_for_cut(rw, path):
    """Metadados do recorte, sem atribuir eventos de componentes ao pai."""
    annotations = []
    for prov in rw.document.provisions:
        if prov.path == path or (path and prov.path.startswith(path + ".")):
            for red in prov.redactions:
                for ann in red.annotations:
                    if ann not in annotations:
                        annotations.append(ann)
    return annotations


def _temporal_select(rw, provision, data=None, **kwargs):
    result = temporal_select(provision, data, **kwargs)
    if not _camara_sem_historia(rw):
        return result
    # 0077: nem silêncio editorial nem data de nota documentam o início atual.
    return replace(result, status="unknown", interval=None, rules_applied=[],
                   needs_judgment=True, reason=INICIO_ATUAL_NAO_DOCUMENTADO,
                   flags=list(dict.fromkeys([*result.flags, INICIO_ATUAL_NAO_DOCUMENTADO])))


def _reading_blockers(rw, path, *, history=False):
    """Mesma admissão para leituras que poderiam publicar texto/tempo conclusivo."""
    if motivo := _caput_nao_representado(rw, path):
        return [motivo]
    issues = [i for i in rw.document.issues if i.blocking_scope == "document"]
    issues += _provision_blocking_issues(rw.document, path)
    codes = [i.code for i in issues]
    if rw.quarantined:
        codes.append("DOCUMENTO_QUARENTENADO")
    if rw.persisted_incomplete:
        codes.append("DADOS_PERSISTIDOS_INCOMPLETOS")
    prov = _find_provision(rw.document, path) if path else None
    if prov and prov.ambiguous:
        codes.append("DUPLICATE_CURRENT")
    if rw.source_id == "camara_legin" and path and any(
        path.startswith(parent.path + ".") and any(r.annotations for r in parent.redactions)
        for parent in rw.document.provisions
    ):
        codes.append("IMPEDIMENTO_ANCESTRAL")
    if history and _camara_sem_historia(rw):
        codes.append(INICIO_ATUAL_NAO_DOCUMENTADO)
    if history and rw.source_id == "camara_legin" and prov and _annotations_for_cut(rw, path):
        codes.append("NOTAS_EDITORIAIS_PENDENTES")
    return list(dict.fromkeys(codes))


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


def _calcular_correspondencia_textual(
    prov: Provision | None,
    trecho: str | None,
    modo: str,
    temporal_res: Any | None,
    is_historical: bool,
    identity_status: str,
) -> dict[str, Any] | None:
    if not is_historical or trecho is None or identity_status != "verified" or prov is None:
        return None

    # Se há redação selecionada pelo temporal:
    red = _redaction_by_id(prov, temporal_res.redaction_id) if (temporal_res and temporal_res.redaction_id) else None

    if red is not None:
        cmp = compare(trecho, red.text, modo)
        if cmp.status == "match":
            return {
                "resultado": "coincide",
                "redaction_id": temporal_res.redaction_id,
                "riscada": bool(red.struck),
                "origem": "rasura_compilada" if (red.struck or red.superseded_without_strike) else "redacao_atual",
            }
        # Se não casou com a selecionada, procura coincidência exata em todas as redações (ex.: trecho de outra redação)
        for other in prov.redactions:
            if other is red:
                continue
            cmp_other = compare(trecho, other.text, modo, exact_only=True)
            if cmp_other.status == "match":
                return {
                    "resultado": "coincide",
                    "redaction_id": f"r{other.order}",
                    "riscada": bool(other.struck),
                    "origem": "rasura_compilada" if (other.struck or other.superseded_without_strike) else "redacao_atual",
                }
        if cmp.status == "partial":
            return {
                "resultado": "parcial",
                "redaction_id": temporal_res.redaction_id,
                "riscada": bool(red.struck),
                "origem": "rasura_compilada" if (red.struck or red.superseded_without_strike) else "redacao_atual",
            }
        return {
            "resultado": "diverge",
            "redaction_id": temporal_res.redaction_id,
            "riscada": bool(red.struck),
            "origem": "rasura_compilada" if (red.struck or red.superseded_without_strike) else "redacao_atual",
        }

    # Sem redação selecionada: procurar coincidência exata em todas as redações
    for r in prov.redactions:
        cmp_r = compare(trecho, r.text, modo, exact_only=True)
        if cmp_r.status == "match":
            return {
                "resultado": "coincide",
                "redaction_id": f"r{r.order}",
                "riscada": bool(r.struck),
                "origem": "rasura_compilada" if (r.struck or r.superseded_without_strike) else "redacao_atual",
            }

    # Se não coincide exatamente com nenhuma:
    vigente = _current_redaction(prov)
    if vigente is not None:
        cmp_v = compare(trecho, vigente.text, modo)
        if cmp_v.status == "partial":
            return {
                "resultado": "parcial",
                "redaction_id": f"r{vigente.order}",
                "riscada": bool(vigente.struck),
                "origem": "rasura_compilada" if (vigente.struck or vigente.superseded_without_strike) else "redacao_atual",
            }

    return {
        "resultado": "diverge",
        "redaction_id": None,
        "riscada": None,
        "origem": "redacao_atual",
    }


def _sem_fundamento_historico(temporal_res, data: str | None) -> bool:
    """C5: consulta histórica (D válida e diferente de hoje) sem fundamento validado (hoje nunca há, IL.2). Mantêm-se
    `nao_existia`, `ambiguous` e data inválida, que têm motivo próprio."""
    if temporal_res is None or _parse_iso(data) is None or _is_current_query(data, today_sp()):
        return False
    return (temporal_res.status not in ("nao_existia", "ambiguous")
            and "data_consulta_invalida" not in temporal_res.flags)


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

    today = today_sp()
    is_historical = not _is_current_query(data, today)

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
            identity=Dimension("unavailable", exc.reason,
                               [Evidence(fontes_consultadas=exc.fontes_consultadas)] if exc.fontes_consultadas else []),
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
    comparison_mode = ("camara_il1" if rw.document.profile in {"camara_atualizado", "camara_original"}
                       and modo == "normalizado" else modo)
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
    from freoa_verifica.qualificacao import rota_aprovada
    if ((rw.source_id == "normas_leg" or rw.document.profile == "normas_leg")
            and not rota_aprovada("normas_leg", "normas_leg")):
        # 0085 §3.3: material parcial, sem confirmação, inclusive na API Python sem serviço.
        evidence = _ev_from_resolved(rw, cite.path, None)
        provision = _find_provision(rw.document, cite.path) if cite.path else None
        if (provision is not None and not provision.ambiguous and not rw.quarantined
                and not _reading_blockers(rw, cite.path)):
            try:
                red = provision.current_redaction()
                evidence.trecho_oficial, evidence.span = red.text, red.span
            except (AmbiguousProvision, RevokedProvision):
                pass
        return _persist(repo, citacao, trecho, data, modo, VerificationResult(
            identity=Dimension("unknown", "rota_nao_qualificada", [evidence]),
            text=Dimension("unknown", "rota_nao_qualificada", [evidence]),
            temporal=Dimension("unknown", "rota_nao_qualificada", [evidence]),
            support=support, citation=cite))
    path = cite.path
    if motivo := _caput_nao_representado(rw, path):
        return _persist(repo, citacao, trecho, data, modo, VerificationResult(
            identity=Dimension("unknown", motivo, [_ev_from_resolved(rw, path, None)]),
            text=Dimension("unknown", motivo),
            temporal=Dimension("unknown", motivo), support=support, citation=cite,
        ))
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

    reading_codes = _reading_blockers(rw, path)
    if blocking or "IMPEDIMENTO_ANCESTRAL" in reading_codes:
        reason = blocking[0].code if blocking else "IMPEDIMENTO_ANCESTRAL"
        return _persist(repo, citacao, trecho, data, modo, VerificationResult(
            identity=Dimension("unknown", reason, [_ev_from_resolved(rw, path, None)]),
            text=Dimension("unknown", reason) if trecho is not None else Dimension("not_assessed", "SEM_TRECHO"),
            temporal=Dimension("unknown", reason), support=support, citation=cite,
        ))

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
            temporal_res = _temporal_select(
                rw, prov,
                data,
                work_date=rw.work_date,
                amending_act_texts=rw.amending_act_texts,
                fetched_at=rw.fetched_at,
            )
            temporal_dim = _map_temporal(temporal_res, rw, path)
            # 0075, §2.2 e C5: a abstenção histórica por falta de fundamento prevalece sobre o motivo de revogação,
            # com ou sem data de revogação (condição histórica, não o motivo intermediário do temporal).
            text_dim = (
                Dimension("unknown", "sem_fundamento_do_periodo"
                          if _sem_fundamento_historico(temporal_res, data) else "DISPOSITIVO_REVOGADO")
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
        temporal_res = _temporal_select(
            rw, prov,
            data,
            work_date=rw.work_date,
            amending_act_texts=rw.amending_act_texts,
            fetched_at=rw.fetched_at,
        )
        temporal_dim = _map_temporal(temporal_res, rw, path)

    # --- text ---
    uncertain = any(i.code == "UNCERTAIN_CONTINUATION" for i in blocking)
    # 0037: fecho do dispositivo pode ter saído com a margem do PDF; nenhum confronto conclui.
    margem = any(i.code == "MARGEM_ADJACENTE" for i in blocking)
    if trecho is None:
        text_dim = Dimension("not_assessed", "SEM_TRECHO")
    elif prov is None:
        text_dim = (Dimension("not_found", "SEM_DISPOSITIVO") if identity.status == "not_found"
                    else Dimension("unknown", identity.reason_code))
    elif temporal_res and (temporal_res.status in ("revogado", "nao_existia", "ambiguous") or "revogacao_anotada" in temporal_res.flags):
        if _sem_fundamento_historico(temporal_res, data):
            # C5: motivo da abstenção histórica antes dos tratamentos de revogação.
            reason = "sem_fundamento_do_periodo"
        else:
            reason = "REVOGADO" if "revogacao_anotada" in temporal_res.flags else (temporal_res.reason or temporal_res.status.upper())
        text_dim = Dimension("unknown", reason)
    elif temporal_res and temporal_res.reason in {"INICIO_SUCESSOR_DESCONHECIDO", "CAPTURA_DATA_INVALIDA"}:
        text_dim = Dimension("unknown", temporal_res.reason)
    elif (temporal_res and not temporal_res.redaction_id
          and temporal_res.status not in ("verified", "vigente_na_fonte")
          and "sem_fundamento_do_periodo" not in temporal_res.flags):
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
            temporal_res is None or (temporal_res.status not in {"verified", "vigente_na_fonte"} and "sem_fundamento_do_periodo" not in temporal_res.flags)
        ):
            # Não afirmar texto sobre redação superada sem rasura fora de verified
            text_dim = Dimension(
                "unknown",
                "REDACAO_SUPERADA",
                [_ev_from_resolved(rw, path, red.text)],
            )
        else:
            cmp = compare(trecho, red.text, comparison_mode)
            ev = _ev_from_resolved(
                rw,
                path,
                red.text,
                span=(cmp.start, cmp.end) if cmp.start is not None else None,
            )
            if margem:
                text_dim = Dimension("unknown", "MARGEM_ADJACENTE", [ev])
            elif cmp.status == "match":
                if uncertain:
                    text_dim = Dimension("unknown", "UNCERTAIN_CONTINUATION", [ev])
                elif is_historical:
                    text_dim = Dimension("unknown", "sem_fundamento_do_periodo", [ev])
                else:
                    text_dim = Dimension("verified", "TEXTO_OK", [ev])
            elif cmp.status == "partial":
                if is_historical:
                    text_dim = Dimension("unknown", "sem_fundamento_do_periodo", [ev])
                else:
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
                    c2 = compare(trecho, r2.text, comparison_mode, exact_only=True)
                    if c2.status == "match":
                        other_hit = r2
                        break
                if other_hit is not None:
                    if is_historical:
                        text_dim = Dimension(
                            "unknown",
                            "sem_fundamento_do_periodo",
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
                    elsewhere = _search_text_in_work(rw.document, trecho, comparison_mode, path)
                    if elsewhere:
                        if is_historical:
                            text_dim = Dimension(
                                "unknown",
                                "sem_fundamento_do_periodo",
                                [
                                    ev,
                                    _ev_from_resolved(rw, elsewhere[0], None),
                                ],
                            )
                        else:
                            text_dim = Dimension(
                                "divergent",
                                "TRECHO_EM_OUTRO_DISPOSITIVO",
                                [
                                    ev,
                                    _ev_from_resolved(rw, elsewhere[0], None),
                                ],
                            )
                    else:
                        if is_historical:
                            text_dim = Dimension("unknown", "sem_fundamento_do_periodo", [ev])
                        else:
                            text_dim = Dimension("divergent", "TEXTO_DIVERGENTE", [ev])

    corr_textual = _calcular_correspondencia_textual(
        prov=prov,
        trecho=trecho,
        modo=comparison_mode,
        temporal_res=temporal_res,
        is_historical=is_historical,
        identity_status=identity.status,
    )
    result = VerificationResult(
        identity=identity,
        text=text_dim,
        temporal=temporal_dim,
        support=support,
        citation=cite,
        correspondencia_textual=corr_textual,
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
            "evidence": [{**{k: v for k, v in asdict(e).items()
                             if k not in ("fontes_consultadas", "proveniencia", "atribuicao", "versao_texto", "legislationLegalValue", "license") or v},
                          "span": list(e.span) if e.span is not None else None}
                         for e in d.evidence],
        }

    out: dict[str, Any] = {
        "identity": dim(result.identity),
        "text": dim(result.text),
        "temporal": dim(result.temporal),
        "support": dim(result.support),
        "algo_versions": result.algo_versions,
        "fundamento_temporal": result.fundamento_temporal,
        "correspondencia_textual": result.correspondencia_textual,
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


def persistir_resultado(conn, citacao, trecho, data, modo, resultado: dict[str, Any], *,
                        ferramenta: str = "verificar_citacao", parametros: dict[str, Any] | None = None) -> str:
    """Grava o recibo (C4): chamado só depois da finalização, com a conclusão devolvida.

    Política `sem_conteudo` (C5): só hashes, política e dimensões; sem citação, trecho nem evidência.
    """
    from freoa_verifica.registro import hmac_entrada, politica_atual

    request = {"citacao": citacao, "trecho": trecho, "data": data, "modo": modo}
    if parametros:
        request.update(parametros)
    request_json = json.dumps(request, ensure_ascii=False, sort_keys=True)
    request_hash = hashlib.sha256(request_json.encode("utf-8")).hexdigest()
    if politica_atual.get() == "sem_conteudo":
        # Entrada do usuário: HMAC com segredo do home (sha256 puro de entrada curta é adivinhável).
        request_hash = hmac_entrada(conn, "request", request_json)
        h = lambda k, v: None if v is None else hmac_entrada(conn, k, str(v))  # noqa: E731
        request_json = json.dumps(
            {"registro": "sem_conteudo", **{f"{k}_sha256": h(k, v) for k, v in request.items()}},
            sort_keys=True,
        )
        result_json = json.dumps(
            {
                "registro": "sem_conteudo",
                **{d: {"status": (resultado.get(d) or {}).get("status"),
                       "reason_code": (resultado.get(d) or {}).get("reason_code")}
                   for d in ("identity", "text", "temporal", "support")},
                "algo_versions": resultado.get("algo_versions"),
                **({"fontes_consultadas_sha256": hmac_entrada(
                    conn, "fontes_consultadas", json.dumps(resultado["fontes_consultadas"],
                                                         ensure_ascii=False, sort_keys=True))}
                   if "fontes_consultadas" in resultado else {}),
            },
            ensure_ascii=False, sort_keys=True,
        )
    else:
        result_json = json.dumps(resultado, ensure_ascii=False, sort_keys=True)
    run_id = new_ulid()
    created_at = datetime.now(timezone.utc).isoformat()

    # Evidências únicas (todas as dimensões, na ordem)
    # Não criar compromisso para evidência sem capture_id, sha256 e url (decisão 0075 / parecer Codex r1)
    evidencias_unicas: list[dict[str, Any]] = []
    vistos_ev: set[tuple[Any, Any, Any]] = set()
    grupos_evidencia = [(resultado.get(d) or {}).get("evidence") or []
                       for d in ("identity", "text", "temporal", "support")]
    grupos_evidencia.append([resultado.get("evidencia"),
                            (resultado.get("ultima_versao_oficial_anterior") or {}).get("evidencia")])
    grupos_evidencia.append([item.get("evidencia") for item in resultado.get("cadeia_alteracoes", [])
                            if isinstance(item, dict)])
    for grupo in grupos_evidencia:
        for ev in grupo:
            if isinstance(ev, dict):
                cid = ev.get("capture_id")
                sha = ev.get("sha256")
                url = ev.get("url")
                if cid and sha and url:
                    tup_key = (cid, sha, url)
                    if tup_key not in vistos_ev:
                        vistos_ev.add(tup_key)
                        evidencias_unicas.append({
                            "capture_id": cid,
                            "sha256": sha,
                            "url": url,
                        })

    compromissos_ev = [
        hmac_entrada(conn, "evidencia", json.dumps(item, ensure_ascii=False, sort_keys=True))
        for item in evidencias_unicas
    ]
    evidencias_compromissos = json.dumps(compromissos_ev, ensure_ascii=False, sort_keys=True)
    if politica_atual.get() == "sem_conteudo":
        evidencias_claro = None
    else:
        evidencias_claro = json.dumps(evidencias_unicas, ensure_ascii=False, sort_keys=True)

    ft = resultado.get("fundamento_temporal")
    if ft is not None:
        ft_canon = json.dumps(ft, ensure_ascii=False, sort_keys=True)
        fundamento_compromisso = hmac_entrada(conn, "fundamento_temporal", ft_canon)
        fundamento_claro = ft_canon if politica_atual.get() != "sem_conteudo" else None
    else:
        fundamento_compromisso = None
        fundamento_claro = None

    doc_mac = {
        "id": run_id,
        "ferramenta": ferramenta,
        "created_at": created_at,
        "request_hash": request_hash,
        "request_json": request_json,
        "result_json": result_json,
        "evidencias_compromissos": evidencias_compromissos,
        "fundamento_compromisso": fundamento_compromisso,
        "evidencias_claro": evidencias_claro,
        "fundamento_claro": fundamento_claro,
    }
    registro_mac = hmac_entrada(conn, "registro", json.dumps(doc_mac, ensure_ascii=False, sort_keys=True))

    conn.execute(
        "INSERT INTO run("
        "id, ferramenta, created_at, request_hash, request_json, policy_version, result_json, "
        "evidencias_compromissos, fundamento_compromisso, evidencias_claro, fundamento_claro, registro_mac"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            run_id,
            ferramenta,
            created_at,
            request_hash,
            request_json,
            POLICY_VERSION,
            result_json,
            evidencias_compromissos,
            fundamento_compromisso,
            evidencias_claro,
            fundamento_claro,
            registro_mac,
        ),
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
    content_type: str | None = None,
) -> ResolvedWork:
    """Persiste obra parseada no repositório e devolve ResolvedWork.

    `fts_alvo="fts_staging"`: candidato ao vivo (A7) é indexado direto no staging, nunca no canônico.
    `content_type`: o cru da resposta que o parser leu; vai ao recibo para que a releitura o reproduza (F-22).
    """
    if fts_alvo not in ("fts_redaction", "fts_staging"):
        raise ValueError(f"fts_alvo inválido: {fts_alvo}")
    from freoa_verifica.transport import Response

    from freoa_verifica.identity import validate_identity
    validate_identity(work_key, document, work_date)

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
        content_type=content_type or "",
    )
    # Modelo de fonte reprocessável só com decisão de interpretação; sem ela, nada se grava (F-26, decisão 0066).
    if source_id in store_repo.FONTES_COMPILADAS and not store_repo.decisao_registrada(
            *store_repo.interpretacao_do_recibo(resp)[1:]):
        raise store_repo.interpretacao_indisponivel(digest, url)

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
    if source_id == "camara_legin":
        # IL.3-c (conferência 4): a Câmara nunca recebe recibo genérico do materializador;
        # o modelo vincula-se à captura real já gravada pelo indexador após o preflight.
        row = conn.execute("SELECT id FROM capture WHERE sha256=? AND url=? AND fetched_at=? "
                           "AND source_id='camara_legin'", (digest, url, fetched_at)).fetchone()
        if fetched_at is None or row is None:
            raise store_repo.IdentityConflict(f"captura {digest} da Câmara ausente para o modelo")
        capture_id = row["id"] if hasattr(row, "keys") else row[0]
    else:
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

    acervo_ate = None
    if source_id == "planalto":
        row_c = conn.execute("SELECT MAX(fetched_at) FROM capture WHERE source_id='planalto' AND fetched_at IS NOT NULL").fetchone()
        acervo_ate = str(row_c[0])[:10] if (row_c and row_c[0]) else None

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
        # Mesma declaração que a obra relida do banco traz (0065): captura sem Content-Type é prova degradada.
        proveniencia=({"interpretacao": ORIGEM_LEGADO} if conn.execute(
            "SELECT origem_da_codificacao FROM capture WHERE id=?", (capture_id,)).fetchone()[0] == ORIGEM_LEGADO
            else None),
        source_id=source_id,
        acervo_ate=acervo_ate,
        # C6: a marca persistida da captura (a existente prevalece sobre a regravação idêntica).
        procedencia_tipo=(conn.execute("SELECT procedencia FROM capture WHERE id=?", (capture_id,)).fetchone()[0]
                          or "nao_identificado"),
        atribuicao=_atribuicao_camara(source_id, home, document, digest, url, resp.fetched_at),
    )
