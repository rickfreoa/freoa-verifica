"""Regressões dos achados 1–9 da auditoria M4."""

from __future__ import annotations

import json
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

import pytest

from freoa_verifica import transport as tr
from freoa_verifica.authority import classify_authority, normalize_species
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.bcb import BcbConnector
from freoa_verifica.connectors.cvm_colegiado import CvmColegiadoConnector, _parse_rss
from freoa_verifica.connectors.cvm_normas import CvmNormasConnector
from freoa_verifica.connectors.datajud import DatajudConnector, _is_publico
from freoa_verifica.connectors.stf import StfConnector
from freoa_verifica.connectors.stj import StjConnector
from freoa_verifica.connectors.tcu import TcuConnector, _cand
from freoa_verifica.connectors.tjsp import TjspConnector, _parse_results
from freoa_verifica.transport import Response, Session
from tests.fixture_util import load_fixture


def _resp(body: bytes, url: str = "https://example.com/", mime: str = "application/json") -> Response:
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


# --- 1. transporte / sessão ---

def test_mime_equality_not_prefix():
    assert tr._mime_allowed("application/json", frozenset({"application/json"}))
    assert not tr._mime_allowed(
        "application/json-unexpected", frozenset({"application/json"})
    )


def test_path_prefix_rejects_generic_slash():
    with pytest.raises(ValueError, match="allowed_path_prefixes"):
        tr.validate_reference(
            "https://example.com/x",
            frozenset({"example.com"}),
            allowed_path_prefixes={"example.com": ("/",)},
        )


def test_session_cookies_not_in_receipt(monkeypatch):
    """Set-Cookie alimenta Session; nunca aparece em Response.headers."""
    tr.reset_guards()

    class H(BaseHTTPRequestHandler):
        hits = 0

        def log_message(self, format, *args):  # noqa: A003
            return

        def do_GET(self):  # noqa: N802
            H.hits += 1
            if self.path.endswith("/a"):
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Set-Cookie", "JSESSIONID=abc123; Path=/")
                body = b"init"
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            cookie = self.headers.get("Cookie") or ""
            body = cookie.encode("utf-8") if cookie else b"nocookie"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), H)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        from urllib.parse import urlsplit, unquote

        def relaxed(url, allowed_hosts, *, allowed_path_prefixes=None):
            parsed = urlsplit(url)
            host = (parsed.hostname or "").lower().rstrip(".")
            if parsed.scheme not in ("https", "http") or host not in allowed_hosts:
                raise tr.BlockedHost("host fora da allowlist")
            target = parsed.path or "/"
            decoded = unquote(target)
            if not tr._path_allowed(host, target, decoded, allowed_path_prefixes):
                raise tr.BlockedHost("caminho fora do escopo")
            if parsed.query:
                target += "?" + parsed.query
            return host, target

        def fake_validate_url(url, allowed_hosts, *, timeout=10.0, allowed_path_prefixes=None):
            host, target = tr.validate_reference(
                url, allowed_hosts, allowed_path_prefixes=allowed_path_prefixes
            )
            return host, target, "127.0.0.1"

        class LocalConn:
            def __init__(self, host, ip, *, timeout=10.0):
                import http.client

                self._c = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
                self.host = host

            def request(self, method, target, body=None, headers=None):
                self._c.request(method, target, body=body, headers=headers or {})

            def getresponse(self):
                return self._c.getresponse()

            def close(self):
                self._c.close()

        monkeypatch.setattr(tr, "validate_reference", relaxed)
        monkeypatch.setattr(tr, "validate_url", fake_validate_url)
        monkeypatch.setattr(tr, "PinnedHTTPSConnection", LocalConn)
        monkeypatch.setattr(
            tr, "_rate_limiter", lambda host: tr.TokenBucket(rate=1000.0, capacity=1000.0)
        )

        session = Session()
        hosts = frozenset({"example.com"})
        prefixes = {"example.com": ("/a", "/b")}
        r1 = tr.fetch(
            "https://example.com/a",
            allowed_hosts=hosts,
            allowed_path_prefixes=prefixes,
            session=session,
            timeout=5,
        )
        assert "set-cookie" not in {k.lower() for k in r1.headers}
        assert "cookie" not in {k.lower() for k in r1.headers}
        assert session.has_cookie("JSESSIONID")
        r2 = tr.fetch(
            "https://example.com/b",
            allowed_hosts=hosts,
            allowed_path_prefixes=prefixes,
            session=session,
            timeout=5,
        )
        assert b"JSESSIONID=abc123" in r2.body
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_tjsp_does_not_use_urllib_opener():
    import freoa_verifica.connectors.tjsp as mod
    import inspect

    src = inspect.getsource(mod)
    assert "build_opener" not in src
    assert "urllib.request" not in src
    assert "Session()" in src


# --- 2. CVM Colegiado ---

def test_cvm_colegiado_unavailable_propagates(monkeypatch):
    conn = CvmColegiadoConnector()

    def boom(*a, **k):
        raise Unavailable("desafio_captcha")

    monkeypatch.setattr(
        "freoa_verifica.connectors.cvm_colegiado.connector_fetch", boom
    )
    with pytest.raises(Unavailable, match="desafio_captcha"):
        conn.search("x", ano="2020")


def test_cvm_colegiado_invalid_xml_unavailable():
    with pytest.raises(Unavailable, match="resposta_invalida"):
        _parse_rss(b"<rss><broken>")
    with pytest.raises(Unavailable, match="resposta_invalida"):
        _parse_rss(b"not-xml-at-all")


def test_cvm_colegiado_valid_empty_rss_is_zero():
    body = b'<?xml version="1.0"?><rss version="2.0"><channel><title>t</title></channel></rss>'
    assert _parse_rss(body) == []


# --- 3. CVM normas sessão ---

def test_cvm_normas_sessao_ausente(monkeypatch):
    conn = CvmNormasConnector()

    class FakeSession:
        def has_cookie(self, name):
            return False

    monkeypatch.setattr(
        "freoa_verifica.connectors.cvm_normas.Session", lambda: FakeSession()
    )

    def fake_fetch(*a, **k):
        return _resp(b"<html><body></body></html>", mime="text/html")

    monkeypatch.setattr(
        "freoa_verifica.connectors.cvm_normas.connector_fetch", fake_fetch
    )
    with pytest.raises(Unavailable, match="sessao_ausente"):
        conn._search_index("Resolução", tipo="resolucoes", limite=5)


# --- 4. schema inválido ---

def test_tcu_error_payload_unavailable():
    with pytest.raises(Unavailable, match="resposta_invalida"):
        _cand("tcu", {"error": "blocked"})


def test_bcb_total_rows_incoherent(monkeypatch):
    conn = BcbConnector()

    def fake_fetch(*a, **k):
        return _resp(json.dumps({"TotalRows": 1, "Rows": []}).encode("utf-8"))

    monkeypatch.setattr("freoa_verifica.connectors.bcb.connector_fetch", fake_fetch)
    with pytest.raises(Unavailable, match="resposta_invalida"):
        conn.search("x")


def test_datajud_timed_out_unavailable():
    conn = DatajudConnector()
    payload = json.loads(load_fixture("datajud_tjsp_sample").decode("utf-8"))
    payload["timed_out"] = True
    payload["hits"]["hits"] = []
    with pytest.raises(Unavailable, match="resposta_invalida"):
        conn.parse(
            _resp(
                json.dumps(payload).encode("utf-8"),
                "https://api-publica.datajud.cnj.jus.br/api_publica_tjsp/_search",
            )
        )


# --- 5. DataJud sigilo ---

def test_datajud_nivel_sigilo_blocks():
    assert _is_publico({"nivelSigilo": 0})
    assert not _is_publico({"nivelSigilo": 1})
    assert not _is_publico({})
    assert not _is_publico({"nivelSigilo": None})

    conn = DatajudConnector()
    payload = json.loads(load_fixture("datajud_tjsp_sample").decode("utf-8"))
    # fixture público
    parsed = conn.parse(
        _resp(
            json.dumps(payload).encode("utf-8"),
            "https://api-publica.datajud.cnj.jus.br/api_publica_tjsp/_search",
        )
    )
    assert parsed.official_id

    sealed = copy.deepcopy(payload)
    sealed["hits"]["hits"][0]["_source"]["nivelSigilo"] = 1
    with pytest.raises(Unavailable, match="resposta_invalida"):
        conn.parse(
            _resp(
                json.dumps(sealed).encode("utf-8"),
                "https://api-publica.datajud.cnj.jus.br/api_publica_tjsp/_search",
            )
        )

    # search descarta e conta
    def fake_post(tribunal, body):
        return _resp(
            json.dumps(sealed).encode("utf-8"),
            f"https://api-publica.datajud.cnj.jus.br/api_publica_{tribunal}/_search",
        )

    conn2 = DatajudConnector()
    conn2._post = fake_post  # type: ignore[method-assign]
    found = conn2._search_body("tjsp", {"size": 1, "query": {"match_all": {}}})
    assert found == []
    assert conn2.descartados_sigilo >= 1


# --- 6. identidade STJ / CVM ---

def test_stj_official_id_is_document_id():
    conn = StjConnector()
    raw = json.loads(load_fixture("stj_espelhos_amostra").decode("utf-8"))
    parsed = conn.parse(_resp(json.dumps(raw).encode("utf-8")))
    assert parsed.official_id == str(raw[0]["id"])
    assert parsed.metadata.get("proceeding") == raw[0]["numeroRegistro"]
    # colisão: mesmo processo, outro id → official_id diferente
    alt = copy.deepcopy(raw[0])
    alt["id"] = "9999999"
    alt["dataDecisao"] = "20250101"
    parsed2 = conn.parse(_resp(json.dumps([alt]).encode("utf-8")))
    assert parsed2.official_id == "9999999"
    assert parsed2.official_id != parsed.official_id


def test_cvm_colegiado_official_id_per_item():
    from freoa_verifica.connectors.cvm_colegiado import _parse_reuniao_html

    html = """<html><body><article>
    <h2>ATA</h2>
    <p class="text-uppercase"><b>Assunto A - PROC. 19957.000001/2026-01</b></p>
    <p>Texto da decisao um.</p>
    <p class="text-uppercase"><b>Assunto B - PROC. 19957.000002/2026-02</b></p>
    <p>Texto da decisao dois.</p>
    </article></body></html>""".encode("utf-8")
    parsed = _parse_reuniao_html(
        html, url="https://conteudo.cvm.gov.br/decisoes/2026/20261014_R1.html"
    )
    assert parsed.official_id.startswith("reuniao=20261014-R1#")
    assert parsed.metadata.get("ata") == "reuniao=20261014-R1"
    assert len(parsed.metadata.get("decisoes") or []) >= 2


# --- 7. TJSP charset ---

def test_tjsp_five_ids_orgao_pub_ementa_sem_mojibake():
    body = load_fixture("tjsp_busca_acordo_acionistas")
    cands = _parse_results(body, source_id="tjsp", limite=20)
    ids = ["21059937", "21059312", "21050853", "21047846", "21044483"]
    by_id = {c.metadata["cdAcordao"]: c for c in cands}
    for cd in ids:
        assert cd in by_id, cd
        meta = by_id[cd].metadata
        assert meta.get("orgao"), f"orgao ausente em {cd}"
        assert meta.get("data_publicacao"), f"publicacao ausente em {cd}"
        ementa = meta.get("ementa") or ""
        assert ementa, f"ementa ausente em {cd}"
        assert "\ufffd" not in ementa
        assert "Ã" not in (meta.get("orgao") or "")
        # acentuação legível
        assert any(ch in ementa for ch in "áàâãéêíóôõúçÁÉÍÓÚÇ") or "&" not in ementa[:20]


# --- 8. autoridade ---

@pytest.mark.parametrize(
    "species,court,organ,class_name,expected",
    [
        ("ACÓRDÃO", "STJ", "Primeira Turma", None, "D"),
        ("Acordao", "STJ", "Corte Especial", None, "C"),
        ("acórdão", "STJ", "Primeira Seção", None, "C"),
        ("monocratica", "STF", "Pleno", "ADPF", "E"),
        ("acordao", "STF", "Pleno", "ADPF", "A"),
        ("administrativa", "TCU", "Plenário", None, "E"),
        ("acordao", "TCU", "Plenário", None, "E"),
        ("irdr_iac", "TJSP", None, None, "B"),
        ("acordao", "STJ", "Corte Especial", None, "C"),
    ],
)
def test_authority_edge_cases(species, court, organ, class_name, expected):
    lab = classify_authority(
        species=species, court=court, organ=organ, class_name=class_name
    )
    assert lab.label == expected
    if court == "TCU" and organ:
        assert lab.attributes.organ == organ


def test_normalize_species_acordao():
    assert normalize_species("ACÓRDÃO") == "acordao"
    assert normalize_species("Acordao") == "acordao"
    assert normalize_species("acórdão") == "acordao"


# --- 9. limites ---

def test_stj_stf_path_prefixes_specific():
    assert "/" not in StjConnector.path_prefixes["dadosabertos.web.stj.jus.br"]
    assert "/" not in StfConnector.path_prefixes["jurisprudencia.stf.jus.br"]
    tr.validate_reference(
        "https://dadosabertos.web.stj.jus.br/api/3/action/package_show",
        StjConnector.hosts,
        allowed_path_prefixes=StjConnector.path_prefixes,
    )
    with pytest.raises(tr.BlockedHost):
        tr.validate_reference(
            "https://dadosabertos.web.stj.jus.br/outro/",
            StjConnector.hosts,
            allowed_path_prefixes=StjConnector.path_prefixes,
        )


def test_bcb_rowlimit_capped(monkeypatch):
    seen = {}

    def fake_fetch(url, **k):
        from urllib.parse import parse_qs, urlsplit

        qs = parse_qs(urlsplit(url).query)
        seen["rowlimit"] = int(qs["rowlimit"][0])
        return _resp(json.dumps({"TotalRows": 0, "Rows": []}).encode("utf-8"))

    monkeypatch.setattr("freoa_verifica.connectors.bcb.connector_fetch", fake_fetch)
    BcbConnector().search("x", limite=9999)
    assert seen["rowlimit"] <= 500


def test_datajud_size_capped(monkeypatch):
    seen = {}

    def fake_post(tribunal, body):
        seen["size"] = body["size"]
        return _resp(
            json.dumps(
                {"timed_out": False, "hits": {"total": {"value": 0}, "hits": []}}
            ).encode("utf-8")
        )

    conn = DatajudConnector()
    conn._post = fake_post  # type: ignore[method-assign]
    conn.search("", tribunal="tjsp", limite=9999)
    assert seen["size"] <= 100


def test_tjsp_pagina_cap(monkeypatch):
    from freoa_verifica.connectors import tjsp as mod

    assert mod.MAX_PAGINA == 2000
    assert mod.MAX_LIMITE == 100

    session = Session()
    # simula JSESSIONID já presente após init
    from http.cookiejar import Cookie

    session._jar.set_cookie(
        Cookie(
            0,
            "JSESSIONID",
            "x",
            None,
            False,
            "esaj.tjsp.jus.br",
            True,
            False,
            "/cjsg",
            True,
            True,
            None,
            True,
            None,
            None,
            {},
            False,
        )
    )

    calls = {"n": 0}

    def fake_fetch(url, **kwargs):
        calls["n"] += 1
        sess = kwargs.get("session")
        if sess is not None and not sess.has_cookie("JSESSIONID"):
            # primeira chamada: devolve HTML e a sessão já tem cookie injetado acima
            pass
        return _resp(b"<html></html>", url=url, mime="text/html")

    monkeypatch.setattr(
        "freoa_verifica.connectors.tjsp.connector_fetch", fake_fetch
    )
    monkeypatch.setattr(
        "freoa_verifica.connectors.tjsp.Session", lambda: session
    )
    conn = TjspConnector()
    with pytest.raises(Unavailable, match="resposta_invalida"):
        conn.search("acordo", pagina=2001)
