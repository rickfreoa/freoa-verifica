"""Rodada 5 (auditor Codex): A7 por documento (012), status com falha de fonte, orçamento na busca inicial."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from freoa_verifica import derivados
from freoa_verifica.aliases import WorkKey
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.parsers.model import ParsedDocument, Provision, Redaction
from freoa_verifica.service import Verifica

KEY = WorkKey("federal", "lei", "9999", 2000)


def _doc(*textos):
    provs = [Provision(f"art{i}", f"art{i}", "", redactions=[Redaction(t, False, 0, [])])
             for i, t in enumerate(textos, 1)]
    return ParsedDocument("synthetic", "9999", "Lei 9.999/2000", None, "x", provisions=provs, issues=[])


def _indexar(s, doc, corpo, quando, alvo="fts_redaction", src="planalto"):
    return s.indexar_obra(source_id=src, work_key=KEY, document=doc, body=corpo,
                          url="https://example.invalid/s", label="Lei 9.999/2000",
                          fetched_at=quando, fts_alvo=alvo)


def test_a7_012_marca_por_documento_obra_com_canonica_e_candidata(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()
    t1 = datetime(2026, 2, 1, tzinfo=timezone.utc).isoformat()
    with Verifica(tmp_path) as s:
        a = _indexar(s, _doc("texto A"), b"A", t0)
        b = _indexar(s, _doc("texto A", "texto B exclusivo"), b"B", t1, alvo="fts_staging")
        with s.conn:  # reproduz o home versão 9: sem marca, B só no staging
            s.conn.execute("ALTER TABLE parsed_document DROP COLUMN candidato_ao_vivo")
            s.conn.execute("DELETE FROM schema_version WHERE version>=10")
            s.conn.execute("DELETE FROM fts_redaction")
            s.conn.execute("DELETE FROM fts_staging")
            s.conn.execute("INSERT INTO fts_redaction(text, rubrica, work_label, path) VALUES "
                           "('texto A', NULL, 'Lei 9.999/2000', 'art1')")
            s.conn.execute("INSERT INTO fts_staging(text, work_label, path) VALUES "
                           "('texto B exclusivo', 'Lei 9.999/2000', 'art2')")
    with Verifica(tmp_path) as s:  # migra 010, 011, 012
        marcas = dict(s.conn.execute("SELECT capture_id, candidato_ao_vivo FROM parsed_document").fetchall())
        assert marcas == {a.capture_id: 0, b.capture_id: 1}
        with s.conn:
            derivados.reindexar_fts(s.conn)
        assert s.conn.execute("select count(*) from fts_redaction where text like '%exclusivo%'").fetchone()[0] == 0
        off = s.buscar_legislacao("exclusivo", fonte="__somente_local__")
        assert not [i for i in off["itens"] if not i.get("candidato_ao_vivo")]
        assert s.buscar_legislacao("texto A", fonte="__somente_local__")["itens"][0]["candidato_ao_vivo"] is False
        with s.conn:  # idempotente
            s.conn.execute("DELETE FROM schema_version WHERE version=12")
    with Verifica(tmp_path) as s:
        assert s.conn.execute("select count(*) from parsed_document where candidato_ao_vivo=1").fetchone()[0] == 1


class _Falha:
    id = "cvm_normas"

    def search(self, q, **f):
        raise Unavailable("http_503")


class _Lento:
    id = "cvm_normas"

    def search(self, q, **f):
        time.sleep(0.4)
        return []


def test_legislacao_fonte_falha_nao_volta_ok(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as s:
        monkeypatch.setattr(s, "_get", lambda _id: _Falha())
        out = s.buscar_legislacao("fato relevante", fonte="cvm_normas")
        assert out["status"] == "indisponivel" and out["motivo"] == "http_503" and out["itens"] == []


def test_legislacao_falha_com_itens_locais_e_parcial(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as s:
        _indexar(s, _doc("texto A"), b"A", datetime.now(timezone.utc).isoformat(), src="cvm_normas")
        monkeypatch.setattr(s, "_get", lambda _id: _Falha())
        out = s.buscar_legislacao("texto", fonte="cvm_normas")
        assert out["itens"] and out["status"] == "parcial"


def test_normas_e_juris_fonte_falha(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as s:
        monkeypatch.setattr(s, "_get", lambda _id: _Falha())
        assert s.buscar_normas_cvm("x")["status"] == "indisponivel"
        assert s.buscar_normas_bcb("x")["status"] == "indisponivel"
        j = s.pesquisar_jurisprudencia("acordo de acionistas", tribunais=["stj"])
        assert j["itens"] == [] and j["status"] == "indisponivel" and j["motivo"] == "http_503"


def test_orcamento_cobre_a_busca_inicial(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as s:
        monkeypatch.setattr(s, "_get", lambda _id: _Lento())
        t = time.monotonic()
        out = s._buscar_normas("cvm_normas", "x", None, orcamento_s=0.03)
        assert time.monotonic() - t < 0.2
        assert out["status"] == "indisponivel" and out["motivo"] == "orcamento"
