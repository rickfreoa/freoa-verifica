"""Decisão 0016, adendo: norma de série única citada sem ano é exata se o acervo tem exatamente uma obra."""

from __future__ import annotations

import pytest

from freoa_verifica.service import Verifica
from freoa_verifica.store import repo
from tests.test_c2_situacao import _bcb_body, _indexar_bcb, _indexar_cvm


@pytest.fixture
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    s = Verifica(home=tmp_path)
    yield s
    s.close()


def _conf(out):
    return out["citation"]["confidence"], out["identity"]["reason_code"]


def test_numero_unico_no_acervo_e_exato(svc):
    rw, path = _indexar_bcb(svc, _bcb_body())
    out = svc.verificar_citacao("Resolução CMN 4.966")
    assert out["identity"]["status"] == "verified"
    assert out["citation"]["confidence"] == "exata" and out["citation"]["work"]["year"] == 2021
    assert "numero_unico_no_acervo" in out["citation"]["flags"]
    # com dispositivo, o confronto também deixa de exigir conferência
    num = path.removeprefix("art")
    com_art = svc.verificar_citacao(f"Resolução CMN 4.966, art. {num}")
    assert com_art["identity"]["reason_code"] != "ASSOCIACAO_REQUER_CONFERENCIA"
    assert com_art["identity"]["status"] == "verified"
    # em texto corrido: encontrada, sem pedir conferência
    texto = svc.verificar_texto("Aplica-se a Resolução CMN 4.966 ao caso.")
    assert texto["citacoes"][0]["status"] == "encontrada"


def test_cvm_resolucao_sem_ano_unica(svc):
    _indexar_cvm(svc)
    out = svc.verificar_citacao("Resolução CVM 80")
    assert out["citation"]["confidence"] == "exata" and out["identity"]["status"] == "verified"


def test_duas_obras_de_mesmo_numero_continua_requerendo_conferencia(svc):
    _indexar_bcb(svc, _bcb_body())
    repo.upsert_work(svc.conn, jurisdiction="br", authority="cmn", kind="resolucao", number="4966", year=2022,
                     label="Resolução CMN 4.966/2022")
    out = svc.verificar_citacao("Resolução CMN 4.966")
    assert out["citation"]["confidence"] == "provavel"
    assert out["identity"]["reason_code"] == "ASSOCIACAO_REQUER_CONFERENCIA"
    texto = svc.verificar_texto("Aplica-se a Resolução CMN 4.966 ao caso.")
    assert texto["citacoes"][0]["status"] == "requer_conferencia"


def test_zero_obras_continua_provavel(svc):
    out = svc.verificar_citacao("Resolução CVM 80")
    assert out["citation"]["confidence"] == "provavel" and out["identity"]["status"] != "verified"


def test_lei_sem_ano_continua_provavel(verifica_populada):
    svc, _, _ = verifica_populada
    out = svc.verificar_citacao("Lei 6.404, art. 254-A")
    assert out["citation"]["confidence"] == "provavel"
    assert out["identity"]["reason_code"] == "ASSOCIACAO_REQUER_CONFERENCIA"
