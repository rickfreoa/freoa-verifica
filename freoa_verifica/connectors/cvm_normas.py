"""Conector CVM normas — resoluções, instruções e correlatos."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

from lxml import html as lxml_html

from freoa_verifica.connectors.base import (
    Candidate,
    Connector,
    HealthProbe,
    HealthReport,
    Unavailable,
    register,
)
from freoa_verifica.connectors.httputil import connector_fetch, form_body
from freoa_verifica.parsers.cvm_docx import parse_cvm_docx
from freoa_verifica.parsers.model import Issue, ParsedDocument
from freoa_verifica.transport import Response, Session

MAX_ITENS_PAGINA = 500

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None  # type: ignore

_HOSTS = frozenset({"conteudo.cvm.gov.br"})
_PREFIXES = {
    "conteudo.cvm.gov.br": (
        "/legislacao/",
        "/export/",
        "/system/",
        "/decisoes/",
    )
}
_MIMES = frozenset(
    {
        "text/html",
        "application/xhtml+xml",
        "application/pdf",
        "application/octet-stream",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
        "text/plain",
    }
)

_INDEX = {
    "resolucoes": {
        "get": "https://conteudo.cvm.gov.br/legislacao/index.html?buscado=true&pasta=resolucoes&filtro=todos&contCategoriasCheck=1&vimDaCategoria=/legislacao/resolucoes/",
        "page": "https://conteudo.cvm.gov.br/legislacao/resolucoes.html",
        "prefix": "resol",
        "folder": "resolucoes",
    },
    "instrucoes": {
        "get": "https://conteudo.cvm.gov.br/legislacao/index.html?buscado=true&pasta=instrucoes&filtro=todos&contCategoriasCheck=1&vimDaCategoria=/legislacao/instrucoes/",
        "page": "https://conteudo.cvm.gov.br/legislacao/instrucoes.html",
        "prefix": "inst",
        "folder": "instrucoes",
    },
    "pareceres-orientacao": {
        "get": "https://conteudo.cvm.gov.br/legislacao/index.html?buscado=true&pasta=pareceres-orientacao&filtro=todos&contCategoriasCheck=1&vimDaCategoria=/legislacao/pareceres-orientacao/",
        "page": "https://conteudo.cvm.gov.br/legislacao/pareceres-orientacao.html",
        "prefix": "pare",
        "folder": "pareceres-orientacao",
    },
    "oficios-circulares": {
        "get": "https://conteudo.cvm.gov.br/legislacao/oficios-circulares.html",
        "page": "https://conteudo.cvm.gov.br/legislacao/oficios-circulares.html",
        "prefix": "oc",
        "folder": "oficios-circulares",
    },
    "deliberacoes": {
        "get": "https://conteudo.cvm.gov.br/legislacao/deliberacoes.html",
        "page": "https://conteudo.cvm.gov.br/legislacao/deliberacoes.html",
        "prefix": "deli",
        "folder": "deliberacoes",
    },
}


def _centena(n: int) -> str:
    if n < 100:
        return "001"
    return f"{(n // 100) * 100:03d}"


@register
class CvmNormasConnector(Connector):
    id = "cvm_normas"
    authority = "CVM"
    hosts = _HOSTS
    path_prefixes = _PREFIXES
    mimes = _MIMES
    user_agent = "browser"
    coverage = {
        "colecoes": list(_INDEX.keys()),
        "periodo": "acervo portal",
        "busca_textual": True,
        "ementa": True,
        "inteiro_teor": True,
        "atualizacao": "índice OpenCms + página do ato",
    }

    def health(self) -> HealthReport:
        probes: list[HealthProbe] = []
        try:
            found = self.search("Resolução CVM 80", tipo="resolucoes", numero=80)
            probes.append(HealthProbe("positivo", "ok" if found else "failed", None))
        except Exception as exc:
            probes.append(HealthProbe("positivo", "unavailable", str(exc)[:200]))
        try:
            empty = self.search("FV_TERM_INEXISTENTE_CVM_XYZ", tipo="resolucoes", limite=5)
            probes.append(HealthProbe("negativo", "zero" if not empty else "failed", f"n={len(empty)}"))
        except Unavailable as exc:
            probes.append(HealthProbe("negativo", "unavailable", exc.reason))
        except Exception as exc:
            probes.append(HealthProbe("negativo", "unavailable", str(exc)[:200]))
        try:
            cand = self.resolve({"tipo": "resolucoes", "numero": 80})
            assert cand is not None
            doc = self.parse(self.fetch(cand))
            probes.append(
                HealthProbe("documento", "ok" if doc.title or doc.text else "failed", doc.title[:80] if doc.title else None)
            )
        except Exception as exc:
            probes.append(HealthProbe("documento", "unavailable", str(exc)[:200]))
        return HealthReport(
            self.id,
            tuple(probes),
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def search(self, q: str, **filtros: Any) -> list[Candidate]:
        tipo = str(filtros.get("tipo") or "resolucoes")
        if tipo not in _INDEX:
            tipo = "resolucoes"
        numero = filtros.get("numero")
        if numero is None and q:
            m = re.search(r"(?i)(?:resolu[cç][aã]o|instru[cç][aã]o|parecer)\s*(?:cvm\s*)?(\d+)", q)
            if m:
                numero = int(m.group(1))
        if numero is not None:
            cand = self.resolve({"tipo": tipo, "numero": int(numero)})
            return [cand] if cand else []
        return self._search_index(q, tipo=tipo, limite=int(filtros.get("limite") or 20), pagina=int(filtros.get("pagina") or 1))

    def resolve(self, key: Any) -> Candidate | None:
        tipo, numero = _parse_key(key)
        if tipo is None or numero is None:
            return None
        meta = _INDEX.get(tipo, _INDEX["resolucoes"])
        nnn = f"{int(numero):03d}"
        page_url = f"https://conteudo.cvm.gov.br/legislacao/{meta['folder']}/{meta['prefix']}{nnn}.html"
        faixa = _centena(int(numero))
        base_anexo = (
            f"https://conteudo.cvm.gov.br/legislacao/{meta['folder']}/anexos/{faixa}/"
            f"{meta['prefix']}{nnn}"
        )
        export_anexo = (
            f"https://conteudo.cvm.gov.br/export/sites/cvm/legislacao/{meta['folder']}/anexos/{faixa}/"
            f"{meta['prefix']}{nnn}"
        )
        return Candidate(
            source_id=self.id,
            key=f"cvm:{tipo}:{int(numero)}",
            title=f"{meta['prefix']} {int(numero)}".replace("resol", "Resolução CVM").replace("inst", "Instrução CVM"),
            url=page_url,
            metadata={
                "tipo": tipo,
                "numero": int(numero),
                "page_url": page_url,
                "docx_consolid": base_anexo + "consolid.docx",
                "pdf_consolid": export_anexo + "consolid.pdf",
                "pdf_original": export_anexo + ".pdf",
            },
        )

    def fetch(self, candidate: Candidate) -> Response:
        """Prioridade: consolid.docx → consolid.pdf → original.pdf → página HTML."""
        urls = [
            candidate.metadata.get("docx_consolid"),
            candidate.metadata.get("pdf_consolid"),
            candidate.metadata.get("pdf_original"),
            candidate.metadata.get("page_url") or candidate.url,
        ]
        last: Unavailable | None = None
        for url in urls:
            if not url:
                continue
            try:
                return connector_fetch(
                    url,
                    hosts=self.hosts,
                    path_prefixes=self.path_prefixes,
                    mimes=self.mimes,
                    user_agent=self.user_agent,
                    timeout=60.0,
                    max_bytes=20 * 1024 * 1024,
                )
            except Unavailable as exc:
                last = exc
                if exc.reason.startswith("http_404"):
                    continue
                # alguns anexos podem falhar; tenta próximo
                continue
        raise last or Unavailable("sem_documento")

    def parse(self, resp: Response) -> ParsedDocument:
        kind = _kind_from_url(resp.final_url)
        if kind == "docx" or resp.body[:2] == b"PK":
            return parse_cvm_docx(resp.body)
        if kind == "pdf" or resp.body[:4] == b"%PDF":
            return _parse_pdf(resp.body, source=resp.final_url)
        # HTML da página do ato — ementa/situação
        return _parse_ato_html(resp.body, base_url=resp.final_url)

    def _search_index(self, q: str, *, tipo: str, limite: int, pagina: int = 1) -> list[Candidate]:
        meta = _INDEX[tipo]
        # Sessão efêmera: JSESSIONID entre GET e POST (nunca em recibos).
        session = Session()
        init = connector_fetch(
            meta["get"],
            hosts=self.hosts,
            path_prefixes=self.path_prefixes,
            mimes=self.mimes,
            user_agent=self.user_agent,
            timeout=45.0,
            session=session,
            expected_content=r'<(?:article\b|a\b[^>]*href=["\'][^"\']*/legislacao/(?:resolucoes/resol|pareceres-orientacao/pare))',
        )
        if not session.has_cookie("JSESSIONID"):
            raise Unavailable("sessao_ausente")
        tree = lxml_html.fromstring(init.body)
        itens = min(MAX_ITENS_PAGINA, max(1, int(limite or 100)))
        fields = {
            "searchPage": str(max(1, pagina)),
            "lastName": "",
            "numero": "",
            "filtro": "todos",
            "dataInicio": "",
            "dataFim": "",
            "buscado": "false",
            "contCategoriasCheck": "1",
            "itensPagina": str(itens),
            "ordenar": "recentes",
            "dataInicioBound": _hidden(tree, "dataInicioBound"),
            "dataFimBound": _hidden(tree, "dataFimBound"),
            "listaBuscaAside": "",
            "tipos": "",
            "tags": "",
        }
        if q:
            fields["lastName"] = q
            fields["buscado"] = "true"
        post_url = "https://conteudo.cvm.gov.br/system/modules/br.com.squadra.legislacao/elements/resultadoLegislacao.jsp"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        resp = connector_fetch(
            post_url,
            hosts=self.hosts,
            path_prefixes=self.path_prefixes,
            mimes=self.mimes,
            user_agent=self.user_agent,
            method="POST",
            body=form_body(fields),
            headers=headers,
            timeout=60.0,
            session=session,
            expected_content=r'<article\b|class=["\'][^"\']*orderResults',
        )
        return _parse_list_html(resp.body, source_id=self.id, tipo=tipo, limite=limite, q=q)


def _kind_from_url(url: str) -> str:
    u = url.lower()
    if u.endswith(".docx"):
        return "docx"
    if u.endswith(".pdf"):
        return "pdf"
    return "html"


def _hidden(tree, name: str) -> str:
    el = tree.xpath(f'//input[@name="{name}"]/@value')
    return str(el[0]) if el else ""


def _parse_list_html(
    body: bytes, *, source_id: str, tipo: str, limite: int, q: str
) -> list[Candidate]:
    text = body.decode("utf-8", errors="replace")
    tree = lxml_html.fromstring(body)
    total_el = tree.xpath('//*[contains(@class,"orderResults")]//span')
    total_txt = total_el[0].text_content() if total_el else ""
    if not total_txt:
        m = re.search(r"(\d+)\s+resultados?\s+encontrados", text, re.I)
        total_txt = m.group(0) if m else ""
    if re.fullmatch(r"\s*Nenhum resultado encontrado\s*", total_txt, re.I):
        return []
    m_total = re.search(r"(\d+)", total_txt)
    if m_total and int(m_total.group(1)) == 0:
        return []
    articles = tree.xpath("//article")
    if not articles and not m_total:
        # fallback: página estática de resolucoes.html
        articles = tree.xpath("//a[contains(@href,'/legislacao/')]")
        if not articles:
            raise Unavailable("resposta_inesperada")
    out: list[Candidate] = []
    q_lower = (q or "").lower()
    for art in articles:
        if len(out) >= limite:
            break
        if art.tag == "a":
            href = art.get("href") or ""
            title = (art.text_content() or "").strip()
            ementa = None
            situacao = None
        else:
            links = art.xpath(".//h3//a")
            if not links:
                continue
            a = links[0]
            href = a.get("href") or ""
            title = (a.text_content() or "").strip()
            desc = art.xpath('.//*[contains(@class,"contentDesc")]')
            ementa = desc[0].text_content().strip() if desc else None
            situacao = None
            if re.search(r"(?i)revogad", title + " " + (ementa or "")):
                situacao = "revogada"
        if q_lower and q_lower not in (title + " " + (ementa or "")).lower():
            continue
        abs_url = urljoin("https://conteudo.cvm.gov.br/", href)
        num_m = re.search(r"(\d+)", title)
        dates = art.xpath(".//b/text()") if art.tag != "a" else []
        dated_year = next((m.group(0) for value in dates
                           if (m := re.search(r"\b(?:19|20)\d{2}\b", value))), None)
        out.append(
            Candidate(
                source_id=source_id,
                key=f"cvm:{tipo}:{num_m.group(1) if num_m else title}",
                title=title,
                url=abs_url,
                snippet=(ementa or "")[:300] or None,
                metadata={"tipo": tipo, "ementa": ementa, "situacao": situacao,
                          "page_url": abs_url, "ano": int(dated_year) if dated_year else None},
            )
        )
    if not out and m_total and int(m_total.group(1)) == 0:
        return []
    if not out and q:
        return []
    if not out:
        raise Unavailable("resposta_inesperada")
    return out


def _parse_ato_html(body: bytes, *, base_url: str) -> ParsedDocument:
    tree = lxml_html.fromstring(body)
    h2 = tree.xpath("//article//h2|//h2")
    title = h2[0].text_content().strip() if h2 else ""
    situacao = "revogada" if re.search(r"(?i)revogad", title) else "vigente"
    paras = tree.xpath("//article//section[contains(@class,'contentArticle')]//p")
    ementa = None
    for p in paras:
        t = (p.text_content() or "").strip()
        if t and not re.match(r"(?i)^(publicad|tue |mon |wed |thu |fri |sat |sun )", t):
            if "revogad" in t.lower() and ementa is None:
                situacao = t
            elif ementa is None and len(t) > 40:
                ementa = t
                break
    links = []
    for a in tree.xpath("//a[@href]"):
        href = a.get("href") or ""
        if any(href.lower().endswith(ext) for ext in (".pdf", ".docx", ".doc")):
            links.append(urljoin(base_url, href))
    text = "\n".join((p.text_content() or "").strip() for p in paras if (p.text_content() or "").strip())
    return ParsedDocument(
        profile="cvm_html",
        parser_version="cvm-html-1",
        title=title,
        ementa=ementa,
        text=f"[situacao={situacao}]\n" + text,
        provisions=[],
        issues=[],
        amendments=[],
    )


def _parse_pdf(body: bytes, *, source: str) -> ParsedDocument:
    text = ""
    if PdfReader is not None:
        import io

        reader = PdfReader(io.BytesIO(body))
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        text = "\n".join(parts)
    issues = [
        Issue(
            code="PDF_SEM_RASURAS",
            path=None,
            detail="PDF consolidado sem marcas de rasura: redações antigas indisponíveis",
            blocking_scope=None,
        )
    ]
    from freoa_verifica.citation import extract
    epigraph = re.split(r"\bArt\.?\s*1[ºo°]?[.\s]",text[:4000],maxsplit=1,flags=re.I)[0]
    epigraph = re.sub(r"\bN\s+o\s+(?=\d)", "Nº ", epigraph, flags=re.I)
    candidates = [c for c in extract(epigraph) if c.work and c.work.authority == "cvm"]
    title = epigraph[candidates[0].span[0]:candidates[0].span[1]+200] if candidates else ""
    return ParsedDocument(
        profile="cvm_pdf",
        parser_version="cvm-pdf-1",
        title=title,
        ementa=None,
        text=text,
        provisions=[],
        issues=issues,
    )


def _parse_key(key: Any) -> tuple[str | None, int | None]:
    if isinstance(key, str):
        m = re.match(r"cvm:([\w-]+):(\d+)$", key)
        if m:
            return m.group(1), int(m.group(2))
        m = re.search(r"(\d+)", key)
        return "resolucoes", int(m.group(1)) if m else None
    if isinstance(key, dict):
        tipo = str(key.get("tipo") or "resolucoes").lower()
        tipo = {"resolucao":"resolucoes", "instrucao":"instrucoes", "parecer_orientacao":"pareceres-orientacao", "deliberacao":"deliberacoes"}.get(tipo,tipo)
        numero = key.get("numero")
        return tipo, int(numero) if numero is not None else None
    return None, None
