"""Gramática posterior fechada, corpus canônico e regressões de pertença."""
import json
import re
from collections import Counter
from pathlib import Path

import pytest

from freoa_verifica.citation import extract
from tests.regression_expectations import audit_gold

FIXTURES = Path(__file__).parent / "fixtures"


def read_rows(name):
    return [json.loads(line) for line in (FIXTURES / name).read_text(encoding="utf-8").splitlines()]


AUDITS = [case for n in (6, 7, 8) for case in read_rows(f"prosa_audit_final{n}.jsonl")]
CANONICAL = read_rows("prosa_r15_canonical.jsonl")


def identities(text):
    return Counter(f"{c.work.authority}/{c.work.kind}/{c.work.number}/{c.work.year}/"
                   + ("-" if "preferir_outro_referente" in c.flags else c.path or "-")
                   for c in extract(text) if c.work)


def gold(case):
    expected = audit_gold(case)
    if expected and isinstance(expected[0], list):
        expected = ["/".join(map(str, row[:4])) + "/" + (row[4] or "-") for row in expected]
    return Counter(expected)


@pytest.mark.parametrize("case", AUDITS, ids=lambda case: case["id"])
def test_all_audit_cases(case):
    assert identities(case["text"]) == gold(case)
    for cite in extract(case["text"]):
        assert set(cite.flags) <= {"preferir_outro_referente"}
        if cite.flags:
            assert cite.confidence == "provavel"
        assert cite.raw == case["text"][slice(*cite.span)]


@pytest.mark.parametrize("case", CANONICAL, ids=lambda case: case["id"])
def test_canonical_case(case):
    expected = Counter(case["gold"])
    if re.search(r"[—–]", case["text"]):
        expected = Counter(key.rsplit("/", 1)[0] + "/-" for key in case["gold"])
        # Artigos múltiplos sem vínculo são uma única referência à obra.
        expected = Counter({key: 1 for key in expected})
    assert identities(case["text"]) == expected
    for cite in extract(case["text"]):
        assert not cite.flags
        assert cite.raw == case["text"][slice(*cite.span)]


def measure():
    tp = fp = fn = 0
    for case in CANONICAL:
        if re.search(r"[—–]", case["text"]):
            continue
        want, got = Counter(case["gold"]), identities(case["text"])
        tp += (want & got).total()
        fp += (got - want).total()
        fn += (want - got).total()
    return dict(cases=len(CANONICAL), tp=tp, fp=fp, fn=fn, recall=tp/(tp+fn))


def test_canonical_recall():
    metrics = measure()
    assert metrics["cases"] == 1776
    assert metrics["recall"] >= .98
    assert metrics["fp"] == 0


CONTINUATIONS = [
    " (do contrato)", " — do contrato", " – do contrato", " do contrato",
    " da norma", " de um pacto", " no formulário", " na ata", " deste ajuste",
    ", pertencente ao estatuto", " constante do termo", " inserido no pacto",
    " previsto no contrato", " segundo o contrato", " e cláusula 7.1 do acordo",
    ", e pertencente ao estatuto", ", mas constante do contrato",
    ", e a ele pertencente", ", e o dispositivo do contrato", ", é pertencente ao contrato",
    ", foi inserido no acordo", ", está previsto no contrato",
    " ICVM 44/1984", ", ICVM 44/1984", " IN CVM 44/1984", ", IN CVM 44/1984",
    " Lei 6.385/1976", ", Lei 6.385/1976", " da ICVM 44/1984",
    ", IIIXYZ", ", II_ABC", ", I-CVM", ", inciso IN", ", CVM",
    " do Anexo II", " do Capítulo II", " mencionado", ", referido no pacto",
    ", conforme o acordo", ", segundo o estatuto", " do contrato — e a Lei 6.385/1976",
]


@pytest.mark.parametrize("continuation", CONTINUATIONS)
@pytest.mark.parametrize("chain", ["art. 5", "arts. 5 e 6", "art. 5, § 2º, inciso II"])
def test_unapproved_continuation(continuation, chain):
    text = "Lei 6.404/1976, " + chain + continuation + "."
    first = [c for c in extract(text) if c.work and c.work.number == "6404"]
    assert first
    if first[0].path is not None:
        assert all(c.confidence == "provavel" for c in first)
    else:
        assert first[0].raw == "Lei 6.404/1976"
    assert not first[0].flags


@pytest.mark.parametrize("text", [
    "Lei 6.404/1976, art. 5)",
    "Lei 6.404/1976 (art. 5)",
    "(Nota) Lei 6.404/1976, art. 5)",
    "(Lei 6.404/1976, art. 5 (texto))",
    "Lei 6.404/1976, art. 5, IIIXYZ.",
])
def test_unmatched_or_late_parenthesis_and_roman_prefix(text):
    cites = extract(text)
    assert len(cites) == 1
    if cites[0].path:
        assert cites[0].confidence == "provavel"
    else:
        assert identities(text) == Counter({"federal/lei/6404/1976/-": 1})


@pytest.mark.parametrize("owner", ["do contrato", "do documento XPTO", "do regulamento",
                                  "do Anexo II do pacto"])
def test_anterior_does_not_cross_owner(owner):
    assert identities(f"art. 5 {owner} — e a Lei 6.404/1976.") == Counter({"federal/lei/6404/1976/-": 1})


@pytest.mark.parametrize("label,path", [("inciso ii", "inc2"), ("inc. xiv", "inc14"),
                                       ("xvi", "inc16"), ("alínea c", "ali-c"), ("c", "ali-c")])
def test_posterior_label_case(label, path):
    assert identities(f"Lei 6.404/1976, art. 116, {label}.") == Counter({f"federal/lei/6404/1976/art116.{path}": 1})


@pytest.mark.parametrize("present", [False, True])
@pytest.mark.parametrize("case", [c for c in AUDITS if c["id"] in {
    "C057", "C058", "C059", "C060", "C061", "C062", "C068", "C076"}], ids=lambda c: c["id"])
def test_service_cannot_verify_invented_device(tmp_path, monkeypatch, present, case):
    from freoa_verifica.aliases import WorkKey
    from freoa_verifica.parsers.model import ParsedDocument, Provision, Redaction
    from freoa_verifica.service import Verifica

    monkeypatch.setenv("FV_OFFLINE", "1")
    monkeypatch.setenv("FV_STAGING_DIR", str(tmp_path / "staging"))
    with Verifica(tmp_path / "home") as svc:
        for key, title in [(WorkKey("federal", "lei", "6404", 1976), "Lei 6.404/1976"),
                           (WorkKey("federal", "lei", "6385", 1976), "Lei 6.385/1976"),
                           (WorkKey("cvm", "resolucao", "44", 2021), "Resolução CVM 44/2021"),
                           (WorkKey("cvm", "instrucao", "44", 1984), "Instrução CVM 44/1984")]:
            paths = [f"art{n}" for n in range(64, 90)] + ["art75.inc1106"] if present else ["art999"]
            provisions = [Provision(p, p, "", redactions=[Redaction("Texto sintético.", False, 0)]) for p in paths]
            svc.indexar_obra(source_id="planalto" if key.authority == "federal" else "cvm",
                             work_key=key, document=ParsedDocument("test", "1", title, None,
                             "Texto sintético.", provisions=provisions), body=title.encode(),
                             url="https://example.invalid/synthetic")
        rows = svc.verificar_texto(case["text"])["citacoes"]
        if case["id"] in {"C062", "C076"}:
            assert all(row["status"] == "requer_conferencia" for row in rows)
        else:
            assert Counter(row["caminho"] for row in rows) == Counter({None: 1, "art75": 1} if case["id"] == "C068" else {None: 1})
