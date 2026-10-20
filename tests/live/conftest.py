"""Testes live: indisponibilidade ambiental provada vira xfail; o resto continua falha (decisão 0045).

Ao fim da sessão grava `saude-fontes.json` com o estado por fonte (decisão 0054).
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone

import pytest

from freoa_verifica.connectors.base import Unavailable

_XFAIL_CATEGORIAS = frozenset({"ambiental_desafio", "fonte_fora"})
_PRIORIDADE = ("regressao", "unavailable", "not_run", "ok")
_SAUDE: dict = {"inicio": None, "testes": {}}


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


def _fonte(item) -> str:
    return item.path.stem.removeprefix("test_live_")


def _commit() -> str | None:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return (r.stdout.strip() or None) if r.returncode == 0 else None


def _registrar(item, estado, categoria=None, motivo=None):
    _SAUDE["testes"][item.nodeid] = {
        "fonte": _fonte(item), "nome": item.nodeid, "estado": estado, "categoria": categoria, "motivo": motivo,
    }


def pytest_sessionstart(session):
    _SAUDE["inicio"] = datetime.now(timezone.utc).isoformat()
    _SAUDE["testes"] = {}


def pytest_collection_finish(session):
    # Todo teste live selecionado começa `not_run`; só deixa de sê-lo se de fato rodar.
    for item in session.items:
        if item.get_closest_marker("live") is not None:
            _registrar(item, "not_run")


def _consolidar(testes: dict) -> dict:
    fontes: dict = {}
    for t in testes.values():
        f = fontes.setdefault(t["fonte"], {"estado": "ok", "categoria": None, "motivo": None, "testes": []})
        f["testes"].append({k: t[k] for k in ("nome", "estado", "categoria", "motivo")})
        if _PRIORIDADE.index(t["estado"]) < _PRIORIDADE.index(f["estado"]):
            f.update(estado=t["estado"], categoria=t["categoria"], motivo=t["motivo"])
    return dict(sorted(fontes.items()))


def pytest_sessionfinish(session, exitstatus):
    testes = _SAUDE["testes"]
    if not testes:  # sessão sem teste live (suíte offline): nada a relatar
        return
    completa = int(exitstatus) in (0, 1) and all(t["estado"] != "not_run" for t in testes.values())
    relatorio = {
        "commit": _commit(),
        "inicio": _SAUDE["inicio"],
        "fim": datetime.now(timezone.utc).isoformat(),
        "completa": completa,
        "fontes": _consolidar(testes),
    }
    destino = os.environ.get("FV_SAUDE_JSON") or str(session.config.rootpath / "saude-fontes.json")
    tmp = destino + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(relatorio, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, destino)


_FASES: dict[str, dict] = {}  # nodeid -> {fase: (estado, categoria, motivo)}


def _consolidar_fases(item, fases: dict) -> None:
    """Resultado do teste só depois de setup, call e teardown: o pior estado prevalece (B2-06)."""
    if not fases:
        return _registrar(item, "not_run", None, "sem_fase_executada")
    pior = min(fases.values(), key=lambda f: _PRIORIDADE.index(f[0]))
    if pior[0] == "ok" and "call" not in fases:
        pior = ("not_run", None, "sem_fase_call")
    _registrar(item, *pior)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    if item.get_closest_marker("live") is None:
        return
    report = outcome.get_result()
    fases = _FASES.setdefault(item.nodeid, {})
    exc = call.excinfo.value if call.excinfo is not None else None
    if (
        call.when == "call"
        and isinstance(exc, Unavailable)
        and exc.categoria in _XFAIL_CATEGORIAS
        and exc.evidencia
    ):
        report.outcome = "skipped"
        report.wasxfail = f"{exc.categoria}:{exc.reason}"
        fases["call"] = ("unavailable", exc.categoria, exc.reason)
    elif exc is not None and not report.skipped:
        tipada = isinstance(exc, Unavailable)
        fases[call.when] = ("regressao", (exc.categoria if tipada else None) or "regressao",
                            (exc.reason if tipada else str(exc))[:200])
    elif report.skipped:
        fases[call.when] = ("not_run", None, "skipped")
    elif call.when == "call":
        fases["call"] = ("ok", None, None)
    if call.when == "teardown":
        _consolidar_fases(item, _FASES.pop(item.nodeid, {}))
