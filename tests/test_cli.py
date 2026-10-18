"""Testes do CLI `fv` — paridade com o serviço via --json."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from freoa_verifica.cli import main
from freoa_verifica.service import Verifica


def test_fv_help():
    r = subprocess.run(
        [sys.executable, "-m", "freoa_verifica.cli", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    assert "busca" in r.stdout
    assert "verifica-texto" in r.stdout
    assert "serve-mcp" in r.stdout


def test_fv_doctor_offline(verifica_populada, monkeypatch, capsys):
    svc, *_ = verifica_populada
    monkeypatch.setenv("FV_HOME", str(svc.home))
    with pytest.raises(SystemExit) as ei:
        main(["doctor", "--offline", "--json"])
    assert ei.value.code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"


def test_paridade_verifica_cli_servico(verifica_populada, monkeypatch, capsys):
    svc, rw, doc = verifica_populada
    monkeypatch.setenv("FV_HOME", str(svc.home))
    trecho = "A alienação, direta ou indireta, do controle de companhia aberta"
    citacao = "art. 254-A da Lei 6.404/76"

    esperado = svc.verificar_citacao(citacao, trecho=trecho)
    # remover run_id (único por chamada)
    esperado.pop("run_id", None)

    with pytest.raises(SystemExit) as ei:
        main(["verifica", citacao, "--trecho", trecho, "--json"])
    assert ei.value.code == 0
    obtido = json.loads(capsys.readouterr().out)
    obtido.pop("run_id", None)
    assert obtido["identity"] == esperado["identity"]
    assert obtido["text"]["status"] == esperado["text"]["status"]
    assert obtido["support"]["status"] == "not_assessed"


def test_paridade_verificar_texto(verifica_populada, monkeypatch, capsys, tmp_path):
    svc, rw, doc = verifica_populada
    monkeypatch.setenv("FV_HOME", str(svc.home))
    texto = "Ver art. 254-A da Lei 6.404/76 neste parecer."
    arq = tmp_path / "parecer.txt"
    arq.write_text(texto, encoding="utf-8")

    esperado = svc.verificar_texto(texto)
    with pytest.raises(SystemExit):
        main(["verifica-texto", str(arq), "--json"])
    obtido = json.loads(capsys.readouterr().out)
    assert obtido["total"] == esperado["total"]
    assert [c["status"] for c in obtido["citacoes"]] == [
        c["status"] for c in esperado["citacoes"]
    ]


def test_fv_lei_json(verifica_populada, monkeypatch, capsys):
    svc, *_ = verifica_populada
    monkeypatch.setenv("FV_HOME", str(svc.home))
    with pytest.raises(SystemExit):
        main(["lei", "art. 254-A da Lei 6.404/76", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "encontrada"
    assert data["texto"]
