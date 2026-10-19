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
# fixture real: REsp 2280461 (recurso null) e EDcl no AREsp 3264125; a terceira ? monocrática
# ambas da QUARTA TURMA, sessão virtual de 29/09/2026 a 06/10/2026 (lida do texto)
import re as _re
_TXT = {s: t for s, (t, _) in ler_textos(ZB).items()}


def _ementa_de(seq) -> str:
    """Trecho real do próprio texto, com a pontuação e o <br> originais, como a ementa do espelho."""
    t = _re.sub(r"(?i)<br\s*/?>", " ", _TXT[str(seq)])
    i = t.index(" ", t.find("Superior Tribunal de Justiça") + 400)
    return t[i:t.rindex(" ", 0, i + 500)]


EM0, EM1 = _ementa_de(M[0]["SeqDocumento"]), _ementa_de(M[1]["SeqDocumento"])
EMS = "AGRAVO INTERNO NOS EMBARGOS DE DECLARAÇÃO NO RECURSO ESPECIAL. " + "Tese sintética da ementa. " * 8
ESP = {REGS[0]: [("e1", "REsp", "2280461", "QUARTA TURMA", "20261006", EM0)],
       REGS[1]: [("e2", "EDcl no AREsp", "3264125", "QUARTA TURMA", "20261006", EM1)]}
ABERTURA = ("ACÓRDÃO<br>Vistos e relatados estes autos em que são partes as acima indicadas, acordam os Ministros "
            "da QUARTA TURMA do Superior Tribunal de Justiça, em Sessão Virtual de 29/09/2026 a 06/10/2026, "
            "por unanimidade, negar provimento.<br>EMENTA<br>").encode("utf-8") + EMS.encode("utf-8")


def test_fixture_real_vincula_acordaos_e_descarta_monocratica():
    res = combinar(MD, ZB, ESP)
    assert [(i.numero_registro, k) for i, k in res.vinculadas] == [(REGS[0], "e1"), (REGS[1], "e2")]
    assert res.descartes == {"monocratica_fora_desta_versao": 1}
    integra = res.vinculadas[0][0]
    assert integra.tipo == "acordao" and len(integra.sha256_texto) == 64
    assert "<br" not in integra.texto_limpo.lower() and integra.texto_limpo


def test_mesmo_registro_outro_grau_recursal_nao_vincula():
    # só o espelho do AREsp no acervo: a íntegra dos EDcl não pode cair nele
    res = combinar(MD, ZB, {REGS[1]: [("e2", "AREsp", "3264125", "QUARTA TURMA", "20261006", EM1)],
                            REGS[0]: [("e1", "AgInt no REsp", "2280461", "QUARTA TURMA", "20261006", EM0)]})
    assert not res.vinculadas and res.descartes["fora_do_recorte_ou_sem_espelho"] == 2


def test_numero_divergente_nao_vincula():
    res = combinar(MD, ZB, {REGS[0]: [("e1", "REsp", "9999999", "QUARTA TURMA", "20261006", EM0)]})
    assert not res.vinculadas


def test_sem_espelho_e_descartado_e_contado():
    res = combinar(MD, ZB, {})
    assert not res.vinculadas and res.descartes["fora_do_recorte_ou_sem_espelho"] == 2


def test_dois_espelhos_compativeis_e_ambiguo_nunca_escolhe():
    res = combinar(MD, ZB, {**ESP, REGS[0]: [ESP[REGS[0]][0], ("e9", "REsp", "2280461", "QUARTA TURMA", "20260930", EM0)]})
    assert len(res.ambiguas) == 1 and res.ambiguas[0][1] == ["e1", "e9"]
    assert [k for _, k in res.vinculadas] == ["e2"]


def test_duas_integras_do_mesmo_acordao_no_dia_sao_ambiguas():
    dup = dict(M[0], SeqDocumento=1)
    md = json.dumps(M + [dup], ensure_ascii=False).encode("utf-8")
    zb = _zip({**{f"{m['SeqDocumento']}.txt": ABERTURA for m in M}, "1.txt": ABERTURA + b" y"})
    esp = {r: [v[0][:5] + (EMS,)] for r, v in ESP.items()}
    res = combinar(md, zb, esp)
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


def test_cadeia_profunda_ausente_no_metadado_nao_cai_no_espelho_raso():
    # recurso="AgInt" + "REsp 123": o documento pode ser AgInt nos EDcl no REsp (achado Codex 1)
    md = json.dumps([{"SeqDocumento": 7, "tipoDocumento": "ACÓRDÃO", "numeroRegistro": "202600000001",
                      "processo": "REsp 123", "recurso": "AgInt"}]).encode("utf-8")
    zb = _zip({"7.txt": ABERTURA})
    raso = ("errado", "AgInt no REsp", "123", "QUARTA TURMA", "20260801", "Outra ementa do agravo interno. " * 6)
    fundo = ("correto", "AgInt nos EDcl no REsp", "123", "QUARTA TURMA", "20261001", EMS)
    assert [k for _, k in combinar(md, zb, {"202600000001": [raso, fundo]}).vinculadas] == ["correto"]
    so_raso = combinar(md, zb, {"202600000001": [raso]})
    assert not so_raso.vinculadas and so_raso.descartes == {"julgamento_divergente_do_espelho": 1}
    # raso sozinho na mesma sessão (Codex, 2ª rodada B1): a ementa não confere, não vincula
    raso_mesma = raso[:4] + ("20261001", raso[5])
    so = combinar(md, zb, {"202600000001": [raso_mesma]})
    assert not so.vinculadas and so.descartes == {"julgamento_divergente_do_espelho": 1}
    assert [k for _, k in combinar(md, zb, {"202600000001": [raso_mesma, fundo]}).vinculadas] == ["correto"]


def test_troca_dos_textos_reais_nao_vincula():
    # bytes do EDcl no AREsp 3264125 sob o Seq do REsp 2280461: mesma turma e sessão, ementa diferente
    s0, s1 = str(M[0]["SeqDocumento"]), str(M[1]["SeqDocumento"])
    zb = _zip({f"{s0}.txt": _TXT[s1].encode("utf-8"), f"{s1}.txt": _TXT[s1].encode("utf-8")})
    res = combinar(MD, zb, ESP)
    assert [k for _, k in res.vinculadas] == ["e2"]
    assert res.descartes["julgamento_divergente_do_espelho"] == 1


def test_espelho_sem_ementa_nao_vincula():
    esp = {r: [v[0][:5] + ("",)] for r, v in ESP.items()}
    assert not combinar(MD, ZB, esp).vinculadas


def test_sem_formula_de_sessao_fica_pendente():
    zb = _zip({f"{M[0]['SeqDocumento']}.txt": b"ACORDAO sem abertura padrao",
               f"{M[1]['SeqDocumento']}.txt": ABERTURA})
    res = combinar(MD, zb, {r: [v[0][:5] + (EMS,)] for r, v in ESP.items()})
    assert res.descartes["sem_prova_do_julgamento"] == 1 and [k for _, k in res.vinculadas] == ["e2"]


def test_orgao_abreviado_e_gerador_de_espelhos():
    esp = {r: iter([(k, c, n, "QUARTA TURMA", d, e)]) for r, [(k, c, n, _, d, e)] in ESP.items()}
    assert len(combinar(MD, ZB, esp).vinculadas) == 2
    from freoa_verifica.connectors.stj_integras import _orgao
    assert _orgao("S2") == _orgao("SEGUNDA SEÇÃO")


def test_metadado_nao_objeto_e_tipo_desconhecido():
    with pytest.raises(IntegrasInvalidas, match="nao_objeto"):
        combinar(json.dumps([None, 1]).encode(), ZB, ESP)
    md = json.dumps([dict(M[0], tipoDocumento="FORMATO NOVO")], ensure_ascii=False).encode("utf-8")
    assert combinar(md, ZB, ESP).descartes == {"tipo_documento_desconhecido": 1}


def _forjar_tamanho(raw: bytes, falso: bytes) -> bytes:
    """Troca, nos cabeçalhos local e central, tamanho descompactado e CRC pelos de `falso`."""
    import struct, zlib
    buf = bytearray(raw)
    crc, tam = struct.pack("<I", zlib.crc32(falso)), struct.pack("<I", len(falso))
    buf[14:18], buf[22:26] = crc, tam
    c = buf.index(b"PK\x01\x02")
    buf[c + 16:c + 20], buf[c + 24:c + 28] = crc, tam
    return bytes(buf)


@pytest.mark.parametrize("metodo", [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED])
def test_tamanho_e_crc_forjados_recusados(metodo):
    real = ABERTURA * 50
    forjado = _forjar_tamanho(_zip({"1.txt": real}, metodo), real[:10])
    assert zipfile.ZipFile(io.BytesIO(forjado)).read("1.txt") == real[:10]  # zipfile aceita o prefixo
    with pytest.raises(IntegrasInvalidas):
        ler_textos(forjado)


@pytest.mark.parametrize("nome", ["d/", "../escape/", "1.txt\x00evil"])
def test_diretorio_e_nul_recusados(nome):
    with pytest.raises(IntegrasInvalidas):
        ler_textos(_zip({nome: b"" if nome.endswith("/") else b"x", "1.txt": b"a"}))
