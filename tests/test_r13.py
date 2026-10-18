"""Regressoes de identidade e isolamento de staging."""
import json
import tempfile
from collections import Counter
from pathlib import Path

import pytest

from freoa_verifica.citation import extract
from freoa_verifica import snapshot
from tests.regression_expectations import audit_gold

CORPUS_PATH = Path(__file__).parent / "fixtures" / "prosa_audit_final6.jsonl"
CORPUS = [json.loads(line) for line in CORPUS_PATH.read_text(encoding="utf-8").splitlines()]


def identities(text):
    return Counter(
        f"{c.work.authority}/{c.work.kind}/{c.work.number}/{c.work.year}/"
        + ("-" if "preferir_outro_referente" in c.flags else c.path or "-")
        for c in extract(text) if c.work
    )


@pytest.mark.parametrize("case", CORPUS, ids=lambda case: case["id"])
def test_literal_corpus(case):
    assert identities(case["text"]) == Counter(audit_gold(case))
    for cite in extract(case["text"]):
        assert set(cite.flags) <= {"preferir_outro_referente"}
        if cite.flags:
            assert cite.confidence == "provavel"


def test_identity_metrics():
    fp = tp = explicit_tp = explicit_gold = 0
    for case in CORPUS:
        expected = Counter(audit_gold(case))
        actual = identities(case["text"])
        hits = sum((expected & actual).values())
        tp += hits
        fp += sum((actual - expected).values())
        if case["group"] == "explicita":
            explicit_tp += hits
            explicit_gold += expected.total()
    assert len(CORPUS) == 80
    assert fp == 0
    assert explicit_tp / explicit_gold >= .98
    assert tp == 77


INSTRUMENTS = ["contrato", "contrato social", "estatuto", "estatuto social",
               "acordo de acionistas", "edital", "regulamento interno", "termo",
               "ata", "parecer", "peti\u00e7\u00e3o", "voto", "instrumento"]


@pytest.mark.parametrize("instrument", INSTRUMENTS)
@pytest.mark.parametrize("prep", ["do", "da", "de"])
@pytest.mark.parametrize("template", [
    "Lei 6.404/76, art. 5 {prep} {instrument}.",
    "art. 5 {prep} {instrument}, da Lei 6.404/76.",
    "Lei 6.404/76 \u2014 arts. 5 e 6 {prep} {instrument}.",
    "art. 5 {prep} {instrument}, Lei 6.404/76, art. 6 {prep} {instrument}.",
])
def test_private_instrument(instrument, prep, template):
    assert identities(template.format(prep=prep, instrument=instrument)) == Counter({"federal/lei/6404/1976/-": 1})


@pytest.mark.parametrize("separator", [". ", "; ", "\n\n", ",\n\n", ": ", " ",
    ", e ", ", mas ", ", por\u00e9m ", ", enquanto ", ", porque ", " \u2014 e ", " \u2014\n\n"])
def test_clause_boundary(separator):
    text = "Lei 6.404/76" + separator + "art. 5 mencionado."
    proposed = separator in {"; ", "\n\n", ",\n\n", ": "}
    assert identities(text) == Counter({"federal/lei/6404/1976/" + ("art5" if proposed else "-"): 1})
    if proposed:
        assert all(c.confidence == "provavel" for c in extract(text))


@pytest.mark.parametrize("separator", [", ", " \u2014 ", " \u2013 ", ",\n"])
def test_positive_posterior_list(separator):
    if separator.strip() in {"—", "–"}:
        assert identities("Lei 6.404/76" + separator + "arts. 5 e 6.") == Counter({"federal/lei/6404/1976/-": 1})
        return
    assert identities("Lei 6.404/76" + separator + "arts. 5 e 6.") == Counter({
        "federal/lei/6404/1976/art5": 1, "federal/lei/6404/1976/art6": 1})


@pytest.mark.parametrize("surface", ["Instr. CVM", "Inst. CVM", "IN CVM"])
def test_instruction_abbreviations(surface):
    assert identities("art. 11 da " + surface + " 44/1984") == Counter({"cvm/instrucao/44/1984/art11": 1})


def test_private_complement_after_long_list():
    articles = ", ".join(str(n) for n in range(100, 125))
    assert identities("Lei 6.404/76, arts. " + articles + " do contrato social.") == Counter({
        "federal/lei/6404/1976/-": 1})


def test_staging_without_system_temp(verifica_populada, tmp_path, monkeypatch):
    svc, _, _ = verifica_populada
    def forbidden():
        pytest.fail("uso do temporario global")
    monkeypatch.setattr(tempfile, "gettempdir", forbidden)
    archive = tmp_path / "snapshot.tar.gz"
    assert snapshot.export_snapshot(svc.conn, svc.home, archive)["status"] == "ok"
    assert snapshot.install_snapshot(svc, archive)["status"] == "ok"
    root = tmp_path / "staging-root"
    assert not list(root.iterdir())


def test_default_and_configurable_staging(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_STAGING_DIR")
    home = tmp_path / "home"
    monkeypatch.setenv("FV_HOME", str(home))
    assert snapshot._staging_root() == home / "staging"
    with snapshot._temporary_staging(prefix="test-") as directory:
        assert directory.parent == home / "staging"
    assert not directory.exists()
    override = tmp_path / "configured"
    with snapshot._temporary_staging(prefix="test-", home=home, staging_dir=override) as directory:
        assert directory.parent == override
    monkeypatch.setenv("FV_STAGING_DIR", str(override))
    assert snapshot._staging_root(home) == override
