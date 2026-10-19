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


# Auditoria comparativa (FREOA × JusRatio, 1.2.0): falhas de reconhecimento, não de acervo.
def test_numero_com_uf_acha_registro_sem_uf_e_declara(svc):
    _indexar(svc, "STJ", "1456264", text="", ementa="ementa do REsp", cls="REsp")
    svc.conn.execute("UPDATE decision SET number='2257277', uf=NULL WHERE official_id='1456264'")
    r = svc.pesquisar_jurisprudencia("REsp 2.257.277/PR")
    assert r["status"] == "encontrada" and len(r["itens"]) == 1
    assert r["evidencia"]["uf_citada_nao_conferida"] == "PR"
    svc.conn.execute("UPDATE decision SET uf='SP' WHERE official_id='1456264'")
    assert svc.pesquisar_jurisprudencia("REsp 2.257.277/PR")["status"] == "nao_confirmado_no_acervo"


def test_sumula_sem_acento_casa_classe_com_acento(svc):
    _indexar(svc, "STF", "Súmula 265", text="", ementa="Na apuração de haveres não prevalece o balanço...",
             cls="Súmula", organ="Plenário", kind="sumula")
    svc.conn.execute("UPDATE decision SET number='265' WHERE official_id='Súmula 265'")
    for q in ("Sumula 265 do STF", "Súmula 265 do STF"):
        assert svc.pesquisar_jurisprudencia(q)["status"] == "encontrada", q


def test_dispositivo_posposto_so_na_citacao_avulsa():
    from freoa_verifica.service import _dispositivo_posposto as d
    assert d("Resolução CVM 44/2021 art. 2º") == "Resolução CVM 44/2021, art. 2º"
    assert d("Lei 6.404/1976 art. 117, § 1º, a)") == "Lei 6.404/1976, art. 117, § 1º, a)"
    for intacto in ("Lei 6.404/1976 art. 117 do contrato", "Lei 6.404/1976 art. 117 e o contrato social",
                    "Resolução CVM 44/2021, art. 2º"):
        assert d(intacto) == intacto


# Parecer do Codex, rodada 3.
def test_reconstrucao_nao_promove_monocratica_legada(svc):
    did = _indexar(svc, "STJ", "901", text="", ementa="decisão individual", kind="monocratica")
    svc.conn.execute("UPDATE decision SET kind='acordao' WHERE id=?", (did,))  # kind legado
    derivados.reclassificar_autoridade(svc.conn)
    row = svc.conn.execute("SELECT kind, authority_label FROM decision WHERE id=?", (did,)).fetchone()
    assert tuple(row) == ("decisao_monocratica", "E")


def test_tjdft_fragmento_e_falha_documental_nao_sao_inteiro_teor():
    rec = _mono()
    frag = {**rec, "inteiroTeor": rec["inteiroTeor"][:1100]}
    assert tjdft.inteiro_teor_valido(frag) is None
    mut = {**rec, "inteiroTeor": f"Processo {rec['processo']} Gabinete do Desembargador "
           + "Não foi possível obter o inteiro teor. " * 55}
    assert tjdft.inteiro_teor_valido(mut) is None
    assert tjdft.inteiro_teor_valido(rec)


def test_tribunal_explicito_variantes():
    assert [c.decision.court for c in extract("AI 123.456 / TJDFT") if c.decision] == ["tjdft"]
    assert [c.decision.court for c in extract("HC 123.456 do tjsp") if c.decision] == ["tjsp"]
    assert [(c.decision.class_, c.decision.court) for c in extract("REsp 1.234.567/DF e RE 123.456 do STF")
            if c.decision] == [("REsp", "stj"), ("RE", "stf")]


def test_verificar_citacao_de_sumula_e_decisao_usa_o_acervo(svc):
    _indexar(svc, "STF", "Súmula 473", text="", ementa="A administração pode anular seus próprios atos...",
             cls="Súmula", organ="Plenário", kind="sumula")
    svc.conn.execute("UPDATE decision SET number='473' WHERE official_id='Súmula 473'")
    r = svc.verificar_citacao("Sumula 473 do STF")
    assert r["identity"]["status"] == "verified" and r["identity"]["evidence"][0]["capture_id"]
    assert r["text"]["status"] == "not_assessed"
    fora = svc.verificar_citacao("Súmula 999 do STJ")
    assert fora["identity"]["status"] == "unknown" and fora["identity"]["reason_code"] == "NAO_CONFIRMADO_NO_ACERVO"
    assert svc.verificar_citacao("REsp 9.999.999/SP")["identity"]["status"] != "verified"


# Parecer do Codex, rodada 4.
def test_numero_com_uf_nao_traz_registro_de_outra_uf_nem_empresta_evidencia(svc):
    pr = _indexar(svc, "STJ", "A-PR", text="", ementa="registro do Paraná", cls="REsp")
    sp = _indexar(svc, "STJ", "A-SP", text="", ementa="registro de São Paulo", cls="REsp")
    svc.conn.execute("UPDATE decision SET number='2257277', uf='PR' WHERE id=?", (pr,))
    svc.conn.execute("UPDATE decision SET number='2257277', uf='SP' WHERE id=?", (sp,))
    r = svc.pesquisar_jurisprudencia("REsp 2.257.277/PR")
    assert r["status"] == "encontrada" and [i["id"] for i in r["itens"]] == [pr]
    cap = svc.conn.execute("SELECT capture_id FROM decision_document WHERE decision_id=?", (pr,)).fetchone()[0]
    assert r["itens"][0]["evidencia"]["capture_id"] == cap


def test_identificador_igual_nao_supera_classe_divergente(svc):
    did = _indexar(svc, "STF", "265", text="", ementa="enunciado comum", cls="Súmula", organ="Plenário", kind="sumula")
    svc.conn.execute("UPDATE decision SET number='265' WHERE id=?", (did,))
    assert svc.pesquisar_jurisprudencia("Súmula Vinculante 265 do STF")["status"] == "nao_confirmado_no_acervo"
    assert svc.verificar_citacao("Súmula Vinculante 265")["identity"]["status"] != "verified"
    assert svc.pesquisar_jurisprudencia("Súmula 265 do STF")["status"] == "encontrada"


def test_cnj_fonte_com_falha_vira_indisponivel_estruturado(svc, monkeypatch):
    from freoa_verifica.connectors.base import Unavailable

    class Falha:
        def search(self, q, **kw):
            raise Unavailable("http_503")
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    svc._connectors["tjdft"] = Falha()
    r = svc.pesquisar_jurisprudencia("0713166-62.2018.8.07.0000")
    assert r["status"] == "nao_confirmado_no_acervo" and r["fontes"]["tjdft"]["status"] == "indisponivel"


def test_sigla_de_tribunal_na_consulta_vira_filtro(svc):
    _indexar(svc, "STJ", "S1", text="", ementa="exclusão de sócio de sociedade limitada por falta grave")
    _indexar(svc, "TCU", "T1", text="", ementa="Tribunal de Justiça do Distrito Federal e dos Territórios TJDFT ofício",
             cls="Acórdão", organ="Plenário")
    r = svc.pesquisar_jurisprudencia("exclusão de sócio STJ")
    assert r["filtro_tribunal_da_consulta"] == ["stj"] and {i["tribunal"] for i in r["itens"]} == {"STJ"}
    so_sigla = svc.pesquisar_jurisprudencia("STJ")
    assert so_sigla["status"] == "entrada_insuficiente" and so_sigla["itens"] == []
    # Dentro de aspas a sigla é parte da frase exata.
    _indexar(svc, "TCU", "T2", text="", ementa="responsabilidade civil STJ em parecer", cls="Acórdão", organ="Plenário")
    frase = svc.pesquisar_jurisprudencia('"responsabilidade civil STJ"')
    assert "filtro_tribunal_da_consulta" not in frase and any(i["tribunal"] == "TCU" for i in frase["itens"])
    aberta = svc.pesquisar_jurisprudencia('de "responsabilidade civil STJ')
    assert "filtro_tribunal_da_consulta" not in aberta
    assert svc.pesquisar_jurisprudencia("STJ,")["status"] == "entrada_insuficiente"


def test_idf_ordena_termo_raro_primeiro_na_complementacao(svc):
    for n in range(6):
        _indexar(svc, "STJ", f"C{n}", text="", ementa=f"apuração de haveres sócio excluído caso {n}")
    _indexar(svc, "STJ", "RARO", text="", ementa="legitimidade do sócio excluído para apuração")
    itens = svc.pesquisar_jurisprudencia("legitimidade socio excluido apuracao haveres", limite=3)["itens"]
    assert itens[0]["classe_numero"].endswith("RARO")


def test_resultado_sem_ementa_mostra_trecho_pertinente_rotulado(svc):
    from freoa_verifica.service import _trecho_pertinente
    corpo = "Poder Judiciário cabeçalho. " * 30 + "Trata-se de exclusão de sócio de sociedade limitada."
    trecho, cortado = _trecho_pertinente(corpo, "exclusao de socio", 200)
    assert "exclusão de sócio" in trecho and cortado


def test_ementa_que_cobre_a_consulta_vem_antes_de_termos_espalhados(svc):
    longo = ("Relatório. A sociedade transformou-se. " * 40 + " O sócio alegou exclusão indevida do foro. "
             + "limitada a competência. " * 20)
    _indexar(svc, "TJDFT", "MONO", text=longo, ementa="", profile="tjdft_inteiro_teor", kind="monocratica",
             metadata={"documento": "inteiro_teor"})
    _indexar(svc, "TJDFT", "ACORD", text="", ementa="Exclusão de sócio. Sociedade limitada. Falta grave.")
    itens = svc.pesquisar_jurisprudencia("exclusao de socio sociedade limitada", tribunais=["tjdft"])["itens"]
    assert itens[0]["classe_numero"].endswith("ACORD")
