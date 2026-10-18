"""B1: o ADCT tem escopo próprio e não se confunde com o texto permanente da CF."""

from __future__ import annotations

import pytest

from freoa_verifica.aliases import WorkKey
from freoa_verifica.citation import extract
from freoa_verifica.parsers.model import AmbiguousProvision, ParsedDocument, Provision, Redaction
from freoa_verifica.parsers.paths import adct_scope_from_heading, is_article_path
from freoa_verifica.parsers.planalto import parse_planalto
from freoa_verifica.parsers.sentinel import run_sentinels
from freoa_verifica.store.db import connect
from freoa_verifica.verify import MemoryResolver, populate_from_parsed, verificar

CF_KEY = WorkKey("federal", "constituicao", "1988", 1988)
ADCT_HEADING = "ATO DAS DISPOSIÇÕES CONSTITUCIONAIS TRANSITÓRIAS"
T_CF5 = "Todos são iguais perante a lei, sem distinção de qualquer natureza."
T_CF60 = "A Constituição poderá ser emendada mediante proposta de um terço dos membros da Câmara dos Deputados."
T_ADCT5 = "Os mandatos dos governadores e dos prefeitos eleitos em quinze de novembro de 1988 terminarão em 1990."
T_ADCT60 = "Nos dez primeiros anos da promulgação da Constituição, o Poder Público desenvolverá esforços para eliminar o analfabetismo."


def _p(text: str) -> str:
    return f"<p>{text}</p>\n"


def cf_html() -> str:
    toc = (
        _p("Constituição da República Federativa do Brasil de 1988")
        + _p("Preâmbulo")
        + _p("TÍTULO I")
        + _p(f'<a href="#adct">{ADCT_HEADING}</a>')
    )
    body = (
        _p("PREÂMBULO")
        + _p("TÍTULO I")
        + _p(f'<a name="art5"></a>Art. 5º {T_CF5}')
        + "".join(_p(f'<a name="art{n}"></a>Art. {n}. Texto do artigo {n}.') for n in range(6, 60))  # evita o sentinela de truncamento
        + _p("TÍTULO IV")
        + _p(f'<a name="art60"></a>Art. 60. {T_CF60}')
        + _p(f'<a name="adct"></a>{ADCT_HEADING}')
        + _p(f"Art. 5º {T_ADCT5}")
        + _p(f"Art. 60. {T_ADCT60}")
    )
    return f"<html><head><title>CF</title></head><body>{toc}{body}</body></html>"


def _paths(doc):
    return {p.path for p in doc.provisions}


def test_cf_adct_escopo_separado():
    doc = parse_planalto(cf_html())
    assert {"art5", "art60", "adct/art5", "adct/art60"} <= _paths(doc)
    assert doc.current_text("art5") == T_CF5
    assert doc.current_text("art60") == T_CF60
    assert doc.current_text("adct/art5") == T_ADCT5
    assert doc.current_text("adct/art60") == T_ADCT60
    assert not [p for p in doc.provisions if p.ambiguous]
    assert is_article_path("adct/art5")


def test_cf_sumario_adct_nao_abre_escopo():
    doc = parse_planalto(cf_html())
    assert doc.current_text("art5") == T_CF5  # a CF não foi jogada no ADCT
    assert {p for p in _paths(doc) if p.startswith("adct/")} == {"adct/art5", "adct/art60"}
    assert adct_scope_from_heading(ADCT_HEADING) == "adct"
    assert adct_scope_from_heading("Veja o Ato das Disposições Constitucionais Transitórias.") is None


def test_sentinela_escopos_distintos_no_mesmo_caminho_nao_substituem():
    reds = [Redaction("a", False, 0, scope=""), Redaction("b", False, 1, scope="adct")]
    doc = ParsedDocument("planalto", "x", "", None, "", provisions=[Provision("art5", "Art. 5º", "", [], reds)])
    issues = run_sentinels(doc)
    assert [i.code for i in issues].count("SCOPE_COLLISION") == 1
    with pytest.raises(AmbiguousProvision):
        doc.current_text("art5")


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "fv"
    home.mkdir()
    monkeypatch.setenv("FV_HOME", str(home))
    conn = connect(home / "verifica.sqlite3")
    body = cf_html().encode("utf-8")
    rw = populate_from_parsed(
        conn, source_id="planalto", work_key=CF_KEY, document=parse_planalto(body), body=body,
        url="https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm",
        fetched_at="2026-10-18T00:00:00Z", work_date="1988-10-05", label="Constituição Federal",
    )
    resolver = MemoryResolver()
    resolver.add(rw)
    yield conn, resolver
    conn.close()


def test_verifica_cf_art60_trecho_adct_nao_verified(env):
    conn, resolver = env
    ok = verificar("art. 60 da CF", trecho=T_CF60, repo=conn, resolver=resolver)
    assert ok.text.status == "verified"  # controle positivo
    bad = verificar("art. 60 da CF", trecho=T_ADCT60, repo=conn, resolver=resolver)
    assert bad.text.status != "verified"
    adct = verificar("art. 60 do ADCT", trecho=T_ADCT60, repo=conn, resolver=resolver)
    assert adct.text.status == "verified"


@pytest.mark.parametrize(
    "texto",
    ["art. 5º do ADCT", "art. 5º do Ato das Disposições Constitucionais Transitórias", "ADCT, art. 5º"],
)
def test_extrator_adct(texto):
    (c,) = extract(texto)
    assert c.work == CF_KEY and c.path == "adct/art5" and c.confidence == "exata"


def test_extrator_art60_cf_segue_permanente():
    (c,) = extract("art. 60 da CF")
    assert c.path == "art60"
