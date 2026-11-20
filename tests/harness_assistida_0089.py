"""Harness EXCLUSIVO de testes: HTTPS loopback e AC efêmera nunca chegam ao produto.

Gera chave/AC sintéticas em tmp_path com OpenSSL já instalado, sem instalar confiança.
Só este módulo passa exceção SPKI e admite IP de loopback. Sem novas dependências Python.
O HTML do harness simula a navegação humana; não é a página inicial do produto.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import os
import shutil
import ssl
import subprocess
import threading
import time
from contextlib import contextmanager

import pytest

from freoa_verifica import transport as t
from freoa_verifica.assistida import ambiente as a
from freoa_verifica.assistida.cdp import AdaptadorCDP, CanalPipe
from freoa_verifica.assistida.perfis import PerfilSessaoAssistida

CORPOS = {
    "utf8": (
        "text/html; charset=utf-8",
        b"<html><body>Art. 1. A\xc3\xa7\xc3\xa3o.</body></html>",
    ),
    "meta": (
        "text/html",
        b'<html><head><meta charset="utf-8"></head><body>A\xc3\xa7\xc3\xa3o.</body></html>',
    ),
    "latin1": (
        "text/html; charset=iso-8859-1",
        b"<html><body>A\xe7\xe3o.</body></html>",
    ),
    "cp1252": (
        "text/html; charset=windows-1252",
        b"<html><body>Pre\xe7o \x80.</body></html>",
    ),
    "utf8_invalido": ("text/html; charset=utf-8", b"<html>\xf0\x9f\x92</html>"),
    "ufffd": ("text/html; charset=utf-8", b"<html>\xef\xbf\xbd</html>"),
    "bom16": ("text/html; charset=utf-8", b"\xff\xfe<\x00h\x00t\x00m\x00l\x00>\x00"),
}


def certificados(path):
    exe = shutil.which("openssl")
    if not exe:
        pytest.skip(
            "harness HTTPS: OpenSSL instalado não encontrado; nenhuma instalação tentada"
        )
    cert, key = path / "ac-sintetica.pem", path / "chave-sintetica.pem"
    subprocess.run(
        [
            exe,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=IP:127.0.0.1",
        ],
        check=True,
        capture_output=True,
    )
    pub = subprocess.run(
        [exe, "x509", "-in", str(cert), "-pubkey", "-noout"],
        check=True,
        capture_output=True,
    ).stdout
    der = subprocess.run(
        [exe, "pkey", "-pubin", "-outform", "DER"],
        input=pub,
        check=True,
        capture_output=True,
    ).stdout
    return cert, key, base64.b64encode(hashlib.sha256(der).digest()).decode()


@contextmanager
def origem_https(path, caso):
    import gzip
    import zlib

    cert, key, spki = certificados(path)
    vistos = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            vistos.append((self.path, list(self.headers.items())))
            ctype, corpo = CORPOS.get(caso, CORPOS["utf8"])
            if caso == "sem_cabecalhos":
                time.sleep(31)
                return
            if caso == "parcial":
                self.connection.sendall(b"HTTP/1.1 200 OK\r\nContent-Typ")
                time.sleep(31)
                return
            status = 302 if caso == "redirect" else 304 if caso == "304" else 200
            encoding = (
                "gzip"
                if caso in {"gzip", "bomba"}
                else "deflate"
                if caso == "deflate"
                else "nao-admitido"
                if caso == "encoding"
                else None
            )
            if caso == "bomba":
                corpo = b"a" * (t.MAX_BYTES + 1)
            wire = (
                gzip.compress(corpo)
                if encoding == "gzip"
                else zlib.compress(corpo)
                if encoding == "deflate"
                else corpo
            )
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header(
                "Content-Length", str(len(wire)) if caso != "cl21" else "1" * 21
            )
            if encoding:
                self.send_header("Content-Encoding", encoding)
            if caso == "redirect":
                self.send_header("Location", "https://127.0.0.1/case/utf8")
            self.end_headers()
            meio = len(wire) // 2
            try:
                self.wfile.write(wire[:meio])
                self.wfile.flush()
                time.sleep(0.3)
                self.wfile.write(wire[meio:])
                self.wfile.flush()
            except (OSError, ssl.SSLError):
                pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 443), Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield spki, vistos
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


@contextmanager
def navegador_pipe(path, monkeypatch, *, nome="brave", spki=None, caso="utf8"):
    if os.name != "nt":
        pytest.skip("0089: pipe Windows exige Windows")
    try:
        _, exe = a.navegador_instalado(nome)
    except a.RecusaSessao as exc:
        pytest.skip(str(exc))
    perfil_dir = path / "perfil"
    perfil_dir.mkdir()
    proc = canal = observador = None
    sessao = None
    pronto = False
    try:
        a.proteger_diretorio(perfil_dir)
        (perfil_dir / "Default" / "Extensions").mkdir(parents=True)
        inicio = path / "inicio-harness.html"
        inicio.write_text(
            '<!doctype html><title>Harness 0089 local</title><script>setTimeout(()=>{location.href="https://127.0.0.1/case/'
            + caso
            + '"},14000)</script>',
            encoding="utf-8",
        )
        if spki:
            produto = a.argumentos

            def argumentos_harness(*args, **kw):
                comando = produto(*args, **kw)
                comando.insert(-1, "--ignore-certificate-errors-spki-list=" + spki)
                return comando

            monkeypatch.setattr(a, "argumentos", argumentos_harness)
            original = t._public_unicast
            monkeypatch.setattr(
                t, "_public_unicast", lambda ip: ip == "127.0.0.1" or original(ip)
            )
        porta = t.PerfilPortaAssistida(
            frozenset({"127.0.0.1"}),
            (
                t.RecursoAssistido(
                    "Document", r"^/case/[a-z0-9_]+$", "^$", frozenset({"text/html"})
                ),
            ),
            (),
            "Origem exclusivamente sintética do harness HTTPS local.",
        )
        perfil = PerfilSessaoAssistida("harness", porta, "documento", None)
        sessao = t.SessaoPortaAssistida(porta, navegador="Brave harness")
        vigia = a.Vigilancia(perfil_dir, exe)
        observador = a.ObservadorWindows(vigia)
        proc, leitura, escrita = a.lancar_pipe(exe, perfil_dir, inicio.as_uri())
        canal = CanalPipe(leitura, escrita, sessao)
        ad = AdaptadorCDP(perfil, sessao, canal, vigia)
        canal.iniciar()
        ad.iniciar()
        limite = time.monotonic() + 10
        while ad.fase < 3:
            if time.monotonic() > limite or proc.poll() is not None:
                pytest.skip(
                    "PIPE_ASSISTIDO_INDISPONIVEL: Brave sem handshake CDP em 10 s"
                )
            msg = canal.receber()
            if msg:
                with msg as obj:
                    ad.processar(obj)
        pronto = True
        yield ad, proc, vigia
    except a.RecusaSessao as exc:
        if pronto:
            raise
        pytest.skip("pré-requisito de navegador/pipe: " + str(exc))
    finally:
        if proc is not None:
            a.fechar_navegador(proc)
        if canal is not None:
            canal.fechar()
        if sessao is not None:
            sessao.encerrar()
        if observador is not None:
            observador.fechar()
