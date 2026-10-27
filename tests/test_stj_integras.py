"""Íntegras do STJ (decisão 0044): parser, limites, recorte por vínculo e ambiguidade."""

import io
import json
import struct
import zipfile
from pathlib import Path

import pytest

from freoa_verifica.connectors.stj_integras import (
    IntegrasInvalidas, MAX_RAZAO, classe_tokens, combinar, ementa_propria, ler_metadados, ler_textos)

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
# fixtures sintéticas (recorte da amostra de 08/10/2026; ver FIXTURES.json): REsp 2280461 (recurso null) e EDcl no
# AREsp 3264125; a terceira é monocrática. Ambas da QUARTA TURMA, sessão virtual de 29/09/2026 a 06/10/2026.
# Os espelhos usados aqui derivam do próprio texto (não são conjunto-ouro independente): provam o mecanismo
# de vínculo, não a taxa de acerto contra espelhos reais do acervo.
import re as _re  # noqa: F401
_TXT = {s: t for s, (t, _) in ler_textos(ZB).items()}


def _ementa_de(seq) -> str:
    """Trecho do bloco da ementa do próprio texto da fixture, como a ementa do espelho (derivada, não independente)."""
    t = ementa_propria(_TXT[str(seq)])
    i = t.index(" ", 50)
    return t[i:t.rindex(" ", 0, i + 500)]


EM0, EM1 = _ementa_de(M[0]["SeqDocumento"]), _ementa_de(M[1]["SeqDocumento"])
EMS = "AGRAVO INTERNO NOS EMBARGOS DE DECLARAÇÃO NO RECURSO ESPECIAL. " + "Tese sintética da ementa. " * 8
ESP = {REGS[0]: [("e1", "REsp", "2280461", "QUARTA TURMA", "20261006", EM0)],
       REGS[1]: [("e2", "EDcl no AREsp", "3264125", "QUARTA TURMA", "20261006", EM1)]}
ABERTURA = ("ACÓRDÃO<br>Vistos e relatados estes autos em que são partes as acima indicadas, acordam os Ministros "
            "da QUARTA TURMA do Superior Tribunal de Justiça, em Sessão Virtual de 29/09/2026 a 06/10/2026, "
            "por unanimidade, negar provimento.<br>EMENTA<br>").encode("utf-8") + EMS.encode("utf-8") + \
    "<br>RELATÓRIO<br>Relatório do caso.".encode("utf-8")


def test_fixture_sintetica_vincula_acordaos_e_descarta_monocratica():
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


def test_troca_dos_textos_da_fixture_nao_vincula():
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


# ---- I2: abertura delimitada, intervalo completo e calendário (decisão 0044, item 3) ----------------
from freoa_verifica.connectors.stj_integras import (  # noqa: E402
    _data_iso, julgamento_no_texto, ler_textos_detalhado, visao_textual)


def _abertura(sessao: str, corpo: str = "por unanimidade, negar provimento.") -> str:
    return (f"ACÓRDÃO<br>Vistos e relatados, acordam os Ministros da QUARTA TURMA do Superior Tribunal de Justiça, "
            f"em Sessão Virtual de {sessao}, {corpo}<br>EMENTA<br>{EMS}<br>RELATÓRIO<br>x")


def test_abertura_completa_e_data_unica_dao_prova():
    assert julgamento_no_texto(_abertura("29/09/2026 a 06/10/2026")) == ("QUARTA TURMA", "2026-09-29", "2026-10-06")
    assert julgamento_no_texto(_abertura("05/10/2026")) == ("QUARTA TURMA", "2026-10-05", "2026-10-05")
    assert julgamento_no_texto(_abertura("26/02/2024 a 29/02/2024"))[2] == "2024-02-29"  # bissexto


def test_formula_fora_da_abertura_nao_da_prova():
    # a fórmula só aparece depois do marcador EMENTA (citação de outro acórdão no corpo)
    citada = ("ACÓRDÃO<br>Vistos e relatados.<br>EMENTA<br>Conforme precedente, acordam os Ministros da QUARTA TURMA "
              "do Superior Tribunal de Justiça, em Sessão Virtual de 29/09/2026 a 06/10/2026, por unanimidade.")
    assert julgamento_no_texto(citada) is None
    # sem marcador EMENTA não há abertura delimitada
    assert julgamento_no_texto(_abertura("29/09/2026 a 06/10/2026").replace("EMENTA", "RESUMO")) is None
    # a citação no corpo não torna repetida a fórmula da abertura: a abertura prevalece
    com_citacao = _abertura("29/09/2026 a 06/10/2026") + (
        "<br>Precedente: acordam os Ministros da TERCEIRA TURMA do Superior Tribunal de Justiça, "
        "em Sessão Virtual de 01/03/2020 a 08/03/2020.")
    assert julgamento_no_texto(com_citacao) == ("QUARTA TURMA", "2026-09-29", "2026-10-06")


def test_formula_repetida_na_abertura_nao_da_prova():
    dupla = ("ACÓRDÃO<br>acordam os Ministros da QUARTA TURMA do Superior Tribunal de Justiça, em Sessão Virtual de "
             "29/09/2026 a 06/10/2026; acordam os Ministros da QUARTA TURMA do Superior Tribunal de Justiça, "
             "em Sessão Virtual de 13/10/2026.<br>EMENTA<br>x")
    assert julgamento_no_texto(dupla) is None


@pytest.mark.parametrize("sessao", ["29/09/2026 a", "29/09/2026 a 06/10", "29/09/2026 a 06/10/26", "29/09/2026 até",
                                    "29/09/2026 a 31/02/2026", "29/09/2026 a 28/09/2026"])
def test_intervalo_incompleto_ou_invertido_nao_recua_para_data_unica(sessao):
    assert julgamento_no_texto(_abertura(sessao, "por unanimidade.")) is None


@pytest.mark.parametrize("sessao", ["31/02/2026", "29/02/2026", "00/09/2026", "15/13/2026", "32/01/2026"])
def test_data_inexistente_no_calendario_nao_da_prova(sessao):
    assert julgamento_no_texto(_abertura(sessao)) is None


def test_recurso_com_intervalo_incompleto_nao_vincula_nem_conta_como_completo():
    zb = _zip({f"{M[0]['SeqDocumento']}.txt": _abertura("29/09/2026 a 06/10").encode("utf-8"),
               f"{M[1]['SeqDocumento']}.txt": ABERTURA})
    res = combinar(MD, zb, {r: [v[0][:5] + (EMS,)] for r, v in ESP.items()})
    assert res.descartes["sem_prova_do_julgamento"] == 1 and [k for _, k in res.vinculadas] == ["e2"]


def test_data_do_espelho_precisa_existir_no_calendario():
    texto = _abertura("01/02/2026 a 03/03/2026").encode("utf-8")
    md = json.dumps([{"SeqDocumento": 7, "tipoDocumento": "ACÓRDÃO", "numeroRegistro": "202600000001",
                      "processo": "REsp 123", "recurso": None}]).encode("utf-8")
    zb = _zip({"7.txt": texto})
    assert _data_iso("20260231") is None and _data_iso("20260228") == "2026-02-28"
    # 31/02 ficaria entre as duas datas por ordem de texto; no calendário não existe
    ruim = ("e", "REsp", "123", "QUARTA TURMA", "20260231", EMS)
    bom = ("e", "REsp", "123", "QUARTA TURMA", "20260228", EMS)
    assert not combinar(md, zb, {"202600000001": [ruim]}).vinculadas
    assert [k for _, k in combinar(md, zb, {"202600000001": [bom]}).vinculadas] == ["e"]


# ---- I3: cabeçalho local, data descriptor e extra ZIP64 contra o diretório central ------------------
import zlib  # noqa: E402

from tests.zip_util import zip_manual as _zip_manual  # noqa: E402


TXT = b"texto de teste"


def test_zip_manual_integro_e_aceito_em_todas_as_variantes():
    import hashlib
    esperado = {"1": (TXT.decode(), hashlib.sha256(TXT).hexdigest())}
    for metodo in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        assert ler_textos_detalhado(_zip_manual({"1.txt": TXT}, metodo=metodo)) == (esperado, {})
        for ass in (True, False):  # data descriptor com e sem assinatura; local zerado
            z = _zip_manual({"1.txt": TXT}, metodo=metodo, descritor=(ass, None, None, None, 4))
            assert zipfile.ZipFile(io.BytesIO(z)).read("1.txt") == TXT
            assert ler_textos_detalhado(z) == (esperado, {})
        comp = len(TXT) if metodo == zipfile.ZIP_STORED else len(zlib.compress(TXT)[2:-4])
        z = _zip_manual({"1.txt": TXT}, metodo=metodo, z64_local=(len(TXT), comp), z64_central=True)
        assert ler_textos_detalhado(z) == (esperado, {})
        z = _zip_manual({"1.txt": TXT}, metodo=metodo, z64_local=(0, 0), z64_central=True,
                        descritor=(True, None, None, None, 8))
        assert ler_textos_detalhado(z) == (esperado, {})


@pytest.mark.parametrize("kw, motivo", [
    ({"local": {"metodo": zipfile.ZIP_DEFLATED}}, "zip_local_metodo_divergente"),
    ({"local": {"flags": 0x800}}, "zip_local_flags_divergente"),
    ({"local": {"crc": 1}}, "zip_local_crc_divergente"),
    ({"local": {"comp": 3}}, "zip_local_tamanho_divergente"),
    ({"local": {"tam": 3}}, "zip_local_tamanho_divergente"),
    ({"local": {"comp": 0xFFFFFFFF}}, "zip_zip64_divergente"),  # sentinela sem extra ZIP64
    ({"descritor": (True, 123, None, None, 4)}, "zip_descriptor_divergente"),
    ({"descritor": (True, None, 3, None, 4)}, "zip_descriptor_divergente"),
    ({"descritor": (False, None, None, 3, 4)}, "zip_descriptor_divergente"),
    ({"z64_local": (3, len(TXT)), "z64_central": True}, "zip_zip64_divergente"),
    ({"z64_local": (len(TXT), 3), "z64_central": True}, "zip_zip64_divergente"),
    ({"z64_local": (0, 0), "z64_central": True, "descritor": (True, None, 3, None, 8)}, "zip_descriptor_divergente"),
])
def test_divergencia_local_central_recusa_a_entrada_com_motivo(kw, motivo):
    z = _zip_manual({"1.txt": TXT}, **kw)
    textos, recusadas = ler_textos_detalhado(z)
    assert textos == {} and recusadas == {"1": motivo}
    assert ler_textos(z) == {}  # a entrada recusada não entra


def test_entrada_recusada_e_contada_no_resultado_sem_derrubar_o_recurso():
    s0 = str(M[0]["SeqDocumento"])
    z = _zip_manual({f"{s0}.txt": ABERTURA, "999.txt": b"sem metadado"}, local={"crc": 1})
    assert ler_textos_detalhado(z)[1] == {s0: "zip_local_crc_divergente", "999": "zip_local_crc_divergente"}
    res = combinar(MD, z, ESP)
    assert not res.vinculadas
    assert res.descartes["zip_local_crc_divergente"] == 1  # o Seq com metadado
    assert res.descartes["texto_ausente_no_zip"] == 1  # o outro acórdão não está no ZIP
    assert res.orfaos == {"zip_local_crc_divergente": 1}  # a 999 não tem metadado
    # a entrada íntegra do mesmo recurso continua valendo
    ok = _zip_manual({f"{M[1]['SeqDocumento']}.txt": ABERTURA})
    esp = {r: [v[0][:5] + (EMS,)] for r, v in ESP.items()}
    assert [k for _, k in combinar(MD, ok, esp).vinculadas] == ["e2"]


def test_divergencia_de_nome_continua_recusando_o_recurso_inteiro():
    z = bytearray(_zip_manual({"1.txt": TXT}))
    z[30] = ord("2")  # nome do cabeçalho local diverge do central
    with pytest.raises(IntegrasInvalidas, match="zip_nome_divergente"):
        ler_textos(bytes(z))


# ---- M1: textos órfãos são contados e nunca vinculam ------------------------------------------------
def test_texto_sem_metadado_e_contado_e_nao_vincula():
    zb = _zip({**{f"{m['SeqDocumento']}.txt": ABERTURA for m in M}, "999.txt": ABERTURA, "1000.txt": ABERTURA})
    res = combinar(MD, zb, {r: [v[0][:5] + (EMS,)] for r, v in ESP.items()})
    assert res.orfaos == {"texto_sem_metadado": 2}
    assert sorted(i.seq for i, _ in res.vinculadas) == sorted(str(m["SeqDocumento"]) for m in M[:2])
    assert combinar(MD, ZB, ESP).orfaos == {}  # sem órfãos o relatório não os inventa


def test_texto_sem_espelho_e_contado_e_nao_vincula():
    res = combinar(MD, ZB, {REGS[0]: ESP[REGS[0]]})
    assert res.orfaos == {"texto_sem_espelho": 1} and [k for _, k in res.vinculadas] == ["e1"]
    res = combinar(MD, ZB, {})
    assert res.orfaos == {"texto_sem_espelho": 2} and not res.vinculadas
    assert res.descartes["fora_do_recorte_ou_sem_espelho"] == 2


# ---- metadados pela interpretação única (decisões 0061 a 0064) e UTF-8 estrito do ZIP (0044, item 5) ----
def test_metadados_utf8_pela_interpretacao_unica():
    assert ler_metadados(MD, "application/json") == M
    assert ler_metadados(b"\xef\xbb\xbf" + MD, "application/json") == M  # BOM UTF-8 é lido como UTF-8
    assert len(combinar(MD, ZB, ESP, "application/json").vinculadas) == 2


@pytest.mark.parametrize("corpo, ct", [
    (MD.decode("utf-8").encode("utf-16"), "application/json"),  # json.loads(bytes) aceitaria; aqui não
    (MD.decode("utf-8").encode("utf-32"), "application/json"),
    (MD, "application/json; charset=iso-8859-1"),
    (MD, "application/octet-stream"),
])
def test_metadados_fora_de_utf8_recusam_o_recurso(corpo, ct):
    with pytest.raises(IntegrasInvalidas, match="metadados_nao_utf8"):
        ler_metadados(corpo, ct)


def test_metadados_content_type_invalido_ou_json_ruim_recusam():
    with pytest.raises(IntegrasInvalidas, match="metadados_invalidos"):
        ler_metadados(b"\xff\xfe\x00", "application/json; charset=utf-8")
    with pytest.raises(IntegrasInvalidas, match="metadados_invalidos"):
        ler_metadados(b"[1,", "application/json")


def test_membro_do_zip_com_bom_ou_nao_utf8_e_descartado_sem_redecodificar():
    (t, _), = ler_textos(_zip({"1.txt": b"\xef\xbb\xbfabc"})).values()
    assert t == "﻿abc"  # sem BOM alternativo: o BOM não é engolido
    assert ler_textos(_zip({"2.txt": b"AC\xd3RD\xc3O"}))["2"][0] is None


# ---- Codex, rodada 1 do PR #10 --------------------------------------------------------------------------------
# B1: a ementa do espelho só prova o julgamento quando é a ementa PRÓPRIA, delimitada na abertura
REG_X = "202600000001"
_MD_X = json.dumps([{"SeqDocumento": 7, "tipoDocumento": "ACÓRDÃO", "numeroRegistro": REG_X,
                     "processo": "REsp 123", "recurso": None}]).encode("utf-8")
_ESP_X = {REG_X: [("x", "REsp", "123", "QUARTA TURMA", "20261001", EMS)]}
_OUTRA = "OUTRO JULGAMENTO. " + "Tese de outro processo, sem relação com o espelho. " * 8
_FORM = ("ACÓRDÃO<br>Vistos, acordam os Ministros da QUARTA TURMA do Superior Tribunal de Justiça, em Sessão "
         "Virtual de 29/09/2026 a 06/10/2026, por unanimidade.<br>EMENTA<br>")


def _vincula(texto: str):
    return combinar(_MD_X, _zip({"7.txt": texto.encode("utf-8")}), _ESP_X)


def test_b1_ementa_propria_do_espelho_vincula():
    res = _vincula(_FORM + EMS + "<br>RELATÓRIO<br>Relatório.<br>VOTO<br>Voto.")
    assert [k for _, k in res.vinculadas] == ["x"]


def test_b1_ementa_do_espelho_citada_como_precedente_em_outro_julgamento_nao_vincula():
    # prova do auditor: órgão e sessão iguais, ementa PRÓPRIA diferente, ementa esperada citada depois
    for citacao in ("PRECEDENTE CITADO: ", "Nesse sentido:<br>"):
        texto = (_FORM + _OUTRA + "<br>RELATÓRIO<br>Relatório.<br>VOTO<br>" + citacao + EMS + "<br>É o voto.")
        res = _vincula(texto)
        assert not res.vinculadas and res.descartes == {"julgamento_divergente_do_espelho": 1}
    # também com uma segunda marcação EMENTA no voto reproduzindo a esperada
    texto = _FORM + _OUTRA + "<br>RELATÓRIO<br>R.<br>EMENTA<br>" + EMS + "<br>VOTO<br>V."
    assert not _vincula(texto).vinculadas


def test_b1_ementa_sem_delimitacao_e_sem_prova():
    # sem título depois da ementa (RELATÓRIO, VOTO...) o bloco não se delimita: nada a confrontar
    res = _vincula(_FORM + _OUTRA + "<br>Precedente citado: " + EMS)
    assert not res.vinculadas and res.descartes == {"sem_prova_do_julgamento": 1}
    # ementa esperada só depois dos 3.000 primeiros caracteres: não há abertura
    res = _vincula("ACÓRDÃO<br>" + "x " * 2000 + _FORM + EMS + "<br>RELATÓRIO<br>R.")
    assert not res.vinculadas and res.descartes == {"sem_prova_do_julgamento": 1}


def test_b1_ementa_propria_e_o_bloco_ate_o_proximo_titulo():
    assert "OUTRO" in ementa_propria(_FORM + _OUTRA + "<br>RELATÓRIO<br>R.<br>VOTO<br>V.")
    assert ementa_propria(_FORM + _OUTRA) is None
    assert "V." not in ementa_propria(_FORM + _OUTRA + "<br>VOTO<br>V.")


# B2: quebras e marcação da fonte não podem fazer o intervalo incompleto recuar para data única
_QUEBRAS = ["<br>", "<br/>", "<BR />", "<p>", "</p><p>", "<div>", "&nbsp;", "&#160;", "\r\n", "\r", "\n", " ",
            " ", " ", "　", " \u200b ", " <br> ", "&nbsp;<br>"]


def _sessao(antes: str, sep: str, depois: str) -> str:
    return (f"ACÓRDÃO<br>acordam os Ministros da QUARTA TURMA do Superior Tribunal de Justiça, em Sessão Virtual de "
            f"{antes}{sep}{depois}, por unanimidade.<br>EMENTA<br>x<br>RELATÓRIO<br>y")


@pytest.mark.parametrize("sep", _QUEBRAS)
def test_b2_intervalo_incompleto_com_quebra_nao_recua_para_data_unica(sep):
    for depois in ("a 06/10", "a", "a 06/10/26", "até"):
        assert julgamento_no_texto(_sessao("29/09/2026", sep, depois)) is None, (sep, depois)
    # a quebra também pode vir DENTRO do intervalo, antes da data final inválida
    assert julgamento_no_texto(_sessao("29/09/2026", sep, "a" + sep + "31/02/2026")) is None


@pytest.mark.parametrize("sep", _QUEBRAS)
def test_b2_intervalo_completo_com_quebra_e_lido_inteiro(sep):
    assert julgamento_no_texto(_sessao("29/09/2026", sep, "a" + sep + "06/10/2026")) == (
        "QUARTA TURMA", "2026-09-29", "2026-10-06")
    assert julgamento_no_texto(_sessao("05/10/2026", sep, "")) == ("QUARTA TURMA", "2026-10-05", "2026-10-05")


def test_b2_visao_textual_nao_altera_o_hash_nem_o_texto_bruto():
    import hashlib
    bruto = (_FORM + EMS + "<br>RELATÓRIO<br>R.").replace("2026 a", "2026&nbsp;a").encode("utf-8")
    res = _vincula(bruto.decode("utf-8"))
    (integra, _), = res.vinculadas
    assert integra.sha256_texto == hashlib.sha256(bruto).hexdigest() and "&nbsp;" in integra.texto
    assert "&nbsp;" not in visao_textual(integra.texto) and "<br" not in visao_textual(integra.texto)


# I1: extra ZIP64 central contraditório não é ignorado quando os campos de 32 bits não têm sentinela
def test_i1_extra_zip64_central_contraditorio_sem_sentinela_recusa_a_entrada():
    for valores in [(len(TXT) + 1, len(TXT)), (len(TXT), len(TXT) + 1), (7,), (len(TXT), len(TXT), 99)]:
        z = _zip_manual({"1.txt": TXT}, z64_central_valores=valores)
        assert zipfile.ZipFile(io.BytesIO(z)).read("1.txt") == TXT  # zipfile ignora o extra e lê o conteúdo
        assert ler_textos_detalhado(z) == ({}, {"1": "zip_zip64_divergente"}), valores


# I2: o limite de entradas e do diretório vale ANTES de ZipFile alocar um ZipInfo por entrada
def _sem_zipfile(monkeypatch):
    def proibido(*a, **k):
        raise AssertionError("ZipFile/ZipInfo instanciado antes dos limites do diretório")
    monkeypatch.setattr(zipfile, "ZipFile", proibido)
    monkeypatch.setattr(zipfile, "ZipInfo", proibido)


def test_i2_entradas_acima_do_limite_recusadas_sem_instanciar_zipinfo(monkeypatch):
    z = _zip_manual({f"{i}.txt": b"a" for i in range(1, 5002)})
    _sem_zipfile(monkeypatch)
    with pytest.raises(IntegrasInvalidas, match="zip_entradas_excedidas"):
        ler_textos_detalhado(z)


def test_i2_diretorio_central_grande_demais_recusado_antes_de_zipfile(monkeypatch):
    z = bytearray(_zip_manual({"1.txt": b"a"}))
    fim = z.rindex(b"PK\x05\x06")
    z[fim + 12:fim + 16] = struct.pack("<I", 3 * 1024 * 1024)
    _sem_zipfile(monkeypatch)
    with pytest.raises(IntegrasInvalidas, match="zip_diretorio_excedido"):
        ler_textos_detalhado(bytes(z))


def test_i2_no_limite_exato_e_aceito():
    z = _zip_manual({f"{i}.txt": b"a" for i in range(1, 5001)})
    assert len(ler_textos_detalhado(z)[0]) == 5000


# I3: a recusa estrutural do ZIP aparece mesmo quando o metadado do Seq sai antes (tipo, registro...)
@pytest.mark.parametrize("campo, valor, descarte", [
    ("tipoDocumento", "DECISÃO", "monocratica_fora_desta_versao"),
    ("tipoDocumento", "FORMATO NOVO", "tipo_documento_desconhecido"),
    ("numeroRegistro", "123", "registro_invalido"),
    ("processo", "sem numero", "processo_invalido"),
])
def test_i3_recusa_do_zip_nao_some_por_saida_antecipada_do_metadado(campo, valor, descarte):
    md = json.dumps([dict(M[0], **{campo: valor})], ensure_ascii=False).encode("utf-8")
    z = _zip_manual({f"{M[0]['SeqDocumento']}.txt": ABERTURA}, local={"crc": 1})
    res = combinar(md, z, ESP)
    assert res.descartes == {descarte: 1} and res.orfaos == {"zip_local_crc_divergente": 1}
    assert not res.vinculadas and not res.ambiguas


def test_i3_seq_monocratico_com_crc_divergente_e_intacto_sem_crc():
    md = json.dumps([M[2]], ensure_ascii=False).encode("utf-8")
    ruim = _zip_manual({f"{M[2]['SeqDocumento']}.txt": b"decisao"}, local={"crc": 1})
    res = combinar(md, ruim, {})
    assert res.descartes == {"monocratica_fora_desta_versao": 1}
    assert res.orfaos == {"zip_local_crc_divergente": 1}
    bom = _zip_manual({f"{M[2]['SeqDocumento']}.txt": b"decisao"})
    assert combinar(md, bom, {}).orfaos == {}  # sem recusa no ZIP não há o que contar


# ---- Codex, rodada 2 do PR #10: prova positiva do caso bom; o resto é sem_prova ou recusa -----------------------
# B1 (rodada 2): a delimitação da ementa não pode ser enganada por marcação, título com texto ou segundo EMENTA
_CITADA = "<br>VOTO<br>Nesse sentido:<br>" + EMS + "<br>É o voto."


@pytest.mark.parametrize("titulo", ["RELAT<span>Ó</span>RIO", "RELAT<b>ÓRIO</b>", "<i>RELATÓRIO</i>",
                                    "RELAT<font color=red>Ó</font>RIO", "RELAT<x-novo>Ó</x-novo>RIO",
                                    "Relatório:", "RELAT&Oacute;RIO"])
def test_b2r_titulo_com_marcacao_inline_fecha_a_ementa_e_a_citada_nao_vincula(titulo):
    texto = _FORM + _OUTRA + f"<br>{titulo}<br>Relatório.{_CITADA}"
    assert ementa_propria(texto).strip() == _OUTRA.strip()  # o bloco terminou no título, não absorveu a citação
    res = _vincula(texto)
    assert not res.vinculadas and res.descartes == {"julgamento_divergente_do_espelho": 1}


@pytest.mark.parametrize("titulo", ["RELAT<span>Ó</span>RIO", "RELAT<b>ÓRIO</b>", "Relatório:", "<em>VOTO</em>"])
def test_b2r_ementa_propria_com_marcacao_inline_continua_vinculando(titulo):
    texto = _FORM + "<b>" + EMS.replace(" ", "<span> </span>", 3) + f"</b><br>{titulo}<br>Relatório."
    assert [k for _, k in _vincula(texto).vinculadas] == ["x"]


@pytest.mark.parametrize("linha", ["RELATÓRIO Cita-se: ", "VOTO: ", "RELAT<b>ÓRIO</b> texto: ", "Decisão anterior: ",
                                   "ACÓRDÃO recorrido: ", "PARECER do MPF: "])
def test_b2r_titulo_seguido_de_texto_na_mesma_linha_nao_delimita(linha):
    texto = _FORM + _OUTRA + "<br>" + linha + EMS + "<br>RELATÓRIO<br>Relatório.<br>" + EMS
    assert ementa_propria(texto) is None
    res = _vincula(texto)
    assert not res.vinculadas and res.descartes == {"sem_prova_do_julgamento": 1}


def test_b2r_segundo_marcador_ementa_antes_da_citacao_nao_delimita():
    texto = _FORM + _OUTRA + "<br>EMENTA<br>" + EMS + "<br>RELATÓRIO<br>Relatório."
    assert ementa_propria(texto) is None
    for outro in ("EMENTA", "Ementa:", "<b>EMENTA</b>", "EM<span>ENTA</span>"):
        t = _FORM + _OUTRA + f"<br>{outro}<br>" + EMS + "<br>RELATÓRIO<br>R."
        assert not _vincula(t).vinculadas and ementa_propria(t) is None


def test_b2r_marcador_ementa_depois_do_titulo_nao_atrapalha_a_ementa_propria():
    # como nos textos da fixture: o EMENTA repetido vem depois do RELATÓRIO
    texto = _FORM + EMS + "<br>RELATÓRIO<br>Relatório.<br>EMENTA<br>" + EMS + "<br>VOTO<br>V."
    assert [k for _, k in _vincula(texto).vinculadas] == ["x"]


@pytest.mark.parametrize("residuo", ["&lt;br&gt;", "&#60;br&#62;", "&lt;/span&gt;", "a < b", "x > y", "&amp;lt;b&amp;gt;"])
def test_b2r_residuo_de_marcacao_no_bloco_nao_da_prova(residuo):
    # entidades viram texto e nunca são reinterpretadas como tag; resíduo < ou > no bloco: sem prova
    texto = _FORM + EMS + f" {residuo}" + "<br>RELATÓRIO<br>R."
    if residuo.startswith("&amp;"):  # "&amp;lt;" decodifica uma vez para "&lt;": texto sem < nem >
        assert [k for _, k in _vincula(texto).vinculadas] == ["x"]
    else:
        assert ementa_propria(texto) is None
        assert not _vincula(texto).vinculadas


def test_b2r_visao_textual_remove_inline_sem_espaco_e_decodifica_depois():
    assert visao_textual("RELAT<span>Ó</span>RIO") == "RELATÓRIO"
    assert visao_textual("a<b>b</b><i>c</i><em>d</em><strong>e</strong><u>f</u><sup>g</sup><sub>h</sub>") == "abcdefgh"
    assert visao_textual("a<br>b<p>c</p>d<div>e</div><li>f<tr>g<h1>h</h1>i") == "a\nb\nc\nd\ne\nf\ng\nh\ni"
    assert visao_textual("&lt;br&gt;") == "<br>"  # texto, não quebra
    assert visao_textual("a&nbsp;b c d") == "a b c d"
    assert visao_textual("a<!-- <br> -->b") == "ab"
    assert visao_textual("<param>x<pre>y") == "xy"  # `param` e `pre` não são `p`


# B2 (rodada 2): data única só com terminador explícito
@pytest.mark.parametrize("sessao", [
    "29/09/2026 at<b>é</b> 06/10", "29/09/2026 at<span>é</span> 06/10/26", "29/09/2026 a<b></b>té 06/10",
    "29/09/2026&lt;br&gt;a 06/10", "29/09/2026 &#60;br&#62; a 06/10", "29/09/2026&lt;/b&gt;",
    "29/09/2026 &amp;lt;br&amp;gt;a 06/10", "29/09/2026 <b>a</b> 06/10", "29/09/2026 <span>a</span>",
    "29/09/2026 (a 06/10/2026)", "29/09/2026 xyz", "29/09/2026 e 06/10/2026", "29/09/2026 - 06/10/2026",
    "29/09/2026 a 06/10/2026 xyz", "29/09/2026 a 06/10/2026/", "29/09/2026 a 06/10/2026&lt;br&gt;",
])
def test_b2r_resto_nao_reconhecido_depois_da_data_nao_da_prova(sessao):
    assert julgamento_no_texto(_abertura(sessao, "por unanimidade.")) is None, sessao


def test_b2r_data_sem_terminador_nem_virgula_nao_da_prova():
    sem = ("ACÓRDÃO<br>acordam os Ministros da QUARTA TURMA do Superior Tribunal de Justiça, em Sessão Virtual de "
           "29/09/2026 por unanimidade.<br>EMENTA<br>x<br>RELATÓRIO<br>y")
    assert julgamento_no_texto(sem) is None


@pytest.mark.parametrize("fecho", [",", ".", ";", ")", " , ", "\n", "<br>", "</p>", ""])
@pytest.mark.parametrize("sessao, esperado", [
    ("05/10/2026", ("QUARTA TURMA", "2026-10-05", "2026-10-05")),
    ("29/09/2026 a 06/10/2026", ("QUARTA TURMA", "2026-09-29", "2026-10-06"))])
def test_b2r_terminador_explicito_da_prova(sessao, esperado, fecho):
    abre = "(" if fecho == ")" else ""
    resto = " por unanimidade" if fecho in (",", ".", ";", ")", " , ") else ""
    texto = ("ACÓRDÃO<br>" + abre + "acordam os Ministros da QUARTA TURMA do Superior Tribunal de Justiça, em "
             f"Sessão Virtual de {sessao}{fecho}{resto}<br>EMENTA<br>x<br>RELATÓRIO<br>y")
    assert julgamento_no_texto(texto) == esperado, (sessao, fecho)


def test_b2r_virgula_seguida_de_continuacao_de_intervalo_nao_recua():
    assert julgamento_no_texto(_abertura("29/09/2026, a 06/10/2026")) is None
    assert julgamento_no_texto(_abertura("29/09/2026, a unanimidade", "")) is not None  # "a unanimidade" não é data


# I1 (rodada 2): extra ZIP64 central exatamente igual ao das sentinelas (APPNOTE 4.5.3)
@pytest.mark.parametrize("valores", [(3, 0), (0,), (3,), (len(TXT), len(TXT)), (), (0, 0, 0), (len(TXT), len(TXT), 0, 0)])
def test_i1r_extra_zip64_sem_nenhuma_sentinela_recusa(valores):
    z = _zip_manual({"1.txt": TXT}, z64_central_valores=valores)
    assert ler_textos_detalhado(z) == ({}, {"1": "zip_zip64_divergente"}), valores


@pytest.mark.parametrize("sentinelas, valores", [
    (("tam",), (len(TXT), 0)),  # (3, 0): um campo a mais do que as sentinelas
    (("tam",), (len(TXT), len(TXT))),
    (("tam", "comp"), (len(TXT), len(TXT), 0)),
    (("comp",), (len(TXT), len(TXT))),
])
def test_i1r_extra_zip64_com_numero_de_campos_diferente_das_sentinelas_recusa(sentinelas, valores):
    z = _zip_manual({"1.txt": TXT}, z64_central_valores=valores, z64_central_sentinelas=sentinelas)
    assert ler_textos_detalhado(z) == ({}, {"1": "zip_zip64_divergente"}), (sentinelas, valores)


@pytest.mark.parametrize("valores", [(len(TXT),), ()])
def test_i1r_extra_zip64_curto_para_as_sentinelas_recusa_o_arquivo(valores):
    # com sentinela e campo faltando o próprio zipfile recusa; o recurso inteiro vira zip_invalido
    z = _zip_manual({"1.txt": TXT}, z64_central_valores=valores, z64_central_sentinelas=("tam", "comp"))
    with pytest.raises(IntegrasInvalidas, match="zip_invalido"):
        ler_textos_detalhado(z)


def test_i1r_extra_zip64_com_as_sentinelas_exatas_e_aceito():
    import hashlib
    ok = {"1": (TXT.decode(), hashlib.sha256(TXT).hexdigest())}
    assert ler_textos_detalhado(_zip_manual({"1.txt": TXT}, z64_central=True)) == (ok, {})  # tam e comp
    z = _zip_manual({"1.txt": TXT}, z64_central_valores=(len(TXT),), z64_central_sentinelas=("tam",))
    assert zipfile.ZipFile(io.BytesIO(z)).read("1.txt") == TXT and ler_textos_detalhado(z) == (ok, {})
    z = _zip_manual({"1.txt": TXT}, z64_central_valores=(len(TXT),), z64_central_sentinelas=("comp",))
    assert ler_textos_detalhado(z) == (ok, {})


def test_i1r_extra_zip64_repetido_ou_malformado_recusa():
    z = bytearray(_zip_manual({"1.txt": TXT}, z64_central_valores=(len(TXT), len(TXT)), z64_central_sentinelas=("tam", "comp")))
    c = z.index(b"PK\x01\x02")
    n_nome = struct.unpack("<H", z[c + 28:c + 30])[0]
    z[c + 46 + n_nome + 2] = 15  # tamanho declarado do extra deixa de caber/ser múltiplo de 8
    try:
        assert ler_textos_detalhado(bytes(z))[1].get("1") == "zip_zip64_divergente"
    except IntegrasInvalidas as exc:  # ou o próprio zipfile recusa o extra corrompido
        assert str(exc) == "zip_invalido"


# I2 (rodada 2): o diretório central efetivo é percorrido antes de ZipFile; contagem e tamanho são reconciliados
def _eocd_editado(z: bytes, *, total=None, tam=None, desloc=None) -> bytes:
    b = bytearray(z)
    pos = bytes(b).rindex(b"PK\x05\x06")
    if total is not None:
        b[pos + 8:pos + 12] = struct.pack("<HH", total, total)
    if tam is not None:
        b[pos + 12:pos + 16] = struct.pack("<I", tam)
    if desloc is not None:
        b[pos + 16:pos + 20] = struct.pack("<I", desloc)
    return bytes(b)


def _com_eocd64(z: bytes, *, total=None, tam=None) -> bytes:
    pos = z.rindex(b"PK\x05\x06")
    ent = struct.unpack("<H", z[pos + 10:pos + 12])[0]
    tam_r = struct.unpack("<I", z[pos + 12:pos + 16])[0]
    off_r = struct.unpack("<I", z[pos + 16:pos + 20])[0]
    n = ent if total is None else total
    e64 = struct.pack("<4sQHHIIQQQQ", b"PK\x06\x06", 44, 45, 45, 0, 0, n, n, tam_r if tam is None else tam, off_r)
    loc = struct.pack("<4sIQI", b"PK\x06\x07", 0, pos, 1)
    eocd = struct.pack("<4sHHHHIIH", b"PK\x05\x06", 0, 0, 0xFFFF, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0)
    return z[:pos] + e64 + loc + eocd


def _muitos(n: int) -> bytes:
    return _zip_manual({f"{i}.txt": b"a" for i in range(1, n + 1)})


_MUTACOES = {
    # (nome) -> (construtor do ZIP, motivo esperado)
    "5001_reais_declara_1": (lambda: _eocd_editado(_muitos(5001), total=1), "zip_entradas_excedidas"),
    "20000_reais_declara_1": (lambda: _eocd_editado(_muitos(20000), total=1), "zip_entradas_excedidas"),
    "40000_reais_declara_1": (lambda: _eocd_editado(_muitos(40000), total=1), "zip_diretorio_excedido"),
    "1_real_declara_5001": (lambda: _eocd_editado(_muitos(1), total=5001), "zip_entradas_excedidas"),
    "1_real_tamanho_3MiB": (lambda: _eocd_editado(_muitos(1), tam=3 * 1024 * 1024), "zip_diretorio_excedido"),
    "3_reais_declara_2": (lambda: _eocd_editado(_muitos(3), total=2), "zip_diretorio_divergente"),
    "1_real_declara_2": (lambda: _eocd_editado(_muitos(1), total=2), "zip_diretorio_divergente"),
    "eocd64_declara_5001": (lambda: _com_eocd64(_muitos(1), total=5001), "zip_entradas_excedidas"),
    "eocd64_5001_reais_declara_1": (lambda: _com_eocd64(_muitos(5001), total=1), "zip_entradas_excedidas"),
    "eocd64_tamanho_3MiB": (lambda: _com_eocd64(_muitos(1), tam=3 * 1024 * 1024), "zip_diretorio_excedido"),
    "eocd64_2_reais_declara_3": (lambda: _com_eocd64(_muitos(2), total=3), "zip_diretorio_divergente"),
}


@pytest.mark.parametrize("nome", sorted(_MUTACOES))
def test_i2r_mutacao_do_diretorio_recusada_sem_instanciar_zipfile_nem_zipinfo(nome, monkeypatch):
    construir, motivo = _MUTACOES[nome]
    z = construir()
    _sem_zipfile(monkeypatch)
    with pytest.raises(IntegrasInvalidas, match=motivo):
        ler_textos_detalhado(z)


def test_i2r_tamanho_declarado_maior_que_o_percorrido_nao_instancia_zipfile(monkeypatch):
    z = _eocd_editado(_muitos(2), tam=struct.unpack("<I", _muitos(2)[-10:-6])[0] + 10)
    _sem_zipfile(monkeypatch)
    with pytest.raises(IntegrasInvalidas):
        ler_textos_detalhado(z)


def test_i2r_eocd64_verdadeiro_e_aceito_e_o_zipinfo_so_aparece_depois_dos_limites():
    z = _com_eocd64(_muitos(3))
    assert zipfile.ZipFile(io.BytesIO(z)).namelist() == ["1.txt", "2.txt", "3.txt"]
    assert sorted(ler_textos_detalhado(z)[0]) == ["1", "2", "3"]


def test_i2r_zip_comum_com_comentario_e_aceito():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("1.txt", b"abc")
        zf.comment = b"comentario do arquivo"
    assert list(ler_textos_detalhado(buf.getvalue())[0]) == ["1"]
