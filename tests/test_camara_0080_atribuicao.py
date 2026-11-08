"""Decisão 0080 §7 (atribuição) e §8.4 (snapshot): campo aditivo por evidência Câmara, em todas as fachadas e caminhos.

Sintético por construção: acervo montado com as capturas reais intactas servidas por transporte simulado;
o termo usado na ativação é o corpo sintético de `tests/_camara_util.py`.
"""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from freoa_verifica.aliases import WorkKey
from freoa_verifica.connectors import camara_ativacao as ativ
from freoa_verifica.connectors.camara_atribuicao import CHAVES, FORMA_DE_CITACAO, FONTE, atribuicao, autoria_declarada
from freoa_verifica.connectors.camara_estado import Estado
from freoa_verifica.connectors.camara_policy import TERMO_URL
from freoa_verifica.service import Verifica
from freoa_verifica.verify import campos_evidencia_obra
from tests._camara_util import TERMO_HTML, portao
from tests.test_camara_legin import servidor  # noqa: F401

TERMO_SHA = hashlib.sha256(TERMO_HTML).hexdigest()
ART = "art. 289 da Lei 6404/1976"


def ativar_home(home: Path, tmp: Path):
    p, t, relogio, estado = portao(home, instrumento=True)
    pre = ativ.capturar(p, estado, relogio)
    revisao = tmp / "revisao.json"
    revisao.write_text(json.dumps({"auditor": "Auditor", "revisado_em": "2026-11-09",
                                   "termo_sha256": pre["termo_sha256"], "resultado": "conforme"}))
    ativ.registrar(estado, revisao, relogio)


@pytest.fixture
def acervo(tmp_path, servidor, monkeypatch):  # noqa: F811
    home = tmp_path / "home"
    ativar_home(home, tmp_path)
    svc = Verifica(home=home)
    monkeypatch.setattr(svc, "_offline", lambda: False)
    key = WorkKey("federal", "lei", "6404", 1976)
    atual = svc._capture_work(key)
    original = svc._capture_work(key, versao="publicacao_original")
    monkeypatch.setattr(svc, "_offline", lambda: True)
    svc.capturas = (atual, original)
    yield svc
    svc.close()


def esperada(autoria=None, sha=TERMO_SHA):
    return {"fonte": "Câmara dos Deputados", "autoria": autoria,
            "forma_de_citacao": "trecho entre aspas, com fonte e autoria quando houver", "termo_url": TERMO_URL,
            "termo_sha256": sha}


# --- função e contrato do campo ------------------------------------------------------------------------------------
def test_formato_exato_do_campo_e_autoria_nunca_fabricada(tmp_path):
    assert atribuicao(tmp_path) == esperada(sha=None)  # sem captura do termo: hash nulo, nunca inventado
    assert set(atribuicao(tmp_path)) == set(CHAVES) and FONTE == "Câmara dos Deputados"
    assert atribuicao(tmp_path, "Comissão X")["autoria"] == "Comissão X"
    assert atribuicao(tmp_path, "")["autoria"] is None
    assert FORMA_DE_CITACAO.startswith("trecho entre aspas")


@pytest.mark.parametrize("texto,autoria", [("Autoria: Poder Executivo\nArt. 1º", "Poder Executivo"),
                                           ("Autor: Fulano de Tal", "Fulano de Tal"),
                                           ("A autoria desta norma é do Congresso", None),
                                           ("Art. 1º Lei do autor", None), (None, None), ("", None)])
def test_autoria_so_se_o_proprio_documento_declara(texto, autoria):
    assert autoria_declarada(texto) == autoria


def test_atribuicao_carrega_o_hash_do_termo_da_ativacao(tmp_path):
    ativar_home(tmp_path / "h", tmp_path)
    assert atribuicao(tmp_path / "h")["termo_sha256"] == TERMO_SHA


def test_origem_preservada_em_respostas_compostas_com_varias_fontes(verifica_populada, acervo):
    svc_planalto, rw_planalto, _ = verifica_populada
    camara = acervo.capturas[0]
    campos_p = campos_evidencia_obra(rw_planalto, None)
    campos_c = acervo._evidencia_dispositivo(camara)
    assert "atribuicao" not in campos_p  # só a evidência de origem Câmara é atribuída
    assert campos_c["atribuicao"] == esperada()
    assert campos_p["capture_id"] != campos_c["capture_id"]


# --- fachadas e caminhos ---------------------------------------------------------------------------------------------
def test_python_obter_dispositivo_vigente_e_original_sem_alterar_o_texto(acervo):
    atual = acervo.obter_dispositivo(ART)
    original = acervo.obter_dispositivo(ART, versao="publicacao_original")
    assert atual["evidencia"]["atribuicao"] == esperada() == original["evidencia"]["atribuicao"]
    assert original["texto"].startswith("As publicações ordenadas pela presente Lei serão feitas no órgão oficial")
    assert '"' not in original["texto"][:5]  # o Verifica não insere aspas nem altera o texto
    assert atual["status"] == "unknown" and atual["texto"] is None  # semântica das guardas intacta


def test_python_verificar_citacao_e_historico(acervo):
    out = acervo.verificar_citacao("art. 1, caput da Lei 6404/1976", trecho="A companhia ou sociedade anônima",
                                   modo="normalizado", data="2025-01-01")
    evidencias = [e for d in ("identity", "text", "temporal", "support") for e in out[d]["evidence"]]
    camara = [e for e in evidencias if e.get("url", "").startswith("https://www2.camara.leg.br")]
    assert camara and all(e["atribuicao"] == esperada() for e in camara)
    assert out["text"]["status"] != "verified"  # a atribuição não promove nada: a guarda do modo normalizado vale
    sem_trecho = acervo.verificar_citacao("art. 1, caput da Lei 6404/1976")
    assert all(sem_trecho[d]["status"] != "verified" for d in ("identity", "text", "temporal", "support"))
    hist = acervo.historico_dispositivo(ART)
    achadas = []

    def varrer(no):
        if isinstance(no, dict):
            if "capture_id" in no and "sha256" in no and str(no.get("url", "")).startswith("https://www2.camara"):
                achadas.append(no)
            [varrer(v) for v in no.values()]
        elif isinstance(no, list):
            [varrer(v) for v in no]

    varrer(hist)
    assert achadas and all(e.get("atribuicao") == esperada() for e in achadas)


def test_obter_evidencia_por_captura_traz_a_atribuicao(acervo):
    for rw in acervo.capturas:
        out = acervo.obter_evidencia(rw.capture_id)
        assert out["status"] == "encontrada" and out["atribuicao"] == esperada()
        assert out["texto"]  # o texto vai sem alteração; a atribuição é campo irmão


def test_cache_e_reabertura_do_acervo_mantem_a_atribuicao(acervo, monkeypatch):
    primeiro = acervo.obter_dispositivo(ART, versao="publicacao_original")
    home = acervo.home
    acervo.close()
    monkeypatch.setenv("FV_OFFLINE", "1")
    reaberto = Verifica(home=home)
    try:
        de_novo = reaberto.obter_dispositivo(ART, versao="publicacao_original")
        assert de_novo["evidencia"]["atribuicao"] == primeiro["evidencia"]["atribuicao"] == esperada()
        assert de_novo["evidencia"]["captured_at"] == primeiro["evidencia"]["captured_at"]
        assert reaberto.obter_evidencia(acervo.capturas[0].capture_id)["atribuicao"] == esperada()
    finally:
        reaberto.close()


def test_mcp_e_rest_trazem_a_mesma_atribuicao(acervo, monkeypatch):
    pytest.importorskip("mcp")
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from freoa_verifica import mcp_server as ms
    from freoa_verifica.mcp_server import create_mcp
    from freoa_verifica.rest import create_app
    from tests.contrato import harness as h

    home = acervo.home
    monkeypatch.setenv("FV_HOME", str(home))
    monkeypatch.setenv("FV_OFFLINE", "1")
    monkeypatch.delenv("FV_API_TOKEN", raising=False)
    monkeypatch.setitem(ms._servicos, str(home), acervo)
    mcp = create_mcp(home=str(home))
    app = create_app(home=str(home), token=None)
    args = {"citacao": ART, "versao": "publicacao_original"}
    with TestClient(app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1") as rest:
        via_mcp = h.chamar_mcp(mcp, "obter_dispositivo", args)
        via_rest = h.chamar_rest(rest, "obter_dispositivo", args)
        evid = {"capture_id": acervo.capturas[1].capture_id}
        ev_mcp = h.chamar_mcp(mcp, "obter_evidencia", evid)
        ev_rest = h.chamar_rest(rest, "obter_evidencia", evid)
        ver_mcp = h.chamar_mcp(mcp, "verificar_citacao", {"citacao": "art. 1, caput da Lei 6404/1976",
                                                           "trecho": "A companhia ou sociedade anônima",
                                                           "modo": "normalizado", "data": "2025-01-01"})
        ver_rest = h.chamar_rest(rest, "verificar_citacao", {"citacao": "art. 1, caput da Lei 6404/1976",
                                                              "trecho": "A companhia ou sociedade anônima",
                                                              "modo": "normalizado", "data": "2025-01-01"})
    for resposta in (via_mcp, via_rest):
        assert resposta["evidencia"]["atribuicao"] == esperada()
    for resposta in (ev_mcp, ev_rest):
        assert resposta["atribuicao"] == esperada()
    for resposta in (ver_mcp, ver_rest):
        camara = [e for d in ("identity", "text", "temporal", "support") for e in resposta[d]["evidence"]
                  if str(e.get("url", "")).startswith("https://www2.camara")]
        assert camara and all(e["atribuicao"] == esperada() for e in camara)


def test_obra_de_origem_camara_montada_fora_do_servico_tambem_e_atribuida(acervo):
    rw = copy.copy(acervo.capturas[0])
    rw.atribuicao = None  # sem a do serviço: default pelo perfil/fonte, hash nulo se o home padrão não tiver termo
    campos = campos_evidencia_obra(rw, None)
    assert campos["atribuicao"]["fonte"] == "Câmara dos Deputados" and set(campos["atribuicao"]) == set(CHAVES)


def test_campos_pre_existentes_preservados_para_o_consumidor_freoa(acervo):
    out = acervo.obter_dispositivo(ART, versao="publicacao_original")["evidencia"]
    for campo in ("capture_id", "sha256", "url", "fetched_at", "captured_at", "source_kind", "natureza_texto",
                  "procedencia", "esfera", "acervo_ate"):
        assert campo in out
    consumidores = json.loads((Path(__file__).parent / "contrato" / "consumidores" / "freoa.json").read_text("utf-8"))
    assert consumidores  # o contrato do consumidor é verificado em tests/contrato; aqui só a aditividade


# --- §8.4: snapshot -----------------------------------------------------------------------------------------------------
def exportar(acervo, destino):
    out = acervo.snapshot_export(destino)
    assert out["status"] == "ok", out
    return destino


def test_snapshot_instala_offline_preserva_captured_at_e_a_atribuicao(acervo, tmp_path, monkeypatch, proibir_rede):
    antes = acervo.obter_dispositivo(ART, versao="publicacao_original")
    pasta = exportar(acervo, tmp_path / "snap")
    manifesto = json.loads((pasta / "MANIFEST.json").read_text("utf-8"))
    assert manifesto["camara_termo"] == {"termo_url": TERMO_URL, "termo_sha256": TERMO_SHA}
    monkeypatch.setenv("FV_OFFLINE", "1")
    novo = Verifica(home=tmp_path / "instalado")
    try:
        r = novo.snapshot_install(pasta, aceitar_nao_vinculado=True)
        assert r["status"] == "ok", r
        depois = novo.obter_dispositivo(ART, versao="publicacao_original")
        assert depois["texto"] == antes["texto"]
        assert depois["evidencia"]["captured_at"] == antes["evidencia"]["captured_at"]  # instalação não renova captura
        assert depois["evidencia"]["fetched_at"] == antes["evidencia"]["fetched_at"]
        assert depois["evidencia"]["sha256"] == antes["evidencia"]["sha256"]
        assert depois["evidencia"]["atribuicao"] == esperada()  # o hash do termo viaja no manifesto conferido
        assert depois["evidencia"]["atribuicao"]["termo_sha256"] == TERMO_SHA
        ev = novo.obter_evidencia(antes["evidencia"]["capture_id"])
        assert ev["atribuicao"] == esperada() and ev["metadados"]["fetched_at"] == antes["evidencia"]["fetched_at"]
        # instalar não ativa a rota nem qualifica: sem registro de ativação no home instalado
        from freoa_verifica.connectors.camara_ativacao import ativacao
        assert ativacao(Estado(novo.home)) is None and novo._get("camara_legin").health().probes[0].detail == \
            "ativacao_ao_vivo_pendente"
        matriz = json.loads((Path(__file__).resolve().parents[1] / "freoa_verifica" / "data" / "qualificacao.json").read_text("utf-8"))
        rotas = json.loads((Path(__file__).resolve().parents[1] / "freoa_verifica" / "data" / "qualificacao_rotas.json").read_text("utf-8"))
        assert {e["estado"] for e in matriz} == {"nao_apurada"} and '"aprovada"' not in json.dumps(rotas)
    finally:
        novo.close()


def test_snapshot_com_blob_adulterado_e_recusado(acervo, tmp_path, monkeypatch):
    pasta = exportar(acervo, tmp_path / "snap")
    blobs = [p for p in (pasta / "blobs").rglob("*") if p.is_file() and len(p.name) == 64]
    assert blobs
    alvo = blobs[0]
    alvo.write_bytes(alvo.read_bytes() + b" adulterado")
    monkeypatch.setenv("FV_OFFLINE", "1")
    novo = Verifica(home=tmp_path / "instalado")
    try:
        r = novo.snapshot_install(pasta, aceitar_nao_vinculado=True)
        assert r["status"] != "ok" and "sha256" in json.dumps(r)
        assert novo.obter_dispositivo(ART, versao="publicacao_original")["status"] != "encontrada"
    finally:
        novo.close()


def test_snapshot_com_manifesto_adulterado_e_recusado(acervo, tmp_path, monkeypatch):
    pasta = exportar(acervo, tmp_path / "snap")
    manifesto = json.loads((pasta / "MANIFEST.json").read_text("utf-8"))
    manifesto["camara_termo"]["termo_sha256"] = "0" * 64  # tentativa de trocar o termo declarado
    (pasta / "MANIFEST.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=2, sort_keys=True), "utf-8")
    monkeypatch.setenv("FV_OFFLINE", "1")
    novo = Verifica(home=tmp_path / "instalado")
    try:
        assert novo.snapshot_install(pasta, aceitar_nao_vinculado=True)["status"] != "ok"
        assert not (Path(novo.home) / "camara" / "termo-de-snapshot.json").exists()
    finally:
        novo.close()


def test_recibo_e_vinculo_da_captura_sao_recuperaveis_depois_da_instalacao(acervo, tmp_path, monkeypatch):
    pasta = exportar(acervo, tmp_path / "snap")
    monkeypatch.setenv("FV_OFFLINE", "1")
    novo = Verifica(home=tmp_path / "instalado")
    try:
        assert novo.snapshot_install(pasta, aceitar_nao_vinculado=True)["status"] == "ok"
        for rw in acervo.capturas:
            ev = novo.obter_evidencia(rw.capture_id)
            assert ev["metadados"]["sha256"] == rw.sha256 and ev["metadados"]["url"] == rw.url
        # recursos fora da gramática ficam inventariados como não obtidos (0077/0080)
        inv = novo.obter_dispositivo(ART, versao="publicacao_original")
        assert inv["evidencia"]["capture_id"]
    finally:
        novo.close()
