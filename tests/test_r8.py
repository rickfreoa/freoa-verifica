"""Filtro de tribunal aplicado antes do limite e da paginação."""
import asyncio

import pytest

from freoa_verifica.service import Verifica
from freoa_verifica.store import repo


@pytest.fixture
def mixed(tmp_path, monkeypatch, verifica_populada):
    monkeypatch.setenv("FV_OFFLINE", "1")
    svc, rw, _ = verifica_populada
    from freoa_verifica.ids import new_ulid
    if svc:
        for court, count in [("CVM", 20), ("STJ", 9), ("STF", 1)]:
            for i in range(count):
                did = repo.upsert_decision(svc.conn, court=court, kind="acordao", official_id=f"{court}-{i}")
                svc.conn.execute("INSERT INTO decision_document(id,decision_id,capture_id,kind,text,sha256) VALUES (?,?,?,?,?,?)",
                                 (new_ulid(), did, rw.capture_id, "ementa", "acordo acionistas", rw.sha256))
                repo.index_decision(svc.conn, ementa="acordo acionistas", inteiro_teor="",
                                    court=court, class_="acordao", official_id=f"{court}-{i}")
        yield svc


@pytest.mark.parametrize("alias", ["stj", "STJ", " Superior Tribunal de Justiça "])
def test_filter_before_limit_and_cursor(mixed, alias):
    first = mixed.pesquisar_jurisprudencia("acordo", tribunais=[alias], limite=3)
    second = mixed.pesquisar_jurisprudencia("acordo", tribunais=[alias], limite=3,
                                         cursor=first["cursor"])
    assert first["cursor"]
    for page in (first, second):
        assert len(page["itens"]) == 3
        assert {x["tribunal"] for x in page["itens"]} == {"STJ"}
    assert len(mixed.pesquisar_jurisprudencia("acordo", tribunais=[], limite=3)["itens"]) == 0


def test_court_sets_and_unsupported(mixed):
    assert len(mixed.pesquisar_jurisprudencia("acordo", limite=50)["itens"]) == 30
    result = mixed.pesquisar_jurisprudencia("acordo", tribunais=["stf"], limite=3)
    assert [x["tribunal"] for x in result["itens"]] == ["STF"]
    assert result["fontes"]["stf"]["motivo"] == "offline"
    assert mixed.pesquisar_jurisprudencia("acordo", tribunais=["invalido"])["fontes"]["invalido"]["motivo"] == "fonte_nao_suportada"
    result = mixed.pesquisar_jurisprudencia("acordo", tribunais=["cvm", "STJ"], limite=50)
    assert len(result["itens"]) == 29


def test_mcp_aliases_and_stf(mixed, monkeypatch):
    from mcp import Client
    from freoa_verifica import mcp_server
    from tests.test_mcp import _tool_payload

    monkeypatch.setitem(mcp_server._servicos, str(mixed.home), mixed)
    server = mcp_server.create_mcp(home=str(mixed.home))

    async def run():
        async with Client(server) as client:
            for alias, expected in [("Superior Tribunal de Justiça", "STJ"), ("stf", "STF")]:
                result = await client.call_tool("pesquisar_jurisprudencia", {"q": "acordo", "tribunais": [alias]})
                assert not result.is_error
                assert {i["tribunal"] for i in _tool_payload(result)["itens"]} == {expected}
    asyncio.run(run())


def test_tcu_bounded_scan_is_not_zero(monkeypatch):
    from freoa_verifica.connectors import tcu
    from freoa_verifica.connectors.base import Unavailable

    monkeypatch.setattr(tcu, "MAX_PAGES", 2)
    connector = tcu.TcuConnector()
    monkeypatch.setattr(connector, "_page", lambda **kw: [{"titulo": "outro"}])
    with pytest.raises(Unavailable, match="tcu_busca_incompleta"):
        connector.search("acionistas")
    monkeypatch.setattr(connector, "_page", lambda **kw: [])
    assert connector.search("acionistas") == []


def test_tjsp_challenge_is_not_ignored(monkeypatch):
    from freoa_verifica.connectors import tjsp
    from freoa_verifica.connectors.base import Unavailable

    def fetch(url, **kwargs):
        assert not kwargs.get("ignore_challenge_kinds")
        raise Unavailable("captcha")
    monkeypatch.setattr(tjsp, "connector_fetch", fetch)
    with pytest.raises(Unavailable, match="captcha"):
        tjsp.TjspConnector().search("acordo de acionistas")


@pytest.mark.parametrize("source,kind,number,title,expected", [
    ("cvm_normas", "resolucoes", "160", "Resolução CVM nº 160, de 13 de julho de 2022", ("cvm", "resolucao")),
    ("bcb", "Resolução CMN", "4557", "Resolução CMN nº 4.557, de 23 de fevereiro de 2017", ("cmn", "resolucao")),
    ("bcb", "Resolução BCB", "1", "Resolução BCB nº 1, de 12 de agosto de 2020", ("bcb", "resolucao_bcb")),
])
def test_candidate_identity_mapping(verifica_populada, source, kind, number, title, expected):
    from types import SimpleNamespace
    from freoa_verifica.connectors.base import Candidate
    from freoa_verifica.parsers.model import ParsedDocument
    svc, _, _ = verifica_populada
    doc = ParsedDocument("test", "1", title, None, title)
    connector = SimpleNamespace(id=source,
        fetch=lambda c: SimpleNamespace(body=title.encode(), url="https://example.org/ato", final_url=None, fetched_at=None),
        parse=lambda r: doc)
    item = svc._index_candidate_legis(connector, Candidate(source, number, title,
        metadata={"tipo":kind,"numero":number}))
    assert item["capture_id"]
    row = svc.conn.execute("SELECT authority,kind FROM work WHERE number=?", (number,)).fetchone()
    assert tuple(row) == expected


@pytest.mark.parametrize("method", ["buscar_normas_cvm", "buscar_normas_bcb"])
@pytest.mark.parametrize("all_failed", [False, True])
def test_specialized_partial_failure(verifica_populada, monkeypatch, method, all_failed):
    from types import SimpleNamespace
    from freoa_verifica.connectors.base import Candidate
    svc, rw, _ = verifica_populada
    monkeypatch.setenv("FV_OFFLINE", "0")
    candidates = [Candidate("test", str(i), "Ato") for i in range(2)]
    monkeypatch.setattr(svc, "_get", lambda cid: SimpleNamespace(search=lambda *a, **kw: candidates))
    monkeypatch.setattr(svc, "_index_candidate_legis", lambda conn, cand:
        {"capture_id": None, "trecho": "não exibir", "motivo": "IDENTIDADE_DIVERGENTE"}
        if cand.key == "1" or all_failed else {"capture_id": rw.capture_id, "trecho": "Regra"})
    result = getattr(svc, method)("regra")
    assert result["status"] == ("indisponivel" if all_failed else "parcial")
    assert len(result["itens"]) == (0 if all_failed else 1)
    assert result["falhas"][0]["motivo"] == "IDENTIDADE_DIVERGENTE"
    assert all("trecho" not in failure and "capture_id" not in failure for failure in result["falhas"])
    monkeypatch.setenv("FV_OFFLINE", "1")
    assert getattr(svc, method)("regra")["motivo"] == "offline"
