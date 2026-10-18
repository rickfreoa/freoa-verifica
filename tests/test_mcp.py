"""Testes MCP — cliente em memória do SDK oficial."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys

import pytest


def _tool_payload(result) -> dict:
    if getattr(result, "structured_content", None):
        sc = result.structured_content
        if isinstance(sc, dict):
            return sc
    texts = []
    for block in getattr(result, "content", []) or []:
        t = getattr(block, "text", None)
        if t:
            texts.append(t)
    raw = "\n".join(texts).strip()
    if not raw:
        return {}
    return json.loads(raw)


def test_mcp_listar_e_verificar(verifica_populada, monkeypatch):
    pytest.importorskip("mcp")
    from mcp import Client

    from freoa_verifica import mcp_server as ms
    from freoa_verifica.mcp_server import create_mcp

    svc, rw, doc = verifica_populada
    monkeypatch.setenv("FV_HOME", str(svc.home))

    if ms._svc is not None:
        try:
            ms._svc.close()
        except Exception:  # noqa: BLE001
            pass
        ms._svc = None

    mcp = create_mcp(home=str(svc.home))
    # Força o singleton a ser a mesma instância já populada do fixture
    ms._svc = svc
    mcp_svc = svc

    trecho = "A alienação, direta ou indireta, do controle de companhia aberta"
    citacao = "art. 254-A da Lei 6.404/76"
    esperado = svc.verificar_citacao(citacao, trecho=trecho)
    esperado.pop("run_id", None)
    texto = f"Conforme {citacao}."
    esperado_txt = svc.verificar_texto(texto)

    async def _run() -> None:
        async with Client(mcp) as client:
            tools = await client.list_tools()
            names = {t.name for t in tools.tools}
            assert "verificar_citacao" in names
            assert "verificar_texto" in names
            assert "buscar_legislacao" in names
            assert "sincronizar" not in names

            r = await client.call_tool(
                "verificar_citacao",
                {"citacao": citacao, "trecho": trecho},
            )
            assert not r.is_error
            obtido = _tool_payload(r)
            obtido.pop("run_id", None)
            assert obtido["identity"]["status"] == esperado["identity"]["status"]
            assert obtido["text"]["status"] == esperado["text"]["status"]

            r2 = await client.call_tool("verificar_texto", {"texto": texto})
            assert not r2.is_error
            obt_txt = _tool_payload(r2)
            assert obt_txt["total"] == esperado_txt["total"]
            assert [c["status"] for c in obt_txt["citacoes"]] == [
                c["status"] for c in esperado_txt["citacoes"]
            ]

    asyncio.run(_run())


def test_freoa_verifica_mcp_help():
    r = subprocess.run(
        [sys.executable, "-m", "freoa_verifica.mcp_server", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    assert "--http" in r.stdout
