"""FIX8/F-08: uma guarda única por chave de requisição cobre toda a execução de `SementeSync.run`.

Servidor local real; 503 + Retry-After longo: cada chave é pedida uma vez e conta um incremento
no breaker, mesmo quando aparece em dois contextos (alterador) ou em duas listas (BCB).
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from freoa_verifica import transport
from freoa_verifica.aliases import WorkKey
from freoa_verifica.parsers.model import Annotation, ParsedDocument, Provision, Redaction
from freoa_verifica.semente import SementeSync
from freoa_verifica.service import Verifica
from tests.test_transport import _fast_guards, _wire_local

_BUSCA_BCB = json.dumps(
    {
        "TotalRows": 1,
        "Rows": [{"TipodoNormativoOWSCHCS": "Resolução CMN", "NumeroOWSNMBR": "4557", "title": "Resolução CMN 4557"}],
    }
).encode()


def _servidor(busca_bcb: bool = False):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            return

        def do_GET(self):  # noqa: N802
            self.server.pedidos.append((self.headers.get("Host"), self.path))
            if busca_bcb and "/api/search/" in self.path:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(_BUSCA_BCB)))
                self.end_headers()
                self.wfile.write(_BUSCA_BCB)
                return
            self.send_response(503)
            self.send_header("Retry-After", "3600")
            self.send_header("Content-Length", "0")
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), H)
    server.pedidos = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _preparar(monkeypatch, server):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    monkeypatch.setattr(transport, "SLOW_WINDOW", 0.05)
    monkeypatch.setattr(transport, "_dormir", lambda s: None)
    monkeypatch.setattr("time.sleep", lambda s: None)
    incrementos: list[None] = []
    original = transport.CircuitBreaker.record_failure

    def contar(self):
        incrementos.append(None)
        original(self)

    monkeypatch.setattr(transport.CircuitBreaker, "record_failure", contar)
    return incrementos


def _obra_com_remissao(svc, numero: int, ano: int) -> None:
    doc = ParsedDocument("fixture", str(numero), f"Lei {numero}", None, "Art. 1 Texto.",
                         [Provision("art1", "Art. 1", "", redactions=[Redaction("Art. 1 Texto.", False, 0)])])
    doc.provisions[0].redactions[0].annotations = [
        Annotation("redacao_dada", "nota", "Lei 7.000, de 1980", act_date="1980")
    ]
    svc.indexar_obra(source_id="planalto", work_key=WorkKey("federal", "lei", str(numero), ano),
                     document=doc, body=f"principal{numero}".encode(), url=f"https://www.planalto.gov.br/{numero}")


def test_dois_contextos_com_o_mesmo_alterador_consultam_a_data_uma_vez(monkeypatch, tmp_path):
    server = _servidor()
    incrementos = _preparar(monkeypatch, server)
    try:
        with Verifica(tmp_path) as svc:
            _obra_com_remissao(svc, 6404, 1976)
            _obra_com_remissao(svc, 6024, 1974)
            sync = SementeSync(svc, fontes=["planalto"], rate_delay=0)
            sync.corpus["planalto"] = [{"tipo": "LEI", "numero": "6404", "ano": 1976},
                                       {"tipo": "LEI", "numero": "6024", "ano": 1974}]
            sync.corpus["leis_principais_alteradores"] = list(sync.corpus["planalto"])
            for chave in ("LEI:6404:1976", "LEI:6024:1974"):
                sync.state.set("planalto", chave, "parseado")
            sync.run()
    finally:
        server.shutdown()
        server.server_close()
    senado = [p for p in server.pedidos if p[0] in {"legis.senado.leg.br", "normas.leg.br"}]
    assert len(senado) == 1
    assert len(server.pedidos) == 2  # data no Senado + texto do alterador no Planalto
    assert len(incrementos) == 2  # um por host, nenhum por repetição


def test_mesma_norma_bcb_em_duas_listas_e_pedida_uma_vez(monkeypatch, tmp_path):
    server = _servidor(busca_bcb=True)
    incrementos = _preparar(monkeypatch, server)
    try:
        with Verifica(tmp_path) as svc:
            sync = SementeSync(svc, fontes=["bcb"], rate_delay=0)
            sync.corpus["bcb_cmn"] = {
                "especificas": [{"tipo": "Resolução CMN", "numero": 4557}],
                "recentes": {"tipos": ["Resolução CMN"], "quantidade": 5},
            }
            sync.run()
    finally:
        server.shutdown()
        server.server_close()
    conteudo = [p for p in server.pedidos if "/api/conteudo/" in p[1]]
    assert len(conteudo) == 1
    assert len(incrementos) == 1
