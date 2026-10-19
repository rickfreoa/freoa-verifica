"""Auditoria 1.2.0 (M2 residual): neto que sai do grupo com setsid não prende o pai além do prazo."""
import os
import subprocess
import sys
import time

import pytest

from freoa_verifica.parsers import isolated


@pytest.mark.skipif(os.name != "posix", reason="setsid é POSIX")
def test_neto_com_setsid_nao_prende_o_pai(monkeypatch):
    codigo = ("import os,subprocess,sys; subprocess.Popen([sys.executable,'-c',"
              "'import os,time; os.setsid(); time.sleep(40)']); print('{}')")
    real = subprocess.Popen
    monkeypatch.setattr(isolated.subprocess, "Popen", lambda args, **kw: real([sys.executable, "-c", codigo], **kw))
    t0 = time.monotonic()
    doc = isolated.parse_isolated("bcb_json", b"{}", 3)
    assert time.monotonic() - t0 < 25 and doc.parser_version == "0"
