"""FIX7c (decisão 0058, revista): entre fontes oficiais distintas, `Unavailable` de qualquer categoria
permite a próxima fonte, declarada em `fontes_consultadas`; erro não-`Unavailable` interrompe.

- `_capture_work` federal: Planalto → Senado.
- `_confirm_cnj`: TJSP → DataJud (confirma só o processo, com a falha do TJSP declarada).
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest

from freoa_verifica.aliases import WorkKey
from freoa_verifica.connectors.base import Candidate, Unavailable
from freoa_verifica.connectors.planalto import PlanaltoConnector
from freoa_verifica.service import Verifica
from freoa_verifica.transport import Response
from freoa_verifica.verify import SourceUnavailable
from tests.fixture_util import load_fixture, load_meta

LEI = WorkKey("federal", "lei", "6404", 1976)


class _Falha:
    def __init__(self, id_, erro):
        self.id = id_
        self.erro = erro
        self.chamadas = 0

    def resolve(self, key):
        self.chamadas += 1
        return Candidate(self.id, "LEI:6404:1976", "t", "https://www.planalto.gov.br/x")

    def fetch(self, cand):
        raise self.erro

    def search(self, *a, **kw):
        self.chamadas += 1
        raise self.erro


class _Senado:
    """Responde 200 com a captura real da Lei 6.404/1976 (sem rede), rotulada como Senado."""

    id = "senado"

    def __init__(self):
        self.chamadas = 0
        self._parser = PlanaltoConnector()

    def resolve(self, key):
        self.chamadas += 1
        return Candidate("senado", "LEI:6404:1976", "Lei 6.404/1976 (Senado)", "https://www25.senado.leg.br/lei6404")

    def fetch(self, cand):
        body = load_fixture("planalto_lei_6404_1976")
        url = "https://www25.senado.leg.br/lei6404"
        return Response(url, url, 200, {}, body, hashlib.sha256(body).hexdigest(),
                        load_meta()["planalto_lei_6404_1976"].get("capturado_em") or "2026-01-01T00:00:00+00:00",
                        [], "text/html")

    def parse(self, resp):
        return self._parser.parse(resp)


class _Marca:
    def __init__(self, id_):
        self.id = id_
        self.chamadas = 0

    def resolve(self, key):
        self.chamadas += 1
        return None


@pytest.mark.parametrize(
    "erro",
    [
        Unavailable("http_403", "recusa_identificado"),
        Unavailable("desafio_captcha", "ambiental_desafio"),
        Unavailable("http_503", "fonte_fora"),
        Unavailable("resposta_invalida"),
        Unavailable("http_404"),
    ],
    ids=["recusa", "desafio", "fonte_fora", "invalida", "404"],
)
def test_captura_federal_segue_para_o_senado_e_declara_a_falha_do_planalto(monkeypatch, tmp_path, erro):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        planalto, senado = _Falha("planalto", erro), _Senado()
        svc._connectors["planalto"], svc._connectors["senado"] = planalto, senado
        rw = svc._capture_work(LEI)
        fonte = svc.conn.execute("SELECT source_id FROM capture WHERE id=?", (rw.capture_id,)).fetchone()[0]
    assert fonte == "senado" and "senado" in rw.url
    assert rw.fontes_consultadas == [
        {"fonte": "planalto", "resultado": "indisponivel", "motivo": erro.reason, "categoria": erro.categoria}]
    assert planalto.chamadas == 1 and senado.chamadas == 1


def test_erro_de_parse_no_planalto_interrompe(monkeypatch, tmp_path):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        planalto, senado = _Falha("planalto", ValueError("parse")), _Senado()
        svc._connectors["planalto"], svc._connectors["senado"] = planalto, senado
        with pytest.raises(SourceUnavailable) as ei:
            svc._capture_work(LEI)
    assert ei.value.reason == "planalto:ValueError"
    assert senado.chamadas == 0


def test_todas_as_fontes_indisponiveis_declaram_ambas(monkeypatch, tmp_path):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        planalto = _Falha("planalto", Unavailable("http_403", "recusa_identificado"))
        senado = _Falha("senado", Unavailable("http_503", "fonte_fora"))
        svc._connectors["planalto"], svc._connectors["senado"] = planalto, senado
        with pytest.raises(SourceUnavailable) as ei:
            svc._capture_work(LEI)
    assert ei.value.reason == "planalto:http_403;senado:http_503"
    assert planalto.chamadas == 1 and senado.chamadas == 1


def test_fontes_consultadas_chega_a_saida_da_verificacao(monkeypatch, tmp_path):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        svc._connectors["planalto"] = _Falha("planalto", Unavailable("http_403", "recusa_identificado"))
        svc._connectors["senado"] = _Senado()
        out = svc.verificar_citacao("Lei 6.404/1976, art. 1º")
    evs = out["identity"]["evidence"]
    assert evs and evs[0]["fontes_consultadas"][0]["fonte"] == "planalto"
    assert evs[0]["fontes_consultadas"][0]["categoria"] == "recusa_identificado"
    assert "senado" in evs[0]["url"]


@pytest.mark.parametrize(
    "erro",
    [
        Unavailable("http_503", "fonte_fora"),
        Unavailable("desafio_captcha", "ambiental_desafio"),
        Unavailable("http_404"),
    ],
    ids=["503", "captcha", "404"],
)
def test_confirmacao_cnj_consulta_datajud_e_declara_a_falha_do_tjsp(monkeypatch, tmp_path, erro):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    cnj = "1000000-00.2020.8.26.0100"

    class _DataJud:
        id, authority, hosts = "datajud", "cnj", frozenset({"api-publica.datajud.cnj.jus.br"})
        chamadas = 0

        def resolve(self, key):
            self.chamadas += 1
            return Candidate("datajud", "k", "t", "https://api-publica.datajud.cnj.jus.br/x")

        def fetch(self, cand):
            body = b"{}"
            return Response(cand.url, cand.url, 200, {}, body, hashlib.sha256(body).hexdigest(),
                            "2026-01-01T00:00:00+00:00", [], "application/json")

        def parse(self, resp):
            return SimpleNamespace(cnj_number=cnj)

    with Verifica(tmp_path) as svc:
        tjsp, datajud = _Falha("tjsp", erro), _DataJud()
        svc._connectors["tjsp"], svc._connectors["datajud"] = tjsp, datajud
        status, ev = svc._confirm_cnj(SimpleNamespace(flags=[], raw=cnj))
    assert tjsp.chamadas == 1 and datajud.chamadas == 1
    assert status == "processo_confirmado" and ev["escopo"] == "processo; não julgamento"
    assert ev["fontes_consultadas"] == [
        {"fonte": "tjsp", "resultado": "indisponivel", "motivo": erro.reason, "categoria": erro.categoria}]


def test_confirmacao_cnj_com_ambas_indisponiveis_mantem_a_do_datajud_e_declara_tjsp(monkeypatch, tmp_path):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        svc._connectors["tjsp"] = _Falha("tjsp", Unavailable("desafio_captcha", "ambiental_desafio"))
        svc._connectors["datajud"] = SimpleNamespace(
            id="datajud", resolve=lambda key: (_ for _ in ()).throw(Unavailable("http_503", "fonte_fora")))
        status, ev = svc._confirm_cnj(SimpleNamespace(flags=[], raw="1000000-00.2020.8.26.0100"))
    assert status == "indisponivel" and ev["motivo"] == "http_503" and ev["categoria"] == "fonte_fora"
    assert ev["fontes_consultadas"][0]["fonte"] == "tjsp"


def test_confirmacao_cnj_erro_de_programacao_no_tjsp_interrompe(monkeypatch, tmp_path):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        tjsp, datajud = _Falha("tjsp", ValueError("x")), _Marca("datajud")
        tjsp.search = lambda *a, **k: (_ for _ in ()).throw(ValueError("x"))
        svc._connectors["tjsp"], svc._connectors["datajud"] = tjsp, datajud
        status, ev = svc._confirm_cnj(SimpleNamespace(flags=[], raw="1000000-00.2020.8.26.0100"))
    assert status == "indisponivel" and ev["motivo"] == "ValueError"
    assert datajud.chamadas == 0
