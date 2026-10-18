"""Versão dos derivados e recuperação do home (contrato C6, decisão 0028)."""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from freoa_verifica.ids import new_ulid
from freoa_verifica.parsers.model import document_from_dict

_log = logging.getLogger(__name__)

# Incrementar quando parsers, modelo serializado ou derivados mudam de forma incompatível.
# 2 = 1.0.3 (ADCT com escopo próprio, rubrica, FTS só com redações do modelo atual).
# 3 = 1.1.0 (cvm-pdf-2 com dispositivos inferidos, tipo "Resolução" do BCB como CMN pelo preâmbulo,
#     data de efeito declarada no BCB, situação estruturada de precedentes).
# 4 = 1.2.0 (espécie declarada pela fonte prevalece: monocrática nunca rotulada como acórdão; decisão 0038).
DERIVED_VERSION = 4

REASON = "ACERVO_DESATUALIZADO"
REASON_NAO_PUBLICADA = "ACERVO_DE_VERSAO_NAO_PUBLICADA"


def versao(conn: sqlite3.Connection) -> int | None:
    try:
        row = conn.execute("SELECT value FROM meta WHERE key='derived_version'").fetchone()
        return int(row[0]) if row else None
    except (sqlite3.Error, ValueError):
        return None


def definir(conn: sqlite3.Connection, valor: int | None) -> None:
    if valor is None:
        conn.execute("DELETE FROM meta WHERE key='derived_version'")
    else:
        conn.execute("INSERT INTO meta(key, value) VALUES ('derived_version', ?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(valor),))


def origem_nao_publicada(conn: sqlite3.Connection) -> bool:
    try:
        return conn.execute("SELECT 1 FROM meta WHERE key='acervo_origem_nao_publicada'").fetchone() is not None
    except sqlite3.Error:
        return False


def marcar_origem_nao_publicada(conn: sqlite3.Connection) -> None:
    """Esquema 8/9 (nunca publicado) com staging e nenhum candidato marcado: não há como separar candidato de
    canônico. shortcut: o histórico de schema_version não distingue 8/9 de 12; usa-se o estado (staging sem marca)."""
    try:
        if (conn.execute("SELECT 1 FROM fts_staging LIMIT 1").fetchone()
                and not conn.execute("SELECT 1 FROM parsed_document WHERE candidato_ao_vivo=1 LIMIT 1").fetchone()):
            conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('acervo_origem_nao_publicada', '1')")
    except sqlite3.Error:
        pass


def compativel(conn: sqlite3.Connection) -> bool:
    """Home vazio não tem derivados a invalidar; senão a versão tem de ser a do código."""
    if versao(conn) == DERIVED_VERSION:
        return True
    try:
        return conn.execute("SELECT 1 FROM work LIMIT 1").fetchone() is None
    except sqlite3.Error:
        return False


def indisponivel(aviso: dict | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "status": "indisponivel", "motivo": REASON, "reason_code": REASON,
        "detalhe": "derivados de versão anterior; execute `fv acervo reconstruir` "
                   "(ou instale um snapshot reprocessado)",
    }
    if aviso:
        out["acervo_incompleto"] = aviso
    return out


def reindexar_fts(conn: sqlite3.Connection, divergentes: list | None = None) -> int:
    """Recompõe fts_redaction só com as redações do modelo atual de cada obra (captura mais recente).

    A7: capturas marcadas `candidato_ao_vivo` nunca entram no canônico; recompõem o fts_staging
    (só para obras sem captura confirmada). Homes antigos não têm marca: contam como canônicos.
    """
    from freoa_verifica.store.repo import aplicar_monotonia

    novas = aplicar_monotonia(conn)  # 0034: captura que perde estrutura não é canônica
    if divergentes is not None:
        divergentes += [d for d in novas if d not in divergentes]
    conn.execute("DELETE FROM fts_redaction")
    conn.execute("DELETE FROM fts_staging")
    n = 0
    rows = conn.execute(
        "SELECT pd.work_id, pd.model_json, pd.candidato_ao_vivo AS cand, COALESCE(w.label, w.number) AS rotulo "
        "FROM parsed_document pd "
        "JOIN capture c ON c.id=pd.capture_id JOIN work w ON w.id=pd.work_id "
        "WHERE pd.model_json IS NOT NULL AND w.authority NOT LIKE 'invalidated:%' "
        "ORDER BY pd.work_id, c.fetched_at DESC, c.id DESC").fetchall()
    canonicas = {r["work_id"] for r in rows if not r["cand"]}
    vistos: set[tuple[str, int]] = set()
    for row in rows:
        cand = bool(row["cand"])
        if (row["work_id"], cand) in vistos or (cand and row["work_id"] in canonicas):
            continue
        vistos.add((row["work_id"], cand))
        doc = document_from_dict(json.loads(row["model_json"]))
        for prov in doc.provisions:
            rubrica = getattr(prov, "rubrica", None)
            for red in prov.redactions:
                if red.struck:
                    continue
                if cand:
                    conn.execute("INSERT INTO fts_staging(text, work_label, path) VALUES (?,?,?)",
                                 (red.text, row["rotulo"], prov.path))
                    continue
                conn.execute("INSERT INTO fts_redaction(text, rubrica, work_label, path) VALUES (?,?,?,?)",
                             (red.text, rubrica, row["rotulo"], prov.path))
                n += 1
    # Obras sem modelo persistido (acervos muito antigos): cai nas tabelas.
    conn.execute(
        "INSERT INTO fts_redaction(text, rubrica, work_label, path) "
        "SELECT r.text, NULL, COALESCE(w.label,w.number), p.path FROM redaction r "
        "JOIN provision p ON p.id=r.provision_id JOIN work w ON w.id=p.work_id "
        "WHERE w.authority NOT LIKE 'invalidated:%' AND w.id NOT IN ("
        "SELECT work_id FROM parsed_document WHERE model_json IS NOT NULL AND work_id IS NOT NULL)")
    return n


def _contagens(conn: sqlite3.Connection) -> dict[str, int]:
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("work", "capture", "extract", "run", "decision", "parsed_document")}


def _validar(origem: dict[str, int], novo: sqlite3.Connection) -> None:
    if novo.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise RuntimeError("integridade do banco reconstruído falhou")
    if novo.execute("PRAGMA foreign_key_check").fetchone():
        raise RuntimeError("relações inválidas no banco reconstruído")
    c = _contagens(novo)
    if origem["work"] > 0 and c["work"] < 1:
        raise RuntimeError("banco reconstruído sem obras")
    for t in ("work", "capture", "run", "decision", "parsed_document"):
        if c[t] != origem[t]:
            raise RuntimeError(f"contagem divergente em {t}: {origem[t]} -> {c[t]}")
    if c["extract"] < origem["extract"]:
        raise RuntimeError("extrações perdidas")


_ESPECIES_GRAVADAS = frozenset({"sumula", "sumula_vinculante", "repetitivo", "irdr_iac",
                                 "repercussao_geral", "controle_concentrado"})


def reclassificar_autoridade(conn: sqlite3.Connection) -> int:
    """Recalcula o rótulo A–E gravado com as regras atuais (decisão 0038). Rótulos de versões anteriores
    ficavam congelados no banco (p. ex. Colegiado da CVM em D) enquanto a busca recalculava. A espécie de
    precedente qualificado gravada pela ingestão é preservada; monocrática declarada prevalece."""
    from freoa_verifica.authority import as_dict, classify_authority
    from freoa_verifica.service import _species_from_meta

    n = 0
    for did, court, cls, organ, kind, attrs_json, label in conn.execute(
            "SELECT id, court, class, organ, kind, authority_attrs_json, authority_label FROM decision").fetchall():
        try:
            old = json.loads(attrs_json) if attrs_json else {}
        except ValueError:
            old = {}
        gravada = ((old.get("attributes") or {}).get("species") if isinstance(old.get("attributes"), dict)
                   else old.get("species"))
        species = _species_from_meta(court or "", cls, organ, kind)
        if species != "monocratica" and gravada in _ESPECIES_GRAVADAS:
            species = gravada
        auth = classify_authority(species=species, court=court or "", class_name=cls, organ=organ)
        attrs = {**old, **as_dict(auth)}
        if auth.label != label or attrs != old:
            conn.execute("UPDATE decision SET authority_label=?, authority_attrs_json=? WHERE id=?",
                         (auth.label, json.dumps(attrs, ensure_ascii=False), did))
            n += 1
    return n


def corrigir_inteiro_teor_sumulas(conn: sqlite3.Connection) -> int:
    """Até a 1.1.0, enunciado de súmula com mais de 500 caracteres era gravado como inteiro_teor (A12).
    Súmula não tem inteiro teor: o documento volta a ementa (ou sai, se a ementa já existe) e o FTS acompanha."""
    alvo = conn.execute(
        "SELECT dd.id, dd.decision_id, d.court, d.official_id, "
        "EXISTS(SELECT 1 FROM decision_document e WHERE e.decision_id=dd.decision_id AND e.kind='ementa') "
        "FROM decision_document dd JOIN decision d ON d.id=dd.decision_id "
        "WHERE dd.kind='inteiro_teor' AND (d.kind='sumula' OR LOWER(COALESCE(d.class,'')) LIKE '%mula%')").fetchall()
    for doc_id, did, court, official_id, tem_ementa in alvo:
        if tem_ementa:
            conn.execute("DELETE FROM decision_document WHERE id=?", (doc_id,))
        else:
            conn.execute("UPDATE decision_document SET kind='ementa', nivel_prova='ementa_capturada' WHERE id=?", (doc_id,))
        conn.execute("UPDATE decision SET nivel_prova='ementa_capturada' WHERE id=?", (did,))
        conn.execute("UPDATE fts_decision SET inteiro_teor='' WHERE court=? AND official_id=?", (court, official_id))
    return len(alvo)


def reprocessar_pasta(pasta: Path, *, com_situacao: bool = False) -> dict[str, Any]:
    """Reprocessa com os parsers atuais o banco `pasta/verifica.sqlite3` (+ blobs), reindexa o FTS,
    carimba DERIVED_VERSION e valida contagens. Levanta RuntimeError se algo não fechar."""
    from freoa_verifica.service import Verifica

    raw = sqlite3.connect(str(pasta / "verifica.sqlite3"))
    try:
        origem = _contagens(raw)
        reprocessaveis = raw.execute(
            "SELECT COUNT(*) FROM capture c JOIN parsed_document p ON p.capture_id=c.id "
            "JOIN work w ON w.id=p.work_id WHERE p.model_json IS NOT NULL "
            "AND c.source_id IN ('planalto','cvm_normas','bcb') AND w.authority NOT LIKE 'invalidated:%'").fetchone()[0]
    finally:
        raw.close()
    if origem["work"] == 0:
        raise RuntimeError("acervo_vazio")
    relatorio: dict[str, Any] = {}
    with Verifica(home=pasta) as novo:
        rep = novo.reprocessar_capturas()
        if rep["falhas"]:
            raise RuntimeError(f"reprocessamento falhou em {len(rep['falhas'])} captura(s): "
                               f"{rep['falhas'][0]['motivo'][:120]}")
        if reprocessaveis and not rep["reprocessados"]:
            raise RuntimeError("nenhuma_captura_reprocessada")
        relatorio.update(reprocessados=rep["reprocessados"], divergentes=rep["divergentes"])
        with novo.conn:
            relatorio["fts"] = reindexar_fts(novo.conn)
            relatorio["decisoes_reclassificadas"] = reclassificar_autoridade(novo.conn)
            relatorio["sumulas_sem_inteiro_teor"] = corrigir_inteiro_teor_sumulas(novo.conn)
        if com_situacao:
            if novo._offline():
                relatorio["situacao"] = "ignorada_offline"
            else:
                relatorio["situacao"] = novo.ressincronizar_situacao()
        with novo.conn:
            definir(novo.conn, DERIVED_VERSION)
        _validar(origem, novo.conn)
        novo.conn.commit()
        novo.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    for suf in ("-wal", "-shm"):
        Path(str(pasta / "verifica.sqlite3") + suf).unlink(missing_ok=True)
    return relatorio


def reconstruir(svc: Any, *, com_situacao: bool = False) -> dict[str, Any]:
    """Reconstrói os derivados numa cópia e troca o banco só depois de validar (idempotente)."""
    if svc._read_only:
        return {"status": "erro", "motivo": "somente_leitura"}
    if origem_nao_publicada(svc.conn):
        return {"status": "erro", "motivo": REASON_NAO_PUBLICADA, "original_intacto": True,
                "orientacao": "este home vem de build de desenvolvimento não publicado; use `fv snapshot install` em home novo"}
    home: Path = svc.home
    db = home / "verifica.sqlite3"
    pasta = home / f".reconstruir-{new_ulid()}"
    try:
        with svc.exclusivo():
            for velha in home.glob(".reconstruir-*"):  # restos de execução interrompida
                shutil.rmtree(velha, ignore_errors=True)
            svc.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            pasta.mkdir()
            # Blobs espelhados por hardlink (sem symlink: exige privilégio no Windows).
            if (home / "blobs").exists():
                from freoa_verifica.store.blobs import espelhar
                espelhar(home / "blobs", pasta / "blobs")
            copia = pasta / "verifica.sqlite3"
            dst = sqlite3.connect(str(copia))
            try:
                svc.conn.backup(dst)
            finally:
                dst.close()
            relatorio = reprocessar_pasta(pasta, com_situacao=com_situacao)
            for suf in ("-wal", "-shm"):
                Path(str(copia) + suf).unlink(missing_ok=True)
            svc._close_all_conns(strict=True)
            try:
                backup = home / f"verifica.sqlite3.pre-reconstruir-{new_ulid()}"
                os.link(db, backup)  # o original segue acessível sem custo de espaço
                relatorio["original_preservado_em"] = str(backup)
            except OSError:
                pass
            for suf in ("-wal", "-shm"):
                Path(str(db) + suf).unlink(missing_ok=True)
            os.replace(copia, db)
            svc._clear_caches()
            return {"status": "ok", "derived_version": DERIVED_VERSION, **relatorio}
    except (RuntimeError, ValueError, OSError, TimeoutError, sqlite3.Error) as exc:
        return {"status": "erro", "motivo": str(exc)[:200], "original_intacto": True}
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
