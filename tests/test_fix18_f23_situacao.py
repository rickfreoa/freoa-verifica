"""FIX18 (auditoria r14, F-23): a ressincronização de situação interrompe a fonte e declara a indisponibilidade.

Entrada pública `ressincronizar_situacao` (e a reconstrução com situação), conectores e transporte reais contra
servidor TCP local, duas obras por fonte. Desafio, recusa (403 simples) ou fonte fora (503) na primeira obra: nenhum
pedido para a segunda, retorno `indisponivel`/`parcial` com categoria e evidência, nunca `ok`.
"""

from __future__ import annotations

import re

import pytest

from freoa_verifica.cli import main
from freoa_verifica.service import Verifica
from freoa_verifica.store import repo
from tests.test_fix17_controladores import servidor_que_le_o_corpo
from tests.test_transport import _fast_guards, _wire_local

CAPTCHA = b"<p>CAPTCHA</p>"
RESPOSTAS = {
    "captcha_403": (b"HTTP/1.1 403 Forbidden\r\nContent-Type: text/html; charset=utf-8\r\n", CAPTCHA, "ambiental_desafio"),
    "recusa_403": (b"HTTP/1.1 403 Forbidden\r\nContent-Type: text/html; charset=utf-8\r\n", b"<p>negado</p>",
                   "recusa_identificado"),
    "fora_503": (b"HTTP/1.1 503 X\r\nContent-Type: text/html; charset=utf-8\r\n", b"<p>manutencao</p>", "fonte_fora"),
}
BCB_URL = "https://www.bcb.gov.br/api/conteudo/app/normativos/exibenormativo?p1=Resolu%C3%A7%C3%A3o+CMN&p2={n}"


def _servir(monkeypatch, caso):
    cab, corpo, _ = RESPOSTAS[caso]
    bruto = cab + b"Connection: close\r\nContent-Length: %d\r\n\r\n" % len(corpo) + corpo
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    server, pedidos = servidor_que_le_o_corpo(bruto)
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    return server, pedidos


def _obras(svc, monkeypatch):
    """Duas resoluções CVM e duas do CMN no acervo; a captura BCB de cada uma só fornece a URL relida."""
    bcb = {}
    for n in (1, 2):
        repo.upsert_work(svc.conn, jurisdiction="br", authority="cvm", kind="resolucao", number=str(n), year=2020,
                         label=f"Resolução CVM {n}")
        wid = repo.upsert_work(svc.conn, jurisdiction="br", authority="cmn", kind="resolucao", number=str(n),
                               year=2020, label=f"Resolução CMN {n}")
        bcb[wid] = [{"source_id": "bcb", "url": BCB_URL.format(n=n)}]
    svc.conn.commit()
    monkeypatch.setattr(repo, "captures_for_work", lambda conn, wid: bcb.get(wid, []))


def _caminhos(pedidos) -> list[str]:
    return [re.match(rb"[A-Z]+ (\S+)", p).group(1).decode() for p in pedidos]


@pytest.mark.parametrize("fonte", ["cvm_normas", "bcb"])
@pytest.mark.parametrize("caso", sorted(RESPOSTAS))
def test_ressincronizar_interrompe_a_fonte_e_declara(monkeypatch, tmp_path, caso, fonte):
    server, pedidos = _servir(monkeypatch, caso)
    try:
        with Verifica(tmp_path / "h") as svc:
            _obras(svc, monkeypatch)
            out = svc.ressincronizar_situacao(fontes=(fonte,))
    finally:
        server.shutdown()
    categoria = RESPOSTAS[caso][2]
    assert out["status"] == "indisponivel", out
    assert out["categoria"] == categoria and out["evidencia_indisponibilidade"], out
    assert out["fontes"][fonte]["status"] == "unavailable" and out["fontes"][fonte]["categoria"] == categoria
    assert out["obras"] == 2 and out["nao_consultadas"] == 2 and out["lidas"] == 0, out
    caminhos = _caminhos(pedidos)
    # só a primeira obra chegou à rede (503 pode repetir a MESMA requisição, pela política do transporte)
    assert caminhos and len(set(caminhos)) == 1, caminhos
    assert ("001" in caminhos[0]) if fonte == "cvm_normas" else caminhos[0].endswith("p2=1"), caminhos
    if categoria != "fonte_fora":
        assert len(pedidos) == 1


def test_uma_fonte_interrompida_nao_cala_a_outra(monkeypatch, tmp_path):
    server, pedidos = _servir(monkeypatch, "captcha_403")
    try:
        with Verifica(tmp_path / "h") as svc:
            _obras(svc, monkeypatch)
            out = svc.ressincronizar_situacao()
    finally:
        server.shutdown()
    assert out["status"] == "indisponivel" and set(out["fontes"]) == {"cvm_normas", "bcb"}, out
    assert len(pedidos) == 2  # um por fonte (hosts distintos), nenhum para a segunda obra de cada


def test_item_ausente_nao_interrompe_a_fonte(monkeypatch, tmp_path):
    """404 é do item: segue para a próxima obra e o resultado é `ok` com ilegíveis declaradas."""
    bruto = b"HTTP/1.1 404 Not Found\r\nContent-Type: text/html\r\nConnection: close\r\nContent-Length: 3\r\n\r\nnao"
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    server, pedidos = servidor_que_le_o_corpo(bruto)
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    try:
        with Verifica(tmp_path / "h") as svc:
            _obras(svc, monkeypatch)
            out = svc.ressincronizar_situacao(fontes=("cvm_normas",))
    finally:
        server.shutdown()
    assert out["status"] == "ok" and out["ilegiveis"] == 2 and out["nao_consultadas"] == 0, out
    assert len(set(_caminhos(pedidos))) == 2


def test_reconstrucao_com_situacao_declara_parcial(monkeypatch, tmp_path, capsys):
    server, pedidos = _servir(monkeypatch, "recusa_403")
    try:
        with Verifica(tmp_path / "h") as svc:
            _obras(svc, monkeypatch)
            out = svc.reconstruir_acervo(com_situacao=True)
            assert out["status"] == "parcial", out
            assert out["categoria"] == "recusa_identificado" and out["situacao"]["status"] == "indisponivel"
        with pytest.raises(SystemExit) as ei:
            main(["--home", str(tmp_path / "h"), "acervo", "ressincronizar-situacao", "--json"])
        assert ei.value.code == 1
    finally:
        server.shutdown()
