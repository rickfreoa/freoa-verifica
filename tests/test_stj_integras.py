"""Íntegras do STJ (decisão 0044): vínculo por identidade de metadados, ZIP estrito, ambiguidade e filtro da ementa."""

import hashlib
import io
import json
import struct
import zipfile
import zlib
from pathlib import Path

import pytest

from freoa_verifica.connectors.stj_integras import (
    IntegrasInvalidas, MAX_RAZAO, _data_iso, _normal, _publicacao_do_espelho, classe_tokens, combinar,
    ler_metadados, ler_textos, ler_textos_detalhado)
from tests.zip_util import zip_manual as _zip_manual

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
# AREsp 3264125; a terceira é monocrática. Os espelhos usados aqui derivam do próprio texto e dos metadados (não são
# conjunto-ouro independente): provam o mecanismo de vínculo, não a taxa de acerto contra espelhos reais do acervo.
_TXT = {s: t for s, (t, _) in ler_textos(ZB).items()}
PUB = "DJEN       DATA:08/10/2026"  # formato real de `dataPublicacao` do espelho (amostra do STJ); metadados: 2026-10-08


def _ementa_de(seq) -> str:
    """Trecho da ementa do texto da fixture, como a ementa do espelho (derivada, não independente)."""
    t = _TXT[str(seq)].split("EMENTA<br>", 1)[1].replace("<br>", " ")
    i = t.index(" ", 50)
    return t[i:t.rindex(" ", 0, i + 500)]


def _esp(chave="x", classe="REsp", numero="123", ementa=None, pub=PUB):
    """Espelho: (chave, siglaClasse, numeroProcesso, nomeOrgaoJulgador, dataDecisao, ementa, dataPublicacao)."""
    return (chave, classe, numero, "QUARTA TURMA", "20261001", EMS if ementa is None else ementa, pub)


EM0, EM1 = _ementa_de(M[0]["SeqDocumento"]), _ementa_de(M[1]["SeqDocumento"])
EMS = "AGRAVO INTERNO NOS EMBARGOS DE DECLARAÇÃO NO RECURSO ESPECIAL. " + "Tese sintética da ementa. " * 8
ESP = {REGS[0]: [_esp("e1", "REsp", "2280461", EM0)],
       REGS[1]: [_esp("e2", "EDcl no AREsp", "3264125", EM1)]}
ABERTURA = ("ACÓRDÃO<br>Vistos e relatados estes autos em que são partes as acima indicadas, acordam os Ministros "
            "da QUARTA TURMA do Superior Tribunal de Justiça, em Sessão Virtual de 29/09/2026 a 06/10/2026, "
            "por unanimidade, negar provimento.<br>EMENTA<br>").encode("utf-8") + EMS.encode("utf-8") + \
    "<br>RELATÓRIO<br>Relatório do caso.".encode("utf-8")


def _esp_ems():
    return {r: [v[0][:5] + (EMS, PUB)] for r, v in ESP.items()}


def test_fixture_sintetica_vincula_acordaos_e_descarta_monocratica():
    res = combinar(MD, ZB, ESP)
    assert [(i.numero_registro, k) for i, k in res.vinculadas] == [(REGS[0], "e1"), (REGS[1], "e2")]
    assert res.descartes == {"monocratica_fora_desta_versao": 1}
    integra = res.vinculadas[0][0]
    assert integra.tipo == "acordao" and len(integra.sha256_texto) == 64
    assert "<br" not in integra.texto_limpo.lower() and integra.texto_limpo


def test_mesmo_registro_outro_grau_recursal_nao_vincula():
    # só o espelho do AREsp no acervo: a íntegra dos EDcl não pode cair nele
    res = combinar(MD, ZB, {REGS[1]: [_esp("e2", "AREsp", "3264125", EM1)],
                            REGS[0]: [_esp("e1", "AgInt no REsp", "2280461", EM0)]})
    assert not res.vinculadas and res.descartes["classe_nao_identica"] == 2


def test_numero_divergente_nao_vincula():
    res = combinar(MD, ZB, {REGS[0]: [_esp("e1", "REsp", "9999999", EM0)]})
    assert not res.vinculadas and res.descartes["numero_divergente"] == 1


def test_sem_espelho_e_descartado_e_contado():
    res = combinar(MD, ZB, {})
    assert not res.vinculadas and res.descartes["fora_do_recorte_ou_sem_espelho"] == 2


def test_dois_espelhos_candidatos_e_ambiguo_nunca_escolhe():
    res = combinar(MD, ZB, {**ESP, REGS[0]: [ESP[REGS[0]][0], _esp("e9", "REsp", "2280461", EM0)]})
    assert len(res.ambiguas) == 1 and res.ambiguas[0][1] == ["e1", "e9"]
    assert [k for _, k in res.vinculadas] == ["e2"]


def test_duas_integras_do_mesmo_acordao_no_dia_sao_ambiguas():
    dup = dict(M[0], SeqDocumento=1)
    md = json.dumps(M + [dup], ensure_ascii=False).encode("utf-8")
    zb = _zip({**{f"{m['SeqDocumento']}.txt": ABERTURA for m in M}, "1.txt": ABERTURA + b" y"})
    res = combinar(md, zb, _esp_ems())
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
    assert ler_textos(_zip({"1.txt": b"a"}, zipfile.ZIP_STORED)) == {"1": ("a", hashlib.sha256(b"a").hexdigest())}
    with pytest.raises(IntegrasInvalidas):
        ler_textos(_zip({"1.txt\n": b"a"}))
    with pytest.raises(IntegrasInvalidas):
        ler_textos(_zip({"\u0661.txt": b"a"}))


# ---- vínculo por identidade de metadados: classe idêntica, número e data de publicação ---------------------------
def _md_x(**campos) -> bytes:
    base = {"SeqDocumento": 7, "tipoDocumento": "ACÓRDÃO", "numeroRegistro": "202600000001", "processo": "REsp 123",
            "recurso": None, "dataPublicacao": "2026-10-08"}
    return json.dumps([{**base, **campos}], ensure_ascii=False).encode("utf-8")


REG_X = "202600000001"
_MD_X = _md_x()
_ESP_X = {REG_X: [_esp()]}


def _vincula(texto: str, md: bytes = _MD_X, esp=_ESP_X):
    return combinar(md, _zip({"7.txt": texto.encode("utf-8")}), esp)


def test_cadeia_de_classe_identica_vincula_e_a_nao_identica_nao_vincula():
    # recurso="AgInt" + "REsp 123": a cadeia dos metadados é (AgInt, REsp); AgInt nos EDcl no REsp é outra
    md = _md_x(recurso="AgInt")
    texto = ABERTURA.decode("utf-8")
    assert [k for _, k in _vincula(texto, md, {REG_X: [_esp("a", "AgInt no REsp")]}).vinculadas] == ["a"]
    res = _vincula(texto, md, {REG_X: [_esp("fundo", "AgInt nos EDcl no REsp")]})
    assert not res.vinculadas and res.descartes == {"classe_nao_identica": 1}
    # raso e fundo juntos: só o de cadeia idêntica é candidato
    esps = {REG_X: [_esp("fundo", "AgInt nos EDcl no REsp"), _esp("raso", "AgInt no REsp")]}
    assert [k for _, k in _vincula(texto, md, esps).vinculadas] == ["raso"]
    # sem recurso nos metadados, REsp não casa com AgInt no REsp
    res = _vincula(texto, _MD_X, {REG_X: [_esp("a", "AgInt no REsp")]})
    assert not res.vinculadas and res.descartes == {"classe_nao_identica": 1}
    # graus intermediários não são livres
    assert not _vincula(texto, _md_x(recurso="EDcl"), {REG_X: [_esp("a", "EDcl nos EDcl no REsp")]}).vinculadas


def test_aginte_contra_aginte_nos_edcl_e_classe_nao_identica():
    # AgInt nos metadados × AgInt nos EDcl no REsp no espelho: perda aceita (decisão 0044, limites conhecidos)
    res = _vincula(ABERTURA.decode("utf-8"), _md_x(recurso="AgInt"), {REG_X: [_esp("b", "AgInt nos EDcl no REsp")]})
    assert not res.vinculadas and res.descartes == {"classe_nao_identica": 1}


def test_data_de_publicacao_divergente_nao_vincula_e_e_contada():
    res = _vincula(ABERTURA.decode("utf-8"), _md_x(dataPublicacao="2026-10-09"))
    assert not res.vinculadas and res.descartes == {"data_publicacao_divergente": 1}


@pytest.mark.parametrize("pub", ["DJEN       DATA:31/02/2026", "DJEN DATA:08/10/26", "08/10/2026", "DJE DATA:", "",
                                 "DJEN DATA:08/10/2026 e mais", "DJ DATA:08/10/2026", "DJEN       DATA:00/10/2026",
                                 "2026-10-08T00:00", "20261008", None, 20261008])
def test_data_de_publicacao_do_espelho_ilegivel_torna_o_espelho_nao_candidato(pub):
    res = _vincula(ABERTURA.decode("utf-8"), esp={REG_X: [_esp(pub=pub)]})
    assert not res.vinculadas and res.descartes == {"data_publicacao_espelho_ilegivel": 1}


@pytest.mark.parametrize("pub", ["DJEN       DATA:08/10/2026", "DJE        DATA:08/10/2026", "DJE DATA: 08/10/2026",
                                 "DJEN DATA:08/10/2026", "2026-10-08"])
def test_data_de_publicacao_do_espelho_em_formato_inequivoco_vincula(pub):
    assert [k for _, k in _vincula(ABERTURA.decode("utf-8"), esp={REG_X: [_esp(pub=pub)]}).vinculadas] == ["x"]


def test_normalizacao_de_datas():
    assert _publicacao_do_espelho("DJEN       DATA:27/10/2025") == "2025-10-27"
    assert _publicacao_do_espelho("DJE        DATA:27/09/2024") == "2024-09-27"
    assert _publicacao_do_espelho("2026-10-08") == "2026-10-08"
    assert _publicacao_do_espelho("DJEN       DATA:29/02/2026") is None  # 2026 não é bissexto
    assert _publicacao_do_espelho("DJEN       DATA:29/02/2024") == "2024-02-29"
    assert _data_iso("2026-02-31") is None and _data_iso("08/10/2026") is None and _data_iso(None) is None


def test_data_de_publicacao_dos_metadados_ilegivel_nao_vincula():
    res = _vincula(ABERTURA.decode("utf-8"), _md_x(dataPublicacao="08/10/2026"))
    assert not res.vinculadas and res.descartes == {"data_publicacao_metadado_ilegivel": 1}
    assert not _vincula(ABERTURA.decode("utf-8"), _md_x(dataPublicacao=None)).vinculadas


def test_motivo_do_espelho_que_foi_mais_longe():
    esps = {REG_X: [_esp("a", "AREsp"), _esp("b", "REsp", "999"), _esp("c", "REsp", "123", pub="DJEN DATA:09/10/2026")]}
    assert _vincula(ABERTURA.decode("utf-8"), esp=esps).descartes == {"data_publicacao_divergente": 1}
    assert _vincula(ABERTURA.decode("utf-8"), esp={REG_X: esps[REG_X][:2]}).descartes == {"numero_divergente": 1}


def test_troca_dos_textos_da_fixture_nao_vincula():
    # bytes do EDcl no AREsp 3264125 sob o Seq do REsp 2280461: a ementa do espelho e1 não ocorre nesse texto
    s0, s1 = str(M[0]["SeqDocumento"]), str(M[1]["SeqDocumento"])
    zb = _zip({f"{s0}.txt": _TXT[s1].encode("utf-8"), f"{s1}.txt": _TXT[s1].encode("utf-8")})
    res = combinar(MD, zb, ESP)
    assert [k for _, k in res.vinculadas] == ["e2"]
    assert res.descartes["ementa_ausente_no_texto"] == 1


def test_espelho_sem_ementa_ou_curta_nao_vincula():
    for em in ("", "curta", "x" * 119):
        res = _vincula(ABERTURA.decode("utf-8"), esp={REG_X: [_esp(ementa=em)]})
        assert not res.vinculadas and res.descartes == {"ementa_ausente_no_texto": 1}


def test_ementa_do_espelho_e_conferida_nos_primeiros_400_caracteres():
    longa = "Tese longa e distinta do julgamento. " * 20  # mais de 700 caracteres
    texto = "ACÓRDÃO<br>EMENTA<br>" + longa[:420] + " fim diferente do espelho.<br>VOTO"
    assert [k for _, k in _vincula(texto, esp={REG_X: [_esp(ementa=longa)]}).vinculadas] == ["x"]
    errada = longa[:390] + "XXXXXXXXXXXX" + longa[402:]  # diverge dentro dos 400 primeiros
    assert not _vincula(texto, esp={REG_X: [_esp(ementa=errada)]}).vinculadas


def test_orgao_e_data_de_julgamento_do_espelho_nao_entram_no_vinculo():
    e = ("x", "REsp", "123", "OUTRA TURMA QUALQUER", "19990101", EMS, PUB)
    assert [k for _, k in _vincula(ABERTURA.decode("utf-8"), esp={REG_X: [e]}).vinculadas] == ["x"]


def test_espelhos_em_gerador_sao_materializados_uma_vez():
    esp = {r: iter(v) for r, v in ESP.items()}
    assert len(combinar(MD, ZB, esp).vinculadas) == 2


def test_metadado_nao_objeto_e_tipo_desconhecido():
    with pytest.raises(IntegrasInvalidas, match="nao_objeto"):
        combinar(json.dumps([None, 1]).encode(), ZB, ESP)
    md = json.dumps([dict(M[0], tipoDocumento="FORMATO NOVO")], ensure_ascii=False).encode("utf-8")
    assert combinar(md, ZB, ESP).descartes == {"tipo_documento_desconhecido": 1}


# ---- unicidade dupla -------------------------------------------------------------------------------------------
def test_dois_acordaos_do_mesmo_registro_no_dia_sao_ambiguos_em_qualquer_classe():
    # (ii): mesmo registro, classes diferentes (REsp e AgInt no REsp): o par fica ambiguous e nada vincula
    dois = json.dumps([json.loads(_md_x())[0], json.loads(_md_x(SeqDocumento=8, recurso="AgInt"))[0]]).encode()
    zb = _zip({"7.txt": ABERTURA, "8.txt": ABERTURA})
    res = combinar(dois, zb, {REG_X: [_esp("x")]})
    assert not res.vinculadas and sorted(i.seq for i, _ in res.ambiguas) == ["7", "8"]
    assert res.descartes == {}


def test_acordao_do_registro_sem_texto_ainda_conta_na_unicidade():
    dois = json.dumps([json.loads(_md_x())[0], json.loads(_md_x(SeqDocumento=8, recurso="AgInt"))[0]]).encode()
    res = combinar(dois, _zip({"7.txt": ABERTURA}), {REG_X: [_esp("x")]})  # o 8 não está no ZIP
    assert not res.vinculadas and [i.seq for i, _ in res.ambiguas] == ["7"]
    assert res.descartes == {"texto_ausente_no_zip": 1}


def test_decisao_monocratica_do_mesmo_registro_nao_quebra_a_unicidade():
    dois = json.dumps([json.loads(_md_x())[0], json.loads(_md_x(SeqDocumento=8, tipoDocumento="DECISÃO"))[0]]).encode()
    res = combinar(dois, _zip({"7.txt": ABERTURA}), {REG_X: [_esp("x")]})
    assert [k for _, k in res.vinculadas] == ["x"] and not res.ambiguas


def test_duplicata_identica_de_metadados_conta_uma_vez():
    md = json.dumps(json.loads(_md_x()) * 2).encode()
    res = combinar(md, _zip({"7.txt": ABERTURA}), {REG_X: [_esp("x")]})
    assert [k for _, k in res.vinculadas] == ["x"] and res.descartes == {"seq_duplicado_identico": 1}


# ---- o texto não influi no vínculo (Codex, rodadas 1 a 3) ---------------------------------------------------------
_OUTRA = "OUTRO JULGAMENTO. " + "Tese de outro processo, sem relação com o espelho. " * 8
_FORM = ("ACÓRDÃO<br>Vistos, acordam os Ministros da QUARTA TURMA do Superior Tribunal de Justiça, em Sessão "
         "Virtual de 29/09/2026 a 06/10/2026, por unanimidade.<br>EMENTA<br>")
_TITULOS = [
    "RELAT<br>ÓRIO", "RELAT\nÓRIO", "RELAT&#10;ÓRIO", "RELAT ÓRIO", "RELAT<![CDATA[Ó]]>RIO", "RELAT&amp;Oacute;RIO",
    "RELAT<span>Ó</span>RIO", "RELAT<b>ÓRIO</b>", "<i>RELATÓRIO</i>", "RELAT<font color=red>Ó</font>RIO",
    "RELAT<x-novo>Ó</x-novo>RIO", "Relatório:", "RELAT&Oacute;RIO", "RELATÓRIO Cita-se:", "VOTO:", "RELATÓRIO",
    "EMENTA", "Ementa:", "<b>EMENTA</b>", "EM<span>ENTA</span>", "ACÓRDÃO recorrido:", "PARECER do MPF:",
]
_RESIDUOS = ["&lt;br&gt;", "&#60;br&#62;", "&lt;/span&gt;", "a < b", "x > y", "&amp;lt;b&amp;gt;"]


def _citada(titulo: str) -> str:
    """Julgamento de outro processo (ementa própria diferente) com a ementa do espelho só citada depois."""
    return _FORM + _OUTRA + f"<br>{titulo}<br>Relatório.<br>VOTO<br>Nesse sentido:<br>" + EMS + "<br>É o voto."


@pytest.mark.parametrize("titulo", _TITULOS)
@pytest.mark.parametrize("metadado, motivo", [
    ({"processo": "REsp 124"}, "numero_divergente"),
    ({"dataPublicacao": "2026-10-09"}, "data_publicacao_divergente"),
    ({"recurso": "AgInt"}, "classe_nao_identica"),
])
def test_r3_b1_ementa_so_citada_com_metadados_que_nao_identificam_o_espelho_nao_vincula(titulo, metadado, motivo):
    res = _vincula(_citada(titulo), _md_x(**metadado))
    assert not res.vinculadas and not res.ambiguas and res.descartes == {motivo: 1}


@pytest.mark.parametrize("titulo", _TITULOS)
def test_r3_b1_dois_acordaos_do_mesmo_registro_no_dia_com_ementa_citada_sao_ambiguous(titulo):
    dois = json.dumps([json.loads(_md_x())[0], json.loads(_md_x(SeqDocumento=8, recurso="EDcl"))[0]]).encode()
    zb = _zip({"7.txt": _citada(titulo).encode("utf-8"), "8.txt": _citada(titulo).encode("utf-8")})
    res = combinar(dois, zb, {REG_X: [_esp("x")]})
    assert not res.vinculadas and sorted(i.seq for i, _ in res.ambiguas) == ["7", "8"]


@pytest.mark.parametrize("residuo", _RESIDUOS)
def test_marcacao_residual_na_ementa_citada_nao_vincula_sem_identidade_de_metadados(residuo):
    texto = _FORM + _OUTRA + "<br>RELATÓRIO<br>R.<br>" + EMS + f" {residuo}<br>VOTO<br>V."
    res = _vincula(texto, _md_x(processo="REsp 124"))
    assert not res.vinculadas and res.descartes == {"numero_divergente": 1}


def test_ementa_do_espelho_ausente_do_texto_nao_vincula_mesmo_com_metadados_identicos():
    res = _vincula(_FORM + _OUTRA + "<br>RELATÓRIO<br>Relatório.<br>VOTO<br>V.")
    assert not res.vinculadas and res.descartes == {"ementa_ausente_no_texto": 1}


@pytest.mark.parametrize("texto", [
    "a ementa só aparece aqui: " + EMS,
    EMS.replace(" ", "<span> </span>", 3),
    "<b>" + EMS.replace(" ", "&nbsp;") + "</b>",
    "<p>" + EMS.upper() + "</p>",
    "RELAT&amp;Oacute;RIO " + EMS + " <!-- comentario -->",
])
def test_ementa_presente_no_texto_em_qualquer_forma_normalizavel_passa_o_filtro(texto):
    assert [k for _, k in _vincula(texto).vinculadas] == ["x"]


def test_normalizacao_unica_e_fraca():
    assert _normal("a<br>b<![CDATA[c]]>d&amp;lt;e&nbsp;F\u200b g<!-- x -->h") == "a b d&lt;e f g h"
    assert _normal("<>x<<y>") == "x<"  # só `<...>` sem `<`/`>` internos vira espaço
    assert _normal("Ação  EMENTA") == "acao ementa"
    assert _normal("&amp;Oacute;") == "&oacute;"  # decodifica uma vez, nunca duas


_SESSOES = [
    "", "29/09/2026 a 06/10/2026", "29/09/2026", "29/09/2026 a", "29/09/2026 a 06/10", "29/09/2026 até",
    "29/09/2026, (a 06/10)", "29/09/2026,&lt;br&gt;a 06/10", "29/09/2026, &amp;lt;br&amp;gt;a 06/10",
    "29/09/2026 at<b>é</b> 06/10", "29/09/2026 &#60;br&#62; a 06/10", "29/09/2026 a 31/02/2026",
    "29/09/2026 a 28/09/2026", "31/02/2026", "99/99/9999", "29/09/2026 xyz", "29/09/2026, a 06/10/2026",
]


def _abertura_com(sessao: str, orgao: str = "QUARTA TURMA") -> str:
    return (f"ACÓRDÃO<br>acordam os Ministros da {orgao} do Superior Tribunal de Justiça, em Sessão Virtual de "
            f"{sessao}, por unanimidade.<br>EMENTA<br>{EMS}<br>RELATÓRIO<br>y")


def _resumo(res):
    return ([k for _, k in res.vinculadas], [(i.seq, ks) for i, ks in res.ambiguas], res.descartes, res.orfaos)


@pytest.mark.parametrize("sessao", _SESSOES)
def test_r3_b2_o_texto_da_sessao_nao_influi_no_vinculo(sessao):
    referencia = _resumo(_vincula(_abertura_com("29/09/2026 a 06/10/2026")))
    assert referencia[0] == ["x"]
    assert _resumo(_vincula(_abertura_com(sessao))) == referencia
    # e o órgão do texto também não: o órgão é sempre o do espelho
    assert _resumo(_vincula(_abertura_com(sessao, "TERCEIRA SEÇÃO"))) == referencia
    # com metadados que não identificam o espelho, nenhuma sessão forjada cria vínculo (r3 B2: antes `indevido`)
    forjado = _vincula(_abertura_com(sessao), _md_x(dataPublicacao="2026-10-09"),
                       {REG_X: [("x", "REsp", "123", "QUARTA TURMA", "20260929", EMS, PUB)]})
    assert not forjado.vinculadas and forjado.descartes == {"data_publicacao_divergente": 1}


def test_texto_sem_formula_nem_marcador_vincula_se_a_ementa_esta_presente():
    zb = _zip({f"{M[0]['SeqDocumento']}.txt": b"sem abertura padrao " + EMS.encode("utf-8"),
               f"{M[1]['SeqDocumento']}.txt": ABERTURA})
    res = combinar(MD, zb, _esp_ems())
    assert [k for _, k in res.vinculadas] == ["e1", "e2"]


def test_r3_i2_comentario_html_ao_final_nao_elimina_os_vinculos_legitimos():
    zb = _zip({f"{s}.txt": (t + "<!-- comentario -->").encode("utf-8") for s, t in _TXT.items()})
    res = combinar(MD, zb, ESP)
    assert [k for _, k in res.vinculadas] == ["e1", "e2"] and res.descartes == {"monocratica_fora_desta_versao": 1}
    assert "ementa_ausente_no_texto" not in res.descartes


def test_hash_e_texto_bruto_nao_sao_alterados_pela_normalizacao():
    bruto = (_FORM + EMS + "<br>RELATÓRIO<br>R.").replace("2026 a", "2026&nbsp;a").encode("utf-8")
    (integra, _), = _vincula(bruto.decode("utf-8")).vinculadas
    assert integra.sha256_texto == hashlib.sha256(bruto).hexdigest() and "&nbsp;" in integra.texto


def test_vinculo_so_consome_ler_textos_e_metadados_nao_o_texto_estruturado():
    import freoa_verifica.connectors.stj_integras as mod
    for nome in ("visao_textual", "julgamento_no_texto", "ementa_propria", "abertura_do_texto", "_FORMULA",
                 "_orgao", "_cadeia_compativel"):
        assert not hasattr(mod, nome), nome


def _forjar_tamanho(raw: bytes, falso: bytes) -> bytes:
    """Troca, nos cabeçalhos local e central, tamanho descompactado e CRC pelos de `falso`."""
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


# ---- cabeçalho local e data descriptor contra o diretório central (entrada recusada, recurso segue) --------------
TXT = b"texto de teste"
_OK = {"1": (TXT.decode(), hashlib.sha256(TXT).hexdigest())}


def test_zip_manual_integro_e_aceito_em_todas_as_variantes():
    for metodo in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        assert ler_textos_detalhado(_zip_manual({"1.txt": TXT}, metodo=metodo)) == (_OK, {})
        for ass in (True, False):  # data descriptor com e sem assinatura; local zerado
            z = _zip_manual({"1.txt": TXT}, metodo=metodo, descritor=(ass, None, None, None, 4))
            assert zipfile.ZipFile(io.BytesIO(z)).read("1.txt") == TXT
            assert ler_textos_detalhado(z) == (_OK, {})
    dois = _zip_manual({"1.txt": TXT, "2.txt": TXT}, descritor=(True, None, None, None, 4))
    assert sorted(ler_textos_detalhado(dois)[0]) == ["1", "2"]


@pytest.mark.parametrize("kw, motivo", [
    ({"local": {"metodo": zipfile.ZIP_DEFLATED}}, "zip_local_metodo_divergente"),
    ({"local": {"flags": 0x800}}, "zip_local_flags_divergente"),
    ({"local": {"crc": 1}}, "zip_local_crc_divergente"),
    ({"local": {"comp": 3}}, "zip_local_tamanho_divergente"),
    ({"local": {"tam": 3}}, "zip_local_tamanho_divergente"),
    ({"descritor": (True, 123, None, None, 4)}, "zip_descriptor_divergente"),
    ({"descritor": (True, None, 3, None, 4)}, "zip_descriptor_divergente"),
    ({"descritor": (False, None, None, 3, 4)}, "zip_descriptor_divergente"),
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
    ok = _zip_manual({f"{M[1]['SeqDocumento']}.txt": ABERTURA})  # a entrada íntegra do mesmo recurso continua valendo
    assert [k for _, k in combinar(MD, ok, _esp_ems()).vinculadas] == ["e2"]


def test_divergencia_de_nome_continua_recusando_o_recurso_inteiro():
    z = bytearray(_zip_manual({"1.txt": TXT}))
    z[30] = ord("2")  # nome do cabeçalho local diverge do central
    with pytest.raises(IntegrasInvalidas, match="zip_nome_divergente"):
        ler_textos(bytes(z))


# ---- textos órfãos são contados e nunca vinculam -------------------------------------------------------------
def test_texto_sem_metadado_e_contado_e_nao_vincula():
    zb = _zip({**{f"{m['SeqDocumento']}.txt": ABERTURA for m in M}, "999.txt": ABERTURA, "1000.txt": ABERTURA})
    res = combinar(MD, zb, _esp_ems())
    assert res.orfaos == {"texto_sem_metadado": 2}
    assert sorted(i.seq for i, _ in res.vinculadas) == sorted(str(m["SeqDocumento"]) for m in M[:2])
    assert combinar(MD, ZB, ESP).orfaos == {}  # sem órfãos o relatório não os inventa


def test_texto_sem_espelho_e_contado_e_nao_vincula():
    res = combinar(MD, ZB, {REGS[0]: ESP[REGS[0]]})
    assert res.orfaos == {"texto_sem_espelho": 1} and [k for _, k in res.vinculadas] == ["e1"]
    res = combinar(MD, ZB, {})
    assert res.orfaos == {"texto_sem_espelho": 2} and not res.vinculadas
    assert res.descartes["fora_do_recorte_ou_sem_espelho"] == 2


@pytest.mark.parametrize("campo, valor, descarte", [
    ("tipoDocumento", "DECISÃO", "monocratica_fora_desta_versao"),
    ("tipoDocumento", "FORMATO NOVO", "tipo_documento_desconhecido"),
    ("numeroRegistro", "123", "registro_invalido"),
    ("processo", "sem numero", "processo_invalido"),
])
def test_recusa_do_zip_nao_some_por_saida_antecipada_do_metadado(campo, valor, descarte):
    md = json.dumps([dict(M[0], **{campo: valor})], ensure_ascii=False).encode("utf-8")
    z = _zip_manual({f"{M[0]['SeqDocumento']}.txt": ABERTURA}, local={"crc": 1})
    res = combinar(md, z, ESP)
    assert res.descartes == {descarte: 1} and res.orfaos == {"zip_local_crc_divergente": 1}
    assert not res.vinculadas and not res.ambiguas


def test_seq_monocratico_com_crc_divergente_e_intacto_sem_crc():
    md = json.dumps([M[2]], ensure_ascii=False).encode("utf-8")
    ruim = _zip_manual({f"{M[2]['SeqDocumento']}.txt": b"decisao"}, local={"crc": 1})
    res = combinar(md, ruim, {})
    assert res.descartes == {"monocratica_fora_desta_versao": 1}
    assert res.orfaos == {"zip_local_crc_divergente": 1}
    bom = _zip_manual({f"{M[2]['SeqDocumento']}.txt": b"decisao"})
    assert combinar(md, bom, {}).orfaos == {}  # sem recusa no ZIP não há o que contar


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


# ---- ZIP estrito: limites do diretório antes de ZipFile -----------------------------------------------------------
def _sem_zipfile(monkeypatch):
    def proibido(*a, **k):
        raise AssertionError("ZipFile/ZipInfo instanciado antes da validação estrutural")
    monkeypatch.setattr(zipfile, "ZipFile", proibido)
    monkeypatch.setattr(zipfile, "ZipInfo", proibido)


def _recusa(z: bytes, monkeypatch, motivo: str):
    _sem_zipfile(monkeypatch)
    with pytest.raises(IntegrasInvalidas, match=motivo):
        ler_textos_detalhado(z)


def _muitos(n: int) -> bytes:
    return _zip_manual({f"{i}.txt": b"a" for i in range(1, n + 1)})


def _eocd_editado(z: bytes, *, total=None, tam=None, desloc=None, disco=None, disco_cd=None, no_disco=None) -> bytes:
    b = bytearray(z)
    pos = bytes(b).rindex(b"PK\x05\x06")
    if disco is not None:
        b[pos + 4:pos + 6] = struct.pack("<H", disco)
    if disco_cd is not None:
        b[pos + 6:pos + 8] = struct.pack("<H", disco_cd)
    if no_disco is not None:
        b[pos + 8:pos + 10] = struct.pack("<H", no_disco)
    if total is not None:
        b[pos + 8:pos + 12] = struct.pack("<HH", total, total)
    if tam is not None:
        b[pos + 12:pos + 16] = struct.pack("<I", tam)
    if desloc is not None:
        b[pos + 16:pos + 20] = struct.pack("<I", desloc)
    return bytes(b)


def test_entradas_acima_do_limite_recusadas_sem_instanciar_zipinfo(monkeypatch):
    _recusa(_muitos(5001), monkeypatch, "zip_entradas_excedidas")


def test_diretorio_central_grande_demais_recusado_antes_de_zipfile(monkeypatch):
    _recusa(_eocd_editado(_zip_manual({"1.txt": b"a"}), tam=3 * 1024 * 1024), monkeypatch, "zip_diretorio_excedido")


def test_no_limite_exato_e_aceito():
    assert len(ler_textos_detalhado(_muitos(5000))[0]) == 5000


@pytest.mark.parametrize("nome, construir, motivo", [
    ("5001_reais_declara_1", lambda: _eocd_editado(_muitos(5001), total=1), "zip_entradas_excedidas"),
    ("20000_reais_declara_1", lambda: _eocd_editado(_muitos(20000), total=1), "zip_entradas_excedidas"),
    ("40000_reais_declara_1", lambda: _eocd_editado(_muitos(40000), total=1), "zip_diretorio_excedido"),
    ("1_real_declara_5001", lambda: _eocd_editado(_muitos(1), total=5001), "zip_entradas_excedidas"),
    ("1_real_tamanho_3MiB", lambda: _eocd_editado(_muitos(1), tam=3 * 1024 * 1024), "zip_diretorio_excedido"),
    ("3_reais_declara_2", lambda: _eocd_editado(_muitos(3), total=2), "zip_diretorio_divergente"),
    ("1_real_declara_2", lambda: _eocd_editado(_muitos(1), total=2), "zip_diretorio_divergente"),
    ("tamanho_maior_que_o_percorrido", lambda: _eocd_editado(_muitos(2), tam=len(_muitos(2)) + 10),
     "zip_estrutura_nao_suportada"),
])
def test_mutacao_do_diretorio_recusada_sem_instanciar_zipfile_nem_zipinfo(nome, construir, motivo, monkeypatch):
    _recusa(construir(), monkeypatch, motivo)


# ---- ZIP estrito: disposição única aceita; o resto recusa o recurso inteiro ---------------------------------------
_NS = "zip_estrutura_nao_suportada"


def _com_eocd64(z: bytes, *, total=None, tam=None, disco_e64=0, disco_cd_e64=0, sentinelas=True) -> bytes:
    pos = z.rindex(b"PK\x05\x06")
    ent = struct.unpack("<H", z[pos + 10:pos + 12])[0]
    tam_r = struct.unpack("<I", z[pos + 12:pos + 16])[0]
    off_r = struct.unpack("<I", z[pos + 16:pos + 20])[0]
    n = ent if total is None else total
    e64 = struct.pack("<4sQHHIIQQQQ", b"PK\x06\x06", 44, 45, 45, disco_e64, disco_cd_e64, n, n,
                      tam_r if tam is None else tam, off_r)
    loc = struct.pack("<4sIQI", b"PK\x06\x07", 0, pos, 1)
    eocd = (struct.pack("<4sHHHHIIH", b"PK\x05\x06", 0, 0, 0xFFFF, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0) if sentinelas
            else z[pos:])
    return z[:pos] + e64 + loc + eocd


def _com_setor_extensivel(n_reais: int, n_falsos: int = 1, sentinelas=True) -> bytes:
    """Membros + diretório real + EOCD64 real + setor extensível [diretório falso + EOCD64 falso] + localizador
    apontando ao EOCD64 real + EOCD (r3 I1: o percurso manual e o `zipfile` liam diretórios diferentes)."""
    z = _muitos(n_reais)
    pos = z.rindex(b"PK\x05\x06")
    off_cd = struct.unpack("<I", z[pos + 16:pos + 20])[0]
    membros, cd_real = z[:off_cd], z[off_cd:pos]
    cd_falso = _muitos(n_falsos)
    cd_falso = cd_falso[struct.unpack("<I", cd_falso[-6:-2])[0]:-22]
    e64 = struct.pack("<4sQHHIIQQQQ", b"PK\x06\x06", 44, 45, 45, 0, 0, n_reais, n_reais, len(cd_real), off_cd)
    e64_falso = struct.pack("<4sQHHIIQQQQ", b"PK\x06\x06", 44, 45, 45, 0, 0, n_falsos, n_falsos, len(cd_falso), 0)
    pos_e64 = off_cd + len(cd_real)
    loc = struct.pack("<4sIQI", b"PK\x06\x07", 0, pos_e64, 1)
    eocd = (struct.pack("<4sHHHHIIH", b"PK\x05\x06", 0, 0, 0xFFFF, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0) if sentinelas
            else struct.pack("<4sHHHHIIH", b"PK\x05\x06", 0, 0, n_reais, n_reais, len(cd_real), off_cd, 0))
    return membros + cd_real + e64 + cd_falso + e64_falso + loc + eocd


@pytest.mark.parametrize("sentinelas", [True, False])
@pytest.mark.parametrize("n_reais", [3, 5001, 40000])
def test_r3_i1_zip64_com_setor_extensivel_e_recusado_sem_instanciar_zipinfo(n_reais, sentinelas, monkeypatch):
    _recusa(_com_setor_extensivel(n_reais, sentinelas=sentinelas), monkeypatch, _NS)


@pytest.mark.parametrize("construir", [
    lambda: _com_eocd64(_muitos(3)),
    lambda: _com_eocd64(_muitos(3), sentinelas=False),
    lambda: _com_eocd64(_muitos(1), total=5001),
    lambda: _com_eocd64(_muitos(5001), total=1),
    lambda: _com_eocd64(_muitos(1), tam=3 * 1024 * 1024),
    lambda: _com_eocd64(_muitos(2), total=3),
    lambda: _com_eocd64(_muitos(2), disco_e64=1),
    lambda: _com_eocd64(_muitos(2), disco_cd_e64=1),
])
def test_zip64_com_eocd64_e_localizador_e_sempre_recusado(construir, monkeypatch):
    _recusa(construir(), monkeypatch, _NS)


def _central_editado(z: bytes, deslocamento_no_registro: int, valor: bytes) -> bytes:
    b = bytearray(z)
    c = bytes(b).index(b"PK\x01\x02")
    b[c + deslocamento_no_registro:c + deslocamento_no_registro + len(valor)] = valor
    return bytes(b)


@pytest.mark.parametrize("nome, construir", [
    ("eocd_disco_1", lambda: _eocd_editado(_muitos(2), disco=1)),
    ("eocd_disco_do_diretorio_1", lambda: _eocd_editado(_muitos(2), disco_cd=1)),
    ("eocd_entradas_no_disco_diferente", lambda: _eocd_editado(_muitos(2), no_disco=1)),
    ("central_disco_inicial_1", lambda: _central_editado(_muitos(2), 34, struct.pack("<H", 1))),
    ("central_disco_inicial_sentinela", lambda: _central_editado(_muitos(2), 34, struct.pack("<H", 0xFFFF))),
    ("central_tamanho_sentinela", lambda: _central_editado(_muitos(2), 24, struct.pack("<I", 0xFFFFFFFF))),
    ("central_comprimido_sentinela", lambda: _central_editado(_muitos(2), 20, struct.pack("<I", 0xFFFFFFFF))),
    ("central_deslocamento_sentinela", lambda: _central_editado(_muitos(2), 42, struct.pack("<I", 0xFFFFFFFF))),
    ("local_comprimido_sentinela", lambda: _zip_manual({"1.txt": TXT}, local={"comp": 0xFFFFFFFF})),
    ("local_tamanho_sentinela", lambda: _zip_manual({"1.txt": TXT}, local={"tam": 0xFFFFFFFF})),
    ("eocd_total_sentinela", lambda: _eocd_editado(_muitos(2), total=0xFFFF)),
    ("eocd_tamanho_sentinela", lambda: _eocd_editado(_muitos(2), tam=0xFFFFFFFF)),
    ("eocd_deslocamento_sentinela", lambda: _eocd_editado(_muitos(2), desloc=0xFFFFFFFF)),
])
def test_m1_disco_e_sentinelas_recusam_o_recurso(nome, construir, monkeypatch):
    _recusa(construir(), monkeypatch, _NS)


@pytest.mark.parametrize("kw", [
    {"z64_local": (len(TXT), len(TXT)), "z64_central": True},
    {"z64_local": (3, len(TXT)), "z64_central": True},
    {"z64_local": (len(TXT), 3), "z64_central": True},
    {"z64_local": (0, 0), "z64_central": True, "descritor": (True, None, None, None, 8)},
    {"z64_local": (0, 0), "z64_central": True, "descritor": (True, None, 3, None, 8)},
    {"z64_central_valores": (len(TXT) + 1, len(TXT))},
    {"z64_central_valores": (len(TXT), len(TXT) + 1)},
    {"z64_central_valores": (7,)},
    {"z64_central_valores": (len(TXT), len(TXT), 99)},
    {"z64_central_valores": ()},
    {"z64_central_valores": (3, 0), "z64_central_sentinelas": ("tam",)},
    {"z64_central_valores": (len(TXT),), "z64_central_sentinelas": ("tam",)},
    {"z64_central_valores": (len(TXT),), "z64_central_sentinelas": ("comp",)},
    {"z64_central_valores": (len(TXT), len(TXT)), "z64_central_sentinelas": ("tam", "comp")},
    {"z64_central_valores": (len(TXT),), "z64_central_sentinelas": ("tam", "comp")},
    {"z64_central": True},
])
def test_qualquer_extra_ou_sentinela_zip64_recusa_o_recurso_inteiro(kw, monkeypatch):
    z = _zip_manual({"1.txt": TXT}, **kw)
    _recusa(z, monkeypatch, f"{_NS}:zip64")


def test_extra_zip64_malformado_ou_extra_qualquer_malformado_recusa(monkeypatch):
    z = bytearray(_zip_manual({"1.txt": TXT}, z64_central_valores=(len(TXT), len(TXT)),
                              z64_central_sentinelas=("tam", "comp")))
    c = z.index(b"PK\x01\x02")
    n_nome = struct.unpack("<H", z[c + 28:c + 30])[0]
    z[c + 46 + n_nome + 2] = 15  # tamanho declarado do extra deixa de caber
    _recusa(bytes(z), monkeypatch, _NS)
    # extra de outro id, truncado, também recusa: o recurso aceita só a disposição estrita
    z = bytearray(_zip_manual({"1.txt": TXT}))
    c = z.index(b"PK\x01\x02")
    n_nome = struct.unpack("<H", z[c + 28:c + 30])[0]
    z[c + 30:c + 32] = struct.pack("<H", 3)  # extra de 3 bytes: nem o cabeçalho de campo cabe
    z[c + 46 + n_nome:c + 46 + n_nome] = b"\x01\x02\x03"
    z[len(z) - 22 + 12:len(z) - 22 + 16] = struct.pack("<I", struct.unpack("<I", z[-10:-6])[0] + 3)
    _recusa(bytes(z), monkeypatch, _NS)


def _inserir_apos_primeiro_membro(z: bytes, extra: bytes, *, ate: str) -> bytes:
    """Insere bytes e corrige os deslocamentos: depois do 1º membro (`ate`='membro') ou antes do diretório."""
    b = bytearray(z)
    pos = bytes(b).rindex(b"PK\x05\x06")
    off_cd = struct.unpack("<I", b[pos + 16:pos + 20])[0]
    centrais = []
    c = off_cd
    while b[c:c + 4] == b"PK\x01\x02":
        n, e, k = struct.unpack("<HHH", b[c + 28:c + 34])
        centrais.append(c)
        c += 46 + n + e + k
    segundo = struct.unpack("<I", b[centrais[1] + 42:centrais[1] + 46])[0] if len(centrais) > 1 else off_cd
    ponto = segundo if ate == "membro" else off_cd
    b[pos + 16:pos + 20] = struct.pack("<I", off_cd + len(extra))
    for c in centrais:
        d = struct.unpack("<I", b[c + 42:c + 46])[0]
        if d >= ponto:
            b[c + 42:c + 46] = struct.pack("<I", d + len(extra))
    b[ponto:ponto] = extra
    return bytes(b)


def test_byte_extra_entre_membros_ou_antes_do_diretorio_e_recusado(monkeypatch):
    base = _muitos(3)
    assert sorted(ler_textos_detalhado(base)[0]) == ["1", "2", "3"]
    zs = [_inserir_apos_primeiro_membro(base, b"X", ate=ate) for ate in ("membro", "diretorio")]
    for z in zs:
        assert zipfile.ZipFile(io.BytesIO(z)).namelist() == ["1.txt", "2.txt", "3.txt"]  # o zipfile aceitaria
    for z in zs:
        _recusa(z, monkeypatch, f"{_NS}:membros_nao_contiguos")


def test_prefixo_antes_do_primeiro_membro_e_recusado(monkeypatch):
    base = _muitos(2)
    pos = base.rindex(b"PK\x05\x06")
    b = bytearray(b"PREFIXO!" + base)  # deslocamentos "corrigidos" como num executável autoextraível
    n_pos = pos + 8
    off_cd = struct.unpack("<I", b[n_pos + 16:n_pos + 20])[0] + 8
    b[n_pos + 16:n_pos + 20] = struct.pack("<I", off_cd)
    c = off_cd
    while b[c:c + 4] == b"PK\x01\x02":
        n, e, k = struct.unpack("<HHH", b[c + 28:c + 34])
        b[c + 42:c + 46] = struct.pack("<I", struct.unpack("<I", b[c + 42:c + 46])[0] + 8)
        c += 46 + n + e + k
    assert zipfile.ZipFile(io.BytesIO(bytes(b))).namelist() == ["1.txt", "2.txt"]
    _recusa(bytes(b), monkeypatch, f"{_NS}:membros_nao_contiguos")


def test_comentario_no_eocd_e_recusado(monkeypatch):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("1.txt", b"abc")
        zf.comment = b"comentario do arquivo"
    assert list(zipfile.ZipFile(io.BytesIO(buf.getvalue())).namelist()) == ["1.txt"]
    _recusa(buf.getvalue(), monkeypatch, f"{_NS}:eocd_nao_final")
    # comprimento de comentário declarado e bytes após o EOCD
    z = bytearray(_zip_manual({"1.txt": TXT}))
    z[-2:] = struct.pack("<H", 4)
    _recusa(bytes(z) + b"abcd", monkeypatch, f"{_NS}:eocd_nao_final")


def test_rabo_depois_do_eocd_e_recusado(monkeypatch):
    _recusa(_zip_manual({"1.txt": TXT}) + b"\x00", monkeypatch, f"{_NS}:eocd_nao_final")


def test_zip_concatenado_e_recusado(monkeypatch):
    a, b = _zip_manual({"1.txt": TXT}), _zip_manual({"2.txt": TXT})
    assert zipfile.ZipFile(io.BytesIO(a + b)).namelist() == ["2.txt"]  # o zipfile leria só o último
    _recusa(a + b, monkeypatch, _NS)
    _recusa(b"lixo" + a, monkeypatch, _NS)


def test_so_a_disposicao_estrita_e_aceita_e_o_zipfile_le_o_mesmo_diretorio():
    for z in (_zip({"1.txt": b"a", "2.txt": b"b"}), _zip({"1.txt": b"a"}, zipfile.ZIP_STORED), _muitos(3),
              _zip_manual({"1.txt": TXT, "2.txt": TXT}, descritor=(False, None, None, None, 4))):
        assert sorted(ler_textos_detalhado(z)[0]) == sorted(i[:-4] for i in zipfile.ZipFile(io.BytesIO(z)).namelist())
    assert ler_textos_detalhado(ZB)[1] == {}
