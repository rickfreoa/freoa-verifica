"""0089 (b): cenarios sinteticos offline, sem navegador ou rede."""

from __future__ import annotations

import json
import codecs
from dataclasses import asdict

import pytest

from freoa_verifica import transport as t

from freoa_verifica.assistida import ambiente as a, indicacao as ind

from freoa_verifica.assistida.cdp import AdaptadorCDP

from freoa_verifica.assistida.perfis import PERFIS, resolver_grafo

from freoa_verifica.assistida.persistencia import persistir

from freoa_verifica.assistida.sessao import executar, pagina_inicial, selecionar

from freoa_verifica.cli import build_parser, main

from freoa_verifica.store.db import connect

from tests.assistida_0089_util import (
    sessao as sessao,
    VigiaSintetico,
    captura,
    metadados,
    URL,
    META,
    BIN,
    BODY,
)


def test_selecao_persistencia_e_cobertura(tmp_path, sessao, monkeypatch):
    cs = [captura(META, metadados(), mime="application/json"), captura(BIN, BODY)]
    docs = resolver_grafo(PERFIS["normas_leg"], cs, orcamento=sessao)
    vigia = VigiaSintetico()
    conn = connect(tmp_path / "verifica.sqlite3")
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert selecionar(docs) == set()
    assert (
        persistir(
            conn, tmp_path, PERFIS["normas_leg"], docs, set(), vigia, orcamento=sessao
        )
        == []
    )
    assert conn.execute("SELECT COUNT(*) FROM capture").fetchone()[0] == 0
    assert not (tmp_path / "blobs").exists()
    ids = persistir(
        conn, tmp_path, PERFIS["normas_leg"], docs, {0}, vigia, orcamento=sessao
    )
    row = dict(conn.execute("SELECT * FROM capture WHERE id=?", (ids[0],)).fetchone())
    assert row["modalidade_acesso"] == row["procedencia"] == "sessao_assistida"
    assert (
        json.loads(row["assistida_json"])["vinculo"]["metadados_sha256"]
        == cs[0].resposta.sha256
    )
    assert conn.execute("SELECT COUNT(*) FROM capture").fetchone()[0] == 2
    assert ind.cobertura(conn, "normas_leg")["automatico"]["capturas"] == 0
    assert not conn.execute("SELECT * FROM run").fetchall()
    conn.close()


def test_cli_sem_tty_sem_lancamento(monkeypatch, capsys):
    monkeypatch.setattr(a, "lancar_pipe", lambda *_: pytest.fail("não pode lançar"))
    args = build_parser().parse_args(["sessao", "planalto"])
    assert executar(args) == 2
    assert "EXIGE_TTY" in capsys.readouterr().out
    with pytest.raises(SystemExit) as exc:
        main(["sessao", "planalto"])
    assert exc.value.code == 2


def test_cli_sem_confirmacao(monkeypatch):
    monkeypatch.setattr(
        "freoa_verifica.assistida.sessao.conferir_terminal", lambda: None
    )
    monkeypatch.setattr("builtins.input", lambda _: "não")
    monkeypatch.setattr(a, "lancar_pipe", lambda *_: pytest.fail("não pode lançar"))
    assert executar(build_parser().parse_args(["sessao", "normas_leg"])) == 2


def test_inicio_estatico_escapado(tmp_path):
    pagina_inicial(tmp_path, "planalto", '<script src="x">segredo</script>')
    data = (tmp_path / "inicio.html").read_text(encoding="utf-8")
    assert (
        "default-src 'none'" in data and "<script" not in data and "&lt;script" in data
    )


def test_snapshot_preserva_modalidade(tmp_path, sessao):
    from freoa_verifica.snapshot import _merge_attach
    from freoa_verifica.service import Verifica

    origem, destino = tmp_path / "origem", tmp_path / "destino"
    origem.mkdir()
    destino.mkdir()
    conn = connect(origem / "verifica.sqlite3")
    docs = resolver_grafo(
        PERFIS["normas_leg"],
        [captura(META, metadados(), mime="application/json"), captura(BIN, BODY)],
        orcamento=sessao,
    )
    ids = persistir(
        conn,
        origem,
        PERFIS["normas_leg"],
        docs,
        {0},
        VigiaSintetico(),
        orcamento=sessao,
    )
    conn.close()
    conn = connect(destino / "verifica.sqlite3")
    conn.close()
    _merge_attach(destino / "verifica.sqlite3", origem / "verifica.sqlite3")
    conn = connect(destino / "verifica.sqlite3")
    row = dict(conn.execute("SELECT * FROM capture WHERE id=?", (ids[0],)).fetchone())
    assert (
        row["procedencia"] == "snapshot"
        and row["modalidade_acesso"] == "sessao_assistida"
    )
    assert json.loads(row["assistida_json"])["sessao_id"]
    conn.close()
    # Evidência pública lê só o store, sem qualquer caminho para o adaptador.
    with Verifica(home=origem) as svc:
        out = svc.obter_evidencia(ids[0])
        assert out["proveniencia"]["modalidade_acesso"] == "sessao_assistida"


def test_cabecalhos_assistidos_seguros_ate_snapshot_exportado(tmp_path, sessao, capsys):
    from freoa_verifica.service import Verifica
    from freoa_verifica.snapshot import export_snapshot
    from tests.harness_assistida_0089_cenarios import varrer_artefatos
    from tests.test_transport_assistida_0089 import fluxo, pedido

    segredo = "TOKEN_SECRETO_TERRA_R1"
    bruto = 'Text/HTML; CHARSET="UtF8"'
    body = codecs.BOM_UTF8 + BODY
    with pytest.raises(t.RespostaInvalida) as exc:
        fluxo(
            sessao, body=body, headers={"Content-Type": "text/html; charset=" + segredo}
        )
    assert segredo not in str(exc.value)
    c = fluxo(
        sessao,
        pedido(chave=t.ChaveAssistida("cdp", "aba", "seguro", 0)),
        body=body,
        encoding="GZip",
        headers={
            "Content-Type": bruto,
            **dict.fromkeys(
                ("Date", "Last-Modified", "Retry-After", "ETag", "X-Token", "Server"),
                segredo,
            ),
            "Set-Cookie": "TSabcdef=" + segredo,
            "Content-Disposition": "inline; filename=" + segredo,
            "Cache-Control": "public, extra=" + segredo,
            "Vary": "X-" + segredo,
        },
    )
    assert c.content_encoding == "gzip"
    assert c.resposta.headers["content-type"] == "text/html; charset=utf-8"
    assert segredo not in repr(asdict(c)) and bruto not in repr(asdict(c))
    home, snapshot = tmp_path / "home", tmp_path / "exportado"
    home.mkdir()
    conn = connect(home / "verifica.sqlite3")
    docs = resolver_grafo(PERFIS["planalto"], [c], orcamento=sessao)
    ids = persistir(
        conn, home, PERFIS["planalto"], docs, {0}, VigiaSintetico(), orcamento=sessao
    )
    row = dict(conn.execute("SELECT * FROM capture WHERE id=?", (ids[0],)).fetchone())
    assert row["content_type"] == "text/html; charset=utf-8"
    assert segredo not in json.dumps(row)
    resultado = export_snapshot(conn, home, snapshot, staging_dir=tmp_path / "staging")
    assert resultado["status"] == "ok", resultado
    conn.close()
    with Verifica(home=home) as svc:
        publico = svc.obter_evidencia(ids[0])
        assert publico["status"] == "encontrada"
        assert segredo not in json.dumps(publico)
    exportado = connect(snapshot / "verifica.sqlite3")
    assert (
        exportado.execute("SELECT content_type FROM capture").fetchone()[0]
        == "text/html; charset=utf-8"
    )
    exportado.close()
    varrer_artefatos(tmp_path, [segredo, bruto])
    assert segredo not in capsys.readouterr().out


def test_frescor_sem_verified_por_captura(tmp_path, sessao, monkeypatch):
    from freoa_verifica.service import Verifica

    monkeypatch.setenv("FV_OFFLINE", "1")
    conn = connect(tmp_path / "verifica.sqlite3")
    c = captura(URL, BODY)
    docs = resolver_grafo(PERFIS["planalto"], [c], orcamento=sessao)
    ids = persistir(
        conn,
        tmp_path,
        PERFIS["planalto"],
        docs,
        {0},
        VigiaSintetico(),
        orcamento=sessao,
    )
    conn.close()
    monkeypatch.setattr(
        t, "capturar_assistida", lambda *_: pytest.fail("consulta não inicia captura")
    )
    monkeypatch.setattr(
        AdaptadorCDP, "__init__", lambda *_: pytest.fail("consulta não cria adaptador")
    )
    with Verifica(home=tmp_path) as svc:
        assert svc.obter_evidencia(ids[0])["status"] == "encontrada"
        obtencao = svc.obter_dispositivo("art. 1º da Lei 6.404/1976", data="2020-01-01")
        verif = svc.verificar_texto(
            "Art. 1º da Lei 6.404/1976: Publico.", data="2020-01-01"
        )
        assert '"status": "verified"' not in json.dumps(obtencao)
        assert '"status": "verified"' not in json.dumps(verif)
        assert (
            svc.conn.execute(
                "SELECT fetched_at FROM capture WHERE id=?", (ids[0],)
            ).fetchone()[0]
            == c.resposta.fetched_at
        )
        assert (
            next(f for f in svc.listar_fontes()["fontes"] if f["id"] == "planalto")[
                "cobertura"
            ]["acesso"]["assistido"]["capturas"]
            == 1
        )


def test_exemplar_fora_porta_recusado(sessao):
    c = captura(URL, BODY)
    with pytest.raises(ValueError, match="EXEMPLAR_NAO_ADMITIDO"):
        resolver_grafo(PERFIS["planalto"], [c.resposta], orcamento=sessao)
