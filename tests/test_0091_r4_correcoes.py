"""0091, rodada 4 (achados 7, 13 e 16 da auditoria r3). Base: rascunho do Cursor, revisado pelo supervisor."""
from __future__ import annotations

import pytest

from freoa_verifica import revalidacao as rev
from freoa_verifica.aliases import WorkKey
from freoa_verifica.citation import extract, parse_one
from freoa_verifica.connectors import normas_leg as nl
from freoa_verifica.parsers.planalto import parse_planalto
from freoa_verifica.service import Verifica
from tests.test_0091_cf_entrega import KEY, T0, _ORFA, _html

CF88 = WorkKey("federal", "constituicao", "1988", 1988)
LEI = WorkKey("federal", "lei", "6404", 1976)
OUTRA = "urn:lex:br:federal:lei:1988;99999"
AUSENCIA = "(sem redação normativa na fonte)"


# ------------------------------------------------------------------ achado 7: todos os identificadores conferem


@pytest.mark.parametrize("meta", [
    {"urn": None, "legislationIdentifier": OUTRA},
    {"urn": None, "@id": OUTRA},
    {"legislationIdentifier": OUTRA},
    {"legislationIdentifier": "lixo"},
])
def test_r4_metadados_com_identificador_de_outra_obra_sao_recusados(meta):
    meta = {"encoding": [], **{k: (nl.urn_da_chave(LEI) if v is None else v) for k, v in meta.items()}}
    assert rev._validar_metadados_obra(meta, LEI) == "identidade_divergente"


def test_r4_metadados_coerentes_sao_aceitos():
    urn = nl.urn_da_chave(LEI)
    meta = {"encoding": [], "urn": urn, "legislationIdentifier": urn, "@id": "https://normas.leg.br/?urn=" + urn}
    assert rev._validar_metadados_obra(meta, LEI) is None


# ------------------------------------------------------------------ achado 13: complemento sintático


@pytest.mark.parametrize("texto", [
    "art. 5 da Constituição de 1988, e o contrato do Estado de São Paulo segue outra regra.",
    "art. 5 da Constituição de 1988.\nO contrato do Estado de Sao Paulo segue outra regra.",
    "art. 5 da Constituição de 1988; o Estado de São Paulo segue outra regra.",
    "art. 5 da Constituição de 1988 e o Estado de São Paulo segue outra regra.",
])
def test_r4_citacao_federal_sobrevive_a_qualificador_independente(texto):
    c = parse_one(texto)
    assert c is not None and c.work == CF88 and c.path == "art5"


def test_r4_citacao_federal_e_estadual_na_mesma_frase():
    assert [c for c in extract("art. 5 da Constituição de 1988 e art. 1 da Constituição Paulista") if c.work == CF88]


@pytest.mark.parametrize("texto", [
    "art. 5 da Constituição do Estado de São Paulo",
    "art. 5 da Constituição Paulista",
    "art. 5 da Constituição Estadual",
])
def test_r4_constituicao_estadual_continua_nao_federal(texto):
    c = parse_one(texto)
    assert c is None or c.work != CF88


# ------------------------------------------------------------------ achado 16: rótulo sem corpo


def _svc(tmp_path, alinea: str) -> Verifica:
    html = _html("<p>Art. 1 Cabe:</p><p>I - processar:</p><p>g) a extradição;</p>" + alinea
                 + "<p>i) o habeas corpus;</p><p>§ 1 Fim.</p>")
    url = "https://example.invalid/r4.htm"
    svc = Verifica(home=tmp_path)
    svc.indexar_obra(source_id="planalto", work_key=KEY, document=parse_planalto(html, base_url=url), body=html,
                     url=url, label="Lei 9.999/2000", fetched_at=T0, content_type="text/html; charset=utf-8")
    return svc


@pytest.mark.parametrize("alinea", ["<p>h)</p>", _ORFA.format("h)")])
def test_r4_alinea_so_com_rotulo_nao_e_vigente_nem_some_do_integral(tmp_path, alinea):
    svc = _svc(tmp_path, alinea)
    r = svc.obter_dispositivo(citacao="art. 1 da Lei 9.999/2000", caminho="art1.inc1.ali-h")
    assert not (r.get("texto") or "").strip()
    assert r["status"] == "unknown" and r["reason_code"] == "dispositivo_sem_redacao_normativa"
    assert r["vigencia"]["status"] != "vigente_na_fonte"
    integral = svc.obter_dispositivo(citacao="art. 1 da Lei 9.999/2000", abrangencia="integral")
    linhas = integral["texto_integral"].splitlines()
    assert any(linha.startswith("h)") and AUSENCIA in linha for linha in linhas)
    assert [linha[:2] for linha in linhas if linha[:2] in ("g)", "h)", "i)")] == ["g)", "h)", "i)"]
    v = svc.verificar_citacao("art. 1, I, h da Lei 9.999/2000", trecho="qualquer texto")
    assert v["text"]["status"] != "verified"


@pytest.mark.parametrize("alinea", ["<p>h) (Revogado pela Lei n. 1.)</p>", _ORFA.format("h) (Revogado pela Lei n. 1.)")])
def test_r4_alinea_revogada_continua_revogada(tmp_path, alinea):
    svc = _svc(tmp_path, alinea)
    r = svc.obter_dispositivo(citacao="art. 1 da Lei 9.999/2000", caminho="art1.inc1.ali-h")
    assert r["vigencia"]["status"] == "revogado" and r["status"] == "encontrada"
