"""FIX8/F-09: o histórico das fontes consultadas acompanha também as saídas de erro."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freoa_verifica.aliases import WorkKey
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.service import Verifica
from freoa_verifica.verify import SourceUnavailable
from tests.test_fix7_varredura_fallback import _Falha

LEI = WorkKey("federal", "lei", "6404", 1976)
CNJ = "1000000-00.2020.8.26.0100"
RECUSA = Unavailable("http_403", "recusa_identificado")
SENADO_FORA = Unavailable("http_503", "fonte_fora")
CAPTCHA = Unavailable("desafio_captcha", "ambiental_desafio")


def _item(fonte, erro):
    return {"fonte": fonte, "resultado": "indisponivel", "motivo": erro.reason, "categoria": erro.categoria}


def test_api_publica_declara_ambas_as_fontes_quando_todas_falham(monkeypatch, tmp_path):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        svc._connectors["planalto"] = _Falha("planalto", RECUSA)
        svc._connectors["senado"] = _Falha("senado", SENADO_FORA)
        out = svc.verificar_citacao("Lei 6.404/1976, art. 1º")
    assert out["identity"]["status"] == "unavailable"
    assert out["identity"]["reason_code"] == "planalto:http_403;senado:http_503"
    assert out["identity"]["evidence"][0]["fontes_consultadas"] == [
        _item("planalto", RECUSA), _item("senado", SENADO_FORA)]


def test_excecao_de_indisponibilidade_carrega_a_lista_estruturada(monkeypatch, tmp_path):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        svc._connectors["planalto"] = _Falha("planalto", RECUSA)
        svc._connectors["senado"] = _Falha("senado", SENADO_FORA)
        with pytest.raises(SourceUnavailable) as ei:
            svc._capture_work(LEI)
    assert ei.value.fontes_consultadas == [_item("planalto", RECUSA), _item("senado", SENADO_FORA)]


def test_erro_de_programacao_posterior_preserva_as_falhas_anteriores_como_regressao(monkeypatch, tmp_path):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        svc._connectors["planalto"] = _Falha("planalto", RECUSA)
        svc._connectors["senado"] = _Falha("senado", ValueError("parse"))
        out = svc.verificar_citacao("Lei 6.404/1976, art. 1º")
    assert out["identity"]["evidence"][0]["fontes_consultadas"] == [
        _item("planalto", RECUSA),
        {"fonte": "senado", "resultado": "erro", "motivo": "ValueError", "categoria": "regressao"},
    ]


def test_cnj_tjsp_captcha_e_datajud_value_error_declaram_ambas(monkeypatch, tmp_path):
    monkeypatch.delenv("FV_OFFLINE", raising=False)

    def quebra(key):
        raise ValueError("x")

    with Verifica(tmp_path) as svc:
        svc._connectors["tjsp"] = _Falha("tjsp", CAPTCHA)
        svc._connectors["datajud"] = SimpleNamespace(id="datajud", resolve=quebra)
        status, ev = svc._confirm_cnj(SimpleNamespace(flags=[], raw=CNJ))
    assert status == "indisponivel" and ev["motivo"] == "ValueError"
    assert ev["fontes_consultadas"] == [
        _item("tjsp", CAPTCHA),
        {"fonte": "datajud", "resultado": "erro", "motivo": "ValueError", "categoria": "regressao"},
    ]
