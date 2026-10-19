"""Conector TJDFT (decisão 0041): captura = JSON inteiro; vínculo por uuid; inteiro teor conservador."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from freoa_verifica.connectors import tjdft
from freoa_verifica.connectors.base import Candidate, Unavailable
from freoa_verifica.courts import normalize_court
from freoa_verifica.service import Verifica
from freoa_verifica.transport import Response

FX = Path(__file__).parent / "fixtures" / "tjdft"
URL = "https://jurisdf.tjdft.jus.br/api/v1/pesquisa"


def _load(name):
    return json.loads((FX / f"{name}.json").read_text(encoding="utf-8"))


def _resp(data, status=200):
    body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode("utf-8")
    return Response(URL, URL, status, {}, body, hashlib.sha256(body).hexdigest(), "2026-10-18T00:00:00Z", [], "application/json")


@pytest.fixture
def conn(monkeypatch):
    state = {"resp": None, "calls": []}

    def fake(url, **kw):
        state["calls"].append((url, kw))
        if isinstance(state["resp"], Exception):
            raise state["resp"]
        return state["resp"]

    monkeypatch.setattr(tjdft, "connector_fetch", fake)
    c = tjdft.TjdftConnector()
    c.state = state
    return c


def _search(conn, data, q="x", **kw):
    conn.state["resp"] = _resp(data)
    return conn.search(q, **kw)


def _por_sub(data, subbase):
    return next(r for r in data["registros"] if r["subbase"] == subbase)


def _parse(conn, data, rec):
    cands = _search(conn, data)
    cand = next(c for c in cands if c.metadata["uuid"] == rec["uuid"])
    return conn.parse_candidate(conn.fetch(cand), cand), cand


def test_requisicao_post_json_pelo_transporte(conn):
    _search(conn, _load("acordo_acionistas"), "acordo de acionistas", limite=3, base="acordaos")
    url, kw = conn.state["calls"][0]
    assert url == URL and kw["method"] == "POST" and kw["hosts"] == {"jurisdf.tjdft.jus.br"}
    assert kw["path_prefixes"] == {"jurisdf.tjdft.jus.br": ("/api/v1/pesquisa",)} and kw["mimes"] == {"application/json"}
    assert json.loads(kw["body"]) == {"query": "\"acordo de acionistas\"", "pagina": 0, "tamanho": 3,  # locucoes-1
                                       "termosAcessorios": [{"campo": "base", "valor": "acordaos"}]}


def test_acordao_so_ementa(conn):
    data = _load("acordo_acionistas")
    rec = data["registros"][0]
    cands = _search(conn, data)
    assert cands.total == 3025 and len(cands) == 3
    p, cand = _parse(conn, data, rec)
    assert (p.profile, p.kind, p.court, p.official_id) == ("tjdft_ementa", "acordao", "TJDFT", rec["identificador"])
    assert p.text == "" and p.ementa == rec["ementa"] and "documento" not in p.metadata
    assert p.judgment_date == "2026-10-08" and p.publication_date == "2026-10-15"
    assert p.organ == rec["descricaoOrgaoJulgador"] and p.rapporteur == rec["nomeRelator"]
    assert {k: p.metadata[k] for k in ("uuid", "processo", "base", "subbase", "codigoClasseCnj")} == {
        "uuid": rec["uuid"], "processo": rec["processo"], "base": "acordaos", "subbase": "acordaos", "codigoClasseCnj": rec["codigoClasseCnj"]}
    assert cand.url is None
    assert conn.fetch(cand).sha256 == hashlib.sha256(conn.state["resp"].body).hexdigest()


def test_monocratica_e_presidencia_com_inteiro_teor_valido(conn):
    mono = _load("monocratica")
    rec = mono["registros"][0]
    p, _ = _parse(conn, mono, rec)
    assert (p.profile, p.kind, p.metadata["documento"]) == ("tjdft_inteiro_teor", "monocratica", "inteiro_teor")
    assert p.text == rec["inteiroTeor"] and rec["processo"] in p.text
    proc = _load("processo")
    p2, _ = _parse(conn, proc, _por_sub(proc, "decisoes-presidencia"))
    assert p2.kind == "monocratica" and p2.profile == "tjdft_inteiro_teor"


def test_inteiro_teor_html_indisponivel_nao_promove(conn):
    data = _load("acordo_acionistas")
    rec = data["registros"][0]
    rec["inteiroTeorHtml"] = "<p>Inteiro Teor indisponível.</p>"
    assert rec["possuiInteiroTeor"] is True
    p, _ = _parse(conn, data, rec)
    assert p.profile == "tjdft_ementa" and p.text == "" and "documento" not in p.metadata
    # Mesmo longo e com o número do processo, a mensagem barra (acentos e caixa normalizados).
    rec["inteiroTeorHtml"] = "<div>INTEIRO TEOR INDISPONIVEL " + rec["processo"] + " x" * 800 + "</div>"
    assert _parse(conn, data, rec)[0].profile == "tjdft_ementa"


def test_inteiro_teor_sem_numero_do_processo_ou_curto(conn):
    mono = _load("monocratica")
    rec = mono["registros"][0]
    rec["inteiroTeor"] = rec["inteiroTeor"].replace(rec["processo"], "0000000-00.0000.0.00.0000")
    assert _parse(conn, mono, rec)[0].profile == "tjdft_ementa"
    sem_numero = _load("monocratica")["registros"][2]  # registro real cujo texto não traz o próprio número
    assert sem_numero["processo"] not in sem_numero["inteiroTeor"]
    assert _parse(conn, _load("monocratica"), sem_numero)[0].profile == "tjdft_ementa"
    curto = _load("monocratica")
    r = curto["registros"][0]
    r["inteiroTeor"] = f"Processo {r['processo']} decisão breve."
    assert _parse(conn, curto, r)[0].profile == "tjdft_ementa"


def test_inteiro_teor_html_valido_vira_texto(conn):
    mono = _load("monocratica")
    rec = mono["registros"][0]
    corpo = f"<html><body><style>x{{}}</style><p>Processo {rec['processo']}</p><p>" + "texto da decisão " * 80 + " Ante o exposto, indefiro. Publique-se.</p></body></html>"  # 1.2.0: exige fecho decisório
    rec["inteiroTeor"], rec["inteiroTeorHtml"] = None, corpo
    p, _ = _parse(conn, mono, rec)
    assert p.profile == "tjdft_inteiro_teor" and "<p>" not in p.text and "x{}" not in p.text and rec["processo"] in p.text


def test_vinculo_por_uuid_e_nao_por_posicao(conn):
    data = _load("monocratica")
    cands = _search(conn, data)
    alvo = cands[1]
    data2 = copy.deepcopy(data)
    data2["registros"].reverse()  # a posição muda; o vínculo é o uuid
    resp2 = _resp(data2)
    p = conn.parse_candidate(resp2, alvo)
    assert p.official_id == alvo.key and p.metadata["uuid"] == alvo.metadata["uuid"]
    forjado = Candidate("tjdft", "999", "x", metadata={"uuid": alvo.metadata["uuid"]})
    with pytest.raises(Unavailable):
        conn.parse_candidate(resp2, forjado)
    ausente = Candidate("tjdft", alvo.key, "x", metadata={"uuid": "nao-existe"})
    with pytest.raises(Unavailable):
        conn.parse_candidate(resp2, ausente)


def test_segredo_de_justica_descartado(conn):
    data = _load("acordo_acionistas")
    data["registros"][0]["segredoJustica"] = True
    cands = _search(conn, data)
    rec = data["registros"][0]
    assert len(cands) == 2 and rec["uuid"] not in {c.metadata["uuid"] for c in cands}
    with pytest.raises(Unavailable):
        conn.parse_candidate(conn.state["resp"], Candidate("tjdft", rec["identificador"], "x", metadata={"uuid": rec["uuid"]}))


def test_hits_zero_e_lista_vazia_com_total_zero(conn):
    cands = _search(conn, _load("vazio"))
    assert list(cands) == [] and cands.total == 0


@pytest.mark.parametrize("resp", [
    Unavailable("http_503"),
    b"<html>nao e json</html>",
    {"hits": {"value": 5}, "paginacao": {}},
    {"hits": {"value": 5}, "registros": []},
    {"registros": []},
    {"hits": {"value": 1}, "registros": ["x"]},
])
def test_falhas_sao_unavailable(conn, resp):
    conn.state["resp"] = resp if isinstance(resp, Exception) else _resp(resp)
    with pytest.raises(Unavailable):
        conn.search("x")


def test_http_diferente_de_200_e_unavailable(conn):
    conn.state["resp"] = _resp(_load("vazio"), status=204)
    with pytest.raises(Unavailable) as e:
        conn.search("x")
    assert e.value.reason == "http_204"


def test_normalizacao_de_tribunal():
    for v in ("TJDFT", "tjdf", "Tribunal de Justiça do Distrito Federal e dos Territórios"):
        assert normalize_court(v) == "tjdft"


@pytest.fixture
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    with Verifica(tmp_path / "h") as s:
        yield s


def test_ponta_a_ponta_indexacao_obter_decisao_e_pesquisa(svc, conn):
    data = _load("frase_exata")  # 1 monocrática válida + 2 acórdãos
    cands = _search(conn, data)
    mono = next(c for c in cands if c.metadata["subbase"] == "decisoes-monocraticas")
    acord = next(c for c in cands if c.metadata["base"] == "acordaos")
    item = svc._index_candidate_juris(conn, mono)
    assert item["capture_id"] and item["rotulo_autoridade"] == "E" and item["nivel_prova"] != "metadados"
    svc._index_candidate_juris(conn, acord)
    assert svc.obter_decisao(mono.key, tribunal="tjdft", parte="inteiro_teor")["status"] == "encontrada"
    r = svc.obter_decisao(acord.key, tribunal="tjdft", parte="inteiro_teor")
    assert r["status"] == "parte_indisponivel" and r["texto"] is None
    assert svc.obter_decisao(acord.key, tribunal="tjdft")["parte_entregue"] == "ementa"
    row = svc.conn.execute("SELECT court, kind, number FROM decision WHERE official_id=?", (mono.key,)).fetchone()
    assert (row["court"], row["kind"], row["number"]) == ("TJDFT", "decisao_monocratica", mono.metadata["processo"])
    found = svc.pesquisar_jurisprudencia("Gabinete Desembargador", tribunais=["tjdft"])["itens"]
    assert any(i["tribunal"] == "TJDFT" for i in found)
    assert svc.pesquisar_jurisprudencia("Gabinete Desembargador", tribunais=["tjdf"])["itens"]


# Auditoria comparativa 1.2.0: número CNJ isolado devolve só o próprio processo.
def test_cnj_digito_verificador_invalido(svc):
    r = svc.pesquisar_jurisprudencia("0710920-40.2025.8.07.0000")
    assert r["status"] == "formato_invalido" and r["itens"] == []


def test_cnj_offline_sem_acervo_nao_mistura_outros(svc):
    r = svc.pesquisar_jurisprudencia("0713166-62.2018.8.07.0000")
    assert r["status"] == "nao_confirmado_no_acervo" and r["itens"] == []


def test_cnj_busca_oficial_traz_so_o_processo(svc, conn, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE")
    data = _load("processo")  # registros do processo 0713166-62.2018.8.07.0000
    conn.state["resp"] = _resp(data)
    svc._connectors["tjdft"] = conn
    r = svc.pesquisar_jurisprudencia("0713166-62.2018.8.07.0000")
    assert r["status"] == "encontrada" and r["itens"]
    assert {i["classe_numero"].split()[-1] for i in r["itens"]} == {"0713166-62.2018.8.07.0000"}
    assert r["fontes"]["tjdft"]["status"] == "ok"


def test_cnj_fonte_sem_o_processo_nao_devolve_outros(svc, conn, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE")
    conn.state["resp"] = _resp(_load("acordo_acionistas"))  # fonte responde com outros processos
    svc._connectors["tjdft"] = conn
    r = svc.pesquisar_jurisprudencia("0713166-62.2018.8.07.0000")
    assert r["status"] == "nao_encontrado_na_fonte" and r["itens"] == []


def test_monocratica_com_inteiro_teor_nao_grava_texto_como_ementa(svc, conn):
    data = _load("monocratica")
    cands = _search(conn, data)
    mono = next(c for c in cands if c.metadata["uuid"] == data["registros"][0]["uuid"])
    svc._index_candidate_juris(conn, mono)
    kinds = [r[0] for r in svc.conn.execute(
        "SELECT dd.kind FROM decision_document dd JOIN decision d ON d.id=dd.decision_id WHERE d.official_id=?", (mono.key,))]
    assert kinds == ["inteiro_teor"]
    assert svc.obter_decisao(mono.key, tribunal="tjdft")["status"] == "parte_indisponivel"  # não há ementa


def test_busca_filtrada_pelo_tjdft_consulta_a_api_mesmo_com_acervo_local(svc, conn, monkeypatch):
    data = _load("frase_exata")
    for cand in _search(conn, data):  # acervo local já tem resultados
        svc._index_candidate_juris(conn, cand)
    monkeypatch.delenv("FV_OFFLINE")
    conn.state["calls"].clear()
    conn.state["resp"] = _resp(_load("acordo_acionistas"))
    svc._connectors["tjdft"] = conn
    r = svc.pesquisar_jurisprudencia("apuração de haveres", tribunais=["tjdft"], limite=1)
    assert conn.state["calls"] and r["fontes"]["tjdft"]["status"] == "ok"


def test_consulta_oficial_poe_locucoes_entre_aspas(conn):
    assert tjdft.consulta_oficial("exclusao de socio sociedade limitada") == '"sociedade limitada" "exclusão de sócio"'
    assert tjdft.consulta_oficial("0713166-62.2018.8.07.0000") == "0713166-62.2018.8.07.0000"
    assert tjdft.consulta_oficial('"acordo de acionistas" x') == '"acordo de acionistas" x'
    _search(conn, _load("vazio"), "apuracao de haveres")
    corpo = json.loads(conn.state["calls"][-1][1]["body"])
    assert corpo["query"] == '"apuração de haveres"'
