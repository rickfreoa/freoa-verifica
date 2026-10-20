"""Captura reproduzível (E2): payload vem do build_*, escrita atômica, falha registrada, sem rede direta."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from freoa_verifica import __version__, captura
from freoa_verifica.connectors import httputil, tjdft
from freoa_verifica.transport import Response, Timeout

RAIZ = Path(__file__).resolve().parents[1]
CORPO = '{"hits":{"value":0},"registros":[],"nota":"  espaços   preservados é"}'.encode("utf-8")
CONSULTA = {"query": "acordo de acionistas", "pagina": 1, "tamanho": 10, "extras": {"sinonimos": True}}


def _resp(url, body=CORPO, status=200):
    return Response(
        url=url, final_url=url, status=status, headers={"content-type": "application/json", "date": "x"},
        body=body, sha256=hashlib.sha256(body).hexdigest(), fetched_at="2026-10-19T00:00:00+00:00",
        redirects=[], mime="application/json", size=len(body),
    )


@pytest.fixture(autouse=True)
def _fora_do_repositorio(monkeypatch):
    """O tmp_path do pytest fica dentro do checkout; a recusa do repositório é testada à parte."""
    monkeypatch.setattr(captura, "_raiz_repo", lambda: None)


@pytest.fixture
def envios(monkeypatch):
    vistos = []

    def fake(url, **kw):
        vistos.append({"url": url, **kw})
        return _resp(url)

    monkeypatch.setattr(httputil, "transport_fetch", fake)
    return vistos


def test_build_search_payload_extras_e_validacao():
    assert tjdft.build_search_payload("q", pagina=0, tamanho=5) == {"query": "q", "pagina": 0, "tamanho": 5}
    p = tjdft.build_search_payload("q", pagina=2, tamanho=5, extras={"espelho": True})
    assert p["espelho"] is True and p["pagina"] == 2
    with pytest.raises(ValueError):
        tjdft.build_search_payload("q", pagina=0, tamanho=5, extras={"query": "outra"})
    with pytest.raises(ValueError):
        tjdft.build_search_payload("q", pagina=0, tamanho=5, extras={"desconhecida": 1})


def test_payload_enviado_e_o_do_construtor(envios, tmp_path, monkeypatch):
    captura.capturar("tjdft", CONSULTA, destino=tmp_path, sonda=True, chave="a")
    corpo = json.loads(envios[0]["body"])
    assert corpo == tjdft.build_search_payload("acordo de acionistas", pagina=1, tamanho=10, extras={"sinonimos": True})
    assert envios[0]["url"] == tjdft.SEARCH_URL and envios[0]["method"] == "POST"
    # o construtor manda: alterá-lo muda a requisição
    orig = tjdft.build_search_payload
    monkeypatch.setattr(tjdft, "build_search_payload", lambda *a, **k: {**orig(*a, **k), "marcador": "mudou"})
    captura.capturar("tjdft", CONSULTA, destino=tmp_path, sonda=True, chave="b")
    assert json.loads(envios[1]["body"])["marcador"] == "mudou"


def test_search_usa_o_construtor(monkeypatch):
    vistos = []

    def fake(url, **kw):
        vistos.append(kw["body"])
        return _resp(url)

    monkeypatch.setattr(httputil, "transport_fetch", fake)
    tjdft.TjdftConnector().search("acordo de acionistas", base="acordaos", limite=7)
    assert json.loads(vistos[0]) == tjdft.build_search_payload(
        tjdft.consulta_oficial("acordo de acionistas"), pagina=0, tamanho=7,
        extras={"retornaInteiroTeor": True, "termosAcessorios": [{"campo": "base", "valor": "acordaos"}]},
    )


def test_registro_e_bytes_sem_reserializacao(envios, tmp_path):
    reg = captura.capturar("tjdft", CONSULTA, destino=tmp_path, sonda=True, chave="k")
    assert (tmp_path / "k.json").read_bytes() == CORPO
    meta = json.loads((tmp_path / "k.captura.json").read_text(encoding="utf-8"))
    assert meta["sha256"] == hashlib.sha256(CORPO).hexdigest() == reg.sha256
    assert meta["versao"] == __version__ and meta["metodo"] == "POST" and meta["status"] == 200
    assert meta["parametros"]["query"] == "acordo de acionistas" and meta["url_final"] == tjdft.SEARCH_URL
    assert meta["cabecalhos"]["content-type"] == "application/json" and meta["capturado_em"].endswith("+00:00")
    assert meta["user_agent"] == httputil.ua_header("identified")["User-Agent"]
    assert not list(tmp_path.glob("*.tmp"))


def test_user_agent_identificado_e_invalido(envios, tmp_path):
    reg = captura.capturar("tjdft", CONSULTA, destino=tmp_path, sonda=True, user_agent="identificado", chave="u")
    assert reg.user_agent == f"freoa-verifica/{__version__} (+https://github.com/rickfreoa/freoa-verifica)"
    assert envios[0]["headers"]["User-Agent"] == reg.user_agent
    with pytest.raises(ValueError):
        captura.capturar("tjdft", CONSULTA, destino=tmp_path, sonda=True, user_agent="outro")


@pytest.mark.parametrize("modo", ["excecao", "http"])
def test_falha_vira_unavailable_sem_arquivo_de_corpo(monkeypatch, tmp_path, modo):
    def fake(url, **kw):
        if modo == "excecao":
            raise Timeout("lento")
        return _resp(url, b"", status=503)

    monkeypatch.setattr(httputil, "transport_fetch", fake)
    reg = captura.capturar("tjdft", CONSULTA, destino=tmp_path, sonda=True, chave="f")
    assert reg.unavailable and reg.motivo and reg.categoria == "fonte_fora" and reg.evidencia
    assert not (tmp_path / "f.json").exists()
    assert json.loads((tmp_path / "f.captura.json").read_text(encoding="utf-8"))["unavailable"] is True


def _fixtures_falsas(tmp_path):
    (tmp_path / "FIXTURES.json").write_bytes(b'{\r\n "x": {"file": "x.json"}\r\n}\r\n')
    return tmp_path


def test_registrar_fixture_atomico(envios, tmp_path):
    fx = _fixtures_falsas(_mk(tmp_path, "fx"))
    reg = captura.capturar("tjdft", CONSULTA, destino=tmp_path / "t", sonda=False, chave="tjdft_x")
    captura.registrar_fixture(reg, "tjdft_x", fx)
    bruto = (fx / "FIXTURES.json").read_bytes()
    assert b"\r\n" in bruto and b"\n" not in bruto.replace(b"\r\n", b"")
    entrada = json.loads(bruto)["tjdft_x"]
    assert entrada["categoria"] == "captura_real" and entrada["file"] == "tjdft/tjdft_x.json"
    assert (fx / entrada["file"]).read_bytes() == CORPO
    assert entrada["sha256"] == hashlib.sha256(CORPO).hexdigest()
    with pytest.raises(ValueError):
        captura.registrar_fixture(reg, "tjdft_x", fx)  # chave repetida


def _mk(base, nome):
    p = base / nome
    p.mkdir()
    return p


def test_registrar_fixture_desfaz_bytes_se_manifesto_falha(envios, tmp_path, monkeypatch):
    fx = _fixtures_falsas(_mk(tmp_path, "fx"))
    reg = captura.capturar("tjdft", CONSULTA, destino=tmp_path / "t", sonda=False, chave="k")
    real = captura._atomico

    def falha_no_manifesto(path, data):
        if path.name == "FIXTURES.json":
            raise OSError("disco")
        real(path, data)

    monkeypatch.setattr(captura, "_atomico", falha_no_manifesto)
    antes = (fx / "FIXTURES.json").read_bytes()
    with pytest.raises(OSError):
        captura.registrar_fixture(reg, "tjdft_k", fx)
    assert not (fx / "tjdft" / "tjdft_k.json").exists()
    assert (fx / "FIXTURES.json").read_bytes() == antes


def test_registrar_fixture_recusa_indisponivel(monkeypatch, tmp_path):
    monkeypatch.setattr(httputil, "transport_fetch", lambda u, **k: (_ for _ in ()).throw(OSError("x")))
    reg = captura.capturar("tjdft", CONSULTA, destino=tmp_path / "t", sonda=True, chave="z")
    with pytest.raises(ValueError):
        captura.registrar_fixture(reg, "tjdft_z", _fixtures_falsas(_mk(tmp_path, "fx")))


@pytest.mark.repositorio
def test_cli_sonda_nao_toca_manifesto(envios, tmp_path, monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location("capturar_fixture", RAIZ / "scripts" / "capturar_fixture.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    manifesto = RAIZ / "tests" / "fixtures" / "FIXTURES.json"
    antes = manifesto.read_bytes()
    monkeypatch.setattr(cli, "REPO", tmp_path / "outro")  # tmp_path do pytest fica dentro do repositório
    rc =cli.main(["--conector", "tjdft", "--consulta", json.dumps(CONSULTA), "--sonda",
                   "--saida", str(tmp_path / "s"), "--chave", "s1"])
    assert rc == 0 and (tmp_path / "s" / "s1.json").read_bytes() == CORPO
    assert manifesto.read_bytes() == antes
    monkeypatch.setattr(cli, "REPO", RAIZ)
    with pytest.raises(SystemExit):  # sonda dentro do repositório é recusada
        cli.main(["--conector", "tjdft", "--consulta", "{}", "--sonda", "--saida", str(RAIZ / "tests" / "x")])


@pytest.mark.repositorio
@pytest.mark.parametrize("arquivo", ["freoa_verifica/captura.py", "scripts/capturar_fixture.py"])
def test_sem_importar_rede_direta(arquivo):
    proibidos = {"urllib", "http", "requests", "httpx", "socket"}
    arvore = ast.parse((RAIZ / arquivo).read_text(encoding="utf-8"))
    achados = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            achados |= {a.name.split(".")[0] for a in no.names}
        elif isinstance(no, ast.ImportFrom) and no.module:
            achados.add(no.module.split(".")[0])
    assert not achados & proibidos
