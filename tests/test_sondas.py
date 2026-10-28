"""Fontes-sonda (S0, plano 1.4.0): allowlist por fonte, recusas antes da rede, registro e isolamento do produto."""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from freoa_verifica import captura
from freoa_verifica.connectors import httputil
from freoa_verifica.connectors.base import CATEGORIAS_INDISPONIBILIDADE, Unavailable, registry
from freoa_verifica.identidade_http import USER_AGENT_IDENTIFICADO
from freoa_verifica.sondas import FONTES_SONDA, HOSTS_RECUSADOS, FonteSonda, prefixos_por_host
from freoa_verifica.transport import Response

IDS = (
    "tst", "stf_acordaos", "bnp", "djen", "cjf_unificada", "trf1", "trf2", "trf3",
    "tjac", "tjal", "tjam", "tjms", "tjrj", "tjmg", "tjrs", "tjpr",
)
CORPO = b'{"ok":true}'


def _resp(url, body=CORPO, status=200, mime="application/json"):
    return Response(
        url=url, final_url=url, status=status, headers={"content-type": mime, "date": "x"},
        body=body, sha256=hashlib.sha256(body).hexdigest(), fetched_at="2026-10-28T00:00:00+00:00",
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


def _urls_validas(fonte: FonteSonda):
    """Uma URL dentro do escopo por host: a raiz nos hosts sem prefixo, o primeiro prefixo nos demais."""
    for host in sorted(fonte.hosts):
        caminho = "/" if host in fonte.hosts_sem_prefixo else fonte.path_prefixes[0]
        yield f"https://{host}{caminho}"


def _cada_fonte_e_host():
    return [pytest.param(f.id, u, id=f"{f.id}:{u.split('/')[2]}") for f in FONTES_SONDA.values()
            for u in _urls_validas(f)]


# --- catálogo ---------------------------------------------------------------------------------------


def test_catalogo_tem_exatamente_os_ids_da_especificacao_e_e_imutavel():
    assert set(FONTES_SONDA) == set(IDS) and len(FONTES_SONDA) == len(IDS)
    with pytest.raises(TypeError):
        FONTES_SONDA["x"] = FONTES_SONDA["tst"]  # type: ignore[index]
    with pytest.raises(TypeError):
        HOSTS_RECUSADOS["x"] = "y"  # type: ignore[index]
    with pytest.raises(dataclasses.FrozenInstanceError):
        FONTES_SONDA["tst"].id = "outro"  # type: ignore[misc]
    for f in FONTES_SONDA.values():
        assert isinstance(f.hosts, frozenset) and isinstance(f.mimes, frozenset)
        assert isinstance(f.path_prefixes, tuple) and f.id in IDS and f.descricao and f.origem_hosts


def test_catalogo_sem_host_fora_de_dominio_oficial():
    for f in FONTES_SONDA.values():
        for host in f.hosts:
            assert host.endswith((".jus.br", ".gov.br")), (f.id, host)
            assert host == host.lower() and "/" not in host and ":" not in host


def test_cada_host_tem_origem_oficial_e_nenhum_recusado_entra():
    catalogados = {h for f in FONTES_SONDA.values() for h in f.hosts}
    assert not catalogados & set(HOSTS_RECUSADOS)
    assert all(motivo.strip() for motivo in HOSTS_RECUSADOS.values())
    for f in FONTES_SONDA.values():
        for host in f.hosts:
            assert f"{host}=https://" in f.origem_hosts, (f.id, host)
    assert not any("juridico" in h or "jusbrasil" in h for h in catalogados)


def test_escopo_de_caminho_consistente():
    for f in FONTES_SONDA.values():
        assert f.hosts_sem_prefixo <= f.hosts
        assert all(p.startswith("/") and p != "/" for p in f.path_prefixes)
        mapa = prefixos_por_host(f)
        if f.hosts_sem_prefixo == f.hosts:
            assert mapa is None
        else:
            assert set(mapa) == f.hosts - f.hosts_sem_prefixo
            assert all(v == f.path_prefixes and isinstance(v, tuple) for v in mapa.values())
    # só estas fontes admitem host inteiro; qualquer outra aparição exige revisão deliberada
    livres = {f.id: set(f.hosts_sem_prefixo) for f in FONTES_SONDA.values() if f.hosts_sem_prefixo}
    assert set(livres) == {"tst", "bnp", "cjf_unificada", "trf1", "trf2"}


def test_fonte_incoerente_e_recusada_na_construcao():
    base = dict(id="x", descricao="d", mimes=frozenset({"text/html"}))
    with pytest.raises(ValueError):
        FonteSonda(hosts=frozenset({"a.jus.br"}), path_prefixes=(), origem_hosts="a.jus.br=https://a.jus.br/", **base)
    with pytest.raises(ValueError):
        FonteSonda(hosts=frozenset({"a.jus.br"}), path_prefixes=("/",), origem_hosts="a.jus.br=https://a.jus.br/", **base)
    with pytest.raises(ValueError):
        FonteSonda(hosts=frozenset({"a.jus.br"}), path_prefixes=("/x/",), origem_hosts="", **base)


def test_registry_do_produto_nao_muda():
    assert not set(IDS) & set(registry())
    assert set(registry()) == {
        "bcb", "cvm_colegiado", "cvm_normas", "datajud", "planalto", "senado", "stf", "stj", "tcu", "tjdft", "tjsp",
    }


# --- allowlist por fonte ----------------------------------------------------------------------------


@pytest.mark.parametrize("fid,url", _cada_fonte_e_host())
def test_get_na_allowlist_da_fonte_usa_transporte_comum_e_ua_identificado(envios, tmp_path, fid, url):
    fonte = FONTES_SONDA[fid]
    reg = captura.capturar(None, url=url, destino=tmp_path, sonda=True, chave="s", fonte_sonda=fid,
                           user_agent="identificado")
    assert not reg.unavailable and reg.metodo == "GET" and reg.parametros is None
    visto = envios[0]
    assert visto["url"] == url and visto["method"] == "GET" and visto["body"] is None
    assert visto["allowed_hosts"] == fonte.hosts and visto["allowed_mimes"] == fonte.mimes
    assert visto["allowed_path_prefixes"] == prefixos_por_host(fonte)
    assert visto["headers"]["User-Agent"] == USER_AGENT_IDENTIFICADO
    assert "mozilla" not in visto["headers"]["User-Agent"].lower()
    salvo = json.loads((tmp_path / "s.captura.json").read_text(encoding="utf-8"))
    assert salvo["fonte_sonda"] == fid and salvo["conector"] is None and salvo["sonda"] is True
    assert salvo["user_agent"] == USER_AGENT_IDENTIFICADO and salvo["status"] == 200
    assert (tmp_path / "s.json").read_bytes() == CORPO


def test_modo_de_ua_conector_tambem_e_identificado(envios, tmp_path):
    url = next(_urls_validas(FONTES_SONDA["tjac"]))
    reg = captura.capturar(None, url=url, destino=tmp_path, sonda=True, chave="s", fonte_sonda="tjac")
    assert reg.user_agent == httputil.ua_header("identified")["User-Agent"] == envios[0]["headers"]["User-Agent"]
    assert "mozilla" not in reg.user_agent.lower()


@pytest.mark.parametrize("fid", sorted(IDS))
def test_url_fora_da_allowlist_recusada_antes_da_rede(envios, tmp_path, fid):
    fonte = FONTES_SONDA[fid]
    host = sorted(fonte.hosts)[0]
    outra = next(f for f in FONTES_SONDA.values() if not f.hosts & fonte.hosts)
    ruins = [
        f"https://{next(iter(outra.hosts))}/",  # host de outra fonte
        f"http://{host}/x",  # sem TLS
        f"https://{host}:8443/x",
        f"https://{host}.evil.example/x",
        f"https://{host}/../x",
        "https://exemplo.invalid/robots.txt",
        f"https://user@{host}/x",
    ]
    for h in sorted(fonte.hosts - fonte.hosts_sem_prefixo):  # fora do prefixo, onde há escopo de caminho
        ruins += [f"https://{h}/fora/do/escopo", f"https://{h}/", f"https://{h}/robots.txt?x=1"]
    for url in ruins:
        with pytest.raises(ValueError, match="fora da allowlist da fonte-sonda"):
            captura.capturar(None, url=url, destino=tmp_path, sonda=True, chave="s", fonte_sonda=fid)
    assert envios == [] and not any(tmp_path.iterdir())


@pytest.mark.parametrize("fid", sorted(IDS))
def test_robots_txt_de_cada_host_da_fonte(envios, tmp_path, fid):
    fonte = FONTES_SONDA[fid]
    for host in sorted(fonte.hosts):
        captura.capturar(None, url=f"https://{host}/robots.txt", destino=tmp_path, sonda=True, chave="r",
                         fonte_sonda=fid)
        visto = envios[-1]
        assert visto["allowed_path_prefixes"] is None and "text/plain" in visto["allowed_mimes"]
        assert visto["allowed_hosts"] == fonte.hosts


def test_host_de_um_conector_nao_vale_para_fonte_sonda_e_vice_versa(envios, tmp_path):
    with pytest.raises(ValueError, match="fora da allowlist"):
        captura.capturar(None, url="https://esaj.tjsp.jus.br/cjsg/", destino=tmp_path, sonda=True, fonte_sonda="tjac")
    with pytest.raises(ValueError, match="fora da allowlist"):
        captura.capturar("tjsp", url="https://esaj.tjac.jus.br/cjsg/", destino=tmp_path, sonda=True)
    assert envios == []


# --- recusas de uso ---------------------------------------------------------------------------------


def test_fonte_sonda_exige_sonda_url_e_alvo_unico(envios, tmp_path):
    url = next(_urls_validas(FONTES_SONDA["tjac"]))
    with pytest.raises(ValueError, match="exige sonda"):
        captura.capturar(None, url=url, destino=tmp_path, sonda=False, chave="s", fonte_sonda="tjac")
    with pytest.raises(ValueError, match="só captura por url"):
        captura.capturar(None, {"termo": "x"}, destino=tmp_path, sonda=True, fonte_sonda="tjac")
    with pytest.raises(ValueError, match="só captura por url"):
        captura.capturar(None, destino=tmp_path, sonda=True, fonte_sonda="tjac")
    with pytest.raises(ValueError, match="exatamente um"):
        captura.capturar("tjsp", url=url, destino=tmp_path, sonda=True, fonte_sonda="tjac")
    with pytest.raises(ValueError, match="exatamente um"):
        captura.capturar(None, url=url, destino=tmp_path, sonda=True)
    with pytest.raises(ValueError, match="desconhecida"):
        captura.capturar(None, url=url, destino=tmp_path, sonda=True, fonte_sonda="inexistente")
    with pytest.raises(ValueError, match="user_agent inválido"):
        captura.capturar(None, url=url, destino=tmp_path, sonda=True, fonte_sonda="tjac", user_agent="navegador")
    with pytest.raises(ValueError, match="chave inválida"):
        captura.capturar(None, url=url, destino=tmp_path, sonda=True, fonte_sonda="tjac", chave="../x")
    assert envios == [] and not any(tmp_path.iterdir())


def _cli():
    spec = importlib.util.spec_from_file_location(
        "capturar_fixture", Path(captura.__file__).resolve().parents[1] / "scripts" / "capturar_fixture.py"
    )
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    return cli


@pytest.mark.repositorio
def test_cli_recusa_antes_da_rede(envios, tmp_path, capsys):
    cli = _cli()
    url = next(_urls_validas(FONTES_SONDA["tjac"]))
    saida = str(tmp_path / "s")
    casos = [
        ["--fonte-sonda", "tjac", "--url", url, "--saida", saida],  # sem --sonda
        ["--fonte-sonda", "tjac", "--sonda", "--saida", saida, "--consulta", "{}"],  # sem --url
        ["--fonte-sonda", "tjac", "--conector", "tjsp", "--sonda", "--saida", saida, "--url", url],  # os dois
        ["--sonda", "--saida", saida, "--url", url],  # nenhum
        ["--fonte-sonda", "nao_existe", "--sonda", "--saida", saida, "--url", url],
        ["--fonte-sonda", "tjac", "--sonda", "--url", url],  # sem --saida
    ]
    for argv in casos:
        with pytest.raises(SystemExit) as exc:
            cli.main(argv)
        assert exc.value.code == 2, argv
    assert envios == [] and not (tmp_path / "s").exists()
    capsys.readouterr()


@pytest.mark.repositorio
def test_cli_url_fora_da_allowlist_sai_com_erro_sem_rede(envios, tmp_path, capsys):
    cli = _cli()
    rc = cli.main(["--fonte-sonda", "tjac", "--sonda", "--saida", str(tmp_path / "s"), "--chave", "x",
                   "--url", "https://esaj.tjsp.jus.br/cjsg/"])
    assert rc == 2 and envios == [] and "fora da allowlist" in capsys.readouterr().err


@pytest.mark.repositorio
def test_cli_grava_registro_da_sonda(envios, tmp_path):
    cli = _cli()
    url = next(_urls_validas(FONTES_SONDA["tjmg"]))
    assert cli.main(["--fonte-sonda", "tjmg", "--sonda", "--saida", str(tmp_path / "s"), "--chave", "k",
                     "--url", url, "--user-agent", "identificado"]) == 0
    salvo = json.loads((tmp_path / "s" / "k.captura.json").read_text(encoding="utf-8"))
    assert salvo["fonte_sonda"] == "tjmg" and salvo["conector"] is None and envios[0]["url"] == url


# --- indisponibilidade classificada -----------------------------------------------------------------


def test_desafio_recusa_e_resposta_inesperada_viram_unavailable_classificado(monkeypatch, tmp_path):
    monkeypatch.setattr(captura, "_raiz_repo", lambda: None)
    url = next(_urls_validas(FONTES_SONDA["tst"]))
    ev = {"status": 403, "marcador": "waf", "url": url}

    def fake(u, **kw):
        raise Unavailable("desafio_anti_robo", "ambiental_desafio", ev)

    monkeypatch.setattr(captura, "connector_fetch", fake)
    reg = captura.capturar(None, url=url, destino=tmp_path, sonda=True, chave="d", fonte_sonda="tst")
    assert reg.unavailable and reg.categoria == "ambiental_desafio" and reg.evidencia == ev
    salvo = json.loads((tmp_path / "d.captura.json").read_text(encoding="utf-8"))
    assert salvo["unavailable"] is True and salvo["categoria"] == "ambiental_desafio"
    assert salvo["fonte_sonda"] == "tst" and salvo["conector"] is None and salvo["arquivo"] is None
    assert not (tmp_path / "d.json").exists()


@pytest.mark.parametrize("status", [403, 429, 500, 503])
def test_status_nao_200_vira_unavailable_com_categoria_valida(monkeypatch, tmp_path, status):
    monkeypatch.setattr(captura, "_raiz_repo", lambda: None)
    monkeypatch.setattr(httputil, "transport_fetch", lambda u, **k: _resp(u, b"<html>x</html>", status, "text/html"))
    url = next(_urls_validas(FONTES_SONDA["djen"]))
    reg = captura.capturar(None, url=url, destino=tmp_path, sonda=True, chave="e", fonte_sonda="djen")
    assert reg.unavailable and reg.motivo
    assert reg.categoria is None or reg.categoria in CATEGORIAS_INDISPONIBILIDADE
    assert (tmp_path / "e.captura.json").is_file() and not (tmp_path / "e.html").exists()


def test_excecao_nao_prevista_do_transporte_nao_vira_zero_resultados(monkeypatch, tmp_path):
    monkeypatch.setattr(captura, "_raiz_repo", lambda: None)
    monkeypatch.setattr(httputil, "transport_fetch", lambda u, **k: (_ for _ in ()).throw(ValueError("x")))
    url = next(_urls_validas(FONTES_SONDA["trf3"]))
    reg = captura.capturar(None, url=url, destino=tmp_path, sonda=True, chave="f", fonte_sonda="trf3")
    assert reg.unavailable and reg.categoria is None and reg.evidencia == {} and reg.corpo is None


# --- registro fora do repositório -------------------------------------------------------------------


def test_registro_gravado_fora_do_repositorio_e_destino_no_repositorio_recusado(envios, tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "sub").mkdir(parents=True)
    monkeypatch.setattr(captura, "_raiz_repo", lambda: repo.resolve())
    url = next(_urls_validas(FONTES_SONDA["tjpr"]))
    for destino in (repo, repo / "sub", repo / "novo" / "fundo"):
        with pytest.raises(ValueError, match="fora do repositório"):
            captura.capturar(None, url=url, destino=destino, sonda=True, chave="s", fonte_sonda="tjpr")
    assert envios == [] and not (repo / "novo").exists()
    fora = tmp_path / "fora"
    reg = captura.capturar(None, url=url, destino=fora, sonda=True, chave="s", fonte_sonda="tjpr")
    assert (fora / "s.captura.json").is_file() and (fora / "s.json").is_file()
    assert repo not in (fora / "s.captura.json").resolve().parents and reg.sonda is True
    assert not list(repo.rglob("*"))[1:]  # nada além de repo/sub


@pytest.mark.repositorio
def test_cli_recusa_saida_dentro_do_repositorio(envios, tmp_path, capsys):
    cli = _cli()
    url = next(_urls_validas(FONTES_SONDA["tjpr"]))
    with pytest.raises(SystemExit) as exc:
        cli.main(["--fonte-sonda", "tjpr", "--sonda", "--saida", str(cli.REPO / "sondas_tmp"), "--url", url])
    assert exc.value.code == 2 and envios == [] and not (cli.REPO / "sondas_tmp").exists()
    capsys.readouterr()


def test_fixture_nao_aceita_fonte_sonda(envios, tmp_path):
    url = next(_urls_validas(FONTES_SONDA["tjac"]))
    with pytest.raises(ValueError, match="exige sonda"):
        captura.capturar(None, url=url, destino=tmp_path, sonda=False, chave="s", fonte_sonda="tjac")
    assert envios == []


# --- isolamento do produto (estrutural) -------------------------------------------------------------

RAIZ = Path(__file__).resolve().parents[1] / "freoa_verifica"


def _modulo_de(caminho: Path, raiz: Path = RAIZ) -> str:
    partes = list(caminho.relative_to(raiz.parent).with_suffix("").parts)
    if partes[-1] == "__init__":
        partes.pop()
    return ".".join(partes)


def _arquivo_de(modulo: str, raiz: Path = RAIZ) -> Path | None:
    base = raiz.parent.joinpath(*modulo.split("."))
    for cand in (base.with_suffix(".py"), base / "__init__.py"):
        if cand.is_file():
            return cand
    return None


def _importados(caminho: Path, raiz: Path = RAIZ) -> set[str]:
    """Módulos do pacote que o arquivo importa em qualquer ponto (topo, função, TYPE_CHECKING, relativo)."""
    pacote = _modulo_de(caminho, raiz).split(".")
    if caminho.name != "__init__.py":
        pacote = pacote[:-1]
    achados: set[str] = set()
    for no in ast.walk(ast.parse(caminho.read_text(encoding="utf-8-sig"))):
        if isinstance(no, ast.Import):
            alvos = [a.name for a in no.names]
        elif isinstance(no, ast.ImportFrom):
            base = no.module or ""
            if no.level:
                topo = pacote[: len(pacote) - (no.level - 1)]
                base = ".".join([*topo, *([base] if base else [])])
            alvos = [base] + [f"{base}.{a.name}" for a in no.names]
        else:
            continue
        for alvo in alvos:
            if alvo == "freoa_verifica" or alvo.startswith("freoa_verifica."):
                achados.add(alvo)
    return achados


def _fecho(inicio: str, raiz: Path = RAIZ) -> set[str]:
    visto: set[str] = set()
    fila = [inicio]
    while fila:
        mod = fila.pop()
        if mod in visto:
            continue
        arq = _arquivo_de(mod, raiz)
        if arq is None:
            continue  # nome de símbolo importado, não módulo
        visto.add(mod)
        partes = mod.split(".")
        fila.extend(".".join(partes[:i]) for i in range(1, len(partes)))  # pacotes pai executam __init__
        fila.extend(_importados(arq, raiz))
    return visto


@pytest.mark.repositorio
@pytest.mark.parametrize("entrada", ["freoa_verifica.service", "freoa_verifica.mcp_server", "freoa_verifica.cli"])
def test_sondas_e_captura_ausentes_do_grafo_de_import_do_produto(entrada):
    fecho = _fecho(entrada)
    assert entrada in fecho and "freoa_verifica.transport" in fecho  # o percurso funciona
    assert "freoa_verifica.sondas" not in fecho
    assert "freoa_verifica.captura" not in fecho


@pytest.mark.repositorio
def test_so_a_captura_importa_sondas_e_so_o_script_importa_a_captura():
    quem = {_modulo_de(p) for p in RAIZ.rglob("*.py") if "freoa_verifica.sondas" in _importados(p)}
    assert quem == {"freoa_verifica.captura"}
    importam_captura = {_modulo_de(p) for p in RAIZ.rglob("*.py") if "freoa_verifica.captura" in _importados(p)}
    assert importam_captura == set()
    assert "freoa_verifica.sondas" not in {m for p in RAIZ.joinpath("connectors").glob("*.py")
                                           for m in _importados(p)}


@pytest.mark.repositorio
def test_detector_de_fecho_acusa_importacao_indireta_e_relativa(tmp_path):
    pacote = tmp_path / "freoa_verifica"
    pacote.mkdir()
    (pacote / "__init__.py").write_text("", encoding="utf-8")
    (pacote / "a.py").write_text("def f():\n    from .b import x\n", encoding="utf-8")
    (pacote / "b.py").write_text("from freoa_verifica import sondas\n", encoding="utf-8")
    (pacote / "limpo.py").write_text("import os\n", encoding="utf-8")
    (pacote / "sondas.py").write_text("", encoding="utf-8")
    assert "freoa_verifica.sondas" in _fecho("freoa_verifica.a", pacote)
    assert "freoa_verifica.sondas" not in _fecho("freoa_verifica.limpo", pacote)


# --- roteiro executável -----------------------------------------------------------------------------

ROTEIRO = Path(__file__).resolve().parents[1] / "docs" / "S0-SONDAS.md"


@pytest.mark.repositorio
def test_toda_url_do_roteiro_esta_na_allowlist_da_fonte_e_toda_fonte_tem_comando():
    import re

    linhas = [ln for ln in ROTEIRO.read_text(encoding="utf-8").splitlines() if "--fonte-sonda" in ln and "--url" in ln]
    achados = []
    for ln in linhas:
        m = re.fullmatch(
            r'python scripts/capturar_fixture\.py --fonte-sonda (\w+) --sonda --saida C:/dev/fv14-sondas/(\w+) '
            r'--url "([^"]+)"', ln.strip(),
        )
        assert m, f"comando fora do formato exato: {ln}"
        fid, pasta, url = m.groups()
        assert fid == pasta and fid in FONTES_SONDA
        plano = captura._planejar_sonda(fid, None, url)  # levanta ValueError se a URL sair da allowlist
        assert plano["metodo"] == "GET" and plano["hosts"] == FONTES_SONDA[fid].hosts
        achados.append(fid)
    assert set(achados) == set(IDS)
    for fid in IDS:  # robots.txt, página de pesquisa e ao menos mais uma URL por fonte
        urls = [ln for ln in linhas if f"--fonte-sonda {fid} " in ln]
        assert len(urls) >= 2 and any("/robots.txt" in u for u in urls), fid
