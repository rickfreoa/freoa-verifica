"""0094, achados 1, 2, 6, 7, 8 e 9 do colega: marcas defensivas do parser 1.2.5.

Nenhuma delas cria caminho nem move texto: o dispositivo afetado deixa de ser confirmado (`unknown`) e a negativa
fica bloqueada onde o dispositivo existe na fonte."""
from __future__ import annotations

from pathlib import Path

import pytest

from freoa_verifica.parsers.planalto import parse_planalto
from freoa_verifica.service import Verifica
from tests.test_0091_cf_entrega import _ORFA, KEY, T0, _html

URL = "https://example.invalid/l9999.htm"
CIT = "Lei 9.999/2000"


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")


def _svc(tmp_path, corpo: str, url: str = URL) -> tuple[Verifica, object]:
    html = _html(corpo)
    doc = parse_planalto(html, base_url=url)
    svc = Verifica(home=tmp_path)
    svc.indexar_obra(source_id="planalto", work_key=KEY, document=doc, body=html, url=url, label=CIT, fetched_at=T0,
                     content_type="text/html; charset=utf-8")
    return svc, doc


def _codigos(doc, codigo):
    return {i.path for i in doc.issues if i.code == codigo}


# --- achados 2, 6 e 9: inciso sem travessão ------------------------------------------------------------------------

@pytest.mark.parametrize("rotulo", ["II processar", "II) processar", "II. processar"])
@pytest.mark.parametrize("forma", ["p", "orfa"])
def test_inciso_sem_travessao_nao_e_anexado_ao_anterior(tmp_path, rotulo, forma):
    bloco = f"{rotulo} e julgar os Ministros;"
    corpo = ("<p>Art. 1 Compete ao Senado:</p><p>I - processar e julgar o Presidente;</p>"
             + (f"<p>{bloco}</p>" if forma == "p" else _ORFA.format(bloco))
             + "<p>a) elaborar propostas.</p><p>Art. 2 Fim.</p><p>Art. 3 Vigência.</p>")
    svc, doc = _svc(tmp_path, corpo)
    assert _codigos(doc, "ROTULO_SEM_SEPARADOR") == {"art1.inc1"}
    por = {p.path: p for p in doc.provisions}
    assert "Ministros" not in por["art1.inc1"].redactions[-1].text  # nada movido para o inciso I
    for citacao, trecho in [("art. 1, I", "processar e julgar os Ministros"), ("art. 1, I", "processar e julgar o Presidente"),
                            ("art. 1, I, a", "elaborar propostas.")]:
        v = svc.verificar_citacao(f"{citacao}, da {CIT}", trecho=trecho)
        assert v["text"]["status"] != "verified", (citacao, v["text"])
    neg = svc.verificar_citacao(f"art. 1, II, da {CIT}", trecho="processar e julgar os Ministros")
    assert neg["identity"]["status"] != "not_found"  # o inciso existe na fonte
    ok = svc.verificar_citacao(f"art. 2 da {CIT}", trecho="Fim.")
    assert ok["text"]["status"] == "verified"  # outro artigo segue confirmável


@pytest.mark.parametrize("texto", ["V. Exa. decidirá.", "Integra o sistema.", "III Congresso"])
def test_prosa_sem_numeral_romano_isolado_nao_marca(texto):
    doc = parse_planalto(_html(f"<p>Art. 1 Cabe:</p><p>I - fazer;</p><p>{texto}</p>"), base_url=URL)
    # "V. Exa." e "III Congresso" casam o padrão: a marca é deliberadamente conservadora (só bloqueia confirmação).
    marcado = bool(_codigos(doc, "ROTULO_SEM_SEPARADOR"))
    assert marcado is (texto.split()[0].rstrip(".") in {"V", "III"})


# --- achado 7: artigo de outro ato dentro de link -----------------------------------------------------------------

LINK = ("<p>Art. 1 Fica acrescido à Lei nº 9, de 2000, o seguinte dispositivo, nos termos abaixo:</p>"
        + _ORFA.format('<a href="{href}">Art. 2. Cabe recurso imediato.</a>')
        + "<p>Art. 3 Esta Lei entra em vigor na data de sua publicação.</p>")


def test_artigo_inteiro_em_link_de_outro_ato_nao_vira_artigo_da_obra(tmp_path):
    svc, doc = _svc(tmp_path, LINK.format(href="l9.htm#art2"))
    assert "art2" not in {p.path for p in doc.provisions}
    assert _codigos(doc, "DISPOSITIVO_FORA_DA_ARVORE") == {"art1"}
    v = svc.verificar_citacao(f"art. 2º da {CIT}", trecho="Cabe recurso imediato.")
    assert v["text"]["status"] != "verified" and v["identity"]["status"] != "not_found"


@pytest.mark.parametrize("href", ["#art2", "l9999.htm#art2", "https://example.invalid/l9999.htm#art2"])
def test_ancora_da_propria_obra_continua_artigo(href):
    doc = parse_planalto(_html(LINK.format(href=href)), base_url=URL)
    assert "art2" in {p.path for p in doc.provisions}
    assert not _codigos(doc, "DISPOSITIVO_FORA_DA_ARVORE")


# --- achado 1: redação viva vazia depois de riscada ----------------------------------------------------------------

A1 = ('<p><a name="art1"></a>Art. 1º Texto do artigo:</p><p><a name="art1§1"></a>§ 1º Contém:</p>'
      '<p><a name="art1§1a"></a>a) primeira alínea;</p><p><strike><a name="art1§1b.0"></a>b) redação antiga;</strike></p>'
      '<p><a name="art1§1b"></a> &nbsp;b) </font><small><font face="Arial">redação nova da alínea;</font></small>'
      '<font face="Arial" size="2">&nbsp;&nbsp; <a href="L9457.htm#art1">(Redação dada pela Lei nº 9.457, de 1997)</a></p>'
      '<p><a name="art1§1c"></a>c) terceira alínea.</p><p>Art. 2 Vigência.</p>')


def test_redacao_viva_vazia_depois_de_riscada_nao_e_servida(tmp_path):
    svc, doc = _svc(tmp_path, A1)
    assert _codigos(doc, "REDACAO_VIVA_VAZIA") == {"art1.par1.ali-b"}
    for trecho in ("redação nova da alínea;", "redação antiga;"):
        v = svc.verificar_citacao(f"art. 1, § 1º, b, da {CIT}", trecho=trecho)
        assert v["text"]["status"] == "unknown" and v["text"]["reason_code"] == "REDACAO_VIVA_VAZIA"
    assert svc.verificar_citacao(f"art. 1, § 1º, c, da {CIT}", trecho="terceira alínea.")["text"]["status"] == "verified"


@pytest.mark.parametrize("nota", ["(Revogado pela Lei n. 1, de 2001)", "(VETADO)"])
def test_vazio_com_nota_de_revogacao_ou_veto_nao_marca(nota):
    corpo = (f"<p>Art. 1 Cabe:</p><p><strike>I - antigo;</strike></p><p>I - {nota}</p><p>II - outro.</p>")
    doc = parse_planalto(_html(corpo), base_url=URL)
    assert not _codigos(doc, "REDACAO_VIVA_VAZIA")


def test_lei_6404_real_marca_as_18_provisoes_com_texto_perdido():
    doc = parse_planalto(Path("tests/fixtures/planalto_lei_6404_1976.html").read_bytes(),
                         base_url="https://www.planalto.gov.br/ccivil_03/leis/l6404consol.htm")
    marcadas = _codigos(doc, "REDACAO_VIVA_VAZIA")
    assert len(marcadas) == 18
    assert {"art72.par2.ali-c", "art72.par2.ali-g", "art72.par2.ali-j", "art256.inc2.ali-a", "art39"} <= marcadas


# --- achado 8: nota editorial truncada ----------------------------------------------------------------------------

def test_nota_editorial_truncada_nao_e_confirmada(tmp_path):
    corpo = ("<p>Art. 1 Cabe:</p><p>V - fiscalização financeira da administração pública direta e indireta; "
             "(Redação dada pela Emenda Constitucional no 40, de 2</p><p>VI - outro.</p>")
    svc, doc = _svc(tmp_path, corpo)
    assert _codigos(doc, "NOTA_EDITORIAL_TRUNCADA") == {"art1.inc5"}
    v = svc.verificar_citacao(f"art. 1, V, da {CIT}", trecho="Redação dada pela Emenda Constitucional no 40, de 2")
    assert v["text"]["status"] != "verified"


def test_nota_completa_sem_parentese_final_nao_marca():
    corpo = "<p>Art. 1 Cabe:</p><p>I - registrar o título. (Redação dada pela Lei no 13.986, de 2020</p><p>II - outro.</p>"
    doc = parse_planalto(_html(corpo), base_url=URL)
    assert not _codigos(doc, "NOTA_EDITORIAL_TRUNCADA")


@pytest.mark.parametrize("fim", ["(Vigência", "(Redação dada pela Emenda Constitucional no 40, de 2",
                                 "(Incluído pela Lei nº 9.457, de 5 de"])
def test_nota_cortada_no_meio_marca(fim):
    corpo = f"<p>Art. 1 Cabe:</p><p>I - registrar o título. {fim}</p><p>II - outro.</p>"
    doc = parse_planalto(_html(corpo), base_url=URL)
    assert _codigos(doc, "NOTA_EDITORIAL_TRUNCADA") == {"art1.inc1"}


# --- Codex 0094, rodada 1 -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("bloco", [
    "<div>II processar Ministros;</div>",
    "<span>II processar Ministros;</span>",
    "<div>II - processar Ministros;</div>",
])
def test_r1_inciso_fora_de_p_marca_e_bloqueia(tmp_path, bloco):
    corpo = ("<p>Art. 1 Cabe:</p><p>I - julgar Presidente;</p>" + bloco
             + "<p>a) elaborar propostas.</p><p>Art. 2 Fim.</p><p>Art. 3 Vigência.</p>")
    svc, doc = _svc(tmp_path, corpo)
    assert _codigos(doc, "ROTULO_SEM_SEPARADOR") == {"art1.inc1"}
    assert svc.verificar_citacao(f"art. 1, I, a, da {CIT}", trecho="elaborar propostas.")["text"]["status"] != "verified"
    assert svc.verificar_citacao(f"art. 1, II, da {CIT}", trecho="processar")["identity"]["status"] != "not_found"


@pytest.mark.parametrize("forma", ["p", "orfa"])
def test_r1_inciso_depois_de_br_no_mesmo_bloco(tmp_path, forma):
    bloco = "I - julgar Presidente;<br>II processar Ministros;"
    corpo = ("<p>Art. 1 Cabe:</p>" + (f"<p>{bloco}</p>" if forma == "p" else _ORFA.format(bloco))
             + "<p>a) elaborar propostas.</p><p>Art. 2 Fim.</p><p>Art. 3 Vigência.</p>")
    svc, doc = _svc(tmp_path, corpo)
    assert "art1.inc1" in _codigos(doc, "ROTULO_SEM_SEPARADOR")
    for trecho in ("processar Ministros", "elaborar propostas."):
        for cit in ("art. 1, I", "art. 1, I, a"):
            assert svc.verificar_citacao(f"{cit}, da {CIT}", trecho=trecho)["text"]["status"] != "verified"


def test_r1_quebra_no_meio_da_frase_nao_marca():
    corpo = "<p>Art. 1 Cabe:</p><p>I - aplicar o disposto no inciso<br>II do § 2º deste artigo;</p><p>II - outro.</p>"
    assert not _codigos(parse_planalto(_html(corpo), base_url=URL), "ROTULO_SEM_SEPARADOR")


def test_r1_dois_pontos_depois_do_numeral_bloqueia_negativa(tmp_path):
    corpo = ("<p>Art. 1 Cabe:</p><p>I - julgar Presidente;</p><p>II: processar Ministros;</p>"
             "<p>Art. 2 Fim.</p><p>Art. 3 Vigência.</p>")
    svc, doc = _svc(tmp_path, corpo)
    assert _codigos(doc, "ROTULO_SEM_SEPARADOR") == {"art1.inc1"}
    assert svc.verificar_citacao(f"art. 1, II, da {CIT}", trecho="processar Ministros")["identity"]["status"] != "not_found"


@pytest.mark.parametrize("href", ["../outro/l9999.htm#art2", "https://outro.invalid/l9999.htm#art2",
                                  "https://example.invalid/outra/l9999.htm#art2"])
def test_r1_mesmo_nome_de_arquivo_em_outro_endereco_e_outro_ato(tmp_path, href):
    svc, doc = _svc(tmp_path, LINK.format(href=href), url="https://example.invalid/leis/l9999.htm")
    assert "art2" not in {p.path for p in doc.provisions}
    assert svc.verificar_citacao(f"art. 2 da {CIT}", trecho="Cabe recurso imediato.")["text"]["status"] != "verified"


def test_r1_sem_url_da_obra_so_fragmento_e_proprio():
    assert "art2" in {p.path for p in parse_planalto(_html(LINK.format(href="#art2")), base_url=None).provisions}
    assert "art2" not in {p.path for p in parse_planalto(_html(LINK.format(href="l9999.htm#art2")),
                                                          base_url=None).provisions}
