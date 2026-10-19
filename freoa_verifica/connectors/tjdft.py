"""Conector TJDFT — API pública oficial de jurisprudência (decisão 0041).

A resposta JSON inteira é a captura; cada candidato aponta para o seu registro por `uuid` + `identificador`.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

from lxml import html as lxml_html

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

_HOST = "jurisdf.tjdft.jus.br"
_API = f"https://{_HOST}/api/v1/pesquisa"
MAX_TAMANHO = 50
MIN_INTEIRO_TEOR = 1000
_CACHE_MAX = 4096
_BASES = {"acordaos", "decisoes"}
_TAG_RE = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")


def _norm(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c)
    )


def _iso(value: Any) -> str | None:
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(value or ""))
    return m.group(1) if m else None


def _segredo(rec: dict[str, Any]) -> bool:
    return str(rec.get("segredoJustica")).strip().lower() in {"true", "1", "s", "sim"}


def _kind(rec: dict[str, Any]) -> str | None:
    if rec.get("subbase") in {"decisoes-monocraticas", "decisoes-presidencia"}:
        return "monocratica"
    if rec.get("base") == "acordaos":
        return "acordao"
    return None


def _html_text(raw: str) -> str:
    root = lxml_html.fromstring(f"<div>{raw}</div>")
    for bad in root.xpath("//script|//style"):
        bad.drop_tree()
    return " ".join(root.text_content().split())


# Frases de indisponibilidade do próprio documento (não "bem indisponível", comum em decisões reais).
_NEGATIVOS = ("teor indisponivel", "teor nao disponivel", "teor nao esta disponivel", "documento indisponivel",
              "documento nao disponivel", "nao disponivel no momento", "indisponivel no momento", "sem inteiro teor",
              "nao foi possivel obter", "erro ao obter", "falha ao obter", "nao foi possivel carregar")
# Prova positiva de documento decisório completo: parte dispositiva E fecho de cumprimento (auditoria 1.2.0).
_DISPOSITIVO = ("ante o exposto", "diante do exposto", "pelo exposto", "isso posto", "posto isso", "ante o quadro",
                "defiro", "indefiro", "nego provimento", "dou provimento", "nego seguimento", "inadmito", "admito o recurso",
                "julgo", "homologo", "nao conheco", "conheco do")
_FECHO = ("publique-se", "intimem-se", "intime-se", "cumpra-se", "comunique-se", "arquive-se", "registre-se",
         "remetam-se", "documento assinado", "assinado digitalmente", "assinado eletronicamente")


def inteiro_teor_valido(rec: dict[str, Any]) -> str | None:
    """Regra conservadora (decisão 0041): só texto íntegro do próprio processo; `possuiInteiroTeor` não conta."""
    processo = str(rec.get("processo") or "").strip()
    if not processo:
        return None
    for campo in ("inteiroTeor", "inteiroTeorHtml"):
        raw = rec.get(campo)
        if not isinstance(raw, str) or not raw.strip():
            continue
        text = _html_text(raw) if _TAG_RE.search(raw) else raw
        n = _norm(text)
        if any(neg in n for neg in _NEGATIVOS):
            continue
        # Prova positiva de documento decisório, não só comprimento e número (auditoria 1.2.0).
        cauda = n[-max(600, len(n) // 4):]  # fecho no fim do texto: fragmento inicial não passa
        if (len(text) >= MIN_INTEIRO_TEOR and processo in text and any(p in n for p in _DISPOSITIVO)
                and any(f in cauda for f in _FECHO)):
            return text
    return None


@register
class TjdftConnector(Connector):
    id = "tjdft"
    authority = "Tribunal de Justiça do Distrito Federal e dos Territórios"
    hosts = frozenset({_HOST})
    path_prefixes = {_HOST: ("/api/v1/pesquisa",)}
    mimes = frozenset({"application/json"})
    user_agent = "identified"
    coverage = {
        "colecoes": ["acordaos", "decisoes-monocraticas", "decisoes-presidencia"],
        "periodo": "acervo da API pública de jurisprudência",
        "busca_textual": True,
        "busca_textual_ao_vivo": True,
        # O acervo local do TJDFT é só a semente temática: a busca filtrada pelo tribunal consulta a API oficial.
        "consultar_ao_vivo_sempre": True,
        "ementa": True,
        "inteiro_teor": "somente quando o registro o traz íntegro (decisões monocráticas e da presidência); acórdão sem íntegra pela API",
        "atualizacao": "sob demanda; semente temática",
    }

    def __init__(self) -> None:
        self._capturas: dict[str, Response] = {}

    def health(self) -> HealthReport:
        probes: list[HealthProbe] = []
        found: list[Candidate] = []
        try:
            found = self.search("acordo de acionistas", limite=3)
            probes.append(HealthProbe("positivo", "ok" if found else "failed", f"n={len(found)}"))
        except Exception as exc:  # noqa: BLE001
            probes.append(HealthProbe("positivo", "unavailable", str(exc)[:200]))
        try:
            empty = self.search("FVXYZTERMOSINTETICO99991QWERTY", limite=3)
            probes.append(HealthProbe("negativo", "zero" if not empty else "failed", f"n={len(empty)}"))
        except Unavailable as exc:
            probes.append(HealthProbe("negativo", "unavailable", exc.reason))
        except Exception as exc:  # noqa: BLE001
            probes.append(HealthProbe("negativo", "unavailable", str(exc)[:200]))
        try:
            if not found:
                probes.append(HealthProbe("documento", "failed", "sem candidato"))
            else:
                parsed = self.parse_candidate(self.fetch(found[0]), found[0])
                probes.append(HealthProbe("documento", "ok" if parsed.official_id else "failed", parsed.official_id))
        except Exception as exc:  # noqa: BLE001
            probes.append(HealthProbe("documento", "unavailable", str(exc)[:200]))
        return HealthReport(self.id, tuple(probes), checked_at=datetime.now(timezone.utc).isoformat())

    def search(self, q: str, **filtros: Any) -> CandidateList:
        if not (q or "").strip():
            raise Unavailable("tjdft_consulta_vazia")
        pagina = max(0, int(filtros.get("pagina") or 0))
        tamanho = min(MAX_TAMANHO, max(1, int(filtros.get("limite") or filtros.get("tamanho") or 20)))
        payload: dict[str, Any] = {"query": q, "pagina": pagina, "tamanho": tamanho}
        if filtros.get("base") in _BASES:
            payload["termosAcessorios"] = [{"campo": "base", "valor": filtros["base"]}]
        resp = connector_fetch(
            _API,
            hosts=self.hosts,
            path_prefixes=self.path_prefixes,
            mimes=self.mimes,
            user_agent=self.user_agent,
            method="POST",
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=60.0,
        )
        if resp.status != 200:
            raise Unavailable(f"http_{resp.status}")
        data = _load(resp)
        hits = data["hits"]["value"] if isinstance(data.get("hits"), dict) else None
        if isinstance(hits, bool) or not isinstance(hits, int) or hits < 0:
            raise Unavailable("tjdft_hits_invalido")
        regs = data.get("registros")
        if regs is None and hits == 0:
            regs = []
        if not isinstance(regs, list) or any(not isinstance(r, dict) for r in regs):
            raise Unavailable("tjdft_registros_ausentes")
        if hits > 0 and not regs and pagina == 0:
            raise Unavailable("tjdft_registros_vazios_com_hits")
        out = []
        for rec in regs:
            if _segredo(rec):
                continue
            cand = _cand(self.id, rec)
            self._capturas[cand.metadata["uuid"]] = resp
            out.append(cand)
        while len(self._capturas) > _CACHE_MAX:
            self._capturas.pop(next(iter(self._capturas)))
        return CandidateList(out, total=hits)

    def resolve(self, key: Any) -> Candidate | None:
        if isinstance(key, dict):
            key = key.get("numero") or key.get("key")
        key_s = str(key or "").strip()
        if not key_s:
            return None
        for cand in self.search(key_s, limite=10):
            if key_s in {cand.key, cand.metadata.get("processo")}:
                return cand
        return None

    def fetch(self, candidate: Candidate) -> Response:
        uuid = candidate.metadata.get("uuid")
        if uuid not in self._capturas:
            # Sem URL de documento por uuid: a captura só existe ao refazer a consulta pelo processo.
            processo = candidate.metadata.get("processo")
            if not processo:
                raise Unavailable("tjdft_captura_ausente")
            self.search(str(processo), limite=MAX_TAMANHO)
        if uuid not in self._capturas:
            raise Unavailable("tjdft_captura_ausente")
        return self._capturas[uuid]

    def parse(self, resp: Response) -> ParsedDecision:
        raise Unavailable("tjdft_identidade_exige_candidato")

    def parse_candidate(self, resp: Response, candidate: Candidate) -> ParsedDecision:
        uuid = candidate.metadata.get("uuid")
        regs = _load(resp).get("registros")
        if not uuid or not isinstance(regs, list):
            raise Unavailable("tjdft_registro_ausente")
        rec = [r for r in regs if isinstance(r, dict) and r.get("uuid") == uuid and str(r.get("identificador")) == candidate.key]
        if len(rec) != 1:
            raise Unavailable("tjdft_registro_ausente_ou_ambiguo")
        rec = rec[0]
        if _segredo(rec):
            raise Unavailable("tjdft_segredo_de_justica")
        kind = _kind(rec)
        if kind is None:
            raise Unavailable("tjdft_especie_desconhecida")
        text = inteiro_teor_valido(rec)
        # Em decisões individuais o campo "ementa" da API é o próprio texto da decisão (começa pelo cabeçalho):
        # não é ementa. Com o texto integral validado, ele vai só para inteiro_teor (comparativo 1.2.0).
        # Sem texto integral validado, a decisão individual fica sem documento (só metadados), em vez de
        # gravar o texto decisório sob o rótulo de ementa (auditoria 1.2.0).
        ementa = rec.get("ementa") or None if rec.get("base") == "acordaos" else None
        meta = {k: rec.get(k) for k in ("uuid", "processo", "base", "subbase", "codigoClasseCnj")}
        if text:
            meta["documento"] = "inteiro_teor"
        return ParsedDecision(
            profile="tjdft_inteiro_teor" if text else "tjdft_ementa",
            kind=kind,
            court="TJDFT",
            official_id=str(rec["identificador"]),
            ementa=ementa,
            text=text or "",
            judgment_date=_iso(rec.get("dataJulgamento")),
            publication_date=_iso(rec.get("dataPublicacao")),
            rapporteur=rec.get("nomeRelator"),
            organ=rec.get("descricaoOrgaoJulgador"),
            class_name=None,
            cnj_number=rec.get("processo"),
            metadata=meta,
        )


def _load(resp: Response) -> dict[str, Any]:
    try:
        data = json.loads(resp.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Unavailable("tjdft_json_invalido") from exc
    if not isinstance(data, dict):
        raise Unavailable("tjdft_json_invalido")
    return data


def _cand(source_id: str, rec: dict[str, Any]) -> Candidate:
    uuid, ident = rec.get("uuid"), rec.get("identificador")
    if not uuid or ident in (None, ""):
        raise Unavailable("tjdft_registro_sem_identidade")
    ementa = (rec.get("ementa") or "") if rec.get("base") == "acordaos" else ""
    processo = rec.get("processo")
    return Candidate(
        source_id=source_id,
        key=str(ident),
        title=f"TJDFT {processo or ident}",
        url=None,
        snippet=ementa[:300] or None,
        metadata={
            "court": "TJDFT",
            "uuid": uuid,
            "processo": processo,
            "number": processo,
            "base": rec.get("base"),
            "subbase": rec.get("subbase"),
            "kind": _kind(rec),
            "orgao": rec.get("descricaoOrgaoJulgador"),
            "relator": rec.get("nomeRelator"),
            "judgment_date": _iso(rec.get("dataJulgamento")),
            "publication_date": _iso(rec.get("dataPublicacao")),
        },
    )
