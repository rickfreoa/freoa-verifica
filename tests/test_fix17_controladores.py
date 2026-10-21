"""FIX17 (auditoria r13, F-23, F-17, F-15): varredura dos controladores que chamam conectores.

Propriedade, para cada controlador: CAPTCHA no primeiro pedido -> (a) nenhum pedido posterior ao mesmo host na
chamada; (b) a indisponibilidade sobe estruturada, com categoria e evidência; (c) a resposta declara a fonte
indisponível (status != "ok"). Transporte e conectores reais, TCP local; nada sai da máquina.
"""

from __future__ import annotations

import re
import socketserver
import sqlite3
import threading
from collections import Counter

import pytest

from freoa_verifica import service
from freoa_verifica.connectors import guarda
from freoa_verifica.connectors.base import Candidate, CandidateList, Unavailable, registry
from freoa_verifica.connectors.bcb import BcbConnector
from freoa_verifica.connectors.cvm_colegiado import CvmColegiadoConnector
from freoa_verifica.connectors.cvm_normas import CvmNormasConnector
from freoa_verifica.connectors.stj import StjConnector
from freoa_verifica.semente import SyncState, _com_guarda
from freoa_verifica.service import Verifica
from tests.test_transport import _fast_guards, _wire_local

CAPTCHA = b"<html><body><p>CAPTCHA</p></body></html>"
RESPOSTA = (b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\nContent-Type: text/html; charset=utf-8\r\n"
            b"Content-Length: %d\r\n\r\n" % len(CAPTCHA)) + CAPTCHA


def servidor_que_le_o_corpo(bytes_resposta: bytes):
    """Como `_servidor`, mas consome o corpo (Content-Length) antes de responder: no Windows, fechar o socket com
    corpo de POST não lido manda RST e o cliente veria falha de transporte em vez da resposta."""
    pedidos: list[bytes] = []

    class H(socketserver.BaseRequestHandler):
        def handle(self):
            dados = b""
            while b"\r\n\r\n" not in dados:
                parte = self.request.recv(4096)
                if not parte:
                    return
                dados += parte
            cab, _, resto = dados.partition(b"\r\n\r\n")
            m = re.search(rb"(?im)^content-length:\s*(\d+)", cab)
            falta = int(m.group(1)) - len(resto) if m else 0
            while falta > 0:
                parte = self.request.recv(min(65536, falta))
                if not parte:
                    break
                falta -= len(parte)
            pedidos.append(cab)
            self.request.sendall(bytes_resposta)

    class S(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    server = S(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, pedidos


@pytest.fixture
def rede(monkeypatch):
    """Servidor local que desafia todo pedido; devolve um contador de pedidos por host (cabeçalho Host)."""
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    server, pedidos = servidor_que_le_o_corpo(RESPOSTA)
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])

    def por_host() -> Counter:
        return Counter(re.search(rb"(?im)^host:\s*([^\r\n:]+)", p).group(1).decode().lower() for p in pedidos)

    yield por_host
    server.shutdown()


def _desafio(declaracao: dict) -> None:
    """(b)+(c): status da fonte diferente de ok, categoria e evidência presentes."""
    assert declaracao.get("status") not in (None, "ok"), declaracao
    assert declaracao.get("categoria") == "ambiental_desafio", declaracao
    assert declaracao.get("evidencia_indisponibilidade"), declaracao


def _um_por_host(por_host: Counter) -> None:
    assert por_host, "o cenário não chegou à rede"
    assert max(por_host.values()) == 1, por_host


CVM_CANDS = [
    Candidate("cvm_normas", f"resolucoes:{n}", f"Resolução CVM {n}",
              url=f"https://conteudo.cvm.gov.br/legislacao/resolucoes/resol{n:03d}.html",
              metadata={"tipo": "resolucoes", "numero": str(n), "ano": 2020,
                        "page_url": f"https://conteudo.cvm.gov.br/legislacao/resolucoes/resol{n:03d}.html"})
    for n in (1, 2)
]
BCB_CANDS = [
    Candidate("bcb", f"bcb:Resolução CMN:{n}", f"Resolução CMN {n}",
              url=f"https://www.bcb.gov.br/api/conteudo/app/normativos/exibenormativo?p1=Resolução+CMN&p2={n}",
              metadata={"tipo": "Resolução CMN", "numero": str(n), "ano": 2020})
    for n in (1, 2)
]
ATAS = [
    Candidate("cvm_colegiado", f"https://conteudo.cvm.gov.br/decisoes/2024/2024013{n}_R0{n}.html", f"Ata {n}",
              url=f"https://conteudo.cvm.gov.br/decisoes/2024/2024013{n}_R0{n}.html",
              metadata={"kind": "ata_colegiado_cvm", "ano": 2024})
    for n in (1, 2)
]


def _busca_controlada(monkeypatch, cls, cands):
    """A busca devolve dois candidatos sem rede; o download de cada um passa pelo transporte real."""
    monkeypatch.setattr(cls, "search", lambda self, q, **kw: CandidateList(list(cands), total=len(cands)))


# --- controladores da fachada -----------------------------------------------------------------------------------


def _buscar_legislacao(svc, monkeypatch, fonte, cls, cands):
    _busca_controlada(monkeypatch, cls, cands)
    r = svc.buscar_legislacao("resolução", fonte=fonte)
    _desafio(r["fontes"][fonte])
    assert r["status"] != "ok"


def _buscar_normas(svc, monkeypatch, fonte, cls, cands):
    _busca_controlada(monkeypatch, cls, cands)
    metodo = svc.buscar_normas_cvm if fonte == "cvm_normas" else svc.buscar_normas_bcb
    r = metodo("resolução")
    _desafio(r["fonte"])
    _desafio({**r, "status": r["status"]})
    assert all(f.get("categoria") == "ambiental_desafio" for f in r["falhas"]), r["falhas"]
    assert r["status"] in {"parcial", "indisponivel"}


def _pesquisar(svc, monkeypatch):
    _busca_controlada(monkeypatch, CvmColegiadoConnector, ATAS)
    svc._connectors["cvm_colegiado"] = CvmColegiadoConnector()
    r = svc.pesquisar_jurisprudencia("ação", tribunais=["cvm"], desde="2024-01-01")
    _desafio(r["fontes"]["cvm_colegiado"])


def _verificar_citacao(svc, monkeypatch):
    r = svc.verificar_citacao("art. 1º da Lei 6.404/1976")
    assert r["identity"]["status"] == "unavailable", r["identity"]
    consultadas = r["identity"]["evidence"][0]["fontes_consultadas"]
    assert consultadas and all(c["categoria"] == "ambiental_desafio" for c in consultadas), consultadas


def _sincronizar_stj(svc, monkeypatch, tmp_path):
    monkeypatch.setattr(service, "registry", lambda: {"stj": StjConnector})
    conn = StjConnector(db_path=tmp_path / "stj.db")
    conn.sync_state = SyncState(svc.conn)  # estado de uma semente anterior na mesma instância (cenário do auditor)
    svc._connectors["stj"] = conn
    r = svc.sincronizar(fontes=["stj"])
    _desafio(r["fontes"][0])


CONTROLADORES = {
    "buscar_legislacao[cvm_normas]": lambda s, m, t: _buscar_legislacao(s, m, "cvm_normas", CvmNormasConnector,
                                                                       CVM_CANDS),
    "buscar_legislacao[bcb]": lambda s, m, t: _buscar_legislacao(s, m, "bcb", BcbConnector, BCB_CANDS),
    "buscar_normas_cvm": lambda s, m, t: _buscar_normas(s, m, "cvm_normas", CvmNormasConnector, CVM_CANDS),
    "buscar_normas_bcb": lambda s, m, t: _buscar_normas(s, m, "bcb", BcbConnector, BCB_CANDS),
    "pesquisar_jurisprudencia[cvm]": lambda s, m, t: _pesquisar(s, m),
    "verificar_citacao": lambda s, m, t: _verificar_citacao(s, m),
    "sincronizar[stj,com_estado]": lambda s, m, t: _sincronizar_stj(s, m, t),
}


@pytest.mark.parametrize("nome", sorted(CONTROLADORES))
def test_controlador_para_a_fonte_apos_captcha_e_declara(rede, monkeypatch, tmp_path, nome):
    with Verifica(tmp_path / "h") as svc:
        CONTROLADORES[nome](svc, monkeypatch, tmp_path)
    _um_por_host(rede())


# --- conectores chamados diretamente (sem a fachada) ------------------------------------------------------------


def test_stj_sync_com_estado_nao_segue_para_outro_pacote(rede, tmp_path):
    db = sqlite3.connect(":memory:")
    from freoa_verifica.store.db import apply_migrations

    apply_migrations(db)
    conn = StjConnector(db_path=tmp_path / "stj.db")
    conn.sync_state = SyncState(db)
    with pytest.raises(Unavailable) as ei:
        conn.sync(orgaos=["espelhos-de-acordaos-corte-especial", "espelhos-de-acordaos-primeira-secao"],
                  precedentes=True)
    assert ei.value.categoria == "ambiental_desafio" and ei.value.evidencia
    assert rede() == Counter({"dadosabertos.web.stj.jus.br": 1})
    assert [k for k, _ in conn.last_failures] == ["package:espelhos-de-acordaos-corte-especial"]


@pytest.mark.parametrize("cid", sorted(registry()))
def test_health_direto_nao_repete_host_apos_desafio(rede, cid):
    """F-17: `health()` chamado fora do `doctor` abre a própria guarda; nenhuma sonda passa por ok."""
    report = registry()[cid]().health()
    por_host = rede()
    if por_host:
        _um_por_host(por_host)
        # sonda resolvida sem rede (ex.: número conhecido) pode ser ok; a fonte, não
        assert not report.healthy and any(p.status == "unavailable" for p in report.probes), report


# --- guarda por chamada: renovada na entrada externa, compartilhada pelas aninhadas (F-15) ----------------------


class _Semente:
    @_com_guarda
    def externa(self):
        return guarda.ativa(), self.aninhada()

    @_com_guarda
    def aninhada(self):
        return guarda.ativa()


def test_semente_renova_a_guarda_por_execucao_e_compartilha_nas_aninhadas():
    s = _Semente()
    g1, g1_aninhada = s.externa()
    g2, _ = s.externa()
    assert g1 is not None and g1 is g1_aninhada and g1 is not g2
    assert guarda.ativa() is None
    with guarda.da_chamada() as externa:
        assert s.externa()[0] is externa


def test_fachada_e_conector_abrem_guarda_e_ela_morre_com_a_chamada(tmp_path, monkeypatch):
    vistas = []

    def search(self, q, **kw):
        vistas.append(guarda.ativa())
        raise Unavailable("x", "ambiental_desafio", {"status": 403})

    monkeypatch.setattr(CvmNormasConnector, "search", search)
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path / "h") as svc:
        svc.buscar_normas_cvm("a")
        svc.buscar_normas_cvm("a")
    assert vistas[0] is not None and vistas[1] is not None and vistas[0] is not vistas[1]
    assert guarda.ativa() is None
