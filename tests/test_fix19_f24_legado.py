"""FIX19 (auditoria final r15, F-24): captura legada sem Content-Type e compatibilidade dos derivados (decisão 0065).

A 1.2.0 gravou as capturas normativas com `headers_json={}`: a releitura decide a codificação só pelos bytes, pela
função única (BOM → prescan WHATWG → declaração XML → JSON/UTF-8 estrito), sem inventar Content-Type, e declara a
prova degradada (`legado_sem_cabecalho`). `derivados.compativel` só certifica derivados da versão atual com decisão
de interpretação registrada para toda captura com modelo.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from freoa_verifica import derivados
from freoa_verifica.parsers.bcb_json import parse_bcb_json
from freoa_verifica.parsers.planalto import parse_planalto
from freoa_verifica.service import Verifica
from freoa_verifica.texto_resposta import (CODIFICACAO_LEGADA_POR_FONTE, interpretar, interpretar_legado,
                                           interpretar_legado_padrao)
from freoa_verifica.transport import RespostaInvalida
from freoa_verifica.verify import WorkKey

FIX = Path(__file__).parent / "fixtures"
LEGADO = "legado_sem_cabecalho"
CONFERIDO = "legado_padrao_da_fonte_conferido"


def _lei(numero: int, corpo_meta: str = '<meta charset="iso-8859-1">') -> str:
    return (f"<html><head>{corpo_meta}</head><body><p>LEI Nº {numero}, DE 1 DE JANEIRO DE 2000</p>"
            "<p>Art. 1º Ação de teste.</p></body></html>")


# --- decisão só dos bytes ------------------------------------------------------------------------------------


@pytest.mark.parametrize("corpo,codec,texto", [
    (_lei(1).encode("latin-1"), "cp1252", "Ação"),  # HTML: <meta> Latin-1 pelo prescan WHATWG
    ('<?xml version="1.0" encoding="ISO-8859-1"?><a>Ação</a>'.encode("latin-1"), "cp1252", "Ação"),  # declaração XML
    ('{"t": "<meta charset=iso-8859-1> Ação"}'.encode("utf-8"), "utf-8", "Ação"),  # JSON: UTF-8, sem prescan
    ("﻿Ação".encode("utf-8"), "utf-8-sig", "Ação"),  # BOM decide
    (b"%PDF-1.4 \xe7\xe3", None, None),  # binário pela assinatura: sem codec
])
def test_interpretar_legado_decide_so_pelos_bytes(corpo, codec, texto):
    d = interpretar_legado(corpo)
    assert (d.codificacao, d.origem) == (codec, LEGADO)
    if texto:
        assert texto in d.texto and "Ã" not in d.texto


def test_interpretar_legado_bytes_invalidos_sao_recusados():
    with pytest.raises(RespostaInvalida):
        interpretar_legado(_lei(1, "").encode("latin-1"))  # sem <meta>: UTF-8 estrito, "ç" Latin-1 inválido


def test_json_sem_content_type_nao_segue_meta_no_conteudo():
    corpo = '{"t": "<meta charset=iso-8859-1> Ação"}'.encode("utf-8")
    assert interpretar(corpo, None).texto == corpo.decode("utf-8")


# --- banco sintético com capturas legadas --------------------------------------------------------------------


def _como_legado(svc, capture_id: str) -> None:
    """Recibo como a 1.2.0 o gravou: sem Content-Type, sem as colunas da 014, `headers_json={}`."""
    svc.conn.execute("DROP TRIGGER IF EXISTS capture_no_update")
    svc.conn.execute("UPDATE capture SET headers_json='{}', content_type=NULL, codificacao=NULL, "
                     "origem_da_codificacao=NULL WHERE id=?", (capture_id,))
    svc.conn.commit()


def _indexar_planalto(svc, numero: int, corpo: bytes, texto: str):
    """`texto` é o que a versão que capturou leu: dele vem o modelo persistido (o anterior, na conferência)."""
    url = f"https://www.planalto.gov.br/ccivil_03/leis/l{numero}.htm"
    rw = svc.indexar_obra(source_id="planalto", work_key=WorkKey("federal", "lei", str(numero), 2000),
                          document=parse_planalto(texto, base_url=url), body=corpo, url=url,
                          fetched_at="2026-10-21T00:00:00+00:00", label=f"Lei {numero}/2000")
    _como_legado(svc, rw.capture_id)
    return rw


def _indexar_bcb(svc):
    corpo = (FIX / "bcb_res_cmn_4966.json").read_bytes()
    rw = svc.indexar_obra(
        source_id="bcb", work_key=WorkKey("cmn", "resolucao", "4966", 2021), document=parse_bcb_json(corpo),
        body=corpo, url="https://www.bcb.gov.br/api/conteudo/app/normativos/exibenormativo?p1=x&p2=4966",
        fetched_at="2026-10-21T00:00:00+00:00", work_date="2021-11-25", label="Resolução CMN 4.966")
    _como_legado(svc, rw.capture_id)
    return rw


@pytest.fixture
def legado(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    with Verifica(tmp_path / "h") as svc:
        caps = {
            "html": _indexar_planalto(svc, 1, _lei(1).encode("latin-1"), _lei(1)).capture_id,
            # cp1252 sem <meta>, modelo anterior divergente do relido: a conferência recusa (0065, emenda).
            "invalido": _indexar_planalto(svc, 2, _lei(2, "").encode("latin-1"),
                                          _lei(2, "").replace("de teste", "de outro teste")).capture_id,
            # cp1252 sem <meta>, modelo anterior idêntico: padrão do Planalto conferido.
            "conferido": _indexar_planalto(svc, 3, _lei(3, "").encode("cp1252"), _lei(3, "")).capture_id,
            "json": _indexar_bcb(svc).capture_id,
        }
        yield svc, caps


def _modelo(svc, capture_id) -> str:
    return svc.conn.execute("SELECT model_json FROM parsed_document WHERE capture_id=?", (capture_id,)).fetchone()[0]


def test_reprocessamento_relata_por_fonte_e_registra_a_decisao(legado):
    svc, caps = legado
    assert not derivados.compativel(svc.conn)  # v5 com capturas sem decisão registrada
    out = svc.reprocessar_capturas()
    assert out["falhas"] == [{"capture_id": caps["invalido"], "motivo": "interpretacao_indisponivel"}], out
    assert out["por_fonte"] == {
        "planalto": {"reprocessadas_atuais": 0, "reprocessadas_legadas": 1, "reprocessadas_legadas_conferidas": 1,
                     "falhas": {"interpretacao_indisponivel": 1}},
        "bcb": {"reprocessadas_atuais": 0, "reprocessadas_legadas": 1, "reprocessadas_legadas_conferidas": 0,
                "falhas": {}},
    }
    assert "Ação" in _modelo(svc, caps["html"]) and "Ã" not in _modelo(svc, caps["html"])
    decisoes = {r[0]: tuple(r[1:]) for r in svc.conn.execute(
        "SELECT c.id, c.content_type, p.interpretacao_codificacao, p.interpretacao_origem "
        "FROM capture c JOIN parsed_document p ON p.capture_id=c.id")}
    assert decisoes == {caps["html"]: (None, "cp1252", LEGADO), caps["json"]: (None, "utf-8", LEGADO),
                        caps["conferido"]: (None, "cp1252", CONFERIDO), caps["invalido"]: (None, None, None)}
    # A captura inválida continua sem decisão: os derivados não são certificados.
    assert not derivados.compativel(svc.conn)
    # Repetir confere a decisão registrada e reproduz a mesma releitura.
    assert svc.reprocessar_capturas()["por_fonte"]["bcb"]["reprocessadas_legadas"] == 1


def test_decisao_legada_registrada_divergente_e_falha(legado):
    svc, caps = legado
    svc.reprocessar_capturas()
    svc.conn.execute("UPDATE parsed_document SET interpretacao_codificacao='utf-8' WHERE capture_id=?",
                     (caps["html"],))
    svc.conn.commit()
    falhas = svc.reprocessar_capturas()["falhas"]
    assert {"capture_id": caps["html"], "motivo": "interpretacao_divergente"} in falhas


def test_xml_legado_pela_declaracao(legado):
    svc, caps = legado
    corpo = '<?xml version="1.0" encoding="ISO-8859-1"?><a>Ação</a>'.encode("latin-1")
    from freoa_verifica.store import blobs
    sha = blobs.put_blob(corpo, home=svc.home)
    row = dict(svc.conn.execute("SELECT c.*, NULL AS interpretacao_codificacao, NULL AS interpretacao_origem "
                                "FROM capture c WHERE id=?", (caps["html"],)).fetchone())
    row["sha256"] = sha
    resp, decisao = svc._resposta_da_captura(row)
    assert decisao == (None, "cp1252", LEGADO) and resp.content_type == ""


def test_compativel_exige_versao_atual_e_decisao_registrada(legado):
    svc, caps = legado
    svc.conn.execute("DELETE FROM parsed_document WHERE capture_id=?", (caps["invalido"],))
    svc.conn.execute("UPDATE work SET authority='invalidated:federal' WHERE label='Lei 2/2000'")
    svc.conn.commit()
    assert derivados.versao(svc.conn) == derivados.DERIVED_VERSION == 5
    assert not derivados.compativel(svc.conn)  # v5 sem decisão registrada
    svc.reprocessar_capturas()
    assert derivados.compativel(svc.conn)
    with svc.conn:
        derivados.definir(svc.conn, 4)
    assert not derivados.compativel(svc.conn)  # v4: derivados de versão anterior


def test_reconstruir_relata_por_fonte_e_respostas_declaram_a_prova(legado):
    svc, caps = legado
    out = svc.reconstruir_acervo()
    assert out["status"] == "erro" and out["original_intacto"], out  # captura inválida: recusa, nunca silêncio
    assert out["por_fonte"]["planalto"]["falhas"] == {"interpretacao_indisponivel": 1}
    svc.conn.execute("UPDATE work SET authority='invalidated:federal' WHERE label='Lei 2/2000'")
    svc.conn.commit()
    out = svc.reconstruir_acervo()
    assert out["status"] == "ok", out
    assert out["por_fonte"]["planalto"]["reprocessadas_legadas"] == 1
    assert out["por_fonte"]["planalto"]["reprocessadas_legadas_conferidas"] == 1
    assert out["por_fonte"]["bcb"]["reprocessadas_legadas"] == 1
    assert derivados.compativel(svc.conn)
    prova = {"interpretacao": LEGADO}
    disp = svc.obter_dispositivo("art. 1º da Lei 1/2000")
    assert disp["status"] == "encontrada" and "Ação" in disp["texto"] and disp["proveniencia"] == prova, disp
    ver = svc.verificar_citacao("art. 1º da Lei 1/2000", trecho="Ação de teste")
    assert ver["text"]["status"] == "verified" and ver["text"]["evidence"][0]["proveniencia"] == prova, ver
    ev = svc.obter_evidencia(caps["html"])
    assert ev["proveniencia"] == prova and "Ação" in ev["texto"], ev


def test_captura_com_content_type_nao_declara_prova_degradada(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    with Verifica(tmp_path / "h") as svc:
        url = "https://www.planalto.gov.br/ccivil_03/leis/l1.htm"
        rw = svc.indexar_obra(source_id="planalto", work_key=WorkKey("federal", "lei", "1", 2000),
                              document=parse_planalto(_lei(1), base_url=url), body=_lei(1).encode("latin-1"),
                              url=url, fetched_at="2026-10-21T00:00:00+00:00", label="Lei 1/2000",
                              content_type="text/html; charset=iso-8859-1")
        assert derivados.compativel(svc.conn)
        assert "proveniencia" not in svc.obter_dispositivo("art. 1º da Lei 1/2000")
        assert "proveniencia" not in svc.obter_evidencia(rw.capture_id)
        ver = svc.verificar_citacao("art. 1º da Lei 1/2000", trecho="Ação de teste")
        assert "proveniencia" not in ver["text"]["evidence"][0]


# --- FIX19b: padrão da fonte sob conferência (0065, emenda) ---------------------------------------------------


def _conferencia(svc, capture_id):
    row = svc.conn.execute("SELECT interpretacao_origem, interpretacao_conferencia FROM parsed_document "
                           "WHERE capture_id=?", (capture_id,)).fetchone()
    return row[0], (json.loads(row[1]) if row[1] else None)


@pytest.mark.parametrize("corpo,fonte", [
    (_lei(1, "").encode("cp1252"), "cvm_normas"),  # fonte sem entrada na tabela
    (_lei(1, "").encode("cp1252"), None),
    (_lei(1).encode("latin-1"), "planalto"),  # <meta> declara: vale a declaração, nunca o padrão
    ('<?xml version="1.0" encoding="ISO-8859-1"?><a>Ação</a>'.encode("latin-1"), "planalto"),
    (_lei(1, "").encode("utf-8"), "planalto"),  # UTF-8 válido: regra 1
    ("﻿Ação".encode("utf-8"), "planalto"),  # BOM
    (b"%PDF-1.4 \xe7\xe3", "planalto"),
])
def test_padrao_da_fonte_so_sem_declaracao_e_utf8_invalido(corpo, fonte):
    assert interpretar_legado_padrao(corpo, fonte) is None


def test_padrao_da_fonte_planalto_cp1252():
    d = interpretar_legado_padrao(_lei(1, "").encode("cp1252"), "planalto")
    assert (d.codificacao, d.origem) == ("cp1252", CONFERIDO) and "Ação" in d.texto
    assert CODIFICACAO_LEGADA_POR_FONTE == {"planalto": "windows-1252"}


def test_planalto_legado_modelo_identico_e_aceito_e_conferido(legado):
    svc, caps = legado
    out = svc.reprocessar_capturas()
    assert not any(f["capture_id"] == caps["conferido"] for f in out["falhas"]), out
    origem, ev = _conferencia(svc, caps["conferido"])
    assert origem == CONFERIDO
    assert set(ev) == {"modelo_anterior_sha256", "modelo_novo_sha256"}
    assert ev["modelo_anterior_sha256"] == ev["modelo_novo_sha256"] and len(ev["modelo_novo_sha256"]) == 64
    assert "Ação" in _modelo(svc, caps["conferido"])
    # Releitura seguinte confere de novo, contra o modelo persistido e a decisão registrada.
    out = svc.reprocessar_capturas()
    assert out["por_fonte"]["planalto"]["reprocessadas_legadas_conferidas"] == 1
    assert _conferencia(svc, caps["conferido"]) == (origem, ev)


def test_planalto_legado_modelo_divergente_falha_sem_tocar_o_modelo(legado):
    svc, caps = legado
    antes = _modelo(svc, caps["invalido"])
    out = svc.reprocessar_capturas()
    assert {"capture_id": caps["invalido"], "motivo": "interpretacao_indisponivel"} in out["falhas"]
    assert _modelo(svc, caps["invalido"]) == antes
    assert _conferencia(svc, caps["invalido"]) == (None, None)
    autoridade = svc.conn.execute("SELECT authority FROM work WHERE label='Lei 2/2000'").fetchone()[0]
    assert autoridade == "federal"  # divergência de interpretação não invalida a obra


def test_planalto_legado_sem_modelo_anterior_falha(legado):
    svc, caps = legado
    svc.conn.execute("UPDATE parsed_document SET model_json='null' WHERE capture_id=?", (caps["conferido"],))
    svc.conn.commit()
    out = svc.reprocessar_capturas()
    assert {"capture_id": caps["conferido"], "motivo": "interpretacao_indisponivel"} in out["falhas"]
    assert _conferencia(svc, caps["conferido"]) == (None, None)


def test_outra_fonte_sem_tabela_falha(legado):
    svc, caps = legado
    svc.conn.execute("INSERT OR IGNORE INTO source(id, authority, profile, hosts_json) "
                     "VALUES ('cvm_normas', 'cvm', 'cvm', '[]')")
    svc.conn.execute("UPDATE capture SET source_id='cvm_normas' WHERE id=?", (caps["conferido"],))
    svc.conn.commit()
    out = svc.reprocessar_capturas()
    assert {"capture_id": caps["conferido"], "motivo": "interpretacao_indisponivel"} in out["falhas"]
    assert out["por_fonte"]["cvm_normas"]["reprocessadas_legadas_conferidas"] == 0


def test_captura_nova_sem_content_type_nao_usa_o_padrao_da_fonte():
    from freoa_verifica.store import repo
    from freoa_verifica.transport import Response

    corpo = _lei(1, "").encode("cp1252")
    resp = Response("https://www.planalto.gov.br/x.htm", "https://www.planalto.gov.br/x.htm", 200, {}, corpo,
                    hashlib.sha256(corpo).hexdigest(), "2026-10-21T00:00:00+00:00", [], "text/html")
    assert repo.interpretacao_do_recibo(resp) == (None, None, None)


def test_respostas_declaram_a_conferencia(legado):
    svc, caps = legado
    svc.conn.execute("UPDATE work SET authority='invalidated:federal' WHERE label='Lei 2/2000'")
    svc.conn.commit()
    assert svc.reconstruir_acervo()["status"] == "ok"
    assert derivados.compativel(svc.conn)
    prova = {"interpretacao": CONFERIDO}
    disp = svc.obter_dispositivo("art. 1º da Lei 3/2000")
    assert disp["status"] == "encontrada" and "Ação" in disp["texto"] and disp["proveniencia"] == prova, disp
    ver = svc.verificar_citacao("art. 1º da Lei 3/2000", trecho="Ação de teste")
    assert ver["text"]["status"] == "verified" and ver["text"]["evidence"][0]["proveniencia"] == prova, ver
    ev = svc.obter_evidencia(caps["conferido"])
    assert ev["proveniencia"] == prova and "Ação" in ev["texto"], ev
