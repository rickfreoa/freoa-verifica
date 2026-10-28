"""Catálogo de fontes-sonda: hosts oficiais ainda sem conector, só para o instrumento de captura (S0, plano 1.4.0).

Uma fonte-sonda NÃO é fonte do produto: não entra em `registry()`, não é importada pelo serviço nem pelo servidor
MCP (teste estrutural em `tests/test_sondas.py`) e só é alcançada por `scripts/capturar_fixture.py --fonte-sonda`
com `--sonda` e `--url`. O pedido sai pelo transporte comum, com UA identificado do pacote.

Proveniência (`confirmacao`, `hosts_b`): nível A = o host consta de página oficial (tribunal, CNJ ou CJF) que foi
LIDA, ou de configuração publicada pelo próprio portal; `origem_hosts` registra, host a host, a URL da confirmação.
Nível B = a página do próprio sistema, no domínio do tribunal, foi só indexada por busca, não lida. Hosts B ficam no
catálogo, mas o instrumento recusa a sonda neles (inclusive o `robots.txt`) sem `--confirmado-por-titular`, registrado
no `.captura.json`. Hosts sem nenhuma indicação oficial ficam em `HOSTS_RECUSADOS`. Nunca host de agregador privado.

Escopo de caminho: `rotas` dá, host a host, os caminhos que a sonda pode pedir. Cada rota é um caminho EXATO (igualdade
de string, sem prefixo: `/config.json.bak` ou `/rest/indicadores/admin` não são `/config.json` nem `/rest/indicadores`),
sem consulta (`?`), exceto nas rotas também listadas em `consultas`. Não há família de diretório (prefixo) no catálogo:
a raiz `/` não entra (o transporte não admite `/` como prefixo) e rota com segmento de login, admin, cadastro, auth,
conta ou usuario é recusada na construção. Host sem rota documentada tem `()`: só o `robots.txt`, que é exceção de
caminho exato, sem redirecionamento. A sonda também não segue redirecionamento (`max_redirects=0`): o destino de um
3xx, mesmo dentro da allowlist, não é pedido. Não há host de escopo livre.

Barreira registrada: fonte que já respondeu recusa (403, desafio) a qualquer leitura registrada sai do catálogo e entra
em `FONTES_BARRADAS` (e seus hosts em `HOSTS_RECUSADOS`); o instrumento a recusa antes da rede, sem nova tentativa por
outra rede ou rota. Acesso só por decisão do titular, por sessão assistida (decisão 0067) ou por documentação oficial.
Exceções: o DJEN (decisão 0069, restrição geográfica geral) e o TJRS (Disallow do robots.txt a outro User-Agent não é recusa ao produto) seguem no catálogo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, Mapping

_MIMES = frozenset({"text/html", "application/json", "text/plain"})
_MIMES_PDF = _MIMES | {"application/pdf"}


SEGMENTOS_PROIBIDOS = ("login", "admin", "cadastro", "auth", "conta", "usuario")


@dataclass(frozen=True)
class FonteSonda:
    id: str
    descricao: str
    hosts: frozenset[str]
    rotas: Mapping[str, tuple[str, ...]]  # host -> caminhos EXATOS permitidos; () = só robots.txt
    mimes: frozenset[str]
    origem_hosts: str  # "host=URL oficial; host=URL oficial": onde cada host foi confirmado
    confirmacao: Literal["A", "B"]  # pior nível entre os hosts: "B" se algum host é B
    hosts_b: frozenset[str] = frozenset()  # hosts de nível B (indexados, não lidos): sonda bloqueada
    nota: str = ""
    consultas: Mapping[str, tuple[str, ...]] = field(default_factory=lambda: MappingProxyType({}))  # host -> rotas (de `rotas`) que admitem consulta

    def __post_init__(self) -> None:
        if not self.hosts or set(self.rotas) != set(self.hosts):
            raise ValueError(f"hosts e rotas inconsistentes em {self.id}")
        if self.confirmacao not in ("A", "B"):
            raise ValueError(f"confirmacao inválida em {self.id}")
        if not self.hosts_b <= self.hosts or (self.confirmacao == "B") != bool(self.hosts_b):
            raise ValueError(f"confirmacao e hosts_b inconsistentes em {self.id}")
        for host, caminhos in self.rotas.items():
            if type(caminhos) is not tuple or any(
                not isinstance(p, str) or not p.startswith("/") or p == "/" or p.lower().startswith("/robots.txt")
                or any(c in p for c in "?#%\\") or any(w in p.lower() for w in SEGMENTOS_PROIBIDOS)
                for p in caminhos
            ):
                raise ValueError(f"rota inválida em {self.id}: {host}")
        if not set(self.consultas) <= set(self.hosts) or any(
            type(c) is not tuple or not set(c) <= set(self.rotas[h]) for h, c in self.consultas.items()
        ):
            raise ValueError(f"consultas inconsistentes em {self.id}")
        for host in self.hosts:
            if f"{host}=" not in self.origem_hosts:
                raise ValueError(f"host sem origem registrada: {host}")


def prefixos_por_host(fonte: FonteSonda) -> dict[str, tuple[str, ...]]:
    """Mapa host -> caminhos no formato (prefixo) do transporte; é só a segunda barreira: a igualdade exata do caminho
    é validada antes, em `captura._plano_get`. Host sem rota documentada admite só o robots.txt."""
    return {h: (fonte.rotas[h] or ("/robots.txt",)) for h in sorted(fonte.hosts)}


def _f(id_: str, descricao: str, rotas: dict[str, tuple[str, ...]], origem: str, *, mimes=_MIMES,
       b: set[str] = frozenset(), nota: str = "",
       consultas: dict[str, tuple[str, ...]] | None = None) -> tuple[str, FonteSonda]:
    return id_, FonteSonda(
        id_, descricao, frozenset(rotas), MappingProxyType(dict(rotas)), mimes, origem,
        "B" if b else "A", frozenset(b), nota, MappingProxyType(dict(consultas or {})),
    )


_ESAJ = "e-SAJ, consulta de jurisprudência de 2º grau (cjsg)"
_B = "confirmação nível B: página do próprio sistema, indexada por busca, não lida; sonda bloqueada até confirmação "
_B += "documental (página oficial lida ou confirmação do titular); "
_S0B = "endpoint de resultado não documentado em página oficial: fora da S0, pendência S0b; "

FONTES_SONDA: Mapping[str, FonteSonda] = MappingProxyType(dict([
    _f("tst", "TST: pesquisa de jurisprudência (portal, backend REST e consulta de documento)",
       {"jurisprudencia.tst.jus.br": ("/config.json",),
        "jurisprudencia-backend.tst.jus.br": ("/rest/orgaos-judicantes", "/rest/indicadores"),
        "consultadocumento.tst.jus.br": ()},
       "jurisprudencia.tst.jus.br=https://jurisprudencia.tst.jus.br/ (portal oficial); "
       "jurisprudencia-backend.tst.jus.br=https://jurisprudencia.tst.jus.br/config.json (campo base_url do portal); "
       "consultadocumento.tst.jus.br=https://jurisprudencia.tst.jus.br/config.json (campos consulta_acordao_url e "
       "consulta_despacho_url)",
       mimes=_MIMES_PDF,
       nota="nível A: o próprio portal publica seus endpoints (config.json e JavaScript do portal); www.tst.jus.br "
            "respondeu 202 sem corpo (desafio) à leitura de pesquisa da ferramenta do agente e não foi usado. A "
            "pesquisa textual é POST JSON: o instrumento só faz GET, pendência S0b. A raiz do portal fica fora "
            "(o transporte não admite `/` como prefixo). consultadocumento: o diretório /consultaDocumento/ é "
            "prefixo (família), que o catálogo não admite; sem rota de caminho exato documentada, só robots.txt."),
    _f("stf_acordaos", "STF: pesquisa de jurisprudência (acórdãos)",
       {"jurisprudencia.stf.jus.br": ("/pages/search",)},
       "jurisprudencia.stf.jus.br=https://portal.stf.jus.br/jurisprudencia/ (links para /pages/search)",
       nota=_S0B + "o conector stf declara WAF na busca textual"),
    _f("bnp", "CNJ: Banco Nacional de Precedentes (Pangea/BNP)",
       {"pangeabnp.pdpj.jus.br": (), "bnp.pdpj.jus.br": ()},
       "pangeabnp.pdpj.jus.br=https://docs.pdpj.jus.br/servicos-negociais/BNP-Pangea/BNP%20-%20Manual%20de%20Utiliza%C3%A7%C3%A3o; "
       "bnp.pdpj.jus.br=https://www.cnj.jus.br/tecnologia-da-informacao-e-comunicacao/justica-4-0/banco-nacional-de-precedentes-bnp/",
       mimes=_MIMES,
       nota="aplicação de página única; nenhuma rota consta de página oficial lida (a raiz não é admitida): só o "
            "robots.txt. " + _S0B.strip()),
    _f("djen", "CNJ: Diário de Justiça Eletrônico Nacional (consulta pública)",
       {"comunica.pje.jus.br": ("/consulta",), "comunicaapi.pje.jus.br": ()},
       "comunica.pje.jus.br=https://www.cnj.jus.br/programas-e-acoes/processo-judicial-eletronico-pje/comunicacoes-processuais/; "
       "comunicaapi.pje.jus.br=https://www.cnj.jus.br/programas-e-acoes/processo-judicial-eletronico-pje/comunicacoes-processuais/orientacoes-aos-tribunais/",
       nota="sujeita à decisão 0069 (restrição geográfica geral): sondável só do ambiente normal do produto no Brasil (notebook do titular), pelo transporte comum, UA identificado, uma só requisição, sem nova tentativa; recusa a partir do Brasil vira barreira (0069, item 4); o 403 de 27/10/2026 foi de ferramenta de pesquisa em nuvem fora do Brasil, sem valor de evidência (0069, item 5). A página oficial documenta /api/v1 como API de envio dos tribunais, com autenticação: não é sondada. "
            "A consulta pública pela API não está documentada: " + _S0B.strip()),
    _f("cjf_unificada", "CJF: pesquisa unificada de jurisprudência da Justiça Federal",
       {"jurisprudencia.cjf.jus.br": (), "www.cjf.jus.br": ("/jurisprudencia/unificada/",)},
       "jurisprudencia.cjf.jus.br=https://www.trf1.jus.br/trf1/busca/ (menu Pesquisa > Jurisprudência: "
       "https://jurisprudencia.cjf.jus.br/?tribunal=trf1); "
       "www.cjf.jus.br=https://www.cjf.jus.br/jurisprudencia/unificada/",
       b={"www.cjf.jus.br"},
       nota=_B + "www.cjf.jus.br; jurisprudencia.cjf.jus.br é nível A (link lido no portal do TRF1), mas a "
            "única rota documentada é a raiz, fora do escopo: só robots.txt. " + _S0B.strip()),
    _f("trf1", "TRF1: pesquisa de jurisprudência (via CJF) e inteiro teor de acórdãos",
       {"jurisprudencia.cjf.jus.br": (), "arquivo.trf1.jus.br": ()},
       "jurisprudencia.cjf.jus.br=https://www.trf1.jus.br/trf1/busca/ (menu Pesquisa > Jurisprudência); "
       "arquivo.trf1.jus.br=https://www.trf1.jus.br/trf1/busca/ (menu Inteiro Teor)",
       mimes=_MIMES_PDF,
       nota="nível A; o menu oficial do TRF1 aponta a pesquisa ao CJF (?tribunal=trf1), sem host próprio; as rotas "
            "documentadas são raízes, fora do escopo: só robots.txt. " + _S0B.strip()),
    _f("trf2", "TRF2: portal de jurisprudência da 2ª Região",
       {"jurisprudencia.trf2.jus.br": (), "www10.trf2.jus.br": ("/consultas/servicos/jurisprudencia/",)},
       "jurisprudencia.trf2.jus.br=https://www.trf2.jus.br/trf2/artigo/coport/consulta-de-jurisprudencia; "
       "www10.trf2.jus.br=https://www.trf2.jus.br/trf2/noticia/2024/trf2-portal-de-jurisprudencia-conta-com-novo-mecanismo-de-busca",
       nota="nível A; a raiz do portal fica fora (só robots.txt); juris.trf2.jus.br aparece só em resultado de "
            "busca e ficou fora. " + _S0B.strip()),
    _f("trf3", "TRF3: busca de jurisprudência e acórdãos",
       {"web.trf3.jus.br": ("/jurisprudencia", "/acordaos/Acordao")},
       "web.trf3.jus.br=https://www.trf3.jus.br/carta-servicos/acordaos (links /jurisprudencia e /acordaos/Acordao)",
       mimes=_MIMES_PDF, nota="nível A; " + _S0B.strip()),
    _f("tjac", _ESAJ + " do TJAC",
       {"esaj.tjac.jus.br": ("/cjsg/consultaCompleta.do", "/cjsg/resultadoCompleta.do")},
       "esaj.tjac.jus.br=https://www.tjac.jus.br/ (links /cjsg/consultaCompleta.do e /cjsg/resultadoCompleta.do)",
       mimes=_MIMES_PDF,
       consultas={"esaj.tjac.jus.br": ("/cjsg/resultadoCompleta.do",)},
       nota="nível A: caminhos lidos em página oficial; os parâmetros do resultado são inferência do e-SAJ"),
    _f("tjal", _ESAJ + " do TJAL", {"www2.tjal.jus.br": ("/cjsg/consultaCompleta.do",)},
       "www2.tjal.jus.br=https://www2.tjal.jus.br/cjsg/consultaCompleta.do (página do próprio tribunal)",
       mimes=_MIMES_PDF, b={"www2.tjal.jus.br"}, nota=_B + "www2.tjal.jus.br; " + _S0B.strip()),
    _f("tjam", _ESAJ + " do TJAM", {"consultasaj.tjam.jus.br": ("/cjsg/consultaCompleta.do",)},
       "consultasaj.tjam.jus.br=https://consultasaj.tjam.jus.br/cjsg/consultaCompleta.do (página do próprio tribunal)",
       mimes=_MIMES_PDF, b={"consultasaj.tjam.jus.br"}, nota=_B + "consultasaj.tjam.jus.br; " + _S0B.strip()),
    _f("tjms", _ESAJ + " do TJMS", {"esaj.tjms.jus.br": ("/cjsg/consultaCompleta.do",)},
       "esaj.tjms.jus.br=https://esaj.tjms.jus.br/cjsg/consultaCompleta.do (página do próprio tribunal)",
       mimes=_MIMES_PDF, b={"esaj.tjms.jus.br"}, nota=_B + "esaj.tjms.jus.br; " + _S0B.strip()),
    _f("tjrj", "TJRJ: eJuris, consulta de jurisprudência",
       {"www3.tjrj.jus.br": ("/ejuris/ConsultarJurisprudencia.aspx",)},
       "www3.tjrj.jus.br=https://www3.tjrj.jus.br/ejuris/ConsultarJurisprudencia.aspx (página do próprio sistema)",
       b={"www3.tjrj.jus.br"},
       nota=_B + "www3.tjrj.jus.br; a leitura das páginas do portal www.tjrj.jus.br foi recusada pelo robots.txt do "
            "site à ferramenta de pesquisa do agente e não foi contornada; www4.tjrj.jus.br ficou fora"),
    _f("tjmg", "TJMG: consulta de jurisprudência",
       {"www5.tjmg.jus.br": ("/jurisprudencia/formEspelhoAcordao.do", "/jurisprudencia/ajuda.do")},
       "www5.tjmg.jus.br=https://www.tjmg.jus.br/portal-tjmg/jurisprudencia/consulta-de-jurisprudencia/ "
       "(links /jurisprudencia/decisao.do, formEspelhoAcordao.do)",
       nota="nível A; os links oficiais usam http, a sonda exige https; " + _S0B.strip()),
    _f("tjrs", "TJRS: pesquisa de jurisprudência", {"www.tjrs.jus.br": ("/novo/buscas-solr/",)},
       "www.tjrs.jus.br=https://www.tjrs.jus.br/novo/buscas-solr/ (página do próprio tribunal)",
       b={"www.tjrs.jus.br"},
       nota=_B + "www.tjrs.jus.br; o Disallow do robots.txt do site à ferramenta de pesquisa do agente é política de "
            "robots para aquele User-Agent, não recusa ao produto (decisão do supervisor, rodada 3 do PR #14); a "
            "primeira sonda do host é o robots.txt, lido com o UA do produto; www3.tjrs.jus.br/site_php/consulta ficou fora (legado, não confirmado); "
            + _S0B.strip()),
    _f("tjpr", "TJPR: consulta de jurisprudência", {"portal.tjpr.jus.br": ("/jurisprudencia/",)},
       "portal.tjpr.jus.br=https://www.tjpr.jus.br/jurisprudencia (link https://portal.tjpr.jus.br/jurisprudencia/)",
       nota="nível A; " + _S0B.strip()),
]))

# fonte-sonda barrada: id -> motivo. Fora do catálogo; o instrumento a recusa antes da rede.
FONTES_BARRADAS: Mapping[str, str] = MappingProxyType({})

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
