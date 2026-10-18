"""Parse de fixtures gravadas por conector."""

from __future__ import annotations

import json

import pytest

from freoa_verifica.connectors.bcb import BcbConnector
from freoa_verifica.connectors.cvm_colegiado import CvmColegiadoConnector, _parse_rss
from freoa_verifica.connectors.cvm_normas import CvmNormasConnector, _parse_ato_html
from freoa_verifica.connectors.datajud import DatajudConnector
from freoa_verifica.connectors.planalto import PlanaltoConnector, generate_lei_urls, urls_for_work
from freoa_verifica.connectors.senado import SenadoConnector, _docs_from_payload
from freoa_verifica.connectors.stf import StfConnector, _parse_aba_decisoes
from freoa_verifica.connectors.stj import StjConnector
from freoa_verifica.connectors.tcu import TcuConnector
from freoa_verifica.connectors.tjsp import TjspConnector, _parse_results
from freoa_verifica.connectors.base import registry
from freoa_verifica.transport import Response
from tests.fixture_util import load_fixture


def _resp(key: str, url: str = "https://example.com/", mime: str = "application/json") -> Response:
    body = load_fixture(key)
    import hashlib
    from datetime import datetime, timezone

    return Response(
        url=url,
        final_url=url,
        status=200,
        headers={"content-type": mime},
        body=body,
        sha256=hashlib.sha256(body).hexdigest(),
        fetched_at=datetime.now(timezone.utc).isoformat(),
        redirects=[],
        mime=mime,
    )


def test_registry_has_ten_connectors():
    reg = registry()
    expected = {
        "planalto",
        "senado",
        "cvm_normas",
        "cvm_colegiado",
        "bcb",
        "stj",
        "datajud",
        "tcu",
        "tjsp",
        "stf",
    }
    assert expected <= set(reg)


def test_planalto_url_generator_and_known_table():
    urls = urls_for_work("LEI", 6404, 1976)
    assert any("l6404" in u for u in urls)
    gen = generate_lei_urls(14133, 2021)
    assert any("_ato2019-2022/2021/lei/" in u for u in gen)
    conn = PlanaltoConnector()
    cand = conn.resolve({"tipo": "LEI", "numero": 6404, "ano": 1976})
    assert cand is not None
    assert cand.metadata.get("urls")
    # parse delega ao perfil planalto (coberto pelos testes M2); aqui só resolve/URLs


def test_senado_lista_fixture():
    payload = json.loads(load_fixture("senado_lei_10303_2001").decode("utf-8"))
    docs = _docs_from_payload(payload)
    assert docs
    conn = SenadoConnector()
    parsed = conn.parse(
        _resp(
            "senado_lei_10303_2001",
            "https://legis.senado.leg.br/dadosabertos/legislacao/lista",
        )
    )
    assert parsed.profile == "senado_norma"
    assert "10.303" in parsed.title or "10303" in parsed.title.replace(".", "")


def test_bcb_busca_fixture():
    payload = json.loads(load_fixture("bcb_busca_cmn_4966").decode("utf-8"))
    assert payload["TotalRows"] >= 1
    row = payload["Rows"][0]
    assert "4966" in str(row.get("NumeroOWSNMBR") or "")
    # resolve offline: monta candidato a partir da chave (sem rede)
    cand = BcbConnector().resolve({"tipo": "Resolução CMN", "numero": 4966})
    # se a API estiver inacessível, resolve ainda devolve candidato sintético
    assert cand is not None
    assert "4966" in (cand.key or "")
    assert "exibenormativo" in (cand.url or "")


def test_cvm_normas_page_html():
    doc = _parse_ato_html(
        load_fixture("cvm_resol_080_page"),
        base_url="https://conteudo.cvm.gov.br/legislacao/resolucoes/resol080.html",
    )
    assert "80" in doc.title
    assert doc.ementa or doc.text


def test_cvm_colegiado_rss():
    items = _parse_rss(load_fixture("cvm_decisoes_feed"))
    assert items
    conn = CvmColegiadoConnector()
    parsed = conn.parse(
        _resp("cvm_decisoes_feed", "https://conteudo.cvm.gov.br/feed/decisoes.xml", mime="application/rss+xml")
    )
    assert parsed.court == "CVM"


def test_tcu_json_parse():
    conn = TcuConnector()
    items = json.loads(load_fixture("tcu_acordaos_page0").decode("utf-8"))
    assert isinstance(items, list) and items
    payload = json.dumps(items[0]).encode("utf-8")
    import hashlib
    from datetime import datetime, timezone

    resp = Response(
        url="https://dados-abertos.apps.tcu.gov.br/api/acordao/recupera-acordaos",
        final_url="https://dados-abertos.apps.tcu.gov.br/api/acordao/recupera-acordaos",
        status=200,
        headers={"content-type": "application/json"},
        body=payload,
        sha256=hashlib.sha256(payload).hexdigest(),
        fetched_at=datetime.now(timezone.utc).isoformat(),
        redirects=[],
        mime="application/json",
    )
    parsed = conn.parse(resp)
    assert parsed.court == "TCU"
    assert parsed.official_id


def test_tjsp_results_positive_and_negative():
    pos = _parse_results(load_fixture("tjsp_busca_acordo_acionistas"), source_id="tjsp", limite=5)
    assert pos
    assert pos[0].metadata.get("cdAcordao")
    neg = _parse_results(load_fixture("tjsp_busca_negativa"), source_id="tjsp", limite=5)
    assert neg == []


def test_stf_aba_decisoes_and_tema():
    items = _parse_aba_decisoes(
        load_fixture("stf_adi_7000_decisoes"),
        base="https://portal.stf.jus.br/processos/abaDecisoes.asp?incidente=6255858",
    )
    assert items
    assert any(i.get("docs") for i in items)
    conn = StfConnector()
    parsed = conn.parse(
        _resp(
            "stf_tema_1000",
            "https://sistemas.stf.jus.br/repgeral/votacao?tema=1000",
            mime="application/json",
        )
    )
    assert parsed.kind == "repercussao_geral"
    assert str(parsed.official_id) == "1000" or str(parsed.metadata.get("numeroTema")) == "1000"


def test_datajud_parse_proceeding():
    conn = DatajudConnector()
    parsed = conn.parse(
        _resp(
            "datajud_tjsp_sample",
            "https://api-publica.datajud.cnj.jus.br/api_publica_tjsp/_search",
        )
    )
    assert parsed.kind == "proceeding"
    assert parsed.cnj_number or parsed.official_id


def test_stj_espelho_parse():
    conn = StjConnector()
    parsed = conn.parse(
        _resp(
            "stj_espelhos_amostra",
            "https://dadosabertos.web.stj.jus.br/",
        )
    )
    assert parsed.court == "STJ"
    assert parsed.metadata.get("reuse_policy")


def test_cvm_normas_resolve_urls():
    cand = CvmNormasConnector().resolve({"tipo": "resolucoes", "numero": 80})
    assert cand is not None
    assert "resol080" in (cand.url or "")
    assert cand.metadata["docx_consolid"].endswith("consolid.docx")
