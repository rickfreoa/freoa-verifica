"""IL.0-R, correção de C8 (parecer `parecer-il0r-final.md`): fronteira do legado fixada na migração do home operacional,
falhas de I/O da chave com resposta controlada e precondições dos modelos sintéticos do diferencial."""

from __future__ import annotations

import json
import pathlib

import pytest

from freoa_verifica import registro
from freoa_verifica.service import Verifica
from freoa_verifica.store.db import connect
from tests.test_il0r import _provisoes_de_inclusao_futura, _registro_novo
from tests.test_il0r_r3 import _banco_da_main


def _inserir_posterior(conn, rid="NOVO-FORJADO"):
    conn.execute(
        "INSERT INTO run(id, created_at, request_hash, request_json, policy_version, result_json) VALUES (?,?,?,?,?,?)",
        (rid, "2026-09-01T00:00:00+00:00", "h", "{}", "1", json.dumps({"temporal": {"status": "verified"}})))
    conn.commit()
    return rid


# ----------------------------------------------------------------------------------------------
# Achado 1: o legado é fixado na migração do home operacional, nunca na primeira verificação
# ----------------------------------------------------------------------------------------------

def test_c8_migracao_do_banco_16_sem_chave_cria_a_chave_e_sela_antes_da_primeira_leitura(tmp_path, monkeypatch):
    legados = _banco_da_main(tmp_path / "verifica.sqlite3", monkeypatch, False)
    assert not (tmp_path / registro.ARQUIVO_CHAVE).exists()
    with Verifica(home=tmp_path) as svc:
        assert (tmp_path / registro.ARQUIVO_CHAVE).exists()  # criada pela migração do home operacional
        assert registro._ancora_ler(svc.conn) is not None
        for rid in legados:  # leitura imediata, sem nenhuma verificação antes
            r = svc.obter_registro(rid)
            assert r["integridade"]["confere"] is None, rid
            assert registro.legado_autenticado(svc.conn, rid)


@pytest.mark.parametrize("politica", ["sem_conteudo", "completo"])
def test_c8_registro_inserido_depois_da_migracao_nao_vira_legado_na_primeira_verificacao(tmp_path, monkeypatch, politica):
    legados = _banco_da_main(tmp_path / "verifica.sqlite3", monkeypatch, False)
    with Verifica(home=tmp_path, registro=politica) as svc:
        forjado = _inserir_posterior(svc.conn)
        assert svc.obter_registro(forjado)["integridade"]["confere"] is False
        _registro_novo(svc)  # primeira verificação do home: não recompõe o legado
        r = svc.obter_registro(forjado)
        assert r["integridade"]["confere"] is False
        assert r["estado"] is None and r["parametros"] is None
        assert not registro.legado_autenticado(svc.conn, forjado)
        for rid in legados:
            assert svc.obter_registro(rid)["integridade"]["confere"] is None


def test_c8_chave_criada_fora_da_migracao_nao_sela_o_legado(tmp_path, monkeypatch):
    """Banco 16 aberto como exportação (sem selo) e depois com chave criada por `chave_do_home`: não recompõe."""
    _banco_da_main(tmp_path / "verifica.sqlite3", monkeypatch, False)
    conn = connect(tmp_path / "verifica.sqlite3")  # não operacional
    registro.chave_do_home(tmp_path, conn)
    assert registro._ancora_ler(conn) is None
    assert not registro.legado_autenticado(conn, "MAIN" + "0" * 22)
    conn.close()


def test_c8_chave_original_desaparecida_falha_fechado_e_nao_e_recriada(tmp_path, monkeypatch):
    legados = _banco_da_main(tmp_path / "verifica.sqlite3", monkeypatch, True)
    with Verifica(home=tmp_path) as svc:
        assert svc.obter_registro(legados[0])["integridade"]["confere"] is None
    chave = tmp_path / registro.ARQUIVO_CHAVE
    chave.unlink()
    registro._cache_chaves.clear()
    with Verifica(home=tmp_path) as svc:
        assert not chave.exists()  # a migração já aplicada não recria
        for rid in legados:
            assert svc.obter_registro(rid)["integridade"]["confere"] is False
        with pytest.raises(RuntimeError, match="CHAVE_REGISTRO_AUSENTE"):
            _registro_novo(svc)
        assert not chave.exists()


def test_c8_home_da_main_com_hmac_e_sem_chave_na_migracao_nao_cria_chave_nem_sela(tmp_path, monkeypatch):
    """Home com histórico `hmac1:` e chave ausente já na migração: falha fechada, sem chave nova."""
    caminho = tmp_path / "verifica.sqlite3"
    legados = _banco_da_main(caminho, monkeypatch, True)
    (tmp_path / registro.ARQUIVO_CHAVE).unlink()
    registro._cache_chaves.clear()
    with Verifica(home=tmp_path) as svc:
        assert not (tmp_path / registro.ARQUIVO_CHAVE).exists()
        assert registro._ancora_ler(svc.conn) is None
        for rid in legados:
            assert svc.obter_registro(rid)["integridade"]["confere"] is False


@pytest.mark.parametrize("nome", ["exportacao.sqlite3", "staging.sqlite3"])
def test_c8_banco_de_exportacao_ou_staging_nao_cria_chave_nem_selo(tmp_path, monkeypatch, nome):
    pasta = tmp_path / "saida"
    pasta.mkdir()
    _banco_da_main(pasta / nome, monkeypatch, False)
    conn = connect(pasta / nome)  # padrão: não operacional (snapshot.py usa assim em exportação e staging)
    assert not (pasta / registro.ARQUIVO_CHAVE).exists()
    assert registro._ancora_ler(conn) is None
    assert conn.execute("SELECT 1 FROM meta WHERE key IN (?,?)", (registro.META_LEGADO, registro.META_LEGADO_MAC)).fetchone() is None
    conn.close()


# ----------------------------------------------------------------------------------------------
# Achado 2: falha de I/O ao ler a chave é integridade não conferida, sem publicar nem escrever
# ----------------------------------------------------------------------------------------------

def _falhar_leitura_da_chave(monkeypatch, exc):
    original = pathlib.Path.read_bytes

    def lendo(self):
        if self.name == registro.ARQUIVO_CHAVE:
            raise exc
        return original(self)

    registro._cache_chaves.clear()
    monkeypatch.setattr(pathlib.Path, "read_bytes", lendo)


FALHAS_DE_IO = [PermissionError(13, "acesso negado"), IsADirectoryError(21, "diretório no lugar do arquivo"),
                OSError(5, "falha de leitura")]
IDS_IO = ["acesso_negado", "diretorio", "falha_leitura"]


def _nao_conferido(r, run_id):
    assert r["status"] == "encontrada" and r["run_id"] == run_id
    assert r["integridade"]["confere"] is False
    for campo in ("parametros", "estado", "evidencias", "fundamento_temporal"):
        assert r[campo] is None, campo


@pytest.mark.parametrize("exc", FALHAS_DE_IO, ids=IDS_IO)
@pytest.mark.parametrize("politica", ["sem_conteudo", "completo"])
def test_c8_falha_de_io_da_chave_devolve_integridade_nao_conferida(verifica_populada, monkeypatch, exc, politica):
    svc, _, _ = verifica_populada
    svc.registro = politica
    rid = _registro_novo(svc)
    assert svc.obter_registro(rid)["integridade"]["confere"] is True
    chave = svc.home / registro.ARQUIVO_CHAVE
    antes = chave.read_bytes()
    _falhar_leitura_da_chave(monkeypatch, exc)
    _nao_conferido(svc.obter_registro(rid), rid)
    _nao_conferido(svc.obter_registro(rid, evidencias=[{"capture_id": "x", "sha256": "y", "url": "z"}],
                                      fundamento_temporal={"x": 1}), rid)
    monkeypatch.undo()
    assert chave.read_bytes() == antes  # nada criado nem substituído
    assert svc.obter_registro(rid)["integridade"]["confere"] is True


# ----------------------------------------------------------------------------------------------
# Achado 3: precondições dos modelos sintéticos do diferencial
# ----------------------------------------------------------------------------------------------

def test_c8_modelos_sinteticos_do_diferencial_tem_os_tipos_corretos():
    provisoes = _provisoes_de_inclusao_futura()
    assert len(provisoes) == 10
    for p in provisoes:
        (red,) = p.redactions
        assert red.text == "t" and red.struck is False and red.order == 0
        assert red.annotations and all(a.kind for a in red.annotations)
        assert red.annotations[0].kind in {"incluido", "redacao_dada"}
