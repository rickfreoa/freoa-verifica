"""B1: as notas da release são só a seção da versão da tag, extraída do CHANGELOG real."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "notas_da_versao.py"
CHANGELOG = ROOT / "CHANGELOG.md"

pytestmark = pytest.mark.repositorio


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("notas_da_versao", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_secao_da_1_4_0a1_nao_traz_ferramenta_externa_nem_outras_secoes(mod):
    texto = mod.notas_da_versao(CHANGELOG.read_text(encoding="utf-8"), "v1.4.0a1")
    assert texto.startswith("## 1.4.0a1")
    assert not re.search(r"jus\s*ratio", texto, re.IGNORECASE)
    assert "## 1.2.0" not in texto and "## 1.3.0" not in texto
    assert len(re.findall(r"^## ", texto, re.MULTILINE)) == 1


def test_todo_o_changelog_esta_livre_de_comparacao_nominal():
    assert not re.search(r"jus\s*ratio", CHANGELOG.read_text(encoding="utf-8"), re.IGNORECASE)


def test_secao_intermediaria_e_a_ultima(mod):
    texto = CHANGELOG.read_text(encoding="utf-8")
    assert mod.notas_da_versao(texto, "1.2.0").startswith("## 1.2.0 (19/10/2026)")
    assert "## 1.1.0" not in mod.notas_da_versao(texto, "1.2.0")
    assert mod.notas_da_versao(texto, "1.0.0").startswith("## 1.0.0")


def test_versao_ausente_ou_prefixo_parcial_falha(mod):
    texto = CHANGELOG.read_text(encoding="utf-8")
    for versao in ("9.9.9", "1.4.0", "1.4.0a", "1.4"):
        with pytest.raises(LookupError):
            mod.notas_da_versao(texto, versao)


def test_secao_vazia_falha(mod):
    with pytest.raises(LookupError):
        mod.notas_da_versao("# H\n\n## 1.0.0\n\n## 0.9.0\n- x\n", "1.0.0")


def test_cli_grava_arquivo_e_falha_sem_secao(tmp_path):
    saida = tmp_path / "notas.md"
    ok = subprocess.run([sys.executable, "-I", str(SCRIPT), "v1.4.0a1", str(CHANGELOG), str(saida)],
                        capture_output=True, text=True)
    assert ok.returncode == 0 and saida.read_text(encoding="utf-8").startswith("## 1.4.0a1")
    ruim = subprocess.run([sys.executable, "-I", str(SCRIPT), "v9.9.9", str(CHANGELOG), str(tmp_path / "x.md")],
                          capture_output=True, text=True)
    assert ruim.returncode == 1 and not (tmp_path / "x.md").exists()


def test_workflow_usa_o_extrator_e_nao_o_changelog_inteiro():
    rel = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "scripts/notas_da_versao.py" in rel
    assert "--notes-file CHANGELOG.md" not in rel
    assert '--notes-file "$RUNNER_TEMP/notas.md"' in rel
