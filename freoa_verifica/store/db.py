"""Abertura do SQLite, pragmas e migrações numeradas."""

from __future__ import annotations

import os
import sqlite3
from importlib import resources
from pathlib import Path


def data_home() -> Path:
    """Diretório de dados: FV_HOME, senão LOCALAPPDATA/XDG_DATA_HOME."""
    override = os.environ.get("FV_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "freoa-verifica"
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "freoa-verifica"
    return Path.home() / ".local" / "share" / "freoa-verifica"


def _migration_files() -> list[tuple[int, str]]:
    root = resources.files("freoa_verifica.store").joinpath("migrations")
    items: list[tuple[int, str]] = []
    for entry in root.iterdir():
        name = entry.name
        if not name.endswith(".sql"):
            continue
        prefix = name.split("_", 1)[0]
        if not prefix.isdigit():
            continue
        items.append((int(prefix), entry.read_text(encoding="utf-8")))
    items.sort(key=lambda item: item[0])
    return items


def split_sql_statements(sql: str) -> list[str]:
    """Divide script SQL em instruções (ignora `--`; preserva blocos TRIGGER)."""
    statements: list[str] = []
    current: list[str] = []
    in_trigger = False
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        upper = stripped.upper()
        if upper.startswith("CREATE TRIGGER"):
            in_trigger = True
        current.append(line)
        if in_trigger:
            if upper == "END;" or upper.endswith(" END;"):
                stmt = "\n".join(current).strip()
                if stmt:
                    statements.append(stmt)
                current = []
                in_trigger = False
            continue
        if line.rstrip().endswith(";"):
            stmt = "\n".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
    tail = "\n".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Aplica migrações pendentes de forma atômica (BEGIN IMMEDIATE)."""
    previous = conn.isolation_level
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_version ("
                "version INTEGER PRIMARY KEY, "
                "applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
                ")"
            )
            # Relê versões dentro da transação (serializa inicializações concorrentes).
            current = {
                row[0]
                for row in conn.execute("SELECT version FROM schema_version").fetchall()
            }
            for version, sql in _migration_files():
                if version in current:
                    continue
                for statement in split_sql_statements(sql):
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO schema_version(version) VALUES (?)", (version,)
                )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.isolation_level = previous


def connect(path: Path | str | None = None, *, busy_timeout_ms: int = 30_000, check_same_thread: bool = True) -> sqlite3.Connection:
    """Abre SQLite com foreign_keys, WAL e migrações aplicadas."""
    if path is None:
        home = data_home()
        home.mkdir(parents=True, exist_ok=True)
        path = home / "verifica.sqlite3"
    else:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=busy_timeout_ms / 1000, check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    apply_migrations(conn)
    return conn
