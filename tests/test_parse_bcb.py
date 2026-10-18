"""Parser BCB JSON — Resolução CMN 4.966."""

from __future__ import annotations

from freoa_verifica.parsers.bcb_json import parse_bcb_json
from freoa_verifica.parsers.paths import is_article_path
from tests.fixture_util import load_fixture


def test_bcb_res_cmn_4966():
    data = load_fixture("bcb_res_cmn_4966")
    doc = parse_bcb_json(data)
    assert "4.966" in doc.title or "4966" in doc.title
    assert doc.ementa
    assert len(doc.provisions) > 0
    arts = [p for p in doc.provisions if is_article_path(p.path)]
    assert len(arts) >= 10
    blocking = [
        i
        for i in doc.issues
        if i.code in {"DUPLICATE_CURRENT", "ORDER", "TRUNCATED"}
    ]
    assert not blocking, blocking
    assert not doc.quarantined
