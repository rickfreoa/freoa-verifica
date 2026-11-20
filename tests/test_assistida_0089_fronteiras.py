"""§3.13: fecho transitivo de imports e execução das entradas não interativas."""

import ast
import asyncio
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

from freoa_verifica import bateria, cli, transport
from freoa_verifica.assistida import ambiente, cdp, sessao
from freoa_verifica.assistida.sessao import executar as executar_sessao
from freoa_verifica.service import Verifica


@pytest.mark.repositorio
def test_item13_ast_fecho_transitivo_sem_porta_ou_adaptador():
    raiz = Path(__file__).parents[1] / "freoa_verifica"
    arvores = {}
    for arquivo in raiz.rglob("*.py"):
        partes = arquivo.relative_to(raiz.parent).with_suffix("").parts
        nome = ".".join(partes[:-1] if partes[-1] == "__init__" else partes)
        arvores[nome] = ast.parse(arquivo.read_text(encoding="utf-8-sig"))
    arestas = {}
    for nome, arvore in arvores.items():
        imports = set()
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                imports.update(a.name for a in no.names)
            elif isinstance(no, ast.ImportFrom):
                modulo = no.module or ""
                if no.level:
                    pacote = (
                        nome
                        if (raiz.parent / nome.replace(".", "/")).is_dir()
                        else nome.rpartition(".")[0]
                    )
                    modulo = importlib.util.resolve_name(
                        "." * no.level + modulo, pacote
                    )
                imports.add(modulo)
                imports.update(modulo + "." + a.name for a in no.names)
        arestas[nome] = imports & arvores.keys()
    visitados = set()
    pendentes = [
        "freoa_verifica." + n
        for n in ("mcp_server", "rest", "service", "bateria", "semente")
    ]
    while pendentes:
        nome = pendentes.pop()
        if nome in visitados:
            continue
        visitados.add(nome)
        pendentes.extend(arestas[nome] - visitados)
    assert (
        len(visitados) > 30
    )  # Prova transitiva, não grep só nos cinco pontos de entrada.
    assert (
        not {"freoa_verifica.assistida.cdp", "freoa_verifica.assistida.sessao"}
        & visitados
    )
    for nome in visitados:
        for no in ast.walk(arvores[nome]):
            if isinstance(no, ast.ImportFrom):
                assert not any(
                    a.name in {"capturar_assistida", "AdaptadorCDP", "lancar_pipe"}
                    for a in no.names
                ), nome
            if isinstance(no, ast.Call):
                func = no.func
                chamado = (
                    func.attr
                    if isinstance(func, ast.Attribute)
                    else func.id
                    if isinstance(func, ast.Name)
                    else ""
                )
                assert chamado not in {
                    "capturar_assistida",
                    "AdaptadorCDP",
                    "lancar_pipe",
                }, nome
                if (
                    chamado in {"__import__", "import_module"}
                    and no.args
                    and isinstance(no.args[0], ast.Constant)
                ):
                    assert "assistida" not in str(no.args[0].value), nome


@pytest.fixture
def proibidos(monkeypatch, tmp_path):
    monkeypatch.setenv("FV_OFFLINE", "1")
    from freoa_verifica.assistida import indicacao
    from tests.assistida_0089_util import URL

    # As entradas também veem barreira recente, que só pode produzir indicação.
    with Verifica(home=tmp_path) as svc:
        for operacao in (
            "buscar_legislacao",
            "verificar_citacao",
            "verificar_texto",
            "obter_dispositivo",
        ):
            indicacao.atualizar(
                svc.conn,
                operacao,
                {
                    "planalto": {
                        "em": datetime.now(timezone.utc).isoformat(),
                        "prova": "0048",
                        "alvo": URL,
                    }
                },
            )
    chamados = []

    def vedado(*args, **kwargs):
        chamados.append(True)
        pytest.fail("entrada não interativa alcançou sessão/porta/adaptador")

    monkeypatch.setattr(transport, "capturar_assistida", vedado)
    monkeypatch.setattr(cdp.AdaptadorCDP, "__init__", vedado)
    monkeypatch.setattr(ambiente, "lancar_pipe", vedado)
    monkeypatch.setattr(sessao, "executar", vedado)
    yield chamados
    assert chamados == []


def test_item13_todas_ferramentas_mcp_executadas(tmp_path, monkeypatch, proibidos):
    from freoa_verifica import mcp_server as ms

    with Verifica(home=tmp_path) as svc:
        monkeypatch.setattr(ms, "_service", lambda *a, **kw: svc)
        server = ms.create_mcp(home=str(tmp_path))
        argumentos = {
            "buscar_legislacao": {"q": "lei 6404", "fonte": "planalto"},
            "resolver_citacao": {"citacao": "art. 1º da Lei 6.404/1976"},
            "obter_dispositivo": {"citacao": "art. 1º da Lei 6.404/1976"},
            "historico_dispositivo": {"citacao": "art. 1º da Lei 6.404/1976"},
            "verificar_citacao": {"citacao": "art. 1º da Lei 6.404/1976"},
            "verificar_texto": {"texto": "Conforme art. 1º da Lei 6.404/1976."},
            "pesquisar_jurisprudencia": {"q": "contrato", "tribunais": ["stj"]},
            "obter_decisao": {"id": "sintetica-ausente"},
            "buscar_normas_cvm": {"q": "160"},
            "buscar_normas_bcb": {"q": "1000"},
            "obter_evidencia": {"capture_id": "sintetica-ausente"},
            "obter_registro": {"run_id": "sintetica-ausente"},
            "listar_fontes": {},
        }

        async def executar():
            nomes = {tool.name for tool in await server.list_tools()}
            assert nomes == argumentos.keys()  # Ferramenta nova exige adicionar prova.
            for nome, args in argumentos.items():
                res = await server.call_tool(nome, args)
                assert not res.is_error, (nome, res)

        asyncio.run(executar())


def test_item13_rest_remoto_todas_rotas(tmp_path, proibidos):
    from freoa_verifica.rest import create_app
    from starlette.testclient import TestClient

    app = create_app(home=str(tmp_path), token="token-sintetico")
    cit = "art. 1º da Lei 6.404/1976"
    casos = [
        ("GET", "/v1/legislacao", {"q": "6404", "fonte": "planalto"}),
        ("GET", "/v1/citacoes/resolver", {"citacao": cit}),
        ("GET", "/v1/dispositivos", {"citacao": cit}),
        ("GET", "/v1/dispositivos/historico", {"citacao": cit}),
        ("POST", "/v1/verificacoes", {"citacao": cit}),
        ("POST", "/v1/verificacoes/texto", {"texto": cit}),
        ("GET", "/v1/jurisprudencia", {"q": "contrato", "tribunais": "stj"}),
        ("GET", "/v1/decisoes/sintetica-ausente", {}),
        ("GET", "/v1/normas/cvm", {"q": "160"}),
        ("GET", "/v1/normas/bcb", {"q": "1000"}),
        ("GET", "/v1/evidencias/sintetica-ausente", {}),
        ("GET", "/v1/fontes", {}),
        ("GET", "/v1/registros/sintetica-ausente", {}),
        ("POST", "/v1/registros/sintetica-ausente/conferencia", {"evidencias": []}),
    ]
    assert {r.path for r in app.routes if r.path.startswith("/v1/")} == {
        "/v1/" + p
        for p in (
            "legislacao",
            "citacoes/resolver",
            "dispositivos",
            "dispositivos/historico",
            "verificacoes",
            "verificacoes/texto",
            "jurisprudencia",
            "decisoes/{id}",
            "normas/cvm",
            "normas/bcb",
            "evidencias/{capture_id}",
            "fontes",
            "registros/{run_id}",
            "registros/{run_id}/conferencia",
        )
    }
    with TestClient(
        app,
        client=("192.0.2.1", 50000),
        headers={"Authorization": "Bearer token-sintetico"},
    ) as cliente:
        for metodo, url, args in casos:
            out = cliente.request(
                metodo, url, **{"params" if metodo == "GET" else "json": args}
            )
            assert out.status_code == 200, (url, out.text)
        assert cliente.post("/v1/sessao", json={"fonte": "planalto"}).status_code == 404


def test_item13_agendado_sync_e_bateria(tmp_path, proibidos, capsys):
    with Verifica(home=tmp_path) as svc:
        out = svc.sincronizar(fontes=["planalto", "normas_leg"], max_itens=1)
        assert len(out["fontes"]) == 2
        semente = svc.sincronizar(fontes=["planalto"], semente=True, max_itens=1)
        assert isinstance(semente, dict)
    assert bateria.executar(tmp_path, sem_blobs=True)["status"] in {"parcial", "falha"}
    with pytest.raises(SystemExit):
        cli.main(["--home", str(tmp_path), "sync", "--fonte", "planalto"])
    assert capsys.readouterr().out


@pytest.mark.parametrize(
    "variavel", ["SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY", "WINRS_SHELL_ID"]
)
def test_item13_terminal_remoto_nao_chega_ao_lancamento(
    monkeypatch, tmp_path, variavel, proibidos
):
    # Exercita conferir_terminal real; só TTY é sintético, para chegar ao corte remoto.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        monkeypatch.setattr(stream, "isatty", lambda: True)
    monkeypatch.setenv(variavel, "remoto-sintetico")
    args = cli.build_parser().parse_args(
        ["--home", str(tmp_path), "sessao", "planalto"]
    )
    assert executar_sessao(args) == 2
