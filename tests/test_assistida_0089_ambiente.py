"""0089 (b): cenarios sinteticos offline, sem navegador ou rede."""

from __future__ import annotations

import json

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
    path = a.preparar_diretorio(tmp_path)
    (path / "arquivo").write_bytes(b"segredo-sintetico")
    novo = a.preparar_diretorio(tmp_path)
    assert not path.exists() and novo.exists()
    with pytest.raises(a.RecusaSessao):
        a.limpar_diretorio(tmp_path, novo.parent)
    a.limpar_diretorio(novo, novo.parent)
    assert not novo.exists()
