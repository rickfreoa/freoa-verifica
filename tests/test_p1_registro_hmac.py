"""Decisão 0040: registro `sem_conteudo` por padrão, com HMAC por home nas entradas."""
import hashlib
import json
import logging
import os
import sqlite3
import tarfile

import pytest

from freoa_verifica import registro as reg
from freoa_verifica.service import Verifica

MARCADOR = "ZZCONFIDENCIALMARCADOR9917"
CITACAO = f"art. 254-A da Lei 6.404/76 {MARCADOR}"


def _todo_texto_do_banco(home) -> list[str]:
    """Todos os valores textuais/BLOB de todas as tabelas (inclusive FTS e sombras)."""
    conn = sqlite3.connect(str(home / "verifica.sqlite3"))
    try:
        out = []
        for (tabela,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            for linha in conn.execute(f'SELECT * FROM "{tabela}"'):
                out.extend(v if isinstance(v, str) else v.decode("latin-1") for v in linha
                           if isinstance(v, (str, bytes)))
        return out
    finally:
        conn.close()


def test_padrao_e_sem_conteudo_e_completo_so_explicito(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_REGISTRO", raising=False)
    assert reg.normalizar(None) == "sem_conteudo"
    with Verifica(home=tmp_path / "a") as svc:
        assert svc.registro == "sem_conteudo"
    monkeypatch.setenv("FV_REGISTRO", "completo")
    assert reg.normalizar(None) == "completo"
    monkeypatch.delenv("FV_REGISTRO")
    with Verifica(home=tmp_path / "b", registro="completo") as svc:
        assert svc.registro == "completo"


def test_consulta_confidencial_com_padrao_nao_aparece_em_nenhuma_tabela(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_REGISTRO", raising=False)
    with Verifica(home=tmp_path) as svc:
        svc.verificar_citacao(CITACAO, trecho=f"{MARCADOR} texto", proposicao=MARCADOR)
        svc.verificar_texto(f"Conforme art. 254-A da Lei 6.404/76, “{MARCADOR}”.")
        svc.conn.commit()
        svc.conn.execute("PRAGMA wal_checkpoint(FULL)")
    assert not [v for v in _todo_texto_do_banco(tmp_path) if MARCADOR in v]
    brutos = b"".join(p.read_bytes() for p in tmp_path.glob("verifica.sqlite3*"))
    assert MARCADOR.encode() not in brutos


def test_controle_negativo_completo_grava_o_texto(tmp_path):
    with Verifica(home=tmp_path, registro="completo") as svc:
        svc.verificar_citacao(CITACAO)
    assert [v for v in _todo_texto_do_banco(tmp_path) if MARCADOR in v]


def test_hashes_de_entrada_sao_hmac_versionado_e_nao_sha256_puro(tmp_path):
    with Verifica(home=tmp_path) as svc:
        rid = svc.verificar_citacao(CITACAO, trecho="abc")["run_id"]
        rh, rj = svc.conn.execute("SELECT request_hash, request_json FROM run WHERE id=?", (rid,)).fetchone()
    req = json.loads(rj)
    assert rh.startswith("hmac1:") and len(rh) == 6 + 64
    puro = {hashlib.sha256(v.encode()).hexdigest() for v in (CITACAO, "abc")}
    for campo in ("citacao", "trecho", "data", "modo"):
        valor = req[f"{campo}_sha256"]
        if valor is not None:
            assert valor.startswith("hmac1:") and valor[6:] not in puro
    assert req["data_sha256"] is None
    puro_req = hashlib.sha256(json.dumps(
        {"citacao": CITACAO, "trecho": "abc", "data": None, "modo": "estrito"}, ensure_ascii=False, sort_keys=True
    ).encode()).hexdigest()
    assert rh[6:] != puro_req


def test_mesma_entrada_em_duas_homes_gera_hashes_diferentes_e_estaveis(tmp_path):
    def request_hash(home):
        with Verifica(home=home) as svc:
            return svc.conn.execute("SELECT request_hash FROM run WHERE id=?",
                                    (svc.verificar_citacao(CITACAO)["run_id"],)).fetchone()[0]
    a1, a2, b = request_hash(tmp_path / "a"), request_hash(tmp_path / "a"), request_hash(tmp_path / "b")
    assert a1 == a2  # mesmo home: estável, permite correlacionar execuções
    assert a1 != b  # outro home: outro segredo


def test_chave_32_bytes_modo_0600_e_nunca_regenerada(tmp_path):
    k1 = reg.chave_do_home(tmp_path)
    caminho = tmp_path / "registro.key"
    assert len(k1) == 32 and caminho.read_bytes() == k1
    if os.name != "nt":  # Windows: ACL herdada do perfil (%LOCALAPPDATA%)
        assert caminho.stat().st_mode & 0o777 == 0o600
    assert reg.chave_do_home(tmp_path) == k1
    caminho.write_bytes(b"curta")
    with pytest.raises(RuntimeError, match="corrompida"):
        reg.chave_do_home(tmp_path)
    assert caminho.read_bytes() == b"curta"


def test_chave_fora_do_snapshot_exportado_e_dos_logs(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    with Verifica(home=tmp_path / "home") as svc:
        svc.verificar_citacao(CITACAO)
        chave = (svc.home / "registro.key").read_bytes()
        destino = tmp_path / "snap"
        assert svc.snapshot_export(destino)["status"] == "ok"
        pacote = tmp_path / "snap.tar.gz"
        assert svc.snapshot_export(pacote)["status"] == "ok"
    arquivos = [p for p in destino.rglob("*") if p.is_file()]
    assert arquivos and not any(p.name == "registro.key" for p in arquivos)
    assert not any(chave in p.read_bytes() or chave.hex().encode() in p.read_bytes() for p in arquivos)
    with tarfile.open(pacote) as tar:
        assert not any("registro.key" in m.name for m in tar.getmembers())
        for m in tar.getmembers():
            f = tar.extractfile(m)
            if f:
                dados = f.read()
                assert chave not in dados and chave.hex().encode() not in dados
    assert chave.hex() not in caplog.text


def test_purgar_apagar_original(tmp_path):
    with Verifica(home=tmp_path, registro="completo") as svc:
        svc.verificar_citacao(CITACAO)
    # sem a opção: original fica em purgados/ para exclusão manual (comportamento existente)
    with Verifica(home=tmp_path) as svc:
        out = svc.purgar_execucoes("2999-01-01")
    assert out["status"] == "ok" and out["removidas"] == 1 and out["original_apagado"] is False
    guardados = [p for p in (tmp_path / "purgados").rglob("verifica.sqlite3")]
    assert len(guardados) == 1 and out["apagar_manualmente"]
    assert MARCADOR.encode() in guardados[0].read_bytes()  # o original ainda guarda o texto completo
    # com a opção: apagado após a troca bem-sucedida
    with Verifica(home=tmp_path, registro="completo") as svc:
        svc.verificar_citacao(CITACAO)
    with Verifica(home=tmp_path) as svc:
        out = svc.purgar_execucoes("2999-01-01", apagar_original=True)
        assert svc.conn.execute("SELECT COUNT(*) FROM run").fetchone()[0] == 0
    assert out["status"] == "ok" and out["original_apagado"] is True and out["apagar_manualmente"] == []
    assert len(list((tmp_path / "purgados").rglob("verifica.sqlite3"))) == 1  # só o da primeira purga
    ultimo = json.loads((tmp_path / "purgas.jsonl").read_text().splitlines()[-1])
    assert ultimo["original_apagado"] is True and ultimo["original_movido_para"] == []


def test_cli_apagar_original_e_flag_registro_completo(tmp_path, monkeypatch):
    from freoa_verifica.cli import build_parser, main

    args = build_parser().parse_args(["runs", "purgar", "--antes", "2999-01-01", "--apagar-original"])
    assert args.apagar_original is True
    monkeypatch.delenv("FV_REGISTRO", raising=False)
    monkeypatch.setenv("FV_HOME", str(tmp_path))
    with pytest.raises(SystemExit):
        main(["--registro-completo", "verifica", CITACAO, "--json"])
    assert [v for v in _todo_texto_do_banco(tmp_path) if MARCADOR in v]
    with pytest.raises(SystemExit) as e:
        main(["--sem-registro", "--registro-completo", "verifica", CITACAO])
    assert e.value.code == 2
