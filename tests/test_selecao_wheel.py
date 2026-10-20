"""A seleção do job da wheel instalada não pode depender de `scripts/` nem de `freoa_verifica/` por caminho (A02)."""

from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.repositorio

TESTES = Path(__file__).resolve().parent
# Único arquivo de scripts/ que o job copia (ci.yml).
PERMITIDO = "instalar-freoa-verifica.ps1"
CAMINHO = re.compile(r"(?:^|[\\/])(?:scripts|freoa_verifica)(?:[\\/]|$)")


def _caminhos_proibidos(no: ast.AST) -> list[str]:
    achados = []
    for n in ast.walk(no):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and CAMINHO.search(n.value):
            if PERMITIDO not in n.value:
                achados.append(n.value)
    return achados


def _selecionados(copia: Path) -> dict[str, set[str]]:
    ambiente = {**os.environ, "PYTHONSAFEPATH": "1"}
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "--collect-only", "-q", "-m", "not live and not repositorio",
         "-p", "no:cacheprovider"],
        cwd=copia, env=ambiente, capture_output=True, text=True, timeout=300,
    )
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    por_arquivo: dict[str, set[str]] = {}
    for linha in r.stdout.splitlines():
        if "::" in linha:
            arquivo, resto = linha.split("::", 1)
            por_arquivo.setdefault(arquivo, set()).add(resto.split("[", 1)[0].split("::")[-1])
    return por_arquivo


def test_selecao_da_wheel_sem_dependencia_de_scripts_ou_pacote_por_caminho():
    # cópia fora do checkout (o tmp_path do pytest fica dentro dele)
    with tempfile.TemporaryDirectory() as tmp:
        copia = Path(tmp)
        shutil.copytree(TESTES, copia / "tests", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        selecao = _selecionados(copia)
        violacoes = _violacoes(copia, selecao)
    assert not violacoes, violacoes


def _violacoes(copia: Path, selecao: dict[str, set[str]]) -> list[str]:
    violacoes = []
    for arquivo, nomes in selecao.items():
        arvore = ast.parse((copia / arquivo).read_text(encoding="utf-8-sig"))
        # nomes de módulo que carregam caminho proibido (ex.: RAIZ / "scripts" / ...)
        globais = {
            alvo.id
            for no in arvore.body if isinstance(no, ast.Assign) and _caminhos_proibidos(no)
            for alvo in no.targets if isinstance(alvo, ast.Name)
        }
        for no in ast.walk(arvore):
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)) and no.name in nomes:
                usados = {n.id for n in ast.walk(no) if isinstance(n, ast.Name)}
                if _caminhos_proibidos(no) or usados & globais:
                    violacoes.append(f"{arquivo}::{no.name}")
    return violacoes


def test_violacoes_acusa_teste_selecionado_com_caminho(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text(
        "RAIZ = 1\nS = RAIZ / 'scripts' / 'a.py'\n\ndef test_a():\n    S.read_text()\n\ndef test_b():\n    pass\n",
        encoding="utf-8",
    )
    assert _violacoes(tmp_path, {"tests/test_x.py": {"test_a", "test_b"}}) == ["tests/test_x.py::test_a"]


def test_detector_pega_caminho_proibido():
    assert _caminhos_proibidos(ast.parse('p = RAIZ / "scripts" / "x.py"'))
    assert _caminhos_proibidos(ast.parse('p = "freoa_verifica/captura.py"'))
    assert not _caminhos_proibidos(ast.parse('p = "scripts/instalar-freoa-verifica.ps1"'))
