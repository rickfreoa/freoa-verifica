"""C6: DERIVED_VERSION, `fv acervo reconstruir` e instalação de snapshot com derivados mais novos."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import replace

import pytest

from freoa_verifica import derivados
from freoa_verifica.aliases import WorkKey
from freoa_verifica.cli import main
from freoa_verifica.parsers.cvm_docx import parse_cvm_docx
from freoa_verifica.parsers.planalto import parse_planalto
from freoa_verifica.service import Verifica
from tests.fixture_util import load_fixture
from tests.test_cf_adct import CF_KEY, T_ADCT5, T_ADCT60, T_CF60, cf_html

CF_URL = "https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm"
CVM_KEY = WorkKey("cvm", "resolucao", "80", 2022)
CVM_URL = "https://conteudo.cvm.gov.br/legislacao/resolucoes/anexos/001/resol080consolid.docx"
CONSULTAS = [
    ("art. 60 da CF", T_CF60),
    ("art. 60 da CF", T_ADCT60),
    ("art. 60 do ADCT", T_ADCT60),
    ("art. 5º do ADCT", T_ADCT5),
]


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")


def _carregar(svc, *, legado: bool):
    body = cf_html().encode("utf-8")
    doc = parse_planalto(body, base_url=CF_URL)
    if legado:
        # Modelo da v1.0.2: o ADCT é engolido pelo texto permanente (sem escopo próprio).
        adct = {p.path.removeprefix("adct/"): p for p in doc.provisions if p.scope == "adct"}
        provs = []
        for p in doc.provisions:
            if p.scope == "adct":
                continue
            if p.path in adct:
                p = replace(p, redactions=adct[p.path].redactions)
            provs.append(p)
        doc = replace(doc, provisions=provs, parser_version="1.2.2")
    svc.indexar_obra(source_id="planalto", work_key=CF_KEY, document=doc, body=body, url=CF_URL,
                     fetched_at="2026-10-18T00:00:00+00:00", work_date=None, label="Constituição Federal")
    cvm = load_fixture("cvm_resol_080_consolid_docx")
    svc.indexar_obra(source_id="cvm_normas", work_key=CVM_KEY, document=parse_cvm_docx(cvm), body=cvm,
                     url=CVM_URL, fetched_at="2026-10-18T00:00:00+00:00", work_date="2022-03-29",
                     label="Resolução CVM 80")


def _respostas(svc):
    out = []
    for cit, trecho in CONSULTAS:
        r = svc.verificar_citacao(cit, trecho=trecho)
        out.append((cit, trecho[:20], *(( r[d]["status"], r[d]["reason_code"]) for d in ("identity", "text", "temporal"))))
    return out


def _home_legado(tmp_path):
    svc = Verifica(home=tmp_path / "legado")
    _carregar(svc, legado=True)
    svc.conn.execute("DELETE FROM meta")  # v1.0.2 não tinha DERIVED_VERSION
    svc.conn.commit()
    return svc


@pytest.fixture
def novo(tmp_path):
    svc = Verifica(home=tmp_path / "novo")
    _carregar(svc, legado=False)
    yield svc
    svc.close()


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_home_novo_tem_derived_version_e_responde(novo):
    assert derivados.versao(novo.conn) == derivados.DERIVED_VERSION == 4
    esperado = _respostas(novo)
    assert esperado[0][2] == ("verified", esperado[0][2][1])  # art. 60 permanente verified
    assert esperado[1][3][0] != "verified"  # trecho do ADCT não confirma o permanente
    assert esperado[3][3][0] == "verified"  # art. 5º do ADCT


def test_home_v102_recusa_consultas_ate_reconstruir(tmp_path):
    svc = _home_legado(tmp_path)
    try:
        for out in (svc.verificar_citacao("art. 60 da CF", trecho=T_CF60), svc.obter_dispositivo(citacao="art. 60 da CF"),
                    svc.buscar_legislacao("Constituição"), svc.verificar_texto("art. 60 da CF")):
            assert out["status"] == "indisponivel" and out["reason_code"] == "ACERVO_DESATUALIZADO"
            assert "derivados_desatualizados" in out["acervo_incompleto"]["motivos"]
    finally:
        svc.close()


def test_reconstruir_v102_igual_a_home_novo(tmp_path, novo):
    esperado = _respostas(novo)
    svc = _home_legado(tmp_path)
    try:
        antes = svc.conn.execute("SELECT (SELECT COUNT(*) FROM capture), (SELECT COUNT(*) FROM run)").fetchone()
        out = svc.reconstruir_acervo()
        assert out["status"] == "ok", out
        assert derivados.versao(svc.conn) == derivados.DERIVED_VERSION
        assert _respostas(svc) == esperado
        # capturas e recibos preservados; derivados do ADCT existem e o FTS só leva o modelo atual
        assert tuple(svc.conn.execute("SELECT (SELECT COUNT(*) FROM capture), (SELECT COUNT(*) FROM run)").fetchone()) \
            >= tuple(antes)
        assert svc.conn.execute("SELECT 1 FROM provision WHERE scope='adct' AND path='adct/art60'").fetchone()
        assert svc.conn.execute("SELECT COUNT(*) FROM fts_redaction WHERE path='art60' AND work_label='Constituição Federal'").fetchone()[0] == 1
        assert svc.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        # idempotente
        assert svc.reconstruir_acervo()["status"] == "ok"
        assert _respostas(svc) == esperado
    finally:
        svc.close()


def test_cli_acervo_reconstruir(tmp_path, capsys):
    svc = _home_legado(tmp_path)
    home = svc.home
    svc.close()
    with pytest.raises(SystemExit) as e:
        main(["--home", str(home), "acervo", "reconstruir", "--json"])
    assert e.value.code == 0
    with Verifica(home=home) as s2:
        assert derivados.versao(s2.conn) == derivados.DERIVED_VERSION


def test_falha_no_meio_nao_altera_o_original(tmp_path, monkeypatch):
    svc = _home_legado(tmp_path)
    try:
        db = svc.home / "verifica.sqlite3"
        svc.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        antes = _sha(db)
        monkeypatch.setattr(derivados, "reindexar_fts", lambda conn: (_ for _ in ()).throw(RuntimeError("falha injetada")))
        out = svc.reconstruir_acervo()
        assert out["status"] == "erro" and out["original_intacto"]
        assert _sha(db) == antes
        assert not list(svc.home.glob(".reconstruir-*"))
        assert derivados.versao(svc.conn) is None  # segue incompatível
        monkeypatch.undo()
        monkeypatch.setenv("FV_OFFLINE", "1")
        # validação reprovada (contagem divergente) também preserva o original
        monkeypatch.setattr(derivados, "_validar", lambda o, n: (_ for _ in ()).throw(RuntimeError("contagem")))
        assert svc.reconstruir_acervo()["status"] == "erro"
        assert _sha(db) == antes
    finally:
        svc.close()


def test_snapshot_instalado_e_reinstalado_igual_ao_home_novo(tmp_path, novo):
    esperado = _respostas(novo)
    dest = tmp_path / "snap"
    assert novo.snapshot_export(dest)["status"] == "ok"
    # home vazio recebe o snapshot duas vezes
    with Verifica(home=tmp_path / "alvo") as alvo:
        assert alvo.snapshot_install(dest)["status"] == "ok"
        assert _respostas(alvo) == esperado
        assert alvo.snapshot_install(dest)["status"] == "ok"
        assert _respostas(alvo) == esperado
        assert alvo.conn.execute("SELECT COUNT(*) FROM fts_redaction WHERE path='art60' AND work_label='Constituição Federal'").fetchone()[0] == 1
        assert derivados.versao(alvo.conn) == derivados.DERIVED_VERSION
    # home v1.0.2 recebe o snapshot (derivados mais novos substituem os locais)
    leg = _home_legado(tmp_path)
    try:
        out = leg.snapshot_install(dest)
        assert out["status"] == "ok", out
        assert derivados.versao(leg.conn) == derivados.DERIVED_VERSION
        assert _respostas(leg) == esperado
        assert leg.snapshot_install(dest)["status"] == "ok"
        assert _respostas(leg) == esperado
        assert leg.acervo_status() is None
    finally:
        leg.close()


def test_manifesto_carrega_derived_version_real(tmp_path, novo):
    import json
    dest = tmp_path / "snap"
    novo.snapshot_export(dest)
    assert json.loads((dest / "MANIFEST.json").read_text())["derived_version"] == "4"


# ---------------------------------------------------------------------------
# Snapshot no formato v1.0.2 (esquema 1..5, sem derived_version) e reconstrução vazia
# ---------------------------------------------------------------------------

def _snapshot_v102(tmp_path, legado):
    """Exporta o home legado e regrava banco e manifesto como a v1.0.2 os publicava."""
    import json
    from freoa_verifica.snapshot import SNAPSHOT_TABLE_COLUMNS, _compress, _sha256_file
    from freoa_verifica.store.db import _migration_files, split_sql_statements

    dest = tmp_path / "snap102"
    assert legado.snapshot_export(dest)["status"] == "ok"
    manifest = json.loads((dest / "MANIFEST.json").read_text())
    novo_db = tmp_path / "antigo.db"
    old = sqlite3.connect(str(novo_db))
    old.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))")
    for versao, sql in _migration_files():
        if versao <= 5:
            for stmt in split_sql_statements(sql):
                old.execute(stmt)
            old.execute("INSERT INTO schema_version(version) VALUES (?)", (versao,))
    old.execute("ATTACH DATABASE ? AS novo", (str(dest / manifest["db_arquivo"]),))
    for tabela, cols in SNAPSHOT_TABLE_COLUMNS.items():
        antigas = {r[1] for r in old.execute(f"PRAGMA main.table_info({tabela})")}
        comuns = ", ".join(c for c in cols if c in antigas)
        if comuns:
            old.execute(f"INSERT INTO main.{tabela}({comuns}) SELECT {comuns} FROM novo.{tabela}")
    old.commit()
    old.close()
    assert not sqlite3.connect(str(novo_db)).execute("SELECT 1 FROM sqlite_master WHERE name IN ('meta','work_status')").fetchall()
    for nome in (manifest["db_arquivo"], "verifica.sqlite3"):
        (dest / nome).write_bytes(novo_db.read_bytes())
    (dest / manifest["db_compactado"]).unlink()
    comp = _compress(dest / manifest["db_arquivo"], dest / manifest["db_arquivo"])
    sha = _sha256_file(dest / manifest["db_arquivo"])
    manifest.update(esquema=[1, 2, 3, 4, 5], esquema_minimo=5, db_sha256=sha, db_compactado=comp.name)
    manifest.pop("derived_version", None)
    manifest["arquivos_sha256"].update({manifest["db_arquivo"]: sha, "verifica.sqlite3": sha,
                                        comp.name: _sha256_file(comp)})
    _regravar(dest, manifest)
    return dest, manifest


def _regravar(dest, manifest):
    import json
    raw = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    (dest / "MANIFEST.json").write_bytes(raw)
    (dest / "MANIFEST.sha256").write_bytes((hashlib.sha256(raw).hexdigest() + "\n").encode("ascii"))
    linhas = [f"{d}  {n}" for n, d in {**manifest["arquivos_sha256"],
                                         "MANIFEST.json": hashlib.sha256(raw).hexdigest()}.items()]
    (dest / "SHA256SUMS").write_text("\n".join(linhas) + "\n", encoding="utf-8")


def test_snapshot_v102_instala_reconstroi_e_reinstala(tmp_path, novo):
    esperado = _respostas(novo)
    legado = _home_legado(tmp_path)
    try:
        dest, _ = _snapshot_v102(tmp_path, legado)
    finally:
        legado.close()
    with Verifica(home=tmp_path / "alvo") as alvo:
        out = alvo.snapshot_install(dest)
        assert out["status"] == "ok", out
        assert derivados.versao(alvo.conn) == derivados.DERIVED_VERSION
        assert _respostas(alvo) == esperado
        assert esperado[0][2][0] == "verified" and esperado[1][3][0] != "verified"
        assert alvo.snapshot_install(dest)["status"] == "ok"
        assert derivados.versao(alvo.conn) == derivados.DERIVED_VERSION
        assert _respostas(alvo) == esperado


def test_snapshot_de_esquema_futuro_ou_nao_prefixo_e_recusado(tmp_path, novo):
    dest = tmp_path / "snap"
    novo.snapshot_export(dest)
    import json
    manifest = json.loads((dest / "MANIFEST.json").read_text())
    for esquema in (manifest["esquema"] + [99], [1, 2, 4]):
        manifest["esquema"] = esquema
        manifest["esquema_minimo"] = max(esquema)
        _regravar(dest, manifest)
        with Verifica(home=tmp_path / f"alvo{len(esquema)}") as alvo:
            out = alvo.snapshot_install(dest)
            assert out["status"] == "erro" and out["motivo"] == "esquema_incompativel", out


def test_reconstruir_home_vazio_recusa(tmp_path):
    with Verifica(home=tmp_path / "vazio") as svc:
        out = svc.reconstruir_acervo()
        assert out["status"] == "erro" and out["motivo"] == "acervo_vazio" and out["original_intacto"]


def test_reconstruir_sem_nenhuma_captura_reprocessada_recusa(tmp_path, monkeypatch):
    svc = _home_legado(tmp_path)
    try:
        monkeypatch.setattr(Verifica, "reprocessar_capturas",
                            lambda self: {"reprocessados": 0, "divergentes": [], "falhas": []})
        out = svc.reconstruir_acervo()
        assert out["status"] == "erro" and out["motivo"] == "nenhuma_captura_reprocessada"
        assert derivados.versao(svc.conn) is None
    finally:
        svc.close()


# ---------------------------------------------------------------------------
# Windows sem privilégio de symlink (WinError 1314)
# ---------------------------------------------------------------------------

@pytest.fixture
def sem_symlink(monkeypatch):
    import os
    from pathlib import Path

    def negar(*a, **k):
        raise OSError(1314, "O cliente não tem o privilégio necessário")

    monkeypatch.setattr(os, "symlink", negar)
    monkeypatch.setattr(Path, "symlink_to", negar)


def test_sem_privilegio_de_symlink_snapshot_v102_reinstala_e_reconstroi(tmp_path, novo, sem_symlink):
    esperado = _respostas(novo)
    legado = _home_legado(tmp_path)
    try:
        dest, _ = _snapshot_v102(tmp_path, legado)
    finally:
        legado.close()
    with Verifica(home=tmp_path / "alvo") as alvo:
        assert alvo.snapshot_install(dest)["status"] == "ok"
        assert alvo.snapshot_install(dest)["status"] == "ok"
        assert _respostas(alvo) == esperado
        out = alvo.reconstruir_acervo()
        assert out["status"] == "ok", out
        assert _respostas(alvo) == esperado


def test_erro_no_meio_da_instalacao_faz_rollback_e_preserva_o_home(tmp_path, novo, monkeypatch, sem_symlink):
    from freoa_verifica import acervo
    esperado = _respostas(novo)
    dest = tmp_path / "snap"
    novo.snapshot_export(dest)
    with Verifica(home=tmp_path / "alvo") as alvo:
        _carregar(alvo, legado=False)
        antes = alvo.conn.execute("SELECT COUNT(*) FROM capture").fetchone()[0]
        blobs_antes = sorted(p.name for p in (alvo.home / "blobs").rglob("*") if p.is_file())

        def falha(*a, **k):
            raise OSError("falha injetada após a troca")

        monkeypatch.setattr(acervo, "save_installed", falha)
        out = alvo.snapshot_install(dest)
        assert out["status"] == "erro" and out["rollback"] is True, out
        assert alvo.conn.execute("SELECT COUNT(*) FROM capture").fetchone()[0] == antes
        assert sorted(p.name for p in (alvo.home / "blobs").rglob("*") if p.is_file()) == blobs_antes
        assert _respostas(alvo) == esperado
