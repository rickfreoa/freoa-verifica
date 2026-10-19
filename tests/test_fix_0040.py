"""Decisão 0040, correções da auditoria (A1 a A8)."""
import json
import os
import signal
import subprocess
import sys
import textwrap

import pytest

from freoa_verifica import fronteira, registro as reg, trava
from freoa_verifica.service import Verifica

MOTIVO = "HOME_EM_USO_POR_OUTRO_PROCESSO"
LOCAL = ("127.0.0.1", 50000)
CIT = "art. 1 da Lei 6.404/1976"

_FILHO = textwrap.dedent("""
    import sys
    from freoa_verifica.service import Verifica
    svc = Verifica(home=sys.argv[1])
    print("pronto", flush=True)
    sys.stdin.readline()
    svc.close()
""")


@pytest.fixture
def outro_processo():
    """Processo real com o home aberto; encerrado ao sair do teste."""
    procs = []

    def abrir(home):
        p = subprocess.Popen([sys.executable, "-c", _FILHO, str(home)], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, text=True)
        assert p.stdout.readline().strip() == "pronto"
        procs.append(p)
        return p

    yield abrir
    for p in procs:
        if p.poll() is None:
            p.kill()
        p.wait()


def _inode(home):
    return (home / "verifica.sqlite3").stat().st_ino


# -- A1 ------------------------------------------------------------------

def test_a1_troca_de_banco_recusada_com_outro_processo_vivo(tmp_path, outro_processo):
    with Verifica(home=tmp_path, registro="completo") as svc:
        svc.verificar_citacao(CIT)
    filho = outro_processo(tmp_path)
    ino = _inode(tmp_path)
    with Verifica(home=tmp_path) as svc:
        for out in (svc.purgar_execucoes("2999-01-01"),
                    svc.purgar_execucoes("2999-01-01", apagar_original=True),
                    svc.reconstruir_acervo(),
                    svc.snapshot_install(tmp_path / "inexistente")):
            assert out["status"] == "erro" and out["motivo"] == MOTIVO, out
        assert _inode(tmp_path) == ino and not (tmp_path / "purgados").exists()
        assert svc.conn.execute("SELECT COUNT(*) FROM run").fetchone()[0] == 1
    filho.communicate("\n")  # o outro processo fecha e sai
    with Verifica(home=tmp_path) as svc:
        assert svc.purgar_execucoes("2999-01-01")["status"] == "ok"


def test_a1_processo_morto_nao_prende_o_home(tmp_path, outro_processo):
    filho = outro_processo(tmp_path)
    if os.name == "nt":
        filho.kill()
    else:
        os.kill(filho.pid, signal.SIGKILL)
    filho.wait()
    assert list((tmp_path / trava.PASTA_USO).glob("*"))  # sobrou o arquivo do morto
    with Verifica(home=tmp_path) as svc:
        assert svc.purgar_execucoes("2999-01-01")["status"] == "ok"
        restos = [p for p in (tmp_path / trava.PASTA_USO).glob("*") if not p.name.startswith(f"{os.getpid()}-")]
        assert not restos


def test_a1_mesmo_processo_nao_conta_como_outro(tmp_path):
    with Verifica(home=tmp_path) as a, Verifica(home=tmp_path):
        assert a.purgar_execucoes("2999-01-01")["status"] == "ok"


def test_a1_checkpoint_ocupado_recusa(tmp_path):
    import sqlite3

    with Verifica(home=tmp_path) as svc:
        svc.verificar_citacao(CIT)
    db = str(tmp_path / "verifica.sqlite3")
    leitor = sqlite3.connect(db)
    leitor.execute("BEGIN")
    leitor.execute("SELECT COUNT(*) FROM run").fetchone()
    escritor = sqlite3.connect(db)
    escritor.execute("PRAGMA journal_mode=WAL")
    escritor.execute("INSERT INTO meta(key, value) VALUES ('x','1')")
    escritor.commit()
    ck = sqlite3.connect(db)
    try:
        with pytest.raises(RuntimeError, match="wal_checkpoint_ocupado"):
            reg.checkpoint_truncate(ck)
    finally:
        for c in (ck, leitor, escritor):
            c.close()


# -- A2 ------------------------------------------------------------------

def test_a2_uvicorn_sem_access_log(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    uvicorn = pytest.importorskip("uvicorn")
    from freoa_verifica import mcp_server, rest

    chamadas = []
    monkeypatch.setattr(uvicorn, "run", lambda *a, **kw: chamadas.append(kw))
    monkeypatch.delenv("FV_API_TOKEN", raising=False)
    rest.run_api(home=str(tmp_path / "r"))
    mcp_server.run_server(http=True, home=str(tmp_path / "m"))
    assert len(chamadas) == 2 and all(kw.get("access_log") is False for kw in chamadas)


# -- A3 ------------------------------------------------------------------

def test_a3_origens_normalizadas_e_validadas(tmp_path):
    assert fronteira.origens_permitidas(" HTTPS://Painel.Exemplo.org/ , http://[::1]:8080,") == \
        frozenset({"https://painel.exemplo.org", "http://[::1]:8080"})
    for ruim in ("painel.exemplo.org", "https://x.org/caminho", "https://x.org:99999", "https://", "*", "https://x y"):
        with pytest.raises(ValueError, match="FV_API_ORIGENS"):
            fronteira.origens_permitidas(ruim)
    pytest.importorskip("fastapi")
    from freoa_verifica.rest import create_app

    with pytest.raises(ValueError):
        create_app(home=str(tmp_path), token="t", origens="sem-esquema")


def test_a3_origin_do_cabecalho_comparada_normalizada(tmp_path):
    pytest.importorskip("fastapi")
    from starlette.testclient import TestClient

    from freoa_verifica.rest import create_app

    app = create_app(home=str(tmp_path), token="s3", origens="https://Painel.Exemplo.org/")
    with TestClient(app, client=LOCAL) as c:
        h = {"Authorization": "Bearer s3", "Origin": "HTTPS://PAINEL.exemplo.org"}
        assert c.get("/v1/fontes", headers=h).status_code == 200


# -- A4 ------------------------------------------------------------------

def test_a4_token_nao_ascii_da_401_no_rest_e_no_mcp(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("mcp")
    from starlette.testclient import TestClient

    from freoa_verifica import mcp_server as ms
    from freoa_verifica.rest import create_app

    ruim = {"Authorization": b"Bearer t\xf3ken\xff"}
    with TestClient(create_app(home=str(tmp_path / "r"), token="s3"), client=LOCAL) as c:
        assert c.get("/v1/fontes", headers=ruim).status_code == 401
    mcp = ms.create_mcp(home=str(tmp_path / "m"))
    with TestClient(ms.build_http_app(mcp, host="127.0.0.1", token="s3"), client=LOCAL) as c:
        assert c.post("/mcp", json={}, headers=ruim).status_code == 401
    assert fronteira.token_ok("s3", "s3") and not fronteira.token_ok("é", "s3")


# -- A5 ------------------------------------------------------------------

def test_a5_mcp_e_rest_aceitam_os_mesmos_hosts(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("mcp")
    from starlette.testclient import TestClient

    from freoa_verifica import mcp_server as ms
    from freoa_verifica.rest import create_app

    for v in ("FV_API_TOKEN", "FV_MCP_TOKEN", "FV_API_ORIGENS"):
        monkeypatch.delenv(v, raising=False)
    rest = create_app(home=str(tmp_path / "r"))
    for host in ("LOCALHOST:8000", "localhost", "127.0.0.1", "[::1]:9", "evil.com", "localhost.evil.com", "localhost:99999"):
        with TestClient(rest, client=LOCAL, base_url="http://127.0.0.1") as c:
            r_ok = c.get("/v1/fontes", headers={"Host": host}).status_code != 403
        mcp_app = ms.build_http_app(ms.create_mcp(home=str(tmp_path / "m")), host="127.0.0.1", token=None)
        with TestClient(mcp_app, client=LOCAL, base_url="http://127.0.0.1") as c:  # sessão do SDK roda uma vez por app
            m_ok = c.post("/mcp", json={}, headers={"Host": host}).status_code not in (403, 421)
        assert r_ok == m_ok == fronteira.host_local(host), host


# -- A6 ------------------------------------------------------------------

def test_a6_chave_em_cache_e_sem_temporario_residual(tmp_path):
    k = reg.chave_do_home(tmp_path)
    assert reg._cache_chaves[str(tmp_path / "registro.key")][0] == k
    assert reg.chave_do_home(tmp_path) == k
    assert not list(tmp_path.glob("registro.key.*"))  # temporário removido


def test_a6_criacao_concorrente_converge_na_mesma_chave(tmp_path):
    codigo = ("import sys;from pathlib import Path;from freoa_verifica import registro as r;"
              "print(r.chave_do_home(Path(sys.argv[1])).hex())")
    ps = [subprocess.Popen([sys.executable, "-c", codigo, str(tmp_path)], stdout=subprocess.PIPE, text=True)
          for _ in range(6)]
    saidas = {p.communicate()[0].strip() for p in ps}
    assert len(saidas) == 1 and len(next(iter(saidas))) == 64
    assert (tmp_path / "registro.key").read_bytes().hex() in saidas


def test_a6_chave_apagada_com_historico_nao_e_regenerada(tmp_path):
    with Verifica(home=tmp_path) as svc:
        svc.verificar_citacao(CIT)
        imp = svc.conn.execute("SELECT value FROM meta WHERE key=?", (reg.META_IMPRESSAO,)).fetchone()[0]
        assert imp == reg._impressao((tmp_path / "registro.key").read_bytes())
    (tmp_path / "registro.key").unlink()
    with Verifica(home=tmp_path) as svc:
        with pytest.raises(RuntimeError, match="CHAVE_REGISTRO_AUSENTE"):
            svc.verificar_citacao("art. 2 da Lei 6.404/1976")
    assert not (tmp_path / "registro.key").exists()


def test_a6_chave_apagada_com_run_hmac1_sem_meta_tambem_recusa(tmp_path):
    with Verifica(home=tmp_path) as svc:
        svc.verificar_citacao(CIT)
        svc.conn.execute("DELETE FROM meta WHERE key=?", (reg.META_IMPRESSAO,))
        svc.conn.commit()
    (tmp_path / "registro.key").unlink()
    with Verifica(home=tmp_path) as svc, pytest.raises(RuntimeError, match="CHAVE_REGISTRO_AUSENTE"):
        svc.verificar_citacao("art. 2 da Lei 6.404/1976")


# -- A7 ------------------------------------------------------------------

def test_a7_registro_gravado_antes_de_apagar_e_falha_nao_levanta(tmp_path, monkeypatch):
    from pathlib import Path

    with Verifica(home=tmp_path, registro="completo") as svc:
        svc.verificar_citacao(CIT)
    visto = {}
    original = Path.unlink

    def unlink(self, *a, **kw):
        if self.name.startswith("verifica.sqlite3") and "purgados" in str(self):
            visto["jsonl_antes"] = (tmp_path / "purgas.jsonl").read_text()
            raise PermissionError("travado")
        return original(self, *a, **kw)

    monkeypatch.setattr(Path, "unlink", unlink)
    with Verifica(home=tmp_path) as svc:
        out = svc.purgar_execucoes("2999-01-01", apagar_original=True)
    assert out["status"] == "ok" and out["falhas"] and out["apagados"] == []
    assert out["original_apagado"] is False and out["apagar_manualmente"]
    assert json.loads(visto["jsonl_antes"].splitlines()[-1])["apagar_original_pedido"] is True
    linhas = [json.loads(x) for x in (tmp_path / "purgas.jsonl").read_text().splitlines()]
    assert linhas[-1]["evento"] == "original_apagado" and linhas[-1]["falhas"]


# -- A8 ------------------------------------------------------------------

def test_a8_encaminhamento_em_qualquer_caixa_recusado_no_rest_e_no_mcp(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("mcp")
    from starlette.testclient import TestClient

    from freoa_verifica import mcp_server as ms
    from freoa_verifica.rest import create_app

    monkeypatch.delenv("FV_API_TOKEN", raising=False)
    monkeypatch.delenv("FV_MCP_TOKEN", raising=False)
    assert fronteira.validar([(b"X-Forwarded-For", b"1.2.3.4"), (b"host", b"127.0.0.1")], com_token=False)
    assert fronteira.validar([(b"FORWARDED", b"for=1.2.3.4"), (b"host", b"127.0.0.1")], com_token=False)
    assert fronteira.validar([(b"X-Forwarded-For", b"1.2.3.4")], com_token=True) is None  # só vale sem token
    rest = create_app(home=str(tmp_path / "r"))
    with TestClient(rest, client=LOCAL, base_url="http://127.0.0.1") as c:
        assert c.get("/v1/fontes", headers={"X-FORWARDED-FOR": "1.2.3.4"}).status_code == 401
        assert c.get("/v1/fontes").status_code == 200
    mcp_app = ms.build_http_app(ms.create_mcp(home=str(tmp_path / "m")), host="127.0.0.1", token=None)
    with TestClient(mcp_app, client=LOCAL, base_url="http://127.0.0.1") as c:
        assert c.post("/mcp", json={}, headers={"Forwarded": "for=1.2.3.4"}).status_code == 403
