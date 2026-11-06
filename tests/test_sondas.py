"""Fontes-sonda (S0, plano 1.4.0): allowlist por fonte, recusas antes da rede, registro e isolamento do produto."""

from __future__ import annotations

import ast
import contextlib
import dataclasses
import hashlib
import importlib.util
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from freoa_verifica import captura
from freoa_verifica.connectors import httputil
from freoa_verifica.connectors.base import CATEGORIAS_INDISPONIBILIDADE, Unavailable, registry
from freoa_verifica.identidade_http import USER_AGENT_IDENTIFICADO
from freoa_verifica.sondas import (
    FONTES_BARRADAS, FONTES_SONDA, HOSTS_RECUSADOS, SEGMENTOS_PROIBIDOS, FonteSonda, prefixos_por_host,
)
from freoa_verifica.transport import Response
from tests.test_transport import _fast_guards, _wire_local

IDS = (
    "tst", "stf_acordaos", "bnp", "djen", "cjf_unificada", "trf1", "trf2", "trf3",
    "tjac", "tjal", "tjam", "tjms", "tjrj", "tjmg", "tjrs", "tjpr",
    "lexml", "normas_leg", "camara_legislacao",
)
IDS_IL2 = ("lexml", "normas_leg", "camara_legislacao")
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
    """Uma URL dentro do escopo por host: a primeira rota documentada, ou o robots.txt se o host só admite ele."""
    for host in sorted(fonte.hosts):
        yield f"https://{host}{(fonte.rotas[host] or ('/robots.txt',))[0]}"


def _liberado(fonte: FonteSonda, url: str) -> bool:
    """Host B só vai à rede com a confirmação do titular; o teste a dá, para exercitar a allowlist."""
    return url.split("/")[2] in fonte.hosts_b


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
        assert f.confirmacao in ('A', 'B') and f.id in IDS and f.descricao and f.origem_hosts


# `.leg.br` só nos hosts exatos do IL.2 (lista fixa aqui, independente do catálogo); as 16 fontes anteriores seguem
# restritas a .jus.br e .gov.br.
HOSTS_LEG_BR_IL2 = frozenset({"normas.leg.br", "www.camara.leg.br", "www2.camara.leg.br"})


def _dominio_oficial(fid: str, host: str) -> bool:
    if host.endswith((".jus.br", ".gov.br")):
        return True
    return fid in IDS_IL2 and host in HOSTS_LEG_BR_IL2


def test_catalogo_sem_host_fora_de_dominio_oficial():
    for f in FONTES_SONDA.values():
        for host in f.hosts:
            assert _dominio_oficial(f.id, host), (f.id, host)
            assert host == host.lower() and "/" not in host and ":" not in host


def test_dominio_leg_br_so_nos_hosts_exatos_do_il2_e_mutantes_sao_pegos():
    antigas = [i for i in IDS if i not in IDS_IL2]
    assert len(antigas) == 16
    for fid in antigas:  # nenhuma fonte antiga tem host .leg.br
        assert not any(h.endswith(".leg.br") for h in FONTES_SONDA[fid].hosts), fid
    assert {h for fid in IDS_IL2 for h in FONTES_SONDA[fid].hosts if h.endswith(".leg.br")} == HOSTS_LEG_BR_IL2
    # mutantes: .leg.br em fonte antiga (o do auditor: auditoria.leg.br no TST) e host .leg.br fora da lista no IL.2
    assert not _dominio_oficial("tst", "auditoria.leg.br")
    assert not any(_dominio_oficial(fid, "auditoria.leg.br") for fid in IDS)
    assert not _dominio_oficial("senado_legislacao", "auditoria.leg.br")
    assert not _dominio_oficial("tst", "legis.senado.leg.br")  # nem o host do IL.2 vale para fonte antiga
    mutante = dataclasses.replace(
        FONTES_SONDA["tst"], hosts=FONTES_SONDA["tst"].hosts | {"auditoria.leg.br"},
        rotas={**FONTES_SONDA["tst"].rotas, "auditoria.leg.br": ()},
        origem_hosts=FONTES_SONDA["tst"].origem_hosts + "; auditoria.leg.br=https://auditoria.leg.br/",
    )
    assert not all(_dominio_oficial(mutante.id, h) for h in mutante.hosts)


def test_cada_host_tem_origem_oficial_e_nenhum_recusado_entra():
    catalogados = {h for f in FONTES_SONDA.values() for h in f.hosts}
    assert not catalogados & set(HOSTS_RECUSADOS)
    assert all(motivo.strip() for motivo in HOSTS_RECUSADOS.values())
    for f in FONTES_SONDA.values():
        for host in f.hosts:
            assert f"{host}=https://" in f.origem_hosts, (f.id, host)
    assert not any("juridico" in h or "jusbrasil" in h for h in catalogados)


def test_escopo_de_caminho_consistente_sem_host_livre():
    for f in FONTES_SONDA.values():
        assert not hasattr(f, "hosts_sem_prefixo") and not hasattr(f, "path_prefixes")
        assert set(f.rotas) == set(f.hosts)
        for host, rotas in f.rotas.items():
            assert type(rotas) is tuple
            assert all(p.startswith("/") and p != "/" and not p.lower().startswith("/robots.txt") for p in rotas)
        mapa = prefixos_por_host(f)
        assert set(mapa) == set(f.hosts)  # todo host tem escopo explícito: nunca None, nunca host inteiro
        for host, prefixos in mapa.items():
            assert prefixos == (f.rotas[host] or ("/robots.txt",)) and "/" not in prefixos
    # hosts que só admitem o robots.txt (nenhuma rota documentada em página oficial lida)
    so_robots = {(f.id, h) for f in FONTES_SONDA.values() for h, r in f.rotas.items() if not r}
    assert so_robots == {
        ("bnp", "bnp.pdpj.jus.br"), ("bnp", "pangeabnp.pdpj.jus.br"), ("djen", "comunicaapi.pje.jus.br"),
        ("tst", "consultadocumento.tst.jus.br"),
        ("cjf_unificada", "jurisprudencia.cjf.jus.br"), ("trf1", "jurisprudencia.cjf.jus.br"),
        ("trf1", "arquivo.trf1.jus.br"), ("trf2", "jurisprudencia.trf2.jus.br"),
        ("normas_leg", "normas.leg.br"), ("lexml", "www.lexml.gov.br"),
    }


PALAVRAS_PROIBIDAS = ("cadastro", "login", "institucional", "nota-tecnica", "admin", "senha", "usuario")


def test_nenhuma_rota_de_cadastro_login_ou_area_institucional():
    for f in FONTES_SONDA.values():
        for host, rotas in f.rotas.items():
            for rota in rotas:
                assert not any(p in rota.lower() for p in PALAVRAS_PROIBIDAS), (f.id, host, rota)


def test_fonte_incoerente_e_recusada_na_construcao():
    base = dict(id="x", descricao="d", mimes=frozenset({"text/html"}), confirmacao="A")
    h = frozenset({"a.jus.br"})
    origem = "a.jus.br=https://a.jus.br/"
    FonteSonda(hosts=h, rotas={"a.jus.br": ("/x/",)}, origem_hosts=origem, **base)  # válida
    FonteSonda(hosts=h, rotas={"a.jus.br": ()}, origem_hosts=origem, **base)  # só robots.txt
    ruins = [
        dict(hosts=h, rotas={}, origem_hosts=origem),  # host sem rota declarada
        dict(hosts=h, rotas={"a.jus.br": ("/",)}, origem_hosts=origem),  # raiz = host inteiro
        dict(hosts=h, rotas={"a.jus.br": ("/robots.txt",)}, origem_hosts=origem),  # exceção não é rota
        dict(hosts=h, rotas={"a.jus.br": ("x",)}, origem_hosts=origem),
        dict(hosts=h, rotas={"a.jus.br": ["/x/"]}, origem_hosts=origem),  # não é tupla
        dict(hosts=h, rotas={"a.jus.br": ("/x/",), "b.jus.br": ()}, origem_hosts=origem),  # rota de host fora
        dict(hosts=h, rotas={"a.jus.br": ("/x/",)}, origem_hosts=""),  # sem origem
        dict(hosts=h, rotas={"a.jus.br": ("/x/",)}, origem_hosts=origem, hosts_b=h),  # B declarado com A
    ]
    for kw in ruins:
        with pytest.raises(ValueError):
            FonteSonda(**{**base, **kw})
    with pytest.raises(ValueError):  # B sem host B
        FonteSonda(**{**base, "confirmacao": "B"}, hosts=h, rotas={"a.jus.br": ("/x/",)}, origem_hosts=origem)
    with pytest.raises(ValueError):  # nível inexistente
        FonteSonda(**{**base, "confirmacao": "C"}, hosts=h, rotas={"a.jus.br": ("/x/",)}, origem_hosts=origem)


def test_registry_do_produto_nao_muda():
    assert not set(IDS) & set(registry())
    assert set(registry()) == {
        "bcb", "camara_legin", "cvm_colegiado", "cvm_normas", "datajud", "planalto", "senado", "stf", "stj", "tcu", "tjdft", "tjsp",
    }


# --- allowlist por fonte ----------------------------------------------------------------------------


@pytest.mark.parametrize("fid,url", _cada_fonte_e_host())
def test_get_na_allowlist_da_fonte_usa_transporte_comum_e_ua_identificado(envios, tmp_path, fid, url):
    fonte = FONTES_SONDA[fid]
    reg = captura.capturar(None, url=url, destino=tmp_path, sonda=True, chave="s", fonte_sonda=fid,
                           user_agent="identificado", confirmado_por_titular=_liberado(fonte, url))
    assert not reg.unavailable and reg.metodo == "GET" and reg.parametros is None
    visto = envios[0]
    assert visto["url"] == url and visto["method"] == "GET" and visto["body"] is None
    assert visto["allowed_hosts"] == fonte.hosts
    if url.endswith("/robots.txt"):  # host só-robots: política do robots.txt (ver teste próprio)
        assert visto["allowed_mimes"] == frozenset({"text/plain"})
    else:
        assert visto["allowed_mimes"] == fonte.mimes
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
    for h in sorted(fonte.hosts):  # fora das rotas: todo host tem escopo de caminho
        ruins += [f"https://{h}/fora/do/escopo", f"https://{h}/", f"https://{h}/robots.txt?x=1", f"https://{h}/Robots.txt",
                 f"https://{h}/robots.txt.bak", f"https://{h}/robots.txt/x"]
    for url in ruins:
        with pytest.raises(ValueError, match="fora da allowlist da fonte-sonda"):
            captura.capturar(None, url=url, destino=tmp_path, sonda=True, chave="s", fonte_sonda=fid)
    assert envios == [] and not any(tmp_path.iterdir())


@pytest.mark.parametrize("fid", sorted(IDS))
def test_robots_txt_de_cada_host_da_fonte(envios, tmp_path, fid):
    fonte = FONTES_SONDA[fid]
    for i, host in enumerate(sorted(fonte.hosts)):
        captura.capturar(None, url=f"https://{host}/robots.txt", destino=tmp_path, sonda=True, chave=f"r{i}",
                         fonte_sonda=fid, confirmado_por_titular=host in fonte.hosts_b)
        visto = envios[-1]
        # exceção de caminho só para o robots.txt exato: prefixo exato em todos os hosts, só text/plain, sem salto
        assert visto["allowed_path_prefixes"] == {h: ("/robots.txt",) for h in fonte.hosts}
        assert visto["allowed_mimes"] == frozenset({"text/plain"}) and visto["max_redirects"] == 0
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
    url = next(_urls_validas(FONTES_SONDA["trf3"]))
    reg = captura.capturar(None, url=url, destino=tmp_path, sonda=True, chave="e", fonte_sonda="trf3")
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


COMANDO_FONTE = re.compile(
    r'python scripts/capturar_fixture\.py --fonte-sonda (\w+) --sonda --saida C:/dev/fv14-sondas/(\w+) '
    r'--chave (\w+) --url "([^"]+)"'
)
COMANDO_CONECTOR = re.compile(
    r'python scripts/capturar_fixture\.py --conector (\w+) --sonda --saida C:/dev/fv14-sondas/(\w+) '
    r"--chave (\w+) (?:--url \"([^\"]+)\"|--consulta '[^']+')"
)


def _comandos_do_roteiro():
    """Comandos na ordem do arquivo: (tipo, id, pasta, chave, url|None, bloqueado). Formato exato ou o teste falha."""
    achados, fence = [], None
    for ln in ROTEIRO.read_text(encoding="utf-8").splitlines():
        if ln.startswith("```"):
            fence = ln[3:].strip() or None
            continue
        if fence is None or not ln.startswith("python "):
            continue
        assert fence in ("powershell", "powershell-bloqueado"), fence
        m = COMANDO_FONTE.fullmatch(ln.strip())
        if m:
            fid, pasta, chave, url = m.groups()
            achados.append(("fonte", fid, pasta, chave, url, fence == "powershell-bloqueado"))
            continue
        m = COMANDO_CONECTOR.fullmatch(ln.strip())
        assert m, f"comando fora do formato exato: {ln}"
        cid, pasta, chave, url = m.groups()
        achados.append(("conector", cid, pasta, chave, url, False))
    return achados


@pytest.mark.repositorio
def test_toda_url_do_roteiro_esta_na_allowlist_da_fonte_e_toda_fonte_tem_comando():
    comandos = _comandos_do_roteiro()
    fontes = [c for c in comandos if c[0] == "fonte"]
    for _, fid, pasta, chave, url, bloqueado in fontes:
        assert fid == pasta and fid in FONTES_SONDA and chave.startswith(f"{fid}_")
        fonte = FONTES_SONDA[fid]
        # levanta ValueError se a URL sair da allowlist, ou se o host for B sem a confirmação do titular
        plano = captura._planejar_sonda(fid, None, url, confirmado_por_titular=True)
        assert plano["metodo"] == "GET" and plano["hosts"] == fonte.hosts
        assert bloqueado == (urlsplit(url).hostname in fonte.hosts_b)  # bloco bloqueado = host B, e só ele
        if bloqueado:
            with pytest.raises(ValueError, match="nível B"):
                captura._planejar_sonda(fid, None, url)
        else:
            captura._planejar_sonda(fid, None, url)
    assert {c[1] for c in fontes} == set(IDS)
    for fid in IDS:
        assert any(c[4].endswith("/robots.txt") for c in fontes if c[1] == fid), fid
    for _, cid, *_ in (c for c in comandos if c[0] == "conector"):
        assert cid in registry()


@pytest.mark.repositorio
def test_primeiro_comando_de_cada_host_do_roteiro_e_o_robots_txt():
    """B3: nenhum host é acessado antes do seu robots.txt, no arquivo todo e dentro de cada fonte."""
    comandos = [c for c in _comandos_do_roteiro() if c[4] is not None]
    vistos_globais, vistos_fonte = {}, {}
    hosts = set()
    for tipo, cid, _, chave, url, _ in comandos:
        host = urlsplit(url).hostname
        hosts.add(host)
        caminho = urlsplit(url).path
        for escopo, chave_escopo in ((vistos_globais, host), (vistos_fonte, (cid, host))):
            if chave_escopo not in escopo:
                escopo[chave_escopo] = (chave, caminho)
                assert caminho == "/robots.txt" and not urlsplit(url).query, f"{cid}: {host} acessado antes do robots.txt"
    # os hosts que o roteiro toca incluem os problemáticos do parecer
    assert {"bnp.pdpj.jus.br", "www.cjf.jus.br", "pangeabnp.pdpj.jus.br"} <= hosts
    for f in FONTES_SONDA.values():  # todo host com rota do catálogo usada no roteiro tem robots antes
        for host in f.hosts:
            usados = [c for c in comandos if c[1] == f.id and urlsplit(c[4]).hostname == host]
            if usados:
                assert urlsplit(usados[0][4]).path == "/robots.txt", (f.id, host)


@pytest.mark.repositorio
def test_roteiro_usa_chave_distinta_por_comando_e_nunca_repete_arquivo_de_saida():
    comandos = _comandos_do_roteiro()
    destinos = [(c[2], c[3]) for c in comandos]
    assert len(destinos) == len(set(destinos)) and len({c[3] for c in comandos}) == len(comandos)
    for _, cid, pasta, chave, *_ in comandos:
        assert CHAVE_VALIDA.fullmatch(chave) and chave.startswith(f"{cid}_")


CHAVE_VALIDA = re.compile(r"[a-z0-9_]+")


@pytest.mark.repositorio
def test_roteiro_sem_descoberta_de_endpoint_fora_do_instrumento_nem_rota_de_cadastro():
    texto = ROTEIRO.read_text(encoding="utf-8")
    low = texto.lower()
    for proibido in ("descubra no navegador", "aba rede", "refazer no notebook", "devtools"):
        assert proibido not in low, proibido
    assert not re.search(r"descubra\b", low)
    assert "/nota-tecnica" not in low
    for c in _comandos_do_roteiro():
        if c[4]:
            assert not any(p in urlsplit(c[4]).path.lower() for p in PALAVRAS_PROIBIDAS), c[4]
    # arbitragem do supervisor (B2): primeiro e único acesso, barreira registrada, sem nova rota
    assert "primeiro e único acesso do produto" in texto and "outra rede ou rota" in texto
    assert "S0b" in texto and "sessão assistida" in texto and "decisão 0067" in texto


@pytest.mark.repositorio
def test_roteiro_marca_bloqueio_de_host_b_e_nao_afirma_confirmacao_geral():
    texto = ROTEIRO.read_text(encoding="utf-8")
    assert "bloqueada até confirmação documental (página oficial lida ou confirmação do titular)" in texto
    assert "--confirmado-por-titular" in texto
    assert "Nenhum host de nível B foi confirmado" in texto
    bs = {(f.id, h) for f in FONTES_SONDA.values() for h in f.hosts_b}
    assert bs == {("cjf_unificada", "www.cjf.jus.br"), ("tjal", "www2.tjal.jus.br"),
                  ("tjam", "consultasaj.tjam.jus.br"), ("tjms", "esaj.tjms.jus.br"),
                  ("tjrj", "www3.tjrj.jus.br"), ("tjrs", "www.tjrs.jus.br")}
    assert {f.id for f in FONTES_SONDA.values() if f.confirmacao == "B"} == {i for i, _ in bs}
    # todo comando de host B está em bloco bloqueado e vice-versa (também checado na allowlist, acima)
    for tipo, cid, _, _, url, bloqueado in _comandos_do_roteiro():
        if tipo == "fonte":
            assert bloqueado == (urlsplit(url).hostname in FONTES_SONDA[cid].hosts_b)


@pytest.mark.repositorio
def test_roteiro_nao_promete_categoria_para_429():
    """M1: 429 sai sem categoria (decisão 0045); o roteiro e o registro da auditoria não podem prometê-la."""
    texto = ROTEIRO.read_text(encoding="utf-8")
    assert "429 e outros status sem regra própria saem sem categoria" in texto
    assert not re.search(r"403/429/5xx\)[^.\n]*com categoria", texto)
    from freoa_verifica.connectors.challenge import map_transport_error
    from freoa_verifica.transport import HTTPStatusError

    u = map_transport_error(HTTPStatusError(429), "https://x.jus.br/")
    assert u.reason == "http_429" and u.categoria is None


# --- B1 (parecer PR #14 r1): robots.txt não segue redirecionamento -------------------------------------


def _servidor_robots(location: str):
    """Servidor local: /robots.txt devolve 302 para `location`; qualquer outro caminho devolve 200 e é registrado."""
    import socketserver
    import threading

    class H(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(2)
            try:
                dados = self.request.recv(65536)
            except OSError:
                return
            caminho = dados.split(b"\r\n", 1)[0].decode("latin-1").split(" ")[1]
            self.server.percursos.append(caminho)
            if caminho == "/robots.txt":
                self.request.sendall(
                    f"HTTP/1.1 302 Found\r\nLocation: {location}\r\nContent-Length: 0\r\n\r\n".encode("latin-1")
                )
            else:
                corpo = b"area restrita: login"
                self.request.sendall(
                    b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: %d\r\n\r\n%s"
                    % (len(corpo), corpo)
                )

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), H)
    server.daemon_threads = True
    server.percursos = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


DESTINOS_DE_REDIRECIONAMENTO = [
    "/admin/login",  # cenário exato do parecer: mesmo host, rota fora do escopo
    "/robots.txt.bak",  # variante que o prefixo "/robots.txt" sozinho aceitaria
    "/robots.txt/../admin",
]


@pytest.mark.parametrize("destino", DESTINOS_DE_REDIRECIONAMENTO)
@pytest.mark.parametrize("alvo", [
    pytest.param(("fonte", "tst", "https://jurisprudencia.tst.jus.br/robots.txt"), id="fonte-sonda-escopo-estreito"),
    pytest.param(("fonte", "bnp", "https://pangeabnp.pdpj.jus.br/robots.txt"), id="fonte-sonda-so-robots"),
    pytest.param(("conector", "tjsp", "https://esaj.tjsp.jus.br/robots.txt"), id="conector-tjsp"),
    pytest.param(("conector", "stf", "https://portal.stf.jus.br/robots.txt"), id="conector-stf"),
])
def test_robots_com_302_nao_e_seguido_e_vira_unavailable(monkeypatch, tmp_path, alvo, destino):
    tipo, id_, url = alvo
    monkeypatch.setattr(captura, "_raiz_repo", lambda: None)
    server = _servidor_robots(destino)
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    try:
        kw = {"fonte_sonda": id_} if tipo == "fonte" else {}
        reg = captura.capturar(None if tipo == "fonte" else id_, url=url, destino=tmp_path, sonda=True,
                               chave="r", **kw)
    finally:
        server.shutdown()
        server.server_close()
    assert server.percursos == ["/robots.txt"]  # nenhum pedido ao destino do redirecionamento
    assert reg.unavailable and reg.motivo and reg.corpo is None and reg.arquivo is None
    salvo = json.loads((tmp_path / "r.captura.json").read_text(encoding="utf-8"))
    assert salvo["unavailable"] is True and salvo["motivo"] and not list(tmp_path.glob("r.[!c]*"))


def test_robots_redirecionando_para_outro_host_da_allowlist_nao_e_seguido(monkeypatch, tmp_path):
    monkeypatch.setattr(captura, "_raiz_repo", lambda: None)
    server = _servidor_robots("https://jurisprudencia-backend.tst.jus.br/rest/indicadores")
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    try:
        reg = captura.capturar(None, url="https://jurisprudencia.tst.jus.br/robots.txt", destino=tmp_path, sonda=True,
                               chave="r", fonte_sonda="tst")
    finally:
        server.shutdown()
        server.server_close()
    assert server.percursos == ["/robots.txt"] and reg.unavailable


def test_robots_200_text_plain_continua_capturado(monkeypatch, tmp_path):
    import socketserver
    import threading

    class H(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(2)
            self.request.recv(65536)
            c = b"User-agent: *\nDisallow: /admin/\n"
            self.request.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: %d\r\n\r\n%s"
                                 % (len(c), c))

    monkeypatch.setattr(captura, "_raiz_repo", lambda: None)
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), H)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    try:
        reg = captura.capturar(None, url="https://web.trf3.jus.br/robots.txt", destino=tmp_path, sonda=True,
                               chave="r", fonte_sonda="trf3")
    finally:
        server.shutdown()
        server.server_close()
    assert not reg.unavailable and reg.status == 200 and (tmp_path / "r.txt").read_bytes().startswith(b"User-agent")


def test_robots_so_admite_text_plain(monkeypatch, tmp_path):
    """A política entregue ao transporte para o robots.txt exclui HTML (casca de SPA não é robots interpretável)."""
    monkeypatch.setattr(captura, "_raiz_repo", lambda: None)
    vistos = []

    def espia(u, **kw):
        vistos.append(kw)
        return _resp(u, b"User-agent: *\n", 200, "text/plain")

    monkeypatch.setattr(httputil, "transport_fetch", espia)
    captura.capturar(None, url="https://pangeabnp.pdpj.jus.br/robots.txt", destino=tmp_path, sonda=True, chave="h",
                     fonte_sonda="bnp")
    assert vistos[0]["allowed_mimes"] == frozenset({"text/plain"})


# --- I2: proveniência (confirmacao A/B) e bloqueio de host B ------------------------------------------

BS = {(f.id, h) for f in FONTES_SONDA.values() for h in f.hosts_b}


def _url_b(fid, host):
    return f"https://{host}{(FONTES_SONDA[fid].rotas[host] or ('/robots.txt',))[0]}"


@pytest.mark.parametrize("fid,host", sorted(BS))
def test_host_b_e_recusado_antes_da_rede_inclusive_robots(envios, tmp_path, fid, host):
    for url in (_url_b(fid, host), f"https://{host}/robots.txt"):
        with pytest.raises(ValueError, match="nível B"):
            captura.capturar(None, url=url, destino=tmp_path, sonda=True, chave="b", fonte_sonda=fid)
    assert envios == [] and not any(tmp_path.iterdir())


@pytest.mark.parametrize("fid,host", sorted(BS))
def test_host_b_com_confirmacao_do_titular_vai_e_fica_registrado(envios, tmp_path, fid, host):
    reg = captura.capturar(None, url=_url_b(fid, host), destino=tmp_path, sonda=True, chave="b", fonte_sonda=fid,
                           confirmado_por_titular=True)
    assert envios and reg.confirmado_por_titular is True and reg.confirmacao_host == "B"
    salvo = json.loads((tmp_path / "b.captura.json").read_text(encoding="utf-8"))
    assert salvo["confirmado_por_titular"] is True and salvo["confirmacao_host"] == "B"
    assert salvo["fonte_sonda"] == fid


def test_host_a_registra_nivel_a_e_sem_confirmacao_do_titular(envios, tmp_path):
    url = next(_urls_validas(FONTES_SONDA["tjac"]))
    captura.capturar(None, url=url, destino=tmp_path, sonda=True, chave="a", fonte_sonda="tjac")
    salvo = json.loads((tmp_path / "a.captura.json").read_text(encoding="utf-8"))
    assert salvo["confirmacao_host"] == "A" and salvo["confirmado_por_titular"] is False


def test_fonte_com_host_a_e_host_b_so_bloqueia_o_b(envios, tmp_path):
    f = FONTES_SONDA["cjf_unificada"]
    assert f.confirmacao == "B" and f.hosts_b == {"www.cjf.jus.br"}
    captura.capturar(None, url="https://jurisprudencia.cjf.jus.br/robots.txt", destino=tmp_path, sonda=True,
                     chave="a", fonte_sonda="cjf_unificada")  # host A: sem flag
    with pytest.raises(ValueError, match="nível B"):
        captura.capturar(None, url="https://www.cjf.jus.br/robots.txt", destino=tmp_path, sonda=True, chave="b",
                         fonte_sonda="cjf_unificada")
    assert len(envios) == 1


def test_confirmado_por_titular_so_vale_com_fonte_sonda(envios, tmp_path):
    with pytest.raises(ValueError, match="só vale com fonte-sonda"):
        captura.capturar("tjsp", url="https://esaj.tjsp.jus.br/cjsg/", destino=tmp_path, sonda=True, chave="c",
                         confirmado_por_titular=True)
    assert envios == []


def test_registro_de_conector_nao_tem_nivel_nem_confirmacao(envios, tmp_path):
    captura.capturar("tjsp", url="https://esaj.tjsp.jus.br/cjsg/x", destino=tmp_path, sonda=True, chave="c")
    salvo = json.loads((tmp_path / "c.captura.json").read_text(encoding="utf-8"))
    assert salvo["confirmacao_host"] is None and salvo["confirmado_por_titular"] is False


@pytest.mark.repositorio
def test_cli_recusa_host_b_sem_flag_e_registra_com_flag(envios, tmp_path, capsys):
    cli = _cli()
    saida = str(tmp_path / "s")
    argv = ["--fonte-sonda", "tjal", "--sonda", "--saida", saida, "--chave", "k", "--url", _url_b("tjal", "www2.tjal.jus.br")]
    assert cli.main(argv) == 2 and envios == [] and "nível B" in capsys.readouterr().err
    assert not (tmp_path / "s").exists()
    assert cli.main([*argv, "--confirmado-por-titular"]) == 0
    salvo = json.loads((tmp_path / "s" / "k.captura.json").read_text(encoding="utf-8"))
    assert salvo["confirmado_por_titular"] is True and salvo["confirmacao_host"] == "B"
    with pytest.raises(SystemExit) as exc:  # a flag não vale fora de --fonte-sonda
        cli.main(["--conector", "tjsp", "--sonda", "--saida", saida, "--url", "https://esaj.tjsp.jus.br/cjsg/",
                  "--confirmado-por-titular"])
    assert exc.value.code == 2
    capsys.readouterr()


# --- I3: evidência não se sobrescreve -----------------------------------------------------------------


def test_nao_sobrescreve_captura_json_existente_e_recusa_antes_da_rede(envios, tmp_path):
    url = next(_urls_validas(FONTES_SONDA["tjac"]))
    captura.capturar(None, url=url, destino=tmp_path, sonda=True, chave="x", fonte_sonda="tjac")
    antes = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert len(envios) == 1
    with pytest.raises(ValueError, match="já existe x.captura.json"):
        captura.capturar(None, url=url, destino=tmp_path, sonda=True, chave="x", fonte_sonda="tjac")
    assert len(envios) == 1  # nenhum pedido à fonte para depois recusar a gravação
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == antes


def test_respostas_identicas_com_chaves_distintas_convivem(envios, tmp_path):
    url = next(_urls_validas(FONTES_SONDA["tjac"]))
    for chave in ("tjac_a", "tjac_b"):
        captura.capturar(None, url=url, destino=tmp_path, sonda=True, chave=chave, fonte_sonda="tjac")
    assert {p.name for p in tmp_path.iterdir()} == {"tjac_a.captura.json", "tjac_a.json", "tjac_b.captura.json",
                                                    "tjac_b.json"}


def test_chave_derivada_do_hash_tambem_nao_sobrescreve(envios, tmp_path):
    url = next(_urls_validas(FONTES_SONDA["tjac"]))
    reg = captura.capturar(None, url=url, destino=tmp_path, sonda=True, fonte_sonda="tjac")  # sem --chave
    antes = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(ValueError, match="já existe"):  # mesma resposta, mesma chave derivada
        captura.capturar(None, url=url, destino=tmp_path, sonda=True, fonte_sonda="tjac")
    assert len(envios) == 2 and {p.name: p.read_bytes() for p in tmp_path.iterdir()} == antes
    assert reg.arquivo and (tmp_path / reg.arquivo).is_file()


def test_corpo_orfao_existente_tambem_impede_a_gravacao(envios, tmp_path):
    url = next(_urls_validas(FONTES_SONDA["tjac"]))
    (tmp_path / "o.json").write_bytes(b"evidencia anterior")
    with pytest.raises(ValueError, match="já existe o.json"):
        captura.capturar(None, url=url, destino=tmp_path, sonda=True, chave="o", fonte_sonda="tjac")
    assert (tmp_path / "o.json").read_bytes() == b"evidencia anterior" and not (tmp_path / "o.captura.json").exists()


def test_unavailable_tambem_nao_sobrescreve_registro(monkeypatch, tmp_path):
    monkeypatch.setattr(captura, "_raiz_repo", lambda: None)
    monkeypatch.setattr(httputil, "transport_fetch", lambda u, **k: _resp(u, b"<html>x</html>", 403, "text/html"))
    url = next(_urls_validas(FONTES_SONDA["trf3"]))
    captura.capturar(None, url=url, destino=tmp_path, sonda=True, chave="u", fonte_sonda="trf3")
    antes = (tmp_path / "u.captura.json").read_bytes()
    with pytest.raises(ValueError, match="já existe"):
        captura.capturar(None, url=url, destino=tmp_path, sonda=True, chave="u", fonte_sonda="trf3")
    assert (tmp_path / "u.captura.json").read_bytes() == antes


@pytest.mark.repositorio
def test_cli_recusa_sobrescrita_com_erro(envios, tmp_path, capsys):
    cli = _cli()
    argv = ["--fonte-sonda", "tjac", "--sonda", "--saida", str(tmp_path / "s"), "--chave", "k",
            "--url", next(_urls_validas(FONTES_SONDA["tjac"]))]
    assert cli.main(argv) == 0
    assert cli.main(argv) == 2 and len(envios) == 1 and "não se sobrescreve" in capsys.readouterr().err


# --- parecer PR #14 r2 -------------------------------------------------------------------------------
# B1: a sonda faz exatamente um pedido (o transporte real não repete 502/503/504); I1: rota é caminho exato;
# B2: fonte com barreira registrada sai do catálogo e é recusada antes da rede.


def _servidor_status(statuses):
    """Servidor local: responde, em ordem, `statuses` (o último se repete); registra cada pedido."""
    import socketserver
    import threading

    class H(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(2)
            try:
                dados = self.request.recv(65536)
            except OSError:
                return
            caminho = dados.split(b"\r\n", 1)[0].decode("latin-1").split(" ")[1]
            with self.server.trava:
                i = len(self.server.percursos)
                self.server.percursos.append(caminho)
            status = statuses[min(i, len(statuses) - 1)]
            if status == 200:
                corpo = b'{"ok":true}'
                self.request.sendall(
                    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n%s"
                    % (len(corpo), corpo)
                )
            else:
                corpo = b"indisponivel"
                self.request.sendall(
                    b"HTTP/1.1 %d X\r\nContent-Type: text/plain\r\nContent-Length: %d\r\n\r\n%s"
                    % (status, len(corpo), corpo)
                )

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), H)
    server.daemon_threads = True
    server.percursos = []
    server.trava = threading.Lock()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _com_servidor(monkeypatch, statuses):
    from freoa_verifica import transport as tr

    monkeypatch.setattr(captura, "_raiz_repo", lambda: None)
    server = _servidor_status(statuses)
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    monkeypatch.setattr(tr, "_dormir", lambda s: None)  # a repetição, se houvesse, não esperaria
    return server


def _parar(server):
    server.shutdown()
    server.server_close()


@pytest.mark.parametrize("statuses", [[503, 200], [503, 503, 503], [502, 200], [504, 504, 200]])
@pytest.mark.parametrize("alvo", [
    pytest.param(("fonte", "tst", "https://jurisprudencia.tst.jus.br/config.json"), id="sonda-rota"),
    pytest.param(("fonte", "tst", "https://jurisprudencia.tst.jus.br/robots.txt"), id="sonda-robots"),
    pytest.param(("conector", "tjsp", "https://esaj.tjsp.jus.br/robots.txt"), id="captura-conector"),
])
def test_captura_faz_exatamente_um_pedido_e_5xx_vira_unavailable(monkeypatch, tmp_path, alvo, statuses):
    tipo, id_, url = alvo
    server = _com_servidor(monkeypatch, statuses)
    try:
        kw = {"fonte_sonda": id_} if tipo == "fonte" else {}
        reg = captura.capturar(None if tipo == "fonte" else id_, url=url, destino=tmp_path, sonda=True,
                               chave="u", **kw)
    finally:
        _parar(server)
    assert len(server.percursos) == 1  # um 503 seguido de 200 NÃO vira sucesso
    assert reg.unavailable and reg.motivo == f"http_{statuses[0]}" and reg.corpo is None
    assert reg.categoria is None or reg.categoria in CATEGORIAS_INDISPONIBILIDADE


def test_captura_com_200_continua_um_pedido_e_sucesso(monkeypatch, tmp_path):
    server = _com_servidor(monkeypatch, [200])
    try:
        reg = captura.capturar(None, url="https://jurisprudencia.tst.jus.br/config.json", destino=tmp_path,
                               sonda=True, chave="u", fonte_sonda="tst")
    finally:
        _parar(server)
    assert server.percursos == ["/config.json"] and not reg.unavailable and reg.status == 200


def test_demais_consumidores_do_transporte_mantem_a_repeticao(monkeypatch):
    """O `connector_fetch` sem `repeticao` (todo conector do produto) segue repetindo 502/503/504 duas vezes."""
    server = _com_servidor(monkeypatch, [503, 200])
    kw = dict(hosts=frozenset({"jurisprudencia.tst.jus.br"}),
              path_prefixes={"jurisprudencia.tst.jus.br": ("/config.json",)},
              mimes=frozenset({"application/json"}), user_agent="identified")
    try:
        resp = httputil.connector_fetch("https://jurisprudencia.tst.jus.br/config.json", **kw)
        assert resp.status == 200 and server.percursos == ["/config.json"] * 2
    finally:
        _parar(server)
    server = _com_servidor(monkeypatch, [503])
    try:
        with pytest.raises(Unavailable) as ei:
            httputil.connector_fetch("https://jurisprudencia.tst.jus.br/config.json", **kw)
    finally:
        _parar(server)
    assert ei.value.reason == "http_503" and len(server.percursos) == 3


def test_connector_fetch_repeticao_zero_chega_ao_transporte(monkeypatch):
    vistos = []

    def fake(url, **kw):
        vistos.append(kw)
        return _resp(url)

    monkeypatch.setattr(httputil, "transport_fetch", fake)
    base = dict(hosts=frozenset({"a.jus.br"}), path_prefixes=None, mimes=frozenset({"application/json"}))
    httputil._connector_fetch("https://a.jus.br/x", **base)
    httputil._connector_fetch("https://a.jus.br/x", repeticao=0, **base)
    assert "repeticao" not in vistos[0] and vistos[1]["repeticao"] == 0


def test_captura_passa_repeticao_zero_em_todo_pedido(envios, tmp_path):
    captura.capturar(None, url="https://jurisprudencia.tst.jus.br/config.json", destino=tmp_path, sonda=True,
                     chave="s", fonte_sonda="tst")
    assert envios[0]["repeticao"] == 0 and envios[0]["max_redirects"] == 0


# --- I1: caminho exato ---------------------------------------------------------------------------------

URLS_I1_DO_PARECER = [
    ("tst", "https://jurisprudencia.tst.jus.br/config.json.bak"),
    ("tst", "https://jurisprudencia-backend.tst.jus.br/rest/indicadores/admin/login"),
    ("tac", "https://esaj.tjac.jus.br/cjsg/consultaCompleta.do.evil"),
    ("tpr", "https://portal.tjpr.jus.br/jurisprudencia-admin/login"),
    ("tpr", "https://portal.tjpr.jus.br/jurisprudencia/login"),
]
VARIANTES_I1 = [
    ("tst", "https://jurisprudencia.tst.jus.br/config.json/"),
    ("tst", "https://jurisprudencia.tst.jus.br/config.json.old"),
    ("tst", "https://jurisprudencia.tst.jus.br/config.jsonx"),
    ("tst", "https://jurisprudencia.tst.jus.br/Config.json"),
    ("tst", "https://jurisprudencia.tst.jus.br/config.json?x=1"),
    ("tst", "https://jurisprudencia.tst.jus.br/config.json/extra"),
    ("tst", "https://jurisprudencia.tst.jus.br//config.json"),
    ("tst", "https://jurisprudencia.tst.jus.br/config%2Ejson"),
    ("tst", "https://jurisprudencia-backend.tst.jus.br/rest/indicadores/"),
    ("tst", "https://jurisprudencia-backend.tst.jus.br/rest/indicadores2"),
    ("tst", "https://jurisprudencia-backend.tst.jus.br/rest/indicadores?a=1"),
    ("tst", "https://jurisprudencia-backend.tst.jus.br/rest/orgaos-judicantes/1"),
    ("tac", "https://esaj.tjac.jus.br/cjsg/consultaCompleta.do/x"),
    ("tac", "https://esaj.tjac.jus.br/cjsg/consultaCompleta.do?a=1"),
    ("tac", "https://esaj.tjac.jus.br/cjsg/resultadoCompleta.do.bak?a=1"),
    ("tpr", "https://portal.tjpr.jus.br/jurisprudencia"),
    ("tpr", "https://portal.tjpr.jus.br/jurisprudencia/x"),
    ("tpr", "https://portal.tjpr.jus.br/jurisprudencia/?q=1"),
    ("trf3", "https://web.trf3.jus.br/jurisprudencia/login"),
    ("trf3", "https://web.trf3.jus.br/acordaos/Acordao/x"),
    ("stf_acordaos", "https://jurisprudencia.stf.jus.br/pages/search/admin"),
]
_FONTE_DO_APELIDO = {"tac": "tjac", "tpr": "tjpr"}


@pytest.mark.parametrize("fid,url", URLS_I1_DO_PARECER + VARIANTES_I1)
def test_rota_e_caminho_exato_prefixo_sufixo_e_segmento_extra_recusados_antes_da_rede(envios, tmp_path, fid, url):
    fid = _FONTE_DO_APELIDO.get(fid, fid)
    with pytest.raises(ValueError, match="fora da allowlist da fonte-sonda"):
        captura.capturar(None, url=url, destino=tmp_path, sonda=True, chave="s", fonte_sonda=fid)
    assert envios == [] and not any(tmp_path.iterdir())


def test_rota_exata_e_consulta_so_na_rota_declarada_com_parametros(envios, tmp_path):
    for fid, url in [("tst", "https://jurisprudencia.tst.jus.br/config.json"),
                     ("tjpr", "https://portal.tjpr.jus.br/jurisprudencia/"),
                     ("tjac", "https://esaj.tjac.jus.br/cjsg/consultaCompleta.do"),
                     ("tjac", "https://esaj.tjac.jus.br/cjsg/resultadoCompleta.do?dados.buscaInteiroTeor=a+b&x=1")]:
        captura.capturar(None, url=url, destino=tmp_path, sonda=True, chave=f"k{len(envios)}", fonte_sonda=fid)
    assert [e["url"] for e in envios][-1].startswith("https://esaj.tjac.jus.br/cjsg/resultadoCompleta.do?")
    assert len(envios) == 4
    assert FONTES_SONDA["tjac"].consultas == {"esaj.tjac.jus.br": ("/cjsg/resultadoCompleta.do",)}
    assert [f.id for f in FONTES_SONDA.values() if f.consultas] == ["tjac", "camara_legislacao"]


def test_catalogo_so_tem_caminho_exato_sem_prefixo_nem_segmento_proibido():
    for f in FONTES_SONDA.values():
        for host, rotas in f.rotas.items():
            for r in rotas:
                assert not any(w in r.lower() for w in SEGMENTOS_PROIBIDOS), (f.id, r)
                assert not any(c in r for c in "?#%\\"), (f.id, r)
        for host, cs in f.consultas.items():
            assert set(cs) <= set(f.rotas[host])


def test_fonte_recusa_rota_com_segmento_proibido_ou_consulta_fora_das_rotas():
    base = dict(id="x", descricao="d", mimes=frozenset({"text/html"}), confirmacao="A", hosts=frozenset({"a.jus.br"}),
                origem_hosts="a.jus.br=https://a.jus.br/")
    FonteSonda(rotas={"a.jus.br": ("/x/",)}, **base)
    for ruim in ("/login", "/a/admin/b", "/jurisprudencia-admin/x", "/cadastro", "/auth/x", "/minha-conta", "/usuario",
                 "/x?y=1", "/x#f", "/x%2e", "/x\\y"):
        with pytest.raises(ValueError):
            FonteSonda(rotas={"a.jus.br": (ruim,)}, **base)
    with pytest.raises(ValueError):
        FonteSonda(rotas={"a.jus.br": ("/x",)}, consultas={"a.jus.br": ("/y",)}, **base)
    with pytest.raises(ValueError):
        FonteSonda(rotas={"a.jus.br": ("/x",)}, consultas={"b.jus.br": ("/x",)}, **base)


@pytest.mark.parametrize("destino", ["/config.json.bak", "/admin/login", "/config.json/../x"])
def test_redirecionamento_de_rota_exata_nao_e_seguido(monkeypatch, tmp_path, destino):
    monkeypatch.setattr(captura, "_raiz_repo", lambda: None)
    import socketserver
    import threading

    class H(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(2)
            dados = self.request.recv(65536)
            self.server.percursos.append(dados.split(b"\r\n", 1)[0].decode("latin-1").split(" ")[1])
            self.request.sendall(f"HTTP/1.1 302 Found\r\nLocation: {destino}\r\nContent-Length: 0\r\n\r\n".encode())

    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    srv.percursos = []
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, srv.server_address[1])
    try:
        reg = captura.capturar(None, url="https://jurisprudencia.tst.jus.br/config.json", destino=tmp_path,
                               sonda=True, chave="r", fonte_sonda="tst")
    finally:
        _parar(srv)
    assert srv.percursos == ["/config.json"] and reg.unavailable and reg.corpo is None


# --- B2: barreira registrada --------------------------------------------------------------------------

def test_fontes_barradas_registradas_e_tjrs_de_volta_em_nivel_b():
    assert set(FONTES_BARRADAS) == {"senado_legislacao", "dou"}
    assert not set(FONTES_BARRADAS) & set(FONTES_SONDA)
    assert "tjrs" in FONTES_SONDA and FONTES_SONDA["tjrs"].hosts_b == {"www.tjrs.jus.br"}
    assert "www.tjrs.jus.br" not in HOSTS_RECUSADOS


def test_instrumento_recusa_fonte_barrada_antes_da_rede(monkeypatch, envios, tmp_path):
    from types import MappingProxyType

    monkeypatch.setattr(captura, "FONTES_BARRADAS", MappingProxyType({"tst": "barreira registrada: x"}))
    for url in ("https://jurisprudencia.tst.jus.br/robots.txt", "https://jurisprudencia.tst.jus.br/config.json"):
        with pytest.raises(ValueError, match="barrada, sem sonda"):
            captura.capturar(None, url=url, destino=tmp_path, sonda=True, chave="b", fonte_sonda="tst",
                             confirmado_por_titular=True)
    assert envios == [] and not any(tmp_path.iterdir())


@pytest.mark.repositorio
def test_djen_referencia_a_decisao_0069_e_roteiro_sem_proxy_nem_repeticao():
    raiz = Path(__file__).resolve().parents[1]
    assert "djen" in FONTES_SONDA and "djen" not in FONTES_BARRADAS
    assert "0069" in FONTES_SONDA["djen"].nota and "Brasil" in FONTES_SONDA["djen"].nota
    assert not {"comunica.pje.jus.br", "comunicaapi.pje.jus.br"} & set(HOSTS_RECUSADOS)
    decisao = raiz / "docs/decisoes/0069-djen-restricao-geografica.md"
    assert decisao.read_text(encoding="utf-8").startswith("# 0069")
    roteiro = (raiz / "docs/S0-SONDAS.md").read_text(encoding="utf-8")
    secao = roteiro[roteiro.index("### djen:"):roteiro.index("### cjf_unificada:")]
    assert "0069" in secao and "27/10/2026" in secao and "sem valor de evidência" in secao
    comandos = [l for l in secao.splitlines() if l.startswith("python scripts/capturar_fixture.py")]
    assert comandos and all("--fonte-sonda djen" in c for c in comandos)
    baixo = secao.lower()
    for proibido in ("--proxy", "http_proxy", "https_proxy", "socks", "openvpn", "wireguard", "tor "):
        assert proibido not in baixo.replace("sem proxy", ""), proibido
    assert len(comandos) == len(set(re.findall(r"--chave (\w+)", "\n".join(comandos))))  # nenhuma repetição
    assert len({re.search(r'--url "([^"]+)"', c).group(1) for c in comandos}) == len(comandos)


@pytest.mark.repositorio
def test_tjrs_robots_primeiro_no_roteiro_e_decisao_na_auditoria():
    raiz = Path(__file__).resolve().parents[1]
    roteiro = (raiz / "docs/S0-SONDAS.md").read_text(encoding="utf-8")
    secao = roteiro[roteiro.index("### tjrs:"):roteiro.index("### tjpr:")]
    comandos = [l for l in secao.splitlines() if l.startswith("python scripts/capturar_fixture.py")]
    assert comandos[0].endswith('--url "https://www.tjrs.jus.br/robots.txt"') and len(comandos) == 2
    assert "UA do produto" in secao and "Disallow" in secao and "não recusa ao produto" in secao
    audit = (raiz / "docs/auditoria/1.4.0/s0-instrumento.md").read_text(encoding="utf-8")
    assert "TJRS de volta ao catálogo em nível B" in audit


# --- IL.2-a: catálogo e roteiro das rotas de legislação ----------------------------------------------------

# IL.2-b.2: valores fixados a partir das evidências, independentes do catálogo.
NORMAS_CAMARA = (
    ('lei6404', '/legin/fed/lei/1970-1979/lei-6404-15-dezembro-1976-368447-norma-pl.html', 62219, '4026cacd902d161f50df1dcd976f6845cf7a867c5fff1301c845f19f13642878'),
    ('lc123', '/legin/fed/leicom/2006/leicomplementar-123-14-dezembro-2006-548099-norma-pl.html', 59778, '9bd90cfad8c6c0fed23f589a24e90e1cb1ee415c824c76034d9e36cb470aedb8'),
    ('lei13874', '/legin/fed/lei/2019/lei-13874-20-setembro-2019-789149-norma-pl.html', 62896, 'c0377cd867d3a3b1b29c6713a6629b41055daa3726053512473893070174744d'),
)

# IL.2-b.3: constantes extraídas das capturas, sem derivação do catálogo.
TEXTOS_CAMARA = (
    ('atualizado_lei6404', '/legin/fed/lei/1970-1979/lei-6404-15-dezembro-1976-368447-normaatualizada-pl.html', 'lei6404', '882ca0784ab7495c6f61725373f8efe15950845313090818aeb0ec3742023a13'),
    ('original_lei6404', '/legin/fed/lei/1970-1979/lei-6404-15-dezembro-1976-368447-publicacaooriginal-1-pl.html', 'lei6404', '882ca0784ab7495c6f61725373f8efe15950845313090818aeb0ec3742023a13'),
    ('mp881_lei6404', '/legin/fed/medpro/2019/medidaprovisoria-881-30-abril-2019-788037-norma-pe.html', 'lei6404', '882ca0784ab7495c6f61725373f8efe15950845313090818aeb0ec3742023a13'),
    ('atualizado_lc123', '/legin/fed/leicom/2006/leicomplementar-123-14-dezembro-2006-548099-normaatualizada-pl.html', 'lc123', '04aee462753d1eaa1caae30fe5be953a4160c343b20565135cf024cab1a842c0'),
    ('original_lc123', '/legin/fed/leicom/2006/leicomplementar-123-14-dezembro-2006-548099-publicacaooriginal-156405-pl.html', 'lc123', '04aee462753d1eaa1caae30fe5be953a4160c343b20565135cf024cab1a842c0'),
    ('anexo_lc123', '/legin/fed/leicom/2006/leicomplementar-123-14-dezembro-2006-548099-anexo-pl.pdf', 'lc123', '04aee462753d1eaa1caae30fe5be953a4160c343b20565135cf024cab1a842c0'),
    ('atualizado_lei13874', '/legin/fed/lei/2019/lei-13874-20-setembro-2019-789149-normaatualizada-pl.html', 'lei13874', '01399e663bc3c108d0eb1a58ebdda1a56a89ef549db537215bd9c4642133b3c3'),
    ('original_lei13874', '/legin/fed/lei/2019/lei-13874-20-setembro-2019-789149-publicacaooriginal-159080-pl.html', 'lei13874', '01399e663bc3c108d0eb1a58ebdda1a56a89ef549db537215bd9c4642133b3c3'),
)
CAPTURAS_NORMAS_CAMARA = (
    ('lei6404', 85675, '882ca0784ab7495c6f61725373f8efe15950845313090818aeb0ec3742023a13'),
    ('lc123', 74769, '04aee462753d1eaa1caae30fe5be953a4160c343b20565135cf024cab1a842c0'),
    ('lei13874', 53481, '01399e663bc3c108d0eb1a58ebdda1a56a89ef549db537215bd9c4642133b3c3'),
)

# IL.2-b.3 REG: valores dos corpos conferidos com o log local do supervisor.
CAPTURAS_TEXTOS_CAMARA = (
    ('atualizado_lei6404', 686299, 'ee3f76848ce42def5e758ed77b994d2a5d05598c4e9dc8b43771c801aa4a854c'),
    ('original_lei6404', 365194, '7dc335d77b1b30f7165c27cb62ce4525bb464b68bf4d03bf5387d7d264156822'),
    ('mp881_lei6404', 47221, '677752f6feaea991ca461933384b451d46d1a2f9c9d0cc7a6b6708de1b73b9e1'),
    ('atualizado_lc123', 796759, 'ad9b586fdf7864ba47dcdeabb20af2cdc9882c8a7511e75461b4321c2e59e459'),
    ('original_lc123', 166709, '65775c1f3e09819229f05c0a10adbeeb6d0bfd8eb0a481c01faaba3bb16e5a99'),
    ('anexo_lc123', 120702, 'c8abdd8ca254a81e4d274335c705630c21ed3cf24948ba70fc12ab145a096887'),
    ('atualizado_lei13874', 117838, 'a231acb388e65b023db0536b60d134e146890f1f642413d1d4e8616317a3c6b0'),
    ('original_lei13874', 103071, '4fd5ddbc75e7dc56ab3c2d53c7abdcbb3eee46c894e18b5a3d07041e7cd244c3'),
)

ROTAS_IL2 = {
    "lexml": {"www.lexml.gov.br": ()},
    "normas_leg": {"normas.leg.br": ()},
    "camara_legislacao": {"www.camara.leg.br": ("/legislacao", "/legislacao/busca"), "www2.camara.leg.br": tuple(p for _, p, _, _ in NORMAS_CAMARA + TEXTOS_CAMARA)},
}
CONSULTAS_IL2 = {"camara_legislacao": {"www.camara.leg.br": ("/legislacao/busca",)}}


def test_il2_allowlist_exata_de_hosts_rotas_e_consultas():
    for fid in IDS_IL2:
        f = FONTES_SONDA[fid]
        assert {h: tuple(r) for h, r in f.rotas.items()} == ROTAS_IL2[fid], fid
        assert {h: tuple(c) for h, c in f.consultas.items()} == CONSULTAS_IL2.get(fid, {}), fid
        assert f.confirmacao == "A" and not f.hosts_b, fid
    assert {h for fid in IDS_IL2 for h in FONTES_SONDA[fid].hosts} == {
        "www.lexml.gov.br", "normas.leg.br", "www.camara.leg.br", "www2.camara.leg.br",
    }


def test_il2_nivel_a_so_com_pagina_oficial_lida_e_nada_de_terceiros_como_origem():
    for fid in IDS_IL2:
        f = FONTES_SONDA[fid]
        baixo = f.origem_hosts.lower()
        assert not any(t in baixo for t in ("br-eli", "pypi", "glama", "matematicsolutions")), fid
        for host in f.hosts:
            assert f"{host}=https://" in f.origem_hosts, (fid, host)
    # caminho só de busca ou de projeto de terceiros (nível B) não entra no catálogo
    todas = {r for fid in IDS_IL2 for rs in FONTES_SONDA[fid].rotas.values() for r in rs}
    assert not any(p in r for r in todas for p in ("/api/public", "/web/dou", "/norma/"))
    assert "pendência IL.2-b" in FONTES_SONDA["normas_leg"].nota and "br-eli-mcp" in FONTES_SONDA["normas_leg"].nota


def test_il2_inlabs_e_hosts_sem_endpoint_oficial_recusados_e_fora_do_catalogo():
    catalogados = {h for f in FONTES_SONDA.values() for h in f.hosts}
    for h in ("inlabs.in.gov.br", "dadosabertos.camara.leg.br", "projeto.lexml.gov.br", "www12.senado.leg.br"):
        assert h in HOSTS_RECUSADOS and h not in catalogados, h
    assert "login" in HOSTS_RECUSADOS["inlabs.in.gov.br"] and "sessão assistida" in HOSTS_RECUSADOS["inlabs.in.gov.br"]


@pytest.mark.parametrize("fid,url", [
    ("lexml", "https://www.lexml.gov.br/robots.txt"),
    ("camara_legislacao", "https://www.camara.leg.br/legislacao"),
])
def test_il2_rota_documentada_vai_ao_transporte(envios, tmp_path, fid, url):
    reg = captura.capturar(None, url=url, destino=tmp_path, sonda=True, chave="s", fonte_sonda=fid)
    assert not reg.unavailable and envios[0]["url"] == url and envios[0]["method"] == "GET"


@pytest.mark.parametrize("fid,url", [
    ("senado_legislacao", "https://legis.senado.leg.br/dadosabertos/legislacao/urn"),  # sem a extensão do catálogo
    ("senado_legislacao", "https://legis.senado.leg.br/dadosabertos/legislacao/urn.json/x"),
    ("senado_legislacao", "https://legis.senado.leg.br/dadosabertos/legislacao/535485.json"),  # rota por código
    ("senado_legislacao", "https://legis.senado.leg.br/dadosabertos/legislacao/LEI/6404/1976.json?v=3"),  # sem consulta
    ("senado_legislacao", "https://legis.senado.leg.br/dadosabertos/legislacao/tiposNorma"),
    ("senado_legislacao", "https://legis.senado.leg.br/dadosabertos/processo.json"),
    ("senado_legislacao", "https://legis.senado.leg.br/norma/535485/publicacao/15711526"),
    ("lexml", "https://www.lexml.gov.br/busca/SRU/"),
    ("lexml", "https://www.lexml.gov.br/urn/urn:lex:br:federal:lei:1976-12-15;6404"),  # resolvedor: sem página oficial
    ("lexml", "https://projeto.lexml.gov.br/documentacao"),
    ("normas_leg", "https://normas.leg.br/api/public/norma"),  # caminho só do br-eli-mcp
    ("normas_leg", "https://normas.leg.br/busca?q=lei+6404"),
    ("camara_legislacao", "https://www.camara.leg.br/legislacao?x=1"),
    ("camara_legislacao", "https://www.camara.leg.br/legislacao/pesquisa-avancada"),
    ("camara_legislacao", "https://www2.camara.leg.br/legin/fed/lei/1970-1979/lei-6404-15-dezembro-1976-540445-norma-pl.html"),
    ("camara_legislacao", "https://dadosabertos.camara.leg.br/api/v2/proposicoes"),
    ("dou", "https://www.in.gov.br/web/dou"),
    ("dou", "https://inlabs.in.gov.br/index.php"),
    ("dou", "https://inlabs.in.gov.br/robots.txt"),
])
def test_il2_caminho_nao_documentado_host_recusado_e_login_recusados_antes_da_rede(envios, tmp_path, fid, url):
    with pytest.raises(ValueError, match="barrada, sem sonda" if fid in FONTES_BARRADAS else "fora da allowlist da fonte-sonda"):
        captura.capturar(None, url=url, destino=tmp_path, sonda=True, chave="s", fonte_sonda=fid)
    assert envios == [] and not any(tmp_path.iterdir())


@pytest.mark.parametrize("path", ["/busca/SRU", "/busca/SRU?operation=searchRetrieve&query=a", "/sru", "/urn"])
def test_il2_lexml_rotas_proibidas_ou_sem_documentacao_recusadas(envios, tmp_path, path):
    with pytest.raises(ValueError, match="fora da allowlist da fonte-sonda"):
        captura.capturar(None, url=f"https://www.lexml.gov.br{path}", destino=tmp_path,
                         sonda=True, chave="s", fonte_sonda="lexml")
    assert envios == [] and not any(tmp_path.iterdir())


_BASE_MIMES = frozenset({"text/html", "application/json", "text/plain"})
MIMES_IL2 = {  # conjunto esperado por fonte, fixado aqui, independente do catálogo
    "lexml": _BASE_MIMES | {"application/xml", "text/xml"},
    "normas_leg": _BASE_MIMES,
    "camara_legislacao": _BASE_MIMES | {"application/pdf"},
}
HOSTS_IL2 = {fid: frozenset(r) for fid, r in ROTAS_IL2.items()}


def _divergencias_il2(fid: str, fonte: FonteSonda) -> list[str]:
    """Compara a fonte com as constantes deste arquivo (igualdade, não inclusão); vazio = fiel."""
    achados = []
    if fonte.mimes != MIMES_IL2[fid]:
        achados.append("mimes")
    if fonte.hosts != HOSTS_IL2[fid]:
        achados.append("hosts")
    if {h: tuple(r) for h, r in fonte.rotas.items()} != ROTAS_IL2[fid]:
        achados.append("rotas")
    if {h: tuple(c) for h, c in fonte.consultas.items()} != CONSULTAS_IL2.get(fid, {}):
        achados.append("consultas")
    return achados


@pytest.mark.parametrize("fid", IDS_IL2)
def test_il2_mime_e_demais_atributos_iguais_as_constantes_do_teste(fid):
    assert _divergencias_il2(fid, FONTES_SONDA[fid]) == []
    assert FONTES_SONDA[fid].mimes == MIMES_IL2[fid]  # igualdade: nem a mais, nem a menos


@pytest.mark.parametrize("fid", IDS_IL2)
def test_il2_mutantes_de_mime_hosts_rotas_e_consulta_sao_rejeitados(fid):
    f = FONTES_SONDA[fid]
    host = sorted(f.hosts)[0]
    mutantes = {
        "mimes": [dataclasses.replace(f, mimes=f.mimes | {"application/octet-stream"}),
                  dataclasses.replace(f, mimes=f.mimes ^ {"application/pdf"}),
                  dataclasses.replace(f, mimes=frozenset(f.mimes - {"application/json"}))],
        "hosts": [dataclasses.replace(f, hosts=f.hosts | {"extra.leg.br"}, rotas={**f.rotas, "extra.leg.br": ()},
                                      origem_hosts=f.origem_hosts + "; extra.leg.br=https://extra.leg.br/")],
        "rotas": [dataclasses.replace(f, rotas={**f.rotas, host: (*f.rotas[host], "/extra")})],
        "consultas": [],
    }
    if f.consultas:  # retirar a consulta declarada diverge
        mutantes["consultas"].append(dataclasses.replace(f, consultas={}))
    com_rota = [h for h, r in f.rotas.items() if r and h not in f.consultas]
    if com_rota:  # liberar consulta em rota que não a admite diverge
        mutantes["consultas"].append(dataclasses.replace(
            f, consultas={**f.consultas, com_rota[0]: f.rotas[com_rota[0]]}))
    if fid == "camara_legislacao":
        mutantes["rotas"].append(dataclasses.replace(
            f, rotas={**f.rotas, "www.camara.leg.br": ("/legislacao",)}, consultas={}))
        mutantes["consultas"].append(dataclasses.replace(
            f, consultas={"www.camara.leg.br": ("/legislacao", "/legislacao/busca")}))
    if fid == "lexml":  # única com XML: retirar o XML também diverge
        mutantes["mimes"].append(dataclasses.replace(f, mimes=frozenset(f.mimes - {"text/xml"})))
    for atributo, lista in mutantes.items():
        for m in lista:
            assert atributo in _divergencias_il2(fid, m), (fid, atributo)
    # o MIME adicional (octet-stream) é acusado exatamente como "mimes"
    assert _divergencias_il2(fid, mutantes["mimes"][0]) == ["mimes"]


def test_il2_mutante_de_mime_chega_ao_transporte_e_o_teste_de_repasse_o_acusa(monkeypatch, envios, tmp_path):
    from types import MappingProxyType

    f = FONTES_SONDA["camara_legislacao"]
    mutante = dataclasses.replace(f, mimes=f.mimes | {"application/octet-stream"})
    monkeypatch.setattr(captura, "FONTES_SONDA", MappingProxyType({**FONTES_SONDA, f.id: mutante}))
    captura.capturar(None, url="https://www.camara.leg.br/legislacao",
                     destino=tmp_path, sonda=True, chave="mut", fonte_sonda=f.id)
    assert envios[-1]["allowed_mimes"] != MIMES_IL2[f.id]  # a comparação com a constante o pega


def _rota_de_cada_host(fid):
    return [f"https://{h}{(rs or ('/robots.txt',))[0]}" for h, rs in sorted(ROTAS_IL2[fid].items())]


@pytest.mark.parametrize("fid", IDS_IL2)
def test_il2_mimes_hosts_e_caminhos_passados_ao_transporte_conferem_com_as_constantes(envios, tmp_path, fid):
    for url in _rota_de_cada_host(fid):
        captura.capturar(None, url=url, destino=tmp_path, sonda=True, chave=f"m{len(envios)}", fonte_sonda=fid)
        visto = envios[-1]
        if url.endswith("/robots.txt"):
            assert visto["allowed_mimes"] == frozenset({"text/plain"})
            assert visto["allowed_path_prefixes"] == {h: ("/robots.txt",) for h in HOSTS_IL2[fid]}
        else:
            assert visto["allowed_mimes"] == MIMES_IL2[fid]  # constante do teste, não o catálogo
            assert visto["allowed_path_prefixes"] == {h: (rs or ("/robots.txt",)) for h, rs in ROTAS_IL2[fid].items()}
        assert visto["allowed_hosts"] == HOSTS_IL2[fid] and visto["max_redirects"] == 0


@pytest.mark.repositorio
def test_il2_roteiro_tem_secao_e_robots_primeiro_para_cada_fonte():
    texto = ROTEIRO.read_text(encoding="utf-8")
    for fid in IDS_IL2:
        assert f"### {fid}:" in texto, fid
    por_fonte = {fid: [c for c in _comandos_do_roteiro() if c[1] == fid] for fid in IDS_IL2}
    for fid, cmds in por_fonte.items():
        assert cmds and cmds[0][4].endswith("/robots.txt") and not any(c[5] for c in cmds), fid  # nenhum host B
    for fid in ("senado_legislacao", "dou"):
        assert f"### {fid}:" in texto
        secao = texto.split(f"### {fid}:", 1)[1].split("\n##", 1)[0]
        assert "04/11/2026" in secao and "http_403" in secao and "recusa_identificado" in secao
        assert not any(c[1] == fid for c in _comandos_do_roteiro())


@pytest.mark.repositorio
def test_il2_roteiro_inlabs_so_como_sessao_assistida_e_b_sem_comando():
    texto = ROTEIRO.read_text(encoding="utf-8")
    secao = texto[texto.index("### dou:"):texto.index("## TJSP e TJDFT")]
    assert "inlabs.in.gov.br" in secao and "sessão assistida" in secao and "nunca automatizada" in secao
    assert not any("inlabs" in ln for ln in secao.splitlines() if ln.startswith("python "))
    assert "decisão 0067" in secao
    assert all("inlabs" not in c[4] for c in _comandos_do_roteiro() if c[4])


@pytest.mark.parametrize("fid,host,rota", [
    ("senado_legislacao", "legis.senado.leg.br", "/dadosabertos/legislacao/LEI/6404/1976.json"),
    ("dou", "www.in.gov.br", "/web/dou"),
])
@pytest.mark.parametrize("confirmado", [False, True])
def test_il2_barreiras_reais_recusadas_por_fonte_e_por_host_antes_da_rede(envios, tmp_path, fid, host, rota, confirmado):
    assert "04/11/2026" in FONTES_BARRADAS[fid] and "http_403" in FONTES_BARRADAS[fid]
    assert "recusa_identificado" in FONTES_BARRADAS[fid]
    assert HOSTS_RECUSADOS[host] == FONTES_BARRADAS[fid]
    for path in ("/robots.txt", rota):
        for fonte in (fid, "camara_legislacao"):
            with pytest.raises(ValueError, match="barrada, sem sonda" if fonte == fid else "fora da allowlist"):
                captura.capturar(None, url=f"https://{host}{path}", destino=tmp_path,
                                 sonda=True, chave="b", fonte_sonda=fonte, confirmado_por_titular=confirmado)
    assert envios == [] and not any(tmp_path.iterdir())


@pytest.mark.repositorio
def test_il2_evidencias_locais_integras_e_sanitizadas():
    base = ROTEIRO.parent / "auditoria/1.4.0/il2a-sondas"
    registros = sorted(base.rglob("*.captura.json"))
    assert len(registros) == 21
    assert {r.name for r in registros if r.stem.startswith("camara_legislacao_textos_")} == {
        f"camara_legislacao_textos_{key}.captura.json" for key, _, _ in CAPTURAS_TEXTOS_CAMARA
    }
    corpos = set()
    for registro in registros:
        texto = registro.read_text(encoding="utf-8")
        assert not re.search(r"(?<![A-Za-z])[A-Za-z]:[\\/]", texto)
        r = json.loads(texto)
        assert r["fonte_sonda"] == registro.parent.name
        assert r["capturado_em"].startswith("2026-11-05" if registro.stem.startswith(("camara_legislacao_busca_", "camara_legislacao_norma_", "camara_legislacao_textos_")) else "2026-11-04") and r["sonda"] is True
        if r["unavailable"]:
            assert r["motivo"] == "http_403" and r["categoria"] == "recusa_identificado"
            assert r["evidencia"]["status"] == 403 and r["arquivo"] is None
        elif r["content_type"] == "text/plain":
            corpo = registro.parent / r["arquivo"]
            data = corpo.read_bytes()
            assert len(data) == r["bytes"] and hashlib.sha256(data).hexdigest() == r["sha256"]
            corpos.add(corpo)
        elif registro.stem.startswith("camara_legislacao_textos_"):
            key, size, sha = next(c for c in CAPTURAS_TEXTOS_CAMARA
                                  if registro.name == f"camara_legislacao_textos_{c[0]}.captura.json")
            pdf = key == "anexo_lc123"
            assert r["status"] == 200 and r["content_type"] == ("application/pdf" if pdf else "text/html")
            assert (r["bytes"], r["sha256"]) == (size, sha)
            assert r["url"] == r["url_final"] == "https://www2.camara.leg.br" + next(c[1] for c in TEXTOS_CAMARA if c[0] == key)
            assert r["arquivo"] == f"camara_legislacao_textos_{key}.{'pdf' if pdf else 'html'}"
            assert not (registro.parent / r["arquivo"]).exists()
        elif registro.stem.startswith("camara_legislacao_norma_"):
            key, size, sha = next(c for c in CAPTURAS_NORMAS_CAMARA
                                  if registro.name == f"camara_legislacao_norma_{c[0]}.captura.json")
            assert r["status"] == 200 and r["content_type"] == "text/html"
            assert (r["bytes"], r["sha256"]) == (size, sha)
            assert r["url"] == r["url_final"] == "https://www2.camara.leg.br" + next(c[1] for c in NORMAS_CAMARA if c[0] == key)
            assert r["arquivo"] == f"camara_legislacao_norma_{key}.html"
            assert not (registro.parent / r["arquivo"]).exists()
        elif registro.stem.startswith("camara_legislacao_busca_"):
            caso = next(c for c in NORMAS_CAMARA if registro.name == f"camara_legislacao_busca_{c[0]}.captura.json")
            assert r["status"] == 200 and r["content_type"] == "text/html"
            assert (r["bytes"], r["sha256"]) == caso[2:]
            assert r["arquivo"] == f"camara_legislacao_busca_{caso[0]}.html"
            assert not (registro.parent / r["arquivo"]).exists()
        else:
            assert r["fonte_sonda"] == "camara_legislacao" and r["bytes"] == 59842
            assert r["sha256"] == "2735440e8cc2c54f71b610af8b0dd38fcb0a46110ef1b9b667b20cc90bda49f1"
            assert not (registro.parent / r["arquivo"]).exists()
    assert len(corpos) == 4
    assert set(base.rglob("*.txt")) == corpos
    lexml = (base / "lexml/lexml_robots.txt").read_text(encoding="utf-8")
    assert "Disallow: /busca/" in lexml and "Crawl-delay: 5" in lexml
    assert "Allow: /urn" in lexml and "Allow: /sru" in lexml


# B1: a recusa pertence ao instrumento inteiro, inclusive aliases e captura de fixture.
ROTAS_SENADO_BARRADAS = (
    "/robots.txt", "/dadosabertos/legislacao/lista", "/sigen/api/catalogo/basico", "/norma/123",
)


@pytest.fixture
def transporte_proibido(monkeypatch):
    def sentinela(*args, **kwargs):
        pytest.fail("host barrado chegou ao transporte")
    monkeypatch.setattr(httputil, "transport_fetch", sentinela)


@pytest.mark.parametrize("rota", ROTAS_SENADO_BARRADAS)
@pytest.mark.parametrize("ua", ["conector", "identificado"])
@pytest.mark.parametrize("sonda", [False, True])
def test_b1_senado_api_recusa_alias_sem_transporte(transporte_proibido, tmp_path, rota, ua, sonda):
    with pytest.raises(ValueError, match="host barrado.*legis.senado.leg.br"):
        captura.capturar("senado", url=f"https://legis.senado.leg.br{rota}",
                         destino=tmp_path, sonda=sonda, user_agent=ua, chave="b1")
    assert not any(tmp_path.iterdir())


@pytest.mark.repositorio
@pytest.mark.parametrize("rota", ROTAS_SENADO_BARRADAS)
@pytest.mark.parametrize("ua", ["conector", "identificado"])
@pytest.mark.parametrize("sonda", [False, True])
def test_b1_senado_cli_recusa_alias_sem_transporte(transporte_proibido, tmp_path, capsys, monkeypatch, rota, ua, sonda):
    cli = _cli()
    # Temporário herdável: Python 3.14 usa ACL privada incompatível com o token restrito Windows.
    destino = tmp_path / "captura"
    destino.mkdir()
    monkeypatch.setattr(cli.tempfile, "TemporaryDirectory", lambda: contextlib.nullcontext(destino))
    argv = ["--conector", "senado", "--url", f"https://legis.senado.leg.br{rota}",
            "--user-agent", ua, "--chave", "b1"]
    if sonda:
        argv += ["--sonda", "--saida", str(tmp_path)]
    assert cli.main(argv) == 2
    assert "host barrado legis.senado.leg.br" in capsys.readouterr().err
    assert not any(destino.iterdir())
    assert set(tmp_path.iterdir()) == {destino}


@pytest.mark.parametrize("rota", ["/robots.txt", "/consulta"])
def test_b1_dou_sem_alias_em_conector_e_recusado_na_api(transporte_proibido, tmp_path, rota):
    assert all("www.in.gov.br" not in c.hosts for c in registry().values())
    with pytest.raises(ValueError, match="barrada, sem sonda"):
        captura.capturar(None, fonte_sonda="dou", url=f"https://www.in.gov.br{rota}",
                         destino=tmp_path, sonda=True)
    for conector in registry():
        with pytest.raises(ValueError):
            captura.capturar(conector, url=f"https://www.in.gov.br{rota}", destino=tmp_path, sonda=False)
    assert not any(tmp_path.iterdir())


def test_b1_allowlist_de_captura_exclui_host_barrado_para_redirecionamento(envios):
    # Plano controlado para isolar a política do instrumento das rotas do conector.
    captura._buscar({
        "hosts": registry()["senado"].hosts, "path_prefixes": {"normas.leg.br": ("/api/",)},
        "mimes": frozenset({"application/json"}), "user_agent": registry()["senado"].user_agent,
        "etapas": [{"url": "https://normas.leg.br/api/teste", "metodo": "GET", "body": None, "headers": {}}],
    }, "conector")
    assert envios[-1]["allowed_hosts"] == frozenset({"normas.leg.br"})
    assert registry()["senado"].hosts == frozenset({"normas.leg.br", "legis.senado.leg.br"})


def test_b1_consulta_valida_todas_as_etapas_antes_do_primeiro_pedido(transporte_proibido, monkeypatch, tmp_path):
    def plano(consulta):
        return {
            "url": "https://normas.leg.br/api/teste", "metodo": "GET", "parametros": consulta,
            "etapas": [{"url": url, "metodo": "GET", "body": None, "headers": {}} for url in (
                "https://normas.leg.br/api/teste", "https://legis.senado.leg.br/dadosabertos/legislacao/lista")],
        }
    monkeypatch.setitem(captura._CONSULTAS, "senado", plano)
    with pytest.raises(ValueError, match="host barrado.*legis.senado.leg.br"):
        captura.capturar("senado", consulta={}, destino=tmp_path, sonda=False)
    assert not any(tmp_path.iterdir())


# IL.2-b.1: contrato do formulário observado na captura, sem depender do catálogo.
CAMPOS_CAMARA = frozenset({"abrangencia", "tipo", "numero", "ano", "geral"})
CASOS_BUSCA_CAMARA = (
    ("lei6404", "Lei Ordinária", "6404", "1976"),
    ("lc123", "Lei Complementar", "123", "2006"),
    ("lei13874", "Lei Ordinária", "13874", "2019"),
)


def _conferir_buscas_camara(comandos):
    esperados = {f"camara_legislacao_busca_{k}": {
        "abrangencia": ["Legislação Federal"], "tipo": [tipo],
        "numero": [numero], "ano": [ano], "geral": [""],
    } for k, tipo, numero, ano in CASOS_BUSCA_CAMARA}
    assert {c[3] for c in comandos} == set(esperados)
    for _, fid, _, chave, url, bloqueado in comandos:
        alvo = urlsplit(url)
        assert fid == "camara_legislacao" and not bloqueado
        assert alvo.scheme == "https" and alvo.netloc == "www.camara.leg.br"
        assert alvo.path == "/legislacao/busca"
        campos = parse_qs(alvo.query, keep_blank_values=True)
        assert set(campos) == CAMPOS_CAMARA
        assert campos == esperados[chave]


@pytest.mark.repositorio
def test_il2b_buscas_do_roteiro_conferem_e_chegam_por_get_ao_transporte(envios, tmp_path):
    comandos = [c for c in _comandos_do_roteiro() if c[3].startswith("camara_legislacao_busca_")]
    _conferir_buscas_camara(comandos)
    for _, fid, _, chave, url, _ in comandos:
        reg = captura.capturar(None, url=url, destino=tmp_path, sonda=True, chave=chave, fonte_sonda=fid)
        enviado = envios[-1]
        assert not reg.unavailable and reg.confirmacao_host == "A"
        assert enviado["url"] == url and enviado["method"] == "GET" and enviado["body"] is None
        assert enviado["allowed_hosts"] == HOSTS_IL2[fid]
        assert enviado["allowed_mimes"] == MIMES_IL2[fid]
        assert enviado["allowed_path_prefixes"] == {
            h: (rs or ("/robots.txt",)) for h, rs in ROTAS_IL2[fid].items()}
        assert enviado["max_redirects"] == 0


@pytest.mark.repositorio
@pytest.mark.parametrize("antes,depois", [("numero=", "number="), ("tipo=", "type="),
                                         ("ano=", "year="), ("geral=", "assunto="),
                                         ("abrangencia=", "escopo="),
                                         ("/legislacao/busca?", "/legislacao/busca/?"),
                                         ("www.camara.leg.br", "www2.camara.leg.br")])
def test_il2b_mutantes_de_campos_e_destino_do_roteiro_falham(antes, depois):
    comandos = [c for c in _comandos_do_roteiro() if c[3].startswith("camara_legislacao_busca_")]
    _conferir_buscas_camara(comandos)  # controle positivo
    mutantes = [(*c[:4], c[4].replace(antes, depois), c[5]) for c in comandos]
    with pytest.raises(AssertionError):
        _conferir_buscas_camara(mutantes)


@pytest.mark.parametrize("url", [
    "https://www.camara.leg.br/legislacao/busca/?numero=6404",
    "https://www.camara.leg.br/legislacao/busca.bak?numero=6404",
    "https://www.camara.leg.br/legislacao/busca/extra?numero=6404",
    "https://www2.camara.leg.br/legislacao/busca?numero=6404",
])
def test_il2b_variantes_da_rota_de_busca_recusadas_antes_do_transporte(envios, tmp_path, url):
    with pytest.raises(ValueError, match="fora da allowlist da fonte-sonda"):
        captura.capturar(None, url=url, destino=tmp_path, sonda=True, chave="b", fonte_sonda="camara_legislacao")
    assert envios == [] and not any(tmp_path.iterdir())


def test_il2b_proveniencia_da_busca_aponta_para_captura():
    f = FONTES_SONDA["camara_legislacao"]
    assert f.confirmacao == "A" and not f.hosts_b
    assert "https://www.camara.leg.br/legislacao (captura de 04/11/2026" in f.origem_hosts
    assert "camara_legislacao_pesquisa.html" in f.origem_hosts
    assert "2735440e8cc2c54f71b610af8b0dd38fcb0a46110ef1b9b667b20cc90bda49f1" in f.origem_hosts
    assert "GET implícito" in f.nota and "IL.2-b.2" in f.nota
    assert "campos abrangencia, tipo, numero, ano, geral" in f.nota


# IL.2-b.2: somente as três páginas publicadas, sem consulta nem prefixo.
def _conferir_normas_camara(comandos):
    esperados = {f"camara_legislacao_norma_{k}": f"https://www2.camara.leg.br{p}"
                 for k, p, _, _ in NORMAS_CAMARA}
    assert len(comandos) == 3 and {c[3] for c in comandos} == set(esperados)
    for _, fid, _, chave, url, bloqueado in comandos:
        assert fid == "camara_legislacao" and not bloqueado
        assert url == esperados[chave]


@pytest.mark.repositorio
def test_il2b2_roteiro_exato_e_repasse_ao_transporte(envios, tmp_path):
    comandos = [c for c in _comandos_do_roteiro() if c[3].startswith("camara_legislacao_norma_")]
    _conferir_normas_camara(comandos)
    for _, fid, _, chave, url, _ in comandos:
        reg = captura.capturar(None, url=url, destino=tmp_path, sonda=True, chave=chave, fonte_sonda=fid)
        enviado = envios[-1]
        assert not reg.unavailable and reg.confirmacao_host == "A"
        assert enviado["url"] == url and enviado["method"] == "GET" and enviado["body"] is None
        assert enviado["allowed_hosts"] == HOSTS_IL2[fid]
        assert enviado["allowed_mimes"] == MIMES_IL2[fid]
        assert enviado["allowed_path_prefixes"] == ROTAS_IL2[fid]
        assert enviado["max_redirects"] == 0
    texto = ROTEIRO.read_text(encoding="utf-8")
    assert "IL.2-b.3: links relativos resolvidos" in texto


@pytest.mark.parametrize("caso", NORMAS_CAMARA)
@pytest.mark.parametrize("variante", ["?x=1", "/", ".bak", "/extra", "host", "id", "publicacao", "atualizado", "anexo", "prefixo"])
def test_il2b2_variantes_recusadas_antes_do_transporte(envios, tmp_path, caso, variante):
    path = caso[1]
    host = "www2.camara.leg.br"
    if variante == "host":
        host = "www.camara.leg.br"
    elif variante == "id":
        path = path.replace("-norma-pl.html", "0-norma-pl.html")
    elif variante in ("publicacao", "atualizado", "anexo"):
        path = path.replace("-norma-pl.html", {"publicacao": "-publicacaooriginal-999999-pl.html",
                            "atualizado": "-textoatualizado-pl.html", "anexo": "-anexo-inexistente-pl.pdf"}[variante])
    elif variante == "prefixo":
        path = "/legin/"
    else:
        path += variante
    with pytest.raises(ValueError, match="fora da allowlist da fonte-sonda"):
        captura.capturar(None, url=f"https://{host}{path}", destino=tmp_path, sonda=True,
                         chave="n", fonte_sonda="camara_legislacao")
    assert envios == [] and not any(tmp_path.iterdir())


@pytest.mark.parametrize("caso", NORMAS_CAMARA)
def test_il2b2_mutantes_catalogo_rejeitados_pela_constante(caso):
    f = FONTES_SONDA["camara_legislacao"]
    assert _divergencias_il2(f.id, f) == []  # controle positivo
    path = caso[1]
    rotas = f.rotas["www2.camara.leg.br"]
    for caminhos in (tuple(p for p in rotas if p != path), (*rotas, "/legin/"),
                     tuple(p.replace("-norma-pl.html", "0-norma-pl.html") if p == path else p for p in rotas)):
        m = dataclasses.replace(f, rotas={**f.rotas, "www2.camara.leg.br": caminhos})
        assert _divergencias_il2(f.id, m) == ["rotas"]
    m = dataclasses.replace(f, consultas={**f.consultas, "www2.camara.leg.br": (path,)})
    assert _divergencias_il2(f.id, m) == ["consultas"]


@pytest.mark.repositorio
@pytest.mark.parametrize("variante", ["host", "id", "query", "prefixo", "remocao"])
def test_il2b2_mutantes_do_roteiro_falham(variante):
    comandos = [c for c in _comandos_do_roteiro() if c[3].startswith("camara_legislacao_norma_")]
    _conferir_normas_camara(comandos)
    if variante == "remocao":
        comandos = comandos[:-1]
    else:
        c = comandos[0]
        url = c[4]
        url = {"host": url.replace("www2.", "www."), "id": url.replace("368447", "540445"),
               "query": url + "?x=1", "prefixo": "https://www2.camara.leg.br/legin/"}[variante]
        comandos[0] = (*c[:4], url, c[5])
    with pytest.raises(AssertionError):
        _conferir_normas_camara(comandos)


def _conferir_proveniencia_normas(fonte):
    assert fonte.confirmacao == "A" and not fonte.hosts_b
    for key, path, _, sha in NORMAS_CAMARA:
        assert f"{path} publicado em camara_legislacao_busca_{key}.html, SHA-256 {sha}" in fonte.origem_hosts


@pytest.mark.parametrize("caso", NORMAS_CAMARA)
def test_il2b2_proveniencia_e_mutantes(caso):
    f = FONTES_SONDA["camara_legislacao"]
    _conferir_proveniencia_normas(f)
    for valor in (caso[1], f"camara_legislacao_busca_{caso[0]}.html", caso[3]):
        with pytest.raises(AssertionError):
            _conferir_proveniencia_normas(dataclasses.replace(f, origem_hosts=f.origem_hosts.replace(valor, "ausente")))


def _conferir_robots_normas(texto):
    # Conferência offline da evidência, não implementação de robots no instrumento.
    assert [l.lower() for l in texto.splitlines() if l.lower().startswith("user-agent:")] == ["user-agent: *"]
    regras = [l.split(":", 1)[1].strip() for l in texto.splitlines() if l.lower().startswith("disallow:")]
    for _, path, _, _ in NORMAS_CAMARA:
        for regra in regras:
            if regra:
                padrao = "^" + re.escape(regra.rstrip("$")).replace(r"\*", ".*") + ("$" if regra.endswith("$") else "")
                assert not re.match(padrao, path), (regra, path)


@pytest.mark.repositorio
def test_il2b2_robots_preservado_e_mutantes_de_disallow():
    data = (ROTEIRO.parent / "auditoria/1.4.0/il2a-sondas/camara_legislacao/camara_legislacao_robots_legin.txt").read_bytes()
    assert len(data) == 5809
    assert hashlib.sha256(data).hexdigest() == "b725bf41f0e293419518714b83edb1c2de6728c5156cba037b848ab0788bee8f"
    texto = data.decode("utf-8")
    _conferir_robots_normas(texto)
    for regra in ("/legin/", "/*norma-pl.html$", *(p for _, p, _, _ in NORMAS_CAMARA)):
        with pytest.raises(AssertionError):
            _conferir_robots_normas(texto + f"\nDisallow: {regra}\n")


def _conferir_textos_camara(comandos):
    esperados = {f"camara_legislacao_textos_{k}": "https://www2.camara.leg.br" + p
                 for k, p, _, _ in TEXTOS_CAMARA}
    assert len(comandos) == 8 and {c[3] for c in comandos} == set(esperados)
    for _, fid, destino, chave, url, bloqueado in comandos:
        assert fid == "camara_legislacao" and not bloqueado
        # O parser do roteiro já exige o prefixo C:/dev/fv14-sondas/ e devolve só a pasta.
        assert destino == "camara_legislacao"
        assert url == esperados[chave]


@pytest.mark.repositorio
def test_il2b3_roteiro_e_repasse_independentes(envios, tmp_path):
    comandos = [c for c in _comandos_do_roteiro() if c[3].startswith("camara_legislacao_textos_")]
    _conferir_textos_camara(comandos)
    for _, fid, _, chave, url, _ in comandos:
        reg = captura.capturar(None, url=url, destino=tmp_path, sonda=True, chave=chave, fonte_sonda=fid)
        enviado = envios[-1]
        assert not reg.unavailable and reg.confirmacao_host == "A"
        assert enviado["url"] == url and enviado["method"] == "GET" and enviado["body"] is None
        assert enviado["allowed_hosts"] == HOSTS_IL2[fid]
        assert enviado["allowed_mimes"] == MIMES_IL2[fid]
        assert enviado["allowed_path_prefixes"] == ROTAS_IL2[fid]
        assert enviado["max_redirects"] == 0


@pytest.mark.parametrize("caso", TEXTOS_CAMARA)
@pytest.mark.parametrize("variante", ["?x=1", "/", ".bak", "/extra", "host", "id"])
def test_il2b3_variantes_recusadas(envios, tmp_path, caso, variante):
    host, path = "www2.camara.leg.br", caso[1]
    if variante == "host":
        host = "www.camara.leg.br"
    elif variante == "id":
        path = path.replace("-pl.", "0-pl.").replace("-pe.", "0-pe.")
    else:
        path += variante
    with pytest.raises(ValueError, match="fora da allowlist da fonte-sonda"):
        captura.capturar(None, url=f"https://{host}{path}", destino=tmp_path,
                         sonda=True, chave="t", fonte_sonda="camara_legislacao")
    assert not envios and not any(tmp_path.iterdir())


def _conferir_proveniencia_textos(fonte):
    assert fonte.confirmacao == "A" and not fonte.hosts_b
    for _, path, key, sha in TEXTOS_CAMARA:
        assert f"{path} publicado em camara_legislacao_norma_{key}.html, SHA-256 {sha}" in fonte.origem_hosts


@pytest.mark.parametrize("caso", TEXTOS_CAMARA)
def test_il2b3_mutantes_catalogo_e_proveniencia(caso):
    f = FONTES_SONDA["camara_legislacao"]
    assert _divergencias_il2(f.id, f) == []
    _conferir_proveniencia_textos(f)
    _, path, key, sha = caso
    rotas = f.rotas["www2.camara.leg.br"]
    for caminhos in (tuple(p for p in rotas if p != path), (*rotas, "/legin/"),
                     tuple(p + ".bak" if p == path else p for p in rotas)):
        m = dataclasses.replace(f, rotas={**f.rotas, "www2.camara.leg.br": caminhos})
        assert _divergencias_il2(f.id, m) == ["rotas"]
    m = dataclasses.replace(f, consultas={**f.consultas, "www2.camara.leg.br": (path,)})
    assert _divergencias_il2(f.id, m) == ["consultas"]
    for valor in (path, f"camara_legislacao_norma_{key}.html", sha):
        with pytest.raises(AssertionError):
            _conferir_proveniencia_textos(dataclasses.replace(f, origem_hosts=f.origem_hosts.replace(valor, "ausente")))


@pytest.mark.repositorio
@pytest.mark.parametrize("variante", ["host", "query", "id", "prefixo", "chave", "destino", "remocao"])
def test_il2b3_mutantes_roteiro(variante):
    comandos = [c for c in _comandos_do_roteiro() if c[3].startswith("camara_legislacao_textos_")]
    _conferir_textos_camara(comandos)
    if variante == "remocao":
        comandos = comandos[:-1]
    else:
        c = list(comandos[0])
        if variante == "chave":
            c[3] += "_errada"
        elif variante == "destino":
            c[2] = "tests/fixtures"
        else:
            c[4] = {"host": c[4].replace("www2.", "www."), "query": c[4] + "?x=1",
                    "id": c[4].replace("368447", "540445"),
                    "prefixo": "https://www2.camara.leg.br/legin/"}[variante]
        comandos[0] = tuple(c)
    with pytest.raises(AssertionError):
        _conferir_textos_camara(comandos)


def _conferir_robots_textos(texto):
    assert [l.lower() for l in texto.splitlines() if l.lower().startswith("user-agent:")] == ["user-agent: *"]
    regras = [l.split(":", 1)[1].strip() for l in texto.splitlines() if l.lower().startswith("disallow:")]
    for _, path, _, _ in TEXTOS_CAMARA:
        for regra in regras:
            if regra:
                padrao = "^" + re.escape(regra.rstrip("$")).replace(r"\*", ".*") + ("$" if regra.endswith("$") else "")
                assert not re.match(padrao, path), (regra, path)


@pytest.mark.repositorio
def test_il2b3_robots_e_mutantes():
    data = (ROTEIRO.parent / "auditoria/1.4.0/il2a-sondas/camara_legislacao/camara_legislacao_robots_legin.txt").read_bytes()
    assert hashlib.sha256(data).hexdigest() == "b725bf41f0e293419518714b83edb1c2de6728c5156cba037b848ab0788bee8f"
    texto = data.decode("utf-8")
    _conferir_robots_textos(texto)
    for regra in ("/legin/", "/*normaatualizada*", "/*anexo-pl.pdf$", *(p for _, p, _, _ in TEXTOS_CAMARA)):
        with pytest.raises(AssertionError):
            _conferir_robots_textos(texto + f"\nDisallow: {regra}\n")
