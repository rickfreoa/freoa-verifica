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
DERIVED_VERSION = 2

REASON = "ACERVO_DESATUALIZADO"


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


def reindexar_fts(conn: sqlite3.Connection) -> int:
    """Recompõe fts_redaction só com as redações do modelo atual de cada obra (captura mais recente)."""
    conn.execute("DELETE FROM fts_redaction")
    n = 0
    rows = conn.execute(
        "SELECT pd.work_id, pd.model_json, COALESCE(w.label, w.number) AS rotulo FROM parsed_document pd "
        "JOIN capture c ON c.id=pd.capture_id JOIN work w ON w.id=pd.work_id "
        "WHERE pd.model_json IS NOT NULL AND w.authority NOT LIKE 'invalidated:%' "
        "ORDER BY pd.work_id, c.fetched_at DESC, c.id DESC").fetchall()
    vistos: set[str] = set()
    for row in rows:
        if row["work_id"] in vistos:
            continue
        vistos.add(row["work_id"])
        doc = document_from_dict(json.loads(row["model_json"]))
        for prov in doc.provisions:
            rubrica = getattr(prov, "rubrica", None)
            for red in prov.redactions:
                if red.struck:
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
    home: Path = svc.home
    db = home / "verifica.sqlite3"
    pasta = home / f".reconstruir-{new_ulid()}"
    try:
        with svc.exclusivo():
            for velha in home.glob(".reconstruir-*"):  # restos de execução interrompida
                shutil.rmtree(velha, ignore_errors=True)
            svc.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            pasta.mkdir()
            # Sem copiar blobs: o serviço da cópia lê os mesmos bytes por ligação simbólica.
            if (home / "blobs").exists():
                (pasta / "blobs").symlink_to((home / "blobs").resolve(), target_is_directory=True)
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
