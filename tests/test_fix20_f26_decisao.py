"""FIX20 (auditoria final r16, F-26): Content-Type presente não dispensa a decisão de interpretação (decisão 0066).

Os dois negativos do auditor pela API pública `indexar_obra`: corpo cp1252 declarado UTF-8 e charset estendido
(`charset*=x`). A indexação recusa antes de gravar (nem recibo, nem modelo); um home que já tenha esse estado
(produzido pela candidata anterior) é incompatível, não entrega o texto como atual e nunca verifica.
"""

from __future__ import annotations

import pytest

from freoa_verifica import derivados
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.parsers.planalto import parse_planalto
from freoa_verifica.service import Verifica
from freoa_verifica.store import repo
from freoa_verifica.verify import WorkKey

NEGATIVOS = {
    "cp1252_declarado_utf8": (lambda t: t.encode("cp1252"), "text/html; charset=utf-8"),
    "charset_estendido": (lambda t: t.encode("utf-8"), "text/html; charset*=x"),
}


def _lei(numero: int) -> str:
    return (f"<html><head></head><body><p>LEI Nº {numero}, DE 1 DE JANEIRO DE 2000</p>"
            "<p>Art. 1º Ação de teste.</p></body></html>")


def _indexar(svc, numero: int, corpo: bytes, content_type: str | None):
    url = f"https://www.planalto.gov.br/ccivil_03/leis/l{numero}.htm"
    return svc.indexar_obra(source_id="planalto", work_key=WorkKey("federal", "lei", str(numero), 2000),
                            document=parse_planalto(_lei(numero), base_url=url), body=corpo, url=url,
                            fetched_at="2026-10-21T00:00:00+00:00", label=f"Lei {numero}/2000",
                            content_type=content_type)


def _contagens(svc) -> dict:
    return {t: svc.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("capture", "parsed_document", "extract", "work", "provision")}


def _sem_decisao(svc) -> int:
    """Invariante (0066): capturas reprocessáveis com modelo e sem decisão de interpretação registrada."""
    return len(svc.conn.execute(derivados._SEM_DECISAO.replace(" LIMIT 1", "")).fetchall())


def _nao_verifica(svc, numero: int) -> None:
    disp = svc.obter_dispositivo(f"art. 1º da Lei {numero}/2000")
    assert disp.get("status") != "encontrada" and "Ação de teste" not in str(disp.get("texto") or ""), disp
    ver = svc.verificar_citacao(f"art. 1º da Lei {numero}/2000", trecho="Ação de teste")
    assert "verified" not in {(ver.get("identity") or {}).get("status"), (ver.get("text") or {}).get("status")}, ver


@pytest.fixture
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    with Verifica(tmp_path / "h") as s:
        _indexar(s, 9, _lei(9).encode("utf-8"), "text/html; charset=utf-8")  # caminho feliz, no mesmo home
        yield s


def test_caminho_feliz_inalterado(svc):
    assert derivados.compativel(svc.conn) and _sem_decisao(svc) == 0
    cap = svc.conn.execute("SELECT codificacao, origem_da_codificacao FROM capture").fetchone()
    assert tuple(cap) == ("utf-8", "header")
    assert svc.obter_dispositivo("art. 1º da Lei 9/2000")["status"] == "encontrada"
    ver = svc.verificar_citacao("art. 1º da Lei 9/2000", trecho="Ação de teste")
    assert ver["identity"]["status"] == "verified" and ver["text"]["status"] == "verified", ver


@pytest.mark.parametrize("caso", sorted(NEGATIVOS))
def test_negativo_do_auditor_recusado_sem_gravar(svc, caso):
    codificar, ctype = NEGATIVOS[caso]
    antes = _contagens(svc)
    with pytest.raises(Unavailable) as exc:
        _indexar(svc, 1, codificar(_lei(1)), ctype)
    assert exc.value.reason == "interpretacao_indisponivel" and exc.value.categoria == "resposta_inesperada"
    assert exc.value.evidencia["url"].endswith("l1.htm")
    assert _contagens(svc) == antes  # nem recibo, nem obra, nem modelo
    assert derivados.compativel(svc.conn) and _sem_decisao(svc) == 0
    _nao_verifica(svc, 1)


def _estado_da_candidata(svc, numero: int, caso: str) -> str:
    """Home gravado pela candidata anterior: os bytes e o Content-Type do negativo, decisão nula, modelo persistido."""
    codificar, ctype = NEGATIVOS[caso]
    rw = _indexar(svc, numero, codificar(_lei(numero)), "text/html; charset=windows-1252")
    svc.conn.execute("DROP TRIGGER IF EXISTS capture_no_update")
    svc.conn.execute("UPDATE capture SET content_type=?, codificacao=NULL, origem_da_codificacao=NULL WHERE id=?",
                     (ctype, rw.capture_id))
    svc.conn.commit()
    svc._resolver = type(svc._resolver)()
    return rw.capture_id


@pytest.mark.parametrize("caso", sorted(NEGATIVOS))
def test_home_com_recibo_sem_decisao_e_incompativel(svc, caso):
    cid = _estado_da_candidata(svc, 1, caso)
    assert _sem_decisao(svc) == 1
    assert not derivados.compativel(svc.conn)
    assert svc.obter_dispositivo("art. 1º da Lei 9/2000")["motivo"] == derivados.REASON  # nem a obra boa é atual
    _nao_verifica(svc, 1)
    modelo = svc.conn.execute("SELECT model_json FROM parsed_document WHERE capture_id=?", (cid,)).fetchone()[0]
    out = svc.reprocessar_capturas()
    assert {"capture_id": cid, "motivo": "interpretacao_indisponivel"} in out["falhas"], out
    assert svc.conn.execute("SELECT model_json, interpretacao_origem FROM parsed_document WHERE capture_id=?",
                            (cid,)).fetchone()[:] == (modelo, None)
    assert not derivados.compativel(svc.conn)


def test_persistir_modelo_sem_decisao_e_recusado(svc):
    cid = _estado_da_candidata(svc, 1, "cp1252_declarado_utf8")
    svc.conn.execute("UPDATE parsed_document SET model_json=NULL WHERE capture_id=?", (cid,))
    svc.conn.commit()
    antes = _contagens(svc)
    rw = svc._rebuild_from_db(WorkKey("federal", "lei", "9", 2000))
    with pytest.raises(Unavailable, match="interpretacao_indisponivel"):
        repo.persist_parsed_document(svc.conn, capture_id=cid, document=rw.document, work_id=rw.work_id)
    with pytest.raises(Unavailable, match="interpretacao_indisponivel"):  # decisão explícita também exige origem
        repo.persist_parsed_document(svc.conn, capture_id=cid, document=rw.document, work_id=rw.work_id,
                                     interpretacao=("utf-8", None, None))
    assert _contagens(svc) == antes
    assert svc.conn.execute("SELECT model_json FROM parsed_document WHERE capture_id=?", (cid,)).fetchone()[0] is None


def test_binario_tem_decisao_sem_codec():
    assert repo.decisao_registrada(None, "binario") and repo.decisao_registrada(None, "legado_sem_cabecalho")
    assert not repo.decisao_registrada(None, "header") and not repo.decisao_registrada("utf-8", None)


def test_invariante_apos_operacoes_publicas(svc):
    """Após indexar (feliz e negativos), reprocessar e reconstruir: zero capturas com modelo e sem decisão."""
    _indexar(svc, 2, _lei(2).encode("cp1252"), "text/html; charset=windows-1252")
    _indexar(svc, 3, _lei(3).encode("utf-8"), None)  # sem Content-Type: decisão só dos bytes (0065)
    for codificar, ctype in NEGATIVOS.values():
        with pytest.raises(Unavailable):
            _indexar(svc, 4, codificar(_lei(4)), ctype)
    assert _sem_decisao(svc) == 0
    assert not svc.reprocessar_capturas()["falhas"] and _sem_decisao(svc) == 0
    assert derivados.reconstruir(svc)["status"] == "ok"
    assert _sem_decisao(svc) == 0 and derivados.compativel(svc.conn)
