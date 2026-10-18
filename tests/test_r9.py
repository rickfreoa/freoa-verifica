"""Regressões de pesquisa do acervo instalado e reconstrução de índices."""
import hashlib
import json
import sqlite3
from types import SimpleNamespace

import pytest

from freoa_verifica.connectors.base import Candidate, ParsedDecision
from freoa_verifica.service import Verifica
from freoa_verifica.snapshot import export_snapshot, install_snapshot
from freoa_verifica.store import repo
from freoa_verifica.transport import Response


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    with Verifica(tmp_path / "source") as svc:
        for court in ("STJ", "TCU", "CVM"):
            for n, (date, cls) in enumerate((("2020-01-01", "REsp"),
                                           ("2024-01-01", "REsp"),
                                           ("2024-01-01", "sumula"))):
                text = "acordo de acionistas e tag along. " + "Fundamentação. " * 60
                body = text.encode()
                url = f"https://example.org/{court}/{n}"
                response = Response(url, url, 200, {}, body, hashlib.sha256(body).hexdigest(),
                                    "2026-10-18T00:00:00Z", [], "text/plain")
                parsed = ParsedDecision("fixture", "acordao", court, f"{court}-{n}",
                    ementa="acordo de acionistas", text=text, class_name=cls,
                    judgment_date=date, organ="Turma", rapporteur="Relator",
                    metadata={"documento": "inteiro_teor"})  # 1.2.0: integral só por declaração
                connector = SimpleNamespace(id=court.lower(), authority=court, hosts={"example.org"},
                    fetch=lambda _, r=response: r, parse=lambda _, p=parsed: p)
                svc._index_candidate_juris(connector, Candidate(court.lower(), f"{court}-{n}", "Acórdão"))
        yield svc


def test_export_install_searchable_all_courts(corpus, tmp_path):
    export = tmp_path / "export"
    assert export_snapshot(corpus.conn, corpus.home, export)["status"] == "ok"
    manifest = json.loads((export / "MANIFEST.json").read_text(encoding="utf-8"))
    db = sqlite3.connect(export / manifest["db_arquivo"])
    try:
        assert db.execute("SELECT COUNT(*) FROM fts_decision").fetchone()[0] == 9
    finally:
        db.close()
    with Verifica(tmp_path / "installed") as target:
        assert install_snapshot(target, export)["status"] == "ok"
        for court in ("stj", "tcu", "cvm"):
            result = target.pesquisar_jurisprudencia("acionistas", tribunais=[court])
            assert len(result["itens"]) == 3
            assert {i["tribunal"] for i in result["itens"]} == {court.upper()}
            assert all(i["capture_id"] and i["url_oficial"] for i in result["itens"])
        # Reinstalação não duplica decisões nem páginas.
        assert install_snapshot(target, export)["status"] == "ok"
        assert len(target.pesquisar_jurisprudencia("acionistas")["itens"]) == 9


def test_filters_ranking_cursor_and_fulltext(corpus):
    repo.rebuild_decision_index(corpus.conn)
    corpus.conn.commit()
    result = corpus.pesquisar_jurisprudencia("tag along", tribunais=["stj"],
        desde="2024-01-01", ate="2024-12-31", autoridade_min="D", limite=1)
    assert len(result["itens"]) == 1
    assert result["itens"][0]["rotulo_autoridade"] == "A"
    assert result["cursor"]
    second = corpus.pesquisar_jurisprudencia("tag along", tribunais=["stj"],
        desde="2024-01-01", ate="2024-12-31", autoridade_min="D", limite=1,
        cursor=result["cursor"])
    assert second["itens"][0]["rotulo_autoridade"] == "D"
    assert second["itens"][0]["id"] != result["itens"][0]["id"]
    assert second["cursor"] is None
    assert not corpus.pesquisar_jurisprudencia("tag along", tribunais=["tcu"], autoridade_min="D")["itens"]
    assert not corpus.pesquisar_jurisprudencia("tag along", desde="2030-01-01")["itens"]
    assert not corpus.pesquisar_jurisprudencia("tag along", ate="2010-01-01")["itens"]


def test_local_precedes_network_and_skips_non_textual(corpus, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "0")
    def fail(*args, **kwargs):
        raise AssertionError("rede não deve ser consultada")
    monkeypatch.setattr(corpus, "_get", fail)
    assert len(corpus.pesquisar_jurisprudencia("acionistas", tribunais=["stj"], limite=2)["itens"]) == 2


def test_legacy_empty_index_install(corpus, tmp_path):
    export = tmp_path / "legacy"
    assert export_snapshot(corpus.conn, corpus.home, export)["status"] == "ok"
    manifest_path = export / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    db_path = export / manifest["db_arquivo"]
    db = sqlite3.connect(db_path)
    with db:
        db.execute("DELETE FROM fts_decision")
    db.close()
    digest = hashlib.sha256(db_path.read_bytes()).hexdigest()
    manifest["db_sha256"] = digest
    manifest["arquivos_sha256"][db_path.name] = digest
    raw = json.dumps(manifest).encode()
    manifest_path.write_bytes(raw)
    mhash = hashlib.sha256(raw).hexdigest()
    (export / "MANIFEST.sha256").write_text(mhash, encoding="ascii")
    sums = {**manifest["arquivos_sha256"], "MANIFEST.json": mhash}
    (export / "SHA256SUMS").write_text("".join(f"{v}  {k}\n" for k, v in sorted(sums.items())), encoding="utf-8")
    with Verifica(tmp_path / "repaired") as target:
        assert install_snapshot(target, export)["status"] == "ok"
        assert len(target.pesquisar_jurisprudencia("acionistas")["itens"]) == 9


def test_authority_filter_ignores_stale_persisted_label(corpus):
    # Rótulo antigo não pode contrariar os atributos e a regra atual da resposta.
    with corpus.conn:
        corpus.conn.execute("UPDATE decision SET authority_label='A' WHERE court IN ('TCU','CVM')")
    assert not corpus.pesquisar_jurisprudencia("acionistas", tribunais=["cvm", "tcu"], autoridade_min="D")["itens"]


@pytest.mark.parametrize("court", ["stj", "tcu", "stf"])
def test_no_live_search_for_local_or_non_textual_connectors(corpus, monkeypatch, court):
    from freoa_verifica.connectors.base import get_connector
    monkeypatch.setenv("FV_OFFLINE", "0")
    connector = get_connector(court)
    def fail(*args, **kwargs):
        raise AssertionError("busca ao vivo indevida")
    monkeypatch.setattr(connector, "search", fail)
    monkeypatch.setattr(corpus, "_get", lambda _: connector)
    result = corpus.pesquisar_jurisprudencia("termoausente", tribunais=[court])
    assert result["itens"] == []
    assert result["fontes"][court]["motivo"] == "busca_textual_ao_vivo_nao_suportada"


def test_date_breaks_tie_and_cursor_has_no_duplicates(corpus):
    repo.rebuild_decision_index(corpus.conn)
    corpus.conn.commit()
    found = []
    cursor = None
    while True:
        page = corpus.pesquisar_jurisprudencia("acionistas", tribunais=["stj"], limite=1, cursor=cursor)
        found.extend(page["itens"])
        cursor = page["cursor"]
        if cursor is None:
            break
    assert len({i["id"] for i in found}) == len(found) == 3
    assert [i["rotulo_autoridade"] for i in found] == ["A", "D", "D"]
    assert [i["datas"]["julgamento"] for i in found] == ["2024-01-01", "2024-01-01", "2020-01-01"]


def test_legacy_stj_ementa_recovered_from_authenticated_json(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    text = "Acordo de acionistas e tag along na ementa oficial."
    record = {"id": "documento-1", "ementa": text, "decisao": "Negaram provimento."}
    body = json.dumps([record]).encode()
    url = "https://dadosabertos.web.stj.jus.br/dataset/recurso.json"
    response = Response(url, url, 200, {}, body, hashlib.sha256(body).hexdigest(),
                        "2026-10-18T00:00:00Z", [], "application/json")
    connector = SimpleNamespace(id="stj", authority="STJ", hosts={"dadosabertos.web.stj.jus.br"},
        fetch=lambda _: response,
        parse=lambda _: ParsedDecision("stj_espelho", "acordao", "STJ", "documento-1",
                                       ementa=text, text=record["decisao"], class_name="REsp"))
    with Verifica(tmp_path / "original") as source:
        source._index_candidate_juris(connector, Candidate("stj", "documento-1", "REsp"))
        saved = source.conn.execute("SELECT text FROM decision_document WHERE kind='ementa'").fetchone()[0]
        assert saved == text  # Novas capturas preservam a ementa distinta do dispositivo.
        with source.conn:
            source.conn.execute("UPDATE decision_document SET text=?", (record["decisao"],))
            source.conn.execute("DELETE FROM fts_decision")
        export = tmp_path / "export"
        assert export_snapshot(source.conn, source.home, export)["status"] == "ok"
    with Verifica(tmp_path / "target") as target:
        assert install_snapshot(target, export)["status"] == "ok"
        result = target.pesquisar_jurisprudencia("tag along", tribunais=["stj"])
        assert result["itens"][0]["ementa"] == text
        assert target.conn.execute("SELECT COUNT(*) FROM decision_document").fetchone()[0] == 2


def test_fulltext_remains_searchable_when_ementa_is_empty(corpus):
    with corpus.conn:
        corpus.conn.execute("UPDATE decision_document SET text='' WHERE kind='ementa'")
        repo.rebuild_decision_index(corpus.conn)
    result = corpus.pesquisar_jurisprudencia("tag along")
    assert len(result["itens"]) == 9
    assert {item["nivel_prova"] for item in result["itens"]} == {"inteiro_teor_capturado"}
