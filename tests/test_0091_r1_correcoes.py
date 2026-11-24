"""Correções da auditoria Codex r1 (0091A): um teste por achado, reproduzindo as provas do parecer."""
from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

import pytest

from freoa_verifica.aliases import WorkKey
from freoa_verifica import bateria
from freoa_verifica import derivados
from freoa_verifica import revalidacao as rev
from freoa_verifica.citation import extract, parse_one
from freoa_verifica.connectors import planalto
from freoa_verifica.identity import declared_identity
from freoa_verifica.mcp_server import _wrap_dispositivo_resposta, _wrap_oficial
from freoa_verifica.parsers.model import Annotation, ParsedDocument, Provision, Redaction
from freoa_verifica.parsers.planalto import parse_planalto
from freoa_verifica.service import Verifica
from freoa_verifica.verify import pode_negar
from tests.test_0091_cf_entrega import KEY, T0, _ORFA, _html

CF = WorkKey("federal", "constituicao", "1988", 1988)


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")


# ------------------------------------------------------------------ achado 1: artigo órfão rejeitado contamina descendentes

def test_r1_orfa_artigo_rejeitado_bloqueia_atribuicao_errada(tmp_path):
    html = _html(
        "<p>Art. 1 Cabe:</p>"
        + _ORFA.format("Art. 2 rege o caso.")
        + "<p>§ 1 Outro parágrafo.</p><p>Art. 3 Outro artigo.</p>"
    )
    doc = parse_planalto(html, base_url="https://example.invalid/l9999.htm")
    paths = {p.path for p in doc.provisions}
    assert "art2" not in paths
    assert any(i.code == "DISPOSITIVO_FORA_DA_ARVORE" for i in doc.issues)

    svc = Verifica(home=tmp_path)
    svc.indexar_obra(
        source_id="planalto",
        work_key=KEY,
        document=doc,
        body=html,
        url="https://example.invalid/l9999.htm",
        label="Lei 9.999/2000",
        fetched_at=T0,
        content_type="text/html; charset=utf-8",
    )
    res = svc.verificar_citacao("art. 1, § 1 da Lei 9.999/2000", trecho="Outro parágrafo.")
    assert res["text"]["status"] != "verified"
    res2 = svc.verificar_citacao("art. 2, § 1 da Lei 9.999/2000", trecho="qualquer")
    assert res2["text"]["status"] in ("not_found", "unknown")


# ------------------------------------------------------------------ achado 2: fonte composta com <br> gera sentinela

def test_r1_fonte_composta_com_br_impede_negativa_e_emite_issue():
    html = _html("<p>Art. 1º Compete:</p>" + _ORFA.format("I - julgar<br>II - processar.") + "<p>Art. 2º Outro.</p>")
    doc = parse_planalto(html, base_url="https://example.invalid/l9999.htm")
    assert any(i.code == "DISPOSITIVO_FORA_DA_ARVORE" for i in doc.issues)

    class _RW:
        capture_id, quarantined, source_id, caminhos_conhecidos = "c", False, "planalto", frozenset()
        document = doc

    assert pode_negar(_RW(), "art1.inc2") == "ESTRUTURA_INCOMPLETA"


# ------------------------------------------------------------------ achado 3: Constituição não federal / ano curto / territorial / ADCT

@pytest.mark.parametrize("texto,ano", [
    ("art. 5 da Constituição de 67", 1967),
    ("art. 5 da Constituição de 89", None),
    ("art. 5 da CF de 1967", 1967),
    ("art. 5 da Constituição sul-rio-grandense", None),
    ("art. 5 da Constituição de 1988 do Estado de São Paulo", None),
])
def test_r1_constituicao_nao_resolve_para_1988_indevidamente(texto, ano):
    c = parse_one(texto)
    if c is None:
        assert ano is None
        return
    if ano is None:
        assert c.work != CF or c.confidence != "exata"
    else:
        assert c.work == WorkKey("federal", "constituicao", str(ano), ano)
        assert c.confidence == "exata"


def test_r1_adct_com_ano_errado_nao_exato_cf_1988():
    cites = extract("art. 5 do ADCT da Constituição de 1967")
    cf = [c for c in cites if c.work and c.work.kind == "constituicao" and c.path and "adct" not in (c.path or "")]
    assert not any(c.work == CF and c.confidence == "exata" for c in cf)


def test_r1_declared_identity_e_planalto_respeitam_ano_constituicao():
    doc = ParsedDocument("planalto", "t", "CONSTITUIÇÃO FEDERAL BRASILEIRA DE 1967", None, "")
    assert declared_identity(doc)[0] == WorkKey("federal", "constituicao", "1967", 1967)
    assert planalto.work_key("CF", "1967", None) == "CF:1967"
    assert planalto.urls_for_work("CF", "1967", 1967) == []


# ------------------------------------------------------------------ achado 4: reconfirmação exige redação vigente estrita

def _prov(text: str, *, annotations=None) -> Provision:
    red = Redaction(
        text=text, order=1, struck=False, superseded_without_strike=False,
        annotations=annotations or [],
    )
    return Provision(path="art1", label="Art. 1", scope="", redactions=[red], ambiguous=False)


def test_r1_reconfirmacao_recusa_redacao_revogada_ou_bloqueada(tmp_path, monkeypatch):
    from freoa_verifica.store import repo
    from dataclasses import asdict

    svc = Verifica(home=tmp_path)
    vigente = _prov("texto canônico")
    cand = _prov("texto canônico", annotations=[Annotation(kind="revogado", raw="(Revogado)")])
    canon_doc = ParsedDocument("planalto", "1.2.4", "Lei", None, "", provisions=[vigente], issues=[])
    cand_doc = ParsedDocument("planalto", "1.2.4", "Lei", None, "", provisions=[cand], issues=[])
    rw = SimpleNamespace(
        work_id="w1", capture_id="c1", source_id="planalto", fetched_at="2020-01-01T00:00:00+00:00",
        document=canon_doc, quarantined=False, persisted_incomplete=False,
    )
    monkeypatch.setattr(repo, "captures_for_work", lambda *a, **k: [
        {"id": "c2", "fetched_at": "2021-01-01T00:00:00+00:00", "source_id": "planalto", "candidato_ao_vivo": 1},
    ])
    monkeypatch.setattr(repo, "avaliar_monotonia", lambda *a, **k: ([], []))
    monkeypatch.setattr(repo, "get_parsed_document", lambda *a, **k: {"model_json": json.dumps(asdict(cand_doc))})
    monkeypatch.setattr(svc, "_authenticate_capture", lambda *a, **k: None)
    reconf, _ = svc._reconfirmacao(rw, vigente)
    assert reconf is None


# ------------------------------------------------------------------ achado 5: busca ao vivo respeita escopo

def test_r1_buscar_legislacao_bloqueia_normas_leg_fora_do_escopo(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    escopo = tmp_path / "normas_leg"
    escopo.mkdir(parents=True)
    (escopo / "escopo.json").write_text(
        json.dumps({"escopo": "metadados_e_renovacao", "decisao": "teste", "em": "2026-01-01T00:00:00+00:00"}),
        encoding="utf-8",
    )
    svc = Verifica(home=tmp_path)
    out = svc.buscar_legislacao("lei 9999")
    nl = out["fontes"].get("normas_leg") or {}
    assert nl.get("status") in {"nao_consultada", "unavailable"}
    assert nl.get("motivo") == "fora_do_escopo_do_home"


# ------------------------------------------------------------------ achado 6: cursor de manutenção retomável

def test_r1_revalidar_cursor_avanca_entre_lotes(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    rows = [
        {"id": "w1", "authority": "federal", "kind": "lei", "number": "1", "year": 2020},
        {"id": "w2", "authority": "federal", "kind": "lei", "number": "2", "year": 2020},
        {"id": "w3", "authority": "federal", "kind": "lei", "number": "3", "year": 2020},
    ]
    monkeypatch.setattr(rev, "_obras_elegiveis", lambda _c: rows)
    from freoa_verifica.connectors.normas_leg import urn_da_chave, identidade

    def _fake_ler(_con, work):
        w = identidade(work)
        return ({"urn": urn_da_chave(w), "encoding": [{"version": "Current", "inLanguage": "pt",
                "encodesCreativeWork": {"@id": "x@2026-01-01~"}}]}, "sha", "2026-01-01T00:00:00+00:00")

    monkeypatch.setattr(rev, "_ler_metadados", _fake_ler)
    monkeypatch.setattr(rev, "_validar_metadados_obra", lambda *a, **k: None)
    monkeypatch.setattr(rev, "sinal_de_metadados", lambda *a, **k: {"date_modified": "d", "versao_current": "v"})
    svc = Verifica(home=tmp_path)
    r1 = rev.revalidar(svc, limite=2)
    r2 = rev.revalidar(svc, limite=2)
    assert {x["work_id"] for x in r1["resultados"]} != {x["work_id"] for x in r2["resultados"]}


# ------------------------------------------------------------------ achado 7: metadado inválido não apaga sinal anterior

def test_r1_meta_vazio_nao_substitui_sinal_valido(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    from tests.test_0091a_revalidacao import _meta_base, _meta_url, _obra, _portao
    from tests.test_0091a_revalidacao import resposta

    from freoa_verifica.connectors import normas_leg as nl

    meta = _meta_base()
    meta["urn"] = nl.urn_da_chave(KEY)
    url = _meta_url()
    con, tr = _portao(tmp_path, {url: resposta(url, json.dumps(meta).encode(), mime="application/json")})
    with Verifica(tmp_path) as svc:
        wid = _obra(svc)
        svc._connectors["normas_leg"] = con
        rev.revalidar(svc)
        tr.rotas[url] = resposta(url, b"{}", mime="application/json")
        r = rev.revalidar(svc)
        alvo = next(x for x in r["resultados"] if x["work_id"] == wid)
        assert alvo["resultado"] == "indisponivel"
        row = svc.conn.execute(
            "SELECT payload_json FROM sync_state WHERE fonte=? AND chave=?", (rev.FONTE_META, wid)
        ).fetchone()
        assert row is not None
        payload = json.loads(row[0])
        assert payload.get("sinal") == rev.sinal_de_metadados(meta)


# ------------------------------------------------------------------ achado 8: MCP envolve campos documentais aninhados

def test_r1_mcp_obter_dispositivo_envolve_todos_os_textos():
    delim = _wrap_oficial("x")[0]
    amostra = {
        "texto": "cabeça",
        "texto_atual": {"texto": "vigente"},
        "redacoes_anteriores": [{"trecho": "antiga"}],
        "anotacoes": [{"raw": "nota"}],
        "subdispositivos": [
            {"texto": "filho", "texto_atual": {"texto": "v"}, "anotacoes": [{"raw": "n"}],
             "redacoes_anteriores": [{"trecho": "t"}]},
        ],
    }
    out = _wrap_dispositivo_resposta(amostra)
    assert out["texto"].startswith(delim)
    assert out["texto_atual"]["texto"].startswith(delim)
    assert out["redacoes_anteriores"][0]["trecho"].startswith(delim)
    assert out["anotacoes"][0]["raw"].startswith(delim)
    assert out["subdispositivos"][0]["texto_atual"]["texto"].startswith(delim)


# ------------------------------------------------------------------ achado 9: obter_evidencia confere codec

def test_r1_obter_evidencia_rejeita_codec_divergente(tmp_path, monkeypatch):
    from freoa_verifica.store import blobs

    svc = Verifica(home=tmp_path)
    body = _html("<p>Art. 1º Teste.</p>")
    url = "http://example.invalid/ev"
    doc = parse_planalto(body, base_url=url)
    cap_id = svc.indexar_obra(
        source_id="planalto",
        work_key=KEY,
        document=doc,
        body=body,
        url=url,
        label="Lei 9.999/2000",
        fetched_at=T0,
        content_type=None,
    ).capture_id
    svc.conn.execute(
        "UPDATE parsed_document SET interpretacao_origem=?, interpretacao_codificacao=? WHERE capture_id=?",
        ("legado_padrao_da_fonte_conferido", "latin-1", cap_id),
    )
    svc.conn.commit()
    blob_corrupto = b"\xff\xfe<html"
    monkeypatch.setattr(blobs, "get_blob", lambda *a, **k: blob_corrupto)
    out = svc.obter_evidencia(cap_id)
    assert out["status"] == "indisponivel"
    assert "interpretacao" in (out.get("motivo") or "")


# ------------------------------------------------------------------ achado 10: manifesto local preserva snapshot_derived_version

def test_r1_atualizar_manifesto_usa_snapshot_derived_version(tmp_path):
    from freoa_verifica.acervo import MANIFESTO_LOCAL

    path = tmp_path / MANIFESTO_LOCAL
    path.write_text(json.dumps({"derived_version": "6", "snapshot_derived_version": "5", "vinculado": False}),
                    encoding="utf-8")
    derivados._atualizar_manifesto_local(tmp_path)
    ref = json.loads(path.read_text(encoding="utf-8"))
    assert ref["derived_version"] == derivados.DERIVED_VERSION
    assert int(ref.get("snapshot_derived_version")) == 5
    assert int(ref.get("derived_version_do_snapshot")) == 5
    assert ref.get("vinculado") is False


# ------------------------------------------------------------------ achado 11: bateria ignora sync_state de manutenção

def test_r1_bateria_exclui_fontes_de_manutencao(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        "CREATE TABLE sync_state(id TEXT PRIMARY KEY, fonte TEXT, chave TEXT, status TEXT, motivo TEXT, "
        "updated_at TEXT, payload_json TEXT, UNIQUE(fonte,chave));"
    )
    for fonte in (rev.FONTE_META, rev.FONTE_PENDENTE, rev.FONTE_CURSOR):
        conn.execute(
            "INSERT INTO sync_state(id,fonte,chave,status,motivo,updated_at,payload_json) VALUES (?,?,?,?,?,?,?)",
            (f"{fonte}:x", fonte, "x", "registrado", None, "2026-01-01T00:00:00+00:00", "{}"),
        )
    pend = bateria._pendencias(conn)
    assert not any(p["fonte"] in {rev.FONTE_META, rev.FONTE_PENDENTE, rev.FONTE_CURSOR} for p in pend)