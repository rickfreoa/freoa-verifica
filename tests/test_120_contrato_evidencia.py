"""1.2.0 (decisão 0037): a descrição da prova corresponde ao documento entregue (achados A1, A2, A3, A5, A12)."""
import hashlib
from types import SimpleNamespace

import pytest

from freoa_verifica import derivados
from freoa_verifica.connectors.base import Candidate, ParsedDecision
from freoa_verifica.limites import EntradaInvalida
from freoa_verifica.service import Verifica
from freoa_verifica.transport import Response


def _indexar(svc, court, official, *, text, ementa="ementa oficial", profile="fixture", kind="acordao",
             cls="REsp", organ="Terceira Turma", metadata=None):
    body = (text or ementa).encode()
    url = f"https://example.org/{court}/{official}"
    resp = Response(url, url, 200, {}, body, hashlib.sha256(body).hexdigest(), "2026-10-18T00:00:00Z", [], "text/plain")
    parsed = ParsedDecision(profile, kind, court, official, ementa=ementa, text=text, class_name=cls,
                            organ=organ, judgment_date="2025-05-05", rapporteur="Relator", metadata=metadata or {})
    conn = SimpleNamespace(id=court.lower(), authority=court, hosts={"example.org"},
                           fetch=lambda _, r=resp: r, parse=lambda _, p=parsed: p)
    svc._index_candidate_juris(conn, Candidate(court.lower(), official, "Decisão"))
    return svc.conn.execute("SELECT id FROM decision WHERE court=? AND official_id=?", (court, official)).fetchone()[0]


@pytest.fixture
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    with Verifica(tmp_path / "h") as s:
        yield s


def test_a1_so_ementa_nunca_sai_como_inteiro_teor_voto_ou_certidao(svc):
    did = _indexar(svc, "STJ", "100", text="", ementa="só a ementa existe")
    for parte in ("inteiro_teor", "voto", "certidao"):
        r = svc.obter_decisao(did, parte=parte)
        assert r["status"] == "parte_indisponivel"
        assert r["texto"] is None and r["parte_entregue"] is None and r["capture_id"] is None
        assert r["parte_solicitada"] == parte and r["partes_disponiveis"] == ["ementa"]
    ok = svc.obter_decisao(did)
    assert ok["status"] == "encontrada" and ok["parte_entregue"] == "ementa" == ok["parte_solicitada"]


def test_a1_parte_invalida_e_recusada(svc):
    did = _indexar(svc, "STJ", "101", text="", ementa="e")
    with pytest.raises(EntradaInvalida):
        svc.obter_decisao(did, parte="acordao")


def test_a2_identificador_oficial_repetido_exige_tribunal(svc):
    a = _indexar(svc, "STJ", "555", text="", ementa="decisão do STJ")
    b = _indexar(svc, "TCU", "555", text="", ementa="decisão do TCU", cls="Acórdão", organ="Plenário")
    amb = svc.obter_decisao("555")
    assert amb["status"] == "ambiguous" and "texto" not in amb
    assert {c["tribunal"] for c in amb["candidatos"]} == {"STJ", "TCU"}
    assert svc.obter_decisao("555", tribunal="TCU")["id"] == b
    assert svc.obter_decisao("555", tribunal="stj")["id"] == a
    # Id interno com tribunal divergente não é resolvido silenciosamente.
    assert svc.obter_decisao(a, tribunal="TCU")["status"] == "nao_encontrado_no_acervo"


def test_a3_ausencia_local_nao_e_inexistencia(svc):
    r = svc.obter_decisao("REsp 9.999.999")
    assert r["status"] == "nao_encontrado_no_acervo" and r["escopo"] == "acervo_local"
    assert r["status"] != "inexistente"


def test_a5_monocratica_declarada_nunca_vira_acordao(svc):
    # O conector STJ normaliza tipoDeDecisao para "monocratica"; até a 1.1.0 isso caía em "acordao".
    did = _indexar(svc, "STJ", "777", text="", ementa="decisão monocrática sobre acordo de acionistas",
                   kind="monocratica", cls="REsp", organ="Corte Especial")
    row = svc.conn.execute("SELECT kind, authority_label FROM decision WHERE id=?", (did,)).fetchone()
    assert row["kind"] == "decisao_monocratica" and row["authority_label"] == "E"
    itens = svc.pesquisar_jurisprudencia("acordo acionistas", tribunais=["stj"])["itens"]
    assert [i["autoridade"]["label"] for i in itens] == ["E"]
    assert svc.pesquisar_jurisprudencia("acordo acionistas", tribunais=["stj"], autoridade_min="C")["itens"] == []


def test_a12_comprimento_nao_promove_a_inteiro_teor(svc):
    longo = "andamento do processo. " * 80  # > 500 caracteres
    did = _indexar(svc, "STF", "RE-1", text=longo, ementa="título", profile="stf_decisoes")
    kinds = [r[0] for r in svc.conn.execute("SELECT kind FROM decision_document WHERE decision_id=?", (did,))]
    assert kinds == ["ementa"]
    assert svc.obter_decisao(did, parte="inteiro_teor")["status"] == "parte_indisponivel"
    did2 = _indexar(svc, "STF", "RE-2", text=longo, ementa="título", profile="stf_pdf")
    assert svc.obter_decisao(did2, parte="inteiro_teor")["parte_entregue"] == "inteiro_teor"


def test_migracao_sumula_gravada_como_inteiro_teor(svc):
    did = _indexar(svc, "STF", "SUM-1", text="", ementa="enunciado", cls="Súmula", organ="Plenário", kind="sumula")
    svc.conn.execute("INSERT INTO decision_document(id, decision_id, capture_id, kind, text, sha256, nivel_prova) "
                     "VALUES ('x', ?, NULL, 'inteiro_teor', 'enunciado longo', 'h', 'inteiro_teor_capturado')", (did,))
    assert derivados.corrigir_inteiro_teor_sumulas(svc.conn) == 1
    kinds = [r[0] for r in svc.conn.execute("SELECT kind FROM decision_document WHERE decision_id=?", (did,))]
    assert kinds == ["ementa"]
    assert derivados.corrigir_inteiro_teor_sumulas(svc.conn) == 0  # idempotente
