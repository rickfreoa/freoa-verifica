"""Conector STF — portal (sem WAF) + repercussão geral; busca textual sob WAF."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode, urljoin

from lxml import html as lxml_html

from freoa_verifica.connectors.base import (
    Candidate,
    Connector,
    HealthProbe,
    HealthReport,
    ParsedDecision,
    Unavailable,
    register,
)
from freoa_verifica.connectors.challenge import detect_challenge, unavailable_from_challenge
from freoa_verifica.connectors.httputil import connector_fetch
from freoa_verifica.transport import Response

_HOSTS = frozenset(
    {
        "portal.stf.jus.br",
        "sistemas.stf.jus.br",
        "jurisprudencia.stf.jus.br",
    }
)
_PREFIXES = {
    "portal.stf.jus.br": (
        "/processos/",
        "/jurisprudenciaRepercussao/",
        "/util/",
        "/arquivo/",
        "/jurisprudencia/sumariosumulas.asp",
    ),
    "sistemas.stf.jus.br": ("/repgeral/",),
    "jurisprudencia.stf.jus.br": ("/api/",),
}

# base do sumário oficial -> (classe, espécie); detalhe = mesma página com &sumula=<id>
SUMULA_BASES = {30: ("Súmula", "sumula"), 26: ("Súmula Vinculante", "sumula_vinculante")}
_SUMARIO = "https://portal.stf.jus.br/jurisprudencia/sumariosumulas.asp"
_SUMULA_RE = re.compile(r"^(Súmula(?: Vinculante)?)\s+(\d+)\s*(?:\((\w+)\))?$")

_MAINTENANCE = re.compile(r"em\s+manuten[cç][aã]o|sistema\s+indispon[ií]vel|maintenance", re.I)

_MIMES = frozenset({"text/html", "application/json", "application/pdf", "text/plain", "application/octet-stream"})

@register
class StfConnector(Connector):
    id = "stf"
    authority = "Supremo Tribunal Federal"
    hosts = _HOSTS
    path_prefixes = _PREFIXES
    mimes = _MIMES
    user_agent = "browser"
    coverage = {
        "colecoes": ["processos", "decisoes", "repercussao_geral", "sumulas", "sumulas_vinculantes"],
        "periodo": "acervo portal",
        "busca_textual": False,  # WAF em jurisprudencia.stf.jus.br
        "ementa": True,
        "inteiro_teor": True,
        "atualizacao": "sob demanda",
        "nota": "busca textual livre → unavailable(stf_busca_textual_sob_waf)",
    }

    def health(self) -> HealthReport:
        probes: list[HealthProbe] = []
        try:
            cand = self.resolve({"classe": "ADI", "numero": 7000})
            assert cand is not None
            probes.append(HealthProbe("positivo", "ok", cand.metadata.get("incidente")))
        except Exception as exc:
            probes.append(HealthProbe("positivo", "unavailable", str(exc)[:200]))
        try:
            self.search("liberdade de expressão")
            probes.append(HealthProbe("negativo", "failed", "busca deveria unavailable"))
        except Unavailable as exc:
            if "stf_busca_textual_sob_waf" in exc.reason or "desafio" in exc.reason:
                probes.append(HealthProbe("negativo", "ok", exc.reason))
            else:
                probes.append(HealthProbe("negativo", "unavailable", exc.reason))
        except Exception as exc:
            probes.append(HealthProbe("negativo", "unavailable", str(exc)[:200]))
        try:
            cand = self.resolve({"classe": "ADI", "numero": 7000})
            assert cand is not None
            decisoes = self.list_decisoes(cand.metadata["incidente"])
            probes.append(
                HealthProbe(
                    "documento",
                    "ok" if decisoes else "failed",
                    f"n={len(decisoes)}",
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
        """Busca textual da jurisprudência está sob AWS WAF."""
        # processo por classe+numero na query
        m = re.search(r"(?i)\b([A-Z]{2,6})\s*(\d+)\b", q or "")
        if m and not filtros.get("forcar_textual"):
            cand = self.resolve({"classe": m.group(1), "numero": int(m.group(2))})
            return [cand] if cand else []
        if filtros.get("tema"):
            return self.resolve_tema(int(filtros["tema"]))
        raise Unavailable("stf_busca_textual_sob_waf")

    def resolve(self, key: Any) -> Candidate | None:
        self.last_not_found_response = None
        if isinstance(key, dict) and key.get("tema") is not None:
            found = self.resolve_tema(int(key["tema"]))
            return found[0] if found else None
        classe, numero = _parse_processo(key)
        if not classe or numero is None:
            return None
        url = (
            "https://portal.stf.jus.br/processos/listarProcessos.asp?"
            + urlencode({"classe": classe, "numeroProcesso": str(numero)})
        )
        resp = connector_fetch(
            url,
            hosts=self.hosts,
            path_prefixes=self.path_prefixes,
            mimes=self.mimes,
            user_agent=self.user_agent,
            timeout=45.0,
        )
        incidente = _incidente_from_response(resp)
        if not incidente:
            text = lxml_html.fromstring(resp.body).text_content()
            if _MAINTENANCE.search(text):
                raise Unavailable("resposta_invalida")
            if re.search(r"\bProcesso\s+n[aã]o\s+encontrado\b",text,re.I):
                self.last_not_found_response = resp
                return None
            raise Unavailable("resposta_inesperada")
        return Candidate(
            source_id=self.id,
            key=f"{classe}:{numero}",
            title=f"{classe} {numero}",
            url=f"https://portal.stf.jus.br/processos/detalhe.asp?incidente={incidente}",
            metadata={
                "classe": classe,
                "numero": numero,
                "incidente": incidente,
            },
        )

    def fetch(self, candidate: Candidate) -> Response:
        incidente = candidate.metadata.get("incidente")
        if candidate.metadata.get("download_url"):
            url = candidate.metadata["download_url"]
        elif incidente:
            url = f"https://portal.stf.jus.br/processos/abaDecisoes.asp?incidente={incidente}"
        else:
            url = candidate.url
        if not url:
            raise Unavailable("sem_url")
        return connector_fetch(
            url,
            hosts=self.hosts,
            path_prefixes=self.path_prefixes,
            mimes=self.mimes,
            user_agent=self.user_agent,
            timeout=60.0,
            max_bytes=30 * 1024 * 1024,
        )

    def parse(self, resp: Response) -> ParsedDecision:
        if "sumariosumulas.asp" in (resp.final_url or ""):
            return _parse_sumula(resp)
        if resp.body[:4] == b"%PDF":
            return ParsedDecision(
                profile="stf_pdf",
                kind="decisao",
                court="STF",
                official_id=resp.final_url,
                text=_pdf_text(resp.body),
                documents=[{"url": resp.final_url, "label": "inteiro_teor"}],
            )
        if "application/json" in (resp.mime or "") or resp.body[:1] in (b"{", b"["):
            try:
                data = json.loads(resp.body.decode("utf-8"))
            except json.JSONDecodeError:
                data = {}
            rg = (
                _rg(data)
                if isinstance(data, (dict, list))
                else {}
            )
            leading_cases = _leading_cases(rg.get("processoLeadingCase"))
            leading = leading_cases[0] if len(leading_cases) == 1 else {}
            theme_numbers = {str(item.get("numeroTema")) for item in leading_cases if item.get("numeroTema") is not None}
            return ParsedDecision(
                profile="stf_rg",
                kind="repercussao_geral",
                court="STF",
                official_id=next(iter(theme_numbers)) if len(theme_numbers) == 1 else "",
                ementa=leading.get("tituloTema"),
                text=json.dumps(leading_cases, ensure_ascii=False),
                rapporteur=leading.get("relator"),
                class_name=leading.get("siglaClasse"),
                metadata=leading if len(leading_cases) == 1 else {"leading_cases":leading_cases},
            )
        # aba decisões HTML
        items = _parse_aba_decisoes(resp.body, base=resp.final_url)
        first = items[0] if items else {}
        return ParsedDecision(
            profile="stf_decisoes",
            kind="decisao",
            court="STF",
            official_id=first.get("id") or resp.final_url,
            ementa=first.get("nome"),
            text="\n".join(f"{i.get('data')} {i.get('nome')}" for i in items),
            judgment_date=first.get("data_iso"),
            rapporteur=first.get("julgador"),
            documents=[d for i in items for d in i.get("docs", [])],
            metadata={"items": items},
        )

    def list_decisoes(self, incidente: str | int) -> list[dict[str, Any]]:
        url = f"https://portal.stf.jus.br/processos/abaDecisoes.asp?incidente={incidente}"
        resp = connector_fetch(
            url,
            hosts=self.hosts,
            path_prefixes=self.path_prefixes,
            mimes=self.mimes,
            user_agent=self.user_agent,
            timeout=45.0,
        )
        return _parse_aba_decisoes(resp.body, base=url)

    def list_sumulas(self, base: int) -> list[Candidate]:
        """Sumário oficial (HTML) -> um candidato por súmula; o enunciado vem da página de detalhe."""
        classe, _ = SUMULA_BASES[base]
        url = f"{_SUMARIO}?base={base}"
        resp = connector_fetch(
            url,
            hosts=self.hosts,
            path_prefixes=self.path_prefixes,
            mimes=self.mimes,
            user_agent=self.user_agent,
            timeout=60.0,
        )
        tree = lxml_html.fromstring(resp.body)
        out = []
        for a in tree.xpath('//div[@class="sumarioSumulas"]//div[contains(@class,"sumula-item")]/a[@href]'):
            m = _SUMULA_RE.match(_texto(a))
            sid = re.search(r"[?&]sumula=(\d+)", a.get("href") or "")
            if not m or not sid or m.group(1) != classe:
                raise Unavailable("resposta_inesperada")
            numero = int(m.group(2))
            detalhe = f"{url}&sumula={sid.group(1)}"
            out.append(Candidate(
                source_id=self.id, key=f"{'sv' if base == 26 else 'sumula'}:{numero}",
                title=f"{classe} {numero}", url=detalhe,
                metadata={"court": "STF", "classe": classe, "numero": numero, "download_url": detalhe,
                          "observacao": m.group(3), "kind": SUMULA_BASES[base][1]}))
        if not out:
            raise Unavailable("resposta_inesperada")
        return out

    def resolve_tema(self, tema: int) -> list[Candidate]:
        url = f"https://sistemas.stf.jus.br/repgeral/votacao?tema={int(tema)}"
        resp = connector_fetch(
            url,
            hosts=self.hosts,
            path_prefixes=self.path_prefixes,
            mimes=self.mimes,
            user_agent=self.user_agent,
            timeout=45.0,
        )
        try:
            data = json.loads(resp.body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise Unavailable("resposta_inesperada") from exc
        leading_cases = _leading_cases(_rg(data).get('processoLeadingCase'))
        candidates = []
        for leading in leading_cases:
            if str(leading.get('numeroTema')) != str(tema):
                raise Unavailable('identidade_tema_divergente')
            incidente = leading.get('seqObjetoIncidente')
            andamento = ('https://portal.stf.jus.br/jurisprudenciaRepercussao/'
                f'verAndamentoProcesso.asp?incidente={incidente}&numeroTema={tema}') if incidente else None
            candidates.append(Candidate(source_id=self.id,
                key=f'tema:{tema}' + (f':{incidente}' if len(leading_cases)>1 else ''),
                title=str(leading.get('tituloTema') or f'Tema {tema}'),url=andamento,
                snippet=str(leading.get('tituloTema') or '')[:300] or None,
                metadata={'tema':tema,'download_url':url,'classe':leading.get('siglaClasse'),
                    'numero':leading.get('numeroProcesso'),'incidente':incidente,
                    'relator':leading.get('relator'),'kind':'repercussao_geral','raw':leading}))
        return candidates


def _texto(el) -> str:
    # nbsp e espaço de largura zero (ex.: "cance&#8203;lada") aparecem no HTML oficial
    return " ".join(el.text_content().replace("\u200b", "").replace("\xa0", " ").split())


def _parse_sumula(resp: Response) -> ParsedDecision:
    tree = lxml_html.fromstring(resp.body)
    titulo = tree.xpath('//div[@class="titulo"]')
    corpo = tree.xpath('//div[@class="titulo"][1]/following-sibling::div[@class="parCOM"][1]')
    m = _SUMULA_RE.match(_texto(titulo[0])) if titulo else None
    if not m or not corpo or not _texto(corpo[0]):
        raise Unavailable("resposta_inesperada")
    classe, numero, obs = m.group(1), int(m.group(2)), m.group(3)
    rotulo = f"{classe} {numero}" + (f" ({obs})" if obs else "")
    return ParsedDecision(
        profile="stf_sumula",
        kind=SUMULA_BASES[26 if classe.endswith("Vinculante") else 30][1],
        court="STF",
        official_id=f"{classe} {numero}",
        ementa=f"{rotulo}. {_texto(corpo[0])}",
        text=_texto(corpo[0]),
        class_name=classe,
        metadata={"numero": numero, "observacao": obs, "processo": numero},
    )


def _parse_processo(key: Any) -> tuple[str | None, int | None]:
    if isinstance(key, str):
        m = re.match(r"([A-Za-z]+):(\d+)$", key)
        if m:
            return m.group(1).upper(), int(m.group(2))
        m = re.match(r"([A-Za-z]+)\s*(\d+)$", key)
        if m:
            return m.group(1).upper(), int(m.group(2))
        return None, None
    if isinstance(key, dict):
        classe = key.get("classe") or key.get("class")
        numero = key.get("numero") or key.get("number")
        if classe is None or numero is None:
            return None, None
        return str(classe).upper(), int(numero)
    return None, None


def _incidente_from_response(resp: Response) -> str | None:
    final = resp.final_url or ""
    m = re.search(r"incidente=(\d+)", final)
    if m:
        return m.group(1)
    text = resp.body.decode("utf-8", errors="replace")
    m = re.search(r"incidente=(\d+)", text)
    return m.group(1) if m else None


def _parse_aba_decisoes(body: bytes, *, base: str) -> list[dict[str, Any]]:
    try:
        content = body.decode("utf-8")
    except UnicodeDecodeError:
        content = body
    tree = lxml_html.fromstring(content)
    items = []
    for div in tree.xpath('//div[contains(@class,"andamento-item")]'):
        data_el = div.xpath('.//*[contains(@class,"andamento-data")]')
        nome_el = div.xpath('.//*[contains(@class,"andamento-nome")]')
        julg_el = div.xpath('.//*[contains(@class,"andamento-julgador")]')
        data = data_el[0].text_content().strip() if data_el else None
        data_iso = None
        if data and re.match(r"\d{2}/\d{2}/\d{4}", data):
            d, m, y = data.split("/")
            data_iso = f"{y}-{m}-{d}"
        docs = []
        for a in div.xpath(".//a[@href]"):
            href = a.get("href") or ""
            if re.search(r"(?:downloadPeca|downloadTexto)\.asp(?:\?|$)",href,re.I) or href.lower().endswith(".pdf"):
                docs.append(
                    {
                        "url": urljoin(base, href),
                        "label": (a.text_content() or "").strip() or "peca",
                    }
                )
        items.append(
            {
                "id": div.get("id"),
                "data": data,
                "data_iso": data_iso,
                "nome": nome_el[0].text_content().strip() if nome_el else None,
                "julgador": julg_el[0].text_content().strip() if julg_el else None,
                "docs": docs,
            }
        )
    return items


def _pdf_text(body: bytes) -> str:
    from freoa_verifica.parsers.isolated import texto_pdf_isolado

    return texto_pdf_isolado(body)


def _object(value):
    if isinstance(value, list):
        if not value:
            return {}
        if len(value) != 1:
            raise Unavailable("resposta_inesperada")
        value = value[0]
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise Unavailable("resposta_inesperada")
    return value

def _rg(data):
    return _object(_object(_object(data).get("package")).get("repercussaoGeral"))


def _leading_cases(value):
    if value is None:
        return []
    cases = value if isinstance(value,list) else [value]
    if not all(isinstance(item,dict) for item in cases):
        raise Unavailable('resposta_inesperada')
    return cases
