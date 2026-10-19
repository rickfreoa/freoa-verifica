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


_cache_chaves: dict[str, tuple[bytes, tuple[int, int, int]]] = {}  # home -> (chave, (ino, size, mtime_ns))
META_IMPRESSAO = "registro_chave_sha256_16"


def _impressao(chave: bytes) -> str:
    return hashlib.sha256(chave).hexdigest()[:16]


def _assinatura(caminho: Path) -> tuple[int, int, int]:
    st = caminho.stat()
    return (st.st_ino, st.st_size, st.st_mtime_ns)


def _chave_ausente_com_historico(conn: sqlite3.Connection | None) -> bool:
    if conn is None:
        return False
    if conn.execute("SELECT 1 FROM meta WHERE key=?", (META_IMPRESSAO,)).fetchone():
        return True
    return conn.execute("SELECT 1 FROM run WHERE request_hash LIKE 'hmac1:%' LIMIT 1").fetchone() is not None


def chave_do_home(home: Path, conn: sqlite3.Connection | None = None) -> bytes:
    """Segredo de 32 bytes do home (`<home>/registro.key`), criado atomicamente e com modo 0o600.

    Criação: grava em arquivo temporário no mesmo diretório (sincronizado) e `os.link` para o nome
    final; EEXIST (outro processo ganhou) lê o existente. Nunca existe estado de 0 byte. Com `conn`,
    a impressão digital (sha256, 16 hex) fica em `meta`; chave ausente com runs `hmac1:` ou impressão
    em `meta` é erro CHAVE_REGISTRO_AUSENTE (não se regenera em silêncio). Cache por home no processo,
    revalidado por stat (arquivo apagado, trocado ou corrompido não passa despercebido).
    Windows: o modo POSIX não se aplica; a proteção vem da ACL herdada da pasta do perfil.
    """
    caminho = Path(home) / ARQUIVO_CHAVE
    try:
        em_cache = _cache_chaves.get(str(caminho))
        if em_cache and em_cache[1] == _assinatura(caminho):
            return em_cache[0]
    except FileNotFoundError:
        pass
    if not caminho.exists():
        if _chave_ausente_com_historico(conn):
            raise RuntimeError(
                f"CHAVE_REGISTRO_AUSENTE: {caminho} sumiu mas o home tem registros com HMAC; "
                "restaure a chave original (uma nova invalidaria os hashes gravados)")
        tmp = caminho.with_name(f"{ARQUIVO_CHAVE}.{secrets.token_hex(8)}.tmp")
        fd = os.open(str(tmp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(secrets.token_bytes(32))
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.link(tmp, caminho)
        except FileExistsError:
            pass
        finally:
            tmp.unlink(missing_ok=True)
    chave = caminho.read_bytes()
    if len(chave) != 32:
        raise RuntimeError(f"{caminho} corrompida (esperado 32 bytes); remova-a ciente de que hashes antigos deixam de casar")
    if conn is not None:
        conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES (?, ?)", (META_IMPRESSAO, _impressao(chave)))
    _cache_chaves[str(caminho)] = (chave, _assinatura(caminho))
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
    chave = chave_do_home(home, conn) if home else _chaves_efemeras.setdefault(str(id(conn)), secrets.token_bytes(32))
    mac = hmac.new(chave, campo.encode("utf-8") + b"\0" + valor.encode("utf-8"), hashlib.sha256)
    return PREFIXO_HMAC + mac.hexdigest()


def checkpoint_truncate(conn: sqlite3.Connection) -> None:
    """`wal_checkpoint(TRUNCATE)` que recusa quando o checkpoint não completou (busy != 0)."""
    busy = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]
    if busy:
        raise RuntimeError("wal_checkpoint_ocupado: há leitor/escritor ativo no banco")


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
        checkpoint_truncate(src)
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
    # A7: o registro da purga é gravado ANTES de apagar o original; depois da troca nada levanta exceção.
    registro = {"em": agora.isoformat(), "antes": antes, "removidas": n, "restantes": restantes,
                "original_movido_para": movidos, "original_apagado": False, "apagar_original_pedido": apagar_original}
    with (home / "purgas.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(registro, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    apagados: list[str] = []
    falhas: list[dict[str, str]] = []
    if apagar_original:
        for m in movidos:
            try:
                Path(m).unlink(missing_ok=True)
                apagados.append(m)
            except OSError as exc:
                falhas.append({"arquivo": m, "erro": str(exc)[:120]})
        try:
            pasta.rmdir()
        except OSError as exc:
            if not falhas:
                falhas.append({"arquivo": str(pasta), "erro": str(exc)[:120]})
        registro.update(original_apagado=not falhas, original_movido_para=[f["arquivo"] for f in falhas])
        with (home / "purgas.jsonl").open("a", encoding="utf-8") as fh:  # desfecho da exclusão
            fh.write(json.dumps({"em": agora.isoformat(), "evento": "original_apagado", "apagados": apagados,
                                 "falhas": falhas}, ensure_ascii=False) + "\n")
    return {"status": "ok", **registro, "apagados": apagados, "falhas": falhas,
            "apagar_manualmente": [f["arquivo"] for f in falhas] if apagar_original else movidos}
