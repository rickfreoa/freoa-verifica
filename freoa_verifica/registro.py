"""Política de registro de entradas (C5/F09) e purga de execuções antigas."""

from __future__ import annotations

import contextvars
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

POLITICAS = ("completo", "sem_conteudo")

# Política da operação em curso; definida pela fachada em cada chamada pública.
PADRAO = "sem_conteudo"  # decisão 0040: `completo` só por opção explícita
politica_atual: contextvars.ContextVar[str] = contextvars.ContextVar("fv_registro", default=PADRAO)


def normalizar(valor: str | None) -> str:
    v = (valor or os.environ.get("FV_REGISTRO") or PADRAO).strip().lower()
    if v not in POLITICAS:
        raise ValueError(f"registro inválido: {v!r} (use {', '.join(POLITICAS)})")
    return v


ARQUIVO_CHAVE = "registro.key"
PREFIXO_HMAC = "hmac1:"  # versão do esquema; hashes antigos são sha256 puro (64 hex, sem prefixo)
_chaves_efemeras: dict[str, bytes] = {}


def chave_do_home(home: Path) -> bytes:
    """Segredo de 32 bytes do home (`<home>/registro.key`), criado atomicamente com O_EXCL e modo 0o600.

    Windows: o modo POSIX não se aplica; a proteção vem da ACL herdada da pasta do perfil
    (%LOCALAPPDATA%). Chave corrompida nunca é regenerada em silêncio: os hashes antigos
    deixariam de casar, então o serviço recusa gravar.
    """
    caminho = Path(home) / ARQUIVO_CHAVE
    try:
        fd = os.open(str(caminho), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        for _ in range(50):  # outro processo pode estar entre o open e o write
            chave = caminho.read_bytes()
            if len(chave) == 32:
                return chave
            time.sleep(0.02)
        raise RuntimeError(f"{caminho} corrompida (esperado 32 bytes); remova-a ciente de que hashes antigos deixam de casar")
    chave = secrets.token_bytes(32)
    with os.fdopen(fd, "wb") as fh:
        fh.write(chave)
        fh.flush()
        os.fsync(fh.fileno())
    return chave


def _home_da_conexao(conn: sqlite3.Connection) -> Path | None:
    arquivo = next((r[2] for r in conn.execute("PRAGMA database_list") if r[1] == "main"), "")
    return Path(arquivo).parent if arquivo else None


def hmac_entrada(conn: sqlite3.Connection, campo: str, valor: str) -> str:
    """HMAC-SHA256 de conteúdo de entrada do usuário, com segredo do home e separação por campo.

    Só para entradas (citação, trecho, requisição). Hash de evidência pública (bytes de documento
    oficial, capturas) segue sha256 puro: é verificável por qualquer pessoa.
    """
    home = _home_da_conexao(conn)
    chave = chave_do_home(home) if home else _chaves_efemeras.setdefault(str(id(conn)), secrets.token_bytes(32))
    mac = hmac.new(chave, campo.encode("utf-8") + b"\0" + valor.encode("utf-8"), hashlib.sha256)
    return PREFIXO_HMAC + mac.hexdigest()


def _fsync_arquivo(caminho: Path) -> None:
    with open(caminho, "r+b") as fh:  # Windows: fsync exige descritor gravável
        os.fsync(fh.fileno())


def _fsync_pasta(pasta: Path) -> None:
    if os.name == "nt":
        return
    fd = os.open(str(pasta), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def recuperar_purga(home: Path) -> bool:
    """Conclui uma purga interrompida entre mover o original e instalar o banco novo.

    O banco novo só existe pronto (íntegro e gravado em disco) quando o original é movido; portanto,
    sem `verifica.sqlite3` e com `verifica.sqlite3.purga-novo`, basta concluir a troca.
    """
    home = Path(home)
    db = home / "verifica.sqlite3"
    novo = home / "verifica.sqlite3.purga-novo"
    if db.exists() or not novo.exists():
        return False
    for suf in ("-wal", "-shm"):  # restos do original não podem acompanhar o banco novo
        resto = Path(str(db) + suf)
        if resto.exists():
            destino = home / "purgados" / "recuperado"
            destino.mkdir(parents=True, exist_ok=True)
            shutil.move(str(resto), str(destino / f"{resto.name}.{datetime.now(timezone.utc):%Y%m%dT%H%M%S%f}"))
    os.replace(novo, db)
    _fsync_pasta(home)
    return True


def purgar(home: Path, antes: str, apagar_original: bool = False) -> dict[str, Any]:
    """Reconstrói o banco sem as execuções anteriores a `antes` (AAAA-MM-DD).

    Ordem segura: constrói o banco novo e o grava em disco; só então move o original
    (com -wal/-shm) para `purgados/<data>/` e renomeia o novo para o lugar. Se o processo cair
    entre os dois renames, `recuperar_purga` conclui a troca na próxima abertura do serviço.
    Requer acesso exclusivo (o chamador fecha as conexões). Apagar o original, e seus
    backups externos, é responsabilidade do operador, salvo `apagar_original=True`: após a troca
    bem-sucedida, apaga o original movido (a purga em si não muda).
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
            dst.execute("PRAGMA journal_mode=DELETE")
        finally:
            dst.close()
        _fsync_arquivo(novo)
    except Exception:
        novo.unlink(missing_ok=True)
        raise
    finally:
        src.close()
    agora = datetime.now(timezone.utc)
    pasta = home / "purgados" / agora.strftime("%Y-%m-%dT%H%M%S-%f")
    pasta.mkdir(parents=True)
    movidos = []
    for suf in ("-wal", "-shm", ""):  # o banco principal por último
        f = Path(str(db) + suf)
        if f.exists():
            shutil.move(str(f), str(pasta / f.name))
            movidos.append(str(pasta / f.name))
    os.replace(novo, db)
    _fsync_pasta(home)
    if apagar_original:
        for m in movidos:
            Path(m).unlink(missing_ok=True)
        pasta.rmdir()
    registro = {"em": agora.isoformat(), "antes": antes, "removidas": n, "restantes": restantes,
                "original_movido_para": [] if apagar_original else movidos, "original_apagado": apagar_original}
    with (home / "purgas.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(registro, ensure_ascii=False) + "\n")
    return {"status": "ok", **registro, "apagar_manualmente": [] if apagar_original else movidos}
