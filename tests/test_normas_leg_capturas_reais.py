"""0085 sobre capturas reais de normas.leg.br (14/11/2026, `scripts/capturar_fixture.py --conector normas_leg`).

Bytes intactos, servidos por dublê com o transporte desligado; conferem o contrato observado
(URN só com o ano, ausência explícita, reedição de MP, texto Original da LC 118/2005).
"""
from __future__ import annotations

import hashlib
import json
from urllib.parse import unquote, urlencode

import pytest

from freoa_verifica.connectors import normas_leg as nl
from freoa_verifica.connectors.base import Unavailable
from tests._camara_util import RelogioFalso, Transporte, resposta
from tests.fixture_util import fixture_path, load_fixture, load_meta

ROBOTS = nl.BASE + "/robots.txt"
BIN_LC118 = nl.BASE + "/api/public/binario/2d8f8857-d7d2-4f31-b1ad-6e64cc27e7fe/texto"


def _api(urn: str) -> str:
    return nl.BASE + "/api/public/normas?" + urlencode({"urn": urn, "tipo_documento": "maior-detalhe"})


def _real(chave: str, url: str, mime: str):
    corpo = load_fixture(chave)
    meta = load_meta()[chave]
    assert hashlib.sha256(corpo).hexdigest() == meta["sha256"]
    assert meta["categoria"] == "captura_real" and unquote(meta["url"]) == unquote(url)
    return resposta(url, corpo, mime=mime)


def _conector(tmp_path, rotas: dict):
    relogio = RelogioFalso()
    rotas = {ROBOTS: _real("normas_leg_robots", ROBOTS, "text/plain"), **rotas}
    tr = Transporte(relogio, rotas)
    portao = nl.NormasPortao(tr, home=tmp_path, relogio=relogio)
    return nl.NormasLegConnector(home=tmp_path, portao=portao), tr


def test_fixtures_reais_estao_no_manifesto():
    for chave in ("normas_leg_robots", "normas_leg_meta_lc118", "normas_leg_meta_mp2158",
                  "normas_leg_ausente", "normas_leg_bin_lc118_original"):
        assert fixture_path(chave).exists()
        assert load_meta()[chave]["categoria"] == "captura_real"


def test_robots_real_permite_tudo():
    linhas = [x.strip() for x in load_fixture("normas_leg_robots").decode("utf-8").splitlines() if x.strip()]
    assert linhas == ["User-agent: *", "Allow: /"]


def test_ausencia_real_e_zero(tmp_path):
    urn = "urn:lex:br:federal:lei:2099;999999"
    con, _ = _conector(tmp_path, {_api(urn): _real("normas_leg_ausente", _api(urn), "application/json")})
    assert json.loads(load_fixture("normas_leg_ausente")) == {"urn": urn}
    assert con.search("", tipo="lei", numero=999999, ano=2099) == []


def test_mp_reeditada_real(tmp_path):
    urn = "urn:lex:br:federal:medida.provisoria:2001;2158-35"
    con, _ = _conector(tmp_path, {_api(urn): _real("normas_leg_meta_mp2158", _api(urn), "application/json")})
    cand = con.search("", tipo="medida provisória", numero="2158-35", ano=2001)[0]
    assert cand.metadata["urn"].startswith("urn:lex:br:federal:medida.provisoria:2001-08-24;2158-35")
    versoes = {e["version"] for e in cand.metadata["encoding"]}
    assert "Original" in versoes
    for e in cand.metadata["encoding"]:
        assert e["contentUrl"].startswith(nl.BASE + "/api/public/binario/")
        assert e["legislationLegalValue"] == "UnofficialLegalValue"


def test_lc118_real_metadados_texto_e_dispositivo(tmp_path):
    urn = "urn:lex:br:federal:lei.complementar:2005;118"
    con, tr = _conector(tmp_path, {
        _api(urn): _real("normas_leg_meta_lc118", _api(urn), "application/json"),
        BIN_LC118: _real("normas_leg_bin_lc118_original", BIN_LC118, "text/html"),
    })
    cand = con.search("Lei Complementar 118/2005")[0]
    assert cand.key == "normas_leg:urn:lex:br:federal:lei.complementar:2005-02-09;118"
    assert cand.metadata["license"] == "https://creativecommons.org/licenses/by/4.0/"
    assert [e["version"] for e in cand.metadata["encoding"]] == ["Original"]
    doc = con.parse(con.fetch(cand))
    assert doc.profile == "normas_leg" and not doc.quarantined
    art3 = doc.provision("art3")
    assert art3 is not None
    assert "inciso I do art. 168 da Lei nº 5.172" in art3.current_redaction().text
    meta = json.loads(next(b.text for b in doc.editorial_blocks if b.kind == "normas_leg_metadados"))
    assert meta["version"] == "Original" and meta["atribuicao"]["texto"] == nl.ATRIBUICAO
    assert tr.chamadas[-1][0] == BIN_LC118


def test_identidade_real_divergente_e_recusada(tmp_path):
    # A resposta real da LC 118 servida para uma consulta de outra norma não vira candidato.
    urn = "urn:lex:br:federal:lei.complementar:2005;119"
    con, _ = _conector(tmp_path, {_api(urn): resposta(_api(urn), load_fixture("normas_leg_meta_lc118"),
                                                      mime="application/json")})
    with pytest.raises(Unavailable, match="resposta_inesperada"):
        con.search("", tipo="lei complementar", numero=119, ano=2005)


@pytest.mark.parametrize("rotulos", [
    {"source_id": "planalto", "profile": "planalto"},
    {"source_id": "planalto", "profile": "planalto", "sem_bloco": True},
    {"source_id": "senado", "profile": "camara_atualizado"},
    {"source_id": "planalto", "profile": "planalto", "url": "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp118.htm"},
    {"source_id": "normas_leg", "profile": "planalto", "sem_bloco": True,
     "url": "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp118.htm"},
])
def test_troca_de_rotulos_nao_promove_a_verified(tmp_path, rotulos):
    # Auditoria 0085, B1: bytes reais da LC 118, rótulos trocados; a procedência (metadados ou host)
    # mantém o gate fechado.
    from dataclasses import replace

    from freoa_verifica.aliases import WorkKey
    from freoa_verifica.service import Verifica
    from freoa_verifica.verify import MemoryResolver, verificar
    urn = "urn:lex:br:federal:lei.complementar:2005;118"
    con, _ = _conector(tmp_path, {
        _api(urn): _real("normas_leg_meta_lc118", _api(urn), "application/json"),
        BIN_LC118: _real("normas_leg_bin_lc118_original", BIN_LC118, "text/html"),
    })
    resp = con.fetch(con.search("Lei Complementar 118/2005")[0])
    doc = con.parse(resp)
    doc.profile = rotulos["profile"]
    if rotulos.get("sem_bloco"):
        doc.editorial_blocks = [b for b in doc.editorial_blocks if b.kind != "normas_leg_metadados"]
    key = WorkKey("federal", "lei_complementar", "118", 2005)
    with Verifica(home=tmp_path / "db") as svc:
        rw = svc.indexar_obra(source_id=rotulos["source_id"], work_key=key, document=doc, body=resp.body,
                              url=rotulos.get("url", resp.url), fetched_at=resp.fetched_at,
                              content_type="text/html; charset=utf-8")
        rw = replace(rw, source_id=rotulos["source_id"]) if getattr(rw, "source_id", None) else rw
        resolver = MemoryResolver()
        resolver.add(rw)
        trecho = doc.provision("art3").current_redaction().text
        out = verificar("art. 3º da Lei Complementar 118/2005", trecho=trecho, resolver=resolver)
    assert "verified" not in {out.identity.status, out.text.status, out.temporal.status}
    assert out.text.reason_code == "rota_nao_qualificada"


def test_publicacao_original_de_normas_leg_e_entregue(tmp_path, monkeypatch):
    # Auditoria 0085, I3: o texto `Original` (publicação no DOU, declarada nos metadados) é entregue
    # como publicação original, com atribuição; antes caía em `primeira_publicacao_nao_identificada`.
    from freoa_verifica.service import Verifica
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    urn = "urn:lex:br:federal:lei.complementar:2005;118"
    con, _ = _conector(tmp_path / "home", {
        _api(urn): _real("normas_leg_meta_lc118", _api(urn), "application/json"),
        BIN_LC118: _real("normas_leg_bin_lc118_original", BIN_LC118, "text/html"),
    })
    with Verifica(home=tmp_path / "home") as svc:
        svc._connectors["normas_leg"] = con
        out = svc.obter_dispositivo(citacao="art. 3º da Lei Complementar 118/2005",
                                    versao="publicacao_original", fonte="normas_leg")
    assert out["status"] == "encontrada", out
    assert "inciso I do art. 168" in (out.get("texto") or "")
