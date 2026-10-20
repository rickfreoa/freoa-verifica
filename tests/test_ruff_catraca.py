"""Catraca do Ruff: `--atualizar` só reduz a baseline; `--inicializar` só cria (A13)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.repositorio

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ruff_catraca.py"


@pytest.fixture
def catraca(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("ruff_catraca", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "RAIZ", tmp_path)
    monkeypatch.setattr(mod, "BASELINE", tmp_path / "ruff-baseline.json")
    achados = []
    monkeypatch.setattr(mod, "rodar_ruff", lambda: list(achados))
    mod.achados = achados
    return mod


def _achado(tmp_path, regra="E501", msg="longa", arquivo="a.py"):
    return {"filename": str(tmp_path / arquivo), "code": regra, "message": msg}


def _baseline(mod):
    return {(d["arquivo"], d["regra"], d["mensagem"]): d["n"] for d in json.loads(mod.BASELINE.read_text("utf-8"))}


def test_inicializar_cria_e_recusa_se_existe(catraca, tmp_path):
    catraca.achados += [_achado(tmp_path)]
    assert catraca.main(["--inicializar"]) == 0
    antes = catraca.BASELINE.read_bytes()
    catraca.achados += [_achado(tmp_path, "S307", "eval")]
    assert catraca.main(["--inicializar"]) == 1
    assert catraca.BASELINE.read_bytes() == antes


def test_atualizar_recusa_achado_novo(catraca, tmp_path):
    catraca.achados += [_achado(tmp_path)]
    catraca.main(["--inicializar"])
    antes = catraca.BASELINE.read_bytes()
    catraca.achados.append(_achado(tmp_path, "S307", "uso de eval"))
    assert catraca.main(["--atualizar"]) == 1
    assert catraca.BASELINE.read_bytes() == antes


def test_atualizar_recusa_aumento_de_contagem(catraca, tmp_path):
    catraca.achados += [_achado(tmp_path)]
    catraca.main(["--inicializar"])
    antes = catraca.BASELINE.read_bytes()
    catraca.achados.append(_achado(tmp_path))
    assert catraca.main(["--atualizar"]) == 1
    assert catraca.BASELINE.read_bytes() == antes


def test_atualizar_aceita_reducao(catraca, tmp_path):
    catraca.achados += [_achado(tmp_path), _achado(tmp_path), _achado(tmp_path, "F401", "import", "b.py")]
    catraca.main(["--inicializar"])
    catraca.achados.pop(0)
    catraca.achados.pop()
    assert catraca.main(["--atualizar"]) == 0
    assert _baseline(catraca) == {("a.py", "E501", "longa"): 1}


def test_atualizar_sem_baseline_falha(catraca, tmp_path):
    with pytest.raises(FileNotFoundError):
        catraca.main(["--atualizar"])
    assert not catraca.BASELINE.exists()


def test_conferir_continua_reprovando_excesso(catraca, tmp_path):
    catraca.main(["--inicializar"])
    catraca.achados.append(_achado(tmp_path))
    assert catraca.main([]) == 1
