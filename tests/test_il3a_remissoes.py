"""IL.3-a, A2: `remissoes[]` em `obter_dispositivo` (matriz IL.1, seção 1, capacidade e; il3-especificacao A2).

Oráculos escritos à mão, independentes do extrator: cada caso traz o conjunto exato esperado de (obra, caminho, resolvida).
Falso positivo (resolvida: true fora do esperado) é confirmação indevida (matriz, seção 2, iii).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import pytest

from freoa_verifica import remissoes as rem
from freoa_verifica.aliases import WorkKey
from freoa_verifica.parsers.model import Issue
from freoa_verifica.parsers.planalto import parse_planalto
from freoa_verifica.service import Verifica
from freoa_verifica.store import blobs
from tests.fixture_util import load_fixture, load_meta

LSA = WorkKey("federal", "lei", "6404", 1976)
L6385 = WorkKey("federal", "lei", "6385", 1976)


def _rodar(texto, art="art14", obra=LSA, existe=lambda w, p: True, implicita=True):
    saida = rem.remissoes(texto, obra, existe, art, implicita=implicita)
    return {(r["alvo"]["obra"], r["alvo"]["caminho"], r["resolvida"]) for r in saida}


LSA_R = "Lei 6.404/1976"

# (nome, texto, esperado exato)
CASOS = [
    ("outra_lei_explicita",
     "Art. 171-C. A transação não caracteriza renúncia para fins do disposto no art. 14 da Lei Complementar no 101, "
     "de 4 de maio de 2000 (Lei de Responsabilidade Fiscal).",
     {("Lei Complementar 101/2000", "art. 14", True)}),
    ("propria_lei_lista",
     "Art. 191-A. Observado o disposto nos arts. 151, 205 e 206 desta Lei.",
     {(LSA_R, "art. 151", True), (LSA_R, "art. 205", True), (LSA_R, "art. 206", True)}),
    ("propria_lei_sem_qualificacao_e_paragrafo_do_ultimo",
     "Art. 14. O preço de emissão, fixado na constituição da companhia, na forma da lei, pelos fundadores "
     "(artigos 166 e 170, § 2o). Parágrafo único. O preço de emissão pode ser fixado.",
     {(LSA_R, "art. 166", True), (LSA_R, "art. 170, § 2º", True)}),
    ("inciso_do_artigo_e_incisos_em_lista",
     "Art. 103. Entram em vigor: I - os atos a que se refere o inciso I do art. 100, na data; II - as decisões a que se "
     "refere o inciso II do art. 100.",
     {(LSA_R, "art. 100, inciso I", True), (LSA_R, "art. 100, inciso II", True)}),
    ("incisos_depois_do_artigo",
     "Art. 9o Não se proferirá decisão. Parágrafo único. II - previstas no art. 311, incisos II e III; III - à decisão "
     "prevista no art. 701.",
     {(LSA_R, "art. 311, inciso II", True), (LSA_R, "art. 311, inciso III", True), (LSA_R, "art. 701", True)}),
    ("caput_do_artigo_e_de_si_mesmo",
     "Art. 1.815-A. Em qualquer dos casos de indignidade previstos no art. 1.814, a sentença prevista no caput do "
     "art. 1.815 deste Código.",
     {(LSA_R, "art. 1.814", True), (LSA_R, "art. 1.815, caput", True)}),
    ("no_caput_e_no_paragrafo_do_proprio_artigo",
     "Art. 9o Não ... Parágrafo único. O disposto no caput não se aplica; ver também o § 2º deste artigo.",
     {(LSA_R, "art. 14, caput", True), (LSA_R, "art. 14, § 2º", True)}),
    ("faixa_de_artigos",
     "Art. 20. Aplicam-se os arts. 5º a 8º desta Lei.",
     {(LSA_R, "art. 5º", True), (LSA_R, "art. 6º", True), (LSA_R, "art. 7º", True), (LSA_R, "art. 8º", True)}),
    ("constituicao_explicita",
     "Art. 910. Observando-se o disposto no art. 100 da Constituição Federal.",
     {("Constituição Federal", "art. 100", True)}),
    ("alinea_paragrafo_inciso_encadeados",
     "Art. 20. Conforme o art. 2º, § 1º, inciso III, alínea a, da Lei nº 8.987, de 13 de fevereiro de 1995.",
     {("Lei 8.987/1995", "art. 2º, § 1º, inciso III, alínea a", True)}),
    ("prefixo_encadeado",
     "Art. 5º Ver §§ 1º e 2º do art. 7º e incisos I e II do § 3º do art. 8º desta Lei.",
     {(LSA_R, "art. 7º, § 1º", True), (LSA_R, "art. 7º, § 2º", True),
      (LSA_R, "art. 8º, § 3º, inciso I", True), (LSA_R, "art. 8º, § 3º, inciso II", True)}),
    ("nota_editorial_nao_conta",
     "Art. 5º Texto sem remissão. (Redação dada pela Lei nº 10.303, de 2001) (Vide art. 9º da Lei nº 1.234, de 1990) "
     "(Incluído pela Lei nº 9.457, de 1997, art. 3º) (NR)",
     set()),
    ("anaforica_e_generica_nunca_resolvem",
     "Art. 5º Na forma da lei, nos termos do artigo anterior e do art. 3º da mesma Lei.",
     set()),
    ("aberta_nao_resolve",
     "Art. 5º Aplica-se o art. 4º e seguintes desta Lei.",
     {(LSA_R, "art. 4º", False)}),
    ("barra_nao_resolve",
     "Art. 5º Aplica-se o disposto nos arts. 4º/5º desta Lei.",
     {(LSA_R, "art. 4º", False)}),
    ("obra_ambigua_depois_de_outra_obra",
     "Art. 5º Nos termos do art. 3º da Lei nº 8.987, de 13 de fevereiro de 1995, e do art. 4º, observado.",
     {("Lei 8.987/1995", "art. 3º", True), (None, "art. 4º", False)}),
    ("obra_ambigua_encadeada_com_obra_explicita",
     "Art. 5º Aplica-se o art. 4º e o art. 6º da Lei nº 8.987, de 13 de fevereiro de 1995.",
     {(None, "art. 4º", False), ("Lei 8.987/1995", "art. 6º", True)}),
    ("obra_sem_ano_nao_resolve",
     "Art. 5º Aplica-se o art. 4º da Lei 10.406.",
     {(None, "art. 4º", False)}),
    ("quantidade_nao_e_artigo",
     "Art. 5º Prazo do art. 4º, 6 (seis) dias, e art. 7 anos.",
     {(LSA_R, "art. 4º", True)}),
    ("rubrica_do_proprio_dispositivo_nao_conta",
     "Art. 14. O preço de emissão pode ser fixado.",
     set()),
]


@pytest.mark.parametrize("nome,texto,esperado", CASOS, ids=[c[0] for c in CASOS])
def test_oraculo_por_classe(nome, texto, esperado):
    assert _rodar(texto) == esperado


def test_alvo_inexistente_nao_resolve_e_preserva_texto():
    saida = rem.remissoes("Art. 5º Ver o art. 99 desta Lei; ver o art. 6º.", LSA,
                          lambda w, p: p == "art6", "art5")
    por = {r["alvo"]["caminho"]: r for r in saida}
    assert por["art. 99"]["resolvida"] is False and "art. 99" in por["art. 99"]["texto"]
    assert por["art. 6º"]["resolvida"] is True


def test_dispositivo_de_anexo_nao_herda_obra_implicita():
    assert _rodar("Art. 3º Aplica-se o art. 4º.", art=None, implicita=False) == {(None, "art. 4º", False)}
    assert _rodar("Art. 3º Aplica-se o art. 4º desta Lei.", art=None, implicita=False) == {(LSA_R, "art. 4º", True)}


def test_excecao_em_existe_e_inexistencia():
    def boom(w, p):
        raise LookupError("falha")
    assert _rodar("Art. 5º art. 4º desta Lei.", existe=boom) == {(LSA_R, "art. 4º", False)}


def test_desta_lei_em_obra_de_outra_especie_nao_resolve():
    decreto = WorkKey("federal", "decreto", "10000", 2019)
    assert _rodar("Art. 5º Aplica-se o art. 4º desta Lei.", obra=decreto) == {(None, "art. 4º", False)}
    assert _rodar("Art. 5º Aplica-se o art. 4º deste Decreto.", obra=decreto) == {("Decreto 10.000/2019", "art. 4º", True)}


# --- mutante: resolver por proximidade textual tem de falhar ---------------------------------------------------------


def _por_proximidade(real):
    """Mutante do extrator: a remissão sem obra herda a obra da remissão explícita mais próxima antes dela."""
    def mutante(texto, obra_propria, art_proprio=None, *, implicita=True, **kw):
        itens = real(texto, obra_propria, art_proprio, implicita=implicita, **kw)
        ultima = None
        for it in itens:
            if it["obra"] is not None and not it["duvida"]:
                ultima = it
            elif it["obra"] is None and ultima is not None:
                it.update(obra=ultima["obra"], obra_rotulo=ultima["obra_rotulo"], duvida=False)
        return itens
    return mutante


def test_mutante_proximidade_falha_no_oraculo(monkeypatch):
    nome, texto, esperado = next(c for c in CASOS if c[0] == "obra_ambigua_depois_de_outra_obra")
    assert _rodar(texto) == esperado
    monkeypatch.setattr(rem, "extrair", _por_proximidade(rem.extrair))
    assert _rodar(texto) != esperado  # o oráculo distingue o mutante: (Lei 8.987/1995, art. 4º, True) é falso positivo


# --- fachada: Python, MCP e REST pelas mesmas regras ------------------------------------------------------------------


@pytest.fixture
def svc6385(tmp_path, monkeypatch):
    home = tmp_path / "fv-a2"
    home.mkdir()
    monkeypatch.setenv("FV_HOME", str(home))
    monkeypatch.setenv("FV_OFFLINE", "1")
    body = load_fixture("planalto_lei_6385_1976")
    entry = load_meta()["planalto_lei_6385_1976"]
    doc = parse_planalto(body, base_url="https://www.planalto.gov.br/ccivil_03/leis/")
    svc = Verifica(home=home)
    rw = svc.indexar_obra(source_id="planalto", work_key=L6385, document=doc, body=body, url=entry["url"],
                          fetched_at=entry.get("capturado_em"), work_date="1976-12-07", label="Lei nº 6.385/1976",
                          content_type="text/html; charset=windows-1252")
    yield svc, rw
    svc.close()


ESPERADO_ART9 = [{"texto": "no § 2o do art. 15", "alvo": {"obra": "Lei 6.385/1976", "caminho": "art. 15, § 2º"},
                  "resolvida": True}]


def test_fachada_python_devolve_remissoes_resolvidas_no_documento(svc6385):
    svc, _ = svc6385
    r = svc.obter_dispositivo(citacao="art. 9 da Lei 6.385/1976")
    assert r["status"] == "encontrada"
    assert r["remissoes"] == ESPERADO_ART9
    assert "referencias_nao_resolvidas" not in r  # o campo anafórico continua só em verificar_texto


def test_fachada_remissao_a_outra_obra_so_resolve_com_documento_capturado(svc6385):
    svc, rw = svc6385
    texto = "Art. 5º Ver o art. 254-A da Lei 6.404/1976 e o art. 3º da Lei 6.385/1976 e o art. 999 desta Lei."
    # a Lei 6.404 não está capturada: nunca resolvida, nem por proximidade nem por existir em outra obra
    por = {r["alvo"]["caminho"]: r["resolvida"] for r in svc._remissoes_dispositivo(rw, "art5", texto)}
    assert por["art. 254-A"] is False
    assert por["art. 3º"] is True and por["art. 999"] is False


def test_fachada_so_acompanha_texto_devolvido(svc6385):
    svc, _ = svc6385
    assert svc.obter_dispositivo(citacao="art. 9999 da Lei 6.385/1976")["remissoes"] == []
    assert svc.obter_dispositivo(citacao="art. 9 da Lei 6.385/1976", data="2001-01-01")["remissoes"] == []  # sem texto em D


def test_fachada_publicacao_original_sem_captura_nao_inventa_remissoes(svc6385):
    svc, _ = svc6385
    r = svc.obter_dispositivo(citacao="art. 9 da Lei 6.385/1976", versao="publicacao_original")
    assert r["remissoes"] == []


def test_rest_mesmas_regras(svc6385, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from freoa_verifica.rest import create_app

    svc, _ = svc6385
    monkeypatch.delenv("FV_API_TOKEN", raising=False)
    app = create_app(home=str(svc.home), token=None)
    for cached in svc._resolver.works.values():
        app.state.verifica.registrar(cached)
    with TestClient(app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1") as c:
        r = c.get("/v1/dispositivos", params={"citacao": "art. 9 da Lei 6.385/1976"})
    assert r.status_code == 200
    assert r.json()["remissoes"] == ESPERADO_ART9


def test_mcp_mesmas_regras_e_texto_da_remissao_envolvido(svc6385, monkeypatch):
    pytest.importorskip("mcp")
    from mcp import Client

    from freoa_verifica import mcp_server as ms
    from freoa_verifica.sanitizacao import DOC_OPEN

    svc, _ = svc6385
    monkeypatch.setenv("FV_HOME", str(svc.home))
    monkeypatch.setitem(ms._servicos, str(svc.home), svc)
    mcp = ms.create_mcp(home=str(svc.home))

    async def _run():
        async with Client(mcp) as client:
            r = await client.call_tool("obter_dispositivo", {"citacao": "art. 9 da Lei 6.385/1976"})
            assert not r.is_error
            sc = getattr(r, "structured_content", None) or json.loads(r.content[0].text)
            return sc

    out = asyncio.run(_run())
    assert [x["alvo"] for x in out["remissoes"]] == [ESPERADO_ART9[0]["alvo"]]
    assert [x["resolvida"] for x in out["remissoes"]] == [True]
    assert out["remissoes"][0]["texto"].startswith(DOC_OPEN) and "art. 15" in out["remissoes"][0]["texto"]


# --- B6 (R1): a expressão só é resolvida depois de consumida e validada por inteiro; na dúvida, abstenção ---------------
# Oráculos escritos à mão por CLASSE (os exemplos do auditor mais as variantes da mesma classe). Em todos o conjunto de
# alvos `resolvida: true` esperado é vazio: o alvo estrutural existe (existe=True), o que falta é a prova da expressão.


def _resolvidas(texto, art="art14", obra=LSA, notas=(), truncado=False, integral=None):
    saida = rem.remissoes(texto, obra, lambda w, p: True, art, notas=notas, truncado=truncado, integral=integral)
    return {(r["alvo"]["obra"], r["alvo"]["caminho"]) for r in saida if r["resolvida"]}


NAO_RESOLVE = [
    # qualificador estrutural depois do artigo que a leitura não reconhece (o ancestral não pode ser resolvido)
    ("inciso_sem_palavra", "Art. 14. Ver art. 5, I, desta Lei."),
    ("inciso_faixa", "Art. 14. Ver art. 5, I a III, desta Lei."),
    ("paragrafo_e_inciso_sem_palavra", "Art. 14. Ver art. 5, § 1, I, desta Lei."),
    ("inciso_capitalizado", "Art. 14. Ver art. 5, Inciso I, desta Lei."),
    ("inciso_abreviado", "Art. 14. Ver art. 5, inc. I, desta Lei."),
    ("inciso_abreviado_sem_virgula", "Art. 14. Ver art. 5 inc. II desta Lei."),
    ("inciso_ordinal_alto", "Art. 14. Ver art. 5º, § 2º, III e IV, desta Lei."),
    ("alinea_abreviada", "Art. 14. Ver art. 5º, I, al. a, desta Lei."),
    ("alinea_com_parenteses", "Art. 14. Ver art. 5º, a) desta Lei."),
    ("letra", "Art. 14. Ver art. 5º, letra b, desta Lei."),
    ("item", "Art. 14. Ver art. 5º, item 3, desta Lei."),
    ("paragrafo_sem_virgula", "Art. 14. Ver art. 5º § 2º desta Lei."),
    ("inciso_antes_abreviado", "Art. 14. Ver inc. I do art. 5º desta Lei."),
    ("inciso_antes_maiusculo", "Art. 14. Ver Inciso II do art. 5º desta Lei."),
    ("alinea_antes_abreviada", "Art. 14. Ver al. b do inciso I do art. 5º desta Lei."),
    ("romano_solto_antes", "Art. 14. Ver II do art. 5º desta Lei."),
    # âmbito de anexo
    ("anexo_depois_desta_lei", "Art. 14. Ver art. 5 do Anexo desta Lei."),
    ("anexo_numerado", "Art. 14. Ver art. 4 do Anexo I."),
    ("anexo_unico", "Art. 14. Ver art. 4º, do Anexo único."),
    ("anexo_no", "Art. 14. Ver art. 4º no Anexo II."),
    ("anexo_antes", "Art. 14. No Anexo I, aplica-se o art. 4º."),
    # obra externa no contexto da frase (inclusive em minúscula) e demonstrativo anafórico
    ("lei_minuscula_antes", "Art. 14. Conforme a lei 10.406/2002, art. 5."),
    ("decreto_minusculo_antes", "Art. 14. Nos termos do decreto 9.000/2017, aplica-se o art. 3."),
    ("mp_antes", "Art. 14. Segundo a medida provisória 2.200-2/2001, art. 3."),
    ("resolucao_antes", "Art. 14. Pela Resolução 4.557/2017, art. 5."),
    ("lei_maiuscula_antes", "Art. 14. A Lei 8.987/1995 aplica-se; ver art. 4 dessa Lei."),
    ("dessa_lei", "Art. 14. Ver art. 4 dessa Lei."),
    ("desse_codigo", "Art. 14. Ver art. 4 desse Código."),
    ("nessa_lei", "Art. 14. Aplica-se o art. 4 nessa Lei."),
    ("nesse_decreto", "Art. 14. Aplica-se o art. 4 nesse Decreto."),
    ("paragrafo_desse_artigo", "Art. 14. Ver no § 1º desse artigo."),
    # parágrafo/caput soltos com outra obra em volta
    ("paragrafo_unico_de_outra_lei", "Art. 14. Ver no parágrafo único da Lei 10.406/2002."),
    ("caput_em_contexto_de_outra_lei", "Art. 14. Na Lei 8.987/1995, aplica-se o disposto no caput."),
    ("caput_em_contexto_de_lei_numerada", "Art. 14. Conforme o decreto 9.000/2017, aplica-se o disposto no caput."),
    ("paragrafo_solto_com_inciso", "Art. 14. O disposto no § 2º, I, não se aplica."),
    ("paragrafo_solto_de_anexo", "Art. 14. O disposto no § 2º do Anexo não se aplica."),
    # nota editorial (parentética ou entre colchetes)
    ("nota_editorial_colchetes", "Art. 14. [Nota editorial: ver art. 5 desta Lei.]"),
    ("nota_do_editor_parenteses", "Art. 14. (Nota do editor: ver art. 5 desta Lei)"),
    ("nota_ne", "Art. 14. (N.E. ver art. 5 desta Lei)"),
    ("colchetes_sem_rotulo", "Art. 14. [ver art. 5 desta Lei]"),
    # R2-5: caixa e abreviação do qualificador (a leitura é feita sobre o texto normalizado)
    ("inciso_em_caixa_alta", "Art. 14. Ver art. 5, INCISO I, desta Lei."),
    ("inciso_abreviado_em_caixa_alta", "Art. 14. Ver art. 5, INC. I, desta Lei."),
    ("incisos_abreviado_plural", "Art. 14. Ver art. 5, INCS. I e II, desta Lei."),
    ("alinea_em_caixa_alta", "Art. 14. Ver art. 5, ALÍNEA a, desta Lei."),
    ("item_em_caixa_alta", "Art. 14. Ver art. 5, ITEM 2, desta Lei."),
    ("romano_minusculo_residual", "Art. 14. Ver art. 5, i, desta Lei."),
    ("romano_minusculo_duplo", "Art. 14. Ver art. 5, ii e iii, desta Lei."),
    # R2-5: separação por dois-pontos ou travessão
    ("dois_pontos_e_inciso", "Art. 14. Ver art. 5: inciso I, desta Lei."),
    ("hifen_e_inciso", "Art. 14. Ver art. 5 - inciso I, desta Lei."),
    ("meia_risca_e_inciso", "Art. 14. Ver art. 5 – inciso I, desta Lei."),
    ("travessao_e_inciso", "Art. 14. Ver art. 5 — inciso I, desta Lei."),
    # R2-5: qualificador DEPOIS da identificação da obra (própria e externa)
    ("inciso_depois_da_obra_propria", "Art. 14. Ver art. 5 desta Lei, inciso I."),
    ("inciso_abreviado_depois_da_obra_propria", "Art. 14. Ver art. 5 desta Lei, inc. I."),
    ("romano_depois_da_obra_propria", "Art. 14. Ver art. 5 desta Lei, I."),
    ("alinea_depois_da_obra_propria", "Art. 14. Ver art. 5 desta Lei, alínea a."),
    ("paragrafo_depois_da_obra_propria", "Art. 14. Ver art. 5 desta Lei, § 2º."),
    ("caput_depois_da_obra_propria", "Art. 14. Ver art. 5 desta Lei, caput."),
    ("item_depois_da_obra_propria", "Art. 14. Ver art. 5 desta Lei, item 2."),
    ("inciso_depois_de_palavras_funcionais", "Art. 14. Ver art. 5 desta Lei e do inciso I."),
    ("inciso_depois_da_obra_externa", "Art. 14. Ver art. 5 da Lei 8.987/1995, inciso I."),
    ("romano_depois_da_obra_externa", "Art. 14. Ver art. 5 da Lei 8.987/1995, I."),
    # R2-5: anexo depois da identificação da obra
    ("anexo_depois_da_obra_propria", "Art. 14. Ver art. 5 desta Lei, do Anexo I."),
    ("anexo_depois_da_obra_externa", "Art. 14. Ver art. 5 da Lei 8.987/1995, do Anexo I."),
    # R2-5: parágrafo solto com qualificador residual
    ("paragrafo_solto_dois_pontos_inciso", "Art. 14. O disposto no § 2º: inciso I, não se aplica."),
    ("paragrafo_solto_hifen_inciso", "Art. 14. O disposto no § 2º - inciso I, não se aplica."),
    ("paragrafo_solto_inciso_em_caixa_alta", "Art. 14. O disposto no § 2º, INCISO I, não se aplica."),
    # R2-5: espécie abreviada e sigla antes da remissão (a obra não é a própria)
    ("mp_abreviada_antes", "Art. 14. Conforme a MP 881/2019, art. 5."),
    ("lc_abreviada_antes", "Art. 14. Conforme a LC 101/2000, art. 5."),
    ("sigla_cc_antes", "Art. 14. Conforme o CC, aplica-se o art. 5."),
    ("mp_abreviada_antes_do_caput", "Art. 14. Conforme a MP 881/2019, aplica-se o disposto no caput."),
    ("lc_abreviada_antes_do_paragrafo", "Art. 14. Conforme a LC 101/2000, aplica-se o disposto no § 2º."),
    # R2-5: contexto de anexo que a pontuação não apaga
    ("anexo_antes_dois_pontos_artigo", "Art. 14. No Anexo I: ver art. 5."),
    ("anexo_antes_dois_pontos_caput", "Art. 14. No Anexo I: aplica-se o disposto no caput."),
    ("anexo_antes_ponto_e_virgula", "Art. 14. No Anexo I; ver art. 5."),
    # R2-5: contexto externo separado por ponto e vírgula ou dois-pontos
    ("lei_externa_ponto_e_virgula", "Art. 14. Conforme a Lei 8.987/1995; aplica-se o art. 5."),
    ("lei_externa_dois_pontos", "Art. 14. Conforme a Lei 8.987/1995: aplica-se o art. 5."),
    ("lei_externa_em_minuscula_ponto_e_virgula", "Art. 14. Conforme a lei 8.987/1995; aplica-se o art. 5."),
    ("lei_externa_antes_do_caput_ponto_e_virgula", "Art. 14. Conforme a Lei 8.987/1995; aplica-se o disposto no caput."),
    ("lei_com_data_por_extenso_antes", "Art. 14. Conforme a Lei nº 8.987, de 13 de fevereiro de 1995; ver art. 5."),
    # R2-6: notas editoriais completas, em colchetes aninhados e fora de qualquer padrão conhecido
    ("nota_vide_parenteses", "Art. 14. (Vide art. 5 desta Lei, conforme explicacao editorial adicional)"),
    ("nota_editorial_parenteses", "Art. 14. (Nota editorial: art. 5 desta Lei, conforme explicacao editorial adicional)"),
    ("nota_editorial_colchetes_longa", "Art. 14. [Nota editorial: art. 5 desta Lei, conforme explicacao editorial adicional]"),
    ("nota_colchetes_aninhados", "Art. 14. [Nota editorial: ver art. 5 desta Lei [nota interna].]"),
    ("nota_parenteses_aninhados", "Art. 14. (Nota editorial: ver art. 5 desta Lei (nota interna) e mais)"),
    ("nota_dentro_da_expressao", "Art. 14. Ver art. 5 (Nota: x) desta Lei."),
    # notas cortadas pelo truncamento (a leitura as reconhece abertas, sem o delimitador final)
    ("nota_vide_cortada", "Art. 14. (Vide art. 5 desta Lei, conforme explicacao editorial adicional"),
    ("nota_editorial_cortada", "Art. 14. (Nota editorial: art. 5 desta Lei, conforme explicacao editorial adicional"),
    ("nota_colchetes_cortada", "Art. 14. [Nota editorial: art. 5 desta Lei, conforme explicacao editorial adicional"),
    ("nota_aninhada_cortada", "Art. 14. [Nota editorial: ver art. 5 desta Lei [nota interna]."),
]


@pytest.mark.parametrize("nome,texto", NAO_RESOLVE, ids=[c[0] for c in NAO_RESOLVE])
def test_b6_classe_nunca_resolve(nome, texto):
    assert _resolvidas(texto) == set(), nome


def test_r2_notas_cortadas_nao_resolvem_com_truncado_e_com_ou_sem_o_texto_integral():
    """O corte retira o delimitador final da nota: a extração sobre o emitido não pode ressuscitar a remissão da nota."""
    notas_completas = [
        "(Vide art. 5 desta Lei, conforme explicacao editorial adicional)",
        "(Nota editorial: art. 5 desta Lei, conforme explicacao editorial adicional)",
        "[Nota editorial: art. 5 desta Lei, conforme explicacao editorial adicional]",
        "[Nota editorial: ver art. 5 desta Lei [nota interna].]",
    ]
    for nota in notas_completas:
        integral = f"Art. 14. O valor é fixado. {nota} Texto depois da nota."
        assert _resolvidas(integral) == set(), nota  # a nota completa nunca resolve
        for cortes in (len(f"Art. 14. O valor é fixado. {nota[:-1]}"), len(f"Art. 14. O valor é fixado. {nota[:-12]}")):
            emitido = integral[:cortes]
            assert _resolvidas(emitido, truncado=True) == set(), (nota, "só o recorte")
            assert _resolvidas(emitido, truncado=True, integral=integral) == set(), (nota, "com o integral")
            # fornecendo também a nota completa pela estrutura do documento (o corte não a contém inteira)
            assert _resolvidas(emitido, truncado=True, integral=integral, notas=(nota,)) == set(), (nota, "com notas=")
            assert _resolvidas(emitido, truncado=True, notas=(nota,)) == set(), (nota, "notas= sem integral")
    # a referência real antes da nota, no mesmo recorte, continua resolvendo
    integral = "Art. 14. Ver art. 7º desta Lei. (Vide art. 5 desta Lei, conforme explicacao editorial adicional)"
    assert _resolvidas(integral[:-5], truncado=True, integral=integral) == {(LSA_R, "art. 7º")}


def test_r2_nota_parentetica_de_um_trecho_que_nao_e_nota_nao_e_mascarada():
    texto = "Art. 14. Ver (conforme art. 5 desta Lei) e mais."
    assert _resolvidas(texto) == {(LSA_R, "art. 5º")}


def test_r2_7_obra_explicitamente_igual_a_propria_e_a_propria_obra():
    """Antes: `Conforme a lei 6.404/1976, aplica-se o art. 5` na própria Lei 6.404/1976 virava obra desconhecida."""
    for texto in ("Art. 14. Conforme a lei 6.404/1976, aplica-se o art. 5.",
                  "Art. 14. Conforme a Lei 6.404/1976, aplica-se o art. 5.",
                  "Art. 14. Conforme a Lei nº 6.404, de 15 de dezembro de 1976, aplica-se o art. 5."):
        assert _resolvidas(texto) == {(LSA_R, "art. 5º")}, texto
    assert _resolvidas("Art. 14. Conforme a Lei 6.404/1976, aplica-se o disposto no caput.") == {(LSA_R, "art. 14, caput")}
    # outra obra, ainda que de mesmo número ou mesmo ano, nunca é a própria
    assert _resolvidas("Art. 14. Conforme a Lei 6.405/1976, aplica-se o art. 5.") == set()
    assert _resolvidas("Art. 14. Conforme a Lei 6.404/1977, aplica-se o art. 5.") == set()
    assert _resolvidas("Art. 14. Conforme a Lei 6.404/1976 e a Lei 8.987/1995, aplica-se o art. 5.") == set()
    assert _resolvidas("Art. 14. Conforme a Lei 6.404/1976, no Anexo I, aplica-se o art. 5.") == set()


def test_b6_controles_positivos_da_mesma_forma_continuam_resolvendo():
    assert _resolvidas("Art. 14. Ver art. 5 desta Lei.") == {(LSA_R, "art. 5º")}
    assert _resolvidas("Art. 14. Ver art. 5, § 1º, desta Lei.") == {(LSA_R, "art. 5º, § 1º")}
    assert _resolvidas("Art. 14. Ver art. 5º, inciso I, desta Lei.") == {(LSA_R, "art. 5º, inciso I")}
    assert _resolvidas("Art. 14. Ver o inciso I do art. 5º desta Lei.") == {(LSA_R, "art. 5º, inciso I")}
    assert _resolvidas("Art. 14. Ver art. 3º da Lei 8.987/1995.") == {("Lei 8.987/1995", "art. 3º")}
    assert _resolvidas("Art. 14. O disposto no caput não se aplica.") == {(LSA_R, "art. 14, caput")}
    assert _resolvidas("Art. 14. O disposto no § 1º deste artigo.") == {(LSA_R, "art. 14, § 1º")}
    # R2-5: prosa depois da expressão, ponto e vírgula e terminais não invalidam a remissão
    assert _resolvidas("Art. 14. Ver art. 5 desta Lei, que regula a matéria.") == {(LSA_R, "art. 5º")}
    assert _resolvidas("Art. 14. Ver art. 5 desta Lei, no prazo de 30 dias.") == {(LSA_R, "art. 5º")}
    assert _resolvidas("Art. 14. Ver art. 5 desta Lei; ver art. 6 da Lei 8.987/1995.") == {(LSA_R, "art. 5º"),
                                                                                    ("Lei 8.987/1995", "art. 6º")}
    assert _resolvidas("Art. 14. Ver art. 5, INCISO I, desta Lei.") == set()
    # o contexto antes da remissão em outra frase não a contamina
    assert _resolvidas("Art. 14. Conforme a Lei 8.987/1995. Ver art. 5.") == {(LSA_R, "art. 5º")}


def test_b6_nao_resolvida_preserva_o_texto_e_nao_inventa_alvo_mais_raso():
    saida = rem.remissoes("Art. 14. Ver art. 5, inc. I, desta Lei.", LSA, lambda w, p: True, "art14")
    assert [r["resolvida"] for r in saida] == [False] and "art. 5" in saida[0]["texto"]
    ext = rem.remissoes("Art. 14. Na Lei 8.987/1995, aplica-se o disposto no caput.", LSA, lambda w, p: True, "art14")
    assert all(r["alvo"]["obra"] is None and r["resolvida"] is False for r in ext)  # nunca a obra própria


def test_b6_notas_da_estrutura_do_documento_saem_da_leitura():
    nota = "(Ver art. 5 desta Lei, conforme texto do editor)"  # forma que nenhum padrão textual reconhece
    texto = f"Art. 14. O valor é fixado. {nota}"
    assert _resolvidas(texto) == {(LSA_R, "art. 5º")}
    assert _resolvidas(texto, notas=(nota,)) == set()


def test_b6_nota_editorial_preservada_pelo_parser_planalto_nao_resolve():
    html = ("<html><body><p>LEI Nº 6.404, DE 15 DE DEZEMBRO DE 1976.</p><p>Dispõe sobre as sociedades por ações.</p>"
            "<p>Art. 5º O valor é fixado. [Nota editorial: ver art. 6º desta Lei.] (Redação dada pela Lei nº 9.457, "
            "de 1997)</p><p>Art. 6º Texto.</p></body></html>")
    doc = parse_planalto(html, base_url="https://www.planalto.gov.br/ccivil_03/leis/")
    texto = doc.current_text("art5")
    assert "Nota editorial" in texto  # o parser preserva a nota: o resolvedor é quem a exclui
    assert _resolvidas(texto, art="art5") == set()


def test_b6_texto_cortado_no_limite_nao_resolve_a_remissao_que_toca_o_corte():
    assert _resolvidas("Art. 5º Ver o art. 15") == {(LSA_R, "art. 15")}
    assert _resolvidas("Art. 5º Ver o art. 15", truncado=True) == set()  # "art. 151" cortado em "art. 15"
    assert _resolvidas("Art. 5º Ver o art. 15, § 2", truncado=True) == set()
    assert _resolvidas("Art. 5º Ver o art. 7º desta Lei. E mais texto.", truncado=True) == {(LSA_R, "art. 7º")}


@pytest.mark.parametrize("regex_attr,nome", [
    ("_PREFIXO_RESIDUAL", "inciso_antes_abreviado"), ("_DEMONSTRATIVO", "dessa_lei"),
    ("_DEMONSTRATIVO", "paragrafo_desse_artigo"),
])
def test_b6_mutantes_sem_cada_cautela_falham_no_oraculo(monkeypatch, regex_attr, nome):
    import re as _re
    texto = dict(NAO_RESOLVE)[nome]
    assert _resolvidas(texto) == set()
    monkeypatch.setattr(rem, regex_attr, _re.compile(r"(?!x)x"))  # a cautela deixa de existir
    if regex_attr == "_DEMONSTRATIVO":  # a leitura volta a tratar "dessa/desse" como próprio
        monkeypatch.setattr(rem, "_PROPRIA", _re.compile(rem._PROPRIA.pattern.replace("desta|deste", "desta|deste|dessa|desse"),
                                                         rem._PROPRIA.flags))
    assert _resolvidas(texto) != set(), f"a ausência de {regex_attr} passou despercebida em {nome}"


@pytest.mark.parametrize("alvo,mutacao,nomes", [
    # sem a leitura fechada da cauda: qualificador depois da expressão, romano solto, anexo, dois-pontos, travessão
    ("_cauda_limpa", lambda *a, **k: True,
     ["inciso_sem_palavra", "inciso_em_caixa_alta", "inciso_abreviado_em_caixa_alta", "romano_minusculo_residual",
      "dois_pontos_e_inciso", "hifen_e_inciso", "inciso_depois_da_obra_propria", "romano_depois_da_obra_propria",
      "inciso_depois_da_obra_externa", "anexo_depois_da_obra_propria", "anexo_depois_da_obra_externa",
      "paragrafo_solto_dois_pontos_inciso", "paragrafo_solto_inciso_em_caixa_alta", "item_em_caixa_alta"]),
    # sem o contexto externo: obra, sigla e anexo antes da remissão sem obra
    ("_contexto_externo", lambda *a, **k: False,
     ["lei_minuscula_antes", "mp_abreviada_antes", "lc_abreviada_antes", "anexo_antes_dois_pontos_artigo",
      "lei_externa_ponto_e_virgula", "caput_em_contexto_de_lei_numerada", "mp_abreviada_antes_do_caput"]),
    # sem a localização das notas
    ("_spans_notas", lambda *a, **k: [],
     ["nota_editorial_colchetes", "nota_vide_parenteses", "nota_colchetes_aninhados", "nota_parenteses_aninhados",
      "nota_vide_cortada", "nota_colchetes_cortada", "nota_aninhada_cortada"]),
    # nota entre os componentes da própria expressão
    ("_toca_nota", lambda *a, **k: False, ["nota_dentro_da_expressao"]),
])
def test_r2_mutantes_da_gramatica_fechada_falham_no_oraculo(monkeypatch, alvo, mutacao, nomes):
    textos = dict(NAO_RESOLVE)
    for nome in nomes:
        assert _resolvidas(textos[nome]) == set(), nome
    monkeypatch.setattr(rem, alvo, mutacao)
    for nome in nomes:
        assert _resolvidas(textos[nome]) != set(), f"a ausência de {alvo} passou despercebida em {nome}"


def test_r2_mutante_fronteira_de_frase_em_ponto_e_virgula_e_dois_pontos_falha_no_oraculo(monkeypatch):
    import re as _re
    textos = dict(NAO_RESOLVE)
    nomes = ["lei_externa_ponto_e_virgula", "lei_externa_dois_pontos", "anexo_antes_dois_pontos_artigo",
             "anexo_antes_ponto_e_virgula"]
    for nome in nomes:
        assert _resolvidas(textos[nome]) == set(), nome
    monkeypatch.setattr(rem, "_FRONTEIRA", _re.compile(r";|:|" + rem._FRONTEIRA.pattern))  # o defeito original
    for nome in nomes:
        assert _resolvidas(textos[nome]) != set(), f"fronteira em ; e : passou despercebida em {nome}"


def test_r2_mutante_obra_igual_a_propria_tratada_como_externa_falha_no_controle_positivo(monkeypatch):
    texto = "Art. 14. Conforme a lei 6.404/1976, aplica-se o art. 5."
    assert _resolvidas(texto) == {(LSA_R, "art. 5º")}
    monkeypatch.setattr(rem, "_obra_da_mencao", lambda trecho: None)  # a igualdade deixa de ser reconhecida
    assert _resolvidas(texto) == set()


# --- B7 (R1): a existência estrutural não é prova do alvo (próprio e externo) ----------------------------------------------

L10303 = WorkKey("federal", "lei", "10303", 2001)


@pytest.fixture
def svc_duas_obras(svc6385):
    """Lei 6.385/1976 (a própria) e Lei 10.303/2001 (alvo externo), as duas capturadas e indexadas."""
    svc, rw = svc6385
    body = load_fixture("planalto_lei_10303_2001")
    entry = load_meta()["planalto_lei_10303_2001"]
    doc = parse_planalto(body, base_url="https://www.planalto.gov.br/ccivil_03/leis/")
    ext = svc.indexar_obra(source_id="planalto", work_key=L10303, document=doc, body=body, url=entry["url"],
                           fetched_at=entry.get("capturado_em"), work_date="2001-10-31", label="Lei nº 10.303/2001",
                           content_type="text/html; charset=windows-1252")
    return svc, rw, ext


TEXTO_EXT = "Art. 5º Ver o art. 1º da Lei 10.303/2001 e o art. 3º desta Lei."


def _res(svc, rw, texto=TEXTO_EXT):
    return {(r["alvo"]["obra"], r["alvo"]["caminho"]): r["resolvida"]
            for r in svc._remissoes_dispositivo(rw, "art5", texto)}


EXT_K, PROP_K = ("Lei 10.303/2001", "art. 1º"), ("Lei 6.385/1976", "art. 3º")


def test_b7_linha_de_base_alvo_proprio_e_externo_com_prova_completa(svc_duas_obras):
    svc, rw, ext = svc_duas_obras
    assert _res(svc, rw) == {EXT_K: True, PROP_K: True}


def test_b7_alvo_ambiguo_nunca_resolve_proprio_ou_externo(svc_duas_obras, monkeypatch):
    svc, rw, ext = svc_duas_obras
    monkeypatch.setattr(svc, "_obra_local", lambda w: ext)  # o mesmo objeto, para mutar o dispositivo
    for dono, caminho, chave in ((ext, "art1", EXT_K), (rw, "art3", PROP_K)):
        prov = next(p for p in dono.document.provisions if p.path == caminho)
        prov.ambiguous = True
        try:
            assert _res(svc, rw)[chave] is False, caminho
        finally:
            prov.ambiguous = False
    assert _res(svc, rw) == {EXT_K: True, PROP_K: True}


@pytest.mark.parametrize("quebra", ["sem_capture_id", "sem_sha256", "sha256_diverge", "quarentena", "incompleto",
                                    "sem_ano", "impedimento_documental", "identidade_nao_demonstrada",
                                    "identidade_divergente"])
def test_b7_cada_elo_da_prova_do_alvo_externo_e_necessario(svc_duas_obras, monkeypatch, quebra):
    svc, rw, ext = svc_duas_obras
    doc = ext.document
    variantes = {
        "sem_capture_id": replace(ext, capture_id=None),
        "sem_sha256": replace(ext, sha256=None),
        "sha256_diverge": replace(ext, sha256="0" * 64),
        "quarentena": replace(ext, quarantined=True),
        "incompleto": replace(ext, persisted_incomplete=True),
        "impedimento_documental": replace(ext, document=replace(doc, issues=list(doc.issues) + [
            Issue("TRUNCATED", None, "bloqueio documental", "document")])),
        "identidade_nao_demonstrada": replace(ext, document=replace(doc, title="Lei sem epígrafe reconhecível")),
        "identidade_divergente": replace(ext, document=replace(doc, title="LEI Nº 6.404, DE 15 DE DEZEMBRO DE 1976")),
    }
    if quebra == "sem_ano":
        monkeypatch.setattr(svc, "_obra_local", lambda w: None)
    else:
        monkeypatch.setattr(svc, "_obra_local", lambda w: variantes[quebra])
    assert _res(svc, rw)[EXT_K] is False
    assert _res(svc, rw)[PROP_K] is True  # a prova do alvo próprio é independente da do externo


def test_b7_captura_com_bytes_corrompidos_nao_resolve(svc_duas_obras):
    svc, rw, ext = svc_duas_obras
    blob = blobs.blob_path(ext.sha256, svc.home)
    original = blob.read_bytes()
    blob.write_bytes(original + b"adulterado")
    try:
        assert _res(svc, rw)[EXT_K] is False
    finally:
        blob.write_bytes(original)
    assert _res(svc, rw)[EXT_K] is True


def test_b7_cache_em_memoria_sem_captura_persistida_nao_prova(svc_duas_obras):
    svc, rw, ext = svc_duas_obras
    solto = replace(ext, capture_id=None, sha256=None)  # o que um cache sem captura autenticada teria
    assert svc._alvo_provado(solto, L10303, "art1") is False
    assert svc._alvo_provado(ext, L10303, "art1") is True


def test_b7_rota_ou_perfil_fora_da_matriz_nao_resolve(svc_duas_obras, monkeypatch):
    svc, rw, ext = svc_duas_obras
    monkeypatch.setattr(svc, "_rotas_admissiveis", lambda: {("camara_legin", "camara_atualizado")})
    assert _res(svc, rw) == {EXT_K: False, PROP_K: False}  # planalto fora da lista: nem a própria obra vale
    monkeypatch.setattr(svc, "_rotas_admissiveis", lambda: set())
    assert _res(svc, rw) == {EXT_K: False, PROP_K: False}
    monkeypatch.undo()
    # publicação original de OUTRA obra não é o texto consolidado a que a remissão se refere
    orig = replace(ext, source_id="camara_legin", document=replace(ext.document, profile="camara_original"))
    # R2-7: nenhum perfil é recusado em bloco; a prova do alvo (identidade, captura, rota, caminho) decide
    assert svc._alvo_provado(orig, L10303, "art1", externo=True) is True
    assert svc._alvo_provado(orig, L10303, "art1", externo=False) is True
    assert svc._alvo_provado(replace(orig, capture_id=None), L10303, "art1", externo=True) is False
    assert svc._alvo_provado(replace(orig, document=replace(orig.document, title="sem epígrafe")), L10303, "art1",
                             externo=True) is False
    prov = next(p for p in orig.document.provisions if p.path == "art1")
    prov.ambiguous = True
    try:
        assert svc._alvo_provado(orig, L10303, "art1", externo=True) is False  # caminho ambíguo continua recusado
    finally:
        prov.ambiguous = False
    monkeypatch.setattr(svc, "_rotas_admissiveis", lambda: {("planalto", "planalto")})
    assert svc._alvo_provado(orig, L10303, "art1", externo=True) is False  # rota fora da matriz continua recusada


def test_b7_alvo_proprio_tambem_exige_captura_e_identidade(svc_duas_obras):
    svc, rw, ext = svc_duas_obras
    assert svc._alvo_provado(replace(rw, capture_id=None), L6385, "art3") is False
    assert svc._alvo_provado(replace(rw, document=replace(rw.document, title="sem epígrafe")), L6385, "art3") is False
    assert svc._alvo_provado(rw, L6385, "art3") is True


def test_b7_mutante_so_estrutura_aceita_tudo_e_falha_nos_oraculos(svc_duas_obras, monkeypatch):
    """O defeito original: `existe` = documento não nulo e dispositivo encontrado. Com ele, o oráculo acima falha."""
    svc, rw, ext = svc_duas_obras
    from freoa_verifica.verify import _find_provision

    monkeypatch.setattr(svc, "_obra_local", lambda w: ext)

    monkeypatch.setattr(svc, "_alvo_provado", lambda alvo, work, p, **k: _find_provision(alvo.document, p) is not None)
    prov = next(p for p in ext.document.provisions if p.path == "art1")
    prov.ambiguous = True
    try:
        assert _res(svc, rw)[EXT_K] is True  # o mutante resolve alvo ambíguo: é exatamente o que o oráculo recusa
    finally:
        prov.ambiguous = False


# --- B8 (R1): `remissoes` cobre o texto EMITIDO e existe em toda saída de obter_dispositivo ----------------------------


def test_b8_remissao_depois_do_corte_nao_aparece_e_a_que_toca_o_corte_nao_resolve(svc6385, monkeypatch):
    import freoa_verifica.service as fachada
    svc, _ = svc6385
    completo = svc.obter_dispositivo(citacao="art. 9 da Lei 6.385/1976")
    assert completo["truncado"] is False and completo["remissoes"] == ESPERADO_ART9
    texto = completo["texto"]
    ponto = texto.index("art. 15")
    monkeypatch.setattr(fachada, "_DEFAULT_TEXT_LIMIT", ponto - 1)  # o corte cai ANTES da remissão
    r = svc.obter_dispositivo(citacao="art. 9 da Lei 6.385/1976")
    assert r["truncado"] is True and "art. 15" not in r["texto"]
    assert not any(x["resolvida"] for x in r["remissoes"])  # "§ 2o do" sem o artigo: nunca o artigo do próprio dispositivo
    monkeypatch.setattr(fachada, "_DEFAULT_TEXT_LIMIT", ponto + len("art. 1"))  # o corte cai NO MEIO ("art. 1" de 15)
    r = svc.obter_dispositivo(citacao="art. 9 da Lei 6.385/1976")
    assert r["truncado"] is True and r["texto"].endswith("art. 1")
    assert not any(x["resolvida"] for x in r["remissoes"])  # nunca resolve "art. 1" por truncar "art. 15"
    for x in r["remissoes"]:
        assert x["texto"] in r["texto"]  # tudo o que sai consta do texto emitido


def test_b8_toda_saida_traz_remissoes_inclusive_as_recusas(svc6385):
    svc, _ = svc6385
    recusas = [svc.obter_dispositivo(citacao="art. 9 da Lei 6.385/1976", versao="invalida"),
               svc.obter_dispositivo(citacao="art. 9 da Lei 6.385/1976", fonte="fonte_que_nao_existe"),
               svc.obter_dispositivo(citacao="art. 9999 da Lei 6.385/1976"),
               svc.obter_dispositivo(citacao="lixo"), svc.obter_dispositivo()]
    assert recusas[0]["motivo"] == "versao_invalida" and recusas[1]["motivo"] == "fonte_invalida"
    for r in recusas:
        assert r["remissoes"] == [], r


def test_b8_recusa_por_autenticacao_de_evidencia_tambem_traz_remissoes(svc6385):
    svc, rw = svc6385
    blob = blobs.blob_path(rw.sha256, svc.home)
    original = blob.read_bytes()
    blob.write_bytes(original + b"adulterado")
    try:
        r = svc.obter_dispositivo(citacao="art. 9 da Lei 6.385/1976")
    finally:
        blob.write_bytes(original)
    assert r["status"] == "unavailable" and r["remissoes"] == []
    assert svc.obter_dispositivo(citacao="art. 9 da Lei 6.385/1976")["remissoes"] == ESPERADO_ART9


def test_r2_8_recusa_por_derivados_incompativeis_traz_remissoes(svc6385, monkeypatch):
    import freoa_verifica.service as fachada
    svc, _ = svc6385
    monkeypatch.setattr(fachada._derivados, "compativel", lambda conn: False)
    r = svc.obter_dispositivo(citacao="art. 9 da Lei 6.385/1976")
    assert r["status"] == "indisponivel" and r["reason_code"] == "ACERVO_DESATUALIZADO"
    assert r["remissoes"] == []


def test_r2_8_identidade_ambigua_traz_remissoes(svc6385, monkeypatch):
    from freoa_verifica.verify import SourceAmbiguous
    svc, _ = svc6385

    def ambigua(*a, **k):
        raise SourceAmbiguous([{"work_id": "a"}, {"work_id": "b"}])
    monkeypatch.setattr(svc, "_obter_dispositivo_autenticado", ambigua)
    r = svc.obter_dispositivo(citacao="art. 9 da Lei 6.385/1976")
    assert r["status"] == "ambigua" and r["motivo"] == "IDENTIDADE_AMBIGUA"
    assert r["remissoes"] == []


def test_r2_8_o_ponto_comum_garante_remissoes_em_qualquer_retorno_da_fachada():
    from freoa_verifica.service import _final_da_fachada
    for out in ({"status": "ambigua"}, {"status": "indisponivel", "reason_code": "ACERVO_DESATUALIZADO"},
                {"status": "formato_invalido"}, {"status": "unknown", "texto": None}):
        assert _final_da_fachada("obter_dispositivo", dict(out))["remissoes"] == []
    assert "remissoes" not in _final_da_fachada("resolver_citacao", {"status": "encontrada"})


def test_r2_6_nota_cortada_pelo_truncamento_no_servico_nao_resolve(svc6385):
    svc, rw = svc6385
    nota = "(Vide art. 3º desta Lei, conforme explicacao editorial adicional)"
    integral = f"Art. 5º Ver o art. 1º desta Lei. {nota}"
    emitido = integral[:-1]  # o corte retirou o parêntese que fecha a nota
    por = {r["alvo"]["caminho"]: r["resolvida"]
           for r in svc._remissoes_dispositivo(rw, "art5", emitido, truncado=True, integral=integral)}
    assert por == {"art. 1º": True}  # a remissão da nota não aparece, nem resolvida
    sem_integral = {r["alvo"]["caminho"]: r["resolvida"]
                    for r in svc._remissoes_dispositivo(rw, "art5", emitido, truncado=True)}
    assert sem_integral == {"art. 1º": True}


def test_b8_invariante_final_descarta_remissao_fora_do_texto_emitido():
    from freoa_verifica.service import _remissoes_no_texto_emitido as fim
    base = {"status": "encontrada", "texto": "Art. 1º Ver art. 2º desta Lei."}
    ok = {"texto": "art. 2º desta Lei", "alvo": {"obra": "Lei 1/2000", "caminho": "art. 2º"}, "resolvida": True}
    fora = {"texto": "art. 9º desta Lei", "alvo": {"obra": "Lei 1/2000", "caminho": "art. 9º"}, "resolvida": True}
    assert fim({**base, "remissoes": [ok, fora]})["remissoes"] == [ok]
    assert fim({**base, "status": "unavailable", "remissoes": [ok]})["remissoes"] == []
    assert fim({**base, "texto": None, "remissoes": [ok]})["remissoes"] == []
    assert fim({"status": "indisponivel"})["remissoes"] == []
    assert fim({**base})["remissoes"] == []
