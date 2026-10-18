"""Testes da API REST (pula se fastapi ausente)."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from freoa_verifica.rest import create_app


@pytest.fixture
def client(verifica_populada, monkeypatch):
    svc, rw, doc = verifica_populada
    monkeypatch.setenv("FV_HOME", str(svc.home))
    monkeypatch.delenv("FV_API_TOKEN", raising=False)
    app = create_app(home=str(svc.home), token=None)
    for cached in svc._resolver.works.values():
        app.state.verifica.registrar(cached)
    with TestClient(app, client=("127.0.0.1", 50000)) as c:
        c.doc_ref = doc  # type: ignore[attr-defined]
        yield c


def test_rest_get_dispositivo(client):
    r = client.get(
        "/v1/dispositivos",
        params={"citacao": "art. 254-A da Lei 6.404/76"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "encontrada"
    assert data["texto"]


def test_rest_post_verificacao(client):
    doc = client.doc_ref
    trecho = "A alienação, direta ou indireta, do controle de companhia aberta"
    r = client.post(
        "/v1/verificacoes",
        json={"citacao": "art. 254-A da Lei 6.404/76", "trecho": trecho},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["identity"]["status"] == "verified"
    assert data["text"]["status"] == "verified"
    assert data["support"]["status"] == "not_assessed"


def test_rest_post_verificacao_texto(client):
    r = client.post(
        "/v1/verificacoes/texto",
        json={"texto": "Nos termos do art. 254-A da Lei 6.404/76."},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    assert any(c["status"] == "encontrada" for c in data["citacoes"])


def test_rest_auth_obrigatorio(verifica_populada, monkeypatch):
    svc, *_ = verifica_populada
    monkeypatch.setenv("FV_HOME", str(svc.home))
    app = create_app(home=str(svc.home), token="segredo")
    with TestClient(app) as c:
        r = c.get("/v1/fontes")
        assert r.status_code == 401
        assert r.headers["content-type"].startswith("application/problem+json")
        r2 = c.get("/v1/fontes", headers={"Authorization": "Bearer segredo"})
        assert r2.status_code == 200
