"""Câmara/Legin: descoberta publicada, política estrita e versões sem reconstrução."""
from __future__ import annotations

from datetime import datetime
import functools
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlencode

from lxml import html

from freoa_verifica.connectors.base import (AmbiguousCandidates, Candidate, CandidateList, Connector, HealthProbe,
                                           HealthReport, Unavailable, register, sob_guarda)
from freoa_verifica.connectors.camara_ativacao import ativacao
from freoa_verifica.connectors.camara_estado import Estado, EstadoIndisponivel, Relogio
from freoa_verifica.connectors.camara_policy import HOSTS, validar_url, url_publicada
from freoa_verifica.connectors.camara_portao import Portao
from freoa_verifica.connectors.camara_robots import politica_robots  # noqa: F401  (assinatura da IL.2-c)
from freoa_verifica.connectors.httputil import _revalidar, connector_fetch
from freoa_verifica.identidade_http import UA_POR_CONECTOR
from freoa_verifica.texto_resposta import corpo_binario, texto_do_response
from freoa_verifica.transport import Response

PORTAL = "https://www.camara.leg.br/legislacao"
TIPOS = {"lei": "Lei Ordinária", "lei_complementar": "Lei Complementar"}


def _erro(reason, resp=None):
    return Unavailable(reason, "resposta_inesperada", {} if resp is None else {
        "url": resp.final_url, "status": resp.status, "sha256": resp.sha256})


def _endereco_da_norma(url, wk) -> bool:
    """O endereço da página de norma é o da obra pedida (família, número e ano)."""
    try:
        info = validar_url(url)
    except ValueError:
        return False
    familia = {"lei": "lei", "leicom": "lei_complementar"}.get(info.get("familia"))
    return familia == wk.kind and str(info.get("numero")) == str(wk.number) and str(info.get("ano")) == str(wk.year)


def arvore(resp):
    if len(resp.body) > 30 * 1024**2:
        raise _erro("corpo_excedido", resp)
    try:
        return html.fromstring(texto_do_response(resp))
    except (ValueError, TypeError) as exc:
        raise _erro("html_nao_reconhecido", resp) from exc


def compacto(el):
    return " ".join("".join(el.itertext()).split())


def inventario(resp: Response) -> dict:
    info = validar_url(resp.final_url)
    if info["recurso"] != "norma":
        raise _erro("pagina_nao_e_norma", resp)
    tree = arvore(resp)
    content = tree.xpath('//*[@id="content"]')
    if len(content) != 1 or "Legislação Informatizada - Dados da Norma" not in compacto(content[0]):
        raise _erro("pagina_norma_nao_reconhecida", resp)
    root = content[0]
    titles = [compacto(e) for e in root.xpath('.//h1|.//h2')]
    title = next((t for t in titles if re.match(r"(?:LEI|MEDIDA|DECRETO)", t)), "")
    if not title:
        raise _erro("identidade_nao_declarada", resp)
    resources = []
    for a in root.xpath('.//a[@href]'):
        label, href = compacto(a), a.get("href")
        url = url_publicada(resp.final_url, href)
        if not label or "/legin/" not in url:
            continue
        try:
            dest = validar_url(url)
            admitted, reason = True, None
        except ValueError:
            dest, admitted, reason = {}, False, "formato_ou_rota_nao_demonstrados"
        role = dest.get("recurso", "fora_admissao")
        if role in {"atualizado", "original", "anexo"} and any(dest.get(k) != info[k] for k in ("id", "familia", "numero", "ano")):
            admitted, reason = False, "versao_de_outra_norma"
        # Rótulo e posição são dados, não autorização para execução.
        expected = {"atualizado": "Texto Atualizado", "original": "Publicação Original", "anexo": "Anexo"}
        if role in expected and expected[role] not in label:
            admitted, reason = False, "rotulo_incompativel"
        relation = re.search(r" - \(([^)]+)\)\.\s*(.*)", label)
        publication = None
        if role == "original":
            parent = a.getparent()
            for _ in range(4):
                if parent is None:
                    break
                pubtext = compacto(parent)
                pubmatch = re.search(r"(Diário Oficial[^\n]*?)\s*-\s*(\d{1,2})/(\d{1,2})/(\d{4}), Página\s+(\d+)\s*\(Publicação Original\)", pubtext)
                if pubmatch:
                    from datetime import date
                    publication = {"data": date(int(pubmatch[4]), int(pubmatch[3]), int(pubmatch[2])).isoformat(),
                                   "veiculo": pubmatch[1], "pagina": pubmatch[5], "raw": pubmatch[0]}
                    break
                parent = parent.getparent()
        resources.append({"rotulo": label, "href": href, "url": url, "recurso": role,
                          "admitido": admitted, "obtido": False, "motivo": reason or "nao_obtido",
                          "ordem_na_fonte": len(resources),
                          "acao": relation[1] if relation else None,
                          "publicacao": publication,
                          "dispositivo_atingido": relation[2] if relation else None,
                          "origem": {"url": resp.final_url, "sha256": resp.sha256}})
    return {"titulo": title, "recursos": resources, "cadeia_completa": False,
            "pagina": {"url": resp.final_url, "sha256": resp.sha256, "fetched_at": resp.fetched_at}}


def _classifica(funcao):
    """Falhas de perfil/resposta dos métodos públicos alimentam o estado de barreiras do portão (0080 §6)."""
    @functools.wraps(funcao)
    def interno(self, *args, **kwargs):
        try:
            return funcao(self, *args, **kwargs)
        except Unavailable as exc:
            self._relancar(exc)
    return interno


def _exigir_instante(resp):
    """Passe final (N3 residual): captura sem instante real não é persistida.

    O materializador genérico preencheria o vazio com o relógio e gravaria outro
    recibo; recusa-se antes da primeira escrita, sem renovar nem inferir o instante.
    """
    instante = resp.fetched_at
    try:
        valido = isinstance(instante, str) and bool(instante) and datetime.fromisoformat(instante) is not None
    except ValueError:
        valido = False
    if not valido:
        raise _erro("instante_captura_invalido", resp)


@register
class CamaraLeginConnector(Connector):
    id = "camara_legin"
    authority = "Câmara dos Deputados / Legislação Informatizada"
    hosts = HOSTS
    path_prefixes = {"www.camara.leg.br": ("/legislacao", "/robots.txt"),
                     "www2.camara.leg.br": ("/legin/fed/", "/robots.txt")}
    mimes = frozenset({"text/html", "application/pdf", "text/plain"})
    user_agent = UA_POR_CONECTOR["camara_legin"]
    coverage = {"colecoes": ["leis", "leis complementares"], "busca_textual": False,
                "inteiro_teor": True, "ementa": True, "periodo": "perfis demonstrados; sem exaustividade",
                "atualizacao": "sob demanda; licença e política pendentes", "qualificacao": "nao_apurada"}

    def __init__(self, *, transporte_offline=None, home=None, relogio: Relogio | None = None,
                 portao: Portao | None = None):
        # Ao vivo só com ativação registrada (0080 §2). A injeção serve ao replay e aos testes com transporte
        # simulado; `portao` é o do instrumento (sessão própria, teto de 200).
        self._transporte_offline = transporte_offline
        self._portao_injetado = portao
        self._portao: Portao | None = portao
        self._relogio = relogio
        self.home = None if home is None else Path(home)
        self.paginas = {}
        self.links = {}
        self.inventarios = {}
        self.politicas = []
        self.falhas_descoberta = []
        self.relacoes_observadas = []
        self._ancoras = {}

    def zerar_descoberta(self):
        """Uma unidade de resolução não herda descobertas ou recusas da anterior."""
        self.paginas.clear()
        self.links.clear()
        self.inventarios.clear()
        self.politicas.clear()
        self.falhas_descoberta.clear()
        self.relacoes_observadas.clear()
        self._ancoras.clear()
        for name in ("_texto_url", "_cadeia_declarada", "_pagina_declarada"):
            self.__dict__.pop(name, None)

    def _portao_da_rota(self) -> Portao:
        if self._portao is not None:
            return self._portao
        if self._transporte_offline is not None:
            estado = Estado(self.home)  # replay/testes: a ativação não é exigida, mas o termo vigente é registrado
            self._portao = Portao(self._transporte_offline, estado=estado, relogio=self._relogio,
                                  ativacao=lambda: ativacao(estado), exigir_ativacao=False)
            return self._portao
        from freoa_verifica.store.db import data_home
        estado = Estado(self.home or data_home())
        # A ativação é revalidada pelo portão antes de CADA obtenção viva, não só ao criá-lo.
        portao = Portao(connector_fetch, estado=estado, relogio=self._relogio, ativacao=lambda: ativacao(estado))
        portao.checar_terminal()  # falha local anterior nesta chamada: nada mais é lido nem emitido
        try:
            registro = ativacao(estado)
        except EstadoIndisponivel as exc:  # falha local ao LER a documentação: terminal, nunca pendência (0080 §6)
            raise portao.falha_local_de_estado(exc) from exc
        if registro is None:
            raise Unavailable("ativacao_ao_vivo_pendente")
        self._portao = portao
        return self._portao

    def _perfil(self, exc: Unavailable) -> Unavailable:
        """Falha de perfil ou de resposta detectada DEPOIS do portão: alimenta o mesmo classificador e o mesmo estado
        de barreiras (recurso persistente; host pelo escopo). Entrada inválida do chamador e formatos não habilitados
        não têm categoria de resposta e passam intactos; falha local do parser encerra o escopo sem culpar a fonte."""
        portao = self._portao
        if portao is None or "bloqueio" in exc.evidencia:
            return exc
        if exc.categoria == "resposta_inesperada" and isinstance(exc.evidencia.get("url"), str):
            return portao.falha_de_resposta(exc, exc.evidencia["url"])
        if exc.reason == "falha_parser_camara":
            return portao.falha_local_de_interpretacao(exc)
        return exc

    def _relancar(self, exc: Unavailable):
        novo = self._perfil(exc)
        if novo is exc:
            raise exc
        raise novo from exc

    def _inventario(self, page):
        try:
            return inventario(page)
        except Unavailable as exc:
            self._relancar(exc)

    def atribuicao(self, autoria: str | None = None, *, sha256: str | None = None, url: str | None = None,
                   fetched_at: str | None = None) -> dict:
        from freoa_verifica.connectors.camara_atribuicao import atribuicao
        return atribuicao(self.home, autoria, sha256=sha256, url=url, fetched_at=fetched_at)

    def _validar_response(self, resp, url, *, validadas=None):
        try:
            route = validar_url(url)
            validar_url(resp.final_url)
        except ValueError as exc:
            raise _erro("url_resposta_nao_admitida", resp) from exc
        if resp.url != url or resp.final_url != url or resp.redirects or resp.status != 200 or len(resp.body) > 30 * 1024**2:
            raise _erro("resposta_camara_invalida", resp)
        if hashlib.sha256(resp.body).hexdigest() != resp.sha256:
            raise _erro("hash_captura_divergente", resp)
        # Cache só deste preflight síncrono. Hash e identidade são reconferidos
        # mesmo na repetição; nenhuma aprovação atravessa chamadas/fronteiras.
        signature = (url, resp.sha256, resp.mime, resp.content_type, resp.size,
                     repr(resp.interpretacao_legada), tuple(sorted(resp.headers.items())))
        if validadas is not None and signature in validadas:
            return
        _revalidar(resp, url, hosts=self.hosts, path_prefixes=self.path_prefixes,
                   mimes=frozenset({route["mime"]}), max_redirects=0, max_bytes=30 * 1024**2)
        if validadas is not None:
            validadas.add(signature)

    def _admitir(self, url, *, validadas=None):
        try:
            return self._admitir_url(url, validadas=validadas)
        except ValueError as exc:
            raise Unavailable(str(exc)) from exc

    def _admitir_url(self, url, *, validadas=None):
        route = validar_url(url)
        if route["recurso"] not in {"robots", "portal", "busca"}:
            origin = self.links.get(url)
            if origin is None:
                raise ValueError("vinculo_descoberta_ausente")
            source, href, label = origin
            self._validar_response(source, source.final_url, validadas=validadas)
            if not label or url_publicada(source.final_url, href) != url:
                raise ValueError("vinculo_descoberta_invalido")
            if (href, label) not in self._ancoras_publicadas(source):
                raise ValueError("link_nao_publicado")
        return route

    def _ancoras_publicadas(self, page):
        # Chamado só depois da conferência do hash; não armazena árvore normativa.
        if page.sha256 not in self._ancoras:
            self._ancoras[page.sha256] = frozenset((a.get("href"), compacto(a))
                                                  for a in arvore(page).xpath('//a[@href]'))
        return self._ancoras[page.sha256]

    def validar_descoberta(self, url, *, validadas=None):
        """Confere a cadeia inteira sem interpretar texto normativo ou obter bytes.

        Cada antecessor deve ser a captura do acumulador, não apenas um objeto
        de resposta íntegro fornecido pela aresta. A raiz também é capturada.
        """
        if self.falhas_descoberta:
            raise self.falhas_descoberta[0]
        cursor, visited, chain = url, set(), []
        while True:
            if cursor in visited:
                raise _erro("ciclo_descoberta", self.paginas.get(url))
            visited.add(cursor)
            page = self.paginas.get(cursor)
            if page is None:
                raise _erro("descoberta_sem_raiz", self.paginas.get(url))
            self._validar_response(page, cursor, validadas=validadas)
            route = self._admitir(cursor, validadas=validadas)
            if route["recurso"] in {"busca", "portal", "robots"} and cursor in self.links:
                raise _erro("raiz_descoberta_invalida", page)
            if cursor not in self.links:
                if route["recurso"] not in {"busca", "portal"} and not (route["recurso"] == "robots" and not chain):
                    raise _erro("descoberta_sem_raiz", page)
                return chain
            source, href, label = self.links[cursor]
            captured = self.paginas.get(source.final_url)
            if captured is None:
                raise _erro("descoberta_sem_raiz", page)
            self._validar_response(source, source.final_url, validadas=validadas)
            if captured.sha256 != source.sha256:
                raise _erro("hash_ancestral_divergente", page)
            chain.append({"url": cursor, "origem_url": source.final_url,
                          "origem_sha256": source.sha256, "href": href, "rotulo": label})
            cursor = source.final_url

    def validar_conjunto(self):
        """Preflight único da unidade inteira, antes da primeira escrita material.

        Robots é evidência administrativa isolada, nunca ancestral normativo.
        Página órfã no acumulador é erro; nenhuma página é descartada aqui.
        """
        if self.falhas_descoberta:
            raise self.falhas_descoberta[0]
        validadas = set()
        for url, resp in self.paginas.items():
            self._validar_response(resp, url, validadas=validadas)
            _exigir_instante(resp)
            self.validar_descoberta(url, validadas=validadas)
        if hasattr(self, "_cadeia_declarada"):
            if self.validar_descoberta(self._texto_url, validadas=validadas) != self._cadeia_declarada:
                raise _erro("cadeia_descoberta_invalida", self.paginas[self._texto_url])
            source = self.links[self._texto_url][0]
            if (source.url, source.sha256) != (self._pagina_declarada["url"], self._pagina_declarada["sha256"]):
                raise _erro("hash_ancestral_divergente", self.paginas[self._texto_url])

    def registrar_conjunto(self, document):
        """Guarda a unidade validada no modelo para releitura sem nova descoberta."""
        from freoa_verifica.parsers.model import EditorialBlock
        for i, block in enumerate(document.editorial_blocks):
            if block.kind != "camara_inventario":
                continue
            inv = json.loads(block.text)
            inv["conjunto_descoberta"] = {
                "paginas": [{"url": url, "sha256": p.sha256} for url, p in self.paginas.items()],
                "arestas": [{"url": url, "origem_url": p.url, "origem_sha256": p.sha256,
                             "href": href, "rotulo": label} for url, (p, href, label) in self.links.items()]}
            document.editorial_blocks[i] = EditorialBlock(json.dumps(inv, ensure_ascii=False, sort_keys=True),
                                                          block.span, block.kind)

    def _registrar_descoberta(self, page, url, href, label, *, validadas=None):
        """Preserva o primeiro caminho; vínculos posteriores são relações observadas."""
        try:
            self._validar_response(page, page.final_url, validadas=validadas)
            captured = self.paginas.get(page.final_url)
            if captured is None:
                raise _erro("descoberta_sem_raiz", page)
            self._validar_response(captured, page.final_url, validadas=validadas)
            if captured.sha256 != page.sha256:
                raise _erro("hash_ancestral_divergente", page)
            if (not label or url_publicada(page.final_url, href) != url or
                    (href, label) not in self._ancoras_publicadas(page)):
                raise _erro("link_nao_publicado", page)
            classe = None
            if url == page.final_url:
                # Uma autorreferência isolada nunca cria uma raiz.
                classe = "autorreferencia"
            elif url in self.links or (url in self.paginas and
                    validar_url(url)["recurso"] in {"busca", "portal"}):
                previous = self.links.get(url)
                if previous is not None and previous[0].final_url == page.final_url:
                    classe = "duplicacao"
                else:
                    cursor, seen = page.final_url, set()
                    while cursor in self.links and cursor not in seen and cursor != url:
                        seen.add(cursor)
                        cursor = self.links[cursor][0].final_url
                    classe = "retorno" if cursor == url else "concorrente"
            if classe is not None:
                self.relacoes_observadas.append({"origem_url": page.final_url,
                    "origem_sha256": page.sha256, "href": href, "rotulo": label,
                    "destino": url, "classe": classe})
                return
            self.links[url] = (page, href, label)
        except Unavailable as exc:
            self.falhas_descoberta.append(exc)
            raise

    @sob_guarda
    def _obter_recurso(self, url):
        try:
            self._admitir(url)  # gramática e vínculo de descoberta, antes inclusive do robots e do cache
        except ValueError as exc:
            raise Unavailable(str(exc)) from exc
        portao = self._portao_da_rota()
        resp = portao.obter(url)
        politica = portao.politica_de.get(url)
        if politica is not None:
            self.politicas.append({"url": url, "politica_sha256": politica})
        try:
            self._validar_response(resp, url)
        except Unavailable as exc:
            self._relancar(exc)
        self.paginas[url] = resp
        return resp

    @_classifica
    def search(self, q: str, **filtros):
        from freoa_verifica.citation import parse_one
        cite = parse_one(q)
        key = cite.work if cite else None
        if not key or key.authority != "federal" or key.kind not in TIPOS or not key.year:
            raise Unavailable("busca_camara_exige_identidade")
        url = PORTAL + "/busca?" + urlencode({"abrangencia": "Legislação Federal", "tipo": TIPOS[key.kind],
                                             "numero": key.number, "ano": key.year, "geral": ""})
        resp = self._obter_recurso(url)
        tree = arvore(resp)
        if "Exibindo resultados de" not in compacto(tree):
            raise _erro("busca_sem_estrutura_reconhecida", resp)
        candidates = []
        seen = set()
        for a in tree.xpath('//a[@href]'):
            target = url_publicada(resp.final_url, a.get("href"))
            try:
                info = validar_url(target)
            except ValueError:
                continue
            if info["recurso"] != "norma" or not compacto(a):
                continue
            self._registrar_descoberta(resp, target, a.get("href"), compacto(a))
            if target in seen:
                continue
            seen.add(target)
            candidates.append(Candidate(self.id, f"{info['familia']}:{info['numero']}:{info['ano']}",
                                        compacto(a), target, metadata={"pagina_busca": resp.sha256}))
        if not candidates:
            raise _erro("busca_sem_marcador_zero_validado", resp)
        return CandidateList(candidates, total=None)

    @_classifica
    def resolve(self, key):
        from freoa_verifica.aliases import WorkKey
        from freoa_verifica.identity import validate_identity
        from freoa_verifica.parsers.model import ParsedDocument
        kind = key.get("kind") or {"LEI": "lei", "LCP": "lei_complementar"}.get(key.get("tipo"))
        number, year = key.get("number", key.get("numero")), key.get("year", key.get("ano"))
        if kind not in TIPOS or not number or not year:
            raise Unavailable("especie_busca_nao_demonstrada")
        wk = WorkKey("federal", kind, str(number), int(year))
        self.zerar_descoberta()
        name = "Lei Complementar" if kind == "lei_complementar" else "Lei"
        found = self.search(f"{name} {number}/{year}")
        matches = []
        divergente = None  # página que o endereço diz ser a norma pedida e cujo conteúdo diz outra coisa
        for cand in found:
            page = self._obter_recurso(cand.url)
            inv = self._inventario(page)
            doc = ParsedDocument("camara_norma", "1", inv["titulo"], None, "")
            try:
                confirmada = validate_identity(wk, doc) is not None
            except ValueError:
                confirmada = False
            if not confirmada:
                if _endereco_da_norma(cand.url, wk):
                    divergente = page
                continue
            self.inventarios[cand.url] = inv
            self._descobrir(page, inv)
            matches.append(Candidate(self.id, cand.key, inv["titulo"], cand.url,
                                     metadata={"inventario": inv, "versao": "vigente"}))
        if len(matches) > 1:
            raise AmbiguousCandidates(matches)
        if not matches:
            if divergente is not None:  # perfil incompatível: evidência da resposta, mesmo classificador das barreiras
                raise _erro("identidade_nao_confirmada", divergente)
            raise Unavailable("identidade_nao_confirmada")  # nenhuma página da norma pedida: ausência demonstrada
        return matches[0]

    def _descobrir(self, page, inv):
        # Apenas este lote síncrono. Cada aresta reconfere hash e metadados,
        # sem repetir o exame puro de perfil para os mesmos bytes da origem.
        validadas = set()
        for r in inv["recursos"]:
            if r["admitido"]:
                self._registrar_descoberta(page, r["url"], r["href"], r["rotulo"], validadas=validadas)

    @_classifica
    def fetch(self, candidate):
        version = candidate.metadata.get("versao", "vigente")
        if version not in {"vigente", "publicacao_original"}:
            raise ValueError("versao_invalida")
        self._admitir(candidate.url)
        inv = self.inventarios.get(candidate.url)
        if inv is None:
            page = self._obter_recurso(candidate.url)
            inv = self._inventario(page)
            from freoa_verifica.aliases import WorkKey
            from freoa_verifica.identity import validate_identity
            from freoa_verifica.parsers.model import ParsedDocument
            info = validar_url(candidate.url)
            kind = {"lei": "lei", "leicom": "lei_complementar"}[info["familia"]]
            key = WorkKey("federal", kind, info["numero"], int(info["ano"]))
            try:
                confirmada = validate_identity(key, ParsedDocument("camara_norma", "1", inv["titulo"], None, "")) is not None
            except ValueError:
                confirmada = False
            if not confirmada:  # o endereço é o da norma e a página declara outra: perfil incompatível, com evidência
                raise _erro("identidade_nao_confirmada", page)
            self.inventarios[candidate.url] = inv
            self._descobrir(page, inv)
        role = "atualizado" if version == "vigente" else "original"
        choices = [r for r in inv["recursos"] if r["recurso"] == role and r["admitido"]]
        if len(choices) != 1:
            raise Unavailable("versao_ausente_ou_ambigua")
        return self._obter_recurso(choices[0]["url"])

    @_classifica
    def parse(self, resp):
        from freoa_verifica.connectors.base import LocalParserFailure, sanitizar_falha_parser
        from freoa_verifica.parsers.isolated import parse_ou_indisponivel
        self._admitir(resp.final_url)
        self._validar_response(resp, resp.final_url)
        descoberta = self.validar_descoberta(resp.final_url)
        if self.paginas[resp.final_url].sha256 != resp.sha256:
            raise _erro("hash_captura_divergente", resp)
        route = validar_url(resp.final_url)
        if route["recurso"] == "anexo":
            try:
                return parse_ou_indisponivel("camara_anexo", corpo_binario(resp), 60)
            except LocalParserFailure as exc:
                raise Unavailable("falha_parser_camara", None, sanitizar_falha_parser(
                    exc, perfil="camara_anexo" if route["recurso"] == "anexo" else "camara_legin",
                    url=resp.url, sha256=resp.sha256).evidencia) from exc
            except Unavailable as exc:
                raise _erro("pdf_nao_processado", resp) from exc
        if route["recurso"] not in {"atualizado", "original"}:
            raise _erro("recurso_nao_e_texto_normativo", resp)
        try:
            doc = parse_ou_indisponivel("camara_legin", texto_do_response(resp), 120, base_url=resp.final_url)
        except Unavailable as exc:
            if isinstance(exc, LocalParserFailure):
                raise Unavailable("falha_parser_camara", None, sanitizar_falha_parser(
                    exc, perfil="camara_anexo" if route["recurso"] == "anexo" else "camara_legin",
                    url=resp.url, sha256=resp.sha256).evidencia) from exc
            if any(error in exc.reason for error in ("AttributeError", "NameError", "TypeError")):
                raise Unavailable("falha_parser_camara", "regressao", {"url": resp.url, "sha256": resp.sha256}) from exc
            raise _erro("html_nao_processado", resp) from exc
        if not doc.provisions:
            raise _erro("texto_normativo_nao_reconhecido", resp)
        # A epígrafe pode faltar no atualizado. Identidade só pelo vínculo exato à página capturada.
        from freoa_verifica.parsers.model import EditorialBlock
        source = self.links[resp.final_url][0]
        inv = self.inventarios.get(source.final_url) or self._inventario(source)
        from freoa_verifica.identity import declared_identity
        page_doc = type(doc)("camara_norma", "1", inv["titulo"], None, "")
        text_key, _ = declared_identity(doc)
        page_key, _ = declared_identity(page_doc)
        if page_key is None or (text_key is not None and text_key != page_key):
            raise _erro("identidade_texto_divergente", resp)
        family = {"lei": "lei", "lei_complementar": "leicom"}.get(page_key.kind)
        if (route["familia"], route["numero"], route["ano"]) != (family, page_key.number, page_key.year):
            raise _erro("identidade_slug_divergente", resp)
        doc.title = inv["titulo"]
        inv = {**inv, "descoberta": descoberta}
        doc.editorial_blocks.append(EditorialBlock(json.dumps(inv, ensure_ascii=False, sort_keys=True), (0, 0),
                                                   "camara_inventario"))
        return doc

    @sob_guarda
    @_classifica
    def fetch_anexo(self, candidate):
        self._admitir(candidate.url)
        inv = self.inventarios.get(candidate.url)
        if inv is None:
            raise Unavailable("pagina_norma_nao_capturada")
        choices = [r for r in inv["recursos"] if r["recurso"] == "anexo" and r["admitido"]]
        if len(choices) != 1:
            raise Unavailable("anexo_nao_identificado")
        return self._obter_recurso(choices[0]["url"])

    @sob_guarda
    def capturar_relacoes(self, candidate, *, limite=8):
        """Obtenção limitada: página relacionada → original publicada; nunca segue sua lista de relações.

        Deduplica obtenções, não ações. A lista visível nunca é certificado de completude.
        Campos privados do retorno destinam-se à persistência pelo serviço.
        """
        if type(limite) is not int or not 0 <= limite <= 32:
            raise ValueError("limite_relacoes_invalido")
        self._admitir(candidate.url)
        inv = self.inventarios.get(candidate.url)
        if inv is None:
            raise Unavailable("pagina_norma_nao_capturada")
        cached, remaining = {}, limite
        materials, pending, failures = [], [], []
        for relation in inv["recursos"]:
            if not relation["acao"]:
                continue
            url = relation["url"]
            if url not in cached:
                if url == candidate.url:
                    cached[url] = {"pendencia": "ciclo_documental"}
                elif not relation["admitido"]:
                    cached[url] = {"pendencia": relation["motivo"]}
                elif remaining == 0:
                    cached[url] = {"pendencia": "limite_relacoes"}
                else:
                    remaining -= 1
                    try:
                        page = self._obter_recurso(url)
                        own = self._inventario(page)
                        self.inventarios[url] = own
                        self._descobrir(page, own)
                        original = [r for r in own["recursos"] if r["recurso"] == "original" and r["admitido"]]
                        if len(original) != 1:
                            cached[url] = {"pendencia": "publicacao_original_sem_perfil_ou_ausente"}
                        else:
                            resp = self._obter_recurso(original[0]["url"])
                            doc = self.parse(resp)
                            cached[url] = {"resposta": resp, "documento": doc, "publicacao": original[0]["publicacao"]}
                            if any(r["url"] == candidate.url and r["acao"] for r in own["recursos"]):
                                pending.append({"motivo": "ciclo_documental_na_lista_relacionada", "url": url})
                    except Unavailable as exc:
                        failure = {"url": url, "motivo": exc.reason, "categoria": exc.categoria, **exc.classificacao()}
                        cached[url] = {"pendencia": "recurso_indisponivel", "falha": failure}
                        failures.append(failure)
            material = {"relacao": relation, **cached[url]}
            materials.append(material)
            if material.get("pendencia"):
                pending.append({"motivo": material["pendencia"], "url": url})
        pending.append({"motivo": "completude_da_lista_nao_demonstrada", "url": candidate.url})
        return {"materiais": materials, "pendencias": pending, "indisponibilidades": failures, "cadeia_completa": False}

    def health(self):
        # Robots e termo não são capacidade aprovada: a qualificação segue `nao_apurada` (0080).
        from freoa_verifica.store.db import data_home
        try:
            ativa = self._portao_injetado is not None or ativacao(Estado(self.home or data_home())) is not None
        except EstadoIndisponivel:
            ativa = False  # sem leitura da documentação não se afirma ativação
        return HealthReport(self.id, (HealthProbe("documento", "unavailable",
                                                  "ativada_sem_sonda_de_saude" if ativa else "ativacao_ao_vivo_pendente"),))
