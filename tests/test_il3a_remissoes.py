"""IL.3-a, A2: `remissoes[]` em `obter_dispositivo` (matriz IL.1, seção 1, capacidade e; il3-especificacao A2).

Oráculos escritos à mão, independentes do extrator: cada caso traz o conjunto exato esperado de (obra, caminho, resolvida).
Falso positivo (resolvida: true fora do esperado) é confirmação indevida (matriz, seção 2, iii).
"""

from __future__ import annotations

import asyncio
import json

import pytest

from freoa_verifica import remissoes as rem
from freoa_verifica.aliases import WorkKey
from freoa_verifica.parsers.planalto import parse_planalto
from freoa_verifica.service import Verifica
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


def _resolvidas(texto, art="art14", obra=LSA, notas=(), truncado=False):
    saida = rem.remissoes(texto, obra, lambda w, p: True, art, notas=notas, truncado=truncado)
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
]


@pytest.mark.parametrize("nome,texto", NAO_RESOLVE, ids=[c[0] for c in NAO_RESOLVE])
def test_b6_classe_nunca_resolve(nome, texto):
    assert _resolvidas(texto) == set(), nome


def test_b6_controles_positivos_da_mesma_forma_continuam_resolvendo():
    assert _resolvidas("Art. 14. Ver art. 5 desta Lei.") == {(LSA_R, "art. 5º")}
    assert _resolvidas("Art. 14. Ver art. 5, § 1º, desta Lei.") == {(LSA_R, "art. 5º, § 1º")}
    assert _resolvidas("Art. 14. Ver art. 5º, inciso I, desta Lei.") == {(LSA_R, "art. 5º, inciso I")}
    assert _resolvidas("Art. 14. Ver o inciso I do art. 5º desta Lei.") == {(LSA_R, "art. 5º, inciso I")}
    assert _resolvidas("Art. 14. Ver art. 3º da Lei 8.987/1995.") == {("Lei 8.987/1995", "art. 3º")}
    assert _resolvidas("Art. 14. O disposto no caput não se aplica.") == {(LSA_R, "art. 14, caput")}
    assert _resolvidas("Art. 14. O disposto no § 1º deste artigo.") == {(LSA_R, "art. 14, § 1º")}


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
    ("_RESIDUO", "inciso_sem_palavra"), ("_RESIDUO", "inciso_abreviado"), ("_RESIDUO", "paragrafo_solto_com_inciso"),
    ("_PREFIXO_RESIDUAL", "inciso_antes_abreviado"), ("_ANEXO_DEPOIS", "anexo_numerado"),
    ("_ANEXO_DEPOIS", "paragrafo_solto_de_anexo"), ("_DEMONSTRATIVO", "dessa_lei"),
    ("_DEMONSTRATIVO", "paragrafo_desse_artigo"), ("_NOTA_COLCHETES", "nota_editorial_colchetes"),
    ("_OBRA_NUMERADA", "lei_minuscula_antes"), ("_OBRA_NUMERADA", "caput_em_contexto_de_lei_numerada"),
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
