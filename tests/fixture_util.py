"""Utilitários de fixtures: carregamento com SHA-256 e validação do inventário (E1)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
FIXTURES_META = FIXTURES_DIR / "FIXTURES.json"

CATEGORIAS = ("captura_real", "sintetica")
CAMPOS_CAPTURA = ("url", "url_final", "status", "content_type", "capturado_em", "origem_metadados")
CAMPOS_SINTETICA = ("gerador", "proposito")


def load_meta() -> dict:
    return json.loads(FIXTURES_META.read_text(encoding="utf-8"))


def _caminho_confinado(raiz: Path, relativo: str) -> Path | None:
    """Caminho dentro de `raiz`, sem `..`, absoluto nem link simbólico; None se fora."""
    if not isinstance(relativo, str) or not relativo or "\\" in relativo:
        return None
    if PurePosixPath(relativo).is_absolute() or PureWindowsPath(relativo).is_absolute():
        return None
    if ".." in PurePosixPath(relativo).parts:
        return None
    caminho = raiz
    for parte in PurePosixPath(relativo).parts:
        caminho = caminho / parte
        if caminho.is_symlink():
            return None
    return caminho


def validar_inventario(raiz: Path = FIXTURES_DIR, manifesto: Path | None = None) -> list[str]:
    """Problemas do inventário de `raiz` frente ao manifesto; lista vazia = conforme."""
    raiz = Path(raiz)
    manifesto = Path(manifesto) if manifesto else raiz / "FIXTURES.json"
    entradas = json.loads(manifesto.read_text(encoding="utf-8"))
    problemas: list[str] = []
    registrados: dict[str, str] = {}

    for chave, e in sorted(entradas.items()):
        arquivo = e.get("file")
        caminho = _caminho_confinado(raiz, arquivo)
        if caminho is None:
            problemas.append(f"caminho fora de {raiz.name}: {chave} -> {arquivo!r}")
            continue
        registrados[arquivo] = chave
        if not caminho.is_file():
            problemas.append(f"ausente: {arquivo} ({chave})")
            continue
        dados = caminho.read_bytes()
        if hashlib.sha256(dados).hexdigest() != e.get("sha256"):
            problemas.append(f"sha256 divergente: {arquivo} ({chave})")
        if len(dados) != e.get("bytes"):
            problemas.append(f"bytes divergentes: {arquivo} ({chave})")
        problemas.extend(_campos(chave, e))

    for atual, nomes, arquivos in os.walk(raiz, followlinks=False):
        for nome in [*nomes, *arquivos]:
            completo = Path(atual) / nome
            rel = completo.relative_to(raiz).as_posix()
            if completo.is_symlink():
                problemas.append(f"link simbólico: {rel}")
            elif completo.is_file() and rel != manifesto.name and rel not in registrados:
                problemas.append(f"não registrado: {rel}")
    return problemas


def _campos(chave: str, e: dict) -> list[str]:
    categoria = e.get("categoria")
    if categoria not in CATEGORIAS:
        return [f"categoria inválida: {chave} -> {categoria!r}"]
    if categoria == "sintetica":
        return [f"campo ausente em {chave}: {c}" for c in CAMPOS_SINTETICA if not e.get(c)]
    faltam = [f"campo ausente em {chave}: {c}" for c in CAMPOS_CAPTURA if c not in e]
    if faltam:
        return faltam
    if any(e[c] is None for c in CAMPOS_CAPTURA) and e["origem_metadados"] != "desconhecida":
        return [f"campo nulo sem origem_metadados 'desconhecida': {chave}"]
    return []


def load_fixture(key: str) -> bytes:
    meta = load_meta()
    if key not in meta:
        raise KeyError(key)
    entry = meta[key]
    path = _caminho_confinado(FIXTURES_DIR, entry["file"])
    if path is None:
        raise AssertionError(f"caminho fora de fixtures: {key} -> {entry['file']!r}")
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
