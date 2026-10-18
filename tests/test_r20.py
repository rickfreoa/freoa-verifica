"""Fronteiras técnicas e abstenção diante de dispositivo não associado."""
import pytest

from freoa_verifica.citation import extract
from tests.test_r17 import service_metrics


@pytest.mark.parametrize("device", ["art. 117.txt", "art. 5.pdf", "art_7", "art-9",
    "art. 117.csv", "art. 5_json", "art. 5-99", "art. 5.html", "art. 5-A.pdf",
    "item 5.pdf", "§ 5.pdf", "inciso II.pdf", "alínea a.pdf"])
@pytest.mark.parametrize("template", ["{device} da Lei 6.404/1976.", "Lei 6.404/1976, {device}."])
def test_technical_device_has_no_path(device, template):
    cite, = extract(template.format(device=device))
    assert cite.path is None
    assert cite.confidence == "provavel"


@pytest.mark.parametrize("text", [
    "O art. 352 pertence à Lei 13.105/2015, segundo a remissão da ficha.",
    "Da Lei 6.404/1976, remeto expressamente ao art. 267.",
    "O artigo 352 remete expressamente à Lei 13.105/2015.",
    "Lei 6.404/1976: confira depois o inciso II.",
])
def test_unattached_label_requires_review(text):
    cite, = extract(text)
    assert cite.confidence == "provavel"


@pytest.mark.parametrize("field", ["etiqueta", "SKU", "código", "lote", "chave", "arquivo", "ticker", "placa"])
@pytest.mark.parametrize("value", ["CC, art. 114", "CPC, art. 115", "CF, art. 5", "CC", "CF", "CPC"])
@pytest.mark.parametrize("template", ["{field}: {value}", '{field} "{value}"',
    "{field} `{value}`", "{field} é “{value}”", 'A {field} tem o texto "{value}"'])
def test_field_value_requires_review(field, value, template):
    cites = extract(template.format(field=field, value=value))
    assert cites and all(c.confidence == "provavel" for c in cites)


@pytest.mark.parametrize("text,path", [("CC, art. 114", "art114"),
    ("Lei 6.404/1976, art. 254-A.", "art254-A"),
    ("art. 1.142 do CC.", "art1142"), ("CF, art. 5º.", "art5")])
def test_legal_form_stays_exact(text, path):
    cite, = extract(text)
    assert (cite.path, cite.confidence) == (path, "exata")


def test_review_gate_in_both_stores(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    cases = [dict(id=str(i), text=text, gold=[]) for i, text in enumerate([
        "O art. 352 pertence à Lei 13.105/2015.",
        "Da Lei 6.404/1976, remeto expressamente ao art. 267.",
        "Lei 6.404/1976, art. 117.txt.", 'etiqueta: "CC, art. 114"',
    ])]
    for mode in ("present", "absent"):
        metrics, _ = service_metrics(cases, tmp_path / mode, mode)
        assert metrics["probable"] == len(cases)
        assert metrics["definitive"] == metrics["gate_failures"] == 0
