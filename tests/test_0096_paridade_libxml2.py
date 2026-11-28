"""0096: o parser lê o HTML do Planalto do mesmo modo em qualquer libxml2.

As wheels da lxml trazem libxml2 2.11 no Windows e 2.14 no Linux; as duas divergiam em referências numéricas de 128
a 159 (`&#150;`) e em `</body></html>` soltos no meio da página. Os casos abaixo falham, sem a normalização, na libxml2
que diverge do HTML5 (a do Windows), e o teste de normalização fixa o contrato independentemente da plataforma.
"""

from freoa_verifica.parsers.html_devices import parse_html_devices
from freoa_verifica.parsers.html_paridade import normalizar_para_lxml


def test_referencias_de_128_a_159_viram_o_caractere_do_html5():
    assert normalizar_para_lxml("I &#150; a; II &#x96; b; &#145;x&#146; &#147;y&#148;") == "I – a; II – b; ‘x’ “y”"
    assert normalizar_para_lxml("I &#150 a") == "I – a"  # sem ponto e vírgula, como o HTML5


def test_fora_da_faixa_ou_sem_mapeamento_fica_intacto():
    assert normalizar_para_lxml("&#160;&#127;&#129;&#8211;&amp;#150;") == "&#160;&#127;&#129;&#8211;&amp;#150;"


def test_fechamentos_soltos_de_body_e_html_saem():
    html = "<p>a</p></body></html><p>b</p></BODY ></HTML>"
    assert normalizar_para_lxml(html) == "<p>a</p><p>b</p>"


def _ler(corpo: str):
    _titulo, _ementa, texto, provisions, *_ = parse_html_devices(
        "<html><head></head><body>" + corpo + "</body></html>", base_url="https://www.planalto.gov.br/ccivil_03/leis/l0001.htm")
    return texto, [p.path for p in provisions]


def test_inciso_com_travessao_em_referencia_numerica_e_reconhecido():
    texto, caminhos = _ler("<p>Art. 1o Compete:</p><p>I &#150; legislar;</p><p>II &#150; julgar.</p>")
    assert "art1.inc1" in caminhos and "art1.inc2" in caminhos
    assert not any("\x80" <= ch <= "\x9f" for ch in texto)


def test_texto_apos_fechamento_solto_e_lido():
    texto, caminhos = _ler("<p>Art. 1o Esta Lei entra em vigor na data de sua publicação.</p></body></html>"
                           "<p>Art. 2o Revogam-se as disposições em contrário.</p>")
    assert "art1" in caminhos and "art2" in caminhos and "Revogam-se" in texto
