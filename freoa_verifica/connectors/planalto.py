"""Conector Planalto — leis federais em HTML."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from freoa_verifica.connectors.base import (
    Candidate,
    Connector,
    HealthProbe,
    HealthReport,
    Unavailable,
    register,
)
from freoa_verifica.connectors.httputil import connector_fetch
from freoa_verifica.parsers.planalto import parse_planalto
from freoa_verifica.transport import HTTPStatusError, Response

_BASE = "https://www.planalto.gov.br"
_URLS_PATH = Path(__file__).with_name("planalto_urls.json")

_ATO_RANGES: list[tuple[int, int, str]] = [
    (2004, 2006, "2004-2006"),
    (2007, 2010, "2007-2010"),
    (2011, 2014, "2011-2014"),
    (2015, 2018, "2015-2018"),
    (2019, 2022, "2019-2022"),
    (2023, 2026, "2023-2026"),
]


def _load_known_urls() -> dict[str, list[str]]:
    if not _URLS_PATH.is_file():
        return {}
    return json.loads(_URLS_PATH.read_text(encoding="utf-8"))


KNOWN_URLS = _load_known_urls()


def work_key(tipo: str, numero: int | str, ano: int | str | None = None) -> str:
    tipo_u = tipo.strip().upper()
    if tipo_u in {"CF", "CONSTITUICAO", "CONSTITUIÇÃO"}:
        return "CF:1988"
    num = str(numero).replace(".", "").lstrip("0") or "0"
    if ano is None:
        return f"{tipo_u}:{num}"
    return f"{tipo_u}:{num}:{int(ano)}"


def ato_faixa(ano: int) -> str | None:
    for start, end, label in _ATO_RANGES:
        if start <= ano <= end:
            return label
    return None


def generate_lei_urls(numero: int, ano: int) -> list[str]:
    """Gera candidatas de URL (compilado primeiro, depois original)."""
    n = str(int(numero))
    urls: list[str] = []

    def add(path: str) -> None:
        full = f"{_BASE}{path}" if path.startswith("/") else path
        if full not in urls:
            urls.append(full)

    if ano < 2000:
        for suffix in ("compilada", "compilado", "consol", ""):
            stem = f"l{n}{suffix}" if suffix else f"l{n}"
            add(f"/ccivil_03/leis/{stem}.htm")
    elif ano < 2002:
        for suffix in ("compilada", "compilado", "consol", ""):
            stem = f"l{n}{suffix}" if suffix else f"l{n}"
            add(f"/ccivil_03/leis/leis_{ano}/{stem}.htm")
            add(f"/ccivil_03/leis/{stem}.htm")
    elif ano == 2002:
        for suffix in ("compilada", "compilado", ""):
            stem = f"l{n}{suffix}" if suffix else f"l{n}"
            add(f"/ccivil_03/leis/2002/{stem}.htm")
    elif ano == 2003:
        # padrão com ponto: L10.639
        dotted = f"{n[:-3]}.{n[-3:]}" if len(n) > 3 else n
        for prefix in (f"l{dotted}", f"L{dotted}", f"l{n}", f"L{n}"):
            for suffix in ("compilado", "compilada", ""):
                stem = f"{prefix}{suffix}" if suffix else prefix
                add(f"/ccivil_03/leis/2003/{stem}.htm")
    else:
        faixa = ato_faixa(ano)
        if faixa:
            for suffix in ("compilada", "compilado", ""):
                stem = f"l{n}{suffix}" if suffix else f"l{n}"
                add(f"/ccivil_03/_ato{faixa}/{ano}/lei/{stem}.htm")
    return urls


def urls_for_work(tipo: str, numero: int | str, ano: int | str | None = None) -> list[str]:
    key = work_key(tipo, numero, ano)
    known = list(KNOWN_URLS.get(key, []))
    tipo_u = tipo.strip().upper()
    if tipo_u == "LEI" and ano is not None:
        for u in generate_lei_urls(int(str(numero).replace(".", "")), int(ano)):
            if u not in known:
                known.append(u)
    elif tipo_u == "LCP":
        n = str(numero).replace(".", "")
        for suffix in ("compilado", "compilada", ""):
            stem = f"lcp{n}{suffix}" if suffix else f"lcp{n}"
            u = f"{_BASE}/ccivil_03/leis/lcp/{stem}.htm"
            if u not in known:
                known.append(u)
    elif tipo_u in {"DEL", "DECRETO-LEI"}:
        n = str(numero).replace(".", "")
        for suffix in ("compilado", "compilada", ""):
            stem = f"del{n}{suffix}" if suffix else f"del{n}"
            u = f"{_BASE}/ccivil_03/decreto-lei/{stem}.htm"
            if u not in known:
                known.append(u)
    elif tipo_u in {"MPV", "MP", "MEDIDA_PROVISORIA"} and ano:
        n = str(numero).replace(".", "")
        faixa = ato_faixa(int(ano))
        if faixa:
            for stem in ((f"mpv{n}", n) if int(ano) >= 2011 else (n, f"mpv{n}")):
                known.append(f"{_BASE}/ccivil_03/_Ato{faixa}/{ano}/Mpv/{stem}.htm")
        else:
            known.append(f"{_BASE}/ccivil_03/MPV/{n}.htm")
    elif key == "CF:1988":
        for u in (
            f"{_BASE}/ccivil_03/constituicao/constituicaocompilado.htm",
            f"{_BASE}/ccivil_03/constituicao/constituicao.htm",
        ):
            if u not in known:
                known.append(u)
    return known


@register
class PlanaltoConnector(Connector):
    id = "planalto"
    authority = "Presidência da República / Planalto"
    hosts = frozenset({"www.planalto.gov.br", "planalto.gov.br"})
    path_prefixes = {
        "www.planalto.gov.br": ("/ccivil_03/",),
        "planalto.gov.br": ("/ccivil_03/",),
    }
    mimes = frozenset({"text/html", "application/xhtml+xml", "text/plain"})
    user_agent = "browser"
    coverage = {
        "colecoes": ["leis", "lcp", "decreto-lei", "constituicao"],
        "periodo": "variavel por espécie",
        "busca_textual": False,
        "ementa": True,
        "inteiro_teor": True,
        "atualizacao": "sob demanda (HTTP)",
    }

    def health(self) -> HealthReport:
        probes: list[HealthProbe] = []
        # positivo: LSA conhecida
        try:
            cand = self.resolve({"tipo": "LEI", "numero": 6404, "ano": 1976})
            assert cand is not None
            resp = self.fetch(cand)
            ok = b"6.404" in resp.body or b"6404" in resp.body
            probes.append(
                HealthProbe("positivo", "ok" if ok else "failed", cand.url)
            )
        except Exception as exc:
            probes.append(HealthProbe("positivo", "unavailable", str(exc)[:200]))
        # negativo: lei inexistente
        try:
            urls = generate_lei_urls(999999, 2026)
            connector_fetch(
                urls[0],
                hosts=self.hosts,
                path_prefixes=self.path_prefixes,
                mimes=self.mimes,
                user_agent=self.user_agent,
                timeout=20.0,
            )
            probes.append(HealthProbe("negativo", "failed", "esperava 404"))
        except Unavailable as exc:
            if "http_404" in exc.reason:
                probes.append(HealthProbe("negativo", "ok", exc.reason))
            else:
                probes.append(HealthProbe("negativo", "unavailable", exc.reason))
        except Exception as exc:
            probes.append(HealthProbe("negativo", "unavailable", str(exc)[:200]))
        # documento: parse LSA fixture-like fetch
        try:
            cand = self.resolve({"tipo": "LEI", "numero": 6404, "ano": 1976})
            assert cand is not None
            doc = self.parse(self.fetch(cand))
            probes.append(
                HealthProbe(
                    "documento",
                    "ok" if doc.title and doc.provisions else "failed",
                    doc.title[:80] if doc.title else None,
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
        # Planalto não tem busca textual própria; resolve padrão "Lei N/AAAA".
        m = re.search(
            r"(?i)\b(?:lei|lcp|del|decreto-?lei)\s*n?[ºo°.]?\s*([\d.]+)\s*(?:/|,|\s+de\s+)?\s*(\d{4})?",
            q or "",
        )
        if not m:
            raise Unavailable("resposta_inesperada")
        tipo_raw = (q or "").lower()
        if "lcp" in tipo_raw or "complementar" in tipo_raw:
            tipo = "LCP"
        elif "decreto-lei" in tipo_raw or re.search(r"\bdel\b", tipo_raw):
            tipo = "DEL"
        else:
            tipo = "LEI"
        numero = m.group(1).replace(".", "")
        ano = m.group(2) or filtros.get("ano")
        cand = self.resolve({"tipo": tipo, "numero": numero, "ano": ano})
        return [cand] if cand else []

    def resolve(self, key: Any) -> Candidate | None:
        tipo, numero, ano = _parse_key(key)
        if tipo is None or numero is None:
            return None
        urls = urls_for_work(tipo, numero, ano)
        if not urls:
            return None
        wk = work_key(tipo, numero, ano)
        return Candidate(
            source_id=self.id,
            key=wk,
            title=f"{tipo} {numero}" + (f"/{ano}" if ano else ""),
            url=urls[0],
            metadata={"tipo": tipo, "numero": str(numero), "ano": ano, "urls": urls},
        )

    def fetch(self, candidate: Candidate) -> Response:
        urls = list(candidate.metadata.get("urls") or [])
        if candidate.url and candidate.url not in urls:
            urls.insert(0, candidate.url)
        if not urls:
            raise Unavailable("sem_url")
        last_err = None
        for url in urls:
            for attempt in range(3):
                if attempt:
                    time.sleep(2 ** attempt)
                try:
                    return connector_fetch(url, hosts=self.hosts, path_prefixes=self.path_prefixes,
                        mimes=self.mimes, user_agent=self.user_agent, timeout=180.0,
                        min_bytes_per_second=256, max_bytes=30 * 1024 * 1024)
                except Unavailable as exc:
                    last_err = exc
                    if exc.reason == "http_404":
                        break
                    if attempt < 2 and exc.reason in {"transporte_Timeout", "transporte_lento", "transporte_TransporteLento", "http_503", "http_502", "http_504"}:
                        continue
                    raise
        raise Unavailable(last_err.reason if last_err else "sem_url")

    def parse(self, resp: Response):
        from freoa_verifica.parsers.isolated import parse_ou_indisponivel
        return parse_ou_indisponivel("planalto", resp.body, 300.0, base_url=resp.final_url)

    def resolve_alterador_date(self, tipo: str, numero: int | str, ano: int) -> str | None:
        """Resolve data completa via Senado quando o Planalto cita só o ano."""
        from freoa_verifica.connectors.senado import SenadoConnector

        cand = SenadoConnector().resolve({"tipo": tipo, "numero": numero, "ano": ano})
        if cand is None:
            return None
        return cand.metadata.get("dataassinatura_iso")


def _parse_key(key: Any) -> tuple[str | None, str | None, int | None]:
    if isinstance(key, str):
        parts = key.split(":")
        if parts[0].upper() == "CF":
            return "CF", "1988", 1988
        if len(parts) >= 3:
            return parts[0].upper(), parts[1], int(parts[2])
        if len(parts) == 2:
            return parts[0].upper(), parts[1], None
        return None, None, None
    if isinstance(key, dict):
        tipo = str(key.get("tipo") or key.get("kind") or "LEI").upper()
        numero = key.get("numero") or key.get("number")
        ano = key.get("ano") or key.get("year")
        if numero is None:
            return None, None, None
        return tipo, str(numero).replace(".", ""), int(ano) if ano else None
    return None, None, None
