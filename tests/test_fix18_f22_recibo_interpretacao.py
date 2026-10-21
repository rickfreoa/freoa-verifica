"""FIX18 (auditoria r14, F-22): o recibo persiste o Content-Type cru e a decisão de interpretação; a releitura usa-os.

Ponta a ponta, com transporte TCP real, persistência (SQLite e blobs) e subprocesso de parse reais: `charset="utf-8"`
entre aspas e `<meta>` Latin-1 divergente → "Ação" na captura e depois de `reprocessar_capturas`. Captura sem esse
metadado → falha declarada `interpretacao_indisponivel`, sem tocar no modelo (decisão 0064).
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from freoa_verifica.parsers.planalto import parse_planalto
from freoa_verifica.service import Verifica
from freoa_verifica.store import repo
from freoa_verifica.transport import Response
from freoa_verifica.verify import WorkKey
from tests.test_fix17_controladores import servidor_que_le_o_corpo
from tests.test_transport import _fast_guards, _wire_local

LEI = ('<html><head><meta charset="iso-8859-1"></head><body>'
       "<p>LEI Nº 1, DE 1 DE JANEIRO DE 2000</p><p>Art. 1º Ação de teste.</p></body></html>").encode("utf-8")
CTYPE = 'text/html; charset="utf-8"'


def _modelo(svc) -> str:
    return " ".join(r[0] for r in svc.conn.execute("SELECT model_json FROM parsed_document"))


@pytest.fixture
def planalto_local(monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    bruto = (b"HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Type: " + CTYPE.encode()
             + b"\r\nContent-Length: %d\r\n\r\n" % len(LEI) + LEI)
    server, pedidos = servidor_que_le_o_corpo(bruto)
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    yield pedidos
    server.shutdown()


def test_captura_persistencia_reprocessamento_preserva_a_interpretacao(planalto_local, tmp_path):
    with Verifica(tmp_path / "h") as svc:
        svc.verificar_citacao("art. 1º da Lei 1/2000", trecho="Ação de teste")
        assert planalto_local, "a captura não passou pelo transporte"
        cap = svc.conn.execute("SELECT * FROM capture WHERE source_id='planalto'").fetchone()
        assert (cap["content_type"], cap["codificacao"], cap["origem_da_codificacao"]) == (CTYPE, "utf-8", "header")
        assert "Ação" in _modelo(svc) and "AÃ" not in _modelo(svc)
        out = svc.reprocessar_capturas()
        assert out["falhas"] == [] and out["reprocessados"] == 1, out
        assert "Ação" in _modelo(svc) and "AÃ" not in _modelo(svc)


def _indexar_sem_metadado(svc, *, headers_json_ctype: str | None = None):
    url = "https://www.planalto.gov.br/ccivil_03/leis/l1.htm"
    doc = parse_planalto(LEI.decode("utf-8"), base_url=url)
    rw = svc.indexar_obra(source_id="planalto", work_key=WorkKey("federal", "lei", "1", 2000), document=doc,
                          body=LEI, url=url, fetched_at="2026-10-21T00:00:00+00:00", label="Lei 1/2000")
    if headers_json_ctype is not None:  # recibo legado (anterior à 014) que guardou o content-type em headers_json
        svc.conn.execute("DROP TRIGGER capture_no_update")
        svc.conn.execute("UPDATE capture SET headers_json=? WHERE id=?",
                         (json.dumps({"content-type": headers_json_ctype}), rw.capture_id))
        svc.conn.commit()
    return rw


def test_captura_sem_metadado_falha_declarada_sem_reinterpretar(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    with Verifica(tmp_path / "h") as svc:
        rw = _indexar_sem_metadado(svc)
        cap = svc.conn.execute("SELECT * FROM capture WHERE id=?", (rw.capture_id,)).fetchone()
        assert cap["content_type"] is None and cap["origem_da_codificacao"] is None
        antes = _modelo(svc)
        out = svc.reprocessar_capturas()
        assert out["reprocessados"] == 0
        assert out["falhas"] == [{"capture_id": rw.capture_id, "motivo": "interpretacao_indisponivel"}]
        assert _modelo(svc) == antes and "AÃ" not in antes


def test_captura_legada_usa_content_type_de_headers_json(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    with Verifica(tmp_path / "h") as svc:
        _indexar_sem_metadado(svc, headers_json_ctype="text/html; charset=utf-8")
        out = svc.reprocessar_capturas()
        assert out["falhas"] == [] and out["reprocessados"] == 1, out
        assert "Ação" in _modelo(svc) and "AÃ" not in _modelo(svc)


def test_decisao_persistida_divergente_e_falha(tmp_path, monkeypatch):
    """A releitura confere a decisão do recibo: se a função atual não a reproduz, falha declarada."""
    monkeypatch.setenv("FV_OFFLINE", "1")
    with Verifica(tmp_path / "h") as svc:
        url = "https://www.planalto.gov.br/ccivil_03/leis/l1.htm"
        doc = parse_planalto(LEI.decode("utf-8"), base_url=url)
        rw = svc.indexar_obra(source_id="planalto", work_key=WorkKey("federal", "lei", "1", 2000), document=doc,
                              body=LEI, url=url, fetched_at="2026-10-21T00:00:00+00:00", label="Lei 1/2000",
                              content_type=CTYPE)
        svc.conn.execute("DROP TRIGGER capture_no_update")
        svc.conn.execute("UPDATE capture SET codificacao='iso8859-1', origem_da_codificacao='meta' WHERE id=?",
                         (rw.capture_id,))
        svc.conn.commit()
        out = svc.reprocessar_capturas()
        assert out["falhas"] == [{"capture_id": rw.capture_id, "motivo": "interpretacao_divergente"}], out


def test_recibo_de_resposta_sintetica_sem_content_type_nao_inventa():
    corpo = b"<p>x</p>"
    resp = Response("u", "u", 200, {}, corpo, "0" * 64, "t", [], "text/html")
    assert repo.interpretacao_do_recibo(resp) == (None, None, None)
    pdf = dataclasses.replace(resp, content_type="application/pdf")
    assert repo.interpretacao_do_recibo(pdf) == ("application/pdf", None, "binario")
