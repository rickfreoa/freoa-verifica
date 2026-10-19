"""Testes live: indisponibilidade ambiental provada vira xfail; o resto continua falha (decisão 0045)."""

from __future__ import annotations

import pytest

from freoa_verifica.connectors.base import Unavailable

_XFAIL_CATEGORIAS = frozenset({"ambiental_desafio", "fonte_fora"})


def exigir_disponivel(resultado):
    """Levanta `Unavailable` tipada se `resultado` for indisponibilidade; senão devolve o resultado.

    Aceita a exceção, ou o dicionário de saída do serviço (`status` unavailable/indisponivel).
    """
    if isinstance(resultado, Unavailable):
        raise resultado
    if isinstance(resultado, dict) and resultado.get("status") in {"unavailable", "indisponivel"}:
        raise Unavailable(
            str(resultado.get("motivo") or resultado.get("reason_code") or "indisponivel"),
            resultado.get("categoria"),
            resultado.get("evidencia_indisponibilidade"),
        )
    return resultado


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    if call.when != "call" or call.excinfo is None or item.get_closest_marker("live") is None:
        return
    exc = call.excinfo.value
    if (
        isinstance(exc, Unavailable)
        and exc.categoria in _XFAIL_CATEGORIAS
        and exc.evidencia
    ):
        report = outcome.get_result()
        report.outcome = "skipped"
        report.wasxfail = f"{exc.categoria}:{exc.reason}"
