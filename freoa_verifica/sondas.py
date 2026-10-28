"""Catálogo de fontes-sonda: hosts oficiais ainda sem conector, só para o instrumento de captura (S0, plano 1.4.0).

Uma fonte-sonda NÃO é fonte do produto: não entra em `registry()`, não é importada pelo serviço nem pelo servidor
MCP (teste estrutural em `tests/test_sondas.py`) e só é alcançada por `scripts/capturar_fixture.py --fonte-sonda`
com `--sonda` e `--url`. O pedido sai pelo transporte comum, com UA identificado do pacote.

Cada host consta aqui só se foi confirmado em página oficial (tribunal, CNJ ou CJF); `origem_hosts` registra, host a
host, a URL oficial da confirmação. Hosts não confirmados ficam em `HOSTS_RECUSADOS`, com o motivo. Nunca host de
agregador privado.

Escopo de caminho: `path_prefixes` vale para todos os hosts da fonte, exceto os de `hosts_sem_prefixo`. Estes são
páginas de aplicação de página única cuja raiz (`/`) o transporte não admite como prefixo (`allowed_path_prefixes`
recusa "/"); neles vale o host inteiro, ainda GET, ainda HTTPS, ainda com a allowlist de MIME.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

_MIMES = frozenset({"text/html", "application/json", "text/plain"})
_MIMES_PDF = _MIMES | {"application/pdf"}


@dataclass(frozen=True)
class FonteSonda:
    id: str
    descricao: str
    hosts: frozenset[str]
    path_prefixes: tuple[str, ...]
    mimes: frozenset[str]
    origem_hosts: str  # "host=URL oficial; host=URL oficial": onde cada host foi confirmado
    hosts_sem_prefixo: frozenset[str] = frozenset()
    nota: str = ""

    def __post_init__(self) -> None:
        if not self.hosts or not self.hosts_sem_prefixo <= self.hosts:
            raise ValueError(f"hosts inconsistentes em {self.id}")
        if not self.path_prefixes and self.hosts_sem_prefixo != self.hosts:
            raise ValueError(f"sem prefixos, todos os hosts devem ser sem_prefixo: {self.id}")
        if any(not p.startswith("/") or p == "/" for p in self.path_prefixes):
            raise ValueError(f"prefixo inválido em {self.id}")
        for host in self.hosts:
            if f"{host}=" not in self.origem_hosts:
                raise ValueError(f"host sem origem registrada: {host}")


def prefixos_por_host(fonte: FonteSonda) -> dict[str, tuple[str, ...]] | None:
    """Mapa host -> prefixos no formato do transporte; None quando nenhum host tem escopo de caminho."""
    mapa = {h: fonte.path_prefixes for h in sorted(fonte.hosts - fonte.hosts_sem_prefixo)}
    return mapa or None


def _f(id_: str, descricao: str, hosts: set[str], prefixos: tuple[str, ...], origem: str, *, mimes=_MIMES,
       livres: set[str] = frozenset(), nota: str = "") -> tuple[str, FonteSonda]:
    return id_, FonteSonda(id_, descricao, frozenset(hosts), prefixos, mimes, origem, frozenset(livres), nota)


_ESAJ = "e-SAJ, consulta de jurisprudência de 2º grau (cjsg)"
_B = "confirmação nível B: página do próprio sistema, indexada por busca, não lida; "

FONTES_SONDA: Mapping[str, FonteSonda] = MappingProxyType(dict([
    _f("tst", "TST: pesquisa de jurisprudência (portal, backend REST e consulta de documento)",
       {"jurisprudencia.tst.jus.br", "jurisprudencia-backend.tst.jus.br", "consultadocumento.tst.jus.br"},
       ("/rest/", "/consultaDocumento/"),
       "jurisprudencia.tst.jus.br=https://jurisprudencia.tst.jus.br/ (portal oficial); "
       "jurisprudencia-backend.tst.jus.br=https://jurisprudencia.tst.jus.br/config.json (campo base_url do portal); "
       "consultadocumento.tst.jus.br=https://jurisprudencia.tst.jus.br/config.json (campos consulta_acordao_url e "
       "consulta_despacho_url)",
       mimes=_MIMES_PDF, livres={"jurisprudencia.tst.jus.br"},
       nota="nível A: o próprio portal publica seus endpoints; www.tst.jus.br respondeu 202 sem corpo (desafio) à "
            "leitura de pesquisa e não foi usado. A pesquisa textual é POST JSON em /rest/pesquisa-textual/: o "
            "instrumento só faz GET (ver docs/S0-SONDAS.md)."),
    _f("stf_acordaos", "STF: pesquisa de jurisprudência (acórdãos)",
       {"jurisprudencia.stf.jus.br"}, ("/pages/search", "/api/"),
       "jurisprudencia.stf.jus.br=https://portal.stf.jus.br/jurisprudencia/ (links para /pages/search)",
       nota="o conector stf registra o prefixo /api/ no mesmo host e declara WAF na busca textual"),
    _f("bnp", "CNJ: Banco Nacional de Precedentes (Pangea/BNP)",
       {"pangeabnp.pdpj.jus.br", "bnp.pdpj.jus.br"}, (),
       "pangeabnp.pdpj.jus.br=https://docs.pdpj.jus.br/servicos-negociais/BNP-Pangea/BNP%20-%20Manual%20de%20Utiliza%C3%A7%C3%A3o; "
       "bnp.pdpj.jus.br=https://www.cnj.jus.br/tecnologia-da-informacao-e-comunicacao/justica-4-0/banco-nacional-de-precedentes-bnp/",
       mimes=_MIMES, livres={"pangeabnp.pdpj.jus.br", "bnp.pdpj.jus.br"},
       nota="aplicação de página única; o caminho da API de pesquisa não consta de fonte oficial lida e deve ser "
            "descoberto na sonda (host inteiro admitido por isso)"),
    _f("djen", "CNJ: Diário de Justiça Eletrônico Nacional (consulta e API de comunicações)",
       {"comunica.pje.jus.br", "comunicaapi.pje.jus.br"}, ("/consulta", "/api/v1/"),
       "comunica.pje.jus.br=https://www.cnj.jus.br/programas-e-acoes/processo-judicial-eletronico-pje/comunicacoes-processuais/; "
       "comunicaapi.pje.jus.br=https://www.cnj.jus.br/programas-e-acoes/processo-judicial-eletronico-pje/comunicacoes-processuais/orientacoes-aos-tribunais/",
       nota="a página oficial documenta /api/v1 como API de envio dos tribunais, com autenticação; a consulta "
            "pública em GET /api/v1/comunicacao não está documentada nela e é o que a sonda testa"),
    _f("cjf_unificada", "CJF: pesquisa unificada de jurisprudência da Justiça Federal",
       {"jurisprudencia.cjf.jus.br", "www.cjf.jus.br"}, ("/jurisprudencia/",),
       "jurisprudencia.cjf.jus.br=https://www.trf1.jus.br/trf1/busca/ (menu Pesquisa > Jurisprudência: "
       "https://jurisprudencia.cjf.jus.br/?tribunal=trf1); "
       "www.cjf.jus.br=https://www.cjf.jus.br/jurisprudencia/unificada/",
       livres={"jurisprudencia.cjf.jus.br"},
       nota=_B + "www.cjf.jus.br; jurisprudencia.cjf.jus.br é nível A (link lido no portal do TRF1)"),
    _f("trf1", "TRF1: pesquisa de jurisprudência (via CJF) e inteiro teor de acórdãos",
       {"jurisprudencia.cjf.jus.br", "arquivo.trf1.jus.br"}, (),
       "jurisprudencia.cjf.jus.br=https://www.trf1.jus.br/trf1/busca/ (menu Pesquisa > Jurisprudência); "
       "arquivo.trf1.jus.br=https://www.trf1.jus.br/trf1/busca/ (menu Inteiro Teor)",
       mimes=_MIMES_PDF, livres={"jurisprudencia.cjf.jus.br", "arquivo.trf1.jus.br"},
       nota="nível A; o menu oficial do TRF1 aponta a pesquisa ao CJF (?tribunal=trf1), sem host próprio"),
    _f("trf2", "TRF2: portal de jurisprudência da 2ª Região",
       {"jurisprudencia.trf2.jus.br", "www10.trf2.jus.br"}, ("/consultas/",),
       "jurisprudencia.trf2.jus.br=https://www.trf2.jus.br/trf2/artigo/coport/consulta-de-jurisprudencia; "
       "www10.trf2.jus.br=https://www.trf2.jus.br/trf2/noticia/2024/trf2-portal-de-jurisprudencia-conta-com-novo-mecanismo-de-busca",
       livres={"jurisprudencia.trf2.jus.br"},
       nota="nível A; juris.trf2.jus.br aparece só em resultado de busca e ficou fora"),
    _f("trf3", "TRF3: busca de jurisprudência e acórdãos",
       {"web.trf3.jus.br"}, ("/jurisprudencia", "/acordaos/"),
       "web.trf3.jus.br=https://www.trf3.jus.br/carta-servicos/acordaos (links /jurisprudencia e /acordaos/Acordao)",
       mimes=_MIMES_PDF, nota="nível A"),
    _f("tjac", _ESAJ + " do TJAC", {"esaj.tjac.jus.br"}, ("/cjsg/",),
       "esaj.tjac.jus.br=https://www.tjac.jus.br/ (links /cjsg/consultaCompleta.do e /cjsg/resultadoCompleta.do)",
       mimes=_MIMES_PDF, nota="nível A"),
    _f("tjal", _ESAJ + " do TJAL", {"www2.tjal.jus.br"}, ("/cjsg/",),
       "www2.tjal.jus.br=https://www2.tjal.jus.br/cjsg/consultaCompleta.do (página do próprio tribunal)",
       mimes=_MIMES_PDF, nota=_B + "www2.tjal.jus.br"),
    _f("tjam", _ESAJ + " do TJAM", {"consultasaj.tjam.jus.br"}, ("/cjsg/",),
       "consultasaj.tjam.jus.br=https://consultasaj.tjam.jus.br/cjsg/consultaCompleta.do (página do próprio tribunal)",
       mimes=_MIMES_PDF, nota=_B + "consultasaj.tjam.jus.br"),
    _f("tjms", _ESAJ + " do TJMS", {"esaj.tjms.jus.br"}, ("/cjsg/",),
       "esaj.tjms.jus.br=https://esaj.tjms.jus.br/cjsg/consultaCompleta.do (página do próprio tribunal)",
       mimes=_MIMES_PDF, nota=_B + "esaj.tjms.jus.br"),
    _f("tjrj", "TJRJ: eJuris, consulta de jurisprudência", {"www3.tjrj.jus.br"}, ("/ejuris/",),
       "www3.tjrj.jus.br=https://www3.tjrj.jus.br/ejuris/ConsultarJurisprudencia.aspx (página do próprio sistema)",
       nota=_B + "www3.tjrj.jus.br; a leitura das páginas do portal www.tjrj.jus.br foi recusada pelo robots.txt do "
            "site à ferramenta de pesquisa e não foi contornada; www4.tjrj.jus.br ficou fora"),
    _f("tjmg", "TJMG: consulta de jurisprudência", {"www5.tjmg.jus.br"}, ("/jurisprudencia/",),
       "www5.tjmg.jus.br=https://www.tjmg.jus.br/portal-tjmg/jurisprudencia/consulta-de-jurisprudencia/ "
       "(links /jurisprudencia/decisao.do, formEspelhoAcordao.do)",
       nota="nível A; os links oficiais usam http, a sonda exige https"),
    _f("tjrs", "TJRS: pesquisa de jurisprudência", {"www.tjrs.jus.br"}, ("/novo/buscas-solr/", "/novo/busca/"),
       "www.tjrs.jus.br=https://www.tjrs.jus.br/novo/buscas-solr/ (página do próprio tribunal)",
       nota=_B + "www.tjrs.jus.br; a leitura foi recusada pelo robots.txt do site à ferramenta de pesquisa e não foi "
            "contornada; www3.tjrs.jus.br/site_php/consulta ficou fora (legado, não confirmado)"),
    _f("tjpr", "TJPR: consulta de jurisprudência", {"portal.tjpr.jus.br"}, ("/jurisprudencia/",),
       "portal.tjpr.jus.br=https://www.tjpr.jus.br/jurisprudencia (link https://portal.tjpr.jus.br/jurisprudencia/)",
       nota="nível A"),
]))

HOSTS_RECUSADOS: Mapping[str, str] = MappingProxyType({
    "jurisprudencia.trf1.jus.br": "não consta de página oficial lida; o TRF1 publica a pesquisa no CJF",
    "jurisprudencia.trf3.jus.br": "não consta de página oficial lida; o TRF3 publica em web.trf3.jus.br",
    "juris.trf2.jus.br": "apenas resultado de busca, sem página oficial lida",
    "www.tst.jus.br": "página de jurisprudência não lida: respondeu 202 sem corpo (desafio) e o robots.txt do site "
                      "foi recusado à ferramenta de pesquisa; sem contorno",
    "consultaunificada2.tst.jus.br": "pesquisa textual legada; apenas resultado de busca, sem página oficial lida",
    "www4.tjrj.jus.br": "duplicata de www3.tjrj.jus.br, apenas em resultado de busca",
    "www3.tjrs.jus.br": "consulta legada, apenas em resultado de busca",
    "www2.cjf.jus.br": "memória virtual e versão antiga da pesquisa unificada; fora do escopo da sonda",
    "hcomunicaapi.cnj.jus.br": "ambiente de homologação do DJEN, para integração de tribunais, não é fonte pública",
    "comunicaapi.cnj.jus.br": "citado na página oficial só como prefixo de ambiente, sem uso público documentado",
    "docs.pdpj.jus.br": "documentação do BNP, não é fonte de decisões",
    "marketplace.pdpj.jus.br": "marketplace de serviços da PDPJ, não é fonte de decisões",
    "juridico.ai": "agregador privado: nunca",
})
