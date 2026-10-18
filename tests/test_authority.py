"""Rótulos de autoridade A–E."""

from __future__ import annotations

from freoa_verifica.authority import RULES_VERSION, as_dict, classify_authority


def test_rules_version():
    assert RULES_VERSION == "autoridade-1"


def test_label_a_sumula_vinculante():
    lab = classify_authority(species="sumula_vinculante", court="STF")
    assert lab.label == "A"
    d = as_dict(lab)
    assert d["attributes"]["species"] == "sumula_vinculante"
    assert d["rule"]


def test_label_a_controle():
    lab = classify_authority(
        species="acordao", court="STF", class_name="ADI", organ="Pleno"
    )
    assert lab.label == "A"


def test_label_b_rg():
    lab = classify_authority(species="repercussao_geral", court="STF")
    assert lab.label == "B"


def test_label_c_pleno():
    lab = classify_authority(species="acordao", court="STJ", organ="Corte Especial")
    assert lab.label == "C"


def test_label_d_turma():
    lab = classify_authority(species="acordao", court="STJ", organ="Primeira Turma")
    assert lab.label == "D"


def test_label_e_administrativa():
    lab = classify_authority(species="administrativa", court="CVM")
    assert lab.label == "E"


def test_adpf_monocratica_is_e_not_a():
    lab = classify_authority(
        species="monocratica", court="STF", class_name="ADPF", organ="Pleno"
    )
    assert lab.label == "E"


def test_tcu_plenario_is_e_with_organ():
    lab = classify_authority(
        species="administrativa", court="TCU", organ="Plenário"
    )
    assert lab.label == "E"
    assert lab.attributes.organ == "Plenário"


def test_species_acordao_accent_normalized():
    lab = classify_authority(species="ACÓRDÃO", court="STJ", organ="Primeira Turma")
    assert lab.label == "D"
    assert lab.attributes.species == "acordao"
