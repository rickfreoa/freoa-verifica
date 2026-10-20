"""P1 (decisão 0055): bloco `cobertura` em pesquisar_jurisprudencia e `CandidateList.total` honesto.

Offline. Expectativas escritas à mão a partir da captura real tests/fixtures/tjdft/acordo_acionistas.json:
`hits.value` = 3025 (sem `relation`) e 3 registros lidos, julgados em 2026-09-16 e 2026-10-08.
"""
import hashlib
import json

import pytest

from freoa_verifica.connectors import datajud, stj, tjdft
from freoa_verifica.connectors.base import CandidateList, Unavailable
from freoa_verifica.service import Verifica
from freoa_verifica.transport import Response
from tests.contrato.harness import semear
from tests.fixture_util import load_fixture

URL = "https://jurisdf.tjdft.jus.br/api/v1/pesquisa"
CAMPOS = {"tribunal", "capacidade", "consulta", "motivo_nao_consulta", "recorte_acervo", "capturado_em",
          "total_remoto", "total_exato", "lidos", "indexados", "truncado_remoto", "truncado_local", "indisponivel"}


@pytest.fixture
def svc(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path / "h") as s:
        yield s


@pytest.fixture
def tjdft_conn(monkeypatch, svc):
    body = load_fixture("tjdft_acordo_acionistas")
    resp = Response(URL, URL, 200, {}, body, hashlib.sha256(body).hexdigest(), "2026-10-18T00:00:00Z", [], "application/json")
    monkeypatch.setattr(tjdft, "connector_fetch", lambda url, **kw: resp)
    c = tjdft.TjdftConnector()
    svc._connectors["tjdft"] = c
    return c


def _cob(r, tribunal):
    achados = [c for c in r["cobertura"] if c["tribunal"] == tribunal]
    assert len(achados) == 1, r["cobertura"]
    assert set(achados[0]) == CAMPOS
    return achados[0]


def _cands_de(conn, monkeypatch, fabrica):
    """Mantém a leitura real (indexação) e troca só o que a lista informa de `total`."""
    original = conn.search

    def search(q, **kw):
        return fabrica(list(original(q, **kw)))

    monkeypatch.setattr(conn, "search", search)


# --- CandidateList ---------------------------------------------------------------------------

def test_candidatelist_total_desconhecido_nao_e_o_lido():
    lista = CandidateList([1, 2, 3])
    assert lista.total is None and lista.total_exato is None and lista.truncado is False


def test_candidatelist_total_informado():
    lista = CandidateList([1, 2], total=10, total_exato=False)
    assert (lista.total, lista.total_exato, lista.truncado) == (10, False, True)
    assert CandidateList([], total=0, total_exato=True).total == 0


def test_candidatelist_total_nao_fica_abaixo_do_lido():
    assert CandidateList([1, 2, 3], total=1).total == 3


def test_tjdft_total_da_fonte_sem_relation_nao_afirma_exatidao(tjdft_conn):
    lista = tjdft_conn.search("sociedade")
    assert (len(lista), lista.total, lista.total_exato, lista.truncado) == (3, 3025, None, True)


# --- busca textual ---------------------------------------------------------------------------

def test_textual_ao_vivo_total_da_fonte_e_truncamento_remoto(svc, tjdft_conn):
    r = svc.pesquisar_jurisprudencia("sociedade", tribunais=["tjdft"])
    c = _cob(r, "TJDFT")
    assert c["capacidade"] == "ambos" and c["consulta"] == "ambos" and c["motivo_nao_consulta"] is None
    assert (c["total_remoto"], c["total_exato"], c["lidos"], c["indexados"]) == (3025, None, 3, 3)
    assert c["truncado_remoto"] is True and c["truncado_local"] is False and c["indisponivel"] is None
    assert c["recorte_acervo"] == {"desde": "2026-09-16", "ate": "2026-10-08"}
    assert c["capturado_em"]
    # truncamento remoto não é ok silencioso, mas não há cursor: ele só pagina o acervo local.
    assert r["truncado"] is True and r["status"] == "parcial" and r["cursor"] is None


def test_textual_total_exato_conforme_a_fonte(svc, tjdft_conn, monkeypatch):
    _cands_de(tjdft_conn, monkeypatch, lambda xs: CandidateList(xs, total=3, total_exato=True))
    r = svc.pesquisar_jurisprudencia("sociedade", tribunais=["tjdft"])
    c = _cob(r, "TJDFT")
    assert (c["total_remoto"], c["total_exato"], c["truncado_remoto"]) == (3, True, False)
    assert r["truncado"] is False and r["status"] == "ok"


def test_textual_total_cota_inferior(svc, tjdft_conn, monkeypatch):
    _cands_de(tjdft_conn, monkeypatch, lambda xs: CandidateList(xs, total=10000, total_exato=False))
    c = _cob(svc.pesquisar_jurisprudencia("sociedade", tribunais=["tjdft"]), "TJDFT")
    assert (c["total_remoto"], c["total_exato"], c["truncado_remoto"]) == (10000, False, True)


def test_textual_total_desconhecido_nunca_vira_zero(svc, tjdft_conn, monkeypatch):
    _cands_de(tjdft_conn, monkeypatch, list)  # lista simples: a fonte não informa total
    c = _cob(svc.pesquisar_jurisprudencia("sociedade", tribunais=["tjdft"]), "TJDFT")
    assert c["total_remoto"] is None and c["total_exato"] is None
    assert c["lidos"] == 3 and c["truncado_remoto"] is False


def test_textual_zero_so_quando_a_fonte_informa(svc, tjdft_conn, monkeypatch):
    monkeypatch.setattr(tjdft_conn, "search", lambda q, **kw: CandidateList([], total=0, total_exato=True))
    c = _cob(svc.pesquisar_jurisprudencia("sociedade", tribunais=["tjdft"]), "TJDFT")
    assert (c["total_remoto"], c["total_exato"], c["lidos"]) == (0, True, 0)


def test_textual_lista_vazia_sem_total_nao_informa_zero(svc, tjdft_conn, monkeypatch):
    monkeypatch.setattr(tjdft_conn, "search", lambda q, **kw: [])
    c = _cob(svc.pesquisar_jurisprudencia("sociedade", tribunais=["tjdft"]), "TJDFT")
    assert c["total_remoto"] is None and c["total_exato"] is None


def test_textual_limite_local_atingido(svc, tjdft_conn):
    r = svc.pesquisar_jurisprudencia("sociedade", tribunais=["tjdft"], limite=1)
    c = _cob(r, "TJDFT")
    assert len(r["itens"]) == 1 and r["cursor"]
    assert c["truncado_local"] is True and c["truncado_remoto"] is True


def test_textual_fonte_nao_consultada_por_limite(svc, tjdft_conn, monkeypatch):
    svc.pesquisar_jurisprudencia("sociedade", tribunais=["tjdft"])  # semeia o acervo local
    monkeypatch.setitem(svc._connectors, "tjsp", type("X", (), {
        "coverage": {"busca_textual": True},
        "search": staticmethod(lambda *a, **k: pytest.fail("tjsp não deveria ser consultado")),
    })())
    r = svc.pesquisar_jurisprudencia("sociedade", tribunais=["tjdft", "tjsp"], limite=1)
    c = _cob(r, "TJSP")
    assert c["consulta"] == "nenhuma" and c["motivo_nao_consulta"] == "limite"
    assert c["total_remoto"] is None and c["lidos"] == 0 and c["recorte_acervo"] is None


def test_textual_falha_de_fonte_preserva_a_categoria(svc, tjdft_conn, monkeypatch):
    def falha(q, **kw):
        raise Unavailable("http_503", categoria="fonte_fora")

    monkeypatch.setattr(tjdft_conn, "search", falha)
    r = svc.pesquisar_jurisprudencia("sociedade", tribunais=["tjdft"])
    c = _cob(r, "TJDFT")
    assert c["consulta"] == "nenhuma" and c["motivo_nao_consulta"] == "falha"
    assert c["indisponivel"] == {"motivo": "http_503", "categoria": "fonte_fora"}
    assert c["total_remoto"] is None and c["truncado_remoto"] is False
    assert r["status"] == "indisponivel" and r["fontes"]["tjdft"]["categoria"] == "fonte_fora"


def test_textual_modo_offline(svc, tjdft_conn, monkeypatch):
    svc.pesquisar_jurisprudencia("sociedade", tribunais=["tjdft"])  # acervo local com o TJDFT
    monkeypatch.setenv("FV_OFFLINE", "1")
    r = svc.pesquisar_jurisprudencia("sociedade", tribunais=["tjdft"])
    c = _cob(r, "TJDFT")
    assert (c["capacidade"], c["consulta"], c["motivo_nao_consulta"]) == ("ambos", "acervo", "offline")
    assert c["total_remoto"] is None and c["lidos"] == 0 and c["indisponivel"] is None
    assert c["recorte_acervo"] == {"desde": "2026-09-16", "ate": "2026-10-08"}


def test_textual_offline_sem_acervo(svc, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    c = _cob(svc.pesquisar_jurisprudencia("sociedade", tribunais=["tjdft"]), "TJDFT")
    assert (c["capacidade"], c["consulta"], c["motivo_nao_consulta"]) == ("ao_vivo", "nenhuma", "offline")
    assert c["recorte_acervo"] is None and c["capturado_em"] is None


def test_textual_tribunal_desconhecido(svc):
    r = svc.pesquisar_jurisprudencia("sociedade", tribunais=["xyz"])
    c = _cob(r, "XYZ")
    assert (c["capacidade"], c["consulta"], c["motivo_nao_consulta"]) == ("nenhuma", "nenhuma", "nao_suportado")
    assert c["total_remoto"] is None and c["recorte_acervo"] is None and c["capturado_em"] is None


def test_textual_so_acervo_nao_e_confundido_com_ao_vivo(svc):
    semear(svc)
    r = svc.pesquisar_jurisprudencia("sintético", tribunais=["stj"])
    c = _cob(r, "STJ")
    assert c["capacidade"] in {"acervo", "ambos"} and "acervo" in c["consulta"]
    assert c["recorte_acervo"] == {"desde": "2025-05-05", "ate": "2025-05-05"}
    assert c["total_remoto"] is None


def test_textual_sem_filtro_de_tribunal_declara_os_implicados(svc):
    semear(svc)
    r = svc.pesquisar_jurisprudencia("sintético")
    nomes = {c["tribunal"] for c in r["cobertura"]}
    assert {"STJ", "TCU", "TJDFT", "TJSP", "STF", "CVM_COLEGIADO"} <= nomes
    assert len(nomes) == len(r["cobertura"])


def test_consulta_so_com_sigla_tem_cobertura_vazia(svc):
    r = svc.pesquisar_jurisprudencia("TJDFT")
    assert r["status"] == "entrada_insuficiente" and r["cobertura"] == []


# --- número CNJ ------------------------------------------------------------------------------

def _cnj(n, aaaa, jtr, oooo):
    dv = 98 - int(f"{n}{aaaa}{jtr}{oooo}00") % 97
    return f"{n}-{dv:02d}.{aaaa}.{jtr[0]}.{jtr[1:]}.{oooo}"


def test_cnj_tjdft_ao_vivo_com_total_informado(svc, tjdft_conn, monkeypatch):
    cnj = _cnj("0713166", "2018", "807", "0000")
    monkeypatch.setattr(tjdft_conn, "search", lambda q, **kw: CandidateList([], total=0, total_exato=True))
    r = svc.pesquisar_jurisprudencia(cnj)
    c = _cob(r, "TJDFT")
    assert (c["consulta"], c["motivo_nao_consulta"]) == ("ao_vivo", None)
    assert (c["total_remoto"], c["total_exato"]) == (0, True)


def test_cnj_offline(svc, tjdft_conn, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    c = _cob(svc.pesquisar_jurisprudencia(_cnj("0713166", "2018", "807", "0000")), "TJDFT")
    assert (c["consulta"], c["motivo_nao_consulta"], c["total_remoto"]) == ("nenhuma", "offline", None)


def test_cnj_falha_de_fonte(svc, tjdft_conn, monkeypatch):
    def falha(q, **kw):
        raise Unavailable("timeout", categoria="fonte_fora")

    monkeypatch.setattr(tjdft_conn, "search", falha)
    c = _cob(svc.pesquisar_jurisprudencia(_cnj("0713166", "2018", "807", "0000")), "TJDFT")
    assert c["motivo_nao_consulta"] == "falha"
    assert c["indisponivel"] == {"motivo": "timeout", "categoria": "fonte_fora"}


def test_cnj_de_tribunal_sem_conector(svc):
    r = svc.pesquisar_jurisprudencia(_cnj("0000001", "2020", "819", "0001"))
    c = _cob(r, "CNJ 8.19")
    assert (c["capacidade"], c["consulta"], c["motivo_nao_consulta"]) == ("nenhuma", "nenhuma", "nao_suportado")


def test_cnj_invalido_nao_consulta_nada(svc):
    r = svc.pesquisar_jurisprudencia("0710920-40.2025.8.07.0000")
    assert r["status"] == "formato_invalido" and r["cobertura"] == []


# --- classe e número (identificador) ---------------------------------------------------------

def test_numero_encontrado_declara_so_o_acervo(svc):
    semear(svc)
    r = svc.pesquisar_jurisprudencia("REsp 900.001")
    c = _cob(r, "STJ")
    assert c["consulta"] == "acervo" and c["total_remoto"] is None and c["lidos"] == 0
    assert c["recorte_acervo"] == {"desde": "2025-05-05", "ate": "2025-05-05"}


def test_numero_nao_confirmado_mantem_o_objeto_legado(svc):
    semear(svc)
    r = svc.pesquisar_jurisprudencia("REsp 9.999.999")
    assert isinstance(r["cobertura"], dict) and "tribunais" in r["cobertura"]  # contrato 1
    c = [x for x in r["cobertura_por_tribunal"] if x["tribunal"] == "STJ"][0]
    assert set(c) == CAMPOS and c["consulta"] == "acervo"


# --- conectores: o total é o da fonte --------------------------------------------------------

def _resp_json(corpo):
    return Response("https://x", "https://x", 200, {}, json.dumps(corpo).encode(), "0" * 64,
                    "2026-10-18T00:00:00Z", [], "application/json")


def test_tjsp_total_da_pagina_e_zero_estrutural():
    from freoa_verifica.connectors.tjsp import _parse_results

    pos = _parse_results(load_fixture("tjsp_busca_acordo_acionistas"), source_id="tjsp", limite=5)
    assert (len(pos), pos.total, pos.total_exato, pos.truncado) == (5, 28141, None, True)
    neg = _parse_results(load_fixture("tjsp_busca_negativa"), source_id="tjsp", limite=5)
    assert (list(neg), neg.total) == ([], 0)


def test_stj_local_total_exato_e_limite(tmp_path):
    from tests.test_e3_filtros import _stj_db

    _stj_db(tmp_path / "stj.db")
    conn = stj.StjConnector(tmp_path / "stj.db")
    got = conn.search("dissolução", limite=2, desde="2026-06-20")
    assert (len(got), got.total, got.total_exato, got.truncado) == (2, 3, True, True)
    vazio = conn.search("dissolução", desde="2027-01-01")
    assert (list(vazio), vazio.total, vazio.total_exato) == ([], 0, True)


@pytest.mark.parametrize("total, esperado", [
    ({"value": 10000, "relation": "gte"}, (10000, False)),
    ({"value": 1, "relation": "eq"}, (1, True)),
    ({"value": 1}, (1, None)),
    (1, (1, None)),
])
def test_datajud_total_e_relation(monkeypatch, total, esperado):
    corpo = {"hits": {"total": total, "hits": [{"_source": {
        "numeroProcesso": "00001234520208070001", "tribunal": "TJDFT", "grau": "G1", "nivelSigilo": 0}}]}}
    conn = datajud.DatajudConnector()
    monkeypatch.setattr(conn, "_post", lambda tribunal, body: _resp_json(corpo))
    got = conn._search_body("tjdft", {})
    assert (got.total, got.total_exato) == esperado


def test_datajud_zero_informado(monkeypatch):
    corpo = {"hits": {"total": {"value": 0, "relation": "eq"}, "hits": []}}
    conn = datajud.DatajudConnector()
    monkeypatch.setattr(conn, "_post", lambda tribunal, body: _resp_json(corpo))
    got = conn._search_body("tjdft", {})
    assert (list(got), got.total, got.total_exato) == ([], 0, True)
