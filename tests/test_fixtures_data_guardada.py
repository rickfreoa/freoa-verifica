"""Pendência 23: fixtures com data guardada não envelhecem com o relógio (regressão de 17/11/2026)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from freoa_verifica import temporal
from tests.fixture_util import guardar_data_da_captura, load_meta
from tests.test_decisao_0075 import CAPTURA_160, svc_160  # noqa: F401  (svc_160 é fixture)

CAPTURA = load_meta()["planalto_lei_6404_1976"]["capturado_em"]


def _hoje(monkeypatch, d: date) -> None:
    monkeypatch.setattr(temporal, "today_sp", lambda: d)


@pytest.mark.parametrize("dias", [2, 31, 400, 4000])
def test_captura_guardada_fica_fresca_em_qualquer_data(monkeypatch, dias):
    futuro = temporal._parse_fetched_at(CAPTURA).date() + timedelta(days=dias)
    _hoje(monkeypatch, futuro)
    assert temporal._capture_fresh(CAPTURA, futuro) == (dias <= 30, [] if dias <= 30 else ["CAPTURA_DESATUALIZADA"])
    guardar_data_da_captura(monkeypatch, CAPTURA)
    assert temporal._capture_fresh(CAPTURA, futuro) == (True, [])


@pytest.mark.parametrize("dias_antes,fresca", [(29, True), (30, False), (31, False)])
def test_limite_da_guarda_para_captura_mais_velha_que_a_guardada(monkeypatch, dias_antes, fresca):
    base = temporal._parse_fetched_at(CAPTURA)
    futuro = base.date() + timedelta(days=400)
    _hoje(monkeypatch, futuro)
    guardar_data_da_captura(monkeypatch, CAPTURA)
    mais_velha = (base - timedelta(days=dias_antes)).isoformat()
    assert temporal._capture_fresh(mais_velha, futuro) == (fresca, [] if fresca else ["CAPTURA_DESATUALIZADA"])


def test_verifica_populada_aplica_a_guarda(verifica_populada):
    """Ligação: sem a chamada em `conftest.py`, a captura de 17/10/2026 já passou dos 30 dias e isto reprova."""
    assert temporal._capture_fresh(CAPTURA, temporal.today_sp()) == (True, [])
    svc, _, _ = verifica_populada
    assert svc.obter_dispositivo("Lei 6.404/1976, art. 254-A")["vigencia"]["status"] == "vigente_na_fonte"


def test_svc_160_aplica_a_guarda(svc_160):  # noqa: F811
    assert temporal._capture_fresh(CAPTURA_160, temporal.today_sp()) == (True, [])


def test_guarda_nao_libera_captura_futura(monkeypatch):
    guardar_data_da_captura(monkeypatch, CAPTURA)
    futura = (datetime.now(temporal._TZ_SP) + timedelta(days=1)).isoformat()
    assert temporal._capture_fresh(futura, temporal.today_sp()) == (False, ["CAPTURA_DATA_INVALIDA"])


def test_guarda_some_ao_fim_do_teste():
    assert temporal._CAPTURE_MAX_AGE == timedelta(days=30)


def test_capturado_em_ilegivel_reprova(monkeypatch):
    with pytest.raises(AssertionError):
        guardar_data_da_captura(monkeypatch, "ontem")
