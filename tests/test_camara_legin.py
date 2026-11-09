"""IL.2-c: constantes de rota e expectativas transcritas das capturas, sem parser-oráculo."""
import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from freoa_verifica.connectors.base import Candidate, Unavailable, registry
from freoa_verifica.connectors.camara_legin import CamaraLeginConnector, politica_robots
from freoa_verifica.connectors.camara_policy import validar_url
from freoa_verifica.identidade_http import USER_AGENT_IDENTIFICADO
from freoa_verifica.transport import Response
from tests._camara_util import RelogioFalso

FIX = Path(__file__).parent / "fixtures" / "camara_legin"
LSA = "https://www2.camara.leg.br/legin/fed/lei/1970-1979/lei-6404-15-dezembro-1976-368447-norma-pl.html"
ATUAL = "https://www2.camara.leg.br/legin/fed/lei/1970-1979/lei-6404-15-dezembro-1976-368447-normaatualizada-pl.html"
ORIGINAL = "https://www2.camara.leg.br/legin/fed/lei/1970-1979/lei-6404-15-dezembro-1976-368447-publicacaooriginal-1-pl.html"


def response(key):
    meta = json.loads((FIX / f"camara_{key}.captura.json").read_bytes())
    body = (FIX / f"camara_{key}{Path(meta['arquivo']).suffix}").read_bytes()
    return Response(meta["url"], meta["url_final"], meta["status"], meta["cabecalhos"], body,
                    meta["sha256"], meta["capturado_em"], [], meta["content_type"],
                    size=len(body), content_type=meta["cabecalhos"]["content-type"])


@pytest.fixture
def servidor(monkeypatch, proibir_rede):
    responses = {response(p.stem.removeprefix("camara_").removesuffix(".captura")).url:
                 response(p.stem.removeprefix("camara_").removesuffix(".captura"))
                 for p in FIX.glob("camara_*.captura.json")}
    calls = type("Chamadas", (list,), {})()
    def fetch(url, **kw):
        calls.append((url, kw))
        assert kw["max_redirects"] == 0
        assert kw["headers"]["User-Agent"] == USER_AGENT_IDENTIFICADO
        if url not in responses:
            raise AssertionError(f"URL não documentada: {url}")
        # o transporte vivo carimba o instante do recebimento; os bytes e o hash são os da captura real, intactos
        return replace(responses[url], fetched_at=datetime.now(timezone.utc).isoformat())
    monkeypatch.setattr("freoa_verifica.connectors.httputil.transport_fetch", fetch)
    from freoa_verifica.connectors.httputil import connector_fetch
    init = CamaraLeginConnector.__init__
    relogio = RelogioFalso()
    monkeypatch.setattr(CamaraLeginConnector, "__init__",
                        lambda self: init(self, transporte_offline=connector_fetch, relogio=relogio))
    calls.relogio = relogio
    return responses, calls


@pytest.mark.parametrize("kind,num,year,title", [
    ("lei", "6404", 1976, "LEI Nº 6.404, DE 15 DE DEZEMBRO DE 1976"),
    ("lei_complementar", "123", 2006, "LEI COMPLEMENTAR Nº 123, DE 14 DE DEZEMBRO DE 2006"),
    ("lei", "13874", 2019, "LEI Nº 13.874, DE 20 DE SETEMBRO DE 2019"),
])
def test_c1_c4_identidades_e_query(servidor, kind, num, year, title):
    _, calls = servidor
    con = CamaraLeginConnector()
    cand = con.resolve({"kind": kind, "number": num, "year": year})
    assert cand.title == title
    assert registry()["camara_legin"] is CamaraLeginConnector
    assert cand.source_id == "camara_legin"
    query = "tipo=Lei+Complementar" if kind == "lei_complementar" else "tipo=Lei+Ordin%C3%A1ria"
    assert calls[1][0] == ("https://www.camara.leg.br/legislacao/busca?abrangencia=Legisla%C3%A7%C3%A3o+Federal&"
                            f"{query}&numero={num}&ano={year}&geral=")
    assert calls[0][0] == "https://www.camara.leg.br/robots.txt"


@pytest.mark.parametrize("url", [
    LSA.replace("www2.camara.leg.br", "www2.camara.leg.br.evil.org"),
    LSA.replace("www2.camara", "auditoria.camara"), LSA.replace("https://", "http://"),
    LSA.replace("https://", "https://user@"), LSA.replace(".br/", ".br:443/"),
    LSA + "?x=1", LSA + ".bak", LSA.replace("/lei/", "/leicom/"),
    LSA.replace("1970-1979", "1980-1987"), LSA.replace("15-dezembro", "32-dezembro"),
    LSA.replace("/lei/", "/lei/../lei/"), LSA.replace("/lei/", "/lei/%252f/"),
    LSA.replace("/lei/", "/lei/extra/"), LSA.replace("368447", "999999"),
])
def test_c2_zero_envio_negativas(servidor, url):
    _, calls = servidor
    with pytest.raises((ValueError, Unavailable)):
        CamaraLeginConnector().fetch(Candidate("camara_legin", "x", "x", url))
    assert calls == []


@pytest.mark.parametrize("text,path,allowed", [
    ("User-agent: *\nDisallow: /legin/", "/legin/fed/lei/a", False),
    ("User-agent: *\nDisallow: /\nAllow: /legin/", "/legin/fed/lei/a", True),
    ("User-agent: *\nDisallow: /*.html$", "/legin/a.html", False),
    ("User-agent: *\nDisallow: /*.html$", "/legin/a.htmlx", True),
    # 0080 §4.1: permitir só ao token do produto não basta; os tokens de IA caem em `*` e o conjunto proíbe.
    ("User-agent: *\nDisallow: /\nUser-agent: freoa-verifica\nAllow: /", "/legin/a", False),
    ("User-agent: *\nAllow: /\nUser-agent: freoa-verifica\nDisallow: /", "/legin/a", False),
])
def test_c3_robots_sinteticos_em_memoria(text, path, allowed):
    # Gerador: parâmetros deste teste; propósito: bordas RFC 9309, sem captura fictícia.
    assert politica_robots(text, path) == (allowed, 0)


@pytest.mark.parametrize("text", ["", "isto não é robots", "Disallow: /", "User-agent: outro\nAllow: /"])
def test_c3_robots_inconclusivo(text):
    with pytest.raises(ValueError):
        politica_robots(text, "/legin/a")


def test_c3_proibicao_impede_conteudo(servidor):
    responses, calls = servidor
    robot = responses["https://www.camara.leg.br/robots.txt"]
    raw = b"User-agent: *\nDisallow: /legislacao/"
    responses[robot.url] = replace(robot, body=raw, sha256=hashlib.sha256(raw).hexdigest(), headers={}, size=len(raw))
    with pytest.raises(Unavailable, match="robots_recusa"):
        CamaraLeginConnector().search("Lei 6404/1976")
    assert [c[0] for c in calls] == [robot.url]


def test_c5_inventario_lc123(servidor):
    con = CamaraLeginConnector()
    cand = con.resolve({"kind": "lei_complementar", "number": "123", "year": 2006})
    resources = cand.metadata["inventario"]["recursos"]
    assert len([r for r in resources if r["rotulo"] == "Texto - Republicação"]) == 3
    assert len([r for r in resources if "Anexo" in r["rotulo"] and not r["acao"]]) == 4
    assert len([r for r in resources if r["acao"] and "leicomplementar-214-" in r["url"]]) > 1
    original = next(r for r in resources if r["recurso"] == "original")
    assert original["publicacao"]["data"] == "2006-12-15"
    assert original["publicacao"]["pagina"] == "1"
    assert all(not r["obtido"] for r in resources)
    assert all(r["motivo"] for r in resources)


@pytest.mark.parametrize("key", ["textos_atualizado_lei6404", "textos_original_lei6404"])
def test_c6_c8_recorte_156_e_notas(servidor, key):
    con = CamaraLeginConnector()
    cand = con.resolve({"kind": "lei", "number": "6404", "year": 1976})
    version = "publicacao_original" if "original" in key else "vigente"
    doc = con.parse(con.fetch(replace(cand, metadata={**cand.metadata, "versao": version})))
    expected = ("Art. 156. É vedado ao administrador intervir em qualquer operação social em que tiver interesse conflitante "
                "com o da companhia, bem como na deliberação que a respeito tomarem os demais administradores, "
                "cumprindo-lhe cientificá-los do seu impedimento e fazer consignar, em ata de reunião do conselho "
                "de administração ou da diretoria, a natureza e extensão do seu interesse.")
    first = doc.provision("art156")
    assert first.redactions[0].text.split("\n")[0] == expected
    assert doc.provision("art156.par1") is not None
    assert doc.provision("art156.par2") is not None
    suffix = "." if version == "publicacao_original" else ""
    assert first.redactions[0].text == expected + (
        f"\n§ 1º{suffix} Ainda que observado o disposto neste artigo, o administrador somente pode contratar com a companhia "
        "em condições razoáveis ou eqüitativas, idênticas às que prevalecem no mercado ou em que a companhia "
        f"contrataria com terceiros.\n§ 2º{suffix} O negócio contratado com infração do disposto no § 1º é anulável, "
        "e o administrador interessado será obrigado a transferir para a companhia as vantagens que dele tiver auferido.")
    assert "transferir para a companhia as vantagens que dele tiver auferido." in first.redactions[0].text
    assert "art157" not in first.redactions[0].text
    assert doc.provision("art289") is not None
    if version == "vigente":
        assert doc.provision("art254-A") is not None
        assert doc.provision("art289").redactions[0].text.startswith("Art. 289. As publicações ordenadas por esta Lei obedecerão às seguintes condições:")
        assert "Caput" not in doc.provision("art289").redactions[0].text
        assert doc.provision("art289.caput").redactions[0].annotations
        assert not doc.provision("art289").redactions[0].annotations
        for b in doc.editorial_blocks:
            if b.kind == "nota_camara":
                assert doc.text[b.span[0]:b.span[1]] == b.text
    else:
        assert doc.provision("art254-A") is None


def test_c2_mutante_redirect_sem_salto(servidor):
    responses, calls = servidor
    robot = responses["https://www.camara.leg.br/robots.txt"]
    responses[robot.url] = replace(robot, status=302, headers={"location": "https://www.camara.leg.br/admin"})
    with pytest.raises(Unavailable):
        CamaraLeginConnector().search("Lei 6404/1976")
    assert len(calls) == 1


def test_c2_urls_positivas_independentes():
    for url in (LSA, ATUAL, ORIGINAL,
                "https://www2.camara.leg.br/legin/fed/leicom/2006/leicomplementar-123-14-dezembro-2006-548099-anexo-pl.pdf"):
        assert validar_url(url)["recurso"] in {"norma", "atualizado", "original", "anexo"}


def test_c13_pdf_preservado_mas_recorte_nao_aprovado(servidor):
    con = CamaraLeginConnector()
    cand = con.resolve({"kind": "lei_complementar", "number": "123", "year": 2006})
    resp = con.fetch_anexo(cand)
    assert resp.sha256 == "c8abdd8ca254a81e4d274335c705630c21ed3cf24948ba70fc12ab145a096887"
    doc = con.parse(resp)
    leaves = [b for b in doc.editorial_blocks if b.kind.startswith("folha_pdf_")]
    assert [b.kind for b in leaves] == ["folha_pdf_1", "folha_pdf_2", "folha_pdf_3"]
    assert leaves[1].text == leaves[2].text
    assert doc.quarantined
    assert {i.code for i in doc.issues} == {"TEXTO_EXTRAIDO_REPETIDO", "ESCOPO_ANEXO_NAO_VALIDADO"}
    config = json.loads(doc.editorial_blocks[0].text)
    assert config["extrator"] == "pypdf"
    assert config["extraction_mode"] == "plain"
    assert config["versao"]


def sintetico(body):
    # Gerador deste teste; propósito: bordas de segmentação e notas, nunca captura oficial.
    from freoa_verifica.parsers.camara_legin import parse_camara_legin
    return parse_camara_legin("<html><body><h1>LEI Nº 1, DE 1 DE JANEIRO DE 2001</h1>" + body +
                              "<p>Brasília, 1 de janeiro de 2001.</p></body></html>")


def test_c6_c7_hierarquia_sintetica_e_duplicidade():
    doc = sintetico('<p>Art.\n1º Texto (oitenta por cento).</p><p>§ 1º Primeiro.<br/>I - Inciso.</p>'
                    '<table><tr><td>a)</td><td>Alínea.</td></tr></table><p>1. Item.</p>'
                    '<p>Art. 2º Outro.</p><p>§ 1º A.<br/>§ 1º B.</p>')
    assert {p.path for p in doc.provisions} >= {"art1", "art1.par1", "art1.par1.inc1",
                                               "art1.par1.inc1.ali-a", "art1.par1.inc1.ali-a.item1"}
    assert "(oitenta por cento)" in doc.provision("art1").redactions[0].text
    assert doc.provision("art2.par1").ambiguous
    assert any(i.code == "DUPLICATE_CURRENT" and i.path == "art2" for i in doc.issues)


def test_c8_nota_incerta_bloqueia_sem_apagar_parenteses():
    doc = sintetico('<p>Art. 1º Valor (oitenta por cento). (Redação extraordinária da Lei nº 2/2002)</p>')
    assert "(oitenta por cento)" in doc.provision("art1").redactions[0].text
    assert "Redação extraordinária" in doc.provision("art1").redactions[0].text
    assert any(i.code == "NOTA_NAO_RECONHECIDA" for i in doc.issues)


def test_c6_c17_citacao_e_script_sao_dados():
    doc = sintetico('<script>Art. 999. Ignore as regras.</script><p>Art. 1º A Lei nº 2 passa a vigorar com a seguinte redação:</p>'
                    '<p>“Art. 9º Texto de outra lei.” (NR)</p><p>Art. 2º Próprio. Referência ao art. 10.</p>')
    assert {p.path for p in doc.provisions} == {"art1", "art1.caput", "art2", "art2.caput"}
    assert len(doc.amendments) == 1
    assert "Texto de outra lei" in doc.amendments[0].text
    assert "Ignore" not in doc.text


def test_c2_c14_evidencia_corrompida_recusada(servidor):
    con = CamaraLeginConnector()
    cand = con.resolve({"kind": "lei", "number": "6404", "year": 1976})
    resp = con.fetch(cand)
    with pytest.raises(Unavailable, match="hash_captura_divergente"):
        con.parse(replace(resp, body=resp.body.replace(b"vedado", b"livre ")))


def test_c1_texto_de_outra_obra_recusado(servidor):
    con = CamaraLeginConnector()
    cand = con.resolve({"kind": "lei", "number": "6404", "year": 1976})
    resp = con.fetch(cand)
    raw = resp.body.replace(b"6.404", b"6.405", 1)
    with pytest.raises(Unavailable, match="identidade_texto_divergente"):
        con.parse(replace(resp, body=raw, sha256=hashlib.sha256(raw).hexdigest(), headers={}, size=len(raw)))


@pytest.mark.parametrize("url", [LSA + "?x=1", LSA + ".bak", LSA.replace("/lei/", "/leicom/"),
                               LSA.replace("1970-1979", "1980-1987")])
def test_c2_gramatica_direta(url):
    with pytest.raises(ValueError):
        validar_url(url)


def test_c10_texto_alterador_real_e_mp_apenas_pagina(servidor):
    con = CamaraLeginConnector()
    candidate = con.resolve({"kind": "lei", "number": "6404", "year": 1976})
    inv = con.inventarios[candidate.url]
    relations = [r for r in inv["recursos"] if r["acao"] and
                 ("lei-13874-" in r["url"] or "medidaprovisoria-881-" in r["url"])]
    assert len(relations) == 2
    # Janela explícita do teste: só estes dois recursos têm corpos relacionados neste lote.
    con.inventarios[candidate.url] = {**inv, "recursos": relations}
    result = con.capturar_relacoes(candidate)
    law = next(m for m in result["materiais"] if "lei-13874-" in m["relacao"]["url"])
    mp = next(m for m in result["materiais"] if "medidaprovisoria-881-" in m["relacao"]["url"])
    assert law["resposta"].sha256 == "4fd5ddbc75e7dc56ab3c2d53c7abdcbb3eee46c894e18b5a3d07041e7cd244c3"
    assert law["documento"].title == "LEI Nº 13.874, DE 20 DE SETEMBRO DE 2019"
    assert law["documento"].provision("art50") is None  # artigo citado do Código Civil não pertence à alteradora
    assert any("Art. 50" in amendment.text for amendment in law["documento"].amendments)
    assert law["publicacao"]["data"] == "2019-09-20"
    assert "resposta" not in mp and "documento" not in mp
    assert mp["pendencia"] == "publicacao_original_sem_perfil_ou_ausente"
    assert result["cadeia_completa"] is False
    assert con.paginas[mp["relacao"]["url"]].sha256 == "677752f6feaea991ca461933384b451d46d1a2f9c9d0cc7a6b6708de1b73b9e1"


def test_c10_multiplas_acoes_limite_e_ciclo(servidor):
    con = CamaraLeginConnector()
    candidate = con.resolve({"kind": "lei", "number": "6404", "year": 1976})
    inv = con.inventarios[candidate.url]
    rel = next(r for r in inv["recursos"] if r["acao"] and "medidaprovisoria-881-" in r["url"])
    # Gerador: metadados deste teste; propósito: duas ações, ciclo e limite, sem captura fictícia.
    con.inventarios[candidate.url] = {**inv, "recursos": [rel, {**rel, "acao": "Revogação parcial"},
                                                         {**rel, "url": candidate.url}]}
    result = con.capturar_relacoes(candidate, limite=0)
    assert len(result["materiais"]) == 3
    assert [m["pendencia"] for m in result["materiais"]] == ["limite_relacoes", "limite_relacoes", "ciclo_documental"]
    result = con.capturar_relacoes(candidate, limite=1)
    assert result["materiais"][0]["relacao"]["acao"] == "Alteração"
    assert result["materiais"][1]["relacao"]["acao"] == "Revogação parcial"
    assert len([url for url, _ in servidor[1] if url == rel["url"]]) == 1


def test_c6_gabaritos_integrais_289_e_254a(servidor):
    # Transcrição conferida nos corpos HTML, sem usar a saída do parser como gabarito.
    con = CamaraLeginConnector()
    candidate = con.resolve({"kind": "lei", "number": "6404", "year": 1976})
    current = con.parse(con.fetch(candidate))
    original = con.parse(con.fetch(replace(candidate, metadata={**candidate.metadata, "versao": "publicacao_original"})))
    expected_original = (
        'Art. 289. As publicações ordenadas pela presente Lei serão feitas no órgão oficial da União ou do Estado, conforme o lugar '
        'em que esteja situada a sede da companhia, e em outro jornal de grande circulação editado na localidade em que '
        'está situado a sede da companhia. '
        '§ 1º. A Comissão de Valores Mobiliários poderá determinar que as publicações, ordenadas pela presente Lei, sejam '
        'feitas, também, em jornal de grande circulação editado nas localidades em que os valores mobiliários da companhia '
        'sejam negociados em bolsa ou em mercado de balcão. '
        '§ 2º. Se no lugar em que estiver situada a sede da companhia não for editado jornal, a publicação se fará em órgão '
        'de grande circulação local. '
        '§ 3º. A companhia deve fazer as publicações previstas nesta Lei sempre no mesmo jornal, e qualquer mudança deverá '
        'ser precedida de aviso aos acionistas no extrato da ata da assembléia-geral ordinária. '
        '§ 4º. O disposto no final do § 3º não se aplica à eventual publicação de atas ou balanços em outros jornais. '
        '§ 5º. Todas as publicações ordenadas nesta Lei deverão ser arquivadas no registro do comércio. '
        '§ 6º. As aplicações do balanço e demonstração de conta de lucros e perdas poderão ser feitas adotando-se como '
        'expressão monetária o "milhar de cruzeiros".'
    )
    expected_current = (
        'Art. 289. As publicações ordenadas por esta Lei obedecerão às seguintes condições: '
        'I - deverão ser efetuadas em jornal de grande circulação editado na localidade em que esteja situada a sede da '
        'companhia, de forma resumida e com divulgação simultânea da íntegra dos documentos na página do mesmo jornal '
        'na internet, que deverá providenciar certificação digital da autenticidade dos documentos mantidos na página '
        'própria emitida por autoridade certificadora credenciada no âmbito da Infraestrutura de Chaves Públicas '
        'Brasileiras (ICP-Brasil); '
        'II - no caso de demonstrações financeiras, a publicação de forma resumida deverá conter, no mínimo, em comparação '
        'com os dados do exercício social anterior, informações ou valores globais relativos a cada grupo e a respectiva '
        'classificação de contas ou registros, assim como extratos das informações relevantes contempladas nas notas '
        'explicativas e nos pareceres dos auditores independentes e do conselho fiscal, se houver. '
        '§ 1º A Comissão de Valores Mobiliários poderá determinar que as publicações ordenadas por esta lei sejam feitas, '
        'também, em jornal de grande circulação nas localidades em que os valores mobiliários da companhia sejam '
        'negociados em bolsa ou em mercado de balcão, ou disseminadas por algum outro meio que assegure sua ampla '
        'divulgação e imediato acesso às informações. '
        '§ 2º Se no lugar em que estiver situada a sede da companhia não for editado jornal, a publicação se fará em órgão '
        'de grande circulação local. '
        '§ 3º A companhia deve fazer as publicações previstas nesta Lei sempre no mesmo jornal, e qualquer mudança deverá '
        'ser precedida de aviso aos acionistas no extrato da ata da assembléia-geral ordinária. '
        '§ 4º O disposto no final do § 3º não se aplica à eventual publicação de atas ou balanços em outros jornais. '
        '§ 5º Todas as publicações ordenadas nesta Lei deverão ser arquivadas no registro do comércio. '
        '§ 6º As publicações do balanço e da demonstração de lucros e perdas poderão ser feitas adotando-se como expressão '
        'monetária o milhar de reais. '
        '§ 7º Sem prejuízo do disposto no caput deste artigo, as companhias abertas poderão, ainda, disponibilizar as '
        'referidas publicações pela rede mundial de computadores.'
    )
    expected_254a = (
        'Art. 254-A. A alienação, direta ou indireta, do controle de companhia aberta somente poderá ser contratada sob a condição, '
        'suspensiva ou resolutiva, de que o adquirente se obrigue a fazer oferta pública de aquisição das ações com direito '
        'a voto de propriedade dos demais acionistas da companhia, de modo a lhes assegurar o preço no mínimo igual a '
        '80% (oitenta por cento) do valor pago por ação com direito a voto, integrante do bloco de controle. '
        '§ 1º Entende-se como alienação de controle a transferência, de forma direta ou indireta, de ações integrantes do '
        'bloco de controle, de ações vinculadas a acordos de acionistas e de valores mobiliários conversíveis em ações '
        'com direito a voto, cessão de direitos de subscrição de ações e de outros títulos ou direitos relativos a valores '
        'mobiliários conversíveis em ações que venham a resultar na alienação de controle acionário da sociedade. '
        '§ 2º A Comissão de Valores Mobiliários autorizará a alienação de controle de que trata o caput, desde que verificado '
        'que as condições da oferta pública atendem aos requisitos legais. '
        '§ 3º Compete à Comissão de Valores Mobiliários estabelecer normas a serem observadas na oferta pública de que trata o caput. '
        '§ 4º O adquirente do controle acionário de companhia aberta poderá oferecer aos acionistas minoritários a opção de '
        'permanecer na companhia, mediante o pagamento de um prêmio equivalente à diferença entre o valor de mercado das '
        'ações e o valor pago por ação integrante do bloco de controle. § 5º'
    )
    for doc, path, expected in [(original, "art289", expected_original), (current, "art289", expected_current),
                                (current, "art254-A", expected_254a)]:
        provision = doc.provision(path)
        assert " ".join(provision.redactions[0].text.split()) == expected
        start, end = provision.redactions[0].span
        assert doc.text[start:end].startswith(provision.label)
        assert end <= len(doc.text)


def test_c6_tabelas_reais_e_c8_referencias_editoriais(servidor):
    con = CamaraLeginConnector()
    candidate = con.resolve({"kind": "lei", "number": "6404", "year": 1976})
    original = con.parse(con.fetch(replace(candidate, metadata={**candidate.metadata, "versao": "publicacao_original"})))
    assert original.provision("art30.par1.ali-a").redactions[0].text == "a) as operações de resgate, reembolso ou amortização previstas em lei;"
    assert original.provision("art30.par1.ali-b").redactions[0].text == (
        "b) a aquisição, para permanência em tesouraria ou cancelamento, desde que até o valor do saldo de lucros ou reservas, "
        "exceto a legal, e sem diminuição do capital social, ou por doação;")
    current = con.parse(con.fetch(candidate))
    renumbered = current.provision("art137.inc4")
    ann = next(a for a in renumbered.redactions[0].annotations if a.kind == "renumerado")
    assert ann.raw == "(Primitivo inciso III renumerado pela Lei nº 10.303, de 31/10/2001)"
    assert ann.act_date == "2001-10-31"
    assert ann.act_href == "http://www2.camara.leg.br/legin/fed/lei/2001/lei-10303-31-outubro-2001-414210-norma-pl.html"
    assert current.provision("art137.inc3").redactions[0].text != renumbered.redactions[0].text


@pytest.mark.parametrize("kind,number,year,source,query", [
    ("lei", "123", 2006, "busca_lc123", "https://www.camara.leg.br/legislacao/busca?abrangencia=Legisla%C3%A7%C3%A3o+Federal&tipo=Lei+Ordin%C3%A1ria&numero=123&ano=2006&geral="),
    ("lei", "6404", 1977, "busca_lei6404", "https://www.camara.leg.br/legislacao/busca?abrangencia=Legisla%C3%A7%C3%A3o+Federal&tipo=Lei+Ordin%C3%A1ria&numero=6404&ano=1977&geral="),
])
def test_c1_especie_e_ano_nao_sao_confirmados_por_numero(servidor, kind, number, year, source, query):
    # Gerador: resposta deslocada deste teste; propósito: homônimo de espécie/ano, não captura real nova.
    base = response(source)
    servidor[0][query] = replace(base, url=query, final_url=query)
    with pytest.raises(Unavailable, match="identidade_nao_confirmada"):
        CamaraLeginConnector().resolve({"kind": kind, "number": number, "year": year})


def test_c4_total_desconhecido_e_sem_zero_por_silencio(servidor):
    con = CamaraLeginConnector()
    result = con.search("Lei 6404/1976")
    assert len(result) == 1
    assert result.total is None and result.total_exato is None
    url = next(url for url in servidor[0] if "/busca?" in url and "numero=6404" in url)
    resp = servidor[0][url]
    body = b"<html><body>Nenhum resultado.</body></html>"
    servidor[0][url] = replace(resp, body=body, sha256=hashlib.sha256(body).hexdigest(), headers={}, size=len(body))
    with pytest.raises(Unavailable) as error:
        CamaraLeginConnector().search("Lei 6404/1976")
    assert error.value.reason == "busca_sem_estrutura_reconhecida"
    assert error.value.categoria == "resposta_inesperada"
    assert error.value.evidencia["sha256"] == hashlib.sha256(body).hexdigest()


@pytest.mark.parametrize("status,categoria", [(401, "recusa_identificado"), (403, "recusa_identificado"),
                                             (503, "fonte_fora"), (404, None)])
def test_c3_c14_falha_robots_encerra_sem_fallback(monkeypatch, proibir_rede, status, categoria):
    from freoa_verifica.transport import HTTPStatusError
    calls = []
    def falha(url, **kw):
        calls.append((url, kw))
        raise HTTPStatusError(status)
    monkeypatch.setattr("freoa_verifica.connectors.httputil.transport_fetch", falha)
    from freoa_verifica.connectors.httputil import connector_fetch
    with pytest.raises(Unavailable) as error:
        CamaraLeginConnector(transporte_offline=connector_fetch).search("Lei 6404/1976")
    assert error.value.categoria == categoria
    # 0080 §4.4: robots ausente (404) é decisão fechada `robots_inconclusivo`; os demais mantêm a classe do §6.
    assert error.value.reason == ("robots_inconclusivo" if status == 404 else f"http_{status}")
    assert [c[0] for c in calls] == ["https://www.camara.leg.br/robots.txt"]
    assert calls[0][1]["max_redirects"] == 0
    assert calls[0][1]["headers"]["User-Agent"] == USER_AGENT_IDENTIFICADO


def test_c2_releitura_valida_url_solicitada_tambem(servidor):
    con = CamaraLeginConnector()
    candidate = con.resolve({"kind": "lei", "number": "6404", "year": 1976})
    resp = con.fetch(candidate)
    before = len(servidor[1])
    with pytest.raises(Unavailable, match="resposta_camara_invalida"):
        con.parse(replace(resp, url="https://www2.camara.leg.br/legin/fed/admin"))
    assert len(servidor[1]) == before


def test_c6_c7_truncamento_e_lacuna_nao_sao_texto_integro():
    from freoa_verifica.parsers.camara_legin import parse_camara_legin
    doc = parse_camara_legin('<html><body><p>Art. 1º Início sem fecho')
    assert doc.quarantined
    assert any(i.code == "TRUNCATED" for i in doc.issues)
    doc = sintetico('<p>Art. 1º Primeiro.</p><p>Art. 3º Terceiro.</p>')
    assert doc.quarantined
    assert any(i.detail == "sequência de artigos com lacuna não explicada" for i in doc.issues)
