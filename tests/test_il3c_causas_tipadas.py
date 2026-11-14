"""Regressão (CI de ad89d58): a sanitização N2 não funde causas tipadas do parser isolado.

Cada mecanismo de falha local mantém código próprio, de lista fechada, do filho ao Unavailable
sanitizado; stderr fora da tabela (exit, código) nunca entra como texto.
"""
import json
from types import SimpleNamespace

import pytest

from freoa_verifica.connectors.base import CAUSAS_PARSER, LocalParserFailure, sanitizar_falha_parser
from freoa_verifica.parsers import isolated

PRIVADO = "C:/dev/tmp/SYNTHETIC_PRIVATE detalhe"


@pytest.mark.parametrize("rc,stderr,causa,tipo", [
    (3, b"memoria_excedida\n", "memoria_excedida", None),
    (3, PRIVADO.encode(), "memoria_excedida", None),
    (78, b"limites_nao_instalados\n", "limites_nao_instalados", None),
    (77, b"", "importacao", None),
    (5, b"pdf_paginas_excedidas\n", "pdf_paginas_excedidas", None),
    (5, b"pdf_texto_excedido\n", "pdf_texto_excedido", None),
    (5, b"erro_so:BlockingIOError\n", "erro_so", "BlockingIOError"),
    (5, b"erro_so:PermissionError\n", "erro_so", "PermissionError"),
    # Código válido com exit incoerente, ou texto livre: só o exit decide.
    (4, b"pdf_paginas_excedidas\n", "exit_nao_zero", None),
    (3, b"limites_nao_instalados\n", "memoria_excedida", None),
    (5, b"erro_so:" + PRIVADO.encode() + b"\n", "exit_nao_zero", None),
    (4, PRIVADO.encode(), "exit_nao_zero", None),
    (-9, b"", "exit_nao_zero", None),
])
def test_causa_do_filho_e_tipada_e_coerente_com_o_exit(monkeypatch, rc, stderr, causa, tipo):
    monkeypatch.setattr(isolated.subprocess, "Popen", lambda *a, **k: SimpleNamespace(returncode=rc))
    monkeypatch.setattr(isolated, "_bounded_io", lambda *a: (b"", stderr, None))
    doc = isolated.parse_isolated("pdf_texto", b"x", 5)
    detalhe = doc.issues[0].detail
    assert doc.quarantined and PRIVADO not in json.dumps(doc.issues[0].__dict__)
    assert f"causa={causa}" in detalhe and f"exit={rc}" in detalhe
    assert (f"tipo={tipo}" in detalhe) if tipo else "tipo=" not in detalhe
    with pytest.raises(LocalParserFailure) as erro:
        isolated.parse_ou_indisponivel("pdf_texto", b"x", 5)
    assert erro.value.evidencia["causa"] == causa and erro.value.evidencia["exit_code"] == rc


@pytest.mark.parametrize("codigo", ["timeout", "stdout_excedido", "stderr_excedido", "leitura_falhou",
                                    "escrita_falhou", "fechamento_falhou", "descendente_reteve_pipes"])
def test_falhas_de_io_preservam_codigo_proprio(monkeypatch, codigo):
    monkeypatch.setattr(isolated.subprocess, "Popen", lambda *a, **k: SimpleNamespace(returncode=0))
    monkeypatch.setattr(isolated, "_bounded_io", lambda *a: (b"", PRIVADO.encode(), codigo))
    with pytest.raises(LocalParserFailure) as erro:
        isolated.parse_ou_indisponivel("camara_legin", b"x", 5)
    assert erro.value.evidencia["causa"] == codigo
    seguro = sanitizar_falha_parser(erro.value, perfil="camara_legin")
    assert seguro.evidencia["causa"] == codigo and PRIVADO not in json.dumps(seguro.evidencia)


def test_codigo_desconhecido_de_io_vira_protocolo(monkeypatch):
    monkeypatch.setattr(isolated.subprocess, "Popen", lambda *a, **k: SimpleNamespace(returncode=0))
    monkeypatch.setattr(isolated, "_bounded_io", lambda *a: (b"", b"", PRIVADO))
    doc = isolated.parse_isolated("pdf_texto", b"x", 5)
    assert doc.issues[0].detail == "causa=protocolo"


def test_causas_distintas_nao_se_fundem_na_sanitizacao():
    vistos = {sanitizar_falha_parser(LocalParserFailure("parser_nao_processado", None, {"causa": c}),
                                     perfil="pdf_texto").evidencia["causa"] for c in CAUSAS_PARSER}
    assert vistos == set(CAUSAS_PARSER)


@pytest.mark.parametrize("detalhe", ["causa=timeout;exit=--5", "causa=texto livre", "exit=1;causa=x",
                                     '{"causa": "timeout"}', None])
def test_leitura_do_detalhe_e_estrita(detalhe):
    campos = isolated._campos_da_falha(detalhe)
    assert set(campos) <= {"causa", "exit_code"}
    assert campos.get("causa") in CAUSAS_PARSER | {None}
    assert "exit_code" not in campos or type(campos["exit_code"]) is int
