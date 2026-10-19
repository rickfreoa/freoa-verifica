"""Regressões de persistência, tempo, identidade e integridade."""

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import asyncio
import hashlib
import json

import pytest

from freoa_verifica.aliases import WorkKey
from freoa_verifica.parsers.model import Annotation, Issue, ParsedDocument, Provision, Redaction
from freoa_verifica.service import Verifica
from freoa_verifica.temporal import select
from freoa_verifica.transport import Response
from tests.fixture_util import load_fixture, load_meta


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if k != "run_id"}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


NORMAS = [k for k in load_meta() if k.startswith("planalto_") or k.endswith("consolid_docx") or k == "bcb_res_cmn_4966"]


@pytest.mark.parametrize("fixture", NORMAS)
def test_estabilidade_fixture_normativa(fixture, tmp_path, monkeypatch):
    from freoa_verifica.parsers.planalto import parse_planalto
    from freoa_verifica.parsers.cvm_docx import parse_cvm_docx
    from freoa_verifica.parsers.bcb_json import parse_bcb_json

    monkeypatch.setenv("FV_OFFLINE", "1")
    body = load_fixture(fixture)
    parse = parse_cvm_docx if fixture.endswith("docx") else parse_bcb_json if fixture.startswith("bcb") else parse_planalto
    document = parse(body)
    from freoa_verifica.identity import declared_identity
    actual_key, actual_date = declared_identity(document)
    assert actual_key is not None
    actual_date = actual_date or f"{actual_key.year:04}-01-01"
    with Verifica(tmp_path) as svc:
        rw = svc.indexar_obra(source_id="planalto", work_key=actual_key,
                             document=document, body=body, url="https://www.planalto.gov.br/fixture",
                             work_date=actual_date)
        # Caminhos de todas as recusas + primeiros/últimos dispositivos.
        paths = list(dict.fromkeys([p.path for p in document.provisions[:2] + document.provisions[-2:]] +
                                  document.ambiguous_paths + [i.path for i in document.issues if i.path]))
        def answers(service):
            result = []
            for path in paths:
                prov = document.provision(path)
                trecho = prov.redactions[-1].text if prov and prov.redactions else "texto"
                from freoa_verifica.verify import _result_to_json, verificar
                # A sintaxe pública não cobre todos os caminhos internos (anexos/subitens).
                for date in (None, "2001-01-01"):
                    result.append(service.obter_dispositivo(work_id=rw.work_id, caminho=path, data=date))
                # Verificação pública do artigo principal da fixture.
                result.append(service.verificar_citacao("art. 1 da Lei 99.991/2000", trecho=trecho))
            return clean(result)
        before = answers(svc)
    with Verifica(tmp_path) as reopened:
        rebuilt = reopened._resolve(rw.work_key)
        assert asdict(rebuilt.document) == asdict(document)
        assert rebuilt.work_date == actual_date
        assert answers(reopened) == before


@pytest.mark.parametrize("kind", ["revogado", "revogacao_parcial", "vide", "superseded", "ambiguous", "issue", "original"])
def test_estabilidade_recusas(kind, tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    red = Redaction("Art. 1 Texto original.", False, 4,
                    annotations=[] if kind in {"original", "superseded", "ambiguous", "issue"} else
                    [Annotation(kind, "nota", "Lei 2/2001", "/lei2", "2001-01-02")],
                    superseded_without_strike=kind == "superseded")
    doc = ParsedDocument("test", "1", "teste", None, red.text,
                         [Provision("art1", "Art. 1", "", redactions=[red], ambiguous=kind == "ambiguous")],
                         issues=[Issue("ORDER", "art1", "ordem", "provision")] if kind == "issue" else [])
    def answers(svc):
        return clean([svc.verificar_citacao("art. 1 da Lei 99.991/2000", trecho=red.text),
                      svc.obter_dispositivo("art. 1 da Lei 99.991/2000")])
    with Verifica(tmp_path) as svc:
        svc.indexar_obra(source_id="planalto", work_key=WorkKey("federal", "lei", "99991", 2000), document=doc,
                         body=b"synthetic", url="https://www.planalto.gov.br/test", work_date="2000-01-01")
        before = answers(svc)
    with Verifica(tmp_path) as svc:
        assert answers(svc) == before


def test_incomplete_persistence_unknown(verifica_populada):
    svc, rw, _ = verifica_populada
    svc.conn.execute("UPDATE parsed_document SET model_json=NULL WHERE capture_id=?", (rw.capture_id,))
    svc.conn.commit()
    svc._clear_caches()
    result = svc.verificar_citacao("art. 254-A da Lei 6.404/76", trecho="texto")
    assert result["identity"]["reason_code"] == "DADOS_PERSISTIDOS_INCOMPLETOS"
    assert result["text"]["status"] == "unknown"
    assert svc.obter_dispositivo("art. 254-A da Lei 6.404/76")["reason_code"] == "DADOS_PERSISTIDOS_INCOMPLETOS"


def test_successor_future_and_invalid_capture():
    p = Provision("art1", "Art. 1", "", redactions=[
        Redaction("antes", True, 0), Redaction("depois", False, 1,
        [Annotation("redacao_dada", "nota", "Lei 2/2099", act_date="2099-01-01")])])
    now = datetime.now(timezone.utc)
    r = select(p, work_date="2000-01-01", fetched_at=now.isoformat())
    assert r.redaction_id == "r0"
    p.redactions[1].annotations[0].act_date = "2099"
    assert select(p, work_date="2000-01-01", fetched_at=now.isoformat()).status == "unknown"
    r = select(p, fetched_at=(now + timedelta(minutes=6)).isoformat())
    assert r.status == "unknown" and r.reason == "CAPTURA_DATA_INVALIDA"


@pytest.mark.parametrize("mutation", ["missing_blob", "extra_nested", "extra_hidden", "outside", "corrupt_blob", "missing_db"])
def test_snapshot_inventory_complete(verifica_populada, tmp_path, mutation):
    svc, *_ = verifica_populada
    dest = tmp_path / "snapshot"
    assert svc.snapshot_export(dest)["status"] == "ok"
    blob = next(p for p in (dest / "blobs").rglob("*") if p.is_file())
    if mutation == "missing_blob":
        blob.unlink()
    elif mutation == "corrupt_blob":
        blob.write_bytes(b"corrupt")
    elif mutation == "missing_db":
        (dest / "verifica.sqlite3").unlink()
    elif mutation == "outside":
        manifest = json.loads((dest / "MANIFEST.json").read_text(encoding="utf-8"))
        manifest["arquivos_sha256"]["../outside"] = "0" * 64
        (dest / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    else:
        (dest / (".hidden" if mutation == "extra_hidden" else "blobs/extra")).write_bytes(b"extra")
    before = svc.conn.execute("SELECT COUNT(*) FROM capture").fetchone()[0]
    assert svc.snapshot_install(dest, aceitar_nao_vinculado=True)["status"] == "erro"
    assert svc.conn.execute("SELECT COUNT(*) FROM capture").fetchone()[0] == before


def test_cvm_resolve_fetch_parse_item2(monkeypatch):
    from freoa_verifica.connectors import cvm_colegiado as cvm
    body = b'<article><h2>ATA</h2><p class="text-uppercase">Assunto A PROC. 111</p><p>Texto primeiro.</p><p class="text-uppercase">Assunto B PROC. 222</p><p>Texto segundo.</p></article>'
    url = "https://conteudo.cvm.gov.br/decisoes/2026/20261014_R1.html"
    def fetch(url, **kwargs):
        return Response(url, url, 200, {}, body, hashlib.sha256(body).hexdigest(), "2026-10-17T00:00:00Z", [], "text/html")
    monkeypatch.setattr(cvm, "connector_fetch", fetch)
    connector = cvm.CvmColegiadoConnector()
    for key in ("reuniao=20261014-R1#2", url + "#2"):
        parsed = connector.parse(connector.fetch(connector.resolve(key)))
        assert parsed.official_id == "reuniao=20261014-R1#2"
        assert "segundo" in parsed.text and "primeiro" not in parsed.text and "PROC. 111" not in parsed.text
        assert parsed.metadata["related"]["ata"] == "reuniao=20261014-R1"


def test_decision_evidence_identity(tmp_path, monkeypatch):
    from freoa_verifica.connectors.base import Candidate, ParsedDecision, Unavailable
    from freoa_verifica.store import repo
    monkeypatch.setenv("FV_OFFLINE", "1")
    class Connector:
        id = "stj"
        def fetch(self, cand):
            if cand.key == "B":
                raise Unavailable("offline")
            body = b"decision A"
            return Response("https://www.stj.jus.br/A", "https://www.stj.jus.br/A", 200, {}, body,
                            hashlib.sha256(body).hexdigest(), datetime.now(timezone.utc).isoformat(), [], "text/plain")
        def parse(self, resp):
            return ParsedDecision("test", "acordao", "STJ", "A", ementa="ementa alfa", text="ementa alfa", class_name="REsp")
    with Verifica(tmp_path) as svc:
        for key, text in (("A", "ementa alfa"), ("B", "ementa beta")):
            svc._index_candidate_juris(Connector(), Candidate("stj", key, key, metadata={"court": "STJ", "classe": "REsp", "ementa": text}))
        result = svc.pesquisar_jurisprudencia("beta")
        assert result["status"] == "unavailable"
        assert result["reason_code"] == "EVIDENCIA_AUSENTE"
        result = svc.pesquisar_jurisprudencia("alfa")
        assert result["itens"][0]["capture_id"] is not None


def test_stf_textual_refuses_browser(monkeypatch):
    from freoa_verifica.connectors.stf import StfConnector
    from freoa_verifica.connectors.base import Unavailable
    with pytest.raises(Unavailable, match="stf_busca_textual_sob_waf"):
        StfConnector().search("consulta", browser=True)


def test_mcp_schemas_limits(tmp_path, monkeypatch):
    from freoa_verifica import mcp_server as ms
    monkeypatch.setattr(ms, "_servicos", {})
    mcp = ms.create_mcp(str(tmp_path))
    def check(schema):
        if schema.get("type") == "string":
            assert "maxLength" in schema, schema
        if schema.get("type") == "integer":
            assert "maximum" in schema and "minimum" in schema, schema
        if schema.get("type") == "array":
            assert "maxItems" in schema, schema
        for value in schema.values():
            if isinstance(value, dict):
                check(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        check(item)
    async def run():
        for tool in await mcp.list_tools():
            check(tool.input_schema)
    try:
        asyncio.run(run())
    finally:
        [v.close() for v in ms._servicos.values()]


@pytest.mark.parametrize("case", ["normal", "revogado", "revogacao_parcial", "vide", "ambiguous", "future", "future_year", "capture_future", "incomplete"])
def test_paridade_json_adversarial(case, tmp_path, monkeypatch, capsys):
    from freoa_verifica.cli import main
    from freoa_verifica import mcp_server as ms
    pytest.importorskip("fastapi")
    from freoa_verifica.rest import create_app
    from fastapi.testclient import TestClient

    monkeypatch.setenv("FV_OFFLINE", "1")
    monkeypatch.setenv("FV_HOME", str(tmp_path))
    ann = [] if case not in {"revogado", "revogacao_parcial", "vide"} else [Annotation(case, "nota")]
    red = Redaction("Art. 1 Texto original.", False, 0, ann)
    prov = Provision("art1", "Art. 1", "", redactions=[red], ambiguous=case == "ambiguous")
    if case in {"future", "future_year"}:
        red.struck = True
        prov.redactions.append(Redaction("Art. 1 Texto futuro.", False, 1,
                              [Annotation("redacao_dada", "nota", act_date="2099" if case == "future_year" else "2099-01-01")]))
    doc = ParsedDocument("test", "1", "teste", None, red.text, [prov])
    citation = "art. 1 da Lei 99.991/2000"
    now = datetime.now(timezone.utc) + (timedelta(days=1) if case == "capture_future" else timedelta())
    with Verifica(tmp_path) as svc:
        rw = svc.indexar_obra(source_id="planalto", work_key=WorkKey("federal", "lei", "99991", 2000),
                             document=doc, body=b"synthetic", url="https://www.planalto.gov.br/test",
                             work_date="2000-01-01", fetched_at=now.isoformat())
        if case == "incomplete":
            svc.conn.execute("UPDATE parsed_document SET model_json=NULL WHERE capture_id=?", (rw.capture_id,))
            svc.conn.commit()
            svc._clear_caches()
        monkeypatch.setitem(ms._servicos, str(svc.home), svc)
        mcp = ms.create_mcp(str(tmp_path))
        app = create_app(str(tmp_path))
        try:
            for trecho in (red.text, "Art. 1 Texto NAO original."):
                arguments = {"citacao": citation, "trecho": trecho}
                expected = clean(svc.verificar_citacao(**arguments))
                with pytest.raises(SystemExit) as exit_info:
                    main(["verifica", citation, "--trecho", trecho, "--json"])
                assert exit_info.value.code == 0
                assert clean(json.loads(capsys.readouterr().out)) == expected
                result = asyncio.run(mcp.call_tool("verificar_citacao", arguments))
                assert not result.is_error
                assert clean(result.structured_content) == expected
                with TestClient(app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1") as client:
                    response = client.post("/v1/verificacoes", json=arguments)
                    assert response.status_code == 200
                    assert clean(response.json()) == expected
                if case == "future_year":
                    assert expected["text"]["status"] == "unknown"
            text = f'{citation} "{red.text}"'
            expected_text = clean(svc.verificar_texto(text))
            input_path = tmp_path / "input.txt"
            input_path.write_text(text, encoding="utf-8")
            with pytest.raises(SystemExit):
                main(["verifica-texto", str(input_path), "--json"])
            assert clean(json.loads(capsys.readouterr().out)) == expected_text
            result = asyncio.run(mcp.call_tool("verificar_texto", {"texto": text}))
            assert not result.is_error
            assert clean(result.structured_content) == expected_text
            with TestClient(app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1") as client:
                response = client.post("/v1/verificacoes/texto", json={"texto": text})
                assert response.status_code == 200
                assert clean(response.json()) == expected_text
        finally:
            app.state.verifica.close()


def test_isolated_timeout_and_crash():
    from freoa_verifica.parsers import parse_isolated
    assert parse_isolated("planalto", b"<html><body>texto</body></html>", 0.00001).quarantined
    assert parse_isolated("bcb_json", b"not json", 20).quarantined


def test_empty_quarantined_document_survives_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    doc = ParsedDocument("test", "1", "vazio", None, "", issues=[Issue("TRUNCATED", None, "incompleto", "document")])
    with Verifica(tmp_path) as svc:
        svc.indexar_obra(source_id="planalto", work_key=WorkKey("federal", "lei", "99991", 2000),
                         document=doc, body=b"empty", url="https://www.planalto.gov.br/empty")
        before = clean(svc.verificar_citacao("Lei 99.991/2000"))
    with Verifica(tmp_path) as svc:
        assert clean(svc.verificar_citacao("Lei 99.991/2000")) == before
