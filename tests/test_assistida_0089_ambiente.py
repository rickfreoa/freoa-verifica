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
