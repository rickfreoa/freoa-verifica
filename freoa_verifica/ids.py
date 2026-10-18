"""Gerador ULID com stdlib (Crockford base32, ordenável por tempo)."""

from __future__ import annotations

import os
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode(value: int, length: int) -> str:
    chars: list[str] = []
    for _ in range(length):
        chars.append(_CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def new_ulid(*, timestamp_ms: int | None = None) -> str:
    """Gera um ULID de 26 caracteres (10 de tempo + 16 de aleatoriedade)."""
    ms = int(time.time() * 1000) if timestamp_ms is None else timestamp_ms
    if ms < 0 or ms >= 2**48:
        raise ValueError("timestamp_ms fora do intervalo ULID")
    entropy = int.from_bytes(os.urandom(10), "big")
    return _encode(ms, 10) + _encode(entropy, 16)
