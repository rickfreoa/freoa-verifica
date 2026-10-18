"""Busca: candidatos sem captura são metadados (nao_indexado), nunca derrubam a resposta inteira."""
from types import SimpleNamespace

import pytest

from freoa_verifica.connectors.base import Candidate, CandidateList

_PROIBIDOS = ("vigencia", "identity", "text", "temporal", "work_id")


def _afirma(item):
    return any(item.get(k) for k in _PROIBIDOS)


@pytest.mark.parametrize("method", ["buscar_normas_cvm", "buscar_normas_bcb"])
def test_busca_normas_nao_indexados_parcial(verifica_populada, monkeypatch, method):
    svc, rw, _ = verifica_populada
    monkeypatch.setenv("FV_OFFLINE", "0")
    cands = CandidateList([Candidate("test", str(i), f"Ato {i}", snippet="s") for i in range(12)], total=30)
    monkeypatch.setattr(svc, "_get", lambda cid: SimpleNamespace(search=lambda *a, **kw: cands))
    monkeypatch.setattr(svc, "_index_candidate_legis",
                        lambda conn, cand: {"capture_id": rw.capture_id, "trecho": "Regra"})
    r = getattr(svc, method)("fato relevante")
    assert r["status"] == "parcial" and len(r["itens"]) == 12
    ni = [i for i in r["itens"] if i.get("nao_indexado")]
    assert len(ni) == 7 and r["nao_indexados"] == 7
    assert all(i["capture_id"] is None and not _afirma(i) for i in ni)


def test_evidencia_de_item_indexado_rebaixa_so_o_item(verifica_populada, monkeypatch):
    svc, rw, _ = verifica_populada
    monkeypatch.setenv("FV_OFFLINE", "0")
    cands = CandidateList([Candidate("test", str(i), f"Ato {i}") for i in range(2)])
    monkeypatch.setattr(svc, "_get", lambda cid: SimpleNamespace(search=lambda *a, **kw: cands))
    monkeypatch.setattr(svc, "_index_candidate_legis", lambda conn, cand: {
        "capture_id": rw.capture_id if cand.key == "0" else "CAPTURA_INEXISTENTE", "trecho": "Regra"})
    r = svc.buscar_normas_cvm("regra")
    assert r["status"] == "parcial" and [bool(i.get("nao_indexado")) for i in r["itens"]] == [False, True]
    assert r["itens"][1]["motivo"] == "EVIDENCIA_AUSENTE"


def test_buscar_legislacao_candidato_sem_captura(verifica_populada, monkeypatch):
    svc, rw, _ = verifica_populada
    monkeypatch.setenv("FV_OFFLINE", "0")
    cands = CandidateList([Candidate("test", str(i), f"Ato {i}") for i in range(3)], total=3)
    monkeypatch.setattr("freoa_verifica.service.registry", lambda: {"planalto": object()})
    monkeypatch.setattr(svc, "_get", lambda cid: SimpleNamespace(search=lambda *a, **kw: cands))
    monkeypatch.setattr(svc, "_index_candidate_legis", lambda conn, cand: {
        "obra": cand.title, "trecho": "x", "capture_id": None, "motivo": "falha", "vigencia": None})
    r = svc.buscar_legislacao("assunto inexistente no acervo local zzqq", fonte="planalto")
    assert r["status"] == "parcial" and r["itens"]
    assert all(i["nao_indexado"] and not _afirma(i) for i in r["itens"])
