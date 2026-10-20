"""Instrumento de captura (FIX1): confinamento, manifesto transacional, registro completo e novos modos."""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

import pytest

from freoa_verifica import __version__, captura
from freoa_verifica.connectors import httputil, tjsp
from freoa_verifica.connectors.base import Unavailable, registry
from freoa_verifica.transport import Response
from tests.fixture_util import validar_inventario

CORPO = b'{"hits":{"value":1},"nota":"  corpo \xc3\xa9 intocado"}'
CONSULTA = {"query": "acordo de acionistas", "pagina": 1, "tamanho": 10}


def _resp(url, body=CORPO, status=200, mime="application/json"):
    return Response(
        url=url, final_url=url, status=status, headers={"content-type": mime, "date": "x"},
        body=body, sha256=hashlib.sha256(body).hexdigest(), fetched_at="2026-10-19T00:00:00+00:00",
        redirects=[], mime=mime, size=len(body),
    )


@pytest.fixture
def envios(monkeypatch):
    vistos = []

    def fake(url, **kw):
        vistos.append({"url": url, **kw})
        return _resp(url)

    monkeypatch.setattr(httputil, "transport_fetch", fake)
    monkeypatch.setattr(captura, "_raiz_repo", lambda: None)
    return vistos


def _fx(base: Path) -> Path:
    fx = base / "fx"
    fx.mkdir()
    (fx / "FIXTURES.json").write_bytes(b"{}\r\n")
    return fx


def _capturar(tmp_path, chave="tjdft_k", **kw):
    return captura.capturar("tjdft", CONSULTA, destino=tmp_path / "t", sonda=False, chave=chave, **kw)


# --- A03: validação antes da rede e confinamento ---------------------------------------------------


@pytest.mark.parametrize("chave", ["../x", "..\\x", "a/b", "A", "a.b", "", "a b", "../dev/wt/INT/sonda"])
@pytest.mark.parametrize("sonda", [True, False])
def test_chave_invalida_recusada_antes_da_rede(envios, tmp_path, chave, sonda):
    with pytest.raises(ValueError, match="chave inválida"):
        captura.capturar("tjdft", CONSULTA, destino=tmp_path / "d", sonda=sonda, chave=chave)
    assert envios == [] and not (tmp_path / "d").exists()


def test_registrar_fixture_chave_invalida(envios, tmp_path):
    reg = _capturar(tmp_path)
    with pytest.raises(ValueError, match="chave inválida"):
        captura.registrar_fixture(reg, "../fora", _fx(tmp_path))


def test_destino_igual_ou_dentro_do_repositorio_recusado_na_api(envios, tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "sub").mkdir(parents=True)
    monkeypatch.setattr(captura, "_raiz_repo", lambda: repo.resolve())
    for destino in (repo, repo / "sub", repo / "novo" / "fundo"):
        with pytest.raises(ValueError, match="fora do repositório"):
            captura.capturar("tjdft", CONSULTA, destino=destino, sonda=True, chave="s")
    assert envios == [] and not (repo / "novo").exists()
    captura.capturar("tjdft", CONSULTA, destino=tmp_path / "fora", sonda=True, chave="s")
    assert (tmp_path / "fora" / "s.json").is_file()


def test_caminho_final_fora_do_destino_recusado(tmp_path):
    for nome in ("../x.json", "sub/x.json", "..\\x.json"):
        with pytest.raises(ValueError, match="fora do destino"):
            captura._confinado(tmp_path, nome)
    assert captura._confinado(tmp_path, "ok.json") == tmp_path.resolve() / "ok.json"


# --- A04 / A08: manifesto válido e registro completo preservado ------------------------------------


def test_captura_simulada_gera_inventario_valido(envios, tmp_path):
    fx = _fx(tmp_path)
    reg = _capturar(tmp_path)
    captura.registrar_fixture(reg, "tjdft_k", fx)
    assert validar_inventario(fx) == []
    e = json.loads((fx / "FIXTURES.json").read_bytes())["tjdft_k"]
    assert e["origem_metadados"] == "captura_instrumento" and e["categoria"] == "captura_real"
    assert {"url_final", "capturado_em"} <= set(e) and not {"final_url", "fetched_at"} & set(e)
    assert (e["status"], e["content_type"]) == (200, "application/json")


def test_registro_completo_preservado_e_inventariado(envios, tmp_path):
    fx = _fx(tmp_path)
    reg = _capturar(tmp_path, user_agent="identificado")
    captura.registrar_fixture(reg, "tjdft_k", fx)
    manifesto = json.loads((fx / "FIXTURES.json").read_bytes())
    m = manifesto["tjdft_k__captura"]
    assert m["categoria"] == "metadados_captura" and m["descreve"] == "tjdft_k"
    registro = json.loads((fx / m["file"]).read_text(encoding="utf-8"))
    assert registro["parametros"]["query"] == "acordo de acionistas" and registro["metodo"] == "POST"
    assert registro["user_agent"] == captura.UA_IDENTIFICADO and registro["versao"] == __version__
    assert registro["cabecalhos"]["content-type"] == "application/json" and registro["sha256"] == reg.sha256
    assert validar_inventario(fx) == []


def test_inventario_exige_fixture_descrita(envios, tmp_path):
    fx = _fx(tmp_path)
    captura.registrar_fixture(_capturar(tmp_path), "tjdft_k", fx)
    dados = json.loads((fx / "FIXTURES.json").read_bytes())
    del dados["tjdft_k"]
    (fx / "FIXTURES.json").write_text(json.dumps(dados), encoding="utf-8")
    assert any("descreve fixture ausente" in p for p in validar_inventario(fx))


@pytest.mark.repositorio
def test_cli_modo_fixture_preserva_registro(envios, tmp_path, monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "capturar_fixture", Path(captura.__file__).resolve().parents[1] / "scripts" / "capturar_fixture.py"
    )
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    fx = _fx(tmp_path)
    monkeypatch.setattr(cli, "FIXTURES", fx)
    assert cli.main(["--conector", "tjdft", "--chave", "tjdft_c", "--consulta", json.dumps(CONSULTA)]) == 0
    assert (fx / "tjdft" / "tjdft_c.captura.json").is_file() and validar_inventario(fx) == []


# --- A05: transação recuperável e exclusão mútua ---------------------------------------------------


class _Queda(BaseException):
    """Simula queda do processo: não é `Exception`, logo nenhuma limpeza do registrar_fixture roda."""


@pytest.mark.parametrize("ponto,publicada", [
    ("temporarios", False), ("diario", False), ("manifesto", True), ("corpo_publicado", True),
])
def test_queda_entre_etapas_e_recuperavel(envios, tmp_path, monkeypatch, ponto, publicada):
    fx = _fx(tmp_path)
    reg = _capturar(tmp_path)

    def cai(nome):
        if nome == ponto:
            raise _Queda(nome)

    monkeypatch.setattr(captura, "_etapa", cai)
    with pytest.raises(_Queda):
        captura.registrar_fixture(reg, "tjdft_k", fx)
    monkeypatch.undo()  # volta o comportamento normal na "abertura seguinte"
    captura.recuperar_pendentes(fx)
    assert validar_inventario(fx) == []
    assert ("tjdft_k" in json.loads((fx / "FIXTURES.json").read_bytes())) is publicada
    assert (fx / "tjdft" / "tjdft_k.json").exists() is publicada
    assert not list(fx.rglob("*.tmp")) and not (fx / "FIXTURES.json.pendente").exists()
    captura.registrar_fixture(_capturar(tmp_path, "tjdft_k2"), "tjdft_k2", fx)  # o diretório segue utilizável
    assert validar_inventario(fx) == []


def test_excecao_antes_da_confirmacao_desfaz(envios, tmp_path, monkeypatch):
    fx = _fx(tmp_path)
    reg = _capturar(tmp_path)
    monkeypatch.setattr(captura, "_etapa", lambda n: (_ for _ in ()).throw(OSError(n)) if n == "diario" else None)
    with pytest.raises(OSError):
        captura.registrar_fixture(reg, "tjdft_k", fx)
    assert (fx / "FIXTURES.json").read_bytes() == b"{}\r\n"
    assert [p for p in fx.rglob("*") if p.is_file()] == [fx / "FIXTURES.json"]


def test_temporarios_orfaos_sao_removidos_na_abertura(tmp_path):
    fx = _fx(tmp_path)
    (fx / "tjdft").mkdir()
    orfao = fx / "tjdft" / "k.json.0123456789ab.tmp"
    orfao.write_bytes(b"x")
    (fx / "FIXTURES.json.0123456789ab.tmp").write_bytes(b"y")
    captura.recuperar_pendentes(fx)
    assert not list(fx.rglob("*.tmp")) and validar_inventario(fx) == []


def test_duas_capturas_concorrentes_preservam_as_duas_entradas(envios, tmp_path):
    fx = _fx(tmp_path)
    regs = {c: _capturar(tmp_path, c) for c in ("tjdft_a", "tjdft_b", "tjdft_c", "tjdft_d")}
    erros = []

    def publica(chave):
        try:
            captura.registrar_fixture(regs[chave], chave, fx)
        except BaseException as exc:  # noqa: BLE001
            erros.append(exc)

    fios = [threading.Thread(target=publica, args=(c,)) for c in regs]
    [f.start() for f in fios]
    [f.join(30) for f in fios]
    assert not erros
    dados = json.loads((fx / "FIXTURES.json").read_bytes())
    assert {k for k in dados if "__" not in k} == set(regs) and validar_inventario(fx) == []
    assert not (fx / "FIXTURES.json.lock").exists()


def test_bloqueio_espera_limitada_e_trava_velha_retomada(tmp_path):
    fx = _fx(tmp_path)
    with captura._bloqueio(fx):
        with pytest.raises(TimeoutError):
            with captura._bloqueio(fx, espera=0.1):
                pass
    assert not (fx / "FIXTURES.json.lock").exists()
    (fx / "FIXTURES.json.lock").write_text("morto", encoding="utf-8")
    with captura._bloqueio(fx, espera=1.0, velho=0.0):  # trava de uma queda é retomada
        pass


# --- A10: categoria e evidência estruturadas --------------------------------------------------------


def test_categoria_e_evidencia_copiadas_sem_inferir_do_motivo(monkeypatch, tmp_path):
    monkeypatch.setattr(captura, "_raiz_repo", lambda: None)
    ev = {"marcador": "transporte:Timeout", "url": "https://x"}

    def fake(url, **kw):
        raise Unavailable("transporte_Timeout", "fonte_fora", ev)

    monkeypatch.setattr(captura, "connector_fetch", fake)
    reg = captura.capturar("tjdft", CONSULTA, destino=tmp_path, sonda=True, chave="f")
    assert (reg.motivo, reg.categoria, reg.evidencia) == ("transporte_Timeout", "fonte_fora", ev)
    salvo = json.loads((tmp_path / "f.captura.json").read_text(encoding="utf-8"))
    assert salvo["categoria"] == "fonte_fora" and salvo["evidencia"] == ev


def test_motivo_sem_categoria_nao_inventa_categoria(monkeypatch, tmp_path):
    monkeypatch.setattr(captura, "_raiz_repo", lambda: None)
    monkeypatch.setattr(httputil, "transport_fetch", lambda u, **k: (_ for _ in ()).throw(ValueError("x")))
    reg = captura.capturar("tjdft", CONSULTA, destino=tmp_path, sonda=True, chave="f")
    assert reg.unavailable and reg.categoria is None and reg.evidencia == {}


# --- I1: GET simples em todos os conectores --------------------------------------------------------


def _url_base(cid):
    host, prefixos = next(iter(registry()[cid].path_prefixes.items()))
    return f"https://{host}{prefixos[0]}"


def _urls_permitidas():
    return [pytest.param(cid, _url_base(cid), id=cid) for cid in registry()]


@pytest.mark.parametrize("cid,url", _urls_permitidas())
def test_get_simples_usa_allowlist_limites_e_ua_do_conector(envios, tmp_path, cid, url):
    classe = registry()[cid]
    reg = captura.capturar(cid, url=url, destino=tmp_path, sonda=True, chave="g")
    assert not reg.unavailable and reg.metodo == "GET" and reg.parametros is None
    visto = envios[0]
    assert visto["url"] == url and visto["method"] == "GET" and visto["body"] is None
    assert visto["allowed_hosts"] == classe.hosts and visto["allowed_mimes"] == classe.mimes
    assert visto["allowed_path_prefixes"] == classe.path_prefixes
    assert visto["headers"] == httputil.ua_header(classe.user_agent)
    assert (tmp_path / "g.json").read_bytes() == CORPO


@pytest.mark.parametrize("url", [
    "https://exemplo.invalid/x", "http://esaj.tjsp.jus.br/cjsg/x", "https://esaj.tjsp.jus.br/outro/x",
    "https://esaj.tjsp.jus.br:8443/cjsg/x", "https://esaj.tjsp.jus.br/cjsg/../x", "https://esaj.tjsp.jus.br.evil/cjsg/",
    "https://esaj.tjsp.jus.br/robots.txt?x=1",
])
def test_url_fora_da_allowlist_recusada_antes_da_rede(envios, tmp_path, url):
    with pytest.raises(ValueError, match="fora da allowlist"):
        captura.capturar("tjsp", url=url, destino=tmp_path, sonda=True, chave="g")
    assert envios == []


def test_robots_txt_do_host_permitido(envios, tmp_path):
    captura.capturar("tjsp", url="https://esaj.tjsp.jus.br/robots.txt", destino=tmp_path, sonda=True, chave="r")
    visto = envios[0]
    assert visto["allowed_path_prefixes"] is None and "text/plain" in visto["allowed_mimes"]
    with pytest.raises(ValueError, match="fora da allowlist"):
        captura.capturar("tjsp", url="https://www.example.org/robots.txt", destino=tmp_path, sonda=True)


def test_escolha_entre_consulta_e_url(envios, tmp_path):
    for kw in ({}, {"consulta": CONSULTA, "url": "https://esaj.tjsp.jus.br/cjsg/"}):
        with pytest.raises(ValueError, match="exatamente uma"):
            captura.capturar("tjsp", destino=tmp_path, sonda=True, **kw)
    with pytest.raises(ValueError, match="só captura por url"):
        captura.capturar("stf", {"x": 1}, destino=tmp_path, sonda=True)
    with pytest.raises(ValueError, match="sem captura"):
        captura.capturar("inexistente", url="https://a/", destino=tmp_path, sonda=True)
    assert envios == []


def test_extensao_segue_o_mime(monkeypatch, tmp_path):
    monkeypatch.setattr(captura, "_raiz_repo", lambda: None)
    monkeypatch.setattr(httputil, "transport_fetch", lambda u, **k: _resp(u, b"%PDF-1.4", mime="application/pdf"))
    reg = captura.capturar("tjsp", url="https://esaj.tjsp.jus.br/cjsg/getArquivo.do", destino=tmp_path, sonda=True, chave="p")
    assert reg.arquivo == "p.pdf" and (tmp_path / "p.pdf").read_bytes() == b"%PDF-1.4"


# --- I2: consulta cjsg do TJSP pela função do conector ---------------------------------------------


class _SessaoComCookie(captura.Session):
    def has_cookie(self, name):
        return True


def test_consulta_tjsp_usa_o_construtor_do_conector(envios, tmp_path, monkeypatch):
    monkeypatch.setattr(captura, "Session", _SessaoComCookie)
    marcador = []
    orig = tjsp.build_cjsg_request

    def espia(q, **f):
        marcador.append((q, f))
        return orig(q, **f)

    monkeypatch.setattr(tjsp, "build_cjsg_request", espia)
    reg = captura.capturar(
        "tjsp", {"termo": "acordo de acionistas", "pagina": 2}, destino=tmp_path, sonda=True, chave="j"
    )
    assert marcador == [("acordo de acionistas", {"pagina": 2})]
    previa, pagina = envios
    esperado = orig("acordo de acionistas", pagina=2)
    assert previa["method"] == "POST" and previa["url"] == esperado.post_url
    assert previa["body"] == httputil.form_body(esperado.fields)
    assert pagina["method"] == "GET" and pagina["url"] == esperado.page_url == reg.url
    assert previa["session"] is pagina["session"] and previa["session"] is not None
    assert reg.parametros["formulario"] == esperado.fields and reg.parametros["consulta"]["pagina"] == 2
    # a busca do conector usa a mesma função
    marcador.clear()
    monkeypatch.setattr(tjsp, "Session", _SessaoComCookie)
    monkeypatch.setattr(tjsp, "_parse_results", lambda *a, **k: [])
    tjsp.TjspConnector().search("acordo de acionistas", pagina=2)
    assert marcador == [("acordo de acionistas", {"pagina": 2})]


def test_consulta_tjsp_sem_sessao_e_indisponivel(envios, tmp_path):
    reg = captura.capturar("tjsp", {"termo": "x"}, destino=tmp_path, sonda=True, chave="j")
    assert reg.unavailable and reg.motivo == "sessao_ausente"


@pytest.mark.parametrize("consulta", [{}, {"termo": " "}, {"termo": "x", "pagina": -1}, {"termo": "x", "pagina": 2001},
                                      {"termo": "x", "inventado": 1}])
def test_consulta_tjsp_invalida_antes_da_rede(envios, tmp_path, consulta):
    with pytest.raises(ValueError):
        captura.capturar("tjsp", consulta, destino=tmp_path, sonda=True, chave="j")
    assert envios == []


# --- I3: --user-agent vale para todos os modos -----------------------------------------------------


def test_user_agent_identificado_em_todos_os_modos(envios, tmp_path, monkeypatch):
    monkeypatch.setattr(captura, "Session", _SessaoComCookie)
    captura.capturar("tjdft", CONSULTA, destino=tmp_path, sonda=True, user_agent="identificado", chave="a")
    captura.capturar("tjsp", {"termo": "x"}, destino=tmp_path, sonda=True, user_agent="identificado", chave="b")
    captura.capturar("stf", url="https://portal.stf.jus.br/robots.txt", destino=tmp_path, sonda=True,
                     user_agent="identificado", chave="c")
    assert len(envios) == 4 and all(e["headers"]["User-Agent"] == captura.UA_IDENTIFICADO for e in envios)


def test_user_agent_do_conector_em_todos_os_modos(envios, tmp_path, monkeypatch):
    monkeypatch.setattr(captura, "Session", _SessaoComCookie)
    captura.capturar("tjsp", {"termo": "x"}, destino=tmp_path, sonda=True, chave="b")
    r = captura.capturar("datajud", url=_url_base("datajud"), destino=tmp_path, sonda=True, chave="d")
    assert r.user_agent == httputil.ua_header("identified")["User-Agent"]
    assert envios[0]["headers"]["User-Agent"] == httputil.ua_header("identified")["User-Agent"]
    assert envios[-1]["headers"]["User-Agent"] == r.user_agent
