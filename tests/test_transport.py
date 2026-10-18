"""Testes offline do transporte (SSRF, limites, rate limit, circuit breaker)."""

from __future__ import annotations

import http.client
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import pytest

from freoa_verifica import transport as tr


ALLOWED = frozenset({"example.com", "www.example.com", "other.example"})


class _Handler(BaseHTTPRequestHandler):
    delay = 0.0
    body = b"ok"
    status = 200
    redirect_to: str | None = None
    redirect_status = 302
    content_length: int | None = None
    omit_content_length = False
    content_type = "text/plain"
    last_request: dict | None = None

    def log_message(self, format, *args):  # noqa: A003
        return

    def _record(self):
        _Handler.last_request = {
            "method": self.command,
            "path": self.path,
            "headers": {k.lower(): v for k, v in self.headers.items()},
            "body": self.rfile.read(int(self.headers.get("Content-Length") or 0)),
        }

    def do_GET(self):  # noqa: N802
        self._handle()

    def do_POST(self):  # noqa: N802
        self._handle()

    def do_HEAD(self):  # noqa: N802
        self._handle(write_body=False)

    def _handle(self, write_body: bool = True):
        self._record()
        if self.delay:
            time.sleep(self.delay)
        if self.redirect_to:
            self.send_response(self.redirect_status)
            self.send_header("Location", self.redirect_to)
            self.end_headers()
            return
        payload = self.body
        self.send_response(self.status)
        self.send_header("Content-Type", self.content_type)
        if not self.omit_content_length:
            length = self.content_length if self.content_length is not None else len(payload)
            self.send_header("Content-Length", str(length))
        self.end_headers()
        if write_body and self.status == 200 and self.command != "HEAD":
            self.wfile.write(payload)


@pytest.fixture
def local_server():
    _Handler.delay = 0.0
    _Handler.body = b"ok"
    _Handler.status = 200
    _Handler.redirect_to = None
    _Handler.redirect_status = 302
    _Handler.content_length = None
    _Handler.omit_content_length = False
    _Handler.content_type = "text/plain"
    _Handler.last_request = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    yield f"http://127.0.0.1:{port}", port, server
    server.shutdown()
    thread.join(timeout=2)


def _fast_guards(monkeypatch):
    """Rate limit permissivo para testes de fetch locais."""
    tr.reset_guards()
    monkeypatch.setattr(
        tr,
        "_rate_limiter",
        lambda host: tr.TokenBucket(rate=1000.0, capacity=1000.0),
    )


def _wire_local(monkeypatch, port: int):
    _allow_http_reference(monkeypatch)

    def fake_validate_url(
        url,
        allowed_hosts,
        *,
        timeout=10.0,
        allowed_path_prefixes=None,
    ):
        host, target = tr.validate_reference(
            url, allowed_hosts, allowed_path_prefixes=allowed_path_prefixes
        )
        return host, target, "127.0.0.1"

    class LocalConn(http.client.HTTPConnection):
        def __init__(self, host, ip, *, timeout=10.0):
            super().__init__("127.0.0.1", port, timeout=timeout)
            self.host = host

        def connect(self):
            self.sock = socket.create_connection(("127.0.0.1", port), self.timeout)

    monkeypatch.setattr(tr, "validate_url", fake_validate_url)
    monkeypatch.setattr(tr, "PinnedHTTPSConnection", LocalConn)


def _allow_http_reference(monkeypatch):
    def relaxed(url, allowed_hosts, *, allowed_path_prefixes=None):
        from urllib.parse import unquote

        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme not in ("https", "http") or host not in allowed_hosts:
            raise tr.BlockedHost("host fora da allowlist")
        if parsed.username or parsed.password or parsed.fragment:
            raise tr.BlockedHost("componente não suportado")
        target = parsed.path or "/"
        decoded = unquote(target)
        if any(part in (".", "..") for part in decoded.split("/")):
            raise tr.BlockedHost("caminho ambíguo")
        if not tr._path_allowed(host, target, decoded, allowed_path_prefixes):
            raise tr.BlockedHost("caminho fora do escopo permitido para o host")
        if parsed.query:
            target += "?" + parsed.query
        return host, target

    monkeypatch.setattr(tr, "validate_reference", relaxed)


# --- SSRF ---

@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.0.0.1", "169.254.1.1", "::1"],
)
def test_ssrf_private_addresses_blocked(monkeypatch, address):
    tr.reset_guards()

    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (address, 443))]

    monkeypatch.setattr(tr.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(tr.BlockedHost):
        tr.validate_url("https://example.com/", ALLOWED)


def test_redirect_to_host_outside_allowlist(monkeypatch, local_server):
    _fast_guards(monkeypatch)
    _, port, _ = local_server
    _Handler.redirect_to = "https://evil.example/"
    _wire_local(monkeypatch, port)
    hosts = frozenset({"example.com"})
    with pytest.raises(tr.BlockedHost):
        tr.fetch("https://example.com/", allowed_hosts=hosts, timeout=5)


def test_validate_reference_rejects_localhost_literal():
    with pytest.raises(tr.BlockedHost):
        tr.validate_reference("https://localhost/", ALLOWED)
    with pytest.raises(tr.BlockedHost):
        tr.validate_reference("https://127.0.0.1/", ALLOWED)


# --- limites ---

def test_too_large_declared(monkeypatch, local_server):
    _fast_guards(monkeypatch)
    _, port, _ = local_server
    _Handler.body = b"x" * 100
    _Handler.content_length = 100
    _wire_local(monkeypatch, port)
    with pytest.raises(tr.TooLarge):
        tr.fetch("https://example.com/", allowed_hosts=ALLOWED, max_bytes=50, timeout=5)


def test_too_large_downloaded(monkeypatch, local_server):
    _fast_guards(monkeypatch)
    _, port, _ = local_server
    _Handler.body = b"y" * 2000
    _Handler.omit_content_length = True
    _wire_local(monkeypatch, port)
    with pytest.raises(tr.TooLarge, match="baixado"):
        tr.fetch("https://example.com/", allowed_hosts=ALLOWED, max_bytes=100, timeout=5)


def test_timeout(monkeypatch, local_server):
    _fast_guards(monkeypatch)
    _, port, _ = local_server
    _Handler.delay = 2.0
    _wire_local(monkeypatch, port)
    with pytest.raises(tr.Timeout):
        tr.fetch("https://example.com/", allowed_hosts=ALLOWED, timeout=0.3)


def test_empty_body_rejected(monkeypatch, local_server):
    _fast_guards(monkeypatch)
    _, port, _ = local_server
    _Handler.body = b""
    _wire_local(monkeypatch, port)
    with pytest.raises(tr.EmptyBody):
        tr.fetch("https://example.com/", allowed_hosts=ALLOWED, timeout=5)


def test_mime_rejected(monkeypatch, local_server):
    _fast_guards(monkeypatch)
    _, port, _ = local_server
    _Handler.body = b"not-html"
    _Handler.content_type = "application/octet-stream"
    _wire_local(monkeypatch, port)
    with pytest.raises(tr.TransportError, match="MIME"):
        tr.fetch(
            "https://example.com/",
            allowed_hosts=ALLOWED,
            allowed_mimes=frozenset({"text/html"}),
            timeout=5,
        )


def test_defaults_max_bytes_and_redirects():
    assert tr.MAX_BYTES == 10 * 1024 * 1024
    assert tr.MAX_REDIRECTS == 3


# --- path prefixes ---

def test_allowed_path_prefixes_enforced():
    hosts = frozenset({"www.gov.br"})
    prefixes = {"www.gov.br": ("/cvm/",)}
    tr.validate_reference(
        "https://www.gov.br/cvm/pt-br/",
        hosts,
        allowed_path_prefixes=prefixes,
    )
    with pytest.raises(tr.BlockedHost):
        tr.validate_reference(
            "https://www.gov.br/receitafederal/",
            hosts,
            allowed_path_prefixes=prefixes,
        )


def test_allowed_path_prefixes_on_redirect(monkeypatch, local_server):
    _fast_guards(monkeypatch)
    _, port, _ = local_server
    _Handler.redirect_to = "https://www.example.com/out/"
    _wire_local(monkeypatch, port)
    with pytest.raises(tr.BlockedHost):
        tr.fetch(
            "https://example.com/in/",
            allowed_hosts=ALLOWED,
            allowed_path_prefixes={"example.com": ("/in/",), "www.example.com": ("/in/",)},
            timeout=5,
        )


# --- cabeçalhos e redirecionamentos ---

def test_reserved_headers_rejected(monkeypatch, local_server):
    _fast_guards(monkeypatch)
    _, port, _ = local_server
    _wire_local(monkeypatch, port)
    with pytest.raises(ValueError, match="reservado"):
        tr.fetch(
            "https://example.com/",
            allowed_hosts=ALLOWED,
            headers={"Host": "evil.example"},
            timeout=5,
        )


def test_header_case_normalization(monkeypatch, local_server):
    _fast_guards(monkeypatch)
    _, port, _ = local_server
    _wire_local(monkeypatch, port)
    tr.fetch(
        "https://example.com/",
        allowed_hosts=ALLOWED,
        headers={"x-custom": "a", "X-Other": "b"},
        timeout=5,
    )
    assert _Handler.last_request is not None
    names = _Handler.last_request["headers"]
    assert "x-custom" in names and "x-other" in names
    assert names.get("host") == "example.com"


def test_post_302_becomes_get_without_body(monkeypatch, local_server):
    _fast_guards(monkeypatch)
    requests_seen: list[dict] = []

    class RedirectThenOk(BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa: A003
            return

        def do_GET(self):  # noqa: N802
            self._handle()

        def do_POST(self):  # noqa: N802
            self._handle()

        def _handle(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            requests_seen.append({"method": self.command, "path": self.path, "body": body})
            if self.path.endswith("/start"):
                self.send_response(302)
                self.send_header("Location", "https://example.com/final")
                self.end_headers()
                return
            payload = b"landed"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectThenOk)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        _wire_local(monkeypatch, server.server_address[1])
        resp = tr.fetch(
            "https://example.com/start",
            method="POST",
            body=b"secret",
            headers={"Authorization": "Bearer t"},
            allowed_hosts=ALLOWED,
            timeout=5,
        )
        assert resp.body == b"landed"
        assert requests_seen[0]["method"] == "POST"
        assert requests_seen[0]["body"] == b"secret"
        assert requests_seen[1]["method"] == "GET"
        assert requests_seen[1]["body"] == b""
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_cross_origin_redirect_strips_credentials(monkeypatch, local_server):
    _fast_guards(monkeypatch)
    _, port, _ = local_server
    hits = {"n": 0}
    seen_auth: list[str | None] = []

    class CrossOrigin(_Handler):
        def _handle(self, write_body: bool = True):
            hits["n"] += 1
            seen_auth.append(self.headers.get("Authorization"))
            if hits["n"] == 1:
                self.send_response(302)
                self.send_header("Location", "https://other.example/page")
                self.end_headers()
                return
            _Handler.body = b"ok-cross"
            super()._handle(write_body=write_body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), CrossOrigin)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        _wire_local(monkeypatch, server.server_address[1])
        resp = tr.fetch(
            "https://example.com/a",
            headers={"Authorization": "Bearer keep"},
            allowed_hosts=ALLOWED,
            timeout=5,
        )
        assert resp.body == b"ok-cross"
        assert seen_auth[0] == "Bearer keep"
        assert seen_auth[1] is None
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_307_cross_origin_rejected(monkeypatch, local_server):
    _fast_guards(monkeypatch)
    _, port, _ = local_server
    _Handler.redirect_to = "https://other.example/x"
    _Handler.redirect_status = 307
    _wire_local(monkeypatch, port)
    with pytest.raises(tr.BlockedHost, match="307/308"):
        tr.fetch(
            "https://example.com/",
            method="POST",
            body=b"x",
            allowed_hosts=ALLOWED,
            timeout=5,
        )


def test_http_metadata_on_success_and_error(monkeypatch, local_server):
    _fast_guards(monkeypatch)
    _, port, _ = local_server
    _Handler.body = b"hello"
    _wire_local(monkeypatch, port)
    resp = tr.fetch("https://example.com/", allowed_hosts=ALLOWED, timeout=5)
    assert resp.http is not None
    assert resp.http.status_code == 200
    assert "content-type" in dict(resp.http.headers)

    _Handler.status = 503
    with pytest.raises(tr.HTTPStatusError) as ei:
        tr.fetch("https://example.com/", allowed_hosts=ALLOWED, timeout=5)
    assert ei.value.http is not None
    assert ei.value.http.status_code == 503


# --- deadline / concorrência ---

def test_deadline_includes_rate_limiter_wait(monkeypatch):
    tr.reset_guards()
    slow = tr.TokenBucket(rate=0.01, capacity=1.0)
    slow.tokens = 0.0
    slow.updated = time.monotonic()
    monkeypatch.setattr(tr, "_rate_limiter", lambda host: slow)

    def boom(*args, **kwargs):
        raise AssertionError("fetch não deveria iniciar após prazo do limiter")

    monkeypatch.setattr(tr, "_fetch_once", boom)
    monkeypatch.setattr(
        tr,
        "validate_reference",
        lambda url, hosts, **kw: ("example.com", "/"),
    )
    start = time.monotonic()
    with pytest.raises(tr.Timeout):
        tr.fetch("https://example.com/", allowed_hosts=ALLOWED, timeout=0.05)
    elapsed = time.monotonic() - start
    assert elapsed < 0.4


def test_concurrency_limit(monkeypatch, local_server):
    _fast_guards(monkeypatch)
    _, port, _ = local_server
    _Handler.delay = 0.4
    _wire_local(monkeypatch, port)
    monkeypatch.setattr(tr, "_CAPTURE_SLOTS", threading.BoundedSemaphore(4))

    results: list[str] = []
    lock = threading.Lock()

    def run():
        try:
            tr.fetch("https://example.com/", allowed_hosts=ALLOWED, timeout=5)
            with lock:
                results.append("ok")
        except tr.Timeout as exc:
            with lock:
                results.append(f"busy:{exc}")

    threads = [threading.Thread(target=run) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    assert results.count("ok") == 4
    assert sum(1 for r in results if r.startswith("busy:")) == 1


# --- rate limit e circuit breaker ---

def test_rate_limit():
    tr.reset_guards()
    bucket = tr.TokenBucket(rate=1.0, capacity=1.0)
    bucket.acquire(timeout=1.0)
    start = time.monotonic()
    with pytest.raises(tr.Timeout):
        bucket.acquire(timeout=0.2)
    assert time.monotonic() - start >= 0.15


def test_circuit_breaker():
    tr.reset_guards()
    cb = tr.CircuitBreaker(failure_threshold=5, cooldown=120.0)
    for _ in range(5):
        cb.record_failure()
    with pytest.raises(tr.Timeout):
        cb.before_call()
    cb.opened_at = time.monotonic() - 121
    cb.before_call()  # half-open após cooldown


def test_circuit_breaker_via_fetch(monkeypatch, local_server):
    _fast_guards(monkeypatch)
    _, port, _ = local_server
    _Handler.status = 500
    _wire_local(monkeypatch, port)
    url = "https://example.com/"
    for _ in range(5):
        with pytest.raises(tr.HTTPStatusError):
            tr.fetch(url, allowed_hosts=ALLOWED, timeout=5)
    with pytest.raises(tr.Timeout, match="Circuit breaker"):
        tr.fetch(url, allowed_hosts=ALLOWED, timeout=5)


def test_successful_fetch(monkeypatch, local_server):
    _fast_guards(monkeypatch)
    _, port, _ = local_server
    _Handler.body = b"hello"
    _wire_local(monkeypatch, port)
    resp = tr.fetch("https://example.com/path", allowed_hosts=ALLOWED, timeout=5)
    assert resp.body == b"hello"
    assert resp.status == 200
    assert resp.sha256
    assert resp.mime == "text/plain"
    assert resp.http is not None
