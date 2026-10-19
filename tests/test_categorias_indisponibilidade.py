"""Categorias de indisponibilidade (decisão 0045) e hook dos testes live."""

from __future__ import annotations

import pytest

from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.challenge import (
    ASSINATURAS_VERSAO,
    _BODY_MARKERS,
    _HEADER_MARKERS,
    detect_challenge,
    map_transport_error,
    unavailable_from_challenge,
)
from freoa_verifica.transport import (
    EmptyBody,
    HTTPMetadata,
    HTTPStatusError,
    Timeout,
    TransportError,
)

URL = "https://exemplo.gov.br/x"
pytest_plugins = ["pytester"]


def test_403_sem_marcador_e_recusa_identificada():
    u = map_transport_error(HTTPStatusError(403), URL)
    assert u.reason == "http_403"
    assert u.categoria == "recusa_identificado"
    assert u.evidencia == {"status": 403, "url": URL}


def test_401_e_recusa_identificada():
    assert map_transport_error(HTTPStatusError(401), URL).categoria == "recusa_identificado"


def test_403_com_pagina_aws_waf_e_ambiental():
    body = b"<html><script>AwsWafIntegration.checkForceRefresh()</script></html>"
    found = detect_challenge(status=403, body=body, headers={"content-type": "text/html"})
    u = unavailable_from_challenge(found, status=403, body=body, url=URL)
    assert u.reason == "desafio_aws_waf"
    assert u.categoria == "ambiental_desafio"
    assert u.evidencia["marcador"] == "awswafintegration"
    assert u.evidencia["status"] == 403 and len(u.evidencia["sha256"]) == 64


def test_cabecalho_de_borda_e_ambiental():
    hdrs = {"X-Amzn-Waf-Action": "challenge"}
    found = detect_challenge(status=202, body=b"", headers=hdrs)
    u = unavailable_from_challenge(found, status=202, headers=hdrs, url=URL)
    assert u.categoria == "ambiental_desafio"
    assert u.evidencia["cabecalho"] == "x-amzn-waf-action"
    http = HTTPMetadata(403, (("content-type", "text/html"),))
    assert map_transport_error(HTTPStatusError(403, http=http), URL).categoria == "recusa_identificado"


def test_503_e_fonte_fora():
    u = map_transport_error(HTTPStatusError(503), URL)
    assert (u.reason, u.categoria) == ("http_503", "fonte_fora")
    assert u.evidencia["status"] == 503


@pytest.mark.parametrize("exc", [Timeout("t"), TransportError("tls")])
def test_timeout_e_falha_de_conexao_sao_fonte_fora(exc):
    u = map_transport_error(exc, URL)
    assert u.categoria == "fonte_fora" and u.evidencia


def test_corpo_vazio_e_resposta_inesperada():
    u = map_transport_error(EmptyBody("vazio"), URL)
    assert (u.reason, u.categoria) == ("corpo_vazio", "resposta_inesperada")


def test_202_sem_prova_nao_e_ambiental():
    u = map_transport_error(HTTPStatusError(202), URL)
    assert u.reason == "desafio_aws_waf" and u.categoria == "resposta_inesperada"


def test_json_invalido_e_resposta_inesperada():
    assert Unavailable("resposta_invalida").categoria == "resposta_inesperada"
    assert Unavailable("resposta_inesperada").categoria == "resposta_inesperada"
    assert Unavailable("sem_url").categoria is None
    assert Unavailable("sem_url").classificacao() == {}


def test_categoria_invalida_recusada():
    with pytest.raises(ValueError):
        Unavailable("x", "inventada")


def test_erro_nao_de_transporte_nao_e_mapeado():
    assert map_transport_error(ValueError("bug")) is None


def test_tabela_de_assinaturas_versionada():
    assert ASSINATURAS_VERSAO == 1
    assert dict(_HEADER_MARKERS) == {"x-amzn-waf-action": "aws_waf", "cf-mitigated": "cloudflare"}
    assert ("awswafintegration", "aws_waf") in _BODY_MARKERS
    for marcador, kind in _BODY_MARKERS:
        found = detect_challenge(status=200, body=f"<html>{marcador}</html>".encode())
        assert found is not None, marcador
    assert detect_challenge(status=200, body=b'{"ok": true}') is None


def test_classificacao_aditiva_na_saida():
    u = Unavailable("http_503", "fonte_fora", {"status": 503})
    assert u.classificacao() == {
        "categoria": "fonte_fora",
        "evidencia_indisponibilidade": {"status": 503},
    }


# --- hook de tests/live/conftest.py ------------------------------------------------

_CONFTEST = "from tests.live.conftest import pytest_runtest_makereport  # noqa: F401\n"


def _rodar(pytester, corpo, marca="@pytest.mark.live"):
    pytester.makeconftest(_CONFTEST)
    pytester.makeini("[pytest]\nmarkers =\n    live: x\n")
    pytester.makepyfile(
        f"import pytest\nfrom freoa_verifica.connectors.base import Unavailable\n{marca}\n"
        f"def test_x():\n    {corpo}\n"
    )
    return pytester.runpytest("-p", "no:cacheprovider", "-rx")


def test_hook_ambiental_com_evidencia_vira_xfail(pytester):
    r = _rodar(pytester, "raise Unavailable('desafio_aws_waf', 'ambiental_desafio', {'status': 403})")
    r.assert_outcomes(xfailed=1)


def test_hook_fonte_fora_com_evidencia_vira_xfail(pytester):
    r = _rodar(pytester, "raise Unavailable('http_503', 'fonte_fora', {'status': 503})")
    r.assert_outcomes(xfailed=1)


def test_hook_motivo_do_xfail(pytester):
    r = _rodar(pytester, "raise Unavailable('http_503', 'fonte_fora', {'status': 503})")
    r.stdout.fnmatch_lines(["*fonte_fora:http_503*"])


@pytest.mark.parametrize(
    "corpo",
    [
        "raise Unavailable('desafio_aws_waf', 'ambiental_desafio')",
        "raise Unavailable('http_503', 'fonte_fora', {})",
        "raise Unavailable('http_403', 'recusa_identificado', {'status': 403})",
        "raise Unavailable('resposta_invalida')",
        "raise Unavailable('bug', 'regressao', {'status': 200})",
        "assert False",
        "raise RuntimeError('inesperada')",
    ],
)
def test_hook_outras_falhas_permanecem_falha(pytester, corpo):
    _rodar(pytester, corpo).assert_outcomes(failed=1)


def test_hook_fora_da_fase_call_nao_converte(pytester):
    pytester.makeconftest(_CONFTEST)
    pytester.makeini("[pytest]\nmarkers =\n    live: x\n")
    pytester.makepyfile(
        "import pytest\nfrom freoa_verifica.connectors.base import Unavailable\n"
        "@pytest.fixture\ndef f():\n    raise Unavailable('x', 'ambiental_desafio', {'status': 1})\n"
        "@pytest.mark.live\ndef test_x(f):\n    pass\n"
    )
    pytester.runpytest("-p", "no:cacheprovider").assert_outcomes(errors=1)


def test_hook_sem_marca_live_nao_converte(pytester):
    r = _rodar(pytester, "raise Unavailable('x', 'ambiental_desafio', {'status': 1})", marca="")
    r.assert_outcomes(failed=1)


def test_exigir_disponivel():
    from tests.live.conftest import exigir_disponivel

    assert exigir_disponivel({"status": "ok"}) == {"status": "ok"}
    with pytest.raises(Unavailable) as ei:
        exigir_disponivel({
            "status": "unavailable", "motivo": "http_503", "categoria": "fonte_fora",
            "evidencia_indisponibilidade": {"status": 503},
        })
    assert ei.value.categoria == "fonte_fora" and ei.value.evidencia == {"status": 503}
