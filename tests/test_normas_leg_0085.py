"""0085. Fixtures sintéticas geradas por payload()/html(); finalidade: contrato e barreiras offline.

Não são capturas do portal nem integram um conjunto-ouro; nenhuma requisição real.
"""
from __future__ import annotations

import json
from urllib.parse import urlencode

import pytest

from freoa_verifica.aliases import WorkKey
from freoa_verifica.connectors import normas_leg as nl, camara_robots as rb
from freoa_verifica.connectors.base import Unavailable, registry
from freoa_verifica.connectors.guarda import da_chamada
from freoa_verifica.service import Verifica
from tests._camara_util import RelogioFalso, Transporte, resposta

ROBOTS = nl.BASE + "/robots.txt"
TEXT = nl.BASE + "/api/public/binario/12345678-1234-1234-1234-123456789abc/texto"
KEY = WorkKey("federal", "lei", "6404", 1976)


def api(urn="urn:lex:br:federal:lei:1976;6404"):
    return nl.BASE + "/api/public/normas?" + urlencode({"urn": urn, "tipo_documento": "maior-detalhe"})


def payload(urn="urn:lex:br:federal:lei:1976-12-15;6404", **extra):
    return {"@type": "Legislation", "legislationIdentifier": urn, "name": "Lei nº 6.404/1976",
            "abstract": "Ementa sintética", "license": "https://creativecommons.org/licenses/by/4.0/",
            "encoding": [{"version": "Current", "name": "Compilação Monovigente na CD",
                          "contentUrl": TEXT.replace("/public/", "/"), "datePublished": "1976-12-17",
                          "legislationLegalValue": "UnofficialLegalValue",
                          "license": "https://creativecommons.org/licenses/by/4.0/"}], **extra}


def html(title="LEI Nº 6.404, DE 15 DE DEZEMBRO DE 1976"):
    return (f"<html><body><p>{title}</p><p>Art. 1º A companhia terá capital dividido em ações.</p>"
            "<p>Brasília, 15 de dezembro de 1976.</p></body></html>").encode()


def ambiente(tmp_path, *, data=None, robots="User-agent: *\nAllow: /\n", url=None):
    clock = RelogioFalso()
    target = url or api()
    tr = Transporte(clock, {ROBOTS: resposta(ROBOTS, robots.encode(), mime="text/plain"),
                           target: resposta(target, json.dumps(payload() if data is None else data).encode(), mime="application/json"),
                           TEXT: resposta(TEXT, html())})
    gate = nl.NormasPortao(tr, home=tmp_path, relogio=clock)
    return nl.NormasLegConnector(home=tmp_path, portao=gate), tr, clock


@pytest.mark.parametrize("kind,number,year,expected", [
    ("LEI", "6.404", 1976, "lei:1976;6404"), ("lei complementar", "118", 2005, "lei.complementar:2005;118"),
    ("LCP", "118", 2005, "lei.complementar:2005;118"), ("decreto", "3000", 1999, "decreto:1999;3000"),
    ("DEL", "2848", 1940, "decreto.lei:1940;2848"), ("decreto-lei", "2848", 1940, "decreto.lei:1940;2848"),
    ("MPV", "2200-2", 2001, "medida.provisoria:2001;2200-2"),
    ("medida_provisoria", "881", 2019, "medida.provisoria:2019;881"),
    ("DLG", "6", 2020, "decreto.legislativo:2020;6"),
    ("decreto legislativo", "6", 2020, "decreto.legislativo:2020;6"),
    ("EMC", "132", 2023, "emenda.constitucional:2023;132"),
    ("emenda constitucional", "132", 2023, "emenda.constitucional:2023;132"),
    ("constituição", "1988", 1988, "constituicao:1988-10-05;1988"),
])
def test_urn_formas_do_workkey_e_senado(kind, number, year, expected):
    w = nl.identidade({"tipo": kind, "numero": number, "ano": year})
    assert nl.urn_da_chave(w) == "urn:lex:br:federal:" + expected


@pytest.mark.parametrize("key,reason", [
    ({"tipo": "lei", "numero": 6404}, "ano_necessario"),
    ({"tipo": "resolução", "numero": 1, "ano": 2020}, "tipo_nao_suportado"),
    ({"tipo": "lei", "numero": "1-2", "ano": 2020}, "identidade_invalida"),
])
def test_rejeicao_antes_do_transporte(tmp_path, key, reason):
    con, tr, _ = ambiente(tmp_path)
    with pytest.raises(Unavailable, match=reason):
        con.resolve(key)
    assert tr.chamadas == []


def test_search_identidade_completa_metadados_fetch_parse(tmp_path):
    con, tr, clock = ambiente(tmp_path)
    cand = con.search("Lei 6.404/1976")[0]
    assert cand.key == "normas_leg:urn:lex:br:federal:lei:1976-12-15;6404"
    assert cand.snippet == "Ementa sintética"
    assert cand.metadata["encoding"][0]["contentUrl"] == TEXT
    doc = con.parse(con.fetch(cand))
    assert doc.profile == "normas_leg" and doc.parser_version == "normas-leg-1"
    assert doc.provisions and not doc.quarantined
    meta = json.loads(next(b.text for b in doc.editorial_blocks if b.kind == "normas_leg_metadados"))
    assert meta["version"] == "Current" and meta["legislationLegalValue"] == "UnofficialLegalValue"
    assert meta["atribuicao"]["texto"] == nl.ATRIBUICAO
    assert tr.urls == [ROBOTS, api(), TEXT]
    assert [t for _, _, t in tr.chamadas] == [0, 5, 10]
    assert clock.dormidas == [5, 5]
    for _, kw, _ in tr.chamadas:
        assert kw["hosts"] == {nl.HOST} and kw["user_agent"] == "identified"
        assert kw["repeticao"] == 0 and kw["max_redirects"] == 0
    assert (tmp_path / "normas_leg" / "obtencoes.jsonl").exists()
    assert con.portao().estado.politica(nl.HOST)["tokens"] == list(rb.TOKENS)


@pytest.mark.parametrize("data", [{}, [], {"urn": "wrong"}, {"urn": "urn:lex:br:federal:lei:1976;6404", "extra": True},
                                  payload(urn="urn:lex:br:federal:lei:1975-12-15;6404"),
                                  payload(urn="urn:lex:br:federal:lei.complementar:1976-12-15;6404"),
                                  payload(urn="urn:lex:br:federal:lei:1976-12-15;6405"),
                                  payload(urn="urn:lex:br:federal:lei:1976-99-99;6404")])
def test_nunca_zero_para_resposta_inesperada(tmp_path, data):
    con, _, _ = ambiente(tmp_path, data=data)
    with pytest.raises(Unavailable, match="resposta_inesperada"):
        con.resolve(KEY)


def test_zero_somente_corpo_exato(tmp_path):
    con, tr, _ = ambiente(tmp_path, data={"urn": "urn:lex:br:federal:lei:1976;6404"})
    assert con.search("Lei 6404/1976") == []
    assert tr.urls == [ROBOTS, api()]


@pytest.mark.parametrize("url", ["http://normas.leg.br/api/binario/123/texto", TEXT + "?x=1", TEXT + "#x",
                                TEXT.replace("normas.leg.br", "evil.invalid"),
                                TEXT.replace("normas.leg.br", "normas.leg.br:443"),
                                TEXT.replace("12345678", "abcdefgh"), TEXT + "/extra"])
def test_content_url_invalido_recusado_sem_obter(tmp_path, url):
    data = payload()
    data["encoding"][0]["contentUrl"] = url
    con, tr, _ = ambiente(tmp_path, data=data)
    with pytest.raises(Unavailable, match="resposta_inesperada"):
        con.resolve(KEY)
    assert tr.urls == [ROBOTS, api()]


def test_original_se_nao_current_e_escolha_explicita(tmp_path):
    data = payload()
    data["encoding"][0]["version"] = "Original"
    con, _, _ = ambiente(tmp_path, data=data)
    cand = con.resolve(KEY)
    doc = con.parse(con.fetch(cand))
    assert '"version": "Original"' in doc.editorial_blocks[-1].text


def test_current_preferido_a_original_e_nao_fallback_apos_barreira(tmp_path):
    data = payload()
    data["encoding"].insert(0, {**data["encoding"][0], "version": "Original", "contentUrl": TEXT.replace("12345678", "87654321")})
    con, tr, _ = ambiente(tmp_path, data=data)
    cand = con.resolve(KEY)
    tr.rotas[TEXT] = Unavailable("http_403", "recusa_identificado", {"status": 403})
    with pytest.raises(Unavailable, match="http_403"):
        con.fetch(cand)
    assert tr.urls == [ROBOTS, api(), TEXT]


@pytest.mark.parametrize("robots,reason", [("", "corpo_vazio"), ("bad", "robots_inconclusivo"),
    ("User-agent: *\nDisallow: /api/\n", "robots_recusa"),
    ("User-agent: *\nAllow: /\nUser-agent: ClaudeBot\nDisallow: /api/\n", "robots_recusa"),
    ("User-agent: *\nCrawl-delay: nan\n", "robots_inconclusivo")])
def test_robots_recusa_ou_inconclusivo_impede_conteudo(tmp_path, robots, reason):
    con, tr, _ = ambiente(tmp_path, robots=robots)
    with pytest.raises(Unavailable, match=reason if reason != "corpo_vazio" else "robots_inconclusivo"):
        con.resolve(KEY)
    assert tr.urls == [ROBOTS]


def test_robots_24h_persistidos_e_crawl_delay(tmp_path):
    con, tr, clock = ambiente(tmp_path, robots="User-agent: *\nAllow: /\nCrawl-delay: 8\n")
    con.resolve(KEY)
    assert clock.t == 8
    new = nl.NormasPortao(tr, home=tmp_path, relogio=clock)
    with da_chamada():
        new.obter(api())
    assert tr.urls == [ROBOTS, api(), api()]
    clock.avancar(24 * 3600)
    with da_chamada():
        new.obter(api())
    assert tr.urls[-2:] == [ROBOTS, api()] and tr.urls.count(ROBOTS) == 2


@pytest.mark.parametrize("reason,category,status,permanent", [
    ("http_401", "recusa_identificado", 401, True), ("http_403", "recusa_identificado", 403, True),
    ("http_429", None, 429, True), ("desafio", "ambiental_desafio", 200, True),
    ("http_503", "fonte_fora", 503, False), ("transporte_Timeout", "fonte_fora", None, False),
])
def test_barreiras_persistidas_apos_reinicio(tmp_path, reason, category, status, permanent):
    con, tr, clock = ambiente(tmp_path)
    tr.rotas[api()] = Unavailable(reason, category, {"status": status})
    with pytest.raises(Unavailable, match=reason):
        con.resolve(KEY)
    emitted = len(tr.chamadas)
    tr.rotas[api()] = resposta(api(), b'{}', mime="application/json")
    new = nl.NormasPortao(tr, home=tmp_path, relogio=clock)
    with pytest.raises(Unavailable, match=reason):
        new.obter(api())
    assert len(tr.chamadas) == emitted
    clock.avancar(3601)
    if permanent:
        with pytest.raises(Unavailable, match=reason):
            new.obter(api())
        assert len(tr.chamadas) == emitted
        new.reabrir("0085-teste-sintetico")
        new.obter(api())
        assert tr.urls[-2:] == [ROBOTS, api()]
        assert new.estado.reaberturas(nl.HOST)[0]["decisao"] == "0085-teste-sintetico"
    else:
        new.obter(api())
        assert len(tr.chamadas) == emitted + 1


def test_teto_12_por_chamada_inclui_robots_e_todas_instancias(tmp_path):
    con, tr, clock = ambiente(tmp_path)
    other = nl.NormasPortao(tr, home=tmp_path, relogio=clock)
    with da_chamada():
        for n in range(11):
            (other if n % 2 else con.portao()).obter(api())
        with pytest.raises(Unavailable, match="teto_de_chamada"):
            other.obter(api())
    assert len(tr.chamadas) == 12


def test_parser_preserva_quarentena(tmp_path):
    con, tr, _ = ambiente(tmp_path)
    tr.rotas[TEXT] = resposta(TEXT, html().replace(b"Bras", b"Ausente"))
    doc = con.parse(con.fetch(con.resolve(KEY)))
    assert doc.quarantined and any(i.code == "TRUNCATED" for i in doc.issues)


def test_identidade_divergente_no_corpo_nao_e_sobrescrita(tmp_path):
    con, tr, _ = ambiente(tmp_path)
    tr.rotas[TEXT] = resposta(TEXT, html("LEI Nº 6.405, DE 15 DE DEZEMBRO DE 1976"))
    with pytest.raises(Unavailable, match="resposta_inesperada"):
        con.parse(con.fetch(con.resolve(KEY)))


def test_servico_captura_sob_demanda_reabre_offline_sem_verified(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    home = tmp_path / "home"
    con, tr, _ = ambiente(home)
    with Verifica(home=home) as svc:
        svc._connectors[nl.NormasLegConnector.id] = con
        out = svc.verificar_citacao("art. 1º da Lei 6.404/1976", trecho="A companhia terá capital dividido em ações.")
        for dim in ("identity", "text", "temporal"):
            assert out[dim]["status"] == "unknown", out
            assert out[dim]["reason_code"] == "rota_nao_qualificada", out
        ev = out["text"]["evidence"][0]
        assert ev["trecho_oficial"] and ev["span"] and ev["path"] == "art1"
        assert ev["capture_id"] and ev["sha256"] and ev["url"] == TEXT and ev["captured_at"]
        assert ev["versao_texto"] == "Current" and ev["legislationLegalValue"] == "UnofficialLegalValue"
        assert ev["license"].endswith("/by/4.0/") and ev["atribuicao"]["texto"] == nl.ATRIBUICAO
    emitted = len(tr.chamadas)
    monkeypatch.setenv("FV_OFFLINE", "1")
    with Verifica(home=home) as svc:
        out = svc.verificar_citacao("art. 1º da Lei 6.404/1976", trecho="A companhia terá capital dividido em ações.")
        assert out["text"]["status"] == "unknown", out
        assert out["text"]["reason_code"] == "rota_nao_qualificada", out
        assert out["text"]["evidence"][0]["versao_texto"] == "Current"
    assert len(tr.chamadas) == emitted


def test_offline_nao_captura_e_listar_fontes_expoe_rota(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    with Verifica(home=tmp_path / "home") as svc:
        svc._get = lambda *a: pytest.fail("offline chegou a conector")
        out = svc.verificar_citacao("art. 1º da Lei 6.404/1976")
        assert out["identity"]["status"] != "verified"
        catalog = svc.listar_fontes()
        route = next(r for r in catalog["qualificacao_rotas"] if r["fonte"] == "normas_leg")
        assert all(c["estado"] == "nao_apurada" for c in route["capacidades"].values())
    assert "normas_leg" in registry()


def test_health_positivo_negativo_e_original(tmp_path):
    con, tr, _ = ambiente(tmp_path)
    negative = "urn:lex:br:federal:lei:2099;999999"
    tr.rotas[api(negative)] = resposta(api(negative), json.dumps({"urn": negative}).encode(), mime="application/json")
    lc = "urn:lex:br:federal:lei.complementar:2005;118"
    lc_data = payload("urn:lex:br:federal:lei.complementar:2005-02-09;118", name="Lei Complementar 118/2005")
    lc_data["encoding"][0]["version"] = "Original"
    tr.rotas[api(lc)] = resposta(api(lc), json.dumps(lc_data).encode(), mime="application/json")
    tr.rotas[TEXT] = resposta(TEXT, html("LEI COMPLEMENTAR Nº 118, DE 9 DE FEVEREIRO DE 2005"))
    report = con.health()
    assert [(p.name, p.status) for p in report.probes] == [("positivo", "ok"), ("negativo", "zero"), ("documento", "ok")]
    assert report.probes[-1].detail == "Original"


@pytest.mark.parametrize("fonte_sonda", [False, True])
def test_instrumento_passando_pelo_mesmo_portao(tmp_path, monkeypatch, fonte_sonda):
    from freoa_verifica import captura
    con, tr, clock = ambiente(tmp_path / "home")
    monkeypatch.setenv("FV_HOME", str(con.home))
    monkeypatch.setattr(captura, "connector_fetch", tr)
    monkeypatch.setattr(nl.NormasPortao, "_esperar", lambda self, host, intervalo: clock.sleep(intervalo))
    kw = {"fonte_sonda": "normas_leg"} if fonte_sonda else {}
    rec = captura.capturar(None if fonte_sonda else "normas_leg", url=api(), destino=tmp_path / "capture",
                           sonda=True, chave="s", **kw)
    assert not rec.unavailable and tr.urls == [ROBOTS, api()]
    assert rec.sha256 and rec.user_agent.startswith("freoa-verifica/")


def test_qualificacao_arquivo_adulterado_nao_abre_gate(monkeypatch):
    from freoa_verifica import qualificacao
    from importlib.resources import files
    d = json.loads(files("freoa_verifica").joinpath("data/qualificacao_rotas.json").read_text(encoding="utf-8"))
    for r in d["rotas"]:
        if r["fonte"] == "normas_leg":
            for cap in r["capacidades"].values():
                cap["estado"] = "aprovada"
    assert all(c["estado"] == "nao_apurada" for r in qualificacao.carregar(json.dumps(d))
               if r["fonte"] == "normas_leg" for c in r["capacidades"].values())
    assert not qualificacao.rota_aprovada("normas_leg", "normas_leg")


def test_verificador_python_direto_nao_confirma_texto_igual(tmp_path):
    from freoa_verifica.verify import MemoryResolver, verificar
    con, _, _ = ambiente(tmp_path)
    cand = con.resolve(KEY)
    resp = con.fetch(cand)
    doc = con.parse(resp)
    with Verifica(home=tmp_path / "db") as svc:
        rw = svc.indexar_obra(source_id="normas_leg", work_key=KEY, document=doc, body=resp.body,
                              url=resp.url, fetched_at=resp.fetched_at, content_type="text/html; charset=utf-8")
        resolver = MemoryResolver()
        resolver.add(rw)
        out = verificar("art. 1º da Lei 6404/1976", trecho=doc.provisions[0].current_text(), resolver=resolver)
        assert out.identity.status == out.text.status == out.temporal.status == "unknown"
        assert out.text.reason_code == "rota_nao_qualificada"
        assert out.text.evidence[0].trecho_oficial == doc.provisions[0].current_text()


def test_atribuicao_em_texto_bruto_busca_e_dispositivo_apos_reabertura(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    home = tmp_path / "home"
    con, _, _ = ambiente(home)
    with Verifica(home=home) as svc:
        svc._connectors["normas_leg"] = con
        out = svc.verificar_citacao("art. 1º da Lei 6404/1976")
        capture_id = out["identity"]["evidence"][0]["capture_id"]
    monkeypatch.setenv("FV_OFFLINE", "1")
    with Verifica(home=home) as svc:
        ev = svc.obter_evidencia(capture_id)
        assert ev["atribuicao"]["texto"] == nl.ATRIBUICAO
        doc = svc.obter_dispositivo("art. 1º da Lei 6404/1976", fonte="normas_leg")
        assert doc["evidencia"]["atribuicao"]["texto"] == nl.ATRIBUICAO, doc
        search = svc.buscar_legislacao("capital", fonte="normas_leg")
        assert search["itens"] and search["itens"][0]["atribuicao"]["texto"] == nl.ATRIBUICAO, search
        assert svc.conn.execute("SELECT COUNT(*) FROM capture WHERE source_id='normas_leg'").fetchone()[0] == 2


@pytest.mark.parametrize("version", ["Current", "Original"])
def test_resolve_fetch_e_parse_das_oito_especies(tmp_path, version):
    from freoa_verifica.identity import declared_identity
    for n, kind in enumerate(nl.TIPOS):
        w = WorkKey("federal", kind, "1988" if kind == "constituicao" else "1", 1988 if kind == "constituicao" else 2005)
        urn = nl.urn_da_chave(w)
        full = urn if kind == "constituicao" else urn.replace(":2005;", ":2005-02-09;")
        data = payload(full, name=f"{kind.replace('_', ' ')} {w.number}/{w.year}")
        data["encoding"][0]["version"] = version
        con, tr, _ = ambiente(tmp_path / str(n), data=data, url=api(urn))
        tr.rotas[TEXT] = resposta(TEXT, html("Epígrafe sintética: identidade declarada no JSON-LD"))
        doc = con.parse(con.fetch(con.resolve(w)))
        assert declared_identity(doc)[0] == w
        assert doc.profile == "normas_leg"


def test_serializacao_entre_instancias_no_mesmo_home(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    con, tr, clock = ambiente(tmp_path)
    other = nl.NormasPortao(tr, home=tmp_path, relogio=clock)
    with ThreadPoolExecutor(2) as pool:
        results = [pool.submit(p.obter, api()) for p in (con.portao(), other)]
        for f in results:
            assert f.result().status == 200
    assert [t for _, _, t in tr.chamadas] == [0, 5, 10]


def test_bloqueio_real_da_guarda_com_desafio_http_200(tmp_path, monkeypatch):
    from freoa_verifica.connectors import httputil
    clock = RelogioFalso()
    calls = []

    def transport(url, **kw):
        calls.append(url)
        if url == ROBOTS:
            return resposta(url, b"User-agent: *\nAllow: /\n", mime="text/plain")
        return resposta(url, b'<html><div class="g-recaptcha">captcha</div></html>')

    monkeypatch.setattr(httputil, "transport_fetch", transport)
    gate = nl.NormasPortao(httputil.connector_fetch, home=tmp_path, relogio=clock)
    with pytest.raises(Unavailable) as exc:
        gate.obter(TEXT)
    assert exc.value.categoria == "ambiental_desafio"
    fresh = nl.NormasPortao(httputil.connector_fetch, home=tmp_path, relogio=clock)
    with pytest.raises(Unavailable):
        fresh.obter(api())
    assert calls == [ROBOTS, TEXT]


@pytest.mark.parametrize("script", nl.SCRIPTS)
def test_scripts_oficiais_somente_instrumento_e_sob_robots(tmp_path, script):
    con, tr, clock = ambiente(tmp_path)
    url = nl.BASE + script
    tr.rotas[url] = resposta(url, b"/* cliente oficial sintetico */", mime="application/javascript")
    with pytest.raises(Unavailable, match="url_nao_admitida"):
        con.portao().obter(url)
    assert tr.urls == []
    gate = nl.NormasPortao(tr, home=tmp_path, relogio=clock, instrumento=True)
    assert gate.obter(url).body and tr.urls == [ROBOTS, url]


def test_parser_isolado_falha_local_continua_tipado(monkeypatch):
    from freoa_verifica.parsers import isolated
    from freoa_verifica.connectors.base import LocalParserFailure
    monkeypatch.setattr(isolated.subprocess, "Popen", lambda *a, **kw: (_ for _ in ()).throw(OSError("falha_sintetica")))
    with pytest.raises(LocalParserFailure) as exc:
        isolated.parse_ou_indisponivel("normas_leg", "<html/>", 1)
    assert exc.value.evidencia["perfil"] == "normas_leg"
    assert exc.value.evidencia["causa"] == "criacao_processo"
