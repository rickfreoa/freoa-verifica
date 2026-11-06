"""IL.3-a, A1: executor da Porta L (`scripts/porta_l.py`) frente à matriz IL.1, seções 1 a 4.

Oráculos independentes da implementação: cada linha das tabelas 1, 1.1, 2 e 3 da matriz tem caso sintético positivo e
negativo, com o resultado esperado escrito à mão. Mutantes do executor (parcial no numerador, duas unidades do mesmo
evento, `fundamento_temporal` sem `capture_id` recuperável, normalização de caixa) têm de falhar na bateria.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import socket
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "porta_l.py"


def _carregar():
    spec = importlib.util.spec_from_file_location("porta_l_executor", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["porta_l_executor"] = mod
    spec.loader.exec_module(mod)
    return mod


ex = _carregar()

TEXTO = "Art. 14. O preço de emissão das ações será fixado pelos fundadores."
D = "2005-06-01"


# --- ajudantes de caso e de serviço ----------------------------------------------------------------------------------


def caso(cid, cap, tipo="texto", familia="original", numero="6404", ano=1976, **gab):
    g = {"tipo": tipo, "texto": TEXTO if tipo in ("texto", "verificado_para_D") else None, "motivos_aceitos": [],
         "cadeia": [], "alvos": [], "alvos_equivalentes": {}}
    g.update(gab)
    return {"id": cid, "conjunto": "desenvolvimento", "capacidade": cap, "familia_alteracao": familia,
            "norma": {"especie": "lei", "numero": numero, "ano": ano}, "citacao": f"art. 14 da Lei {numero}/{ano}",
            "caminho": "art. 14", "data": D if cap == "c" else None, "trecho": None, "gabarito": g,
            "norma_grande": False}


class Svc:
    def __init__(self, evidencias=None):
        self.evidencias = evidencias or {}

    def obter_evidencia(self, capture_id, offset=0, max_chars=4000):
        return self.evidencias.get(capture_id, {"status": "inexistente", "capture_id": capture_id})


def evid_ok(cid="c1", sha="a" * 64):
    return {cid: {"status": "encontrada", "capture_id": cid, "metadados": {"sha256": sha}}}


def fund(cid="c1", sha="a" * 64, data="2001-01-01", tipo="versao_oficial_na_data"):
    return {"tipo": tipo, "capture_id": cid, "url": "https://x", "sha256": sha, "data": data}


def av(c, resp, svc=None):
    return ex.avaliar_resposta(c, resp, svc or Svc(evid_ok()))


def enc(texto=TEXTO, **kw):
    return {"status": "encontrada", "texto": texto, "truncado": False, "remissoes": [],
            "evidencia": {"natureza_texto": "publicacao_original"}, "vigencia": {"status": "vigente_na_fonte"}, **kw}


def verif(text="verified", temporal="verified", fundamento=None, t=None, m=None, **kw):
    return {"identity": {"status": "verified"}, "text": {"status": text, **(t or {})},
            "temporal": {"status": temporal, **(m or {})}, "fundamento_temporal": fundamento, **kw}


def rem(obra, caminho, resolvida=True):
    return {"texto": "x", "alvo": {"obra": obra, "caminho": caminho}, "resolvida": resolvida}


def aval(resultado, indevidas=()):
    return {"resultado": resultado, "motivo": "", "indevidas": list(indevidas), "extra": {}, "latencias_s": []}


# --- comparação textual: a do validador, importada --------------------------------------------------------------------


def test_normalizacao_e_a_do_validador_por_identidade():
    assert ex.norm is ex.VALIDADOR.norm
    fonte = SCRIPT.read_text(encoding="utf-8")
    assert "unicodedata" not in fonte and "translate(" not in fonte  # nenhuma cópia da normalização


def test_comparacao_textual_secao_7():
    assert ex.igual_texto("Art.  1º X\n", "Art. 1o X")  # espaços, NBSP, quebra e ordinal
    assert ex.igual_texto("“a”", '"a"')
    assert not ex.igual_texto("Art. 1º X", "art. 1º x")  # nem caixa
    assert not ex.igual_texto("Art. 1º X.", "Art. 1º X")  # nem pontuação
    assert not ex.igual_texto(None, "x")


# --- tabela 1: (a), (b), (d) -----------------------------------------------------------------------------------------


def test_a_acerto_e_negativos():
    c = caso("L-a-001", "a")
    assert av(c, enc())["resultado"] == "acerto"
    assert av(c, enc(evidencia={"natureza_texto": "consolidacao_oficial"}))["resultado"] == "erro"
    r = av(c, enc(texto=TEXTO + " Outro."))
    assert r["resultado"] == "erro" and [i["item"] for i in r["indevidas"]] == ["ii"]
    assert av(c, {"status": "unknown", "texto": None})["resultado"] == "erro"
    assert av(c, {"status": "indisponivel", "motivo": "COBERTURA"})["resultado"] == "indisponivel"


def test_b_texto_exige_nao_truncado_e_revogado_exige_vigencia():
    c = caso("L-b-001", "b")
    assert av(c, enc())["resultado"] == "acerto"
    assert av(c, enc(truncado=True))["resultado"] == "erro"
    assert av(c, enc(truncado=None))["resultado"] == "erro"
    rev = caso("L-b-002", "b", tipo="revogado_vigente")
    resp = {"status": "encontrada", "texto": "Art. 5º (Revogado)", "vigencia": {"status": "revogado"}}
    assert av(rev, resp)["resultado"] == "acerto"
    assert av(rev, enc())["resultado"] == "erro"
    assert av(rev, {"status": "inexistente"})["resultado"] == "erro"


def test_d_anexo_texto_igual():
    c = caso("L-d-001", "d")
    assert av(c, enc())["resultado"] == "acerto"
    r = av(c, enc(texto="outro anexo"))
    assert r["resultado"] == "erro" and r["indevidas"][0]["item"] == "ii"


# --- tabela 1: (e) e confirmação indevida (iii) ------------------------------------------------------------------------

ALVOS = [{"obra": "Lei 6.404/1976", "caminho": "art. 166"}, {"obra": "Lei 6.404/1976", "caminho": "art. 170, § 2º"}]


def test_e_conjunto_exato_dos_alvos_resolvidos():
    c = caso("L-e-001", "e", alvos=ALVOS)
    ok = [rem("Lei 6.404/1976", "art. 166"), rem("Lei 6.404/1976", "art. 170, § 2º")]
    assert av(c, enc(remissoes=ok))["resultado"] == "acerto"
    r = av(c, enc(remissoes=ok[:1]))  # faltante: parcial, nunca acerto
    assert r["resultado"] == "parcial" and r["indevidas"] == []
    r = av(c, enc(remissoes=ok + [rem("Lei 6.404/1976", "art. 4º")]))  # excedente resolvido: (iii)
    assert r["resultado"] == "erro" and [i["item"] for i in r["indevidas"]] == ["iii"]
    assert av(c, enc(remissoes=ok + [rem("Lei 6.404/1976", "art. 4º", resolvida=False)]))["resultado"] == "acerto"
    outra_grafia = [rem("Lei 6.404/1976", "art. 166"), rem("Lei 6.404/1976", "art. 170, § 2o")]
    assert av(c, enc(remissoes=outra_grafia))["resultado"] == "acerto"
    r = av(c, enc(remissoes=[rem("Lei 6.404/1976", "art. 166"), rem("Lei 10.406/2002", "art. 170, § 2º")]))
    assert [i["item"] for i in r["indevidas"]] == ["iii"]  # obra diferente, mesmo caminho: alvo distinto


def test_e_alvos_equivalentes_aceitos_na_forma_listada():
    c = caso("L-e-002", "e", alvos=[{"obra": "Lei 6.404/1976", "caminho": "art. 14, caput"}],
             alvos_equivalentes={"Lei 6.404/1976, art. 14, caput": ["Lei 6.404/1976, art. 14"]})
    assert av(c, enc(remissoes=[rem("Lei 6.404/1976", "art. 14")]))["resultado"] == "acerto"
    r = av(c, enc(remissoes=[rem("Lei 6.404/1976", "art. 15")]))
    assert r["resultado"] == "erro" and r["indevidas"][0]["item"] == "iii"


def test_e_sem_alvos_exige_nenhum_resolvido():
    c = caso("L-e-003", "e", alvos=[])
    assert av(c, enc())["resultado"] == "acerto"
    assert av(c, enc(remissoes=[rem("Lei 6.404/1976", "art. 1º")]))["indevidas"][0]["item"] == "iii"


# --- tabela 1.1: (c) -------------------------------------------------------------------------------------------------


def test_c_verificado_para_D_exige_fundamento_nos_termos_de_1_1():
    c = caso("L-c-001", "c", tipo="verificado_para_D")
    assert av(c, verif(fundamento=fund()))["resultado"] == "acerto"
    ruins = [(None, "ausente"), (fund(tipo="outro"), "tipo"), (fund(cid="inexistente"), "capture_id"),
             (fund(sha="b" * 64), "sha256"), (fund(data="2005-06-02"), "data posterior a D"),
             ({**fund(), "capture_id": None}, "sem capture_id")]
    for ruim, rotulo in ruins:
        r = av(c, verif(fundamento=ruim))
        assert r["resultado"] != "acerto", rotulo
        assert [i["item"] for i in r["indevidas"]] == ["i"], rotulo  # verified sem fundamento válido é indevido
    assert av(c, verif(fundamento=fund(data=D)))["resultado"] == "acerto"  # data == D vale (menor ou igual)
    assert av(c, verif(temporal="unknown", fundamento=None))["resultado"] != "acerto"
    abst = verif("unknown", "unknown", t={"reason_code": "sem_fundamento_do_periodo"})
    assert av(c, abst)["resultado"] == "erro"


def test_c_nao_verificado_para_D_motivo_aceito_e_cadeia():
    c = caso("L-c-002", "c", tipo="nao_verificado_para_D", motivos_aceitos=["sem_fundamento_do_periodo"])
    sfp = {"reason_code": "sem_fundamento_do_periodo"}
    r = av(c, verif("unknown", "unknown", t=sfp, m=sfp))
    assert r["resultado"] == "acerto" and r["extra"]["nao_verificado_com_motivo"] is True
    for ruim in (verif("unknown", "unknown", t={"reason_code": "OUTRO"}, m=sfp), verif("unknown", "unknown"),
                 verif("unknown", "ambiguous", m=sfp)):
        r = av(c, ruim)
        assert r["resultado"] == "erro" and r["extra"]["nao_verificado_com_motivo"] is False
    r = av(c, verif("verified", "verified", fundamento=fund()))  # verified onde o gabarito é não verificado
    assert [i["item"] for i in r["indevidas"]] == ["i"] and r["resultado"] == "erro"

    cad = caso("L-c-003", "c", tipo="nao_verificado_para_D", motivos_aceitos=["sem_versao_oficial_na_data"],
               cadeia=[{"ato": "lei-10303-2001", "data": "2001-10-31"}, {"ato": "lei-11941-2009", "data": "2009-05-27"}])
    cad["data"] = "2010-01-01"
    svo = {"reason_code": "sem_versao_oficial_na_data"}

    def chain(*atos):
        return [{"ato": {"especie": "lei", "numero": n, "ano": a, "url": "u"}, "publicacao": {"data": d}}
                for n, a, d in atos]

    boa = verif("unknown", "unknown", t=svo, m=svo, ultima_versao_oficial_anterior={"data": "1976-12-17"},
                cadeia_alteracoes=chain(("10.303", 2001, "2001-11-01"), (11941, 2009, "2009-05-28")))
    assert av(cad, boa)["resultado"] == "acerto"
    ruins = [
        {**boa, "cadeia_alteracoes": list(reversed(boa["cadeia_alteracoes"]))},  # fora de ordem
        {**boa, "cadeia_alteracoes": boa["cadeia_alteracoes"][:1]},  # incompleta
        {**boa, "cadeia_alteracoes": chain(("10.303", 2001, "2001-11-01"), (11942, 2009, "2009-05-28"))},  # ato errado
        {**boa, "cadeia_alteracoes": chain(("10.303", 2001, "2001-11-01"), (11941, 2009, "2009-09-01"))},  # fora da folga
        {**boa, "ultima_versao_oficial_anterior": None},
        {**boa, "ultima_versao_oficial_anterior": {"data": "2010-01-01"}},  # não anterior a D
    ]
    for ruim in ruins:
        r = av(cad, ruim)
        assert r["resultado"] == "parcial" and r["extra"]["nao_verificado_com_motivo"] is True


def test_c_nao_existia_em_D():
    c = caso("L-c-004", "c", tipo="nao_existia_em_D")
    assert av(c, verif("unknown", "not_found", m={"reason_code": "NAO_EXISTIA"}))["resultado"] == "acerto"
    assert av(c, verif("unknown", "not_found", m={"reason_code": "OUTRO"}))["resultado"] == "erro"
    assert av(c, verif("unknown", "unknown"))["resultado"] == "erro"
    r = av(c, verif("verified", "not_found", m={"reason_code": "NAO_EXISTIA"}))
    assert r["resultado"] == "erro" and r["indevidas"][0]["item"] == "i"


# --- tabela 2: confirmação indevida, unidade de independência, denominador -------------------------------------------


def _conjunto(cap, n, tipo="texto"):
    """n casos de eventos distintos, em 5 normas."""
    return [caso(f"L-{cap}-{i + 1:03d}", cap, tipo=tipo, familia="original" if i == 0 else f"lei-{1000 + i}-2000",
                 numero=str(6404 + (i % 5)), ano=1976 + (i % 5)) for i in range(n)]


def _rodar(casos, respostas, mutantes=(), res_mut=None, lat=None, modo="local", conjunto=None):
    avs = {}
    for c in casos:
        avs[c["id"]] = {**ex.avaliar_resposta(c, respostas[c["id"]], Svc(evid_ok())), "latencias_s": [0.01]}
    rm = res_mut if res_mut is not None else {m["id"]: {"rejeitado": True, "motivo": ""} for m in mutantes}
    latencias = lat if lat is not None else {c["capacidade"]: [0.01] * 3 for c in casos}
    return ex.consolidar(casos, list(mutantes), avs, rm, latencias, modo, conjunto)


def _mutantes_de(casos):
    return [{"id": f"{c['id']}#renumerado", "caso": c["id"], "tipo": "renumerado"} for c in casos]


def test_aprovacao_so_com_todos_os_pisos_e_confirmacao_indevida_reprova_todas_as_capacidades():
    casos = [c for cap in ex.CAPS for c in _conjunto(cap, 8, "texto" if cap != "c" else "verificado_para_D")]
    resp = {c["id"]: (verif(fundamento=fund()) if c["capacidade"] == "c" else enc()) for c in casos}
    muts = _mutantes_de(casos)
    rel = _rodar(casos, resp, muts)
    assert ex.tabela(rel) == {cap: "aprovado" for cap in ex.CAPS}, \
        {k: v["motivos_reprovacao"] for k, v in rel["capacidades"].items()}
    assert rel["confirmacoes_indevidas_total"] == 0
    # uma única confirmação indevida em (e) reprova TODAS as capacidades
    e1 = next(c for c in casos if c["capacidade"] == "e")
    resp_i = {**resp, e1["id"]: enc(remissoes=[rem("Lei 6.404/1976", "art. 99")])}
    rel = _rodar(casos, resp_i, muts)
    assert set(ex.tabela(rel).values()) == {"reprovado"}
    assert all(any("eliminatório" in m for m in rel["capacidades"][k]["motivos_reprovacao"]) for k in ex.CAPS)
    # mutante não rejeitado = confirmação indevida (iv), idem
    rm = {m["id"]: {"rejeitado": m["caso"] != casos[0]["id"], "motivo": "x"} for m in muts}
    rel = _rodar(casos, resp, muts, res_mut=rm)
    assert set(ex.tabela(rel).values()) == {"reprovado"}
    assert any(x["item"] == "iv" for x in rel["capacidades"]["a"]["confirmacoes_indevidas"])


def test_piso_de_acerto_por_capacidade():
    casos = _conjunto("a", 20)
    muts = _mutantes_de(casos)
    rm = {m["id"]: {"rejeitado": True, "motivo": ""} for m in muts}

    def com(k):
        avs = {c["id"]: aval("acerto" if i < k else "erro") for i, c in enumerate(casos)}
        return ex.consolidar(casos, muts, avs, rm, {"a": [0.1] * 3}, "local", None)["capacidades"]["a"]
    assert com(19)["acerto"] == 0.95  # piso de (a): ≥ 0,95
    assert not any("abaixo do piso" in m for m in com(19)["motivos_reprovacao"])
    assert any("abaixo do piso" in m for m in com(18)["motivos_reprovacao"])


def test_unidade_de_independencia_conta_so_o_menor_id():
    c1 = caso("L-a-002", "a", familia="lei-10303-2001")
    c2 = caso("L-a-001", "a", familia="lei-10303-2001", numero="10406", ano=2002)
    c3 = caso("L-a-003", "a", familia="original")
    assert ex.representantes([c1, c2, c3]) == {"lei-10303-2001": "L-a-001", "lei-6404-1976": "L-a-003"}
    c4 = caso("L-a-004", "a", familia="lei-010303-2001")  # grafia do mesmo ato (zeros à esquerda): um evento
    assert ex.unidade(c4) == ex.unidade(c1)
    c5 = caso("L-a-005", "a", familia="lei-10303-2001-b")  # sufixo vedado: sem evento, o caso é a própria unidade
    assert ex.unidade(c5) == "caso:L-a-005"
    # o representante que falha derruba a unidade: o outro caso (que acerta) não a substitui
    avs = {"L-a-001": aval("erro"), "L-a-002": aval("acerto")}
    rel = ex.consolidar([c2, c1], [], avs, {}, {"a": [0.1]}, "local", None)
    a = rel["capacidades"]["a"]
    assert a["denominador"] == 1 and a["acertos"] == 0
    assert [x["conta_no_denominador"] for x in a["casos"]] == [True, False]


def test_parcial_unavailable_e_indisponivel_ficam_no_denominador_nunca_no_numerador():
    casos = _conjunto("e", 4)
    avs = {c["id"]: aval(r) for c, r in zip(casos, ("acerto", "parcial", "indisponivel", "erro"))}
    e = ex.consolidar(casos, [], avs, {}, {"e": [0.1]}, "local", None)["capacidades"]["e"]
    assert (e["denominador"], e["acertos"]) == (4, 1)
    c = caso("L-c-009", "c", tipo="verificado_para_D")
    assert av(c, verif("unavailable", "unavailable"))["resultado"] == "indisponivel"
    assert av(caso("L-b-009", "b"), {"status": "indisponivel", "motivo": "x"})["resultado"] == "indisponivel"
    assert not ex.eh_acerto("parcial") and not ex.eh_acerto("indisponivel") and not ex.eh_acerto("unavailable")


def test_b_norma_grande_sem_truncamento():
    casos = _conjunto("b", 8)
    for c in casos[:2]:
        c["norma_grande"] = True
    resp = {c["id"]: enc() for c in casos}
    muts = _mutantes_de(casos)
    b = _rodar(casos, resp, muts)["capacidades"]["b"]
    assert b["extras"]["norma_grande_sem_truncamento"] == "2/2"
    assert not any("truncamento" in m for m in b["motivos_reprovacao"])
    resp[casos[0]["id"]] = enc(truncado=True)
    b = _rodar(casos, resp, muts)["capacidades"]["b"]
    assert any("truncamento" in m for m in b["motivos_reprovacao"])


def test_c_casos_sem_fundamento_da_data_devolvidos_como_nao_verificados_com_motivo():
    sfp = {"reason_code": "sem_fundamento_do_periodo"}
    sem = caso("L-c-020", "c", tipo="nao_verificado_para_D", familia="lei-11941-2009",
               motivos_aceitos=["sem_fundamento_do_periodo"])
    cs = _conjunto("c", 8, "verificado_para_D") + [sem]
    resp = {c["id"]: verif(fundamento=fund()) for c in cs[:8]}
    resp["L-c-020"] = verif("unknown", "unknown", t=sfp, m=sfp)
    c_ = _rodar(cs, resp, _mutantes_de(cs))["capacidades"]["c"]
    assert c_["extras"]["sem_fundamento_devolvidos_como_nao_verificados"] == "1/1" and c_["aprovada"]
    resp["L-c-020"] = verif("verified", "verified", fundamento=fund())  # devolvido como verificado: reprova
    c_ = _rodar(cs, resp, _mutantes_de(cs))["capacidades"]["c"]
    assert any("sem fundamento da data" in m for m in c_["motivos_reprovacao"])


def test_c_abstencao_sistematica_na_reserva():
    sfp = {"reason_code": "sem_fundamento_do_periodo"}
    cs = _conjunto("c", 8, "nao_verificado_para_D")
    for c in cs:
        c["gabarito"]["motivos_aceitos"] = ["sem_fundamento_do_periodo"]
    resp = {c["id"]: verif("unknown", "unknown", t=sfp, m=sfp) for c in cs}
    muts = _mutantes_de(cs)
    dev = _rodar(cs, resp, muts, conjunto="desenvolvimento")["capacidades"]["c"]
    res = _rodar(cs, resp, muts, conjunto="reserva")["capacidades"]["c"]
    assert not any("40%" in m for m in dev["motivos_reprovacao"])
    assert any("40%" in m for m in res["motivos_reprovacao"])


# --- tabela 3: mutantes ----------------------------------------------------------------------------------------------


def test_mutantes_rejeitados_e_nao_rejeitados():
    c = caso("L-a-001", "a")
    m = {"id": "x", "caso": "L-a-001", "tipo": "renumerado"}
    assert ex.avaliar_mutante(m, c, {"status": "encontrada", "texto": "Art. 15. Outro texto."})["rejeitado"] is True
    assert ex.avaliar_mutante(m, c, {"status": "inexistente"})["rejeitado"] is True
    assert ex.avaliar_mutante(m, c, {"status": "indisponivel"})["rejeitado"] is True
    assert ex.avaliar_mutante(m, c, {"status": "encontrada", "texto": TEXTO})["rejeitado"] is False  # texto do original
    assert ex.avaliar_mutante(m, c, verif())["rejeitado"] is False  # verified
    ch = {"id": "y", "caso": "L-a-001", "tipo": "caractere"}
    assert ex.avaliar_mutante(ch, c, verif("not_found", "unknown"))["rejeitado"] is True
    assert ex.avaliar_mutante(ch, c, verif("verified", "unknown"))["rejeitado"] is False
    dt = {"id": "z", "caso": "L-a-001", "tipo": "data_trocada"}
    assert ex.avaliar_mutante(dt, c, verif("unknown", "not_found"))["rejeitado"] is True
    assert ex.avaliar_mutante(dt, c, verif("unknown", "verified"))["rejeitado"] is False
    assert ex.avaliar_mutante(dt, c, verif("verified", "unknown"))["rejeitado"] is False
    assert ex.avaliar_mutante(m, None, {})["rejeitado"] is False  # sem caso de origem: fechado
    assert ex.avaliar_mutante({"tipo": "outro"}, c, {})["rejeitado"] is False


def test_mutante_e_chamado_pela_chamada_declarada_no_proprio_mutante():
    chamadas = []

    class S(Svc):
        def verificar_citacao(self, citacao, trecho=None, data=None, modo="literal", proposicao=None):
            chamadas.append(("verificar_citacao", citacao, trecho, data))
            return verif("not_found", "unknown")

        def obter_dispositivo(self, citacao=None, work_id=None, caminho=None, data=None, versao="vigente", fonte=None):
            chamadas.append(("obter_dispositivo", citacao, versao))
            return {"status": "inexistente"}
    c = caso("L-a-001", "a")
    muts = [{"id": "L-a-001#caractere", "caso": "L-a-001", "tipo": "caractere",
             "chamada": {"funcao": "verificar_citacao",
                         "parametros": {"citacao": "art. 14 da Lei 6.404/1976", "trecho": "T1"}}},
            {"id": "L-a-001#renumerado", "caso": "L-a-001", "tipo": "renumerado",
             "chamada": {"funcao": "obter_dispositivo",
                         "parametros": {"citacao": "art. 15 da Lei 6.404/1976", "versao": "publicacao_original"}}}]
    ex.executar([c], muts, S(), "remoto", aquecimento=0, medidas=1)
    assert ("verificar_citacao", "art. 14 da Lei 6.404/1976", "T1", None) in chamadas
    assert ("obter_dispositivo", "art. 15 da Lei 6.404/1976", "publicacao_original") in chamadas
    # função fora da fachada pública ou parâmetro estranho: mutante inexecutável, nunca "rejeitado"
    ruins = [{"id": "m1", "caso": "L-a-001", "tipo": "caractere", "chamada": {"funcao": "_resolve", "parametros": {}}},
             {"id": "m2", "caso": "L-a-001", "tipo": "caractere",
              "chamada": {"funcao": "verificar_citacao", "parametros": {"citacao": "x", "interno": 1}}}]
    rel = ex.executar([c], ruins, S(), "remoto", aquecimento=0, medidas=1)
    assert all(not m["rejeitado"] for m in rel["capacidades"]["a"]["mutantes"])


# --- p95 e passadas --------------------------------------------------------------------------------------------------


def test_p95_posto_mais_proximo():
    assert ex.p95([]) is None
    assert ex.p95([float(i) for i in range(1, 101)]) == 95.0  # posto ceil(0,95·100) = 95
    assert ex.p95([float(i) for i in range(1, 21)]) == 19.0  # ceil(19) = 19
    assert ex.p95([5.0]) == 5.0
    assert ex.p95([3.0, 1.0, 2.0]) == 3.0  # ceil(2,85) = 3


def test_uma_passada_de_aquecimento_descartada_e_tres_medidas():
    chamadas = []

    class S(Svc):
        def obter_dispositivo(self, citacao=None, work_id=None, caminho=None, data=None, versao="vigente", fonte=None):
            chamadas.append(citacao)
            return enc()
    rel = ex.executar([caso("L-b-001", "b")], [], S(), "remoto")
    assert len(chamadas) == 4  # 1 de aquecimento + 3 medidas
    assert len(rel["capacidades"]["b"]["casos"][0]["latencias_s"]) == 3  # a de aquecimento não entra


def test_limite_de_p95_por_modo():
    casos = _conjunto("a", 8)
    resp = {c["id"]: enc() for c in casos}
    muts = _mutantes_de(casos)

    def motivos(lat, modo):
        return _rodar(casos, resp, muts, lat={"a": lat}, modo=modo)["capacidades"]["a"]["motivos_reprovacao"]
    assert any("p95" in m for m in motivos([6.0] * 24, "local"))
    assert not any("p95" in m for m in motivos([6.0] * 24, "remoto"))
    assert any("p95" in m for m in motivos([21.0] * 24, "remoto"))


# --- rede: bloqueio com falha fechada --------------------------------------------------------------------------------


def test_bloqueio_de_rede_barra_restaura_e_falha_fechado():
    original = socket.getaddrinfo
    with ex.BloqueioDeRede() as b:
        b.autoteste()
        with pytest.raises(ex.RedeBloqueada):
            socket.create_connection(("example.invalid", 80), timeout=0.1)
        with pytest.raises(ex.RedeBloqueada):
            socket.getaddrinfo("example.invalid", 80)
        with pytest.raises(ex.ViolacaoDeRede):
            b.verificar()
    assert socket.getaddrinfo is original


def test_executar_aborta_se_a_chamada_tentou_rede_mesmo_com_excecao_engolida():
    class S(Svc):
        def obter_dispositivo(self, citacao=None, work_id=None, caminho=None, data=None, versao="vigente", fonte=None):
            try:
                socket.create_connection(("example.invalid", 80), timeout=0.1)
            except OSError:
                pass  # o serviço engole a falha; o executor não
            return {"status": "indisponivel", "motivo": "rede"}
    with ex.BloqueioDeRede() as b:
        with pytest.raises(ex.ViolacaoDeRede):
            ex.executar([caso("L-a-001", "a")], [], S(), "local", bloqueio=b)


# --- congelamento: o executor recusa arquivo divergente --------------------------------------------------------------


def _md(tmp_path, conj_dev, mut_dev, conj_res, mut_res):
    def h(p):
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()
    md = tmp_path / "congelamento.md"
    md.write_text(
        "| Item | Local | SHA-256 |\n|---|---|---|\n"
        f"| Desenvolvimento (2 casos) | `d.jsonl` | `{h(conj_dev)}` |\n"
        f"| Mutantes do desenvolvimento (1) | `dm.jsonl` | `{h(mut_dev)}` |\n"
        f"| Reserva (2 casos) | `r.jsonl` | `{h(conj_res)}` |\n"
        f"| Mutantes da reserva (1) | `rm.jsonl` | `{h(mut_res)}` |\n"
        f"| Cobertura do desenvolvimento | `c.json` | `{'0' * 64}` |\n", encoding="utf-8")
    return md


def _arquivos(tmp_path):
    nomes = {}
    for n in ("d", "dm", "r", "rm"):
        p = tmp_path / f"{n}.jsonl"
        p.write_text(json.dumps({"id": n}) + "\n", encoding="utf-8")
        nomes[n] = p
    return nomes, _md(tmp_path, *(nomes[n] for n in ("d", "dm", "r", "rm")))


def test_conferencia_do_congelamento(tmp_path):
    f, md = _arquivos(tmp_path)
    assert ex.conferir_congelamento(f["d"], f["dm"], md) == "desenvolvimento"
    assert ex.conferir_congelamento(f["r"], f["rm"], md) == "reserva"
    with pytest.raises(ValueError):  # conjunto de um lado e mutantes do outro
        ex.conferir_congelamento(f["d"], f["rm"], md)
    f["d"].write_text('{"id": "adulterado"}\n', encoding="utf-8")
    with pytest.raises(ValueError):
        ex.conferir_congelamento(f["d"], f["dm"], md)
    with pytest.raises(ValueError):  # documento sem os hashes
        ex.hashes_congelados(tmp_path / "d.jsonl")


@pytest.mark.repositorio
def test_arquivos_congelados_do_desenvolvimento_conferem_e_adulterado_e_recusado(tmp_path):
    pl = RAIZ / "tests" / "porta_l"
    papel = ex.conferir_congelamento(pl / "desenvolvimento.jsonl", pl / "mutantes.jsonl", ex.CONGELAMENTO_PADRAO)
    assert papel == "desenvolvimento"
    copia = tmp_path / "desenvolvimento.jsonl"
    copia.write_bytes((pl / "desenvolvimento.jsonl").read_bytes() + b"\n")
    with pytest.raises(ValueError):
        ex.conferir_congelamento(copia, pl / "mutantes.jsonl", ex.CONGELAMENTO_PADRAO)


def test_cli_recusa_divergente_e_nao_executa(tmp_path):
    f, md = _arquivos(tmp_path)
    f["d"].write_text('{"id": "adulterado"}\n', encoding="utf-8")

    class Boom:
        def __getattr__(self, n):
            raise AssertionError("não devia executar")
    rc = ex.main(["--conjunto", str(f["d"]), "--mutantes", str(f["dm"]), "--home", str(tmp_path), "--modo", "remoto",
                  "--saida", str(tmp_path / "s.json"), "--congelamento", str(md)], _servico=Boom())
    assert rc == 2 and not (tmp_path / "s.json").exists()


def _montar(tmp_path, casos):
    d, dm, r, rm = (tmp_path / n for n in ("d.jsonl", "dm.jsonl", "r.jsonl", "rm.jsonl"))
    d.write_text("\n".join(json.dumps(c) for c in casos) + "\n", encoding="utf-8")
    for p, t in ((dm, ""), (r, "x\n"), (rm, "y\n")):
        p.write_text(t, encoding="utf-8")
    return d, dm, _md(tmp_path, d, dm, r, rm)


def test_cli_somente_tabela_nao_vaza_casos(tmp_path, capsys):
    d, dm, md = _montar(tmp_path, _conjunto("a", 3))

    class S(Svc):
        def obter_dispositivo(self, citacao=None, work_id=None, caminho=None, data=None, versao="vigente", fonte=None):
            return enc()
    rc = ex.main(["--conjunto", str(d), "--mutantes", str(dm), "--home", str(tmp_path), "--modo", "remoto",
                  "--saida", str(tmp_path / "s.json"), "--congelamento", str(md), "--somente-tabela"], _servico=S())
    out = capsys.readouterr().out
    saida = json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))
    assert set(saida) == {"tabela"} and set(saida["tabela"]) == set(ex.CAPS)
    assert rc == 1  # sem casos de b a e e sem unidades suficientes: reprovado
    assert "L-a-" not in out and "L-a-" not in json.dumps(saida)
    assert out.splitlines()[0] in ("(a) aprovado", "(a) reprovado")


def test_cli_modo_local_falha_fechada_em_tentativa_de_rede(tmp_path):
    d, dm, md = _montar(tmp_path, _conjunto("a", 2))

    class S(Svc):
        def obter_dispositivo(self, citacao=None, work_id=None, caminho=None, data=None, versao="vigente", fonte=None):
            try:
                socket.getaddrinfo("example.invalid", 443)
            except OSError:
                pass
            return {"status": "indisponivel"}
    rc = ex.main(["--conjunto", str(d), "--mutantes", str(dm), "--home", str(tmp_path), "--modo", "local",
                  "--saida", str(tmp_path / "s.json"), "--congelamento", str(md)], _servico=S())
    assert rc == 3 and not (tmp_path / "s.json").exists()


def test_executor_nao_le_a_reserva_por_caminho_fixo():
    fonte = SCRIPT.read_text(encoding="utf-8")
    assert "Claude_Externos" not in fonte and "reserva-v2" not in fonte and "porta-l/reserva" not in fonte


# --- mutantes do executor: a bateria tem de pegá-los --------------------------------------------------------------------


def bateria(m) -> list[str]:
    """Cenários que o executor correto passa; devolve as falhas observadas em `m` (o módulo, possivelmente mutado)."""
    falhas = []
    cs = [caso(f"L-e-{i:03d}", "e", familia=f"lei-{2000 + i}-1999", numero=str(6404 + i % 5), ano=1976 + i % 5,
               alvos=ALVOS) for i in range(1, 9)]
    rel = m.consolidar(cs, [], {c["id"]: aval("parcial") for c in cs}, {}, {"e": [0.1]}, "remoto", None)
    if rel["capacidades"]["e"]["acertos"] != 0:
        falhas.append("parcial no numerador")
    dois = [caso("L-a-001", "a", familia="lei-10303-2001"), caso("L-a-002", "a", familia="lei-10303-2001")]
    rel = m.consolidar(dois, [], {c["id"]: aval("acerto") for c in dois}, {}, {"a": [0.1]}, "remoto", None)
    if rel["capacidades"]["a"]["denominador"] != 1:
        falhas.append("duas unidades do mesmo evento")
    if m.fundamento_ok(fund(cid="inexistente"), D, Svc(evid_ok()))[0]:
        falhas.append("fundamento sem capture_id recuperável")
    if m.fundamento_ok({**fund(), "capture_id": None}, D, Svc(evid_ok()))[0]:
        falhas.append("fundamento sem capture_id")
    if m.igual_texto("Art. 1º Texto", "art. 1º texto"):
        falhas.append("normaliza caixa")
    return falhas


def test_bateria_passa_no_executor_correto():
    assert bateria(ex) == []


@pytest.mark.parametrize("nome,alvo,mutacao", [
    ("aceita_parcial_no_numerador", "eh_acerto", lambda r: r in ("acerto", "parcial")),
    ("conta_duas_unidades_do_mesmo_evento", "representantes", lambda casos: {c["id"]: c["id"] for c in casos}),
    ("aceita_fundamento_sem_capture_id_recuperavel", "fundamento_ok",
     lambda f, d, svc: (isinstance(f, dict) and f.get("tipo") == "versao_oficial_na_data", "")),
    ("normaliza_caixa", "igual_texto",
     lambda a, b: isinstance(a, str) and isinstance(b, str) and ex.norm(a).lower() == ex.norm(b).lower()),
])
def test_mutantes_do_executor_falham(monkeypatch, nome, alvo, mutacao):
    monkeypatch.setattr(ex, alvo, mutacao)
    assert bateria(ex) != [], f"o mutante {nome} passou despercebido"


# --- fachada real: o executor chama a fachada pública e mede (b) e (e) ----------------------------------------------------


@pytest.fixture
def svc6385(tmp_path, monkeypatch):
    from freoa_verifica.aliases import WorkKey
    from freoa_verifica.parsers.planalto import parse_planalto
    from freoa_verifica.service import Verifica
    from tests.fixture_util import load_fixture, load_meta

    home = tmp_path / "fv-exec"
    home.mkdir()
    monkeypatch.setenv("FV_HOME", str(home))
    monkeypatch.setenv("FV_OFFLINE", "1")
    body = load_fixture("planalto_lei_6385_1976")
    entry = load_meta()["planalto_lei_6385_1976"]
    doc = parse_planalto(body, base_url="https://www.planalto.gov.br/ccivil_03/leis/")
    svc = Verifica(home=home)
    svc.indexar_obra(source_id="planalto", work_key=WorkKey("federal", "lei", "6385", 1976), document=doc, body=body,
                     url=entry["url"], fetched_at=entry.get("capturado_em"), work_date="1976-12-07",
                     label="Lei nº 6.385/1976", content_type="text/html; charset=windows-1252")
    yield svc, doc
    svc.close()


def test_executor_mede_b_e_e_pela_fachada_publica(svc6385):
    svc, doc = svc6385
    texto = doc.current_text("art9")
    base = {"conjunto": "desenvolvimento", "familia_alteracao": "original", "familia_fundamento": None,
            "norma": {"especie": "lei", "numero": "6385", "ano": 1976}, "citacao": "art. 9 da Lei 6.385/1976",
            "caminho": "art. 9", "data": None, "trecho": None, "norma_grande": False}
    b = {**base, "id": "L-b-001", "capacidade": "b", "gabarito": {"tipo": "texto", "texto": texto, "motivos_aceitos": [],
                                                                  "cadeia": [], "alvos": [], "alvos_equivalentes": {}}}
    e = {**base, "id": "L-e-001", "capacidade": "e",
         "gabarito": {"tipo": "texto", "texto": texto, "motivos_aceitos": [], "cadeia": [], "alvos_equivalentes": {},
                      "alvos": [{"obra": "Lei 6.385/1976", "caminho": "art. 15, § 2º"}]}}
    e_ruim = {**e, "id": "L-e-002", "familia_alteracao": "lei-1-2000",
              "gabarito": {**e["gabarito"], "alvos": [{"obra": "Lei 6.385/1976", "caminho": "art. 16"}]}}
    rel = ex.executar([b, e, e_ruim], [], svc, "remoto", aquecimento=0, medidas=1)
    por = {c["id"]: c for cap in ("b", "e") for c in rel["capacidades"][cap]["casos"]}
    assert por["L-b-001"]["resultado"] == "acerto"
    assert por["L-e-001"]["resultado"] == "acerto"
    # remissão resolvida fora do gabarito é confirmação indevida (iii), pela mesma fachada
    assert por["L-e-002"]["resultado"] == "erro" and por["L-e-002"]["indevidas"][0]["item"] == "iii"
