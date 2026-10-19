"""Achados do parecer do Codex sobre a 1.2.0: espécie em recaptura, semente STJ, histórico, TJDFT e tribunal explícito."""
import copy
import json
from pathlib import Path

from freoa_verifica.citation import extract
from freoa_verifica.connectors import tjdft
from freoa_verifica import derivados
from freoa_verifica.semente import SementeSync
from freoa_verifica.service import Verifica

from tests.test_120_contrato_evidencia import _indexar, svc  # noqa: F401 (fixture)

FIX = Path(__file__).parent / "fixtures" / "tjdft"


def test_recaptura_monocratica_corrige_especie_de_identidade_preexistente(svc):
    did = _indexar(svc, "STJ", "900", text="", ementa="primeira captura como acórdão", kind="acordao")
    assert svc.conn.execute("SELECT kind FROM decision WHERE id=?", (did,)).fetchone()[0] == "acordao"
    _indexar(svc, "STJ", "900", text="", ementa="a fonte declara monocrática", kind="monocratica")
    row = svc.conn.execute("SELECT kind, authority_label FROM decision WHERE id=?", (did,)).fetchone()
    assert tuple(row) == ("decisao_monocratica", "E")
    assert svc.pesquisar_jurisprudencia("fonte declara monocrática", tribunais=["stj"], autoridade_min="D")["itens"] == []
    derivados.reclassificar_autoridade(svc.conn)
    assert svc.conn.execute("SELECT authority_label FROM decision WHERE id=?", (did,)).fetchone()[0] == "E"


def test_falha_de_semente_preserva_historico_da_ultima_captura(tmp_path):
    with Verifica(tmp_path) as s:
        eng = SementeSync(s, rate_delay=0)
        eng.state.set("stj_resource", "resource:x:None", "capturado",
                      payload={"sha256": "abc", "ultima_captura_ok": "2026-10-01T00:00:00Z"})
        eng._mark_indisponivel("stj_resource", "resource:x:None", "transporte_Timeout")
        row = eng.state.get("stj_resource", "resource:x:None")
        assert row["status"] == "indisponivel"
        assert json.loads(row["payload_json"])["sha256"] == "abc"


def _mono():
    return copy.deepcopy(json.loads((FIX / "monocratica.json").read_text(encoding="utf-8"))["registros"][0])


def test_tjdft_variante_de_indisponibilidade_nao_e_inteiro_teor():
    rec = _mono()
    rec["inteiroTeor"] = f"Processo {rec['processo']}. " + "Inteiro teor não disponível no momento. " * 60
    assert tjdft.inteiro_teor_valido(rec) is None


def test_tjdft_texto_longo_com_processo_sem_fecho_decisorio_nao_e_inteiro_teor():
    rec = _mono()
    rec["inteiroTeor"] = f"Processo {rec['processo']}. " + "lorem ipsum dolor sit amet " * 80
    assert tjdft.inteiro_teor_valido(rec) is None


def test_tjdft_decisao_real_com_bem_indisponivel_continua_valida():
    rec = _mono()
    rec["inteiroTeor"] = rec["inteiroTeor"] + " Determino que o imóvel permaneça indisponível."
    assert tjdft.inteiro_teor_valido(rec)


def test_tribunal_explicito_prevalece_na_extracao():
    for texto in ("TJDFT AI 90387634", "AI 90387634/TJDFT", "AI 123.456 do TJDFT"):
        assert [c.decision.court for c in extract(texto) if c.decision] == ["tjdft"], texto
    # Classe exclusiva de tribunal superior não muda por tribunal de origem citado junto.
    assert [c.decision.court for c in extract("REsp 1.234.567 do TJRJ") if c.decision] == ["stj"]
    assert [(c.decision.court, c.decision.uf) for c in extract("REsp 1.234.567/DF") if c.decision] == [("stj", "DF")]
