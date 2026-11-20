"""Origem sintética HTTP/2 para 103: Chromium ignora Early Hints em HTTP/1.x.

Somente harness. Requer o extra test-navegador; nenhuma dependência do produto.
"""

from contextlib import contextmanager
import socket
import socketserver
import ssl
import threading
import time

import pytest

from tests.harness_assistida_0089 import certificados


def responder_h2(conexao, caminho, stream_id, estado, *, hints=False):
    """Responde em memória; o handler separa 103, headers finais e blocos no tempo."""
    from tests.harness_assistida_0089_cenarios import driver, pagina

    if hints:
        conexao.send_headers(
            stream_id,
            [
                (":status", "103"),
                ("link", "</case/hinted>; rel=preload; as=script"),
            ],
        )
        return None
    tipo = "text/html; charset=utf-8"
    status = "200"
    if caminho == "/driver":
        corpo = driver("early_hints")
    elif caminho == "/case/early_hints":
        corpo = pagina("fetch('/done')")
    elif caminho == "/case/hinted":
        corpo, tipo = b"/* preload sintetico 0089 */", "application/javascript"
    elif caminho == "/done":
        estado["marcas"].append(caminho)
        corpo, tipo = b"ok", "text/plain"
    else:
        corpo, status = b"ausente", "404"
        if caminho == "/erro_driver":
            estado["erros"].append("driver")
    conexao.send_headers(
        stream_id,
        [
            (":status", status),
            ("content-type", tipo),
            ("content-length", str(len(corpo))),
            ("cache-control", "no-store"),
        ],
    )
    return corpo


@contextmanager
def origem_early_hints_h2(path, *, atraso_primeiro_byte=0.15):
    pytest.importorskip(
        "h2",
        reason="Early Hints exige origem HTTP/2; instale o extra .[test-navegador] no ambiente do ensaio real",
    )
    from h2.config import H2Configuration
    from h2.connection import H2Connection
    from h2.events import (
        ConnectionTerminated,
        DataReceived,
        RequestReceived,
        StreamReset,
    )

    cert, key, spki = certificados(path)
    estado = {"pedidos": [], "marcas": [], "erros": [], "protocolos": []}

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            protocolo = self.request.selected_alpn_protocol()
            estado["protocolos"].append(protocolo)
            if protocolo != "h2":
                estado["erros"].append("ALPN_SEM_H2")
                return
            conexao = H2Connection(
                config=H2Configuration(client_side=False, header_encoding="utf-8")
            )
            conexao.initiate_connection()
            self.request.sendall(conexao.data_to_send())
            self.request.settimeout(0.02)
            pendentes = {}
            limite = time.monotonic() + 90
            try:
                while time.monotonic() < limite:
                    try:
                        data = self.request.recv(65536)
                    except socket.timeout:
                        data = None
                    if data == b"":
                        return
                    for evento in conexao.receive_data(data) if data else []:
                        if isinstance(evento, RequestReceived):
                            campos = dict(evento.headers)
                            caminho = campos[":path"]
                            estado["pedidos"].append(
                                (campos[":method"], caminho, tuple(evento.headers))
                            )
                            pendentes[evento.stream_id] = (
                                time.monotonic() + atraso_primeiro_byte,
                                caminho,
                                "inicio",
                            )
                        elif isinstance(evento, DataReceived):
                            conexao.acknowledge_received_data(
                                evento.flow_controlled_length, evento.stream_id
                            )
                        elif isinstance(evento, StreamReset):
                            pendentes.pop(evento.stream_id, None)
                        elif isinstance(evento, ConnectionTerminated):
                            return
                    for sid, (quando, caminho, fase) in list(pendentes.items()):
                        if time.monotonic() < quando:
                            continue
                        if fase == "inicio" and caminho == "/case/early_hints":
                            responder_h2(conexao, caminho, sid, estado, hints=True)
                            pendentes[sid] = (time.monotonic() + 0.5, caminho, "final")
                        elif isinstance(fase, bytes):
                            conexao.send_data(sid, fase, end_stream=True)
                            del pendentes[sid]
                        else:
                            corpo = responder_h2(conexao, caminho, sid, estado)
                            meio = len(corpo) // 2
                            conexao.send_data(sid, corpo[:meio])
                            pendentes[sid] = (
                                time.monotonic() + 0.3,
                                caminho,
                                corpo[meio:],
                            )
                    saida = conexao.data_to_send()
                    if saida:
                        self.request.sendall(saida)
            except OSError:
                # O navegador fecha sockets no encerramento do cenário.
                return

    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = True

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    ctx.set_alpn_protocols(["h2"])
    with Server(("127.0.0.1", 443), Handler) as server:
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield spki, estado
        finally:
            server.shutdown()
            thread.join(2)
