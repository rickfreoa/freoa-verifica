"""Recall de prosa sintética independente e segurança de associação."""
import json
from collections import Counter
from pathlib import Path

import pytest

from freoa_verifica.citation import extract
from freoa_verifica.service import Verifica
from tests.regression_expectations import prosa_expected


CORPUS = json.loads((Path(__file__).parent / "fixtures" / "prosa_extracao_r12.json").read_text(encoding="utf-8"))


def expected_key(row):
    return (tuple(row["work"]), row["path"], tuple(row["span"]), row["raw"])


def extracted_key(cite):
    work = cite.work
    identity = (work.authority, work.kind, work.number, work.year) if work else None
    return (identity, cite.path, cite.span, cite.raw)


def measure():
    """Microcontagem exata: identidade, dispositivo, offsets e superfície."""
    tp = fp = fn = identity_fp = quote_tp = quote_total = 0
    failures = []
    for case in CORPUS:
        cites = extract(case["text"])
        want = Counter(expected_key(row) for row in prosa_expected(case))
        got = Counter(extracted_key(cite) for cite in cites if not cite.flags)
        hits = sum((want & got).values())
        extra = sum((got - want).values()) + sum(bool(c.flags) for c in cites)
        missing = sum((want - got).values())
        tp += hits
        fp += extra
        fn += missing
        identities = Counter((k[0], k[1]) for k in want.elements())
        actual_identities = Counter(extracted_key(c)[:2] for c in cites)
        identity_fp += sum((Counter(k[0] for k in actual_identities.elements()) - Counter(k[0] for k in identities.elements())).values())
        if case["quote"]:
            quote_total += len(case["expected"])
            quote_tp += sum(Verifica._trecho_apos_aspas(case["text"], c.span[1]) == case["quote"] for c in cites)
        if extra or missing:
            failures.append({"id": case["id"], "text": case["text"], "tp": hits, "fp": extra, "fn": missing,
                             "actual": [extracted_key(c) for c in cites]})
    return dict(sentences=len(CORPUS), explicit_sentences=sum(c["category"] == "explicit" for c in CORPUS),
                tp=tp, fp=fp, fn=fn, precision=tp / (tp + fp), recall=tp / (tp + fn),
                identity_fp=identity_fp, quote_tp=quote_tp, quote_total=quote_total, failures=failures)


@pytest.mark.parametrize("case", CORPUS, ids=lambda case: case["id"])
def test_prosa(case):
    cites = extract(case["text"])
    assert not any(c.flags for c in cites)
    assert Counter(map(extracted_key, cites)) == Counter(map(expected_key, prosa_expected(case)))
    for cite in cites:
        assert case["text"][slice(*cite.span)] == cite.raw
        if case["quote"]:
            assert Verifica._trecho_apos_aspas(case["text"], cite.span[1]) == case["quote"]


def test_corpus_metrics():
    metrics = measure()
    assert metrics["explicit_sentences"] >= 80
    assert metrics["recall"] >= .95
    assert metrics["identity_fp"] == 0
    assert metrics["precision"] == 1


@pytest.fixture
def prosa_service(tmp_path, monkeypatch):
    from freoa_verifica.aliases import WorkKey
    from freoa_verifica.parsers.model import ParsedDocument, Provision, Redaction

    monkeypatch.setenv("FV_OFFLINE", "1")
    with Verifica(tmp_path / "home") as svc:
        provisions = [Provision(path, path, "", redactions=[Redaction(text, False, 0)])
                      for path, text in [("art116", "Regra primeira."), ("art117", "Regra segunda."),
                                         ("art118", "Regra terceira."),
                                         ("art116.parunico", "Regra particular.")]]
        svc.indexar_obra(source_id="planalto", work_key=WorkKey("federal", "lei", "6404", 1976),
                         document=ParsedDocument("test", "1", "Lei 6.404/1976", None, "Texto de teste.",
                                                 provisions=provisions),
                         body=b"captura sintetica", url="https://www.planalto.gov.br/test")
        yield svc


@pytest.mark.parametrize("separator", [":", ",", ":\n", ",\n"])
@pytest.mark.parametrize("quotes", [('"', '"'), ('“', '”'), ('«', '»'), ('‘', '’')])
def test_abbreviation_quote_confrontation(prosa_service, separator, quotes):
    text = ('Nos termos do art. 116, parágrafo único, da Lei das S.A.' + separator
            + quotes[0] + 'Regra particular.' + quotes[1])
    row, = prosa_service.verificar_texto(text)["citacoes"]
    assert row["citacao"].endswith("S.A.")
    assert row["trecho_conferido"] == "Regra particular."
    assert row["identity"]["status"] == row["text"]["status"] == "verified"


def test_list_each_provision_is_actually_checked(prosa_service):
    rows = prosa_service.verificar_texto('arts. 116, 117 e 118 da Lei das S.A.: “Regra segunda.”')["citacoes"]
    assert [r["caminho"] for r in rows] == ["art116", "art117", "art118"]
    assert [r["verificacao"]["citation"]["path"] for r in rows] == ["art116", "art117", "art118"]
    assert [r["text"]["status"] == "verified" for r in rows] == [False, True, False]


@pytest.mark.parametrize("case", [c for c in CORPUS if c["category"] == "remission"], ids=lambda c: c["id"])
def test_remission_does_not_inherit_identity(prosa_service, case):
    rows = prosa_service.verificar_texto(case["text"])["citacoes"]
    assert all(r["status"] != "inexistente" and r["caminho"] is None for r in rows)
    assert len(rows) == len(case["expected"])


def test_latest_snapshot_after_wheel_only_release(monkeypatch):
    from types import SimpleNamespace
    from freoa_verifica import snapshot
    from freoa_verifica.connectors import httputil

    url = "https://github.com/rickfreoa/freoa-verifica/releases/download/v1.0.0/freoa-verifica-snapshot-20261018.tar.gz"
    def fetch(request, **kwargs):
        latest = {"tag_name": "v1.0.2", "assets": [{"name": "freoa_verifica-1.0.2-py3-none-any.whl"}]}
        payload = latest if request.endswith("/latest") else [latest, {"tag_name": "v1.0.1", "assets": []},
                   {"tag_name": "v1.0.0", "assets": [{"name": "freoa-verifica-snapshot-20261018.tar.gz", "browser_download_url": url}]}]
        return SimpleNamespace(body=json.dumps(payload).encode())
    monkeypatch.setattr(snapshot, "_snapshots_oficiais", lambda: [{"arquivo": 'freoa-verifica-snapshot-20261018.tar.gz', "sha256": '0' * 64, "derived_version": 3}])
    monkeypatch.setattr(httputil, "connector_fetch", fetch)
    monkeypatch.setattr(snapshot, "_download_release", lambda found, **kwargs: found)
    assert snapshot._download_latest_release() == url


def test_read_only_verification_preserves_database(prosa_service, monkeypatch):
    import hashlib
    import sqlite3

    home = prosa_service.home
    prosa_service.close()
    database = home / "verifica.sqlite3"
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    monkeypatch.setenv("FV_READ_ONLY", "1")
    with Verifica(home) as svc:
        count = svc.conn.execute("SELECT count(*) FROM run").fetchone()[0]
        def no_capture(*args, **kwargs):
            raise AssertionError("consulta somente leitura tentou capturar documento")
        monkeypatch.setattr(svc, "_get", no_capture)
        rows = svc.verificar_texto('arts. 116, 117 e 118 da Lei das S.A.: “Regra segunda.”')["citacoes"]
        assert rows[1]["text"]["status"] == "verified"
        assert all(row["verificacao"]["run_id"] is None for row in rows)
        assert svc.conn.execute("SELECT count(*) FROM run").fetchone()[0] == count
        assert svc.verificar_texto('Lei 998877/2025')["citacoes"][0]["status"] == "indisponivel"
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            svc.conn.execute("DELETE FROM run")
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before


def test_read_only_does_not_create_home(tmp_path, monkeypatch):
    import sqlite3

    monkeypatch.setenv("FV_READ_ONLY", "1")
    home = tmp_path / "absent"
    with Verifica(home) as svc:
        with pytest.raises(sqlite3.OperationalError):
            svc.verificar_texto("Lei 6.404/1976")
    assert not home.exists()
