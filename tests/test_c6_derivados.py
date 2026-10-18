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
    assert derivados.versao(novo.conn) == derivados.DERIVED_VERSION == 2
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
    assert json.loads((dest / "MANIFEST.json").read_text())["derived_version"] == "2"
