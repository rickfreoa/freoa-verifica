"""FIX12/F-16: a URL SOLICITADA nesta chamada é validada antes do cache (decisão 0059, emenda FIX12).

Propriedade: para toda URL, o resultado com cache é o resultado sem cache, exceto pelo número de pedidos.
"""

from __future__ import annotations

import pytest

from freoa_verifica import transport as tr
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.guarda import GuardaExecucao
from freoa_verifica.connectors.httputil import connector_fetch
from tests.test_fix9_guarda_execucao import HOST, HTML_OK, ambiente  # noqa: F401

CAMINHO = "/ccivil_03/leis/l7000compilada.htm"
URL = f"https://{HOST}{CAMINHO}"
BASE = {"hosts": frozenset({HOST}), "path_prefixes": None, "mimes": frozenset({"text/html"})}
ROTAS = {CAMINHO: [(200, "text/html", HTML_OK)]}
_VALIDATE_REAL = tr.validate_reference  # o ambiente de teste relaxa a validação; aqui vale a do produto

# (URL pedida, política extra)
VARIANTES = {
    "fragmento": (URL + "#frag", {}),
    "userinfo": (f"https://user:secret@{HOST}{CAMINHO}", {}),
    "porta_invalida": (f"https://{HOST}:bad{CAMINHO}", {}),
    "porta_zero": (f"https://{HOST}:0{CAMINHO}", {}),
    "porta_outra": (f"https://{HOST}:8443{CAMINHO}", {}),
    "esquema_maiusculo": (f"HTTPS://{HOST}{CAMINHO}", {}),
    "ponto_ponto": (f"https://{HOST}/ccivil_03/leis/../leis/l7000compilada.htm", {}),
    "ponto_ponto_codificado": (f"https://{HOST}/ccivil_03/leis/%2e%2e/leis/l7000compilada.htm", {}),
    "barra_codificada": (f"https://{HOST}/ccivil_03%2Fleis/l7000compilada.htm", {}),
    "prefixo_com_percent": (
        f"https://{HOST}/ccivil_03/leis/%6C7000compilada.htm",
        {"path_prefixes": {HOST: ("/ccivil_03/decreto/",)}},
    ),
    "prefixo_proibido": (URL, {"path_prefixes": {HOST: ("/ccivil_03/decreto/",)}}),
    "ipv6_literal": ("https://[2001:db8::1]" + CAMINHO, {}),
    "arroba_no_caminho": (f"https://{HOST}/ccivil_03/leis@evil.com/x", {}),
    "arroba_na_autoridade": (f"https://{HOST}@evil.com{CAMINHO}", {}),
    "barra_invertida": (f"https://{HOST}\\@evil.com{CAMINHO}", {}),
    "host_diferente": (f"https://evil.com{CAMINHO}", {}),
    "controle": (URL + "\n", {}),
    "valida": (URL, {}),
}


def _resultado(url, politica):
    try:
        return ("ok", connector_fetch(url, **{**BASE, **politica}).body)
    except Unavailable as exc:
        return ("recusa", exc.reason, exc.categoria)


@pytest.mark.parametrize("nome", sorted(VARIANTES))
def test_com_cache_igual_a_sem_cache(ambiente, monkeypatch, nome):
    url, politica = VARIANTES[nome]
    server, _ = ambiente(ROTAS)
    monkeypatch.setattr(tr, "validate_reference", _VALIDATE_REAL)
    sem_cache = _resultado(url, politica)
    pedidos_sem_cache = len(server.pedidos)
    with GuardaExecucao().ativar():
        assert _resultado(URL, {})[0] == "ok"  # captura guardada da URL canônica
        pedidos = len(server.pedidos)
        com_cache = _resultado(url, politica)
        assert com_cache == sem_cache
        assert len(server.pedidos) - pedidos <= pedidos_sem_cache  # o cache só pode poupar pedidos
        if pedidos_sem_cache == 0:
            assert len(server.pedidos) == pedidos  # recusa de entrada não gera pedido


def test_entrada_recusada_nao_bloqueia_a_fonte(ambiente, monkeypatch):
    server, _ = ambiente(ROTAS)
    monkeypatch.setattr(tr, "validate_reference", _VALIDATE_REAL)
    with GuardaExecucao().ativar():
        assert _resultado(URL, {})[0] == "ok"
        assert _resultado(URL + "#frag", {})[0] == "recusa"
        assert _resultado(URL, {})[0] == "ok"
