"""Auditoria Codex r1: metadados e bancos sintéticos, sem navegador ou rede."""

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
import sqlite3
from types import SimpleNamespace

import pytest

from freoa_verifica import transport as t
from freoa_verifica.assistida.ambiente import RecusaSessao
from freoa_verifica.assistida.indicacao import cobertura
from freoa_verifica.assistida.perfis import PERFIS, resolver_grafo
from freoa_verifica.assistida.persistencia import persistir, recibo
from freoa_verifica.service import Verifica
from freoa_verifica.snapshot import export_snapshot, install_snapshot
from freoa_verifica.store import repo
from tests.assistida_0089_util import (
    sessao as sessao,
    adapter,
    request,
    entregar,
    captura,
    metadados,
    META,
    BIN,
    BODY,
    URL,
    VigiaSintetico,
)


AUSENTE = "__campo_ausente__"
CAMINHOS = [
    ("requestWillBeSentExtraInfo", ("headers",)),
    ("requestWillBeSentExtraInfo", ("associatedCookies",)),
    ("responseReceivedExtraInfo", ("headers",)),
    ("responseReceivedExtraInfo", ("blockedCookies",)),
    ("responseReceivedExtraInfo", ("statusCode",)),
    ("responseReceivedExtraInfo", ("headersText",)),
    *[
        ("responseReceived", ("response", k))
        for k in (
            "securityDetails",
            "securityState",
            "fromDiskCache",
            "fromServiceWorker",
            "fromPrefetchCache",
            "remoteIPAddress",
            "remotePort",
            "status",
            "protocol",
            "url",
        )
    ],
    ("responseReceived", ("response", "securityDetails", "protocol")),
    ("responseReceived", ("response", "securityDetails", "issuer")),
]


@pytest.mark.parametrize("metodo,caminho", CAMINHOS)
@pytest.mark.parametrize(
    "valor", [AUSENTE, None, 12, ["incompleto"], {"incompleto": True}]
)
def test_metadados_evento_sem_prova_nunca_admitem(
    sessao, monkeypatch, metodo, caminho, valor
):
    ad = adapter(sessao)
    original = ad._evento

    def truncar(sid, rid, evento, dados):
        if evento == metodo:
            dados = deepcopy(dados)
            alvo = dados
            for k in caminho[:-1]:
                alvo = alvo[k]
            if valor == AUSENTE:
                alvo.pop(caminho[-1])
            else:
                alvo[caminho[-1]] = valor
        return original(sid, rid, evento, dados)

    monkeypatch.setattr(ad, "_evento", truncar)
    request(ad)
    try:
        entregar(ad)
    except RecusaSessao as exc:
        assert str(exc) == "EVENTO_CDP_INVALIDO"
    assert ad.pedidos["cdp", "pedido"].admitida is None
    assert ad.fechado or ad.recusas
    ad.descartar()


@pytest.mark.parametrize(
    "campo,validos",
    [
        (
            "associatedCookies",
            {"cookie": {"name": "nome"}, "blockedReasons": ["SecureOnly"]},
        ),
        (
            "blockedCookies",
            {"cookieLine": "valor-sintetico", "blockedReasons": ["SecureOnly"]},
        ),
    ],
)
@pytest.mark.parametrize(
    "defeito",
    [
        None,
        1,
        {},
        {"cookie": {}},
        {"blockedReasons": []},
        {"cookie": {"name": None}, "blockedReasons": []},
        {"cookie": {"name": "nome"}, "cookieLine": "x"},
        {"cookie": {"name": "nome"}, "cookieLine": "x", "blockedReasons": None},
        {"cookie": {"name": 12}, "cookieLine": 12, "blockedReasons": []},
        {"cookie": {"name": ""}, "cookieLine": "", "blockedReasons": []},
        {"cookie": None, "cookieLine": "x", "blockedReasons": []},
        {"cookie": [], "cookieLine": "x", "blockedReasons": []},
        {"cookie": {"name": "nome"}, "cookieLine": "x", "blockedReasons": [None]},
        {"cookie": {"name": "nome"}, "cookieLine": "x", "blockedReasons": [1]},
        {"cookie": {"name": "nome"}, "cookieLine": "x", "blockedReasons": "bloqueado"},
    ],
)
def test_elementos_cookies_incompletos_recusados(
    sessao, monkeypatch, campo, validos, defeito
):
    ad = adapter(sessao)
    original = ad._evento
    metodo = (
        "requestWillBeSentExtraInfo"
        if campo == "associatedCookies"
        else "responseReceivedExtraInfo"
    )

    def truncar(sid, rid, evento, dados):
        if evento == metodo:
            dados = {**dados, campo: [deepcopy(validos), defeito]}
        return original(sid, rid, evento, dados)

    monkeypatch.setattr(ad, "_evento", truncar)
    request(ad)
    with pytest.raises(RecusaSessao, match="EVENTO_CDP_INVALIDO"):
        entregar(ad)
    assert ad.pedidos["cdp", "pedido"].admitida is None
    ad.descartar()


@pytest.mark.parametrize(
    "metodo", ["requestWillBeSentExtraInfo", "responseReceivedExtraInfo"]
)
@pytest.mark.parametrize(
    "headers",
    [
        {"Authorization": None},
        {"Authorization": []},
        {"": "x"},
        {1: "x"},
        {" Authorization": "x"},
        {"Authorization ": "x"},
        {"Auth\x00orization": "x"},
    ],
)
def test_headers_incompletos_nao_viram_prova(sessao, monkeypatch, metodo, headers):
    ad = adapter(sessao)
    original = ad._evento

    def truncar(sid, rid, evento, dados):
        return original(
            sid,
            rid,
            evento,
            {**dados, "headers": headers} if evento == metodo else dados,
        )

    monkeypatch.setattr(ad, "_evento", truncar)
    request(ad)
    with pytest.raises(RecusaSessao, match="EVENTO_CDP_INVALIDO"):
        entregar(ad)
    assert ad.pedidos["cdp", "pedido"].admitida is None
    ad.descartar()


@pytest.mark.parametrize("campo", ["initiator", "frameId", "documentURL"])
@pytest.mark.parametrize("valor", [AUSENTE, None, [], {}, 1])
def test_metadados_pedido_incompletos_recusados(sessao, monkeypatch, campo, valor):
    ad = adapter(sessao)
    original = ad._pedido

    def truncar(sid, alvo, p):
        p = {**p}
        if valor == AUSENTE:
            del p[campo]
        else:
            p[campo] = valor
        return original(sid, alvo, p)

    monkeypatch.setattr(ad, "_pedido", truncar)
    with pytest.raises(RecusaSessao, match="EVENTO_CDP_INVALIDO"):
        request(ad)
    assert not ad.pedidos and not ad.canal.comandos
    ad.descartar()


@pytest.mark.parametrize(
    "f",
    [
        None,
        [],
        {},
        {"id": "raiz"},
        {"id": "raiz", "url": None},
        {"id": "raiz", "url": URL, "parentId": None},
        {"id": [], "url": URL},
    ],
)
def test_frame_sem_prova_nao_estabelece_raiz(sessao, f):
    ad = adapter(sessao)
    with pytest.raises(RecusaSessao, match="EVENTO_CDP_INVALIDO"):
        ad.processar(
            {
                "sessionId": "cdp",
                "method": "Page.frameNavigated",
                "params": {"frame": f},
            }
        )
    assert not ad.pedidos
    ad.descartar()


@pytest.mark.parametrize("campo", ["type", "url", "targetId", "subtype"])
@pytest.mark.parametrize("valor", [None, [], 1])
def test_metadados_alvo_invalidos_recusados(sessao, campo, valor):
    ad = adapter(sessao)
    info = {"targetId": "nova", "type": "page", "url": "about:blank", "subtype": ""}
    info[campo] = valor
    with pytest.raises(RecusaSessao):
        ad.processar({"method": "Target.targetCreated", "params": {"targetInfo": info}})
    assert not ad.pedidos and not ad.canal.comandos
    ad.descartar()


@pytest.mark.skipif(
    os.name != "nt", reason="FILE_NOTIFY_INFORMATION contém WCHAR Windows"
)
@pytest.mark.parametrize(
    "nome,esperado",
    [
        ("Default/Extensões/arquivo", True),
        ("Default/\U0001f642", True),
        ("Default/\ud800", False),
    ],
)
def test_notificacao_windows_unicode_estrito(nome, esperado):
    import ctypes
    import struct
    from freoa_verifica.assistida import ambiente as a

    observer = object.__new__(a.ObservadorWindows)
    codificado = nome.encode("utf-16-le", errors="surrogatepass")
    raw = struct.pack("III", 0, 1, len(codificado)) + codificado
    observer.buf = ctypes.create_string_buffer(raw)
    observer.parado = False
    observer.handle = None
    observer.overlapped = ctypes.c_int()
    notificados, falhas = [], []

    def concluir(*_):
        observer.parado = True

    def ler(_, __, tamanho, ___):
        tamanho._obj.value = len(raw)
        return True

    observer.kernel = SimpleNamespace(GetOverlappedResult=ler)
    observer.vigia = SimpleNamespace(
        notificar=lambda nome, acao: notificados.append((nome, acao)),
        falhar=lambda: (falhas.append(True), concluir()),
    )
    observer._armar = concluir
    observer._ler()
    assert notificados == ([(nome, 1)] if esperado else [])
    assert bool(falhas) is not esperado


@pytest.mark.parametrize("local", ["a", "ab", "b"])
def test_snapshot_colisoes_naturais_dependentes_e_reinstalacao(
    tmp_path, monkeypatch, local
):
    monkeypatch.setenv("FV_OFFLINE", "1")
    cs = [captura(META, metadados(), mime="application/json"), captura(BIN, BODY)]
    orcamento = t.SessaoPortaAssistida(
        PERFIS["normas_leg"].porta, navegador="sintetico"
    )
    try:
        docs = resolver_grafo(PERFIS["normas_leg"], cs, orcamento=orcamento)
        with (
            Verifica(home=tmp_path / "origem") as origem,
            Verifica(home=tmp_path / "destino") as destino,
        ):
            ids = persistir(
                origem.conn,
                origem.home,
                PERFIS["normas_leg"],
                docs,
                {0},
                VigiaSintetico(),
                orcamento=orcamento,
            )
            aid = origem.conn.execute(
                "SELECT id FROM capture WHERE url=?", (META,)
            ).fetchone()[0]
            # Mesmo recibo/obtenção, com identidades SQL diferentes e destino não vazio.
            destino.conn.execute(
                "INSERT INTO source(id,authority,profile,hosts_json) VALUES ('normas_leg','sintetico','normas_leg','[]')"
            )
            with monkeypatch.context() as patch:
                if local == "b":
                    patch.setattr(repo, "new_ulid", lambda: aid)
                la = repo.save_capture(
                    destino.conn,
                    cs[0].resposta,
                    "normas_leg",
                    home=destino.home,
                    procedencia="sessao_assistida",
                    assistida=recibo(cs[0]),
                )
            if local in {"ab", "b"}:
                v = {**docs[0].vinculo, "metadados_capture_id": la}
                lb = repo.save_capture(
                    destino.conn,
                    cs[1].resposta,
                    "normas_leg",
                    home=destino.home,
                    procedencia="sessao_assistida",
                    assistida=recibo(cs[1], v),
                )
            assert (la == aid) == (local == "b")
            pacote = tmp_path / "pacote"
            assert export_snapshot(origem.conn, origem.home, pacote)["status"] == "ok"
            for _ in range(2):
                out = install_snapshot(destino, pacote, aceitar_nao_vinculado=True)
                assert out["status"] == "ok", out
                rows = destino.conn.execute(
                    "SELECT id,assistida_json FROM capture WHERE url=?", (BIN,)
                ).fetchall()
                assert len(rows) == 1
                v = json.loads(rows[0][1])["vinculo"]
                dep = destino.conn.execute(
                    "SELECT sha256,assistida_json FROM capture WHERE id=?",
                    (v["metadados_capture_id"],),
                ).fetchone()
                assert dep[0] == v["metadados_sha256"] == cs[0].resposta.sha256
                assert (
                    json.loads(dep[1])["obtencao_id"]
                    == v["metadados_obtencao_id"]
                    == cs[0].obtencao_id
                )
                assert v["metadados_capture_id"] == (aid if local == "b" else la)
                assert rows[0][0] == (ids[0] if local == "a" else lb)
    finally:
        orcamento.encerrar()


@pytest.mark.parametrize("defeito", ["ausente", "hash", "obtencao"])
def test_snapshot_recusa_vinculo_quebrado_antes_de_publicar(
    tmp_path, monkeypatch, defeito
):
    monkeypatch.setenv("FV_OFFLINE", "1")
    with (
        Verifica(home=tmp_path / "origem") as origem,
        Verifica(home=tmp_path / "destino") as destino,
    ):
        cs = [captura(META, metadados(), mime="application/json"), captura(BIN, BODY)]
        s = t.SessaoPortaAssistida(PERFIS["normas_leg"].porta, navegador="sintetico")
        try:
            docs = resolver_grafo(PERFIS["normas_leg"], cs, orcamento=s)
            ids = persistir(
                origem.conn,
                origem.home,
                PERFIS["normas_leg"],
                docs,
                {0},
                VigiaSintetico(),
                orcamento=s,
            )
            row = origem.conn.execute(
                "SELECT assistida_json FROM capture WHERE id=?", (ids[0],)
            ).fetchone()
            data = json.loads(row[0])
            campo = {
                "ausente": "metadados_capture_id",
                "hash": "metadados_sha256",
                "obtencao": "metadados_obtencao_id",
            }[defeito]
            data["vinculo"][campo] = "inexistente"
            origem.conn.execute("DROP TRIGGER capture_no_update")
            origem.conn.execute(
                "UPDATE capture SET assistida_json=? WHERE id=?",
                (json.dumps(data), ids[0]),
            )
            origem.conn.commit()
            pacote = tmp_path / "pacote"
            assert export_snapshot(origem.conn, origem.home, pacote)["status"] == "ok"
            out = install_snapshot(destino, pacote, aceitar_nao_vinculado=True)
            assert (
                out["status"] == "erro"
                and "snapshot_vinculo_assistido_invalido" in out["motivo"]
            )
            assert (
                destino.conn.execute("SELECT count(*) FROM capture").fetchone()[0] == 0
            )
        finally:
            s.encerrar()


def test_cobertura_legado_migracao_real_nao_inferida():
    from importlib.resources import files

    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE TABLE capture(source_id TEXT, procedencia TEXT)")
        conn.execute("INSERT INTO capture VALUES ('planalto','captura_direta')")
        antes = cobertura(conn, "planalto")
        assert antes["automatico"]["capturas"] is None
        conn.executescript(
            files("freoa_verifica")
            .joinpath("store/migrations/018_sessao_assistida.sql")
            .read_text(encoding="utf-8")
        )
        out = cobertura(conn, "planalto")
        assert out["contagem_parcial"] is True
        assert out["modalidade_desconhecida"]["capturas"] == 1
        assert (
            conn.execute("SELECT modalidade_acesso FROM capture").fetchone()[0] is None
        )
        conn.execute(
            "INSERT INTO capture(source_id,modalidade_acesso) VALUES ('planalto','automatico')"
        )
        conn.execute(
            "INSERT INTO capture(source_id,modalidade_acesso) VALUES ('planalto','sessao_assistida')"
        )
        out = cobertura(conn, "planalto")
        assert out["automatico"]["capturas"] == out["assistido"]["capturas"] == 1
        assert out["modalidade_desconhecida"]["capturas"] == 1
        assert cobertura(conn, "normas_leg")["contagem_parcial"] is False
    finally:
        conn.close()


@pytest.mark.parametrize("confirmacao", ["REABRIR", "nao"])
def test_comando_completo_reabertura_normas_leg(
    tmp_path, monkeypatch, capsys, confirmacao, proibir_rede
):
    from freoa_verifica import cli
    from freoa_verifica.assistida import terminal
    from freoa_verifica.connectors.camara_estado import Estado
    from freoa_verifica.connectors.normas_leg import NormasPortao

    def vedado(*args, **kwargs):
        pytest.fail("comando local não pode emitir rede ou consultar home real")

    monkeypatch.setattr(terminal, "conferir_terminal", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _: confirmacao)
    monkeypatch.setattr(t, "fetch", vedado)
    monkeypatch.setattr("freoa_verifica.store.db.data_home", vedado)
    monkeypatch.setenv("FV_HOME", str(tmp_path / "home-ambiente"))
    home = tmp_path / "home-explicito"
    portao = NormasPortao(None, home=home)
    agora = datetime.now(timezone.utc)
    registro = {
        "classe": "desafio",
        "motivo": "sintetico",
        "desde": agora.isoformat(),
        "ate": None,
    }
    portao.estado.bloquear_host("normas.leg.br", registro)
    args = [
        "--home",
        str(home),
        "reabrir-normas-leg",
        "--decisao",
        "0087/0089 r1 sintetico",
    ]
    if confirmacao == "REABRIR":
        cli.main(args)
        assert "nenhuma requisição emitida" in capsys.readouterr().out
    else:
        with pytest.raises(SystemExit) as exc:
            cli.main(args)
        assert exc.value.code == 2
    estado = Estado(home, hosts=frozenset({"normas.leg.br"}), diretorio="normas_leg")
    dados = estado._bloqueios("normas.leg.br")
    assert (dados["host"] is None) == (confirmacao == "REABRIR")
    assert len(dados["reaberturas"]) == (1 if confirmacao == "REABRIR" else 0)
    if dados["reaberturas"]:
        assert dados["reaberturas"][-1]["decisao"] == "0087/0089 r1 sintetico"
    assert not (tmp_path / "home-ambiente").exists()
    assert not proibir_rede


@pytest.mark.skipif(
    os.name != "nt", reason="lançamento de pipe Windows, processo simulado"
)
def test_ambiente_produto_e_harness_identico_temporarios_confinados(
    tmp_path, monkeypatch
):
    from freoa_verifica.assistida import ambiente as a
    from tests import harness_assistida_0089 as h

    ambientes = []

    def popen(args, **kw):
        ambientes.append(kw["env"])
        assert kw["creationflags"] == 4
        return SimpleNamespace(poll=lambda: None)

    monkeypatch.setattr(a.subprocess, "Popen", popen)
    monkeypatch.setattr(a, "_conter_processo", lambda _: "job-sintetico")
    monkeypatch.setattr(a, "_dlls", lambda: None)
    monkeypatch.setattr(
        a, "navegador_instalado", lambda _: ("brave", tmp_path / "brave.exe")
    )
    monkeypatch.setattr(a, "conferir_politicas", lambda _: None)
    monkeypatch.setattr(a, "proteger_diretorio", lambda _: None)
    monkeypatch.setattr(a, "_processos_do_perfil", lambda *_: set())
    monkeypatch.setattr(a, "fechar_navegador", lambda *_: None)
    vigia = SimpleNamespace(linha_base=1, limite_inventario=100)
    monkeypatch.setattr(a, "Vigilancia", lambda *_: vigia)
    monkeypatch.setattr(
        a, "ObservadorWindows", lambda _: SimpleNamespace(fechar=lambda: None)
    )
    monkeypatch.setattr(
        h,
        "CanalPipe",
        lambda leitura, escrita, _: SimpleNamespace(
            iniciar=lambda: None, fechar=lambda: (leitura.close(), escrita.close())
        ),
    )
    monkeypatch.setattr(
        h,
        "AdaptadorCDP",
        lambda *_: SimpleNamespace(
            fase=3, iniciar=lambda: None, alvos={"sid": SimpleNamespace(pronto=True)}
        ),
    )
    perfil = tmp_path / "sessao-0089-harness"
    perfil.mkdir()
    _, leitura, escrita = a.lancar_pipe(
        tmp_path / "brave.exe", perfil, "file:///inicio.html"
    )
    leitura.close()
    escrita.close()
    (perfil / "temporarios").rmdir()
    perfil.rmdir()
    with h.navegador_pipe(tmp_path, monkeypatch):
        assert ambientes[0] == ambientes[1]
        for nome in ("TEMP", "TMP", "TMPDIR", "TEMPDIR"):
            assert ambientes[0][nome] == str(perfil / "temporarios")
        assert os.environ["TEMP"] != ambientes[0]["TEMP"]
    assert not perfil.exists()
