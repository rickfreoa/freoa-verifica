"""FIX7 (varredura): em `service.py`, só ausência explícita autoriza nova requisição após falha.

- `_capture_work` federal: falha no Planalto não consulta o Senado; 404 consulta.
- `_confirm_cnj`: falha na busca do TJSP não cai para o DataJud; 404 cai.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freoa_verifica.aliases import WorkKey
from freoa_verifica.connectors.base import Candidate, Unavailable
from freoa_verifica.service import Verifica
from freoa_verifica.verify import SourceUnavailable


class _Falha:
    def __init__(self, id_, erro):
        self.id = id_
        self.erro = erro
        self.chamadas = 0

    def resolve(self, key):
        self.chamadas += 1
        return Candidate(self.id, "k", "t", "https://www.planalto.gov.br/x")

    def fetch(self, cand):
        raise self.erro

    def search(self, *a, **kw):
        self.chamadas += 1
        raise self.erro


class _Marca:
    def __init__(self, id_):
        self.id = id_
        self.chamadas = 0

    def resolve(self, key):
        self.chamadas += 1
        return None


@pytest.mark.parametrize(
    "erro,senado_consultado",
    [
        (Unavailable("desafio_captcha", "ambiental_desafio"), False),
        (Unavailable("http_403", "recusa_identificado"), False),
        (Unavailable("http_503", "fonte_fora"), False),
        (Unavailable("resposta_invalida"), False),
        (Unavailable("http_404"), True),
    ],
    ids=["captcha", "403", "503", "invalida", "404"],
)
def test_captura_federal_so_consulta_o_senado_apos_ausencia_explicita(monkeypatch, tmp_path, erro, senado_consultado):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        planalto, senado = _Falha("planalto", erro), _Marca("senado")
        svc._connectors["planalto"], svc._connectors["senado"] = planalto, senado
        with pytest.raises(SourceUnavailable) as ei:
            svc._capture_work(WorkKey("federal", "lei", "6404", 1976))
    assert ei.value.reason.startswith(f"planalto:{erro.reason}")
    assert (senado.chamadas == 1) is senado_consultado


@pytest.mark.parametrize(
    "erro,datajud_consultado",
    [
        (Unavailable("http_503", "fonte_fora"), False),
        (Unavailable("desafio_captcha", "ambiental_desafio"), False),
        (Unavailable("http_404"), True),
    ],
    ids=["503", "captcha", "404"],
)
def test_confirmacao_cnj_so_consulta_datajud_apos_ausencia_explicita(monkeypatch, tmp_path, erro, datajud_consultado):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        tjsp, datajud = _Falha("tjsp", erro), _Marca("datajud")
        svc._connectors["tjsp"], svc._connectors["datajud"] = tjsp, datajud
        cite = SimpleNamespace(flags=[], raw="1000000-00.2020.8.26.0100")
        status, ev = svc._confirm_cnj(cite)
    assert tjsp.chamadas == 1
    assert (datajud.chamadas == 1) is datajud_consultado
    if not datajud_consultado:
        assert status == "indisponivel" and ev["motivo"] == erro.reason
