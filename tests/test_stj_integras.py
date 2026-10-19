"""Íntegras do STJ (decisão 0044): parser, limites, recorte por vínculo e ambiguidade."""

import io
import json
import zipfile
from pathlib import Path

import pytest

from freoa_verifica.connectors.stj_integras import (
    IntegrasInvalidas, MAX_RAZAO, combinar, ler_textos)

FIX = Path(__file__).parent / "fixtures" / "stj_integras"
MD = (FIX / "metadados.json").read_bytes()
ZB = (FIX / "textos.zip").read_bytes()
REGS = [m["numeroRegistro"] for m in json.loads(MD.decode("utf-8"))]


def _zip(entradas: dict[str, bytes], metodo=zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", metodo) as z:
        for nome, dado in entradas.items():
            z.writestr(nome, dado)
    return buf.getvalue()


def test_fixture_real_vincula_acordaos_e_descarta_monocratica():
    res = combinar(MD, ZB, {REGS[0]: ["e1"], REGS[1]: ["e2"]})
    assert [(i.numero_registro, k) for i, k in res.vinculadas] == [(REGS[0], "e1"), (REGS[1], "e2")]
    assert res.descartes == {"monocratica_fora_desta_versao": 1}
    integra = res.vinculadas[0][0]
    assert integra.tipo == "acordao" and len(integra.sha256_texto) == 64
    assert "<br" not in integra.texto_limpo.lower() and integra.texto_limpo


def test_sem_espelho_e_descartado_e_contado():
    res = combinar(MD, ZB, {})
    assert not res.vinculadas and res.descartes["fora_do_recorte_ou_sem_espelho"] == 2


def test_registro_com_varios_espelhos_e_ambiguo_nunca_escolhe():
    res = combinar(MD, ZB, {REGS[0]: ["e1", "e9"], REGS[1]: ["e2"]})
    assert len(res.ambiguas) == 1 and res.ambiguas[0][1] == ["e1", "e9"]
    assert [k for _, k in res.vinculadas] == ["e2"]


def test_texto_ausente_no_zip():
    so_um = _zip({f"{json.loads(MD)[0]['SeqDocumento']}.txt": b"ACORDAO texto"})
    res = combinar(MD, so_um, {r: ["x" + r] for r in REGS})
    assert len(res.vinculadas) == 1 and res.descartes["texto_ausente_no_zip"] == 1


def test_idempotente():
    a = combinar(MD, ZB, {REGS[0]: ["e1"]})
    b = combinar(MD, ZB, {REGS[0]: ["e1"]})
    assert [(i.sha256_texto, k) for i, k in a.vinculadas] == [(i.sha256_texto, k) for i, k in b.vinculadas]


@pytest.mark.parametrize("nome", ["../1.txt", "a/1.txt", "C:\\1.txt", "x.txt", "1.exe"])
def test_zip_slip_e_nomes_inesperados_recusados(nome):
    with pytest.raises(IntegrasInvalidas):
        ler_textos(_zip({nome: b"x"}))


def test_bomba_de_compressao_recusada():
    with pytest.raises(IntegrasInvalidas, match="razao"):
        ler_textos(_zip({"1.txt": b"0" * int(MAX_RAZAO * 1000)}))


def test_zip_corrompido_e_seq_repetido():
    with pytest.raises(IntegrasInvalidas, match="zip_invalido"):
        ler_textos(b"nao e zip")
    raw = _zip({"1.txt": b"a"}).replace(b"1.txt", b"1.txt")
    assert ler_textos(raw) == {"1": "a"}
