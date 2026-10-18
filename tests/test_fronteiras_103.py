"""1.0.3 F-E: fronteiras remotas, limites, âncora, conexões, registro e acervo."""

from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path

import pytest

from freoa_verifica import acervo
from freoa_verifica.limites import EntradaInvalida, Sobrecarga
from freoa_verifica.service import Verifica
from freoa_verifica.textcmp import compare

LOCAL = ("127.0.0.1", 50000)
ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- F01

def _client(app, **kw):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    return TestClient(app, **kw)


def test_f01_fabrica_asgi_sem_token_recusa_origem_nao_local(tmp_path, monkeypatch):
    from freoa_verifica.rest import create_app

    monkeypatch.delenv("FV_API_TOKEN", raising=False)
    app = create_app(home=str(tmp_path))
    with _client(app) as anon:  # cliente "testclient": não é loopback
        assert anon.get("/v1/fontes").status_code == 401
        assert anon.get("/v1/rota-inexistente").status_code == 401
    with _client(app, client=LOCAL) as local:
        assert local.get("/v1/fontes").status_code == 200
        # loopback atrás de proxy não vale como origem local
        assert local.get("/v1/fontes", headers={"X-Forwarded-For": "8.8.8.8"}).status_code == 401


def test_f01_modo_remoto_exige_token(tmp_path, monkeypatch):
    from freoa_verifica.rest import create_app

    monkeypatch.delenv("FV_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="token"):
        create_app(home=str(tmp_path), modo="remoto")
    app = create_app(home=str(tmp_path), modo="remoto", token="s3")
    with _client(app, client=LOCAL) as c:
        assert c.get("/v1/fontes").status_code == 401
        assert c.get("/v1/fontes", headers={"Authorization": "Bearer errado"}).status_code == 401
        assert c.get("/v1/fontes", headers={"Authorization": "Bearer s3"}).status_code == 200


def test_f01_mcp_http_host_remoto_exige_token(tmp_path, monkeypatch):
    pytest.importorskip("mcp")
    from starlette.testclient import TestClient

    from freoa_verifica import mcp_server as ms

    monkeypatch.delenv("FV_MCP_TOKEN", raising=False)
    mcp = ms.create_mcp(home=str(tmp_path))
    with pytest.raises(RuntimeError, match="token"):
        ms.build_http_app(mcp, host="0.0.0.0", token=None)
    with pytest.raises(RuntimeError, match="token"):
        ms.run_server(http=True, host="0.0.0.0", home=str(tmp_path))
    app = ms.build_http_app(mcp, host="0.0.0.0", token="s3")
    with TestClient(app, base_url="http://0.0.0.0") as c:
        assert c.post("/mcp", json={}).status_code == 401
        assert c.get("/qualquer").status_code == 401
        assert c.post("/mcp", json={}, headers={"Authorization": "Bearer errado"}).status_code == 401
        assert c.post("/mcp", json={}, headers={"Authorization": "Bearer s3"}).status_code != 401


# ---------------------------------------------------------------- F02

def test_f02_fachada_valida_tipos_e_tetos(tmp_path):
    with Verifica(home=tmp_path) as svc:
        with pytest.raises(EntradaInvalida):
            svc.verificar_citacao("x" * 4001)
        with pytest.raises(EntradaInvalida):
            svc.verificar_citacao("art. 254-A da Lei 6.404/76", trecho="x" * 100_001)
        with pytest.raises(EntradaInvalida):
            svc.verificar_citacao("art. 254-A da Lei 6.404/76", trecho=123)
        with pytest.raises(EntradaInvalida):
            svc.verificar_texto("x" * 100_001)
        with pytest.raises(EntradaInvalida):
            svc.buscar_legislacao("q" * 4001)
        with pytest.raises(EntradaInvalida):
            svc.buscar_legislacao("lei", limite=0)
        with pytest.raises(EntradaInvalida):
            svc.buscar_legislacao("lei", limite=True)
        with pytest.raises(EntradaInvalida):
            svc.pesquisar_jurisprudencia("x", tribunais=["stj"] * 6)


def test_f02_rest_422_413_e_corpo_em_streaming(tmp_path, monkeypatch):
    from freoa_verifica.limites import MAX_CORPO_HTTP
    from freoa_verifica.rest import create_app

    monkeypatch.delenv("FV_API_TOKEN", raising=False)
    app = create_app(home=str(tmp_path))
    with _client(app, client=LOCAL) as c:
        r = c.post("/v1/verificacoes", json={"citacao": "x" * 4001})
        assert r.status_code == 422
        assert c.post("/v1/verificacoes", json={"citacao": 7}).status_code == 422
        assert c.get("/v1/legislacao", params={"q": "lei", "limite": 999}).status_code == 422
        big = b'{"citacao":"' + b"a" * (MAX_CORPO_HTTP + 10) + b'"}'
        r = c.post("/v1/verificacoes", content=big, headers={"Content-Type": "application/json"})
        assert r.status_code == 413
        # sem Content-Length (chunked): a leitura é cortada ao passar do teto
        def chunks():
            for _ in range(8):
                yield b"a" * (MAX_CORPO_HTTP // 4)

        r = c.post("/v1/verificacoes", content=chunks(), headers={"Content-Type": "application/json"})
        assert r.status_code == 413


def test_f02_semaforo_de_operacoes_caras(tmp_path, monkeypatch):
    from freoa_verifica import service

    monkeypatch.setattr(service, "_ESPERA_CONCORRENCIA", 0.2)
    with Verifica(home=tmp_path, max_concorrencia=1) as svc:
        dentro, sair = threading.Event(), threading.Event()

        def segura():
            with svc._operacao(caro=True):
                dentro.set()
                sair.wait(5)

        t = threading.Thread(target=segura)
        t.start()
        dentro.wait(5)
        try:
            with pytest.raises(Sobrecarga):
                svc.verificar_citacao("art. 254-A da Lei 6.404/76")
        finally:
            sair.set()
            t.join()
        assert svc.verificar_citacao("art. 254-A da Lei 6.404/76")  # liberado


# ---------------------------------------------------------------- F05

@pytest.mark.parametrize(
    "oficial, trecho, modo",
    [
        ("é abc", "abc", "literal"),
        ("é́ á õ abc", "abc", "literal"),
        ("Á   Foó — bar ,x", "Foó", "literal"),
        ("Á   Foó — bar ,x", "foó - bar,x", "normalizado"),
        ("á é “Décimo”", "décimo", "normalizado"),
    ],
)
def test_f05_intervalo_recupera_o_trecho(oficial, trecho, modo):
    from freoa_verifica.textcmp import normalize

    r = compare(trecho, oficial, modo)
    assert r.status == "match" and r.start is not None
    assert normalize(oficial[r.start:r.end], modo)[0] == normalize(trecho, modo)[0]


def test_f05_abc_apos_composicao():
    r = compare("abc", "é abc")
    assert "é abc"[r.start:r.end] == "abc"


def test_f05_ancora_recusada_quando_o_mapa_nao_reproduz(monkeypatch):
    from freoa_verifica import textcmp

    monkeypatch.setattr(textcmp, "_map_norm_to_orig", lambda o, m: None)
    r = compare("abc", "é abc")
    assert r.status == "match" and r.start is None and r.end is None
    assert r.ancora_motivo == "mapa_indisponivel"


# ---------------------------------------------------------------- F06

def test_f06_conexoes_por_thread_fecham_sem_erro(tmp_path):
    svc = Verifica(home=tmp_path)

    def usa():
        svc.conn.execute("SELECT 1").fetchone()

    ts = [threading.Thread(target=usa) for _ in range(3)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(svc._all_conns) >= 3
    svc.close()  # fecha conexões de threads já encerradas
    assert svc._all_conns == []


def test_f06_falha_de_fechamento_e_registrada(tmp_path, caplog):
    svc = Verifica(home=tmp_path)
    svc.conn.execute("SELECT 1")

    class Ruim:
        def close(self):
            raise sqlite3.ProgrammingError("boom")

    svc._all_conns.append((Ruim(), threading.current_thread()))
    with caplog.at_level(logging.ERROR, logger="freoa_verifica.service"):
        with pytest.raises(RuntimeError, match="conexoes_nao_fechadas"):
            svc._close_all_conns(strict=True)
    assert "boom" in caplog.text
    assert len(svc._all_conns) == 1  # a conexão com falha não é esquecida
    svc._all_conns.clear()
    svc.close()


def test_f06_troca_de_banco_bloqueada_com_operacao_ativa(tmp_path):
    from freoa_verifica import snapshot

    with Verifica(home=tmp_path) as svc:
        dentro, sair = threading.Event(), threading.Event()

        def ativa():
            with svc._operacao():
                dentro.set()
                sair.wait(5)

        t = threading.Thread(target=ativa)
        t.start()
        dentro.wait(5)
        try:
            with pytest.raises(TimeoutError):
                with svc.exclusivo(timeout=0.2):
                    pass
            assert snapshot.install_snapshot.__doc__  # entrada pública exclusiva
        finally:
            sair.set()
            t.join()
        with svc.exclusivo(timeout=1):  # livre depois
            pass


def test_f06_instalacao_de_snapshot_espera_operacoes(tmp_path, monkeypatch):
    from freoa_verifica import snapshot

    svc = Verifica(home=tmp_path)
    monkeypatch.setattr(type(svc), "exclusivo", lambda self, timeout=60.0: (_ for _ in ()).throw(TimeoutError("operacoes_ativas")))
    assert snapshot.install_snapshot(svc, tmp_path / "x") == {"status": "erro", "motivo": "operacoes_ativas"}
    monkeypatch.undo()
    svc.close()


# ---------------------------------------------------------------- F08

def test_f08_dois_homes_no_mesmo_processo(tmp_path):
    pytest.importorskip("mcp")
    from freoa_verifica import mcp_server as ms

    a, b = tmp_path / "a", tmp_path / "b"
    ms._servicos.clear()
    try:
        ms.create_mcp(home=str(a))
        ms.create_mcp(home=str(b))
        sa, sb = ms._service(str(a)), ms._service(str(b))
        assert sa is not sb
        assert sa.home == a.resolve() and sb.home == b.resolve()
        assert ms._service(str(a)) is sa
    finally:
        for s in ms._servicos.values():
            s.close()
        ms._servicos.clear()


# ---------------------------------------------------------------- C5 / F09

MARCADOR = "ZZMARCADORSINTETICO7731"


def _bytes_do_banco(home: Path) -> bytes:
    return b"".join(p.read_bytes() for p in sorted(home.glob("verifica.sqlite3*")) if p.is_file())


@pytest.mark.parametrize("politica, esperado", [("completo", True), ("sem_conteudo", False)])
def test_c5_marcador_no_arquivo_do_banco(tmp_path, politica, esperado):
    svc = Verifica(home=tmp_path, registro=politica)
    out = svc.verificar_citacao(
        f"art. 254-A da Lei 6.404/76 {MARCADOR}", trecho=f"{MARCADOR} texto qualquer", proposicao=MARCADOR
    )
    run_id = out["run_id"]
    assert run_id
    row = svc.conn.execute("SELECT request_json, result_json FROM run WHERE id=?", (run_id,)).fetchone()
    assert row
    svc.verificar_texto(f"Conforme art. 254-A da Lei 6.404/76, “{MARCADOR}”.")
    svc.conn.commit()
    svc.conn.execute("PRAGMA wal_checkpoint(FULL)")
    svc.close()
    assert (MARCADOR.encode() in _bytes_do_banco(tmp_path)) is esperado


def test_c5_sem_conteudo_projecao_exata(tmp_path):
    import json

    with Verifica(home=tmp_path, registro="sem_conteudo") as svc:
        rid = svc.verificar_citacao("art. 254-A da Lei 6.404/76", trecho="abc")["run_id"]
        req, res = svc.conn.execute("SELECT request_json, result_json FROM run WHERE id=?", (rid,)).fetchone()
    req, res = json.loads(req), json.loads(res)
    assert set(req) == {"registro", "citacao_sha256", "trecho_sha256", "data_sha256", "modo_sha256"}
    assert set(res) == {"registro", "identity", "text", "temporal", "support", "algo_versions"}
    assert all(set(res[d]) == {"status", "reason_code"} for d in ("identity", "text", "temporal", "support"))


def test_c5_registro_via_cli_e_ambiente(tmp_path, monkeypatch):
    from freoa_verifica.cli import main

    monkeypatch.setenv("FV_HOME", str(tmp_path))
    with pytest.raises(SystemExit):
        main(["--sem-registro", "verifica", f"art. 254-A da Lei 6.404/76 {MARCADOR}", "--json"])
    assert MARCADOR.encode() not in _bytes_do_banco(tmp_path)
    monkeypatch.setenv("FV_REGISTRO", "invalido")
    with pytest.raises(ValueError):
        Verifica(home=tmp_path)


def test_c5_purga_preserva_triggers_e_move_original(tmp_path, capsys):
    from freoa_verifica.cli import main

    with Verifica(home=tmp_path) as svc:
        svc.verificar_citacao(f"art. 254-A da Lei 6.404/76 {MARCADOR}")
    with pytest.raises(SystemExit) as e:
        main(["--home", str(tmp_path), "runs", "purgar", "--antes", "2000-01-01", "--json"])
    assert e.value.code == 0  # nada antes de 2000: nada removido
    with Verifica(home=tmp_path) as svc:
        assert svc.conn.execute("SELECT COUNT(*) FROM run").fetchone()[0] == 1
    capsys.readouterr()
    with pytest.raises(SystemExit) as e:
        main(["--home", str(tmp_path), "runs", "purgar", "--antes", "2999-01-01", "--json"])
    assert e.value.code == 0
    assert "purgados" in capsys.readouterr().out
    with Verifica(home=tmp_path) as svc:
        assert svc.conn.execute("SELECT COUNT(*) FROM run").fetchone()[0] == 0
        with pytest.raises(sqlite3.DatabaseError):
            svc.conn.execute("INSERT INTO run(id,request_hash,request_json) VALUES ('x','h','{}')")
            svc.conn.execute("UPDATE run SET request_hash='y' WHERE id='x'")
    assert MARCADOR.encode() not in (tmp_path / "verifica.sqlite3").read_bytes()
    antigos = list((tmp_path / "purgados").rglob("verifica.sqlite3"))
    assert antigos and MARCADOR.encode() in antigos[0].read_bytes()
    assert (tmp_path / "purgas.jsonl").is_file()
    with Verifica(home=tmp_path) as svc:
        assert svc.purgar_execucoes("data-invalida")["status"] == "erro"


# ---------------------------------------------------------------- C7

def test_c7_minimo_embutido_e_manifesto_instalado(tmp_path):
    with Verifica(home=tmp_path) as svc:
        aviso = acervo.status(svc.conn, tmp_path)
        assert aviso["codigo"] == "acervo_incompleto" and aviso["referencia"] == "minimo_embutido"
        # manifesto instalado: mesmas contagens, ids diferentes -> alerta
        svc.conn.execute(
            "INSERT INTO work(id,jurisdiction,authority,kind,number,year) VALUES ('1','br','federal','lei','1',2000)"
        )
        svc.conn.commit()
        assert acervo.status(svc.conn, tmp_path) is None  # mínimo atendido
        acervo.save_installed(tmp_path, {"obras": 1, "decisoes": 0, "obras_ids": ["federal:lei:2/2001"]})
        aviso = acervo.status(svc.conn, tmp_path)
        assert aviso["referencia"] == "snapshot_instalado" and "obras_ausentes_do_manifesto" in aviso["motivos"]
        acervo.save_installed(tmp_path, {"obras": 1, "decisoes": 0, "obras_ids_sha256": "0" * 64})
        assert "obras_ids_divergentes" in acervo.status(svc.conn, tmp_path)["motivos"]
        acervo.save_installed(tmp_path, {"obras": 1, "decisoes": 0, "obras_ids": ["federal:lei:1/2000"]})
        assert acervo.status(svc.conn, tmp_path) is None
        # doctor reporta
        (tmp_path / acervo.MANIFESTO_LOCAL).write_text('{"obras": 5}')
        svc._clear_caches()
        d = svc.doctor(offline=True)
        assert d["acervo_incompleto"] and any(c["nome"] == "acervo" for c in d["verificacoes"])


def test_c7_snapshot_publica_manifesto(verifica_populada, tmp_path):
    import json

    svc, *_ = verifica_populada
    out = tmp_path / "snap"
    svc.snapshot_export(out)
    m = json.loads((out / "MANIFEST.json").read_text(encoding="utf-8"))
    assert m["obras"] == 1 and m["obras_ids"] == ["federal:lei:6404/1976"]
    assert len(m["obras_ids_sha256"]) == 64 and len(m["decisoes_ids_sha256"]) == 64
    assert "derived_version" in m and m["db_sha256"]


def test_c7_servidor_avisa_em_toda_resposta(tmp_path, monkeypatch):
    from freoa_verifica.rest import create_app

    monkeypatch.delenv("FV_API_TOKEN", raising=False)
    app = create_app(home=str(tmp_path))
    with _client(app, client=LOCAL) as c:
        assert c.get("/v1/fontes").json()["acervo_incompleto"]["codigo"] == "acervo_incompleto"


# ---------------------------------------------------------------- F10

def test_f10_release_depende_da_suite_e_nao_substitui_assets():
    if not (ROOT / "pyproject.toml").exists():
        pytest.skip("pacote instalado fora do checkout: os workflows não o acompanham")
    rel = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "workflow_call" in ci
    assert "uses: ./.github/workflows/ci.yml" in rel and "needs: testes" in rel
    assert "--clobber" not in rel
    assert "requirements-lock.txt" in rel


# ---------------------------------------------------------------- purga atômica com recuperação (C5)

def _home_com_execucoes(tmp_path):
    svc = Verifica(home=tmp_path)
    svc.conn.execute("INSERT INTO run(id, request_hash, request_json, created_at) VALUES ('velha','h','{}','2000-01-01 00:00:00')")
    svc.conn.execute("INSERT INTO run(id, request_hash, request_json, created_at) VALUES ('nova','h','{}','2999-01-01 00:00:00')")
    svc.conn.commit()
    return svc


def test_purga_falha_entre_os_renames_e_recuperada_na_abertura(tmp_path, monkeypatch):
    import os
    from freoa_verifica import registro

    svc = _home_com_execucoes(tmp_path)
    db = tmp_path / "verifica.sqlite3"
    real = os.replace

    def falha(src, dst, *a, **k):
        if str(src).endswith("purga-novo"):
            raise OSError("falha injetada entre os renames")
        return real(src, dst, *a, **k)

    monkeypatch.setattr(registro.os, "replace", falha)
    out = svc.purgar_execucoes("2500-01-01")
    monkeypatch.undo()
    assert out["status"] == "erro"
    assert not db.exists() and (tmp_path / "verifica.sqlite3.purga-novo").exists()
    assert list((tmp_path / "purgados").rglob("verifica.sqlite3"))  # o original está guardado
    # a próxima abertura conclui a troca em vez de criar um banco vazio
    with Verifica(home=tmp_path) as novo:
        ids = {r[0] for r in novo.conn.execute("SELECT id FROM run")}
    assert ids == {"nova"} and not (tmp_path / "verifica.sqlite3.purga-novo").exists()


def test_purga_falha_antes_da_troca_deixa_o_original(tmp_path, monkeypatch):
    from freoa_verifica import registro

    svc = _home_com_execucoes(tmp_path)
    monkeypatch.setattr(registro, "_fsync_arquivo", lambda p: (_ for _ in ()).throw(OSError("falha injetada no fsync")))
    assert svc.purgar_execucoes("2500-01-01")["status"] == "erro"
    monkeypatch.undo()
    assert not (tmp_path / "verifica.sqlite3.purga-novo").exists() and not (tmp_path / "purgados").exists()
    assert {r[0] for r in svc.conn.execute("SELECT id FROM run")} == {"velha", "nova"}
    svc.close()


def test_limite_de_concorrencia_so_nas_entradas_de_servidor(tmp_path, monkeypatch):
    """F02: biblioteca e CLI não recusam uso legítimo em processo; REST e MCP limitam."""
    monkeypatch.delenv("FV_MAX_CONCORRENCIA", raising=False)
    with Verifica(home=tmp_path / "lib") as svc:
        assert svc._caro is None
    monkeypatch.setenv("FV_MAX_CONCORRENCIA", "2")
    with Verifica(home=tmp_path / "env") as svc:
        assert svc._caro is not None
    from freoa_verifica.limites import servidor_max_concorrencia
    monkeypatch.delenv("FV_MAX_CONCORRENCIA", raising=False)
    assert servidor_max_concorrencia() == 4


def test_concorrencia_zero_equivale_a_um(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_MAX_CONCORRENCIA", "0")
    with Verifica(home=tmp_path) as svc:
        assert svc._caro is not None and svc._caro.acquire(blocking=False)
        assert not svc._caro.acquire(blocking=False)
        svc._caro.release()
