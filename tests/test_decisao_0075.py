"""Testes de regressão da Decisão 0075 (IL.0: estado com data e fronteira com o FREOA)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from freoa_verifica import situacao
from freoa_verifica.aliases import WorkKey
from freoa_verifica.parsers.cvm_docx import parse_cvm_docx
from freoa_verifica.parsers.model import Annotation, Provision, Redaction
from freoa_verifica.service import Verifica
from freoa_verifica.temporal import select as temporal_select
from tests.fixture_util import load_fixture


@pytest.fixture
def svc_160(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    s = Verifica(home=tmp_path)
    body_160 = load_fixture("cvm_resol_160_consolid_docx")
    doc_160 = parse_cvm_docx(body_160)
    rw = s.indexar_obra(
        source_id="cvm_normas",
        work_key=WorkKey("cvm", "resolucao", "160", 2022),
        document=doc_160,
        body=body_160,
        url="https://conteudo.cvm.gov.br/legislacao/resolucoes/resol160.docx",
        fetched_at="2026-10-18T00:00:00Z",
        work_date="2022-07-13",
        label="Resolução CVM nº 160/2022",
    )
    # Situação inicial vigente declarada autenticada
    situacao.gravar(
        s.conn,
        situacao.WorkStatus(
            rw.work_id,
            "vigente_declarada",
            captura_id=rw.capture_id,
            sha256=rw.sha256,
            lido_em=datetime.now(timezone.utc).isoformat(),
        ),
    )
    yield s, rw, doc_160
    s.close()


def test_0075_regressao_a_texto_riscado_data_historica(svc_160):
    """(a) texto riscado em data histórica dá unknown/sem_fundamento_do_periodo e coincide com riscada: true."""
    svc, _, doc = svc_160
    prov = doc.provision("art2.inc16")
    struck = next(r for r in prov.redactions if r.struck)

    res = svc.verificar_citacao("art. 2º, XVI da Resolução CVM nº 160/2022", trecho=struck.text, data="2022-08-01")
    assert res["identity"]["status"] == "verified"
    assert res["text"]["status"] == "unknown"
    assert res["text"]["reason_code"] == "sem_fundamento_do_periodo"
    assert res["temporal"]["status"] == "unknown"
    assert res["temporal"]["reason_code"] == "sem_fundamento_do_periodo"
    assert res["fundamento_temporal"] is None
    corr = res["correspondencia_textual"]
    assert corr is not None
    assert corr["resultado"] == "coincide"
    assert corr["riscada"] is True
    assert corr["origem"] == "rasura_compilada"


def test_0075_regressao_b_texto_atual_data_historica(svc_160):
    """(b) texto atual em data histórica, idem com origem: redacao_atual."""
    svc, _, doc = svc_160
    prov = doc.provision("art1")
    current = next(r for r in prov.redactions if not r.struck)

    res = svc.verificar_citacao("art. 1º da Resolução CVM nº 160/2022", trecho=current.text, data="2023-01-01")
    assert res["identity"]["status"] == "verified"
    assert res["text"]["status"] == "unknown"
    assert res["text"]["reason_code"] == "sem_fundamento_do_periodo"
    assert res["temporal"]["status"] == "unknown"
    assert res["temporal"]["reason_code"] == "sem_fundamento_do_periodo"
    assert res["fundamento_temporal"] is None
    corr = res["correspondencia_textual"]
    assert corr is not None
    assert corr["resultado"] == "coincide"
    assert corr["riscada"] is False
    assert corr["origem"] == "redacao_atual"


def test_0075_regressao_c_trecho_de_outra_redacao_data_historica(svc_160):
    """(c) trecho de outra redação dá unknown e correspondencia que aponta a redação coincidente."""
    svc, _, doc = svc_160
    prov = doc.provision("art2.inc16")
    current = next(r for r in prov.redactions if not r.struck)

    # Em 2022-08-01 vigorava a redação original (r0), mas o trecho passado é da redação posterior (r1)
    res = svc.verificar_citacao("art. 2º, XVI da Resolução CVM nº 160/2022", trecho=current.text, data="2022-08-01")
    assert res["text"]["status"] == "unknown"
    assert res["text"]["reason_code"] == "sem_fundamento_do_periodo"
    corr = res["correspondencia_textual"]
    assert corr is not None
    assert corr["resultado"] == "coincide"
    assert corr["redaction_id"] == "r1"
    assert corr["riscada"] is False
    assert corr["origem"] == "redacao_atual"


def test_0075_regressao_d_data_trocada_e_caractere_alterado_nunca_verified(svc_160):
    """(d) data trocada e caractere alterado nunca dão verified."""
    svc, _, doc = svc_160
    prov = doc.provision("art2.inc16")
    current = next(r for r in prov.redactions if not r.struck)
    adulterado = current.text + " modificado"

    res = svc.verificar_citacao("art. 2º, XVI da Resolução CVM nº 160/2022", trecho=adulterado, data="2023-01-01")
    assert res["text"]["status"] != "verified"
    assert res["temporal"]["status"] != "verified"
    assert res["text"]["status"] == "unknown"
    assert res["text"]["reason_code"] == "sem_fundamento_do_periodo"
    assert res["correspondencia_textual"]["resultado"] in ("parcial", "diverge")


def test_0075_regressao_e_consulta_corrente_inalterada(svc_160):
    """(e) consulta corrente inalterada (vigente_na_fonte)."""
    svc, _, doc = svc_160
    prov = doc.provision("art1")
    current = next(r for r in prov.redactions if not r.struck)

    res = svc.verificar_citacao("art. 1º da Resolução CVM nº 160/2022", trecho=current.text)
    assert res["temporal"]["status"] == "vigente_na_fonte"
    assert res["text"]["status"] == "verified"
    assert res["correspondencia_textual"] is None
    assert res["fundamento_temporal"] is None


def test_0075_regressao_f_nao_existia():
    """(f) nao_existia inalterado: D anterior à obra e D anterior à inclusão sem juízo pendente."""
    # 1. D anterior à data da obra
    p1 = Provision(path="art1", label="Art. 1º", scope="norma", redactions=[Redaction(order=0, text="Texto original", struck=False, annotations=[])])
    res_antes_obra = temporal_select(p1, "1970-01-01", work_date="1976-12-15")
    assert res_antes_obra.status == "nao_existia"

    # 2. D anterior à inclusão comprovada sem juízo pendente
    ann_inc = Annotation(kind="incluido", raw="Incluído pela Lei 10.000", act_ref="Lei 10.000", act_date="2000-01-01")
    p2 = Provision(path="art1-A", label="Art. 1º-A", scope="norma", redactions=[Redaction(order=0, text="Texto novo", struck=False, annotations=[ann_inc])])
    res_antes_inc = temporal_select(p2, "1995-01-01", work_date="1976-12-15")
    assert res_antes_inc.status == "nao_existia"

    # 3. D anterior à inclusão COM juízo pendente -> unknown com sem_fundamento_do_periodo
    ann_vig = Annotation(kind="vigencia", raw="Vigência a definir")
    p3 = Provision(path="art1-B", label="Art. 1º-B", scope="norma", redactions=[Redaction(order=0, text="Texto c pendencia", struck=False, annotations=[ann_inc, ann_vig])])
    res_pendente = temporal_select(p3, "1995-01-01", work_date="1976-12-15")
    assert res_pendente.status == "unknown"
    assert res_pendente.reason == "sem_fundamento_do_periodo"
    assert "sem_fundamento_do_periodo" in res_pendente.flags


def test_0075_regressao_g_revogado_historico_vira_unknown():
    """(g) revogado histórico vira unknown com flag revogacao_anotada, revogado corrente continua revogado."""
    ann_rev = Annotation(kind="revogado", raw="Revogado pela Lei 9.000", act_ref="Lei 9.000", act_date="1995-01-01")
    prov = Provision(
        path="art5",
        label="Art. 5º",
        scope="norma",
        redactions=[
            Redaction(order=0, text="Texto", struck=True, annotations=[ann_rev]),
        ],
    )
    # Consulta histórica após revogação: unknown com flags
    res_hist = temporal_select(prov, "2000-01-01", work_date="1980-01-01")
    assert res_hist.status == "unknown"
    assert res_hist.reason == "sem_fundamento_do_periodo"
    assert "sem_fundamento_do_periodo" in res_hist.flags
    assert "revogacao_anotada" in res_hist.flags

    # Consulta corrente (sem data): continua revogado
    res_corr = temporal_select(prov, None, work_date="1980-01-01")
    assert res_corr.status == "revogado"


def test_0075_fundamento_temporal_permite_verified():
    """select com fundamento_temporal não nulo permite verified em data histórica."""
    prov = Provision(
        path="art1",
        label="Art. 1º",
        scope="norma",
        redactions=[
            Redaction(order=0, text="Texto original", struck=False, annotations=[]),
        ],
    )
    # Sem fundamento: unknown
    res_sem = temporal_select(prov, "2000-01-01", work_date="1990-01-01")
    assert res_sem.status == "unknown"
    assert res_sem.reason == "sem_fundamento_do_periodo"

    # Com fundamento fictício: verified
    fundamento = {"tipo": "versao_oficial_na_data", "capture_id": "c1", "url": "https://example.org", "sha256": "abc", "data": "2000-01-01"}
    res_com = temporal_select(prov, "2000-01-01", work_date="1990-01-01", fundamento_temporal=fundamento)
    assert res_com.status == "verified"


def test_0075_obter_dispositivo_data_historica(svc_160):
    """obter_dispositivo com data histórica: vigencia corrigida e fundamento_temporal/correspondencia_textual no topo."""
    svc, _, _ = svc_160
    out = svc.obter_dispositivo(citacao="art. 2º, XVI da Resolução CVM nº 160/2022", data="2022-08-01")
    assert out["status"] == "encontrada"
    assert out["fundamento_temporal"] is None
    assert out["correspondencia_textual"] is None
    assert out["vigencia"]["status"] == "unknown"
    assert out["vigencia"]["reason_code"] == "sem_fundamento_do_periodo"


def test_0075_historico_dispositivo(svc_160):
    """historico_dispositivo: cada item de linha_do_tempo ganha limites_inferidos e fundamento_temporal."""
    svc, _, _ = svc_160
    out = svc.historico_dispositivo("art. 2º, XVI da Resolução CVM nº 160/2022")
    assert out["status"] == "encontrada"
    assert len(out["linha_do_tempo"]) >= 2
    for item in out["linha_do_tempo"]:
        assert "limites_inferidos" in item
        assert isinstance(item["limites_inferidos"], bool)
        assert "fundamento_temporal" in item
        assert item["fundamento_temporal"] is None


def test_0075_verificar_texto_embutida(svc_160):
    """verificar_texto em data histórica propaga a correção para a verificação embutida."""
    svc, _, doc = svc_160
    prov = doc.provision("art2.inc16")
    current = next(r for r in prov.redactions if not r.struck)

    texto = f'Conforme o art. 2º, XVI da RCVM 160: "{current.text}".'
    out = svc.verificar_texto(texto, data="2023-01-01")
    assert out["total"] == 1
    c = out["citacoes"][0]
    assert c["identity"]["status"] == "verified"
    assert c["text"]["status"] == "unknown"
    assert c["text"]["reason_code"] == "sem_fundamento_do_periodo"
    v = c["verificacao"]
    assert v is not None
    assert v["fundamento_temporal"] is None
    assert v["correspondencia_textual"]["resultado"] == "coincide"


def test_0075_situacao_revogada_nao_converte_historico(svc_160):
    """Situação de obra CVM gravada como revogada não converte sem_fundamento_do_periodo em consulta histórica."""
    svc, rw, doc = svc_160
    prov = doc.provision("art1")
    current = next(r for r in prov.redactions if not r.struck)

    # Gravar situação revogada na obra
    ws = situacao.WorkStatus(
        work_id=rw.work_id,
        situacao="revogada",
        texto_oficial="Revogada por...",
        ato_revogador="Resolução CVM 200",
        data_efeito="2022-12-01",
        captura_id=rw.capture_id,
        sha256=rw.sha256,
        lido_em="2026-10-18T00:00:00Z",
    )
    situacao.gravar(svc.conn, ws)

    # Consulta histórica: continua unknown / sem_fundamento_do_periodo
    out_hist = svc.verificar_citacao("art. 1º da Resolução CVM nº 160/2022", trecho=current.text, data="2023-01-01")
    assert out_hist["temporal"]["status"] == "unknown"
    assert out_hist["temporal"]["reason_code"] == "sem_fundamento_do_periodo"
    assert out_hist["text"]["status"] == "unknown"
    assert out_hist["text"]["reason_code"] == "sem_fundamento_do_periodo"

    # Consulta corrente: situação da obra revogada converte em divergent
    out_corr = svc.verificar_citacao("art. 1º da Resolução CVM nº 160/2022")
    assert out_corr["temporal"]["status"] == "divergent"
    assert out_corr["temporal"]["reason_code"] == "OBRA_REVOGADA_NA_FONTE"


def test_0075_regressao_auditor_r1_art2_inc16_vacatio_situacao_revogada(svc_160):
    """B.1 (Auditor Codex r1 ALTO): redação histórica selecionada cujo estado intermediário
    já é unknown (ex.: vacatio) não pode ser convertida pela situação gravada da obra em negativa.
    Reprodução exata: cvm_resol_160_consolid_docx, art. 2º, XVI, data 2023-01-01, obra revogada com data_efeito=2022-12-01.
    Testado nos 3 caminhos: verificar_citacao, obter_dispositivo e verificar_texto.
    """
    svc, rw, doc = svc_160
    prov = doc.provision("art2.inc16")
    current = next(r for r in prov.redactions if not r.struck)

    ws = situacao.WorkStatus(
        work_id=rw.work_id,
        situacao="revogada",
        texto_oficial="Revogada por Resolução CVM 200",
        ato_revogador="Resolução CVM 200",
        data_efeito="2022-12-01",
        captura_id=rw.capture_id,
        sha256=rw.sha256,
        lido_em="2026-10-18T00:00:00Z",
    )
    situacao.gravar(svc.conn, ws)

    # 1. Caminho verificar_citacao
    res_cit = svc.verificar_citacao(
        "art. 2º, XVI da Resolução CVM nº 160/2022",
        trecho=current.text,
        data="2023-01-01",
    )
    assert res_cit["temporal"]["status"] == "unknown"
    assert res_cit["temporal"]["reason_code"] == "sem_fundamento_do_periodo"
    assert res_cit["fundamento_temporal"] is None

    # 2. Caminho obter_dispositivo
    res_disp = svc.obter_dispositivo(
        citacao="art. 2º, XVI da Resolução CVM nº 160/2022",
        data="2023-01-01",
    )
    assert res_disp["status"] == "encontrada"
    assert res_disp["vigencia"]["status"] == "unknown"
    assert res_disp["vigencia"]["reason_code"] == "sem_fundamento_do_periodo"
    assert res_disp["fundamento_temporal"] is None

    # 3. Caminho verificar_texto
    texto = f'Conforme o art. 2º, XVI da RCVM 160: "{current.text}".'
    res_txt = svc.verificar_texto(texto, data="2023-01-01")
    assert res_txt["total"] == 1
    cit_emb = res_txt["citacoes"][0]
    assert cit_emb["text"]["status"] == "unknown"
    assert cit_emb["text"]["reason_code"] == "sem_fundamento_do_periodo"
    assert cit_emb["verificacao"]["temporal"]["status"] == "unknown"
    assert cit_emb["verificacao"]["temporal"]["reason_code"] == "sem_fundamento_do_periodo"
    assert cit_emb["verificacao"]["fundamento_temporal"] is None


def test_0075_evidencia_eixos_verificar_citacao(svc_160):
    """3.2: Eixos da evidência em verificar_citacao."""
    svc, rw, doc = svc_160
    prov = doc.provision("art1")
    current = next(r for r in prov.redactions if not r.struck)

    res = svc.verificar_citacao("art. 1º da Resolução CVM nº 160/2022", trecho=current.text)
    ev = res["identity"]["evidence"][0]
    assert ev["captured_at"] == rw.fetched_at
    assert ev["acervo_ate"] is None  # CVM é fonte viva
    assert ev["source_kind"] == "resolucao_cvm"
    assert ev["natureza_texto"] == "consolidacao_oficial"
    assert ev["procedencia"] == "nao_identificado"
    assert ev["esfera"] == "federal"


def test_0075_evidencia_eixos_obter_dispositivo(svc_160):
    """3.2: Eixos da evidência em obter_dispositivo."""
    svc, rw, _ = svc_160
    res = svc.obter_dispositivo(citacao="art. 1º da Resolução CVM nº 160/2022")
    assert res["status"] == "encontrada"
    ev = res["evidencia"]
    assert ev["captured_at"] == rw.fetched_at
    assert ev["acervo_ate"] is None
    assert ev["source_kind"] == "resolucao_cvm"
    assert ev["natureza_texto"] == "consolidacao_oficial"
    assert ev["procedencia"] == "nao_identificado"
    assert ev["esfera"] == "federal"


def test_0075_regressao_auditor_r1_acervo_ate_duas_obras_capturas_distintas(tmp_path, monkeypatch):
    """B.4 (Auditor Codex r1 MÉDIO): acervo_ate congelado no ResolvedWork fica desatualizado;
    calcule ao emitir a resposta ou invalide nas obras carregadas.
    Regressão com duas obras e capturas em datas distintas.
    """
    monkeypatch.setenv("FV_OFFLINE", "1")
    from freoa_verifica.parsers.model import ParsedDocument, Provision, Redaction

    with Verifica(home=tmp_path) as svc:
        p1 = Provision("art1", "Art. 1º", "", [Redaction("Texto 1", False, 0)])
        doc1 = ParsedDocument(profile="planalto", parser_version="1", title="LEI Nº 6.404, DE 15 DE DEZEMBRO DE 1976.", ementa=None, text="Texto 1", provisions=[p1])
        svc.indexar_obra(
            source_id="planalto",
            work_key=WorkKey("federal", "lei", "6404", 1976),
            document=doc1,
            body=b"<html>Lei 6404</html>",
            url="https://www.planalto.gov.br/lei6404.htm",
            fetched_at="2026-10-18T12:00:00Z",
            work_date="1976-12-15",
            label="Lei nº 6.404/1976",
            content_type="text/html; charset=utf-8",
        )
        # Primeira obra carregada: corte é 2026-10-18
        res1_cit = svc.verificar_citacao("art. 1º da Lei 6.404/76", trecho="Texto 1")
        assert res1_cit["identity"]["evidence"][0]["acervo_ate"] == "2026-10-18"
        res1_disp = svc.obter_dispositivo(citacao="art. 1º da Lei 6.404/76")
        assert res1_disp["evidencia"]["acervo_ate"] == "2026-10-18"

        # Segunda obra com captura mais recente (2026-10-19)
        p2 = Provision("art1", "Art. 1º", "", [Redaction("Texto 2", False, 0)])
        doc2 = ParsedDocument(profile="planalto", parser_version="1", title="LEI Nº 10.406, DE 10 DE JANEIRO DE 2002.", ementa=None, text="Texto 2", provisions=[p2])
        svc.indexar_obra(
            source_id="planalto",
            work_key=WorkKey("federal", "lei", "10406", 2002),
            document=doc2,
            body=b"<html>Lei 10406</html>",
            url="https://www.planalto.gov.br/lei10406.htm",
            fetched_at="2026-10-19T15:00:00Z",
            work_date="2002-01-10",
            label="Lei nº 10.406/2002",
            content_type="text/html; charset=utf-8",
        )

        # Agora o corte agregado da primeira obra (que já estava em cache) deve refletir 2026-10-19
        res1_atualizada_cit = svc.verificar_citacao("art. 1º da Lei 6.404/76", trecho="Texto 1")
        assert res1_atualizada_cit["identity"]["evidence"][0]["acervo_ate"] == "2026-10-19"
        res1_atualizada_disp = svc.obter_dispositivo(citacao="art. 1º da Lei 6.404/76")
        assert res1_atualizada_disp["evidencia"]["acervo_ate"] == "2026-10-19"

        # E a segunda obra também
        res2_disp = svc.obter_dispositivo(citacao="art. 1º da Lei 10.406/2002")
        assert res2_disp["evidencia"]["acervo_ate"] == "2026-10-19"


def test_0075_evidencia_planalto_acervo_ate(tmp_path, monkeypatch):
    """3.2: Planalto calcula acervo_ate da maior fetched_at do acervo instalado."""
    monkeypatch.setenv("FV_OFFLINE", "1")
    s = Verifica(home=tmp_path)
    body_lsa = load_fixture("planalto_lei_6404_1976")
    from freoa_verifica.parsers.planalto import parse_planalto
    doc_lsa = parse_planalto(body_lsa)
    s.indexar_obra(
        source_id="planalto",
        work_key=WorkKey("federal", "lei", "6404", 1976),
        document=doc_lsa,
        body=body_lsa,
        url="http://www.planalto.gov.br/ccivil_03/leis/l6404consol.htm",
        fetched_at="2026-10-18T12:00:00Z",
        work_date="1976-12-15",
        label="Lei nº 6.404/1976",
        content_type="text/html; charset=windows-1252",
    )
    res = s.obter_dispositivo(citacao="art. 1º da Lei 6404/1976")
    assert res["status"] == "encontrada"
    ev = res["evidencia"]
    assert ev["captured_at"] == "2026-10-18T12:00:00Z"
    assert ev["acervo_ate"] == "2026-10-18"
    assert ev["source_kind"] == "lei"
    assert ev["natureza_texto"] == "consolidacao_oficial"
    assert ev["esfera"] == "federal"
    s.close()


def test_0075_listar_fontes_qualificacao_e_avisos(tmp_path):
    """3.3: qualificacao e avisos_incidente em listar_fontes."""
    s = Verifica(home=tmp_path)
    lf = s.listar_fontes()
    assert "qualificacao" in lf
    assert "avisos_incidente" in lf
    assert isinstance(lf["qualificacao"], list)
    assert len(lf["qualificacao"]) == 6
    for q in lf["qualificacao"]:
        assert q["porta"] in ("L", "A", "stj_1_4_0")
        assert q["estado"] == "nao_apurada"
        assert q["versao"] is None
        assert q["manifesto"] is None
        assert isinstance(q["rotulo"], str) and q["rotulo"]
    assert lf["avisos_incidente"] == []
    s.close()


def test_0075_listar_fontes_avisos_incidente_home_validacao(tmp_path):
    """3.3: Leitura e validação estrita de <home>/avisos_incidente.json."""
    import json
    from pathlib import Path

    home_avisos = [
        {
            "id": "AV-001",
            "data": "2026-11-03",
            "versoes_afetadas": ["1.4.0a1"],
            "acao": "correcao",
            "descricao": "Correção de estado temporal",
            "referencia": "decisao 0075",
        },
        {
            "id": "AV-INVALIDO",
            # falta data, acao errada
            "acao": "invalida",
        },
    ]
    (Path(tmp_path) / "avisos_incidente.json").write_text(json.dumps(home_avisos), encoding="utf-8")

    s = Verifica(home=tmp_path)
    lf = s.listar_fontes()
    avisos = lf["avisos_incidente"]
    assert len(avisos) == 1
    assert avisos[0]["id"] == "AV-001"
    s.close()


def test_0075_obter_registro_inexistente(svc_160):
    """3.4: obter_registro inexistente."""
    svc, _, _ = svc_160
    reg = svc.obter_registro("01M6H1Y11Y99K728HPNASE0000")
    assert reg == {"status": "inexistente", "run_id": "01M6H1Y11Y99K728HPNASE0000"}


def test_0075_obter_registro_completo(tmp_path, monkeypatch):
    """3.4: obter_registro sob política completo."""
    monkeypatch.setenv("FV_OFFLINE", "1")
    monkeypatch.setenv("FV_REGISTRO", "completo")
    s = Verifica(home=tmp_path)
    body_160 = load_fixture("cvm_resol_160_consolid_docx")
    doc_160 = parse_cvm_docx(body_160)
    rw = s.indexar_obra(
        source_id="cvm_normas",
        work_key=WorkKey("cvm", "resolucao", "160", 2022),
        document=doc_160,
        body=body_160,
        url="https://conteudo.cvm.gov.br/legislacao/resolucoes/resol160.docx",
        fetched_at="2026-10-18T00:00:00Z",
        work_date="2022-07-13",
        label="Resolução CVM nº 160/2022",
    )
    situacao.gravar(
        s.conn,
        situacao.WorkStatus(
            rw.work_id,
            "vigente_declarada",
            captura_id=rw.capture_id,
            sha256=rw.sha256,
            lido_em="2026-10-18T00:00:00Z",
        ),
    )
    prov = doc_160.provision("art1")
    current = next(r for r in prov.redactions if not r.struck)
    res = s.verificar_citacao("art. 1º da Resolução CVM nº 160/2022", trecho=current.text)
    run_id = res["run_id"]
    assert run_id is not None

    reg = s.obter_registro(run_id)
    assert reg["status"] == "encontrada"
    assert reg["run_id"] == run_id
    assert reg["ferramenta"] == "verificar_citacao"
    assert reg["politica"] == "completo"
    assert reg["integridade"]["confere"] is True
    assert isinstance(reg["evidencias"], list)
    assert len(reg["evidencias"]) > 0
    assert reg["evidencias"][0]["capture_id"] == rw.capture_id
    assert reg["confere_evidencias"] is None
    assert reg["confere_fundamento"] is None
    s.close()


def test_0075_obter_registro_sem_conteudo_com_conferencia(svc_160):
    """3.4: obter_registro sob política sem_conteudo com conferência de evidências."""
    svc, rw, doc = svc_160
    prov = doc.provision("art1")
    current = next(r for r in prov.redactions if not r.struck)

    res = svc.verificar_citacao("art. 1º da Resolução CVM nº 160/2022", trecho=current.text)
    run_id = res["run_id"]
    assert run_id is not None

    # Sem apresentação de evidências
    reg = svc.obter_registro(run_id)
    assert reg["status"] == "encontrada"
    assert reg["politica"] == "sem_conteudo"
    assert reg["evidencias"] is None
    assert reg["fundamento_temporal"] is None
    assert reg["integridade"]["confere"] is True
    assert reg["confere_evidencias"] is None
    assert reg["confere_fundamento"] is None

    # Com apresentação de evidência correta e falsa
    ev_correta = {"capture_id": rw.capture_id, "sha256": rw.sha256, "url": rw.url}
    ev_falsa = {"capture_id": rw.capture_id, "sha256": "1" * 64, "url": rw.url}
    reg_conf = svc.obter_registro(run_id, evidencias=[ev_correta, ev_falsa])
    assert reg_conf["confere_evidencias"] == [
        {"capture_id": rw.capture_id, "confere": True},
        {"capture_id": rw.capture_id, "confere": False},
    ]


def test_0075_regressao_auditor_r1_evidencias_incompletas_e_vazias_rejeitadas(svc_160):
    """B.3 (Auditor Codex r1 MÉDIO): confere_evidencias não pode dar true para apresentação vazia
    ou incompleta, e operações sem captura não criam compromisso.
    """
    svc, rw, _ = svc_160
    res = svc.verificar_citacao("art. 1º da Resolução CVM nº 160/2022")
    run_id = res["run_id"]

    # 1. Apresentação vazia / incompleta deve dar confere: False
    conferencia = svc.obter_registro(run_id, evidencias=[{}, {"capture_id": None}, {"capture_id": "c1"}])
    assert conferencia["status"] == "encontrada"
    assert conferencia["confere_evidencias"] == [
        {"capture_id": None, "confere": False},
        {"capture_id": None, "confere": False},
        {"capture_id": "c1", "confere": False},
    ]

    # 2. Operação que não teve captura (sem capture_id, sha256 ou url) não grava compromissos de captura
    from freoa_verifica.verify import persistir_resultado

    run_id_unav = persistir_resultado(
        svc.conn,
        "citacao inexistente 99999",
        None,
        None,
        "literal",
        {"identity": {"status": "unavailable", "evidence": [{"source_id": "cvm", "tentativa": True}]}},
    )
    conf_unav = svc.obter_registro(run_id_unav, evidencias=[{}, {"capture_id": None}])
    assert conf_unav["confere_evidencias"] == [
        {"capture_id": None, "confere": False},
        {"capture_id": None, "confere": False},
    ]


def test_0075_obter_registro_integridade_adulterada(svc_160):
    """3.4: adulteração de registro quebra MAC de integridade."""
    svc, rw, doc = svc_160
    prov = doc.provision("art1")
    current = next(r for r in prov.redactions if not r.struck)

    res = svc.verificar_citacao("art. 1º da Resolução CVM nº 160/2022", trecho=current.text)
    run_id = res["run_id"]

    # Desativa temporariamente o trigger imutavel para simular adulteração externa
    trigs = svc.conn.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger' AND tbl_name='run'").fetchall()
    for name, _ in trigs:
        svc.conn.execute(f'DROP TRIGGER "{name}"')

    svc.conn.execute("UPDATE run SET result_json='{}' WHERE id=?", (run_id,))
    svc.conn.commit()

    for _, sql in trigs:
        svc.conn.execute(sql)
    svc.conn.commit()

    reg = svc.obter_registro(run_id)
    assert reg["status"] == "encontrada"
    assert reg["integridade"]["confere"] is False


def test_0075_obter_registro_legado_sem_mac(tmp_path):
    """3.4: registro legado sem registro_mac dá integridade.confere = null."""
    s = Verifica(home=tmp_path)
    run_id = "01LEGADO000000000000000000"
    s.conn.execute(
        "INSERT INTO run (id, request_hash, request_json, policy_version, created_at, result_json) "
        "VALUES (?,?,?,?,?,?)",
        (run_id, "hash", '{"citacao": "art 1"}', "verify-r5-1", "2026-01-01T00:00:00Z", '{"identity": {"status": "verified"}}'),
    )
    s.conn.commit()

    reg = s.obter_registro(run_id)
    assert reg["status"] == "encontrada"
    assert reg["integridade"]["confere"] is None
    assert reg["ferramenta"] == "verificar_citacao"
    s.close()


def test_0075_rest_e_mcp_obter_registro(svc_160):
    """3.4: obter_registro em REST (GET e POST conferencia) e MCP."""
    import asyncio
    import json
    from starlette.testclient import TestClient
    from freoa_verifica import mcp_server as ms
    from freoa_verifica.rest import create_app

    svc, rw, doc = svc_160
    prov = doc.provision("art1")
    current = next(r for r in prov.redactions if not r.struck)
    res = svc.verificar_citacao("art. 1º da Resolução CVM nº 160/2022", trecho=current.text)
    run_id = res["run_id"]
    ev = {"capture_id": rw.capture_id, "sha256": rw.sha256, "url": rw.url}

    # 1. REST GET /v1/registros/{run_id}
    app = create_app(home=str(svc.home), token="t")
    with TestClient(app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1") as c:
        r_get = c.get(f"/v1/registros/{run_id}", headers={"Authorization": "Bearer t"})
        assert r_get.status_code == 200
        data_get = r_get.json()
        assert data_get["status"] == "encontrada"
        assert data_get["run_id"] == run_id

        # 2. REST POST /v1/registros/{run_id}/conferencia
        r_post = c.post(
            f"/v1/registros/{run_id}/conferencia",
            json={"evidencias": [ev]},
            headers={"Authorization": "Bearer t"},
        )
        assert r_post.status_code == 200
        data_post = r_post.json()
        assert data_post["confere_evidencias"] == [{"capture_id": rw.capture_id, "confere": True}]

    # 3. MCP tool obter_registro
    server = ms.create_mcp(home=str(svc.home))
    try:
        mcp_res = asyncio.run(server.call_tool("obter_registro", {"run_id": run_id, "evidencias": [ev]}))
        assert not mcp_res.is_error
        text_content = mcp_res.content[0].text if hasattr(mcp_res.content[0], "text") else mcp_res.content[0]
        payload = json.loads(text_content)
        assert payload["status"] == "encontrada"
        assert payload["confere_evidencias"] == [{"capture_id": rw.capture_id, "confere": True}]
    finally:
        from pathlib import Path
        ms._servicos.pop(str(Path(svc.home).resolve()), None)


def test_0075_mcp_e_rest_obter_registro_validacao_estrita(svc_160):
    """Auditor r2 MÉDIO: validação estrita (Pydantic) de evidencias e fundamento_temporal.
    O exemplo do parecer ([{"capture_id": 42, "sha256": [], "url": {"x": "y"}, "extra": "accepted"}])
    e extras são recusados; a forma válida continua aceita em MCP e REST.
    """
    import asyncio
    from starlette.testclient import TestClient
    from freoa_verifica import mcp_server as ms
    from freoa_verifica.rest import create_app

    svc, rw, doc = svc_160
    prov = doc.provision("art1")
    current = next(r for r in prov.redactions if not r.struck)
    res = svc.verificar_citacao("art. 1º da Resolução CVM nº 160/2022", trecho=current.text)
    run_id = res["run_id"]

    ev_invalida_parecer = [
        {"capture_id": 42, "sha256": [], "url": {"x": "y"}, "extra": "accepted"}
    ]
    ev_valida = [
        {"capture_id": rw.capture_id, "sha256": rw.sha256, "url": rw.url}
    ]
    ft_invalido_extra = {
        "tipo": "versao_oficial_na_data",
        "capture_id": rw.capture_id,
        "url": rw.url,
        "sha256": rw.sha256,
        "data": "2022-08-01",
        "extra": "proibido",
    }
    ft_valido = {
        "tipo": "versao_oficial_na_data",
        "capture_id": rw.capture_id,
        "url": rw.url,
        "sha256": rw.sha256,
        "data": "2022-08-01",
    }

    # REST
    app = create_app(home=str(svc.home), token="t")
    with TestClient(app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1") as c:
        # Exemplo do parecer recusado com 422
        r_inv1 = c.post(
            f"/v1/registros/{run_id}/conferencia",
            json={"evidencias": ev_invalida_parecer},
            headers={"Authorization": "Bearer t"},
        )
        assert r_inv1.status_code == 422

        # Extra em fundamento_temporal recusado com 422
        r_inv2 = c.post(
            f"/v1/registros/{run_id}/conferencia",
            json={"fundamento_temporal": ft_invalido_extra},
            headers={"Authorization": "Bearer t"},
        )
        assert r_inv2.status_code == 422

        # Forma válida aceita com 200
        r_ok = c.post(
            f"/v1/registros/{run_id}/conferencia",
            json={"evidencias": ev_valida, "fundamento_temporal": ft_valido},
            headers={"Authorization": "Bearer t"},
        )
        assert r_ok.status_code == 200

    # MCP
    server = ms.create_mcp(home=str(svc.home))
    try:
        from mcp import Client

        async def _call_client(args):
            async with Client(server) as client:
                return await client.call_tool("obter_registro", args)

        # Exemplo do parecer recusado pelo MCP (ToolError ou is_error no protocolo)
        with pytest.raises(Exception):
            asyncio.run(server.call_tool("obter_registro", {"run_id": run_id, "evidencias": ev_invalida_parecer}))
        res_mcp_inv1 = asyncio.run(_call_client({"run_id": run_id, "evidencias": ev_invalida_parecer}))
        assert res_mcp_inv1.is_error

        # Extra em fundamento_temporal recusado pelo MCP
        with pytest.raises(Exception):
            asyncio.run(server.call_tool("obter_registro", {"run_id": run_id, "fundamento_temporal": ft_invalido_extra}))
        res_mcp_inv2 = asyncio.run(_call_client({"run_id": run_id, "fundamento_temporal": ft_invalido_extra}))
        assert res_mcp_inv2.is_error

        # Forma válida aceita pelo MCP
        res_mcp_ok = asyncio.run(_call_client({"run_id": run_id, "evidencias": ev_valida, "fundamento_temporal": ft_valido}))
        assert not res_mcp_ok.is_error
    finally:
        from pathlib import Path
        ms._servicos.pop(str(Path(svc.home).resolve()), None)
