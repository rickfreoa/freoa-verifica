"""Manifesto de fixtures (E1): inventário bidirecional, hash, confinamento e campos por categoria."""

import hashlib
import json
from pathlib import Path

import pytest

from tests import fixture_util
from tests.fixture_util import FIXTURES_DIR, load_fixture, load_meta, validar_inventario


def _sintetica(nome, dados):
    return {
        "categoria": "sintetica", "gerador": "manual", "proposito": "teste",
        "file": nome, "bytes": len(dados), "sha256": hashlib.sha256(dados).hexdigest(),
    }


def _monta(raiz, arquivos, entradas=None):
    """Cria `raiz` com `arquivos` ({nome: bytes}) e o manifesto (padrão: todos sintéticos)."""
    raiz.mkdir(parents=True, exist_ok=True)
    for nome, dados in arquivos.items():
        (raiz / nome).parent.mkdir(parents=True, exist_ok=True)
        (raiz / nome).write_bytes(dados)
    if entradas is None:
        entradas = {nome.split(".")[0]: _sintetica(nome, dados) for nome, dados in arquivos.items()}
    manifesto = raiz / "FIXTURES.json"
    manifesto.write_text(json.dumps(entradas), encoding="utf-8")
    return manifesto


def _arquivos_do_disco():
    return {p.relative_to(FIXTURES_DIR).as_posix() for p in FIXTURES_DIR.rglob("*") if p.is_file()} - {"FIXTURES.json"}


def test_inventario_real_bate_com_o_disco():
    assert validar_inventario() == []


def test_todo_arquivo_esta_no_manifesto_e_vice_versa():
    registrados = {e["file"] for e in load_meta().values()}
    assert _arquivos_do_disco() == registrados


def test_hash_e_tamanho_de_cada_entrada_conferem():
    for chave, e in load_meta().items():
        dados = (FIXTURES_DIR / e["file"]).read_bytes()
        assert hashlib.sha256(dados).hexdigest() == e["sha256"], chave
        assert len(dados) == e["bytes"], chave


def test_campos_obrigatorios_por_categoria_no_manifesto_real():
    for chave, e in load_meta().items():
        assert e["categoria"] in ("captura_real", "sintetica"), chave
        if e["categoria"] == "sintetica":
            assert e["gerador"] and e["proposito"], chave
        else:
            for campo in ("url", "url_final", "status", "content_type", "capturado_em", "origem_metadados"):
                assert campo in e, (chave, campo)


def test_arquivo_extra_reprova(tmp_path):
    raiz = tmp_path / "fixtures"
    manifesto = _monta(raiz, {"a.txt": b"a"})
    (raiz / "b.txt").write_bytes(b"b")
    assert validar_inventario(raiz, manifesto) == ["não registrado: b.txt"]


def test_arquivo_ausente_reprova(tmp_path):
    raiz = tmp_path / "fixtures"
    manifesto = _monta(raiz, {"a.txt": b"a", "c.txt": b"c"})
    (raiz / "c.txt").unlink()
    assert validar_inventario(raiz, manifesto) == ["ausente: c.txt (c)"]


def test_byte_alterado_reprova(tmp_path):
    raiz = tmp_path / "fixtures"
    manifesto = _monta(raiz, {"a.txt": b"abc"})
    (raiz / "a.txt").write_bytes(b"abd")
    assert validar_inventario(raiz, manifesto) == ["sha256 divergente: a.txt (a)"]


def test_caminho_com_dotdot_reprova(tmp_path):
    raiz = tmp_path / "fixtures"
    (tmp_path / "fora.txt").write_bytes(b"fora")
    manifesto = _monta(raiz, {}, {"a": {**_sintetica("../fora.txt", b"fora")}})
    assert validar_inventario(raiz, manifesto) == ["caminho fora de fixtures: a -> '../fora.txt'"]


def test_link_simbolico_reprova(tmp_path):
    raiz = tmp_path / "fixtures"
    manifesto = _monta(raiz, {"a.txt": b"a"})
    alvo = tmp_path / "fora.txt"
    alvo.write_bytes(b"fora")
    try:
        (raiz / "ln.txt").symlink_to(alvo)
    except OSError as erro:
        pytest.skip(f"sem permissão para link simbólico: {erro}")
    assert validar_inventario(raiz, manifesto) == ["link simbólico: ln.txt"]


def test_entrada_em_link_simbolico_reprova(tmp_path, monkeypatch):
    # simula o link sem depender de privilégio de criação de symlink no Windows
    raiz = tmp_path / "fixtures"
    manifesto = _monta(raiz, {"a.txt": b"a"})
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda self: self.name == "a.txt" or original(self))
    assert validar_inventario(raiz, manifesto) == ["caminho fora de fixtures: a -> 'a.txt'", "link simbólico: a.txt"]


def test_captura_sem_campo_obrigatorio_reprova(tmp_path):
    raiz = tmp_path / "fixtures"
    dados = b"<html></html>"
    entrada = {"categoria": "captura_real", "file": "p.html", "bytes": len(dados),
               "sha256": hashlib.sha256(dados).hexdigest(), "url": "https://x", "url_final": "https://x",
               "status": 200, "capturado_em": "2026-10-18", "origem_metadados": "teste"}
    manifesto = _monta(raiz, {"p.html": dados}, {"p": entrada})
    assert validar_inventario(raiz, manifesto) == ["campo ausente em p: content_type"]


def test_campo_nulo_sem_origem_desconhecida_reprova(tmp_path):
    raiz = tmp_path / "fixtures"
    dados = b"x"
    entrada = {"categoria": "captura_real", "file": "p.txt", "bytes": 1,
               "sha256": hashlib.sha256(dados).hexdigest(), "url": "https://x", "url_final": None,
               "status": 200, "content_type": "text/plain", "capturado_em": None,
               "origem_metadados": "manifesto_original"}
    manifesto = _monta(raiz, {"p.txt": dados}, {"p": entrada})
    assert validar_inventario(raiz, manifesto) == ["campo nulo sem origem_metadados 'desconhecida': p"]


def test_categoria_invalida_reprova(tmp_path):
    raiz = tmp_path / "fixtures"
    manifesto = _monta(raiz, {"a.txt": b"a"}, {"a": {**_sintetica("a.txt", b"a"), "categoria": "real"}})
    assert validar_inventario(raiz, manifesto) == ["categoria inválida: a -> 'real'"]


def test_load_fixture_recusa_caminho_fora(monkeypatch):
    monkeypatch.setattr(fixture_util, "load_meta", lambda: {"x": {"file": "../FIXTURES.json", "sha256": "0"}})
    with pytest.raises(AssertionError, match="caminho fora de fixtures: x"):
        load_fixture("x")


def test_load_fixture_le_pelo_manifesto():
    assert load_fixture("challenge_aws_waf_sample") == (FIXTURES_DIR / "challenge_aws_waf_sample.html").read_bytes()
