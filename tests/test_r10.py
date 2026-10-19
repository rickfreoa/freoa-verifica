"""Normalização local: flexão mínima, frases e ampliação explícita."""
import pytest

from freoa_verifica.search import normalize_fts_query
from tests.test_r9 import corpus  # noqa: F401


@pytest.mark.parametrize("query, expected", [
    ("acordo", '"acordo"*'), ("acordos", '"acordo"*'),
    ("acionista", '"acionista"*'), ("acionistas", '"acionista"*'),
    ("ação", '"acao"*'), ("ações", '"acoes"'),
    ("capital", '"capital"*'), ("capitais", '"capita"*'),
    ("papel", '"papel"*'), ("papéis", '"pape"*'),
    ("credor", '"credor"*'), ("credores", '"credor"*'),
    ("voz", '"voz"'), ("vozes", '"vozes"'),
    ("mês", '"mes"'), ("meses", '"meses"'),
    ("bem", '"bem"'), ("bens", '"bens"'),
    ('"tag along"', '"tag along"'), ("tag along", '"tag" AND "along"*'),
    ('acordo "de acionistas"', '"acordo"* AND "de acionistas"'),
    ("ACÓRDÃOS", '"acordao"*'), ("cães", '"caes"'),
    ("homens", '"home"*'), ("de à às e para", ''), ("", ''),
    ("acordo-de-acionistas", '"acordo"* AND "acionista"*'),
    ('acordo "acionistas', '"acordo"* AND "acionistas"'),
    ('"a ação"', '"a ação"'), ("abc* OR NEAR(x)", '"abc" AND "or" AND "near"* AND "x"'),
    ("'' : ()", ''), ("2026", '"2026"'),
])
def test_normalize(query, expected):
    assert normalize_fts_query(query) == expected


def test_all_stopwords_and_expansion():
    assert normalize_fts_query("de da do das dos e a o as os em no na nos nas por para com que ao aos à às") == ''
    assert normalize_fts_query('acordos "tag along"', expanded=True) == '"acordo"* OR "tag along"'


def test_juris_normal_expanded_quotes_and_pagination(corpus):
    # O plural recupera o singular existente no acervo sintético.
    result = corpus.pesquisar_jurisprudencia("acordos dos acionistas", tribunais=["stj"], limite=1)
    assert result["modo_busca"] == "normal" and len(result["itens"]) == 1
    expanded = corpus.pesquisar_jurisprudencia("acordos inexistente", tribunais=["stj"], limite=1)
    assert expanded["modo_busca"] == "ampliada" and expanded["cursor"]
    page2 = corpus.pesquisar_jurisprudencia("acordos inexistente", tribunais=["stj"], limite=1, cursor=expanded["cursor"])
    assert page2["modo_busca"] == "ampliada"
    assert page2["itens"][0]["id"] != expanded["itens"][0]["id"]
    assert not corpus.pesquisar_jurisprudencia('"acordos de acionistas"')["itens"]
    assert len(corpus.pesquisar_jurisprudencia('"tag along"')["itens"]) == 9
    assert not corpus.pesquisar_jurisprudencia('"along tag"')["itens"]
    assert not corpus.pesquisar_jurisprudencia('de e a')["itens"]
    assert not corpus.pesquisar_jurisprudencia('acordos', desde="2030-01-01")["itens"]


def test_fallback_uses_bm25_and_does_not_replace_exhausted_and_page(corpus):
    with corpus.conn:
        corpus.conn.execute("UPDATE fts_decision SET ementa='acordos', inteiro_teor='' WHERE official_id='STJ-0'")
        corpus.conn.execute("UPDATE fts_decision SET ementa='debentures', inteiro_teor='' WHERE official_id='STJ-1'")
        corpus.conn.execute("UPDATE fts_decision SET ementa='acordos debentures', inteiro_teor='' WHERE official_id='STJ-2'")
    normal = corpus.pesquisar_jurisprudencia('acordos debentures', tribunais=['stj'], limite=1)
    # 1.2.0 (auditoria): há complemento OR depois do único AND, logo existe próxima página (antes encerrava cedo).
    assert normal['modo_busca'] == 'normal' and normal['cursor'] is not None
    from freoa_verifica.service import _encode_cursor
    exhausted = corpus.pesquisar_jurisprudencia('acordos debentures', tribunais=['stj'], cursor=_encode_cursor(1))
    # Decisão 0025: o AND esgotado é completado pelo OR, sempre marcado como parcial.
    assert exhausted['modo_busca'] == 'normal'
    assert exhausted['itens'] and {i['correspondencia'] for i in exhausted['itens']} == {'parcial'}
    expanded = corpus.pesquisar_jurisprudencia('acordos inexistente', tribunais=['stj'])
    rows = corpus.conn.execute(
        "SELECT d.id FROM fts_decision f JOIN decision d ON d.official_id=f.official_id AND d.court=f.court "
        "WHERE fts_decision MATCH ? AND f.court='STJ' ORDER BY bm25(fts_decision)",
        ('"acordo"* OR "inexistente"*',)).fetchall()
    assert [i['id'] for i in expanded['itens']] == [row[0] for row in rows]


def test_legislation_normal_expanded_and_exact(verifica_populada):
    svc, _, _ = verifica_populada
    normal = svc.buscar_legislacao("alienações de controle")
    assert normal["modo_busca"] == "normal" and normal["itens"]
    expanded = svc.buscar_legislacao("alienações inexistente")
    assert expanded["modo_busca"] == "ampliada" and expanded["itens"]
    assert not svc.buscar_legislacao('"alienações de controle"')["itens"]
    assert not svc.buscar_legislacao("de e a")["itens"]
