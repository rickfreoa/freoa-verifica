"""Utilitários de fixtures com verificação de SHA-256."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
FIXTURES_META = FIXTURES_DIR / "FIXTURES.json"


def load_meta() -> dict:
    return json.loads(FIXTURES_META.read_text(encoding="utf-8"))


def load_fixture(key: str) -> bytes:
    meta = load_meta()
    if key not in meta:
        raise KeyError(key)
    entry = meta[key]
    path = FIXTURES_DIR / entry["file"]
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    expected = entry["sha256"]
    if digest != expected:
        raise AssertionError(
            f"sha256 mismatch for {key}: got {digest}, expected {expected}"
        )
    return data


def fixture_path(key: str) -> Path:
    meta = load_meta()
    return FIXTURES_DIR / meta[key]["file"]
