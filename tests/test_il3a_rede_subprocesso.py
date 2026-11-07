"""IL.3-a RED2c: os testes que instalam o gancho de auditoria rodam em subprocesso; o processo do pytest não o carrega.

`sys.addaudithook` não tem remoção. Instalado no processo do pytest, o gancho contaminaria todos os testes seguintes
(custo medido de ~14% e semântica de eventos alterada). O corpo dos testes está em `_il3a_rede_corpo.py` e roda aqui em
um único subprocesso do pytest, com as mesmas asserções de antes."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.repositorio

RAIZ = Path(__file__).resolve().parents[1]
CORPO = RAIZ / "tests" / "_il3a_rede_corpo.py"
if not CORPO.exists():  # job da wheel: sem checkout
    pytest.skip("exige o checkout (tests/)", allow_module_level=True)

TOTAL_NO_CORPO = 34  # 11 testes simples + 23 parâmetros de `test_b5_autoteste_falha_se_qualquer_primitiva_escapar`


def test_corpo_dos_testes_de_rede_em_subprocesso_unico(tmp_path):
    r = subprocess.run([sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rs", str(CORPO),
                        "--basetemp", str(tmp_path / "filho")], capture_output=True, text=True, timeout=600,
                       cwd=str(RAIZ))
    assert r.returncode == 0, (r.stdout[-4000:], r.stderr[-2000:])
    contagem = {k: int(n) for n, k in re.findall(r"(\d+) (passed|skipped|failed|error)", r.stdout.splitlines()[-1])}
    assert contagem.get("passed", 0) + contagem.get("skipped", 0) == TOTAL_NO_CORPO, r.stdout[-2000:]


def test_sentinela_nenhum_gancho_de_auditoria_no_processo_do_pytest():
    """Executado por último (conftest). O executor registra `sys._porta_l_gancho_instalado` ao instalar o gancho: o
    marcador não pode existir aqui, nem em nenhum módulo do executor carregado neste processo."""
    assert not getattr(sys, "_porta_l_gancho_instalado", False), "gancho de auditoria instalado no processo do pytest"
    for nome, mod in list(sys.modules.items()):
        assert not getattr(mod, "_gancho_instalado", False), f"{nome} instalou o gancho no processo do pytest"
