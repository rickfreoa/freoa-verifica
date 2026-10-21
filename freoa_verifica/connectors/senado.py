"""Conector Senado Dados Abertos — identidade e data de normas."""

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
    Unavailable,
    register,
)
from freoa_verifica.connectors.httputil import connector_fetch
from freoa_verifica.identidade_http import UA_POR_CONECTOR
from freoa_verifica.texto_resposta import texto_do_response
from freoa_verifica.transport import Response

_TIPOS = frozenset({"LEI", "LCP", "DEL", "MPV", "DEC", "EMC", "DLG", "DSN"})
_JSON_MIMES = frozenset(
    {
        "application/json",
        "text/json",
        "text/plain",
        "application/octet-stream",
    }
)


def _parse_br_date(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(value[:10] if fmt != "%d/%m/%Y" else value, fmt).date().isoformat()
        except ValueError:
            continue
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", value)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return None


def _lexml_urn(tipo: str, numero: str, data_iso: str | None) -> str | None:
    if not data_iso:
        return None
    kind = {
        "LEI": "lei",
        "LCP": "lei.complementar",
        "DEL": "decreto.lei",
        "MPV": "medida.provisoria",
        "DEC": "decreto",
    }.get(tipo.upper(), tipo.lower())
    return f"urn:lex:br:federal:{kind}:{data_iso};{numero}"


def _docs_from_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    # ListaDocumento.documentos.documento[] ou DetalheDocumento...
    for root_key in ("ListaDocumento", "DetalheDocumento", "listaDocumento", "detalheDocumento"):
        root = payload.get(root_key)
        if isinstance(root, dict):
            payload = {**payload, **root}
    docs = payload.get("documentos") or payload.get("Documento")
    if isinstance(docs, dict):
        doc = docs.get("documento") or docs.get("Documento")
        if isinstance(doc, list):
            return [d for d in doc if isinstance(d, dict)]
        if isinstance(doc, dict):
            return [doc]
    if isinstance(payload.get("documento"), list):
        return [d for d in payload["documento"] if isinstance(d, dict)]
    return []


@register
class SenadoConnector(Connector):
    id = "senado"
    authority = "Senado Federal / Dados Abertos"
    hosts = frozenset({"legis.senado.leg.br", "normas.leg.br"})
    path_prefixes = {
        "legis.senado.leg.br": ("/dadosabertos/", "/sigen/", "/norma/"),
        "normas.leg.br": ("/api/", "/"),
    }
    mimes = _JSON_MIMES | frozenset({"text/html", "application/xhtml+xml", "text/xml", "application/xml"})
    user_agent = UA_POR_CONECTOR["senado"]
    coverage = {
        "colecoes": sorted(_TIPOS),
        "periodo": "acervo Sigen",
        "busca_textual": True,
        "ementa": True,
        "inteiro_teor": False,
        "atualizacao": "API dados abertos",
    }

    def health(self) -> HealthReport:
        probes: list[HealthProbe] = []
        try:
            found = self.search("", tipo="LEI", numero=10303, ano=2001)
            probes.append(
                HealthProbe("positivo", "ok" if found else "failed", found[0].key if found else None)
            )
        except Exception as exc:
            probes.append(HealthProbe("positivo", "unavailable", str(exc)[:200]))
        try:
            empty = self.search("", tipo="LEI", numero=999999, ano=2099)
            probes.append(HealthProbe("negativo", "zero" if not empty else "failed", f"n={len(empty)}"))
        except Unavailable as exc:
            probes.append(HealthProbe("negativo", "unavailable", exc.reason))
        except Exception as exc:
            probes.append(HealthProbe("negativo", "unavailable", str(exc)[:200]))
        try:
            cand = self.resolve({"tipo": "LEI", "numero": 10303, "ano": 2001})
            assert cand is not None
            resp = self.fetch(cand)
            doc = self.parse(resp)
            probes.append(
                HealthProbe(
                    "documento",
                    "ok" if cand.metadata.get("dataassinatura_iso") or doc.ementa else "failed",
                    cand.metadata.get("norma"),
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
        tipo = str(filtros.get("tipo") or "LEI").upper()
        if tipo not in _TIPOS:
            tipo = "LEI"
        numero = filtros.get("numero")
        ano = filtros.get("ano")
        if numero is None and q:
            m = re.search(r"(\d[\d.]*)\s*/?\s*(\d{4})?", q)
            if m:
                numero = m.group(1).replace(".", "")
                ano = ano or m.group(2)
        if numero is None:
            # busca textual Sigen
            return self._search_sigen(q, **filtros)
        params: dict[str, Any] = {"tipo": tipo, "numero": int(str(numero).replace(".", ""))}
        if ano:
            params["ano"] = int(ano)
        url = "https://legis.senado.leg.br/dadosabertos/legislacao/lista?" + urlencode(params)
        resp = connector_fetch(
            url,
            hosts=self.hosts,
            path_prefixes=self.path_prefixes,
            mimes=self.mimes,
            user_agent=self.user_agent,
            headers={"Accept": "application/json"},
            timeout=45.0,
        )
        try:
            payload = json.loads(texto_do_response(resp))
        except json.JSONDecodeError as exc:
            raise Unavailable("resposta_inesperada") from exc
        docs = _docs_from_payload(payload)
        if not docs:
            # marcador estrutural: lista vazia explícita
            if isinstance(payload, dict) and (
                "ListaDocumento" in payload
                or "documentos" in payload
                or payload.get("documentos") == {}
            ):
                return []
            raise Unavailable("resposta_inesperada")
        return [self._candidate_from_doc(d, tipo) for d in docs]

    def resolve(self, key: Any) -> Candidate | None:
        tipo, numero, ano = _parse_key(key)
        if tipo is None or numero is None or ano is None:
            return None
        found = self.search("", tipo=tipo, numero=numero, ano=ano)
        return found[0] if found else None

    def fetch(self, candidate: Candidate) -> Response:
        doc_id = candidate.metadata.get("id")
        if doc_id:
            url = f"https://legis.senado.leg.br/dadosabertos/legislacao/{doc_id}"
        else:
            tipo = candidate.metadata.get("tipo", "LEI")
            numero = candidate.metadata.get("numero")
            ano = candidate.metadata.get("ano")
            url = (
                f"https://legis.senado.leg.br/dadosabertos/legislacao/"
                f"{tipo}/{numero}/{ano}"
            )
        return connector_fetch(
            url,
            hosts=self.hosts,
            path_prefixes=self.path_prefixes,
            mimes=self.mimes,
            user_agent=self.user_agent,
            headers={"Accept": "application/json"},
            timeout=45.0,
        )

    def parse(self, resp: Response):
        from freoa_verifica.parsers.model import ParsedDocument

        payload = json.loads(texto_do_response(resp))
        docs = _docs_from_payload(payload)
        doc = docs[0] if docs else {}
        ident = doc.get("identificacao") if isinstance(doc.get("identificacao"), dict) else doc
        title = str(
            (ident or {}).get("normaNome")
            or doc.get("normaNome")
            or doc.get("norma")
            or doc.get("descricao")
            or ""
        )
        ementa = doc.get("ementa") or (ident or {}).get("ementa")
        return ParsedDocument(
            profile="senado_norma",
            parser_version="senado-1",
            title=title,
            ementa=str(ementa) if ementa else None,
            text=json.dumps(doc, ensure_ascii=False, indent=2) if doc else "",
            provisions=[],
            issues=[],
        )

    def _candidate_from_doc(self, doc: dict[str, Any], tipo_default: str) -> Candidate:
        ident = doc.get("identificacao") if isinstance(doc.get("identificacao"), dict) else {}
        norma = str(doc.get("norma") or ident.get("norma") or "")
        numero = str(doc.get("numero") or ident.get("numero") or "")
        tipo = str(doc.get("tipo") or ident.get("tipo") or tipo_default).upper()
        tipo = tipo.split("-")[0] if "-" in tipo else tipo
        if tipo not in _TIPOS:
            tipo = tipo_default
        data_br = doc.get("dataassinatura") or ident.get("dataassinatura")
        data_iso = _parse_br_date(str(data_br) if data_br else None)
        ano = doc.get("anoassinatura") or (data_iso[:4] if data_iso else None)
        ementa = doc.get("ementa") or ident.get("ementa")
        doc_id = str(doc.get("id") or ident.get("id") or "")
        urn = _lexml_urn(tipo, numero, data_iso)
        title = str(doc.get("normaNome") or ident.get("normaNome") or norma or f"{tipo} {numero}")
        return Candidate(
            source_id=self.id,
            key=f"senado:{doc_id or norma or f'{tipo}-{numero}-{ano}'}",
            title=title,
            url=f"https://legis.senado.leg.br/dadosabertos/legislacao/{doc_id}" if doc_id else None,
            snippet=str(ementa)[:300] if ementa else None,
            metadata={
                "id": doc_id,
                "tipo": tipo,
                "numero": numero,
                "ano": int(ano) if ano else None,
                "norma": norma,
                "dataassinatura": data_br,
                "dataassinatura_iso": data_iso,
                "ementa": ementa,
                "alias": "senado_norma",
                "urn_lexml_gerada": urn,
            },
        )

    def _search_sigen(self, q: str, **filtros: Any) -> list[Candidate]:
        if not (q or "").strip():
            raise Unavailable("resposta_inesperada")
        params = {
            "q": q.strip(),
            "pagina": int(filtros.get("pagina") or 0),
            "tamanhoPagina": int(filtros.get("limite") or 10),
        }
        if filtros.get("ano_inicial"):
            params["anoInicial"] = int(filtros["ano_inicial"])
        if filtros.get("ano_final"):
            params["anoFinal"] = int(filtros["ano_final"])
        url = "https://legis.senado.leg.br/sigen/api/catalogo/basico?" + urlencode(params)
        resp = connector_fetch(
            url,
            hosts=self.hosts,
            path_prefixes=self.path_prefixes,
            mimes=self.mimes,
            user_agent=self.user_agent,
            headers={"Accept": "application/json"},
            timeout=45.0,
        )
        try:
            payload = json.loads(texto_do_response(resp))
        except json.JSONDecodeError as exc:
            raise Unavailable("resposta_inesperada") from exc
        total = payload.get("totalHits")
        hits = payload.get("searchHits") or []
        if total == 0 or (isinstance(total, int) and total == 0):
            return []
        if not hits and total is None:
            raise Unavailable("resposta_inesperada")
        out: list[Candidate] = []
        for hit in hits:
            content = hit.get("content") if isinstance(hit, dict) else None
            if not isinstance(content, dict):
                continue
            out.append(
                Candidate(
                    source_id=self.id,
                    key=f"sigen:{content.get('urn') or content.get('nome')}",
                    title=str(content.get("nome") or ""),
                    snippet=str(content.get("ementa") or "")[:300] or None,
                    metadata={
                        "urn": content.get("urn"),
                        "status": content.get("status"),
                        "ementa": content.get("ementa"),
                        "alias": "senado_norma",
                        "urn_lexml_gerada": content.get("urn"),
                    },
                )
            )
        return out


def _parse_key(key: Any) -> tuple[str | None, str | None, int | None]:
    if isinstance(key, str):
        parts = key.split(":")
        if len(parts) >= 3:
            return parts[0].upper(), parts[1], int(parts[2])
        return None, None, None
    if isinstance(key, dict):
        tipo = str(key.get("tipo") or "LEI").upper()
        numero = key.get("numero")
        ano = key.get("ano")
        if numero is None or ano is None:
            return None, None, None
        return tipo, str(numero).replace(".", ""), int(ano)
    return None, None, None
