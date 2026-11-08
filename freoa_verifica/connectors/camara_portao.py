"""Portão da rota Câmara (decisão 0080; correções da 0081): admissão exata, robots por token, ritmo, tetos e barreiras.

Tudo o que a rota emite passa por `Portao.obter`, fora de `transport.py` (que não é alterado). Ordem, sob a
trava de arquivo do host: estado terminal da chamada → admissão da URL (antes do transporte) → ativação revalidada
→ bloqueios persistidos → política de robots (lida de novo se expirou; `/robots.txt` segue o MESMO fluxo) → decisão do
caminho → reserva atômica do teto → ritmo (marca monotônica persistida) → uma única emissão, sem repetição interna e
sem seguir redirecionamento → classificação do desfecho pela tabela do §6 e persistência.

Falha local (persistência, esquema persistido ou interpretação local) é terminal para a chamada pública ou para a
sessão do instrumento, nos dois hosts: nada mais é emitido naquele escopo (§6, linha "falha local").
"""
from __future__ import annotations

import threading
import weakref
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.camara_estado import (BLOQUEIO_TRANSITORIO, REVALIDACAO_INICIAL, REVALIDACAO_MAXIMA,
                                                     VALIDADE_ROBOTS, Estado, EstadoIndisponivel, Relogio, _de_iso,
                                                     iso)
from freoa_verifica.connectors import camara_robots as rb
from freoa_verifica.connectors.camara_policy import HOSTS, TERMO_URL, validar_termo, validar_url
from freoa_verifica.connectors.guarda import ativa as guarda_ativa
from freoa_verifica.identidade_http import USER_AGENT_IDENTIFICADO
from freoa_verifica.limites import restante
from freoa_verifica.texto_resposta import content_type_do_response, texto_da_resposta, texto_do_response
from freoa_verifica.transport import RespostaInvalida

INTERVALO_MINIMO = 10.0
TETO_SESSAO_INSTRUMENTO = 200
TETO_CHAMADA_PRODUTO = 30
_TERMO_PATH = urlsplit(TERMO_URL).path
PREFIXOS = {"www.camara.leg.br": ("/legislacao", "/robots.txt"),
            "www2.camara.leg.br": ("/legin/fed/", "/robots.txt")}
PREFIXOS_TERMO = {"www2.camara.leg.br": (_TERMO_PATH,)}
_LIMITE_BYTES = {"robots": 1024**2, "termo": 2 * 1024**2}
_ROTA_ROBOTS = {"recurso": "robots", "mime": "text/plain"}

# Classes da tabela do §6, da mais específica à residual (precedência do item 3).
A_HOST, TRES_XX, TRANSITORIA, ROBOTS, CORPO_MIME, RESIDUAL = (
    "host_persistente", "redirecionamento", "transitoria_1h", "robots_inconclusivo", "corpo_ou_mime", "residual")


def classificar(exc: Unavailable) -> str:
    """Classe da barreira de uma falha de transporte já mapeada pelo conector HTTP."""
    status = exc.evidencia.get("status")
    if exc.categoria == "ambiental_desafio" or exc.reason in {"http_401", "http_403", "http_429"}:
        return A_HOST
    if exc.reason == "transporte_BlockedHost" or (isinstance(status, int) and 300 <= status <= 399):
        return TRES_XX
    if exc.categoria == "fonte_fora" or exc.reason.startswith("http_5"):
        return TRANSITORIA
    if exc.reason == "corpo_vazio" or (exc.reason.startswith("transporte_") and exc.categoria == "resposta_inesperada"):
        return CORPO_MIME
    return RESIDUAL


def _copia(registro: dict, **extra) -> Unavailable:
    return Unavailable(registro["motivo"], registro.get("categoria"),
                       {**registro.get("evidencia", {}), "bloqueio": registro["classe"], **extra})


def _clonar(exc: Unavailable) -> Unavailable:
    return Unavailable(exc.reason, exc.categoria, exc.evidencia)


class Escopo:
    """Estado compartilhado de uma chamada pública (todas as instâncias participantes) ou da sessão do instrumento."""

    def __init__(self) -> None:
        self.trava = threading.Lock()
        self.usadas = 0  # requisições emitidas no escopo (teto por chamada)
        self.hosts: dict[str, Unavailable] = {}  # host bloqueado pelo restante do escopo
        self.terminal: Unavailable | None = None  # falha local: nada mais é emitido


_ESCOPOS: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
_ESCOPOS_TRAVA = threading.Lock()


class Portao:
    def __init__(self, transporte, *, estado: Estado | None = None, relogio: Relogio | None = None,
                 instrumento: bool = False, teto_sessao: int | None = None, teto_chamada: int | None = None,
                 ativacao=None, exigir_ativacao: bool = True):
        """`ativacao`: função sem argumentos que devolve o registro de ativação válido (ou None). Com
        `exigir_ativacao` (padrão) é revalidada antes de TODA obtenção viva; sem ela (replay e testes com transporte
        simulado) só informa o termo vigente. O hash do termo vigente vai em cada obtenção registrada."""
        self.transporte = transporte
        self.estado = estado if estado is not None else Estado(None)
        self.relogio = relogio or Relogio()
        self.instrumento = instrumento
        self.teto_sessao = teto_sessao if teto_sessao is not None else (TETO_SESSAO_INSTRUMENTO if instrumento else None)
        self.teto_chamada = teto_chamada if teto_chamada is not None else (None if instrumento else TETO_CHAMADA_PRODUTO)
        self.ativacao = ativacao
        self.exigir_ativacao = exigir_ativacao
        self.emitidas = 0  # requisições efetivamente emitidas por este portão
        self.politica_de: dict[str, str] = {}  # url -> sha256 do robots que autorizou a última obtenção
        self._orcamento = threading.Lock()
        self._sessao = Escopo()

    # --- admissão --------------------------------------------------------------------------------------------
    @staticmethod
    def admitir(url: str) -> dict:
        """Gramática da 0077 (+ `/robots.txt`) ou a URL exata do termo; o resto é recusado antes do transporte."""
        try:
            return validar_url(url)
        except ValueError as exc:
            primeira = exc
        try:
            return validar_termo(url)
        except ValueError:
            raise Unavailable(str(primeira)) from primeira

    # --- escopos ---------------------------------------------------------------------------------------------
    def _escopo(self) -> Escopo:
        if self.instrumento:
            return self._sessao
        guarda = guarda_ativa()
        if guarda is None:
            return Escopo()  # sem chamada pública não há escopo que sobreviva ao uso
        with _ESCOPOS_TRAVA:
            return _ESCOPOS.setdefault(guarda, Escopo())

    @staticmethod
    def _checar_terminal(escopo: Escopo) -> None:
        if escopo.terminal is not None:
            raise _clonar(escopo.terminal)

    def _local(self, motivo: str, exc: BaseException | None = None, **evidencia) -> Unavailable:
        """Falha local: encerra o escopo inteiro (os dois hosts) e devolve a indisponibilidade tipada."""
        if exc is not None:
            evidencia.setdefault("causa", type(exc).__name__)
        falha = Unavailable(motivo, None, evidencia)
        self._escopo().terminal = _clonar(falha)
        return falha

    def _exigir_ativacao(self) -> dict | None:
        if self.ativacao is None:
            return None
        try:
            registro = self.ativacao()
        except (OSError, KeyError, TypeError, ValueError):
            registro = None
        if registro is None and self.exigir_ativacao:
            raise Unavailable("ativacao_ao_vivo_pendente")
        return registro

    # --- API -------------------------------------------------------------------------------------------------
    def _executar(self, host: str, funcao):
        escopo = self._escopo()
        self._checar_terminal(escopo)
        try:
            with self.estado.trava_do_host(host):
                return funcao()
        except EstadoIndisponivel as exc:
            raise self._local("persistencia_local_falhou", exc) from exc
        except (KeyError, TypeError, ValueError) as exc:  # estrutura persistida ou interpretação local
            raise self._local("interpretacao_local_falhou", exc) from exc

    def obter(self, url: str):
        rota = self.admitir(url)
        host = urlsplit(url).netloc
        return self._executar(host, lambda: self._obter(url, rota, host))

    def verificar_caminhos(self, host: str, caminhos) -> dict:
        """Política vigente do host (lida de novo se expirou) e decisão de cada caminho pelo MESMO fluxo do
        `obter` (decisão persistida, bloqueio do host se proibido). Usada pelo fluxo de ativação."""
        if host not in HOSTS:
            raise Unavailable("host_nao_admitido")

        def passo():
            agora = self.relogio.agora()
            self._checar_bloqueios(host, f"https://{host}/robots.txt", agora)
            politica = self._politica(host, agora)
            for caminho in caminhos:
                self._decidir_caminho(host, politica, caminho, f"https://{host}{caminho}", agora)
            return politica
        return self._executar(host, passo)

    def garantir_politica(self, host: str) -> dict:
        """Política de robots vigente do host, lida de novo se expirou (sem decidir caminhos)."""
        return self.verificar_caminhos(host, ())

    def falha_de_resposta(self, exc: Unavailable, url: str) -> Unavailable:
        """Falha de perfil ou de resposta detectada DEPOIS do portão: alimenta o mesmo classificador e o mesmo
        estado de barreiras (recurso persistente; host pelo restante do escopo), sem bloquear por entrada inválida."""
        host = urlsplit(url).netloc
        if host not in HOSTS:
            return exc
        try:
            recurso = self.admitir(url)["recurso"]
        except Unavailable:
            return exc

        def passo():
            return self._registrar_falha(exc, url, host, recurso, classe=CORPO_MIME)
        try:
            return self._executar(host, passo)
        except Unavailable as falha:
            return falha

    def falha_local_de_interpretacao(self, exc: Unavailable) -> Unavailable:
        """Falha local do parser: terminal para o escopo, sem culpar o servidor."""
        self._escopo().terminal = _clonar(exc)
        return exc

    # --- núcleo ----------------------------------------------------------------------------------------------
    def _obter(self, url, rota, host):
        agora = self.relogio.agora()
        ativacao = self._exigir_ativacao()
        self._checar_bloqueios(host, url, agora)
        if rota["recurso"] == "robots":  # leitura direta de robots: mesmo fluxo de validação, persistência e backoff
            return self._ler_robots(host, agora)[1]
        politica = self._politica(host, agora)
        partes = urlsplit(url)
        caminho = partes.path + ("?" + partes.query if partes.query else "")
        self._decidir_caminho(host, politica, caminho, url, agora)
        resp = self._emitir(url, rota, host)
        self.politica_de[url] = politica["sha256"]
        self.estado.registrar_obtencao({"url": url, "sha256": resp.sha256, "politica_sha256": politica["sha256"],
                                        "politica_obtida_em": politica["obtido_em"], "em": iso(self.relogio.agora()),
                                        "termo_sha256": ativacao["termo_sha256"] if ativacao else None})
        return resp

    def _registro(self, classe, motivo, categoria, evidencia, agora, ate=None) -> dict:
        return {"classe": classe, "motivo": motivo, "categoria": categoria, "evidencia": evidencia,
                "desde": iso(agora), "ate": None if ate is None else iso(ate)}

    def _bloquear_host(self, host, registro) -> None:
        try:
            self.estado.bloquear_host(host, registro)
        except EstadoIndisponivel as exc:
            raise self._local("persistencia_local_falhou", exc, bloqueio_pretendido=registro["classe"]) from exc

    def _checar_bloqueios(self, host, url, agora) -> None:
        escopo = self._escopo().hosts.get(host)
        if escopo is not None:
            raise _clonar(escopo)
        bloqueio = self.estado.bloqueio_do_host(host, agora)
        if bloqueio is not None:
            if bloqueio["classe"] == "robots_inconclusivo":
                # Uma única tentativa de revalidação, só de /robots.txt, vencida a espera (§6, linha 4).
                revalidacao = self.estado.revalidacao(host)
                if revalidacao and agora >= _de_iso(revalidacao["proxima"]):
                    return  # sem política vigente, `_politica` lê o robots antes de qualquer conteúdo
            raise _copia(bloqueio)
        recurso = self.estado.bloqueio_do_recurso(host, url)
        if recurso is not None:
            raise _copia(recurso)

    # --- robots ----------------------------------------------------------------------------------------------
    def _grupos(self, politica) -> list:
        """Bytes originais, com o hash conferido em toda releitura, e interpretação textual única."""
        corpo = self.estado.corpo_da_politica(politica["host"], politica["sha256"])
        try:
            return rb.interpretar(texto_da_resposta(corpo, politica["content_type"]))
        except (RespostaInvalida, rb.RobotsInconclusivo) as exc:
            raise EstadoIndisponivel("politica_persistida_nao_interpretavel") from exc

    def _registrar_decisao(self, host, politica, caminho, estado) -> None:
        decisoes = politica.setdefault("decisoes", {})
        if decisoes.get(caminho) == estado:
            return
        decisoes[caminho] = estado  # sem teto: o recibo é renovado a cada 24 h e nenhuma decisão é descartada
        self.estado.regravar_politica(host, politica)

    def _decidir_caminho(self, host, politica, caminho, url, agora) -> None:
        decisao = rb.decidir(self._grupos(politica), caminho)
        self._registrar_decisao(host, politica, caminho, decisao.estado)
        if decisao.estado == rb.PROIBIDO:
            registro = self._registro(A_HOST, "robots_recusa", None,
                                      {"url": url, "robots_sha256": politica["sha256"],
                                       "robots_url": politica["url"]}, agora)
            self._bloquear_host(host, registro)
            raise _copia(registro)
        if decisao.estado == rb.INCONCLUSIVO:
            raise self._robots_inconclusivo(host, decisao.motivo or "robots_inconclusivo", politica["sha256"], agora)

    def _politica(self, host, agora) -> dict:
        vigente = self.estado.politica_valida(host, agora)
        if vigente is not None:
            return vigente
        return self._ler_robots(host, agora)[0]

    def _robots_inconclusivo(self, host, motivo, sha, agora, evidencia=None) -> Unavailable:
        ev = {"robots_sha256": sha, **(evidencia or {})}
        revalidacao = self.estado.revalidacao(host)
        intervalo = REVALIDACAO_INICIAL
        if revalidacao:
            intervalo = min(timedelta(seconds=revalidacao["intervalo_s"]) * 2, REVALIDACAO_MAXIMA)
        registro = self._registro(ROBOTS, motivo if motivo.startswith("robots") else "robots_inconclusivo",
                                  None, ev, agora)
        try:
            self.estado.bloquear_robots_inconclusivo(host, registro, agora + intervalo, intervalo)
        except EstadoIndisponivel as exc:  # a proteção persistente falhou: a falha local é declarada e encerra o escopo
            return self._local("persistencia_local_falhou", exc, bloqueio_pretendido=ROBOTS, motivo_original=motivo)
        return _copia(registro)

    def _ler_robots(self, host, agora) -> tuple[dict, object]:
        url = f"https://{host}/robots.txt"
        anterior = self.estado.politica(host)
        reaproveitada = self._em_cache(url)
        resp = self._emitir(url, _ROTA_ROBOTS, host,
                            atraso=float(anterior.get("crawl_delay", 0)) if anterior else 0.0)
        if reaproveitada:
            # Resposta reaproveitada da guarda NÃO é nova obtenção: vale pelo instante original, nunca renova.
            obtido = min(_de_iso(resp.fetched_at), self.relogio.agora())
            if obtido + VALIDADE_ROBOTS <= self.relogio.agora():
                raise Unavailable("robots_expirado_sem_nova_obtencao", None, {"obtido_em": iso(obtido)})
        try:
            texto = texto_do_response(resp)  # interpretação textual única; charset inválido é inconclusivo
            grupos = rb.interpretar(texto)
        except (RespostaInvalida, rb.RobotsInconclusivo) as exc:
            motivo = exc.args[0] if isinstance(exc, rb.RobotsInconclusivo) else "robots_inconclusivo"
            raise self._robots_inconclusivo(host, motivo, resp.sha256, agora) from exc
        geral = rb.decidir(grupos, "/")
        if geral.estado == rb.INCONCLUSIVO:
            raise self._robots_inconclusivo(host, geral.motivo or "robots_inconclusivo", resp.sha256, agora)
        instante = obtido if reaproveitada else self.relogio.agora()
        registro = {"host": host, "url": url, "sha256": resp.sha256, "obtido_em": iso(instante),
                    "valido_ate": iso(instante + VALIDADE_ROBOTS), "user_agent": USER_AGENT_IDENTIFICADO,
                    "tokens": list(rb.TOKENS), "grupos_considerados": [list(g) for g in geral.grupos_considerados],
                    "crawl_delay": geral.crawl_delay, "status": resp.status, "mime": resp.mime,
                    "content_type": content_type_do_response(resp) or resp.mime,
                    "bytes": len(resp.body), "decisoes": {}}
        self.estado.gravar_politica(host, registro, resp.body)
        self.estado.limpar_robots_inconclusivo(host)
        return registro, resp

    # --- emissão ---------------------------------------------------------------------------------------------
    def _em_cache(self, url) -> bool:
        guarda = guarda_ativa()
        if guarda is None:
            return False
        cabecalhos = {"\0user-agent-modo": "identified"}
        return guarda.em_cache("GET", url, None, cabecalhos)

    def _atraso_do_host(self, host, atraso_extra: float | None = None) -> float:
        if atraso_extra is not None:
            return max(INTERVALO_MINIMO, atraso_extra)
        registro = self.estado.politica(host)
        return max(INTERVALO_MINIMO, float(registro.get("crawl_delay", 0)) if registro else 0.0)

    def _esperar(self, host, intervalo) -> None:
        """Espera o resto do intervalo medido pela marca persistida: vale o MENOR entre o decorrido monotônico e o
        civil; recuo do relógio civil ou reinício da marca monotônica contam como nada decorrido (conservador)."""
        marca = self.estado.ultimo_inicio(host)
        if marca is None:
            return
        civil, mono = marca
        decorrido = max(0.0, min((self.relogio.agora() - civil).total_seconds(), self.relogio.monotonic() - mono))
        espera = intervalo - decorrido
        if espera <= 0:
            return
        if espera > rb.TETO_OPERACIONAL_DO_ATRASO:  # válido, honrado, mas fora do teto operacional: abstenção declarada
            raise Unavailable("crawl_delay_acima_do_teto_operacional", None,
                              {"intervalo_s": intervalo, "teto_s": rb.TETO_OPERACIONAL_DO_ATRASO})
        if espera > restante(3600):
            raise Unavailable("orcamento")
        self.relogio.sleep(espera)

    def _reservar(self, escopo: Escopo) -> bool:
        """Reserva atômica da vaga nos tetos (sessão e chamada, somando os hosts) ANTES de esperar e emitir."""
        chamada = guarda_ativa() is not None and self.teto_chamada is not None
        with self._orcamento:
            if self.teto_sessao is not None and self.emitidas >= self.teto_sessao:
                raise Unavailable("teto_de_sessao", evidencia={"limite": self.teto_sessao})
            with escopo.trava:
                if chamada and escopo.usadas >= self.teto_chamada:
                    raise Unavailable("teto_de_chamada", evidencia={"limite": self.teto_chamada})
                if chamada:
                    escopo.usadas += 1
            self.emitidas += 1
        return chamada

    def _devolver(self, escopo: Escopo, chamada: bool) -> None:
        with self._orcamento:
            self.emitidas -= 1
            if chamada:
                with escopo.trava:
                    escopo.usadas -= 1

    def _emitir(self, url, rota, host, atraso: float | None = None):
        recurso = rota["recurso"]
        escopo = self._escopo()
        if not self._em_cache(url):
            self._exigir_ativacao()
            chamada = self._reservar(escopo)
            try:
                self._esperar(host, self._atraso_do_host(host, atraso))
                self._checar_terminal(escopo)  # a espera pode ter durado: outra thread pode ter falhado localmente
                self._exigir_ativacao()
                self.estado.marcar_inicio(host, self.relogio.agora(), self.relogio.monotonic())
            except BaseException:
                self._devolver(escopo, chamada)
                raise
        try:
            resp = self.transporte(
                url, hosts=HOSTS, path_prefixes=PREFIXOS_TERMO if recurso == "termo" else PREFIXOS,
                mimes=frozenset({rota["mime"]}), user_agent="identified", max_redirects=0, repeticao=0,
                max_bytes=_LIMITE_BYTES.get(recurso, 30 * 1024**2), timeout=60)
        except Unavailable as exc:
            raise self._registrar_falha(exc, url, host, recurso) from exc
        invalida = self._resposta_invalida(resp, url, rota)
        if invalida is not None:
            raise self._registrar_falha(invalida, url, host, recurso) from None
        return resp

    @staticmethod
    def _resposta_invalida(resp, url, rota) -> Unavailable | None:
        ev = {"url": url, "status": resp.status}
        if resp.redirects or resp.final_url != url or 300 <= resp.status <= 399:
            return Unavailable("transporte_BlockedHost", None, ev)
        if resp.status != 200:
            if resp.status in (401, 403):
                return Unavailable(f"http_{resp.status}", "recusa_identificado", ev)
            if 500 <= resp.status <= 599:
                return Unavailable(f"http_{resp.status}", "fonte_fora", ev)
            return Unavailable(f"http_{resp.status}", None, ev)
        if not resp.body:
            return Unavailable("corpo_vazio", "resposta_inesperada", ev)
        if resp.mime != rota["mime"]:
            return Unavailable("transporte_RespostaInvalida", "resposta_inesperada", {**ev, "mime": resp.mime})
        return None

    def _registrar_falha(self, exc: Unavailable, url, host, recurso, classe: str | None = None) -> Unavailable:
        if exc.reason in {"teto_de_sessao", "teto_de_chamada", "orcamento", "persistencia_local_falhou",
                          "interpretacao_local_falhou", "ativacao_ao_vivo_pendente",
                          "crawl_delay_acima_do_teto_operacional"}:
            return exc
        classe = classe or classificar(exc)
        agora = self.relogio.agora()
        registro = self._registro(classe, exc.reason, exc.categoria, {**exc.evidencia, "url": url}, agora)
        escopo = self._escopo()
        try:
            if classe == A_HOST:
                self.estado.bloquear_host(host, registro)
            elif classe == TRANSITORIA:
                registro["ate"] = iso(agora + BLOQUEIO_TRANSITORIO)
                self.estado.bloquear_host(host, registro)
            elif recurso == "robots" and classe in {CORPO_MIME, RESIDUAL}:
                return self._robots_inconclusivo(host, "robots_inconclusivo", None, agora,
                                                 {"motivo_original": exc.reason, "status": exc.evidencia.get("status")})
            else:  # redirecionamento, corpo/MIME ou residual: recurso persistente, host pelo escopo
                self.estado.bloquear_recurso(host, url, registro)
                escopo.hosts[host] = _copia(registro)
        except EstadoIndisponivel as falha:
            # A proteção persistente não pôde ser gravada: a falha local é explícita e encerra o escopo inteiro.
            return self._local("persistencia_local_falhou", falha, bloqueio_pretendido=classe,
                               falha_original=exc.reason)
        return Unavailable(exc.reason, exc.categoria, {**exc.evidencia, "url": url, "bloqueio": classe})


__all__ = ["Portao", "classificar", "Escopo"]
