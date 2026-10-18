"""Extrator de citações — ≥60 positivos e ≥15 negativos."""

from __future__ import annotations

import pytest

from freoa_verifica.aliases import WorkKey
from freoa_verifica.citation import extract, parse_one, validate_cnj_dv


def _norma(text: str):
    c = parse_one(text)
    assert c is not None, text
    assert c.kind == "norma", (text, c)
    return c


def _work(c) -> WorkKey:
    assert c.work is not None
    return c.work


# ---------------------------------------------------------------------------
# Positivos — leis e formas
# ---------------------------------------------------------------------------

POSITIVE_NORMS = [
    ("Lei nº 6.404/1976", WorkKey("federal", "lei", "6404", 1976), None),
    ("Lei 6.404/76", WorkKey("federal", "lei", "6404", 1976), None),
    (
        "Lei nº 6.404, de 15 de dezembro de 1976",
        WorkKey("federal", "lei", "6404", 1976),
        None,
    ),
    ("LC 123/2006", WorkKey("federal", "lei_complementar", "123", 2006), None),
    ("Lei Complementar nº 123", WorkKey("federal", "lei_complementar", "123", 0), None),
    ("Decreto-Lei 5.452/1943", WorkKey("federal", "decreto_lei", "5452", 1943), None),
    ("MP 2.200-2/2001", WorkKey("federal", "medida_provisoria", "2200-2", 2001), None),
    ("Decreto nº 10.000/2019", WorkKey("federal", "decreto", "10000", 2019), None),
    ("CF/88", WorkKey("federal", "constituicao", "1988", 1988), None),
    ("art. 5º da Constituição", WorkKey("federal", "constituicao", "1988", 1988), "art5"),
    ("Resolução CVM nº 160", WorkKey("cvm", "resolucao", "160", 0), None),
    ("RCVM 160", WorkKey("cvm", "resolucao", "160", 0), None),
    ("Res. CVM 44/2021", WorkKey("cvm", "resolucao", "44", 2021), None),
    ("Instrução CVM 400", WorkKey("cvm", "instrucao", "400", 0), None),
    ("ICVM 400", WorkKey("cvm", "instrucao", "400", 0), None),
    ("Parecer de Orientação CVM nº 35", WorkKey("cvm", "parecer_orientacao", "35", 0), None),
    ("PO CVM 35", WorkKey("cvm", "parecer_orientacao", "35", 0), None),
    ("Ofício-Circular CVM/SEP nº 1/2024", WorkKey("cvm", "oficio_circular", "1", 2024), None),
    ("Resolução CMN nº 4.966", WorkKey("cmn", "resolucao", "4966", 0), None),
    ("Res. CMN 4966", WorkKey("cmn", "resolucao", "4966", 0), None),
    ("Resolução BCB nº 1", WorkKey("bcb", "resolucao_bcb", "1", 0), None),
    ("Circular nº 3.978", WorkKey("bcb", "circular", "3978", 0), None),
]


@pytest.mark.parametrize("text,work,path", POSITIVE_NORMS)
def test_positive_norms(text, work, path):
    c = _norma(text)
    w = _work(c)
    assert w.authority == work.authority
    assert w.kind == work.kind
    assert w.number == work.number
    if work.year != 0:
        assert w.year == work.year
    if path:
        assert c.path == path


# Apelidos
ALIASES = [
    ("LSA", WorkKey("federal", "lei", "6404", 1976)),
    ("Lei das S.A.", WorkKey("federal", "lei", "6404", 1976)),
    ("Lei das Sociedades por Ações", WorkKey("federal", "lei", "6404", 1976)),
    ("Lei do Mercado de Capitais", WorkKey("federal", "lei", "6385", 1976)),
    ("Lei da CVM", WorkKey("federal", "lei", "6385", 1976)),
    ("Código Civil", WorkKey("federal", "lei", "10406", 2002)),
    ("art. 1º do CC", WorkKey("federal", "lei", "10406", 2002)),
    ("CPC", WorkKey("federal", "lei", "13105", 2015)),
    ("Código de Processo Civil", WorkKey("federal", "lei", "13105", 2015)),
    ("CDC", WorkKey("federal", "lei", "8078", 1990)),
    ("Lei de Falências", WorkKey("federal", "lei", "11101", 2005)),
    ("Lei Anticorrupção", WorkKey("federal", "lei", "12846", 2013)),
    ("LGPD", WorkKey("federal", "lei", "13709", 2018)),
    ("Marco da Securitização", WorkKey("federal", "lei", "14430", 2022)),
    ("Lei de Arbitragem", WorkKey("federal", "lei", "9307", 1996)),
    ("Constituição", WorkKey("federal", "constituicao", "1988", 1988)),
    ("art. 5º da CF", WorkKey("federal", "constituicao", "1988", 1988)),
]


@pytest.mark.parametrize("text,work", ALIASES)
def test_aliases(text, work):
    c = _norma(text)
    assert _work(c) == work


# Dispositivos
DEVICE_CASES = [
    (
        "art. 254-A, § 1º, II, 'a', da Lei 6.404/76",
        "art254-A.par1.inc2.ali-a",
    ),
    ("art. 254-A da Lei 6.404/76", "art254-A"),
    ("§ 2º do art. 118 da Lei 6.404/76", "art118.par2"),
    ("inciso II do art. 1º da Lei 6.404/76", "art1.inc2"),
    ("caput do art. 5º da CF/88", "art5.caput"),
    ("parágrafo único do art. 116 da LSA", "art116.parunico"),
]


@pytest.mark.parametrize("text,path", DEVICE_CASES)
def test_devices(text, path):
    c = _norma(text)
    assert c.path == path, (text, c.path, c.raw)


def test_arts_multiplos():
    cites = extract("arts. 116 e 117 da LSA")
    normas = [c for c in cites if c.kind == "norma"]
    paths = {c.path for c in normas}
    assert "art116" in paths
    assert "art117" in paths
    assert len(paths) >= 2


# Decisões / súmulas / temas / processo
DECISION_CASES = [
    ("REsp 1.234.567/SP", "decisao", "stj", "REsp"),
    ("AgInt no AREsp nº 1.234.567/RJ", "decisao", "stj", "AREsp"),
    ("EREsp 1.111.111", "decisao", "stj", "EREsp"),
    ("RE 1.010.606", "decisao", "stf", "RE"),
    ("ARE 700.000", "decisao", "stf", "ARE"),
    ("ADI 2.591", "decisao", "stf", "ADI"),
    ("ADC 1", "decisao", "stf", "ADC"),
    ("ADPF 347", "decisao", "stf", "ADPF"),
    ("HC 100.000", "decisao", "stf", "HC"),
    ("MS 30.000", "decisao", "stf", "MS"),
    ("Rcl 5.000", "decisao", "stf", "Rcl"),
    ("AI 800.000", "decisao", "stf", "AI"),
]


@pytest.mark.parametrize("text,kind,court,cls", DECISION_CASES)
def test_decisions(text, kind, court, cls):
    c = parse_one(text)
    assert c is not None
    assert c.kind == kind
    assert c.decision is not None
    assert c.decision.court == court
    assert cls.lower() in c.decision.class_.lower().replace(" ", "")


def test_sumulas():
    c = parse_one("Súmula 7/STJ")
    assert c and c.kind == "sumula" and c.decision and c.decision.court == "stj"
    c = parse_one("Súmula nº 473 do STF")
    assert c and c.kind == "sumula" and c.decision.court == "stf"
    c = parse_one("Súmula Vinculante 13")
    assert c and c.kind == "sumula" and "Vinculante" in c.decision.class_


def test_temas():
    c = parse_one("Tema 1.046 do STF")
    assert c and c.kind == "tema" and c.decision.court == "stf"
    assert c.decision.number == "1046"
    c = parse_one("Tema Repetitivo 1.076/STJ")
    assert c and c.kind == "tema" and c.decision.court == "stj"
    c = parse_one("Tema 1076")
    assert c and c.kind == "tema"


def test_acordao_tcu():
    c = parse_one("Acórdão 1.234/2020-TCU-Plenário")
    assert c and c.kind == "decisao" and c.decision.court == "tcu"
    c = parse_one("Acórdão TCU nº 1234/2020 – Plenário")
    assert c and c.decision.court == "tcu"


def test_pas_cvm():
    c = parse_one("PAS CVM nº 19957.001234/2020-11")
    assert c and c.kind == "decisao" and c.decision.court == "cvm"


def test_cnj_valido():
    # Número sintético com DV correto: calcular
    # base = 000000120180100000 → DV
    # Usamos um número conhecido válido: 0000001-05.2018.8.26.0100? Vamos gerar
    nnnnnnn, aaaa, j, tr, oooo = "0000001", "2018", "8", "26", "0100"
    base = int(nnnnnnn + aaaa + j + tr + oooo)
    dv = 98 - ((base * 100) % 97)
    if dv == 98:
        dv = 1
    num = f"{nnnnnnn}-{dv:02d}.{aaaa}.{j}.{tr}.{oooo}"
    assert validate_cnj_dv(num)
    c = parse_one(num)
    assert c and c.kind == "processo" and c.confidence == "exata"
    assert "cnj_dv_invalido" not in c.flags


def test_cnj_invalido():
    num = "0000001-99.2018.8.26.0100"
    assert not validate_cnj_dv(num)
    c = parse_one(num)
    assert c and c.kind == "processo"
    assert c.confidence == "provavel"
    assert "cnj_dv_invalido" in c.flags


# Contagem mínima de positivos
def test_positive_count():
    n = (
        len(POSITIVE_NORMS)
        + len(ALIASES)
        + len(DEVICE_CASES)
        + 1  # arts multiplos
        + len(DECISION_CASES)
        + 3  # sumulas
        + 3  # temas
        + 2  # tcu
        + 1  # pas
        + 1  # cnj valido
    )
    assert n >= 60, n


# ---------------------------------------------------------------------------
# Negativos
# ---------------------------------------------------------------------------

NEGATIVES = [
    "artigo de opinião",
    "lei de Murphy",
    "lei de Moore",
    "RE",  # isolado
    "sobre o tema",
    "artigo científico",
    "a lei do retorno",
    "código de conduta interno",
    "circular interna da empresa",
    "sumula de boas práticas",
    "tema da reunião",
    "processo seletivo 2024",
    "ADI sem número aqui",
    "apenas texto corrido sem citação normativa",
    "Lei de Murphy e artigo de opinião",
]


@pytest.mark.parametrize("text", NEGATIVES)
def test_negatives(text):
    cites = extract(text)
    # nenhum com confidence exata de norma/decisão real; RE isolado → vazio
    assert cites == [] or all(
        c.kind == "processo" and "cnj_dv_invalido" in c.flags for c in cites
    ), (text, cites)


def test_negative_count():
    assert len(NEGATIVES) >= 15


def test_extract_mixed():
    text = (
        "Conforme art. 254-A da Lei 6.404/76 e a Súmula 7/STJ, "
        "bem como o REsp 1.234.567/SP."
    )
    cites = extract(text)
    kinds = {c.kind for c in cites}
    assert "norma" in kinds
    assert "sumula" in kinds
    assert "decisao" in kinds
