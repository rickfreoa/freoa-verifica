"""Rodada 3 (auditor Codex, parecer sobre fbd1f7e): C5 MCP, C6 atomicidade, F01 MCP, fsync, A7, downgrade, F06, F08, 0031."""

from __future__ import annotations

import asyncio
import os
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from freoa_verifica import derivados
from freoa_verifica import mcp_server as m
from freoa_verifica import registro, service
from freoa_verifica.service import Verifica
from freoa_verifica.store import repo
from tests.test_f_c_negativa_historico_recibo import _doc, _indexar, _prov

ROOT = str(Path(__file__).resolve().parent.parent)


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    for v in ("FV_API_TOKEN", "FV_MCP_TOKEN", "FV_REGISTRO"):
        monkeypatch.delenv(v, raising=False)


def _fechar_mcp(home):
    m._servicos.pop(str(Path(home).resolve())).close()


# ---- 1. C5 MCP: política na reutilização do serviço

def test_mcp_reuso_com_politica_diferente_e_recusado_e_nada_vaza(tmp_path):
    marker = "ZXPRIVATECITATION761994"
    m.create_mcp(home=str(tmp_path), registro="completo")
    try:
        _indexar(m._service(str(tmp_path)), _doc([_prov("art1")]))
        with pytest.raises(ValueError, match="conflito de política"):
            m.create_mcp(home=str(tmp_path), registro="sem_conteudo")
        # reuso sem pedir política explícita segue a do serviço
        server = m.create_mcp(home=str(tmp_path))
        asyncio.run(server.call_tool("verificar_citacao", {"citacao": "art. 1 da Lei 6.404/1976"}))
    finally:
        _fechar_mcp(tmp_path)


def test_mcp_sem_conteudo_nao_persiste_marcador(tmp_path):
    marker = "ZXPRIVATECITATION761995"
    server = m.create_mcp(home=str(tmp_path), registro="sem_conteudo")
    try:
        s = m._service(str(tmp_path))
        _indexar(s, _doc([_prov("art1")]))
        asyncio.run(server.call_tool("verificar_citacao",
                                     {"citacao": "art. 1 da Lei 6.404/1976 " + marker, "trecho": marker}))
        assert s.conn.execute("select count(*) from run").fetchone()[0] > 0
        dados = "".join(str(tuple(r)) for r in s.conn.execute("select request_json,result_json from run"))
        assert marker not in dados
    finally:
        _fechar_mcp(tmp_path)


# ---- 8. F08: um serviço por home sob concorrência

def test_mcp_criacao_concorrente_gera_um_servico(tmp_path, monkeypatch):
    barrier = threading.Barrier(2, timeout=1)
    made, errors = [], []

    def factory(**kw):
        s = Verifica(**kw)
        made.append(s)
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass  # a outra thread está barrada pelo lock: comportamento esperado
        return s

    monkeypatch.setattr(m, "Verifica", factory)

    def get():
        try:
            m._service(str(tmp_path))
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))

    ts = [threading.Thread(target=get) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    try:
        assert not errors and len(made) == 1
    finally:
        m._servicos.pop(str(tmp_path.resolve()), None)
        [s.close() for s in made]


# ---- 3. F01 MCP local

def _init(c):
    return c.post("/mcp", headers={"Content-Type": "application/json",
                                   "Accept": "application/json, text/event-stream"},
                  json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                                   "clientInfo": {"name": "t", "version": "1"}}})


def test_mcp_local_sem_token_recusa_cliente_remoto_e_encaminhado(tmp_path):
    pytest.importorskip("starlette")
    from starlette.testclient import TestClient

    server = m.create_mcp(home=str(tmp_path))
    try:
        app = m.build_http_app(server, host="127.0.0.1", token=None)
        with TestClient(app, client=("203.0.113.7", 1234), base_url="http://127.0.0.1:8765") as c:
            assert _init(c).status_code == 403
        # o gerenciador de sessões HTTP só roda uma vez por servidor
        app = m.build_http_app(m.create_mcp(home=str(tmp_path)), host="127.0.0.1", token=None)
        with TestClient(app, client=("127.0.0.1", 1234), base_url="http://127.0.0.1:8765") as c:
            r = c.post("/mcp", json={}, headers={"X-Forwarded-For": "203.0.113.7"})
            assert r.status_code == 403
            r = c.post("/mcp", json={}, headers={"Forwarded": "for=203.0.113.7"})
            assert r.status_code == 403
    finally:
        _fechar_mcp(tmp_path)


def test_mcp_local_sem_token_aceita_loopback_direto(tmp_path):
    pytest.importorskip("starlette")
    from starlette.testclient import TestClient

    server = m.create_mcp(home=str(tmp_path))
    try:
        app = m.build_http_app(server, host="127.0.0.1", token=None)
        with TestClient(app, client=("127.0.0.1", 1234), base_url="http://127.0.0.1:8765") as c:
            assert _init(c).status_code == 200
    finally:
        _fechar_mcp(tmp_path)


# ---- 2. C6: sincronizar_derivados atômico, com triggers

def _triggers(s):
    return {tuple(r) for r in s.conn.execute("select name,sql from sqlite_master where type='trigger'")}


def _sync_args(s):
    rw = _indexar(s, _doc([_prov("art117"), _prov("art118")]))
    eid = s.conn.execute("select id from extract where capture_id=?", (rw.capture_id,)).fetchone()[0]
    return dict(capture_id=rw.capture_id, work_id=rw.work_id, document=_doc([]), extract_id=eid)


@pytest.mark.parametrize("negar", ["drop2", "delete_redaction"])
def test_sincronizar_derivados_falha_restaura_dados_e_triggers(tmp_path, negar):
    with Verifica(tmp_path) as s:
        args = _sync_args(s)
        antes, dump = _triggers(s), list(s.conn.iterdump())
        assert antes, "o esquema deve ter triggers de imutabilidade"
        dropped = []

        def auth(action, a, b, c, d):
            if negar == "drop2" and action == sqlite3.SQLITE_DROP_TRIGGER:
                dropped.append(a)
                if len(dropped) == 2:
                    return sqlite3.SQLITE_DENY
            if negar == "delete_redaction" and action == sqlite3.SQLITE_DELETE and a == "redaction":
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        s.conn.set_authorizer(auth)
        with pytest.raises(sqlite3.DatabaseError):
            repo.sincronizar_derivados(s.conn, **args)
        s.conn.set_authorizer(None)
        s.conn.rollback()
        assert _triggers(s) == antes
        assert list(s.conn.iterdump()) == dump  # occurrences intactas


def test_sincronizar_derivados_morte_do_processo_mantem_triggers_e_dados(tmp_path):
    with Verifica(tmp_path) as s:
        args = _sync_args(s)
        antes = _triggers(s)
        n_occ = s.conn.execute("select count(*) from occurrence").fetchone()[0]
    child = r'''
import os, sys, sqlite3
sys.path.insert(0, sys.argv[2])
os.environ["FV_OFFLINE"] = "1"
from freoa_verifica.service import Verifica
from freoa_verifica.store import repo
from tests.test_f_c_negativa_historico_recibo import _doc
s = Verifica(sys.argv[1]); c = s.conn
row = c.execute("select capture_id, work_id from parsed_document limit 1").fetchone()
eid = c.execute("select id from extract where capture_id=?", (row[0],)).fetchone()[0]
def auth(action, a, b, c_, d):
    if action == sqlite3.SQLITE_DELETE and a == "redaction": os._exit(72)
    return sqlite3.SQLITE_OK
c.set_authorizer(auth)
repo.sincronizar_derivados(c, capture_id=row[0], work_id=row[1], document=_doc([]), extract_id=eid)
'''
    p = subprocess.run([sys.executable, "-B", "-c", child, str(tmp_path), ROOT], capture_output=True)
    assert p.returncode == 72, p.stderr
    with Verifica(tmp_path) as s:
        assert _triggers(s) == antes
        assert s.conn.execute("select count(*) from occurrence").fetchone()[0] == n_occ


# ---- 4. Windows: fsync em descritor gravável; diretório só em POSIX

def test_fsync_arquivo_abre_gravavel_e_pasta_ignorada_no_windows(tmp_path, monkeypatch):
    f = tmp_path / "x.bin"
    f.write_bytes(b"abc")
    modos = []
    real_fsync = os.fsync

    def fsync_win(fd):  # Windows: EBADF em descritor somente leitura
        import fcntl
        if (fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE) == os.O_RDONLY:
            raise OSError(9, "Bad file descriptor")
        modos.append(fd)
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync_win)
    registro._fsync_arquivo(f)
    assert modos

    def sem_open_de_pasta(*a, **k):
        raise AssertionError("diretório não pode ser aberto no Windows")

    monkeypatch.setattr(registro.os, "name", "nt")
    monkeypatch.setattr(registro.os, "open", sem_open_de_pasta)
    registro._fsync_pasta(tmp_path)


def test_purga_funciona_com_fsync_estrito(tmp_path, monkeypatch):
    real_fsync = os.fsync

    def estrito(fd):
        import fcntl
        if (fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE) == os.O_RDONLY and not os.path.isdir(f"/proc/self/fd/{fd}"):
            raise OSError(9, "Bad file descriptor")
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", estrito)
    with Verifica(tmp_path, registro="sem_conteudo") as s:
        _indexar(s, _doc())
        assert s.purgar_execucoes("2999-01-01")["status"] == "ok"


# ---- 5. A7: candidato ao vivo nunca toca o FTS canônico

def test_candidato_ao_vivo_grava_direto_no_staging_sem_resíduo_canônico(tmp_path):
    from tests.test_fd_busca import _Cvm

    with Verifica(tmp_path) as s:
        c = _Cvm()
        original = s.indexar_obra
        vistos = []

        def espia(**kw):
            r = original(**kw)
            # logo após a indexação (instante em que o processo poderia morrer): canônico vazio
            vistos.append(s.conn.execute("select count(*) from fts_redaction").fetchone()[0])
            vistos.append(s.conn.execute("select count(*) from fts_staging").fetchone()[0])
            return r

        s.indexar_obra = espia
        s._index_candidate_legis(c, c.search("zebrafish")[0])
        assert vistos[0] == 0 and vistos[1] >= 1
        assert s.conn.execute("select count(*) from fts_redaction").fetchone()[0] == 0


# ---- 6. snapshot de derivados antigos nunca rebaixa a versão

def test_snapshot_antigo_nao_rebaixa_derived_version(tmp_path):
    with Verifica(tmp_path / "old") as s:
        _indexar(s, _doc())
        derivados.definir(s.conn, 1)
        s.conn.commit()
        assert s.snapshot_export(tmp_path / "snap")["status"] == "ok"
    with Verifica(tmp_path / "new") as s:
        _indexar(s, _doc())
        assert derivados.versao(s.conn) == derivados.DERIVED_VERSION
        out = s.snapshot_install(tmp_path / "snap")
        assert out["status"] == "ok" and "aviso" in out
        assert derivados.versao(s.conn) == derivados.DERIVED_VERSION
        assert derivados.compativel(s.conn)


# ---- 7. F06: timeout não fecha conexão de operação ativa

def test_close_com_timeout_nao_fecha_conexao_ativa(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "_ESPERA_CLOSE", 0.2)
    s = Verifica(tmp_path)
    entrou, soltar, erros, resultado = threading.Event(), threading.Event(), [], []

    def segura():
        with s._operacao():
            c = s.conn
            c.execute("select 1")
            entrou.set()
            soltar.wait(5)
            try:
                c.execute("select 1")
            except Exception as exc:  # noqa: BLE001
                erros.append(repr(exc))

    t = threading.Thread(target=segura)
    t.start()
    assert entrou.wait(3)
    try:
        with pytest.raises(TimeoutError):
            s.close()
    finally:
        soltar.set()
        t.join()
    assert not erros
    s.close()  # sem operação ativa, fecha normalmente


def test_purga_com_operacao_ativa_aborta_sem_trocar_banco(tmp_path, monkeypatch):
    s = Verifica(tmp_path)
    entrou, soltar = threading.Event(), threading.Event()

    def segura():
        with s._operacao():
            entrou.set()
            soltar.wait(5)

    t = threading.Thread(target=segura)
    t.start()
    assert entrou.wait(3)
    try:
        monkeypatch.setattr(Verifica, "exclusivo", _exclusivo_curto(Verifica.exclusivo))
        out = s.purgar_execucoes("2999-01-01")
        assert out["status"] == "erro"
        assert not (tmp_path / "purgados").exists()
    finally:
        soltar.set()
        t.join()
        s.close()


def _exclusivo_curto(orig):
    def f(self, timeout=0.2):
        return orig(self, timeout=0.2)
    return f


# ---- 9. decisão 0031: obra única precisa vir da fonte oficial, não quarentenada

def test_0031_obra_unica_sem_captura_oficial_continua_provavel(tmp_path):
    with Verifica(tmp_path) as s:
        repo.upsert_work(s.conn, jurisdiction="br", authority="cmn", kind="resolucao", number="4966",
                         year=2021, label="Resolução CMN 4.966/2021")
        out = s.verificar_citacao("Resolução CMN 4.966")
        assert out["citation"]["confidence"] == "provavel"
        assert "numero_unico_no_acervo" not in out["citation"]["flags"]


def test_0031_obra_unica_de_fonte_oficial_promove_com_flag(tmp_path):
    from tests.test_c2_situacao import _bcb_body, _indexar_bcb

    with Verifica(tmp_path) as s:
        _indexar_bcb(s, _bcb_body())
        out = s.verificar_citacao("Resolução CMN 4.966")
        assert out["citation"]["confidence"] == "exata"
        assert "numero_unico_no_acervo" in out["citation"]["flags"]


def test_0031_lei_sem_ano_nao_promove(tmp_path):
    with Verifica(tmp_path) as s:
        _indexar(s, _doc())
        out = s.verificar_citacao("Lei 6.404")
        assert out["citation"]["confidence"] == "provavel"
