"""Instalação transacional: falhas preservam banco e todas as evidências locais."""
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from freoa_verifica import snapshot
from freoa_verifica.connectors.base import Candidate, ParsedDecision
from freoa_verifica.service import Verifica
from freoa_verifica.store import repo
from freoa_verifica.transport import Response


def seed(svc, key):
    body = json.dumps([{"id": key, "ementa": "acordo acionista " + key}]).encode()
    url = "https://dadosabertos.web.stj.jus.br/dataset/recurso.json"
    response = Response(url, url, 200, {}, body, hashlib.sha256(body).hexdigest(),
                        "2026-10-18T00:00:00Z", [], "application/json")
    connector = SimpleNamespace(id="stj", authority="STJ", fetch=lambda _: response,
        parse=lambda _: ParsedDecision("stj_espelho", "acordao", "STJ", key,
            ementa="acordo acionista " + key, text="Negado.", class_name="REsp"))
    svc._index_candidate_juris(connector, Candidate("stj", key, "REsp"))


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file() and not p.name.endswith(("-wal", "-shm"))
            and ".fv-uso" not in p.parts and p.name != ".fv.lock"}  # travas de uso (1.2.0) são transitórias


def reseal(export):
    path = export / "MANIFEST.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for name in manifest["arquivos_sha256"]:
        manifest["arquivos_sha256"][name] = hashlib.sha256((export / name).read_bytes()).hexdigest()
    manifest["db_sha256"] = manifest["arquivos_sha256"][manifest["db_arquivo"]]
    raw = json.dumps(manifest).encode()
    path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    (export / "MANIFEST.sha256").write_text(digest, encoding="ascii")
    sums = {**manifest["arquivos_sha256"], "MANIFEST.json": digest}
    (export / "SHA256SUMS").write_text(
        "".join(f"{v}  {k}\n" for k, v in sorted(sums.items())), encoding="utf-8")


def route(export, mode, tmp_path, monkeypatch):
    if mode == "directory":
        return export
    archive = tmp_path / "freoa-verifica-snapshot-test.tar.gz"
    snapshot.pack_snapshot(export, archive)
    if mode == "file":
        return archive
    # Exercita o download, checksum e extração reais; só o transporte é simulado.
    from freoa_verifica.connectors import httputil
    url = "https://github.com/rickfreoa/freoa-verifica/releases/download/v1/" + archive.name
    def fetch(address, **kw):
        if "/releases/tags/v" in address:
            return SimpleNamespace(body=json.dumps({"assets": [{"name": archive.name,
                "browser_download_url": url}]}).encode())
        if address.endswith(".sha256"):
            return SimpleNamespace(body=Path(str(archive) + ".sha256").read_bytes())
        assert address == url
        shutil.copyfile(archive, kw["sink"])
        return SimpleNamespace(sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
    monkeypatch.setattr(snapshot, "_snapshots_oficiais", lambda: [{"arquivo": archive.name,
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "derived_version": 3}])
    monkeypatch.setattr(httputil, "connector_fetch", fetch)
    return None


STAGES = ("validation", "reconstruction", "blob_copy", "fts", "db_backup",
          "blob_backup", "db_swap", "blob_swap", "after_swap", "reopen")


@pytest.mark.parametrize("mode", ["directory", "file", "release"])
@pytest.mark.parametrize("stage", STAGES)
def test_install_failure_preserves_all_local_evidence(tmp_path, monkeypatch, mode, stage):
    monkeypatch.setenv("FV_OFFLINE", "1")
    export = tmp_path / "export"
    with Verifica(tmp_path / "source") as source:
        seed(source, "incoming")
        assert snapshot.export_snapshot(source.conn, source.home, export)["status"] == "ok"
    origin = route(export, mode, tmp_path, monkeypatch)
    with Verifica(tmp_path / "target") as target:
        for key in ("local-one", "local-two", "local-three"):
            seed(target, key)
        # Evidência não referenciada pelo snapshot também deve sobreviver.
        extra = target.home / "blobs" / "local" / "evidence.bin"
        extra.parent.mkdir()
        extra.write_bytes(b"local evidence outside incoming inventory")
        target.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        before = hashes(target.home)
        rows = [tuple(r) for r in target.conn.execute("SELECT * FROM capture ORDER BY id")]
        before_transient = {p.name: p.read_bytes() for p in target.home.iterdir() if p.is_file()}
        calls = []
        def fail():
            calls.append(stage)
            raise OSError("injected_" + stage)
        if stage == "validation":
            monkeypatch.setattr(snapshot, "_verify_sums", lambda *a: "injected_validation")
            calls.append(stage)
        elif stage == "reconstruction":
            original = snapshot._restore_stj_ementas
            def restore(*args):
                original(*args)
                fail()
            monkeypatch.setattr(snapshot, "_restore_stj_ementas", restore)
        elif stage == "fts":
            original = repo.rebuild_decision_index
            def rebuild(conn):
                original(conn)
                # Falha no índice do banco final mesclado, após reconstruir o snapshot.
                if conn.execute("SELECT COUNT(*) FROM decision").fetchone()[0] > 1:
                    fail()
            monkeypatch.setattr(repo, "rebuild_decision_index", rebuild)
        elif stage == "blob_copy":
            original = snapshot.shutil.copy2
            def copy(src, dst, *a, **kw):
                result = original(src, dst, *a, **kw)
                if ("merged-blobs" in Path(dst).parts
                        and not Path(src).is_relative_to(target.home) and not calls):
                    fail()
                return result
            monkeypatch.setattr(snapshot.shutil, "copy2", copy)
        elif stage in ("db_backup", "blob_backup", "db_swap", "blob_swap"):
            original = snapshot.os.replace
            def replace(src, dst):
                src, dst = Path(src), Path(dst)
                hit = ((stage == "db_backup" and dst.name.startswith("verifica.sqlite3.bak-")) or
                       (stage == "blob_backup" and dst.name.startswith("blobs.bak-")) or
                       (stage == "db_swap" and src.name == "merged.sqlite3") or
                       (stage == "blob_swap" and src.name == "merged-blobs"))
                if hit and not calls:
                    fail()
                return original(src, dst)
            monkeypatch.setattr(snapshot.os, "replace", replace)
        elif stage == "after_swap":
            original = target._clear_caches
            def clear():
                if not calls:
                    fail()
                original()
            monkeypatch.setattr(target, "_clear_caches", clear)
        elif stage == "reopen":
            original = snapshot.connect
            def connect(path):
                if Path(path) == target._db_path and not calls:
                    fail()
                return original(path)
            monkeypatch.setattr(snapshot, "connect", connect)
        result = snapshot.install_snapshot(target, origin, aceitar_nao_vinculado=True)
        assert calls == [stage]
        assert result["status"] == "erro" and "injected_" + stage in result["motivo"]
        assert "rollback_error" not in result and "reopen_error" not in result
        if stage in ("validation", "reconstruction", "blob_copy", "fts"):
            # Inclui WAL/SHM: uma falha anterior à troca não fecha nem muda o destino.
            assert before_transient == {p.name: p.read_bytes() for p in target.home.iterdir() if p.is_file()}
            assert not result.get("rollback", False)
        target.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        assert hashes(target.home) == before  # presença E hash de cada arquivo, inclusive banco
        assert rows == [tuple(r) for r in target.conn.execute("SELECT * FROM capture ORDER BY id")]
        assert target.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert target.conn.execute("SELECT COUNT(*) FROM decision").fetchone()[0] == 3
        assert not list(tmp_path.glob("fv-snap-*"))


def test_stj_failed_reconstruction_preserves_existing_blobs(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    export = tmp_path / "export"
    with Verifica(tmp_path / "source") as source:
        seed(source, "incoming")
        assert snapshot.export_snapshot(source.conn, source.home, export)["status"] == "ok"
    manifest = json.loads((export / "MANIFEST.json").read_text(encoding="utf-8"))
    db = sqlite3.connect(export / manifest["db_arquivo"])
    with db:
        db.execute("UPDATE decision SET official_id='absent-in-capture'")
    db.close()
    reseal(export)
    with Verifica(tmp_path / "target") as target:
        for key in ("local-one", "local-two", "local-three"):
            seed(target, key)
        target.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        before = hashes(target.home)
        result = snapshot.install_snapshot(target, export, aceitar_nao_vinculado=True)
        assert result["status"] == "erro"
        assert result["motivo"] == "stj_documento_ausente_no_recurso"
        assert result["rollback"] is False
        assert hashes(target.home) == before


def test_success_keeps_complete_backup_and_combines_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    export = tmp_path / "export"
    with Verifica(tmp_path / "source") as source:
        seed(source, "incoming")
        assert snapshot.export_snapshot(source.conn, source.home, export)["status"] == "ok"
    with Verifica(tmp_path / "target") as target:
        seed(target, "local")
        target.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        before = hashes(target.home)
        result = snapshot.install_snapshot(target, export, aceitar_nao_vinculado=True)
        assert result["status"] == "ok"
        assert hashlib.sha256(Path(result["backup"]).read_bytes()).hexdigest() == before["verifica.sqlite3"]
        assert hashes(Path(result["backup_blobs"])) == {
            name.removeprefix("blobs/"): value for name, value in before.items() if name.startswith("blobs/")}
        assert target.conn.execute("SELECT COUNT(*) FROM capture").fetchone()[0] == 2
        assert len(target.pesquisar_jurisprudencia("acionista", tribunais=["stj"])["itens"]) == 2
