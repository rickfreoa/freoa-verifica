"""Seleção de redação vigente por data (modelo temporal por eventos).

Regras documentadas em RULES e nas docstrings de cada função auxiliar.
Estados: verified | vigente_na_fonte | unknown | revogado | nao_existia | ambiguous.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from freoa_verifica.parsers.model import Annotation, Provision, Redaction

RULES: dict[str, str] = {
    "R1": (
        "Redação vigente atual = a não riscada; redações riscadas são anteriores, "
        "na ordem do documento."
    ),
    "R2": (
        "Início de uma redação = data do ato alterador da anotação que a introduziu "
        "(incluido/redacao_dada); se só houver ano, a data fica unknown até o "
        "conector (M4) resolver via work.date."
    ),
    "R3": "Redação original (sem anotação) inicia na data da obra.",
    "R4": (
        "Fim de uma redação = início da seguinte. Revogação (anotação revogado) "
        "fecha o intervalo da última redação; após ela o dispositivo está revogado. "
        "Fim desconhecido (sucessor sem data) ≠ fim aberto."
    ),
    "R5": (
        "vide, vigencia, producao_efeitos e vetos NUNCA alteram intervalo "
        "automaticamente; marcam needs_judgment=True."
    ),
    "R6": (
        "Data do ato marcada rule='data_do_ato' e flag vacatio_nao_verificada, "
        "salvo se o texto do ato alterador contiver "
        "'entra em vigor na data de sua publicação' "
        "(então rule='vigencia_na_publicacao' e flag publicacao_dou_nao_verificada)."
    ),
}

_INTRO_KINDS = frozenset({"incluido", "redacao_dada"})
_JUDGMENT_KINDS = frozenset({"vide", "vigencia", "producao_efeitos", "veto"})
_BLOCKING_FLAGS = frozenset(
    {
        "vacatio_nao_verificada",
        "publicacao_dou_nao_verificada",
        "data_ano_nao_resolvida",
        "revogacao_parcial",
        "revogacao_sem_data",
        "fim_desconhecido",
        "CAPTURA_DESATUALIZADA",
    }
)
_VIGENCIA_NA_PUB = re.compile(
    r"entra\s+em\s+vigor\s+na\s+data\s+de\s+sua\s+publica[cç][aã]o",
    re.I,
)
_TZ_SP = ZoneInfo("America/Sao_Paulo")
_CAPTURE_MAX_AGE = timedelta(days=30)


@dataclass
class Interval:
    start: str | None  # ISO date ou None (=unknown)
    end: str | None  # ISO date; None = aberto (vigente) se end_unknown=False
    end_unknown: bool = False  # True = fim desconhecido (≠ aberto)


@dataclass
class TemporalResult:
    status: str  # verified|vigente_na_fonte|unknown|revogado|nao_existia|ambiguous
    redaction_id: str | None
    interval: Interval | None
    rules_applied: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    needs_judgment: bool = False
    reason: str | None = None


@dataclass
class _DatedRedaction:
    redaction: Redaction
    redaction_id: str
    start: str | None
    end: str | None
    end_unknown: bool
    rule: str | None
    flags: list[str]
    intro_annotation: Annotation | None


def today_sp() -> date:
    return datetime.now(_TZ_SP).date()


def _parse_iso(d: str | None) -> date | None:
    if not d:
        return None
    try:
        return date.fromisoformat(d[:10])
    except ValueError:
        return None


def _parse_fetched_at(fetched_at: str | None) -> datetime | None:
    if not fetched_at:
        return None
    try:
        raw = fetched_at.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_TZ_SP)
        return dt.astimezone(_TZ_SP)
    except ValueError:
        return None


def _year_only(act_date: str | None, act_ref: str | None) -> bool:
    """True se a data conhecida for só o ano (ou inexistente com ref só com ano)."""
    if act_date and re.fullmatch(r"\d{4}-\d{2}-\d{2}", act_date):
        return False
    if act_date and re.fullmatch(r"\d{4}", act_date):
        return True
    if act_ref and re.search(r",\s*de\s+\d{4}\s*$", act_ref):
        return True
    if act_ref and re.search(r"/\d{4}\b", act_ref) and not re.search(
        r"\d{1,2}\s+de\s+\w+\s+de\s+\d{4}", act_ref, re.I
    ):
        if not re.search(r"\d{1,2}\s+de\s+\w+", act_ref, re.I):
            return True
    return act_date is None and act_ref is not None


def _resolve_start(
    red: Redaction,
    *,
    work_date: str | None,
    amending_texts: dict[str, str],
    is_first_original: bool,
) -> tuple[str | None, str | None, list[str], Annotation | None, list[str]]:
    """Aplica R2/R3/R6. Retorna (start, rule, flags, intro_ann, rules)."""
    rules: list[str] = []
    flags: list[str] = []
    intro = next((a for a in red.annotations if a.kind in _INTRO_KINDS), None)

    if intro is None:
        rules.append("R3")
        return work_date, None, flags, None, rules

    rules.append("R2")
    if intro.act_date and re.fullmatch(r"\d{4}-\d{2}-\d{2}", intro.act_date):
        start = intro.act_date
    elif _year_only(intro.act_date, intro.act_ref):
        start = None
        flags.append("data_ano_nao_resolvida")
    else:
        start = intro.act_date

    rules.append("R6")
    act_text = ""
    if intro.act_ref and intro.act_ref in amending_texts:
        act_text = amending_texts[intro.act_ref]
    elif intro.act_ref:
        for k, v in amending_texts.items():
            if intro.act_ref in k or k in intro.act_ref:
                act_text = v
                break

    if act_text and _VIGENCIA_NA_PUB.search(act_text):
        rule = "vigencia_na_publicacao"
        flags.append("publicacao_dou_nao_verificada")
    else:
        rule = "data_do_ato"
        if start is not None:
            flags.append("vacatio_nao_verificada")

    return start, rule, flags, intro, rules


def _has_partial_revocation(provision: Provision) -> bool:
    return any(
        a.kind == "revogacao_parcial"
        for r in provision.redactions
        for a in r.annotations
    )


def _revocation_info(
    provision: Provision,
) -> tuple[str | None, bool]:
    """Retorna (revoked_at ISO ou None, sem_data)."""
    revoked_at: str | None = None
    sem_data = False
    for red in provision.redactions:
        for ann in red.annotations:
            if ann.kind == "revogado":
                if ann.act_date and re.fullmatch(r"\d{4}-\d{2}-\d{2}", ann.act_date):
                    revoked_at = ann.act_date
                    sem_data = False
                else:
                    revoked_at = None
                    sem_data = True
    return revoked_at, sem_data


def build_intervals(
    provision: Provision,
    *,
    work_date: str | None = None,
    amending_act_texts: dict[str, str] | None = None,
    redaction_ids: list[str] | None = None,
) -> tuple[list[_DatedRedaction], list[str], bool, list[str]]:
    """Projeta intervalos [início, fim) a partir das redações (R1–R6).

    Retorna (redações datadas ordenadas, rules_applied, needs_judgment, flags globais).
    """
    amending_act_texts = amending_act_texts or {}
    reds = sorted(provision.redactions, key=lambda r: r.order)
    rules_applied: list[str] = ["R1"]
    needs_judgment = False
    global_flags: list[str] = []

    for red in reds:
        for ann in red.annotations:
            if ann.kind in _JUDGMENT_KINDS:
                needs_judgment = True
                if "R5" not in rules_applied:
                    rules_applied.append("R5")
            if ann.kind == "revogacao_parcial":
                global_flags.append("revogacao_parcial")
                needs_judgment = True

    dated: list[_DatedRedaction] = []
    for i, red in enumerate(reds):
        rid = (
            redaction_ids[i]
            if redaction_ids and i < len(redaction_ids)
            else f"r{red.order}"
        )
        is_original = not any(a.kind in _INTRO_KINDS for a in red.annotations)
        start, rule, flags, intro, local_rules = _resolve_start(
            red,
            work_date=work_date,
            amending_texts=amending_act_texts,
            is_first_original=is_original,
        )
        for rr in local_rules:
            if rr not in rules_applied:
                rules_applied.append(rr)
        dated.append(
            _DatedRedaction(
                redaction=red,
                redaction_id=rid,
                start=start,
                end=None,
                end_unknown=False,
                rule=rule,
                flags=list(flags),
                intro_annotation=intro,
            )
        )

    if "R4" not in rules_applied:
        rules_applied.append("R4")
    revoked_at, rev_sem_data = _revocation_info(provision)
    if rev_sem_data:
        global_flags.append("revogacao_sem_data")

    for i, dr in enumerate(dated):
        if i + 1 < len(dated):
            nxt = dated[i + 1]
            if nxt.start is not None:
                dr.end = nxt.start
                dr.end_unknown = False
            else:
                # Sucessor existe mas início unknown → fim desconhecido (≠ aberto)
                dr.end = None
                dr.end_unknown = True
                if "fim_desconhecido" not in dr.flags:
                    dr.flags.append("fim_desconhecido")
        elif revoked_at is not None:
            dr.end = revoked_at
            dr.end_unknown = False
        elif rev_sem_data:
            dr.end = None
            dr.end_unknown = True
            if "fim_desconhecido" not in dr.flags:
                dr.flags.append("fim_desconhecido")
        else:
            # última sem revogação: aberta (vigente) — só se não superada
            if dr.redaction.struck or dr.redaction.superseded_without_strike:
                dr.end = None
                dr.end_unknown = True
                if "fim_desconhecido" not in dr.flags:
                    dr.flags.append("fim_desconhecido")
            else:
                dr.end = None
                dr.end_unknown = False

    return dated, rules_applied, needs_judgment, global_flags


def _is_current_query(data: str | None, today: date) -> bool:
    if data is None:
        return True
    d = _parse_iso(data)
    return d == today


def _capture_fresh(fetched_at: str | None, today: date) -> tuple[bool, list[str]]:
    """True se captura ≤ 30 dias. Sem fetched_at → não fresh (unknown)."""
    flags: list[str] = []
    dt = _parse_fetched_at(fetched_at)
    if dt is None:
        flags.append("CAPTURA_DESATUALIZADA")
        return False, flags
    if dt > datetime.now(_TZ_SP) + timedelta(minutes=5):
        return False, ["CAPTURA_DATA_INVALIDA"]
    age = today - dt.date()
    if age > _CAPTURE_MAX_AGE:
        flags.append("CAPTURA_DESATUALIZADA")
        return False, flags
    return True, flags


def _blocking_for_verified(flags: list[str], needs_judgment: bool) -> bool:
    if needs_judgment:
        return True
    return any(f in _BLOCKING_FLAGS or f.startswith("data_ano") for f in flags)


def _status_verified_or_unknown(
    interval: Interval,
    *,
    flags: list[str],
    needs_judgment: bool,
) -> str:
    if _blocking_for_verified(flags, needs_judgment):
        return "unknown"
    if interval.start is None:
        return "unknown"
    if interval.end_unknown:
        return "unknown"
    if interval.end is not None and _parse_iso(interval.end) is None:
        return "unknown"
    return "verified"


def _current_non_superseded(dated: list[_DatedRedaction]) -> _DatedRedaction | None:
    for d in reversed(dated):
        if d.redaction.struck or d.redaction.superseded_without_strike:
            continue
        if any(a.kind == "revogado" for a in d.redaction.annotations):
            continue
        return d
    return None


def select(
    provision: Provision,
    data: str | None = None,
    *,
    work_date: str | None = None,
    amending_act_texts: dict[str, str] | None = None,
    redaction_ids: list[str] | None = None,
    fetched_at: str | None = None,
    ambiguous: bool = False,
    quarantined: bool = False,
) -> TemporalResult:
    """Seleciona a redação aplicável em `data` (ISO) ou a vigente se data is None.

    `data` omitida = data atual em America/Sao_Paulo.
    `verified` só com limites conhecidos, vigência demonstrada e sem flags impeditivas.
    `vigente_na_fonte` para consulta atual sobre redação não superada da captura fresca.
    """
    if ambiguous:
        return TemporalResult(
            status="ambiguous",
            redaction_id=None,
            interval=None,
            rules_applied=[],
            flags=["dispositivo_ambiguo"],
            reason="DISPOSITIVO_AMBIGUO",
        )
    if quarantined:
        return TemporalResult(
            status="unknown",
            redaction_id=None,
            interval=None,
            rules_applied=[],
            flags=["DOCUMENTO_QUARENTENADO"],
            reason="DOCUMENTO_QUARENTENADO",
        )

    if not provision.redactions:
        return TemporalResult(
            status="unknown",
            redaction_id=None,
            interval=None,
            rules_applied=[],
            flags=["sem_redacao"],
            reason="HISTORICO_ANTERIOR_AUSENTE",
        )

    if provision.ambiguous:
        return TemporalResult(
            status="ambiguous",
            redaction_id=None,
            interval=None,
            rules_applied=[],
            flags=["dispositivo_ambiguo"],
            reason="DISPOSITIVO_AMBIGUO",
        )

    captured = _parse_fetched_at(fetched_at)
    if captured and captured > datetime.now(_TZ_SP) + timedelta(minutes=5):
        return TemporalResult("unknown", None, None,
                              flags=["CAPTURA_DATA_INVALIDA"], reason="CAPTURA_DATA_INVALIDA")

    dated, rules, needs_judgment, gflags = build_intervals(
        provision,
        work_date=work_date,
        amending_act_texts=amending_act_texts,
        redaction_ids=redaction_ids,
    )

    today = today_sp()
    query_omitted = data is None
    if query_omitted:
        target = today
        data_iso = today.isoformat()
    else:
        target = _parse_iso(data)
        data_iso = data
        if target is None:
            return TemporalResult(
                status="unknown",
                redaction_id=None,
                interval=None,
                rules_applied=rules,
                flags=["data_consulta_invalida"] + gflags,
                needs_judgment=needs_judgment,
            )

    current_query = _is_current_query(None if query_omitted else data_iso, today)
    revoked_at, rev_sem_data = _revocation_info(provision)

    # Revogação sem data: atual/omitida → revogado; histórica → unknown
    if rev_sem_data:
        if current_query:
            return TemporalResult(
                status="revogado",
                redaction_id=None,
                interval=None,
                rules_applied=rules,
                flags=gflags,
                needs_judgment=needs_judgment,
                reason="REVOGADO_SEM_DATA",
            )
        return TemporalResult(
            status="unknown",
            redaction_id=None,
            interval=None,
            rules_applied=rules,
            flags=gflags,
            needs_judgment=needs_judgment,
            reason="REVOGACAO_SEM_DATA",
        )

    # Revogado com data conhecida
    if revoked_at is not None:
        end_d = _parse_iso(revoked_at)
        if end_d and target >= end_d:
            return TemporalResult(
                status="revogado",
                redaction_id=None,
                interval=Interval(revoked_at, None),
                rules_applied=rules,
                flags=gflags,
                needs_judgment=needs_judgment,
            )

    # Revogação parcial sem resolução → unknown
    if _has_partial_revocation(provision):
        return TemporalResult(
            status="unknown",
            redaction_id=None,
            interval=None,
            rules_applied=rules,
            flags=list(dict.fromkeys(gflags + ["revogacao_parcial"])),
            needs_judgment=True,
            reason="REVOGACAO_PARCIAL",
        )

    # A data da obra prova inexistência anterior; alteração não prova inclusão.
    origin = _parse_iso(work_date)
    if origin and target < origin:
        return TemporalResult("nao_existia", None, None, rules_applied=rules)
    first_start = _parse_iso(dated[0].start) if dated[0].start else None
    if first_start and target < first_start:
        inclusion = dated[0].intro_annotation
        proven = inclusion is not None and inclusion.kind == "incluido"
        return TemporalResult(
            status="nao_existia" if proven else "unknown",
            redaction_id=None,
            interval=None,
            rules_applied=rules,
            flags=gflags,
            needs_judgment=needs_judgment,
            reason=None if proven else "HISTORICO_ANTERIOR_AUSENTE",
        )

    # Consulta atual: vigente_na_fonte se condições ok
    if current_query:
        future = [d for d in dated if _parse_iso(d.start) and _parse_iso(d.start) > target]
        future_year = any(
            a.kind in _INTRO_KINDS and _year_only(a.act_date, a.act_ref)
            and any(int(y) > target.year for y in re.findall(r"\b\d{4}\b", a.act_date or a.act_ref or ""))
            for d in dated for a in d.redaction.annotations
        )
        if future_year:
            return TemporalResult("unknown", None, None, rules_applied=rules,
                                  flags=gflags + ["data_ano_nao_resolvida"], reason="INICIO_SUCESSOR_DESCONHECIDO")
        if future:
            eligible = [d for d in dated if _parse_iso(d.start) and _parse_iso(d.start) <= target
                        and (not d.end or (_parse_iso(d.end) and target < _parse_iso(d.end)))]
            current = eligible[-1] if eligible else None
        else:
            current = _current_non_superseded(dated)
        if current is None:
            # Só superadas / revogadas — se fim unknown nas antigas, unknown
            return TemporalResult(
                status="unknown",
                redaction_id=None,
                interval=None,
                rules_applied=rules,
                flags=["sem_redacao_vigente"] + gflags,
                needs_judgment=needs_judgment,
            )
        # Nunca selecionar redação antiga (superada) para data atual
        if not future and (current.redaction.struck or current.redaction.superseded_without_strike):
            return TemporalResult(
                status="unknown",
                redaction_id=None,
                interval=None,
                rules_applied=rules,
                flags=gflags,
                needs_judgment=needs_judgment,
            )
        fresh, cap_flags = _capture_fresh(fetched_at, today)
        flags = list(current.flags) + gflags + cap_flags
        interval = Interval(current.start, current.end, current.end_unknown)
        if needs_judgment or any(
            a.kind in _JUDGMENT_KINDS for a in current.redaction.annotations
        ):
            return TemporalResult(
                status="unknown",
                redaction_id=current.redaction_id,
                interval=interval,
                rules_applied=rules,
                flags=flags,
                needs_judgment=True,
            )
        if not fresh:
            return TemporalResult(
                status="unknown",
                redaction_id=current.redaction_id,
                interval=interval,
                rules_applied=rules,
                flags=flags,
                needs_judgment=needs_judgment,
                reason="CAPTURA_DESATUALIZADA",
            )
        return TemporalResult(
            status="vigente_na_fonte",
            redaction_id=current.redaction_id,
            interval=interval,
            rules_applied=rules,
            flags=flags,
            needs_judgment=needs_judgment,
        )

    # Data histórica específica: achar intervalo
    chosen: _DatedRedaction | None = None
    for dr in dated:
        start_d = _parse_iso(dr.start)
        if dr.start is None or start_d is None:
            continue
        if target < start_d:
            continue
        if dr.end_unknown:
            # [início, ?) — unknown para qualquer data ≥ início; não seleciona
            if target >= start_d:
                return TemporalResult(
                    status="unknown",
                    redaction_id=None,
                    interval=Interval(dr.start, None, end_unknown=True),
                    rules_applied=rules,
                    flags=list(dr.flags) + gflags + ["fim_desconhecido"],
                    needs_judgment=needs_judgment,
                    reason="FIM_DESCONHECIDO",
                )
            continue
        end_d = _parse_iso(dr.end) if dr.end else None
        if end_d is not None and target >= end_d:
            continue
        if dr.end is not None and end_d is None:
            continue
        chosen = dr

    if chosen is None:
        # Redações com início unknown que poderiam cobrir
        if any(d.start is None for d in dated):
            return TemporalResult(
                status="unknown",
                redaction_id=None,
                interval=None,
                rules_applied=rules,
                flags=["intervalo_nao_resolvido"] + gflags,
                needs_judgment=needs_judgment,
                reason="HISTORICO_ANTERIOR_AUSENTE",
            )
        return TemporalResult(
            status="unknown",
            redaction_id=None,
            interval=None,
            rules_applied=rules,
            flags=["intervalo_nao_resolvido"] + gflags,
            needs_judgment=needs_judgment,
        )

    interval = Interval(chosen.start, chosen.end, chosen.end_unknown)
    flags = list(chosen.flags) + gflags
    status = _status_verified_or_unknown(
        interval, flags=flags, needs_judgment=needs_judgment
    )
    return TemporalResult(
        status=status,
        redaction_id=chosen.redaction_id,
        interval=interval,
        rules_applied=rules,
        flags=flags,
        needs_judgment=needs_judgment,
    )
