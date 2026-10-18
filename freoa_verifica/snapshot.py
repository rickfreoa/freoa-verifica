"""Exportação e instalação de snapshots de corpus público."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import sqlite3
from contextlib import contextmanager
from uuid import uuid4
import tarfile
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from freoa_verifica import acervo, derivados
from freoa_verifica.ids import new_ulid
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.store import blobs
from freoa_verifica.store.db import connect, data_home

# Autenticidade do snapshot: confiança no canal autenticado (release GitHub do
# autor rickfreoa/freoa-verifica) + attestation do GitHub Actions
# (`gh attestation verify`). Não é assinatura criptográfica própria do pacote.
AUTHENTICITY_NOTE = (
    "Checksums demonstram integridade. A origem depende do canal da release "
    "GitHub rickfreoa/freoa-verifica; eventual attestation deve ser conferida "
    "separadamente. Não há assinatura própria nem attestation demonstrada aqui."
)


GITHUB_HOSTS = frozenset({"github.com", "objects.githubusercontent.com", "api.github.com", "release-assets.githubusercontent.com"})
GITHUB_PREFIXES = {
    "github.com": ("/rickfreoa/freoa-verifica/", "/repos/rickfreoa/freoa-verifica/"),
    "api.github.com": ("/repos/rickfreoa/freoa-verifica/",),
}
GITHUB_MIMES = frozenset(
    {
        "application/octet-stream",
        "application/gzip",
        "application/zstd",
        "application/json",
        "application/zip",
        "text/plain",
        "text/html",
        "application/vnd.github+json",
    }
)

BLOB_SIZE_LIMIT = int(1.5 * 1024 * 1024 * 1024)  # 1,5 GB

SNAPSHOT_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "source": (
        "id", "authority", "profile", "hosts_json", "reuse_policy",
        "policy_version", "created_at",
    ),
    "work": (
        "id", "jurisdiction", "authority", "kind", "number", "year",
        "label", "created_at",
    ),
    "alias": (
        "id", "work_id", "scheme", "value", "origin",
        "resolution_status", "created_at",
    ),
    "edition": ("id", "work_id", "kind", "publication_date", "created_at"),
    "capture": (
        "id", "source_id", "edition_id", "url", "final_url", "fetched_at",
        "status", "headers_json", "redirects_json", "sha256", "mime",
        "size", "outcome",
    ),
    "extract": (
        "id", "capture_id", "parser_version", "text_sha256", "quality",
        "created_at",
    ),
    "provision": ("id", "work_id", "scope", "path", "parent_id"),
    "redaction": ("id", "provision_id", "text", "text_sha256", "created_at"),
    "occurrence": (
        "id", "redaction_id", "extract_id", "anchor_json", "editorial_json",
    ),
    "event": (
        "id", "kind", "provision_id", "redaction_id", "source_work_id",
        "publication_date", "effective_date", "effects_date", "scope_json",
        "rule", "evidence_occurrence_id", "state", "created_at",
    ),
    "relation": (
        "id", "from_edition", "to_edition", "kind", "evidence_occurrence_id",
    ),
    "proceeding": (
        "id", "court", "number", "cnj_number", "uf", "class", "created_at",
    ),
    "decision": (
        "id", "proceeding_id", "court", "class", "number", "uf", "organ",
        "rapporteur", "judgment_date", "publication_date", "kind",
        "official_id", "identity_status", "authority_attrs_json",
        "authority_label", "created_at", "nivel_prova",
    ),
    "decision_document": (
        "id", "decision_id", "capture_id", "extract_id", "kind", "text",
        "sha256", "created_at", "nivel_prova",
    ),
    "theme": ("id", "court", "number", "title", "thesis", "created_at"),
    "parsed_document": (
        "capture_id", "profile", "parser_version", "quarantined",
        "issues_json", "ambiguous_paths_json", "editorial_json",
        "model_json", "work_id", "work_date", "amending_texts_json", "events_json",
    ),
    "work_year_issue": ("work_id", "reason", "capture_id"),
    "work_status": (
        "work_id", "situacao", "texto_oficial", "ato_revogador", "data_efeito",
        "captura_id", "sha256", "lido_em",
    ),
}

# Tabelas/colunas excluídas do snapshot público
EXCLUIDAS = frozenset({"run", "sync_state", "schema_version"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _cobertura(conn: sqlite3.Connection) -> dict[str, Any]:
    out: dict[str, Any] = {}
    rows = conn.execute(
        "SELECT source_id, MIN(fetched_at), MAX(fetched_at), COUNT(*) "
        "FROM capture GROUP BY source_id"
    ).fetchall()
    for sid, mn, mx, n in rows:
        out[sid] = {
            "capturas": n,
            "fetched_at_min": mn,
            "fetched_at_max": mx,
        }
    return out


def _parser_versions(conn: sqlite3.Connection) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        rows = conn.execute(
            "SELECT capture_id, parser_version FROM parsed_document"
        ).fetchall()
        for cid, pv in rows:
            out[str(cid)] = str(pv)
    except sqlite3.Error:
        pass
    try:
        rows = conn.execute(
            "SELECT capture_id, parser_version FROM extract"
        ).fetchall()
        for cid, pv in rows:
            out.setdefault(str(cid), str(pv))
    except sqlite3.Error:
        pass
    return out


def _compress(src: Path, dest_stem: Path) -> Path:
    """Compacta com zstandard se disponível, senão gzip. Retorna caminho final."""
    try:
        import zstandard as zstd  # type: ignore

        out = Path(str(dest_stem) + ".zst")
        cctx = zstd.ZstdCompressor(level=3)
        with src.open("rb") as fin, out.open("wb") as fout:
            cctx.copy_stream(fin, fout)
        return out
    except ImportError:
        out = Path(str(dest_stem) + ".gz")
        with src.open("rb") as fin, gzip.open(out, "wb") as fout:
            shutil.copyfileobj(fin, fout)
        return out


def _decompress_to(src: Path, dest: Path) -> None:
    name = src.name.lower()
    if name.endswith(".zst"):
        import zstandard as zstd  # type: ignore

        dctx = zstd.ZstdDecompressor()
        with src.open("rb") as fin, dest.open("wb") as fout:
            dctx.copy_stream(fin, fout)
    elif name.endswith(".gz"):
        with gzip.open(src, "rb") as fin, dest.open("wb") as fout:
            shutil.copyfileobj(fin, fout)
    else:
        shutil.copy2(src, dest)


def _restore_stj_ementas(conn: sqlite3.Connection, home: Path) -> None:
    """Recupera ementas antigas substituídas pelo dispositivo na extração."""
    captures = conn.execute("""
        SELECT DISTINCT c.id, c.sha256 FROM capture c
        JOIN decision_document dd ON dd.capture_id=c.id
        JOIN decision d ON d.id=dd.decision_id
        WHERE d.court='STJ' AND c.source_id='stj' AND c.mime LIKE '%json%'
    """).fetchall()
    for cap in captures:
        try:
            raw = blobs.get_blob(cap["sha256"], home=home)
        except FileNotFoundError:
            # Snapshots declaradamente sem blobs conservam somente as extrações.
            continue
        data = json.loads(raw)
        records = data if isinstance(data, list) else [data]
        by_key = {}
        for item in records:
            if not isinstance(item, dict):
                raise ValueError("stj_recurso_invalido")
            key = str(item.get("id") or item.get("numeroDocumento") or "")
            if key in by_key:
                raise ValueError("stj_identidade_ambigua")
            by_key[key] = item
        rows = conn.execute("""
            SELECT DISTINCT d.id, d.official_id FROM decision d
            JOIN decision_document dd ON dd.decision_id=d.id
            WHERE dd.capture_id=? AND d.court='STJ'
        """, (cap["id"],)).fetchall()
        for decision in rows:
            item = by_key.get(decision["official_id"])
            if item is None:
                raise ValueError("stj_documento_ausente_no_recurso")
            text = item.get("ementa")
            if not text:
                continue
            if not isinstance(text, str):
                raise ValueError("stj_ementa_invalida")
            if conn.execute("""
                SELECT 1 FROM decision_document
                WHERE decision_id=? AND capture_id=? AND kind='ementa' AND text=?
            """, (decision["id"], cap["id"], text)).fetchone():
                continue
            conn.execute("""
                INSERT INTO decision_document
                    (id, decision_id, capture_id, kind, text, sha256, nivel_prova)
                VALUES (?,?,?,'ementa',?,?,'ementa_capturada')
            """, (new_ulid(), decision["id"], cap["id"], text,
                  hashlib.sha256(text.encode("utf-8")).hexdigest()))


def _staging_root(home: Path | None = None, staging_dir: str | Path | None = None) -> Path:
    configured = staging_dir or os.environ.get("FV_STAGING_DIR")
    root = Path(configured).expanduser().resolve() if configured else (home or data_home()) / "staging"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _new_staging(*, prefix: str, home: Path | None = None, staging_dir: str | Path | None = None) -> Path:
    root = _staging_root(home, staging_dir)
    # Herda as permissoes do diretorio configurado, inclusive no Windows.
    directory = root / (prefix + uuid4().hex)
    directory.mkdir()
    return directory


@contextmanager
def _temporary_staging(**kwargs):
    directory = _new_staging(**kwargs)
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def export_snapshot(
    conn: sqlite3.Connection,
    home: Path,
    destino: str | Path,
    *,
    atribuicoes: dict[str, str] | None = None,
    staging_dir: str | Path | None = None,
) -> dict[str, Any]:
    destino = Path(destino)
    if destino.name.endswith(".tar.gz"):
        if destino.exists():
            return {"status":"erro", "motivo":"destino_existente"}
        with _temporary_staging(prefix="fv-export-", home=home, staging_dir=staging_dir) as temporary:
            directory = Path(temporary)
            result = export_snapshot(conn, home, directory, atribuicoes=atribuicoes)
            if result["status"] != "ok":
                return result
            digest = pack_snapshot(directory, destino)
            return {**result, "destino":str(destino), "asset_sha256":digest}
    if destino.exists():
        if any(destino.iterdir()):
            return {
                "status": "erro",
                "motivo": "destino_nao_vazio",
                "destino": str(destino),
            }
    else:
        destino.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    db_name = f"freoa-verifica-corpus-{stamp}.db"
    export_db = destino / db_name
    # Alias M5
    legacy_db = destino / "verifica.sqlite3"

    out_conn = connect(export_db)
    derivados.definir(out_conn, derivados.versao(conn))  # o banco exportado herda a versão da origem
    out_conn.commit()
    for t in SNAPSHOT_TABLE_COLUMNS:
        try:
            out_conn.execute(f"DELETE FROM {t}")
        except sqlite3.Error:
            pass
    out_conn.commit()

    inventario: dict[str, list[str]] = {}
    for t, wanted_cols in SNAPSHOT_TABLE_COLUMNS.items():
        existing = {
            r[1]: r[0]
            for r in conn.execute(f"PRAGMA table_info({t})").fetchall()
        }
        cols = [c for c in wanted_cols if c in existing]
        inventario[t] = cols
        if not cols:
            continue
        col_list = ", ".join(cols)
        rows = conn.execute(f"SELECT {col_list} FROM {t}").fetchall()
        if not rows:
            continue
        placeholders = ",".join(["?"] * len(cols))
        out_conn.executemany(
            f"INSERT OR IGNORE INTO {t}({col_list}) VALUES ({placeholders})",
            [tuple(row) for row in rows],
        )
    from freoa_verifica.store.repo import rebuild_decision_index

    _restore_stj_ementas(out_conn, home)
    rebuild_decision_index(out_conn)
    out_conn.commit()

    # Blobs: se total > 1,5 GB, só texto extraído + hash + URL
    hashes = [
        r[0] for r in conn.execute("SELECT DISTINCT sha256 FROM capture").fetchall()
    ]
    total_size = 0
    sizes: dict[str, int] = {}
    for h in hashes:
        row = conn.execute(
            "SELECT size FROM capture WHERE sha256=? LIMIT 1", (h,)
        ).fetchone()
        sz = int(row[0]) if row and row[0] is not None else 0
        sizes[h] = sz
        total_size += sz

    blobs_completos = total_size <= BLOB_SIZE_LIMIT
    blob_dir = destino / "blobs"
    blob_dir.mkdir(exist_ok=True)
    blob_digests: dict[str, str] = {}
    blob_refs: list[dict[str, Any]] = []

    if blobs_completos:
        for h in hashes:
            try:
                data = blobs.get_blob(h, home=home)
                actual = hashlib.sha256(data).hexdigest()
                if actual != h:
                    out_conn.close()
                    return {"status": "erro", "motivo": f"blob_integridade:{h}"}
                target = blob_dir / h[:2] / h[2:4]
                target.mkdir(parents=True, exist_ok=True)
                (target / h).write_bytes(data)
                blob_digests[h] = actual
            except Exception:  # noqa: BLE001
                out_conn.close()
                return {"status": "erro", "motivo": f"blob_ausente_ou_invalido:{h}"}
    else:
        # Apenas referências: texto de extract + hash + URL
        for h in hashes:
            row = conn.execute(
                "SELECT c.url, c.final_url, e.text_sha256, e.parser_version "
                "FROM capture c LEFT JOIN extract e ON e.capture_id=c.id "
                "WHERE c.sha256=? LIMIT 1",
                (h,),
            ).fetchone()
            if row is None:
                continue
            blob_refs.append(
                {
                    "sha256": h,
                    "url": row[0],
                    "final_url": row[1],
                    "text_sha256": row[2],
                    "parser_version": row[3],
                    "modo": "texto_somente",
                }
            )
            blob_digests[h] = h

    out_conn.close()
    shutil.copy2(export_db, legacy_db)

    compressed = _compress(export_db, destino / db_name)
    db_sha256 = _sha256_file(export_db)

    from freoa_verifica import __version__
    from freoa_verifica.semente import load_corpus

    try:
        atrib = atribuicoes or load_corpus().get("atribuicoes") or {}
    except Exception:  # noqa: BLE001
        atrib = atribuicoes or {}

    esquema = [
        r[0] for r in conn.execute("SELECT version FROM schema_version").fetchall()
    ]

    file_hashes: dict[str, str] = {
        db_name: db_sha256,
        "verifica.sqlite3": _sha256_file(legacy_db),
        compressed.name: _sha256_file(compressed),
    }
    for f in blob_dir.rglob("*"):
        if f.is_file() and len(f.name) == 64:
            rel = f.relative_to(destino).as_posix()
            file_hashes[rel] = _sha256_file(f)

    manifest = {
        "formato": "freoa-verifica-snapshot-1",
        "gerado_em": _now(),
        "versao_pacote": __version__,
        "esquema": esquema,
        "esquema_minimo": max(esquema) if esquema else 0,
        "capturas": len(blob_digests),
        "obras": conn.execute("SELECT COUNT(*) FROM work").fetchone()[0],
        "decisoes": conn.execute("SELECT COUNT(*) FROM decision").fetchone()[0],
        **{k: v for k, v in acervo.manifest_fields(conn).items() if k not in ("obras", "decisoes", "db_sha256")},
        "hashes_blobs": sorted(blob_digests.keys()),
        "blob_sha256": blob_digests,
        "blobs_completos": blobs_completos,
        "blob_refs": blob_refs,
        "db_sha256": db_sha256,
        "db_arquivo": db_name,
        "db_compactado": compressed.name,
        "tabelas": list(SNAPSHOT_TABLE_COLUMNS.keys()),
        "inventario_colunas": inventario,
        "parser_version_por_capture": _parser_versions(conn),
        "cobertura_por_fonte": _cobertura(conn),
        "atribuicoes": atrib,
        "licenca_metadados": "CC-BY-4.0",
        "autenticidade": AUTHENTICITY_NOTE,
        "arquivos_sha256": file_hashes,
    }
    manifest_json = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
    manifest_path = destino / "MANIFEST.json"
    # Escrita binária evita conversão CRLF no Windows (hash divergiria).
    manifest_bytes = manifest_json.encode("utf-8")
    manifest_path.write_bytes(manifest_bytes)
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    (destino / "MANIFEST.sha256").write_bytes((digest + "\n").encode("ascii"))
    file_hashes["MANIFEST.json"] = digest

    # SHA256SUMS
    sums_lines = [f"{h}  {name}" for name, h in sorted(file_hashes.items())]
    (destino / "SHA256SUMS").write_bytes(("\n".join(sums_lines) + "\n").encode("utf-8"))

    return {
        "status": "ok",
        "destino": str(destino),
        "manifest_sha256": digest,
        "capturas": len(blob_digests),
        "db_sha256": db_sha256,
        "db_arquivo": db_name,
        "db_compactado": compressed.name,
        "blobs_completos": blobs_completos,
        "autenticidade": AUTHENTICITY_NOTE,
    }


def _find_db(origem: Path, manifest: dict[str, Any]) -> Path:
    named = manifest.get("db_arquivo")
    path = _safe_file(origem, named)
    expected = manifest.get("db_sha256")
    if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected):
        raise ValueError("db_sha256_obrigatorio")
    inventory = manifest.get("arquivos_sha256")
    if not isinstance(inventory, dict) or inventory.get(named) != expected:
        raise ValueError("banco_fora_do_inventario")
    if not path.is_file():
        raise FileNotFoundError("banco_ausente")
    if _sha256_file(path) != expected:
        raise ValueError("db_integridade")
    return path


def _safe_file(root: Path, name: str) -> Path:
    from pathlib import PurePosixPath
    if not isinstance(name, str) or "\\" in name or ":" in name:
        raise ValueError("caminho_invalido")
    rel = PurePosixPath(name)
    if rel.is_absolute() or any(p in {"..", ".", ""} for p in name.split("/")):
        raise ValueError("caminho_externo")
    target = root / name
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("caminho_externo")
    for part in [target, *target.parents]:
        if part == root.parent:
            break
        if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
            raise ValueError("link_nao_permitido")
    return target


def _verify_sums(origem: Path, manifest: dict[str, Any]) -> str | None:
    try:
        _find_db(origem, manifest)
        expected = manifest["arquivos_sha256"]
        if not isinstance(expected, dict) or not expected:
            return "inventario_ausente"
        sums = {}
        for line in (origem / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
            digest, name = line.split("  ", 1)
            if name in sums:
                return "sums_duplicado"
            sums[name] = digest
        wanted = {**expected, "MANIFEST.json": _sha256_file(origem / "MANIFEST.json")}
        if sums != wanted:
            return "inventario_divergente"
        allowed = set(wanted) | {"SHA256SUMS", "MANIFEST.sha256"}
        for name, digest in wanted.items():
            path = _safe_file(origem, name)
            if not path.is_file():
                return f"arquivo_ausente:{name}"
            if _sha256_file(path) != digest:
                return f"sha256_divergente:{name}"
        for path in origem.rglob("*"):
            name = path.relative_to(origem).as_posix()
            _safe_file(origem, name)
            if path.is_file() and name not in allowed:
                return f"arquivo_extra:{name}"
            if path.is_dir() and name != "blobs" and not any(n.startswith(name + "/") for n in allowed):
                return f"diretorio_extra:{name}"
        if manifest.get("blobs_completos"):
            for h in manifest["hashes_blobs"]:
                name = f"blobs/{h[:2]}/{h[2:4]}/{h}"
                if expected.get(name) != h:
                    return f"blob_ausente:{h}"
        return None
    except (ValueError, KeyError, TypeError, OSError):
        return "inventario_invalido"


def _versao_derivados(conn: sqlite3.Connection, schema: str) -> int | None:
    try:
        row = conn.execute(f"SELECT value FROM {schema}.meta WHERE key='derived_version'").fetchone()
        return int(row[0]) if row else None
    except (sqlite3.Error, ValueError):
        return None


def _reconstruir_derivados_substituidos(conn: sqlite3.Connection, capturas: list[str]) -> None:
    """Regrava provisions, redações e ocorrências dos documentos cujo modelo o snapshot substituiu."""
    from freoa_verifica.parsers.model import document_from_dict
    from freoa_verifica.store.repo import sincronizar_derivados

    for cid in capturas:
        row = conn.execute("SELECT model_json, work_id FROM main.parsed_document WHERE capture_id=?",
                           (cid,)).fetchone()
        if not row or not row["model_json"] or not row["work_id"]:
            continue
        ext = conn.execute("SELECT id FROM main.extract WHERE capture_id=? ORDER BY created_at DESC, id DESC LIMIT 1",
                           (cid,)).fetchone()
        sincronizar_derivados(conn, capture_id=cid, work_id=row["work_id"],
                              document=document_from_dict(json.loads(row["model_json"])),
                              extract_id=ext["id"] if ext else None)


def _merge_attach(live_db: Path, snap_db: Path) -> None:
    """Anexa dados publicos, remapeando identidades naturais ja existentes."""
    conn = sqlite3.connect(str(live_db))
    conn.row_factory = sqlite3.Row
    natural = {
        "source": ("id",), "work": ("jurisdiction", "authority", "kind", "number", "year"),
        "provision": ("work_id", "scope", "path"),
        "capture": ("sha256", "url", "fetched_at"), "decision": ("court", "official_id"),
        "alias": ("scheme", "value"),
    }
    mappings = {}
    try:
        conn.execute("ATTACH DATABASE ? AS snap", (str(snap_db),))
        local_dv = derivados.versao(conn)
        snap_dv = _versao_derivados(conn, "snap")
        # C6: snapshot de derivados mais novos substitui os modelos locais.
        substituir = (snap_dv or 0) > (local_dv or 0)
        substituidas: list[str] = []
        for table, columns in SNAPSHOT_TABLE_COLUMNS.items():
            fks = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
            rows = conn.execute(f"SELECT {', '.join(columns)} FROM snap.{table}").fetchall()
            table_map = mappings.setdefault(table, {})
            for row in rows:
                values = dict(row)
                for fk in fks:
                    values[fk[3]] = mappings.get(fk[2], {}).get(values[fk[3]], values[fk[3]])
                old_id = row["id"] if "id" in columns else None
                key = natural.get(table)
                existing = None
                if key and all(values[k] is not None for k in key):
                    where = " AND ".join(f"{k}=?" for k in key)
                    existing = conn.execute(f"SELECT * FROM main.{table} WHERE {where}",
                                            [values[k] for k in key]).fetchone()
                if existing is not None:
                    if table == "capture" and existing["source_id"] != values["source_id"]:
                        raise ValueError("conflito_identidade_captura")
                    if old_id:
                        table_map[old_id] = existing["id"]
                    continue
                col_list = ", ".join(columns)
                placeholders = ",".join("?" for _ in columns)
                modo = "OR REPLACE" if table == "parsed_document" and substituir else "OR IGNORE"
                conn.execute(f"INSERT {modo} INTO main.{table}({col_list}) VALUES ({placeholders})",
                             [values[c] for c in columns])
                if table == "parsed_document":
                    substituidas.append(values["capture_id"])
                if old_id:
                    table_map[old_id] = values["id"]
        if conn.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("snapshot_relacoes_invalidas")
        from freoa_verifica.rotulos import corrigir_rotulos
        corrigir_rotulos(conn)
        if substituir:
            _reconstruir_derivados_substituidos(conn, substituidas)
        # C6: o FTS só leva as redações do modelo atual (nunca as de modelos substituídos).
        derivados.reindexar_fts(conn)
        # Versão do home: a do snapshot só vale se nenhum modelo local ficou para trás.
        if substituir:
            chaves = {tuple(r) for r in conn.execute(
                "SELECT sha256, url, fetched_at FROM snap.capture WHERE id IN "
                "(SELECT capture_id FROM snap.parsed_document)")}
            fora = any(tuple(r) not in chaves for r in conn.execute(
                "SELECT c.sha256, c.url, c.fetched_at FROM main.parsed_document pd "
                "JOIN main.capture c ON c.id=pd.capture_id WHERE pd.model_json IS NOT NULL"))
            if not fora:
                derivados.definir(conn, snap_dv)
        elif (snap_dv or 0) < (local_dv or 0):
            derivados.definir(conn, snap_dv)  # dados de derivados antigos entraram: home volta a incompatível
        from freoa_verifica.store.repo import rebuild_decision_index
        rebuild_decision_index(conn)
        conn.commit()
    finally:
        conn.close()


def install_snapshot(
    svc: Any,
    origem: str | Path | None = None,
    *,
    url: str | None = None,
) -> dict[str, Any]:
    """Instala o snapshot com acesso exclusivo: espera as operações ativas terminarem."""
    try:
        with svc.exclusivo():
            return _install_snapshot(svc, origem, url=url)
    except TimeoutError as exc:
        return {"status": "erro", "motivo": str(exc)}


def _install_snapshot(
    svc: Any,
    origem: str | Path | None = None,
    *,
    url: str | None = None,
) -> dict[str, Any]:
    staging_download: Path | None = None
    try:
        if url:
            origem_path = _download_release(url, staging_dir=_staging_root(svc.home))
            staging_download = origem_path
        elif origem is not None:
            origem_path = Path(origem)
            if origem_path.is_file():
                checksum = Path(str(origem_path) + ".sha256")
                if checksum.exists():
                    expected = checksum.read_text(encoding="utf-8").split()
                    if not expected or expected[0] != _sha256_file(origem_path):
                        raise ValueError("asset_integridade")
                staging_download = _new_staging(prefix="fv-snap-local-", home=svc.home)
                _extract_archive(origem_path, staging_download)
                origem_path = staging_download
        else:
            origem_path = _download_latest_release(staging_dir=_staging_root(svc.home))
            staging_download = origem_path

        return _install_from_dir(svc, origem_path)
    except Unavailable as exc:
        return {"status": "erro", "motivo": exc.reason}
    except (ValueError, OSError, RuntimeError, tarfile.TarError) as exc:
        return {"status": "erro", "motivo": str(exc) or type(exc).__name__}
    finally:
        if staging_download is not None:
            shutil.rmtree(staging_download, ignore_errors=True)


def _download_latest_release(*, staging_dir: str | Path | None = None) -> Path:
    """Baixa asset da última release via API GitHub (hosts permitidos)."""
    from freoa_verifica.connectors.httputil import connector_fetch

    api = "https://api.github.com/repos/rickfreoa/freoa-verifica/releases/latest"
    resp = connector_fetch(
        api,
        hosts=GITHUB_HOSTS,
        path_prefixes=GITHUB_PREFIXES,
        mimes=GITHUB_MIMES,
        user_agent="identified",
        timeout=60.0,
        max_bytes=5 * 1024 * 1024,
    )
    data = json.loads(resp.body.decode("utf-8"))
    def choose(release):
        if release.get("draft") or release.get("prerelease"):
            return None
        assets = release.get("assets") or []
        for asset in assets:
            name = str(asset.get("name") or "")
            if re.fullmatch(r"freoa-verifica-snapshot-[A-Za-z0-9][A-Za-z0-9._-]*\.tar\.gz", name):
                return asset["browser_download_url"]
        return None

    chosen = choose(data)
    if chosen:
        return _download_release(chosen, staging_dir=staging_dir)
    # A API lista as releases da mais recente para a mais antiga.
    page = 1
    while True:
        resp = connector_fetch(
            api.removesuffix("/latest") + f"?per_page=100&page={page}",
            hosts=GITHUB_HOSTS, path_prefixes=GITHUB_PREFIXES,
            mimes=GITHUB_MIMES, user_agent="identified", timeout=60.0,
            max_bytes=5 * 1024 * 1024,
        )
        releases = json.loads(resp.body.decode("utf-8"))
        if not isinstance(releases, list):
            raise RuntimeError("releases_resposta_inesperada")
        for release in releases:
            chosen = choose(release)
            if chosen:
                return _download_release(chosen, staging_dir=staging_dir)
        if len(releases) < 100:
            raise RuntimeError("release_sem_assets")
        page += 1


def _download_release(url: str, *, staging_dir: str | Path | None = None) -> Path:
    from freoa_verifica.connectors.httputil import connector_fetch

    parsed = urlparse(url)
    host = parsed.hostname or ""
    if host not in GITHUB_HOSTS:
        raise RuntimeError(f"host_nao_permitido:{host}")
    staging = _new_staging(prefix="fv-snap-dl-", staging_dir=staging_dir)
    try:
        raw = staging / "asset.tar.gz"
        resp = connector_fetch(
            url, hosts=GITHUB_HOSTS, path_prefixes=GITHUB_PREFIXES,
            mimes=frozenset({"application/octet-stream", "application/gzip"}),
            user_agent="identified", timeout=1800.0,
            max_bytes=4 * 1024**3, sink=raw,
        )
        checksum = connector_fetch(
            url + ".sha256", hosts=GITHUB_HOSTS, path_prefixes=GITHUB_PREFIXES,
            mimes=GITHUB_MIMES, user_agent="identified", timeout=60, max_bytes=4096,
        ).body.decode("utf-8").split()
        if not checksum or not re.fullmatch(r"[0-9a-fA-F]{64}", checksum[0]) or checksum[0].lower() != resp.sha256:
            raise ValueError("asset_integridade")
        out = staging / "snap"
        out.mkdir()
        _extract_archive(raw, out)
        raw.unlink()
        # Retorna a raiz para que o chamador remova todo o temporário.
        for child in out.iterdir():
            shutil.move(str(child), staging / child.name)
        out.rmdir()
        return staging
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


ARCHIVE_SIZE_LIMIT = 2 * 1024 * 1024 * 1024


def _extract_archive(archive: Path, dest: Path) -> None:
    if archive.name.endswith(".zip"):
        import zipfile
        with zipfile.ZipFile(archive) as z:
            total = 0
            for entry in z.infolist():
                _safe_file(dest, entry.filename.rstrip("/"))
                total += entry.file_size
                if total > ARCHIVE_SIZE_LIMIT or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("entrada_nao_permitida")
            z.extractall(dest)
        return
    total = 0
    seen = set()
    with tarfile.open(archive, "r:gz") as tar:
        for entry in tar:
            name = entry.name.rstrip("/")
            target = _safe_file(dest, name)
            if name in seen or not (entry.isfile() or entry.isdir()):
                raise ValueError("entrada_nao_permitida")
            seen.add(name)
            total += entry.size
            if entry.size < 0 or total > ARCHIVE_SIZE_LIMIT:
                raise ValueError("tamanho_excedido")
            if entry.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(entry) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)


def pack_snapshot(directory: Path, archive: Path) -> str:
    """Empacota inventário validado e grava checksum externo do asset."""
    manifest = json.loads((directory / "MANIFEST.json").read_text(encoding="utf-8"))
    error = _verify_sums(directory, manifest)
    if error:
        raise ValueError(error)
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "w:gz") as tar:
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                tar.add(path, arcname=path.relative_to(directory).as_posix(), recursive=False)
    digest = _sha256_file(archive)
    Path(str(archive) + ".sha256").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    return digest


def _install_from_dir(svc: Any, origem: Path) -> dict[str, Any]:
    origem = Path(origem)
    manifest_path = origem / "MANIFEST.json"
    sha_path = origem / "MANIFEST.sha256"
    if not manifest_path.is_file():
        return {"status": "erro", "motivo": "manifesto_ausente"}
    raw = manifest_path.read_text(encoding="utf-8")
    if sha_path.is_file():
        expected = sha_path.read_text(encoding="utf-8").strip().split()[0]
        got = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        if got != expected:
            return {"status": "erro", "motivo": "manifesto_integridade"}
    try:
        manifest = json.loads(raw)
    except ValueError:
        return {"status": "erro", "motivo": "manifesto_invalido"}
    sum_err = _verify_sums(origem, manifest)
    if sum_err:
        return {"status": "erro", "motivo": sum_err}

    local_schema = sorted(
        r[0] for r in svc.conn.execute("SELECT version FROM schema_version").fetchall()
    )
    snap_schema = manifest.get("esquema")
    # Aceita esquema igual ou anterior (prefixo): as migrações faltantes rodam na área de staging.
    if (not isinstance(snap_schema, list) or not snap_schema
            or sorted(snap_schema) != local_schema[:len(snap_schema)]):
        return {"status": "erro", "motivo": "esquema_incompativel",
                "detalhe": f"snapshot {snap_schema}, local {local_schema}"}

    try:
        db_src = _find_db(origem, manifest)
    except FileNotFoundError:
        return {"status": "erro", "motivo": "banco_ausente"}

    db_sha = _sha256_file(db_src)
    expected_db = manifest.get("db_sha256")
    if expected_db and db_sha != expected_db:
        return {"status": "erro", "motivo": "db_integridade"}

    # Mesmo volume do destino para que cada troca use rename atomico.
    staging = _new_staging(prefix="fv-snap-", home=svc.home)
    staging_db = staging / "verifica.sqlite3"
    staging_blobs = staging / "blobs"
    backup_db = svc.home / f"verifica.sqlite3.bak-{new_ulid()}"
    backup_blobs = svc.home / f"blobs.bak-{new_ulid()}"
    db_dst = svc.home / "verifica.sqlite3"
    live_blobs = svc.home / "blobs"

    db_saved = blobs_saved = db_installed = blobs_installed = False
    closed = False
    try:
        shutil.copy2(db_src, staging_db)

        blob_map = manifest.get("blob_sha256") or {
            h: h for h in (manifest.get("hashes_blobs") or [])
        }
        src_blobs = origem / "blobs"
        if src_blobs.is_dir():
            for f in src_blobs.rglob("*"):
                if not f.is_file() or len(f.name) != 64:
                    continue
                data = f.read_bytes()
                actual = hashlib.sha256(data).hexdigest()
                expected_blob = blob_map.get(f.name)
                if expected_blob and actual != expected_blob:
                    raise ValueError(f"blob_integridade:{f.name}")
                if actual != f.name.lower():
                    raise ValueError(f"blob_nome:{f.name}")
                dest = staging_blobs / f.name[:2] / f.name[2:4]
                dest.mkdir(parents=True, exist_ok=True)
                (dest / f.name).write_bytes(data)

        # Também recupera snapshots antigos cujo índice derivado veio vazio.
        from freoa_verifica.store.repo import rebuild_decision_index
        staged_conn = connect(staging_db)
        try:
            _restore_stj_ementas(staged_conn, staging)
            rebuild_decision_index(staged_conn)
            staged_conn.commit()
        finally:
            staged_conn.close()

        # Preparar a anexacao e todas as evidencias sem escrever no destino.
        merged_db = staging / "merged.sqlite3"
        merged_conn = sqlite3.connect(str(merged_db))
        try:
            svc.conn.backup(merged_conn)
        finally:
            merged_conn.close()
        _merge_attach(merged_db, staging_db)
        merged_blobs = staging / "merged-blobs"
        if live_blobs.is_dir():
            shutil.copytree(live_blobs, merged_blobs, copy_function=shutil.copy2)
        else:
            merged_blobs.mkdir()
        if staging_blobs.is_dir():
            for f in staging_blobs.rglob("*"):
                if not f.is_file():
                    continue
                dest = merged_blobs / f.relative_to(staging_blobs)
                if dest.exists():
                    if _sha256_file(dest) != f.name:
                        raise ValueError(f"blob_local_integridade:{f.name}")
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
        # C6: derivados fora da versão atual (snapshot v1.0.2, sem derived_version) são reconstruídos
        # aqui, no staging, antes da troca.
        probe = sqlite3.connect(str(merged_db))
        try:
            reconstruir = not derivados.compativel(probe)
        finally:
            probe.close()
        if reconstruir:
            rebuild = staging / "rebuild"
            rebuild.mkdir()
            os.replace(merged_db, rebuild / "verifica.sqlite3")
            (rebuild / "blobs").symlink_to(merged_blobs, target_is_directory=True)
            try:
                derivados.reprocessar_pasta(rebuild)
            finally:
                os.replace(rebuild / "verifica.sqlite3", merged_db)
        check = sqlite3.connect(str(merged_db))
        try:
            if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("snapshot_banco_invalido")
            if check.execute("PRAGMA foreign_key_check").fetchone():
                raise ValueError("snapshot_relacoes_invalidas")
        finally:
            check.close()

        # So agora fechar e guardar os originais completos antes de publicar.
        svc._close_all_conns(strict=True)
        closed = True
        if db_dst.exists():
            os.replace(db_dst, backup_db)
            db_saved = True
        if live_blobs.exists():
            os.replace(live_blobs, backup_blobs)
            blobs_saved = True
        os.replace(merged_db, db_dst)
        db_installed = True
        os.replace(merged_blobs, live_blobs)
        blobs_installed = True

        svc._db_path = db_dst
        svc._clear_caches()
        svc.conn = connect(db_dst)
        acervo.save_installed(svc.home, manifest)
        return {
            "status": "ok",
            "backup": str(backup_db) if backup_db.exists() else None,
            "backup_blobs": str(backup_blobs) if blobs_saved else None,
            "obras": manifest.get("obras"),
            "capturas": manifest.get("capturas"),
            "modo": "anexacao",
            "autenticidade": AUTHENTICITY_NOTE,
        }
    except Exception as exc:  # noqa: BLE001
        mutated = db_saved or blobs_saved or db_installed or blobs_installed
        result = {"status": "erro", "motivo": str(exc)[:200], "rollback": False}
        if not closed:
            return result
        svc._close_all_conns()
        try:
            # Remover apenas componentes novos efetivamente publicados.
            if db_installed:
                db_dst.unlink(missing_ok=True)
                for suffix in ("-wal", "-shm"):
                    Path(str(db_dst) + suffix).unlink(missing_ok=True)
            if blobs_installed:
                shutil.rmtree(live_blobs)
            if db_saved:
                os.replace(backup_db, db_dst)
            if blobs_saved:
                os.replace(backup_blobs, live_blobs)
            result["rollback"] = mutated
        except Exception as rollback_exc:  # noqa: BLE001
            # Nao anunciar restauracao se ela falhou; preservar os backups.
            result["rollback_error"] = str(rollback_exc)[:200]
            result["backup"] = str(backup_db)
            result["backup_blobs"] = str(backup_blobs)
        svc._clear_caches()
        try:
            svc.conn = connect(db_dst)
        except Exception as reopen_exc:  # noqa: BLE001
            result["reopen_error"] = str(reopen_exc)[:200]
        return result
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def snapshot_info(svc: Any, origem: str | Path | None = None) -> dict[str, Any]:
    if origem is None:
        return {
            "home": str(svc.home),
            "obras": svc.conn.execute("SELECT COUNT(*) FROM work").fetchone()[0],
            "capturas": svc.conn.execute("SELECT COUNT(*) FROM capture").fetchone()[0],
            "decisoes": svc.conn.execute("SELECT COUNT(*) FROM decision").fetchone()[0],
            "autenticidade": AUTHENTICITY_NOTE,
        }
    origem = Path(origem)
    manifest_path = origem / "MANIFEST.json"
    if not manifest_path.is_file():
        return {"status": "erro", "motivo": "manifesto_ausente"}
    return json.loads(manifest_path.read_text(encoding="utf-8"))
