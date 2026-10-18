"""Recall por interpretação preferida e propagação em dois acervos sintéticos."""
import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from freoa_verifica.aliases import WorkKey
from freoa_verifica.citation import extract
from freoa_verifica.parsers.model import ParsedDocument, Provision, Redaction
from freoa_verifica.service import Verifica

FIXTURES = Path(__file__).parent / "fixtures"
DEFINITIVE = {"encontrada", "inexistente"}


def normalize(value):
    if isinstance(value, dict):
        return (("federal", "lei", str(value["number"]), value["year"]),
                "art" + value["article"] if value["article"] else None)
    if isinstance(value, str):
        a, k, n, y, p = value.split("/", 4)
        return ((a, k, n, int(y)), None if p == "-" else p)
    if len(value) == 5:
        return (tuple(value[:4]), value[4])
    if len(value) == 4:
        return (("federal", value[0], value[1], int(value[2])),
                "art" + value[3] if value[3] else None)
    return (tuple(value[0]), value[1])


def cases_for(rounds):
    return [dict(r, gold=[normalize(x) for x in r.get("gold", r.get("expected", []))])
            for n in rounds for r in map(json.loads, (FIXTURES / f"prosa_audit_final{n}.jsonl")
                                        .read_text(encoding="utf-8").splitlines())]


def identity(cite, preferred=False):
    return (tuple(vars(cite.work).values()),
            None if preferred and "preferir_outro_referente" in cite.flags else cite.path)


def wrong(item, gold):
    return item not in gold and (item[1] is not None or not any(w == item[0] for w, _ in gold))


def extraction_metrics(cases):
    m = Counter(cases=len(cases), hits=0, expected=0, exact=0, wrong_exact=0,
                explicit_hits=0, explicit_expected=0)
    for case in cases:
        cites = [c for c in extract(case["text"]) if c.work]
        gold = Counter(case["gold"])
        preferred = Counter(identity(c, True) for c in cites)
        hits = (gold & preferred).total()
        m["hits"] += hits
        m["expected"] += gold.total()
        if case["group"] in {"explicit", "explicita"}:
            m["explicit_hits"] += hits
            m["explicit_expected"] += gold.total()
        for c in cites:
            if c.confidence == "exata":
                m["exact"] += 1
                m["wrong_exact"] += wrong(identity(c), gold)
    return dict(m, recall=m["hits"] / m["expected"],
                exact_error_rate=m["wrong_exact"] / m["exact"],
                explicit_recall=m["explicit_hits"] / m["explicit_expected"] if m["explicit_expected"] else None)


def service_metrics(cases, home, mode):
    works = {}
    for case in cases:
        for w, p in case["gold"] + [identity(c) for c in extract(case["text"]) if c.work]:
            works.setdefault(w, set()).update([p] if p else [])
    m = Counter(false_definitive=0, controls_definitive=0, gate_failures=0,
                definitive=0, controls=0, probable=0)
    results = []
    with Verifica(home) as svc:
        for w, paths in works.items():
            paths = sorted(paths | {"art99999"}) if mode == "present" else ["art99999"]
            body = json.dumps(dict(synthetic=True, work=w, paths=paths)).encode()
            doc = ParsedDocument("synthetic", "1", "Synthetic", None, "Synthetic", provisions=[
                Provision(p, p, "body", redactions=[Redaction("Synthetic " + p, False, 0)]) for p in paths])
            svc.indexar_obra(source_id="planalto" if w[0] == "federal" else "cvm_normas",
                             work_key=WorkKey(*w), document=doc, body=body,
                             url="https://example.invalid/synthetic/" + w[0] + "/" + w[2])
        for case in cases:
            out = svc.verificar_texto(case["text"])
            control = not case["gold"]
            m["controls"] += control
            for row in out["citacoes"]:
                if row["confidence"] == "provavel":
                    m["probable"] += 1
                    review = row["conferencia"] or {}
                    m["gate_failures"] += (row["status"] != "requer_conferencia"
                        or row["identity"]["status"] != "unknown"
                        or not review.get("interpretacao_proposta")
                        or not review.get("interpretacao_preferida")
                        or "dispositivo de outro referente" not in review.get("alternativas", []))
                if row["status"] in DEFINITIVE:
                    m["definitive"] += 1
                    m["controls_definitive"] += control
                    w = row["parseada"].get("work")
                    item = (tuple(w.values()), row["caminho"]) if w else (None, None)
                    status = "encontrada" if mode == "present" or item[1] is None else "inexistente"
                    m["false_definitive"] += wrong(item, case["gold"]) or row["status"] != status
            results.append(dict(id=case["id"], response=out))
    return dict(m), results


@pytest.mark.parametrize("rounds", [(10,), (6, 7, 8, 9)])
def test_recall_and_exact_errors(rounds):
    m = extraction_metrics(cases_for(rounds))
    assert m["recall"] >= .95, m
    assert m["explicit_recall"] >= .95, m
    assert m["exact_error_rate"] <= .01, m


@pytest.mark.parametrize("rounds", [(10,), (6, 7, 8, 9)])
@pytest.mark.parametrize("mode", ["present", "absent"])
def test_status_propagation(rounds, mode, tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    m, _ = service_metrics(cases_for(rounds), tmp_path / mode, mode)
    assert m["false_definitive"] == m["controls_definitive"] == m["gate_failures"] == 0, m


def test_frozen_oracle():
    pre = json.loads((FIXTURES / "prosa_audit_final10_preregistration.json").read_text(encoding="utf-8"))
    assert hashlib.sha256((FIXTURES / "prosa_audit_final10.jsonl").read_bytes()).hexdigest() == pre["corpus_sha256"]
    assert len(cases_for((10,))) == pre["cases"]


@pytest.mark.parametrize("connector", ["cujo", "cuja", "cujos", "cujas", ":", ";", "\n",
    "notadamente", "especialmente", "em especial", "no", "em seu"])
def test_new_connectors_are_probable(connector):
    c, = extract(f"Lei 6.404/1976 {connector} art. 37.")
    assert c.path == "art37" and c.confidence == "provavel"
    assert c.raw == f"Lei 6.404/1976 {connector} art. 37"


@pytest.mark.parametrize("distance", [120, 121])
def test_proposal_distance(distance):
    prefix = "Lei 6.404/1976"
    c, = extract(prefix + " " * (distance - 5) + "cujo art. 1142.")
    assert c.path == ("art1142" if distance == 120 else None)


def test_private_preference_and_alternative(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    text = "Lei 6.404/1976 cujo art. 37 do pacto de voto."
    c, = extract(text)
    assert c.path == "art37" and c.confidence == "provavel"
    assert "preferir_outro_referente" in c.flags
    with Verifica(tmp_path / "private") as svc:
        row, = svc.verificar_texto(text)["citacoes"]
    review = row["conferencia"]
    assert row["status"] == "requer_conferencia"
    assert review["interpretacao_preferida"] == "dispositivo de outro referente"
    assert review["interpretacao_proposta"]["path"] == "art37"
    assert review["alternativas"] == ["norma sem dispositivo", "dispositivo de outro referente"]


@pytest.mark.parametrize("case", cases_for((10,)), ids=lambda c: c["id"])
def test_preferred_interpretation_frozen_cases(case):
    assert Counter(identity(c, True) for c in extract(case["text"]) if c.work) == Counter(case["gold"])


@pytest.mark.parametrize("connector", [":", ";", "cujo", "em especial"])
def test_explicit_other_norm_owns_device(connector):
    cites = extract(f"Lei 6.404/1976 {connector} art. 37 da Lei 6.385/1976.")
    assert [(c.work.number, c.path) for c in cites] == [("6404", None), ("6385", "art37")]
    assert cites[1].confidence == "exata"


@pytest.mark.parametrize("number", ["37.4", "37.42", "37X"])
def test_new_connector_never_truncates(number):
    c, = extract(f"Lei 6.404/1976 cujo art. {number}.")
    assert c.path is None


@pytest.mark.parametrize("text", [
    "Lei 6.385/1976 (arts. 46 e 47) consta do roteiro.",
    "RCVM 44/2021, art. 38 do Anexo I, consta da ementa interna.",
    "Lei 6.404/1976 — art. 37 — integra a fundamentação.",
])
def test_outer_predicate_does_not_override_delimited_device(text):
    assert all("preferir_outro_referente" not in c.flags for c in extract(text))


@pytest.mark.parametrize("opening,closing", [("(", ")"), ("—", "—"), ("–", "–")])
def test_pair_after_intermediate_prose(opening, closing):
    text = f"Lei 6.404/1976 foi citada {opening}art. 37{closing} no voto."
    c, = extract(text)
    assert c.path == "art37" and c.confidence == "provavel"
    assert c.raw == text[slice(*c.span)] and c.raw.endswith(closing)
