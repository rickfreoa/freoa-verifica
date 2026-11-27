"""0094, achado 5 do colega: a pendência de renovação só sai com captura nova de verdade."""
from __future__ import annotations

from dataclasses import replace

import pytest

from freoa_verifica import revalidacao as rev
from freoa_verifica.service import Verifica
from freoa_verifica.verify import ResolvedWork
from tests.test_0091a_revalidacao import T0, _obra


def _resolvido(svc, work_id, fetched_at, capture_id="cap-x"):
    from freoa_verifica.parsers.planalto import parse_planalto

    doc = parse_planalto(b"<html><body><p>Art. 1 Teste.</p></body></html>")
    rw = ResolvedWork(work_id=work_id, work_key=None, document=doc, work_date=None, capture_id=capture_id,
                      sha256="0" * 64, url="https://example.invalid", fetched_at=fetched_at, quarantined=False)
    return replace(rw, source_id="planalto") if hasattr(rw, "source_id") else rw


def _pendencia(svc, work_id, em):
    rev._gravar_sync(svc.conn, rev.FONTE_PENDENTE, work_id, "pendente", motivo="metadados_alterados",
                     payload={"sinal_anterior": "a", "sinal_novo": "b", "em": em})


def _renovar(svc, monkeypatch, fetched_at):
    monkeypatch.setattr(svc, "_capture_work", lambda work: _resolvido(svc, "w", fetched_at))
    return svc.renovar_acervo(dias=1)


@pytest.mark.parametrize("fetched_at,motivo", [
    (T0, "captura_canonica_nao_renovada"),                          # mesmos bytes, data original
    ("2025-12-01T00:00:00+00:00", "captura_canonica_nao_renovada"),  # monotonia devolveu captura mais antiga
    ("sem-data", "captura_canonica_nao_renovada"),                  # não é data: nunca posterior
    ("2026-02-01T00:00:00", "captura_canonica_nao_renovada"),       # sem fuso: não se presume
    ("2026-02-01T00:00:00+00:00", "captura_anterior_ao_sinal_da_pendencia"),  # intermediária, antes do sinal
])
def test_pendencia_fica_sem_captura_posterior(tmp_path, monkeypatch, fetched_at, motivo):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        work_id = _obra(svc)
        _pendencia(svc, work_id, "2026-03-01T00:00:00+00:00")
        r = _renovar(svc, monkeypatch, fetched_at)
        assert r["renovadas"] == [] and r["falhas"] == [] and r["status"] == "parcial"
        assert r["sem_renovacao"][0]["motivo"] == motivo
        assert work_id in rev.obras_pendentes(svc.conn)


def test_captura_posterior_ao_sinal_renova_e_limpa(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        work_id = _obra(svc)
        _pendencia(svc, work_id, "2026-03-01T00:00:00+00:00")
        r = _renovar(svc, monkeypatch, "2026-03-02T00:00:00+00:00")
        assert len(r["renovadas"]) == 1 and r["status"] == "ok" and work_id not in rev.obras_pendentes(svc.conn)


def test_obra_envelhecida_sem_pendencia_renova_com_captura_posterior(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        _obra(svc)
        assert _renovar(svc, monkeypatch, "2026-01-02T00:00:00+00:00")["status"] == "ok"


def test_pendencia_antiga_sem_data_usa_a_do_registro(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        work_id = _obra(svc)
        rev._gravar_sync(svc.conn, rev.FONTE_PENDENTE, work_id, "pendente", motivo="metadados_alterados")
        assert rev.data_do_sinal_da_pendencia(svc.conn, work_id) is not None  # updated_at do registro (agora)
        r = _renovar(svc, monkeypatch, "2026-01-02T00:00:00+00:00")  # posterior à captura, anterior ao registro
        assert r["sem_renovacao"][0]["motivo"] == "captura_anterior_ao_sinal_da_pendencia"


def test_sem_renovacao_conta_como_progresso_sem_falha_real(tmp_path, monkeypatch):
    monkeypatch.setattr(Verifica, "revalidar_acervo", lambda self, **k: {"status": "ok", "contagens": {}, "obras": 0})
    monkeypatch.setattr(Verifica, "renovar_acervo", lambda self, **k: {
        "status": "parcial", "renovadas": [], "falhas": [], "adiadas": [], "sem_renovacao": [{}], "candidatas": 1})
    with Verifica(tmp_path) as svc:
        r = svc.manter_acervo()
        assert r["status"] == "parcial" and r["manutencao"]["falhas"] is False
        assert r["manutencao"]["renovacao"]["sem_renovacao"] == 1


@pytest.mark.parametrize("valor,esperado", [
    ("2026-01-01T00:00:00+00:00", True), ("2026-01-01T00:00:00Z", True), ("2026-01-01T00:00:00", False),
    ("sem-data", False), ("", False), (None, False), (20260101, False),
])
def test_instante(valor, esperado):
    assert (rev.instante(valor) is not None) is esperado


def test_r1_sinal_novo_gravado_durante_a_captura_sobrevive(tmp_path, monkeypatch):
    """Codex 0094 r1, achado 5: captura de 02/03 não pode apagar o sinal de 03/03 gravado durante ela."""
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        work_id = _obra(svc)
        _pendencia(svc, work_id, "2026-03-01T00:00:00+00:00")

        def captura(work):
            _pendencia(svc, work_id, "2026-03-03T00:00:00+00:00")
            return _resolvido(svc, work_id, "2026-03-02T00:00:00+00:00")

        monkeypatch.setattr(svc, "_capture_work", captura)
        r = svc.renovar_acervo(dias=1)
        assert r["renovadas"] == [] and r["sem_renovacao"][0]["motivo"] == "captura_anterior_ao_sinal_da_pendencia"
        assert work_id in rev.obras_pendentes(svc.conn)


def test_r1_pendencia_criada_durante_a_captura_de_obra_envelhecida_sobrevive(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        work_id = _obra(svc)

        def captura(work):
            _pendencia(svc, work_id, "2026-03-03T00:00:00+00:00")
            return _resolvido(svc, work_id, "2026-03-02T00:00:00+00:00")

        monkeypatch.setattr(svc, "_capture_work", captura)
        r = svc.renovar_acervo(dias=1)
        assert r["renovadas"] == [] and work_id in rev.obras_pendentes(svc.conn)


def test_r1_pendencia_sem_instante_legivel_nao_sai(tmp_path, monkeypatch):
    """Codex 0094 r1, achado 6: sem `em` e com `updated_at` sem fuso, a pendência não é tratada como livre."""
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        work_id = _obra(svc)
        rev._gravar_sync(svc.conn, rev.FONTE_PENDENTE, work_id, "pendente", motivo="metadados_alterados")
        svc.conn.execute("UPDATE sync_state SET updated_at='2026-03-03 00:00:00' WHERE fonte=? AND chave=?",
                         (rev.FONTE_PENDENTE, work_id))
        r = _renovar(svc, monkeypatch, "2026-03-02T00:00:00+00:00")
        assert r["sem_renovacao"][0]["motivo"] == "sinal_da_pendencia_sem_data"
        assert work_id in rev.obras_pendentes(svc.conn)
