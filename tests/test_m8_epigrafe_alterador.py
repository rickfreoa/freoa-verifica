"""M8: data do ato alterador extraída da epígrafe quando o Senado não dá a data."""

from datetime import datetime, timezone
import hashlib

import pytest

from freoa_verifica.aliases import WorkKey
from freoa_verifica.connectors.base import Candidate, Unavailable
from freoa_verifica.parsers.model import Annotation, ParsedDocument, Provision, Redaction
from freoa_verifica.semente import SementeSync, data_da_epigrafe
from freoa_verifica.service import Verifica
from freoa_verifica.transport import Response


@pytest.mark.parametrize(
    "epigrafe,esperado",
    [
        ("LEI Nº 14.195, DE 26 DE AGOSTO DE 2021", "2021-08-26"),
        ("LEI Nº 10.303, DE 31 DE OUTUBRO DE 2001", "2001-10-31"),
        ("LEI Nº 1.000, DE 1º DE MARÇO DE 2000", "2000-03-01"),
        ("LEI No 1.000, DE 1o DE MARÇO DE 2000", "2000-03-01"),
        ("lei nº 1.000, de 1º de março de 2000", "2000-03-01"),
        ("LEI Nº 1, DE 2 DE MARCO DE 2000", "2000-03-02"),
        ("LEI Nº 1, DE 1 DE ABRIL DE 1999", "1999-04-01"),
        ("LEI Nº 1, DE 29 DE FEVEREIRO DE 2024", "2024-02-29"),
        ("DECRETO-LEI Nº 4.657, DE 4 DE SETEMBRO DE 1942", "1942-09-04"),
    ],
)
def test_data_da_epigrafe_formatos(epigrafe, esperado):
    assert data_da_epigrafe(epigrafe) == esperado


@pytest.mark.parametrize(
    "epigrafe",
    [
        "LEI Nº 1, DE 31 DE FEVEREIRO DE 2021",  # dia inexistente
        "LEI Nº 1, DE 29 DE FEVEREIRO DE 2023",  # ano não bissexto
        "LEI Nº 1, DE 5 DE ABC DE 2021",  # mês desconhecido
        "LEI Nº 1, DE 2021",  # sem data completa
        "Sem data alguma",
        "",
        None,
    ],
)
def test_data_da_epigrafe_invalida_vira_none(epigrafe):
    assert data_da_epigrafe(epigrafe) is None


def _doc(text="Art. 1 Texto original.", title="teste"):
    return ParsedDocument("fixture", "1", title, None, text,
                          [Provision("art1", "Art. 1", "", redactions=[Redaction(text, False, 0)])])


class AlteradorConnector:
    id = "planalto"

    def __init__(self, senado_data, titulo):
        self.senado_data = senado_data
        self.titulo = titulo

    def resolve_alterador_date(self, *args):
        return self.senado_data

    def resolve(self, key):
        return Candidate(self.id, str(key["numero"]), "teste", "https://www.planalto.gov.br/fixture")

    def fetch(self, cand):
        body = cand.key.encode()
        return Response(cand.url, cand.url, 200, {}, body, hashlib.sha256(body).hexdigest(),
                        datetime.now(timezone.utc).isoformat(), [], "text/plain")

    def parse(self, response):
        return _doc(f"{self.titulo}\nArt. 1 Texto do alterador.", title=self.titulo)


def _data_do_alterador(tmp_path, monkeypatch, senado_data, titulo):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    doc = _doc()
    doc.provisions[0].redactions[0].annotations = [
        Annotation("redacao_dada", "nota", "Lei 14.195, de 2021", act_date="2021")
    ]
    with Verifica(tmp_path) as svc:
        svc.indexar_obra(source_id="planalto", work_key=WorkKey("federal", "lei", "6404", 1976),
                         document=doc, body=b"parent", url="https://www.planalto.gov.br/parent")
        svc._connectors["planalto"] = AlteradorConnector(senado_data, titulo)
        engine = SementeSync(svc, rate_delay=0)
        engine._resolve_alteradores("LEI:6404:1976", document=doc)
    return doc.provisions[0].redactions[0].annotations[0].act_date


def test_epigrafe_preenche_data_quando_senado_nao_da(tmp_path, monkeypatch):
    titulo = "LEI Nº 14.195, DE 26 DE AGOSTO DE 2021"
    assert _data_do_alterador(tmp_path, monkeypatch, None, titulo) == "2021-08-26"


def test_senado_tem_precedencia_sobre_epigrafe(tmp_path, monkeypatch):
    titulo = "LEI Nº 14.195, DE 26 DE AGOSTO DE 2021"
    assert _data_do_alterador(tmp_path, monkeypatch, "2021-08-20", titulo) == "2021-08-20"


def test_epigrafe_sem_data_valida_mantem_ano(tmp_path, monkeypatch):
    titulo = "LEI Nº 14.195, DE 31 DE FEVEREIRO DE 2021"
    assert _data_do_alterador(tmp_path, monkeypatch, None, titulo) == "2021"
