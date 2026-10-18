"""Parser Planalto — LSA, leis alteradoras, CC e mutantes de sentinela."""

from __future__ import annotations

import pytest

from freoa_verifica.parsers.model import (
    AmbiguousProvision,
    QuarantinedDocument,
    RevokedProvision,
)
from freoa_verifica.parsers.paths import is_article_path
from freoa_verifica.parsers.planalto import parse_planalto
from tests.fixture_util import load_fixture

# Limite superior de ambiguous_paths por fixture (regressão).
_AMBIGUOUS_CAPS = {
    # art289.*: "Vigência encerrada" + texto novo sem nota de substituição
    "planalto_lei_6404_1976": 6,
    "planalto_lei_6385_1976": 0,
    # VETADO da alteradora vs republicações / resíduos de citação
    "planalto_lei_10303_2001": 12,
    "planalto_lei_10406_2002": 0,
    "planalto_lei_14195_2021": 0,
    "planalto_lei_14430_2022": 0,
}


def _current_arts(doc) -> list:
    return [
        p
        for p in doc.provisions
        if is_article_path(p.path) and any(not r.struck for r in p.redactions)
    ]


def _doc_blocking(doc):
    return [i for i in doc.issues if i.blocking_scope == "document"]


def test_lsa_art254a_and_structure():
    data = load_fixture("planalto_lei_6404_1976")
    doc = parse_planalto(
        data,
        base_url="https://www.planalto.gov.br/ccivil_03/leis/",
    )

    assert "6.404" in doc.title
    assert "1976" in doc.title
    assert not doc.quarantined, _doc_blocking(doc)
    assert len(doc.ambiguous_paths) <= _AMBIGUOUS_CAPS["planalto_lei_6404_1976"]

    text_254a = doc.current_text("art254-A")
    assert text_254a is not None
    assert text_254a.startswith(
        "A alienação, direta ou indireta, do controle de companhia aberta "
        "somente poderá ser contratada sob a condição, suspensiva ou resolutiva,"
    )
    prov = doc.provision("art254-A")
    assert prov is not None
    anns = [a for r in prov.redactions if not r.struck for a in r.annotations]
    assert any(
        a.kind == "incluido" and a.act_ref and "Lei nº 10.303, de 2001" in a.act_ref
        for a in anns
    )

    assert doc.provision("art254-A.par1") is not None
    assert doc.provision("art116.parunico") is not None

    par8 = doc.provision("art118.par8")
    assert par8 is not None
    cur = doc.current_text("art118.par8")
    assert cur is not None
    assert cur.startswith(
        "O presidente da assembléia ou do órgão colegiado"
    )

    found_pair = False
    for p in doc.provisions:
        if any(r.struck for r in p.redactions) and any(
            not r.struck for r in p.redactions
        ):
            found_pair = True
            break
    assert found_pair

    assert len(_current_arts(doc)) >= 300


def test_lei_6385_art2_incisos():
    data = load_fixture("planalto_lei_6385_1976")
    doc = parse_planalto(data)
    assert "6.385" in doc.title
    art2 = doc.provision("art2")
    assert art2 is not None
    incisos = [p for p in doc.provisions if p.path.startswith("art2.inc")]
    assert len(incisos) >= 2
    assert not doc.quarantined, _doc_blocking(doc)
    assert len(doc.ambiguous_paths) <= _AMBIGUOUS_CAPS["planalto_lei_6385_1976"]
    # Art. 7 / Art. 8 com "Art . N" devem ser reconhecidos
    assert doc.provision("art7") is not None
    assert doc.provision("art8") is not None


def test_lei_10303_quoted_amendment_254a():
    doc = parse_planalto(load_fixture("planalto_lei_10303_2001"))
    assert not doc.quarantined, _doc_blocking(doc)
    assert len(doc.ambiguous_paths) <= _AMBIGUOUS_CAPS["planalto_lei_10303_2001"]
    assert doc.amendments, "esperadas emendas citadas da Lei 6.404"
    hit = [
        a
        for a in doc.amendments
        if "254-A" in a.target_label.replace(" ", "")
        and "6.404" in a.target_ref_text
    ]
    assert hit, [(a.target_label, a.target_ref_text) for a in doc.amendments[:12]]
    assert "alienação" in hit[0].text.lower() or "alienacao" in hit[0].text.lower()


def test_lei_14195_no_document_quarantine():
    doc = parse_planalto(load_fixture("planalto_lei_14195_2021"))
    assert not doc.quarantined, _doc_blocking(doc)
    assert len(doc.ambiguous_paths) <= _AMBIGUOUS_CAPS["planalto_lei_14195_2021"]
    assert doc.amendments


def test_cc_and_14430_no_document_quarantine():
    for key in ("planalto_lei_10406_2002", "planalto_lei_14430_2022"):
        doc = parse_planalto(load_fixture(key))
        assert not doc.quarantined, (key, _doc_blocking(doc))
        assert len(doc.ambiguous_paths) <= _AMBIGUOUS_CAPS[key], (
            key,
            len(doc.ambiguous_paths),
            doc.ambiguous_paths[:20],
        )


def test_normative_fixtures_counts():
    """Registra contagens e garante quarentena só por escopo documento."""
    keys = [
        "planalto_lei_6404_1976",
        "planalto_lei_6385_1976",
        "planalto_lei_10303_2001",
        "planalto_lei_10406_2002",
        "planalto_lei_14195_2021",
        "planalto_lei_14430_2022",
    ]
    for key in keys:
        doc = parse_planalto(load_fixture(key))
        assert not doc.quarantined, (key, _doc_blocking(doc))
        assert len(doc.ambiguous_paths) <= _AMBIGUOUS_CAPS[key], (
            key,
            len(doc.ambiguous_paths),
            doc.ambiguous_paths[:25],
        )
        for i in doc.issues:
            if i.code in {"DUPLICATE_CURRENT", "ORDER"}:
                assert i.blocking_scope == "provision", (key, i)


def test_mutant_duplicate_current():
    data = load_fixture("planalto_lei_6385_1976")
    text = data.decode("cp1252")
    marker = "Art. 1"
    idx = text.find(marker)
    assert idx > 0
    p_start = text.rfind("<p", 0, idx)
    p_end = text.find("</p>", idx) + 4
    chunk = text[p_start:p_end]
    mutated = text[:p_end] + chunk + text[p_end:]
    doc = parse_planalto(mutated.encode("cp1252"))
    assert any(i.code == "DUPLICATE_CURRENT" for i in doc.issues)
    assert any(i.blocking_scope == "provision" for i in doc.issues if i.code == "DUPLICATE_CURRENT")
    # Quarentena granular: DUPLICATE não quarentena o documento
    assert not doc.quarantined
    assert doc.ambiguous_paths


def test_mutant_order():
    data = load_fixture("planalto_lei_6385_1976")
    text = data.decode("cp1252")
    inject = (
        '<p align="JUSTIFY">Art. 99. Dispositivo injetado para mutante de ordem.</p>'
    )
    idx = text.find("Art. 2")
    assert idx > 0
    p_start = text.rfind("<p", 0, idx)
    mutated = text[:p_start] + inject + text[p_start:]
    doc = parse_planalto(mutated.encode("cp1252"))
    assert any(i.code == "ORDER" for i in doc.issues)
    assert not doc.quarantined
    assert any(p.ambiguous for p in doc.provisions if "art2" in p.path or p.path == "art2")


def test_mutant_truncated():
    data = load_fixture("planalto_lei_6385_1976")
    half = data[: len(data) // 2]
    doc = parse_planalto(half)
    assert any(i.code == "TRUNCATED" for i in doc.issues)
    assert any(i.blocking_scope == "document" for i in doc.issues if i.code == "TRUNCATED")
    assert doc.quarantined
    with pytest.raises(QuarantinedDocument):
        doc.current_text("art1")


def test_editorial_chain_requires_explicit_substitution():
    """Três textos distintos de art1 sem cadeia editorial → ambiguous + accessor recusa."""
    html = """<html><body>
    <p>Art. 1º Texto alfa antigo.</p>
    <p>Art. 1º Texto beta intermediário.</p>
    <p>Art. 1º Texto gama vigente. (Incluído pela Lei nº 1, de 2000)</p>
    </body></html>"""
    doc = parse_planalto(html.encode("utf-8"))
    assert any(i.code == "DUPLICATE_CURRENT" for i in doc.issues)
    assert "art1" in doc.ambiguous_paths
    with pytest.raises(AmbiguousProvision):
        doc.current_text("art1")


def test_editorial_chain_ok_marks_superseded():
    """Cadeia: anterior sem nota + seguinte com Redação dada → sem DUPLICATE."""
    html = """<html><body>
    <p>Art. 1º Texto antigo sem nota.</p>
    <p>Art. 1º Texto novo oficial. (Redação dada pela Lei nº 2, de 2001)</p>
    </body></html>"""
    doc = parse_planalto(html.encode("utf-8"))
    assert not any(i.code == "DUPLICATE_CURRENT" and i.path == "art1" for i in doc.issues)
    prov = doc.provision("art1")
    assert prov is not None
    assert any(r.superseded_without_strike for r in prov.redactions)
    assert doc.current_text("art1").startswith("Texto novo oficial")


def test_revoked_accessor_raises():
    html = """<html><body>
    <p>Art. 5º (Revogado pela Lei nº 9, de 1999)</p>
    </body></html>"""
    doc = parse_planalto(html.encode("utf-8"))
    with pytest.raises(RevokedProvision):
        doc.current_text("art5")


def test_mixed_strike_splits_and_issues():
    html = """<html><body>
    <p>Art. 3º <strike>Permitido.</strike> Proibido.</p>
    </body></html>"""
    doc = parse_planalto(html.encode("utf-8"))
    prov = doc.provision("art3")
    assert prov is not None
    assert any(r.struck and "Permitido" in r.text for r in prov.redactions)
    assert any(not r.struck and "Proibido" in r.text for r in prov.redactions)
    assert any(i.code == "MIXED_STRIKE" and i.path == "art3" for i in doc.issues)
    assert "Permitido" not in (doc.current_text("art3") or "")
    assert "Proibido" in (doc.current_text("art3") or "")


def test_continuation_paragraph_aggregates():
    html = (
        "<html><body>"
        "<p>Art. 4o Primeira frase do caput.</p>"
        "<p>continuacao sem rotulo proprio no paragrafo seguinte.</p>"
        "</body></html>"
    )
    doc = parse_planalto(html.encode("utf-8"))
    text = doc.current_text("art4") or ""
    assert "Primeira frase" in text
    assert "continuacao sem rotulo" in text


def test_amendment_ends_at_blockquote_veto_is_host():
    """Após blockquote, Art. 2 (VETADO) da alteradora não vira emenda."""
    html = """<html><body>
    <p>Art. 1º A Lei nº 1.000, de 2000, passa a vigorar com a seguinte redação:</p>
    <blockquote>
    <p>"Art. 10. Texto citado da lei-alvo."</p>
    </blockquote>
    <p>Art. 2º (VETADO)</p>
    </body></html>"""
    doc = parse_planalto(html.encode("utf-8"))
    assert doc.provision("art2") is not None
    assert not any(
        a.target_label and "Art. 2" in a.target_label for a in doc.amendments
    )
    assert any("Art. 10" in a.target_label for a in doc.amendments)


def test_structural_change_orphans_annotation():
    html = """<html><body>
    <p>Art. 1º Dispositivo do corpo.</p>
    <p>ANEXO I</p>
    <p>(Incluído pela Lei nº 3, de 2002)</p>
    </body></html>"""
    doc = parse_planalto(html.encode("utf-8"))
    assert any(i.code == "ORPHAN_ANNOTATION" for i in doc.issues)
    art1 = doc.provision("art1")
    assert art1 is not None
    anns = [a for r in art1.redactions for a in r.annotations]
    assert not any(a.kind == "incluido" for a in anns)


def test_encoding_fallback_no_crash():
    # 0x81 é indefinido em cp1252 strict → cai para latin-1
    data = b"<html><body><p>Art. 1o texto \x81 x.</p></body></html>"
    doc = parse_planalto(data)
    assert any(i.code == "ENCODING_FALLBACK" for i in doc.issues)
    assert doc.provision("art1") is not None


def test_nesting_limit_quarantines():
    nested = "<div>" * 250 + "<p>Art. 1o fundo.</p>" + "</div>" * 250
    html = f"<html><body>{nested}</body></html>"
    doc = parse_planalto(html.encode("utf-8"))
    assert doc.quarantined
    assert any(i.code == "TRUNCATED" for i in doc.issues)


def test_hyphen_variants_planalto():
    html = (
        "<html><body>"
        "<p>Art. 70\u2013A. Com meia-risca.</p>"
        "<p>Art. 70\u2014B. Com travessao.</p>"
        "<p>Art. 70-C. Com hifen.</p>"
        "</body></html>"
    )
    doc = parse_planalto(html.encode("utf-8"))
    assert doc.provision("art70-A") is not None
    assert doc.provision("art70-B") is not None
    assert doc.provision("art70-C") is not None
    assert doc.current_text("art70-A") == "Com meia-risca."


def test_parse_isolated_smoke():
    from freoa_verifica.parsers import parse_isolated

    html = b"<html><body><p>Art. 1o Isolado.</p></body></html>"
    doc = parse_isolated("planalto", html, timeout=30)
    assert doc.provision("art1") is not None
    assert not doc.quarantined
