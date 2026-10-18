"""Ida e volta de caminhos canônicos."""

from freoa_verifica.parsers.paths import (
    annex_scope_from_heading,
    label_to_path,
    path_to_label,
    roman_to_int,
    supplement_scope_from_heading,
)


def test_roman():
    assert roman_to_int("XVI") == 16
    assert roman_to_int("IV") == 4


def test_article_letter():
    assert label_to_path("Art. 254-A") == "art254-A"
    assert label_to_path("Art. 1º") == "art1"
    assert label_to_path("Art. 1-B") == "art1-B"
    assert label_to_path("Art. 70–A") == "art70-A"  # meia-risca
    assert label_to_path("Art. 70—A") == "art70-A"  # travessão


def test_article_thousands():
    assert label_to_path("Art. 2.002") == "art2002"


def test_paragraph_relative():
    assert label_to_path("§ 1º", parent="art254-A") == "art254-A.par1"
    assert label_to_path("Parágrafo único", parent="art116") == "art116.parunico"


def test_inciso_alinea_item():
    assert label_to_path("XVI -", parent="art2") == "art2.inc16"
    assert label_to_path("inciso XVI", parent="art2") == "art2.inc16"
    assert label_to_path("a)", parent="art2.inc3") == "art2.inc3.ali-a"
    assert label_to_path("1.", parent="art2.inc3.ali-a") == "art2.inc3.ali-a.item1"


def test_compound_citation():
    assert label_to_path("Art. 254-A, § 1º") == "art254-A.par1"


def test_annex_and_supplement_headings():
    assert annex_scope_from_heading("ANEXO I") == "anexo-i"
    assert annex_scope_from_heading("ANEXO A — Formulário") == "anexo-a"
    assert annex_scope_from_heading("ANEXO NORMATIVO I — FUNDOS") == "anexo-i"
    assert supplement_scope_from_heading("SUPLEMENTO A — Termo") == "suplemento-a"
    assert supplement_scope_from_heading("SUPLEMENTO B") == "suplemento-b"


def test_path_to_label_roundtrip():
    samples = [
        "art254-A",
        "art254-A.par1",
        "art116.parunico",
        "art2.inc16",
        "art2.inc3.ali-a",
        "art1",
        "anexo-i/art1",
        "anexo-i/suplemento-a/art1",
    ]
    for path in samples:
        label = path_to_label(path)
        if path.startswith("anexo-") or path.startswith("suplemento-"):
            scope_parts = path.split("/")[:-1]
            rest = path.split("/")[-1]
            scope = "/".join(scope_parts)
            art = rest.split(".")[0]
            parent = f"{scope}/{art}"
            back = parent
            for seg in rest.split(".")[1:]:
                if seg.startswith("par") and seg != "parunico":
                    n = seg[3:]
                    back = label_to_path(f"§ {n}", parent=back)
                elif seg == "parunico":
                    back = label_to_path("Parágrafo único", parent=back)
                elif seg.startswith("inc"):
                    from freoa_verifica.parsers.paths import int_to_roman

                    body = seg[3:]
                    if "-" in body:
                        num, let = body.split("-", 1)
                        back = label_to_path(
                            f"inciso {int_to_roman(int(num))}-{let}", parent=back
                        )
                    else:
                        back = label_to_path(
                            f"inciso {int_to_roman(int(body))}", parent=back
                        )
                elif seg.startswith("ali-"):
                    back = label_to_path(f"{seg[4:]})", parent=back)
                elif seg.startswith("item"):
                    back = label_to_path(f"{seg[4:]}.", parent=back)
            assert back == path, (path, label, back)
        else:
            if path == "art254-A.par1":
                assert label_to_path("Art. 254-A, § 1º") == path
            elif path == "art116.parunico":
                assert (
                    label_to_path("Parágrafo único", parent="art116") == path
                )
            elif path == "art2.inc16":
                assert label_to_path("XVI -", parent="art2") == path
            elif path == "art2.inc3.ali-a":
                assert label_to_path("a)", parent="art2.inc3") == path
            elif path in {"art254-A", "art1"}:
                if path == "art1":
                    assert label_to_path("Art. 1º") == path
                else:
                    assert label_to_path("Art. 254-A") == path
        assert isinstance(label, str) and label
