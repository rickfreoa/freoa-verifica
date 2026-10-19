"""Regressões de download em fluxo e apresentação de identidade."""
import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from freoa_verifica import snapshot, transport as tr
from freoa_verifica.connectors import httputil
from tests.test_transport import ALLOWED, _fast_guards, _wire_local, local_server, _Handler


@pytest.mark.parametrize("cut", [False, True])
def test_stream_sixty_mib(monkeypatch, tmp_path, cut):
    size = 60 * 1024**2
    chunk = b"x" * 65536
    source = tmp_path / "source.bin"
    with source.open("wb") as stream:
        for _ in range(size // len(chunk)):
            stream.write(chunk)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(size))
            self.end_headers()
            with source.open("rb") as stream:
                for _ in range((size // len(chunk)) // (2 if cut else 1)):
                    self.wfile.write(stream.read(len(chunk)))

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    dest = tmp_path / "download"
    dest.write_bytes(b"previous")
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_port)
    try:
        if cut:
            with pytest.raises(tr.TransportError):
                tr.fetch("https://example.com/file", allowed_hosts=ALLOWED,
                         max_bytes=4 * 1024**3, sink=dest, timeout=20)
            assert dest.read_bytes() == b"previous"
        else:
            response = tr.fetch("https://example.com/file", allowed_hosts=ALLOWED,
                                max_bytes=4 * 1024**3, sink=dest, timeout=20)
            assert response.body == b""
            assert response.size == dest.stat().st_size == size
            digest = hashlib.sha256()
            with dest.open("rb") as stream:
                for part in iter(lambda: stream.read(65536), b""):
                    digest.update(part)
            assert response.sha256 == digest.hexdigest()
        assert sorted(p.name for p in tmp_path.iterdir()) == ["download", "source.bin"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


@pytest.mark.parametrize("failure", ["mime", "declared", "downloaded", "redirect", "timeout"])
def test_stream_guards(monkeypatch, tmp_path, local_server, failure):
    _fast_guards(monkeypatch)
    _, port, _ = local_server
    _wire_local(monkeypatch, port)
    kwargs = dict(max_bytes=100, timeout=2)
    if failure == "mime":
        _Handler.content_type = "application/octet-stream"
    elif failure == "declared":
        _Handler.content_length = 101
    elif failure == "downloaded":
        _Handler.omit_content_length = True
        _Handler.body = b"x" * 101
    elif failure == "redirect":
        _Handler.redirect_to = "https://evil.example/file"
    elif failure == "timeout":
        _Handler.delay = .2
        kwargs["timeout"] = .05
    dest = tmp_path / "file"
    with pytest.raises(tr.TransportError):
        tr.fetch("https://example.com/file", allowed_hosts=ALLOWED, sink=dest, **kwargs)
    # O trabalhador pode terminar a limpeza depois de o prazo público vencer.
    deadline = time.monotonic() + 2
    while list(tmp_path.iterdir()) and time.monotonic() < deadline:
        time.sleep(.01)
    assert list(tmp_path.iterdir()) == []


def test_stream_minimum_rate(monkeypatch, tmp_path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", "100")
            self.end_headers()
            self.wfile.flush()
            time.sleep(.3)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_port)
    monkeypatch.setattr(tr, "SLOW_WINDOW", .05)
    try:
        with pytest.raises(tr.TransporteLento):
            tr.fetch("https://example.com/file", allowed_hosts=ALLOWED,
                     sink=tmp_path / "file", timeout=2)
        assert list(tmp_path.iterdir()) == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_actual_invalid_device(verifica_populada):
    svc, _, _ = verifica_populada
    result = svc.verificar_texto("artigo banana da Lei 6.404/76")["citacoes"][0]
    assert result["identity"]["reason_code"] == "ASSOCIACAO_REQUER_CONFERENCIA"
    assert result["status"] == "requer_conferencia"
    assert result["confidence"] == "provavel"
    assert "dispositivo_invalido" in result["parseada"]["flags"]


@pytest.mark.parametrize("sink,limit", [(False, 50 * 1024**2 + 1), (True, 4 * 1024**3 + 1)])
def test_stream_limit_validation(tmp_path, sink, limit):
    with pytest.raises(ValueError, match="max_bytes"):
        tr.fetch("https://example.com/", allowed_hosts=ALLOWED, max_bytes=limit,
                 sink=tmp_path / "file" if sink else None)


@pytest.mark.parametrize("reason,expected", [
    ("formato_invalido", "formato_invalido"),
    ("CITACAO_NAO_RECONHECIDA", "formato_invalido"),
    ("IDENTIDADE_DIVERGENTE", "indisponivel"),
    ("OBRA_NAO_ENCONTRADA", "indisponivel"),
    ("DISPOSITIVO_INEXISTENTE", "indisponivel"),
    ("NOVO_CODIGO", "indisponivel"),
])
def test_no_negative_promotion(verifica_populada, monkeypatch, reason, expected):
    svc, _, _ = verifica_populada
    monkeypatch.setattr(svc, "verificar_citacao", lambda *a, **kw: {
        "identity": {"status": "not_found", "reason_code": reason, "evidence": []}})
    assert svc.verificar_texto("art. 254-A da Lei 6.404/76")["citacoes"][0]["status"] == expected


def test_latest_release_fallback(monkeypatch):
    calls = []
    name = "freoa-verifica-snapshot-20261018.tar.gz"
    url = "https://github.com/rickfreoa/freoa-verifica/releases/download/v1/" + name
    def fetch(request, **kwargs):
        calls.append(request)
        data = {"assets": []} if request.endswith("/latest") else [
            {"assets": []}, {"assets": [{"name": name, "browser_download_url": url}]}]
        return SimpleNamespace(body=json.dumps(data).encode())
    monkeypatch.setattr(snapshot, "_snapshots_oficiais", lambda: [{"arquivo": name, "sha256": '0' * 64, "derived_version": 3}])
    monkeypatch.setattr(httputil, "connector_fetch", fetch)
    monkeypatch.setattr(snapshot, "_download_release", lambda found, **kwargs: found)
    assert snapshot._download_latest_release() == url
    assert "page=1" in calls[-1]


@pytest.mark.parametrize("failure", ["checksum", "download", "checksum_unavailable"])
def test_snapshot_failure_cleans_before_extraction(monkeypatch, tmp_path, failure):
    from freoa_verifica.connectors.base import Unavailable
    staging = tmp_path / "staging"
    staging.mkdir()
    monkeypatch.setattr(snapshot, "_new_staging", lambda **kw: staging)
    def fetch(url, **kwargs):
        if url.endswith(".sha256"):
            if failure == "checksum_unavailable":
                raise Unavailable("http_503")
            return SimpleNamespace(body=b"0" * 64)
        Path(kwargs["sink"]).write_bytes(b"archive")
        if failure == "download":
            raise Unavailable("conexao_interrompida")
        return SimpleNamespace(body=b"", sha256=hashlib.sha256(b"archive").hexdigest())
    def extract(*args):
        pytest.fail("extração antes de conferir integridade")
    monkeypatch.setattr(httputil, "connector_fetch", fetch)
    monkeypatch.setattr(snapshot, "_extract_archive", extract)
    with pytest.raises((ValueError, Unavailable)):
        snapshot._download_release("https://github.com/rickfreoa/freoa-verifica/releases/download/v1/snapshot.tar.gz")
    assert not staging.exists()


@pytest.mark.parametrize("mutation", ["hash", "quarantine", "blob"])
def test_negative_requires_authenticated_evidence(verifica_populada, monkeypatch, mutation):
    from freoa_verifica.store import blobs
    svc, rw, _ = verifica_populada
    verification = svc.verificar_citacao("art. 999999 da Lei 6.404/76")
    assert verification["identity"]["reason_code"] == "DISPOSITIVO_INEXISTENTE"
    if mutation == "hash":
        verification["identity"]["evidence"][0]["sha256"] = "0" * 64
    elif mutation == "quarantine":
        verification["text"]["reason_code"] = "DOCUMENTO_QUARENTENADO"
    else:
        blobs.blob_path(rw.sha256, svc.home).unlink()
    monkeypatch.setattr(svc, "verificar_citacao", lambda *a, **kw: verification)
    assert svc.verificar_texto("art. 999999 da Lei 6.404/76")["citacoes"][0]["status"] == "indisponivel"
