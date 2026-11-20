"""§3: cenários reais pendentes de execução externa pelo supervisor, com Brave.

Cada fase começa após inventário/base/prontidão (até 60 s + assentamento).
Prazos de cenário explícitos, sem pytest-timeout ou outra dependência nova.
"""

import json
import os
from pathlib import Path
import time
from html import escape

import pytest

from freoa_verifica.assistida import ambiente as a
from freoa_verifica.assistida import sessao
from freoa_verifica.assistida.cdp import METODOS
from freoa_verifica.assistida.perfis import DocumentoSelecionavel
from freoa_verifica.assistida.persistencia import persistir
from freoa_verifica.store.db import connect
from tests.gerar_0089_wire import BODY
from tests.harness_assistida_0089 import navegador_pipe
from tests.harness_assistida_0089_cenarios import (
    BASE,
    FRAMING,
    PUBLICO_CAMINHO,
    PUBLICO_CORPO,
    SEGREDOS,
    SondaEventos,
    bombear,
    capturas,
    cenarios_https,
    varrer_artefatos,
)

pytestmark = pytest.mark.navegador_assistido


@pytest.mark.parametrize("caso", ["br", "zstd", *FRAMING])
def test_item1_codificacoes_e_framing_reais(tmp_path, monkeypatch, caso):
    with cenarios_https(tmp_path, caso) as (spki, estado):
        with navegador_pipe(tmp_path, monkeypatch, spki=spki, caso=caso) as (
            ad,
            _,
            vigia,
        ):
            sonda = SondaEventos(ad)
            bombear(ad, vigia, ate=lambda: bool(capturas(ad) or ad.recusas), prazo=40)
            assert any(p[1] == "/case/" + caso for p in estado["pedidos"])
            if caso in {"br", "zstd"}:
                cs = capturas(ad)
                assert len(cs) == 1 and cs[0].resposta.body == BODY
                assert cs[0].content_encoding == caso
            else:
                assert not capturas(ad)
                assert ad.recusas
            assert any(e["metodo"].startswith("Network.") for e in sonda.eventos)


@pytest.mark.parametrize(
    "caso", ["fetch_identity", "fetch_gzip", "xhr_identity", "xhr_gzip"]
)
def test_item1_confrontos_finais_fetch_xhr_reais(tmp_path, monkeypatch, caso):
    with cenarios_https(tmp_path, caso) as (spki, estado):
        with navegador_pipe(
            tmp_path, monkeypatch, spki=spki, script=f"location.href='{BASE}/driver';"
        ) as (ad, _, vigia):
            sonda = SondaEventos(ad)
            bombear(ad, vigia, ate=lambda: "/done" in estado["marcas"], prazo=40)
            assert not estado["erros"]
            cs = capturas(ad)
            assert len(cs) == 1 and cs[0].resposta.body == BODY
            assert cs[0].encoded_data_length is not None
            assert cs[0].content_encoding == ("gzip" if caso.endswith("gzip") else None)
            assert any(
                e["tipo"] == ("XHR" if caso.startswith("xhr") else "Fetch")
                for e in sonda.eventos
            )


@pytest.mark.parametrize(
    "sem_prova", [False, True], ids=["hsts_provado", "hsts_prova_suprimida"]
)
def test_item1_hsts_interno_real_e_ausencia_de_prova(tmp_path, monkeypatch, sem_prova):
    # .test mapeado exclusivamente pelo harness a loopback; nenhum DNS externo.
    # O negativo suprime a prova no evento REAL: injeção de falha no harness,
    # explicitamente distinta da observação integral do caso positivo.
    with cenarios_https(tmp_path, "hsts") as (spki, estado):
        with navegador_pipe(
            tmp_path,
            monkeypatch,
            spki=spki,
            hsts=True,
            script="location.href='https://hsts.0089.test/prime_hsts';",
        ) as (ad, _, vigia):
            processar = ad.processar
            saltos = []

            def observar(obj):
                p = obj.get("params", {})
                if (
                    obj.get("method") == "Network.requestWillBeSent"
                    and "redirectResponse" in p
                ):
                    salto = p["redirectResponse"]
                    if salto.get("url") == "http://hsts.0089.test/case/hsts":
                        saltos.append(salto)
                        if sem_prova:
                            p = {**p, "redirectResponse": {**salto, "headers": {}}}
                            obj = {**obj, "params": p}
                processar(obj)

            monkeypatch.setattr(ad, "processar", observar)
            bombear(ad, vigia, ate=lambda: "/done" in estado["marcas"], prazo=40)
            assert saltos, (
                "navegador deve demonstrar salto HSTS interno; falha não vira aprovação"
            )
            assert any(
                s.get("headers", {}).get("Non-Authoritative-Reason") == "HSTS"
                for s in saltos
            )
            cs = capturas(ad)
            assert not any(c.resposta.url.startswith("http:") for c in cs)
            assert (
                bool(
                    [
                        c
                        for c in cs
                        if c.resposta.url == "https://hsts.0089.test/case/hsts"
                    ]
                )
                is not sem_prova
            )


def test_item1_item8_instalacao_manual_desempacotada_recusa(tmp_path, monkeypatch):
    # Mecanismo aceito pela UI do Brave, sem política, pacote externo, admin ou
    # flags --load-extension/unsafe. Não afirma provar location 1/10 assinada.
    extensao = tmp_path / "extensao-sintetica"
    extensao.mkdir()
    (extensao / "manifest.json").write_text(
        json.dumps(
            {
                "manifest_version": 3,
                "name": "Harness sintetico 0089 webRequest",
                "version": "1.0",
                "permissions": ["webRequest"],
                "host_permissions": ["https://127.0.0.1/*"],
            }
        ),
        encoding="utf-8",
    )
    with cenarios_https(tmp_path, "extensao") as (spki, estado):
        estado["instrucoes_extensao"] = (
            "<!doctype html><meta charset=utf-8><h1>Harness 0089: instalação manual</h1>"
            "<p>Depois de 2 segundos, abra brave://extensions nesta janela dedicada, "
            "ative o modo de desenvolvedor e use Carregar sem compactação. Selecione: "
            + escape(str(extensao))
            + "</p><p>Prazo: 90 segundos. Não use outra janela/perfil.</p>"
        )
        with navegador_pipe(tmp_path, monkeypatch, spki=spki, caso="extensao") as (
            ad,
            proc,
            vigia,
        ):
            bombear(ad, vigia, ate=lambda: bool(capturas(ad)), prazo=40)
            assert capturas(ad), "candidata anterior à instalação deve existir"
            perfil = tmp_path / "sessao-0089-harness"
            limite = time.monotonic() + 90
            recusa = None
            encontrada = False
            while time.monotonic() < limite:
                if recusa is None:
                    try:
                        mensagem = ad.canal.receber()
                        if mensagem:
                            with mensagem as obj:
                                ad.processar(obj)
                    except a.RecusaSessao as exc:
                        recusa = str(exc)
                for nome in ("Secure Preferences", "Preferences"):
                    try:
                        data = json.loads((perfil / "Default" / nome).read_bytes())
                    except (FileNotFoundError, json.JSONDecodeError):
                        continue  # somente observação de teste da gravação assíncrona
                    for item in data.get("extensions", {}).get("settings", {}).values():
                        if (
                            item.get("path")
                            and Path(item["path"]).resolve() == extensao.resolve()
                        ):
                            assert item["location"] == 4
                            encontrada = True
                if encontrada:
                    try:
                        vigia.barreira()
                    except a.RecusaSessao as exc:
                        recusa = str(exc)
                    break
                time.sleep(0.05)
            assert encontrada, "instalação manual não demonstrada dentro do prazo"
            assert recusa in {"EXTENSOES_ALTERADAS", "EXTENSAO_DESEMPACOTADA"}
            with pytest.raises(
                a.RecusaSessao, match="EXTENSOES_ALTERADAS|EXTENSAO_DESEMPACOTADA"
            ):
                vigia.barreira()  # a seleção/publicação não pode atravessar a barreira
            if recusa == "EXTENSOES_ALTERADAS":
                assert ad.fechado and ad.sessao._encerrada
        assert proc.poll() is not None


@pytest.mark.parametrize(
    "caso", ["cache", "sw", "prefetch", "prerender", "bfcache", "early_hints"]
)
def test_item2_proveniencia_real_sem_candidata_derivada(tmp_path, monkeypatch, caso):
    with cenarios_https(tmp_path, caso) as (spki, estado):
        with navegador_pipe(
            tmp_path, monkeypatch, spki=spki, script=f"location.href='{BASE}/driver';"
        ) as (ad, _, vigia):
            sonda = SondaEventos(ad)
            bombear(ad, vigia, ate=lambda: "/done" in estado["marcas"], prazo=55)
            assert not estado["erros"]
            if caso in {"cache", "sw", "prefetch"}:
                campo = {"cache": "cache", "sw": "sw", "prefetch": "prefetch"}[caso]
                derivados = {
                    e["chave"]
                    for e in sonda.eventos
                    if e[campo]
                    or (
                        caso == "cache"
                        and e["metodo"] == "Network.requestServedFromCache"
                    )
                }
                assert derivados, (
                    f"o navegador não demonstrou {caso}; não aceitar só ausência de captura"
                )
                assert all(
                    k not in ad.pedidos or ad.pedidos[k].admitida is None
                    for k in derivados
                )
                if caso == "sw":
                    assert not any(c.resposta.url.endswith("/sw") for c in capturas(ad))
                if caso == "prefetch":
                    assert any(
                        "prefetch" in v.lower()
                        for _, _, hs in estado["pedidos"]
                        for k, v in hs
                        if k.lower() in {"sec-purpose", "purpose"}
                    )
            elif caso == "prerender":
                assert any(e["subtipo"] == "prerender" for e in sonda.eventos)
                assert "/marca/prerender" in estado["marcas"]
                assert not any(
                    c.resposta.url.endswith("/prerender") for c in capturas(ad)
                )
            elif caso == "bfcache":
                assert "/marca/bfcache" in estado["marcas"]
                assert sum(p[1] == "/case/bfcache" for p in estado["pedidos"]) == 1
                assert (
                    sum(c.resposta.url.endswith("/bfcache") for c in capturas(ad)) == 1
                )
            else:
                assert any(
                    e["metodo"] == "Network.responseReceivedEarlyHints"
                    for e in sonda.eventos
                )
                assert any(p[1] == "/case/hinted" for p in estado["pedidos"]), (
                    "origem deve ver o recurso de 103"
                )
                assert not any(c.resposta.url.endswith("/hinted") for c in capturas(ad))
                assert any(
                    c.resposta.url.endswith("/early_hints") for c in capturas(ad)
                ), "resposta final é avaliada por si"


def test_item2_recarga_forcada_humana_vem_da_rede(tmp_path, monkeypatch):
    # O Chromium ignora o booleano de location.reload(true). Exige gesto humano
    # e prova pelos DOIS cabeçalhos, em vez de simular Network.setCacheDisabled.
    with cenarios_https(tmp_path, "reload") as (spki, estado):
        with navegador_pipe(tmp_path, monkeypatch, spki=spki, caso="reload") as (
            ad,
            _,
            vigia,
        ):
            bombear(ad, vigia, ate=lambda: "/done" in estado["marcas"], prazo=90)
            reais = [
                dict((k.lower(), v) for k, v in hs)
                for _, p, hs in estado["pedidos"]
                if p == "/case/reload"
            ]
            assert len(reais) >= 2
            assert (
                reais[-1].get("cache-control") == reais[-1].get("pragma") == "no-cache"
            )
            assert sum(c.resposta.url.endswith("/reload") for c in capturas(ad)) >= 2


@pytest.mark.parametrize(
    "caso",
    ["iframe", "iframe_xhr", "blob", "data", "download", "websocket", "post", "cookie"],
)
def test_item3_escopo_e_quadros_reais(tmp_path, monkeypatch, caso):
    with cenarios_https(tmp_path, caso) as (spki, estado):
        with navegador_pipe(
            tmp_path, monkeypatch, spki=spki, script=f"location.href='{BASE}/driver';"
        ) as (ad, _, vigia):
            sonda = SondaEventos(ad)
            bombear(ad, vigia, ate=lambda: "/done" in estado["marcas"], prazo=40)
            assert not estado["erros"]
            assert not capturas(ad)
            if caso in {"blob", "data"}:
                assert any(e["frame"].startswith(caso + ":") for e in sonda.eventos)
            elif caso == "websocket":
                assert any(
                    e["metodo"] == "Network.webSocketCreated" for e in sonda.eventos
                )
                assert any(p[1] == "/ws" for p in estado["pedidos"])
            else:
                pedidos = [p for p in estado["pedidos"] if p[1] == "/case/" + caso]
                assert pedidos
                if caso == "post":
                    assert pedidos[0][0] == "POST"
                if caso == "cookie":
                    assert "nao_declarado=" in dict(pedidos[0][2]).get("Cookie", "")
                if caso in {"iframe", "iframe_xhr"}:
                    assert any(
                        e["metodo"] == "Network.requestWillBeSent"
                        and e["url"].endswith("/case/" + caso)
                        and e["frame_id"] != e["raiz"]
                        and e["tipo"] == ("XHR" if caso == "iframe_xhr" else "Document")
                        for e in sonda.eventos
                    )


def test_item6_varredura_todos_artefatos_publicados(tmp_path, monkeypatch, capsys):
    home = tmp_path / "produto"
    home.mkdir()
    with cenarios_https(tmp_path, "segredos") as (spki, estado):
        with navegador_pipe(
            tmp_path, monkeypatch, spki=spki, script=f"location.href='{BASE}/driver';"
        ) as (ad, _, vigia):
            bombear(ad, vigia, ate=lambda: "/done" in estado["marcas"], prazo=45)
            assert not estado["erros"]
            cs = capturas(ad)
            assert len(cs) == 1 and cs[0].resposta.url.endswith("/" + PUBLICO_CAMINHO)
            assert PUBLICO_CORPO.encode() in cs[0].resposta.body
            # Prova que os segredos realmente atravessaram a origem sintética.
            bruto_origem = json.dumps(estado["pedidos"])
            assert all(SEGREDOS[k] in bruto_origem for k in ("cookie", "auth", "query"))
            conn = connect(home / "verifica.sqlite3")
            try:
                persistir(
                    conn,
                    home,
                    ad.perfil,
                    [DocumentoSelecionavel(cs[0], "público sintético")],
                    {0},
                    vigia,
                    orcamento=ad.sessao,
                )
                assert conn.execute("SELECT count(*) FROM capture").fetchone()[0] == 1
                assert conn.execute("SELECT count(*) FROM extract").fetchone()[0] == 0
            finally:
                conn.close()
            perfil = tmp_path / "sessao-0089-harness"
            inventario = sorted(
                p.relative_to(perfil).as_posix()
                for p in perfil.rglob("*")
                if p.is_file()
            )
            assert inventario and any("Preferences" in p for p in inventario)
            (home / "inventario-temporario.json").write_text(
                json.dumps(inventario), encoding="utf-8"
            )
            (home / "diagnostico.json").write_text(
                json.dumps(ad.recusas), encoding="utf-8"
            )
        a.limpar_diretorio(perfil, tmp_path)
        assert not perfil.exists()
    saida = capsys.readouterr()
    (home / "terminal.txt").write_text(saida.out + saida.err, encoding="utf-8")
    # Após a limpeza, varre TODO o diretório, também certificados/HTML/sinal do
    # harness. O log de origem com segredos permanece apenas em memória.
    arquivos = varrer_artefatos(tmp_path, SEGREDOS.values())
    assert any("verifica.sqlite3" in p for p in arquivos)
    assert any("blobs/" in p for p in arquivos)


def test_item7_segunda_conta_windows_sem_privilegio():
    pytest.skip(
        "não executável neste notebook: não existe segunda conta Windows e o titular não é administrador; não criar conta nem elevar privilégio"
    )


@pytest.mark.parametrize("nome", ["chrome", "edge"])
def test_item8_politica_maquina_recusa_antes_de_abrir(
    tmp_path, monkeypatch, nome, capsys
):
    if os.name != "nt":
        pytest.skip("exige Registro Windows real")
    try:
        a.navegador_instalado(nome)
    except a.RecusaSessao as exc:
        pytest.skip(str(exc))
    import winreg

    forca = False
    for vista in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                a.POLITICAS[nome] + r"\ExtensionInstallForcelist",
                0,
                winreg.KEY_READ | vista,
            ) as chave:
                forca |= winreg.QueryInfoKey(chave)[1] > 0
        except FileNotFoundError:
            pass
    assert forca, (
        "premissa do notebook: ExtensionInstallForcelist de máquina deve conter item"
    )
    monkeypatch.setattr(sessao, "conferir_terminal", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _: "INICIAR")
    monkeypatch.setattr(
        a,
        "lancar_pipe",
        lambda *args, **kw: pytest.fail("navegador com política foi lançado"),
    )
    monkeypatch.setattr(
        a,
        "preparar_diretorio",
        lambda *args: pytest.fail("política deve recusar antes de preparar perfil"),
    )
    from freoa_verifica.cli import build_parser

    args = build_parser().parse_args(
        ["--home", str(tmp_path), "sessao", "planalto", "--navegador", nome]
    )
    assert sessao.executar(args) == 2
    assert "POLITICA_ASSISTIDA_RECUSADA" in capsys.readouterr().out


def test_item9_pedidos_e_cabecalhos_iguais_com_sem_adaptador(tmp_path, monkeypatch):
    registros = []
    for observar in (False, True):
        path = tmp_path / str(observar)
        path.mkdir()
        with monkeypatch.context() as patch:
            with cenarios_https(path, "passividade") as (spki, estado):
                with navegador_pipe(
                    path,
                    patch,
                    spki=spki,
                    observar=observar,
                    script=f"location.href='{BASE}/driver';",
                ) as (ad, _, vigia):
                    sonda = SondaEventos(ad) if ad is not None else None
                    bombear(
                        ad, vigia, ate=lambda: "/done" in estado["marcas"], prazo=40
                    )
                    assert not estado["erros"]
                    assert any(p[1] == "/case/passividade" for p in estado["pedidos"])
                    if sonda:
                        assert capturas(ad)
                        assert all(
                            m in METODOS and (METODOS[m] is None or p == METODOS[m])
                            for m, p in sonda.comandos
                        )
                    # Lista inteira vista pela origem, cabeçalhos sem normalização
                    # ou exclusões. Ordenação só neutraliza intercalação concorrente.
                    registros.append(sorted(estado["pedidos"]))
    assert registros[0] == registros[1]
