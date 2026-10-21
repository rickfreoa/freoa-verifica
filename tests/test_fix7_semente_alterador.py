"""FIX7/F-04: alterador que falha pela primeira vez durante `run` não é repetido na mesma execução.

Percurso `SementeSync.run → _resolve_alteradores → conector → transporte` contra servidor local real.
"""

from __future__ import annotations

import json

from freoa_verifica import transport
from freoa_verifica.aliases import WorkKey
from freoa_verifica.parsers.model import Annotation, ParsedDocument, Provision, Redaction
from freoa_verifica.semente import SementeSync
from freoa_verifica.service import Verifica
from tests.test_fix6_semente_repeticao import _servidor_status
from tests.test_transport import _fast_guards, _wire_local



def _so_desta_thread(esperas):
    """time.sleep global registra só as esperas da thread do teste: threads de outros testes não contam."""
    import threading
    dono = threading.get_ident()
    real = __import__("time").sleep

    def dormir(s):
        if threading.get_ident() == dono:
            esperas.append(s)
        else:
            real(s)
    return dormir

def _rodar(monkeypatch, tmp_path, server):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    monkeypatch.setattr(transport, "SLOW_WINDOW", 0.05)
    esperas: list[float] = []
    monkeypatch.setattr(transport, "_dormir", esperas.append)
    monkeypatch.setattr("time.sleep", _so_desta_thread(esperas))
    doc = ParsedDocument("fixture", "1", "Lei 6.404", None, "Art. 1 Texto.",
                         [Provision("art1", "Art. 1", "", redactions=[Redaction("Art. 1 Texto.", False, 0)])])
    doc.provisions[0].redactions[0].annotations = [
        Annotation("redacao_dada", "nota", "Lei 7.000, de 1980", act_date="1980")
    ]
    try:
        with Verifica(tmp_path) as svc:
            svc.indexar_obra(source_id="planalto", work_key=WorkKey("federal", "lei", "6404", 1976),
                             document=doc, body=b"principal", url="https://www.planalto.gov.br/principal")
            sync = SementeSync(svc, fontes=["planalto"], rate_delay=0)
            sync.corpus["planalto"] = [{"tipo": "LEI", "numero": "6404", "ano": 1976}]
            sync.corpus["leis_principais_alteradores"] = [{"tipo": "LEI", "numero": "6404", "ano": 1976}]
            sync.state.set("planalto", "LEI:6404:1976", "parseado")  # obra principal já capturada
            sync.state.set("alterador_data", "LEI:7000:1980", "parseado", payload={"data": "1980-01-01"})
            sync.run()
            linha = sync.state.get("alterador", "LEI:7000:1980")
        breaker = transport._circuit_breaker("www.planalto.gov.br")
    finally:
        server.shutdown()
        server.server_close()
    return linha, breaker


def test_alterador_503_durante_run_faz_tres_pedidos_e_um_incremento(monkeypatch, tmp_path):
    linha, breaker = _rodar(monkeypatch, tmp_path, server := _servidor_status(503))
    assert server.pedidos == 3
    assert breaker.failures == 1
    assert linha["status"] == "indisponivel"
    assert json.loads(linha["payload_json"])["categoria"] == "fonte_fora"


def test_alterador_retry_after_longo_durante_run_faz_um_pedido(monkeypatch, tmp_path):
    linha, breaker = _rodar(monkeypatch, tmp_path, server := _servidor_status(503, "3600"))
    assert server.pedidos == 1
    assert breaker.failures == 1
    assert linha["status"] == "indisponivel"
