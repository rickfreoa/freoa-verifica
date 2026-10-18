"""Testes da fachada Verifica."""

from __future__ import annotations

import json

from freoa_verifica.service import DOC_OPEN, Verifica


def test_buscar_legislacao_local(verifica_populada):
    svc, rw, doc = verifica_populada
    # texto típico do art. 254-A
    res = svc.buscar_legislacao("alienação", limite=5)
    assert "itens" in res
    assert res["total_parcial"] >= 1
    assert res["itens"][0]["caminho"] == "art254-A"


def test_resolver_e_obter_dispositivo(verifica_populada):
    svc, rw, doc = verifica_populada
    r = svc.resolver_citacao("art. 254-A da Lei 6.404/76")
    assert r["status"] == "encontrada"
    assert r["work_id"] == rw.work_id
    assert r["caminho"] == "art254-A"

    disp = svc.obter_dispositivo(citacao="art. 254-A da Lei 6.404/76")
    assert disp["status"] == "encontrada"
    assert disp["texto"]
    assert disp["evidencia"]["capture_id"] == rw.capture_id


def test_historico_dispositivo(verifica_populada):
    svc, *_ = verifica_populada
    h = svc.historico_dispositivo("art. 254-A da Lei 6.404/76")
    assert h["status"] == "encontrada"
    assert "linha_do_tempo" in h


def test_verificar_citacao(verifica_populada):
    svc, rw, doc = verifica_populada
    trecho = doc.current_text("art254-A")
    assert trecho
    # fronteira lexical (textcmp exige bordas não alfanuméricas)
    trecho = "A alienação, direta ou indireta, do controle de companhia aberta"
    res = svc.verificar_citacao(
        "art. 254-A da Lei 6.404/76",
        trecho=trecho,
        proposicao="eco-teste",
    )
    assert res["identity"]["status"] == "verified"
    assert res["text"]["status"] == "verified"
    assert res["support"]["status"] == "not_assessed"
    assert res["proposicao"] == "eco-teste"


def test_verificar_texto(verifica_populada):
    svc, rw, doc = verifica_populada
    trecho = (doc.current_text("art254-A") or "")[:100]
    texto = (
        f'Conforme o art. 254-A da Lei 6.404/76 "{trecho}" '
        "e também a Lei inventada 99.999/2099."
    )
    res = svc.verificar_texto(texto)
    assert res["total"] >= 1
    statuses = {c["status"] for c in res["citacoes"]}
    assert "encontrada" in statuses


def test_listar_fontes_e_doctor_offline(verifica_populada):
    svc, *_ = verifica_populada
    fontes = svc.listar_fontes()
    assert fontes["total"] >= 5
    ids = {f["id"] for f in fontes["fontes"]}
    assert "planalto" in ids
    doc = svc.doctor(offline=True)
    assert doc["status"] == "ok"


def test_obter_evidencia_envolve_documento(verifica_populada):
    svc, rw, _ = verifica_populada
    ev = svc.obter_evidencia(rw.capture_id, max_chars=500)
    assert ev["status"] == "encontrada"
    assert DOC_OPEN in ev["texto"]
    assert ev["metadados"]["sha256"] == rw.sha256


def test_snapshot_export_info(verifica_populada, tmp_path):
    svc, *_ = verifica_populada
    dest = tmp_path / "snap"
    out = svc.snapshot_export(dest)
    assert out["status"] == "ok"
    assert (dest / "MANIFEST.json").is_file()
    info = svc.snapshot_info(dest)
    assert info["capturas"] >= 1


def test_pesquisar_jurisprudencia_vazio_local(verifica_populada):
    svc, *_ = verifica_populada
    # sem rede: índice local vazio → lista (possivelmente vazia) sem explodir
    res = svc.pesquisar_jurisprudencia("xyzzy_inexistente_999", tribunais=[], limite=3)
    assert "itens" in res
    assert isinstance(res["itens"], list)
