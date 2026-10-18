"""Conector TCU — dados abertos de acórdãos (UA identificado)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

from freoa_verifica.connectors.base import (
    Candidate,
    Connector,
    HealthProbe,
    HealthReport,
    ParsedDecision,
    Unavailable,
    register,
)
from freoa_verifica.connectors.httputil import connector_fetch
from freoa_verifica.transport import Response

_API = "https://dados-abertos.apps.tcu.gov.br/api/acordao/recupera-acordaos"
_HOSTS = frozenset(
    {
        "dados-abertos.apps.tcu.gov.br",
        "pesquisa.apps.tcu.gov.br",
        "contas.tcu.gov.br",
        "sites.tcu.gov.br",
    }
)
_PREFIXES = {
    "dados-abertos.apps.tcu.gov.br": ("/api/",),
    "pesquisa.apps.tcu.gov.br": ("/rest/",),
    "contas.tcu.gov.br": ("/sagas/", "/sisdoc/", "/pesquisaJurisprudencia/"),
    "sites.tcu.gov.br": ("/dados-abertos/",),
}
_MIMES = frozenset(
    {
        "application/json",
        "text/json",
        "text/plain",
        "application/octet-stream",
        "application/pdf",
        "text/html",
        "text/rtf",
        "application/rtf",
        "text/csv",
    }
)

MAX_QUANTIDADE = 100
MAX_PAGES = 20
MAX_SCAN = 500


@register
class TcuConnector(Connector):
    id = "tcu"
    authority = "Tribunal de Contas da União"
    hosts = _HOSTS
    path_prefixes = _PREFIXES
    mimes = _MIMES
    user_agent = "identified"  # UA de navegador cai em desafio F5/TSPD
    coverage = {
        "colecoes": ["acordaos"],
        "periodo": "acervo API recupera-acordaos",
        "busca_textual": True,
        "ementa": True,
        "inteiro_teor": True,
        "atualizacao": "sincronização incremental por inicio",
    }

    def health(self) -> HealthReport:
        probes: list[HealthProbe] = []
        try:
            found = self.search("", inicio=0, quantidade=2)
            probes.append(HealthProbe("positivo", "ok" if found else "failed", None))
        except Exception as exc:
            probes.append(HealthProbe("positivo", "unavailable", str(exc)[:200]))
        try:
            # negativo: offset absurdo ainda retorna lista; use filtro inexistente via busca
            empty = self.search("FV_TERM_INEXISTENTE_TCU_XYZ_999991", quantidade=5)
            probes.append(HealthProbe("negativo", "zero" if not empty else "failed", f"n={len(empty)}"))
        except Unavailable as exc:
            probes.append(HealthProbe("negativo", "unavailable", exc.reason))
        except Exception as exc:
            probes.append(HealthProbe("negativo", "unavailable", str(exc)[:200]))
        try:
            found = self.search("", inicio=0, quantidade=1)
            assert found
            parsed = self.parse(self.fetch(found[0]))
            probes.append(
                HealthProbe(
                    "documento",
                    "ok" if parsed.official_id else "failed",
                    parsed.official_id,
                )
            )
        except Exception as exc:
            probes.append(HealthProbe("documento", "unavailable", str(exc)[:200]))
        return HealthReport(
            self.id,
            tuple(probes),
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def search(self, q: str, **filtros: Any) -> list[Candidate]:
        inicio = int(filtros.get("inicio") or 0)
        quantidade = min(
            MAX_QUANTIDADE,
            max(1, int(filtros.get("quantidade") or filtros.get("limite") or 20)),
        )
        items = self._page(inicio=inicio, quantidade=quantidade)
        q_lower = (q or "").lower().strip()
        if not q_lower:
            return [_cand(self.id, it) for it in items]
        out = []
        cursor = inicio
        scanned = 0
        pages = 0
        while scanned < MAX_SCAN and pages < MAX_PAGES:
            batch = (
                items
                if cursor == inicio
                else self._page(inicio=cursor, quantidade=min(MAX_QUANTIDADE, quantidade))
            )
            pages += 1
            if not batch:
                break
            for it in batch:
                blob = " ".join(
                    str(it.get(k) or "")
                    for k in ("titulo", "sumario", "relator", "colegiado", "numeroAcordao")
                ).lower()
                if q_lower in blob:
                    out.append(_cand(self.id, it))
                    if len(out) >= quantidade:
                        return out
            scanned += len(batch)
            cursor += len(batch)
            if len(batch) < 1:
                break
        return out

    def resolve(self, key: Any) -> Candidate | None:
        if isinstance(key, dict):
            key = key.get("key") or key.get("numeroAcordao")
        if not key:
            return None
        key_s = str(key)
        if key_s.startswith("ACORDAO"):
            # varrer primeiras páginas
            for inicio in range(0, 200, 50):
                for it in self._page(inicio=inicio, quantidade=50):
                    if it.get("key") == key_s:
                        return _cand(self.id, it)
            return None
        # numero/ano
        m = re.match(r"(\d+)/(\d{4})", key_s)
        if m:
            num, ano = m.group(1), m.group(2)
            for inicio in range(0, 200, 50):
                for it in self._page(inicio=inicio, quantidade=50):
                    if str(it.get("numeroAcordao")) == num and str(it.get("dataSessao") or "")[-4:] == ano:
                        return _cand(self.id, it)
        return None

    def fetch(self, candidate: Candidate) -> Response:
        cache = getattr(self,'_captured_pages',{})
        if candidate.key in cache:
            return cache[candidate.key]
        for inicio in range(0,300,50):
            self._page(inicio=inicio,quantidade=50)
            cache = getattr(self,'_captured_pages',{})
            if candidate.key in cache:
                return cache[candidate.key]
        raise Unavailable('tcu_fora_do_recorte_capturado')

    def parse_candidate(self, resp, candidate):
        return self.parse(resp,key=candidate.key)

    def parse(self, resp: Response, *, key=None) -> ParsedDecision:
        item = json.loads(resp.body.decode("utf-8"))
        if isinstance(item, list):
            if not item:
                raise Unavailable("resposta_invalida")
            if key is not None:
                matches = [it for it in item if isinstance(it,dict) and _official_id(it) == key]
                if len(matches) != 1:
                    raise Unavailable("tcu_identidade_ambigua_ou_ausente")
                item = matches[0]
            else:
                item = item[0]
        if not isinstance(item, dict) or item.get("error") is not None:
            raise Unavailable("resposta_invalida")
        official = _official_id(item)
        if not official:
            raise Unavailable("resposta_invalida")
        docs = []
        for field, label in (
            ("urlArquivoPdf", "pdf"),
            ("urlArquivo", "rtf"),
            ("urlAcordao", "permalink"),
        ):
            if item.get(field):
                docs.append({"url": item[field], "label": label})
        data = item.get("dataSessao")
        data_iso = None
        if isinstance(data, str) and re.match(r"\d{2}/\d{2}/\d{4}", data):
            d, m, y = data.split("/")
            data_iso = f"{y}-{m}-{d}"
        # TCU é administrativa (E); preservar grafia do colegiado (ex.: Plenário).
        organ = item.get("colegiado")
        return ParsedDecision(
            profile="tcu_acordao",
            kind="administrativa",
            court="TCU",
            official_id=official,
            ementa=item.get("sumario"),
            text=str(item.get("sumario") or item.get("titulo") or ""),
            judgment_date=data_iso,
            rapporteur=item.get("relator"),
            organ=organ,
            class_name="Acordao",
            documents=docs,
            metadata={
                "numeroAcordao": item.get("numeroAcordao"),
                "anoAcordao": item.get("anoAcordao"),
                "titulo": item.get("titulo"),
                "situacao": item.get("situacao"),
                "orgao": organ,
            },
        )

    def sync(self, *, inicio: int = 0, quantidade: int = 100, max_pages: int = 10) -> list[dict]:
        """Sincronização incremental por `inicio`."""
        quantidade = min(MAX_QUANTIDADE, max(1, quantidade))
        max_pages = min(MAX_PAGES, max(1, max_pages))
        all_items: list[dict] = []
        cursor = inicio
        for _ in range(max_pages):
            batch = self._page(inicio=cursor, quantidade=quantidade)
            if not batch:
                break
            all_items.extend(batch)
            cursor += len(batch)
            if len(batch) < quantidade:
                break
        return all_items

    def _page(self, *, inicio: int, quantidade: int) -> list[dict[str, Any]]:
        quantidade = min(MAX_QUANTIDADE, max(1, quantidade))
        url = _API + "?" + urlencode({"inicio": inicio, "quantidade": quantidade})
        resp = connector_fetch(
            url,
            hosts=self.hosts,
            path_prefixes=self.path_prefixes,
            mimes=self.mimes,
            user_agent=self.user_agent,
            timeout=60.0,
        )
        try:
            payload = json.loads(resp.body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise Unavailable("resposta_invalida") from exc
        if not isinstance(payload, list):
            raise Unavailable("resposta_invalida")
        out: list[dict[str, Any]] = []
        for x in payload:
            if not isinstance(x, dict):
                raise Unavailable("resposta_invalida")
            if x.get("error") is not None:
                raise Unavailable("resposta_invalida")
            if not _official_id(x):
                raise Unavailable("resposta_invalida")
            out.append(x)
        if not hasattr(self,"_captured_pages"):
            self._captured_pages = {}
        for item in out:
            self._captured_pages[_official_id(item)] = resp
        while len(self._captured_pages) > 4096:
            self._captured_pages.pop(next(iter(self._captured_pages)))
        return out


def _official_id(it: dict[str, Any]) -> str | None:
    key = it.get("key")
    if key is not None and str(key).strip() and "None" not in str(key):
        return str(key)
    num, ano = it.get("numeroAcordao"), it.get("anoAcordao")
    if num is None or ano is None or str(num) in {"", "None"} or str(ano) in {"", "None"}:
        return None
    return f"{num}/{ano}"


def _cand(source_id: str, it: dict[str, Any]) -> Candidate:
    key = _official_id(it)
    if not key:
        raise Unavailable("resposta_invalida")
    return Candidate(
        source_id=source_id,
        key=key,
        title=str(it.get("titulo") or key),
        url=it.get("urlAcordao"),
        snippet=(it.get("sumario") or "")[:300] or None,
        metadata=dict(it),
    )
