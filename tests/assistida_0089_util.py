"""0089 (b): eventos, arquivos e políticas SINTÉTICOS; não são prova de navegador real.

Geradores captura/adapter/entregar usam a porta real, sem rede e sem adulterar transport.
"""

from __future__ import annotations

import json

import threading

import pytest

from freoa_verifica import transport as t

from freoa_verifica.assistida import ambiente as a

from freoa_verifica.assistida.cdp import AdaptadorCDP, Alvo

from freoa_verifica.assistida.perfis import PERFIS

from tests.test_transport_assistida_0089 import eventos, pedido


URL = "https://www.planalto.gov.br/ccivil_03/leis/l6404.htm"


URN = "urn:lex:br:federal:lei:1976-12-15;6404"


UID = "f61218b3-1234-1234-1234-123456789abc"


META = (
    f"https://normas.leg.br/api/public/normas?urn={URN}&&tipo_documento=maior-detalhe"
)


BIN = f"https://normas.leg.br/api/public/binario/{UID}/texto"


BODY = b"<html><head><meta charset='utf-8'></head><body>Art. 1. Publico.</body></html>"


@pytest.fixture
def sessao():
    s = t.SessaoPortaAssistida(PERFIS["planalto"].porta, navegador="Brave 1")
    yield s
    s.encerrar()


class VigiaSintetico:
    linha_base = 1.0
    cond = threading.RLock()

    def __init__(self):
        self.erro = None
        self.barreiras = 0
        self.ao_invalidar = lambda: None

    def conferir(self):
        if self.erro:
            raise a.RecusaSessao(self.erro)

    def assentar(self):
        self.conferir()
        return self.linha_base

    def barreira(self):
        self.conferir()
        self.barreiras += 1


class CanalSintetico:
    def __init__(self):
        self.comandos = []

    def enviar(self, obj):
        self.comandos.append(obj)


def adapter(sessao):
    canal, vigia = CanalSintetico(), VigiaSintetico()
    ad = AdaptadorCDP(PERFIS["planalto"], sessao, canal, vigia)
    ad.fase = 3
    ad.alvos["cdp"] = Alvo("aba", "page", "", True, "raiz", URL)
    return ad


def request(ad, *, sid="cdp", rid="pedido", url=URL, tipo="Document", **extra):
    p = dict(
        requestId=rid,
        request={"url": url, "method": "GET"},
        type=tipo,
        frameId="raiz",
        documentURL=URL,
        timestamp=100.0,
        wallTime=1_700_000_000.0,
        initiator={"type": "other"},
    )
    p.update(extra)
    ad.processar({"method": "Network.requestWillBeSent", "sessionId": sid, "params": p})


def entregar(ad, *, sid="cdp", rid="pedido", body=BODY, **kw):
    p = pedido(chave=t.ChaveAssistida(sid, ad.alvos[sid].id, rid, 0))
    for e in eventos(p, body=body, **kw):
        dados = e.dados
        if e.metodo == "streamResourceContent":
            cmd = next(
                c
                for c in reversed(ad.canal.comandos)
                if c["method"] == "Network.streamResourceContent"
                and c["sessionId"] == sid
            )
            ad.processar({"id": cmd["id"], "result": dados})
            continue
        if e.metodo == "requestWillBeSentExtraInfo":
            dados = {"headers": {}, "associatedCookies": []}
        ad.processar(
            {
                "sessionId": sid,
                "method": "Network." + e.metodo,
                "params": {"requestId": rid, **dados},
            }
        )


def captura(url, body, *, ident="x", mime="text/html"):
    perfil = PERFIS["planalto" if url == URL else "normas_leg"]
    s = t.SessaoPortaAssistida(perfil.porta, navegador="Brave 1")
    tipo = "Document" if url == URL else "XHR"
    p = pedido(
        url=url,
        tipo=tipo,
        chave=t.ChaveAssistida("cdp", "aba", ident, 0),
        documento_raiz="https://normas.leg.br/" if tipo == "XHR" else URL,
        iniciador={
            "tipo": "script",
            "frame_id": "raiz",
            "documento": "https://normas.leg.br/",
            "alvo": "aba",
        }
        if tipo == "XHR"
        else {"tipo": "other"},
    )
    porta = t.capturar_assistida(s, p)
    for e in eventos(p, body=body, headers={"Content-Type": mime + "; charset=utf-8"}):
        porta.observar(e)
    c = porta.admitir()
    s.encerrar()
    return c


def metadados(*, urn=URN, uid=UID, version="Current", eid=None, extra=None):
    e = {
        "@type": "LegislationObject",
        "version": version,
        "@id": eid or urn + "@versao.atualizada",
        "contentUrl": f"https://normas.leg.br/api/binario/{uid}/texto",
    }
    return json.dumps(
        {"legislationIdentifier": urn, "encoding": [e, *(extra or [])]}
    ).encode()


class RegistroSintetico:
    HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE = "cu", "lm"
    KEY_WOW64_64KEY, KEY_WOW64_32KEY, KEY_READ = 1, 2, 4

    def __init__(self, valores=None, forca=False, falha=False):
        self.valores, self.forca, self.falha = valores or {}, forca, falha

    def OpenKey(self, hive, path, *args):
        if self.falha:
            raise PermissionError
        if path == "ExtensionInstallForcelist":
            if not self.forca:
                raise FileNotFoundError
            return RegistroChave({"1": "valor-nao-gravavel"})
        return RegistroChave(self.valores if hive == "cu" else {})

    def QueryInfoKey(self, key):
        return (0, len(key.valores), 0)

    def EnumValue(self, key, i):
        k = list(key.valores)[i]
        return k, key.valores[k], 1


class RegistroChave:
    def __init__(self, valores):
        self.valores = valores

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass
