"""IL.0-R, rodada 2 (parecer `parecer-il0r-r1.md`): provas por classe dos oito achados que deixaram C4, C5, C6, C8, C11
e C12 sem cumprimento integral. Os mutantes são os do parecer."""

from __future__ import annotations

import json
import sqlite3
import sys
from types import SimpleNamespace

import pytest

from freoa_verifica import registro, situacao
from freoa_verifica.aliases import WorkKey
from freoa_verifica.parsers.model import Annotation, Provision, Redaction
from freoa_verifica.service import Verifica
from freoa_verifica.store.db import connect
from freoa_verifica.verify import SourceUnavailable, verificar
from tests.test_il0r import (  # noqa: F401  (fixtures reutilizadas)
    CITACAO_160,
    _indexar_decisao,
    _registro_novo,
    _resolver_com,
    _sem_triggers,
    _situacao,
    svc160,
)

ART254A = "art. 254-A da Lei 6.404/76"
TRECHO254A = "A alienação, direta ou indireta, do controle de companhia aberta"


def _falha_so_dentro_de(svc, monkeypatch, funcao: str, motivo: str = "EVIDENCIA_CORROMPIDA"):
    """Faz `_authenticate_capture` falhar apenas quando chamado de dentro de `funcao` (a resolução normal segue íntegra)."""
    original = svc._authenticate_capture

    def seletivo(capture_id):
        f = sys._getframe(1)
        while f is not None:
            if f.f_code.co_name == funcao:
                raise SourceUnavailable(motivo)
            f = f.f_back
        return original(capture_id)

    monkeypatch.setattr(svc, "_authenticate_capture", seletivo)


# ----------------------------------------------------------------------------------------------
# 1. C4: normalização no ponto único, em todo estado
# ----------------------------------------------------------------------------------------------

def test_r2_c4_rebaixamento_por_falha_de_autenticacao_zera_a_correspondencia(verifica_populada, monkeypatch):
    svc, _, _ = verifica_populada
    svc.registro = "completo"
    controle = svc.verificar_citacao(ART254A, trecho=TRECHO254A, data="2020-01-01")
    assert controle["identity"]["status"] == "verified" and controle["correspondencia_textual"] is not None
    _falha_so_dentro_de(svc, monkeypatch, "_finalizar")
    out = svc.verificar_citacao(ART254A, trecho=TRECHO254A, data="2020-01-01")
    assert out["identity"]["status"] == "unavailable"
    assert out["correspondencia_textual"] is None and out["fundamento_temporal"] is None
    gravado = json.loads(svc.conn.execute("SELECT result_json FROM run WHERE id=?", (out["run_id"],)).fetchone()[0])
    assert gravado["identity"]["status"] == "unavailable"
    assert gravado["correspondencia_textual"] is None  # o recibo também não preserva a resposta inconsistente


def test_r2_c4_rebaixamento_por_ausencia_de_captura_zera_a_correspondencia(verifica_populada, monkeypatch):
    from freoa_verifica import service as modulo
    from freoa_verifica.verify import Dimension, Evidence, VerificationResult
    from freoa_verifica.citation import parse_one

    svc, _, _ = verifica_populada
    original = modulo.verificar

    def sem_capture_id(*a, **k):
        res = original(*a, **k)
        res.identity = Dimension("verified", "OBRA_E_CAMINHO_OK", [Evidence()])
        assert isinstance(res, VerificationResult) and parse_one(ART254A)
        return res

    monkeypatch.setattr(modulo, "verificar", sem_capture_id)
    out = svc.verificar_citacao(ART254A, trecho=TRECHO254A, data="2020-01-01")
    assert out["identity"]["status"] == "unknown" and out["identity"]["reason_code"] == "SEM_EVIDENCIA_CAPTURADA"
    assert out["correspondencia_textual"] is None


def _estados_de_obter_dispositivo(svc, rw, monkeypatch) -> dict[str, dict]:
    estados: dict[str, dict] = {}
    estados["encontrada"] = svc.obter_dispositivo(citacao=ART254A)
    estados["formato_invalido"] = svc.obter_dispositivo(citacao="xyz")
    estados["requer_conferencia"] = svc.obter_dispositivo(citacao="Lei 6.404, art. 254-A")
    estados["inexistente"] = svc.obter_dispositivo(work_id="inexistente")
    estados["indisponivel"] = svc.obter_dispositivo(citacao="art. 1 da Lei 8.666/93")
    with monkeypatch.context() as m:
        m.setattr(svc, "_resolve", lambda *a, **k: [rw, rw])
        estados["ambigua"] = svc.obter_dispositivo(citacao=ART254A)
    with monkeypatch.context() as m:
        m.setattr(svc, "_resolve", lambda *a, **k: SimpleNamespace(**{**rw.__dict__, "persisted_incomplete": True}) if False
                  else __import__("dataclasses").replace(rw, persisted_incomplete=True))
        estados["unknown"] = svc.obter_dispositivo(citacao=ART254A)
    with monkeypatch.context() as m:
        def falha(self, valor):
            raise SourceUnavailable("EVIDENCIA_CORROMPIDA")
        m.setattr(Verifica, "_authenticate_output", falha)
        estados["unavailable"] = svc.obter_dispositivo(citacao=ART254A)
    return estados


def test_r2_c4_obter_dispositivo_todo_estado_tem_os_dois_campos_nulos(verifica_populada, monkeypatch):
    svc, rw, _ = verifica_populada
    estados = _estados_de_obter_dispositivo(svc, rw, monkeypatch)
    assert set(estados) == {"encontrada", "formato_invalido", "requer_conferencia", "inexistente", "indisponivel",
                            "ambigua", "unknown", "unavailable"}
    for nome, resp in estados.items():
        assert resp["status"] == nome, (nome, resp)
        assert "fundamento_temporal" in resp and resp["fundamento_temporal"] is None, nome
        assert "correspondencia_textual" in resp and resp["correspondencia_textual"] is None, nome


def test_r2_c4_verificar_citacao_todo_estado_tem_os_dois_campos(verifica_populada, monkeypatch):
    svc, _, _ = verifica_populada
    casos = [
        (ART254A, TRECHO254A), ("xyz sem citação", None), ("Lei 6.404, art. 254-A", TRECHO254A),
        ("art. 1 da Lei 8.666/93", None), ("art. 999 da Lei 6.404/76", "x"), ("REsp 9.999.999", None),
    ]
    for cit, trecho in casos:
        for data in (None, "2020-01-01"):
            out = svc.verificar_citacao(cit, trecho=trecho, data=data)
            assert out["fundamento_temporal"] is None, (cit, data)
            assert "correspondencia_textual" in out, (cit, data)
            if out["identity"]["status"] != "verified":
                assert out["correspondencia_textual"] is None, (cit, data)


def test_r2_c4_recusa_pelos_derivados_traz_os_campos_e_o_recibo(verifica_populada, monkeypatch):
    from freoa_verifica import service as modulo

    svc, _, _ = verifica_populada
    antes = svc.conn.execute("SELECT COUNT(*) FROM run").fetchone()[0]
    monkeypatch.setattr(modulo._derivados, "compativel", lambda conn: False)
    od = svc.obter_dispositivo(citacao=ART254A)
    vc = svc.verificar_citacao(ART254A, trecho=TRECHO254A)
    vt = svc.verificar_texto(f"Conforme {ART254A}.")
    for resp in (od, vc):
        assert resp["status"] == "indisponivel" and resp["reason_code"] == "ACERVO_DESATUALIZADO"
        assert resp["fundamento_temporal"] is None and resp["correspondencia_textual"] is None
    for resp in (vc, vt):  # C11 (rodada 3): serviço gravável grava o recibo e devolve o `run_id`
        assert resp["run_id"] and "registro" not in resp
        reg = svc.obter_registro(resp["run_id"])
        assert reg["integridade"]["confere"] is True
        assert reg["estado"]["identity"] == {"status": "unavailable", "reason_code": "ACERVO_DESATUALIZADO"}
    assert svc.conn.execute("SELECT COUNT(*) FROM run").fetchone()[0] == antes + 2


def test_r2_c4_verificar_texto_embutida_e_decisoes_tem_os_campos(verifica_populada):
    svc, _, _ = verifica_populada
    _indexar_decisao(svc, "STJ", "900001")
    out = svc.verificar_texto(f"Nos termos de {ART254A}: \"{TRECHO254A}\"; do REsp 900.001 e de xyz 12.")
    assert out["citacoes"]
    for item in out["citacoes"]:
        assert "fundamento_temporal" in item and item["fundamento_temporal"] is None
        assert "correspondencia_textual" in item
        verif = item["verificacao"]
        if verif is not None:
            assert verif["fundamento_temporal"] is None and "correspondencia_textual" in verif
            if verif["identity"]["status"] != "verified":
                assert verif["correspondencia_textual"] is None


# ----------------------------------------------------------------------------------------------
# 2. C6: evidência da situação cadastral pelo construtor comum, com o recibo da captura
# ----------------------------------------------------------------------------------------------

def _evidencias_da_obra_revogada(svc, rw, data=None):
    cap = svc.conn.execute("SELECT fetched_at FROM capture WHERE id=?", (rw.capture_id,)).fetchone()[0]
    lido_em = "2026-11-04T09:30:00+00:00"
    situacao.gravar(svc.conn, situacao.WorkStatus(
        rw.work_id, "revogada", texto_oficial="Declarada pela página do ato", data_efeito="2025-01-01",
        captura_id=rw.capture_id, sha256=rw.sha256, lido_em=lido_em))
    return cap, lido_em


def _mesmo_capture(evs: list[dict], capture_id: str) -> list[dict]:
    return [e for e in evs if e.get("capture_id") == capture_id]


def test_r2_c6_evidencia_da_situacao_tem_o_mesmo_recibo_da_normativa(svc160):
    svc, rw, doc = svc160
    cap_fetched_at, lido_em = _evidencias_da_obra_revogada(svc, rw)
    assert cap_fetched_at != lido_em
    out = svc.verificar_citacao("art. 1º da Resolução CVM nº 160/2022",
                                trecho=next(r.text for r in doc.provision("art1").redactions if not r.struck))
    assert out["temporal"]["reason_code"] == situacao.REVOGADO_NA_FONTE
    evs = _mesmo_capture(out["identity"]["evidence"] + out["temporal"]["evidence"], rw.capture_id)
    assert len(evs) >= 2  # a normativa e a da situação, ambas do mesmo capture_id
    chaves = ("fetched_at", "captured_at", "acervo_ate", "source_kind", "natureza_texto", "procedencia", "esfera")
    for e in evs:
        assert e["captured_at"] == cap_fetched_at and e["fetched_at"] == cap_fetched_at
        assert e["captured_at"] != lido_em
        assert e["procedencia"] == "captura_direta" and e["source_kind"] == "resolucao_cvm"
        assert e["esfera"] == "federal" and e["natureza_texto"] == "consolidacao_oficial"
    assert {tuple(e[k] for k in chaves) for e in evs} == {tuple(evs[0][k] for k in chaves)}
    # `lido_em` continua sendo informação distinta, na situação da obra
    od = svc.obter_dispositivo(citacao="art. 1º da Resolução CVM nº 160/2022")
    assert od["situacao_obra"]["lido_em"] == lido_em
    assert od["evidencia"]["captured_at"] == cap_fetched_at


def test_r2_c6_evidencia_da_situacao_em_verificar_texto_e_nos_rebaixamentos(svc160):
    svc, rw, doc = svc160
    cap_fetched_at, _ = _evidencias_da_obra_revogada(svc, rw)
    texto = svc.verificar_texto("Conforme o art. 1º da Resolução CVM nº 160/2022.")
    verif = texto["citacoes"][0]["verificacao"]
    for e in _mesmo_capture(verif["identity"]["evidence"] + verif["temporal"]["evidence"], rw.capture_id):
        assert e["captured_at"] == cap_fetched_at and e["procedencia"] == "captura_direta"
        assert e["source_kind"] == "resolucao_cvm" and e["esfera"] == "federal"
    # situação ilegível/desatualizada: o rebaixamento também publica a evidência com o recibo da captura
    situacao.gravar(svc.conn, situacao.WorkStatus(
        rw.work_id, "ilegivel", texto_oficial="campos ausentes", captura_id=rw.capture_id, sha256=rw.sha256,
        lido_em="2026-11-04T09:30:00+00:00"))
    out = svc.verificar_citacao("art. 1º da Resolução CVM nº 160/2022",
                                trecho=next(r.text for r in doc.provision("art1").redactions if not r.struck))
    evs = _mesmo_capture(out["temporal"]["evidence"], rw.capture_id)
    assert evs and all(e["captured_at"] == cap_fetched_at and e["procedencia"] == "captura_direta" for e in evs)


def test_r2_c6_evidencia_da_situacao_preserva_procedencia_sessao_assistida_e_snapshot(svc160):
    svc, rw, _ = svc160
    _evidencias_da_obra_revogada(svc, rw)
    for nome in [r[0] for r in svc.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='capture'")]:
        svc.conn.execute(f'DROP TRIGGER "{nome}"')
    for procedencia in ("sessao_assistida", "snapshot"):
        svc.conn.execute("UPDATE capture SET procedencia=? WHERE id=?", (procedencia, rw.capture_id))
        ws = situacao.carregar(svc.conn, rw, svc.home)
        assert ws.recibo["procedencia"] == procedencia
        assert situacao._evidencia(ws).procedencia == procedencia


@pytest.mark.parametrize("autoridade,tipo,esperado", [
    ("cvm", "resolucao", "resolucao_cvm"), ("bcb", "resolucao", "resolucao_bcb"), ("cmn", "resolucao", "resolucao_cmn"),
    ("bcb", "circular", "circular_bcb"),
])
def test_r2_c6_recibo_da_situacao_para_cvm_bcb_e_cmn(svc160, autoridade, tipo, esperado):
    svc, rw, _ = svc160
    outra = SimpleNamespace(work_key=WorkKey(autoridade, tipo, "1", 2022), capture_id=rw.capture_id, document=rw.document)
    ws = situacao.WorkStatus(rw.work_id, "revogada", captura_id=rw.capture_id, sha256=rw.sha256, url="https://x",
                             lido_em="2026-11-04T09:30:00+00:00")
    recibo = situacao._recibo_da_captura(svc.conn, ws, outra)
    assert recibo["source_kind"] == esperado and recibo["esfera"] == "federal"
    assert recibo["captured_at"] == "2026-10-18T00:00:00Z"
    assert recibo["procedencia"] == "captura_direta"


# ----------------------------------------------------------------------------------------------
# 3. C8: âncora do legado fora do banco; reaplicar a migração não a recria
# ----------------------------------------------------------------------------------------------

def _adulterar_como_legado(conn, rid, *, apagar_selo=True):
    """Mutante do parecer: apaga MAC e colunas novas, adultera o resultado, apaga o selo e a versão 17."""
    _sem_triggers(conn)
    conn.execute(
        "UPDATE run SET registro_mac=NULL, ferramenta=NULL, evidencias_compromissos=NULL, fundamento_compromisso=NULL,"
        " evidencias_claro=NULL, fundamento_claro=NULL, result_json=? WHERE id=?",
        (json.dumps({"temporal": {"status": "verified"}}), rid))
    if apagar_selo:
        conn.execute("DELETE FROM meta WHERE key IN (?,?)", (registro.META_LEGADO, registro.META_LEGADO_MAC))
    conn.execute("DELETE FROM schema_version WHERE version=17")
    conn.commit()


def test_r2_c8_mutante_completo_do_parecer_reaplicar_a_migracao_nao_sela_o_adulterado(verifica_populada):
    from freoa_verifica.store.db import apply_migrations

    svc, _, _ = verifica_populada
    rid = _registro_novo(svc)
    assert svc.obter_registro(rid)["integridade"]["confere"] is True
    _adulterar_como_legado(svc.conn, rid)
    assert svc.obter_registro(rid)["integridade"]["confere"] is False
    apply_migrations(svc.conn)  # reaplica a 017
    assert svc.conn.execute("SELECT 1 FROM schema_version WHERE version=17").fetchone()
    r = svc.obter_registro(rid)
    assert r["integridade"]["confere"] is False
    assert r["estado"] is None  # o conteúdo adulterado não é publicado como se fosse o registro


def test_r2_c8_mutante_completo_em_banco_sem_home(tmp_path):
    from freoa_verifica.store.db import apply_migrations

    conn = connect(":memory:")
    registro.selar_legado(conn)  # nasce com a fronteira estabelecida (sem registros anteriores)
    assert registro._ancora_ler(conn) is not None
    conn.execute(
        "INSERT INTO run(id, created_at, request_hash, request_json, policy_version, result_json, registro_mac)"
        " VALUES ('NOVO0000000000000000000001','2026-11-03T00:00:00+00:00','h','{}','1','{}','hmac1:x')")
    _adulterar_como_legado(conn, "NOVO0000000000000000000001")
    apply_migrations(conn)
    assert not registro.legado_autenticado(conn, "NOVO0000000000000000000001")


def test_r2_c8_ausencia_da_ancora_depois_da_fronteira_falha_fechada(verifica_populada):
    from freoa_verifica.store.db import apply_migrations

    svc, _, _ = verifica_populada
    rid = _registro_novo(svc)
    home = svc.home
    chave = (home / registro.ARQUIVO_CHAVE)
    assert registro._ancora_ler(svc.conn) is not None
    # perde-se a âncora (arquivo da chave só com os 32 bytes) mas o espelho no banco denuncia a fronteira
    chave.write_bytes(chave.read_bytes()[:32])
    registro._cache_chaves.clear()
    assert registro._ancora_ler(svc.conn) is None
    _adulterar_como_legado(svc.conn, rid, apagar_selo=False)
    apply_migrations(svc.conn)
    assert registro.selar_legado(svc.conn) is False
    assert not registro.legado_autenticado(svc.conn, rid)
    assert svc.obter_registro(rid)["integridade"]["confere"] is False


def test_r2_c8_ancora_nao_se_recria_a_partir_de_registro_com_mac(verifica_populada):
    svc, _, _ = verifica_populada
    rid = _registro_novo(svc)
    chave = svc.home / registro.ARQUIVO_CHAVE
    chave.write_bytes(chave.read_bytes()[:32])
    registro._cache_chaves.clear()
    svc.conn.execute("DELETE FROM meta WHERE key IN (?,?)", (registro.META_LEGADO, registro.META_LEGADO_MAC))
    svc.conn.commit()
    # o banco ainda guarda registro com MAC: é indício de fronteira; a âncora não é recomposta
    assert registro.selar_legado(svc.conn) is False
    assert not registro.legado_autenticado(svc.conn, rid)


def test_r2_c8_ancora_forjada_no_arquivo_da_chave_nao_autentica(verifica_populada):
    svc, _, _ = verifica_populada
    rid = _registro_novo(svc)
    chave = svc.home / registro.ARQUIVO_CHAVE
    dados = chave.read_bytes()[:32]
    forjada = json.dumps({"ids": json.dumps([rid]), "mac": "hmac1:" + "0" * 64})
    chave.write_bytes(dados + registro._TAG_ANCORA + forjada.encode())
    registro._cache_chaves.clear()
    assert not registro.legado_autenticado(svc.conn, rid)
    chave.write_bytes(dados + registro._TAG_ANCORA + b"nao-e-json")
    assert not registro.legado_autenticado(svc.conn, rid)


def test_r2_c8_legado_anterior_continua_null_depois_de_reaplicar_a_migracao(tmp_path):
    """Home anterior à 1.4.0a2, com chave e sem âncora: a migração sela UMA vez; reaplicá-la não muda o conjunto."""
    from freoa_verifica.store.db import apply_migrations

    caminho = tmp_path / "verifica.sqlite3"
    conn = connect(caminho)
    registro.chave_do_home(tmp_path, conn)
    chave = tmp_path / registro.ARQUIVO_CHAVE
    chave.write_bytes(chave.read_bytes()[:32])  # chave de uma versão anterior: sem âncora
    registro._cache_chaves.clear()
    conn.execute("DELETE FROM meta WHERE key IN (?,?)", (registro.META_LEGADO, registro.META_LEGADO_MAC))
    conn.execute("DELETE FROM schema_version WHERE version=17")
    conn.execute(
        "INSERT INTO run(id, created_at, request_hash, request_json, policy_version, result_json) VALUES (?,?,?,?,?,?)",
        ("LEGADO0000000000000000000B", "2026-01-01T00:00:00+00:00", "h", "{}", "1", "{}"))
    conn.commit()
    apply_migrations(conn)
    assert registro.legado_autenticado(conn, "LEGADO0000000000000000000B")
    conn.execute(
        "INSERT INTO run(id, created_at, request_hash, request_json, policy_version, result_json) VALUES (?,?,?,?,?,?)",
        ("ADULTERADO000000000000000C", "2026-11-03T00:00:00+00:00", "h", "{}", "1", "{}"))
    conn.execute("DELETE FROM schema_version WHERE version=17")
    conn.execute("DELETE FROM meta WHERE key IN (?,?)", (registro.META_LEGADO, registro.META_LEGADO_MAC))
    conn.commit()
    apply_migrations(conn)
    assert registro.legado_autenticado(conn, "LEGADO0000000000000000000B")
    assert not registro.legado_autenticado(conn, "ADULTERADO000000000000000C")
    conn.close()
    assert isinstance(sqlite3.connect(str(caminho)), sqlite3.Connection)


# ----------------------------------------------------------------------------------------------
# 4. C11: recibo para decisões, súmulas e processos dentro de verificar_texto
# ----------------------------------------------------------------------------------------------

def test_r2_c11_decisao_embutida_em_verificar_texto_tem_recibo_recuperavel(verifica_populada):
    svc, _, _ = verifica_populada
    _indexar_decisao(svc, "STJ", "900001")
    out = svc.verificar_texto("Conforme o REsp 900.001.")
    item = out["citacoes"][0]
    assert item["status"] == "encontrada"
    verif = item["verificacao"]
    assert verif is not None and verif["identity"]["status"] == "verified" and verif["run_id"]
    r = svc.obter_registro(verif["run_id"])
    assert r["status"] == "encontrada" and r["integridade"]["confere"] is True
    assert r["estado"]["identity"]["status"] == "verified"
    avulsa = svc.verificar_citacao("REsp 900.001")  # o mesmo resultado que o caminho avulso
    assert avulsa["identity"]["reason_code"] == verif["identity"]["reason_code"]


def test_r2_c11_decisao_e_processo_nao_confirmados_em_texto_tambem_tem_recibo(verifica_populada):
    svc, _, _ = verifica_populada
    out = svc.verificar_texto("Veja o REsp 9.999.999 e o processo 0713166-62.2018.8.07.0000.")
    itens = [i for i in out["citacoes"] if i["kind"] in ("decisao", "processo", "sumula") or i["verificacao"]]
    assert len(itens) >= 2
    for item in itens:
        run_id = item["verificacao"]["run_id"]
        assert run_id, item["citacao"]
        assert svc.obter_registro(run_id)["estado"]["identity"]["status"] == item["verificacao"]["identity"]["status"]


def test_r2_c11_decisao_em_texto_preserva_a_data_de_julgamento_do_contexto(verifica_populada, monkeypatch):
    svc, _, _ = verifica_populada
    _indexar_decisao(svc, "STJ", "900001")  # julgada em 2025-05-05
    com = svc.verificar_texto("O REsp 900.001, julgado em 05/05/2025, afirma.")["citacoes"][0]
    sem = svc.verificar_texto("O REsp 900.001, julgado em 01/01/2020, afirma.")["citacoes"][0]
    assert com["verificacao"]["identity"]["status"] == "verified"
    assert sem["verificacao"]["identity"]["status"] != "verified"  # o contexto usado na confirmação não se perde
    assert sem["verificacao"]["run_id"]


def test_r2_c11_decisao_em_texto_em_home_somente_leitura_declara_a_execucao(verifica_populada, monkeypatch):
    svc, _, _ = verifica_populada
    _indexar_decisao(svc, "STJ", "900001")
    monkeypatch.setattr(svc, "_read_only", True)
    item = svc.verificar_texto("Conforme o REsp 900.001.")["citacoes"][0]
    assert item["verificacao"]["run_id"] is None
    assert item["verificacao"]["registro"] == {"gravado": False, "motivo": "somente_leitura"}


# ----------------------------------------------------------------------------------------------
# 5. obter_registro com campos persistidos inválidos
# ----------------------------------------------------------------------------------------------

_INVALIDOS = [
    ("request_json", "not-json"), ("request_json", "[]"), ("request_json", '"texto"'),
    ("result_json", "not-json"), ("result_json", "[1,2]"), ("result_json", "null"),
    ("result_json", json.dumps({"identity": "x"})), ("result_json", json.dumps({"temporal": [1]})),
    ("evidencias_claro", "not-json"), ("evidencias_claro", "{}"), ("evidencias_claro", "[1]"),
    ("fundamento_claro", "not-json"), ("fundamento_claro", "[]"),
    ("evidencias_compromissos", "not-json"), ("evidencias_compromissos", "{}"), ("evidencias_compromissos", "[1]"),
]


@pytest.mark.parametrize("coluna,valor", _INVALIDOS)
@pytest.mark.parametrize("com_mac", [True, False])
def test_r2_obter_registro_com_campo_invalido_devolve_integridade_invalida(verifica_populada, coluna, valor, com_mac):
    svc, _, _ = verifica_populada
    svc.registro = "completo"
    rid = _registro_novo(svc)
    _sem_triggers(svc.conn)
    sets = f"{coluna}=?" + ("" if com_mac else ", registro_mac=NULL")
    svc.conn.execute(f"UPDATE run SET {sets} WHERE id=?", (valor, rid))
    svc.conn.commit()
    r = svc.obter_registro(rid, evidencias=[{"capture_id": "x", "sha256": "y", "url": "z"}],
                           fundamento_temporal={"a": 1})  # nunca levanta
    assert r["status"] == "encontrada" and r["run_id"] == rid
    assert r["integridade"]["confere"] is False
    assert r["estado"] is None and r["parametros"] is None and r["evidencias"] is None  # nada não autêntico
    assert r["integridade"]["motivo"] in ("ESTRUTURA_INVALIDA", "MAC_NAO_CONFERE")


def test_r2_obter_registro_integro_segue_completo(verifica_populada):
    svc, _, _ = verifica_populada
    svc.registro = "completo"
    rid = _registro_novo(svc)
    r = svc.obter_registro(rid)
    assert r["integridade"] == {"algoritmo": "hmac-sha256", "confere": True}
    assert r["estado"]["identity"]["status"] == "verified" and r["evidencias"]


def test_r2_obter_registro_legado_com_estrutura_invalida_nao_levanta(tmp_path):
    with Verifica(home=tmp_path) as svc:
        svc.conn.execute(
            "INSERT INTO run(id, created_at, request_hash, request_json, policy_version, result_json) VALUES (?,?,?,?,?,?)",
            ("LEGADO0000000000000000000A", "2026-01-01T00:00:00+00:00", "h", "{}", "1", "not-json"))
        svc.conn.commit()
        r = svc.obter_registro("LEGADO0000000000000000000A")
        assert r["integridade"]["confere"] is False and r["integridade"]["motivo"] == "ESTRUTURA_INVALIDA"


# ----------------------------------------------------------------------------------------------
# 6. C6 / 0075 §3.2: natureza_texto pelo documento, não pela autoridade
# ----------------------------------------------------------------------------------------------

def _rw_com(perfil: str, autoridade: str, kind: str = "lei", com_dispositivos: bool = True):
    from freoa_verifica.parsers.model import ParsedDocument

    provs = [Provision(path="art1", label="Art. 1º", scope="", redactions=[Redaction(text="x", struck=False, order=0)])] if com_dispositivos else []
    doc = ParsedDocument(profile=perfil, parser_version="t", title="t", ementa=None, text="", provisions=provs, issues=[])
    return SimpleNamespace(document=doc, work_key=WorkKey(autoridade, kind, "1", 2001))


@pytest.mark.parametrize("perfil,autoridade,esperado", [
    ("planalto", "federal", "consolidacao_oficial"), ("cvm_docx", "cvm", "consolidacao_oficial"),
    ("senado_norma", "federal", "nao_identificado"), ("cvm_html", "cvm", "nao_identificado"),
    ("cvm_pdf", "cvm", "nao_identificado"), ("bcb_json", "bcb", "nao_identificado"),
    ("desconhecido", "federal", "nao_identificado"), ("planalto", "estadual", "consolidacao_oficial"),
])
def test_r2_natureza_texto_vem_do_perfil_do_documento_e_nao_da_autoridade(perfil, autoridade, esperado):
    from freoa_verifica.verify import _inferir_natureza_texto

    assert _inferir_natureza_texto(_rw_com(perfil, autoridade)) == esperado


def test_r2_natureza_texto_sem_texto_parseado_e_nao_identificado():
    from freoa_verifica.verify import _inferir_natureza_texto

    assert _inferir_natureza_texto(_rw_com("planalto", "federal", com_dispositivos=False)) == "nao_identificado"
    assert _inferir_natureza_texto(SimpleNamespace(document=None, work_key=None)) == "nao_identificado"


def test_r2_fixture_real_do_senado_nao_e_consolidacao_oficial(verifica_populada):
    from freoa_verifica.connectors.senado import SenadoConnector
    from tests.fixture_util import load_fixture
    from tests.test_connectors_parse import _resp

    svc, _, _ = verifica_populada
    parsed = SenadoConnector().parse(_resp("senado_lei_10303_2001", "https://legis.senado.leg.br/dadosabertos/legislacao/lista"))
    assert parsed.profile == "senado_norma" and not parsed.provisions
    svc.indexar_obra(
        source_id="senado", work_key=WorkKey("federal", "lei", "10303", 2001), document=parsed,
        body=load_fixture("senado_lei_10303_2001"), url="https://legis.senado.leg.br/dadosabertos/legislacao/lista",
        fetched_at="2026-10-18T00:00:00Z", work_date="2001-10-31", label="Lei nº 10.303/2001")
    out = svc.obter_dispositivo("Lei 10.303/2001")
    assert out["status"] == "encontrada"
    assert out["evidencia"]["natureza_texto"] == "nao_identificado"
    assert out["evidencia"]["source_kind"] == "lei"  # o tipo da obra segue pela chave; a natureza, não


def test_r2_natureza_texto_das_obras_reais_com_parser_consolidado_segue_consolidacao(verifica_populada, svc160):
    svc, _, _ = verifica_populada
    assert svc.obter_dispositivo(citacao=ART254A)["evidencia"]["natureza_texto"] == "consolidacao_oficial"
    svc2, _, _ = svc160
    assert svc2.obter_dispositivo(citacao=CITACAO_160)["evidencia"]["natureza_texto"] == "consolidacao_oficial"


# ----------------------------------------------------------------------------------------------
# 7. C5 no chamável verify.verificar: revogação sem data e outros impedimentos temporais
# ----------------------------------------------------------------------------------------------

def _prov_revogado_sem_data(riscada: bool) -> Provision:
    ann = Annotation(kind="revogado", raw="(Revogado)", act_ref=None, act_date=None)
    red = Redaction(text="Texto de redação antiga do dispositivo revogado sem data.", struck=riscada, order=0, annotations=[ann])
    return Provision(path="art1", label="Art. 1º", scope="", redactions=[red])


@pytest.mark.parametrize("riscada", [True, False])
@pytest.mark.parametrize("data", ["1990-01-01", "2040-01-01"])
def test_r2_c5_revogacao_sem_data_historica_leva_sem_fundamento_ao_texto(monkeypatch, riscada, data):
    monkeypatch.setattr("freoa_verifica.identity.validate_identity", lambda *a, **k: SimpleNamespace(year=1976))
    prov = _prov_revogado_sem_data(riscada)
    res = verificar("art. 1º da Lei 6.404/76", trecho="Texto de redação antiga do dispositivo revogado sem data.",
                    data=data, repo=None, resolver=_resolver_com(prov))
    assert res.temporal.reason_code == "REVOGACAO_SEM_DATA" and res.temporal.status == "unknown"
    assert res.text.status == "unknown"
    assert res.text.reason_code == "sem_fundamento_do_periodo"


def test_r2_c5_revogacao_sem_data_corrente_mantem_o_motivo_de_revogacao(monkeypatch):
    monkeypatch.setattr("freoa_verifica.identity.validate_identity", lambda *a, **k: SimpleNamespace(year=1976))
    prov = _prov_revogado_sem_data(False)
    res = verificar("art. 1º da Lei 6.404/76", trecho="Texto de redação antiga do dispositivo revogado sem data.",
                    repo=None, resolver=_resolver_com(prov))
    assert res.text.reason_code != "sem_fundamento_do_periodo"
    assert "REVOGADO" in (res.text.reason_code or "")


def test_r2_c5_nao_existia_e_data_invalida_conservam_motivo_proprio(monkeypatch):
    monkeypatch.setattr("freoa_verifica.identity.validate_identity", lambda *a, **k: SimpleNamespace(year=1976))
    prov = Provision(path="art1", label="Art. 1º", scope="", redactions=[Redaction(text="texto vigente x", struck=False, order=0)])
    anterior = verificar("art. 1º da Lei 6.404/76", trecho="texto vigente x", data="1970-01-01", repo=None,
                         resolver=_resolver_com(prov))
    assert anterior.temporal.status == "not_found" and anterior.text.reason_code != "sem_fundamento_do_periodo"
    invalida = verificar("art. 1º da Lei 6.404/76", trecho="texto vigente x", data="31/12/1990", repo=None,
                         resolver=_resolver_com(prov))
    assert invalida.text.reason_code != "sem_fundamento_do_periodo"


def test_r2_c5_mutante_dependencia_exclusiva_do_motivo_intermediario(monkeypatch):
    """Mutante do parecer: se o texto voltasse a depender da igualdade do motivo do temporal, a revogação sem data
    (temporal `REVOGACAO_SEM_DATA`) perderia o motivo histórico. A condição histórica prevalece."""
    from freoa_verifica import verify as modulo

    monkeypatch.setattr("freoa_verifica.identity.validate_identity", lambda *a, **k: SimpleNamespace(year=1976))
    chamadas = []
    original = modulo._sem_fundamento_historico
    monkeypatch.setattr(modulo, "_sem_fundamento_historico", lambda tr, d: chamadas.append(tr.reason) or original(tr, d))
    verificar("art. 1º da Lei 6.404/76", trecho="x", data="1990-01-01", repo=None,
              resolver=_resolver_com(_prov_revogado_sem_data(True)))
    assert "REVOGACAO_SEM_DATA" in chamadas
