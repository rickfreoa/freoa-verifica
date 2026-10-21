"""FIX6/F-04: a semente não repete falhas; a repetição é só do transporte.

Percurso completo `SementeSync.run → conector → transporte` contra servidor local real. A falha fica
pendente no checkpoint com categoria e motivo para a próxima execução.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


from freoa_verifica import transport
from freoa_verifica.semente import SementeSync
from freoa_verifica.service import Verifica
from tests.test_fix5_resposta_iniciada import _servidor as _servidor_gotejante
from tests.test_transport import _fast_guards, _wire_local


def _servidor_status(status: int, retry_after: str | None = None):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            return

        def do_GET(self):  # noqa: N802
            self.server.pedidos += 1
            self.send_response(status)
            if retry_after is not None:
                self.send_header("Retry-After", retry_after)
            self.send_header("Content-Length", "0")
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), H)
    server.pedidos = 0
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _rodar(monkeypatch, tmp_path, server):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    monkeypatch.setattr(transport, "SLOW_WINDOW", 0.05)
    esperas: list[float] = []
    monkeypatch.setattr(transport, "_dormir", esperas.append)
    monkeypatch.setattr("time.sleep", esperas.append)  # nenhum laço da semente pode dormir de verdade
    try:
        with Verifica(tmp_path) as svc:
            sync = SementeSync(svc, fontes=["planalto"], rate_delay=0)
            sync.corpus["planalto"] = [{"tipo": "LEI", "numero": "6404", "ano": 1976}]
            sync.run()
            linha = sync.state.get("planalto", "LEI:6404:1976")
        breaker = transport._circuit_breaker("www.planalto.gov.br")
    finally:
        server.shutdown()
        server.server_close()
        if hasattr(server, "parar"):
            server.parar.set()
    return linha, breaker, esperas


def _categoria(linha):
    assert linha["status"] == "indisponivel"
    return json.loads(linha["payload_json"])["categoria"]


def test_503_persistente_na_semente_faz_tres_pedidos_e_um_incremento_no_breaker(monkeypatch, tmp_path):
    linha, breaker, esperas = _rodar(monkeypatch, tmp_path, server := _servidor_status(503))
    assert server.pedidos == 3  # 1 + 2 repetições do transporte; a semente não repete
    assert breaker.failures == 1
    assert len(esperas) == 2
    assert linha["motivo"] == "http_503" and _categoria(linha) == "fonte_fora"


def test_retry_after_longo_na_semente_faz_um_pedido(monkeypatch, tmp_path):
    linha, breaker, esperas = _rodar(monkeypatch, tmp_path, server := _servidor_status(503, "3600"))
    assert server.pedidos == 1
    assert esperas == []
    assert _categoria(linha) == "fonte_fora"


def test_429_na_semente_faz_um_pedido(monkeypatch, tmp_path):
    linha, _, _ = _rodar(monkeypatch, tmp_path, server := _servidor_status(429))
    assert server.pedidos == 1
    assert linha["motivo"] == "http_429"


def test_transporte_lento_apos_200_na_semente_faz_um_pedido(monkeypatch, tmp_path):
    linha, _, _ = _rodar(monkeypatch, tmp_path, server := _servidor_gotejante("text/html"))
    assert server.pedidos == 1
    assert _categoria(linha) == "resposta_inesperada"


def test_pendencia_fonte_fora_e_retomada_so_na_proxima_execucao(monkeypatch, tmp_path):
    """Alterador pendente com categoria `fonte_fora` volta na execução seguinte, nunca na mesma."""
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        sync = SementeSync(svc, rate_delay=0)
        sync.corpus = {"planalto": []}
        sync.state.set("alterador", "LEI:8766:2000", "indisponivel", motivo="http_503", payload={"categoria": "fonte_fora"})
        sync.state.set("alterador", "LEI:8767:2000", "indisponivel", motivo="http_503", payload={"categoria": "resposta_inesperada"})
        chamadas = []

        def indexar(fonte, chave, **kw):
            chamadas.append(chave)
            sync.state.set(fonte, chave, "indisponivel", motivo="http_503", payload={"categoria": "fonte_fora"})
            return "indisponivel", None

        monkeypatch.setattr(sync, "_index_legis", indexar)
        sync.sync_planalto()
        assert chamadas == ["LEI:8766:2000"]
