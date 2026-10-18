"""Duas camadas: estrutura, confiança e status sem promoção de propostas."""
import json
from pathlib import Path

import pytest

from freoa_verifica.aliases import WorkKey
from freoa_verifica.citation import extract
from freoa_verifica.parsers.model import ParsedDocument, Provision, Redaction
from freoa_verifica.service import Verifica


NORM = "Lei 6.404/1976"
KEY = WorkKey("federal", "lei", "6404", 1976)
CANONICAL = [f"{NORM}, art. {n}{suffix}{end}"
             for n in (1, 7, 118, 1022)
             for suffix in ("", ", § 2º", ", inciso IV", ", § 2º, inciso IV")
             for end in ("", ".", "; outra questão", ": texto")]
PROSE = [f"{NORM}, art. 118, {predicate}." for predicate in (
    "permite o pedido", "exige o exame", "será aplicada", "autoriza a medida",
    "não admite o pedido", "rege a questão", "constitui fundamento",
    "consta do contrato", "prevê no contrato a regra", "é objeto do contrato")]
PAIRED = [f"{NORM} {a} art. 118 {b} integra o fundamento."
          for a, b in (("(", ")"), ("—", "—"), ("–", "–"))]
OWNERS = ["do contrato", "da convenção", "dos documentos", "das atas", "de um pacto",
          "no acordo", "na minuta", "nos acordos", "nas minutas", "pertencente ao pacto",
          "constante do termo", "inserido no pacto", "previsto no acordo", "integrante da ata"]
PRIVATE = [f"{NORM}, {label} {n} {owner}."
           for label in ("art.", "cláusula", "item") for n in ("7.1", "12.3", "2.99")
           for owner in ("do instrumento", "")]
PRIVATE += [f"{NORM}, art. 118 {owner}." for owner in OWNERS]
PRIVATE += [f"{NORM} {tail}" for tail in ("(art. 118", "— art. 118.", "– art. 118.",
                                                        "(art. 118 do acordo)", "— art. 118 do acordo —")]
COMPACT = ["RCVM44", "ICVM44X", "LSA2", "RCVM 44X", "Lei 44X/2021"]


@pytest.mark.parametrize("text", CANONICAL)
def test_canonical_exact(text):
    cites = extract(text)
    assert cites and all(c.confidence == "exata" and c.path for c in cites)


@pytest.mark.parametrize("text", PROSE + PAIRED)
def test_posterior_proposal(text):
    cites = extract(text)
    assert len(cites) == 1
    assert cites[0].path == "art118"
    assert cites[0].confidence == "provavel"
    assert cites[0].raw == text[slice(*cites[0].span)]


@pytest.mark.parametrize("text", PRIVATE)
def test_private_and_unpaired_not_devices(text):
    cites = extract(text)
    assert len(cites) == 1 and cites[0].path is None


@pytest.mark.parametrize("text", COMPACT)
def test_full_norm_token(text):
    assert not extract(text)


@pytest.mark.parametrize("number", ["1.022", "1.142"])
@pytest.mark.parametrize("template", ["art. {n} da Lei 6.404/1976.", "Lei 6.404/1976, art. {n}."])
def test_thousands(number, template):
    cite, = extract(template.format(n=number))
    assert cite.path == "art" + number.replace(".", "")
    assert cite.confidence == "exata"


def test_no_device_transfer():
    cites = extract("RCVM 44/2021, art. 8º, e ICVM 44/1984, art. 9º.")
    assert [(c.work.kind, c.path) for c in cites] == [("resolucao", "art8"), ("instrucao", "art9")]


@pytest.mark.parametrize("present", [True, False])
def test_service_status_gate(tmp_path, monkeypatch, present):
    monkeypatch.setenv("FV_OFFLINE", "1")
    with Verifica(tmp_path / "home") as svc:
        path = "art118" if present else "art9999"
        doc = ParsedDocument("synthetic", "1", NORM, None, "Texto sintético.", provisions=[
            Provision(path, path, "body", redactions=[Redaction("Texto sintético.", False, 0)])])
        svc.indexar_obra(source_id="planalto", work_key=KEY, document=doc,
                         body=b"synthetic-r16", url="https://example.invalid/synthetic")
        for text in PROSE + PAIRED:
            row, = svc.verificar_texto(text)["citacoes"]
            assert row["confidence"] == "provavel"
            assert row["status"] == "requer_conferencia"
            assert row["identity"]["status"] == "unknown"
            review = row["conferencia"]
            assert review["interpretacao_proposta"]["path"] == "art118"
            assert review["alternativas"] == ["norma sem dispositivo", "dispositivo de outro referente"]
            assert review["evidencia_disponivel"]["sha256"]
            assert review["confronto_proposto"]["identity"]["status"] == ("verified" if present else "not_found")
        row, = svc.verificar_texto(NORM + ", art. 118.")["citacoes"]
        assert row["status"] == ("encontrada" if present else "inexistente")
        assert row["confidence"] == "exata"


@pytest.mark.parametrize("case", [json.loads(line) for line in
    (Path(__file__).parent / "fixtures" / "prosa_audit_final9.jsonl").read_text(encoding="utf-8").splitlines()], ids=lambda c: c["id"])
def test_audit_no_wrong_exact(case):
    gold = [(tuple(work), path) for work, path in case["expected"]]
    for cite in extract(case["text"]):
        assert cite.confidence in {"exata", "provavel"}
        if cite.confidence != "exata":
            continue
        work = tuple(vars(cite.work).values())
        # Obra sem artigo é uma omissão de dispositivo, medida no recall.
        assert (work, cite.path) in gold or (cite.path is None and any(w == work for w, _ in gold))
