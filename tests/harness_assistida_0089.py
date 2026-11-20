"""Harness EXCLUSIVO de testes: HTTPS loopback e AC efêmera nunca chegam ao produto.

Gera chave/AC sintéticas em tmp_path com OpenSSL já instalado, sem instalar confiança.
Só este módulo passa exceção SPKI e admite IP de loopback. Sem novas dependências Python.
O HTML do harness simula a navegação humana; não é a página inicial do produto.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import shutil
import ssl
import subprocess
import threading
import time
from contextlib import ExitStack, contextmanager

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


def sinal_unico(script):
    # O documento antigo continua vivo enquanto a navegação espera cabeçalhos.
    # A sondagem do arquivo não pode disparar outra navegação e abortar a primeira.
    return "if(!window.disparou0089){window.disparou0089=true;" + script + "}"


def responder_condicao_item1(handler, caso, manter_aberta, estado):
    """Condições sintéticas; a conexão só é liberada no teardown do ensaio."""
    if caso in {"sem_cabecalhos", "parcial", "sem_termino"}:
        if caso == "parcial":
            handler.connection.sendall(b"HTTP/1.1 200 OK\r\nContent-Typ")
        elif caso == "sem_termino":
            handler.connection.sendall(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                b"Content-Length: 999\r\n\r\n"
            )
            # Dá ao consumidor a mesma janela de streaming dos casos positivos.
            time.sleep(0.3)
            handler.connection.sendall(b"<html>")
        estado["respostas"].append({"caso": caso, "inicio": time.monotonic()})
        manter_aberta.wait()  # sem sleep/fechamento concorrendo com os 30 s da porta
        return True
    if caso != "304":
        return False
    if handler.path == "/driver":
        corpo = (
            b"<!doctype html><script>(async()=>{"
            b"await fetch('/case/304').then(r=>r.text());"
            b"await fetch('/case/304',{cache:'no-cache'}).then(r=>r.text()).catch(()=>{});"
            b"await fetch('/done')})().catch(()=>fetch('/erro_driver'))</script>"
        )
        status = 200
        headers = [("Cache-Control", "no-store")]
    elif handler.path == "/case/304":
        condicional = handler.headers.get("If-None-Match") == '"0089-etag"'
        status = 304 if condicional else 200
        corpo = b"" if condicional else CORPOS["utf8"][1]
        headers = [
            ("Cache-Control", "public, max-age=0, must-revalidate"),
            ("ETag", '"0089-etag"'),
        ]
        estado["respostas"].append({"status": status, "condicional": condicional})
    else:
        corpo, status, headers = b"", 404, []
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    # 304 não tem corpo; omitir CL evita declarar tamanho zero do recurso em cache.
    if status != 304:
        handler.send_header("Content-Length", str(len(corpo)))
    for nome, valor in headers:
        handler.send_header(nome, valor)
    handler.end_headers()
    if corpo:
        meio = len(corpo) // 2
        handler.wfile.write(corpo[:meio])
        handler.wfile.flush()
        time.sleep(0.3)
        handler.wfile.write(corpo[meio:])
        handler.wfile.flush()
    return True


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
            "subjectAltName=IP:127.0.0.1,DNS:hsts.0089.test",
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
def origem_https(path, caso, *, atraso_primeiro_byte=0.15, estado=None):
    """150 ms emulam latência de rede na origem, não comportamento do navegador."""
    import gzip
    import zlib

    cert, key, spki = certificados(path)
    vistos = []
    estado = estado if estado is not None else {}
    estado["respostas"] = []
    manter_aberta = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1" if caso == "304" else "HTTP/1.0"

        def log_message(self, *_):
            pass

        def do_GET(self):
            vistos.append((self.path, list(self.headers.items())))
            time.sleep(atraso_primeiro_byte)
            ctype, corpo = CORPOS.get(caso, CORPOS["utf8"])
            if responder_condicao_item1(self, caso, manter_aberta, estado):
                return
            status = 302 if caso == "redirect" else 200
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
            if caso == "redirect" and self.path == "/case/utf8":
                status = 200
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header(
                "Content-Length", str(len(wire)) if caso != "cl21" else "1" * 21
            )
            if encoding:
                self.send_header("Content-Encoding", encoding)
            if status == 302:
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
        manter_aberta.set()
        server.shutdown()
        server.server_close()
        thread.join(2)


@contextmanager
def navegador_pipe(
    path,
    monkeypatch,
    *,
    nome="brave",
    spki=None,
    caso="utf8",
    script=None,
    observar=True,
    hsts=False,
):
    if os.name != "nt":
        pytest.skip("0089: pipe Windows exige Windows")
    try:
        _, exe = a.navegador_instalado(nome)
    except a.RecusaSessao as exc:
        pytest.skip(str(exc))
    # Mesma conferência de produto; política vedada nunca vira skip de pipe/ACL.
    a.conferir_politicas(nome)
    perfil_dir = path / "sessao-0089-harness"
    perfil_dir.mkdir()
    proc = canal = observador = None
    sessao = None
    protocolo_iniciado = False
    try:
        a.proteger_diretorio(perfil_dir)
        (perfil_dir / "Default" / "Extensions").mkdir(parents=True)
        inicio = path / "inicio-harness.html"
        sinal = path / "pronto-harness.js"
        sinal.write_text(
            "/* aguardando inventário e linha de base */", encoding="utf-8"
        )
        inicio.write_text(
            "<!doctype html><title>Harness 0089 local</title><script>"
            'function aguardar(){const s=document.createElement("script");'
            's.src="pronto-harness.js?"+Date.now();'
            "s.onload=s.onerror=()=>{s.remove();setTimeout(aguardar,100)};"
            "document.head.appendChild(s)}aguardar()</script>",
            encoding="utf-8",
        )
        if spki:
            produto = a.argumentos

            def argumentos_harness(*args, **kw):
                comando = produto(*args, **kw)
                comando.insert(-1, "--ignore-certificate-errors-spki-list=" + spki)
                if hsts:
                    comando.insert(
                        -1, "--host-resolver-rules=MAP hsts.0089.test 127.0.0.1"
                    )
                return comando

            monkeypatch.setattr(a, "argumentos", argumentos_harness)
            original = t._public_unicast
            monkeypatch.setattr(
                t, "_public_unicast", lambda ip: ip == "127.0.0.1" or original(ip)
            )
        porta = t.PerfilPortaAssistida(
            frozenset({"127.0.0.1", "hsts.0089.test"} if hsts else {"127.0.0.1"}),
            (
                *(
                    t.RecursoAssistido(
                        tipo, r"^/case/[A-Za-z0-9_]+$", "^$", frozenset({"text/html"})
                    )
                    for tipo in ("Document", "XHR", "Fetch")
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
        if not observar:
            protocolo_iniciado = (
                True  # erros de inventário após lançar são falhas, não skips
            )
            # Controle: mesmo pipe e flags, nenhum cliente envia comandos/anexa.
            limite = vigia.limite_inventario + 10
            while vigia.assentar() is None:
                if time.monotonic() >= limite or proc.poll() is not None:
                    raise a.RecusaSessao("AMBIENTE_NAO_ASSENTADO")
                time.sleep(0.05)
            sinal.write_text(
                sinal_unico(script or "location.href='https://127.0.0.1/case/utf8';"),
                encoding="utf-8",
            )
            try:
                yield None, proc, vigia
            finally:
                leitura.close()
                escrita.close()
            return
        canal = CanalPipe(leitura, escrita, sessao)
        ad = AdaptadorCDP(perfil, sessao, canal, vigia)
        canal.iniciar()
        protocolo_iniciado = True
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
        # Fase 3 só conclui o handshake do navegador; o alvo ainda precisa do
        # inventário, da linha de base e da sequência CDP completa.
        while vigia.linha_base is None or not any(x.pronto for x in ad.alvos.values()):
            if proc.poll() is not None:
                raise a.RecusaSessao("NAVEGADOR_ENCERRADO_ANTES_DA_PRONTIDAO")
            if time.monotonic() >= vigia.limite_inventario + 10:
                raise a.RecusaSessao("AMBIENTE_NAO_ASSENTADO")
            ad.passo()
        # Só o HTML de teste simula a ação humana, após prontidão observada.
        sinal.write_text(
            sinal_unico(
                script
                or "location.href=" + json.dumps("https://127.0.0.1/case/" + caso) + ";"
            ),
            encoding="utf-8",
        )
        yield ad, proc, vigia
    except a.RecusaSessao as exc:
        if protocolo_iniciado:
            raise
        pytest.skip("pré-requisito de navegador/pipe: " + str(exc))
    finally:
        # Executa toda a limpeza mesmo se um fechamento anterior falhar.
        with ExitStack() as limpeza:
            limpeza.callback(limpar_perfil_harness, perfil_dir, path)
            if observador is not None:
                limpeza.callback(observador.fechar)
            if sessao is not None:
                limpeza.callback(sessao.encerrar)
            if canal is not None:
                limpeza.callback(canal.fechar)
            if proc is not None:
                limpeza.callback(a.fechar_navegador, proc, perfil_dir)


def limpar_perfil_harness(perfil, raiz):
    """§3(7): usa a limpeza do produto e torna sobra de perfil falha explícita."""
    try:
        a.limpar_diretorio(perfil, raiz)
        assert not perfil.exists(), "perfil ainda existe após limpar_diretorio"
    except Exception as exc:
        print(f"LIMPEZA_PERFIL_HARNESS_FALHOU: {perfil}: {type(exc).__name__}: {exc}")
        raise
