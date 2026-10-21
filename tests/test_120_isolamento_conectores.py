"""Auditoria 1.2.0 (B2, M1, M2): Planalto e BCB parseiam no filho limitado, com resultado idêntico ao do pai."""
import dataclasses
import hashlib
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.bcb import BcbConnector
from freoa_verifica.connectors.planalto import PlanaltoConnector
from freoa_verifica.parsers import isolated
from freoa_verifica.parsers.bcb_json import parse_bcb_json
from freoa_verifica.parsers.planalto import parse_planalto
from freoa_verifica.transport import Response

FIX = Path(__file__).parent / "fixtures"
URL = "https://www.planalto.gov.br/ccivil_03/leis/l6404consol.htm"


def _resp(body, url):
    return Response(url, url, 200, {}, body, hashlib.sha256(body).hexdigest(), "2026-10-19T00:00:00Z", [], "text/html")


def test_planalto_no_filho_identico_ao_pai():
    body = (FIX / "planalto_lei_6404_1976.html").read_bytes()
    # FIX18 (0064): sem Content-Type não há escada alternativa; o charset é o que ela deduzia (ver conftest).
    resp = dataclasses.replace(_resp(body, URL), content_type="text/html; charset=windows-1252")
    filho = PlanaltoConnector().parse(resp)
    pai = parse_planalto(body.decode("cp1252"), base_url=URL)
    assert asdict(filho) == asdict(pai) and len(pai.provisions) > 100


def test_bcb_no_filho_identico_ao_pai():
    body = (FIX / "bcb_res_cmn_4966.json").read_bytes()
    assert asdict(BcbConnector().parse(_resp(body, "https://www.bcb.gov.br/api/x"))) == asdict(parse_bcb_json(body))


def test_conector_usa_o_filho_e_falha_do_filho_e_indisponivel(monkeypatch):
    chamadas = []
    real = isolated.parse_isolated

    def espia(profile, data, timeout, **kw):
        chamadas.append(profile)
        return isolated._failure(profile, "filho_morto")
    monkeypatch.setattr(isolated, "parse_isolated", espia)
    with pytest.raises(Unavailable, match="planalto_nao_processado"):
        PlanaltoConnector().parse(_resp(b"<html></html>", URL))
    with pytest.raises(Unavailable, match="bcb_json_nao_processado"):
        BcbConnector().parse(_resp(b"{}", "https://www.bcb.gov.br/api/x"))
    assert chamadas == ["planalto", "bcb_json"]
    assert real is not espia


def test_diretorio_corrente_nao_entra_no_path_do_filho(tmp_path, monkeypatch):
    (tmp_path / "pypdf.py").write_text("raise SystemExit('PWNED_FROM_CWD')\n")
    monkeypatch.chdir(tmp_path)
    doc = isolated.parse_isolated("pdf_texto", b"%PDF-1.4", 20)
    assert "PWNED_FROM_CWD" not in " ".join(i.detail or "" for i in doc.issues)


@pytest.mark.skipif(os.name != "posix", reason="grupo de processos POSIX")
def test_descendente_com_pipes_nao_trava_o_pai(monkeypatch):
    # Filho que deixa um neto dormindo com os pipes herdados e sai: o pai não pode esperar o neto.
    codigo = "import subprocess,sys; subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); print('{}')"
    real_popen = subprocess.Popen

    def popen(args, **kw):
        return real_popen([sys.executable, "-c", codigo], **kw)
    monkeypatch.setattr(isolated.subprocess, "Popen", popen)
    import time
    t0 = time.monotonic()
    doc = isolated.parse_isolated("bcb_json", b"{}", 3)
    assert time.monotonic() - t0 < 20
    assert doc.parser_version == "0"
