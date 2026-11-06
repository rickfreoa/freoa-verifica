"""D5 F15/F16: matriz do parecer final, sem ampliar a segmentação ou o parser comum."""
from dataclasses import replace

import pytest

from freoa_verifica.aliases import WorkKey
from freoa_verifica.citation import parse_one
from freoa_verifica.parsers.camara_legin import parse_camara_legin
from freoa_verifica.parsers.paths import path_to_label
from freoa_verifica.service import Verifica
from freoa_verifica.verify import _caput_nao_representado, pode_negar
from tests.test_camara_legin import response, servidor


MOTIVO_PAR = "caput_refere_se_ao_artigo"
MOTIVO_INC = "inciso_do_caput_nao_resolvido"


def _motivo(path):
    # Caput abaixo de parágrafo é referência imprópria e prevalece (titular).
    antes = path.split(".caput")[0]
    if any(p.startswith("par") for p in antes.split(".")):
        return MOTIVO_PAR
    return MOTIVO_INC if ".caput.inc" in path else MOTIVO_PAR


def _assert_alternativas(out, path):
    if _motivo(path) == MOTIVO_PAR:
        parts = path.split(".")
        resto = parts[parts.index("caput") + 1:]
        assert out["alternativas"] == [".".join([parts[0], "caput", *resto]), path.replace(".caput", "")]


NORMAS = {
    "lei6404": (WorkKey("federal", "lei", "6404", 1976), "Lei 6404/1976"),
    "lc123": (WorkKey("federal", "lei_complementar", "123", 2006), "Lei Complementar 123/2006"),
    "lei13874": (WorkKey("federal", "lei", "13874", 2019), "Lei 13874/2019"),
}

# Transcrição literal expandida das tabelas F15 do parecer-pr36-final.md.
F15_VER = {
    "lei6404": "art30.par1 art57.par2 art66.par3 art67.parunico art68.par1 art68.par3 art72.par2 art82.par1 art88.par2 art117.par1 art123.parunico art126.par2 art130.par1 art154.par2 art157.par1 art168.par1 art171.par1 art171.par7 art178.par1 art178.par2 art246.par1 art247.parunico art249.parunico art269.parunico art277.par1 art295.par1",
    "lc123": "art5.parunico art7.parunico art30.par1 art30.par3 art85-A.par2",
    "lei13874": "art1.par5",
}
F15_HIST = {
    "lei6404": "art30.par1 art41.par3 art55.par2 art55.par3 art57.par2 art66.par3 art67.parunico art68.par1 art68.par3 art72.par2 art82.par1 art88.par2 art110-A.par1 art110-A.par7 art110-A.par8 art110-A.par11 art110-A.par12 art110-A.par13 art117.par1 art123.parunico art126.par2 art130.par1 art133.par6 art136-A.par2 art146.par2 art154.par2 art157.par1 art161.par4 art168.par1 art171.par1 art171.par7 art176.par5 art177.par2 art178.par1 art178.par2 art182.par1 art187.par1 art197.par1 art246.par1 art247.parunico art249.parunico art269.parunico art277.par1 art294-B.par1 art294-B.par2 art295.par1",
    "lc123": "art2.par9 art3.par4 art4.par1 art4.par4 art5.parunico art7.parunico art8.par1 art9.par1 art13.par1 art13.par6 art16.par1-A art16.par1-B art17.par1 art18.par1 art18.par1-B art18.par4 art18.par4-A art18.par5 art18.par5-B art18.par5-C art18.par5-M art18.par14 art18.par15-A art18.par20-A art18.par22-B art18-A.par1 art18-A.par3 art18-A.par4 art18-A.par5 art18-A.par7 art18-A.par13 art18-A.par17 art18-C.par1 art18-C.par3 art21.par4 art21.par24 art23.par4 art26.par1 art26.par4-A art26.par6 art29.par6 art29.par9 art30.par1 art30.par3 art38.par2 art38-A.par3 art38-B.parunico art41.par4 art41.par5 art56.par2 art56.par5 art61-A.par4 art61-A.par6 art65.par4 art65-A.par4 art85-A.par2",
    "lei13874": "art1.par5 art3.par1 art3.par3 art3.par6 art4-A.par1 art4-A.par4",
}
F16_PREFIXOS = {
    "lei6404": "art16 art24 art40 art49 art57 art64 art79 art80 art84 art86 art95 art100 art107 art109 art126 art132 art133 art155 art158 art163 art166 art176 art178.par1 art178.par2 art184 art186 art194 art200 art206 art209 art210 art219 art224 art225 art250 art253 art256 art258 art269 art271 art287 art297 art298",
    "lc123": "art5.parunico art7.parunico art10 art30 art30.par1 art30.par3 art45 art51 art64 art73 art85-A.par2",
    "lei13874": "art1.par5 art2 art4 art18",
}


def _matriz():
    casos = []
    for norma in NORMAS:
        for grupo, tabela in (("F15-ver", F15_VER), ("F15-hist", F15_HIST)):
            casos.extend((grupo, norma, p + ".caput") for p in tabela[norma].split())
        resp = response("textos_atualizado_" + norma)
        doc = parse_camara_legin(resp.body.decode("utf-8"), base_url=resp.final_url)
        # Regra explícita de F16: todos os caminhos .inc existentes e descendentes,
        # salvo .caput terminal; a seleção de verificação usa os prefixos do auditor.
        paths = sorted({p.path for p in doc.provisions if ".inc" in p.path and not p.path.endswith(".caput")})
        for path in paths:
            prefixo, resto = path.split(".inc", 1)
            alvo = prefixo + ".caput.inc" + resto
            casos.append(("F16-hist", norma, alvo))
            if prefixo in F16_PREFIXOS[norma].split():
                casos.append(("F16-ver", norma, alvo))
    return casos


CASOS = _matriz()


def _citacao(norma, path):
    return path_to_label(path) + " da " + NORMAS[norma][1]


@pytest.fixture(scope="module")
def acervo_red(tmp_path_factory):
    # Replay dos corpos/recibos reais existentes; não gera nem altera fixtures.
    with pytest.MonkeyPatch.context() as mp:
        servidor.__wrapped__(mp, None)
        svc = Verifica(home=tmp_path_factory.mktemp("caput-red") / "home")
        mp.setattr(svc, "_offline", lambda: False)
        for key, _ in NORMAS.values():
            svc._capture_work(key)
        mp.setattr(svc, "_offline", lambda: True)
        yield svc
        svc.close()


@pytest.fixture(scope="module", params=["python", "mcp", "rest"])
def fachada(request, acervo_red):
    from tests.contrato import harness

    if request.param == "python":
        yield lambda method, args: getattr(acervo_red, method)(**args)
    elif request.param == "mcp":
        from freoa_verifica import mcp_server as ms
        with pytest.MonkeyPatch.context() as mp:
            mp.setitem(ms._servicos, str(acervo_red.home), acervo_red)
            mcp = ms.create_mcp(home=str(acervo_red.home))
            yield lambda method, args: harness.chamar_mcp(mcp, method, args)
    else:
        from fastapi.testclient import TestClient
        from freoa_verifica.rest import create_app
        with TestClient(create_app(home=str(acervo_red.home), token=None),
                        client=("127.0.0.1", 50000), base_url="http://127.0.0.1") as client:
            yield lambda method, args: harness.chamar_rest(client, method, args)


def test_inventario_do_parecer():
    esperados = {
        "F15-ver": [26, 5, 1], "F15-hist": [46, 56, 6],
        "F16-ver": [227, 49, 17], "F16-hist": [452, 450, 88],
    }
    for grupo, contagens in esperados.items():
        assert [sum(g == grupo and n == norma for g, n, _ in CASOS) for norma in NORMAS] == contagens
    assert len(CASOS) == 32 + 108 + 293 + 990


def _assert_verificacao(out, path):
    assert out["citation"]["path"] == path
    for dim in ("identity", "text"):
        assert out[dim]["status"] == "unknown", out
        assert out[dim]["reason_code"] == _motivo(path), out
    assert out["temporal"]["status"] != "verified", out
    assert out["fundamento_temporal"] is None
    _assert_alternativas(out, path)


@pytest.mark.parametrize("grupo,norma,path", CASOS, ids=["-".join(c) for c in CASOS])
def test_reducao_todas_ocorrencias(fachada, grupo, norma, path, proibir_rede):
    cite = _citacao(norma, path)
    assert parse_one(cite).path == path  # caminho público, sem _path ou normalização artificial
    if grupo.endswith("ver"):
        for trecho in (None, "Nessa proibição não se compreendem:"):
            out = fachada("verificar_citacao", {"citacao": cite, "trecho": trecho})
            _assert_verificacao(out, path)
        out = fachada("verificar_texto", {"texto": cite + ', "Texto para confronto".'})
        assert len(out["citacoes"]) == 1
        item = out["citacoes"][0]
        assert item["status"] == "indisponivel"
        _assert_verificacao(item["verificacao"], path)
    else:
        out = fachada("historico_dispositivo", {"citacao": cite})
        assert out["status"] == "unknown", out
        assert out["reason_code"] == _motivo(path)
        _assert_alternativas(out, path)
        assert out["linha_do_tempo"] == []
        assert out["fundamento_temporal"] is None
    out = fachada("obter_dispositivo", {"citacao": cite})
    assert out["status"] == "unknown", out
    assert out["reason_code"] == _motivo(path)
    assert out["texto"] is None
    _assert_alternativas(out, path)
    assert not proibir_rede


def test_caput_representado_e_outras_fontes(fachada, acervo_red, proibir_rede):
    cite = "art. 1, caput da Lei 6404/1976"
    out = fachada("verificar_citacao", {"citacao": cite})
    assert out["identity"]["status"] == "verified"
    assert out["text"]["reason_code"] == "SEM_TRECHO"
    out = fachada("obter_dispositivo", {"citacao": cite})
    assert out["status"] == "encontrada"
    assert "A companhia ou sociedade anônima" in out["texto"]
    out = fachada("historico_dispositivo", {"citacao": cite})
    assert out["reason_code"] == "inicio_redacao_atual_nao_documentado"
    rw = acervo_red._resolve(NORMAS["lei6404"][0])
    for source in ("planalto", "senado_norma", None):
        other = replace(rw, source_id=source)
        for path in ("art16.caput.inc1", "art30.par1.caput"):
            assert _caput_nao_representado(other, path) is None
            assert pode_negar(other, path) is None


def test_caput_improprio_mesmo_se_materializado(acervo_red):
    from freoa_verifica.parsers.model import ParsedDocument, Provision, Redaction

    rw = acervo_red._resolve(NORMAS["lei6404"][0])
    path = "art30.par1.caput"
    doc = ParsedDocument("camara_atualizado", "antigo", "", None, "", provisions=[
        Provision(path, "rótulo impróprio", "", redactions=[
            Redaction("Nessa proibição não se compreendem:", False, 0)]),
    ])
    assert _caput_nao_representado(replace(rw, document=doc), path) == MOTIVO_PAR
    assert pode_negar(replace(rw, document=doc), path) == MOTIVO_PAR


def test_guarda_precede_construcao_historica(acervo_red, monkeypatch, proibir_rede):
    def proibido(*args, **kwargs):
        pytest.fail("recorte indisponível não pode construir histórico")

    monkeypatch.setattr(acervo_red, "_material_historico_camara", proibido)
    monkeypatch.setattr("freoa_verifica.temporal.build_intervals", proibido)
    for path in ("art30.par1.caput", "art16.caput.inc1"):
        cite = _citacao("lei6404", path)
        _assert_verificacao(acervo_red.verificar_citacao(cite, data="2025-01-01"), path)
        assert acervo_red.obter_dispositivo(cite, data="2025-01-01")["reason_code"] == _motivo(path)
        assert acervo_red.historico_dispositivo(cite)["reason_code"] == _motivo(path)


@pytest.mark.parametrize("path", ["art30.par1.caput", "art16.caput.inc1"])
def test_obtencao_por_work_id(fachada, acervo_red, path, proibir_rede):
    rw = acervo_red._resolve(NORMAS["lei6404"][0])
    out = fachada("obter_dispositivo", {"work_id": rw.work_id, "caminho": path})
    assert out["status"] == "unknown"
    assert out["reason_code"] == _motivo(path)
    assert out["texto"] is None
    _assert_alternativas(out, path)
    assert not proibir_rede


@pytest.mark.parametrize("cite", [
    "inciso I do caput do art. 16 da Lei 6404/1976",
    "art. 16, caput, inciso I da Lei 6404/1976",
    "art. 30, § 1, caput da Lei 6404/1976",
])
def test_formas_publicas_e_resolucao(fachada, cite, proibir_rede):
    path = parse_one(cite).path
    out = fachada("resolver_citacao", {"citacao": cite})
    assert out["status"] == "unknown"
    assert out["motivo"] == _motivo(path)
    _assert_alternativas(out, path)
    _assert_verificacao(fachada("verificar_citacao", {"citacao": cite}), path)
