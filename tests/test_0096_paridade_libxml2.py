"""0096: o parser lê o HTML do Planalto e da CVM do mesmo modo em qualquer libxml2.

As wheels da lxml trazem libxml2 2.11 no Windows e 2.14 no Linux. Sem a normalização, o teste do travessão falha na
2.11 (Windows: U+0096 e inciso perdido) e o do fechamento solto falha na 2.14 (Linux: o texto final é descartado);
a CI roda nas duas plataformas. Os testes de normalização fixam o contrato léxico em qualquer plataforma.
"""

from freoa_verifica.parsers.html_devices import parse_html_devices
from freoa_verifica.parsers.html_paridade import normalizar_para_lxml


def _ler(corpo: str):
    _titulo, _ementa, texto, provisions, *_ = parse_html_devices(
        "<html><head></head><body>" + corpo + "</body></html>",
        base_url="https://www.planalto.gov.br/ccivil_03/leis/l0001.htm")
    return texto, {p.path: p for p in provisions}


def _sem_c1(texto: str) -> bool:
    return not any("\x80" <= ch <= "\x9f" for ch in texto)


# --- contrato da normalização ---------------------------------------------------------------------------------

def test_referencias_de_128_a_159_viram_o_caractere_do_html5():
    assert normalizar_para_lxml("I &#150; a; II &#x96; b; &#145;x&#146; &#147;y&#148;") == "I – a; II – b; ‘x’ “y”"
    assert normalizar_para_lxml("I &#150 a") == "I – a"  # sem ponto e vírgula, como o HTML5


def test_zeros_a_esquerda_sao_lidos_por_inteiro():
    assert normalizar_para_lxml("&#00000150; &#x0000096; &#0150;") == "– – –"


def test_referencia_longa_nunca_e_consumida_pela_metade():
    for ref in ("&#00001500;", "&#x0000960;", "&#1500;", "&#" + "9" * 5000 + ";", "&#x" + "f" * 5000 + ";"):
        assert normalizar_para_lxml(ref) == ref


def test_fora_da_faixa_ou_sem_mapeamento_fica_intacto():
    assert normalizar_para_lxml("&#160;&#127;&#129;&#8211;&amp;#150;") == "&#160;&#127;&#129;&#8211;&amp;#150;"


def test_fechamentos_inteiros_de_body_e_html_saem_so_entre_tags():
    assert (normalizar_para_lxml("<p>a</p></body></html><p>b</p></BODY ></HTML>")
            == "<p>a</p><!----><!----><p>b</p><!----><!---->")
    for intacto in ("</body", "</ body>", "</bodyx>", "</htmlx>"):
        assert normalizar_para_lxml("a" + intacto + "b") == "a" + intacto + "b"


def test_atributos_comentarios_e_conteudo_bruto_ficam_intactos():
    for trecho in ('<span style="text-decoration:line-</body>through">x</span>',
                   "<span title='&#150;'>x</span>",
                   "<!-- </body> &#150; -->",
                   "<![CDATA[ </html> &#150; ]]>",
                   "<script>var s = '</body>&#150;';</script>",
                   "<style>p:after{content:'&#150;'}</style>"):
        assert normalizar_para_lxml(trecho) == trecho


def test_remocao_nao_junta_fragmentos_em_marcacao_nova():
    assert normalizar_para_lxml("<</body>s>x") == "<<!---->s>x"


def test_fechamento_no_meio_do_paragrafo_segue_o_html5():
    # Leitura do HTML5 (html5lib, navegadores): `</body>` no meio do corpo não fecha o parágrafo nem o `<s>`, e o texto
    # continua. Sem a normalização, a libxml2 2.11 separa os nós ("n ão") e a 2.14 corta o resto ("n").
    _t, prov = _ler("<p>Art. 1o n</body>ão é permitido contratar.</p>")
    assert prov["art1"].redactions[-1].text == "não é permitido contratar."
    _t, prov = _ler("<p>Art. 1o O prazo é de 1</body>0 dias.</p>")
    assert prov["art1"].redactions[-1].text == "O prazo é de 10 dias."


def test_remocao_nao_fabrica_referencia_nem_texto():
    texto, prov = _ler("<p>Art. 1o n&ati</body>lde;o e permitido contratar &n</body>ot; aqui.</p>")
    vigente = prov["art1"].redactions[-1].text
    assert "não" not in vigente and "¬" not in vigente and "lde;o" in vigente


def test_limites_lexicos_seguem_os_da_libxml2():
    for prefixo in ("<!-->", "<!--->", "<script-x></script-x>", '<?x a=">', "<!DOCTYPE html>",
                    "<script>x</script x>", "<script>x</script/>", "<style>p{}</style x>"):
        texto, prov = _ler(prefixo + "<p>Art. 1o Compete:</p><p>I &#150; legislar.</p>")
        assert "art1.inc1" in prov and _sem_c1(texto), prefixo


def test_varredura_linear_em_entrada_adversarial():
    import time

    for unidade in ("<p ", "<!", "<?", "<p a=\"x", "<script ", "&#", "<!--x", "</body", "<script></script x"):
        inicio = time.perf_counter()
        normalizar_para_lxml(unidade * 40000)
        assert time.perf_counter() - inicio < 1.0, unidade


# --- efeito no parser ----------------------------------------------------------------------------------------

def test_inciso_com_travessao_em_referencia_numerica_e_reconhecido():
    texto, prov = _ler("<p>Art. 1o Compete:</p><p>I &#150; legislar;</p><p>II &#x0000096; julgar.</p>")
    assert "art1.inc1" in prov and "art1.inc2" in prov
    assert _sem_c1(texto)


def test_fechamento_solto_dentro_do_paragrafo_nao_corta_o_texto():
    # Estrutura da Lei 14.661/2023 no Planalto: <html>/<body> aninhados e fechamentos soltos dentro de <font>.
    texto, _ = _ler(
        "<p>Art. 1o Esta Lei entra em vigor na data de sua publicação.</p><p>Brasília, 1o de janeiro de 2023.</p>"
        "<p><font>Fulano de Tal</font></p>"
        '<p><html xmlns="http://www.w3.org/TR/REC-html40"><body><font>Este texto não substitui o publicado no DOU.'
        "</font></body></html></p>"
        '<p><span>&nbsp;</span><font></body></html></body></html>&nbsp; </font> <font color="#FF0000">*</font></p>')
    assert texto.rstrip().endswith("*")


def test_atributo_com_fechamento_nao_vira_texto_riscado():
    _texto, prov = _ler('<p>Art. 1o E <span style="text-decoration:line-</body>through">vedado</span> contratar.</p>')
    assert "vedado" in prov["art1"].redactions[-1].text


def test_cvm_html_normaliza_referencias():
    from freoa_verifica.connectors.cvm_normas import _html_tree

    arvore = _html_tree("<article><section class='contentArticle'><p>Ementa &#150; texto</p></section></article>")
    assert _sem_c1(arvore.text_content()) and "–" in arvore.text_content()
