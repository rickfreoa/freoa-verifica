"""Decisão 0040: Host/Origin estritos no REST local e no MCP HTTP local."""
import pytest

pytest.importorskip("fastapi")
from starlette.testclient import TestClient  # noqa: E402

from freoa_verifica import fronteira  # noqa: E402
from freoa_verifica.rest import create_app  # noqa: E402

LOCAL = ("127.0.0.1", 50000)


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_API_TOKEN", raising=False)
    monkeypatch.delenv("FV_API_ORIGENS", raising=False)
    return create_app(home=str(tmp_path))


def _get(app, host="127.0.0.1", headers=None, **kw):
    with TestClient(app, client=LOCAL, base_url=f"http://{host}", **kw) as c:
        return c.get("/v1/fontes", headers=headers)


def test_host_loopback_aceito(app):
    for h in ("127.0.0.1", "127.0.0.1:8000", "localhost", "localhost:8000", "[::1]:8000", "[::1]"):
        assert _get(app, h).status_code == 200, h


def test_dns_rebinding_host_externo_com_ip_loopback_recusado(app):
    r = _get(app, "evil.com")
    assert r.status_code == 403
    assert r.headers["content-type"].startswith("application/problem+json")
    assert _get(app, "localhost.evil.com").status_code == 403
    assert _get(app, "127.0.0.1.nip.io").status_code == 403
    assert _get(app, "localhost.").status_code == 403
    assert _get(app, "127.0.0.1:99999").status_code == 403


def test_host_duplicado_vazio_ou_invalido_recusado(app):
    # Cabeçalhos brutos: o TestClient não aceita Host duplicado, então chama o ASGI.
    assert fronteira.validar([(b"host", b"127.0.0.1"), (b"host", b"evil.com")], com_token=False)
    assert fronteira.validar([(b"host", b"127.0.0.1"), (b"host", b"127.0.0.1")], com_token=False)
    assert fronteira.validar([], com_token=False)
    assert fronteira.validar([(b"host", b"")], com_token=False)
    assert fronteira.validar([(b"host", b"127.0.0.1 evil.com")], com_token=False)
    assert fronteira.validar([(b"host", b"127.0.0.1@evil.com")], com_token=False)
    assert fronteira.validar([(b"host", b"127.0.0.1:80a")], com_token=False)
    assert fronteira.validar([(b"host", b"[::1]:8000")], com_token=False) is None


def test_host_duplicado_via_asgi_devolve_403(app):
    import asyncio

    msgs = []

    async def run():
        scope = {"type": "http", "method": "GET", "path": "/v1/fontes", "query_string": b"", "headers": [
            (b"host", b"127.0.0.1"), (b"host", b"evil.com")], "client": LOCAL, "server": ("127.0.0.1", 80),
            "scheme": "http", "http_version": "1.1", "root_path": ""}

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(m):
            msgs.append(m)

        await app(scope, receive, send)

    asyncio.run(run())
    assert msgs[0]["status"] == 403


def test_origin_local_ou_ausente_aceito_e_demais_recusados(app):
    assert _get(app).status_code == 200  # ausente: cliente não navegador
    for o in ("http://127.0.0.1:3000", "http://localhost", "http://[::1]:8000"):
        assert _get(app, headers={"Origin": o}).status_code == 200, o
    for o in ("https://evil.com", "null", "http://localhost.evil.com", "https://127.0.0.1",
              "http://127.0.0.1/x", "http://evil.com"):
        assert _get(app, headers={"Origin": o}).status_code == 403, o


def test_sec_fetch_site_cross_site_recusado(app):
    assert _get(app, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert _get(app, headers={"Sec-Fetch-Site": "same-origin"}).status_code == 200
    assert _get(app, headers={"Sec-Fetch-Site": "none"}).status_code == 200


def test_ip_nao_local_continua_401_antes_do_host(app):
    with TestClient(app, client=("203.0.113.7", 1), base_url="http://127.0.0.1") as c:
        assert c.get("/v1/fontes").status_code == 401


def test_modo_token_mantem_token_e_recusa_origin_externa(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_API_ORIGENS", raising=False)
    app = create_app(home=str(tmp_path), token="s3")
    auth = {"Authorization": "Bearer s3"}
    with TestClient(app, client=LOCAL) as c:  # Host arbitrário é aceito com token (uso remoto)
        assert c.get("/v1/fontes").status_code == 401
        assert c.get("/v1/fontes", headers=auth).status_code == 200
        assert c.get("/v1/fontes", headers={**auth, "Origin": "https://evil.com"}).status_code == 403
        assert c.get("/v1/fontes", headers={**auth, "Origin": "null"}).status_code == 403
        assert c.get("/v1/fontes", headers={**auth, "Origin": "http://localhost:3000"}).status_code == 200
        assert c.get("/v1/fontes", headers={"Origin": "https://evil.com"}).status_code == 403


def test_modo_token_origem_permitida_por_ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_API_ORIGENS", "https://painel.exemplo.org, https://b.exemplo.org")
    app = create_app(home=str(tmp_path), token="s3")
    auth = {"Authorization": "Bearer s3"}
    with TestClient(app, client=LOCAL) as c:
        assert c.get("/v1/fontes", headers={**auth, "Origin": "https://painel.exemplo.org"}).status_code == 200
        assert c.get("/v1/fontes", headers={**auth, "Origin": "https://b.exemplo.org"}).status_code == 200
        assert c.get("/v1/fontes", headers={**auth, "Origin": "https://painel.exemplo.org.evil.com"}).status_code == 403
        assert c.get("/v1/fontes", headers={**auth, "Origin": "https://evil.com"}).status_code == 403


def test_mcp_http_local_usa_a_mesma_fronteira(tmp_path, monkeypatch):
    pytest.importorskip("mcp")
    from freoa_verifica import mcp_server as ms

    monkeypatch.delenv("FV_MCP_TOKEN", raising=False)
    monkeypatch.delenv("FV_API_ORIGENS", raising=False)
    mcp = ms.create_mcp(home=str(tmp_path))
    app = ms.build_http_app(mcp, host="127.0.0.1", token=None)

    with TestClient(app, client=LOCAL, base_url="http://127.0.0.1") as c:
        def post(host, headers=None):
            return c.post("/mcp", json={}, headers={"Host": host, **(headers or {})}).status_code

        assert post("127.0.0.1") != 403
        assert post("[::1]:8000") != 403
        assert post("evil.com") == 403
        assert post("localhost.evil.com") == 403
        assert post("127.0.0.1", {"Origin": "https://evil.com"}) == 403
        assert post("127.0.0.1", {"Origin": "null"}) == 403
        assert post("127.0.0.1", {"Sec-Fetch-Site": "cross-site"}) == 403

    com_token = ms.build_http_app(mcp, host="127.0.0.1", token="s3")
    with TestClient(com_token, client=LOCAL, base_url="http://127.0.0.1") as c:
        h = {"Authorization": "Bearer s3"}
        assert c.post("/mcp", json={}, headers={**h, "Origin": "https://evil.com"}).status_code == 403
        assert c.post("/mcp", json={}, headers=h).status_code not in (401, 403)
        assert c.post("/mcp", json={}).status_code == 401
