"""Portão da rota Câmara (decisão 0080): admissão exata, robots por token, ritmo, tetos e barreiras.

Tudo o que a rota emite passa por `Portao.obter`, fora de `transport.py` (que não é alterado). Ordem, sob a
trava de arquivo do host: admissão da URL (antes do transporte) → bloqueios persistidos → política de robots
(lida de novo se expirou) → decisão do caminho → teto → ritmo → uma única emissão, sem repetição interna e sem
seguir redirecionamento → classificação do desfecho pela tabela do §6 e persistência.
"""
from __future__ import annotations

import weakref
from datetime import timedelta
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

INTERVALO_MINIMO = 10.0
TETO_SESSAO_INSTRUMENTO = 200
TETO_CHAMADA_PRODUTO = 30
_TERMO_PATH = urlsplit(TERMO_URL).path
PREFIXOS = {"www.camara.leg.br": ("/legislacao", "/robots.txt"),
            "www2.camara.leg.br": ("/legin/fed/", "/robots.txt")}
PREFIXOS_TERMO = {"www2.camara.leg.br": (_TERMO_PATH,)}
_LIMITE_BYTES = {"robots": 1024**2, "termo": 2 * 1024**2}

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


class Portao:
    def __init__(self, transporte, *, estado: Estado | None = None, relogio: Relogio | None = None,
                 instrumento: bool = False, teto_sessao: int | None = None, teto_chamada: int | None = None):
        self.transporte = transporte
        self.estado = estado if estado is not None else Estado(None)
        self.relogio = relogio or Relogio()
        self.instrumento = instrumento
        self.teto_sessao = teto_sessao if teto_sessao is not None else (TETO_SESSAO_INSTRUMENTO if instrumento else None)
        self.teto_chamada = teto_chamada if teto_chamada is not None else (None if instrumento else TETO_CHAMADA_PRODUTO)
        self.emitidas = 0  # requisições efetivamente emitidas por este portão
        self.politica_de: dict[str, str] = {}  # url -> sha256 do robots que autorizou a última obtenção
        self._ultimo_inicio: dict[str, float] = {}
        self._por_chamada: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
        self._hosts_do_escopo: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
        self._hosts_da_sessao: dict[str, Unavailable] = {}

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
    def _bloqueios_do_escopo(self) -> dict[str, Unavailable]:
        if self.instrumento:
            return self._hosts_da_sessao
        guarda = guarda_ativa()
        if guarda is None:
            return {}
        return self._hosts_do_escopo.setdefault(guarda, {})

    def _contar_chamada(self) -> None:
        guarda = guarda_ativa()
        if guarda is None or self.teto_chamada is None:
            return
        usadas = self._por_chamada.get(guarda, 0)
        if usadas >= self.teto_chamada:
            raise Unavailable("teto_de_chamada", evidencia={"limite": self.teto_chamada})
        self._por_chamada[guarda] = usadas + 1

    # --- API -------------------------------------------------------------------------------------------------
    def obter(self, url: str):
        rota = self.admitir(url)
        host = urlsplit(url).netloc
        try:
            with self.estado.trava_do_host(host):
                return self._obter(url, rota, host)
        except EstadoIndisponivel as exc:
            raise Unavailable("persistencia_local_falhou") from exc

    def garantir_politica(self, host: str) -> dict:
        """Política de robots vigente do host, lida de novo se expirou (usada pelo fluxo de ativação)."""
        if host not in HOSTS:
            raise Unavailable("host_nao_admitido")
        try:
            with self.estado.trava_do_host(host):
                agora = self.relogio.agora()
                self._checar_bloqueios(host, f"https://{host}/robots.txt", agora)
                return self._politica(host, agora)
        except EstadoIndisponivel as exc:
            raise Unavailable("persistencia_local_falhou") from exc

    # --- núcleo ----------------------------------------------------------------------------------------------
    def _obter(self, url, rota, host):
        agora = self.relogio.agora()
        eh_robots = rota["recurso"] == "robots"
        self._checar_bloqueios(host, url, agora)
        politica = None
        if not eh_robots:
            politica = self._politica(host, agora)
            partes = urlsplit(url)
            caminho = partes.path + ("?" + partes.query if partes.query else "")
            decisao = rb.decidir(self._grupos(politica), caminho)
            self._registrar_decisao(host, politica, caminho, decisao.estado)
            if decisao.estado == rb.PROIBIDO:
                registro = self._registro("host_persistente", "robots_recusa", None,
                                          {"url": url, "robots_sha256": politica["sha256"],
                                           "robots_url": politica["url"]}, agora)
                self._bloquear_host(host, registro)
                raise _copia(registro)
            if decisao.estado == rb.INCONCLUSIVO:
                raise self._robots_inconclusivo(host, decisao.motivo or "robots_inconclusivo", politica["sha256"], agora)
        resp = self._emitir(url, rota, host, politica)
        if politica is not None:
            self.politica_de[url] = politica["sha256"]
            self.estado.registrar_obtencao({"url": url, "sha256": resp.sha256, "politica_sha256": politica["sha256"],
                                            "politica_obtida_em": politica["obtido_em"], "em": iso(self.relogio.agora())})
        return resp

    def _registro(self, classe, motivo, categoria, evidencia, agora, ate=None) -> dict:
        return {"classe": classe, "motivo": motivo, "categoria": categoria, "evidencia": evidencia,
                "desde": iso(agora), "ate": None if ate is None else iso(ate)}

    def _bloquear_host(self, host, registro) -> None:
        try:
            self.estado.bloquear_host(host, registro)
        except EstadoIndisponivel:
            self._bloqueios_do_escopo()[host] = _copia(registro)  # falha local: vale só para esta chamada/sessão
            raise

    def _checar_bloqueios(self, host, url, agora) -> None:
        escopo = self._bloqueios_do_escopo().get(host)
        if escopo is not None:
            raise escopo
        bloqueio = self.estado.bloqueio_do_host(host, agora)
        if bloqueio is not None:
            if bloqueio["classe"] == "robots_inconclusivo":
                # Uma única tentativa de revalidação, só de /robots.txt, vencida a espera (§6, linha 4).
                revalidacao = self.estado.revalidacao(host)
                if revalidacao and agora >= _de_iso(revalidacao["proxima"]):
                    return  # só /robots.txt é emitido: sem política vigente, `_politica` lê o robots e nada mais
            raise _copia(bloqueio)
        recurso = self.estado.bloqueio_do_recurso(host, url)
        if recurso is not None:
            raise _copia(recurso)

    def _grupos(self, politica) -> list:
        return rb.interpretar(self._corpo(politica))

    def _corpo(self, politica) -> str:
        if self.estado.home is None:
            return self.estado._memoria[f"corpo-{politica['sha256']}"]
        try:
            return (self.estado.pasta / f"robots-{politica['host']}-{politica['sha256']}.txt").read_text("utf-8")
        except OSError as exc:
            raise EstadoIndisponivel("corpo do robots ausente") from exc

    def _registrar_decisao(self, host, politica, caminho, estado) -> None:
        decisoes = politica.setdefault("decisoes", {})
        if decisoes.get(caminho) == estado or len(decisoes) >= 500:
            return
        decisoes[caminho] = estado
        self.estado._gravar(f"robots-{host}.json", politica)

    def _politica(self, host, agora) -> dict:
        vigente = self.estado.politica_valida(host, agora)
        if vigente is not None:
            return vigente
        return self._ler_robots(host, agora)

    def _robots_inconclusivo(self, host, motivo, sha, agora, evidencia=None) -> Unavailable:
        ev = {"robots_sha256": sha, **(evidencia or {})}
        revalidacao = self.estado.revalidacao(host)
        intervalo = REVALIDACAO_INICIAL
        if revalidacao:
            intervalo = min(timedelta(seconds=revalidacao["intervalo_s"]) * 2, REVALIDACAO_MAXIMA)
        registro = self._registro(ROBOTS, motivo if motivo.startswith("robots") else "robots_inconclusivo",
                                  None, ev, agora)
        try:
            self.estado.bloquear_host(host, registro)
            self.estado.agendar_revalidacao(host, agora + intervalo, intervalo)
        except EstadoIndisponivel:
            self._bloqueios_do_escopo()[host] = _copia(registro)
        return _copia(registro)

    def _ler_robots(self, host, agora) -> dict:
        url = f"https://{host}/robots.txt"
        anterior = self.estado.politica(host)
        resp = self._emitir(url, {"recurso": "robots", "mime": "text/plain"}, host, None,
                            atraso=float(anterior.get("crawl_delay", 0)) if anterior else 0.0)
        corpo = resp.body
        try:
            grupos = rb.interpretar(corpo.decode("utf-8"))
        except (UnicodeDecodeError, rb.RobotsInconclusivo) as exc:
            raise self._robots_inconclusivo(host, getattr(exc, "args", ["robots_inconclusivo"])[0] if isinstance(
                exc, rb.RobotsInconclusivo) else "robots_inconclusivo", resp.sha256, agora) from exc
        geral = rb.decidir(grupos, "/")
        if geral.estado == rb.INCONCLUSIVO:
            raise self._robots_inconclusivo(host, geral.motivo or "robots_inconclusivo", resp.sha256, agora)
        instante = self.relogio.agora()
        registro = {"host": host, "url": url, "sha256": resp.sha256, "obtido_em": iso(instante),
                    "valido_ate": iso(instante + VALIDADE_ROBOTS), "user_agent": USER_AGENT_IDENTIFICADO,
                    "tokens": list(rb.TOKENS), "grupos_considerados": [list(g) for g in geral.grupos_considerados],
                    "crawl_delay": geral.crawl_delay, "status": resp.status, "mime": resp.mime,
                    "bytes": len(corpo), "decisoes": {}}
        self.estado.gravar_politica(host, registro, corpo)
        self.estado.limpar_robots_inconclusivo(host)
        return registro

    # --- emissão ---------------------------------------------------------------------------------------------
    def _em_cache(self, url, rota) -> bool:
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
        espera = 0.0
        ultimo = self.estado.ultimo_inicio(host)
        if ultimo is not None:
            decorrido = max(0.0, (self.relogio.agora() - ultimo).total_seconds())
            espera = max(espera, intervalo - decorrido)
        if host in self._ultimo_inicio:
            espera = max(espera, intervalo - (self.relogio.monotonic() - self._ultimo_inicio[host]))
        if espera > 0:
            if espera > restante(3600):
                raise Unavailable("orcamento")
            self.relogio.sleep(espera)

    def _emitir(self, url, rota, host, politica, atraso: float | None = None):
        recurso = rota["recurso"]
        em_cache = self._em_cache(url, rota)
        if not em_cache:
            if self.teto_sessao is not None and self.emitidas >= self.teto_sessao:
                raise Unavailable("teto_de_sessao", evidencia={"limite": self.teto_sessao})
            self._contar_chamada()
            self._esperar(host, self._atraso_do_host(host, atraso))
            self._ultimo_inicio[host] = self.relogio.monotonic()
            self.estado.marcar_inicio(host, self.relogio.agora())
            self.emitidas += 1
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

    def _registrar_falha(self, exc: Unavailable, url, host, recurso) -> Unavailable:
        if exc.reason in {"teto_de_sessao", "teto_de_chamada", "orcamento", "persistencia_local_falhou"}:
            return exc
        classe = classificar(exc)
        agora = self.relogio.agora()
        registro = self._registro(classe, exc.reason, exc.categoria, {**exc.evidencia, "url": url}, agora)
        escopo = self._bloqueios_do_escopo()
        try:
            if classe == A_HOST:
                self._bloquear_host(host, registro)
            elif classe == TRANSITORIA:
                registro["ate"] = iso(agora + BLOQUEIO_TRANSITORIO)
                self._bloquear_host(host, registro)
            elif recurso == "robots" and classe in {CORPO_MIME, RESIDUAL}:
                return self._robots_inconclusivo(host, "robots_inconclusivo", None, agora,
                                                 {"motivo_original": exc.reason, "status": exc.evidencia.get("status")})
            else:  # redirecionamento, corpo/MIME ou residual: recurso persistente, host pelo escopo
                self.estado.bloquear_recurso(host, url, registro)
                escopo[host] = _copia(registro)
        except EstadoIndisponivel:
            escopo[host] = _copia(registro)
        return Unavailable(exc.reason, exc.categoria, {**exc.evidencia, "url": url, "bloqueio": classe})


__all__ = ["Portao", "classificar"]
