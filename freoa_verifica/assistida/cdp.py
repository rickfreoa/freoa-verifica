"""Observador CDP pelo pipe: lista fechada, sem navegação ou leitura de DOM."""

from __future__ import annotations

import json
import hashlib
import queue
import re
import threading
import time
from dataclasses import dataclass, field

from freoa_verifica import transport as t
from freoa_verifica.assistida.ambiente import RecusaSessao

METODOS = {
    "Target.setDiscoverTargets": {"discover": True},
    "Target.setAutoAttach": {
        "autoAttach": True,
        "waitForDebuggerOnStart": True,
        "flatten": True,
    },
    "Network.enable": {},
    "Page.enable": {},
    "Runtime.runIfWaitingForDebugger": {},
    "Page.getFrameTree": {},
    "Network.streamResourceContent": None,
    "Browser.getVersion": {},
    "Browser.setDownloadBehavior": {"behavior": "deny"},
    "Browser.close": {},
}
ALVO_NAVEGADOR = frozenset(
    {
        "Target.setDiscoverTargets",
        "Target.setAutoAttach",
        "Browser.getVersion",
        "Browser.setDownloadBehavior",
        "Browser.close",
    }
)
EVENTOS_REDE = frozenset(
    {
        "responseReceived",
        "responseReceivedExtraInfo",
        "requestWillBeSentExtraInfo",
        "requestServedFromCache",
        "dataReceived",
        "loadingFinished",
        "loadingFailed",
        "responseReceivedEarlyHints",
    }
)


class CanalPipe:
    """Fila de bytes limitada; reservas precedem leitura, cópia e interpretação JSON."""

    def __init__(self, leitura, escrita, sessao):
        self.leitura, self.escrita, self.sessao = leitura, escrita, sessao
        self.fila = queue.Queue(maxsize=10_000)
        self.bytes_fila = 0
        self.lock = threading.RLock()
        self.parado = False
        self.erro = None
        self.thread = threading.Thread(target=self._ler, daemon=True)

    def iniciar(self):
        self.thread.start()

    def _enfileirar(self, buffer):
        tamanho = len(buffer) + 128
        with self.lock:
            if self.bytes_fila + tamanho > 32 * 1024**2 or self.fila.full():
                self.sessao.encerrar()
                raise RecusaSessao("FILA_ASSISTIDA_EXCEDIDA")
            self.sessao.reservar(tamanho)
            try:
                mensagem = bytes(buffer)
                self.fila.put_nowait((mensagem, tamanho))
                self.bytes_fila += tamanho
            except BaseException:
                self.sessao.liberar(tamanho)
                raise

    def _ler(self):
        buffer = bytearray()
        retido = 0
        try:
            while not self.parado:
                reserva = 65536 + 128
                self.sessao.reservar(reserva)
                try:
                    bloco = self.leitura.read(65536)
                    if not bloco:
                        if buffer:
                            raise RecusaSessao("PIPE_ASSISTIDO_MENSAGEM_TRUNCADA")
                        self._enfileirar(b"")
                        return
                    inicio = 0
                    while inicio < len(bloco):
                        fim = bloco.find(b"\0", inicio)
                        limite = len(bloco) if fim < 0 else fim
                        # Fatia, realocação do bytearray e folga de capacidade, antes de alocar.
                        novo = 2 * (len(buffer) + limite - inicio) + 256
                        self.sessao.reservar(novo)
                        try:
                            buffer.extend(bloco[inicio:limite])
                        except BaseException:
                            self.sessao.liberar(novo)
                            raise
                        self.sessao.liberar(retido)
                        retido = novo
                        if fim >= 0:
                            if buffer:
                                self._enfileirar(buffer)
                            buffer = bytearray()
                            self.sessao.liberar(retido)
                            retido = 0
                        inicio = limite + 1
                finally:
                    self.sessao.liberar(reserva)
        except (OSError, ValueError, t.TransportError, RecusaSessao):
            if not self.parado:
                self.erro = "CANAL_ASSISTIDO_PERDIDO"
                self.sessao.encerrar()
        finally:
            self.sessao.liberar(retido)

    def receber(self, timeout=0.1):
        if self.erro:
            raise RecusaSessao(self.erro)
        try:
            raw, tamanho = self.fila.get(timeout=timeout)
        except queue.Empty:
            return None
        with self.lock:
            self.bytes_fila -= tamanho
        reserva = len(raw) * 64 + 4096
        self.sessao.reservar(reserva)
        try:
            if not raw:
                raise RecusaSessao("CANAL_ASSISTIDO_PERDIDO")
            obj = json.loads(raw)
            if not isinstance(obj, dict):
                raise ValueError
            return Mensagem(obj, self.sessao, reserva)
        except (ValueError, UnicodeError, RecursionError):
            self.sessao.encerrar()
            self.sessao.liberar(reserva)
            raise RecusaSessao("MENSAGEM_CDP_INVALIDA") from None
        except BaseException:
            self.sessao.liberar(reserva)
            raise
        finally:
            self.sessao.liberar(tamanho)

    def enviar(self, obj):
        # As mensagens de comando contêm só IDs observados e parâmetros fechados.
        reserva = (
            8192  # IDs limitados antes da construção; serialização não mede alocando
        )
        self.sessao.reservar(reserva)
        try:
            data = json.dumps(obj, separators=(",", ":")).encode("ascii") + b"\0"
            self.escrita.write(data)
            self.escrita.flush()
        finally:
            self.sessao.liberar(reserva)

    def fechar(self):
        self.parado = True
        self.leitura.close()
        self.escrita.close()
        self.thread.join(2)
        while True:
            try:
                _, n = self.fila.get_nowait()
                self.sessao.liberar(n)
            except queue.Empty:
                break


@dataclass
class Mensagem:
    dados: dict
    sessao: t.SessaoPortaAssistida
    reserva: int

    def __enter__(self):
        return self.dados

    def __exit__(self, *args):
        self.dados.clear()
        self.sessao.liberar(self.reserva)


@dataclass
class Alvo:
    id: str
    tipo: str
    subtipo: str | None
    pronto: bool = False
    raiz: str = ""
    documento: str = ""
    primeira_url: bool = False
    sequencia_concluida: bool = False


@dataclass
class EmCurso:
    chave: t.ChaveAssistida
    porta: object
    url: str
    vistos: set = field(default_factory=set)
    admitida: t.CapturaAssistida | None = None
    inicio: float = 0.0
    recusada: bool = False


class AdaptadorCDP:
    def __init__(self, perfil, sessao, canal, vigia, *, relogio=time.monotonic):
        self.perfil, self.sessao, self.canal, self.vigia = perfil, sessao, canal, vigia
        self.relogio = relogio
        self.pendentes, self.alvos, self.criados, self.pedidos = {}, {}, {}, {}
        self.numero = 0
        self.fase = 0
        self.normal = False
        self.fechado = False
        self.aceitou_page = False
        self.inicio = relogio()
        self.recusas = []
        self.retido = 0
        self.desanexados = {}
        self.historico = {}
        self.vigia.ao_invalidar = self.invalidar

    def invalidar(self):
        self.fechado = True
        self.sessao.encerrar()

    def _reter(self, n=1024):
        self.sessao.reservar(n)
        self.retido += n

    def comando(self, metodo, params=None, sid=None, retorno=None):
        if metodo not in METODOS:
            raise RecusaSessao("METODO_CDP_RECUSADO")
        params = {} if params is None else params
        esperado = METODOS[metodo]
        if (
            esperado is not None
            and params != esperado
            or esperado is None
            and (
                set(params) != {"requestId"} or not self.id_valido(params["requestId"])
            )
        ):
            raise RecusaSessao("PARAMETROS_CDP_RECUSADOS")
        if (metodo in ALVO_NAVEGADOR) != (sid is None):
            raise RecusaSessao("ALVO_CDP_RECUSADO")
        if sid is not None and sid not in self.alvos:
            raise RecusaSessao("ALVO_CDP_DESCONHECIDO")
        if (
            sid is not None
            and self.alvos[sid].tipo != "page"
            and metodo != "Runtime.runIfWaitingForDebugger"
        ):
            raise RecusaSessao("ALVO_CDP_RECUSADO")
        self._reter(4096)
        self.numero += 1
        self.pendentes[self.numero] = (metodo, sid, retorno)
        obj = {"id": self.numero, "method": metodo, "params": params}
        if sid is not None:
            obj["sessionId"] = sid
        self.canal.enviar(obj)

    def iniciar(self):
        def descoberta(_):
            self.fase = 1
            self.comando(
                "Target.setAutoAttach",
                METODOS["Target.setAutoAttach"],
                retorno=anexacao,
            )

        def anexacao(_):
            self.fase = 2
            self.comando("Browser.getVersion", retorno=versao)

        def versao(r):
            import re

            nome = r.get("product", "")
            if not re.fullmatch(r"[A-Za-z0-9 ./()-]{1,192}", nome):
                raise RecusaSessao("VERSAO_CDP_INDISPONIVEL")
            self.sessao.navegador = nome
            self.comando(
                "Browser.setDownloadBehavior",
                {"behavior": "deny"},
                retorno=lambda _: setattr(self, "fase", 3),
            )

        self.comando(
            "Target.setDiscoverTargets", {"discover": True}, retorno=descoberta
        )

    def atualizar_prontidao(self):
        base = self.vigia.assentar()
        if base is not None:
            for sid, alvo in self.alvos.items():
                if alvo.sequencia_concluida and sid not in self.desanexados:
                    alvo.pronto = True
        return base

    def _anexar(self, p):
        sid, info = p["sessionId"], p["targetInfo"]
        if sid in self.alvos:
            raise RecusaSessao("SESSAO_CDP_REPETIDA")
        self._reter(2048)
        # Ausência do histórico de criação nunca prova ausência de prerender.
        historico = self.criados.get(info["targetId"])
        subtipo = (
            historico if historico is not None and not info.get("subtype") else None
        )
        alvo = Alvo(
            info["targetId"],
            info["type"],
            subtipo,
            primeira_url=info.get("url", "") not in {"", "about:blank"}
            and not info.get("url", "").startswith("file:"),
        )
        self.alvos[sid] = alvo
        if alvo.tipo != "page":
            self.comando("Runtime.runIfWaitingForDebugger", sid=sid)
            return
        self.aceitou_page = True

        def rede(_):
            self.comando("Page.enable", sid=sid, retorno=pagina)

        def pagina(_):
            self.comando("Page.getFrameTree", sid=sid, retorno=arvore)

        def arvore(r):
            f = r["frameTree"]["frame"]
            if f.get("parentId") or not f.get("id"):
                raise RecusaSessao("ARVORE_CDP_SEM_RAIZ")
            alvo.raiz, alvo.documento = f["id"], f.get("url", "")
            self.comando(
                "Runtime.runIfWaitingForDebugger",
                sid=sid,
                retorno=retomada,
            )

        def retomada(_):
            alvo.sequencia_concluida = True
            self.atualizar_prontidao()

        self.comando("Network.enable", sid=sid, retorno=rede)

    @staticmethod
    def id_valido(valor):
        return (
            isinstance(valor, str)
            and re.fullmatch(r"[A-Za-z0-9_.-]{1,192}", valor) is not None
        )

    def processar(self, obj):
        try:
            return self._processar(obj)
        except (KeyError, TypeError, ValueError, AttributeError, RecursionError):
            self.invalidar()
            raise RecusaSessao("EVENTO_CDP_INVALIDO") from None

    def conferir_canal(self):
        if any(self.relogio() >= limite for limite in self.desanexados.values()):
            self.invalidar()
            raise RecusaSessao("CANAL_ALVO_PERDIDO")

    def fiscalizar_capturas(self):
        for curso in self.pedidos.values():
            if (
                not curso.recusada
                and curso.admitida is None
                and self.relogio() - curso.inicio >= 30
            ):
                codigo = (
                    "RespostaInvalida"
                    if curso.vistos & {"responseReceived", "responseReceivedExtraInfo"}
                    else "Timeout"
                )
                curso.porta.descartar()
                curso.recusada = True
                self.recusas.append((curso.url, codigo))

    def _processar(self, obj):
        if self.fechado:
            raise RecusaSessao("SESSAO_ASSISTIDA_ENCERRADA")
        self.vigia.conferir()
        self.conferir_canal()
        if self.relogio() - self.inicio >= 1200:
            self.invalidar()
            raise RecusaSessao("SESSAO_ASSISTIDA_EXPIRADA")
        if "id" in obj:
            comando = self.pendentes.pop(obj["id"], None)
            if comando is None:
                raise RecusaSessao("RESPOSTA_CDP_SEM_COMANDO")
            self.retido -= 4096
            self.sessao.liberar(4096)
            metodo, sid, callback = comando
            if "error" in obj:
                if metodo == "Network.streamResourceContent":
                    callback(None)
                    return
                raise RecusaSessao("COMANDO_CDP_FALHOU")
            if callback:
                callback(obj.get("result", {}))
            return
        metodo, p = obj.get("method", ""), obj.get("params", {})
        sid = obj.get("sessionId")
        for nome in ("requestId", "sessionId", "targetId", "frameId"):
            if nome in p and not self.id_valido(p[nome]):
                raise RecusaSessao("IDENTIFICADOR_CDP_INVALIDO")
        if sid is not None and not self.id_valido(sid):
            raise RecusaSessao("IDENTIFICADOR_CDP_INVALIDO")
        if "targetInfo" in p and not self.id_valido(p["targetInfo"]["targetId"]):
            raise RecusaSessao("IDENTIFICADOR_CDP_INVALIDO")
        if metodo == "Target.targetCreated":
            info = p["targetInfo"]
            self._reter()
            self.criados[info["targetId"]] = info.get("subtype", "")
        elif metodo == "Target.targetInfoChanged":
            info = p["targetInfo"]
            if info.get("subtype"):
                self.criados[info["targetId"]] = info["subtype"]
                for alvo in self.alvos.values():
                    if alvo.id == info["targetId"]:
                        alvo.subtipo = info["subtype"]
        elif metodo == "Target.attachedToTarget" and self.fase >= 1:
            self._anexar(p)
        elif metodo == "Target.targetDestroyed":
            mortos = [s for s, a in self.alvos.items() if a.id == p.get("targetId")]
            for s in mortos:
                del self.alvos[s]
                self.desanexados.pop(s, None)
            if (
                mortos
                and self.aceitou_page
                and not any(a.tipo == "page" for a in self.alvos.values())
            ):
                self.normal = True
        elif metodo == "Target.detachedFromTarget":
            # O fechamento pode desanexar antes de notificar a destruição. Não admite
            # mais pedidos nessa sessão; exige targetDestroyed em prazo curto.
            if p.get("sessionId") in self.alvos:
                self.alvos[p["sessionId"]].pronto = False
                self.desanexados[p["sessionId"]] = self.relogio() + 2
        elif sid in self.alvos:
            alvo = self.alvos[sid]
            if metodo == "Page.frameNavigated":
                f = p["frame"]
                if not f.get("parentId"):
                    alvo.raiz, alvo.documento = f["id"], f.get("url", "")
            elif metodo == "Page.frameAttached" and p.get("frameId") == alvo.raiz:
                alvo.raiz = ""
            elif metodo == "Network.requestWillBeSent":
                self._pedido(sid, alvo, p)
            elif metodo.startswith("Network.") and metodo[8:] in EVENTOS_REDE:
                self._evento(sid, p.get("requestId"), metodo[8:], p)

    def _pedido(self, sid, alvo, p):
        observado = self.relogio()
        rid = p.get("requestId")
        chave = (sid, rid)
        anterior = self.pedidos.get(chave)
        if anterior:
            anterior.porta.descartar()
            # Nenhum histórico de salto retido incompleto é reutilizado.
            raise RecusaSessao("CADEIA_CDP_AMBIGUA")
        req = p.get("request", {})
        url, tipo = req.get("url", ""), p.get("type")
        anterior_http = self.historico.get(chave)
        self._reter(1024)
        http_elegivel = (
            req.get("method") == "GET"
            and url.startswith("http://")
            and self.perfil.recurso("https://" + url[7:], tipo) is not None
        )
        if chave in self.historico:
            # Só o HSTS imediato de um primeiro HTTP observado pode carregar história.
            if (
                not anterior_http
                or "redirectResponse" not in p
                or hashlib.sha256(
                    p["redirectResponse"].get("url", "").encode("utf-8")
                ).digest()
                != anterior_http
            ):
                return
            self.historico[chave] = None
        else:
            self.historico[chave] = (
                hashlib.sha256(url.encode("utf-8")).digest() if http_elegivel else None
            )
            if "redirectResponse" in p:
                return  # salto anterior não observado: histórico incompleto
        if not self.perfil.recurso(url, tipo):
            return
        # Não se retêm headers nem dados da solicitação.
        self._reter(2048 + len(url) * 4)
        if alvo.primeira_url and tipo == "Document":
            alvo.primeira_url = False
            return
        base = self.atualizar_prontidao()
        if self.fase != 3 or not alvo.pronto or base is None or observado <= base:
            return
        iniciador = p.get("initiator", {})
        tipo_iniciador = iniciador.get("type", "")
        inicio = {"tipo": tipo_iniciador}
        if tipo != "Document":
            # CDP prova o quadro do pedido e o documento corrente; não usa URL da stack como substituto.
            if p.get("frameId") != alvo.raiz or p.get("documentURL") != alvo.documento:
                return
            inicio.update(
                frame_id=p["frameId"], documento=p["documentURL"], alvo=alvo.id
            )
        saltos = (p["redirectResponse"],) if "redirectResponse" in p else ()
        pedido = t.PedidoAssistido(
            t.ChaveAssistida(sid, alvo.id, rid, len(saltos)),
            url,
            req.get("method", ""),
            tipo,
            p.get("timestamp"),
            p.get("wallTime"),
            self.relogio(),
            p.get("frameId", ""),
            alvo.raiz,
            alvo.documento,
            inicio,
            True,
            True,
            True,
            alvo.tipo,
            alvo.subtipo,
            saltos,
        )
        try:
            porta = t.capturar_assistida(self.sessao, pedido)
        except t.TransportError as exc:
            self.recusas.append((self.perfil.sanitizar(url), type(exc).__name__))
            return
        curso = EmCurso(
            pedido.chave, porta, self.perfil.sanitizar(url), inicio=self.relogio()
        )
        self.pedidos[chave] = curso

        def streaming(resultado):
            if resultado is None:
                porta.descartar()
                curso.recusada = True
                self.recusas.append((curso.url, "RespostaInvalida"))
                return
            self._observar(curso, "streamResourceContent", resultado)

        self.comando(
            "Network.streamResourceContent",
            {"requestId": rid},
            sid=sid,
            retorno=streaming,
        )

    def _evento(self, sid, rid, metodo, dados):
        curso = self.pedidos.get((sid, rid))
        if curso is None:
            return
        if metodo == "requestWillBeSentExtraInfo":
            headers = dados.get("headers", {})
            dados = {
                "authorization_presente": any(
                    k.lower() == "authorization" for k in headers
                ),
                "associatedCookies": [
                    {
                        "nome": c.get("cookie", {}).get("name"),
                        "blockedReasons": c.get("blockedReasons"),
                    }
                    for c in dados.get("associatedCookies", [])
                ],
            }
        elif metodo == "responseReceivedExtraInfo":
            headers = dados.get("headers", {})
            bruto = dados.get("headersText", "")
            tamanho = len(bruto) + sum(len(k) + len(v) for k, v in headers.items())
            # A porta mantém esses campos até o confronto; a reserva da mensagem
            # JSON termina antes disso. Não projeta blockedCookies nem seus valores.
            self._reter(tamanho * 16 + 4096)
            dados = {
                k: dados[k]
                for k in ("statusCode", "headers", "headersText")
                if k in dados
            }
        self._observar(curso, metodo, dados)

    def _observar(self, curso, metodo, dados):
        if curso.recusada:
            return
        try:
            curso.porta.observar(t.EventoAssistido(curso.chave, metodo, dados))
            curso.vistos.add(metodo)
            if {
                "streamResourceContent",
                "requestWillBeSentExtraInfo",
                "responseReceived",
                "responseReceivedExtraInfo",
                "loadingFinished",
            } <= curso.vistos and curso.admitida is None:
                curso.admitida = curso.porta.admitir()
        except t.TransportError as exc:
            curso.porta.descartar()
            curso.admitida = None
            curso.recusada = True
            self.recusas.append((curso.url, type(exc).__name__))

    def executar(self):
        self.canal.iniciar()
        self.iniciar()
        while not self.normal:
            self.vigia.conferir()
            self.conferir_canal()
            self.fiscalizar_capturas()
            if self.relogio() - self.inicio >= 1200:
                raise RecusaSessao("SESSAO_ASSISTIDA_EXPIRADA")
            if self.fase < 3 and self.relogio() - self.inicio > 10:
                raise RecusaSessao("PIPE_ASSISTIDO_INDISPONIVEL")
            self.atualizar_prontidao()
            mensagem = self.canal.receber()
            if mensagem is not None:
                with mensagem as obj:
                    self.processar(obj)
        for curso in self.pedidos.values():
            if curso.admitida is None and not curso.recusada:
                curso.porta.descartar()
                curso.recusada = True
                self.recusas.append((curso.url, "RespostaInvalida"))
        return [c.admitida for c in self.pedidos.values() if c.admitida is not None]

    def descartar(self):
        self.sessao.encerrar()
        self.sessao.liberar(self.retido)
        self.retido = 0
