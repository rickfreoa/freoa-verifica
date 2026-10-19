"""Fluxos offline de retomada, contexto dos alteradores e distribuição."""

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

import pytest

from freoa_verifica.aliases import WorkKey
from freoa_verifica.connectors.base import Candidate, Unavailable
from freoa_verifica.parsers.model import Annotation, ParsedDocument, Provision, Redaction
from freoa_verifica.semente import SementeSync
from freoa_verifica.service import Verifica
from freoa_verifica.transport import Response


def document(text="Art. 1 Texto original."):
    return ParsedDocument("fixture", "1", "teste", None, text,
                          [Provision("art1", "Art. 1", "", redactions=[Redaction(text, False, 0)])])


class LegisConnector:
    id = "planalto"
    def __init__(self):
        self.failed = True
        self.calls = 0
    def resolve(self, key):
        return Candidate(self.id, str(key["numero"]), "teste", "https://www.planalto.gov.br/fixture")
    def fetch(self, cand):
        self.calls += 1
        if self.failed:
            raise Unavailable("transitorio")
        body = cand.key.encode()
        return Response(cand.url, cand.url, 200, {}, body, hashlib.sha256(body).hexdigest(),
                        datetime.now(timezone.utc).isoformat(), [], "text/plain")
    def parse(self, response):
        return document()


def test_sync_retry_and_checkpoint(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        connector = LegisConnector()
        svc._connectors["planalto"] = connector
        engine = SementeSync(svc, fontes=["planalto"], max_itens=1, rate_delay=0)
        engine.corpus["planalto"] = [{"tipo": "LEI", "numero": "99991", "ano": 2000}]
        first = engine.run()
        assert first["fontes"][0]["indisponiveis"] == 1
        connector.failed = False
        assert engine.run()["fontes"][0]["parseados"] == 1
        before = connector.calls
        engine.run()
        assert connector.calls == before
        assert svc.conn.execute("SELECT COUNT(*) FROM capture").fetchone()[0] == 1


def test_offline_sync_never_calls_connector(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    with Verifica(tmp_path) as svc:
        def forbidden(*args):
            pytest.fail("rede em modo offline")
        monkeypatch.setattr(svc, "_get", forbidden)
        result = svc.sincronizar(semente=True, max_itens=1)
        assert len(result["fontes"]) == 7
        assert all(f["motivos"] == {"offline": 1} for f in result["fontes"])


def test_alterador_context_survives_restart(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    doc = document()
    for red in doc.provisions[0].redactions:
        red.annotations = [Annotation("redacao_dada", "nota", "Lei 2, de 2001", act_date="2001")]
    with Verifica(tmp_path) as svc:
        rw = svc.indexar_obra(source_id="planalto", work_key=WorkKey("federal", "lei", "6404", 1976),
                             document=doc, body=b"parent", url="https://www.planalto.gov.br/parent")
        class Connector(LegisConnector):
            def resolve_alterador_date(self, *args):
                return "2001-01-02"
            def parse(self, resp):
                return document("Art. 1 Esta lei entra em vigor na data de sua publicação.")
        connector = Connector()
        connector.failed = False
        svc._connectors["planalto"] = connector
        engine = SementeSync(svc, rate_delay=0)
        engine._resolve_alteradores("LEI:6404:1976", document=doc)
        assert doc.provisions[0].redactions[0].annotations[0].act_date == "2001-01-02"
        before = dict(rw.amending_act_texts)
        assert "publicação" in before["Lei 2, de 2001"]
    with Verifica(tmp_path) as svc:
        rebuilt = svc._resolve(rw.work_key)
        assert rebuilt.amending_act_texts == before
        assert asdict(rebuilt.document) == asdict(doc)


def test_snapshot_same_work_remaps_and_reopens(verifica_populada, tmp_path):
    svc, rw, doc = verifica_populada
    dest = tmp_path / "snapshot"
    assert svc.snapshot_export(dest)["status"] == "ok"
    local_home = tmp_path / "local"
    with Verifica(local_home) as local:
        local_rw = local.indexar_obra(source_id="planalto", work_key=rw.work_key, document=doc,
                                     body=b"local", url="https://www.planalto.gov.br/local")
        assert local_rw.work_id != rw.work_id
        result = local.snapshot_install(dest, aceitar_nao_vinculado=True)
        assert result["status"] == "ok", result
        assert local.conn.execute("PRAGMA foreign_key_check").fetchone() is None
        assert local.conn.execute("SELECT COUNT(*) FROM work").fetchone()[0] == 1
        assert local.conn.execute("SELECT COUNT(*) FROM capture").fetchone()[0] == 2
        assert local._resolve(rw.work_key).work_id == local_rw.work_id
        assert local.buscar_legislacao("alienação", fonte="__somente_local__")["resultados"]


def test_snapshot_rollback_on_blob_copy_failure(verifica_populada, tmp_path, monkeypatch):
    svc, *_ = verifica_populada
    dest = tmp_path / "snapshot"
    assert svc.snapshot_export(dest)["status"] == "ok"
    from freoa_verifica import snapshot
    original = snapshot.shutil.copy2
    home = tmp_path / "new-home"
    with Verifica(home) as local:
        def fail(src, dst, *args, **kwargs):
            if "merged-blobs" in Path(dst).parts:
                raise OSError("simulated failure")
            return original(src, dst, *args, **kwargs)
        monkeypatch.setattr(snapshot.shutil, "copy2", fail)
        result = local.snapshot_install(dest, aceitar_nao_vinculado=True)
        assert result["status"] == "erro" and not result["rollback"]
        assert local.conn.execute("SELECT COUNT(*) FROM work").fetchone()[0] == 0
        assert local.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_snapshot_zip_and_traversal(verifica_populada, tmp_path):
    svc, *_ = verifica_populada
    dest = tmp_path / "snapshot"
    assert svc.snapshot_export(dest)["status"] == "ok"
    archive = Path(shutil.make_archive(str(tmp_path / "snapshot-bundle"), "zip", dest))
    with Verifica(tmp_path / "zip-home") as local:
        assert local.snapshot_install(archive, aceitar_nao_vinculado=True)["status"] == "ok"
        with zipfile.ZipFile(archive, "a") as z:
            z.writestr("../outside", b"forbidden")
        assert local.snapshot_install(archive, aceitar_nao_vinculado=True)["status"] == "erro"
        assert not (tmp_path / "outside").exists()


def test_bench_denominators_and_gold_preserved(tmp_path):
    from freoa_verifica.bench import run_bench
    class Service:
        def verificar_citacao(self, citation, trecho=None):
            return {"identity": {"status": "verified"},
                    "text": {"status": "divergent" if trecho else "not_assessed",
                             "evidence": [{"trecho_oficial": "texto oficial", "url": "https://www.planalto.gov.br/test"}]}}
        def verificar_texto(self, text):
            return {"citacoes": []}
    cases = [{"id": "p1", "tipo": "positivo", "citacao": "lei", "trecho": "texto errado"},
             {"id": "p2", "tipo": "positivo", "citacao": "lei"},
             {"id": "m1", "tipo": "mutante", "citacao": "lei"},
             {"id": "d1", "tipo": "decisao", "texto": "nao e citacao", "decisao_real": False}]
    path = tmp_path / "gold.jsonl"
    path.write_text("\n".join(json.dumps(c) for c in cases), encoding="utf-8")
    before = path.read_bytes()
    report = run_bench(Service(), path)
    assert path.read_bytes() == before
    assert report["metricas"]["positivos"]["com_trecho"] == 1
    assert report["metricas"]["positivos"]["total"] == 2
    assert report["metricas"]["mutantes"]["falsos_verified"] == 1
    assert report["metricas"]["decisoes"]["acertos"] == 0
    assert len(report["gold_suspeitos"]) == 1


def test_cvm_seed_paginates_all_categories(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        calls = []
        captured = []
        class Connector:
            def search(self, q, *, tipo, limite, pagina):
                calls.append((tipo, pagina))
                size = 500 if pagina == 1 else 1
                return [Candidate("cvm_normas", f"{tipo}:{pagina}:{i}", "teste") for i in range(size)]
        svc._connectors["cvm_normas"] = Connector()
        engine = SementeSync(svc, rate_delay=0)
        engine.corpus["cvm"]["instrucoes_historicas"] = []
        monkeypatch.setattr(engine, "_capture_cvm_cand", lambda conn, cand: captured.append(cand.key))
        engine.sync_cvm()
        assert calls == [("resolucoes", 1), ("resolucoes", 2), ("pareceres-orientacao", 1), ("pareceres-orientacao", 2)]
        assert len(set(captured)) == 1002


def test_stj_seed_uses_recent_monthly_corpus_organs(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        calls = []
        class Connector:
            db_path = tmp_path / "absent.db"
            def sync(self, **kwargs):
                calls.append(kwargs)
                return 0
        svc._connectors["stj"] = Connector()
        engine = SementeSync(svc, max_itens=2, rate_delay=0)
        engine.sync_stj()
        assert len(calls) == 1
        assert calls[0]["desde"] is None
        assert len(calls[0]["orgaos"]) == 7  # 1.1.0: sete órgãos não criminais
        assert all(c["max_itens"] == 2 for c in calls)
        engine.sync_stj()
        assert len(calls) == 1


def test_colegiado_seed_captures_each_item(tmp_path, monkeypatch):
    from freoa_verifica.connectors import cvm_colegiado as cvm
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    year = datetime.now().year
    url = f"https://conteudo.cvm.gov.br/decisoes/{year}/{year}1014_R1.html"
    body = b'<article><h2>ATA</h2><p class="text-uppercase">Assunto A PROC. 111</p><p>Texto primeiro.</p><p class="text-uppercase">Assunto B PROC. 222</p><p>Texto segundo.</p></article>'
    def fetch(url, **kwargs):
        return Response(url, url, 200, {}, body, hashlib.sha256(body).hexdigest(),
                        datetime.now(timezone.utc).isoformat(), [], "text/html")
    monkeypatch.setattr(cvm, "connector_fetch", fetch)
    connector = cvm.CvmColegiadoConnector()
    monkeypatch.setattr(connector, "search", lambda q, **kw: [connector.resolve(url)])
    with Verifica(tmp_path) as svc:
        svc._connectors["cvm_colegiado"] = connector
        engine = SementeSync(svc, rate_delay=0)
        engine.corpus["jurisprudencia"]["cvm_colegiado_desde"] = year
        engine.sync_cvm_colegiado()
        # 1.2.0: deliberação integral da ata (inteiro_teor) + assunto (ementa), por item.
        assert svc.conn.execute("SELECT COUNT(*) FROM decision_document").fetchone()[0] == 4

        for n, word in ((1, "primeiro"), (2, "segundo")):
            result = svc.obter_decisao(f"reuniao={year}1014-R1#{n}", parte="inteiro_teor")
            assert word in result["texto"] and result["parte_entregue"] == "inteiro_teor"
        engine.sync_cvm_colegiado()
        assert svc.conn.execute("SELECT COUNT(*) FROM decision_document").fetchone()[0] == 4  # sem duplicar


@pytest.mark.parametrize("kind,number,year,tipo", [("lei_complementar", "182", 2021, "LCP"),
                                                   ("decreto_lei", "4657", 1942, "DEL"),
                                                   ("constituicao", "1988", 1988, "CF")])
def test_seed_canonical_planalto_kinds(tmp_path, kind, number, year, tipo):
    from freoa_verifica.connectors.planalto import PlanaltoConnector
    class Connector(PlanaltoConnector):
        def resolve(self, key):
            assert key["tipo"] == tipo
            candidate = super().resolve(key)
            assert candidate is not None
            return candidate
        def fetch(self, candidate):
            raise Unavailable("fixture_offline")
    with Verifica(tmp_path) as svc:
        svc._connectors["planalto"] = Connector()
        engine = SementeSync(svc, rate_delay=0)
        status, _ = engine._index_legis("planalto", "fixture", connector_id="planalto",
                                      work_key=WorkKey("federal", kind, number, year), label="teste")
        assert status == "indisponivel"
        assert engine.state.get("planalto", "fixture")["motivo"] == "fixture_offline"
