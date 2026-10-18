"""Armazenamento de blobs endereçados por SHA-256."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from freoa_verifica.store.db import data_home


class BlobError(Exception):
    """Erro de leitura/escrita de blob."""


class BlobCorruption(BlobError):
    """Conteúdo no disco não corresponde ao SHA-256 esperado."""


def blobs_root(home: Path | None = None) -> Path:
    root = (home or data_home()) / "blobs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def blob_path(sha256: str, home: Path | None = None) -> Path:
    digest = sha256.lower()
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("sha256 inválido")
    return blobs_root(home) / digest[:2] / digest[2:4] / digest


def put_blob(data: bytes, home: Path | None = None) -> str:
    """Escreve blob de forma atômica e idempotente; retorna sha256 hex."""
    digest = hashlib.sha256(data).hexdigest()
    target = blob_path(digest, home)
    if target.exists():
        existing = target.read_bytes()
        if hashlib.sha256(existing).hexdigest() != digest:
            raise BlobCorruption(f"blob corrompido: {digest}")
        return digest
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=target.parent, prefix=".blob-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            try:
                os.unlink(temporary)
            except OSError:
                pass
    return digest


def get_blob(sha256: str, home: Path | None = None) -> bytes:
    """Lê blob e verifica o hash; levanta BlobCorruption se divergir."""
    target = blob_path(sha256, home)
    if not target.is_file():
        raise FileNotFoundError(sha256)
    data = target.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != sha256.lower():
        raise BlobCorruption(f"blob corrompido: esperado {sha256}, obtido {actual}")
    return data


_AUTHENTICATED = {}

def authenticate_blob(sha256: str, home: Path | None = None) -> None:
    """Autentica bytes; alterações de mtime/tamanho invalidam o cache."""
    target = blob_path(sha256, home)
    stat = target.stat()
    stamp = (stat.st_mtime_ns, stat.st_size, stat.st_ctime_ns)
    key = (str(target.resolve()), sha256)
    if _AUTHENTICATED.get(key) != stamp:
        get_blob(sha256, home)
        _AUTHENTICATED[key] = stamp
