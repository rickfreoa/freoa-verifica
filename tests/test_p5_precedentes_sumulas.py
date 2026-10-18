"""P5: temas STJ (CKAN CSV) e súmulas STF (portal) no índice local, com autoridade A/B. Sem rede."""

from __future__ import annotations

import hashlib
import sqlite3

import pytest

from freoa_verifica.connectors import stf as stf_mod
from freoa_verifica.connectors import stj as stj_mod
from freoa_verifica.connectors.base import Candidate, Unavailable
from freoa_verifica.semente import SementeSync
from freoa_verifica.service import Verifica
from freoa_verifica.transport import Response
from tests.fixture_util import load_fixture

_PKG = {"resources": [
    {"name": "Temas.csv", "format": "CSV", "url": "https://dadosabertos.web.stj.jus.br/dataset/x/resource/1/download/temas.csv"},
    {"name": "Processos.csv", "format": "CSV", "url": "https://dadosabertos.web.stj.jus.br/dataset/x/resource/2/download/processos.csv"},
]}
_SUMARIO = "https://portal.stf.jus.br/jurisprudencia/sumariosumulas.asp"


def _resp(url: str, body: bytes, mime: str) -> Response:
    return Response(url, url, 200, {"content-type": mime}, body, hashlib.sha256(body).hexdigest(),
                    "2026-10-18T19:00:00+00:00", [], mime)


def _fake_stj_fetch(url, **kw):
    key = "stj_precedentes_temas" if url.endswith("temas.csv") else "stj_precedentes_processos"
    return _resp(url, load_fixture(key), "text/csv")


def _fake_stf_fetch(url, **kw):
    fixtures = {
        _SUMARIO + "?base=30": "stf_sumulas_sumario",
        _SUMARIO + "?base=26": "stf_sumulas_vinculantes_sumario",
        _SUMARIO + "?base=30&sumula=1306": "stf_sumula_3_detalhe",
        _SUMARIO + "?base=26&sumula=1212": "stf_sumula_vinculante_9_detalhe",
    }
    if url not in fixtures:
        raise Unavailable("sem_fixture")
    return _resp(url, load_fixture(fixtures[url]), "text/html")


def test_stj_sync_ingere_temas_no_mesmo_fts(tmp_path, monkeypatch):
    monkeypatch.setattr(stj_mod, "connector_fetch", _fake_stj_fetch)
    c = stj_mod.StjConnector(tmp_path / "stj.sqlite")
    monkeypatch.setattr(c, "package_show", lambda pkg: _PKG)
    # Tema 14, Tema 479, IAC 2 e Tema 1116; a Controvérsia é ignorada.
    assert c.sync(orgaos=["precedentes-qualificados"]) == 4
    hit = c.search("desvio de função")[0]
    assert hit.key == "tema:14"
    assert "Tese firmada: Reconhecido o desvio de função" in hit.snippet
    assert hit.metadata["processosParadigmaNaoAutenticados"] == ["REsp 1091539"]
    assert hit.metadata["siglaClasse"] == "Tema Repetitivo"
    assert [h.key for h in c.search("Cancelado")] == ["tema:479"]
    con = sqlite3.connect(tmp_path / "stj.sqlite")
    assert con.execute("SELECT COUNT(*) FROM fts_stj WHERE key LIKE 'iac:%'").fetchone()[0] == 1


def test_stj_sync_sem_recurso_csv_e_indisponivel(tmp_path, monkeypatch):
    c = stj_mod.StjConnector(tmp_path / "stj.sqlite")
    monkeypatch.setattr(c, "package_show", lambda pkg: {"resources": []})
    with pytest.raises(Unavailable, match="stj_precedentes_recurso_ausente"):
        c.sync(orgaos=["precedentes-qualificados"])


def test_stj_tema_chega_com_autoridade_b(tmp_path, monkeypatch):
    monkeypatch.setattr(stj_mod, "connector_fetch", _fake_stj_fetch)
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        conn = svc._get("stj")
        monkeypatch.setattr(conn, "package_show", lambda pkg: _PKG)
        SementeSync(svc, rate_delay=0, fontes=["stj"]).sync_stj()
        monkeypatch.setenv("FV_OFFLINE", "1")
        out = svc.pesquisar_jurisprudencia("desvio de função", tribunais=["stj"])
    item = out["itens"][0]
    assert item["rotulo_autoridade"] == "B"
    assert item["classe_numero"].startswith("Tema Repetitivo 14")
    assert item["nivel_prova"] != "metadados" and item["capture_id"]


def test_stf_sumario_extrai_numero_e_observacao():
    c = stf_mod.StfConnector()
    orig = stf_mod.connector_fetch
    try:
        stf_mod.connector_fetch = _fake_stf_fetch
        sumulas = c.list_sumulas(30)
        svs = c.list_sumulas(26)
    finally:
        stf_mod.connector_fetch = orig
    assert [s.key for s in sumulas] == [f"sumula:{n}" for n in range(1, 6)]
    assert {s.key: s.metadata["observacao"] for s in sumulas if s.metadata["observacao"]} == {
        "sumula:3": "superada", "sumula:4": "cancelada"}
    assert svs[8].key == "sv:9" and svs[8].metadata["observacao"] == "cancelada"  # U+200B removido
    assert svs[8].metadata["classe"] == "Súmula Vinculante"


def test_stf_detalhe_parseia_enunciado():
    body = load_fixture("stf_sumula_3_detalhe")
    p = stf_mod.StfConnector().parse(_resp(_SUMARIO + "?base=30&sumula=1306", body, "text/html"))
    assert (p.kind, p.class_name, p.official_id) == ("sumula", "Súmula", "Súmula 3")
    assert p.text.startswith("A imunidade concedida a deputados estaduais")
    assert p.ementa.startswith("Súmula 3 (superada).")
    sv = stf_mod.StfConnector().parse(_resp(_SUMARIO + "?base=26&sumula=1212",
                                            load_fixture("stf_sumula_vinculante_9_detalhe"), "text/html"))
    assert sv.kind == "sumula_vinculante" and "(cancelada)" in sv.ementa


@pytest.mark.parametrize("html", [b"<html><body>fora do ar</body></html>", b"<div class='titulo'>Outra coisa</div>"])
def test_stf_pagina_inesperada_e_unavailable(html):
    c = stf_mod.StfConnector()
    with pytest.raises(Unavailable, match="resposta_inesperada"):
        c.parse(_resp(_SUMARIO + "?base=30&sumula=1", html, "text/html"))
    orig = stf_mod.connector_fetch
    stf_mod.connector_fetch = lambda url, **kw: _resp(url, html, "text/html")
    try:
        with pytest.raises(Unavailable, match="resposta_inesperada"):
            c.list_sumulas(30)
    finally:
        stf_mod.connector_fetch = orig


def test_stf_sumulas_indexadas_com_autoridade_a(tmp_path, monkeypatch):
    monkeypatch.setattr(stf_mod, "connector_fetch", _fake_stf_fetch)
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        SementeSync(svc, rate_delay=0, max_itens=9, fontes=["stf"]).sync_stf()
        monkeypatch.setenv("FV_OFFLINE", "1")
        sumula = svc.pesquisar_jurisprudencia("imunidade deputados estaduais", tribunais=["stf"])["itens"]
        vinculante = svc.pesquisar_jurisprudencia("Lei de Execução Penal artigo 127", tribunais=["stf"])["itens"]
        outras = svc.conn.execute("SELECT status FROM sync_state WHERE fonte='stf' AND chave='sumula:1'").fetchone()
    assert sumula[0]["rotulo_autoridade"] == "A" and "superada" in sumula[0]["ementa"]
    assert sumula[0]["capture_id"]
    assert vinculante[0]["rotulo_autoridade"] == "A"
    assert outras["status"] == "indisponivel"  # detalhe não capturado nunca vira ausência silenciosa


# ---- auditoria P5: duplicatas, paradigmas não autenticados, situação estruturada ----

def _csv_duplicado() -> bytes:
    import csv
    import io
    rows = list(csv.DictReader(io.StringIO(load_fixture("stj_precedentes_temas").decode("utf-8"), newline="")))
    t14 = rows[0]
    velha = {**t14, "teseFirmada": "TESE ANTIGA"}
    nova = {**t14, "teseFirmada": "TESE NOVA", "situacao": "Cancelado"}
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=list(t14), lineterminator="\n")
    w.writeheader()
    w.writerows([velha, nova])
    return buf.getvalue().encode("utf-8")


def test_stj_linhas_repetidas_mesma_politica_no_sync_e_na_releitura(tmp_path, monkeypatch):
    csv_dup = _csv_duplicado()
    monkeypatch.setattr(stj_mod, "connector_fetch", lambda url, **kw: _resp(
        url, csv_dup if url.endswith("temas.csv") else load_fixture("stj_precedentes_processos"), "text/csv"))
    c = stj_mod.StjConnector(tmp_path / "stj.sqlite")
    monkeypatch.setattr(c, "package_show", lambda pkg: _PKG)
    assert c.sync(orgaos=["precedentes-qualificados"]) == 1
    hit = c.search("tema")[0]
    assert "TESE NOVA" in hit.metadata["ementa"] and "TESE ANTIGA" not in hit.metadata["ementa"]
    parsed = c.parse_candidate(c.fetch(hit), hit)  # releitura do CSV capturado
    assert "TESE NOVA" in parsed.ementa and "TESE ANTIGA" not in parsed.ementa
    assert "Divergência na fonte" in parsed.ementa
    assert parsed.metadata["divergencia_na_fonte"] is True
    assert parsed.metadata["situacao_precedente"] == {"valor": "cancelada", "texto_oficial": "Cancelado"}


def test_stj_paradigma_adulterado_no_metadado_nao_entra_no_texto(tmp_path, monkeypatch):
    monkeypatch.setattr(stj_mod, "connector_fetch", _fake_stj_fetch)
    c = stj_mod.StjConnector(tmp_path / "stj.sqlite")
    monkeypatch.setattr(c, "package_show", lambda pkg: _PKG)
    c.sync(orgaos=["precedentes-qualificados"])
    hit = c.search("desvio de função")[0]
    assert "REsp 1091539" not in hit.metadata["ementa"]  # nem o verdadeiro: vem de outra captura
    hit.metadata["processosParadigma"] = ["REsp 9999999"]
    hit.metadata["processosParadigmaNaoAutenticados"] = ["REsp 9999999"]
    parsed = c.parse_candidate(c.fetch(hit), hit)
    assert "9999999" not in parsed.ementa + parsed.text


def _situacoes(svc, q, tribunal):
    item = svc.pesquisar_jurisprudencia(q, tribunais=[tribunal])["itens"][0]
    full = svc.obter_decisao(item["id"])
    return item, full


def test_situacao_estruturada_persiste_e_alerta(tmp_path, monkeypatch):
    monkeypatch.setattr(stj_mod, "connector_fetch", _fake_stj_fetch)
    monkeypatch.setattr(stf_mod, "connector_fetch", _fake_stf_fetch)
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        monkeypatch.setattr(svc._get("stj"), "package_show", lambda pkg: _PKG)
        SementeSync(svc, rate_delay=0, fontes=["stj"]).sync_stj()
        SementeSync(svc, rate_delay=0, max_itens=9, fontes=["stf"]).sync_stf()
    monkeypatch.setenv("FV_OFFLINE", "1")
    casos = [  # consulta, tribunal, situação esperada, alerta esperado
        ("desvio de função", "stj", "vigente", False),
        ("Cancelado", "stj", "cancelada", True),
        ("imunidade deputados estaduais", "stf", "superada", True),
        ("Lei de Execução Penal artigo 127", "stf", "cancelada", True),
    ]
    for _ in range(2):  # a segunda volta reabre o banco do disco
        with Verifica(tmp_path) as svc:
            for q, trib, valor, alerta in casos:
                item, full = _situacoes(svc, q, trib)
                for out in (item, full):
                    assert out["situacao_precedente"]["valor"] == valor, (q, out["situacao_precedente"])
                    assert ("PRECEDENTE_NAO_VIGENTE_NA_FONTE" in out.get("alertas", [])) is alerta
                assert item["rotulo_autoridade"] in {"A", "B"}  # rótulo segue sendo espécie
            assert item["situacao_precedente"]["texto_oficial"] == "cancelada"


def test_situacao_ausente_e_desconhecida_nunca_vigente():
    from freoa_verifica.service import _situacao_precedente
    assert _situacao_precedente(None, "sumula")["situacao_precedente"]["valor"] == "desconhecida"
    assert _situacao_precedente("{}", "repetitivo")["situacao_precedente"]["valor"] == "desconhecida"
    assert _situacao_precedente(None, "acordao") == {}
    html = (b"<html><head><meta charset=utf-8></head><body><div class='titulo'>S\xc3\xbamula 7</div><div class='parCOM'><p>Enunciado.</p></div></body></html>")
    p = stf_mod.StfConnector().parse(_resp(_SUMARIO + "?base=30&sumula=1", html, "text/html"))
    assert p.metadata["situacao_precedente"] == {"valor": "desconhecida", "texto_oficial": None}
    assert stj_mod._situacao_estruturada("Afetado")["valor"] == "desconhecida"
    assert stj_mod._situacao_estruturada("Revisado")["valor"] == "revisada"


def _csv_tema14(tese: str, situacao: str) -> bytes:
    import csv
    import io
    rows = list(csv.DictReader(io.StringIO(load_fixture("stj_precedentes_temas").decode("utf-8"), newline="")))
    rows[0] = {**rows[0], "teseFirmada": tese, "situacao": situacao}
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def test_nova_versao_do_tema_reprocessa_texto_captura_situacao_e_fts(tmp_path, monkeypatch):
    versao = {"csv": _csv_tema14("TESE ANTIGA", "Trânsito em Julgado")}
    monkeypatch.setattr(stj_mod, "connector_fetch", lambda url, **kw: _resp(
        url, versao["csv"] if url.endswith("temas.csv") else load_fixture("stj_precedentes_processos"), "text/csv"))
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        conn = svc._get("stj")
        monkeypatch.setattr(conn, "package_show", lambda pkg: _PKG)
        engine = SementeSync(svc, rate_delay=0, fontes=["stj"])
        engine.sync_stj()
        antes = svc.conn.execute("SELECT id FROM decision WHERE official_id='tema:14'").fetchone()["id"]
        cap_antiga = svc.conn.execute("SELECT capture_id FROM decision_document WHERE decision_id=?", (antes,)).fetchone()[0]
        # versão inalterada: nada é reindexado
        chamadas = []
        orig = svc._index_candidate_juris
        monkeypatch.setattr(svc, "_index_candidate_juris", lambda *a, **k: chamadas.append(a) or orig(*a, **k))
        engine._index_stj_from_fts(conn, max_items=None)
        assert chamadas == []
        # o recurso muda na fonte: troca a linha de fts_stj por outro CSV/hash
        versao["csv"] = _csv_tema14("TESE NOVA", "Cancelado")
        conn.sync(orgaos=["precedentes-qualificados"], precedentes=True)
        engine._index_stj_from_fts(conn, max_items=None)
        assert [c[1].key for c in chamadas] == ["tema:14"]  # só o tema alterado
    monkeypatch.setenv("FV_OFFLINE", "1")
    with Verifica(tmp_path) as svc:  # banco reaberto
        docs = svc.conn.execute("SELECT text, capture_id FROM decision_document WHERE decision_id=?", (antes,)).fetchall()
        assert len(docs) == 1 and "TESE NOVA" in docs[0]["text"] and "TESE ANTIGA" not in docs[0]["text"]
        assert docs[0]["capture_id"] != cap_antiga
        item = svc.pesquisar_jurisprudencia("TESE NOVA", tribunais=["stj"])["itens"][0]
        assert item["situacao_precedente"]["valor"] == "cancelada"
        assert "PRECEDENTE_NAO_VIGENTE_NA_FONTE" in item["alertas"]
        assert svc.obter_decisao(antes)["situacao_precedente"]["valor"] == "cancelada"
        assert not [i for i in svc.pesquisar_jurisprudencia("TESE ANTIGA", tribunais=["stj"])["itens"]
                    if "TESE ANTIGA" in (i["ementa"] or "")]
