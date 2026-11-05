"""IL.0-R, rodada 3 (parecer `parecer-il0r-r2.md`): provas por classe dos achados 1, 2, 3 e 5.

Achado 4 (C12, contrato do consumidor) fica em `tests/contrato/test_contrato.py`, que exerce os três adaptadores.
"""

from __future__ import annotations

import gc
import json
import secrets
import sqlite3

import pytest

from freoa_verifica import registro
from freoa_verifica.service import Verifica
from freoa_verifica.store import db as dbmod
from freoa_verifica.store.db import ConexaoFV, connect
from tests.test_il0r import _registro_novo, _sem_triggers

ART254A = "art. 254-A da Lei 6.404/76"
TRECHO254A = "A alienação, direta ou indireta, do controle de companhia aberta"
COLUNAS_LIDAS = ("id", "ferramenta", "created_at", "request_hash", "request_json", "result_json",
                 "evidencias_compromissos", "fundamento_compromisso", "evidencias_claro", "fundamento_claro",
                 "registro_mac")


# ----------------------------------------------------------------------------------------------
# Achado 1: `obter_registro` nunca lança diante de coluna persistida adulterada
# ----------------------------------------------------------------------------------------------

def _invalido(r, run_id):
    assert r["status"] == "encontrada" and r["run_id"] == run_id
    assert r["integridade"]["confere"] is False
    for campo in ("ferramenta", "criado_em", "politica", "parametros", "estado", "evidencias", "fundamento_temporal"):
        assert r[campo] is None, campo


@pytest.mark.parametrize("politica", ["sem_conteudo", "completo"])
@pytest.mark.parametrize("coluna", [c for c in COLUNAS_LIDAS if c != "id"])
@pytest.mark.parametrize("valor", [b"{}", 7, 1.5], ids=["blob", "inteiro", "real"])
def test_a1_tipo_sqlite_inesperado_em_qualquer_coluna_lida_e_resposta_controlada(
        verifica_populada, politica, coluna, valor):
    svc, _, _ = verifica_populada
    svc.registro = politica
    rid = _registro_novo(svc)
    assert svc.obter_registro(rid)["integridade"]["confere"] is True
    _sem_triggers(svc.conn)
    svc.conn.execute(f"UPDATE run SET {coluna}=? WHERE id=?", (valor, rid))
    svc.conn.commit()
    _invalido(svc.obter_registro(rid), rid)


def test_a1_texto_que_nao_e_utf8_e_resposta_controlada(verifica_populada):
    svc, _, _ = verifica_populada
    rid = _registro_novo(svc)
    _sem_triggers(svc.conn)
    svc.conn.execute("UPDATE run SET result_json=CAST(X'FFFE7B7D' AS TEXT) WHERE id=?", (rid,))
    svc.conn.commit()
    _invalido(svc.obter_registro(rid), rid)


def test_a1_registro_legado_com_coluna_blob_tambem_e_controlado(tmp_path):
    with Verifica(home=tmp_path) as svc:
        svc.conn.execute(
            "INSERT INTO run(id, created_at, request_hash, request_json, policy_version, result_json) VALUES (?,?,?,?,?,?)",
            ("LEGADO0000000000000000000A", "2026-01-01T00:00:00+00:00", "h", b"{}", "1", "{}"))
        svc.conn.commit()
        _invalido(svc.obter_registro("LEGADO0000000000000000000A"), "LEGADO0000000000000000000A")


@pytest.mark.parametrize("trailer", [
    b'{"ids": ["x"], "mac": 7}', b'[1,2]', b'"texto"', b'7', b'{"ids": "[[1]]", "mac": "hmac1:\xc3\xa9"}',
    b'{"ids": "[[\\"a\\"]]", "mac": "hmac1:00"}', b'\xff\xfe', b'{"ids": 3, "mac": "m"}',
], ids=lambda b: repr(b)[:24])
def test_a1_ancora_malformada_no_arquivo_da_chave_nunca_lanca(verifica_populada, trailer):
    """Âncora com tipos inesperados, MAC não ASCII ou ids não hasheáveis: `confere: false`, sem exceção."""
    svc, _, _ = verifica_populada
    rid = _registro_novo(svc)
    _sem_triggers(svc.conn)
    svc.conn.execute("UPDATE run SET registro_mac=NULL WHERE id=?", (rid,))
    svc.conn.commit()
    chave = svc.home / registro.ARQUIVO_CHAVE
    chave.write_bytes(chave.read_bytes()[:32] + registro._TAG_ANCORA + trailer)
    registro._cache_chaves.clear()
    assert registro.legado_autenticado(svc.conn, rid) is False
    assert svc.obter_registro(rid)["integridade"]["confere"] is False


def test_a1_registro_integro_continua_integro_nas_duas_politicas(verifica_populada):
    svc, _, _ = verifica_populada
    for politica in ("sem_conteudo", "completo"):
        svc.registro = politica
        rid = _registro_novo(svc)
        r = svc.obter_registro(rid)
        assert r["integridade"]["confere"] is True and r["politica"] == politica
        assert r["estado"]["identity"]["status"] == "verified"


# ----------------------------------------------------------------------------------------------
# Achado 2 (C8): migração consolidada; ponto de partida admitido é o banco da `main`
# ----------------------------------------------------------------------------------------------

def _banco_da_main(caminho, monkeypatch, com_chave: bool):
    """Banco no esquema da `main` (1.4.0a1, versão 16), com registros que a `main` gravou (sem MAC nem colunas novas)."""
    todas = dbmod._migration_files()
    with monkeypatch.context() as m:
        m.setattr(dbmod, "_migration_files", lambda: [x for x in todas if x[0] <= 16])
        conn = connect(caminho)
    assert {r[1] for r in conn.execute("PRAGMA table_info(run)")}.isdisjoint({"registro_mac", "ferramenta"})
    assert max(r[0] for r in conn.execute("SELECT version FROM schema_version")) == 16
    if com_chave:  # a `main` já cria a chave (32 bytes, sem âncora) ao gravar o primeiro registro com HMAC
        chave = secrets.token_bytes(32)
        (caminho.parent / registro.ARQUIVO_CHAVE).write_bytes(chave)
        conn.execute("INSERT INTO meta(key, value) VALUES (?, ?)", (registro.META_IMPRESSAO, registro._impressao(chave)))
    ids = []
    for i in range(3):
        rid = f"MAIN{i:022d}"
        conn.execute(
            "INSERT INTO run(id, created_at, request_hash, request_json, policy_version, result_json) VALUES (?,?,?,?,?,?)",
            (rid, f"2026-0{i + 1}-01T00:00:00+00:00", "hmac1:" + "0" * 64 if com_chave else "h", "{}", "1",
             json.dumps({"identity": {"status": "verified"}, "registro": "sem_conteudo"})))
        ids.append(rid)
    conn.commit()
    conn.close()
    registro._cache_chaves.clear()
    return ids


@pytest.mark.parametrize("com_chave", [True, False], ids=["home_com_chave", "home_sem_chave"])
def test_a2_banco_da_main_migra_e_marca_todos_os_registros_existentes_como_legado(tmp_path, monkeypatch, com_chave):
    caminho = tmp_path / "verifica.sqlite3"
    legados = _banco_da_main(caminho, monkeypatch, com_chave)
    with Verifica(home=tmp_path) as svc:  # abre o banco: aplica a migração 017 única
        assert {r[0] for r in svc.conn.execute("SELECT version FROM schema_version")} == set(range(1, 18))
        assert {"registro_mac", "ferramenta", "evidencias_claro"} <= {r[1] for r in svc.conn.execute("PRAGMA table_info(run)")}
        assert "procedencia" in {r[1] for r in svc.conn.execute("PRAGMA table_info(capture)")}
        novo = svc.verificar_citacao("Lei inventada 99.999/2099")["run_id"]  # cria a chave, se ainda não havia
        assert (tmp_path / registro.ARQUIVO_CHAVE).exists()
        for rid in legados:
            assert svc.obter_registro(rid)["integridade"]["confere"] is None, rid
            assert registro.legado_autenticado(svc.conn, rid)
        # registro criado depois só é aceito com MAC
        assert svc.obter_registro(novo)["integridade"]["confere"] is True
        assert not registro.legado_autenticado(svc.conn, novo)
        _sem_triggers(svc.conn)
        svc.conn.execute("UPDATE run SET registro_mac=NULL WHERE id=?", (novo,))
        svc.conn.commit()
        assert svc.obter_registro(novo)["integridade"]["confere"] is False


@pytest.mark.parametrize("politica", ["sem_conteudo", "completo"])
def test_a2_mutantes_completos_em_banco_migrado_da_main_falham_fechados(tmp_path, monkeypatch, politica):
    """Mutantes dos pareceres r1 e r2: apagar MAC; apagar MAC e colunas novas; adulterar o resultado; apagar o selo
    (espelho no banco) e a versão da migração; reaplicar as migrações. A perda da âncora com o selo no banco é coberta em `test_il0r_r2.py`."""
    from freoa_verifica.store.db import apply_migrations

    legados = _banco_da_main(tmp_path / "verifica.sqlite3", monkeypatch, True)
    with Verifica(home=tmp_path, registro=politica) as svc:
        novo = svc.verificar_citacao("Lei inventada 99.999/2099")["run_id"]
        assert svc.obter_registro(novo)["integridade"]["confere"] is True
        _sem_triggers(svc.conn)
        svc.conn.execute(
            "UPDATE run SET registro_mac=NULL, ferramenta=NULL, evidencias_compromissos=NULL, fundamento_compromisso=NULL,"
            " evidencias_claro=NULL, fundamento_claro=NULL, result_json=? WHERE id=?",
            (json.dumps({"temporal": {"status": "verified"}}), novo))
        svc.conn.execute("DELETE FROM meta WHERE key IN (?,?)", (registro.META_LEGADO, registro.META_LEGADO_MAC))
        svc.conn.execute("DELETE FROM schema_version WHERE version=17")
        svc.conn.commit()
        assert svc.obter_registro(novo)["integridade"]["confere"] is False
        apply_migrations(svc.conn)  # reaplica a 017
        assert svc.obter_registro(novo)["integridade"]["confere"] is False
        assert svc.obter_registro(novo)["estado"] is None
        for rid in legados:  # o legado autêntico segue legado
            assert svc.obter_registro(rid)["integridade"]["confere"] is None


def test_a2_ha_uma_unica_migracao_do_incremento_e_nenhuma_do_ramo_intermediario():
    nomes = [n for n, _ in dbmod._migration_files()]
    assert nomes == list(range(1, 18))
    from importlib import resources
    arquivos = {e.name for e in resources.files("freoa_verifica.store").joinpath("migrations").iterdir()}
    assert {"017_il0r_registro_e_procedencia.py"} <= arquivos
    assert not {"017_registro_conferencia.py", "018_procedencia_captura.py", "019_registro_legado_autenticado.py"} & arquivos


def test_a2_migracao_idempotente_nas_colunas(tmp_path, monkeypatch):
    legados = _banco_da_main(tmp_path / "verifica.sqlite3", monkeypatch, True)
    conn = connect(tmp_path / "verifica.sqlite3")
    conn.execute("DELETE FROM schema_version WHERE version=17")
    conn.commit()
    dbmod.apply_migrations(conn)  # colunas já existem: não falha
    assert all(registro.legado_autenticado(conn, r) for r in legados)
    conn.close()


# ----------------------------------------------------------------------------------------------
# Achado 3 (C11): recusa por derivados incompatíveis grava recibo em modo gravável
# ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("politica", ["sem_conteudo", "completo"])
def test_a3_recusa_em_modo_gravavel_grava_recibo_com_a_politica_de_minimizacao(verifica_populada, monkeypatch, politica):
    from freoa_verifica import service as modulo

    svc, _, _ = verifica_populada
    svc.registro = politica
    monkeypatch.setattr(modulo._derivados, "compativel", lambda conn: False)
    antes = svc.conn.execute("SELECT COUNT(*) FROM run").fetchone()[0]
    vc = svc.verificar_citacao(ART254A, trecho=TRECHO254A, data="2024-01-01")
    vt = svc.verificar_texto(f"Conforme {ART254A}: \"{TRECHO254A}\".")
    assert svc.conn.execute("SELECT COUNT(*) FROM run").fetchone()[0] == antes + 2
    for resp, ferramenta in ((vc, "verificar_citacao"), (vt, "verificar_texto")):
        assert resp["status"] == "indisponivel" and resp["reason_code"] == "ACERVO_DESATUALIZADO"
        assert isinstance(resp["run_id"], str) and "registro" not in resp
        r = svc.obter_registro(resp["run_id"])
        assert r["integridade"]["confere"] is True and r["ferramenta"] == ferramenta and r["politica"] == politica
        assert r["estado"]["identity"] == {"status": "unavailable", "reason_code": "ACERVO_DESATUALIZADO"}
        linha = svc.conn.execute("SELECT request_json FROM run WHERE id=?", (resp["run_id"],)).fetchone()[0]
        if politica == "sem_conteudo":  # minimização: nem a citação nem o texto ficam em claro
            assert "254-A" not in linha and TRECHO254A not in linha
        else:
            assert r["parametros"]["data"] in ("2024-01-01", None)
    assert svc.obter_registro(vc["run_id"])["parametros"] is not None


def test_a3_recusa_nao_depende_dos_derivados_e_demais_operacoes_nao_ganham_recibo(verifica_populada, monkeypatch):
    from freoa_verifica import service as modulo

    svc, _, _ = verifica_populada
    monkeypatch.setattr(modulo._derivados, "compativel", lambda conn: False)
    antes = svc.conn.execute("SELECT COUNT(*) FROM run").fetchone()[0]
    obtencao = svc.obter_dispositivo(citacao=ART254A)
    assert obtencao["status"] == "indisponivel"
    assert svc.obter_registro(obtencao["run_id"])["integridade"]["confere"] is True  # IL.2-c C12
    for resp in (svc.resolver_citacao(ART254A),
                 svc.buscar_legislacao("alienação de controle"), svc.historico_dispositivo(citacao=ART254A)):
        assert resp["status"] == "indisponivel" and "run_id" not in resp  # não concluem verificação
    assert svc.conn.execute("SELECT COUNT(*) FROM run").fetchone()[0] == antes + 1


def test_a3_recusa_em_modo_somente_leitura_declara_o_modo(verifica_populada, monkeypatch):
    from freoa_verifica import service as modulo

    svc, _, _ = verifica_populada
    monkeypatch.setattr(modulo._derivados, "compativel", lambda conn: False)
    monkeypatch.setattr(svc, "_read_only", True)
    antes = svc.conn.execute("SELECT COUNT(*) FROM run").fetchone()[0]
    for resp in (svc.verificar_citacao(ART254A), svc.verificar_texto(f"Conforme {ART254A}.")):
        assert resp["status"] == "indisponivel" and resp["run_id"] is None
        assert resp["registro"] == {"gravado": False, "motivo": "somente_leitura"}
    assert svc.conn.execute("SELECT COUNT(*) FROM run").fetchone()[0] == antes


# ----------------------------------------------------------------------------------------------
# Achado 5: a âncora efêmera não retém conexões nem bancos
# ----------------------------------------------------------------------------------------------

def _conexoes_vivas() -> int:
    gc.collect()
    return sum(1 for o in gc.get_objects() if isinstance(o, ConexaoFV))


def test_a5_conexoes_sem_home_sao_liberadas_com_a_ultima_referencia():
    antes = _conexoes_vivas()
    for _ in range(20):
        conn = connect(":memory:")  # aplica as migrações, que selam o legado vazio na âncora efêmera
        assert registro._ancora_ler(conn) is not None
        del conn
    assert _conexoes_vivas() == antes
    assert not hasattr(registro, "_ancoras_efemeras")


def test_a5_close_remove_o_estado_efemero_e_a_identidade_nao_e_reaproveitada():
    conn = connect(":memory:")
    assert registro._ancora_ler(conn) is not None
    registro.hmac_entrada(conn, "x", "y")
    assert getattr(conn, "_chave_fv", None) is not None
    conn.close()
    assert "_ancora_fv" not in conn.__dict__ and "_chave_fv" not in conn.__dict__
    for _ in range(50):  # nenhuma conexão nova herda âncora de outra, mesmo que o id seja reutilizado
        outra = connect(":memory:")
        assert registro._ancora_ler(outra) == getattr(outra, "_ancora_fv")
        assert not registro.legado_autenticado(outra, "QUALQUER")
        outra.close()


def test_a5_conexao_nao_gerenciada_sem_home_nao_tem_legado():
    """sqlite3 puro, sem home: não há onde guardar a âncora; falha fechada (nenhum registro sem MAC vira legado)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    dbmod.apply_migrations(conn)
    assert registro._ancora_ler(conn) is None
    assert not registro.legado_autenticado(conn, "QUALQUER")
    conn.close()
