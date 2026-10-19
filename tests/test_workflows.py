"""Meta-teste dos workflows: gate bloqueante não pode ser mascarado.

Reprova `continue-on-error` diferente de false e `|| true` (ou equivalente) em
`.github/workflows/*.yml`. Exceção só com `# gate-nao-bloqueante: <motivo>` na
mesma linha.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.repositorio

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((ROOT / ".github/workflows").glob("*.yml"))

MASCARAS = (
    re.compile(r"\bcontinue-on-error:\s*(?!false\b)\S"),
    re.compile(r"\|\|\s*(?:true|:|exit\s+0)\b"),
)
EXCECAO = re.compile(r"#\s*gate-nao-bloqueante:\s*\S")


def mascaramentos(texto: str) -> list[tuple[int, str]]:
    achados = []
    for n, linha in enumerate(texto.splitlines(), 1):
        if linha.lstrip().startswith("#") or EXCECAO.search(linha):
            continue
        if any(m.search(linha) for m in MASCARAS):
            achados.append((n, linha.strip()))
    return achados


def test_ha_workflows_no_checkout():
    nomes = {p.name for p in WORKFLOWS}
    assert {"ci.yml", "release.yml", "pypi.yml"} <= nomes


@pytest.mark.parametrize("arquivo", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_sem_gate_mascarado(arquivo):
    assert mascaramentos(arquivo.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("trecho", [
    "    continue-on-error: true\n",
    "    continue-on-error: ${{ matrix.experimental }}\n",
    "      - run: pytest -q || true\n",
    "      - run: pytest -q || exit 0\n",
    "    continue-on-error: true  # gate-nao-bloqueante:\n",  # motivo vazio não vale
])
def test_yaml_adulterado_e_reprovado(trecho):
    base = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert mascaramentos(base) == []
    assert mascaramentos(base + trecho)


def test_excecao_documentada_e_aceita_e_false_passa():
    ok = (
        "    continue-on-error: true  # gate-nao-bloqueante: sonda semanal\n"
        "    continue-on-error: false\n"
        "# continue-on-error: true\n"
    )
    assert mascaramentos(ok) == []


def test_pypi_so_depois_de_publicada_a_release():
    pypi = (ROOT / ".github/workflows/pypi.yml").read_text(encoding="utf-8")
    rel = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "types: [published]" in pypi and "environment: pypi" in pypi
    assert "id-token: write" in pypi and "vars.PYPI_PUBLICAR == 'true'" in pypi
    for passo in ("gh release download", "sha256sum -c SHA256SUMS",
                  "gh attestation verify", "--repo rickfreoa/freoa-verifica"):
        assert passo in pypi
    assert "--draft" in rel and "gh-action-pypi-publish" not in rel
