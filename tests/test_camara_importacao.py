"""C16: pares reais importados pelo instrumento; corrupção só em diretório temporário."""
import hashlib
import json
from pathlib import Path

import pytest

from freoa_verifica.captura import importar_fixture_offline

FIX = Path(__file__).parent / "fixtures"


def par(tmp_path, key="camara_robots_legin"):
    entry = json.loads((FIX / "FIXTURES.json").read_bytes())[key]
    meta = entry["importacao_offline"]["recibo_original"]
    receipt = tmp_path / "original.captura.json"
    receipt.write_text(json.dumps(meta), encoding="utf-8")
    body = tmp_path / meta["arquivo"]
    body.write_bytes((FIX / entry["file"]).read_bytes())
    target = tmp_path / "fixtures"
    target.mkdir()
    (target / "FIXTURES.json").write_text("{}", encoding="utf-8")
    return receipt, body, target


def test_c16_importacao_idempotente_sem_rede(tmp_path, monkeypatch):
    monkeypatch.setattr("freoa_verifica.captura.connector_fetch", lambda *a, **k: pytest.fail("rede"))
    r, b, dest = par(tmp_path)
    first = importar_fixture_offline(r, b, "robots", dest)
    before = {p: p.read_bytes() for p in dest.rglob("*") if p.is_file()}
    second = importar_fixture_offline(r, b, "robots", dest)
    assert first.meta() == second.meta()
    assert before == {p: p.read_bytes() for p in dest.rglob("*") if p.is_file()}
    assert first.capturado_em == json.loads(r.read_bytes())["capturado_em"]
    assert first.user_agent == "freoa-verifica/1.4.0a2 (+https://github.com/rickfreoa/freoa-verifica)"
    manifest = json.loads((dest / "FIXTURES.json").read_bytes())
    assert manifest["robots"]["metodo"] == "GET"
    assert manifest["robots"]["categoria"] == "captura_real"


@pytest.mark.parametrize("field,value", [
    ("sha256", "0" * 64), ("bytes", 1), ("categoria", "regressao"), ("status", 403),
    ("metodo", "POST"), ("unavailable", True), ("capturado_em", "2026-11-04"),
    ("url", "https://www2.camara.leg.br/admin"), ("content_type", "application/pdf"),
    ("user_agent", "Mozilla/5.0"), ("arquivo", "../fora.txt"),
])
def test_c16_recibo_divergente_recusado(tmp_path, field, value):
    r, b, dest = par(tmp_path)
    meta = json.loads(r.read_bytes())
    meta[field] = value
    r.write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises((ValueError, OSError)):
        importar_fixture_offline(r, b, "robots", dest)
    assert (dest / "FIXTURES.json").read_text() == "{}"


def test_c16_mutante_corpo_editado(tmp_path):
    r, b, dest = par(tmp_path)
    b.write_bytes(b.read_bytes() + b"X")
    with pytest.raises(ValueError, match="recibo_corpo_divergente"):
        importar_fixture_offline(r, b, "robots", dest)


def test_c16_manifesto_e_hashes_lote():
    manifest = json.loads((FIX / "FIXTURES.json").read_bytes())
    entries = [v for v in manifest.values() if v["file"].startswith("camara_legin/")]
    assert len(entries) == 34
    assert {e["file"] for e in entries} == {p.relative_to(FIX).as_posix() for p in (FIX / "camara_legin").iterdir()}
    for e in entries:
        raw = (FIX / e["file"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == e["sha256"]
        assert len(raw) == e["bytes"]


def test_c16_conteudo_exige_descoberta(tmp_path):
    r, b, dest = par(tmp_path, "camara_textos_atualizado_lei6404")
    with pytest.raises(ValueError, match="vinculo_ausente"):
        importar_fixture_offline(r, b, "texto", dest)


@pytest.mark.parametrize("mutacao", ["recibo", "manifesto_caminho", "manifesto_tamanho", "arquivo_ausente"])
def test_c16_reimportacao_nao_oculta_corrupcao(tmp_path, mutacao):
    r, b, dest = par(tmp_path)
    importar_fixture_offline(r, b, "robots", dest)
    manifest_path = dest / "FIXTURES.json"
    manifest = json.loads(manifest_path.read_bytes())
    if mutacao == "recibo":
        saved = dest / manifest["robots__captura"]["file"]
        saved.write_bytes(saved.read_bytes() + b" ")
    elif mutacao == "manifesto_caminho":
        manifest["robots"]["file"] = "../fora.txt"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    elif mutacao == "manifesto_tamanho":
        manifest["robots"]["bytes"] = 0
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    else:
        b.unlink()
    with pytest.raises((ValueError, OSError)):
        importar_fixture_offline(r, b, "robots", dest)
