"""E3 (decisão 0053): propagação de `desde`/`ate` do serviço à fonte, e declaração do que a fonte não filtra.

Expectativas escritas à mão a partir das datas das fixtures capturadas (tests/fixtures/tjdft/acordo_acionistas.json):
2185035 e 2185013 julgados em 2026-10-08; 2179323 em 2026-09-16.
"""
import hashlib
import json
import sqlite3
from urllib.parse import parse_qs

import pytest

from freoa_verifica.connectors import stj, tjdft, tjsp
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.service import Verifica
from freoa_verifica.transport import Response
from tests.fixture_util import load_fixture

URL = "https://jurisdf.tjdft.jus.br/api/v1/pesquisa"
CORPO_SEM_DATAS = {"query": "sociedade", "pagina": 0, "tamanho": 20, "retornaInteiroTeor": True}  # 0046


@pytest.fixture
def svc(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path / "h") as s:
        yield s


@pytest.fixture
def tjdft_conn(monkeypatch, svc):
    body = load_fixture("tjdft_acordo_acionistas")
    resp = Response(URL, URL, 200, {}, body, hashlib.sha256(body).hexdigest(), "2026-10-18T00:00:00Z", [], "application/json")
    chamadas = []
    monkeypatch.setattr(tjdft, "connector_fetch", lambda url, **kw: chamadas.append((url, kw)) or resp)
    c = tjdft.TjdftConnector()
    c.chamadas = chamadas
    svc._connectors["tjdft"] = c
    return c


def _ids(r):
    return sorted(i["id"] for i in r["itens"])


def _juris(svc, **kw):
    return svc.pesquisar_jurisprudencia("sociedade", tribunais=["tjdft"], **kw)


def _id_de(svc, identificador):
    return svc.conn.execute("SELECT id FROM decision WHERE official_id=?", (identificador,)).fetchone()[0]


@pytest.mark.parametrize("filtros, esperado", [
    ({}, {"2185035", "2185013", "2179323"}),
    ({"desde": "2026-10-01"}, {"2185035", "2185013"}),
    ({"desde": "2026-10-08"}, {"2185035", "2185013"}),  # limite inferior inclusivo
    ({"desde": "2026-10-09"}, set()),
    ({"ate": "2026-09-30"}, {"2179323"}),
    ({"ate": "2026-09-16"}, {"2179323"}),  # limite superior inclusivo
    ({"ate": "2026-09-15"}, set()),
    ({"desde": "2026-09-01", "ate": "2026-09-30"}, {"2179323"}),
    ({"desde": "2026-10-08", "ate": "2026-10-08"}, {"2185035", "2185013"}),
    ({"desde": "2026-09-17", "ate": "2026-10-07"}, set()),
])
def test_tjdft_datas_do_servico_ao_resultado(svc, tjdft_conn, filtros, esperado):
    r = _juris(svc, **filtros)
    assert _ids(r) == sorted(_id_de(svc, i) for i in esperado)
    # Nenhum parâmetro de data não comprovado é enviado: o corpo é o de sempre.
    assert [json.loads(kw["body"]) for _, kw in tjdft_conn.chamadas] == [CORPO_SEM_DATAS]
    assert r["fontes"]["tjdft"]["status"] == "ok"
    assert r["fontes"]["tjdft"]["filtros"] == {f: "local" for f in filtros}
    assert r["filtros_nao_aplicados"] == []


def test_tjdft_conector_filtra_antes_de_indexar(svc, tjdft_conn):
    r = _juris(svc, desde="2026-10-01")
    assert r["total_parcial"] == 2
    gravados = {row[0] for row in svc.conn.execute("SELECT official_id FROM decision")}
    assert gravados == {"2185035", "2185013"}  # o fora da janela nem foi indexado


def test_tjdft_filtro_com_limite(svc, tjdft_conn):
    r = _juris(svc, desde="2026-10-01", limite=1)
    assert len(r["itens"]) == 1 and r["truncado"] is True and r["cursor"]
    assert r["itens"][0]["datas"]["julgamento"] == "2026-10-08"


def test_tjdft_sem_data_no_registro_nao_prova_a_janela(tjdft_conn):
    assert tjdft._na_janela({}, "2026-01-01", None) is False
    assert tjdft._na_janela({"publication_date": "2026-05-01"}, "2026-01-01", "2026-12-31") is True
    assert tjdft._na_janela({}, None, None) is True


# ---------------------------------------------------------------- TJSP


def _captura_tjsp(monkeypatch, svc):
    chamadas = []

    def fake(url, **kw):
        chamadas.append((url, kw))
        raise Unavailable("fonte_fora_simulada")

    monkeypatch.setattr(tjsp, "connector_fetch", fake)
    svc._connectors["tjsp"] = tjsp.TjspConnector()
    return chamadas


@pytest.mark.parametrize("filtros, esperado", [
    ({"desde": "2026-03-05"}, {"dados.dtJulgamentoInicio": ["05/03/2026"]}),
    ({"ate": "2026-10-31"}, {"dados.dtJulgamentoFim": ["31/10/2026"]}),
    ({"desde": "2026-03-05", "ate": "2026-10-31"},
     {"dados.dtJulgamentoInicio": ["05/03/2026"], "dados.dtJulgamentoFim": ["31/10/2026"]}),
])
def test_tjsp_datas_viram_campos_do_formulario(svc, monkeypatch, filtros, esperado):
    chamadas = _captura_tjsp(monkeypatch, svc)
    r = svc.pesquisar_jurisprudencia("sociedade anônima", tribunais=["tjsp"], **filtros)
    form = parse_qs(chamadas[0][1]["body"].decode("utf-8"), keep_blank_values=True)
    assert {k: v for k, v in form.items() if k.startswith("dados.dtJulgamento")} == esperado
    # falha da fonte continua falha, não zero resultados
    assert r["fontes"]["tjsp"]["status"] == "unavailable" and r["fontes"]["tjsp"]["motivo"] == "fonte_fora_simulada"
    assert r["filtros_nao_aplicados"] == []


def test_tjsp_sem_datas_nao_envia_campos(svc, monkeypatch):
    chamadas = _captura_tjsp(monkeypatch, svc)
    svc.pesquisar_jurisprudencia("sociedade anônima", tribunais=["tjsp"])
    form = parse_qs(chamadas[0][1]["body"].decode("utf-8"), keep_blank_values=True)
    assert not [k for k in form if k.startswith("dados.dtJulgamento")]


def test_tjsp_data_fora_do_formato_nao_e_enviada():
    assert tjsp._data_br("2026-03-05") == "05/03/2026"
    assert tjsp._data_br("05/03/2026") is None and tjsp._data_br(None) is None


# ---------------------------------------------------------------- STJ local (SQL)


def _stj_db(path):
    c = sqlite3.connect(path)
    c.execute("CREATE VIRTUAL TABLE fts_stj USING fts5(key UNINDEXED,title,ementa,organ,rapporteur,decision_date,class_name,payload UNINDEXED)")
    linhas = [("a", "20260105"), ("b", "20260620"), ("c", "2026-12-01"), ("d", "15/07/2026"), ("e", "")]
    for chave, dia in linhas:
        c.execute("INSERT INTO fts_stj(key,title,ementa,decision_date,payload) VALUES (?,?,?,?,?)",
                  (chave, f"REsp {chave}", "dissolução parcial de sociedade", dia, "{}"))
    c.commit()
    c.close()


@pytest.mark.parametrize("filtros, esperado", [
    ({}, ["a", "b", "c", "d", "e"]),
    ({"desde": "2026-06-20"}, ["b", "c", "d"]),
    ({"ate": "2026-06-20"}, ["a", "b"]),
    ({"desde": "2026-06-21", "ate": "2026-11-30"}, ["d"]),
    ({"desde": "2026-12-02"}, []),
    ({"desde": "2026-01-05", "ate": "2026-01-05"}, ["a"]),
])
def test_stj_datas_no_sql(tmp_path, filtros, esperado):
    _stj_db(tmp_path / "stj.db")
    conn = stj.StjConnector(tmp_path / "stj.db")
    assert sorted(c.key for c in conn.search("dissolução", limite=10, **filtros)) == esperado


def test_stj_limite_vale_depois_do_filtro_de_data(tmp_path):
    _stj_db(tmp_path / "stj.db")
    conn = stj.StjConnector(tmp_path / "stj.db")
    got = conn.search("dissolução", limite=2, desde="2026-06-20")
    assert len(got) == 2 and {c.key for c in got} <= {"b", "c", "d"}


def test_stj_no_servico_a_busca_ao_vivo_nao_existe_e_e_declarada(svc, tmp_path):
    # `busca_textual_ao_vivo: False`: o serviço não chama stj.search; o STJ responde pelo acervo local (SQL do serviço).
    _stj_db(tmp_path / "stj.db")
    svc._connectors["stj"] = stj.StjConnector(tmp_path / "stj.db")
    r = svc.pesquisar_jurisprudencia("dissolução", tribunais=["stj"], desde="2026-06-20")
    assert r["fontes"]["stj"] == {"status": "unavailable", "motivo": "busca_textual_ao_vivo_nao_suportada", "parcial": False}


# ---------------------------------------------------------------- declaração do que não é filtrado


def test_fonte_sem_filtro_de_data_declara(svc, monkeypatch):
    class Fonte(tjdft.TjdftConnector):
        id = "tcu"
        filtros = {}

        def search(self, q, **filtros):
            self.recebido = filtros
            return tjdft.CandidateList([])

    svc._connectors["tcu"] = f = Fonte()
    r = svc.pesquisar_jurisprudencia("licitação", tribunais=["tcu"], desde="2026-01-01", ate="2026-06-30")
    assert f.recebido == {"desde": "2026-01-01", "ate": "2026-06-30"}  # o serviço ainda repassa
    assert r["filtros_nao_aplicados"] == [
        {"fonte": "tcu", "filtro": "desde", "compensacao": "filtro_local_sobre_o_recuperado"},
        {"fonte": "tcu", "filtro": "ate", "compensacao": "filtro_local_sobre_o_recuperado"},
    ]
    assert r["fontes"]["tcu"]["filtros"] == {"desde": "nao_suportado", "ate": "nao_suportado"}


def test_cvm_colegiado_so_o_ano_de_desde_chega_a_fonte(svc, monkeypatch):
    from freoa_verifica.connectors import cvm_colegiado

    class Fake(cvm_colegiado.CvmColegiadoConnector):
        def _sync_year(self, ano, q, limite):
            self.ano = ano
            return []

    svc._connectors["cvm_colegiado"] = f = Fake()
    r = svc.pesquisar_jurisprudencia("fato relevante", tribunais=["cvm"], desde="2025-03-01", ate="2025-09-30")
    assert f.ano == 2025
    assert r["fontes"]["cvm_colegiado"]["filtros"] == {"desde": "remoto", "ate": "nao_suportado"}
    assert r["filtros_nao_aplicados"] == [
        {"fonte": "cvm_colegiado", "filtro": "ate", "compensacao": "filtro_local_sobre_o_recuperado"}]


def test_sem_filtros_pedidos_nada_a_declarar(svc, tjdft_conn):
    r = _juris(svc)
    assert r["filtros_nao_aplicados"] == [] and r["fontes"]["tjdft"]["filtros"] == {}
