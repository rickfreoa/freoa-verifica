"""0089 (b): cenarios sinteticos offline, sem navegador ou rede."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import threading

import time

import pytest
from tests.assistida_0089_util import RegistroSintetico

from freoa_verifica import transport as t

from freoa_verifica.assistida import ambiente as a

from tests.assistida_0089_util import sessao as sessao


@pytest.mark.parametrize("ausente", ["Secure Preferences", "Preferences", "ambos"])
def test_inventario_ausente_aguarda_ate_primeira_leitura(tmp_path, ausente):
    relogio = [100.0]
    default = tmp_path / "Default"
    (default / "Extensions").mkdir(parents=True)
    for nome in ("Secure Preferences", "Preferences"):
        if ausente not in {nome, "ambos"}:
            (default / nome).write_text("{}", encoding="utf-8")
    vigia = a.Vigilancia(tmp_path, tmp_path / "brave.exe", relogio=lambda: relogio[0])
    for instante in (100, 110, 130, 159):
        relogio[0] = instante
        assert vigia.assentar() is None
        assert vigia.erro is None and not vigia.inventario_lido
        assert vigia.caminhos is None
    for nome in ("Secure Preferences", "Preferences"):
        (default / nome).write_text("{}", encoding="utf-8")
    relogio[0] = 159.9
    assert vigia.assentar() == 159.9
    assert vigia.inventario_lido and vigia.caminhos == ()


@pytest.mark.parametrize("aparece_no_limite", [False, True])
def test_inventario_ausente_ate_prazo_recusa(tmp_path, aparece_no_limite):
    relogio = [0.0]
    (tmp_path / "Default" / "Extensions").mkdir(parents=True)
    vigia = a.Vigilancia(tmp_path, tmp_path / "brave.exe", relogio=lambda: relogio[0])
    invalidacoes = []
    vigia.ao_invalidar = lambda: invalidacoes.append(True)
    relogio[0] = a.PRAZO_INVENTARIO_INICIAL_S - 0.1
    assert vigia.assentar() is None
    if aparece_no_limite:
        for nome in ("Secure Preferences", "Preferences"):
            (tmp_path / "Default" / nome).write_text("{}", encoding="utf-8")
    relogio[0] = a.PRAZO_INVENTARIO_INICIAL_S
    with pytest.raises(a.RecusaSessao, match="^INVENTARIO_ASSISTIDO_INDISPONIVEL$"):
        vigia.assentar()
    assert vigia.erro == "INVENTARIO_ASSISTIDO_INDISPONIVEL"
    assert invalidacoes == [True] and vigia.linha_base is None


@pytest.mark.parametrize("arquivo", ["Secure Preferences", "Preferences"])
@pytest.mark.parametrize(
    "conteudo",
    ["{", "[]", '{"extensions": []}', '{"extensions": {"settings": []}}'],
)
def test_inventario_invalido_recusa_imediata_mesmo_outro_ausente(
    tmp_path, arquivo, conteudo
):
    (tmp_path / "Default" / "Extensions").mkdir(parents=True)
    (tmp_path / "Default" / arquivo).write_text(conteudo, encoding="utf-8")
    vigia = a.Vigilancia(tmp_path, tmp_path / "brave.exe", relogio=lambda: 0)
    with pytest.raises(a.RecusaSessao, match="^INVENTARIO_ASSISTIDO_INDISPONIVEL$"):
        vigia.assentar()
    assert vigia.erro == "INVENTARIO_ASSISTIDO_INDISPONIVEL"
    assert not vigia.inventario_lido and vigia.linha_base is None


def test_instalacao_durante_espera_adia_linha_base(tmp_path):
    relogio = [0.0]
    default = tmp_path / "Default"
    (default / "Extensions").mkdir(parents=True)
    vigia = a.Vigilancia(tmp_path, tmp_path / "brave.exe", relogio=lambda: relogio[0])
    relogio[0] = 28
    assert vigia.assentar() is None
    relogio[0] = 29
    (default / "Extensions" / "instalacao-sintetica").write_bytes(b"abc")
    vigia.notificar("Default/Extensions/instalacao-sintetica", 1)
    for nome in ("Secure Preferences", "Preferences"):
        (default / nome).write_text("{}", encoding="utf-8")
    for instante in (30, 38.9):
        relogio[0] = instante
        assert vigia.assentar() is None
        assert vigia.inventario_lido
    relogio[0] = 39
    assert vigia.assentar() == 39
    assert vigia.caminhos == (
        (str(default.relative_to(tmp_path) / "Extensions" / "instalacao-sintetica"), 3),
    )


def test_primeira_leitura_nao_dispensa_dez_segundos_sem_mudancas(tmp_path):
    relogio = [0.0]
    (tmp_path / "Default" / "Extensions").mkdir(parents=True)
    for nome in ("Secure Preferences", "Preferences"):
        (tmp_path / "Default" / nome).write_text("{}", encoding="utf-8")
    vigia = a.Vigilancia(tmp_path, tmp_path / "brave.exe", relogio=lambda: relogio[0])
    assert vigia.assentar() is None and vigia.inventario_lido
    relogio[0] = a.PRAZO_INVENTARIO_INICIAL_S - 1
    vigia.notificar("Default/Extensions/nova", 1)
    relogio[0] += 9.9
    assert vigia.assentar() is None
    relogio[0] += 0.1
    assert vigia.assentar() == relogio[0]


def test_leitura_que_termina_depois_do_prazo_recusa(tmp_path):
    relogio = [0.0]
    (tmp_path / "Default" / "Extensions").mkdir(parents=True)

    def inventario(*_):
        relogio[0] = a.PRAZO_INVENTARIO_INICIAL_S

    vigia = a.Vigilancia(
        tmp_path,
        tmp_path / "brave.exe",
        relogio=lambda: relogio[0],
        inventario=inventario,
    )
    with pytest.raises(a.RecusaSessao, match="^INVENTARIO_ASSISTIDO_INDISPONIVEL$"):
        vigia.assentar()
    assert vigia.erro is not None and vigia.linha_base is None


def test_preferencias_ausentes_na_barreira_nao_aguardam(tmp_path, monkeypatch):
    (tmp_path / "Default" / "Extensions").mkdir(parents=True)
    vigia = a.Vigilancia(tmp_path, tmp_path / "brave.exe")
    vigia.linha_base = time.monotonic()
    monkeypatch.setattr(
        vigia.cond, "wait", lambda _: vigia.notificar(next(iter(vigia.sentinelas)), 1)
    )
    with pytest.raises(a.RecusaSessao, match="^INVENTARIO_ASSISTIDO_INDISPONIVEL$"):
        vigia.barreira()


@pytest.mark.parametrize("manifesto", [None, "{", "[]"])
@pytest.mark.parametrize("location", [1, 5])
def test_manifesto_indisponivel_ou_invalido_nao_aguarda(tmp_path, manifesto, location):
    default = tmp_path / "Default"
    extensao = default / "Extensions" / "extensao"
    extensao.mkdir(parents=True)
    if manifesto is not None:
        (extensao / "manifest.json").write_text(manifesto, encoding="utf-8")
    for nome in ("Secure Preferences", "Preferences"):
        (default / nome).write_text(
            json.dumps(
                {
                    "extensions": {
                        "settings": {
                            "id": {
                                "location": location,
                                "path": str(extensao) if location == 5 else "extensao",
                            }
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
    vigia = a.Vigilancia(tmp_path, tmp_path / "brave.exe", relogio=lambda: 0)
    with pytest.raises(a.RecusaSessao, match="^INVENTARIO_ASSISTIDO_INDISPONIVEL$"):
        vigia.assentar()
    assert vigia.erro is not None and vigia.linha_base is None


def test_componentes_absolutos_embutidos_e_preferences_sem_settings(tmp_path):
    perfil, instalacao = tmp_path / "perfil", tmp_path / "Application"
    (perfil / "Default").mkdir(parents=True)
    settings = {}
    for nome in ("pdf", "brave_extension"):
        caminho = instalacao / "158.1.100.58" / "resources" / nome
        caminho.mkdir(parents=True)
        (caminho / "manifest.json").write_text(
            json.dumps({"permissions": ["webRequest", "webRequestBlocking"]}),
            encoding="utf-8",
        )
        assert caminho.is_absolute()
        settings[nome] = {"location": 5, "path": str(caminho)}
    (perfil / "Default" / "Secure Preferences").write_text(
        json.dumps({"extensions": {"settings": settings}}), encoding="utf-8"
    )
    (perfil / "Default" / "Preferences").write_text("{}", encoding="utf-8")
    a.inventariar(perfil, instalacao / "brave.exe")


@pytest.mark.parametrize("manifesto", [{"permissions": ["webRequest"]}, None, [], "{}"])
@pytest.mark.parametrize(
    "location,dentro,relativo",
    [
        (5, True, False),
        (5, False, False),
        (10, True, False),
        (1, False, True),
        (5, True, True),
    ],
)
def test_manifesto_componente_nas_preferencias(
    tmp_path, manifesto, location, dentro, relativo
):
    perfil, instalacao = tmp_path / "perfil", tmp_path / "Application"
    default = perfil / "Default"
    (default / "Extensions").mkdir(parents=True)
    caminho = instalacao / "158/resources/pdf" if dentro else tmp_path / "externa"
    # Inclusive o diretório do componente pode não existir: recursos embutidos.
    item = {
        "location": location,
        "path": "pdf" if relativo else str(caminho),
        "manifest": manifesto,
    }
    (default / "Secure Preferences").write_text(
        json.dumps({"extensions": {"settings": {"pdf": item}}}), encoding="utf-8"
    )
    (default / "Preferences").write_text("{}", encoding="utf-8")
    vigia = a.Vigilancia(perfil, instalacao / "brave.exe", relogio=lambda: 11)
    if location == 5 and dentro and not relativo and isinstance(manifesto, dict):
        vigia.assentar()
        assert vigia.inventario_lido and vigia.erro is None
    else:
        with pytest.raises(a.RecusaSessao, match="^INVENTARIO_ASSISTIDO_INDISPONIVEL$"):
            vigia.assentar()
        assert vigia.linha_base is None and vigia.erro is not None


def test_manifesto_location_10_vedado_encerra(tmp_path):
    default = tmp_path / "perfil/Default"
    default.mkdir(parents=True)
    externo = tmp_path / "Application/externo"
    externo.mkdir(parents=True)
    (externo / "manifest.json").write_text(
        '{"permissions": ["webRequest"]}', encoding="utf-8"
    )
    item = {"location": 10, "path": str(externo), "manifest": {}}
    for nome in ("Secure Preferences", "Preferences"):
        (default / nome).write_text(
            json.dumps({"extensions": {"settings": {"externo": item}}}),
            encoding="utf-8",
        )
    vigia = a.Vigilancia(
        default.parent, tmp_path / "Application/brave.exe", relogio=lambda: 11
    )
    with pytest.raises(a.RecusaSessao, match="^EXTENSAO_INTERCEPTADORA$"):
        vigia.assentar()
    assert vigia.erro == "EXTENSAO_INTERCEPTADORA" and vigia.linha_base is None


@pytest.mark.parametrize(
    "permissao,location,dentro,aceita",
    [
        ("webRequest", 5, True, True),
        ("webRequest", 10, True, False),
        ("proxy", 1, False, False),
        ("declarativeNetRequest", 1, False, False),
        ("debugger", 4, False, False),
    ],
)
def test_inventario(tmp_path, permissao, location, dentro, aceita):
    perfil, exe = tmp_path / "perfil", tmp_path / "browser" / "brave.exe"
    caminho = exe.parent / "componente" if dentro else tmp_path / "externa"
    caminho.mkdir(parents=True)
    (caminho / "manifest.json").write_text(json.dumps({"permissions": [permissao]}))
    (perfil / "Default").mkdir(parents=True)
    for nome in ("Preferences", "Secure Preferences"):
        (perfil / "Default" / nome).write_text(
            json.dumps(
                {
                    "extensions": {
                        "settings": {"id": {"location": location, "path": str(caminho)}}
                    }
                }
            )
        )
    if aceita:
        a.inventariar(perfil, exe)
    else:
        with pytest.raises(a.RecusaSessao):
            a.inventariar(perfil, exe)
    (perfil / "Default" / "Secure Preferences").unlink()
    with pytest.raises(a.RecusaSessao):
        a.inventariar(perfil, exe)


@pytest.mark.parametrize("acao", [1, 2, 3, 4, 5, 0])
def test_vigilancia_apos_linha_base(tmp_path, acao):
    relogio = [0.0]
    (tmp_path / "Default" / "Extensions").mkdir(parents=True)
    vigia = a.Vigilancia(
        tmp_path,
        tmp_path / "brave.exe",
        relogio=lambda: relogio[0],
        inventario=lambda *_: None,
    )
    relogio[0] = 9
    assert vigia.assentar() is None
    vigia.notificar("Default/Extensions/nova", 1)
    relogio[0] = 18
    assert vigia.assentar() is None
    relogio[0] = 20
    assert vigia.assentar() == 20
    if acao:
        vigia.notificar("Default/Extensions/nova", acao)
    else:
        vigia.falhar()
    with pytest.raises(a.RecusaSessao):
        vigia.conferir()


def test_barreira_sentinela_e_atraso(tmp_path, monkeypatch):
    (tmp_path / "Default" / "Extensions").mkdir(parents=True)
    vigia = a.Vigilancia(tmp_path, tmp_path / "brave.exe", inventario=lambda *_: None)
    vigia.linha_base = 1

    def aviso():
        while not vigia.sentinelas:
            time.sleep(0.001)
        vigia.notificar(next(iter(vigia.sentinelas)), 1)

    thread = threading.Thread(target=aviso)
    thread.start()
    vigia.barreira()
    thread.join()

    def timeout(_):
        vigia.falhar("BARREIRA_ASSISTIDA_EXPIRADA")

    monkeypatch.setattr(vigia.cond, "wait", timeout)
    with pytest.raises(a.RecusaSessao, match="EXPIRADA"):
        vigia.barreira()


@pytest.mark.parametrize(
    "politica",
    [
        "ProxySettings",
        "ProxyMode",
        "ProxyServer",
        "ProxyPacUrl",
        "CloudManagementEnrollmentToken",
        "ExtensionSettings",
        "forcelist",
        "falha",
    ],
)
def test_registro_recusa_antes_do_lancamento(politica):
    valores = {politica: "SEGREDO"}
    if politica == "ExtensionSettings":
        valores = {
            politica: json.dumps({"*": {"installation_mode": "force_installed"}})
        }
    registro = RegistroSintetico(
        valores, forca=politica == "forcelist", falha=politica == "falha"
    )
    with pytest.raises(a.RecusaSessao) as exc:
        a.conferir_politicas("brave", registro=registro)
    assert "SEGREDO" not in str(exc.value)


def test_reabertura_sem_rede(tmp_path, monkeypatch):
    from freoa_verifica.connectors.normas_leg import NormasPortao
    from freoa_verifica.connectors.camara_estado import Estado

    monkeypatch.setattr(t, "fetch", lambda *_: pytest.fail("reabertura não emite rede"))
    portao = NormasPortao(None, home=tmp_path)
    assert portao.reabrir("0087/0089: autorização sintética") is False
    estado = Estado(
        tmp_path, hosts=frozenset({"normas.leg.br"}), diretorio="normas_leg"
    )
    assert estado._bloqueios("normas.leg.br")["reaberturas"][-1]["decisao"].startswith(
        "0087"
    )


def test_limpeza_e_recuperacao_confinadas(tmp_path, monkeypatch):
    monkeypatch.setattr(a, "proteger_diretorio", lambda _: None)
    monkeypatch.setattr(a, "_processos_do_perfil", lambda *_: set())
    path = a.preparar_diretorio(tmp_path)
    (path / "arquivo").write_bytes(b"segredo-sintetico")
    novo = a.preparar_diretorio(tmp_path)
    assert not path.exists() and novo.exists()
    with pytest.raises(a.RecusaSessao):
        a.limpar_diretorio(tmp_path, novo.parent)
    a.limpar_diretorio(novo, novo.parent)
    assert not novo.exists()


def _relogio_limpeza(monkeypatch):
    agora = [0.0]
    monkeypatch.setattr(
        a,
        "time",
        SimpleNamespace(
            monotonic=lambda: agora[0],
            sleep=lambda s: agora.__setitem__(0, agora[0] + s),
        ),
    )
    return agora


@pytest.mark.parametrize("sai", [True, False])
def test_limpeza_aguarda_filhos_apos_saida_do_principal(tmp_path, monkeypatch, sai):
    agora = _relogio_limpeza(monkeypatch)
    perfil = tmp_path / "sessao-0089-filha"
    perfil.mkdir()
    (perfil / "bloqueado").write_bytes(b"cache sintetico")
    monkeypatch.setattr(
        a,
        "_processos_do_perfil",
        lambda *_: {42} if not sai or agora[0] < 0.3 else set(),
    )
    real = a.shutil.rmtree
    remocoes = []

    def apagar(path):
        assert agora[0] >= 0.3
        remocoes.append(path)
        real(path)

    monkeypatch.setattr(a.shutil, "rmtree", apagar)
    if sai:
        a.limpar_diretorio(perfil, tmp_path)
        assert remocoes == [perfil] and not perfil.exists()
    else:
        with pytest.raises(a.RecusaSessao, match="LIMPEZA_ASSISTIDA_PENDENTE"):
            a.limpar_diretorio(perfil, tmp_path)
        assert not remocoes
        assert (perfil / ".limpeza-pendente").is_file()
        assert agora[0] == pytest.approx(a.PRAZO_SAIDA_NAVEGADOR_S)


@pytest.mark.parametrize("libera", [True, False])
def test_limpeza_arquivo_bloqueado_e_recuperacao(tmp_path, monkeypatch, capsys, libera):
    agora = _relogio_limpeza(monkeypatch)
    monkeypatch.setattr(a, "_processos_do_perfil", lambda *_: set())
    monkeypatch.setattr(a, "proteger_diretorio", lambda *_: None)
    perfil = a.preparar_diretorio(tmp_path)
    fora = tmp_path / "fora"
    fora.write_bytes(b"intocado")
    real = a.shutil.rmtree
    tentativas = []

    def bloqueado(path):
        tentativas.append(path)
        if not libera or len(tentativas) < 3:
            erro = PermissionError("bloqueio sintetico")
            erro.winerror = 32
            raise erro
        real(path)

    with monkeypatch.context() as patch:
        patch.setattr(a.shutil, "rmtree", bloqueado)
        if libera:
            a.limpar_diretorio(perfil, perfil.parent)
            assert len(tentativas) == 3 and not perfil.exists()
        else:
            with pytest.raises(a.RecusaSessao, match="LIMPEZA_ASSISTIDA_PENDENTE"):
                a.limpar_diretorio(perfil, perfil.parent)
            assert len(tentativas) == a.TENTATIVAS_LIMPEZA
            assert (perfil / ".limpeza-pendente").is_file()
            assert str(perfil) in capsys.readouterr().out
    assert agora[0] < 2
    novo = a.preparar_diretorio(tmp_path)
    assert not perfil.exists() and novo.exists() and fora.read_bytes() == b"intocado"


def test_limpeza_falha_de_enumeracao_preserva_perfil(tmp_path, monkeypatch, capsys):
    perfil = tmp_path / "sessao-0089-enumeracao"
    perfil.mkdir()

    def indisponivel(*_):
        raise a.RecusaSessao("ENUMERACAO_ASSISTIDA_INDISPONIVEL")

    monkeypatch.setattr(a, "_processos_do_perfil", indisponivel)
    with pytest.raises(a.RecusaSessao, match="LIMPEZA_ASSISTIDA_PENDENTE"):
        a.limpar_diretorio(perfil, tmp_path)
    assert perfil.exists() and (perfil / ".limpeza-pendente").is_file()
    assert "LIMPEZA_ASSISTIDA_PENDENTE" in capsys.readouterr().out


@pytest.mark.parametrize("job", [True, False])
@pytest.mark.parametrize("saida_principal", [0.2, 0.6])
def test_encerramento_espera_principal_e_filhos(
    tmp_path, monkeypatch, job, saida_principal
):
    agora = _relogio_limpeza(monkeypatch)
    acoes = []

    def terminar(*_):
        acoes.append("job")

    def fechar(*_):
        acoes.append("handle")

    kernel = SimpleNamespace(TerminateJobObject=terminar, CloseHandle=fechar)
    monkeypatch.setattr(a, "_dlls", lambda: (kernel, None))
    proc = SimpleNamespace(
        _fv_job=123 if job else None,
        poll=lambda: 0 if agora[0] >= saida_principal else None,
        wait=lambda **_: acoes.append("wait"),
        kill=lambda: acoes.append("kill"),
    )
    monkeypatch.setattr(
        a, "_processos_do_perfil", lambda *_: {42} if agora[0] < 0.4 else set()
    )
    a.fechar_navegador(proc, tmp_path)
    assert agora[0] >= max(0.4, saida_principal)
    assert acoes == (["job", "handle"] if job else ["kill"]) + ["wait"]


def test_prazo_inclui_principal_e_enumeracao(tmp_path, monkeypatch):
    agora = _relogio_limpeza(monkeypatch)
    monkeypatch.setattr(a, "_processos_do_perfil", lambda *_: set())
    proc = SimpleNamespace(poll=lambda: None)
    with pytest.raises(a.RecusaSessao, match="SAIDA_ASSISTIDA_NAO_CONFIRMADA"):
        a.aguardar_saida_navegador(tmp_path, proc)
    assert agora[0] == pytest.approx(a.PRAZO_SAIDA_NAVEGADOR_S)

    def demorar(*_):
        agora[0] += a.PRAZO_SAIDA_NAVEGADOR_S + 1
        return set()

    monkeypatch.setattr(a, "_processos_do_perfil", demorar)
    with pytest.raises(a.RecusaSessao, match="SAIDA_ASSISTIDA_NAO_CONFIRMADA"):
        a.aguardar_saida_navegador(tmp_path)


def test_sessao_finaliza_todos_os_recursos_mesmo_com_falha(tmp_path, monkeypatch):
    from contextlib import nullcontext
    from freoa_verifica.assistida import sessao as s

    acoes = []
    monkeypatch.setattr(s, "conferir_terminal", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _: "INICIAR")
    monkeypatch.setattr(
        a, "navegador_instalado", lambda _: ("brave", tmp_path / "brave.exe")
    )
    monkeypatch.setattr(a, "conferir_politicas", lambda _: None)
    monkeypatch.setattr(a, "proteger_diretorio", lambda _: None)
    monkeypatch.setattr(a, "lock_sessao", lambda _: nullcontext())
    monkeypatch.setattr(a, "Vigilancia", lambda *_: None)
    monkeypatch.setattr(a, "_processos_do_perfil", lambda *_: set())
    monkeypatch.setattr(
        a,
        "ObservadorWindows",
        lambda _: SimpleNamespace(fechar=lambda: acoes.append("observador")),
    )
    monkeypatch.setattr(
        a, "lancar_pipe", lambda *_: (SimpleNamespace(poll=lambda: None), None, None)
    )
    monkeypatch.setattr(
        s, "CanalPipe", lambda *_: SimpleNamespace(fechar=lambda: acoes.append("canal"))
    )

    def falhar(*_):
        raise a.RecusaSessao("FALHA_SINTETICA")

    monkeypatch.setattr(a, "fechar_navegador", falhar)
    monkeypatch.setattr(
        s,
        "AdaptadorCDP",
        lambda *_: SimpleNamespace(
            executar=falhar,
            comando=lambda *_: None,
            descartar=lambda: acoes.append("adaptador"),
        ),
    )
    args = SimpleNamespace(
        fonte="planalto", alvo=None, home=str(tmp_path), navegador="brave"
    )
    assert s.executar(args) == 2
    assert acoes == ["canal", "adaptador", "observador"]
    assert not list((tmp_path / "staging/sessoes-assistidas").glob("sessao-0089-*"))


@pytest.mark.skipif(os.name != "nt", reason="enumeração Windows, processo simulado")
def test_enumeracao_somente_leitura_confere_argumento_exato(tmp_path, monkeypatch):
    perfil = tmp_path / "sessao-0089-com espacos"
    linhas = [
        {"ProcessId": 1, "CommandLine": f'brave.exe --user-data-dir="{perfil}"'},
        {
            "ProcessId": 2,
            "CommandLine": f'brave.exe --type=gpu --user-data-dir "{perfil}"',
        },
        {"ProcessId": 3, "CommandLine": f'brave.exe --user-data-dir="{perfil}-outra"'},
        {"ProcessId": 4, "CommandLine": f'outro.exe --titulo="{perfil}"'},
        {"ProcessId": 5, "CommandLine": None},
    ]

    def enumerar(args, **kw):
        assert "-NoProfile" in args and "Get-CimInstance Win32_Process" in args[-1]
        assert str(perfil) not in args[-1]
        assert (
            kw["timeout"] == 1 and kw["creationflags"] == a.subprocess.CREATE_NO_WINDOW
        )
        return SimpleNamespace(stdout=json.dumps(linhas))

    monkeypatch.setattr(a.subprocess, "run", enumerar)
    assert a._processos_do_perfil(perfil, 1) == {1, 2}
