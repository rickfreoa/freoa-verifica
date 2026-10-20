"""Resposta recebida porém inválida não é indisponibilidade da fonte (decisão 0045, A01).

Ponta a ponta: transporte real contra servidor local → classificação → hook dos testes live.
"""

from __future__ import annotations

import pytest

from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.challenge import map_transport_error
from freoa_verifica.connectors.httputil import connector_fetch
from freoa_verifica.transport import RespostaInvalida, TooLarge, TransportError
from tests.test_transport import (  # noqa: F401  (fixtures e helpers do servidor local)
    ALLOWED,
    _fast_guards,
    _Handler,
    _wire_local,
    local_server,
)

pytest_plugins = ["pytester"]
_CONFTEST = "from tests.live.conftest import pytest_runtest_makereport  # noqa: F401\n"


def _buscar(monkeypatch, local_server, **kw):
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, local_server[1])
    return connector_fetch(
        "https://example.com/", hosts=ALLOWED, path_prefixes=None,
        mimes=frozenset({"application/json"}), timeout=5, **kw,
    )


def test_mime_proibido_em_200_e_resposta_inesperada(monkeypatch, local_server):
    _Handler.body = b"<html>x</html>"
    _Handler.content_type = "text/html"
    with pytest.raises(Unavailable) as ei:
        _buscar(monkeypatch, local_server)
    u = ei.value
    assert u.categoria == "resposta_inesperada"
    assert u.evidencia["status"] == 200 and "MIME" in str(u.__cause__)


def test_corpo_acima_do_limite_e_resposta_inesperada(monkeypatch, local_server):
    _Handler.body = b"x" * 100
    _Handler.content_type = "application/json"
    with pytest.raises(Unavailable) as ei:
        _buscar(monkeypatch, local_server, max_bytes=10)
    assert ei.value.categoria == "resposta_inesperada"


@pytest.mark.parametrize("exc", [RespostaInvalida("framing"), TooLarge("grande")])
def test_tipos_de_resposta_invalida(exc):
    assert map_transport_error(exc, "https://x.gov.br/").categoria == "resposta_inesperada"


def test_falha_de_conexao_continua_fonte_fora():
    assert map_transport_error(TransportError("tls"), "https://x.gov.br/").categoria == "fonte_fora"


def test_hook_nao_converte_mime_invalido_em_xfail(monkeypatch, local_server, pytester):
    _Handler.body = b"<html>x</html>"
    _Handler.content_type = "text/html"
    with pytest.raises(Unavailable) as ei:
        _buscar(monkeypatch, local_server)
    u = ei.value
    pytester.makeconftest(_CONFTEST)
    pytester.makeini("[pytest]\nmarkers =\n    live: x\n")
    pytester.makepyfile(
        "import pytest\nfrom freoa_verifica.connectors.base import Unavailable\n"
        "@pytest.mark.live\ndef test_x():\n"
        f"    raise Unavailable({u.reason!r}, {u.categoria!r}, {u.evidencia!r})\n"
    )
    pytester.runpytest("-p", "no:cacheprovider").assert_outcomes(failed=1)
