"""Guarda de execução: uma requisição efetiva é feita no máximo uma vez por execução (FIX9/F-08, F-11).

Ativa só dentro de `with guarda.ativar():` (a sincronização da semente). Em `connector_fetch`:

1. a identidade efetiva da requisição é método + URL normalizada + corpo; não depende do papel
   (obra principal, alteradora) nem do conector que a pede;
2. o primeiro desfecho (resposta capturada ou `Unavailable`) é reaproveitado por todo caminho que
   repete a identidade, sem novo pedido e sem novo incremento no breaker. A captura guardada só é entregue
   depois de revalidada contra a política da chamada atual (host, caminho, MIME, tamanho, redirecionamentos,
   desafio), sem rede; a política não entra na chave, e uma falha guardada só vale para a mesma política
   (FIX11/F-16). O desfecho guardado é o final do conector, depois de `reclassificar` (FIX11/F-11);
3. por fonte (host): depois de `Unavailable` com categoria `ambiental_desafio` ou
   `recusa_identificado`, nenhuma nova requisição àquele host na execução; as seguintes recebem a
   mesma categoria, sem rede, e ficam pendentes. O host bloqueado é o inicial e o de cada salto da
   cadeia que respondeu sem redirecionar (`evidencia.saltos`, `url_final`); o transporte consulta
   `antes_do_salto` antes de seguir cada redirecionamento e não visita host bloqueado (FIX10/F-11).

Requisições com `session` (estado de cookie) ou `sink` (arquivo) não entram no cache de desfechos, mas
observam e respeitam o bloqueio por host. Respostas bem-sucedidas ficam num LRU limitado em bytes
(`LIMITE_BYTES`); uma resposta expulsa pode ser pedida de novo. Falhas ficam todas.
"""

from __future__ import annotations

import contextlib
import contextvars
from collections import OrderedDict
from typing import Callable
from urllib.parse import urlsplit

from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.transport import _host_canonico, identidade_requisicao

BLOQUEIAM_A_FONTE = frozenset({"ambiental_desafio", "recusa_identificado"})
_REDIRECIONAMENTOS = frozenset({301, 302, 303, 307, 308})
LIMITE_BYTES =64 * 1024 * 1024
_ATIVA: contextvars.ContextVar["GuardaExecucao | None"] = contextvars.ContextVar("guarda_execucao", default=None)


def ativa() -> "GuardaExecucao | None":
    return _ATIVA.get()


def _copia(exc: Unavailable, **extra) -> Unavailable:
    return Unavailable(exc.reason, exc.categoria, {**exc.evidencia, **extra})


class GuardaExecucao:
    def __init__(self, limite_bytes: int = LIMITE_BYTES) -> None:
        self.limite_bytes = limite_bytes
        self._sucessos: OrderedDict[tuple, object] = OrderedDict()
        self._bytes = 0
        self._falhas: dict[tuple, tuple[Unavailable, object]] = {}  # chave -> (falha, política da chamada)
        self.bloqueios: dict[str, Unavailable] = {}  # host -> primeira falha que bloqueou a fonte
        self.requisicoes = 0  # chamadas que de fato chegaram à rede (para testes e diagnóstico)

    @contextlib.contextmanager
    def ativar(self):
        if _ATIVA.get() is self:
            yield self
            return
        token = _ATIVA.set(self)
        try:
            yield self
        finally:
            _ATIVA.reset(token)

    @staticmethod
    def _hosts_recusantes(inicial: str, exc: Unavailable) -> set[str]:
        """Host inicial e host de cada salto que respondeu sem ser redirecionamento (evidência `saltos`)."""
        ev = exc.evidencia
        urls = [s.get("url") for s in ev.get("saltos") or () if s.get("status") not in _REDIRECIONAMENTOS]
        urls.append(ev.get("url_final"))
        hosts = {_host_canonico(urlsplit(u)) for u in urls if u}
        hosts.add(inicial)
        hosts.discard("")
        return hosts

    def antes_do_salto(self, host: str) -> None:
        """Chamado pelo transporte antes de seguir um redirecionamento: host bloqueado não é visitado."""
        bloqueio = self.bloqueios.get(host)
        if bloqueio is not None:
            raise _copia(bloqueio, bloqueio_fonte=host)

    def _bloquear(self, host: str, exc: Unavailable) -> None:
        if exc.categoria in BLOQUEIAM_A_FONTE:
            for recusante in self._hosts_recusantes(host, exc):
                self.bloqueios.setdefault(recusante, exc)

    def executar(
        self, method: str, url: str, body: bytes | None, *, cacheavel: bool, baixar: Callable,
        revalidar: Callable | None = None, politica: object = None, entrada: Callable | None = None,
        cabecalhos: dict[str, str] | None = None,
    ):
        """`entrada()` valida a URL solicitada nesta chamada, antes de qualquer cache (FIX12/F-16).

        `revalidar(resp)` confere a captura guardada contra a política da chamada atual, sem rede (F-16).

        A chave é só a identidade efetiva; a política (`politica`) não entra nela. Uma falha guardada só vale
        para chamada de mesma política: outra política pode ter aceitado a resposta que a primeira recusou.
        """
        if entrada is not None:
            entrada()
        host = _host_canonico(urlsplit(url))
        bloqueio = self.bloqueios.get(host)
        if bloqueio is not None:
            raise _copia(bloqueio, url=url, bloqueio_fonte=host)
        chave = identidade_requisicao(method, url, body, cabecalhos)
        if cacheavel:
            falha = self._falhas.get(chave)
            if falha is not None and falha[1] == politica:
                raise _copia(falha[0])
            if chave in self._sucessos:
                guardada = self._sucessos[chave]
                if revalidar is not None:
                    try:
                        revalidar(guardada)
                    except Unavailable as exc:
                        self._bloquear(host, exc)
                        raise
                self._sucessos.move_to_end(chave)
                return guardada
        self.requisicoes += 1
        try:
            resp = baixar()
        except Unavailable as exc:
            if exc.reason == "orcamento":
                raise
            if cacheavel:
                self._falhas[chave] = (exc, politica)
            self._bloquear(host, exc)
            raise
        if cacheavel:
            tamanho = len(getattr(resp, "body", b"") or b"")
            if tamanho <= self.limite_bytes:
                self._sucessos[chave] = resp
                self._bytes += tamanho
                while self._bytes > self.limite_bytes and len(self._sucessos) > 1:
                    _, velho = self._sucessos.popitem(last=False)
                    self._bytes -= len(getattr(velho, "body", b"") or b"")
        return resp
