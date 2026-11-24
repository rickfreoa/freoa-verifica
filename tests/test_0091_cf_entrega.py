"""Decisão 0091: entrega da Constituição pelo MCP (relato de uso em 24/11/2026) e defeito do parser do Planalto.

HTML sintético (categoria `sintetica`, inline): reproduz a marcação real do Planalto observada na CF compilada
(`<p ...></font><font>LXXVIII - ...`), em que o `</font>` órfão esvazia o `<p>` e o lxml põe a fonte sob o body.
"""
from __future__ import annotations

import pytest

from freoa_verifica.aliases import WorkKey
from freoa_verifica.citation import parse_one
from freoa_verifica.connectors import planalto
from freoa_verifica.identity import declared_identity
from freoa_verifica.parsers.model import ParsedDocument
from freoa_verifica.parsers.planalto import parse_planalto
from freoa_verifica.service import Verifica, _marcador
from freoa_verifica.verify import pode_negar

CF = WorkKey("federal", "constituicao", "1988", 1988)
KEY = WorkKey("federal", "lei", "9999", 2000)
T0, T1 = "2026-01-01T00:00:00+00:00", "2026-02-01T00:00:00+00:00"


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")


# --------------------------------------------------------------------------- pontos 3 e 4: citação

@pytest.mark.parametrize("texto,caminho", [
    ("Constituição Federal de 1988, art. 5º", "art5"),
    ("art. 5º da Constituição Federal", "art5"),
    ("CF/88, art. 5º", "art5"),
    ("art. 5º, LXXIII, da CF/88", "art5.inc73"),
    ("art. 5º da CRFB/1988", "art5"),
    ("Constituição da República Federativa do Brasil de 1988, art. 37", "art37"),
    ("Constituição Federal, art. 5º, inciso XI", "art5.inc11"),
    ("art. 10 do ADCT", "adct/art10"),
])
def test_formas_de_citar_a_cf_de_1988(texto, caminho):
    c = parse_one(texto)
    assert c is not None and c.work == CF and c.path == caminho and c.confidence == "exata"


@pytest.mark.parametrize("texto,ano,caminho", [
    ("Constituição de 1891, art. 72", 1891, "art72"),
    ("art. 5º da Constituição de 1967", 1967, "art5"),
    ("art. 113 da Constituição de 16 de julho de 1934", 1934, "art113"),
    ("Constituição de 1824, art. 179", 1824, "art179"),
])
def test_constituicoes_anteriores_nunca_sao_a_de_1988(texto, ano, caminho):
    c = parse_one(texto)
    assert c is not None and c.work == WorkKey("federal", "constituicao", str(ano), ano) and c.path == caminho


def test_ano_que_nao_e_constituicao_federal_fica_provavel_e_nao_vira_1988():
    c = parse_one("Constituição de 1989, art. 2º")
    assert c.work.number == "1989" and c.confidence == "provavel" and "constituicao_nao_federal" in c.flags


@pytest.mark.parametrize("texto", ["art. 1º da Constituição do Estado de São Paulo", "Constituição Estadual, art. 3º",
                                   "art. 2º da Constituição Paulista"])
def test_constituicao_estadual_nao_e_citada_como_federal(texto):
    assert parse_one(texto) is None


def test_chave_do_planalto_e_identidade_declarada_pelo_ano():
    assert planalto.work_key("CF", "1988", 1988) == "CF:1988"
    assert planalto.work_key("CF", "1891", 1891) == "CF:1891"
    assert planalto.urls_for_work("CF", "1891", 1891) == []  # sem rota conhecida: nunca a URL da de 1988
    assert planalto._parse_key("CF:1934") == ("CF", "1934", 1934)
    doc = ParsedDocument("planalto", "t", "CONSTITUIÇÃO DOS ESTADOS UNIDOS DO BRASIL (DE 16 DE JULHO DE 1934)", None, "")
    assert declared_identity(doc)[0] == WorkKey("federal", "constituicao", "1934", 1934)
    doc = ParsedDocument("planalto", "t", "CONSTITUIÇÃO DA REPÚBLICA FEDERATIVA DO BRASIL DE 1988", None, "")
    assert declared_identity(doc)[0] == CF


# --------------------------------------------------------------------------- parser: fonte órfã fora de <p>

# Dentro de um <font> externo (como na CF compilada), o </font> do <p> fecha o externo: a fonte seguinte vai ao body
# e a próxima <font> reabre o invólucro dos parágrafos seguintes (que continuam em <p>).
_ORFA = ('<p ALIGN="JUSTIFY"></font><font face="Arial" SIZE="2">{}</font>\n<font face="Arial">')


def _html(corpo: str) -> bytes:
    return ("<html><head><title>Lei 9.999</title></head><body><p>LEI Nº 9.999, DE 1º DE JANEIRO DE 2000</p>"
            f'<p>Dispõe sobre testes.</p><font face="Arial">{corpo}<p>Brasília, 1º de janeiro de 2000.</p></font>'
            "</body></html>").encode()


def _caminhos(corpo: str):
    doc = parse_planalto(_html(corpo), base_url="https://example.invalid/l9999.htm")
    return {p.path: p.redactions[-1].text for p in doc.provisions}, doc


def test_inciso_em_fonte_orfa_entra_no_modelo():
    p, _ = _caminhos('<p>Art. 5º Todos são iguais:</p><p>I - homens e mulheres;</p>'
                     + _ORFA.format("II - a todos é assegurada a razoável duração do processo.")
                     + '<p>Art. 6º Outro artigo.</p>')
    assert p["art5.inc2"] == "a todos é assegurada a razoável duração do processo."
    assert set(p) >= {"art5", "art5.inc1", "art5.inc2", "art6"}


def test_artigo_em_fonte_orfa_nao_cede_seus_paragrafos_ao_anterior():
    p, _ = _caminhos('<p>Art. 61. A iniciativa das leis cabe a qualquer membro.</p>'
                     '<p>§ 1º São de iniciativa privativa as leis que:</p><p>§ 2º A iniciativa popular.</p>'
                     + _ORFA.format("Art. 62. Em caso de relevância e urgência, o Presidente poderá adotar medidas.")
                     + '<p>§ 1º É vedada a edição de medidas provisórias sobre matéria:</p>'
                       '<p>§ 3º As medidas provisórias perderão eficácia.</p>')
    assert "art61.par3" not in p and p["art62.par3"] == "As medidas provisórias perderão eficácia."
    assert p["art61.par1"].startswith("São de iniciativa") and p["art62.par1"].startswith("É vedada")


def test_remissao_e_rotulo_sem_corpo_em_fonte_orfa_nao_viram_dispositivo():
    p, _ = _caminhos('<p>Art. 1º Fica excluído do monopólio o previsto no</p>'
                     + _ORFA.format("art. 45 da Lei no 2.004, de 3 de outubro de 1953")
                     + '<p>Art. 2º Compete:</p><p>I - julgar;</p>'
                     + _ORFA.format("II) (Revogado pela Lei nº 1, de 2004)") + '<p>III - processar.</p>')
    assert "art45" not in p and p["art1"].startswith("Fica excluído") and "2.004" not in p["art2.inc1"]


def test_fonte_orfa_com_varios_dispositivos_impede_negativa():
    _, doc = _caminhos('<p>Art. 1º Compete:</p>' + _ORFA.format("I - julgar; II - processar.")
                       + '<p>Art. 2º Outro.</p>')
    assert any(i.code == "DISPOSITIVO_FORA_DA_ARVORE" for i in doc.issues)

    class _RW:  # pode_negar só lê documento, captura e caminhos conhecidos
        capture_id, quarantined, source_id, caminhos_conhecidos, document = "c", False, "planalto", frozenset(), doc
    assert pode_negar(_RW(), "art1.inc2") == "ESTRUTURA_INCOMPLETA"


# --------------------------------------------------------------------------- ponto 2: artigo integral

def _idx(s, corpo, quando, nome):
    body = _html(corpo)
    url = "https://example.invalid/" + nome
    return s.indexar_obra(source_id="planalto", work_key=KEY, document=parse_planalto(body, base_url=url), body=body,
                          url=url, label="Lei 9.999/2000", fetched_at=quando, content_type="text/html; charset=utf-8")


_ART = ('<p>Art. 1º Compete à União:</p><p>I - legislar;</p><p>a) sobre direito civil;</p><p>b) sobre direito penal;</p>'
        '<p>II - julgar.</p><p>Parágrafo único. A lei disporá.</p><p>Art. 2º Outro artigo.</p>')


def test_obter_dispositivo_integral_devolve_o_artigo_inteiro(tmp_path):
    with Verifica(tmp_path) as s:
        _idx(s, _ART, T0, "A")
        so = s.obter_dispositivo(citacao="art. 1º da Lei 9.999/2000")
        assert so["status"] == "encontrada" and "subdispositivos" not in so and so["texto"] == "Compete à União:"
        r = s.obter_dispositivo(citacao="art. 1º da Lei 9.999/2000", abrangencia="integral")
        assert r["abrangencia"] == "integral" and r["texto"] == "Compete à União:"
        assert [i["caminho"] for i in r["subdispositivos"]] == [
            "art1.inc1", "art1.inc1.ali-a", "art1.inc1.ali-b", "art1.inc2", "art1.parunico"]
        assert all(i["vigencia"]["status"] for i in r["subdispositivos"]) and not r["subdispositivos_truncado"]
        assert r["texto_integral"].splitlines() == ["Art. 1º Compete à União:", "I – legislar;", "a) sobre direito civil;",
                                                    "b) sobre direito penal;", "II – julgar.",
                                                    "Parágrafo único. A lei disporá."]
        assert "art2" not in str(r["subdispositivos"])
        assert s.obter_dispositivo(citacao="art. 1º da Lei 9.999/2000", abrangencia="tudo")["status"] == "formato_invalido"


def test_marcadores_de_leitura():
    assert [_marcador(x) for x in ("Inciso IV", "§ 2", "§ 12", "Alínea c", "Parágrafo único", "Art. 5", "Art. 62")] == [
        "IV –", "§ 2º", "§ 12.", "c)", "Parágrafo único.", "Art. 5º", "Art. 62."]


# --------------------------------------------------------------------------- ponto 1: captura recente rebaixada

def test_captura_mais_nova_rebaixada_reconfirma_o_dispositivo_ou_se_declara(tmp_path):
    with Verifica(tmp_path) as s:
        _idx(s, '<p>Art. 1º Um.</p><p>Art. 2º Dois.</p><p>Art. 3º Três.</p>', T0, "A")
        _idx(s, '<p>Art. 1º Um.</p><p>Art. 2º Dois alterado.</p>', T1, "B")  # perde o art. 3º: rebaixada (0034)
        r1 = s.obter_dispositivo(citacao="art. 1º da Lei 9.999/2000")
        assert r1["evidencia"]["fetched_at"] == T0  # o texto continua o da captura canônica
        assert r1["reconfirmacao"]["fetched_at"] == T1
        assert r1["reconfirmacao"]["motivo"] == "MESMA_REDACAO_EM_CAPTURA_MAIS_RECENTE"
        r2 = s.obter_dispositivo(citacao="art. 2º da Lei 9.999/2000")  # redação divergente: nunca reconfirma
        assert "reconfirmacao" not in r2 and r2["texto"] == "Dois."
        recente = r2["capturas_recentes_nao_canonicas"][0]
        assert recente["fetched_at"] == T1 and recente["motivo"] == "PERDA_ESTRUTURAL"
        assert recente["dispositivo"] == "redacao_divergente_ou_ambigua" and "art3" in recente["perdidos"]


# --------------------------------------------------------------------------- ponto 5: envelhecimento e renovação

def test_envelhecimento_e_renovacao_offline(tmp_path):
    from datetime import date

    from freoa_verifica.acervo import envelhecimento

    with Verifica(tmp_path) as s:
        _idx(s, _ART, T0, "A")
        aviso = envelhecimento(s.conn, hoje=date(2026, 3, 1))
        assert aviso["codigo"] == "acervo_envelhecendo" and aviso["obras"] == 1
        assert envelhecimento(s.conn, hoje=date(2026, 1, 10)) is None
        r = s.renovar_acervo()
        assert r["status"] == "indisponivel" and r["motivo"] == "offline"


# --------------------------------------------------------------------------- emenda à 0065 (reprocessamento legado)

def test_decisao_legada_ja_conferida_aceita_modelo_novo_so_com_parser_novo(tmp_path):
    """Captura cp1252 sem Content-Type (recibo da 1.2.0), conferida na primeira releitura: com o mesmo parser e modelo
    persistido divergente, a releitura falha (0065); com modelo persistido de parser anterior, aceita e registra."""
    import json

    from freoa_verifica.texto_resposta import ORIGEM_LEGADO_CONFERIDO

    texto = ("<html><head></head><body><p>LEI Nº 3, DE 1 DE JANEIRO DE 2000</p>"
             "<p>Art. 1º Ação de teste.</p></body></html>")
    url = "https://www.planalto.gov.br/ccivil_03/leis/l3.htm"
    with Verifica(tmp_path) as s:
        rw = s.indexar_obra(source_id="planalto", work_key=WorkKey("federal", "lei", "3", 2000),
                            document=parse_planalto(texto, base_url=url), body=texto.encode("cp1252"), url=url,
                            fetched_at=T0, label="Lei 3/2000", content_type="text/html; charset=windows-1252")
        cap = rw.capture_id
        s.conn.execute("DROP TRIGGER IF EXISTS capture_no_update")  # recibo como a 1.2.0 o gravou
        s.conn.execute("UPDATE capture SET headers_json='{}', content_type=NULL, codificacao=NULL, "
                       "origem_da_codificacao=NULL WHERE id=?", (cap,))
        s.conn.commit()
        assert not s.reprocessar_capturas()["falhas"]  # primeira releitura: modelo idêntico, decisão conferida

        def _modelo(parser):
            m = json.loads(s.conn.execute("SELECT model_json FROM parsed_document WHERE capture_id=?",
                                          (cap,)).fetchone()[0])
            m = {**m, "title": m["title"] + " (anterior)", "parser_version": parser or m["parser_version"]}
            with s.conn:
                s.conn.execute("UPDATE parsed_document SET model_json=? WHERE capture_id=?", (json.dumps(m), cap))

        assert s.conn.execute("SELECT interpretacao_origem FROM parsed_document WHERE capture_id=?",
                              (cap,)).fetchone()[0] == ORIGEM_LEGADO_CONFERIDO
        _modelo(None)  # mesmo parser, modelo divergente
        assert {"capture_id": cap, "motivo": "interpretacao_indisponivel"} in s.reprocessar_capturas()["falhas"]
        _modelo("1.2.3")  # modelo de parser anterior
        assert not s.reprocessar_capturas()["falhas"]
        conf = json.loads(s.conn.execute("SELECT interpretacao_conferencia FROM parsed_document WHERE capture_id=?",
                                         (cap,)).fetchone()[0])
        assert conf["decisao_ja_conferida"] is True and conf["parser_anterior"] == "1.2.3"
