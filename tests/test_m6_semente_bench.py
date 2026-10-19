"""Testes offline M6 — corpus semente, sync checkpoint, snapshot e bench."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from freoa_verifica.bench import markdown_table, run_bench
from freoa_verifica.semente import load_corpus, parse_act_ref
from freoa_verifica.service import Verifica
from freoa_verifica.store.db import connect


def test_corpus_semente_carrega():
    c = load_corpus()
    assert c["versao"] == 1
    assert len(c["planalto"]) >= 20
    assert "6404" in {str(x["numero"]) for x in c["planalto"]}
    assert c["cvm"]["instrucoes_historicas"] == [358, 361, 400, 476, 480, 481, 555, 472, 578]
    assert c["jurisprudencia"]["tcu_acordaos"] == 2000
    assert c["atribuicoes"]["stj"]


def test_parse_act_ref():
    assert parse_act_ref("Lei nº 10.303, de 2001") == ("LEI", "10303", 2001)
    assert parse_act_ref("Lei Complementar nº 182, de 2021") == ("LCP", "182", 2021)


def test_sync_state_migration(tmp_path):
    db = tmp_path / "t.sqlite3"
    conn = connect(db)
    try:
        versions = {r[0] for r in conn.execute("SELECT version FROM schema_version")}
        assert 3 in versions
        conn.execute(
            "INSERT INTO sync_state(id, fonte, chave, status) VALUES (?,?,?,?)",
            ("planalto:x", "planalto", "x", "parseado"),
        )
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM sync_state").fetchone()[0]
        assert n == 1
    finally:
        conn.close()


def test_snapshot_export_m6_artefatos(verifica_populada, tmp_path):
    svc, *_ = verifica_populada
    dest = tmp_path / "snap-m6"
    out = svc.snapshot_export(dest)
    assert out["status"] == "ok"
    assert (dest / "MANIFEST.json").is_file()
    assert (dest / "SHA256SUMS").is_file()
    assert (dest / "verifica.sqlite3").is_file()
    dbs = list(dest.glob("freoa-verifica-corpus-*.db"))
    assert dbs, "falta db datado"
    compact = list(dest.glob("freoa-verifica-corpus-*.db.gz")) + list(
        dest.glob("freoa-verifica-corpus-*.db.zst")
    )
    assert compact, "falta compactação"
    manifest = json.loads((dest / "MANIFEST.json").read_text(encoding="utf-8"))
    assert "cobertura_por_fonte" in manifest
    assert "atribuicoes" in manifest
    assert "autenticidade" in manifest
    assert "parser_version_por_capture" in manifest
    assert "run" not in manifest["tabelas"]
    assert "sync_state" not in manifest["tabelas"]
    assert "gh attestation" in manifest["autenticidade"].lower() or "attestation" in manifest[
        "autenticidade"
    ].lower()


def test_snapshot_install_anexacao_preserva_local(verifica_populada, tmp_path):
    svc, rw, _ = verifica_populada
    dest = tmp_path / "snap-merge"
    assert svc.snapshot_export(dest)["status"] == "ok"

    home2 = tmp_path / "home-local"
    home2.mkdir()
    with Verifica(home=home2) as svc2:
        # obra local distinta
        from freoa_verifica.aliases import WorkKey
        from freoa_verifica.parsers.model import ParsedDocument, Provision, Redaction

        local_doc = ParsedDocument(
            profile="test",
            parser_version="t-1",
            title="Local",
            ementa=None,
            text="texto local",
            provisions=[
                Provision(
                    path="art1",
                    label="art. 1",
                    scope="",
                    redactions=[Redaction(text="só local", struck=False, order=0)],
                )
            ],
        )
        svc2.indexar_obra(
            source_id="planalto",
            work_key=WorkKey("federal", "lei", "99901", 2099),
            document=local_doc,
            body=b"local-body",
            url="https://www.planalto.gov.br/ccivil_03/local.htm",
            label="Local 99901",
        )
        before = svc2.conn.execute("SELECT COUNT(*) FROM work").fetchone()[0]
        inst = svc2.snapshot_install(dest, aceitar_nao_vinculado=True)
        assert inst["status"] == "ok"
        assert inst.get("modo") == "anexacao"
        after = svc2.conn.execute("SELECT COUNT(*) FROM work").fetchone()[0]
        assert after >= before
        # captura local permanece
        local = svc2.conn.execute(
            "SELECT id FROM work WHERE number='99901'"
        ).fetchone()
        assert local is not None


def test_bench_mini_offline(verifica_populada, tmp_path):
    svc, *_ = verifica_populada
    gold = Path(__file__).parent / "fixtures" / "bench_mini.jsonl"
    rel = run_bench(svc, gold)
    assert rel["status"] == "ok"
    assert rel["total"] == 6
    m = rel["metricas"]
    assert m["mutantes"]["falsos_verified"] == 0
    assert m["positivos"]["total"] == 2
    # pelo menos identity verified no positivo com obra indexada
    assert m["positivos"]["identity_verified"] >= 1
    md = markdown_table(rel)
    assert "Benchmark" in md
    assert "Falsos" in md or "falsos" in md.lower() or "text=verified" in md

    # CLI
    from freoa_verifica.cli import main

    out_dir = tmp_path / "bench-out"
    try:
        main(["--home", str(svc.home), "bench", "--gold", str(gold), "--saida", str(out_dir)])
    except SystemExit as exc:
        assert exc.code in (0, None)
    assert (out_dir / "bench-report.json").is_file()
    assert (out_dir / "bench-report.md").is_file()


def test_sync_semente_offline_respeita_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    home = tmp_path / "sync-home"
    home.mkdir()
    with Verifica(home=home) as svc:
        # sem rede: deve marcar indisponíveis, não abortar
        rel = svc.sincronizar(semente=True, fontes=["planalto"], max_itens=2)
        assert rel["modo"] == "semente"
        assert "fontes" in rel
        # checkpoint gravado
        n = svc.conn.execute("SELECT COUNT(*) FROM sync_state").fetchone()[0]
        assert n >= 1
        # segunda chamada idempotente (pula ou reafirma)
        rel2 = svc.sincronizar(semente=True, fontes=["planalto"], max_itens=2)
        assert rel2["modo"] == "semente"


def test_cli_sync_semente_flags():
    from freoa_verifica.cli import build_parser

    p = build_parser()
    args = p.parse_args(["sync", "--semente", "--fontes", "planalto", "bcb", "--max-itens", "5"])
    assert args.semente is True
    assert args.fontes_flag == ["planalto", "bcb"]
    assert args.max_itens == 5
    args2 = p.parse_args(["snapshot", "export", "--saida", "dist/snapshot"])
    assert args2.saida == "dist/snapshot"
    args3 = p.parse_args(["snapshot", "install", "--arquivo", "x", "--url", "https://github.com/x"])
    assert args3.arquivo == "x"
    assert args3.url.startswith("https://")
