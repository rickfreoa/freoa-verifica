"""A9: vínculo externo ao manifesto, persistência e compatibilidade de latest."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from freoa_verifica import snapshot, acervo, derivados
from freoa_verifica.service import Verifica


def pin(monkeypatch, archive):
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    monkeypatch.setattr(snapshot, "_snapshots_oficiais", lambda: [{
        "arquivo": archive.name, "sha256": digest, "derived_version": 3}])
    return digest


def test_published_pin():
    assert snapshot._snapshots_oficiais() == [
        {"arquivo": "freoa-verifica-snapshot-20261018-1.1.0.tar.gz",
         "sha256": "adaeca748fba9e3ad97f4459fad754f61ba337305383677b3655c7ea20c27119",
         "versao_pacote_min": "1.1.0", "derived_version": 3},
        {"arquivo": "freoa-verifica-snapshot-20261019-1.2.0.tar.gz",
         "sha256": "926a6eb7fcf25ca4b7c8ec37f2804b1b9a32232fc67b3770ca05c2e4d2acc4e7",
         "versao_pacote_min": "1.2.0", "derived_version": 4},
        {"arquivo": "freoa-verifica-snapshot-20261021-1.3.0.tar.gz",
         "sha256": "b6921f68289a61fb35647e51397f008bebf39b3e69329ddc1e158b762ffc7fde",
         "versao_pacote_min": "1.3.0", "derived_version": 5},
        {"arquivo": "freoa-verifica-snapshot-20261028-1.4.0a1.tar.gz",
         "sha256": "ad090c341b5e95c606309bff84ef9a233e144d223bcb5c6a40a9076dc3d8fafa",
         "versao_pacote_min": "1.4.0a1", "derived_version": 5}]


@pytest.mark.parametrize("packed", [True, False])
def test_unknown_refused_or_explicit_persistent(verifica_populada, tmp_path, packed):
    source, _, _ = verifica_populada
    export = tmp_path / ("snap.tar.gz" if packed else "snap")
    assert source.snapshot_export(export)["status"] == "ok"
    home = tmp_path / "target"
    with Verifica(home) as target:
        assert target.snapshot_install(export) == {"status": "erro", "motivo": "SNAPSHOT_NAO_VINCULADO"}
        assert not (home / acervo.MANIFESTO_LOCAL).exists()
        result = target.snapshot_install(export, aceitar_nao_vinculado=True)
        assert result["status"] == "ok" and result["vinculado"] is False
    with Verifica(home) as reopened:
        assert reopened.snapshot_info()["vinculado"] is False
        assert reopened.snapshot_info()["instalado"] is True
        check = next(c for c in reopened.doctor(offline=True)["verificacoes"] if c["nome"] == "snapshot_proveniencia")
        assert check["status"] == "alerta" and check["detalhe"]["vinculado"] is False
        assert json.loads((home / acervo.MANIFESTO_LOCAL).read_text())["vinculado"] is False


def test_official_binding_persists(verifica_populada, tmp_path, monkeypatch):
    source, _, _ = verifica_populada
    export = tmp_path / "snap.tar.gz"
    source.snapshot_export(export)
    digest = pin(monkeypatch, export)
    with Verifica(tmp_path / "target") as target:
        result = target.snapshot_install(export)
        assert result["status"] == "ok" and result["vinculado"] is True
        info = target.snapshot_info()
        assert info["derived_version"] == info["derived_version_atual"] == derivados.DERIVED_VERSION
        assert info["proveniencia"]["snapshot_sha256"] == digest
        assert info["vinculado"] is True


def test_manifest_cannot_claim_binding(verifica_populada, tmp_path):
    source, _, _ = verifica_populada
    export = tmp_path / "snap"
    source.snapshot_export(export)
    path = export / "MANIFEST.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["vinculado"] = True
    path.write_text(json.dumps(manifest), encoding="utf-8")
    from tests.test_r11 import reseal
    reseal(export)
    # A flag explícita não promove um diretório, mesmo se o manifesto alegar vínculo.
    with Verifica(tmp_path / "target") as target:
        assert target.snapshot_install(export, aceitar_nao_vinculado=True)["vinculado"] is False


def test_remote_digest_checked_before_extract(monkeypatch, tmp_path):
    from freoa_verifica.connectors import httputil
    body = b"not even tar"
    digest = hashlib.sha256(body).hexdigest()
    def fetch(url, **kw):
        if kw.get("sink"):
            Path(kw["sink"]).write_bytes(body)
        return SimpleNamespace(body=(digest + " file").encode(), sha256=digest)
    monkeypatch.setattr(httputil, "connector_fetch", fetch)
    monkeypatch.setattr(snapshot, "_extract_archive", lambda *a: pytest.fail("extraiu bytes nao vinculados"))
    with pytest.raises(ValueError, match="SNAPSHOT_NAO_VINCULADO"):
        snapshot._download_release("https://github.com/rickfreoa/freoa-verifica/releases/download/v1/snap.tar.gz")


def test_pinned_legacy_rebuild_before_publish(tmp_path, monkeypatch):
    from tests.test_c6_derivados import _home_legado, _snapshot_v102
    legacy = _home_legado(tmp_path)
    try:
        directory, _ = _snapshot_v102(tmp_path, legacy)
    finally:
        legacy.close()
    archive = tmp_path / "legacy.tar.gz"
    snapshot.pack_snapshot(directory, archive)
    pin(monkeypatch, archive)
    with Verifica(tmp_path / "target") as target:
        result = target.snapshot_install(archive)
        assert result["status"] == "ok", result
        assert result["vinculado"] is True
        assert "reconstruídos" in result["aviso"]
        info = target.snapshot_info()
        assert info["derived_version"] == derivados.DERIVED_VERSION
        assert info["proveniencia"]["snapshot_derived_version"] == 3
        assert not target.acervo_status()


def test_cli_requires_explicit_exception(verifica_populada, tmp_path, capsys):
    from freoa_verifica.cli import main
    source, _, _ = verifica_populada
    export = tmp_path / "snap.tar.gz"
    source.snapshot_export(export)
    args = ["--home", str(tmp_path / "cli"), "snapshot", "install", str(export), "--json"]
    with pytest.raises(SystemExit) as exit:
        main(args)
    assert exit.value.code == 1  # recusa não sai com sucesso; o JSON traz o motivo
    assert json.loads(capsys.readouterr().out)["motivo"] == "SNAPSHOT_NAO_VINCULADO"
    with pytest.raises(SystemExit) as exit:
        main(args + ["--aceitar-nao-vinculado"])
    assert exit.value.code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "ok" and result["vinculado"] is False
