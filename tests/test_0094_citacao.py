"""0094, achados 3 e 4 do colega: data da Constituição e complemento de dispositivo depois da norma."""
from __future__ import annotations

import pytest

from freoa_verifica.citation import extract


def _uma(texto):
    cs = [c for c in extract(texto) if c.path]
    assert len(cs) == 1, cs
    return cs[0]


@pytest.mark.parametrize("texto", [
    "art. 5º da CF/88, § 2º", "art. 5º da CF/88, inciso II", "art. 5º da CF/88, inc. II", "art. 5º da CF/88, II",
    "art. 5º da CF/88 inc. II", "art. 5º da CF/88 ou do ADCT?", "art. 5º da CF/88, ou do ADCT?",
    "art. 5º da CF/88 (ou da CF/67)?", "art. 5º da CF/88, al. a", "art. 5º da CF/88, a)", "art. 5º da CF/1988, II",
    "art. 5º da Constituição Federal de 1988, § 2º", "art. 5º da CF, § 2º", "art. 5º da CF, inc. II",
    "art. 5º da CF, II", "art. 5º da Lei 6.404/1976, § 2º",
])
def test_complemento_de_dispositivo_ou_alternativa_nao_confirma_o_artigo(texto):
    c = _uma(texto)
    assert c.path == "art5" and c.confidence == "provavel"
    assert "complemento_de_dispositivo_apos_a_norma" in c.flags


@pytest.mark.parametrize("texto,caminho", [
    ("art. 5º da CF", "art5"), ("CF/88, art. 5º", "art5"), ("art. 5º da CF/88.", "art5"), ("(art. 5º da CF/88)", "art5"),
    ("art. 5º da CF/88, caput", "art5"), ("CF/88, art. 5º, § 2º", "art5.par2"),
    ("art. 5º da Constituição de 1988, fundamento do Estado Democrático de Direito", "art5"),
    ("nos termos do art. 5º da Lei 6.404/1976, e do art. 2º", "art5"),
])
def test_formas_sem_complemento_continuam_exatas(texto, caminho):
    c = _uma(texto)
    assert c.path == caminho and c.confidence == "exata"


@pytest.mark.parametrize("texto,esperado", [
    ("Constituição Federal de 31 de outubro de 1988, art. 5º", "provavel"),
    ("Constituição Federal de 25 de outubro de 1988, art. 5º", "provavel"),
    ("Constituição Federal de 5 de outubro de 1988, art. 5º", "exata"),
    ("art. 5º da Constituição Federal de 05 de outubro de 1988", "exata"),
    ("art. 5º da Constituição Federal de 1988", "exata"),
])
def test_data_da_promulgacao(texto, esperado):
    c = _uma(texto)
    assert c.confidence == esperado
    assert ("constituicao_data_divergente" in c.flags) is (esperado == "provavel")
