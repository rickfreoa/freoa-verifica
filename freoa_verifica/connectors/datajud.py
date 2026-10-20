"""Conector DataJud CNJ — metadados processuais (não há índice STF)."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any

from freoa_verifica.connectors.base import (
    Candidate,
    CandidateList,
    Connector,
    HealthProbe,
    HealthReport,
    ParsedDecision,
    Unavailable,
    register,
)
from freoa_verifica.connectors.httputil import connector_fetch
from freoa_verifica.transport import Response

# Chave pública documentada na wiki DataJud (não é segredo).
_DEFAULT_KEY = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="

_HOSTS = frozenset({"api-publica.datajud.cnj.jus.br"})
_PREFIXES = {"api-publica.datajud.cnj.jus.br": ("/api_publica_",)}
_MIMES = frozenset({"application/json", "text/json", "text/plain", "application/octet-stream"})

MAX_ROWS = 100


def _api_key() -> str:
    return (os.environ.get("FV_DATAJUD_KEY") or _DEFAULT_KEY).strip()


def normalize_cnj(numero: str) -> str:
    digits = re.sub(r"\D", "", numero or "")
    return digits


def _is_publico(src: dict[str, Any]) -> bool:
    """Só emite quando nivelSigilo == 0 explícito (int ou str '0')."""
    if "nivelSigilo" not in src:
        return False
    nivel = src.get("nivelSigilo")
    if nivel is None:
        return False
    try:
        return int(nivel) == 0
    except (TypeError, ValueError):
        return False


@register
class DatajudConnector(Connector):
    id = "datajud"
    authority = "CNJ DataJud"
    hosts = _HOSTS
    path_prefixes = _PREFIXES
    mimes = _MIMES
    user_agent = "identified"
    coverage = {
        "colecoes": ["metadados_processuais"],
        "periodo": "conforme tribunal",
        "busca_textual": False,
        "ementa": False,
        "inteiro_teor": False,
        "atualizacao": "API pública Elasticsearch",
        "nota": "Sem índice do STF (404). Usado para confirmar existência de número CNJ.",
    }

    def __init__(self) -> None:
        self.descartados_sigilo = 0

    def health(self) -> HealthReport:
        probes: list[HealthProbe] = []
        try:
            # positivo: busca ampla TJSP size=1
            found = self.search("", tribunal="tjsp", limite=1)
            probes.append(HealthProbe("positivo", "ok" if found else "failed", None))
        except Exception as exc:
            probes.append(HealthProbe("positivo", "unavailable", str(exc)[:200]))
        try:
            empty = self.search("", tribunal="tjsp", numero="00000000000000000000", limite=1)
            probes.append(HealthProbe("negativo", "zero" if not empty else "failed", f"n={len(empty)}"))
        except Unavailable as exc:
            probes.append(HealthProbe("negativo", "unavailable", exc.reason))
        except Exception as exc:
            probes.append(HealthProbe("negativo", "unavailable", str(exc)[:200]))
        try:
            # documento / STF ausente
            self.search("", tribunal="stf", limite=1)
            probes.append(HealthProbe("documento", "failed", "stf deveria 404"))
        except Unavailable as exc:
            if "404" in exc.reason or "stf" in exc.reason:
                probes.append(HealthProbe("documento", "ok", exc.reason))
            else:
                probes.append(HealthProbe("documento", "unavailable", exc.reason))
        except Exception as exc:
            probes.append(HealthProbe("documento", "unavailable", str(exc)[:200]))
        return HealthReport(
            self.id,
            tuple(probes),
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def search(self, q: str, **filtros: Any) -> list[Candidate]:
        tribunal = str(filtros.get("tribunal") or "tjsp").lower()
        if tribunal == "stf":
            raise Unavailable("datajud_stf_inexistente")
        numero = filtros.get("numero") or filtros.get("cnj")
        if not numero and q:
            digits = normalize_cnj(q)
            if len(digits) >= 20:
                numero = digits
        size = min(MAX_ROWS, max(1, int(filtros.get("limite") or 10)))
        if numero:
            query = {"match": {"numeroProcesso": normalize_cnj(str(numero))}}
        else:
            # match_all é lento; amostra por grau recente
            query = {"term": {"grau.keyword": "G2"}} if filtros.get("match_all") else {
                "bool": {
                    "must": [{"exists": {"field": "numeroProcesso"}}],
                }
            }
        body = {"size": size, "query": query}
        return self._search_body(tribunal, body)

    def resolve(self, key: Any) -> Candidate | None:
        if isinstance(key, dict):
            tribunal = str(key.get("tribunal") or "tjsp").lower()
            numero = key.get("numero") or key.get("cnj")
        elif isinstance(key, str):
            if ":" in key:
                tribunal, numero = key.split(":", 1)
            else:
                tribunal, numero = "tjsp", key
        else:
            return None
        found = self.search("", tribunal=tribunal, numero=numero, limite=1)
        return found[0] if found else None

    def fetch(self, candidate: Candidate) -> Response:
        tribunal = candidate.metadata.get("tribunal", "tjsp")
        numero = candidate.metadata.get("numeroProcesso") or candidate.key
        body = {
            "size": 1,
            "query": {"match": {"numeroProcesso": normalize_cnj(str(numero))}},
        }
        return self._post(tribunal, body)

    def parse(self, resp: Response) -> ParsedDecision:
        payload = json.loads(resp.body.decode("utf-8"))
        if payload.get("timed_out") is True:
            raise Unavailable("resposta_invalida")
        hits = (((payload.get("hits") or {}).get("hits")) or [])
        src = (hits[0].get("_source") if hits else {}) or {}
        if not _is_publico(src):
            raise Unavailable("resposta_invalida")
        official = str(src.get("numeroProcesso") or src.get("id") or "")
        if not official:
            raise Unavailable("resposta_invalida")
        return ParsedDecision(
            profile="datajud_proceeding",
            kind="proceeding",
            court=str(src.get("tribunal") or ""),
            official_id=official,
            ementa=None,
            text="",
            class_name=(src.get("classe") or {}).get("nome")
            if isinstance(src.get("classe"), dict)
            else None,
            organ=(src.get("orgaoJulgador") or {}).get("nome")
            if isinstance(src.get("orgaoJulgador"), dict)
            else None,
            cnj_number=src.get("numeroProcesso"),
            metadata={
                "grau": src.get("grau"),
                "assuntos": src.get("assuntos"),
                "movimentos_count": len(src.get("movimentos") or []),
                "dataAjuizamento": src.get("dataAjuizamento"),
                "nivelSigilo": src.get("nivelSigilo"),
            },
        )

    def _search_body(self, tribunal: str, body: dict[str, Any]) -> list[Candidate]:
        resp = self._post(tribunal, body)
        try:
            payload = json.loads(resp.body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise Unavailable("resposta_invalida") from exc
        if payload.get("timed_out") is True:
            raise Unavailable("resposta_invalida")
        hits_wrap = payload.get("hits")
        if not isinstance(hits_wrap, dict) or "hits" not in hits_wrap:
            raise Unavailable("resposta_invalida")
        total = hits_wrap.get("total")
        total_n = total.get("value") if isinstance(total, dict) else total
        relacao = total.get("relation") if isinstance(total, dict) else None
        total_exato = None if relacao is None else relacao == "eq"
        hits = hits_wrap.get("hits") or []
        if total_n == 0:
            self.descartados_sigilo = 0
            return CandidateList([], total=0, total_exato=total_exato)
        if total_n and int(total_n) > 0 and not hits:
            raise Unavailable("resposta_invalida")
        out: list[Candidate] = []
        descartados = 0
        for hit in hits:
            src = hit.get("_source") or {}
            if not _is_publico(src):
                descartados += 1
                continue
            numero = str(src.get("numeroProcesso") or "")
            if not numero:
                descartados += 1
                continue
            classe = src.get("classe") or {}
            title = f"{classe.get('nome') or 'processo'} {numero}".strip()
            out.append(
                Candidate(
                    source_id=self.id,
                    key=f"{src.get('tribunal') or tribunal}:{numero}",
                    title=title,
                    metadata={
                        "tribunal": src.get("tribunal") or tribunal.upper(),
                        "numeroProcesso": numero,
                        "grau": src.get("grau"),
                        "classe": classe,
                        "orgaoJulgador": src.get("orgaoJulgador"),
                        "assuntos": src.get("assuntos"),
                        "nivelSigilo": src.get("nivelSigilo"),
                        "kind": "proceeding",
                    },
                )
            )
        self.descartados_sigilo = descartados
        informado = total_n if isinstance(total_n, int) and not isinstance(total_n, bool) else None
        return CandidateList(out, total=informado, total_exato=total_exato)

    def _post(self, tribunal: str, body: dict[str, Any]) -> Response:
        tribunal = tribunal.strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9]{1,15}",tribunal):
            raise Unavailable("tribunal_invalido")
        url = f"https://api-publica.datajud.cnj.jus.br/api_publica_{tribunal}/_search"
        payload = json.dumps(body).encode("utf-8")
        return connector_fetch(
            url,
            hosts=self.hosts,
            path_prefixes=self.path_prefixes,
            mimes=self.mimes,
            user_agent=self.user_agent,
            method="POST",
            body=payload,
            headers={
                "Authorization": f"APIKey {_api_key()}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=120.0,
        )


def court_from_cnj(number: str) -> str | None:
    digits = normalize_cnj(number)
    if len(digits) != 20:
        return None
    justice, region = int(digits[13]), int(digits[14:16])
    if justice == 3 and region == 0:
        return 'stj'
    if justice == 4 and 1 <= region <= 6:
        return f'trf{region}'
    if justice == 5:
        return 'tst' if region == 0 else (f'trt{region}' if 1 <= region <= 24 else None)
    if justice == 8:
        states = ['ac','al','ap','am','ba','ce','dft','es','go','ma','mt','ms','mg','pa','pb','pr','pe','pi','rj','rn','rs','ro','rr','sc','se','sp','to']
        if 1 <= region <= len(states):
            return 'tj' + states[region-1]
    return None
