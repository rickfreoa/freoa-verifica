"""Utilitários dos testes da rota Câmara (0080): relógio controlado e transporte simulado.

Sintético por construção: nenhum socket, nenhuma requisição real.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from freoa_verifica.connectors.camara_estado import Relogio


class RelogioFalso(Relogio):
    """Tempo só avança por `sleep`/`avancar`; `monotonic` e `agora` andam juntos."""

    def __init__(self, inicio: datetime | None = None):
        self.t = 0.0
        self.inicio = inicio or datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
        self.dormidas: list[float] = []

    def monotonic(self) -> float:
        return self.t

    def agora(self) -> datetime:
        return self.inicio + timedelta(seconds=self.t)

    def sleep(self, segundos: float) -> None:
        self.dormidas.append(segundos)
        self.t += segundos

    def avancar(self, segundos: float) -> None:
        self.t += segundos


import hashlib
import json
from pathlib import Path

from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.camara_estado import Estado
from freoa_verifica.connectors.camara_policy import TERMO_URL
from freoa_verifica.transport import Response

FIX = Path(__file__).parent / "fixtures" / "camara_legin"
ROBOTS_WWW = "https://www.camara.leg.br/robots.txt"
ROBOTS_WWW2 = "https://www2.camara.leg.br/robots.txt"
BUSCA = ("https://www.camara.leg.br/legislacao/busca?abrangencia=Legisla%C3%A7%C3%A3o+Federal&tipo=Lei+Ordin%C3%A1ria"
         "&numero=6404&ano=1976&geral=")
LEI = "https://www2.camara.leg.br/legin/fed/lei/1970-1979/lei-6404-15-dezembro-1976-368447-norma-pl.html"
TERMO_HTML = "<html><body><h1>Termos gerais</h1><p>Atualizado em 05/11/2026</p></body></html>".encode()


def resposta(url, corpo: bytes = b"x", *, status=200, mime="text/html"):
    return Response(url, url, status, {}, corpo, hashlib.sha256(corpo).hexdigest(), "2026-11-08T12:00:00+00:00", [],
                    mime, size=len(corpo), content_type=f"{mime}; charset=utf-8")


def robots_resp(host_url, texto):
    return resposta(host_url, texto.encode(), mime="text/plain")


def da_fixture(chave, *, fetched_at=None):
    """Captura real intacta (bytes e hash) servida por dublê. `fetched_at` simula o carimbo do transporte vivo, que é o
    instante do recebimento: sem ele vale o da captura histórica (que precede qualquer política obtida hoje)."""
    meta = json.loads((FIX / f"camara_{chave}.captura.json").read_bytes())
    corpo = (FIX / f"camara_{chave}{Path(meta['arquivo']).suffix}").read_bytes()
    return Response(meta["url"], meta["url_final"], meta["status"], meta["cabecalhos"], corpo, meta["sha256"],
                    fetched_at or meta["capturado_em"], [], meta["content_type"], size=len(corpo),
                    content_type=meta["cabecalhos"]["content-type"])


LIVRE = "User-agent: *\nDisallow: /wp-admin*\n"


class Transporte:
    """Transporte simulado com a assinatura de `connector_fetch`: registra cada requisição emitida e o instante."""

    def __init__(self, relogio, rotas=None):
        self.relogio = relogio
        self.rotas = {ROBOTS_WWW: robots_resp(ROBOTS_WWW, LIVRE), ROBOTS_WWW2: robots_resp(ROBOTS_WWW2, LIVRE),
                      TERMO_URL: resposta(TERMO_URL, TERMO_HTML), **(rotas or {})}
        self.chamadas: list[tuple[str, dict, float]] = []

    def __call__(self, url, **kw):
        assert kw["max_redirects"] == 0 and kw["repeticao"] == 0, "repetição e redirecionamento devem estar desligados"
        self.chamadas.append((url, kw, self.relogio.monotonic()))
        destino = self.rotas.get(url)
        if destino is None:
            raise AssertionError(f"URL não prevista: {url}")
        if callable(destino):
            destino = destino()
        if isinstance(destino, Exception):
            raise destino
        return destino

    @property
    def urls(self):
        return [c[0] for c in self.chamadas]


def barreira(reason, categoria=None, status=None):
    return Unavailable(reason, categoria, {"status": status} if status else {})


def portao(tmp_path=None, rotas=None, *, relogio=None, home="auto", **kw):
    from freoa_verifica.connectors.camara_portao import Portao
    relogio = relogio or RelogioFalso()
    transporte = Transporte(relogio, rotas)
    estado = Estado(tmp_path if home == "auto" else home)
    return Portao(transporte, estado=estado, relogio=relogio, **kw), transporte, relogio, estado


def selo_do_termo(home, digest):
    """Hash do (único) recibo preservado do termo `digest` no home (identidade da OBTENÇÃO do termo)."""
    nomes = sorted((Path(home) / "camara" / "termo").glob(f"{digest}.*.recibo.json"))
    assert len(nomes) == 1, nomes
    return nomes[0].name.split(".")[1]


FETCHED_PADRAO = "2026-11-08T12:00:00+00:00"  # `fetched_at` das respostas sintéticas de `resposta()`


def obter_vinculado(home, rotas, relogio, url):
    """Obtenção REAL pelo portão de um home já ativado (instrumento): grava o vínculo captura → política → termo como
    o produto grava. Devolve `(resposta, transporte)`."""
    from freoa_verifica.connectors import camara_ativacao as ativ
    from freoa_verifica.connectors.camara_portao import Portao
    estado = Estado(home)
    transporte = Transporte(relogio, rotas)
    p = Portao(transporte, estado=estado, relogio=relogio, instrumento=True, ativacao=lambda: ativ.ativacao(estado))
    return p.obter(url), transporte
