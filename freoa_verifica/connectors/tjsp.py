"""Conector TJSP e-SAJ cjsg — busca de acórdãos e PDF do inteiro teor."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode


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
from freoa_verifica.connectors.httputil import connector_fetch, form_body
from freoa_verifica.identidade_http import UA_POR_CONECTOR
from freoa_verifica.texto_resposta import arvore_html, texto_da_resposta, texto_do_response
from freoa_verifica.transport import Response, Session

_HOST = "esaj.tjsp.jus.br"
_BASE = f"https://{_HOST}/cjsg/"
_HOSTS = frozenset({_HOST})
_PREFIXES = {_HOST: ("/cjsg/",)}
_MIMES = frozenset(
    {
        "text/html",
        "application/xhtml+xml",
        "application/pdf",
        "application/octet-stream",
        "text/plain",
    }
)

# Tetos de paginação (contrato e-SAJ: 20/página; deep paging >2000 falha).
MAX_PAGINA = 2000
MAX_LIMITE = 100


def _data_br(iso: Any) -> str | None:
    """AAAA-MM-DD -> DD/MM/AAAA (formato do formulário e-SAJ); outra forma não é enviada."""
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", str(iso or ""))
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else None


@dataclass(frozen=True)
class CjsgRequest:
    post_url: str
    fields: dict[str, Any]
    pagina: int
    page_url: str


def build_cjsg_request(q: str, **filtros: Any) -> CjsgRequest:
    """Formulário e URL da página da consulta cjsg; usado pelo conector e pela captura reproduzível."""
    fields = {
        "dados.buscaInteiroTeor": q,
        "dados.pesquisarComSinonimos": filtros.get("sinonimos", "S"),
        "dados.origensSelecionadas": filtros.get("origem", "T"),
        "tipoDecisaoSelecionados": filtros.get("tipo_decisao", "A"),
        "dados.ordenarPor": "dtPublicacao",
    }
    if filtros.get("numero_processo"):
        fields["dados.nuProcesso"] = filtros["numero_processo"]
        fields["dados.buscaInteiroTeor"] = ""
    dt_inicio = filtros.get("dt_inicio") or _data_br(filtros.get("desde"))
    dt_fim = filtros.get("dt_fim") or _data_br(filtros.get("ate"))
    if dt_inicio:
        fields["dados.dtJulgamentoInicio"] = dt_inicio
    if dt_fim:
        fields["dados.dtJulgamentoFim"] = dt_fim
    pagina = int(filtros.get("pagina") or 1)
    page_url = (
        _BASE
        + "trocaDePagina.do?"
        + urlencode(
            {
                "tipoDeDecisao": fields["tipoDecisaoSelecionados"],
                "pagina": str(pagina),
                "conversationId": "",
            }
        )
    )
    return CjsgRequest(_BASE + "resultadoCompleta.do", fields, pagina, page_url)


@register
class TjspConnector(Connector):
    id = "tjsp"
    authority = "Tribunal de Justiça de São Paulo"
    hosts = _HOSTS
    path_prefixes = _PREFIXES
    mimes = _MIMES
    user_agent = UA_POR_CONECTOR["tjsp"]
    filtros = {"desde": "remoto", "ate": "remoto"}  # datas de julgamento (0053)
    coverage = {
        "colecoes": ["acordãos_cjsg"],
        "periodo": "acervo e-SAJ",
        "busca_textual": True,
        "ementa": True,
        "inteiro_teor": True,
        "atualizacao": "sob demanda",
    }

    def health(self) -> HealthReport:
        probes: list[HealthProbe] = []
        try:
            found = self.search("acordo de acionistas", limite=3)
            probes.append(HealthProbe("positivo", "ok" if found else "failed", f"n={len(found)}"))
        except Exception as exc:
            probes.append(HealthProbe("positivo", "unavailable", str(exc)[:200]))
        try:
            empty = self.search("FVXYZTERMOSINTETICO99991QWERTY", limite=5)
            probes.append(HealthProbe("negativo", "zero" if not empty else "failed", f"n={len(empty)}"))
        except Unavailable as exc:
            probes.append(HealthProbe("negativo", "unavailable", exc.reason))
        except Exception as exc:
            probes.append(HealthProbe("negativo", "unavailable", str(exc)[:200]))
        try:
            found = self.search("acordo de acionistas", limite=1)
            if not found:
                probes.append(HealthProbe("documento", "failed", "sem candidato"))
            else:
                resp = self.fetch(found[0])
                ok = resp.body[:4] == b"%PDF"
                probes.append(
                    HealthProbe(
                        "documento",
                        "ok" if ok else "failed",
                        f"status={resp.status}; bytes={len(resp.body)}",
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
        if not (q or "").strip():
            raise Unavailable("resposta_inesperada")
        # Sessão efêmera por consulta (CookieJar em memória; nunca em recibos).
        session = Session()
        req = build_cjsg_request(q, **filtros)
        init = connector_fetch(
            req.post_url,
            hosts=self.hosts,
            path_prefixes=self.path_prefixes,
            mimes=self.mimes,
            user_agent=self.user_agent,
            method="POST",
            body=form_body(req.fields),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "text/html",
            },
            timeout=60.0,
            session=session,
        )
        if not session.has_cookie("JSESSIONID"):
            raise Unavailable("sessao_ausente")
        if req.pagina < 1 or req.pagina > MAX_PAGINA:
            raise Unavailable("resposta_invalida")
        limite = min(MAX_LIMITE, max(1, int(filtros.get("limite") or 20)))
        page = connector_fetch(
            req.page_url,
            hosts=self.hosts,
            path_prefixes=self.path_prefixes,
            mimes=self.mimes,
            user_agent=self.user_agent,
            timeout=60.0,
            session=session,
        )
        return _parse_results(
            texto_do_response(page),  # `page.headers` não guarda todos os charsets: o Content-Type cru está no Response
            source_id=self.id,
            limite=limite,
        )

    def resolve(self, key: Any) -> Candidate | None:
        if isinstance(key, dict):
            cd = key.get("cdAcordao")
        else:
            cd = str(key)
        if not cd:
            return None
        return Candidate(
            source_id=self.id,
            key=str(cd),
            title=f"cdAcordao={cd}",
            url=f"{_BASE}getArquivo.do?cdAcordao={cd}&cdForo=0&casChecked=true",
            metadata={"cdAcordao": str(cd), "cdForo": "0"},
        )

    def fetch(self, candidate: Candidate) -> Response:
        cd = candidate.metadata.get("cdAcordao") or candidate.key
        url = f"{_BASE}getArquivo.do?cdAcordao={cd}&cdForo=0&casChecked=true"
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
        if resp.body[:4] == b"%PDF":
            text = _pdf_text(resp.body)
            return ParsedDecision(
                profile="tjsp_pdf",
                kind="acordao",
                court="TJSP",
                official_id=resp.url,
                text=text,
                documents=[{"url": resp.final_url, "label": "inteiro_teor"}],
            )
        text = _decode_html(resp.body, {"content-type": resp.content_type or resp.headers.get("content-type", "")})
        return ParsedDecision(
            profile="tjsp_html",
            kind="acordao",
            court="TJSP",
            official_id=resp.url,
            ementa=text[:2000],
            text=text,
        )


def _decode_html(body: bytes, headers: dict[str, str] | None = None) -> str:
    """Função única (BOM → charset do cabeçalho → meta → utf-8); inválido é `RespostaInvalida` (0061)."""
    h = headers or {}
    return texto_da_resposta(body, h.get("content-type") or h.get("Content-Type"))


def _parse_results(
    body: bytes,
    *,
    source_id: str,
    limite: int,
    headers: dict[str, str] | None = None,
) -> list[Candidate]:
    text = _decode_html(body, headers)
    m_total = re.search(
        r'id="totalResultadoAbaRetornoFiltro-A"[^>]*value="(\d+)"',
        text,
    )
    total = int(m_total.group(1)) if m_total else None  # a página não diz se é exato: total_exato fica nulo
    if total == 0:
        return CandidateList([], total=0)
    if "#%#emptySession#%#" in text:
        raise Unavailable("resposta_inesperada")
    # DOM sobre texto já decodificado (evita mojibake em Órgão/publicação/ementa).
    tree = arvore_html(text)
    rows = tree.xpath('//tr[contains(@class,"fundocinza1")]')
    if not rows:
        if m_total is None:
            raise Unavailable("resposta_inesperada")
        return CandidateList([], total=total)
    out: list[Candidate] = []
    for row in rows:
        if len(out) >= limite:
            break
        link = row.xpath('.//a[contains(@class,"downloadEmenta")]')
        if not link:
            continue
        a = link[0]
        cd = a.get("cdAcordao") or a.get("cdacordao") or ""
        cnj = (a.text_content() or "").strip()
        cnj = re.sub(r"\s+", " ", cnj).strip()
        ementa_el = row.xpath('.//div[contains(@class,"mensagemSemFormatacao")]')
        ementa = ementa_el[0].text_content().strip() if ementa_el else None
        meta_lines = {
            _norm_label(_label(td)): _value(td)
            for td in row.xpath('.//tr[contains(@class,"ementaClass2")]/td')
        }
        if not cd:
            continue
        out.append(
            Candidate(
                source_id=source_id,
                key=cd,
                title=cnj or cd,
                url=f"{_BASE}getArquivo.do?cdAcordao={cd}&cdForo=0&casChecked=true",
                snippet=(ementa or "")[:300] or None,
                metadata={
                    "cdAcordao": cd,
                    "cdForo": "0",
                    "cnj": cnj,
                    "classe_assunto": meta_lines.get(_norm_label("Classe/Assunto")),
                    "relator": meta_lines.get(_norm_label("Relator(a)")),
                    "comarca": meta_lines.get(_norm_label("Comarca")),
                    "orgao": meta_lines.get(_norm_label("Órgão julgador"))
                    or meta_lines.get(_norm_label("Orgao julgador")),
                    "data_julgamento": meta_lines.get(_norm_label("Data do julgamento")),
                    "data_publicacao": meta_lines.get(_norm_label("Data de publicação"))
                    or meta_lines.get(_norm_label("Data de publicacao")),
                    "ementa": ementa,
                },
            )
        )
    return CandidateList(out, total=total)


def _norm_label(value: str) -> str:
    return (
        (value or "")
        .strip()
        .lower()
        .replace("á", "a")
        .replace("ã", "a")
        .replace("à", "a")
        .replace("é", "e")
        .replace("ê", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ô", "o")
        .replace("õ", "o")
        .replace("ú", "u")
        .replace("ç", "c")
    )


def _label(td) -> str:
    strong = td.xpath("./strong")
    if strong:
        return (strong[0].text_content() or "").strip().rstrip(":")
    text = (td.text_content() or "").strip()
    if ":" in text:
        return text.split(":", 1)[0].strip()
    return text


def _value(td) -> str:
    text = (td.text_content() or "").strip()
    if ":" in text:
        return text.split(":", 1)[1].strip()
    return text


def _pdf_text(body: bytes) -> str:
    from freoa_verifica.parsers.isolated import texto_pdf_isolado

    return texto_pdf_isolado(body)
