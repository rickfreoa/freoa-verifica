"""F-C (1.0.3): C1 negativa, C3 histórico ausente, C4 recibo final, A5, A8."""
import json
from datetime import datetime, timezone

import pytest

from freoa_verifica.aliases import WorkKey
from freoa_verifica.parsers.model import Annotation, Issue, ParsedDocument, Provision, Redaction
from freoa_verifica.service import Verifica
from freoa_verifica.verify import ResolvedWork, pode_negar, verificar

KEY = WorkKey("federal", "lei", "6404", 1976)
NORM = "Lei 6.404/1976"
TEXTO = "O texto sintético do artigo cento e dezoito."
ATUAL = "Redação atual sintética do artigo cento e dezessete."


def _prov(path, text=TEXTO, annotations=()):
    return Provision(path, path, "", redactions=[Redaction(text, False, 0, list(annotations))])


def _doc(provisions=None, issues=()):
    provisions = [_prov("art118")] if provisions is None else provisions
    return ParsedDocument("synthetic", "1", NORM, None, "x", provisions=provisions, issues=list(issues))


@pytest.fixture
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    with Verifica(tmp_path / "home") as s:
        yield s


def _indexar(svc, doc):
    return svc.indexar_obra(source_id="planalto", work_key=KEY, document=doc, body=b"sintetico",
                            url="https://example.invalid/s", label=NORM,
                            fetched_at=datetime.now(timezone.utc).isoformat(), content_type="text/html")


def _nucleo(svc, citacao, **kw):
    return verificar(citacao, resolver=svc._resolver_adapter(), **kw)


TRUNCADO = Issue("TRUNCATED", None, "corte", "document")
QUARENTENA = Issue("OUTRO_BLOQUEIO", None, "x", "document")

# ---------------------------------------------------------------- C1: pode_negar e consumidores


def test_pode_negar_sem_captura_e_cobertura():
    assert pode_negar(None, "art1") == "COBERTURA"
    rw = ResolvedWork("w", KEY, _doc(), None, None, None, None, None, False)
    assert pode_negar(rw, "art999") == "COBERTURA"


@pytest.mark.parametrize("doc,motivo", [
    (_doc(issues=[TRUNCADO]), "ESTRUTURA_INCOMPLETA"),
    (_doc(issues=[QUARENTENA]), "DOCUMENTO_QUARENTENADO"),
    (_doc(provisions=[]), "DOCUMENTO_SEM_ESTRUTURA"),
    (_doc(provisions=[_prov("adct/art5")]), "DOCUMENTO_SEM_ESTRUTURA"),  # corpo sem dispositivo
])
def test_c1_verify_nucleo_nao_nega(svc, doc, motivo):
    _indexar(svc, doc)
    res = _nucleo(svc, f"art. 999 da {NORM}", trecho="qualquer")
    assert res.identity.status == "unknown" and res.identity.reason_code == motivo
    assert res.text.status != "not_found"


def test_c1_verify_ramo_quarentena_com_caminho_inexistente(svc):
    _indexar(svc, _doc(issues=[QUARENTENA]))
    res = _nucleo(svc, f"art. 999 da {NORM}")
    assert res.identity.status == "unknown"
    assert res.identity.reason_code == "DOCUMENTO_QUARENTENADO"


def test_c1_verify_ramo_sem_captura(svc):
    rw = ResolvedWork("w", KEY, _doc(), None, None, None, None, None, False)

    class R:
        def resolve(self, work):
            return rw

    res = verificar(f"art. 999 da {NORM}", resolver=R())
    assert res.identity.status == "unavailable" and res.identity.reason_code == "COBERTURA"


def test_c1_documento_truncado_nao_nega_outro_artigo_na_fachada(svc):
    _indexar(svc, _doc(issues=[TRUNCADO]))
    cit = f"art. 999 da {NORM}"
    assert svc.resolver_citacao(cit)["status"] != "inexistente"
    d = svc.obter_dispositivo(citacao=cit)
    assert d["status"] == "unknown" and d["reason_code"] == "ESTRUTURA_INCOMPLETA"
    assert svc.historico_dispositivo(cit)["status"] == "unknown"
    v = svc.verificar_citacao(cit)
    assert v["identity"]["status"] == "unknown"
    row, = svc.verificar_texto(f"Veja o {cit}.")["citacoes"]
    assert row["status"] != "inexistente"


def test_c1_pdf_sem_dispositivos_e_sem_estrutura(svc):
    _indexar(svc, _doc(provisions=[]))
    cit = f"art. 5 da {NORM}"
    assert svc.obter_dispositivo(citacao=cit)["reason_code"] == "DOCUMENTO_SEM_ESTRUTURA"
    assert svc.historico_dispositivo(cit)["reason_code"] == "DOCUMENTO_SEM_ESTRUTURA"
    assert svc.verificar_citacao(cit)["identity"]["reason_code"] == "DOCUMENTO_SEM_ESTRUTURA"


def test_c1_obra_ausente_do_acervo_offline_e_cobertura_nao_inexistente(svc):
    cit = f"art. 5 da {NORM}"
    assert svc.resolver_citacao(cit)["status"] == "indisponivel"
    assert svc.obter_dispositivo(citacao=cit) == {"status": "indisponivel", "motivo": "COBERTURA"}
    assert svc.historico_dispositivo(cit)["motivo"] == "COBERTURA"
    v = svc.verificar_citacao(cit)
    assert v["identity"] == {"status": "unavailable", "reason_code": "COBERTURA", "evidence": []}
    row, = svc.verificar_texto(f"Veja o {cit}.")["citacoes"]
    assert row["status"] == "indisponivel"


def test_c1_caput_usa_resolucao_canonica(svc):
    _indexar(svc, _doc())
    d = svc.obter_dispositivo(citacao=f"caput do art. 118 da {NORM}")
    assert d["status"] == "encontrada" and d["texto"]


# ---------------------------------------------------------------- controles positivos


def test_controle_positivo_dispositivo_existente_continua_verified(svc):
    _indexar(svc, _doc())
    v = svc.verificar_citacao(f"art. 118 da {NORM}", trecho=TEXTO)
    assert v["identity"]["status"] == "verified"
    assert v["text"]["status"] == "verified"
    assert svc.obter_dispositivo(citacao=f"art. 118 da {NORM}")["texto"] == TEXTO


def test_controle_positivo_dispositivo_ausente_de_obra_integra_continua_inexistente(svc):
    _indexar(svc, _doc())
    cit = f"art. 999 da {NORM}"
    res = _nucleo(svc, cit, trecho="qualquer")
    assert (res.identity.status, res.identity.reason_code) == ("not_found", "DISPOSITIVO_INEXISTENTE")
    assert svc.verificar_citacao(cit)["identity"]["status"] == "not_found"
    assert svc.obter_dispositivo(citacao=cit)["status"] == "inexistente"
    assert svc.historico_dispositivo(cit)["status"] == "inexistente"
    row, = svc.verificar_texto(f"Veja o {cit}.")["citacoes"]
    assert row["status"] == "inexistente"


# ---------------------------------------------------------------- C3 histórico ausente


def _doc_so_atual():
    ann = Annotation("redacao_dada", "(Redação dada pela Lei nº 14.195, de 2021)",
                     "Lei 14.195/2021", "2021-08-26")
    return _doc([_prov("art118", ATUAL, [ann])])


def test_a3_nucleo_nao_confronta_redacao_atual(svc):
    _indexar(svc, _doc_so_atual())
    res = _nucleo(svc, f"art. 118 da {NORM}", trecho=ATUAL, data="2000-01-01")
    assert res.text.status == "unknown" and res.text.reason_code == "HISTORICO_ANTERIOR_AUSENTE"


def test_a3_fachada(svc):
    _indexar(svc, _doc_so_atual())
    v = svc.verificar_citacao(f"art. 118 da {NORM}", trecho=ATUAL, data="2000-01-01")
    assert v["text"]["status"] == "unknown" and v["text"]["reason_code"] == "HISTORICO_ANTERIOR_AUSENTE"


def test_a3_obter_dispositivo_texto_nulo_e_texto_atual_rotulado(svc):
    _indexar(svc, _doc_so_atual())
    d = svc.obter_dispositivo(citacao=f"art. 118 da {NORM}", data="2000-01-01")
    assert d["texto"] is None
    assert d["texto_atual"]["texto"] == ATUAL and "atual" in d["texto_atual"]["rotulo"]
    assert d["redacoes_anteriores"] == []  # M1: a vigente não é anterior
    assert d["redacao_anterior_ausente_na_fonte"] is True
    assert svc.historico_dispositivo(f"art. 118 da {NORM}")["redacao_anterior_ausente_na_fonte"] is True


def test_m1_redacoes_anteriores_excluem_vigente(svc):
    velha = Redaction("texto antigo", True, 0)
    nova = Redaction(ATUAL, False, 1)
    _indexar(svc, _doc([Provision("art118", "art118", "", redactions=[velha, nova])]))
    d = svc.obter_dispositivo(citacao=f"art. 118 da {NORM}")
    assert [r["trecho"] for r in d["redacoes_anteriores"]] == ["texto antigo"]
    assert d["redacao_anterior_ausente_na_fonte"] is False


# ---------------------------------------------------------------- C4 / B3 recibo final


def _recibo(svc, run_id):
    row = svc.conn.execute("SELECT result_json FROM run WHERE id=?", (run_id,)).fetchone()
    return json.loads(row[0])


def _conclusoes(d):
    return {k: (d[k]["status"], d[k]["reason_code"]) for k in ("identity", "text", "temporal")}


def test_verifica_bloqueia_pertenca_privada(svc):
    _indexar(svc, _doc([_prov("art117", TEXTO)]))
    v = svc.verificar_citacao(f"{NORM}: art. 117 do contrato", trecho=TEXTO)
    for dim in ("identity", "text", "temporal"):
        assert v[dim]["status"] not in {"verified", "vigente_na_fonte"}
    assert v["identity"]["reason_code"] == "ASSOCIACAO_REQUER_CONFERENCIA"
    assert "conferencia" in v


@pytest.mark.parametrize("cenario", ["privada", "truncado", "historico", "positivo"])
def test_recibo_por_run_id_coincide_com_resposta(svc, cenario):
    if cenario == "truncado":
        _indexar(svc, _doc(issues=[TRUNCADO]))
    elif cenario == "historico":
        _indexar(svc, _doc_so_atual())
    else:
        _indexar(svc, _doc([_prov("art117", TEXTO), _prov("art118", TEXTO)]))
    citacao, trecho, data = {
        "privada": (f"{NORM}: art. 117 do contrato", TEXTO, None),
        "truncado": (f"art. 999 da {NORM}", "x", None),
        "historico": (f"art. 118 da {NORM}", ATUAL, "2000-01-01"),
        "positivo": (f"art. 118 da {NORM}", TEXTO, None),
    }[cenario]
    v = svc.verificar_citacao(citacao, trecho=trecho, data=data)
    assert v["run_id"]
    assert _conclusoes(_recibo(svc, v["run_id"])) == _conclusoes(v)
    assert svc.conn.execute("SELECT COUNT(*) FROM run").fetchone()[0] == 1  # um recibo só


def test_verificar_nucleo_sem_persistir_nao_grava(svc):
    _indexar(svc, _doc())
    verificar(f"art. 118 da {NORM}", resolver=svc._resolver_adapter(), repo=svc.conn, persistir=False)
    assert svc.conn.execute("SELECT COUNT(*) FROM run").fetchone()[0] == 0


# ---------------------------------------------------------------- A5 e A8


def test_a5_remissao_anaforica_listada_sem_herdar_obra(svc):
    _indexar(svc, _doc([_prov("art117"), _prov("art118")]))
    res = svc.verificar_texto(f"A {NORM}, art. 118, trata do tema. O art. 117 da mesma lei também.")
    assert [c["caminho"] for c in res["citacoes"]] == ["art118"]
    ref, = res["referencias_nao_resolvidas"]
    assert ref["status"] == "referencia_nao_resolvida"
    assert ref["citacao"].startswith("art. 117")


def test_a8_mais_de_200_citacoes_declara_truncamento(svc):
    _indexar(svc, _doc([_prov("art118")]))
    partes = [f"art. 118 da {NORM}" for _ in range(200)] + [f"art. 999 da {NORM}"]
    res = svc.verificar_texto(". ".join(partes) + ".")
    assert (res["total_detectado"], res["total_processado"], res["truncado"]) == (201, 200, True)
    assert len(res["citacoes"]) == 200  # a 201ª (com erro) não foi processada e isso está declarado


def test_a8_ate_200_citacoes_nao_trunca(svc):
    _indexar(svc, _doc())
    res = svc.verificar_texto(f"art. 118 da {NORM}.")
    assert (res["total_detectado"], res["total_processado"], res["truncado"]) == (1, 1, False)
