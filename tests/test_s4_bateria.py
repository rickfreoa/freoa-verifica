"""S4 (decisão 0057): `fv acervo conferir` — bateria do snapshot, somente leitura."""
import hashlib
import json
import os
import sqlite3
from pathlib import Path

import pytest

from freoa_verifica import bateria, cli
from freoa_verifica.derivados import DERIVED_VERSION
from freoa_verifica.service import Verifica
from freoa_verifica.store import repo
from freoa_verifica.transport import Response
from freoa_verifica.ids import new_ulid

RECORTE = {"desde": "2026-01-01", "ate": "2026-03-31"}


def _captura(svc, tag):
    corpo = f"corpo {tag}".encode()
    resp = Response(f"https://x/{tag}", f"https://x/{tag}", 200, {}, corpo, hashlib.sha256(corpo).hexdigest(),
                    "2026-10-18T00:00:00+00:00", [], "application/json")
    svc.conn.execute("INSERT OR IGNORE INTO source(id, authority, profile, hosts_json) VALUES ('stj','STJ','p','[]')")
    return repo.save_capture(svc.conn, resp, "stj", home=svc.home)


def _decisao(svc, oid, *, orgao="PRIMEIRA TURMA", data="2026-02-10", captura=True):
    did = repo.upsert_decision(svc.conn, court="STJ", kind="acordao", number=oid, organ=orgao, official_id=oid,
                               judgment_date=data, publication_date=data)
    if captura:
        svc.conn.execute("INSERT INTO decision_document(id, decision_id, capture_id, kind, text) VALUES (?,?,?,?,?)",
                         (new_ulid(), did, _captura(svc, oid), "ementa", "texto"))
        svc.conn.commit()
    return did


@pytest.fixture
def home(tmp_path):
    tmp_path = tmp_path / "acervo"  # fora dele ficam os manifestos que os testes gravam
    with Verifica(tmp_path) as svc:
        _decisao(svc, "d1")
        _decisao(svc, "d2", orgao="SEGUNDA TURMA", data="2026-03-05")
        svc.conn.execute("INSERT INTO sync_state(id, fonte, chave, status, payload_json) VALUES (?,?,?,?,?)",
                         ("s1", "stj_resource", "resource:r1:None", "capturado",
                          json.dumps({"sha256": "ab" * 32, "mes": "202602", "n": 2, "meta": {"last_modified": "2026-03-01"}})))
        svc.conn.commit()
        svc.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return tmp_path


def _codigos(r):
    return {f["codigo"] for f in r["falhas"]}


def test_caso_integro_passa_e_conta(home):
    r = bateria.executar(home, recorte=RECORTE)
    assert r["status"] == "ok", r["falhas"]
    c = r["contagens"]
    assert c["decisoes"] == 2 and c["derived_version"] == DERIVED_VERSION
    assert c["fontes"]["stj"] == {"capturas": 2, "documentos": 2, "parseados": 0}
    assert c["stj"]["por_orgao"] == {"PRIMEIRA TURMA": 1, "SEGUNDA TURMA": 1}
    assert c["stj"]["por_mes_julgamento"] == {"2026-02": 1, "2026-03": 1}
    assert c["recursos_ckan"] == [{"id": "r1", "nome": "202602", "last_modified": "2026-03-01", "sha256": "ab" * 32, "n": 2}]


def test_manifesto_grava_canonico_e_confere(home, tmp_path):
    arq = tmp_path / "m.json"
    r = bateria.executar(home, gravar=arq, recorte=RECORTE)
    assert r["manifesto_gravado"] == str(arq)
    texto = arq.read_text(encoding="utf-8")
    assert texto == json.dumps(json.loads(texto), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    assert bateria.executar(home, manifesto=arq)["status"] == "ok"  # recorte vem do manifesto


def test_contagem_divergente_do_manifesto(home, tmp_path):
    arq = tmp_path / "m.json"
    bateria.executar(home, gravar=arq)
    with Verifica(home) as svc:
        _decisao(svc, "d3")
    r = bateria.executar(home, manifesto=arq)
    assert r["status"] == "falha" and _codigos(r) == {"contagem_divergente"}
    assert any(f["mensagem"].startswith("decisoes: manifesto=2 acervo=3") for f in r["falhas"])


def test_decisao_sem_captura(home):
    with Verifica(home) as svc:
        _decisao(svc, "d3", captura=False)
    r = bateria.executar(home)
    assert _codigos(r) == {"decisao_sem_captura"} and "1 decisão" in r["falhas"][0]["mensagem"]


def test_data_fora_do_recorte(home):
    with Verifica(home) as svc:
        _decisao(svc, "d3", data="2025-12-31")
    r = bateria.executar(home, recorte=RECORTE)
    assert _codigos(r) == {"data_fora_do_recorte"} and "2025-12-31" in r["falhas"][0]["mensagem"]
    assert bateria.executar(home)["status"] == "ok"  # sem recorte declarado, sem verificação


def test_derivado_antigo(home):
    with Verifica(home) as svc:
        svc.conn.execute("UPDATE meta SET value='1' WHERE key='derived_version'")
        svc.conn.execute("INSERT INTO work(id, jurisdiction, authority, kind, number, year) VALUES ('w','federal','a','lei','1',2000)")
        svc.conn.commit()
    r = bateria.executar(home)
    assert _codigos(r) == {"derivado_desatualizado"} and "derived_version 1" in r["falhas"][0]["mensagem"]


def test_duplicata_official_id(home, tmp_path):
    # O esquema tem UNIQUE(court, official_id); acervo de origem estranha é simulado sem essa restrição.
    origem = sqlite3.connect(str(home / bateria.BANCO))
    script = "\n".join(origem.iterdump()).replace(",\n    UNIQUE (court, official_id)", "")
    origem.close()
    dup = tmp_path / "dup"
    dup.mkdir()
    novo = sqlite3.connect(str(dup / bateria.BANCO))
    novo.executescript(script)
    novo.execute("INSERT INTO decision(id, court, kind, official_id) VALUES ('x','STJ','acordao','d1')")
    novo.commit()
    novo.close()
    r = bateria.executar(dup)
    assert "duplicata" in _codigos(r)
    assert any("STJ d1" in f["mensagem"] for f in r["falhas"])


def test_pendencia_so_falha_no_estrito(home):
    with Verifica(home) as svc:
        svc.conn.execute("INSERT INTO sync_state(id, fonte, chave, status, motivo) VALUES ('p','stj_resource','resource:r2:None','indisponivel','http_503')")
        svc.conn.commit()
    assert bateria.executar(home)["status"] == "ok"
    r = bateria.executar(home, estrito=True)
    assert _codigos(r) == {"pendencia"} and "http_503" in r["falhas"][0]["mensagem"]


def test_banco_somente_leitura_e_acervo_intacto(home):
    banco = home / bateria.BANCO
    antes = hashlib.sha256(banco.read_bytes()).hexdigest()
    conn = bateria.abrir_somente_leitura(home)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        conn.execute("DELETE FROM decision")
    conn.close()
    bateria.executar(home)
    assert hashlib.sha256(banco.read_bytes()).hexdigest() == antes


def test_home_sem_banco_e_erro(tmp_path):
    r = bateria.executar(tmp_path / "vazio")
    assert r["status"] == "erro" and "banco ausente" in r["motivo"]
    assert not (tmp_path / "vazio").exists()


def test_cli_codigo_de_saida(home, tmp_path, capsys):
    arq = tmp_path / "m.json"
    with pytest.raises(SystemExit) as e:
        cli.main(["acervo", "conferir", "--home", str(home), "--gravar-manifesto", str(arq), "--json"])
    assert e.value.code == 0 and arq.is_file()
    assert json.loads(capsys.readouterr().out)["status"] == "ok"
    with Verifica(home) as svc:
        _decisao(svc, "d3")
    with pytest.raises(SystemExit) as e:
        cli.main(["acervo", "conferir", "--home", str(home), "--manifesto", str(arq)])
    assert e.value.code == 1


def _blobs_do_home(home):
    conn = sqlite3.connect(str(home / bateria.BANCO))
    try:
        return [home / "blobs" / s[:2] / s[2:4] / s for (s,) in conn.execute("SELECT sha256 FROM capture ORDER BY id")]
    finally:
        conn.close()


def test_blob_ausente_falha(home):
    """B3-04: captura sem os bytes não passa."""
    alvo = _blobs_do_home(home)[0]
    alvo.unlink()
    r = bateria.executar(home)
    assert r["status"] == "falha" and _codigos(r) == {"blob_ausente"}


def test_blob_com_tamanho_ou_hash_divergente_falha(home):
    a, b = _blobs_do_home(home)
    a.write_bytes(b"curto")
    b.write_bytes(b"x" * len(b.read_bytes()))  # mesmo tamanho, outros bytes
    assert _codigos(bateria.executar(home)) == {"blob_tamanho", "blob_hash"}


def test_sem_blobs_e_parcial_e_nao_grava_manifesto(home, tmp_path):
    _blobs_do_home(home)[0].unlink()
    arq = tmp_path / "m.json"
    r = bateria.executar(home, sem_blobs=True, gravar=arq)
    assert r["status"] == "parcial" and r["falhas"] == [] and r["defeitos"]["blobs"] is None
    assert r["manifesto_gravado"] is False and not arq.exists()


def test_verificacao_de_blobs_nao_cria_diretorios(tmp_path):
    with Verifica(tmp_path) as svc:
        _decisao(svc, "d1")
        svc.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    raiz = tmp_path / "blobs"
    for f in sorted(raiz.rglob("*"), reverse=True):
        f.unlink() if f.is_file() else f.rmdir()
    raiz.rmdir()
    assert bateria.executar(tmp_path)["status"] == "falha"
    assert not raiz.exists()


def _recusado(home, destino):
    antes = destino.read_bytes() if destino.exists() else None
    r = bateria.executar(home, gravar=destino)
    assert r["status"] == "erro" and "ValueError" in r["motivo"], r
    assert (destino.read_bytes() if destino.exists() else None) == antes


def test_gravar_manifesto_recusa_banco_e_blob_do_home(home):
    """B3-03: o destino é resolvido antes de abrir o banco e nada dentro do home é sobrescrito."""
    _recusado(home, home / bateria.BANCO)
    _recusado(home, _blobs_do_home(home)[0])
    _recusado(home, home / "novo" / ".." / "novo.json")
    assert bateria.executar(home)["status"] == "ok"


def test_gravar_manifesto_recusa_symlink_para_o_home(home, tmp_path):
    ln = tmp_path / "ln.json"
    try:
        ln.symlink_to(home / bateria.BANCO)
    except (OSError, NotImplementedError):
        pytest.skip("symlink indisponível neste sistema")
    _recusado(home, ln)


def test_gravar_manifesto_recusa_hardlink_para_o_home(home, tmp_path):
    hl = tmp_path / "hl.json"
    try:
        os.link(_blobs_do_home(home)[0], hl)
    except OSError:
        pytest.skip("hardlink indisponível neste sistema")
    _recusado(home, hl)


def test_cli_sem_blobs_sai_com_codigo_proprio(home, capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["acervo", "conferir", "--home", str(home), "--sem-blobs", "--json"])
    assert e.value.code == 2 and json.loads(capsys.readouterr().out)["status"] == "parcial"


def test_cli_sem_datas_herda_recorte_do_manifesto(home, tmp_path, capsys):
    """B3-02: a CLI efetiva sem flags de data usa o recorte congelado (mudança dentro do mesmo mês)."""
    arq = tmp_path / "m.json"
    with pytest.raises(SystemExit) as e:
        cli.main(["acervo", "conferir", "--home", str(home), "--gravar-manifesto", str(arq),
                  "--recorte-desde", "2026-02-05", "--recorte-ate", "2026-03-31", "--json"])
    assert e.value.code == 0
    capsys.readouterr()
    with Verifica(home) as svc:
        svc.conn.execute("UPDATE decision SET judgment_date='2026-02-01' WHERE official_id='d1'")
        svc.conn.commit()
        svc.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    with pytest.raises(SystemExit) as e:
        cli.main(["acervo", "conferir", "--home", str(home), "--manifesto", str(arq), "--json"])
    saida = json.loads(capsys.readouterr().out)
    assert e.value.code == 1 and saida["status"] == "falha"
    assert saida["recorte"] == {"desde": "2026-02-05", "ate": "2026-03-31"}
    assert "data_fora_do_recorte" in _codigos(saida)


# --- FIX4 (decisão 0057, emenda): conteúdo do snapshot × estado de sincronização ---

def _instalado(home):
    """Acervo simulado de snapshot: mesmo conteúdo, sem sync_state."""
    with Verifica(home) as svc:
        svc.conn.execute("DELETE FROM sync_state")
        svc.conn.commit()
        svc.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def test_manifesto_tem_conteudo_e_origem(home, tmp_path):
    arq = tmp_path / "m.json"
    bateria.executar(home, gravar=arq, recorte=RECORTE)
    m = json.loads(arq.read_text(encoding="utf-8"))
    assert "contagens" not in m and "recursos_ckan" not in m["conteudo"]
    assert m["conteudo"]["decisoes"] == 2 and m["origem"]["recursos_ckan"][0]["id"] == "r1"


def test_pos_instalacao_confere_so_conteudo(home, tmp_path):
    arq = tmp_path / "m.json"
    bateria.executar(home, gravar=arq, recorte=RECORTE)
    _instalado(home)
    r = bateria.executar(home, manifesto=arq, pos_instalacao=True)
    assert r["status"] == "ok", r["falhas"]
    assert r["origem"] == "nao_aplicavel_pos_instalacao"
    r = bateria.executar(home, manifesto=arq)  # sem a flag e sem sync_state: também não aplicável, e dito
    assert r["status"] == "ok" and r["origem"] == "nao_aplicavel_pos_instalacao"


def test_origem_conferida_quando_ha_sync_state(home, tmp_path):
    arq = tmp_path / "m.json"
    bateria.executar(home, gravar=arq, recorte=RECORTE)
    assert bateria.executar(home, manifesto=arq)["origem"] == "conferida"
    with Verifica(home) as svc:
        svc.conn.execute("UPDATE sync_state SET payload_json=? WHERE id='s1'",
                         (json.dumps({"sha256": "cd" * 32, "mes": "202602", "n": 2}),))
        svc.conn.commit()
    r = bateria.executar(home, manifesto=arq)
    assert r["status"] == "falha" and any("recursos_ckan[r1]" in f["mensagem"] for f in r["falhas"])


def test_pos_instalacao_continua_pegando_divergencia_de_conteudo(home, tmp_path):
    arq = tmp_path / "m.json"
    bateria.executar(home, gravar=arq, recorte=RECORTE)
    _instalado(home)
    with Verifica(home) as svc:
        _decisao(svc, "d3")
    r = bateria.executar(home, manifesto=arq, pos_instalacao=True)
    assert r["status"] == "falha" and _codigos(r) == {"contagem_divergente"}


def test_pos_instalacao_falha_com_sync_state(home, tmp_path):
    arq = tmp_path / "m.json"
    bateria.executar(home, gravar=arq, recorte=RECORTE)
    r = bateria.executar(home, manifesto=arq, pos_instalacao=True)
    assert r["status"] == "falha" and _codigos(r) == {"sync_state_presente"}


def test_manifesto_antigo_sem_secoes_continua_legivel(home, tmp_path):
    r0 = bateria.executar(home, recorte=RECORTE)
    antigo = tmp_path / "antigo.json"
    antigo.write_text(json.dumps({"manifesto_versao": 1, "recorte": RECORTE, "contagens": r0["contagens"]}),
                      encoding="utf-8")
    r = bateria.executar(home, manifesto=antigo)
    assert r["status"] == "ok" and r["origem"] == "conferida"
    _instalado(home)  # recursos_ckan do manifesto antigo é origem: não falha pós-instalação
    r = bateria.executar(home, manifesto=antigo, pos_instalacao=True)
    assert r["status"] == "ok", r["falhas"]


def test_cli_pos_instalacao(home, tmp_path, capsys):
    arq = tmp_path / "m.json"
    bateria.executar(home, gravar=arq, recorte=RECORTE)
    _instalado(home)
    with pytest.raises(SystemExit) as e:
        cli.main(["acervo", "conferir", "--home", str(home), "--manifesto", str(arq), "--pos-instalacao", "--json"])
    assert e.value.code == 0 and json.loads(capsys.readouterr().out)["origem"] == "nao_aplicavel_pos_instalacao"


def _pendencia(home, status="indisponivel"):
    with Verifica(home) as svc:
        svc.conn.execute("INSERT INTO sync_state(id, fonte, chave, status, motivo) VALUES ('p','stj_resource','resource:r2:None',?,'http_503')", (status,))
        svc.conn.commit()


def test_manifesto_inclui_pendencias_em_origem(home, tmp_path):
    # FIX5/F-03: a pendência não desaparece do manifesto canônico.
    _pendencia(home)
    arq = tmp_path / "m.json"
    bateria.executar(home, gravar=arq, recorte=RECORTE)
    m = json.loads(arq.read_text(encoding="utf-8"))
    assert [(p["fonte"], p["status"]) for p in m["origem"]["pendencias"]] == [("stj_resource", "indisponivel")]
    assert "pendencias" not in m["conteudo"]


def test_pendencias_de_origem_so_se_comparam_no_estrito(home, tmp_path):
    arq = tmp_path / "m.json"
    bateria.executar(home, gravar=arq, recorte=RECORTE)  # manifesto sem pendências
    assert json.loads(arq.read_text(encoding="utf-8"))["origem"]["pendencias"] == []
    _pendencia(home)
    r = bateria.executar(home, manifesto=arq)
    assert r["status"] == "ok", r["falhas"]
    r = bateria.executar(home, manifesto=arq, estrito=True)
    assert {"pendencia", "contagem_divergente"} <= _codigos(r)
    assert any(f["mensagem"].startswith("pendencias") for f in r["falhas"] if f["codigo"] == "contagem_divergente")


def test_pendencias_de_origem_nao_se_aplicam_pos_instalacao(home, tmp_path):
    _pendencia(home)
    arq = tmp_path / "m.json"
    bateria.executar(home, gravar=arq, recorte=RECORTE)
    _instalado(home)
    r = bateria.executar(home, manifesto=arq, estrito=True, pos_instalacao=True)
    assert r["status"] == "ok", r["falhas"]
