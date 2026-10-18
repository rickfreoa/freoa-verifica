"""Parser CVM DOCX — RCVM 160, 44, 175 e 80."""

from __future__ import annotations

import io
import zipfile

from freoa_verifica.parsers.cvm_docx import parse_cvm_docx
from freoa_verifica.parsers.paths import is_article_path
from tests.fixture_util import load_fixture

_AMBIGUOUS_CAPS = {
    "cvm_resol_044_consolid_docx": 0,
    "cvm_resol_160_consolid_docx": 0,
    # art70-A/B tipográficos resolvidos; restam colisões reais do consolidado
    "cvm_resol_175_consolid_docx": 8,
    "cvm_resol_080_consolid_docx": 5,
}


def _doc_blocking(doc):
    return [i for i in doc.issues if i.blocking_scope == "document"]


def _structural_ambiguities(doc):
    # Notas sem associação segura agora bloqueiam texto de forma conservadora.
    roots = [i.path for i in doc.issues if i.code == "ORPHAN_ANNOTATION" and i.path]
    return [p for p in doc.ambiguous_paths if not any(p == r or p.startswith(r+".") or p.startswith(r+"/") for r in roots)]


def test_rcvm_160_art2_inc16():
    data = load_fixture("cvm_resol_160_consolid_docx")
    doc = parse_cvm_docx(data)

    assert doc.provision("art1") is not None
    assert doc.current_text("art1")

    prov = doc.provision("art2.inc16")
    assert prov is not None
    assert any(r.struck for r in prov.redactions)
    assert any(not r.struck for r in prov.redactions)

    anns = [a for r in prov.redactions if not r.struck for a in r.annotations]
    assert any(
        a.kind == "redacao_dada"
        and a.act_ref
        and "Resolução CVM nº 173" in a.act_ref
        and a.act_date == "2022-11-29"
        for a in anns
    ), anns

    arts = [p.path for p in doc.provisions if is_article_path(p.path)]
    assert "art1" in arts

    assert not _doc_blocking(doc)
    assert not doc.quarantined
    assert len(_structural_ambiguities(doc)) <= _AMBIGUOUS_CAPS["cvm_resol_160_consolid_docx"]


def test_rcvm_44():
    data = load_fixture("cvm_resol_044_consolid_docx")
    doc = parse_cvm_docx(data)
    assert doc.provision("art1") is not None
    arts = [
        p
        for p in doc.provisions
        if is_article_path(p.path) and any(not r.struck for r in p.redactions)
    ]
    assert len(arts) >= 25
    assert len(arts) == 25
    assert not doc.quarantined
    assert len(_structural_ambiguities(doc)) <= _AMBIGUOUS_CAPS["cvm_resol_044_consolid_docx"]


def test_rcvm_175_annex_scope():
    doc = parse_cvm_docx(load_fixture("cvm_resol_175_consolid_docx"))
    assert not doc.quarantined, _doc_blocking(doc)
    assert len(_structural_ambiguities(doc)) <= _AMBIGUOUS_CAPS["cvm_resol_175_consolid_docx"], (
        len(doc.ambiguous_paths),
        doc.ambiguous_paths[:30],
    )
    assert doc.provision("art1") is not None
    # Anexo Normativo I tem Art. 1 distinto do corpo
    anexo_art1 = doc.provision("anexo-i/art1")
    assert anexo_art1 is not None, [
        p.path for p in doc.provisions if p.path.endswith("/art1") or p.path == "art1"
    ][:20]
    assert anexo_art1.path != "art1"
    assert anexo_art1.scope.startswith("anexo-i")


def test_rcvm_080_no_document_quarantine():
    doc = parse_cvm_docx(load_fixture("cvm_resol_080_consolid_docx"))
    assert not doc.quarantined, _doc_blocking(doc)
    assert len(_structural_ambiguities(doc)) <= _AMBIGUOUS_CAPS["cvm_resol_080_consolid_docx"], (
        len(doc.ambiguous_paths),
        doc.ambiguous_paths,
    )


def test_rcvm_160_no_leading_period():
    doc = parse_cvm_docx(load_fixture("cvm_resol_160_consolid_docx"))
    text = doc.current_text("art32")
    assert text is not None
    assert not text.startswith(".")
    assert text.startswith("A condução")


def test_rcvm_175_art70_letter_en_dash():
    """70–A / 70–B (meia-risca) → art70-A / art70-B, sem colisão em art70."""
    doc = parse_cvm_docx(load_fixture("cvm_resol_175_consolid_docx"))
    assert doc.provision("anexo-i/art70-A") is not None, [
        p.path for p in doc.provisions if "art70" in p.path
    ][:30]
    assert doc.provision("anexo-i/art70-B") is not None
    art70 = doc.provision("anexo-i/art70")
    assert art70 is not None
    # art70 não deve absorver o texto de 70-A
    currents = [r.text for r in art70.redactions if not r.struck]
    assert not any("FAPI" in t for t in currents)


def test_docx_bomb_refused():
    """max_input_bytes / max_uncompressed → TRUNCATED."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "word/document.xml",
            b"<w:document xmlns:w="
            b"'http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
            b"<w:body><w:p><w:r><w:t>Art. 1. Hi.</w:t></w:r></w:p>"
            b"</w:body></w:document>",
        )
    raw = buf.getvalue()
    doc = parse_cvm_docx(raw, max_input_bytes=10)
    assert doc.quarantined
    assert any(i.code == "TRUNCATED" for i in doc.issues)


def test_docx_compression_ratio_refused():
    """Razão file_size/compress_size > 100 → recusa."""
    # Gera zip com um arquivo altamente compressível anunciando tamanho grande
    import struct
    import zlib

    # Monta ZIP mínimo à mão com file_size alto e compress_size baixo
    name = b"word/document.xml"
    xml = (
        b"<?xml version='1.0'?><w:document xmlns:w="
        b"'http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
        b"<w:body><w:p><w:r><w:t>Art. 1. Ok.</w:t></w:r></w:p></w:body>"
        b"</w:document>"
    )
    # PAD com zeros compressíveis para ratio alto
    uncompressed = xml + (b"\x00" * 200_000)
    compressed = zlib.compress(uncompressed, 9)[2:-4]  # raw deflate
    ratio = len(uncompressed) / max(len(compressed), 1)
    assert ratio > 100

    def _u32(n):
        return struct.pack("<I", n)

    def _u16(n):
        return struct.pack("<H", n)

    crc = zlib.crc32(uncompressed) & 0xFFFFFFFF
    local = (
        b"PK\x03\x04"
        + _u16(20)
        + _u16(0)
        + _u16(8)
        + _u16(0)
        + _u16(0)
        + _u32(crc)
        + _u32(len(compressed))
        + _u32(len(uncompressed))
        + _u16(len(name))
        + _u16(0)
        + name
        + compressed
    )
    central = (
        b"PK\x01\x02"
        + _u16(20)
        + _u16(20)
        + _u16(0)
        + _u16(8)
        + _u16(0)
        + _u16(0)
        + _u32(crc)
        + _u32(len(compressed))
        + _u32(len(uncompressed))
        + _u16(len(name))
        + _u16(0)
        + _u16(0)
        + _u16(0)
        + _u16(0)
        + _u32(0)
        + _u32(0)
        + name
    )
    end = (
        b"PK\x05\x06"
        + _u16(0)
        + _u16(0)
        + _u16(1)
        + _u16(1)
        + _u32(len(central))
        + _u32(len(local))
        + _u16(0)
    )
    raw = local + central + end
    doc = parse_cvm_docx(raw)
    assert doc.quarantined
    assert any(i.code == "TRUNCATED" for i in doc.issues)
