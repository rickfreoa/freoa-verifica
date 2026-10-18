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
    assert "Processos paradigma: REsp 1091539" in hit.metadata["ementa"]
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
