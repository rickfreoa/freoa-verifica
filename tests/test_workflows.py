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
    re.compile(r"\|\|\s*(?:true|:|exit\s+0)(?![\w-])"),  # `\b` não reconhece `:` no fim da linha
    re.compile(r";\s*(?:true|:)\s*(?:#.*)?$"),
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
    "      - run: pytest -q || :\n",
    "      - run: pytest -q || : # ignora\n",
    "      - run: pytest -q ||true\n",
    "      - run: pytest -q; true\n",
    "      - run: pytest -q ; true\n",
    "      - run: pytest -q; :\n",
    "      - run: pytest -q || true; echo ok\n",
    "    continue-on-error: true  # gate-nao-bloqueante:\n",  # motivo vazio não vale
])
def test_yaml_adulterado_e_reprovado(trecho):
    base = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert mascaramentos(base) == []
    assert mascaramentos(base + trecho)


@pytest.mark.parametrize("linha", [
    "pytest || :", "pytest || true", "pytest || exit 0", "pytest; true", "pytest;true", "pytest ||:",
])
def test_mascaramento_isolado_e_reconhecido(linha):
    assert mascaramentos(f"- run: {linha}\n")


@pytest.mark.parametrize("linha", [
    "pytest || exit 1", "echo 'a; true'", "pytest || trueish", "pytest || exit 01", "python -c 'x = {1: 2}'",
    "echo ok; true_check", "cmd || :foo",
])
def test_comando_legitimo_nao_e_mascaramento(linha):
    assert mascaramentos(f"- run: {linha}\n") == []


def test_excecao_documentada_e_aceita_e_false_passa():
    ok = (
        "    continue-on-error: true  # gate-nao-bloqueante: sonda semanal\n"
        "    continue-on-error: false\n"
        "# continue-on-error: true\n"
    )
    assert mascaramentos(ok) == []


def instalacoes_sem_trava(texto: str) -> list[str]:
    """`pip install` sem hashes nem `--no-deps`, e `python -m build` com isolamento (resolve de novo, sem lock)."""
    achados = []
    for linha in texto.splitlines():
        s = linha.strip()
        if s.startswith("#"):
            continue
        if re.search(r"\bpip install\b", s) and "--require-hashes" not in s and "--no-deps" not in s:
            achados.append(s)
        if re.search(r"-m build\b", s) and "--no-isolation" not in s:
            achados.append(s)
    return achados


@pytest.mark.parametrize("nome", ["ci.yml", "release.yml"])
def test_build_e_instalacao_so_com_locks(nome):
    assert instalacoes_sem_trava((ROOT / ".github/workflows" / nome).read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("trecho", [
    "python -m pip install --upgrade pip build\n",
    "python -m pip install -e .\n",
    "pip install dist/*.whl\n",
    "python -m build\n",
    "pip install \"$(ls dist/*.whl)[server]\"\n",
])
def test_instalacao_sem_trava_e_reprovada(trecho):
    assert instalacoes_sem_trava(trecho)


def test_release_instala_locks_e_publica_o_lock_do_ci():
    rel = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "pip install --require-hashes -r requirements/build.lock" in rel
    assert "python -m build --no-isolation" in rel
    assert "pip install --require-hashes -r requirements/ci.lock" in rel
    assert "pip install --no-deps dist/*.whl" in rel
    assert "cp requirements/ci.lock dist/requirements-lock.txt" in rel and "pip freeze" not in rel
    repo = ci.split("  repositorio:")[1].split("\n  lint:")[0]
    assert "requirements/build.lock" in repo and "--no-build-isolation" in repo and "--no-deps" in repo


def test_pypi_so_depois_de_publicada_a_release():
    pypi = (ROOT / ".github/workflows/pypi.yml").read_text(encoding="utf-8")
    rel = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "types: [published]" in pypi and "environment: pypi" in pypi
    assert "id-token: write" in pypi and "vars.PYPI_PUBLICAR == 'true'" in pypi
    for passo in ("gh release download", "sha256sum -c SHA256SUMS",
                  "gh attestation verify", "--repo rickfreoa/freoa-verifica"):
        assert passo in pypi
    assert "--draft" in rel and "gh-action-pypi-publish" not in rel
