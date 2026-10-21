"""FIX17, auditoria adversarial própria: variantes novas nas três classes (charset, texto ao parser, controladores).

Cada variante é uma tentativa que o auditor ainda não fez; as que expuseram defeito foram corrigidas no mesmo lote.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter

import pytest

from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.planalto import PlanaltoConnector
from freoa_verifica.connectors.tjsp import TjspConnector
from freoa_verifica.parsers.bcb_json import parse_bcb_json
from freoa_verifica.service import Verifica
from freoa_verifica.transport import Response
from tests.test_fix12_sintaxe_estrita import _servidor
from tests.test_fix15_charset import _enviar
from tests.test_transport import _fast_guards, _wire_local

CAPTCHA = b"<p>CAPTCHA</p>"  # 14 bytes ASCII: par, decodifica "com sucesso" em UTF-16 como lixo CJK

# --- classe 1: charset ------------------------------------------------------------------------------------------

# nome -> (linhas de cabeçalho Content-Type cruas, corpo)
VARIANTES_CHARSET = {
    "quoted_pair_no_rotulo": (b'Content-Type: text/html; charset="utf\\-16le"\r\n', CAPTCHA),
    "rotulo_verdadeiro_utf16le_corpo_ascii": (b"Content-Type: text/html; charset=utf-16le\r\n", CAPTCHA),
    "bom_utf16_seguido_de_ascii": (b"Content-Type: text/html\r\n", b"\xff\xfe" + CAPTCHA),
    "utf32le_corpo_ascii": (b"Content-Type: text/html; charset=utf-32le\r\n", CAPTCHA + b"  "),
    "content_type_duplicado": (b"Content-Type: text/html\r\nContent-Type: text/html; charset=utf-16le\r\n", CAPTCHA),
}


def _enviar_cru(monkeypatch, status, cabecalhos, corpo):
    bruto = (b"HTTP/1.1 %d X\r\nConnection: close\r\n" % status + cabecalhos
             + b"Content-Length: %d\r\n\r\n" % len(corpo) + corpo)
    server, pedidos = _servidor(bruto)
    from tests.test_fix12_sintaxe_estrita import _buscar

    try:
        try:
            return _buscar(monkeypatch, server), pedidos
        except Unavailable as exc:
            return exc, pedidos
    finally:
        server.shutdown()


@pytest.mark.parametrize("status", [200, 403, 503])
@pytest.mark.parametrize("caso", sorted(VARIANTES_CHARSET))
def test_variante_charset_nunca_sucesso_nem_repeticao(monkeypatch, caso, status):
    """CAPTCHA em ASCII nos bytes é prova positiva, ainda que um rótulo UTF-16/32 o esconda do texto."""
    cab, corpo = VARIANTES_CHARSET[caso]
    u, pedidos = _enviar_cru(monkeypatch, status, cab, corpo)
    assert isinstance(u, Unavailable), u
    assert u.categoria in {"ambiental_desafio", "resposta_inesperada"}, (u.categoria, u.reason)
    assert len(pedidos) == 1


def test_rotulo_utf16_com_marcador_ascii_e_desafio(monkeypatch):
    u, _ = _enviar(monkeypatch, 503, "text/html; charset=utf-16le", CAPTCHA)
    assert u.categoria == "ambiental_desafio" and u.evidencia.get("marcador")


# --- classe 2: texto ao parser ----------------------------------------------------------------------------------

URL_PLANALTO = "https://www.planalto.gov.br/ccivil_03/leis/l1.htm"
CORPO_LEI = "<p>LEI Nº 1, DE 1 DE JANEIRO DE 2000</p><p>Art. 1º Ação de teste.</p>"


def _resp(url, corpo, ctype, mime="text/html"):
    return Response(url, url, 200, {}, corpo, hashlib.sha256(corpo).hexdigest(), "2026-10-20T00:00:00Z", [], mime,
                    content_type=ctype)


def _textos(doc):
    return " ".join(r.text for p in doc.provisions for r in p.redactions)


@pytest.mark.parametrize(
    "corpo, ctype",
    [
        # declaração XML divergente: o lxml recusa str com encoding declarado; o parser precisa retirá-la
        (f'<?xml version="1.0" encoding="iso-8859-1"?><html><body>{CORPO_LEI}</body></html>'.encode(),
         "text/html; charset=utf-8"),
        # meta http-equiv divergente do cabeçalho
        (('<html><head><meta http-equiv="Content-Type" content="text/html; charset=windows-1252">'
          f"</head><body>{CORPO_LEI}</body></html>").encode(), "text/html; charset=utf-8"),
        # BOM UTF-8 vence cabeçalho latin-1 (0061)
        (b"\xef\xbb\xbf" + f"<html><body>{CORPO_LEI}</body></html>".encode(), "text/html; charset=iso-8859-1"),
    ],
    ids=["xml_decl_divergente", "http_equiv_divergente", "bom_vence_cabecalho"],
)
def test_planalto_variantes(corpo, ctype):
    doc = PlanaltoConnector().parse(_resp(URL_PLANALTO, corpo, ctype))
    assert "Ação" in _textos(doc) and "Ã" not in _textos(doc), (_textos(doc), [i.code for i in doc.issues])


def test_bcb_html_embutido_com_meta_nao_reinterpreta():
    payload = {"conteudo": [{"Titulo": "Resolução CMN nº 1", "Tipo": "Resolução CMN", "Numero": 1,
                             "Data": "2024-01-01T00:00:00",
                             "Texto": '<meta charset="iso-8859-1"><p>Art. 1º Ação de teste.</p>',
                             "Revogado": False, "Cancelado": False}]}
    doc = parse_bcb_json(json.dumps(payload, ensure_ascii=False))
    assert "Ação" in doc.text and "Ã" not in doc.text


def test_tjsp_parse_html_com_meta_divergente():
    html = '<html><head><meta charset="iso-8859-1"></head><body><p>Ação de cobrança</p></body></html>'
    dec = TjspConnector().parse(_resp("https://esaj.tjsp.jus.br/cjsg/getArquivo.do", html.encode(),
                                      "text/html; charset=utf-8"))
    assert "Ação" in dec.text and "Ã" not in dec.text


# --- classe 3: controladores ------------------------------------------------------------------------------------

RESPOSTA = (b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\nContent-Type: text/html; charset=utf-8\r\n"
            b"Content-Length: 14\r\n\r\n" + CAPTCHA)


@pytest.fixture
def rede(monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    server, pedidos = _servidor(RESPOSTA)
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    yield lambda: Counter(re.search(rb"(?im)^host:\s*([^\r\n:]+)", p).group(1).decode().lower() for p in pedidos)
    server.shutdown()


def test_verificar_texto_varias_citacoes_compartilham_a_guarda(rede, tmp_path):
    texto = ("Conforme o art. 1º da Lei 6.404/1976 e o art. 2º da Lei 6.385/1976 "
             "e o art. 3º da Lei 10.406/2002.")
    with Verifica(tmp_path / "h") as svc:
        r = svc.verificar_texto(texto)
    por_host = rede()
    assert por_host and max(por_host.values()) == 1, por_host
    assert all(c["identity"]["status"] != "verified" for c in r["citacoes"]), r


def test_obter_dispositivo_declara_fonte_e_nao_repete(rede, tmp_path):
    with Verifica(tmp_path / "h") as svc:
        r = svc.obter_dispositivo("art. 1º da Lei 6.404/1976")
    por_host = rede()
    assert por_host and max(por_host.values()) == 1, por_host
    assert r.get("status") != "ok", r


def test_sincronizar_tcu_declara_e_nao_repete(rede, tmp_path):
    with Verifica(tmp_path / "h") as svc:
        r = svc.sincronizar(fontes=["tcu", "tcu"])  # fonte repetida na lista: a guarda é da chamada
    assert rede() == Counter({"dados-abertos.apps.tcu.gov.br": 1})
    assert [f["status"] for f in r["fontes"]] == ["indisponivel", "indisponivel"]
    assert all(f.get("categoria") == "ambiental_desafio" for f in r["fontes"]), r


def test_rest_normas_cvm_declara_fonte(rede, tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from freoa_verifica.connectors.base import Candidate, CandidateList
    from freoa_verifica.connectors.cvm_normas import CvmNormasConnector
    from freoa_verifica.rest import create_app

    cands = [Candidate("cvm_normas", f"resolucoes:{n}", f"Resolução CVM {n}",
                       url=f"https://conteudo.cvm.gov.br/legislacao/resolucoes/resol{n:03d}.html",
                       metadata={"tipo": "resolucoes", "numero": str(n), "ano": 2020}) for n in (1, 2, 3)]
    monkeypatch.setattr(CvmNormasConnector, "search", lambda self, q, **kw: CandidateList(cands, total=3))
    with Verifica(tmp_path / "h") as svc:
        app = create_app(home=str(svc.home))
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 5000)) as c:
        r = c.get("/v1/normas/cvm", params={"q": "resolução"}).json()
    assert rede() == Counter({"conteudo.cvm.gov.br": 1})
    assert r["fonte"]["status"] == "unavailable" and r["fonte"]["categoria"] == "ambiental_desafio", r


def test_chamadas_externas_sucessivas_nao_herdam_bloqueio(rede, tmp_path):
    """A guarda morre com a chamada: a segunda chamada externa consulta de novo (F-15 na fachada)."""
    with Verifica(tmp_path / "h") as svc:
        svc.sincronizar(fontes=["tcu"])
        svc.sincronizar(fontes=["tcu"])
    assert rede() == Counter({"dados-abertos.apps.tcu.gov.br": 2})
