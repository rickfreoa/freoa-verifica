"""Auditoria 1.2.0 (B1): snapshot não vinculado anexado continua marcando o acervo."""
import hashlib
from freoa_verifica import snapshot, acervo
from freoa_verifica.service import Verifica

def test_b1_nao_vinculado_e_permanente_apos_anexacao(verifica_populada, tmp_path, monkeypatch):
    source, _, _ = verifica_populada
    unbound = tmp_path / "unbound.tar.gz"; source.snapshot_export(unbound)
    home = tmp_path / "target"
    with Verifica(home) as t:
        r1 = t.snapshot_install(unbound, aceitar_nao_vinculado=True)
        assert r1["status"] == "ok" and r1["vinculado"] is False
        n_unbound = t.conn.execute("SELECT COUNT(*) FROM work").fetchone()[0]
    # agora um snapshot "oficial" (pin sintético) anexado por cima
    official = tmp_path / "official.tar.gz"; source.snapshot_export(official)
    d = hashlib.sha256(official.read_bytes()).hexdigest()
    monkeypatch.setattr(snapshot, "_snapshots_oficiais", lambda: [{"arquivo": official.name, "sha256": d, "derived_version": 3}])
    with Verifica(home) as t:
        r2 = t.snapshot_install(official)

        info = t.snapshot_info()

        doc = next(c for c in t.doctor(offline=True)["verificacoes"] if c["nome"] == "snapshot_proveniencia")

        assert info["vinculado"] is False and r2["vinculado"] is False
        assert r2.get("vinculo_motivo") == "ACERVO_CONTEM_SNAPSHOT_NAO_VINCULADO"
        assert doc["status"] != "ok"


import json
import pytest


@pytest.mark.parametrize("cenario", ["manifesto_1_1_sem_chave", "sem_manifesto"])
def test_b1_upgrade_e_home_sem_manifesto_nao_viram_vinculados(verifica_populada, tmp_path, monkeypatch, cenario):
    source, _, _ = verifica_populada
    unbound = tmp_path / "unbound.tar.gz"; source.snapshot_export(unbound)
    home = tmp_path / "alvo"
    with Verifica(home) as t:
        assert t.snapshot_install(unbound, aceitar_nao_vinculado=True)["status"] == "ok"
    mf = home / acervo.MANIFESTO_LOCAL
    if cenario == "sem_manifesto":
        mf.unlink()
    else:  # manifesto como a 1.1 gravava: sem a chave "vinculado"
        data = json.loads(mf.read_text(encoding="utf-8")); data.pop("vinculado", None); data.pop("vinculo_motivo", None)
        mf.write_text(json.dumps(data), encoding="utf-8")
    official = tmp_path / "official.tar.gz"; source.snapshot_export(official)
    d = hashlib.sha256(official.read_bytes()).hexdigest()
    monkeypatch.setattr(snapshot, "_snapshots_oficiais", lambda: [{"arquivo": official.name, "sha256": d, "derived_version": 3}])
    with Verifica(home) as t:
        r = t.snapshot_install(official)
        assert r["status"] == "ok" and r["vinculado"] is False
        assert r["vinculo_motivo"] == "ACERVO_PREEXISTENTE_SEM_VINCULO"
        assert t.snapshot_info()["vinculado"] is False


def test_b1_home_vazio_com_snapshot_oficial_e_vinculado(verifica_populada, tmp_path, monkeypatch):
    source, _, _ = verifica_populada
    official = tmp_path / "official.tar.gz"; source.snapshot_export(official)
    d = hashlib.sha256(official.read_bytes()).hexdigest()
    monkeypatch.setattr(snapshot, "_snapshots_oficiais", lambda: [{"arquivo": official.name, "sha256": d, "derived_version": 3}])
    with Verifica(tmp_path / "vazio") as t:
        r = t.snapshot_install(official)
        assert r["vinculado"] is True and "vinculo_motivo" not in r
        assert t.snapshot_install(official)["vinculado"] is True  # reinstalação oficial sobre vinculado mantém
