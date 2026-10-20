from __future__ import annotations

import hashlib

import pytest

from freoa_verifica.connectors.tjdft import TjdftConnector
from freoa_verifica.service import Verifica

pytestmark = pytest.mark.live

CONSULTA = "sociedade anônima dissolução parcial"


# `Unavailable` tipada levantada pelo conector vira xfail ambiental pelo hook de conftest (decisão 0045).
def test_live_tjdft_positivo():
    found = TjdftConnector().search(CONSULTA, limite=5)
    assert len(found) >= 1
    for cand in found:
        assert cand.metadata["uuid"] and cand.metadata["processo"] and cand.key


def test_live_tjdft_negativo_estrutural():
    # Lista vazia só vale com a estrutura da fonte (`hits.value == 0`): sem ela `search` levanta Unavailable.
    found = TjdftConnector().search("FVXYZTERMOSINTETICO99991QWERTY", limite=5)
    assert list(found) == []
    assert found.total == 0


def test_live_tjdft_documento_captura_e_parse():
    c = TjdftConnector()
    found = c.search(CONSULTA, limite=5)
    assert found
    resp = c.fetch(found[0])
    assert resp.sha256 == hashlib.sha256(resp.body).hexdigest()
    parsed = c.parse_candidate(resp, found[0])
    assert parsed.official_id == found[0].key
    assert parsed.metadata["uuid"] == found[0].metadata["uuid"]


def test_live_tjdft_acordao_sem_integra_fica_so_com_ementa(tmp_path):
    c = TjdftConnector()
    found = c.search(CONSULTA, limite=20, base="acordaos")
    acordaos = [x for x in found if x.metadata["base"] == "acordaos"]
    assert acordaos
    resp = c.fetch(acordaos[0])
    parsed = c.parse_candidate(resp, acordaos[0])
    # Confronto da resposta pública (B2-09): indexa a captura obtida e pede o inteiro teor ao serviço.
    with Verifica(tmp_path / "home") as svc:
        assert svc._index_candidate_juris(c, acordaos[0], captured_response=resp)
        r = svc.obter_decisao(acordaos[0].key, tribunal="tjdft", parte="inteiro_teor")
    if parsed.text:  # perfil com íntegra validada (F1): a parte tem de ser entregue
        assert parsed.profile == "tjdft_inteiro_teor"
        assert r["status"] == "encontrada" and r["parte_entregue"] == "inteiro_teor" and r["texto"]
    else:  # a API não entrega íntegra de acórdão: o serviço responde `parte_indisponivel`
        assert parsed.profile == "tjdft_ementa"
        assert parsed.metadata.get("documento") is None
        assert r["status"] == "parte_indisponivel" and r["texto"] is None and r["parte_entregue"] is None
