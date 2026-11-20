"""Origem HTTPS exclusivamente sintética, drivers JS e observações do harness.

Nenhuma automação/CDP de navegação: somente as páginas locais disparam ações.
O log bruto de pedidos pertence à origem sintética, nunca ao produto.
"""

from contextlib import contextmanager
from collections import Counter, defaultdict
import gzip
import hashlib
import http.server
import json
from pathlib import Path
import ssl
import threading
import time
from urllib.parse import urlsplit

import pytest

from tests.gerar_0089_wire import BODY
from tests.harness_assistida_0089 import certificados

BASE = "https://127.0.0.1"
SEGREDOS = {
    k: "SEGREDO_SINTETICO_0089_" + k.upper()
    for k in ("cookie", "auth", "query", "ctype", "corpo")
}
PUBLICO_CAMINHO = "TOKEN_PUBLICO_0089"
PUBLICO_CORPO = "Pessoa Sintética Publicada"


def pagina(script):
    return (
        "<!doctype html><meta charset=utf-8><body><script>"
        + script
        + "</script></body>"
    ).encode()


def driver(caso):
    fim = "await fetch('/done');"
    fetch = "await fetch('/case/" + caso + "').then(r=>r.text()).catch(()=>{});"
    scripts = {
        "cache": fetch + fetch + fim,
        "reload": "if(!sessionStorage.recarregou){sessionStorage.recarregou='1';location.href='/case/reload'}",
        "sw": "await navigator.serviceWorker.register('/sw.js',{scope:'/'});await navigator.serviceWorker.ready;if(!navigator.serviceWorker.controller)await new Promise(r=>navigator.serviceWorker.addEventListener('controllerchange',r,{once:true}));await fetch('/case/sw');"
        + fim,
        "prefetch": "let l=document.createElement('link');l.rel='prefetch';l.href='/case/prefetch';document.head.append(l);await new Promise(r=>setTimeout(r,2500));location.href='/case/prefetch';",
        "prerender": "let s=document.createElement('script');s.type='speculationrules';s.textContent=JSON.stringify({prerender:[{source:'list',urls:['/case/prerender']}]});document.head.append(s);let pronto=false;for(let i=0;i<40&&!pronto;i++){await new Promise(r=>setTimeout(r,200));pronto=await fetch('/sonda/prerender').then(r=>r.json())}if(pronto){location.href='/case/prerender'}else{await fetch('/indisponivel/prerender');await fetch('/done')}",
        "bfcache": "location.href='/case/bfcache'",
        "early_hints": "location.href='/case/early_hints'",
        "iframe": "let f=document.createElement('iframe');f.src='/case/iframe';document.body.append(f);await new Promise(r=>f.onload=r);"
        + fim,
        "iframe_xhr": "let f=document.createElement('iframe');f.src='/frame';document.body.append(f);await new Promise(r=>setTimeout(r,2500));"
        + fim,
        "blob": "let b=new Blob(['<html>blob sintetico</html>'],{type:'text/html'});let f=document.createElement('iframe');f.src=URL.createObjectURL(b);document.body.append(f);await new Promise(r=>f.onload=r);"
        + fim,
        "data": "let f=document.createElement('iframe');f.src='data:text/html,<html>data sintetico</html>';document.body.append(f);await new Promise(r=>f.onload=r);"
        + fim,
        "download": "location.href='/case/download';await new Promise(r=>setTimeout(r,2000));"
        + fim,
        "websocket": "let w=new WebSocket('wss://127.0.0.1/ws');await new Promise(r=>{w.onopen=()=>{w.close();r()};w.onerror=r});"
        + fim,
        "post": "await fetch('/case/post',{method:'POST',body:'sintetico'});" + fim,
        "cookie": "document.cookie='nao_declarado=valor_sintetico; Secure; SameSite=Strict';"
        + fetch
        + fim,
        "fetch_identity": fetch + fim,
        "fetch_gzip": fetch + fim,
        "xhr_identity": "await new Promise(r=>{let x=new XMLHttpRequest();x.open('GET','/case/xhr_identity');x.onloadend=r;x.send()});"
        + fim,
        "xhr_gzip": "await new Promise(r=>{let x=new XMLHttpRequest();x.open('GET','/case/xhr_gzip');x.onloadend=r;x.send()});"
        + fim,
        "passividade": "await fetch('/case/passividade').then(r=>r.text());" + fim,
        "segredos": (
            "await fetch('/case/auth',{headers:{Authorization:'Bearer "
            + SEGREDOS["auth"]
            + "'}});"
            "document.cookie='nao_declarado="
            + SEGREDOS["cookie"]
            + "; Secure; SameSite=Strict';"
            "await fetch('/case/cookie');document.cookie='nao_declarado=; Max-Age=0; path=/';"
            "await fetch('/case/query?token=" + SEGREDOS["query"] + "');"
            "await fetch('/case/ctype');await fetch('/case/corpo');"
            "await fetch('/case/" + PUBLICO_CAMINHO + "');" + fim
        ),
    }
    return pagina(
        "(async()=>{" + scripts[caso] + "})().catch(()=>fetch('/erro_driver'))"
    )


@contextmanager
def cenarios_https(path, caso, *, atraso_primeiro_byte=0.15):
    """Atraso na origem até os headers: emulação de rede, sem alterar o cliente."""
    if caso == "early_hints":
        from tests.harness_assistida_0089_h2 import origem_early_hints_h2

        with origem_early_hints_h2(
            path, atraso_primeiro_byte=atraso_primeiro_byte
        ) as resultado:
            yield resultado
        return
    cert, key, spki = certificados(path)
    estado = {"pedidos": [], "marcas": [], "erros": []}

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_):
            pass

        def enviar(
            self,
            corpo,
            *,
            tipo="text/html; charset=utf-8",
            headers=(),
            status=200,
            pausa=True,
        ):
            self.send_response(status)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            for k, v in headers:
                self.send_header(k, v)
            self.end_headers()
            try:
                meio = max(1, len(corpo) // 2)
                self.wfile.write(corpo[:meio])
                self.wfile.flush()
                if pausa:
                    time.sleep(
                        0.3
                    )  # segmentação do corpo, não corrige streaming tardio
                self.wfile.write(corpo[meio:])
                self.wfile.flush()
            except OSError:
                pass

        def registrar(self):
            estado["pedidos"].append(
                (self.command, self.path, tuple(self.headers.items()))
            )
            time.sleep(atraso_primeiro_byte)

        def do_POST(self):
            self.registrar()
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.enviar(BODY)

        def do_GET(self):
            self.registrar()
            caminho = urlsplit(self.path).path
            if caminho.startswith("/done") or caminho.startswith("/marca/"):
                estado["marcas"].append(self.path)
                return self.enviar(b"ok", tipo="text/plain", pausa=False)
            if caminho == "/erro_driver":
                estado["erros"].append("driver")
                return self.enviar(b"erro", tipo="text/plain", pausa=False)
            if caminho == "/sonda/prerender":
                return self.enviar(
                    b"true" if "/marca/prerender" in estado["marcas"] else b"false",
                    tipo="application/json",
                    headers=[("Cache-Control", "no-store")],
                    pausa=False,
                )
            if caminho == "/indisponivel/prerender":
                estado["marcas"].append(caminho)
                return self.enviar(b"indisponivel", tipo="text/plain", pausa=False)
            if caminho == "/driver":
                return self.enviar(
                    driver(caso), headers=[("Cache-Control", "no-store")]
                )
            if caminho == "/prime_hsts":
                return self.enviar(
                    pagina(
                        "setTimeout(()=>location.href='http://hsts.0089.test/case/hsts',800)"
                    ),
                    headers=[("Strict-Transport-Security", "max-age=600")],
                )
            if caminho == "/case/hsts":
                return self.enviar(pagina("fetch('/done')"))
            if caminho == "/case/extensao":
                return self.enviar(estado["instrucoes_extensao"].encode())
            if caminho == "/sw.js":
                script = "self.addEventListener('install',e=>self.skipWaiting());self.addEventListener('activate',e=>e.waitUntil(clients.claim()));self.addEventListener('fetch',e=>{if(new URL(e.request.url).pathname=='/case/sw')e.respondWith(new Response('sintetizado pelo SW',{headers:{'Content-Type':'text/html'}}))});"
                return self.enviar(
                    script.encode(),
                    tipo="application/javascript",
                    headers=[("Service-Worker-Allowed", "/")],
                )
            if caminho == "/frame":
                return self.enviar(
                    pagina(
                        "let x=new XMLHttpRequest();x.open('GET','/case/iframe_xhr');x.send();"
                    )
                )
            if caminho == "/away":
                return self.enviar(pagina("setTimeout(()=>history.back(),1000)"))
            if caminho == "/ws":
                # Handshake WebSocket real; encerramento sem receber dados de cliente.
                chave = self.headers["Sec-WebSocket-Key"]
                import base64

                accept = base64.b64encode(
                    hashlib.sha1(
                        (chave + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode(),
                        usedforsecurity=False,
                    ).digest()
                ).decode()
                self.send_response(101)
                self.send_header("Upgrade", "websocket")
                self.send_header("Connection", "Upgrade")
                self.send_header("Sec-WebSocket-Accept", accept)
                self.end_headers()
                self.connection.sendall(b"\x88\x00")
                self.close_connection = True
                return
            if caminho == "/case/bfcache":
                return self.enviar(
                    pagina(
                        "addEventListener('pageshow',e=>{if(e.persisted)fetch('/marca/bfcache').then(()=>fetch('/done'));else setTimeout(()=>location.href='/away',800)})"
                    ),
                    headers=[("Cache-Control", "max-age=600")],
                )
            if caminho in {"/case/prerender", "/case/prefetch"}:
                return self.enviar(
                    pagina(
                        "if(document.prerendering){fetch('/marca/prerender');document.addEventListener('prerenderingchange',()=>fetch('/done'))}else{fetch('/done')}"
                    ),
                    headers=[("Cache-Control", "max-age=600")],
                )
            if caminho == "/case/reload":
                forcou = (
                    self.headers.get("Cache-Control") == "no-cache"
                    and self.headers.get("Pragma") == "no-cache"
                )
                corpo = (
                    pagina("fetch('/done')")
                    if forcou
                    else b"<html>Harness 0089: pressione Ctrl+Shift+R nesta janela (recarga forcada humana).</html>"
                )
                return self.enviar(corpo, headers=[("Cache-Control", "max-age=600")])
            if caminho == "/case/download":
                return self.enviar(
                    BODY,
                    headers=[
                        ("Content-Disposition", 'attachment; filename="sintetico.html"')
                    ],
                )
            if caminho == "/case/cache":
                return self.enviar(
                    BODY, headers=[("Cache-Control", "public, max-age=600")]
                )
            if caminho == "/case/corpo":
                return self.enviar(
                    ("<html>" + SEGREDOS["corpo"] + "</html>").encode(),
                    headers=[("Cache-Control", "private")],
                )
            if caminho == "/case/ctype":
                return self.enviar(BODY, tipo="text/html; token=" + SEGREDOS["ctype"])
            if caminho == "/case/" + PUBLICO_CAMINHO:
                return self.enviar(("<html>" + PUBLICO_CORPO + "</html>").encode())
            if caminho.endswith(("fetch_gzip", "xhr_gzip")):
                return self.enviar(
                    gzip.compress(BODY), headers=[("Content-Encoding", "gzip")]
                )
            if caso in {"br", "zstd"}:
                wire = (
                    Path(__file__).parent / "fixtures" / f"0089_wire_{caso}.bin"
                ).read_bytes()
                return self.enviar(wire, headers=[("Content-Encoding", caso)])
            if caso in FRAMING:
                self.close_connection = True
                self.connection.sendall(FRAMING[caso])
                return
            if caminho == "/favicon.ico":
                return self.enviar(b"", status=404, pausa=False)
            return self.enviar(BODY)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 443), Handler)
    server.daemon_threads = True
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield spki, estado
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


PREFIXO = b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
FRAMING = {
    "campo_malformado": PREFIXO
    + b"campo-sem-dois-pontos\r\nContent-Length: 1\r\n\r\nx",
    "cl_duplicado": PREFIXO + b"Content-Length: 1\r\nContent-Length: 1\r\n\r\nx",
    "cl_conflitante": PREFIXO + b"Content-Length: 1\r\nContent-Length: 2\r\n\r\nxx",
    "cl_te": PREFIXO
    + b"Content-Length: 1\r\nTransfer-Encoding: chunked\r\n\r\n1\r\nx\r\n0\r\n\r\n",
    "chunk_malformado": PREFIXO
    + b"Transfer-Encoding: chunked\r\n\r\nZZ\r\nx\r\n0\r\n\r\n",
    "chunk_truncado": PREFIXO + b"Transfer-Encoding: chunked\r\n\r\n10\r\nx",
    "cl_truncado": PREFIXO + b"Content-Length: 999\r\n\r\nx",
    "cl_acima_limite": PREFIXO + b"Content-Length: 10485761\r\n\r\nx",
    "vazio": PREFIXO + b"Content-Length: 0\r\n\r\n",
}


class SondaEventos:
    """Só no harness: prova os mecanismos observados, sem reter headers/segredos."""

    def __init__(self, ad):
        self.ad = ad
        self.eventos = []
        self.pedidos = {}
        self.comandos = []
        self.recusas = []
        self._streams = {}
        self._processar = ad.processar
        self._enviar = ad.canal.enviar
        ad.processar = self.processar
        ad.canal.enviar = self.enviar

    def enviar(self, obj):
        self.comandos.append((obj["method"], obj.get("params", {})))
        if obj["method"] == "Network.streamResourceContent":
            self._streams[obj["id"]] = (
                obj.get("sessionId"),
                obj["params"]["requestId"],
            )
        return self._enviar(obj)

    def processar(self, obj):
        alvo = self.ad.alvos.get(obj.get("sessionId"))
        subtipo_alvo = alvo.subtipo if alvo else None
        primeira_url = alvo.primeira_url if alvo else None
        metodo, p = obj.get("method", ""), obj.get("params", {})
        chave = (obj.get("sessionId"), p.get("requestId"))
        stream = obj.get("id") in self._streams
        if stream:
            chave = self._streams[obj["id"]]
        if metodo == "Network.requestWillBeSent":
            self.pedidos[chave] = p.get("request", {}).get("url", "")
        antes = len(getattr(self.ad, "motivos_recusas", ()))
        resultado = self._processar(obj)
        for url, motivo in getattr(self.ad, "motivos_recusas", ())[antes:]:
            self.recusas.append(
                {
                    "chave": chave,
                    "url": url,
                    "motivo": motivo,
                    "causa": metodo or "resposta_streaming",
                }
            )
        r = p.get("response", {})
        alvo = self.ad.alvos.get(obj.get("sessionId"))
        self.eventos.append(
            {
                "metodo": metodo,
                "chave": chave,
                "url": self.pedidos.get(chave, ""),
                "tipo": p.get("type"),
                "cache": r.get("fromDiskCache"),
                "memoria": r.get("fromMemoryCache"),
                "sw": r.get("fromServiceWorker"),
                "prefetch": r.get("fromPrefetchCache"),
                "iniciador": p.get("initiator", {}).get("type"),
                "frame": p.get("frame", {}).get("url", ""),
                "frame_id": p.get("frameId"),
                "raiz": alvo.raiz if alvo else None,
                "subtipo": p.get("targetInfo", {}).get("subtype", ""),
                "status": r.get("status", p.get("statusCode")),
                "protocolo": r.get("protocol"),
                "erro_rede": p.get("errorText"),
                "metodo_http": p.get("request", {}).get("method"),
                "subtipo_alvo": subtipo_alvo,
                "primeira_url": primeira_url,
                "stream_resposta": stream,
                "stream_erro": stream and "error" in obj,
                "data_presente": "data" in p,
                "data_length": p.get("dataLength"),
            }
        )
        return resultado


def bombear(ad, vigia, *, ate, prazo=40):
    """Prazo da fase do cenário; os até 60 s de preferências vêm antes dele."""
    limite = time.monotonic() + prazo
    satisfeito = None
    proxima_vigia = 0.0
    while time.monotonic() < limite:
        if ad is not None:
            ad.passo()
        else:
            if time.monotonic() >= proxima_vigia:
                vigia.assentar()
                proxima_vigia = time.monotonic() + 0.2
            time.sleep(0.02)
        if ate():
            satisfeito = satisfeito or time.monotonic()
            if time.monotonic() - satisfeito > 1:
                return
        else:
            satisfeito = None
    raise AssertionError("prazo próprio do cenário HTTPS excedido")


def capturas(ad):
    return [c.admitida for c in ad.pedidos.values() if c.admitida is not None]


def exigir_recusa(ad, url, motivos, *, sonda=None, chave=None):
    """Negativo não passa por zero capturas ou por falha alheia ao mecanismo."""
    if chave is not None:
        assert sonda is not None and sonda.pedidos[chave] == url
        observados = [r["motivo"] for r in sonda.recusas if r["chave"] == chave]
        curso = ad.pedidos.get(chave)
        diagnostico = json.dumps(
            {
                "chave": chave,
                "url": url,
                "motivos": observados,
                "eventos": [e for e in sonda.eventos if e["chave"] == chave],
            },
            ensure_ascii=False,
            indent=2,
        )
        assert observados and all(m in motivos for m in observados), diagnostico
        assert curso is None or (curso.recusada and curso.admitida is None), diagnostico
        return
    observados = [m for u, m in ad.motivos_recusas if u == url]
    assert observados, (url, ad.motivos_recusas)
    assert all(m in motivos for m in observados), (url, observados)
    assert not any(c.resposta.url == url for c in capturas(ad))


def conferir_recusa_evento(sonda, url, erros_rede):
    """EVENTO_ASSISTIDO_RECUSADO deve vir do evento impeditivo do mesmo pedido."""
    recusas = [
        r
        for r in sonda.recusas
        if r["url"] == url and r["motivo"] == "EVENTO_ASSISTIDO_RECUSADO"
    ]
    assert recusas
    for recusa in recusas:
        eventos = [e for e in sonda.eventos if e["chave"] == recusa["chave"]]
        prova = any(
            e["metodo"] == recusa["causa"]
            and (
                e["metodo"] == "Network.requestServedFromCache"
                or (
                    e["metodo"] == "Network.loadingFailed"
                    and e["erro_rede"] in erros_rede
                )
            )
            for e in eventos
        )
        if not prova:
            pytest.fail(
                json.dumps(
                    {"recusa": recusa, "eventos": eventos}, ensure_ascii=False, indent=2
                )
            )


def conferir_recusa_streaming(sonda, url, motivo):
    """Motivo alternativo exige a ordem/erro do comando do próprio pedido."""
    eventos = [e for e in sonda.eventos if e["url"] == url]
    respostas = [i for i, e in enumerate(eventos) if e["stream_resposta"]]
    if motivo == "COMANDO_STREAMING_RECUSADO":
        assert any(e["stream_erro"] for e in eventos), eventos
    elif motivo == "STREAMING_ASSISTIDO_TARDIO":
        fins = [
            i for i, e in enumerate(eventos) if e["metodo"] == "Network.loadingFinished"
        ]
        assert fins and (not respostas or fins[0] < respostas[0]), eventos
    else:
        raise AssertionError("motivo não é recusa de streaming demonstrável")


def _agrupar_pedidos(pedidos):
    grupos = defaultdict(list)
    for metodo, caminho, headers in pedidos:
        grupos[metodo, caminho].append(tuple(headers))
    return {k: sorted(v) for k, v in grupos.items()}


def _campos(headers):
    campos = defaultdict(list)
    for nome, valor in headers:
        campos[nome].append(valor)
    return {k: tuple(v) for k, v in campos.items()}


def diferenca_pedidos(esquerda, direita):
    """Diagnóstico completo, sem depender do diff truncado do pytest."""
    a, b = _agrupar_pedidos(esquerda), _agrupar_pedidos(direita)
    cont_a = Counter({k: len(v) for k, v in a.items()})
    cont_b = Counter({k: len(v) for k, v in b.items()})
    detalhes = []
    for metodo, caminho in sorted(a.keys() | b.keys()):
        chave = metodo, caminho
        for i, (ha, hb) in enumerate(zip(a.get(chave, ()), b.get(chave, ()))):
            ca, cb = _campos(ha), _campos(hb)
            if ha != hb:
                detalhes.append(
                    {
                        "metodo": metodo,
                        "caminho": caminho,
                        "ocorrencia": i,
                        "cabecalhos_so_esquerda": {
                            k: ca[k] for k in ca.keys() - cb.keys()
                        },
                        "cabecalhos_so_direita": {
                            k: cb[k] for k in cb.keys() - ca.keys()
                        },
                        "valores_diferentes": {
                            k: [ca[k], cb[k]]
                            for k in ca.keys() & cb.keys()
                            if ca[k] != cb[k]
                        },
                        "mesma_colecao_cabecalhos_ordem_diferente": sorted(ha)
                        == sorted(hb),
                        "cabecalhos_esquerda": ha,
                        "cabecalhos_direita": hb,
                    }
                )
    return {
        "numero_pedidos": [len(esquerda), len(direita)],
        "pedidos_so_esquerda": [[*k, n] for k, n in sorted((cont_a - cont_b).items())],
        "pedidos_so_direita": [[*k, n] for k, n in sorted((cont_b - cont_a).items())],
        "mesma_colecao_pedidos_ordem_diferente": a == b and esquerda != direita,
        "ordem_metodos_caminhos": [
            [(m, p) for m, p, _ in pedidos] for pedidos in (esquerda, direita)
        ],
        "diferencas": detalhes,
    }


def comparar_passividade(sem1, sem2, com):
    """Só desconta variação provada nos dois controles, por método/caminho.

    Nem favicon nem cabeçalho têm exclusão fixa. Valor novo exclusivo do
    adaptador continua falha, inclusive em campo variável nos controles.
    Ordem de chegada só é descontada se também variar nos controles.
    """
    grupos = [_agrupar_pedidos(p) for p in (sem1, sem2, com)]
    diagnostico = {
        "controle_sem_sem": diferenca_pedidos(sem1, sem2),
        "comparacao_sem1_com": diferenca_pedidos(sem1, com),
        "comparacao_sem2_com": diferenca_pedidos(sem2, com),
        "ruido_declarado": [],
        "passou": True,
    }
    contagens = [{k: len(v) for k, v in g.items()} for g in grupos]
    if not contagens[0] == contagens[1] == contagens[2]:
        diagnostico["passou"] = False
        return diagnostico
    ordens = [[(m, p) for m, p, _ in pedidos] for pedidos in (sem1, sem2, com)]
    diagnostico["ordem_chegada_variavel_no_controle"] = ordens[0] != ordens[1]
    if ordens[0] == ordens[1] and ordens[0] != ordens[2]:
        diagnostico["passou"] = False
    for chave in sorted(grupos[0]):
        colecoes = [[_campos(hs) for hs in g[chave]] for g in grupos]
        nomes = {nome for campos in colecoes for c in campos for nome in c}
        for nome in nomes:
            variantes = [Counter(c.get(nome) for c in campos) for campos in colecoes]
            # Repetições do mesmo método/caminho não podem combinar variantes
            # em uma multiplicidade que só exista com o adaptador.
            if variantes[2] not in variantes[:2]:
                diagnostico["passou"] = False
        for i, (h1, h2, hc) in enumerate(zip(*(g[chave] for g in grupos))):
            c1, c2, cc = map(_campos, (h1, h2, hc))
            ruido = {k for k in c1.keys() | c2.keys() if c1.get(k) != c2.get(k)}
            # A exclusão só vale neste pedido e para valores já demonstrados.
            novos = {k for k in ruido if cc.get(k) not in (c1.get(k), c2.get(k))}
            estaveis = [
                tuple((k, v) for k, v in hs if k not in ruido) for hs in (h1, h2, hc)
            ]
            ordem_variavel = estaveis[0] != estaveis[1]
            if ruido or ordem_variavel:
                diagnostico["ruido_declarado"].append(
                    {
                        "metodo": chave[0],
                        "caminho": chave[1],
                        "ocorrencia": i,
                        "cabecalhos_excluidos": {
                            k: [c1.get(k), c2.get(k)] for k in sorted(ruido)
                        },
                        "ordem_cabecalhos_variavel": ordem_variavel,
                        "justificativa": "variação observada entre duas execuções SEM adaptador; só valores dos controles são admitidos",
                    }
                )
            iguais = (
                sorted(estaveis[0]) == sorted(estaveis[1]) == sorted(estaveis[2])
                if ordem_variavel
                else estaveis[0] == estaveis[2]
            )
            if novos or not iguais:
                diagnostico["passou"] = False
    return diagnostico


def varrer_artefatos(raiz, segredos):
    """Todos os arquivos gravados pela ferramenta, incluindo SQLite, WAL e blobs.

    O perfil temporário do navegador é inventariado separadamente: cookies/cache
    nele são esperados durante a sessão e não são artefatos publicados do produto.
    """
    arquivos = []
    for path in raiz.rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            arquivos.append(path.relative_to(raiz).as_posix())
            for segredo in segredos:
                for codec in ("utf-8", "utf-16-le", "utf-16-be"):
                    assert segredo.encode(codec) not in data, path
    assert arquivos, "varredura vazia não prova ausência de segredos"
    return arquivos
