"""Rótulos CVM com mojibake (UTF-8 lido como latin-1), já gravados ou recém-chegados (M11)."""

from __future__ import annotations

import re
import sqlite3

# Ã e Â e controles C1 são os restos típicos de UTF-8 decodificado como latin-1.
_SUSPEITOS = re.compile(r"[ÃÂ\x80-\x9f]")


def _suspeitos(texto: str) -> int:
    return len(_SUSPEITOS.findall(texto))


def corrigir_mojibake(texto: str) -> str:
    """Reverte UTF-8 lido como latin-1 só se a reversão é UTF-8 válido e reduz suspeitos."""
    if not texto or not _suspeitos(texto):
        return texto
    try:
        revertido = texto.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return texto
    if "�" in revertido or _suspeitos(revertido) >= _suspeitos(texto):
        return texto
    return revertido


def corrigir_rotulos(conn: sqlite3.Connection) -> int:
    """Corrige work.label das normas CVM e o rótulo replicado no FTS; devolve quantas obras mudaram."""
    corrigidos = 0
    rows = conn.execute(
        "SELECT id, label FROM work WHERE authority='cvm' AND label IS NOT NULL"
    ).fetchall()
    for wid, antigo in rows:
        novo = corrigir_mojibake(antigo)
        if novo == antigo:
            continue
        conn.execute("UPDATE work SET label=? WHERE id=?", (novo, wid))
        conn.execute("UPDATE fts_redaction SET work_label=? WHERE work_label=?", (novo, antigo))
        corrigidos += 1
    return corrigidos
