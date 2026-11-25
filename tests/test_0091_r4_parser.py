"""0091, rodada 4 (achados 2, 14 e 15 da auditoria r3): fonte órfã ambígua bloqueia a região, nunca vira dispositivo."""
from __future__ import annotations

import pytest

from freoa_verifica.parsers.planalto import parse_planalto
from freoa_verifica.service import Verifica
from tests.test_0091_cf_entrega import KEY, T0, _ORFA, _html

URL = "https://example.invalid/l9999.htm"


def _doc(corpo: str):
    html = _html(corpo)
    return html, parse_planalto(html, base_url=URL)


def _svc(tmp_path, html, doc) -> Verifica:
    svc = Verifica(home=tmp_path)
    svc.indexar_obra(source_id="planalto", work_key=KEY, document=doc, body=html, url=URL,
                     label="Lei 9.999/2000", fetched_at=T0, content_type="text/html; charset=utf-8")
    return svc


def _fronteiras(doc) -> list:
    return [i.path for i in doc.issues if i.code == "DISPOSITIVO_FORA_DA_ARVORE"]


def _nao_confirma(res) -> bool:
    return not (res["identity"]["status"] == "verified" and res["text"]["status"] == "verified")


@pytest.mark.parametrize("orfa", [
    "Art. 45 da Lei no 2.004, de 3 de outubro de 1953",
    "Art. 45 desta Lei",
    "Art. 45 rege o caso.",
    "Art. 45 Da Lei no 2.004, de 3 de outubro de 1953",
    "Art. 45 Desta Lei",
    "Art. 45 DA LEI No 2.004",
])
def test_r4_remissao_em_fonte_orfa_bloqueia_e_nao_vira_artigo(tmp_path, orfa):
    """Achado 14: "Art. N" seguido de minúscula é remissão partida pelo markup ou caput ambíguo: fronteira, sem artigo."""
    html, doc = _doc("<p>Art. 1 Fica previsto no</p>" + _ORFA.format(orfa) + "<p>§ 1 Outro.</p><p>Art. 2 Fim.</p>")
    caminhos = {p.path for p in doc.provisions}
    assert "art45" not in caminhos and "art45.par1" not in caminhos
    assert _fronteiras(doc) == ["art1"]
    svc = _svc(tmp_path, html, doc)
    assert _nao_confirma(svc.verificar_citacao("art. 45, § 1 da Lei 9.999/2000", trecho="Outro."))
    assert _nao_confirma(svc.verificar_citacao("art. 45 da Lei 9.999/2000", trecho=orfa[8:]))
    assert _nao_confirma(svc.verificar_citacao("art. 1, § 1 da Lei 9.999/2000", trecho="Outro."))
    assert "art2" in caminhos  # o artigo seguinte continua no modelo


@pytest.mark.parametrize("aspas", ["“", '"'])
def test_r4_abertura_citada_orfa_controla_a_citacao_como_o_p(tmp_path, aspas):
    """Achado 15: abertura citada órfã depois de "...redação:" entra na máquina de citação, como o <p>."""
    cauda = "<p>§ 1 Outro.” (NR)</p><p>Art. 3 Fim.</p>"
    host = "<p>Art. 1 O art. 2 da Lei n. 1 passa a vigorar com a seguinte redação:</p>"
    html, doc = _doc(host + _ORFA.format(aspas + "Art. 2 Novo texto:") + _ORFA.format("I - julgar;") + cauda)
    _, doc_p = _doc(host + f"<p>{aspas}Art. 2 Novo texto:</p><p>I - julgar;</p>" + cauda)
    assert {p.path for p in doc.provisions} == {p.path for p in doc_p.provisions}
    assert "art1.inc1" not in {p.path for p in doc.provisions}
    assert len(doc.amendments) == len(doc_p.amendments) == 1
    svc = _svc(tmp_path, html, doc)
    assert _nao_confirma(svc.verificar_citacao("art. 1, I da Lei 9.999/2000", trecho="julgar;"))


def test_r4_abertura_citada_orfa_sem_introducao_bloqueia(tmp_path):
    """Achado 15, variante: sem o texto que introduz a citação, a ordem é incerta; fronteira em vez de atribuição."""
    html, doc = _doc("<p>Art. 1 Diz algo.</p>" + _ORFA.format("“Art. 2 Novo texto:") + _ORFA.format("I - julgar;")
                     + "<p>Art. 3 Fim.</p>")
    assert _fronteiras(doc) == ["art1"]
    svc = _svc(tmp_path, html, doc)
    assert _nao_confirma(svc.verificar_citacao("art. 1, I da Lei 9.999/2000", trecho="julgar;"))


@pytest.mark.parametrize("composta", ["1. julgar; 2. processar.", "1. julgar. 2. processar.", "1) julgar; 2) processar."])
def test_r4_itens_numericos_compostos_em_fonte_orfa_bloqueiam(tmp_path, composta):
    """Achado 2: itens numéricos na mesma fonte órfã são fonte composta; nenhum item confirma o conteúdo combinado."""
    html, doc = _doc("<p>Art. 1 Compete:</p>" + _ORFA.format(composta) + "<p>Art. 3 Fim.</p>")
    assert _fronteiras(doc) == ["art1"]
    svc = _svc(tmp_path, html, doc)
    assert _nao_confirma(svc.verificar_citacao("art. 1, item 1 da Lei 9.999/2000", trecho=composta[3:]))


def test_r4_artigo_com_ponto_apos_o_numero_nao_e_composto():
    """Falso positivo medido na CF (arts. 52, 57, 62, 126, 222): "Art. 57. O ..." não é item numérico."""
    _, doc = _doc("<p>Art. 56 Antes.</p>" + _ORFA.format("Art. 57. O Congresso Nacional reunir-se-á, anualmente.")
                  + "<p>§ 1 Outro.</p><p>Art. 58 Depois.</p>")
    caminhos = {p.path: p.redactions[-1].text for p in doc.provisions}
    assert caminhos.get("art57.par1") == "Outro." and not _fronteiras(doc)


@pytest.mark.parametrize("intro", ["Art. 1 Compete:", "Art. 1 São exemplos:", "Art. 1 O total devido é:"])
def test_r4_abertura_citada_apos_dois_pontos_genericos_bloqueia(tmp_path, intro):
    """r4, achado 17: dois-pontos sem a introdução que a máquina de emendas reconhece não admitem a abertura citada."""
    html, doc = _doc(f"<p>{intro}</p>" + _ORFA.format("“Art. 2 Novo texto:") + _ORFA.format("I - julgar;")
                     + "<p>§ 1 Outro.” (NR)</p><p>Art. 3 Fim.</p>")
    caminhos = {p.path for p in doc.provisions}
    assert "art2" not in caminhos and "art2.inc1" not in caminhos
    assert _fronteiras(doc) == ["art1"]
    svc = _svc(tmp_path, html, doc)
    assert _nao_confirma(svc.verificar_citacao("art. 2, I da Lei 9.999/2000", trecho="julgar;"))
    assert _nao_confirma(svc.verificar_citacao("art. 1, I da Lei 9.999/2000", trecho="julgar;"))


@pytest.mark.parametrize("caput", ["Art. 62. Em caso de relevância e urgência, cabe medida.", "Art. 62 Da decisão caberá recurso.",
                                   "Art. 62 No prazo de dez dias, decide."])
def test_r4_caput_que_comeca_por_preposicao_nao_e_remissao(caput):
    """Falso positivo medido na CF (art. 62): preposição só indica remissão seguida de nome de ato."""
    _, doc = _doc("<p>Art. 61 Antes.</p>" + _ORFA.format(caput) + "<p>§ 1 Outro.</p><p>Art. 63 Depois.</p>")
    caminhos = {p.path: p.redactions[-1].text for p in doc.provisions}
    assert caminhos.get("art62.par1") == "Outro." and not _fronteiras(doc)
