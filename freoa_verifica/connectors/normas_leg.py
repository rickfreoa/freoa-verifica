"""Legislação federal sob demanda do Congresso Nacional; rota não qualificada (0085)."""
from __future__ import annotations

import json
import re
import unicodedata
from copy import deepcopy
from dataclasses import asdict
from datetime import date, datetime, timezone
from urllib.parse import parse_qs, urlencode, urlsplit

from freoa_verifica.aliases import WorkKey
from freoa_verifica.connectors.base import Candidate, Connector, HealthProbe, HealthReport, Unavailable, register
from freoa_verifica.connectors.camara_estado import Estado
from freoa_verifica.connectors.camara_portao import Portao
from freoa_verifica.connectors.httputil import connector_fetch
from freoa_verifica.identidade_http import UA_POR_CONECTOR
from freoa_verifica.texto_resposta import texto_do_response

HOST = "normas.leg.br"
BASE = "https://" + HOST
HOSTS = frozenset({HOST})
PREFIXOS = {HOST: ("/robots.txt", "/api/public/normas", "/api/public/binario/")}
SCRIPTS = ("/main.9e54abd8eff4fac4.js", "/987.9451176cf8cb4e12.js")
JSON_MIMES = frozenset({"application/json", "application/ld+json", "text/json"})
ATRIBUICAO = "Fonte: normas.leg.br (Congresso Nacional), licença CC BY 4.0; texto sem valor oficial"
TIPOS = {"lei": "lei", "lei_complementar": "lei.complementar", "decreto": "decreto",
         "decreto_lei": "decreto.lei", "medida_provisoria": "medida.provisoria",
         "decreto_legislativo": "decreto.legislativo", "emenda_constitucional": "emenda.constitucional",
         "constituicao": "constituicao"}
SIGLAS = dict(zip(("lei", "lcp", "dec", "del", "mpv", "dlg", "emc", "cf"), TIPOS, strict=True))
URN = re.compile(r"urn:lex:br:federal:([a-z.]+):(\d{4}(?:-\d{2}-\d{2})?);(\d+(?:-\d+)?)")
BINARIO = re.compile(r"https://normas\.leg\.br/api/(?:public/)?binario/"
                     r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}/texto")


def tipo_normalizado(value):
    texto = "".join(c for c in unicodedata.normalize("NFKD", str(value)) if not unicodedata.combining(c)).lower()
    texto = re.sub(r"[ .-]+", "_", texto)
    return SIGLAS.get(texto, texto)


def identidade(key):
    if isinstance(key, WorkKey):
        key = asdict(key)
    if not isinstance(key, dict):
        raise Unavailable("identidade_necessaria")
    kind = tipo_normalizado(key.get("kind") or key.get("tipo"))
    if kind not in TIPOS or key.get("authority", "federal") != "federal":
        raise Unavailable("tipo_nao_suportado")
    year = key.get("year") or key.get("ano")
    if not year:
        raise Unavailable("ano_necessario")
    number = str(key.get("number") or key.get("numero") or "").replace(".", "")
    if (not re.fullmatch(r"\d{4}", str(year)) or not re.fullmatch(r"\d+(?:-\d+)?", number)
            or "-" in number and kind != "medida_provisoria"):
        raise Unavailable("identidade_invalida")
    number = "-".join(str(int(n)) for n in number.split("-"))
    if kind == "constituicao" and (int(year), number) != (1988, "1988"):
        raise Unavailable("tipo_nao_suportado")
    return WorkKey("federal", kind, number, int(year))


def urn_da_chave(w):
    when = "1988-10-05" if w.kind == "constituicao" else str(w.year)
    return f"urn:lex:br:federal:{TIPOS[w.kind]}:{when};{w.number}"


def url_texto(value):
    if not isinstance(value, str) or not BINARIO.fullmatch(value):
        raise Unavailable("resposta_inesperada")
    return value.replace("/api/binario/", "/api/public/binario/")


def admitir(url, *, scripts=False):
    p = urlsplit(url)
    if p.scheme != "https" or p.netloc != HOST or "#" in url or "\\" in url:
        raise Unavailable("url_nao_admitida")
    if p.path == "/robots.txt" and not p.query:
        return {"recurso": "robots", "mime": "text/plain"}
    if p.path == "/api/public/normas":
        query = parse_qs(p.query, keep_blank_values=True)
        if (set(query) == {"urn", "tipo_documento"} and query["tipo_documento"] == ["maior-detalhe"]
                and len(query["urn"]) == 1 and URN.fullmatch(query["urn"][0])):
            return {"recurso": "metadados", "mime": "application/json", "mimes": JSON_MIMES}
    if BINARIO.fullmatch(url) and "/api/public/" in url:
        return {"recurso": "texto", "mime": "text/html"}
    if scripts and p.path in SCRIPTS and not p.query:
        return {"recurso": "script", "mime": "application/javascript",
                "mimes": frozenset({"application/javascript", "text/javascript"})}
    raise Unavailable("url_nao_admitida")


class NormasPortao(Portao):
    """Mesmo núcleo de robots, serialização e barreiras da Câmara; parâmetros próprios."""

    def __init__(self, transporte, *, home=None, relogio=None, instrumento=False):
        super().__init__(transporte, estado=Estado(home, hosts=HOSTS, diretorio="normas_leg"),
                         relogio=relogio, exigir_ativacao=False, hosts=HOSTS,
                         prefixos={HOST: PREFIXOS[HOST] + (SCRIPTS if instrumento else ())},
                         intervalo_minimo=5.0, teto_chamada=12,
                         instrumento=instrumento, teto_sessao=12 if instrumento else None)
        self.scripts = instrumento

    def admitir(self, url):
        return admitir(url, scripts=self.scripts)

    def reabrir(self, decisao):
        if not isinstance(decisao, str) or not decisao.strip():
            raise ValueError("decisao_necessaria")
        with self.estado.trava_do_host(HOST):
            return self.estado.liberar_host(HOST, decisao, self.relogio.agora())


@register
class NormasLegConnector(Connector):
    id = "normas_leg"
    authority = "Congresso Nacional / normas.leg.br"
    hosts = HOSTS
    path_prefixes = PREFIXOS
    mimes = JSON_MIMES | {"text/html"}
    user_agent = UA_POR_CONECTOR[id]
    coverage = {"colecoes": list(TIPOS), "periodo": "legislação federal",
                "busca_textual": False, "ementa": True, "inteiro_teor": True,
                "atualizacao": "sob demanda (0085)", "qualificacao": "nao_apurada"}

    def __init__(self, *, home=None, portao=None):
        self.home, self._portao = home, portao
        self._candidatos, self._textos, self.paginas = {}, {}, {}

    def portao(self):
        if self._portao is None:
            from freoa_verifica.store.db import data_home
            self._portao = NormasPortao(connector_fetch, home=self.home or data_home())
        return self._portao

    def _erro(self, resp):
        exc = Unavailable("resposta_inesperada", evidencia={"url": resp.url, "sha256": resp.sha256})
        return self.portao().falha_de_resposta(exc, resp.url)

    def search(self, q, **filtros):
        from freoa_verifica.citation import parse_one
        cite = parse_one(q) if q else None
        key = asdict(cite.work) if cite and cite.work else {}
        # Filtros explícitos prevalecem, nas formas da fachada e do Senado.
        for target, names in (("kind", ("tipo", "kind")), ("number", ("numero", "number")), ("year", ("ano", "year"))):
            for name in names:
                if filtros.get(name) is not None:
                    key[target] = filtros[name]
                    break
        w = identidade(key)
        urn = urn_da_chave(w)
        url = BASE + "/api/public/normas?" + urlencode({"urn": urn, "tipo_documento": "maior-detalhe"})
        resp = self.portao().obter(url)
        try:
            payload = json.loads(texto_do_response(resp))
            if payload == {"urn": urn}:
                return []
            if not isinstance(payload, dict):
                raise ValueError("formato")
            full = payload.get("legislationIdentifier")
            match = URN.fullmatch(full) if isinstance(full, str) else None
            if not match or (match[1], int(match[2][:4]), match[3]) != (TIPOS[w.kind], w.year, w.number):
                raise ValueError("identidade")
            if len(match[2]) > 4:
                date.fromisoformat(match[2])
            if w.kind == "constituicao" and full != urn:
                raise ValueError("data_constituicao")
            encodings = payload.get("encoding")
            if not isinstance(encodings, list):
                raise ValueError("encoding")
            texts = []
            for e in encodings:
                if not isinstance(e, dict):
                    raise ValueError("encoding")
                if any(e.get(k) is not None and not isinstance(e[k], str)
                       for k in ("version", "name", "legislationLegalValue", "datePublished", "license")):
                    raise ValueError("encoding")
                texts.append({k: e.get(k) for k in ("version", "name", "legislationLegalValue", "datePublished", "license")} |
                             {"contentUrl": url_texto(e.get("contentUrl"))})
            if any(payload.get(k) is not None and not isinstance(payload[k], str)
                   for k in ("abstract", "name", "datePublished", "license", "sdLicense")):
                raise ValueError("metadados")
            title = payload.get("name") or f"{w.kind.replace('_', ' ').title()} {w.number}/{w.year}"
            if not isinstance(title, str):
                raise ValueError("titulo")
            cand = Candidate(self.id, self.id + ":" + full, title, url, payload.get("abstract"),
                             {"urn": full, "kind": w.kind, "tipo": w.kind, "numero": w.number, "ano": w.year,
                              "data": match[2], "datePublished": payload.get("datePublished"),
                              "ementa": payload.get("abstract"), "encoding": texts,
                              "metadados_sha256": resp.sha256, "license": payload.get("license"),
                              "sdLicense": payload.get("sdLicense"), "atribuicao": {"texto": ATRIBUICAO}})
        except (ValueError, TypeError, Unavailable):
            raise self._erro(resp) from None
        self.paginas[resp.url] = resp
        self._candidatos[cand.key] = deepcopy(cand)
        return [cand]

    def resolve(self, key):
        w = identidade(key)
        found = self.search("", kind=w.kind, number=w.number, year=w.year)
        return found[0] if found else None

    def fetch(self, candidate):
        # Candidato reconstruído não fornece metadados confiáveis: reler pela API.
        cand = self._candidatos.get(candidate.key)
        if cand is None:
            cand = self.resolve(candidate.metadata)
        if cand is None or cand.key != candidate.key:
            raise Unavailable("resposta_inesperada")
        wanted = candidate.metadata.get("versao")
        if wanted is not None and wanted not in {"Current", "Original"}:
            raise ValueError("versao_invalida")
        choices = []
        for version in ([wanted] if wanted else ["Current", "Original"]):
            choices = [e for e in cand.metadata["encoding"] if e["version"] == version]
            if choices:
                break
        if len(choices) != 1:
            raise Unavailable("versao_ausente_ou_ambigua")
        chosen = choices[0]
        resp = self.portao().obter(url_texto(chosen["contentUrl"]))
        self._textos[(resp.final_url, resp.sha256)] = {**cand.metadata, **chosen}
        return resp

    def parse(self, resp):
        from freoa_verifica.parsers.isolated import parse_ou_indisponivel
        from freoa_verifica.parsers.model import EditorialBlock
        meta = self._textos.get((resp.final_url, resp.sha256))
        if meta is None:
            raise Unavailable("texto_sem_metadados_capturados")
        doc = parse_ou_indisponivel("normas_leg", texto_do_response(resp), 120, base_url=resp.final_url)
        # A identidade do corpo nunca é substituída pelo título dos metadados.
        from freoa_verifica.identity import declared_identity
        observed, _ = declared_identity(doc)
        w = identidade(meta)
        if observed is not None and (observed.authority, observed.kind, observed.number) != (w.authority, w.kind, w.number):
            raise self._erro(resp)
        if observed is not None and observed.year and observed.year != w.year:
            raise self._erro(resp)
        if not doc.provisions:
            raise self._erro(resp)
        if observed is None:
            doc.title = self._candidatos[self.id + ":" + meta["urn"]].title
        doc.editorial_blocks.append(EditorialBlock(json.dumps(meta, ensure_ascii=False), (0, 0), "normas_leg_metadados"))
        return doc

    def health(self):
        # Três sondas explícitas, fora de laço (garantias estruturais: o controlador não engole falhas).
        probes = []
        try:
            cand = self.resolve({"tipo": "LEI", "numero": 6404, "ano": 1976})
            probes.append(HealthProbe("positivo", "ok" if cand else "failed"))
        except Unavailable as exc:
            probes.append(HealthProbe("positivo", "unavailable", exc.reason))
        try:
            cand = self.resolve({"tipo": "LEI", "numero": 999999, "ano": 2099})
            probes.append(HealthProbe("negativo", "zero" if cand is None else "failed"))
        except Unavailable as exc:
            probes.append(HealthProbe("negativo", "unavailable", exc.reason))
        try:
            cand = self.resolve({"tipo": "LCP", "numero": 118, "ano": 2005})
            if cand is None:
                probes.append(HealthProbe("documento", "failed"))
            else:
                from dataclasses import replace
                doc = self.parse(self.fetch(replace(cand, metadata={**cand.metadata, "versao": "Original"})))
                probes.append(HealthProbe("documento", "ok" if doc.provisions else "failed", "Original"))
        except Unavailable as exc:
            probes.append(HealthProbe("documento", "unavailable", exc.reason))
        return HealthReport(self.id, tuple(probes), datetime.now(timezone.utc).isoformat())
