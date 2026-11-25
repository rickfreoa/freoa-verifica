"""§3.11–13: cortes finais com capturas SINTÉTICAS admitidas e persistidas.

Gerador de HTML neste módulo; sem fixture real modificada nem rede.
"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from importlib.resources import files
import json

import pytest

from freoa_verifica import transport as t
from freoa_verifica.assistida.perfis import PERFIS, resolver_grafo
from freoa_verifica.assistida.persistencia import persistir
from freoa_verifica.service import Verifica
from tests.assistida_0089_util import URL, VigiaSintetico
from tests.test_transport_assistida_0089 import eventos, pedido


def html_sintetico():
    return """<html><head><meta charset="utf-8"></head><body>
    <p>LEI Nº 6.404, DE 15 DE DEZEMBRO DE 1976</p>
    <p>Dispõe sobre norma exclusivamente sintética.</p>
    <p>Art. 1º Texto atual sintético.</p>
    <p><strike>Art. 2º Texto antigo sintético.</strike></p>
    <p>Art. 2º Texto novo sintético. (Redação dada pela Lei nº 10.000, de 1.1.2000)</p>
    <p>Art. 3º Texto pendente sintético. (Vide Lei nº 10.000, de 1.1.2000)</p>
    </body></html>""".encode()


def admitir_sintetica(body, *, dias=0):
    agora = datetime.now(timezone.utc) - timedelta(days=dias)
    p = replace(pedido(url=URL), wall_time=agora.timestamp())
    with_sessao = t.SessaoPortaAssistida(
        PERFIS["planalto"].porta, navegador="sintetico"
    )
    try:
        porta = t.capturar_assistida(with_sessao, p)
        for ev in eventos(p, body=body):
            porta.observar(ev)
        return porta.admitir()
    finally:
        with_sessao.encerrar()


@pytest.fixture
def assistida_persistida(tmp_path, monkeypatch, request):
    monkeypatch.setenv("FV_OFFLINE", "1")
    dias = getattr(request, "param", 0)
    modelo = (
        files("freoa_verifica").joinpath("data/planalto_cauda_0089.bin").read_bytes()
    )
    c = admitir_sintetica(
        html_sintetico() + modelo.replace(b"<TOKEN>", b"A" * 128), dias=dias
    )
    svc = Verifica(home=tmp_path)
    orcamento = t.SessaoPortaAssistida(PERFIS["planalto"].porta, navegador="sintetico")
    try:
        docs = resolver_grafo(PERFIS["planalto"], [c], orcamento=orcamento)
        ids = persistir(
            svc.conn,
            tmp_path,
            PERFIS["planalto"],
            docs,
            {0},
            VigiaSintetico(),
            orcamento=orcamento,
        )
        assert (
            svc.conn.execute("SELECT count(*) FROM parsed_document").fetchone()[0] == 1
        )
        yield svc, ids[0], c
    finally:
        orcamento.encerrar()
        svc.close()


@pytest.mark.parametrize("assistida_persistida", [0, 31], indirect=True)
@pytest.mark.parametrize(
    "artigo,trecho",
    [
        (1, "Texto atual sintético."),
        (2, "Texto antigo sintético."),
        (2, "Texto novo sintético."),
        (2, "Texto novo sintético adulterado."),
        (3, "Texto pendente sintético."),
    ],
)
def test_item11_0075_historico_nos_dois_caminhos(assistida_persistida, artigo, trecho):
    svc, cid, c = assistida_persistida
    cit = f"art. {artigo}º da Lei 6.404/1976"
    obt = svc.obter_dispositivo(cit, data="2001-01-01")
    out = svc.verificar_texto(f'Conforme o {cit}: "{trecho}".', data="2001-01-01")
    assert obt["status"] == "encontrada"
    assert obt["vigencia"]["status"] == "unknown"
    assert obt["vigencia"]["reason_code"] == "sem_fundamento_do_periodo"
    assert obt["fundamento_temporal"] is None
    assert out["total"] == 1
    v = out["citacoes"][0]["verificacao"]
    assert v["identity"]["status"] == "verified"
    for eixo in ("text", "temporal"):
        assert v[eixo]["status"] == "unknown"
        assert v[eixo]["reason_code"] == "sem_fundamento_do_periodo"
    assert v["fundamento_temporal"] is None
    assert v["correspondencia_textual"]["resultado"] == (
        "diverge" if "adulterado" in trecho else "coincide"
    )
    assert (
        svc.obter_evidencia(cid)["proveniencia"]["modalidade_acesso"]
        == "sessao_assistida"
    )
    assert (
        svc.conn.execute(
            "SELECT fetched_at FROM capture WHERE id=?", (cid,)
        ).fetchone()[0]
        == c.resposta.fetched_at
    )


@pytest.mark.parametrize("assistida_persistida", [0, 30, 31], indirect=True)
def test_item11_trinta_dias_so_consulta_corrente_e_cobertura(assistida_persistida):
    svc, cid, c = assistida_persistida
    idade = (
        datetime.now(timezone.utc).date()
        - datetime.fromisoformat(c.resposta.fetched_at).date()
    ).days
    cit = "art. 1º da Lei 6.404/1976"
    obt = svc.obter_dispositivo(cit)
    v = svc.verificar_texto(f'Conforme o {cit}: "Texto atual sintético.".')["citacoes"][
        0
    ]["verificacao"]
    esperado = "vigente_na_fonte" if idade <= 30 else "unknown"
    assert obt["vigencia"]["status"] == v["temporal"]["status"] == esperado
    assert v["text"]["status"] == "verified"
    pendente = svc.obter_dispositivo("art. 3º da Lei 6.404/1976")
    assert pendente["vigencia"]["status"] == "unknown"
    pendente_texto = svc.verificar_texto(
        'Conforme o art. 3º da Lei 6.404/1976: "Texto pendente sintético.".'
    )["citacoes"][0]["verificacao"]
    assert pendente_texto["temporal"]["status"] == "unknown"
    assert pendente_texto["fundamento_temporal"] is None
    historia = svc.historico_dispositivo("art. 2º da Lei 6.404/1976")
    assert len(historia["linha_do_tempo"]) == 2
    assert all(x["fundamento_temporal"] is None for x in historia["linha_do_tempo"])
    fonte = next(x for x in svc.listar_fontes()["fontes"] if x["id"] == "planalto")
    assert fonte["cobertura"]["acesso"]["assistido"]["capturas"] == 1
    assert fonte["cobertura"]["acesso"]["automatico"]["capturas"] == 0
    assert (
        svc.conn.execute(
            "SELECT fetched_at FROM capture WHERE id=?", (cid,)
        ).fetchone()[0]
        == c.resposta.fetched_at
    )


def test_item11_sem_ancora_ou_confronto_nao_verified(assistida_persistida):
    svc, _, _ = assistida_persistida
    ausente = svc.obter_dispositivo("art. 99º da Lei 6.404/1976")
    assert ausente["status"] != "encontrada"
    sem_trecho = svc.verificar_texto("Conforme o art. 1º da Lei 6.404/1976.")
    assert sem_trecho["total"] == 1
    assert sem_trecho["citacoes"][0]["text"]["status"] == "not_assessed"


def test_item12_exportacao_instalacao_remapeia_vinculos(assistida_persistida, tmp_path):
    from freoa_verifica.snapshot import export_snapshot, install_snapshot

    svc, cid, c = assistida_persistida
    pacote = tmp_path / "snapshot-publico"
    assert export_snapshot(svc.conn, svc.home, pacote)["status"] == "ok"
    with Verifica(home=tmp_path / "instalado") as destino:
        # Mesma chave natural, IDs locais diferentes: não basta instalar em home vazio.
        wid = svc.conn.execute("SELECT id FROM work").fetchone()[0]
        work = dict(svc.conn.execute("SELECT * FROM work").fetchone())
        work["id"] = "work-local"
        destino.conn.execute(
            f"INSERT INTO work({','.join(work)}) VALUES ({','.join('?' for _ in work)})",
            tuple(work.values()),
        )
        provs = svc.conn.execute("SELECT id, scope, path FROM provision").fetchall()
        for i, prov in enumerate(provs):
            destino.conn.execute(
                "INSERT INTO provision(id,work_id,scope,path) VALUES (?,?,?,?)",
                (f"prov-local-{i}", "work-local", prov["scope"], prov["path"]),
            )
        destino.conn.commit()
        assert (
            install_snapshot(destino, pacote, aceitar_nao_vinculado=True)["status"]
            == "ok"
        )
        assert not destino.conn.execute("PRAGMA foreign_key_check").fetchall()
        assert (
            destino.conn.execute(
                "SELECT work_id FROM parsed_document WHERE capture_id=?", (cid,)
            ).fetchone()[0]
            == "work-local"
        )
        assert not destino.conn.execute(
            "SELECT 1 FROM work WHERE id=?", (wid,)
        ).fetchone()
        assert all(
            r[0].startswith("prov-local-")
            for r in destino.conn.execute("SELECT provision_id FROM redaction")
        )
        cap = dict(
            destino.conn.execute("SELECT * FROM capture WHERE id=?", (cid,)).fetchone()
        )
        assert (
            cap["modalidade_acesso"] == "sessao_assistida"
            and cap["procedencia"] == "snapshot"
        )
        assert json.loads(cap["assistida_json"])["sessao_id"] == c.sessao_id
        ev = destino.obter_evidencia(cid)
        assert ev["proveniencia"]["modalidade_acesso"] == "sessao_assistida"
        assert ev["proveniencia"]["procedencia"] == "snapshot"
        assert (
            destino.obter_dispositivo("art. 1º da Lei 6.404/1976")["status"]
            == "encontrada"
        )


def test_item12_snapshot_preserva_dependente_e_hash(tmp_path, monkeypatch):
    from freoa_verifica.snapshot import export_snapshot, install_snapshot
    from tests.assistida_0089_util import META, BIN, BODY, captura, metadados

    monkeypatch.setenv("FV_OFFLINE", "1")
    with Verifica(home=tmp_path / "origem") as origem:
        orcamento = t.SessaoPortaAssistida(
            PERFIS["normas_leg"].porta, navegador="sintetico"
        )
        try:
            cs = [
                captura(META, metadados(), mime="application/json"),
                captura(BIN, BODY),
            ]
            docs = resolver_grafo(PERFIS["normas_leg"], cs, orcamento=orcamento)
            ids = persistir(
                origem.conn,
                origem.home,
                PERFIS["normas_leg"],
                docs,
                {0},
                VigiaSintetico(),
                orcamento=orcamento,
            )
            pacote = tmp_path / "pacote"
            assert export_snapshot(origem.conn, origem.home, pacote)["status"] == "ok"
            with Verifica(home=tmp_path / "destino") as destino:
                assert (
                    install_snapshot(destino, pacote, aceitar_nao_vinculado=True)[
                        "status"
                    ]
                    == "ok"
                )
                assert (
                    destino.conn.execute(
                        "SELECT count(*) FROM capture WHERE procedencia='snapshot' AND modalidade_acesso='sessao_assistida'"
                    ).fetchone()[0]
                    == 2
                )
                row = destino.conn.execute(
                    "SELECT assistida_json FROM capture WHERE id=?", (ids[0],)
                ).fetchone()
                vinculo = json.loads(row[0])["vinculo"]
                dep = destino.conn.execute(
                    "SELECT sha256 FROM capture WHERE id=?",
                    (vinculo["metadados_capture_id"],),
                ).fetchone()
                assert dep[0] == vinculo["metadados_sha256"] == cs[0].resposta.sha256
                assert (
                    destino.obter_evidencia(ids[0])["proveniencia"]["procedencia"]
                    == "snapshot"
                )
        finally:
            orcamento.encerrar()
