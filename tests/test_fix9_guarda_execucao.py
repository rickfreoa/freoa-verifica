"""FIX9/F-08 e F-11: a requisição efetiva é feita uma vez por execução e a fonte que desafiou não é consultada de novo.

Propriedades sobre servidor HTTP local real: identidade = método + URL normalizada + corpo (não o papel
da chamada); o primeiro desfecho (sucesso ou `Unavailable`) é reaproveitado; após `ambiental_desafio` ou
`recusa_identificado`, nenhum novo pedido ao host na execução; o breaker conta 1 por falha lógica.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from freoa_verifica import transport
from freoa_verifica.aliases import WorkKey
from freoa_verifica.connectors.base import Candidate, Unavailable
from freoa_verifica.connectors.cvm_colegiado import CvmColegiadoConnector
from freoa_verifica.connectors.guarda import GuardaExecucao
from freoa_verifica.connectors.httputil import connector_fetch
from freoa_verifica.parsers.model import Annotation, ParsedDocument, Provision, Redaction
from freoa_verifica.semente import SementeSync
from freoa_verifica.service import Verifica
from tests.test_transport import _fast_guards, _wire_local

HOST = "www.planalto.gov.br"
CAPTCHA = b"<html><body>Please solve this CAPTCHA to continue</body></html>"
ATA = (
    "<html><body><h2>Reuniao do Colegiado</h2><article>"
    '<p class="text-uppercase">ASSUNTO UM PROC. 19957.000001/2024-11 sobre o item um</p><p>Decisao um.</p>'
    '<p class="text-uppercase">ASSUNTO DOIS PROC. 19957.000002/2024-22 sobre o item dois</p><p>Decisao dois.</p>'
    '<p class="text-uppercase">ASSUNTO TRES PROC. 19957.000003/2024-33 sobre o item tres</p><p>Decisao tres.</p>'
    "</article></body></html>"
).encode()
HTML_OK = b"<html><body>ok</body></html>"


def _servidor(rotas):
    """rotas: caminho -> lista de respostas (status, content_type, corpo); a última se repete."""

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            return

        def _responder(self, corpo_req=b""):
            self.server.pedidos.append((self.command, self.path, corpo_req))
            fila = rotas.get(self.path.split("?")[0]) or rotas.get("*") or [(404, "text/html", b"x")]
            n = sum(1 for p in self.server.pedidos if p[1] == self.path and p[0] == self.command)
            status, ctype, corpo, *extra = fila[min(n, len(fila)) - 1]
            self.send_response(status)
            for nome, valor in (extra[0] if extra else {}).items():
                self.send_header(nome, valor)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def do_GET(self):  # noqa: N802
            self._responder()

        def do_POST(self):  # noqa: N802
            tamanho = int(self.headers.get("Content-Length") or 0)
            self._responder(self.rfile.read(tamanho))

    server = ThreadingHTTPServer(("127.0.0.1", 0), H)
    server.pedidos = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture
def ambiente(monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    _fast_guards(monkeypatch)
    monkeypatch.setattr(transport, "_dormir", lambda s: None)
    monkeypatch.setattr("time.sleep", lambda s: None)
    incrementos: list[None] = []
    original = transport.CircuitBreaker.record_failure

    def contar(self):
        incrementos.append(None)
        original(self)

    monkeypatch.setattr(transport.CircuitBreaker, "record_failure", contar)
    servidores = []

    def subir(rotas):
        server = _servidor(rotas)
        servidores.append(server)
        _wire_local(monkeypatch, server.server_address[1])
        return server, incrementos

    yield subir
    for s in servidores:
        s.shutdown()
        s.server_close()


def _baixar(url, metodo="GET", corpo=None):
    return connector_fetch(
        url,
        hosts=frozenset({HOST}),
        path_prefixes=None,
        mimes=frozenset({"text/html"}),
        method=metodo,
        body=corpo,
    )


# --- identidade efetiva ------------------------------------------------------------------------


@pytest.mark.parametrize("resposta", [(200, "text/html", HTML_OK), (503, "text/html", b"fora")], ids=["200", "503"])
@pytest.mark.parametrize("metodo,corpo", [("GET", None), ("POST", b"a=1")], ids=["GET", "POST"])
def test_mesma_identidade_em_papeis_diferentes_pede_uma_vez(ambiente, resposta, metodo, corpo):
    server, incrementos = ambiente({"/ccivil_03/leis/l7000compilada.htm": [resposta]})
    guarda = GuardaExecucao()
    url = f"https://{HOST}/ccivil_03/leis/l7000compilada.htm"
    resultados = []
    with guarda.ativar():
        for variante in (url, url.replace("https://www.planalto", "https://WWW.PLANALTO")):  # normalização
            try:
                resultados.append(_baixar(variante, metodo, corpo).body)
            except Unavailable as u:
                resultados.append((u.reason, u.categoria))
    assert len(server.pedidos) == (1 + (2 if resposta[0] == 503 and metodo == "GET" else 0))
    assert resultados[0] == resultados[1]
    assert len(incrementos) == (0 if resposta[0] == 200 else 1)


def test_corpo_diferente_e_outra_identidade(ambiente):
    server, _ = ambiente({"/x": [(200, "text/html", HTML_OK)]})
    guarda = GuardaExecucao()
    with guarda.ativar():
        _baixar(f"https://{HOST}/x", "POST", b"a=1")
        _baixar(f"https://{HOST}/x", "POST", b"a=2")
        _baixar(f"https://{HOST}/x", "POST", b"a=1")
    assert [p[2] for p in server.pedidos] == [b"a=1", b"a=2"]


def test_sem_guarda_ativa_nada_muda(ambiente):
    server, _ = ambiente({"/x": [(200, "text/html", HTML_OK)]})
    _baixar(f"https://{HOST}/x")
    _baixar(f"https://{HOST}/x")
    assert len(server.pedidos) == 2


# --- bloqueio por fonte ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "resposta,categoria,bloqueia",
    [
        ((403, "text/html", CAPTCHA), "ambiental_desafio", True),
        ((403, "text/html", b"negado"), "recusa_identificado", True),
        ((503, "text/html", b"fora"), "fonte_fora", False),
        ((200, "application/json", b"{}"), "resposta_inesperada", False),
    ],
    ids=["desafio", "recusa", "fonte_fora", "resposta_inesperada"],
)
def test_bloqueio_por_fonte_so_para_desafio_e_recusa(ambiente, resposta, categoria, bloqueia):
    server, incrementos = ambiente({"/a": [resposta], "/b": [(200, "text/html", HTML_OK)]})
    guarda = GuardaExecucao()
    with guarda.ativar():
        with pytest.raises(Unavailable) as primeira:
            _baixar(f"https://{HOST}/a")
        pedidos_a = len(server.pedidos)
        if bloqueia:
            with pytest.raises(Unavailable) as segunda:
                _baixar(f"https://{HOST}/b")
            assert segunda.value.categoria == categoria
            assert segunda.value.evidencia["bloqueio_fonte"] == HOST
            assert len(server.pedidos) == pedidos_a  # nenhum pedido novo ao host
        else:
            assert _baixar(f"https://{HOST}/b").body == HTML_OK
            assert len(server.pedidos) == pedidos_a + 1
    assert primeira.value.categoria == categoria
    assert len(incrementos) == 1  # uma falha lógica, qualquer que seja o número de consultas posteriores


def test_bloqueio_nao_vaza_para_fora_da_guarda(ambiente):
    server, _ = ambiente({"/a": [(403, "text/html", CAPTCHA)], "/b": [(200, "text/html", HTML_OK)]})
    with GuardaExecucao().ativar():
        with pytest.raises(Unavailable):
            _baixar(f"https://{HOST}/a")
    assert _baixar(f"https://{HOST}/b").body == HTML_OK  # nova execução, nova decisão


# --- F-08: obra principal = alteradora ---------------------------------------------------------


def _obra_com_remissao(svc, numero: int, ano: int) -> None:
    doc = ParsedDocument("fixture", str(numero), f"Lei {numero}", None, "Art. 1 Texto.",
                         [Provision("art1", "Art. 1", "", redactions=[Redaction("Art. 1 Texto.", False, 0)])])
    doc.provisions[0].redactions[0].annotations = [
        Annotation("redacao_dada", "nota", "Lei 7.000, de 1980", act_date="1980")
    ]
    svc.indexar_obra(source_id="planalto", work_key=WorkKey("federal", "lei", str(numero), ano),
                     document=doc, body=f"principal{numero}".encode(), url=f"https://www.planalto.gov.br/{numero}")


@pytest.mark.parametrize("ordem", [("6404", "7000"), ("7000", "6404")], ids=["alteradora_antes", "principal_antes"])
def test_lei_principal_e_alteradora_e_pedida_uma_vez(ambiente, tmp_path, ordem):
    server, incrementos = ambiente({"*": [(503, "text/html", b"", {"Retry-After": "3600"})]})
    with Verifica(tmp_path) as svc:
        _obra_com_remissao(svc, 6404, 1976)
        sync = SementeSync(svc, fontes=["planalto"], rate_delay=0)
        anos = {"6404": 1976, "7000": 1980}
        sync.corpus["planalto"] = [{"tipo": "LEI", "numero": n, "ano": anos[n]} for n in ordem]
        sync.corpus["leis_principais_alteradores"] = [{"tipo": "LEI", "numero": "6404", "ano": 1976}]
        sync.state.set("planalto", "LEI:6404:1976", "parseado")
        sync.run()
    l7000 = [p for p in server.pedidos if "l7000" in p[1]]
    assert len(l7000) == 1, server.pedidos
    # 1 incremento para a lei 7000 (Planalto) e 1 para a data no Senado
    assert len(incrementos) == 2


# --- F-11: CVM Colegiado -----------------------------------------------------------------------


def _colegiado(monkeypatch, tmp_path, urls_por_ano):
    def busca(self, q, **filtros):
        url = urls_por_ano[filtros["ano"]]
        return [Candidate(source_id="cvm_colegiado", key=url, title="Reuniao", url=url,
                          metadata={"kind": "ata_colegiado_cvm"})]

    monkeypatch.setattr(CvmColegiadoConnector, "search", busca)
    anos = sorted(urls_por_ano)
    return anos


def test_ata_com_n_itens_e_baixada_uma_vez_e_cada_item_seleciona_o_seu(ambiente, monkeypatch, tmp_path):
    ano = datetime.now().year
    url = f"https://conteudo.cvm.gov.br/decisoes/{ano}/{ano}0105_R1.html"
    # primeiro 200 e depois CAPTCHA, como na reprodução do auditor: só o primeiro GET deve acontecer
    server, incrementos = ambiente({f"/decisoes/{ano}/{ano}0105_R1.html": [(200, "text/html", ATA), (403, "text/html", CAPTCHA)]})
    _colegiado(monkeypatch, tmp_path, {ano: url})
    with Verifica(tmp_path) as svc:
        sync = SementeSync(svc, fontes=["cvm_colegiado"], rate_delay=0)
        sync.corpus["jurisprudencia"] = {"cvm_colegiado_desde": ano}
        sync.run()
        feitos = {r[0] for r in svc.conn.execute(
            "SELECT chave FROM sync_state WHERE fonte='cvm_colegiado_doc' AND status='parseado'")}
        processos = {r[0] for r in svc.conn.execute("SELECT number FROM decision WHERE court='CVM'")}
    assert len(server.pedidos) == 1
    assert len(incrementos) == 0
    assert feitos == {f"{ano}0105-R1#{k}" for k in (1, 2, 3)} or len(feitos) == 3, feitos
    assert {"19957.000001/2024-11", "19957.000002/2024-22", "19957.000003/2024-33"} <= processos


def test_desafio_no_meio_da_lista_nao_gera_pedido_posterior_ao_host(ambiente, monkeypatch, tmp_path):
    ano = datetime.now().year
    u1 = f"https://conteudo.cvm.gov.br/decisoes/{ano - 1}/{ano - 1}0105_R1.html"
    u2 = f"https://conteudo.cvm.gov.br/decisoes/{ano}/{ano}0105_R1.html"
    server, incrementos = ambiente({
        f"/decisoes/{ano - 1}/{ano - 1}0105_R1.html": [(403, "text/html", CAPTCHA)],
        f"/decisoes/{ano}/{ano}0105_R1.html": [(200, "text/html", ATA)],
    })
    _colegiado(monkeypatch, tmp_path, {ano - 1: u1, ano: u2})
    with Verifica(tmp_path) as svc:
        sync = SementeSync(svc, fontes=["cvm_colegiado"], rate_delay=0)
        sync.corpus["jurisprudencia"] = {"cvm_colegiado_desde": ano - 1}
        sync.run()
        pendente = svc.conn.execute(
            "SELECT status, payload_json FROM sync_state WHERE fonte='cvm_colegiado' AND chave=?",
            (f"colegiado:{ano}",),
        ).fetchone()
    assert [p[1] for p in server.pedidos] == [f"/decisoes/{ano - 1}/{ano - 1}0105_R1.html"]  # nada depois do desafio
    assert len(incrementos) == 1
    assert pendente[0] == "indisponivel"
    assert json.loads(pendente[1])["categoria"] == "ambiental_desafio"
