"""Acervo efetivo (contrato C7): manifesto do snapshot x conteúdo do home."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

MANIFESTO_LOCAL = "acervo-manifesto.json"
# Mínimo embutido na versão, usado quando nenhum snapshot foi instalado.
# shortcut: valor-guarda (home vazio alerta); fixar com os totais do snapshot
# publicado a cada release.
MINIMO_EMBUTIDO = {"obras": 1, "decisoes": 0}

_OBRAS_SQL = "SELECT authority||':'||kind||':'||number||'/'||year FROM work"
_DECISOES_SQL = (
    "SELECT court||'|'||COALESCE(class,'')||'|'||COALESCE(number,'')||'|'||"
    "COALESCE(judgment_date,'')||'|'||kind FROM decision"
)


def _ids(conn: sqlite3.Connection, sql: str) -> list[str]:
    return sorted(r[0] for r in conn.execute(sql).fetchall())


def _digest(ids: list[str]) -> str:
    return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()


def derived_version(conn: sqlite3.Connection) -> str | None:
    try:
        row = conn.execute("SELECT value FROM meta WHERE key='derived_version'").fetchone()
    except sqlite3.Error:
        return None
    return str(row[0]) if row else None


def manifest_fields(conn: sqlite3.Connection, db_sha256: str | None = None) -> dict[str, Any]:
    """Campos do manifesto publicados pelo snapshot (obras, decisões, derivados, hashes)."""
    obras, decisoes = _ids(conn, _OBRAS_SQL), _ids(conn, _DECISOES_SQL)
    return {
        "obras": len(obras),
        "decisoes": len(decisoes),
        "derived_version": derived_version(conn),
        "obras_ids": obras,
        "obras_ids_sha256": _digest(obras),
        "decisoes_ids_sha256": _digest(decisoes),
        "db_sha256": db_sha256,
    }


def save_installed(home: Path, manifest: dict[str, Any]) -> None:
    keys = ("obras", "decisoes", "derived_version", "obras_ids", "obras_ids_sha256",
            "decisoes_ids_sha256", "db_sha256", "vinculado", "snapshot_sha256", "snapshot_derived_version",
            "vinculo_motivo")
    (Path(home) / MANIFESTO_LOCAL).write_text(
        json.dumps({k: manifest.get(k) for k in keys}, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def status(conn: sqlite3.Connection, home: Path) -> dict[str, Any] | None:
    """None se o acervo atende ao manifesto instalado (ou ao mínimo); senão o aviso."""
    path = Path(home) / MANIFESTO_LOCAL
    try:
        ref = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    except (OSError, ValueError):
        ref = None
    origem = "snapshot_instalado" if ref else "minimo_embutido"
    ref = ref or MINIMO_EMBUTIDO
    obras, decisoes = _ids(conn, _OBRAS_SQL), _ids(conn, _DECISOES_SQL)
    motivos: list[str] = []
    if len(obras) < int(ref.get("obras") or 0):
        motivos.append("obras_abaixo_do_manifesto")
    if len(decisoes) < int(ref.get("decisoes") or 0):
        motivos.append("decisoes_abaixo_do_manifesto")
    if ref.get("obras_ids") is not None:
        if set(ref["obras_ids"]) - set(obras):
            motivos.append("obras_ausentes_do_manifesto")
    elif ref.get("obras_ids_sha256") and len(obras) == ref.get("obras") and _digest(obras) != ref["obras_ids_sha256"]:
        motivos.append("obras_ids_divergentes")
    if (ref.get("decisoes_ids_sha256") and len(decisoes) == ref.get("decisoes")
            and _digest(decisoes) != ref["decisoes_ids_sha256"]):
        motivos.append("decisoes_ids_divergentes")
    dv = ref.get("derived_version")
    if dv is not None and derived_version(conn) != str(dv):
        motivos.append("derived_version_divergente")
    from freoa_verifica.derivados import compativel

    if not compativel(conn):
        motivos.append("derivados_desatualizados")
    from freoa_verifica.derivados import REASON_NAO_PUBLICADA, origem_nao_publicada

    if origem_nao_publicada(conn):
        motivos.append(REASON_NAO_PUBLICADA)
    if not motivos:
        return None
    return {
        "codigo": "acervo_incompleto",
        "referencia": origem,
        "motivos": motivos,
        "obras": len(obras),
        "decisoes": len(decisoes),
    }


def installed_provenance(home: Path) -> dict[str, Any]:
    try:
        data = json.loads((Path(home) / MANIFESTO_LOCAL).read_text(encoding="utf-8"))
        return {k: data.get(k) for k in ("vinculado", "snapshot_sha256", "snapshot_derived_version", "vinculo_motivo")}
    except (OSError, ValueError, AttributeError):
        return {"vinculado": False}
