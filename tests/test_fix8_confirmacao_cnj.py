"""FIX8/F-10: a confirmação CNJ reaproveita a resposta já capturada e interrompe a fonte diante de
`Unavailable` do indexador, declarando a falha antes de seguir ao DataJud.
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

from freoa_verifica.connectors.base import Candidate, ParsedDecision, Unavailable
from freoa_verifica.service import Verifica
from freoa_verifica.transport import Response

CNJ = "1000000-00.2020.8.26.0100"
CAPTCHA = Unavailable("desafio_captcha", "ambiental_desafio")


class _Tjsp:
    """Segunda requisição à mesma URL cai em CAPTCHA, como no cenário do auditor."""

    id, authority, hosts = "tjsp", "TJSP", frozenset({"esaj.tjsp.jus.br"})

    def __init__(self, parse_falha_na_indexacao=False):
        self.baixados: list[str] = []
        self.parses = 0
        self.parse_falha_na_indexacao = parse_falha_na_indexacao

    def search(self, *a, **kw):
        return [Candidate("tjsp", f"k{i}", "t", f"https://esaj.tjsp.jus.br/doc{i}") for i in (1, 2)]

    def fetch(self, cand):
        self.baixados.append(cand.url)
        if self.baixados.count(cand.url) > 1:
            raise CAPTCHA
        body = b"<html>acordao</html>"
        return Response(cand.url, cand.url, 200, {}, body, hashlib.sha256(body).hexdigest(),
                        "2026-01-01T00:00:00+00:00", [], "text/html")

    def parse(self, resp):
        self.parses += 1
        if self.parse_falha_na_indexacao and self.parses > 1:
            raise CAPTCHA
        return ParsedDecision("tjsp_cjsg", "acordao", "TJSP", "k", ementa="Ementa.", text="Inteiro teor.",
                              cnj_number=CNJ)


class _DataJud:
    id, authority, hosts = "datajud", "cnj", frozenset({"api-publica.datajud.cnj.jus.br"})

    def resolve(self, key):
        return Candidate("datajud", "k", "t", "https://api-publica.datajud.cnj.jus.br/x")

    def fetch(self, cand):
        body = b"{}"
        return Response(cand.url, cand.url, 200, {}, body, hashlib.sha256(body).hexdigest(),
                        "2026-01-01T00:00:00+00:00", [], "application/json")

    def parse(self, resp):
        return SimpleNamespace(cnj_number=CNJ)


def test_confirmacao_cnj_reaproveita_a_resposta_capturada(monkeypatch, tmp_path):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        tjsp = _Tjsp()
        svc._connectors["tjsp"] = tjsp
        status, ev = svc._confirm_cnj(SimpleNamespace(flags=[], raw=CNJ))
    assert tjsp.baixados == ["https://esaj.tjsp.jus.br/doc1"]
    assert status == "encontrada" and ev["capture_id"]


def test_unavailable_do_indexador_interrompe_a_fonte_e_e_declarado(monkeypatch, tmp_path):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        tjsp = _Tjsp(parse_falha_na_indexacao=True)
        svc._connectors["tjsp"], svc._connectors["datajud"] = tjsp, _DataJud()
        status, ev = svc._confirm_cnj(SimpleNamespace(flags=[], raw=CNJ))
    assert tjsp.baixados == ["https://esaj.tjsp.jus.br/doc1"]  # nenhum pedido adicional ao TJSP
    assert status == "processo_confirmado"
    assert ev["fontes_consultadas"] == [
        {"fonte": "tjsp", "resultado": "indisponivel", "motivo": CAPTCHA.reason, "categoria": CAPTCHA.categoria}]
