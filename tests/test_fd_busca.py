"""Frente F-D: busca por número, staging ao vivo, fontes não consultadas, pertinência e tesauro."""
import hashlib
import json
from types import SimpleNamespace

import pytest

from freoa_verifica.connectors.base import Candidate, ParsedDecision
from freoa_verifica.parsers.model import ParsedDocument, Provision, Redaction
from freoa_verifica.search import tesauro
from freoa_verifica.service import Verifica
from freoa_verifica.transport import Response


def _indexar(svc, court, official_id, ementa, *, cls="REsp", number=None, date="2024-05-01"):
    text = ementa + " " + "Fundamentação do voto. " * 40
    body = text.encode()
    url = f"https://example.org/{court}/{official_id}"
    resp = Response(url, url, 200, {}, body, hashlib.sha256(body).hexdigest(),
                    "2026-10-18T00:00:00Z", [], "text/plain")
    parsed = ParsedDecision("fixture", "acordao", court, official_id, ementa=ementa, text=text,
                            class_name=cls, judgment_date=date, organ="Terceira Turma",
                            rapporteur="Relator", metadata={"processo": number or official_id})
    conn = SimpleNamespace(id=court.lower(), authority=court, hosts={"example.org"},
                           fetch=lambda _: resp, parse=lambda _: parsed)
    svc._index_candidate_juris(conn, Candidate(court.lower(), official_id, "Acórdão"))


@pytest.fixture
def acervo(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    with Verifica(tmp_path / "home") as svc:
        _indexar(svc, "STJ", "2210785", "Recurso sobre acordo de acionistas", number="2.210.785")
        _indexar(svc, "STJ", "2210785-AgInt", "Agravo contra decisão sobre acordo", cls="AgInt no REsp",
                 number="2210785", date="2024-09-01")
        _indexar(svc, "STJ", "1111111", "Outro processo sobre acordo de acionistas", number="1111111")
        yield svc


# --- A6 ---------------------------------------------------------------------

@pytest.mark.parametrize("q", ["REsp 2.210.785", "REsp 2210785", "Recurso Especial nº 2.210.785"])
def test_resp_presente_e_achado_pelo_numero(acervo, q):
    res = acervo.pesquisar_jurisprudencia(q)
    assert res["status"] == "encontrada" and res["modo_busca"] == "numero"
    assert [i["classe_numero"] for i in res["itens"]] == ["REsp 2.210.785"]
    assert res["itens"][0]["evidencia"]["capture_id"] and res["itens"][0]["relacao"] == "exato"
    # incidente do mesmo processo vai para `relacionados`; outro processo nunca aparece
    assert [i["relacao"] for i in res["relacionados"]] == ["incidente_do_mesmo_processo"]
    assert res["resultados_textuais"] == []
    assert "1111111" not in json.dumps(res)


def test_resp_ausente_nao_mistura_outros_processos(acervo):
    res = acervo.pesquisar_jurisprudencia("REsp 9.999.999")
    assert res["status"] == "nao_confirmado_no_acervo"
    assert res["itens"] == [] and res["resultados"] == [] and res["relacionados"] == []
    cob = res["cobertura"]
    assert cob["tribunais"] == ["STJ"] and cob["registros"] == 3 and cob["desde"] and cob["ate"]


def test_busca_textual_continua_achando_o_documento_certo(acervo):  # controle positivo
    ids = {i["classe_numero"] for i in acervo.pesquisar_jurisprudencia("acordo de acionistas")["itens"]}
    assert "REsp 2.210.785" in ids and "REsp 1111111" in ids


# --- A7, A9/M7, M10 ---------------------------------------------------------

def _doc(titulo, texto, numero):
    red = Redaction(text=texto, struck=False, order=0, annotations=[], span=(0, len(texto)),
                    superseded_without_strike=False)
    return ParsedDocument(profile="cvm_html", parser_version="t", title=titulo, ementa=None, text=texto,
                          provisions=[Provision(path="art1", label="Art. 1º", scope="body",
                                                headings=[], redactions=[red], ambiguous=False)])


class _Cvm:
    id = "cvm_normas"
    coverage = {"busca_textual": True}

    def search(self, q, **kw):
        return [Candidate("cvm_normas", "cvm:resolucoes:99", "Resolução CVM 99", "https://x.org/99",
                          metadata={"tipo": "resolucoes", "numero": 99, "ano": 2022})]

    def fetch(self, cand):
        body = b"x"
        return Response("https://x.org/99", "https://x.org/99", 200, {}, body, hashlib.sha256(body).hexdigest(),
                        "2026-10-18T00:00:00Z", [], "text/html")

    def parse(self, resp):
        return _doc("Resolução CVM nº 99", "Art. 1º Fica vedada a negociação de zebrafish quântico.", 99)


def _live(svc, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    svc._connectors["cvm_normas"] = _Cvm()
    def nunca(*a, **k):
        raise AssertionError("não deveria ser consultado")
    for cid in ("planalto", "bcb", "senado"):
        svc._connectors[cid] = SimpleNamespace(id=cid, coverage={"busca_textual": cid != "planalto"}, search=nunca)


def test_fts_canonico_intacto_apos_busca_ao_vivo(verifica_populada, monkeypatch):
    svc, *_ = verifica_populada
    antes = svc.conn.execute("SELECT COUNT(*) FROM fts_redaction").fetchone()[0]
    _live(svc, monkeypatch)
    svc._connectors["bcb"].search = lambda q, **k: []
    res = svc.buscar_legislacao("zebrafish", fonte="cvm_normas")
    assert [i["capture_id"] for i in res["itens"]] and res["fontes"]["cvm_normas"]["status"] == "ok"
    assert svc.conn.execute("SELECT COUNT(*) FROM fts_redaction").fetchone()[0] == antes
    assert svc.conn.execute("SELECT COUNT(*) FROM fts_staging").fetchone()[0] == 1
    # busca local não vê o candidato; a busca que pede candidatos ao vivo vê, marcado
    local = svc.buscar_legislacao("zebrafish", fonte="__somente_local__")
    assert local["itens"] == []
    vivo = svc.buscar_legislacao("zebrafish")
    assert any(i.get("candidato_ao_vivo") for i in vivo["itens"])


def test_fontes_nao_consultadas(verifica_populada, monkeypatch):
    svc, *_ = verifica_populada
    _live(svc, monkeypatch)
    svc._connectors["bcb"].search = lambda q, **k: []
    svc._connectors["senado"].search = lambda q, **k: []
    res = svc.buscar_legislacao("zebrafish")
    assert res["fontes"]["planalto"] == {"status": "nao_consultada",
                                         "motivo": "busca_textual_nao_suportada", "parcial": False}
    assert res["fontes"]["cvm_normas"]["status"] == "ok"
    monkeypatch.setenv("FV_OFFLINE", "1")
    off = svc.buscar_legislacao("zebrafish")
    assert {v["status"] for v in off["fontes"].values()} == {"nao_consultada"}
    # limite já atingido pelo acervo local: demais fontes não são consultadas nem marcadas ok
    monkeypatch.delenv("FV_OFFLINE")
    cheio = svc.buscar_legislacao("alienação", limite=1)
    assert cheio["itens"] and {v["status"] for v in cheio["fontes"].values()} == {"nao_consultada"}


def test_filtro_fonte_antes_do_limite(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    from freoa_verifica.aliases import WorkKey
    with Verifica(tmp_path / "h") as svc:
        for n in range(1, 9):  # 8 obras do Planalto à frente no ranking
            svc.indexar_obra(source_id="planalto", work_key=WorkKey("federal", "lei", str(n), 2000),
                             document=_doc(f"Lei {n}", "Art. 1º alienação alienação controle.", n),
                             body=b"p%d" % n, url=f"https://p.org/{n}", label=f"Lei {n}/2000")
        svc.indexar_obra(source_id="cvm_normas", work_key=WorkKey("cvm", "resolucao", "99", 2022),
                         document=_doc("Resolução CVM 99", "Art. 1º alienação de controle de companhia.", 99),
                         body=b"c", url="https://c.org/99", label="Resolução CVM 99")
        res = svc.buscar_legislacao("alienação", fonte="cvm_normas", limite=1)
        assert [i["obra"] for i in res["itens"]] == ["Resolução CVM 99"]


# --- M5/M6 ------------------------------------------------------------------

def test_pertinencia_e_corte_de_dois_tercos(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    with Verifica(tmp_path / "h") as svc:
        _indexar(svc, "STJ", "A", "debentures conversíveis em ações emitidas")
        _indexar(svc, "STJ", "B", "debentures conversíveis em títulos")
        _indexar(svc, "STJ", "C", "debentures simples")
        res = svc.pesquisar_jurisprudencia("debentures conversíveis emitidas")
        por_id = {i["classe_numero"]: i for i in res["itens"]}
        assert por_id["REsp A"]["pertinencia"] == 1.0 and por_id["REsp A"]["correspondencia"] == "todos_os_termos"
        assert por_id["REsp B"]["pertinencia"] == 0.67 and por_id["REsp B"]["correspondencia"] == "parcial"
        assert "REsp C" not in por_id  # 1/3 abaixo do corte
        assert [i["classe_numero"] for i in res["itens"]][0] == "REsp A"


# --- Tesauro ----------------------------------------------------------------

def test_tesauro_pequeno_e_versionado():
    t = tesauro()
    assert t["versao"] == "tesauro-1" and len(t["pares"]) < 30


def test_tesauro_expande_tag_along_e_recupera_art_254a(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    with Verifica(tmp_path / "h") as svc:
        _indexar(svc, "STJ", "X", "Aplicação do art. 254-A da Lei das S.A. à venda do bloco")
        _indexar(svc, "STJ", "Y", "Cláusula de tag along em contrato de compra e venda de ações")
        _indexar(svc, "STJ", "Z", "Responsabilidade civil do transportador")
        res = svc.pesquisar_jurisprudencia("tag along")
        ids = {i["classe_numero"] for i in res["itens"]}
        assert ids == {"REsp X", "REsp Y"}  # Y é controle positivo (texto literal)
        assert res["tesauro"]["versao"] == "tesauro-1"
        assert {"termo": "tag along", "alternativa": "art. 254-A"} in res["tesauro"]["expansoes"]
        sem = svc.pesquisar_jurisprudencia("transportador")
        assert sem["tesauro"]["expansoes"] == []
