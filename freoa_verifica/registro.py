"""Política de registro de entradas (C5/F09) e purga de execuções antigas."""

from __future__ import annotations

import contextvars
import json
import os
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

POLITICAS = ("completo", "sem_conteudo")

# Política da operação em curso; definida pela fachada em cada chamada pública.
politica_atual: contextvars.ContextVar[str] = contextvars.ContextVar("fv_registro", default="completo")


def normalizar(valor: str | None) -> str:
    v = (valor or os.environ.get("FV_REGISTRO") or "completo").strip().lower()
    if v not in POLITICAS:
        raise ValueError(f"registro inválido: {v!r} (use {', '.join(POLITICAS)})")
    return v


def purgar(home: Path, antes: str) -> dict[str, Any]:
    """Reconstrói o banco sem as execuções anteriores a `antes` (AAAA-MM-DD).

    Requer acesso exclusivo (o chamador fecha as conexões). O banco original
    (com -wal/-shm) vai para `purgados/<data>/` no home; apagá-lo, e a seus
    backups externos, é responsabilidade do operador.
    """
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", antes):
        raise ValueError("data inválida: use AAAA-MM-DD")
    home = Path(home)
    db = home / "verifica.sqlite3"
    novo = home / "verifica.sqlite3.purga-novo"
    novo.unlink(missing_ok=True)
    src = sqlite3.connect(str(db))
    try:
        src.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        dst = sqlite3.connect(str(novo))
        try:
            src.backup(dst)
            trig = dst.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND tbl_name='run'"
            ).fetchall()
            for name, _ in trig:
                dst.execute(f'DROP TRIGGER "{name}"')
            n = dst.execute("DELETE FROM run WHERE created_at < ?", (antes,)).rowcount
            for _, sql in trig:
                dst.execute(sql)
            dst.commit()
            if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("purga: integridade do banco novo falhou")
            restantes = dst.execute("SELECT COUNT(*) FROM run").fetchone()[0]
            dst.execute("VACUUM")
        finally:
            dst.close()
    except Exception:
        novo.unlink(missing_ok=True)
        raise
    finally:
        src.close()
    agora = datetime.now(timezone.utc)
    pasta = home / "purgados" / agora.strftime("%Y-%m-%dT%H%M%S-%f")
    pasta.mkdir(parents=True)
    movidos = []
    for suf in ("", "-wal", "-shm"):
        f = Path(str(db) + suf)
        if f.exists():
            shutil.move(str(f), str(pasta / f.name))
            movidos.append(str(pasta / f.name))
    os.replace(novo, db)
    registro = {"em": agora.isoformat(), "antes": antes, "removidas": n, "restantes": restantes,
                "original_movido_para": movidos}
    with (home / "purgas.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(registro, ensure_ascii=False) + "\n")
    return {"status": "ok", **registro, "apagar_manualmente": movidos}
