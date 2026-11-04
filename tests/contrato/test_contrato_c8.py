"""IL.0-R, correção de C8, achado 2: falha de I/O da chave nos três adaptadores (Python, MCP, REST)."""

from __future__ import annotations

import pathlib

import pytest

from freoa_verifica import registro
from tests.contrato import harness as h
from tests.contrato.test_contrato import _responder, ambiente  # noqa: F401

FALHAS = [PermissionError(13, "acesso negado"), IsADirectoryError(21, "diretório no lugar do arquivo"),
          OSError(5, "falha de leitura")]


@pytest.mark.parametrize("adaptador", h.ADAPTADORES)
@pytest.mark.parametrize("exc", FALHAS, ids=["acesso_negado", "diretorio", "falha_leitura"])
def test_c8_falha_de_io_da_chave_e_resposta_controlada_nos_tres_adaptadores(ambiente, monkeypatch, adaptador, exc):  # noqa: F811
    svc = ambiente["python"]
    chave = svc.home / registro.ARQUIVO_CHAVE
    antes = chave.read_bytes()
    original = pathlib.Path.read_bytes

    def lendo(self):
        if self.name == registro.ARQUIVO_CHAVE:
            raise exc
        return original(self)

    registro._cache_chaves.clear()
    monkeypatch.setattr(pathlib.Path, "read_bytes", lendo)
    r = _responder(ambiente, adaptador, "obter_registro", {"run_id": "@run_id_valido"})
    assert r["status"] == "encontrada"
    assert r["integridade"]["confere"] is False
    assert r["estado"] is None and r["parametros"] is None and r["evidencias"] is None
    monkeypatch.undo()
    assert chave.read_bytes() == antes
