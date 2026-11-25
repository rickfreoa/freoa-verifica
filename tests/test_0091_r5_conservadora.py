"""0091, regra conservadora (titular, após a conferência r5): classes 14, 18 e 20 fechadas por regra de classe."""
from __future__ import annotations

import pytest

from freoa_verifica.citation import parse_one
from tests.test_0091_r4_parser import _doc, _fronteiras, _nao_confirma, _svc
from tests.test_0091_cf_entrega import _ORFA


@pytest.mark.parametrize("orfa", ["Art. 45 Da referida Lei no 2.004", "Art. 45 Da citada Lei", "Art. 45 Da mencionada Lei",
                                  "Art. 45 Da presente Lei", "Art. 45 Do art. 3", "Art. 45 DESSE DECRETO"])
def test_r5_remissao_com_determinante_bloqueia(tmp_path, orfa):
    html, doc = _doc("<p>Art. 1 Fica previsto no</p>" + _ORFA.format(orfa) + "<p>§ 1 Outro.</p><p>Art. 2 Fim.</p>")
    assert "art45" not in {p.path for p in doc.provisions} and _fronteiras(doc) == ["art1"]
    svc = _svc(tmp_path, html, doc)
    assert _nao_confirma(svc.verificar_citacao("art. 45, § 1 da Lei 9.999/2000", trecho="Outro."))
    assert _nao_confirma(svc.verificar_citacao("art. 1, § 1 da Lei 9.999/2000", trecho="Outro."))


@pytest.mark.parametrize("caput", ["Art. 62. Em caso de relevância, cabe medida.", "Art. 62 A propriedade é livre.",
                                   "Art. 62 Ao Presidente compete decidir.", "Art. 62 Nos casos previstos, decide."])
def test_r5_caput_com_preposicao_e_substantivo_comum_continua_admitido(caput):
    _, doc = _doc("<p>Art. 61 Antes.</p>" + _ORFA.format(caput) + "<p>§ 1 Outro.</p><p>Art. 63 Depois.</p>")
    assert {p.path: p.redactions[-1].text for p in doc.provisions}.get("art62.par1") == "Outro." and not _fronteiras(doc)


@pytest.mark.parametrize("texto", [
    "art. 5 da Constituição, a do Estado de São Paulo",
    "art. 5 da Constituição, isto é, a do Estado de Minas Gerais",
    "art. 5 da Constituição e Emendas Constitucionais do Estado de São Paulo",
    "art. 5 da Constituição e respectivas emendas do Estado de Minas Gerais",
    "art. 5 da Constituição de 1988 e o contrato do Estado de São Paulo segue outra regra",
    "art. 5 da Constituição Federal e a Lei Orgânica Municipal",
])
def test_r5_qualificador_territorial_na_frase_nunca_e_exata(texto):
    c = parse_one(texto)
    assert c is None or (c.confidence == "provavel" and "constituicao_qualificador_territorial_na_frase" in c.flags)


@pytest.mark.parametrize("texto", ["art. 5 da Constituição Federal", "art. 5 da Constituição de 1988.",
                                   "art. 5 da Constituição de 1988. O Estado de São Paulo segue outra regra."])
def test_r5_federal_sem_qualificador_na_frase_continua_exata(texto):
    c = parse_one(texto)
    assert c is not None and c.work.number == "1988" and c.confidence == "exata"


def test_r5_verificacao_com_qualificador_na_frase_requer_conferencia(tmp_path):
    """Com qualificador territorial na frase, a verificação não conclui: requer conferência."""
    from freoa_verifica.service import Verifica
    svc = Verifica(home=tmp_path)
    res = svc.verificar_citacao("art. 5 da Constituição e Emendas Constitucionais do Estado de São Paulo", trecho="x")
    assert _nao_confirma(res)


# ------------------------------------------------------------------ conferência r6


@pytest.mark.parametrize("orfa", ["Art. 45 Da supramencionada Lei", "Art. 45 Da sobredita Lei", "Art. 45 I, da Lei",
                                  "Art. 45 Rege o caso."])
def test_r6_artigo_orfao_fora_da_sequencia_bloqueia(tmp_path, orfa):
    """Critério estrutural: artigo órfão que não continua a numeração (N+1 ou N-A) vira fronteira, qualquer redação."""
    html, doc = _doc("<p>Art. 1 Fica previsto no</p>" + _ORFA.format(orfa) + "<p>§ 1 Outro.</p><p>Art. 3 Fim.</p>")
    assert "art45" not in {p.path for p in doc.provisions} and _fronteiras(doc) == ["art1"]
    svc = _svc(tmp_path, html, doc)
    assert _nao_confirma(svc.verificar_citacao("art. 45, § 1 da Lei 9.999/2000", trecho="Outro."))
    assert _nao_confirma(svc.verificar_citacao("art. 1, § 1 da Lei 9.999/2000", trecho="Outro."))


def test_r6_artigo_orfao_com_letra_na_sequencia_e_admitido():
    _, doc = _doc("<p>Art. 5 Antes.</p>" + _ORFA.format("Art. 5-A Novo artigo.") + "<p>§ 1 Outro.</p><p>Art. 6 Depois.</p>")
    assert not _fronteiras(doc)


@pytest.mark.parametrize("texto", [
    "art. 5 da CF, a do Estado de São Paulo",
    "art. 5 da Constituição Federal de 1988 e o contrato do Estado de São Paulo",
])
def test_r6_guarda_territorial_vale_para_apelido_e_forma_qualificada(texto):
    c = parse_one(texto)
    assert c.confidence == "provavel" and "constituicao_qualificador_territorial_na_frase" in c.flags


def test_r6_estado_democratico_nao_e_qualificador_territorial():
    c = parse_one("art. 5 da Constituição de 1988, fundamento do Estado Democrático de Direito")
    assert c.confidence == "exata"


@pytest.mark.parametrize("texto", [
    "art. 5 da Constituição",
    "art. 5 da Constituição bandeirante",
    "art. 5 da Constituição e Emendas Constitucionais; ambas do Estado de São Paulo",
    "Da Constituição do Estado de São Paulo: consulte o art. 5 da Constituição",
    "art. 5 da Constituição. Trata-se da do Estado de São Paulo.",
])
def test_r6_constituicao_sem_qualificacao_federal_requer_conferencia(texto):
    """Titular, após a r6: exata só quando o texto nomeia a Federal (Federal, da República, do Brasil, ano, CF/CRFB/CR)."""
    c = parse_one(texto)
    assert c is None or c.confidence == "provavel"


@pytest.mark.parametrize("texto", ["art. 5 da Constituição Federal", "art. 5 da Constituição da República",
                                   "art. 5 da Constituição de 1988", "art. 5 da CF/88", "art. 5 da CRFB/88",
                                   "Constituição Federal de 1988, art. 5º"])
def test_r6_constituicao_qualificada_continua_exata(texto):
    c = parse_one(texto)
    assert c is not None and c.work.number == "1988" and c.confidence == "exata"


# ------------------------------------------------------------------ conferência r7 (titular: guarda no texto inteiro)


@pytest.mark.parametrize("texto", [
    "Da Constituição Estadual: consulte o art. 5 da CF",
    "Da Constituição do Estado de São Paulo: consulte o art. 5 da Constituição Federal",
    "art. 5 da Constituição Federal, leia-se CE/SP",
    "art. 5 da Constituição Federal, leia-se a Lei Orgânica de São Paulo",
    "art. 5 da Constituição de 1988 e respectivas emendas, todas da CE/SP",
    "art. 5 da CF, a Estadual",
])
def test_r7_marca_de_ente_em_qualquer_ponto_do_texto_impede_exata(texto):
    c = parse_one(texto)
    assert c is None or c.confidence == "provavel"


@pytest.mark.parametrize("texto", [
    "art. 5 da Constituição Federal; compete à União, aos Estados, ao Distrito Federal e aos Municípios",
    "art. 5 da Constituição Federal, perante a Justiça Estadual",
    "art. 5 da Constituição de 1988, fundamento do Estado Democrático de Direito",
])
def test_r7_federacao_em_geral_nao_rebaixa(texto):
    assert parse_one(texto).confidence == "exata"


def test_r7_adct_reinicia_a_numeracao():
    _, doc = _doc("<p>Art. 250 Último.</p><p>ATO DAS DISPOSIÇÕES CONSTITUCIONAIS TRANSITÓRIAS</p>"
                  + _ORFA.format("Art. 1 Primeiro do ADCT.") + "<p>§ 1 Outro.</p><p>Art. 2 Segundo.</p>")
    assert not _fronteiras(doc)
