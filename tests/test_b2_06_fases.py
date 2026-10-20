"""B2-06: o hook live consolida o teste só depois de setup, call e teardown (decisão 0054)."""
import json

pytest_plugins = ["pytester"]

_FONTE = '''
import pytest
from freoa_verifica.connectors.base import Unavailable
pytestmark = pytest.mark.live

@pytest.fixture
def teardown_falho():
    yield
    raise RuntimeError("teardown quebrou")

@pytest.fixture
def setup_falho():
    raise RuntimeError("setup quebrou")

def test_ok():
    pass

def test_call_ok_teardown_falho(teardown_falho):
    pass

def test_setup_falho(setup_falho):
    pass

def test_ambiental_com_teardown_falho(teardown_falho):
    raise Unavailable("http_503", "fonte_fora", {"status": 503})
'''


def _rodar(pytester):
    pytester.makeconftest("from tests.live.conftest import *  # noqa: F401,F403\n")
    pytester.makeini("[pytest]\nmarkers =\n    live: x\n")
    pytester.makepyfile(test_live_bcb=_FONTE)
    pytester.runpytest("-p", "no:cacheprovider")
    rel = json.loads((pytester.path / "saude-fontes.json").read_text(encoding="utf-8"))
    return {t["nome"].split("::")[-1]: t for t in rel["fontes"]["bcb"]["testes"]}, rel


def test_falha_em_qualquer_fase_vira_regressao(pytester):
    testes, rel = _rodar(pytester)
    assert testes["test_ok"]["estado"] == "ok"
    assert testes["test_call_ok_teardown_falho"]["estado"] == "regressao"
    assert "teardown quebrou" in testes["test_call_ok_teardown_falho"]["motivo"]
    assert testes["test_setup_falho"]["estado"] == "regressao"
    # xfail ambiental no call não esconde um teardown quebrado
    assert testes["test_ambiental_com_teardown_falho"]["estado"] == "regressao"
    assert rel["fontes"]["bcb"]["estado"] == "regressao" and rel["completa"] is True
