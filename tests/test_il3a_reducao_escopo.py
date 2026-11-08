"""IL.3-a r3, redução de escopo das remissões (D5, `docs/auditoria/1.4.0/il3a-reducao-escopo.md`).

Invariante: nenhuma remissão sai com `resolvida: true` em `obter_dispositivo`, por Python, MCP e REST, nem nas recusas.
`texto` e `alvo` continuam (leitura mecânica não verificada). Os contraexemplos R3-1, R3-2, R3-3 e R3-6 do parecer r3
ficam como negativos do extrator: `xfail(strict=True)` enquanto o extrator ainda os resolve (ou omite) internamente. São a
BASE DA RETOMADA (nova trilha com gramática de expressões completas); quando um passar, o strict acusa e o marcador sai."""
from __future__ import annotations

import asyncio
import json

import pytest

from freoa_verifica import remissoes as rem
from freoa_verifica.aliases import WorkKey
from freoa_verifica.service import _final_da_fachada, _remissoes_no_texto_emitido
from tests.test_il3a_remissoes import svc6385  # noqa: F401  (fixture da fachada)

LSA = WorkKey("federal", "lei", "6404", 1976)
BASE_RETOMADA = pytest.mark.xfail(strict=True, reason="base da retomada (IL.3-a r3, D5): o extrator ainda resolve/omite")

R31 = [f"Art. 14. Ver art. 5 da {s}." for s in ("LC 101/2000", "MP 881/2019", "CF", "CPC", "CLT", "EC 45/2004", "LRF", "CTN")] \
    + [f"Conforme o {n}, aplica-se o art. 5." for n in (
        "código civil", "constituição federal", "código de processo civil", "estatuto da criança e do adolescente",
        "cpc", "cf", "clt", "lrf")]
R32 = ["art. 5 desta Lei (inciso I)", "art. 5 desta Lei (inc. I)", "art. 5 desta Lei, em seu inciso I",
       "art. 5 desta Lei, especialmente o inciso I", "art. 5 desta Lei, apenas inciso I",
       "art. 5 desta Lei, pertencente ao Anexo I", "art. 5 da Lei 8.987/1995 (inciso I)",
       "art. 5 da Lei 8.987/1995, em seu inciso I", "art. 5, inciso I (alínea a) desta Lei",
       "art. 5, § 1º (inciso I) desta Lei", "arts. 5 e 6 desta Lei, em seus incisos I e II",
       "arts. 5 e 6 desta Lei (incisos I e II)", "No Anexo I: ver art. 5 desta Lei",
       "No Anexo I: aplica-se o § 2º deste artigo", "art. 5 / inciso I desta Lei", "art. 5, nº 2, desta Lei",
       "art. 5, § 1º/2º desta Lei", "inc. I: do art. 5 desta Lei", "art. 5 desta Lei; inciso I"]
R32 = [f"Art. 14. Ver {t}." for t in R32]
R33 = [f"Art. 14. Ver art. 5, inciso {t} desta Lei." for t in ("IIII", "IIV", "VX", "IIIA", "IIIa", "III-BB")]
R36 = ["Ver Art. 5 desta Lei.", "Ver ART. 5 DESTA LEI."]


def _resolvidas(texto):
    return [r for r in rem.remissoes(texto, LSA, lambda w, p: True, "art14") if r["resolvida"]]


@BASE_RETOMADA
@pytest.mark.parametrize("texto", R31 + R32 + R33, ids=lambda t: t[:60])
def test_r3_1_a_3_extrator_nao_resolve_obra_ou_dispositivo_errado(texto):
    assert _resolvidas(texto) == []


@BASE_RETOMADA
@pytest.mark.parametrize("texto", R36)
def test_r3_6_extrator_reconhece_artigo_em_qualquer_caixa(texto):
    # a referência expressa simples não pode ser omitida (resolvida ou não): ao menos uma entrada
    assert rem.remissoes(texto, LSA, lambda w, p: True, "art14")


# --- a fachada nunca devolve `resolvida: true` ----------------------------------------------------------------------


def _todas_as_resolvidas(obj):
    """Percorre a resposta inteira: qualquer `resolvida` que não seja exatamente `False`."""
    achados = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "resolvida" and v is not False:
                achados.append(v)
            achados += _todas_as_resolvidas(v)
    elif isinstance(obj, list):
        for v in obj:
            achados += _todas_as_resolvidas(v)
    return achados


def test_python_nunca_devolve_resolvida_true_nem_nas_recusas(svc6385):  # noqa: F811
    svc, _ = svc6385
    citacao = "art. 9 da Lei 6.385/1976"
    sucesso = svc.obter_dispositivo(citacao=citacao)
    assert sucesso["status"] == "encontrada" and sucesso["remissoes"]  # `texto` e `alvo` preservados
    assert all(r["texto"] and r["alvo"]["caminho"] for r in sucesso["remissoes"])
    respostas = [sucesso,
                 svc.obter_dispositivo(citacao=citacao, versao="invalida"),
                 svc.obter_dispositivo(citacao=citacao, fonte="fonte_que_nao_existe"),
                 svc.obter_dispositivo(citacao="art. 9999 da Lei 6.385/1976"),
                 svc.obter_dispositivo(citacao=citacao, data="2001-01-01"),
                 svc.obter_dispositivo(citacao=citacao, versao="publicacao_original"),
                 svc.obter_dispositivo(citacao="lixo"), svc.obter_dispositivo()]
    for r in respostas:
        assert _todas_as_resolvidas(r) == [], r


def test_python_recusas_por_derivados_e_identidade_ambigua(svc6385, monkeypatch):  # noqa: F811
    import freoa_verifica.service as fachada
    from freoa_verifica.verify import SourceAmbiguous
    svc, _ = svc6385
    with monkeypatch.context() as m:
        m.setattr(fachada._derivados, "compativel", lambda conn: False)
        assert _todas_as_resolvidas(svc.obter_dispositivo(citacao="art. 9 da Lei 6.385/1976")) == []

    def ambigua(*a, **k):
        raise SourceAmbiguous([{"work_id": "a"}, {"work_id": "b"}])
    monkeypatch.setattr(svc, "_obter_dispositivo_autenticado", ambigua)
    assert _todas_as_resolvidas(svc.obter_dispositivo(citacao="art. 9 da Lei 6.385/1976")) == []


def test_rest_nunca_devolve_resolvida_true(svc6385, monkeypatch):  # noqa: F811
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from freoa_verifica.rest import create_app

    svc, _ = svc6385
    monkeypatch.delenv("FV_API_TOKEN", raising=False)
    app = create_app(home=str(svc.home), token=None)
    for cached in svc._resolver.works.values():
        app.state.verifica.registrar(cached)
    with TestClient(app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1") as c:
        respostas = [c.get("/v1/dispositivos", params=p) for p in (
            {"citacao": "art. 9 da Lei 6.385/1976"}, {"citacao": "art. 9 da Lei 6.385/1976", "versao": "invalida"},
            {"citacao": "art. 9999 da Lei 6.385/1976"}, {"citacao": "lixo"})]
    assert respostas[0].json()["remissoes"]
    for r in respostas:
        assert _todas_as_resolvidas(r.json()) == [], r.text


def test_mcp_nunca_devolve_resolvida_true(svc6385, monkeypatch):  # noqa: F811
    pytest.importorskip("mcp")
    from mcp import Client

    from freoa_verifica import mcp_server as ms

    svc, _ = svc6385
    monkeypatch.setenv("FV_HOME", str(svc.home))
    monkeypatch.setitem(ms._servicos, str(svc.home), svc)
    mcp = ms.create_mcp(home=str(svc.home))

    async def _run():
        saidas = []
        async with Client(mcp) as client:
            for args in ({"citacao": "art. 9 da Lei 6.385/1976"},
                         {"citacao": "art. 9 da Lei 6.385/1976", "versao": "invalida"},
                         {"citacao": "art. 9999 da Lei 6.385/1976"}, {"citacao": "lixo"}):
                r = await client.call_tool("obter_dispositivo", args)
                saidas.append(getattr(r, "structured_content", None) or json.loads(r.content[0].text))
        return saidas

    saidas = asyncio.run(_run())
    assert saidas[0]["remissoes"]
    for s in saidas:
        assert _todas_as_resolvidas(s) == [], s


def test_ponto_comum_forca_false_mesmo_quando_o_extrator_afirma_true():
    base = {"status": "encontrada", "texto": "Art. 1º Ver art. 2º desta Lei."}
    verdadeira = {"texto": "art. 2º desta Lei", "alvo": {"obra": "Lei 1/2000", "caminho": "art. 2º"}, "resolvida": True}
    for out in (_remissoes_no_texto_emitido({**base, "remissoes": [verdadeira]}),
                _final_da_fachada("obter_dispositivo", {**base, "remissoes": [verdadeira]})):
        assert out["remissoes"] == [{**verdadeira, "resolvida": False}]  # texto e alvo preservados
    assert verdadeira["resolvida"] is True  # a entrada de origem não é mutada


def test_extrator_continua_resolvendo_internamente_o_controle_positivo():
    # base da retomada: o extrator permanece no repositório; só a emissão está desativada
    assert [r["alvo"]["caminho"] for r in _resolvidas("Art. 14. Ver art. 5 desta Lei.")] == ["art. 5º"]
