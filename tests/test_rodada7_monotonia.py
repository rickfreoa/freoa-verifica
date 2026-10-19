"""Rodada 7 (auditor Codex): monotonia estrutural (decisão 0034)."""
from __future__ import annotations

import pytest

from freoa_verifica import derivados
from freoa_verifica.aliases import WorkKey

from freoa_verifica.service import Verifica

KEY = WorkKey("federal", "lei", "9999", 2000)
T0, T1, T2 = "2026-01-01T00:00:00+00:00", "2026-02-01T00:00:00+00:00", "2026-03-01T00:00:00+00:00"
CIT2 = "art. 2º da Lei 9.999/2000"


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")


def _html(*textos):
    arts = "".join(f'<p><a name="art{i}"></a>Art. {i}º {t}.</p>' for i, t in enumerate(textos, 1))
    return ("<html><head><title>Lei 9.999</title></head><body><p>LEI Nº 9.999, DE 1º DE JANEIRO DE 2000</p>"
            f"<p>Dispõe sobre testes.</p>{arts}</body></html>").encode()


def _idx(s, textos, quando, nome):
    """Indexa corpo HTML real (reprocessável) com o parser do Planalto."""
    from freoa_verifica.parsers.planalto import parse_planalto
    corpo = _html(*textos)
    url = "https://example.invalid/" + nome
    return s.indexar_obra(source_id="planalto", work_key=KEY, document=parse_planalto(corpo, base_url=url),
                          body=corpo, url=url, label="Lei 9.999/2000", fetched_at=quando)


def _cands(s):
    return dict(s.conn.execute("SELECT capture_id, candidato_ao_vivo FROM parsed_document").fetchall())


def _status(s, n=2, texto="dois"):
    return s.verificar_citacao(f"art. {n}º da Lei 9.999/2000", texto)["identity"]["status"]


def _desmarcar_e_esquema9(tmp_path, s, _b):
    """Reproduz o home de build intermediário: B sem marca, staging vazio, esquema 9."""
    with s.conn:
        s.conn.execute("UPDATE parsed_document SET candidato_ao_vivo=0")
        s.conn.execute("DELETE FROM fts_staging")
        s.conn.execute("ALTER TABLE parsed_document DROP COLUMN candidato_ao_vivo")
        s.conn.execute("DELETE FROM schema_version WHERE version>=10")
        s.conn.execute("DELETE FROM meta WHERE key='acervo_origem_nao_publicada'")


def test_a_esquema9_candidato_subconjunto_sem_marca_e_staging_vazio(tmp_path):
    with Verifica(tmp_path) as s:
        a = _idx(s, ("um", "dois", "tres"), T0, "A")
        b = _idx(s, ("um",), T1, "B")
        assert b.capture_id == a.capture_id  # indexar_obra devolve o canônico
        b = next(k for k, v in _cands(s).items() if v == 1)  # rebaixada já na indexação
        _desmarcar_e_esquema9(tmp_path, s, None)
    with Verifica(tmp_path) as s:  # migra 010..013
        assert not derivados.origem_nao_publicada(s.conn)
        assert _cands(s)[b] == 0
        assert _status(s) == "verified"  # seleção dinâmica, antes de reconstruir
        out = s.reconstruir_acervo()
        assert out["status"] == "ok", out
        assert [(d["capture_id"], d["motivo"]) for d in out["divergentes"]] == [(b, "PERDA_ESTRUTURAL")]
        assert _cands(s)[b] == 1
        assert _status(s) == "verified"
        r = s.buscar_legislacao("dois", fonte="__somente_local__")
        assert any(i.get("path") == "art2" or "dois" in str(i) for i in r["itens"])
        assert s.reconstruir_acervo()["divergentes"] == []  # idempotente


def test_b_home_novo_via_indexar_obra(tmp_path):
    with Verifica(tmp_path) as s:
        a = _idx(s, ("um", "dois", "tres"), T0, "A")
        rw = _idx(s, ("um",), T1, "B")
        assert rw.capture_id == a.capture_id and {p.path for p in rw.document.provisions} == {"art1", "art2", "art3"}
        assert _status(s) == "verified"
        assert s.conn.execute("select count(*) from fts_redaction where text like '%dois%'").fetchone()[0] == 1


def test_c_instalacao_de_snapshot(tmp_path):
    with Verifica(tmp_path / "origem") as o:
        _idx(o, ("um", "dois", "tres"), T0, "A")
        _idx(o, ("um",), T1, "B")
        with o.conn:
            o.conn.execute("UPDATE parsed_document SET candidato_ao_vivo=0")  # snapshot sem a marca
        assert o.snapshot_export(tmp_path / "snap")["status"] == "ok"
    with Verifica(tmp_path / "alvo") as t:
        _idx(t, ("um", "dois", "tres"), T0, "A")
        out = t.snapshot_install(tmp_path / "snap", aceitar_nao_vinculado=True)
        assert out["status"] == "ok", out
        assert [d["motivo"] for d in out["divergentes"]] == ["PERDA_ESTRUTURAL"]
        assert t.conn.execute("select candidato_ao_vivo from parsed_document pd join capture c on c.id=pd.capture_id "
                              "where c.url like '%B'").fetchone()[0] == 1
        assert _status(t) == "verified"


def test_d_acrescimo_e_texto_novo_sao_promovidos(tmp_path):
    with Verifica(tmp_path) as s:
        _idx(s, ("um", "dois", "tres"), T0, "A")
        c = _idx(s, ("um novo", "dois", "tres", "quatro"), T1, "C")
        assert _cands(s)[c.capture_id] == 0 and s.reconstruir_acervo()["divergentes"] == []
        assert s.verificar_citacao("art. 1º da Lei 9.999/2000", "um novo")["identity"]["status"] == "verified"
        assert s.verificar_citacao("art. 4º da Lei 9.999/2000", "quatro")["identity"]["status"] == "verified"


def test_e_negativa_legitima_continua(tmp_path):
    with Verifica(tmp_path) as s:
        _idx(s, ("um", "dois", "tres"), T0, "A")
        r = s.verificar_citacao("art. 312 da Lei 9.999/2000", "x")
        assert (r["identity"]["status"], r["identity"]["reason_code"]) == ("not_found", "DISPOSITIVO_INEXISTENTE")


def test_rede_de_seguranca_nao_nega_caminho_de_captura_anterior(tmp_path):
    from freoa_verifica.verify import pode_negar
    with Verifica(tmp_path) as s:
        _idx(s, ("um", "dois", "tres"), T0, "A")
        rw = _idx(s, ("um",), T1, "B")
        from dataclasses import replace
        so_art1 = replace(rw.document, provisions=[p for p in rw.document.provisions if p.path == "art1"])
        assert pode_negar(replace(rw, document=so_art1), "art2") == "ESTRUTURA_DIVERGENTE_ENTRE_CAPTURAS"
