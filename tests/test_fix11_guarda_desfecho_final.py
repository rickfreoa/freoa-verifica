"""FIX11/F-11: a guarda registra o desfecho final do conector, depois da reclassificação (decisão 0048)."""

from __future__ import annotations

import pytest

from freoa_verifica import transport as tr
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.guarda import GuardaExecucao
from freoa_verifica.connectors.planalto import PlanaltoConnector

HOST = "www.planalto.gov.br"


@pytest.fixture
def rede(monkeypatch):
    """Transporte real (repetição, breaker) sobre uma tentativa simulada que sempre falha com `erro`."""
    tr.reset_guards()
    r = type("Rede", (), {})()
    r.pedidos, r.erro = [], None
    monkeypatch.setattr(tr, "_rate_limiter", lambda host: tr.TokenBucket(rate=1000.0, capacity=1000.0))
    monkeypatch.setattr(tr, "_dormir", lambda s: None)
    monkeypatch.setattr(tr, "_sortear", lambda a, b: 0.0)

    def uma_vez(url, **kw):
        r.pedidos.append(url)
        raise r.erro

    monkeypatch.setattr(tr, "_fetch_once", uma_vez)
    r.falhas = lambda: tr._circuit_breaker(HOST).failures
    yield r
    tr.reset_guards()


def _lei(numero: int):
    c = PlanaltoConnector()
    return c, c.resolve({"tipo": "LEI", "numero": numero, "ano": 2020})


@pytest.mark.parametrize("erro", [tr.TransportError("fechou sem resposta"), tr.Timeout("prazo")], ids=["fechou", "timeout"])
@pytest.mark.parametrize("segunda", [7001, 8123])
def test_recusa_reclassificada_do_planalto_bloqueia_o_host(rede, erro, segunda):
    rede.erro = erro
    guarda = GuardaExecucao()
    with guarda.ativar():
        c, primeira = _lei(7000)
        with pytest.raises(Unavailable) as ei:
            c.fetch(primeira)
        assert (ei.value.reason, ei.value.categoria) == ("recusa_identificado_planalto", "recusa_identificado")
        pedidos, falhas = len(rede.pedidos), rede.falhas()
        assert HOST in guarda.bloqueios and guarda.bloqueios[HOST].categoria == "recusa_identificado"
        assert falhas == 1

        c, outra = _lei(segunda)
        with pytest.raises(Unavailable) as ei:
            c.fetch(outra)
    assert ei.value.categoria == "recusa_identificado"
    assert ei.value.evidencia["bloqueio_fonte"] == HOST
    assert len(rede.pedidos) == pedidos  # a segunda lei não fez pedido
    assert rede.falhas() == 1  # e o breaker continua em 1


def test_sem_guarda_a_reclassificacao_continua_valendo(rede):
    rede.erro = tr.TransportError("fechou sem resposta")
    c, cand = _lei(7000)
    with pytest.raises(Unavailable) as ei:
        c.fetch(cand)
    assert (ei.value.reason, ei.value.categoria) == ("recusa_identificado_planalto", "recusa_identificado")


def test_resposta_http_503_nao_bloqueia_o_host(rede):
    rede.erro = tr.HTTPStatusError(503)
    guarda = GuardaExecucao()
    with guarda.ativar():
        c, primeira = _lei(7000)
        with pytest.raises(Unavailable):
            c.fetch(primeira)
        antes = len(rede.pedidos)
        c, outra = _lei(7001)
        with pytest.raises(Unavailable):
            c.fetch(outra)
    assert guarda.bloqueios == {}
    assert len(rede.pedidos) > antes
