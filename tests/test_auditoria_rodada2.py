"""Rodada 2 do auditor: provável não vira vigência fora de verificar_citacao; situação autêntica e
identificada; histórico com efeito cadastral; atomicidade do staging (A7)."""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

from freoa_verifica import situacao
from freoa_verifica.connectors.base import Candidate
from freoa_verifica.situacao import WorkStatus
from freoa_verifica.store import blobs
from tests.test_c2_situacao import _CvmFake, _PAGINA, _agora, _art, _indexar_bcb, _bcb_body, _indexar_cvm, svc  # noqa: F401
from tests.test_fd_busca import _live

PROVAVEL = "Lei 6.404/1976: art. 254-A do contrato"


# --- B1 ---------------------------------------------------------------------

def test_b1_provavel_nao_decide_fora_de_verificar_citacao(verifica_populada):
    svc, _, _ = verifica_populada
    v = svc.verificar_citacao(PROVAVEL)
    assert v["identity"]["reason_code"] == "ASSOCIACAO_REQUER_CONFERENCIA"
    for out in (svc.obter_dispositivo(PROVAVEL), svc.historico_dispositivo(PROVAVEL), svc.resolver_citacao(PROVAVEL)):
        assert out["status"] == "requer_conferencia"
        assert out["identity"]["reason_code"] == "ASSOCIACAO_REQUER_CONFERENCIA"
        assert "conferencia" in out and "vigencia" not in out and "texto" not in out and "linha_do_tempo" not in out


def test_b1_controle_positivo(verifica_populada):
    svc, _, _ = verifica_populada
    out = svc.obter_dispositivo("Lei 6.404/1976, art. 254-A")
    assert out["vigencia"]["status"] == "vigente_na_fonte"


# --- B2 ---------------------------------------------------------------------

def test_b2_captura_de_situacao_corrompida_rebaixa(svc):  # noqa: F811
    rw, cand, path = _indexar_cvm(svc)
    pagina = _PAGINA.format(titulo="Resolução CVM 80", extra="").encode()
    ws = situacao.registrar_cvm(svc.conn, svc.home, _CvmFake(pagina), cand, rw)
    cit = f"Resolução CVM 80/2022, {_art(path)}"
    assert svc.verificar_citacao(cit)["temporal"]["status"] == "vigente_na_fonte"
    blobs.blob_path(ws.sha256, svc.home).write_bytes(b"adulterado")
    out = svc.verificar_citacao(cit)
    assert (out["temporal"]["status"], out["temporal"]["reason_code"]) == ("unknown", "SITUACAO_INDISPONIVEL")
    assert svc.obter_dispositivo(cit)["vigencia"]["status"] == "unknown"


# --- B3 ---------------------------------------------------------------------

@pytest.mark.parametrize("corpo", [
    "<article><h2>Servico indisponivel</h2><p>Tente novamente mais tarde</p></article>",
    "<article><h2>Resolução CVM 81</h2><section class='contentArticle'><p>x</p></section></article>",  # outro ato
])
def test_b3_pagina_sem_identidade_do_ato_e_ilegivel(svc, corpo):  # noqa: F811
    rw, cand, path = _indexar_cvm(svc)
    ws = situacao.registrar_cvm(svc.conn, svc.home, _CvmFake(corpo.encode()), cand, rw)
    assert ws.situacao == "ilegivel"
    out = svc.verificar_citacao(f"Resolução CVM 80/2022, {_art(path)}")
    assert out["temporal"]["status"] == "unknown"


# --- A4 ---------------------------------------------------------------------

def test_a4_historico_fecha_intervalo_aberto_pela_situacao(svc):  # noqa: F811
    rw, path = _indexar_bcb(svc, _bcb_body(Revogado=True))
    cit = f"Resolução CMN 4.966/2021, {_art(path)}"
    sem_data = svc.historico_dispositivo(cit)["linha_do_tempo"]
    assert sem_data[-1]["fim"] is None and sem_data[-1]["fim_desconhecido"]
    assert "REVOGACAO_DATA_DESCONHECIDA" in sem_data[-1]["flags"]
    svc.conn.execute("UPDATE work_status SET data_efeito='2025-01-01' WHERE work_id=?", (rw.work_id,))
    svc.conn.commit()
    ultimo = svc.historico_dispositivo(cit)["linha_do_tempo"][-1]
    assert ultimo["fim"] == "2025-01-01" and "OBRA_REVOGADA_NA_FONTE" in ultimo["flags"]


# --- A5/A7 ------------------------------------------------------------------

def test_a7_falha_no_staging_nao_deixa_rastro_no_fts_canonico(verifica_populada, monkeypatch):
    svc, *_ = verifica_populada
    antes = svc.conn.execute("SELECT COUNT(*) FROM fts_redaction").fetchone()[0]
    _live(svc, monkeypatch)
    svc._connectors["bcb"].search = lambda q, **k: []

    def nega(acao, tabela, *_):
        return sqlite3.SQLITE_DENY if acao == sqlite3.SQLITE_INSERT and tabela == "fts_staging" else sqlite3.SQLITE_OK

    svc.conn.set_authorizer(nega)
    try:
        svc.buscar_legislacao("zebrafish", fonte="cvm_normas")
    finally:
        svc.conn.set_authorizer(None)
    assert svc.conn.execute("SELECT COUNT(*) FROM fts_redaction").fetchone()[0] == antes
    vivo = svc.buscar_legislacao("zebrafish")
    assert not any(i.get("candidato_ao_vivo") for i in vivo["itens"])
