"""FIX9/F-06 e F-13: a classificação da falha de transporte é uma só e depende do estado da chamada.

Propriedade, sobre servidor TCP local real: {0, 1, 2 redirecionamentos} x {fechamento sem bytes,
silêncio até o prazo, status cortado, cabeçalho excessivo, chunk inválido, falha de DNS no salto}
x {200, 503}. Nenhum byte/status recebido em toda a chamada = `fonte_fora` repetível; qualquer
status ou byte recebido = `resposta_inesperada`, um percurso, `saltos` preservados, hook live falha.
"""

from __future__ import annotations

import socketserver
import threading
import time

import pytest

from freoa_verifica import transport
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.httputil import connector_fetch
from tests.live.conftest import _XFAIL_CATEGORIAS
from tests.test_transport import _fast_guards, _wire_local

HOST = "www.planalto.gov.br"
MODOS = ["fechamento", "silencio", "status_cortado", "cabecalho_excessivo", "chunk_invalido", "dns"]
# modos em que o salto final não manda byte algum
SEM_BYTES = {"fechamento", "silencio", "dns"}


def _servidor(n_redirects: int, modo: str, status: int):
    parar = threading.Event()

    class H(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(3)
            try:
                dados = self.request.recv(65536)
                caminho = dados.split(b"\r\n", 1)[0].decode("latin-1").split(" ")[1]
                self.server.percursos.append(caminho)
                i = int(caminho[2:])
                if i < n_redirects:
                    self.request.sendall(
                        f"HTTP/1.1 302 Found\r\nLocation: /h{i + 1}\r\nContent-Length: 0\r\n\r\n".encode()
                    )
                    return
                if modo == "fechamento":
                    return
                if modo == "status_cortado":
                    self.request.sendall(f"HTTP/1.1 {status}".encode())
                elif modo == "cabecalho_excessivo":
                    cab = "".join(f"X-{k}: a\r\n" for k in range(150))
                    self.request.sendall(f"HTTP/1.1 {status} X\r\nContent-Type: text/html\r\n{cab}".encode())
                elif modo == "chunk_invalido":
                    self.request.sendall(
                        f"HTTP/1.1 {status} X\r\nContent-Type: text/html\r\n"
                        "Transfer-Encoding: chunked\r\n\r\nZZ\r\n".encode()
                    )
                parar.wait(10)  # silêncio (ou pausa depois dos bytes) até o prazo
            except OSError:
                pass

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), H)
    server.daemon_threads = True
    server.percursos = []
    server.parar = parar
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _dns_no_salto(monkeypatch, n_redirects: int):
    original = transport.validate_url

    def validar(url, *a, **kw):
        if url.endswith(f"/h{n_redirects}"):
            raise transport.TransportError("Falha de DNS simulada")
        return original(url, *a, **kw)

    monkeypatch.setattr(transport, "validate_url", validar)


@pytest.mark.parametrize("status", [200, 503])
@pytest.mark.parametrize("modo", MODOS)
@pytest.mark.parametrize("n", [0, 1, 2])
def test_classificacao_depende_so_do_estado_da_chamada(monkeypatch, n, modo, status):
    server = _servidor(n, modo, status)
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    if modo == "dns":
        _dns_no_salto(monkeypatch, n)
    esperas: list[float] = []
    monkeypatch.setattr(transport, "_dormir", esperas.append)
    try:
        with pytest.raises(Unavailable) as ei:
            connector_fetch(
                f"https://{HOST}/h0",
                hosts=frozenset({HOST}),
                path_prefixes=None,
                mimes=frozenset({"text/html"}),
                timeout=0.5,
            )
    finally:
        server.parar.set()
        server.shutdown()
        server.server_close()
    u = ei.value
    houve_resposta = n > 0 or modo not in SEM_BYTES
    redirecionamentos = [f"/h{i}" for i in range(n)]
    if houve_resposta:
        assert u.categoria == "resposta_inesperada", (u.reason, u.evidencia)
        assert esperas == []
        assert server.percursos[: n + (0 if modo == "dns" else 1)] == redirecionamentos + (
            [] if modo == "dns" else [f"/h{n}"]
        )
        assert len(server.percursos) == n + (0 if modo == "dns" else 1)  # 1 percurso
        if n:
            assert u.evidencia["saltos"][:n] == [
                {"url": f"https://{HOST}/h{i}", "status": 302} for i in range(n)
            ]
        # hook live: tudo que não é fonte_fora/desafio é falha
        assert u.categoria not in _XFAIL_CATEGORIAS
    else:
        assert u.categoria == "fonte_fora", (u.reason, u.evidencia)
        assert "saltos" not in u.evidencia
        assert u.categoria in _XFAIL_CATEGORIAS
    breaker = transport._circuit_breaker(HOST)
    for _ in range(100):  # no prazo, o worker registra a falha logo depois do controlador
        if breaker.failures:
            break
        time.sleep(0.05)
    assert breaker.failures == 1  # uma falha lógica


def test_dns_sem_resposta_anterior_e_repetivel(monkeypatch):
    """Sem status nem byte na chamada, falha de DNS repete (fonte_fora); com 3 percursos de resolução."""
    _fast_guards(monkeypatch)
    _allow = []
    monkeypatch.setattr(transport, "_dormir", lambda s: None)
    monkeypatch.setattr(transport, "_sortear", lambda a, b: 0.0)

    def validar(url, *a, **kw):
        _allow.append(url)
        raise transport.TransportError("Falha de DNS simulada")

    monkeypatch.setattr(transport, "validate_url", validar)
    with pytest.raises(transport.TransportError):
        transport.fetch(f"https://{HOST}/h0", allowed_hosts=frozenset({HOST}))
    assert len(_allow) == 1 + transport.REPETICOES_PADRAO


def test_falha_de_resolucao_real_vira_transport_error_e_nao_politica(monkeypatch):
    import socket

    def falha(*a, **kw):
        raise socket.gaierror("sem DNS")

    monkeypatch.setattr(socket, "getaddrinfo", falha)
    with pytest.raises(transport.TransportError) as ei:
        transport.validate_url(f"https://{HOST}/x", frozenset({HOST}))
    assert type(ei.value) is transport.TransportError


def test_desafio_na_resposta_nao_engole_erro_de_leitura():
    class Resp:
        status = 503

        def getheaders(self):
            return []

        def read1(self, n):
            import http.client

            raise http.client.IncompleteRead(b"")

    with pytest.raises(transport.RespostaInvalida):
        transport._desafio_na_resposta(Resp())


def test_503_com_chunk_invalido_um_percurso_sem_espera(monkeypatch):
    """Reprodução exata do auditor (F-13): 503 + chunked + tamanho `ZZ`."""
    server = _servidor(0, "chunk_invalido", 503)
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    esperas: list[float] = []
    monkeypatch.setattr(transport, "_dormir", esperas.append)
    try:
        with pytest.raises(Unavailable) as ei:
            connector_fetch(
                f"https://{HOST}/h0",
                hosts=frozenset({HOST}),
                path_prefixes=None,
                mimes=frozenset({"text/html"}),
            )
    finally:
        server.parar.set()
        server.shutdown()
        server.server_close()
    assert server.percursos == ["/h0"] and esperas == []
    assert ei.value.categoria == "resposta_inesperada"


def test_repeticao_apos_503_e_novo_percurso(monkeypatch):
    """O 503 repetível de uma tentativa não contamina a seguinte: fechar sem bytes depois dele é fonte_fora."""
    estado = transport._EstadoChamada()
    estado.resposta_iniciada = True
    estado.saltos.append({"url": "u", "status": 503})
    estado.reiniciar()
    falha, repetivel = transport._classificar(transport.TransportError("fechou"), estado)
    assert type(falha) is transport.TransportError and repetivel
    estado.resposta_iniciada = True
    falha, repetivel = transport._classificar(transport.TransportError("fechou"), estado)
    assert isinstance(falha, transport.RespostaInvalida) and not repetivel
