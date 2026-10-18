"""Regressões de pertença estrutural e formas explícitas de referência."""
import json
from collections import Counter
from pathlib import Path

import pytest

from freoa_verifica.citation import extract
from tests.regression_expectations import audit_gold


def identities(text):
    return Counter(
        f"{c.work.authority}/{c.work.kind}/{c.work.number}/{c.work.year}/"
        + ("-" if "preferir_outro_referente" in c.flags else c.path or "-")
        for c in extract(text) if c.work
    )


CORPUS = [json.loads(line) for filename in (
    "prosa_audit_final6.jsonl", "prosa_audit_final7.jsonl"
) for line in (Path(__file__).parent / "fixtures" / filename).read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("case", CORPUS, ids=lambda c: c["id"])
def test_audit_corpora(case):
    assert identities(case["text"]) == Counter(audit_gold(case))
    for cite in extract(case["text"]):
        assert set(cite.flags) <= {"preferir_outro_referente"}
        if cite.flags:
            assert cite.confidence == "provavel"


# Quarenta sintagmas distintos, sem depender de enumeração no extrator.
OWNERS = [
    "do nosso contrato", "do referido estatuto", "do Acordo de Acionistas de 2019",
    "da Escritura de Emissão", "do Regulamento do Fundo", "do seu contrato social",
    "da nossa política interna", "do presente instrumento", "da mencionada escritura",
    "dos novos contratos", "das antigas atas", "de um acordo particular",
    "no regulamento aprovado", "na política vigente", "deste estatuto",
    "dessa convenção", "daquele pacto", "do documento XPTO", "da CCB",
    "do MoU", "do NDA", "do SPA", "do AA", "da escritura pública",
    "do contrato revisado", "da minuta consolidada", "dos nossos termos",
    "das referidas condições", "de qualquer instrumento", "do plano de incentivos",
    "da deliberação assemblear", "do prospecto definitivo", "do laudo independente",
    "da proposta comercial", "do memorando preliminar", "da circular interna",
    "do código de conduta", "da cláusula especial", "do relatório anual",
    "do Anexo I do nosso contrato",
]


@pytest.mark.parametrize("owner", OWNERS)
@pytest.mark.parametrize("template", [
    "Lei 6.404/1976, art. 5 {owner}.",
    "art. 5 {owner} e a Lei 6.404/1976.",
    "art. 5 {owner}, da Lei 6.404/1976.",
    "Lei 6.404/1976 (art. 5 {owner}).",
    "Lei 6.404/1976, arts. 5 e 6 {owner}.",
])
def test_foreign_owner(owner, template):
    text = template.format(owner=owner)
    assert identities(text) == Counter({"federal/lei/6404/1976/-": 1})
    assert not any(c.flags for c in extract(text))


SCOPES = [
    ("do Anexo I", "anexo-i/art5"), ("do Anexo II", "anexo-ii/art5"),
    ("do Anexo III", "anexo-iii/art5"), ("do Anexo IV", "anexo-iv/art5"),
    ("do Anexo V", "anexo-v/art5"), ("do Anexo VI", "anexo-vi/art5"),
    ("do Anexo VII", "anexo-vii/art5"), ("do Anexo VIII", "anexo-viii/art5"),
    ("do Anexo IX", "anexo-ix/art5"), ("do Anexo X", "anexo-x/art5"),
    ("do Anexo A", "anexo-a/art5"), ("do Anexo B", "anexo-b/art5"),
    ("do Anexo 1", "anexo-1/art5"), ("do Anexo 2", "anexo-2/art5"),
    ("do Capítulo I", "art5"), ("do Capítulo II", "art5"),
    ("do Capítulo III", "art5"), ("do Capítulo IV", "art5"),
    ("do Capítulo V", "art5"), ("do caput", "art5.caput"),
]


@pytest.mark.parametrize("scope,path", SCOPES)
@pytest.mark.parametrize("template", [
    "Lei 6.404/1976, art. 5 {scope}.",
    "art. 5 {scope} da Lei 6.404/1976.",
    "Lei 6.404/1976 (art. 5 {scope}).",
])
def test_same_norm_scope(scope, path, template):
    text = template.format(scope=scope)
    expected_path = path
    assert identities(text) == Counter({f"federal/lei/6404/1976/{expected_path}": 1})
    assert not any(c.flags for c in extract(text))


@pytest.mark.parametrize("marker", ["n.º", "nº.", "n."])
@pytest.mark.parametrize("year", ["/1976", ""])
def test_number_marker(marker, year):
    assert identities(f"art. 116 da Lei {marker} 6.404{year}") == Counter({
        f"federal/lei/6404/{1976 if year else 0}/art116": 1})


def test_parenthesized_article():
    assert identities("Lei 6.404/1976 (art. 116)") == Counter({
        "federal/lei/6404/1976/art116": 1})


def test_explicit_owner_is_not_assigned_to_preceding_norm():
    assert identities("Lei 6.404/1976, art. 5 da Lei 6.385/1976") == Counter({
        "federal/lei/6404/1976/-": 1, "federal/lei/6385/1976/art5": 1})


@pytest.mark.parametrize("owner", ["do Anexo Interno", "do Capítulo Inicial",
    "do Capítulo II do contrato", "do caput do nosso estatuto"])
def test_scope_requires_complete_identifier_and_same_owner(owner):
    assert identities(f"Lei 6.404/1976, art. 5 {owner}.") == Counter({
        "federal/lei/6404/1976/-": 1})
