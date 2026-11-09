"""Decisão 0080 §4: robots por token. Reais (capturas intactas) e sintéticos rotulados (gerador: parâmetros do teste)."""
import hashlib
import json

import pytest

from freoa_verifica.connectors import camara_robots as rb
from tests._camara_util import FIX

PORTAL = (FIX / "camara_robots_portal.txt").read_bytes()
LEGIN = (FIX / "camara_robots_legin.txt").read_bytes()
BUSCA = "/legislacao/busca?abrangencia=Legisla%C3%A7%C3%A3o+Federal&tipo=Lei+Ordin%C3%A1ria&numero=6404&ano=1976&geral="
LEI = "/legin/fed/lei/1970-1979/lei-6404-15-dezembro-1976-368447-norma-pl.html"
TERMO = "/termo-de-uso-e-politica-de-privacidade/termos-gerais"


def decidir(texto, caminho):
    return rb.decidir(rb.interpretar(texto), caminho)


# --- capturas reais ---------------------------------------------------------------------------------------------
def test_reais_hashes_conferidos_com_o_recibo():
    for nome, corpo in (("portal", PORTAL), ("legin", LEGIN)):
        recibo = json.loads((FIX / f"camara_robots_{nome}.captura.json").read_bytes())
        assert hashlib.sha256(corpo).hexdigest() == recibo["sha256"]
    assert hashlib.sha256(PORTAL).hexdigest() == "80d159e66519e14dba592a93c29301b63409896856d10f8ff54a55805ec9ce4a"
    assert hashlib.sha256(LEGIN).hexdigest() == "b725bf41f0e293419518714b83edb1c2de6728c5156cba037b848ab0788bee8f"


def test_real_portal_grupo_de_ia_tem_as_mesmas_regras_do_grupo_geral():
    grupos = rb.interpretar(PORTAL.decode())
    ia = next(g for g in grupos if "gptbot" in g.agentes)
    geral = next(g for g in grupos if g.agentes == ["*"])
    assert set(ia.agentes) >= {"gptbot", "chatgpt-user", "google-extended", "anthropic-ai", "claude-web",
                               "omgilibot", "omgili", "facebookbot", "ccbot", "perplexitybot"}
    assert ia.regras == geral.regras and ia.regras  # idênticas, na mesma ordem


@pytest.mark.parametrize("caminho", ["/legislacao", BUSCA])
def test_real_portal_permite_os_caminhos_html_usados(caminho):
    decisao = decidir(PORTAL.decode(), caminho)
    assert decisao.estado == rb.PERMITIDO and decisao.crawl_delay == 0
    assert set(decisao.por_token) == set(rb.TOKENS) and all(v == rb.PERMITIDO for v in decisao.por_token.values())


def test_real_portal_proibe_pdf_com_padrao_sem_cifrao():
    assert decidir(PORTAL.decode(), "/arquivos/norma.pdf").estado == rb.PROIBIDO
    assert decidir(PORTAL.decode(), "/legislacao/norma.pdf?x=1").estado == rb.PROIBIDO  # padrão, não extensão terminal


@pytest.mark.parametrize("caminho", [LEI, TERMO, "/legin/fed/lei/1980-1987/qualquer.html"])
def test_real_www2_nao_proibe_legin_nem_o_termo(caminho):
    assert decidir(LEGIN.decode(), caminho).estado == rb.PERMITIDO


# --- sintéticos: bordas da RFC 9309 ----------------------------------------------------------------------------
def test_grupos_separados_do_mesmo_token_sao_combinados():
    texto = "User-agent: GPTBot\nDisallow: /a\nUser-agent: *\nAllow: /\nUser-agent: GPTBot\nDisallow: /b"
    assert decidir(texto, "/a/x").por_token["GPTBot"] == rb.PROIBIDO
    assert decidir(texto, "/b/x").por_token["GPTBot"] == rb.PROIBIDO
    assert decidir(texto, "/c").por_token["GPTBot"] == rb.PERMITIDO


def test_ordem_dos_grupos_nao_altera_a_decisao():
    a = "User-agent: *\nDisallow: /\nUser-agent: freoa-verifica\nAllow: /"
    b = "User-agent: freoa-verifica\nAllow: /\nUser-agent: *\nDisallow: /"
    assert decidir(a, "/x") == decidir(b, "/x")


def test_token_sem_grupo_proprio_cai_em_asterisco_e_sem_nenhum_e_inconclusivo():
    assert decidir("User-agent: *\nDisallow: /x", "/x").estado == rb.PROIBIDO
    assert decidir("User-agent: outro\nAllow: /", "/x").estado == rb.INCONCLUSIVO
    assert decidir("", "/x").estado == rb.INCONCLUSIVO


def test_maior_correspondencia_decide_e_allow_vence_o_empate():
    assert decidir("User-agent: *\nDisallow: /\nAllow: /legin/", "/legin/a").estado == rb.PERMITIDO
    assert decidir("User-agent: *\nAllow: /legin\nDisallow: /legin", "/legin/a").estado == rb.PERMITIDO  # empate
    assert decidir("User-agent: *\nAllow: /\nDisallow: /legin/fed", "/legin/fed/a").estado == rb.PROIBIDO
    assert decidir("User-agent: *\nDisallow:", "/qualquer").estado == rb.PERMITIDO  # Disallow vazio


@pytest.mark.parametrize("regra,caminho,proibido", [
    ("Disallow: /*.pdf", "/a/b.pdf", True), ("Disallow: /*.pdf", "/a/b.pdf?x", True),
    ("Disallow: /*.pdf$", "/a/b.pdf", True), ("Disallow: /*.pdf$", "/a/b.pdf?x", False),
    ("Disallow: /a*c", "/abbbc", True), ("Disallow: /a*c", "/abbb", False),
    ("Disallow: /legin/$", "/legin/", True), ("Disallow: /legin/$", "/legin/x", False),
])
def test_curingas_e_cifrao(regra, caminho, proibido):
    assert (decidir(f"User-agent: *\n{regra}", caminho).estado == rb.PROIBIDO) is proibido


def test_qualquer_token_proibido_proibe_o_conjunto():
    texto = "User-agent: *\nAllow: /\nUser-agent: ClaudeBot\nDisallow: /"
    decisao = decidir(texto, "/legin/a")
    assert decisao.estado == rb.PROIBIDO and decisao.por_token["ClaudeBot"] == rb.PROIBIDO
    assert decisao.por_token[rb.TOKEN_PRODUTO] == rb.PERMITIDO


def test_token_do_produto_proibido_proibe_mesmo_com_ia_liberada():
    texto = "User-agent: *\nAllow: /\nUser-agent: freoa-verifica\nDisallow: /"
    assert decidir(texto, "/x").estado == rb.PROIBIDO


def test_grupos_de_outros_agentes_nao_entram():
    texto = "User-agent: *\nAllow: /\nUser-agent: AhrefsBot\nDisallow: /\nUser-agent: Googlebot\nCrawl-delay: abc"
    decisao = decidir(texto, "/x")
    assert decisao.estado == rb.PERMITIDO and decisao.crawl_delay == 0


def test_crawl_delay_e_o_maior_valor_valido_entre_os_grupos_aplicados():
    texto = ("User-agent: *\nCrawl-delay: 5\nUser-agent: GPTBot\nCrawl-delay: 30\n"
             "User-agent: bingbot\nCrawl-delay: 900")
    assert decidir(texto, "/x").crawl_delay == 30.0


@pytest.mark.parametrize("valor", ["abc", "-1", "nan", "inf", ""])
def test_crawl_delay_invalido_em_grupo_aplicado_e_inconclusivo(valor):
    decisao = decidir(f"User-agent: *\nCrawl-delay: {valor}", "/x")
    assert decisao.estado == rb.INCONCLUSIVO and decisao.motivo == "crawl_delay_invalido"


@pytest.mark.parametrize("valor", ["3601", "99999", "86400"])
def test_crawl_delay_maior_que_o_teto_operacional_e_valido_e_honrado(valor):
    """Atraso acima do teto atual não é sintaticamente inválido (parecer r1, achado 3): a política o registra."""
    decisao = decidir(f"User-agent: *\nCrawl-delay: {valor}", "/x")
    assert decisao.estado == rb.PERMITIDO and decisao.crawl_delay == float(valor)


@pytest.mark.parametrize("texto", ["isto não é robots", "Disallow: /x", "User-agent:\nAllow: /",
                                   "User-agent: *\nHost: exemplo.gov.br"])
def test_malformado_e_inconclusivo(texto):
    with pytest.raises(rb.RobotsInconclusivo):
        rb.interpretar(texto)


def test_regra_malformada_so_invalida_o_grupo_em_que_esta():
    assert decidir("User-agent: *\nAllow: /\nUser-agent: Googlebot\nDisallow: sem-barra", "/x").estado == rb.PERMITIDO
    assert decidir("User-agent: *\nDisallow: sem-barra", "/x").estado == rb.INCONCLUSIVO


def test_lista_fechada_de_tokens_da_decisao():
    assert rb.TOKENS_IA == ("GPTBot", "ChatGPT-User", "Google-Extended", "anthropic-ai", "Claude-Web", "ClaudeBot",
                            "Claude-User", "Claude-SearchBot", "Omgilibot", "Omgili", "FacebookBot", "CCBot",
                            "PerplexityBot")
    assert rb.TOKEN_PRODUTO == "freoa-verifica"


def test_token_de_ia_nao_listado_nao_e_inferido_de_comentario():
    texto = "# GPTBot e SuperBot de IA\nUser-agent: *\nAllow: /\nUser-agent: SuperBot\nDisallow: /"
    assert decidir(texto, "/x").estado == rb.PERMITIDO


# --- RFC 9309 §2.2.2: comparação e especificidade sobre octetos normalizados (parecer r1, achado 3) --------------------------
@pytest.mark.parametrize("regra,caminho,estado", [
    ("Disallow: /legislacao/%62usca", "/legislacao/busca", rb.PROIBIDO),  # C01: %62 é `b`, não reservado: decodificado
    ("Disallow: /legislacao/busca", "/legislacao/%62usca", rb.PROIBIDO),  # a equivalência vale nos dois sentidos
    ("Disallow: /a%3cd.html", "/a%3Cd.html", rb.PROIBIDO),  # hexadecimal sem distinção de caixa
    ("Disallow: /a%3Cd.html", "/a%3cd.html", rb.PROIBIDO),
    ("Disallow: /~joe", "/%7Ejoe", rb.PROIBIDO),  # `~` é não reservado
    ("Disallow: /%7Ejoe", "/~joe", rb.PROIBIDO),
    ("Disallow: /SanJoséSellers", "/SanJos%C3%A9Sellers", rb.PROIBIDO),  # octetos fora do ASCII
    ("Disallow: /SanJos%C3%A9Sellers", "/SanJoséSellers", rb.PROIBIDO),
    ("Disallow: /SanJos%c3%a9", "/SanJos%C3%A9", rb.PROIBIDO),
    ("Disallow: /a%2fb", "/a/b", rb.PERMITIDO),  # `/` é reservado: `%2F` NÃO é decodificado
    ("Disallow: /a/b", "/a%2fb", rb.PERMITIDO),
    ("Disallow: /a%2Fb", "/a%2fb", rb.PROIBIDO),
    ("Disallow: /x%2A", "/x%2a", rb.PROIBIDO),  # `*` codificado é octeto literal, não curinga
    ("Disallow: /x%2A", "/xyz", rb.PERMITIDO),
    ("Disallow: /x%24", "/x", rb.PERMITIDO),  # `$` codificado não ancora o fim
    ("Disallow: /%41%42", "/AB", rb.PROIBIDO),  # letras decodificadas
    ("Disallow: /q?a=%62", "/q?a=b", rb.PROIBIDO),  # na query também
    ("Disallow: /*.pdf$", "/x%2Epdf", rb.PROIBIDO),  # `.` é não reservado
    ("Disallow: /ab%zz", "/ab%zz", rb.PROIBIDO),  # `%` inválido segue literal, igual nos dois lados
])
def test_rfc9309_comparacao_por_octetos_normalizados(regra, caminho, estado):
    assert decidir(f"User-agent: *\n{regra}", caminho).estado == estado


def test_especificidade_e_medida_em_octetos_normalizados_e_allow_vence_o_empate():
    # `Allow` mais longo em octetos vence o `Disallow` mais curto, ainda que escrito com percent-encoding
    texto = "User-agent: *\nDisallow: /p\nAllow: /p%61th"
    assert decidir(texto, "/path").estado == rb.PERMITIDO
    # a mesma regra por extenso e por codificação empata em octetos: `Allow` prevalece
    assert decidir("User-agent: *\nDisallow: /path\nAllow: /p%61th", "/path").estado == rb.PERMITIDO
    # `Disallow` mais específico (em octetos) que o `Allow` prevalece
    assert decidir("User-agent: *\nAllow: /p\nDisallow: /p%61th", "/path").estado == rb.PROIBIDO
    # octeto fora do ASCII conta como três octetos (`%C3%A9`) na regra normalizada: vence o Allow de 4
    texto = "User-agent: *\nAllow: /abc\nDisallow: /é"
    assert decidir(texto, "/é").estado == rb.PROIBIDO


def test_normalizar_e_idempotente_e_so_decodifica_nao_reservados():
    assert rb.normalizar(b"/a%62c") == b"/abc"
    assert rb.normalizar(b"/a%2fc") == b"/a%2Fc"
    assert rb.normalizar(rb.normalizar("/é%7E".encode())) == rb.normalizar("/é%7E".encode()) == b"/%C3%A9~"
