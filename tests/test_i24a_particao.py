"""I2.4-a: partes de `obter_decisao` (PARIDADE-1.4, CH1–CH6, C1/C5/C8; decisão 0073, seção 7). Tudo offline."""

from __future__ import annotations

import ast
import asyncio
import hashlib
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from freoa_verifica import mcp_server as ms, particao as pt  # noqa: E402
from freoa_verifica.limites import EntradaInvalida  # noqa: E402
from freoa_verifica.mcp_server import create_mcp  # noqa: E402
from freoa_verifica.rest import create_app  # noqa: E402
from freoa_verifica.sanitizacao import DOC_CLOSE, DOC_OPEN  # noqa: E402
from tests.contrato import harness as h  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
S = pt.SOBREPOSICAO

# ----------------------------------------------------------------------------------------------
# Textos sintéticos (determinísticos)
# ----------------------------------------------------------------------------------------------

TEXTOS = {
    "ascii": "Palavra simples de teste. " * 400,
    "acentos": "Ação rescisória, decisão unânime: não conhecida, à exceção do §2º. " * 150,
    "emoji_e_fora_do_bmp": "Fim 😀 de 𝒳 linha 文字 🧑‍⚖️ ok. " * 300,
    "paragrafos_curtos": "Parágrafo curto.\n\n" * 600,
    "paragrafos_longos": ("Frase longa de um parágrafo extenso. " * 25 + "\n\n") * 12,
    "linhas": "Linha de texto com quebra simples.\n" * 300,
    "sem_quebra": "a" * 5000,
    "menor_que_uma_parte": "Texto curto, menor que uma parte.",
    "exato_uma_parte": "b" * 2000,
    "exato_duas_partes": "c" * 4000,
    "um_a_mais": "d" * 2001,
    "emoji_no_limite": "x" * 1999 + "😀" * 1500,
}


def _reconstruir(partes: list[str], intervalos: list[tuple[int, int]]) -> str:
    out = partes[0]
    for (ini, _), p, (_, fim_ant) in zip(intervalos[1:], partes[1:], intervalos):
        assert fim_ant - ini == S  # sobreposição fixa
        out += p[S:]
    return out


# ----------------------------------------------------------------------------------------------
# Regra pura: CH2, CH3, CH4
# ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("tamanho", [500, 777, 2000, 10_000])
@pytest.mark.parametrize("nome", sorted(TEXTOS))
def test_ch2_ch3_concatenar_sem_sobreposicao_reconstroi_texto_e_hash(nome, tamanho):
    texto = TEXTOS[nome]
    ivs = pt.intervalos(texto, tamanho)
    ps = [pt.particionar(texto, i, tamanho) for i in range(len(ivs))]
    assert [p.intervalo for p in ps] == ivs and all(p.partes_total == len(ivs) for p in ps)
    assert ivs[0][0] == 0 and ivs[-1][1] == len(texto)
    assert all(b - a >= 1 for a, b in ivs) and all(b - a <= tamanho for a, b in ivs)
    rec = _reconstruir([p.texto_parte for p in ps], ivs)
    assert rec == texto
    assert hashlib.sha256(rec.encode("utf-8")).hexdigest() == ps[0].sha256_texto
    for p in ps:
        assert p.sha256_parte == hashlib.sha256(p.texto_parte.encode("utf-8")).hexdigest()
        assert p.texto_parte == texto[p.intervalo[0]:p.intervalo[1]]
    # determinismo: mesma entrada, mesmos bytes
    ps2 = [pt.particionar(texto, i, tamanho) for i in range(len(ivs))]
    assert [p.texto_parte.encode() for p in ps] == [p.texto_parte.encode() for p in ps2]


def test_ch3_texto_menor_ou_igual_a_parte_tem_uma_parte():
    for nome in ("menor_que_uma_parte", "exato_uma_parte"):
        assert pt.intervalos(TEXTOS[nome], 2000) == [(0, len(TEXTOS[nome]))]
    assert len(pt.intervalos(TEXTOS["exato_duas_partes"], 2000)) == 3  # 0–2000, 1800–3800, 3600–4000
    assert len(pt.intervalos(TEXTOS["um_a_mais"], 2000)) == 2


def test_ch4_nenhum_corte_separa_ponto_de_codigo_ou_par_substituto():
    for nome in ("emoji_e_fora_do_bmp", "emoji_no_limite"):
        texto = TEXTOS[nome]
        for tamanho in (500, 501, 777, 1999, 2000):
            for ini, fim in pt.intervalos(texto, tamanho):
                parte = texto[ini:fim]
                u16 = parte.encode("utf-16-le")  # `strict`: par solto levanta
                unidades = [int.from_bytes(u16[i:i + 2], "little") for i in range(0, len(u16), 2)]
                assert not 0xDC00 <= unidades[0] <= 0xDFFF, "parte começa no meio de um par substituto"
                assert not 0xD800 <= unidades[-1] <= 0xDBFF, "parte termina no meio de um par substituto"
                assert parte.encode("utf-8").decode("utf-8") == parte


def test_ch4_prefere_fim_de_paragrafo_na_janela_final():
    # janela de 500: últimos 200 = [300, 500)
    t = "a" * 400 + "\n\n" + "b" * 1000
    assert pt.intervalos(t, 500)[0] == (0, 402)  # corta depois de \n\n
    t = "a" * 100 + "\n\n" + "b" * 1000  # parágrafo fora dos últimos 200: limite da janela
    assert pt.intervalos(t, 500)[0] == (0, 500)
    t = "a" * 450 + "\n" + "b" * 1000  # só \n
    assert pt.intervalos(t, 500)[0] == (0, 451)
    t = "a" * 350 + "\n\n" + "b" * 127 + "\n" + "c" * 1000  # \n\n precede \n mesmo mais distante
    assert pt.intervalos(t, 500)[0] == (0, 352)
    t = "a" * 300 + "\n\n" + "b" * 1000  # \n\n no início da faixa (lo = 300)
    assert pt.intervalos(t, 500)[0] == (0, 302)
    t = "a" * 299 + "\n\n" + "b" * 1000  # o par começa antes da faixa: só o segundo \n está nela e vale como \n
    assert pt.intervalos(t, 500)[0] == (0, 301)
    t = "a" * 299 + "\n" + "b" * 1000  # \n antes da faixa: não conta
    assert pt.intervalos(t, 500)[0] == (0, 500)
    # a parte seguinte começa sempre 200 antes do fim da anterior
    ivs = pt.intervalos("a" * 400 + "\n\n" + "b" * 1000, 500)
    assert ivs[1][0] == 402 - S


def test_ch4_progresso_garantido_em_texto_so_de_quebras():
    for t in ("\n" * 5000, "\n\n" * 3000, "\n\n\n" * 2000):
        ivs = pt.intervalos(t, 500)
        assert all(b > a for a, b in ivs) and all(ivs[i + 1][0] > ivs[i][0] for i in range(len(ivs) - 1))
        assert ivs[-1][1] == len(t)
        ps = [pt.particionar(t, i, 500).texto_parte for i in range(len(ivs))]
        assert _reconstruir(ps, ivs) == t


def test_parte_fora_do_intervalo_levanta_com_partes_total():
    n = len(pt.intervalos(TEXTOS["ascii"], 2000))
    with pytest.raises(IndexError, match=f"partes_total={n}"):
        pt.particionar(TEXTOS["ascii"], n, 2000)
    with pytest.raises(IndexError):
        pt.particionar(TEXTOS["ascii"], -1, 2000)
    with pytest.raises(ValueError):
        pt.intervalos("x", 499)
    with pytest.raises(ValueError):
        pt.intervalos("x", 10_001)


# ----------------------------------------------------------------------------------------------
# Serviço e adaptadores
# ----------------------------------------------------------------------------------------------

@pytest.fixture
def ambiente(verifica_populada, monkeypatch):
    svc, rw, _ = verifica_populada
    ctx = dict(h.semear(svc))
    for i, (nome, texto) in enumerate(sorted(TEXTOS.items())):
        ctx[nome] = h.indexar_decisao(svc, "STJ", f"92{i:04d}", text=texto, ementa="Ementa sintética.",
                                      profile="stf_pdf")
    ctx["ementa_longa"] = h.indexar_decisao(svc, "STJ", "930001", text=None, ementa=TEXTOS["paragrafos_longos"])
    monkeypatch.setenv("FV_HOME", str(svc.home))
    monkeypatch.delenv("FV_API_TOKEN", raising=False)
    monkeypatch.setitem(ms._servicos, str(svc.home), svc)
    mcp = create_mcp(home=str(svc.home))
    app = create_app(home=str(svc.home), token=None)
    for cached in svc._resolver.works.values():
        app.state.verifica.registrar(cached)
    with TestClient(app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1") as rest:
        yield {"python": svc, "mcp": mcp, "rest": rest, "ctx": ctx}


def _chamar(amb, adaptador, **args):
    chamar = {"python": h.chamar_python, "mcp": h.chamar_mcp, "rest": h.chamar_rest}[adaptador]
    return chamar(amb[adaptador], "obter_decisao", args)


def _sem_delimitadores(resp: dict) -> dict:
    """Única normalização admitida do MCP para `obter_decisao` (CONTRATO, Convenções)."""
    resp = dict(resp)
    t = resp.get("texto")
    if isinstance(t, str):
        assert t.startswith(DOC_OPEN + "\n") and t.endswith("\n" + DOC_CLOSE)  # C6
        resp["texto"] = t[len(DOC_OPEN) + 1:-len(DOC_CLOSE) - 1]
    return resp


def _texto_inteiro(svc, did, parte="inteiro_teor") -> str:
    partes, cursor = [], "0"
    while cursor is not None:
        r = svc.obter_decisao(did, parte=parte, max_chars=50_000, offset=int(cursor))
        partes.append(r["texto"])
        cursor = r["cursor"]
    return "".join(partes)


def _todas_as_partes(svc, did, tamanho, parte="inteiro_teor"):
    r0 = svc.obter_decisao(did, parte=parte, parte_idx=0, parte_tamanho=tamanho)
    total = r0["particao"]["partes_total"]
    return [r0] + [svc.obter_decisao(did, parte=parte, parte_idx=i, parte_tamanho=tamanho) for i in range(1, total)]


@pytest.mark.parametrize("nome", sorted(TEXTOS))
def test_servico_reconstroi_texto_e_hash_pelas_partes(ambiente, nome):
    svc, did = ambiente["python"], ambiente["ctx"][nome]
    canonico = _texto_inteiro(svc, did)
    rs = _todas_as_partes(svc, did, 777)
    ivs = [tuple(r["particao"]["intervalo"]) for r in rs]
    assert _reconstruir([r["texto"] for r in rs], ivs) == canonico
    for r in rs:
        p = r["particao"]
        assert p["sha256_texto"] == hashlib.sha256(canonico.encode("utf-8")).hexdigest()
        assert p["sha256_parte"] == hashlib.sha256(r["texto"].encode("utf-8")).hexdigest()
        assert p["partes_total"] == len(rs) and p["parte_tamanho"] == 777 and p["sobreposicao"] == 200
        assert p["segmentos"] == ["nao_identificado"]
    # mesma entrada, mesmos bytes
    assert svc.obter_decisao(did, parte="inteiro_teor", parte_idx=0, parte_tamanho=777) == rs[0]


def test_servico_parte_ementa_e_padrao_de_tamanho(ambiente):
    svc, did = ambiente["python"], ambiente["ctx"]["ementa_longa"]
    r = svc.obter_decisao(did, parte_idx=0)  # parte=ementa, parte_tamanho=2000
    assert r["parte_entregue"] == "ementa" and r["particao"]["parte_tamanho"] == 2000 == r["max_chars"]
    assert r["texto"] == TEXTOS["paragrafos_longos"][:r["particao"]["intervalo"][1]]


def test_ch6_campos_do_contrato_1_iguais_aos_da_resposta_sem_parte_idx(ambiente):
    svc, did = ambiente["python"], ambiente["ctx"]["stj_inteiro"]
    sem = svc.obter_decisao(did, parte="inteiro_teor", max_chars=100)
    for idx in range(0, 3):
        com = svc.obter_decisao(did, parte="inteiro_teor", parte_idx=idx, parte_tamanho=500)
        assert set(sem) <= set(com) and set(com) - set(sem) == {"particao"}
        assert h.incompatibilidades("obter_decisao", sem, com) == []  # tipo, nulidade e estados
        for k in ("status", "parte", "parte_solicitada", "parte_entregue", "partes_disponiveis", "capture_id",
                  "id", "tribunal", "classe", "numero", "orgao", "relator", "autoridade_label"):
            assert com[k] == sem[k], k


def test_ch1_sem_parte_idx_resposta_identica_a_de_sempre(ambiente):
    svc, did = ambiente["python"], ambiente["ctx"]["stj_inteiro"]
    r = svc.obter_decisao(did, parte="inteiro_teor", max_chars=100)
    assert "particao" not in r and r["max_chars"] == 100 and r["cursor"] == "100" and r["offset"] == 0
    r = svc.obter_decisao(did, parte="inteiro_teor")
    assert "particao" not in r and r["max_chars"] == 8000
    r = svc.obter_decisao(did, parte="inteiro_teor", max_chars=100, offset=50)
    assert r["cursor"] == "150" and r["texto"] == _texto_inteiro(svc, did)[50:150]


ENTRADAS_INVALIDAS = {
    "parte_idx_negativo": {"parte_idx": -1},
    "parte_idx_com_offset": {"parte_idx": 0, "offset": 5},
    "parte_idx_com_max_chars": {"parte_idx": 0, "max_chars": 100},
    "parte_idx_com_max_chars_padrao": {"parte_idx": 0, "max_chars": 8000},
    "parte_tamanho_pequeno": {"parte_idx": 0, "parte_tamanho": 499},
    "parte_tamanho_grande": {"parte_idx": 0, "parte_tamanho": 10_001},
    "parte_tamanho_sem_parte_idx": {"parte_tamanho": 600},
    "parte_idx_alem_do_total": {"parte_idx": 9999},
    "parte_tamanho_zero": {"parte_idx": 0, "parte_tamanho": 0},
    "parte_tamanho_negativo": {"parte_idx": 0, "parte_tamanho": -500},
}
MSG_MCP_MASCARADA = "Error executing tool obter_decisao"
# No MCP, o esquema estrito recusa antes do serviço; a mensagem é do SDK e nomeia o parâmetro.
REJEITADOS_PELO_ESQUEMA_MCP = {
    "parte_idx_negativo": "parte_idx",
    "parte_tamanho_pequeno": "parte_tamanho",
    "parte_tamanho_grande": "parte_tamanho",
    "parte_tamanho_zero": "parte_tamanho",
    "parte_tamanho_negativo": "parte_tamanho",
}

# Tipos que o SDK coagiria sem o esquema estrito (achado da r1 do PR #23): o MCP recusa, o serviço recusa, e nenhum
# chega ao acervo.
TIPOS_INVALIDOS = {
    "parte_idx_true": ({"parte_idx": True}, "parte_idx"),
    "parte_idx_false": ({"parte_idx": False}, "parte_idx"),
    "parte_idx_string": ({"parte_idx": "1"}, "parte_idx"),
    "parte_idx_float": ({"parte_idx": 1.0}, "parte_idx"),
    "parte_tamanho_float": ({"parte_idx": 0, "parte_tamanho": 500.0}, "parte_tamanho"),
    "parte_tamanho_true": ({"parte_idx": 0, "parte_tamanho": True}, "parte_tamanho"),
    "parte_tamanho_string": ({"parte_idx": 0, "parte_tamanho": "600"}, "parte_tamanho"),
}


@pytest.mark.parametrize("caso", sorted(TIPOS_INVALIDOS))
def test_r1_pr23_tipos_invalidos_recusados_no_mcp_e_no_servico(ambiente, caso, monkeypatch):
    extra, nome = TIPOS_INVALIDOS[caso]
    svc, did = ambiente["python"], ambiente["ctx"]["stj_inteiro"]
    args = {"id": did, "parte": "inteiro_teor", **extra}
    with pytest.raises(EntradaInvalida) as exc:
        svc.obter_decisao(**args)
    assert nome in str(exc.value)
    msg = _erro_mcp(ambiente["mcp"], args)
    assert nome in msg, msg
    assert "encontrada" not in msg and "particao" not in msg.replace(nome, "")


def test_r1_pr23_esquema_mcp_estrito_com_faixa_do_servico(ambiente):
    async def _esquema():
        return {t.name: t.input_schema for t in await ambiente["mcp"].list_tools()}["obter_decisao"]

    props = asyncio.run(_esquema())["properties"]

    def _inteiro(p):
        return next(s for s in p.get("anyOf", [p]) if s.get("type") == "integer")

    idx, tam = _inteiro(props["parte_idx"]), _inteiro(props["parte_tamanho"])
    assert (idx["minimum"], tam["minimum"], tam["maximum"]) == (0, pt.PARTE_TAMANHO_MIN, pt.PARTE_TAMANHO_MAX)


def _erro_mcp(mcp, args) -> str:
    from mcp import Client

    async def _run():
        async with Client(mcp) as client:
            r = await client.call_tool("obter_decisao", args)
            assert r.is_error, f"esperava erro de ferramenta, veio {r}"
            return "\n".join(getattr(b, "text", "") or "" for b in r.content or [])

    return asyncio.run(_run())


@pytest.mark.parametrize("caso", sorted(ENTRADAS_INVALIDAS))
def test_ch1_ch6_entrada_invalida_nos_tres_adaptadores(ambiente, caso):
    did = ambiente["ctx"]["stj_inteiro"]
    args = {"id": did, "parte": "inteiro_teor", **ENTRADAS_INVALIDAS[caso]}
    with pytest.raises(EntradaInvalida) as exc:
        ambiente["python"].obter_decisao(**args)
    msg_python = str(exc.value)
    if caso == "parte_idx_alem_do_total":
        assert "partes_total=" in msg_python
    msg_mcp = _erro_mcp(ambiente["mcp"], args)
    if caso in REJEITADOS_PELO_ESQUEMA_MCP:
        assert REJEITADOS_PELO_ESQUEMA_MCP[caso] in msg_mcp, msg_mcp
    else:
        # O SDK do MCP mascara a mensagem de exceção do serviço (comportamento de todas as ferramentas, não deste PR):
        # confere-se o erro de ferramenta com o texto exato do SDK; a causa é a EntradaInvalida acima, mesmos argumentos.
        assert msg_mcp == MSG_MCP_MASCARADA, msg_mcp
    rest_args = dict(args)
    r = ambiente["rest"].get(f"/v1/decisoes/{rest_args.pop('id')}", params=rest_args)
    assert r.status_code == 422 and r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["detail"] == msg_python


def test_ch6_parte_idx_igual_ao_total_e_negativos(ambiente):
    svc, did = ambiente["python"], ambiente["ctx"]["stj_inteiro"]
    total = svc.obter_decisao(did, parte="inteiro_teor", parte_idx=0, parte_tamanho=500)["particao"]["partes_total"]
    assert total > 1
    for idx in (total, total + 1, -1, -100):
        with pytest.raises(EntradaInvalida) as exc:
            svc.obter_decisao(did, parte="inteiro_teor", parte_idx=idx, parte_tamanho=500)
        if idx >= 0:
            assert f"partes_total={total}" in str(exc.value)
    assert svc.obter_decisao(did, parte="inteiro_teor", parte_idx=total - 1, parte_tamanho=500)["status"] == "encontrada"
    with pytest.raises(EntradaInvalida):
        svc.obter_decisao(did, parte="inteiro_teor", parte_idx=True)
    with pytest.raises(EntradaInvalida):
        svc.obter_decisao(did, parte="inteiro_teor", parte_idx="1")


def test_parte_indisponivel_vale_com_e_sem_parte_idx(ambiente):
    svc, did = ambiente["python"], ambiente["ctx"]["stj_ementa"]
    sem = svc.obter_decisao(did, parte="inteiro_teor")
    com = svc.obter_decisao(did, parte="inteiro_teor", parte_idx=0)
    assert sem == com and com["status"] == "parte_indisponivel" and "particao" not in com
    assert com["texto"] is None and com["capture_id"] is None


def test_outros_estados_com_parte_idx_nao_mudam(ambiente):
    svc = ambiente["python"]
    assert svc.obter_decisao("REsp 8.888.888", parte_idx=0)["status"] == "nao_encontrado_no_acervo"
    assert svc.obter_decisao("555", parte_idx=0)["status"] == "ambiguous"
    assert svc.obter_decisao("555", tribunal="TCU", parte_idx=0)["status"] == "encontrada"


@pytest.mark.parametrize("nome", ["paragrafos_longos", "paragrafos_curtos", "emoji_e_fora_do_bmp", "sem_quebra",
                                  "exato_duas_partes"])
@pytest.mark.parametrize("tamanho", [500, 777, 2000])
def test_navegacao_cursor_offset_e_intervalo_coerentes(ambiente, nome, tamanho):
    svc, did = ambiente["python"], ambiente["ctx"][nome]
    canonico = _texto_inteiro(svc, did)
    rs = _todas_as_partes(svc, did, tamanho)
    cortes_antes_do_limite = 0
    for i, r in enumerate(rs):
        ini, fim = r["particao"]["intervalo"]
        assert r["offset"] == ini and r["max_chars"] == tamanho and fim - ini <= tamanho
        assert r["texto"] == canonico[ini:fim]
        cortes_antes_do_limite += fim - ini < tamanho and i < len(rs) - 1
        if i < len(rs) - 1:
            assert r["truncado"] is True and r["cursor"] == str(fim)
            # seguir por `cursor` no modo offset lê o restante sem lacuna nem repetição
            resto, cursor = "", r["cursor"]
            while cursor is not None:
                p = svc.obter_decisao(did, parte="inteiro_teor", max_chars=1234, offset=int(cursor))
                resto += p["texto"]
                cursor = p["cursor"]
            assert r["texto"] + resto == canonico[ini:]
            assert rs[i + 1]["particao"]["intervalo"][0] == fim - 200  # parte seguinte: início = fim - sobreposição
        else:
            assert r["truncado"] is False and r["cursor"] is None and fim == len(canonico)
    if nome in ("paragrafos_longos", "paragrafos_curtos") and tamanho == 777:
        assert cortes_antes_do_limite > 0  # o fim de parágrafo antecipou o corte, e os três campos seguiram coerentes


def test_navegacao_tipos_do_cursor(ambiente):
    svc, did = ambiente["python"], ambiente["ctx"]["paragrafos_longos"]
    rs = _todas_as_partes(svc, did, 500)
    assert all(isinstance(r["cursor"], str) for r in rs[:-1]) and rs[-1]["cursor"] is None
    assert all(isinstance(r["truncado"], bool) for r in rs)


@pytest.mark.parametrize("args", [
    {"parte": "inteiro_teor", "parte_idx": 0, "parte_tamanho": 500},
    {"parte": "inteiro_teor", "parte_idx": 3, "parte_tamanho": 600},
    {"parte": "inteiro_teor", "parte_idx": 0},
    {"parte": "ementa", "parte_idx": 0},
], ids=["primeira", "meio", "tamanho_padrao", "ementa"])
@pytest.mark.parametrize("nome", ["stj_inteiro", "paragrafos_longos"])
def test_c8_mesma_resposta_nos_tres_adaptadores(ambiente, nome, args):
    args = {"id": ambiente["ctx"][nome], **args}
    py = _chamar(ambiente, "python", **args)
    mcp = _chamar(ambiente, "mcp", **args)
    rest = _chamar(ambiente, "rest", **args)
    assert py["status"] == "encontrada" or py["status"] == "parte_indisponivel"
    if py["status"] == "encontrada":
        assert mcp["texto"].startswith(DOC_OPEN + "\n")  # C6
        assert "particao" in py
    assert _sem_delimitadores(mcp) == py == rest


def test_c8_sem_parte_idx_mesma_resposta_nos_tres_adaptadores(ambiente):
    args = {"id": ambiente["ctx"]["stj_inteiro"], "parte": "inteiro_teor", "max_chars": 100}
    py, mcp, rest = (_chamar(ambiente, a, **args) for a in ("python", "mcp", "rest"))
    assert "particao" not in py and _sem_delimitadores(mcp) == py == rest
    # padrão do MCP e do REST sem max_chars: o mesmo 8000 de sempre
    args = {"id": ambiente["ctx"]["stj_inteiro"], "parte": "inteiro_teor"}
    py, mcp, rest = (_chamar(ambiente, a, **args) for a in ("python", "mcp", "rest"))
    assert py["max_chars"] == 8000 and _sem_delimitadores(mcp) == py == rest


def test_c8_hash_e_do_texto_canonico_nao_do_texto_envolvido(ambiente):
    args = {"id": ambiente["ctx"]["stj_inteiro"], "parte": "inteiro_teor", "parte_idx": 1, "parte_tamanho": 500}
    mcp = _chamar(ambiente, "mcp", **args)
    interno = _sem_delimitadores(mcp)["texto"]
    assert mcp["particao"]["sha256_parte"] == hashlib.sha256(interno.encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------------------------------
# Contrato
# ----------------------------------------------------------------------------------------------

@pytest.mark.repositorio
def test_particao_e_experimental_e_documentada():
    from freoa_verifica.contrato import EXPERIMENTAL

    assert "obter_decisao:particao" in EXPERIMENTAL
    md = (RAIZ / "docs" / "CONTRATO.md").read_text(encoding="utf-8")
    secao = md.split("### `obter_decisao`", 1)[1].split("\n### ", 1)[0]
    for termo in ("particao", "experimental", "parte_idx", "parte_tamanho", "sobreposicao", "sha256_parte",
                  "sha256_texto", "segmentos", "nao_identificado", "\\n\\n"):
        assert termo in secao, termo


# ----------------------------------------------------------------------------------------------
# C1 e C5: sem rede, sem subprocesso, sem runtime de modelo
# ----------------------------------------------------------------------------------------------

PROIBIDOS_NO_MODULO = {"urllib", "http", "socket", "ssl", "requests", "httpx", "subprocess", "os", "asyncio",
                       "onnxruntime", "torch", "transformers", "sqlite_vec", "numpy", "freoa_verifica"}
RUNTIMES_DE_MODELO = ("onnxruntime", "torch", "transformers", "sqlite_vec", "tensorflow", "sentence_transformers",
                      "llama_cpp", "openai", "anthropic")


@pytest.mark.repositorio
def test_c1_c5_estrutural_modulo_novo_so_importa_hashlib_e_dataclasses():
    arvore = ast.parse((RAIZ / "freoa_verifica" / "particao.py").read_text(encoding="utf-8"))
    importados = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            importados |= {a.name.split(".")[0] for a in no.names}
        elif isinstance(no, ast.ImportFrom):
            importados.add((no.module or "").split(".")[0])
    assert importados <= {"__future__", "hashlib", "dataclasses"}, importados
    assert not importados & PROIBIDOS_NO_MODULO


@pytest.mark.repositorio
def test_c1_c5_estrutural_obter_decisao_nao_chama_rede_nem_subprocesso():
    fonte = (RAIZ / "freoa_verifica" / "service.py").read_text(encoding="utf-8")
    arvore = ast.parse(fonte)
    metodo = next(n for n in ast.walk(arvore) if isinstance(n, ast.FunctionDef) and n.name == "obter_decisao")
    nomes = {n.id for n in ast.walk(metodo) if isinstance(n, ast.Name)} | \
            {n.attr for n in ast.walk(metodo) if isinstance(n, ast.Attribute)}
    assert not nomes & {"subprocess", "socket", "urllib", "requests", "httpx", "system", "Popen", "fetch",
                        "transport", "onnxruntime", "torch", "transformers"}, nomes


def test_c1_c5_execucao_sem_rede_sem_subprocesso_sem_runtime_de_modelo(ambiente, monkeypatch):
    svc = ambiente["python"]
    did = ambiente["ctx"]["paragrafos_longos"]
    antes = {m for m in sys.modules if m.split(".")[0] in RUNTIMES_DE_MODELO}

    def proibido(*a, **k):
        raise AssertionError("execução externa ou conexão de rede proibida")

    # Só loopback passa: o laço de eventos do Windows liga um par de sockets locais; qualquer outro destino falha.
    local = ("127.0.0.1", "::1", "localhost")

    def so_local(original):
        def guarda(self_ou_host, destino=None, *a, **k):
            host = destino[0] if isinstance(destino, tuple) else destino
            if host not in local:
                proibido()
            return original(self_ou_host, destino, *a, **k)
        return guarda

    monkeypatch.setattr(socket.socket, "connect", so_local(socket.socket.connect))
    monkeypatch.setattr(socket.socket, "connect_ex", so_local(socket.socket.connect_ex))
    monkeypatch.setattr(socket, "create_connection", proibido)
    monkeypatch.setattr(socket, "getaddrinfo", proibido)
    for nome in ("run", "Popen", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, nome, proibido)
    monkeypatch.setattr(os, "system", proibido)
    for nome in dir(os):
        if nome.startswith(("exec", "spawn", "posix_spawn")):
            monkeypatch.setattr(os, nome, proibido)

    for adaptador in ("python", "mcp", "rest"):
        r = _chamar(ambiente, adaptador, id=did, parte="inteiro_teor", parte_idx=1, parte_tamanho=500)
        assert r["status"] == "encontrada" and r["particao"]["parte_idx"] == 1
    depois = {m for m in sys.modules if m.split(".")[0] in RUNTIMES_DE_MODELO}
    assert depois == antes
    assert svc.obter_decisao(did, parte="inteiro_teor", parte_idx=0)["status"] == "encontrada"
