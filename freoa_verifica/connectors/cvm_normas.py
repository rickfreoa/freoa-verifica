"""Conector CVM normas — resoluções, instruções e correlatos."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

from lxml import etree as lxml_etree
from lxml import html as lxml_html

from freoa_verifica.connectors.base import (
    CandidateList,
    Candidate,
    Connector,
    HealthProbe,
    HealthReport,
    Unavailable,
    register,
)
from freoa_verifica.connectors.httputil import connector_fetch, form_body
from freoa_verifica.identidade_http import UA_POR_CONECTOR
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
    user_agent = UA_POR_CONECTOR["cvm_normas"]
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
            especie, num_q = _especie_numero(q)
            if num_q is not None:
                numero = num_q
                tipo = especie or tipo  # M2: "Instrução CVM 358" não vai à pasta de resoluções
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
                # Só a ausência explícita da representação autoriza tentar a próxima; desafio,
                # recusa, fonte fora esgotada e resposta inválida interrompem e propagam.
                if exc.reason not in {"http_404", "http_410"}:
                    raise
                last = exc
        raise last or Unavailable("sem_documento")

    def fetch_situacao(self, candidate: Candidate) -> Response:
        """C2: a página do ato é sempre capturada como evidência de situação."""
        return connector_fetch(
            candidate.metadata.get("page_url") or candidate.url,
            hosts=self.hosts,
            path_prefixes=self.path_prefixes,
            mimes=self.mimes,
            user_agent=self.user_agent,
            timeout=45.0,
            max_bytes=5 * 1024 * 1024,
        )

    def parse(self, resp: Response) -> ParsedDocument:
        kind = _kind_from_url(resp.final_url)
        if kind == "docx" or resp.body[:2] == b"PK":
            return _parse_docx(resp.body)
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


_ESPECIES = (
    (r"resolu[cç][aã]o", "resolucoes"),
    (r"instru[cç][aã]o", "instrucoes"),
    (r"parecer(?:\s+de)?(?:\s+orienta[cç][aã]o)?", "pareceres-orientacao"),
    (r"delibera[cç][aã]o", "deliberacoes"),
    (r"of[ií]cio[\s-]+circular", "oficios-circulares"),
)
_ESPECIE_NUM = re.compile(
    r"(?i)\b(" + "|".join(p for p, _ in _ESPECIES) + r")\s*(?:cvm\s*)?(?:(?:n[ºo°.]+|n\.?\s*[ºo°])\s*)?(\d[\d.]*)"
)


def _especie_numero(texto: str) -> tuple[str | None, int | None]:
    m = _ESPECIE_NUM.search(texto or "")
    if not m:
        return None, None
    rotulo = m.group(1)
    tipo = next(t for p, t in _ESPECIES if re.fullmatch(p, rotulo, re.I))
    digitos = m.group(2).replace(".", "")
    return tipo, int(digitos) if digitos.isdigit() else None


def _html_tree(body: bytes):
    """UTF-8 primeiro; sem isso o lxml presume latin-1 e produz mojibake (A4)."""
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        text = body.decode("cp1252", errors="replace")
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text)
    try:
        return lxml_html.fromstring(text)
    except (ValueError, lxml_etree.ParserError) as exc:
        raise Unavailable("resposta_inesperada") from exc


def _parse_list_html(
    body: bytes, *, source_id: str, tipo: str, limite: int, q: str
) -> list[Candidate]:
    tree = _html_tree(body)
    text = tree.text_content()
    total_el = tree.xpath('//*[contains(@class,"orderResults")]//span')
    total_txt = total_el[0].text_content() if total_el else ""
    if not total_txt:
        m = re.search(r"(\d+)\s+resultados?\s+encontrados", text, re.I)
        total_txt = m.group(0) if m else ""
    if re.fullmatch(r"\s*Nenhum resultado encontrado\s*", total_txt, re.I):
        return []
    m_total = re.search(r"(\d+)", total_txt)
    total = int(m_total.group(1)) if m_total else None
    if total == 0:
        return []
    articles = tree.xpath("//article")
    if not articles and total is None:
        # fallback: página estática de resolucoes.html
        articles = tree.xpath("//a[contains(@href,'/legislacao/')]")
        if not articles:
            raise Unavailable("resposta_inesperada")
    por_ato: dict[str, Candidate] = {}
    for art in articles:
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
        abs_url = urljoin("https://conteudo.cvm.gov.br/", href)
        especie, num_t = _especie_numero(title)
        num_m = re.search(r"(\d+)", title)
        numero = num_t if num_t is not None else (int(num_m.group(1)) if num_m else None)
        tipo_item = especie or tipo
        dates = art.xpath(".//b/text()") if art.tag != "a" else []
        dated_year = next((m.group(0) for value in dates
                           if (m := re.search(r"\b(?:19|20)\d{2}\b", value))), None)
        cand = Candidate(
            source_id=source_id,
            key=f"cvm:{tipo_item}:{numero if numero is not None else title}",
            title=title,
            url=abs_url,
            snippet=(ementa or "")[:300] or None,
            metadata={"tipo": tipo_item, "ementa": ementa, "situacao": situacao,
                      "page_url": abs_url, "ano": int(dated_year) if dated_year else None},
        )
        # M3: um item por ato; anexo não normativo cede lugar à página/peça do ato.
        anterior = por_ato.get(cand.key)
        if anterior is None or (_e_anexo(anterior) and not _e_anexo(cand)):
            por_ato[cand.key] = cand
    out = CandidateList(list(por_ato.values())[:limite], total)
    if not out:
        if total is None and not articles:
            raise Unavailable("resposta_inesperada")
        raise Unavailable("itens_nao_lidos")  # A4: a fonte informa total>0 e nada foi lido
    return out


def _e_anexo(c: Candidate) -> bool:
    return bool(re.search(r"(?i)\banexo\b|/anexos/", f"{c.title} {c.url}"))


def ler_situacao_pagina(body: bytes, esperado: tuple[str | None, int | None] | None = None) -> dict[str, Any] | None:
    """Situação cadastral declarada na página do ato (C2).

    None = página ilegível (sem título/artigo, ou sem a identidade do ato: espécie e número
    no título, iguais a `esperado` quando dado): o chamador grava `ilegivel`.
    A ausência de marca de revogação numa página lida é `vigente_declarada`,
    nunca prova de vigência temporal.
    """
    try:
        tree = _html_tree(body)
    except Unavailable:
        return None
    h2 = tree.xpath("//article//h2|//h2")
    if not h2 or not tree.xpath("//article"):
        return None
    title = h2[0].text_content().strip()
    especie, numero = _especie_numero(title)
    if especie is None or numero is None or (esperado is not None and esperado != (especie, numero)):
        return None  # "Serviço indisponível" ou página de outro ato não declara situação alguma
    textos = [(p.text_content() or "").strip() for p in tree.xpath("//article//p")]
    marca = re.compile(r"(?is)^\W*(revogad[ao]|cancelad[ao])\b")
    achado = next((t for t in textos if marca.match(t)), None)
    if achado is None and re.search(r"(?i)\((?:revogad|cancelad)", title):
        achado = title
    if achado is None:
        return {"situacao": "vigente_declarada", "texto_oficial": None, "ato_revogador": None}
    cancelada = bool(re.search(r"(?i)cancelad", achado[:20]))
    rev = re.search(r"(?is)\bpel[ao]s?\s+(.+?)(?=\s*(?:[,;.(]|\s+de\s+\d|$))", achado)
    return {
        "situacao": "cancelada" if cancelada else "revogada",
        "texto_oficial": re.sub(r"\s+", " ", achado)[:500],
        "ato_revogador": rev.group(1).strip()[:200] if rev else None,
    }


def _parse_ato_html(body: bytes, *, base_url: str) -> ParsedDocument:
    tree = _html_tree(body)
    h2 = tree.xpath("//article//h2|//h2")
    title = h2[0].text_content().strip() if h2 else ""
    lida = ler_situacao_pagina(body)
    situacao = lida["situacao"] if lida else "nao_declarada"  # C2: nunca presume vigente
    paras = tree.xpath("//article//section[contains(@class,'contentArticle')]//p")
    ementa = None
    for p in paras:
        t = (p.text_content() or "").strip()
        if t and not re.match(r"(?i)^(publicad|tue |mon |wed |thu |fri |sat |sun )", t):
            if "revogad" in t.lower():
                continue
            if ementa is None and len(t) > 40:
                ementa = t
                break
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


# F03: PDF sempre em processo descartável com limites (decisão 0026).
PDF_MAX_PAGINAS = 600
PDF_MAX_TEXTO = 8 * 1024 * 1024
PDF_TIMEOUT_S = 90.0


DOCX_TIMEOUT_S = 60.0


def _parse_docx(body: bytes) -> ParsedDocument:
    from freoa_verifica.parsers.isolated import parse_isolated

    doc = parse_isolated("cvm_docx", body, DOCX_TIMEOUT_S)
    if doc.profile == "cvm_docx" and not doc.quarantined:
        return doc
    detalhe = next((i.detail for i in doc.issues if i.code == "TRUNCATED"), "docx_isolado_falhou")
    raise Unavailable(f"docx_nao_processado: {detalhe}")


def _parse_pdf(body: bytes, *, source: str) -> ParsedDocument:
    from freoa_verifica.parsers.isolated import parse_isolated

    doc = parse_isolated("cvm_pdf", body, PDF_TIMEOUT_S)
    if doc.profile == "cvm_pdf" and not doc.quarantined:
        return doc
    detalhe = next((i.detail for i in doc.issues if i.code == "TRUNCATED"), "pdf_isolado_falhou")
    raise Unavailable(f"pdf_nao_processado: {detalhe}")


def _limpar_marca(obj: Any, marca: str) -> bool:
    """Remove a marca de corte de toda string do objeto (dataclasses, listas); diz se havia."""
    import dataclasses

    achou = False
    if isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str):
                if marca.strip() in v:
                    obj[i] = v.replace(marca, "").replace(marca.strip(), "").rstrip()
                    achou = True
            else:
                achou |= _limpar_marca(v, marca)
    elif dataclasses.is_dataclass(obj):
        for f in dataclasses.fields(obj):
            v = getattr(obj, f.name)
            if isinstance(v, str):
                if marca.strip() in v:
                    setattr(obj, f.name, v.replace(marca, "").replace(marca.strip(), "").rstrip())
                    achou = True
            elif isinstance(v, (list, tuple)) or dataclasses.is_dataclass(v):
                achou |= _limpar_marca(list(v) if isinstance(v, tuple) else v, marca)
    return achou


def parse_pdf_direto(body: bytes) -> ParsedDocument:
    """Corpo do filho isolado: aplica limites de páginas e texto."""
    if PdfReader is None:
        raise Unavailable("pdf_sem_biblioteca")
    import io

    reader = PdfReader(io.BytesIO(body))
    if len(reader.pages) > PDF_MAX_PAGINAS:
        raise Unavailable(f"pdf_paginas_excedidas: {len(reader.pages)}>{PDF_MAX_PAGINAS}")
    parts: list[str] = []
    total = 0
    for page in reader.pages:
        t = page.extract_text() or ""
        total += len(t)
        if total > PDF_MAX_TEXTO:
            raise Unavailable("pdf_texto_excedido")
        parts.append(t)
    text = "\n".join(parts)
    issues = [
        Issue(
            code="PDF_SEM_RASURAS",
            path=None,
            detail="PDF consolidado sem marcas de rasura: redações antigas indisponíveis",
            blocking_scope=None,
        )
    ]
    from freoa_verifica.parsers.html_devices import parse_html_devices
    from freoa_verifica.parsers.pdf_dispositivos import MARCA_CORTE, como_html, textos_de_corpo
    from freoa_verifica.parsers.sentinel import run_sentinels

    descartadas: set[str] = set()
    pagina_html = como_html(textos_de_corpo(reader.pages, descartadas))
    _t, _e, _txt, provisions, local_issues, amendments, editorial = parse_html_devices(
        pagina_html, base_url="https://conteudo.cvm.gov.br/")
    for extra in (amendments, editorial):
        _limpar_marca(extra, MARCA_CORTE)
    for prov in provisions:
        # Só a redação do próprio dispositivo decide; anotações e textos derivados apenas são limpos.
        proprio = any(MARCA_CORTE.strip() in r.text for r in prov.redactions)
        _limpar_marca(prov, MARCA_CORTE)
        if proprio:
            issues.append(Issue(code="MARGEM_ADJACENTE", path=prov.path, blocking_scope="provision",
                                detail="conteúdo não extraído do PDF (margem descartada ou imagem) é vizinho do dispositivo; texto não confirmável"))
    pagina_html = pagina_html.replace(MARCA_CORTE, "")
    if provisions:
        issues.append(Issue(
            code="ESTRUTURA_INFERIDA_PDF", path=None,
            detail="dispositivos inferidos de PDF sem marcação estrutural; conferir no original",
            blocking_scope=None))
        issues.extend(local_issues)
        if descartadas:  # transparência: o que saiu como cabeçalho/rodapé (decisão 0038)
            issues.append(Issue(code="MARGEM_DESCARTADA", path=None, blocking_scope=None,
                                detail="; ".join(sorted(t for t in descartadas if not t.isdigit()))[:500]))
    from freoa_verifica.citation import extract
    epigraph = re.split(r"\bArt\.?\s*1[ºo°]?[.\s]",text[:4000],maxsplit=1,flags=re.I)[0]
    epigraph = re.sub(r"\bN\s+o\s+(?=\d)", "Nº ", epigraph, flags=re.I)
    candidates = [c for c in extract(epigraph) if c.work and c.work.authority == "cvm"]
    title = epigraph[candidates[0].span[0]:candidates[0].span[1]+200] if candidates else ""
    doc = ParsedDocument(
        profile="cvm_pdf",
        parser_version="cvm-pdf-2",
        title=title,
        ementa=None,
        text=text,
        provisions=provisions,
        issues=issues,
        amendments=amendments if provisions else [],
        editorial_blocks=editorial if provisions else [],
    )
    if provisions:
        doc.issues.extend(run_sentinels(doc, raw=pagina_html))
    return doc


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
