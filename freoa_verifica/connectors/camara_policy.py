"""Admissão Legin da decisão 0077. Não gera endereços nem realiza I/O."""
from __future__ import annotations

import re
from datetime import date
from urllib.parse import parse_qsl, urlsplit, urljoin, urldefrag

HOSTS = frozenset({"www.camara.leg.br", "www2.camara.leg.br"})
FAIXAS = frozenset({"1970-1979", "1980-1987"})
MESES = dict(zip(("janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho",
                 "agosto", "setembro", "outubro", "novembro", "dezembro"), range(1, 13)))
PARES = {"lei": "lei", "leicom": "leicomplementar", "medpro": "medidaprovisoria",
         "declei": "decreto-lei", "decret": "decreto"}
_ATO = re.compile(r"/legin/fed/(lei|leicom|medpro|declei|decret)/(\d{4}(?:-\d{4})?)/"
                  r"(lei|leicomplementar|medidaprovisoria|decreto-lei|decreto)-"
                  r"([1-9]\d*)-(\d{1,2})-([a-z]+)-(\d{4})-([1-9]\d*)-"
                  r"(norma-p[le]\.html|normaatualizada-pl\.html|"
                  r"publicacaooriginal-[1-9]\d*-pl\.html|anexo-pl\.pdf)")


def validar_url(url: str) -> dict:
    """Validação estrutural, inclusive na releitura. Vínculo é conferido separadamente."""
    if not isinstance(url, str) or any(c in url for c in ("\\", "#")) or any(not 33 <= ord(c) <= 126 for c in url):
        raise ValueError("url_camara_invalida")
    p = urlsplit(url)
    if p.scheme != "https" or p.netloc not in HOSTS or p.fragment or ".." in p.path or "%" in p.path:
        raise ValueError("url_camara_invalida")
    if p.path == "/robots.txt" and not p.query:
        return {"recurso": "robots", "mime": "text/plain"}
    if p.netloc == "www.camara.leg.br":
        if p.path == "/legislacao" and not p.query:
            return {"recurso": "portal", "mime": "text/html"}
        if p.path == "/legislacao/busca":
            # Percent-encoding só na query do formulário, nunca no caminho de conteúdo.
            return validar_busca(url)
        raise ValueError("rota_camara_nao_admitida")
    m = _ATO.fullmatch(p.path)
    if not m or p.query:
        raise ValueError("rota_camara_nao_admitida")
    familia, periodo, radical, numero, dia, mes, ano, ident, sufixo = m.groups()
    if PARES[familia] != radical or mes not in MESES:
        raise ValueError("identidade_slug_invalida")
    date(int(ano), MESES[mes], int(dia))
    if "-" in periodo:
        if periodo not in FAIXAS or not int(periodo[:4]) <= int(ano) <= int(periodo[5:]):
            raise ValueError("periodo_incoerente")
    elif periodo != ano:
        raise ValueError("periodo_incoerente")
    legislativo = familia in {"lei", "leicom"}
    if sufixo.startswith("norma-"):
        if sufixo != ("norma-pl.html" if legislativo else "norma-pe.html"):
            raise ValueError("formato_nao_demonstrado")
        recurso = "norma"
    elif not legislativo or (sufixo == "anexo-pl.pdf" and familia != "leicom"):
        raise ValueError("formato_nao_demonstrado")
    else:
        recurso = ("atualizado" if sufixo == "normaatualizada-pl.html" else
                   "anexo" if sufixo == "anexo-pl.pdf" else "original")
    return dict(recurso=recurso, mime="application/pdf" if recurso == "anexo" else "text/html",
                familia=familia, numero=numero, ano=int(ano), id=ident)


def validar_busca(url: str) -> dict:
    p = urlsplit(url)
    if p.scheme != "https" or p.netloc != "www.camara.leg.br" or p.path != "/legislacao/busca" or p.fragment:
        raise ValueError("busca_invalida")
    pares = parse_qsl(p.query, keep_blank_values=True, strict_parsing=True)
    q = dict(pares)
    if len(pares) != 5 or set(q) != {"abrangencia", "tipo", "numero", "ano", "geral"}:
        raise ValueError("campos_busca_invalidos")
    if (q["abrangencia"] != "Legislação Federal" or q["tipo"] not in {"Lei Ordinária", "Lei Complementar"}
            or not re.fullmatch(r"[1-9]\d*", q["numero"]) or not re.fullmatch(r"\d{4}", q["ano"]) or q["geral"]):
        raise ValueError("valores_busca_invalidos")
    return {"recurso": "busca", "mime": "text/html"}


def url_publicada(base: str, href: str) -> str:
    return urldefrag(urljoin(base, href))[0]
