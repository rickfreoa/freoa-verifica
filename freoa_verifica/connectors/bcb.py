"""Conector BCB/CMN — busca e texto de normativos."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlencode

from freoa_verifica.connectors.base import (
    CandidateList,
    Candidate,
    Connector,
    HealthProbe,
    HealthReport,
    Unavailable,
    register,
)
from freoa_verifica.connectors.httputil import connector_fetch
from freoa_verifica.identidade_http import UA_POR_CONECTOR
from freoa_verifica.parsers.bcb_json import parse_bcb_json
from freoa_verifica.transport import Response

_JSON_MIMES = frozenset(
    {
        "application/json",
        "text/json",
        "text/plain",
        "text/html",
        "application/octet-stream",
    }
)

MAX_ROWS = 500

_TIPO_NUM = re.compile(
    r"(?i)\b(resolu[cç][aã]o\s+(?:cmn|bcb|conjunta)|carta\s+circular|circular|"
    r"instru[cç][aã]o\s+normativa(?:\s+bcb)?|comunicado)\s*(?:n[ºo°.]+\s*)?(\d[\d.]*)"
)
_TIPOS = {"resolucao cmn": "Resolução CMN", "resolucao bcb": "Resolução BCB",
          "resolucao conjunta": "Resolução Conjunta", "carta circular": "Carta Circular",
          "circular": "Circular", "instrucao normativa": "Instrução Normativa BCB",
          "instrucao normativa bcb": "Instrução Normativa BCB", "comunicado": "Comunicado"}


def tipo_numero_da_consulta(q: str) -> tuple[str | None, str | None]:
    """M4: "Resolução CMN 4.966" na consulta aciona o lookup exato por número."""
    m = _TIPO_NUM.search(q or "")
    if not m:
        return None, None
    import unicodedata
    chave = unicodedata.normalize("NFKD", re.sub(r"\s+", " ", m.group(1).lower()))
    chave = "".join(c for c in chave if not unicodedata.combining(c))
    num = m.group(2).replace(".", "")
    return _TIPOS.get(chave), (num or None)


def _clean_numero(raw: Any) -> str:
    if raw is None:
        return ""
    s = str(raw).strip()
    if "." in s:
        try:
            return str(int(float(s)))
        except ValueError:
            pass
    return re.sub(r"\D", "", s) or s


@register
class BcbConnector(Connector):
    id = "bcb"
    authority = "Banco Central do Brasil"
    hosts = frozenset({"www.bcb.gov.br", "bcb.gov.br", "normativos.bcb.gov.br"})
    path_prefixes = {
        "www.bcb.gov.br": ("/api/",),
        "bcb.gov.br": ("/api/",),
        "normativos.bcb.gov.br": ("/Lists/",),
    }
    mimes = _JSON_MIMES | frozenset({"application/pdf"})
    user_agent = UA_POR_CONECTOR["bcb"]
    coverage = {
        "colecoes": [
            "Resolução BCB",
            "Resolução CMN",
            "Circular",
            "Carta Circular",
            "Instrução Normativa BCB",
        ],
        "periodo": "acervo SharePoint normativos",
        "busca_textual": True,
        "ementa": True,
        "inteiro_teor": True,
        "atualizacao": "API buscanormativos",
    }

    def health(self) -> HealthReport:
        probes: list[HealthProbe] = []
        try:
            found = self.search("Resolução CMN 4966", tipo="Resolução CMN", numero=4966)
            probes.append(HealthProbe("positivo", "ok" if found else "failed", None))
        except Exception as exc:
            probes.append(HealthProbe("positivo", "unavailable", str(exc)[:200]))
        try:
            empty = self.search("FV_TERM_INEXISTENTE_XYZ_999", limite=5)
            probes.append(HealthProbe("negativo", "zero" if not empty else "failed", f"n={len(empty)}"))
        except Unavailable as exc:
            probes.append(HealthProbe("negativo", "unavailable", exc.reason))
        except Exception as exc:
            probes.append(HealthProbe("negativo", "unavailable", str(exc)[:200]))
        try:
            cand = self.resolve({"tipo": "Resolução CMN", "numero": 4966})
            assert cand is not None
            doc = self.parse(self.fetch(cand))
            probes.append(
                HealthProbe("documento", "ok" if doc.title else "failed", doc.title[:80])
            )
        except Exception as exc:
            probes.append(HealthProbe("documento", "unavailable", str(exc)[:200]))
        return HealthReport(
            self.id,
            tuple(probes),
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def search(self, q: str, **filtros: Any) -> list[Candidate]:
        terms = (q or "").strip()
        tipo = filtros.get("tipo")
        numero = filtros.get("numero")
        if numero is None and terms:
            tipo_q, numero = tipo_numero_da_consulta(terms)
            tipo = tipo or tipo_q
        rowlimit = min(MAX_ROWS, max(1, int(filtros.get("limite") or filtros.get("rowlimit") or 15)))
        startrow = max(0, int(filtros.get("startrow") or 0))
        parts = ["ContentType:normativo", "AND", "contentSource:normativos"]
        if tipo:
            if str(tipo) in {"Resolução CMN", "Resolução"}:
                parts.append(
                    'AND (TipodoNormativoOWSCHCS="Resolução CMN" OR TipodoNormativoOWSCHCS="Resolução")'
                )
            else:
                parts.append(f'AND TipodoNormativoOWSCHCS="{tipo}"')
        if numero is not None:
            n = _clean_numero(numero)
            parts.append(f"AND (NumeroOWSNMBR:{n} OR NumeroOWSNMBR=\"{n}.00000000000\")")
        if terms and not numero:
            # termos livres além da base
            safe = re.sub(r"[^\wÀ-ÿ\s\-\"\.]", " ", terms)
            parts.append(f"AND ({safe})")
        querytext = " ".join(parts)
        params = {
            "querytext": querytext,
            "rowlimit": str(rowlimit),
            "startrow": str(startrow),
            "sortlist": "Data1OWSDATE:descending",
        }
        url = (
            "https://www.bcb.gov.br/api/search/app/normativos/buscanormativos?"
            + urlencode(params, quote_via=quote)
        )
        resp = connector_fetch(
            url,
            hosts=self.hosts,
            path_prefixes=self.path_prefixes,
            mimes=self.mimes,
            user_agent=self.user_agent,
            timeout=45.0,
        )
        try:
            payload = json.loads(resp.body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise Unavailable("resposta_invalida") from exc
        if "TotalRows" not in payload or "Rows" not in payload:
            raise Unavailable("resposta_invalida")
        total = int(payload.get("TotalRows") or 0)
        rows = payload.get("Rows")
        if not isinstance(rows, list):
            raise Unavailable("resposta_invalida")
        if total == 0:
            if rows:
                raise Unavailable("resposta_invalida")
            return []
        if total > 0 and not rows:
            raise Unavailable("resposta_invalida")
        out = CandidateList()
        for row in rows:
            if not isinstance(row, dict):
                raise Unavailable("resposta_invalida")
            tipo_row = str(row.get("TipodoNormativoOWSCHCS") or "")
            num = _clean_numero(row.get("NumeroOWSNMBR"))
            if not tipo_row or not num:
                raise Unavailable("resposta_invalida")
            title = str(row.get("title") or f"{tipo_row} {num}")
            assunto = row.get("AssuntoNormativoOWSMTXT") or ""
            if isinstance(assunto, str):
                assunto = re.sub(r"<[^>]+>", " ", assunto).strip()
            out.append(
                Candidate(
                    source_id=self.id,
                    key=f"bcb:{tipo_row}:{num}",
                    title=title,
                    url=(
                        "https://www.bcb.gov.br/api/conteudo/app/normativos/exibenormativo?"
                        + urlencode({"p1": tipo_row, "p2": num})
                    ),
                    snippet=assunto[:300] or None,
                    metadata={
                        "tipo": tipo_row,
                        "numero": num,
                        "data": row.get("data"),
                        "revogado": row.get("RevogadoOWSBOOL") == "1",
                        "listItemId": row.get("listItemId"),
                    },
                )
            )
        out.total = max(total, len(out))
        return out

    def resolve(self, key: Any) -> Candidate | None:
        if isinstance(key, str) and key.startswith("bcb:"):
            parts = key.split(":", 2)
            if len(parts) == 3:
                tipo, numero = parts[1], parts[2]
                found = self._buscar_ou_ausente(tipo, numero, 1)
                return found[0] if found else self._synthetic(tipo, numero)
        if isinstance(key, dict):
            tipo = key.get("tipo") or "Resolução CMN"
            numero = key.get("numero")
            if numero is None:
                return None
            found = self._buscar_ou_ausente(tipo, numero, 3)
            return found[0] if found else self._synthetic(tipo, numero)
        return None

    def _buscar_ou_ausente(self, tipo: Any, numero: Any, limite: int) -> list:
        """Só ausência explícita (resultado vazio estruturado ou 404) autoriza o endpoint de conteúdo.

        Desafio, recusa, `fonte_fora` esgotada e resposta inválida propagam com a categoria original.
        """
        try:
            return self.search("", tipo=tipo, numero=numero, limite=limite)
        except Unavailable as exc:
            if exc.reason == "http_404":
                return []
            raise

    def _synthetic(self, tipo: Any, numero: Any) -> Candidate:
        n = _clean_numero(numero)
        return Candidate(
            source_id=self.id,
            key=f"bcb:{tipo}:{n}",
            title=f"{tipo} {n}",
            url=(
                "https://www.bcb.gov.br/api/conteudo/app/normativos/exibenormativo?"
                + urlencode({"p1": tipo, "p2": n})
            ),
            metadata={"tipo": tipo, "numero": n},
        )

    def fetch(self, candidate: Candidate) -> Response:
        tipo = candidate.metadata.get("tipo")
        numero = candidate.metadata.get("numero")
        if not tipo or not numero:
            raise Unavailable("sem_chave")
        outras = {"Comunicado", "Ato de Diretor", "Ato do Presidente", "Decisão Conjunta"}
        endpoint = "exibeoutrasnormas" if tipo in outras else "exibenormativo"
        url = (
            f"https://www.bcb.gov.br/api/conteudo/app/normativos/{endpoint}?"
            + urlencode({"p1": tipo, "p2": numero})
        )
        resp = connector_fetch(
            url,
            hosts=self.hosts,
            path_prefixes=self.path_prefixes,
            mimes=self.mimes,
            user_agent=self.user_agent,
            timeout=60.0,
        )
        if tipo == "Resolução CMN" and _sem_conteudo(resp.body):
            # Resoluções do CMN anteriores a 2020 estão no BCB como tipo "Resolução".
            resp = self.fetch(Candidate(self.id, f"bcb:Resolução:{numero}", f"Resolução {numero}",
                                        metadata={"tipo": "Resolução", "numero": numero}))
        return resp

    def parse(self, resp: Response):
        from freoa_verifica.parsers.isolated import parse_ou_indisponivel
        return parse_ou_indisponivel("bcb_json", resp.body, 120.0)


def _sem_conteudo(body: bytes) -> bool:
    try:
        return not (json.loads(body.decode("utf-8")).get("conteudo") or [])
    except (ValueError, AttributeError):
        return False
