"""Íntegras do STJ (decisão 0044): parser, limites, recorte por vínculo e ambiguidade."""

import io
import json
import zipfile
from pathlib import Path

import pytest

from freoa_verifica.connectors.stj_integras import (
    IntegrasInvalidas, MAX_RAZAO, classe_tokens, combinar, ler_textos)

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


M = json.loads(MD.decode("utf-8"))
# fixture real: REsp 2280461 (recurso null) e EDcl no AREsp 3264125; a terceira ? monocr?tica
ESP = {REGS[0]: [("e1", "REsp", "2280461")], REGS[1]: [("e2", "EDcl no AREsp", "3264125")]}


def test_fixture_real_vincula_acordaos_e_descarta_monocratica():
    res = combinar(MD, ZB, ESP)
    assert [(i.numero_registro, k) for i, k in res.vinculadas] == [(REGS[0], "e1"), (REGS[1], "e2")]
    assert res.descartes == {"monocratica_fora_desta_versao": 1}
    integra = res.vinculadas[0][0]
    assert integra.tipo == "acordao" and len(integra.sha256_texto) == 64
    assert "<br" not in integra.texto_limpo.lower() and integra.texto_limpo


def test_mesmo_registro_outro_grau_recursal_nao_vincula():
    # s? o espelho do AREsp no acervo: a ?ntegra dos EDcl n?o pode cair nele
    res = combinar(MD, ZB, {REGS[1]: [("e2", "AREsp", "3264125")], REGS[0]: [("e1", "AgInt no REsp", "2280461")]})
    assert not res.vinculadas and res.descartes["fora_do_recorte_ou_sem_espelho"] == 2


def test_numero_divergente_nao_vincula():
    res = combinar(MD, ZB, {REGS[0]: [("e1", "REsp", "9999999")]})
    assert not res.vinculadas


def test_sem_espelho_e_descartado_e_contado():
    res = combinar(MD, ZB, {})
    assert not res.vinculadas and res.descartes["fora_do_recorte_ou_sem_espelho"] == 2


def test_dois_espelhos_compativeis_e_ambiguo_nunca_escolhe():
    res = combinar(MD, ZB, {**ESP, REGS[0]: [("e1", "REsp", "2280461"), ("e9", "REsp", "2280461")]})
    assert len(res.ambiguas) == 1 and res.ambiguas[0][1] == ["e1", "e9"]
    assert [k for _, k in res.vinculadas] == ["e2"]


def test_duas_integras_do_mesmo_acordao_no_dia_sao_ambiguas():
    dup = dict(M[0], SeqDocumento=1)
    md = json.dumps(M + [dup], ensure_ascii=False).encode("utf-8")
    zb = _zip({**{f"{m['SeqDocumento']}.txt": b"ACORDAO x" for m in M}, "1.txt": b"ACORDAO y"})
    res = combinar(md, zb, ESP)
    assert len(res.ambiguas) == 2 and [k for _, k in res.vinculadas] == ["e2"]


def test_seq_repetido_com_dados_diferentes_descarta_ambos():
    md = json.dumps(M + [dict(M[0], numeroRegistro="000000000000")], ensure_ascii=False).encode("utf-8")
    res = combinar(md, ZB, ESP)
    assert res.descartes["seq_repetido_divergente"] == 2 and [k for _, k in res.vinculadas] == ["e2"]


def test_texto_nao_utf8_e_ausente():
    zb = _zip({f"{M[0]['SeqDocumento']}.txt": "AC\u00d3RD\u00c3O".encode("cp1252")})
    res = combinar(MD, zb, ESP)
    assert not res.vinculadas
    assert res.descartes["texto_nao_utf8"] == 1 and res.descartes["texto_ausente_no_zip"] == 1


def test_idempotente():
    a, b = combinar(MD, ZB, ESP), combinar(MD, ZB, ESP)
    assert [(i.sha256_texto, k) for i, k in a.vinculadas] == [(i.sha256_texto, k) for i, k in b.vinculadas]


def test_classe_tokens_ignora_conectivos():
    assert classe_tokens("AgInt nos EDcl no AREsp") == classe_tokens("AgInt EDcl AREsp")
    assert classe_tokens("AgInt no REsp") != classe_tokens("REsp")


@pytest.mark.parametrize("nome", ["../1.txt", "a/1.txt", "C:\\1.txt", "x.txt", "1.exe"])
def test_zip_slip_e_nomes_inesperados_recusados(nome):
    with pytest.raises(IntegrasInvalidas):
        ler_textos(_zip({nome: b"x"}))


def test_bomba_de_compressao_recusada():
    with pytest.raises(IntegrasInvalidas, match="razao"):
        ler_textos(_zip({"1.txt": b"0" * int(MAX_RAZAO * 1000)}))


def test_zip_corrompido():
    with pytest.raises(IntegrasInvalidas, match="zip_invalido"):
        ler_textos(b"nao e zip")
    import hashlib
    assert ler_textos(_zip({"1.txt": b"a"}, zipfile.ZIP_STORED)) == {"1": ("a", hashlib.sha256(b"a").hexdigest())}
    with pytest.raises(IntegrasInvalidas):
        ler_textos(_zip({"1.txt\n": b"a"}))
    with pytest.raises(IntegrasInvalidas):
        ler_textos(_zip({"\u0661.txt": b"a"}))
