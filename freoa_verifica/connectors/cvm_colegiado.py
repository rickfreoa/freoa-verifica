"""Conector CVM Colegiado — RSS e páginas de reunião."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from dataclasses import replace
from typing import Any
from urllib.parse import urljoin, urldefrag, urlencode

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
from freoa_verifica.connectors.httputil import connector_fetch
from freoa_verifica.transport import Response

_FEED = "https://conteudo.cvm.gov.br/feed/decisoes.xml"
_HOSTS = frozenset({"conteudo.cvm.gov.br", "www.cvm.gov.br", "cvm.gov.br"})
_PREFIXES = {
    "conteudo.cvm.gov.br": ("/feed/", "/decisoes/", "/export/", "/system/"),
    "www.cvm.gov.br": ("/decisoes/", "/feed/", "/legislacao/"),
    "cvm.gov.br": ("/decisoes/", "/feed/", "/legislacao/"),
}
_MIMES = frozenset(
    {
        "application/rss+xml",
        "application/xml",
        "text/xml",
        "text/html",
        "application/xhtml+xml",
        "application/pdf",
        "application/octet-stream",
        "text/plain",
    }
)

_MAINTENANCE = re.compile(
    r"(em\s+manuten[cç][aã]o|sistema\s+indispon[ií]vel|maintenance)",
    re.I,
)


@register
class CvmColegiadoConnector(Connector):
    id = "cvm_colegiado"
    authority = "CVM Colegiado"
    hosts = _HOSTS
    path_prefixes = _PREFIXES
    mimes = _MIMES
    user_agent = "browser"
    coverage = {
        "colecoes": ["decisoes_colegiado", "atas"],
        "periodo": "2002–presente",
        "busca_textual": True,
        "ementa": True,
        "inteiro_teor": True,
        "atualizacao": "RSS + páginas decisoes/AAAA/",
    }

    def health(self) -> HealthReport:
        probes: list[HealthProbe] = []
        try:
            found = self.search("", limite=3)
            probes.append(HealthProbe("positivo", "ok" if found else "failed", None))
        except Exception as exc:
            probes.append(HealthProbe("positivo", "unavailable", str(exc)[:200]))
        try:
            empty = self.search("FV_TERM_INEXISTENTE_COLEGIADO_XYZ_999", limite=5)
            probes.append(HealthProbe("negativo", "zero" if not empty else "failed", f"n={len(empty)}"))
        except Unavailable as exc:
            probes.append(HealthProbe("negativo", "unavailable", exc.reason))
        except Exception as exc:
            probes.append(HealthProbe("negativo", "unavailable", str(exc)[:200]))
        try:
            found = self.search("", limite=1)
            assert found
            parsed = self.parse(self.fetch(found[0]))
            probes.append(
                HealthProbe(
                    "documento",
                    "ok" if isinstance(parsed, ParsedDecision) and parsed.official_id else "failed",
                    getattr(parsed, "official_id", None),
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
        ano = filtros.get("ano") or filtros.get("desde")
        if ano and isinstance(ano, str) and len(ano) >= 4:
            return self._sync_year(int(str(ano)[:4]), q=q, limite=int(filtros.get("limite") or 20))
        if ano is not None and not isinstance(ano, str):
            return self._sync_year(int(ano), q=q, limite=int(filtros.get("limite") or 20))
        return self._search_portal(q, limite=int(filtros.get('limite') or 20))

    def _search_portal(self, q, *, limite=20, ano=None):
        url = "https://conteudo.cvm.gov.br/decisoes/index.html?" + urlencode({
            'buscadoDecisao':'true', 'categoria':'decisao', 'lastName':q or '',
            'lastNameShow':q or '', 'filtro':'exato',
            'dataInicio':f'01/01/{ano}' if ano else '',
            'dataFim':f'31/12/{ano}' if ano else ''})
        resp = connector_fetch(url, hosts=self.hosts, path_prefixes=self.path_prefixes,
                               mimes=self.mimes, user_agent=self.user_agent, timeout=60.0)
        return _parse_search(resp.body, base=url, source_id=self.id, limite=limite)

    def resolve(self, key: Any) -> Candidate | None:
        if isinstance(key, str) and key.startswith("http"):
            url = _canonicalize_cvm_url(key)
            return Candidate(
                source_id=self.id,
                key=url,
                title=url.rsplit("/", 1)[-1],
                url=url,
                metadata={
                    "kind": "ata_colegiado_cvm",
                    "reuniao": _reuniao_id_from_url(url),
                },
            )
        if isinstance(key, dict) and key.get("url"):
            return self.resolve(key["url"])
        if isinstance(key, str) and re.match(r"\d{8}_R\d+", key):
            ano = key[:4]
            url = f"https://conteudo.cvm.gov.br/decisoes/{ano}/{key}.html"
            return self.resolve(url)
        if isinstance(key, str) and key.startswith("reuniao="):
            # reuniao=AAAAMMDD-Rn#item
            m = re.match(r"reuniao=(\d{8})-R(\d+)(?:#(\d+))?$", key)
            if m:
                stamp, rn, item = m.group(1), m.group(2), m.group(3)
                ano = stamp[:4]
                url = f"https://conteudo.cvm.gov.br/decisoes/{ano}/{stamp}_R{rn}.html"
                cand = self.resolve(url)
                if cand and item:
                    meta = dict(cand.metadata)
                    meta["item"] = int(item)
                    meta["official_id"] = key
                    return Candidate(
                        source_id=cand.source_id,
                        key=key,
                        title=cand.title,
                        url=cand.url,
                        snippet=cand.snippet,
                        metadata=meta,
                    )
                return cand
        return None

    def fetch(self, candidate: Candidate) -> Response:
        url = _canonicalize_cvm_url(candidate.url or candidate.key)
        if not url:
            raise Unavailable("sem_url")
        base, fragment = urldefrag(url)
        item = candidate.metadata.get("item") or fragment
        resp = connector_fetch(
            base,
            hosts=self.hosts,
            path_prefixes=self.path_prefixes,
            mimes=self.mimes,
            user_agent=self.user_agent,
            timeout=45.0,
        )
        if item:
            return replace(resp, url=base + f"#{item}", final_url=urldefrag(resp.final_url or base)[0] + f"#{item}")
        return resp

    def parse(self, resp: Response) -> ParsedDecision:
        if resp.final_url.endswith(".xml") or (
            resp.body.lstrip()[:1] == b"<" and b"<item>" in resp.body[:5000]
        ):
            items = _parse_rss(resp.body)
            first = items[0] if items else {}
            link = _canonicalize_cvm_url(first.get("link") or "")
            reuniao = _reuniao_id_from_url(link or resp.final_url)
            return ParsedDecision(
                profile="cvm_colegiado_rss",
                kind="decisao_colegiado_cvm",
                court="CVM",
                official_id=f"{reuniao}#1" if reuniao else (link or resp.final_url),
                ementa=first.get("description"),
                text=first.get("description") or "",
                metadata={"items": len(items), "ata": reuniao},
            )
        return _parse_reuniao_html(resp.body, url=resp.final_url or resp.url)

    def _sync_year(self, ano: int, *, q: str, limite: int) -> list[Candidate]:
        index_url = f"https://conteudo.cvm.gov.br/decisoes/{ano}/"
        # Unavailable propaga — nunca converter indisponibilidade em zero.
        try:
            resp = connector_fetch(
                index_url,
                hosts=self.hosts,
                path_prefixes=self.path_prefixes,
                mimes=self.mimes,
                user_agent=self.user_agent,
                timeout=45.0,
            )
        except Unavailable as exc:
            if exc.reason in {'http_404','http_410'}:
                return self._search_portal(q,limite=limite,ano=ano)
            raise
        text = resp.body.decode("utf-8", errors="replace")
        if _MAINTENANCE.search(text):
            raise Unavailable("resposta_invalida")
        tree = lxml_html.fromstring(resp.body)
        links = tree.xpath("//a[@href]")
        q_lower = (q or "").lower()
        out: list[Candidate] = []
        for a in links:
            href = a.get("href") or ""
            if not re.search(r"\d{8}_R\d+", href):
                continue
            abs_url = urljoin(index_url, href)
            title = (a.text_content() or abs_url).strip()
            if q_lower and q_lower not in title.lower():
                continue
            reuniao = _reuniao_id_from_url(abs_url)
            out.append(
                Candidate(
                    source_id=self.id,
                    key=abs_url,
                    title=title,
                    url=abs_url,
                    metadata={
                        "kind": "ata_colegiado_cvm",
                        "ano": ano,
                        "reuniao": reuniao,
                    },
                )
            )
            if len(out) >= limite:
                break
        return out


def _canonicalize_cvm_url(url: str | None) -> str:
    """RSS ainda aponta http://www.cvm.gov.br → HTTPS em conteudo.cvm.gov.br."""
    if not url:
        return ""
    u = url.strip()
    u = re.sub(r"^http://", "https://", u, flags=re.I)
    u = re.sub(r"^https://(www\.)?cvm\.gov\.br/", "https://conteudo.cvm.gov.br/", u, flags=re.I)
    return u


def _reuniao_id_from_url(url: str) -> str | None:
    m = re.search(r"(\d{8})_R(\d+)", url or "")
    if not m:
        return None
    return f"reuniao={m.group(1)}-R{m.group(2)}"


def _parse_rss(body: bytes) -> list[dict[str, str]]:
    if _MAINTENANCE.search(body.decode("utf-8", errors="replace")[:2000]):
        raise Unavailable("resposta_invalida")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise Unavailable("resposta_invalida") from exc
    tag = root.tag.split("}")[-1].lower() if isinstance(root.tag, str) else ""
    if tag not in {"rss", "feed"}:
        # RSS inválido estruturalmente (ex.: <rss><broken>)
        if root.find("channel") is None and root.find("{http://www.w3.org/2005/Atom}entry") is None:
            raise Unavailable("resposta_invalida")
    if tag == "rss" and root.find("channel") is None:
        raise Unavailable("resposta_invalida")
    items: list[dict[str, str]] = []
    for item in root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry"):

        def _text(tag_name: str, node=item) -> str:
            el = node.find(tag_name)
            if el is None:
                el = node.find(f"{{http://www.w3.org/2005/Atom}}{tag_name}")
            return (el.text or "").strip() if el is not None and el.text else ""

        link_el = item.find("link")
        link = ""
        if link_el is not None:
            link = (link_el.get("href") or link_el.text or "").strip()
        items.append(
            {
                "title": _text("title"),
                "link": link,
                "description": _text("description") or _text("summary"),
                "pub_date": _text("pubDate") or _text("updated"),
            }
        )
    # Zero só com RSS válido (channel/feed presente).
    return items


def _parse_reuniao_html(body: bytes, *, url: str) -> ParsedDecision:
    text_head = body[:4000].decode("utf-8", errors="replace")
    if _MAINTENANCE.search(text_head):
        raise Unavailable("resposta_invalida")
    tree = lxml_html.fromstring(body)
    title_el = tree.xpath("//h2|//h1")
    title = title_el[0].text_content().strip() if title_el else url
    text = tree.xpath("string(//article)") or body.decode("utf-8", errors="replace")
    reuniao = _reuniao_id_from_url(url)
    if not reuniao:
        raise Unavailable("resposta_invalida")
    if re.search(r"/\d{8}_D[^/]+\.html", url):
        article = tree.xpath("//article")
        content = article[0].text_content() if article else text
        proc = re.search(r"(?:\d{5}\.\d{6}/\d{4}-\d{2}|RJ\s*\d{4}/\d+)", title + " " + content, re.I)
        stamp = re.search(r"/(\d{4})(\d{2})(\d{2})_D",url)
        return ParsedDecision(profile="cvm_colegiado",kind="decisao_colegiado_cvm",court="CVM",official_id=url,
            class_name="PAS", text=content,ementa=title,judgment_date="-".join(stamp.groups()) if stamp else None,
            metadata={"processo": proc[0] if proc else None})
    # Itens individuais da ata (assunto/processo).
    item_nodes = tree.xpath(
        '//article//p[contains(@class,"text-uppercase")]'
        '|//article//p[contains(.,"PROC.") or contains(.,"Proc.")]'
    )
    decisoes: list[dict[str, Any]] = []
    for idx, node in enumerate(item_nodes, start=1):
        blob = (node.text_content() or "").strip()
        if len(blob) < 10:
            continue
        proc = None
        m = re.search(r"(?i)PROC\.?\s*([\d./-]+)", blob)
        if m:
            proc = m.group(1).strip()
        oid = f"{reuniao}#{idx}"
        decisoes.append({"official_id": oid, "processo": proc, "assunto": blob[:500]})
    if not decisoes:
        # Ata sem itens tipados: um item sintético #1.
        proc = None
        m = re.search(r"(?i)PROC\.?\s*([\d./-]+)", text)
        if m:
            proc = m.group(1).strip()
        decisoes = [{"official_id": f"{reuniao}#1", "processo": proc, "assunto": title}]
    fragment = urldefrag(url)[1]
    if fragment and (not fragment.isdigit() or not 1 <= int(fragment) <= len(decisoes)):
        raise Unavailable("item_nao_encontrado")
    selected = int(fragment) - 1 if fragment else 0
    first = decisoes[selected]
    paragraphs = tree.xpath("//article//p")
    if item_nodes:
        start = paragraphs.index(item_nodes[selected])
        end = paragraphs.index(item_nodes[selected + 1]) if selected + 1 < len(item_nodes) else len(paragraphs)
        paragraphs = paragraphs[start:end]
    data_m = re.search(r"(\d{8})_R\d+", url)
    meeting_date = None
    if data_m:
        raw = data_m.group(1)
        meeting_date = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    paras = [
        (p.text_content() or "").strip()
        for p in paragraphs
        if (p.text_content() or "").strip()
    ]
    ementa = None
    for p in paras:
        if first.get("processo") and first["processo"] in p:
            continue
        if len(p) > 60 and not p.lower().startswith("participantes"):
            ementa = p
            break
    docs = []
    for a in tree.xpath("//a[@href]"):
        href = a.get("href") or ""
        if href.lower().endswith(".pdf"):
            docs.append(
                {
                    "url": urljoin(url, href),
                    "label": (a.text_content() or "").strip() or "pdf",
                }
            )
    return ParsedDecision(
        profile="cvm_colegiado",
        kind="decisao_colegiado_cvm",
        court="CVM",
        official_id=str(first["official_id"]),
        ementa=ementa or first["assunto"],
        text="\n\n".join(paras),
        judgment_date=meeting_date,
        documents=docs,
        metadata={
            "title": title,
            "processo": first.get("processo"),
            "ata": reuniao,
            "decisoes": decisoes,
            "related": {"ata": reuniao, "url": url},
        },
    )


def _parse_search(body, *, base, source_id, limite):
    tree = lxml_html.fromstring(body)
    text = tree.text_content()
    if _MAINTENANCE.search(text):
        raise Unavailable('resposta_invalida')
    marker = re.search(r'(\d[\d.]*)\s+resultados?\s+encontrados',text,re.I)
    if re.search(r'\bNenhum resultado encontrado\b',text,re.I):
        return []
    links = tree.xpath('//a[contains(@href,"/decisoes/")]')
    out = []
    seen = set()
    for a in links:
        href = urljoin(base,a.get('href'))
        if not re.search(r'/decisoes/\d{4}/\d{8}_R\d+/',href) or href in seen:
            continue
        seen.add(href)
        out.append(Candidate(source_id=source_id,key=href,title=a.text_content().strip(),url=href,metadata={'kind':'decisao_colegiado_cvm'}))
        if len(out) >= limite:
            break
    if not out and not (marker and int(marker[1].replace('.','')) == 0):
        raise Unavailable('resposta_inesperada')
    return out
