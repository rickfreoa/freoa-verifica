"""Fronteiras de identificadores, apelidos e controles determinísticos."""
import hashlib
import json
import random
from collections import Counter

import pytest

from freoa_verifica.aliases import ALIAS_SURFACES
from freoa_verifica.citation import extract
from tests.test_r17 import FIXTURES, identity, service_metrics


ACRONYMS = sorted({s for s, _ in ALIAS_SURFACES if s.isalpha() and s.isupper()}
                  | {"RCVM", "ICVM", "CMN", "CVM", "BCB", "LC", "MP"})


def corpus12():
    rows = [json.loads(line) for line in
            (FIXTURES / "prosa_audit_final12.jsonl").read_text(encoding="utf-8").splitlines()]
    return [dict(r, gold=[(("federal", "lei", e["work"].split("/")[0],
                           int(e["work"].split("/")[1])), e["path"])
                          for e in r["expected"]]) for r in rows]


def nonlegal_cases():
    """2.400 frases únicas; doze famílias, sem qualquer norma no ouro."""
    rng = random.Random(190219)
    templates = [
        "O produto {a}-{n} saiu do lote {b}_{num}.",
        "O ticker {a}{n} fechou em R$ {value}; série {b}/{num}.",
        "A placa {a}-{n} foi registrada na garagem {b}_{num}.",
        "Envie para {a}.{num}@example.invalid ou suporte+{b}{n}@example.invalid.",
        "Visite https://example.invalid/{a}/{num}?item={b}-{n}.",
        "Abra {a}.pdf e arquivo_{b}_{num}.txt no pedido {n}.",
        "A versão {a}.{num}.{n} substitui o pacote {b}-{num}.",
        "O pedido {a}/{num} contém a peça {b}_{n}.",
        "CNPJ 12.345.678/0001-90, conta {a}-{num}, lote {b}.{n}.",
        "CPF 123.456.789-09, recibo {a}_{num}, total R$ {value}.",
        "Em 18/10/2026 recebemos {a}-{num}; próxima entrega 19/10/2026, {b}{n}.",
        "Software {a.lower} e {b.lower}: preço R$ {value}, licença {n}.",
    ]
    numbers = ["13.105/2015", "10.406/2002", "6.404/1976", "44/2021",
               "101/2000", "13.709/2018", "4.966/2021", "8.078/1990"]
    for n in range(2400):
        a, b = rng.sample(ACRONYMS, 2)
        template = templates[n % len(templates)].replace("{a.lower}", a.lower()).replace("{b.lower}", b.lower())
        text = template.format(a=a, b=b, n=10000+n, num=rng.choice(numbers),
                               value=f"{rng.randrange(1, 999)}.{rng.randrange(1000):03d},90")
        yield dict(id=f"FUZZ-{n:04d}", group=f"nonlegal-{n % 12}", text=text, gold=[])


@pytest.mark.parametrize("a", ACRONYMS)
@pytest.mark.parametrize("template", ["{a}-901", "{a}_2", "{a}/2", "{a}.pdf",
    "{a}901", "x{a}", "{a}x", "{a}@example.invalid", "x@{a}.invalid",
    "https://example.invalid/{a}", "arquivo.{a}", "{a}.13.105/2015",
    "{a}-13.105/2015", "{a}_13.105/2015", "{a}/13.105/2015",
    "https://example.invalid/({a})", "https://example.invalid?q=({a})",
    "({a}).pdf", "nome+({a})@example.invalid"])
def test_identifier_is_not_citation(a, template):
    assert not extract("Conforme " + template.format(a=a) + ", guardar.")


@pytest.mark.parametrize("a", ACRONYMS)
def test_lowercase_and_inside_words(a):
    for token in (a.lower(), a.capitalize(), "x" + a + "x"):
        if token == a:
            continue
        assert not extract(f"Conforme {token}, guardar.")


@pytest.mark.parametrize("a", ["CPC", "CC", "CF", "CDC", "LSA", "LGPD", "LRF",
                               "Código Civil", "Constituição Federal"])
@pytest.mark.parametrize("template", ["Conforme {a}.", "Conforme ({a}).", "Conforme {a}, seguir."])
def test_alias_without_device_is_probable(a, template):
    cites = extract(template.format(a=a))
    assert cites and all(c.confidence == "provavel" and c.path is None for c in cites)


def test_numbered_work_stays_exact_and_explicit_alias_device_stays_exact():
    for text in ("Lei 13.105/2015.", "art. 345 do CPC.", "art. 5º da CF."):
        cite, = extract(text)
        assert cite.confidence == "exata"


@pytest.mark.parametrize("ref", ["Lei 13.105/2015", "RCVM 44/2021", "ICVM 400/2003",
                                "LC 101/2000", "MP 2.200-2/2001", "Resolução CMN 4.966/2021"])
@pytest.mark.parametrize("template", ["arquivo_{ref}", "https://example.invalid/{ref}",
                                      "{ref}.pdf", "{ref}-lote", "{ref}_2", "{ref}/produto"])
def test_numbered_norm_inside_identifier(ref, template):
    assert not extract(template.format(ref=ref))


@pytest.mark.parametrize("text", ["rcvm 44/2021", "icvm 400/2003", "lc 101/2000",
                                 "mp 2.200-2/2001", "Resolução cmn 4.966/2021"])
def test_lowercase_numbered_abbreviation(text):
    assert not extract(text)


def test_all_aliases_without_device_public_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    cases = [dict(id=str(n), text=f"Conforme {surface}.",
                  gold=[(tuple(vars(work).values()), None)])
             for n, (surface, work) in enumerate(ALIAS_SURFACES) if "/" not in surface]
    for case in cases:
        assert extract(case["text"])
        assert all(c.confidence == "provavel" for c in extract(case["text"]))
    for mode in ("present", "absent"):
        counts, _ = service_metrics(cases, tmp_path / mode, mode)
        assert counts["definitive"] == counts["gate_failures"] == 0, counts
        assert counts["probable"] >= len(cases)


def test_frozen_corpus12():
    pre = json.loads((FIXTURES / "prosa_audit_final12_preregistration.json").read_text(encoding="utf-8"))
    assert hashlib.sha256((FIXTURES / "prosa_audit_final12.jsonl").read_bytes()).hexdigest() == pre["corpus_sha256"]
    assert len(corpus12()) == pre["cases"]


@pytest.mark.parametrize("case", [c for c in corpus12() if c["id"] in {"N006", "N054", "N058"}], ids=lambda c: c["id"])
def test_missed_devices(case):
    cite, = extract(case["text"])
    assert identity(cite) == case["gold"][0]
    assert cite.confidence == "provavel"


@pytest.mark.parametrize("case", [c for c in corpus12() if c["id"] in {"N021", "N022", "N023", "N024", "N025", "N026", "N027", "N029"}], ids=lambda c: c["id"])
def test_private_predicates(case):
    cite, = extract(case["text"])
    assert cite.confidence == "provavel"
    assert "preferir_outro_referente" in cite.flags
    assert identity(cite, True) == case["gold"][0]


def test_deterministic_nonlegal_fuzz(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    cases = list(nonlegal_cases())
    assert cases == list(nonlegal_cases())
    assert len(cases) == len({r["text"] for r in cases}) == 2400
    assert len(Counter(c["group"] for c in cases)) == 12
    assert not [(r["id"], c) for r in cases for c in extract(r["text"]) if c.confidence == "exata"]
    # Indexar também qualquer obra proposta impede que falta de acervo mascare o erro.
    for mode in ("present", "absent"):
        counts, _ = service_metrics(cases, tmp_path / mode, mode)
        assert counts["false_definitive"] == counts["controls_definitive"] == counts["definitive"] == 0, counts


def test_corpus12_public_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    for mode in ("present", "absent"):
        counts, _ = service_metrics(corpus12(), tmp_path / mode, mode)
        assert counts["false_definitive"] == counts["controls_definitive"] == counts["gate_failures"] == 0, counts
