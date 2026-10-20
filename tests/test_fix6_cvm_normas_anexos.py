"""FIX6/F-05: CVM Normas só passa à próxima representação do normativo após ausência explícita (404/410)."""

from __future__ import annotations

import hashlib

import pytest

from freoa_verifica.connectors import cvm_normas
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.cvm_normas import CvmNormasConnector
from freoa_verifica.transport import Response


def _resp(url: str) -> Response:
    corpo = b"ok"
    return Response(url, url, 200, {}, corpo, hashlib.sha256(corpo).hexdigest(), "2026-01-01T00:00:00+00:00", [], "text/html")


def _executar(monkeypatch, roteiro):
    """`roteiro`: lista de erros (Unavailable) ou None (200), um por chamada."""
    chamadas: list[str] = []

    def falso(url, **kw):
        chamadas.append(url)
        item = roteiro[len(chamadas) - 1] if len(chamadas) <= len(roteiro) else None
        if item is not None:
            raise item
        return _resp(url)

    monkeypatch.setattr(cvm_normas, "connector_fetch", falso)
    c = CvmNormasConnector()
    return c, c.resolve({"tipo": "resolucoes", "numero": 80}), chamadas


def test_captcha_na_primeira_representacao_interrompe_com_desafio(monkeypatch):
    c, cand, chamadas = _executar(monkeypatch, [Unavailable("desafio_captcha", "ambiental_desafio")])
    with pytest.raises(Unavailable) as ei:
        c.fetch(cand)
    assert len(chamadas) == 1
    assert ei.value.categoria == "ambiental_desafio"


def test_403_interrompe(monkeypatch):
    c, cand, chamadas = _executar(monkeypatch, [Unavailable("http_403", "recusa_identificado")])
    with pytest.raises(Unavailable) as ei:
        c.fetch(cand)
    assert len(chamadas) == 1
    assert ei.value.reason == "http_403"


def test_503_esgotado_nao_chama_outros_anexos(monkeypatch):
    c, cand, chamadas = _executar(monkeypatch, [Unavailable("http_503", "fonte_fora")])
    with pytest.raises(Unavailable) as ei:
        c.fetch(cand)
    assert len(chamadas) == 1
    assert ei.value.categoria == "fonte_fora"


def test_resposta_invalida_interrompe(monkeypatch):
    c, cand, chamadas = _executar(monkeypatch, [Unavailable("resposta_invalida")])
    with pytest.raises(Unavailable) as ei:
        c.fetch(cand)
    assert len(chamadas) == 1
    assert ei.value.categoria == "resposta_inesperada"


@pytest.mark.parametrize("motivo", ["http_404", "http_410"])
def test_ausencia_explicita_passa_a_proxima_representacao(monkeypatch, motivo):
    c, cand, chamadas = _executar(monkeypatch, [Unavailable(motivo)])
    resp = c.fetch(cand)
    assert len(chamadas) == 2
    assert resp.url == chamadas[1] == cand.metadata["pdf_consolid"]


def test_todas_ausentes_propaga_a_ultima_ausencia(monkeypatch):
    c, cand, chamadas = _executar(monkeypatch, [Unavailable("http_404")] * 4)
    with pytest.raises(Unavailable) as ei:
        c.fetch(cand)
    assert len(chamadas) == 4
    assert ei.value.reason == "http_404"
