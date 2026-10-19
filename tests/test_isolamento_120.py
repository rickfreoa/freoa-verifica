"""Regressões A6: processos reais; nenhum perfil/env hostil no produto."""
import os
import subprocess
import sys

import pytest

from freoa_verifica.parsers import isolated


def hostile(monkeypatch, tmp_path, body, *, before=""):
    script = tmp_path / "hostile.py"
    script.write_text("from freoa_verifica.parsers import isolated as m\n" + before +
                      "\ndef attack(data):\n" + "\n".join("    " + l for l in body.splitlines()) +
                      "\nm.pdf_texto = attack\nm._main()\n", encoding="utf-8")
    real = subprocess.Popen
    def launch(args, **kwargs):
        return real([sys.executable, str(script), "pdf_texto"], **kwargs)
    monkeypatch.setattr(isolated.subprocess, "Popen", launch)


def test_memory_hostile_quarantined(monkeypatch, tmp_path):
    hostile(monkeypatch, tmp_path, "x = bytearray(1100 * 1024**2)\nraise AssertionError('limite ignorado')")
    doc = isolated.parse_isolated("pdf_texto", b"x", 30)
    assert doc.quarantined
    assert "memoria_excedida" in doc.issues[0].detail
    assert bytearray(1024)  # pai permanece operacional


@pytest.mark.parametrize("pipe,reason", [(1, "stdout_excedido"), (2, "stderr_excedido")])
def test_output_hostile_killed(monkeypatch, tmp_path, pipe, reason):
    hostile(monkeypatch, tmp_path, f"import os\nwhile True: os.write({pipe}, b'x' * 65536)")
    doc = isolated.parse_isolated("pdf_texto", b"x", 30)
    assert doc.quarantined and reason in doc.issues[0].detail


def test_descendants_denied(monkeypatch, tmp_path):
    if os.name != "nt":
        import resource
        if os.geteuid() == 0 or not hasattr(resource, "RLIMIT_NPROC"):
            pytest.skip("NPROC inaplicável a root/sem suporte")
    hostile(monkeypatch, tmp_path,
            "import subprocess, sys\nsubprocess.run([sys.executable, '-c', 'pass'], check=True)\n"
            "return m.ParsedDocument('pdf_texto', '1', '', None, 'DESCENDENTE CRIADO')")
    doc = isolated.parse_isolated("pdf_texto", b"x", 30)
    assert doc.quarantined
    assert any(e in doc.issues[0].detail for e in ("OSError", "BlockingIOError", "PermissionError"))


def test_limit_install_failure_closed(monkeypatch, tmp_path):
    hostile(monkeypatch, tmp_path, "raise AssertionError('leu entrada')",
            before="def fail(profile): raise OSError('simulado')\nm._aplicar_limites = fail\n")
    doc = isolated.parse_isolated("pdf_texto", b"x", 30)
    assert doc.quarantined
    assert "exit=78" in doc.issues[0].detail
    assert "limites_nao_instalados" in doc.issues[0].detail


def test_cpu_hostile_killed(monkeypatch, tmp_path):
    hostile(monkeypatch, tmp_path, "while True: pass", before="m._LIMITES['pdf_texto'] = (1024, 1)\n")
    doc = isolated.parse_isolated("pdf_texto", b"x", 15)
    assert doc.quarantined and "timeout" not in doc.issues[0].detail


def test_input_refused_before_launch(monkeypatch):
    monkeypatch.setattr(isolated, "INPUT_LIMIT", 5)
    monkeypatch.setattr(isolated.subprocess, "Popen", lambda *a, **k: pytest.fail("lançou filho"))
    for data in (b"123456", "ééé"):
        assert "entrada_excedida" in isolated.parse_isolated("planalto", data, 2).issues[0].detail


def test_all_profiles_limited():
    assert set(isolated._LIMITES) == set(isolated._PROFILES)
    for profile, limits in isolated._LIMITES.items():
        assert limits == ((1024, 60) if profile in {"pdf_texto", "cvm_pdf"} else (2048, 120))
