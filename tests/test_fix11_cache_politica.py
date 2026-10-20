"""FIX11/F-16: a captura guardada só é entregue depois de revalidada contra a política da chamada ATUAL.

Sem novo pedido; a recusa é a mesma que a chamada receberia sem cache. A política não entra na chave.
"""

from __future__ import annotations

import pytest

from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.guarda import GuardaExecucao
from freoa_verifica.connectors.httputil import connector_fetch
from tests.test_fix9_guarda_execucao import CAPTCHA, HOST, HTML_OK, ambiente  # noqa: F401

CAMINHO = "/ccivil_03/leis/l7000compilada.htm"
URL = f"https://{HOST}{CAMINHO}"
BASE = {"hosts": frozenset({HOST}), "path_prefixes": None, "mimes": frozenset({"text/html"})}

# política da segunda chamada que o transporte recusaria sobre a mesma resposta
RECUSAS = {
    "host_proibido": {"hosts": frozenset({"outro.gov.br"})},
    "caminho_proibido": {"path_prefixes": {HOST: ("/ccivil_03/decreto/",)}},
    "mime_restrito": {"mimes": frozenset({"application/pdf"})},
    "max_bytes_1": {"max_bytes": 1},
    "max_bytes_abaixo_do_tamanho": {"max_bytes": len(HTML_OK) - 1},
    "mime_de_outro_tipo": {"mimes": frozenset({"application/json", "text/plain"})},
}


def _baixar(url=URL, **politica):
    return connector_fetch(url, **{**BASE, **politica})


def _sem_cache(ambiente_, politica, rotas):
    """O que a chamada receberia sem guarda: reproduz a recusa pelo transporte."""
    server, _ = ambiente_(rotas)
    with pytest.raises(Unavailable) as ei:
        _baixar(**politica)
    return ei.value


@pytest.mark.parametrize("nome", sorted(RECUSAS))
def test_politica_atual_recusa_a_captura_guardada_sem_novo_pedido(ambiente, nome):
    server, _ = ambiente({CAMINHO: [(200, "text/html", HTML_OK)]})
    guarda = GuardaExecucao()
    with guarda.ativar():
        assert _baixar().body == HTML_OK  # captura guardada
        pedidos = len(server.pedidos)
        with pytest.raises(Unavailable) as ei:
            _baixar(**RECUSAS[nome])
        assert len(server.pedidos) == pedidos
        # a captura continua servida a quem a política permite
        assert _baixar().body == HTML_OK
    assert len(server.pedidos) == pedidos
    esperado = _sem_cache(ambiente, RECUSAS[nome], {CAMINHO: [(200, "text/html", HTML_OK)]})
    assert (ei.value.reason, ei.value.categoria) == (esperado.reason, esperado.categoria)


def test_destino_de_redirecionamento_fora_da_politica_atual_e_recusado(ambiente):
    rotas = {
        CAMINHO: [(302, "text/html", b"x", {"Location": f"https://{HOST}/ccivil_03/destino.htm"})],
        "/ccivil_03/destino.htm": [(200, "text/html", HTML_OK)],
    }
    server, _ = ambiente(rotas)
    with GuardaExecucao().ativar():
        assert _baixar().body == HTML_OK
        pedidos = len(server.pedidos)
        for politica in (
            {"path_prefixes": {HOST: (CAMINHO,)}},  # URL pedida permitida, destino do salto não
            {"max_redirects": 0},
        ):
            with pytest.raises(Unavailable):
                _baixar(**politica)
        assert len(server.pedidos) == pedidos


def test_deteccao_de_desafio_da_chamada_atual_vale_sobre_a_captura_guardada(ambiente):
    server, _ = ambiente({CAMINHO: [(200, "text/html", CAPTCHA)]})
    guarda = GuardaExecucao()
    with guarda.ativar():
        _baixar(check_challenge=False)  # primeira chamada não procurava desafio
        with pytest.raises(Unavailable) as ei:
            _baixar()  # a segunda procura
    assert ei.value.categoria == "ambiental_desafio"
    assert len(server.pedidos) == 1
    assert HOST in guarda.bloqueios  # e o desafio bloqueia a fonte como se tivesse sido visto ao vivo


def test_falha_de_uma_politica_nao_vale_para_politica_mais_permissiva(ambiente):
    server, _ = ambiente({CAMINHO: [(200, "text/html", HTML_OK)]})
    with GuardaExecucao().ativar():
        with pytest.raises(Unavailable):
            _baixar(max_bytes=1)  # recusada pelo limite desta chamada
        assert _baixar().body == HTML_OK  # outra política: sem a recusa que não é dela
        assert _baixar().body == HTML_OK  # e agora há captura guardada
    assert len(server.pedidos) == 2


def test_mesma_politica_continua_um_unico_pedido(ambiente):
    server, _ = ambiente({CAMINHO: [(200, "text/html", HTML_OK)]})
    with GuardaExecucao().ativar():
        for _ in range(3):
            assert _baixar().body == HTML_OK
        with pytest.raises(Unavailable):
            _baixar(max_bytes=1)
        with pytest.raises(Unavailable):
            _baixar(max_bytes=1)
    assert len(server.pedidos) == 1  # as recusas por política saem da captura guardada, sem rede
