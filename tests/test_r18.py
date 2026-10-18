"""Determinantes posteriores, pertença e métricas dos seis corpora congelados."""
import hashlib
import json

import pytest

from freoa_verifica.citation import extract
from collections import Counter
from tests.test_r17 import FIXTURES, cases_for, extraction_metrics, service_metrics, identity


def device_metrics(cases):
    hits = expected = 0
    for case in cases:
        gold = Counter(item for item in case["gold"] if item[1] is not None)
        actual = Counter(identity(c, True) for c in extract(case["text"]) if c.work)
        hits += (gold & actual).total()
        expected += gold.total()
    return dict(device_hits=hits, device_expected=expected, device_recall=hits / expected)


@pytest.mark.parametrize("rounds", [(6,), (7,), (8,), (9,), (10,), (11,), tuple(range(6, 12))])
def test_explicit_device_metrics_and_statuses(rounds, tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    metrics = extraction_metrics(cases_for(rounds))
    devices = device_metrics(cases_for(rounds))
    assert devices["device_recall"] >= .95, devices
    if rounds == (10,) or len(rounds) > 1:
        assert metrics["recall"] >= .95, metrics
    elif rounds[0] < 10:
        assert metrics["explicit_recall"] >= .95, metrics
    assert metrics["exact_error_rate"] <= .01, metrics
    for mode in ("present", "absent"):
        counts, _ = service_metrics(cases_for(rounds), tmp_path / mode, mode)
        assert counts["false_definitive"] == counts["controls_definitive"] == counts["gate_failures"] == 0, counts


def test_frozen_corpus():
    pre = json.loads((FIXTURES / "prosa_audit_final11_preregistration.json").read_text(encoding="utf-8"))
    assert hashlib.sha256((FIXTURES / "prosa_audit_final11.jsonl").read_bytes()).hexdigest() == pre["corpus_sha256"]
    assert len(cases_for((11,))) == pre["cases"]


DETERMINERS = "o os a as um uns uma umas seu seus sua suas esse esses essa essas este estes esta estas aquele aqueles aquela aquelas tal tais referido referidos referida referidas mencionado mencionados mencionada mencionadas".split()


@pytest.mark.parametrize("determiner", DETERMINERS + ["o seu", "esse referido"])
@pytest.mark.parametrize("connector", [", ", " ", ": ", " cujo ", " especialmente "])
def test_determiners_are_probable(determiner, connector):
    text = f"Na Lei nº 13.105/2015{connector}{determiner} art. 345 orienta?"
    cite, = extract(text)
    assert cite.path == "art345" and cite.confidence == "provavel"
    assert cite.raw == text[slice(*cite.span)]
    assert cite.raw.endswith("art. 345")


@pytest.mark.parametrize("determiner", ["o", "seu", "esse", "referido"])
def test_explicit_norm_owns_device(determiner):
    cites = extract(f"Lei 13.105/2015, {determiner} art. 345 da Lei 10.406/2002.")
    assert [(c.work.number, c.path) for c in cites] == [("13105", None), ("10406", "art345")]
    assert cites[1].confidence == "exata"


@pytest.mark.parametrize("owner", ["do contrato", "da convenção", "pertencente ao regulamento", "oriundo do pacto"])
def test_private_owner_is_preferred(owner):
    cite, = extract(f"Lei 13.105/2015, o art. 345 {owner}.")
    assert cite.path == "art345" and cite.confidence == "provavel"
    assert "preferir_outro_referente" in cite.flags


@pytest.mark.parametrize("number", ["345.4", "345.42", "345X"])
def test_no_truncation(number):
    cite, = extract(f"Lei 13.105/2015, o art. {number}.")
    assert cite.path is None


@pytest.mark.parametrize("distance", [120, 121])
def test_distance(distance):
    cite, = extract("Lei 13.105/2015" + " " * (distance - 2) + "o art. 345.")
    assert cite.path == ("art345" if distance == 120 else None)


def test_determiner_does_not_search_across_sentence():
    cite, = extract("Lei 13.105/2015 foi citada. Do mesmo diploma, o art. 345 foi destacado.")
    assert cite.path is None


@pytest.mark.parametrize("label,path", [
    ("arts. 345 e 346", "art345"),
    ("art. 345, § 2º, inciso IV", "art345.par2.inc4"),
    ("art. 345, parágrafo único", "art345.parunico"),
    ("art. 345, item 3", "art345.item3"),
])
def test_device_chain(label, path):
    cites = extract(f"Lei 13.105/2015, esse {label}.")
    assert cites[0].path == path
    assert all(c.confidence == "provavel" for c in cites)


def test_determiners_never_receive_definitive_status(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    cases = [dict(id=str(n), text=f"Lei 13.105/2015, {d} art. 345.",
                  gold=[(("federal", "lei", "13105", 2015), "art345")])
             for n, d in enumerate(DETERMINERS)]
    for mode in ("present", "absent"):
        counts, _ = service_metrics(cases, tmp_path / mode, mode)
        assert counts["probable"] == len(cases)
        assert counts["definitive"] == counts["gate_failures"] == 0
