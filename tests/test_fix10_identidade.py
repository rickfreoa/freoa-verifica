"""FIX10/F-08: a guarda usa a mesma canonicalização de URL que o transporte usa para validar o destino."""

from __future__ import annotations

import pytest

from freoa_verifica import transport
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.guarda import GuardaExecucao
from tests.test_fix9_guarda_execucao import (  # noqa: F401  (fixture `ambiente` e utilitários)
    CAPTCHA,
    HOST,
    HTML_OK,
    _baixar,
    ambiente,
)

CAMINHO = "/ccivil_03/leis/l7000compilada.htm"
VARIANTES = {
    "normal": f"https://{HOST}{CAMINHO}",
    "porta_443": f"https://{HOST}:443{CAMINHO}",
    "ponto_final": f"https://{HOST}.{CAMINHO}",
    "maiusculas": f"https://{HOST.upper()}{CAMINHO}",
    "esquema_maiusculo": f"HTTPS://{HOST}{CAMINHO}",
    "fragmento": f"https://{HOST}{CAMINHO}#art1",
    "ponto_final_e_porta": f"https://{HOST.upper()}.:443{CAMINHO}",
}


@pytest.mark.parametrize("nome", list(VARIANTES))
def test_identidade_igual_a_da_variante_normal(nome):
    ref = transport.identidade_requisicao("GET", VARIANTES["normal"])
    assert transport.identidade_requisicao("get", VARIANTES[nome]) == ref


def test_percent_encoding_de_nao_reservado_e_mesma_identidade():
    a = transport.identidade_requisicao("GET", f"https://{HOST}/a~b?q=%7e&p=%2f")
    b = transport.identidade_requisicao("GET", f"https://{HOST}/a%7Eb?q=~&p=%2F")
    assert a == b


def test_query_ordenada_mas_valores_distintos_seguem_distintos():
    base = f"https://{HOST}/x"
    assert transport.identidade_requisicao("GET", base + "?a=1&b=2") == transport.identidade_requisicao("GET", base + "?b=2&a=1")
    assert transport.identidade_requisicao("GET", base + "?a=1") != transport.identidade_requisicao("GET", base + "?a=2")
    assert transport.identidade_requisicao("GET", base) != transport.identidade_requisicao("POST", base)
    assert transport.identidade_requisicao("GET", base) != transport.identidade_requisicao("GET", base + "/y")
    assert transport.identidade_requisicao("GET", base) != transport.identidade_requisicao("GET", "https://outro.gov.br/x")


# "fragmento" fica de fora: o transporte recusa fragmento e a entrada atual é validada antes do cache (FIX12/F-16)
@pytest.mark.parametrize("nome", [n for n in VARIANTES if n not in ("normal", "fragmento")])
@pytest.mark.parametrize(
    "resposta,pedidos,incrementos",
    [
        ((200, "text/html", HTML_OK), 1, 0),
        ((503, "text/html", b"fora"), 3, 1),  # o transporte repete 502/503/504 dentro de um percurso
        ((503, "text/html", b"fora", {"Retry-After": "3600"}), 1, 1),
        ((403, "text/html", CAPTCHA), 1, 1),
    ],
    ids=["200", "503", "503-retry-after", "captcha"],
)
def test_variantes_da_mesma_url_fazem_um_unico_percurso(ambiente, nome, resposta, pedidos, incrementos):
    server, contados = ambiente({CAMINHO: [resposta]})
    guarda = GuardaExecucao()
    saidas = []
    with guarda.ativar():
        for url in (VARIANTES["normal"], VARIANTES[nome]):
            try:
                saidas.append(_baixar(url).body)
            except Unavailable as u:
                saidas.append((u.reason, u.categoria))
    assert saidas[0] == saidas[1]
    assert len(server.pedidos) == pedidos
    assert len(contados) == incrementos


@pytest.mark.parametrize("nome", ["porta_443", "ponto_final", "maiusculas", "ponto_final_e_porta"])
def test_apos_captcha_a_variante_nao_faz_novo_pedido(ambiente, nome):
    server, _ = ambiente({CAMINHO: [(403, "text/html", CAPTCHA)], "/outra": [(200, "text/html", HTML_OK)]})
    guarda = GuardaExecucao()
    with guarda.ativar():
        with pytest.raises(Unavailable):
            _baixar(VARIANTES["normal"])
        with pytest.raises(Unavailable) as ei:
            _baixar(VARIANTES[nome])
        with pytest.raises(Unavailable):  # o bloqueio é por host efetivo, também para outro caminho
            _baixar(VARIANTES[nome].replace(CAMINHO, "/outra"))
    assert ei.value.categoria == "ambiental_desafio"
    assert len(server.pedidos) == 1


# --- F-11: bloqueio pelo host de cada salto -----------------------------------------------------

HOSTS = frozenset({HOST, "planalto.gov.br", "legis.planalto.gov.br"})
ALVO = "https://planalto.gov.br/target"


def _pedir(url):
    from freoa_verifica.connectors.httputil import connector_fetch

    return connector_fetch(url, hosts=HOSTS, path_prefixes=None, mimes=frozenset({"text/html"}))


@pytest.mark.parametrize(
    "categoria,resposta",
    [
        ("ambiental_desafio", (403, "text/html", CAPTCHA)),
        ("recusa_identificado", (403, "text/html", b"negado")),
    ],
)
def test_host_que_desafiou_no_salto_e_bloqueado_e_nao_visitado(ambiente, categoria, resposta):
    server, incrementos = ambiente({
        "/start": [(302, "text/html", b"", {"Location": ALVO})],
        "/start2": [(302, "text/html", b"", {"Location": ALVO})],
        "/target": [resposta],
        "/direto": [(200, "text/html", HTML_OK)],
    })
    guarda = GuardaExecucao()
    with guarda.ativar():
        with pytest.raises(Unavailable) as primeira:
            _pedir(f"https://{HOST}/start")
        assert primeira.value.categoria == categoria
        assert [p[1] for p in server.pedidos] == ["/start", "/target"]
        assert {"www.planalto.gov.br", "planalto.gov.br"} <= set(guarda.bloqueios)
        antes = len(incrementos)
        # consulta direta ao host que de fato desafiou
        with pytest.raises(Unavailable) as direta:
            _pedir("https://planalto.gov.br/direto")
        assert direta.value.categoria == categoria
        # host inicial ainda livre cujo redirecionamento leva ao host bloqueado: o salto é recusado
        with pytest.raises(Unavailable) as salto:
            _pedir("https://legis.planalto.gov.br/start2")
        assert salto.value.categoria == categoria
    assert [p[1] for p in server.pedidos] == ["/start", "/target", "/start2"]  # nenhum novo /target
    assert len(incrementos) == antes  # a recusa do salto não conta como falha da fonte
