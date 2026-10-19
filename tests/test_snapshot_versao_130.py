"""D2: `fv snapshot install` só aceita o asset da release da versão instalada, por digest."""
import json
from types import SimpleNamespace

import pytest

from freoa_verifica import __version__, acervo, snapshot
from freoa_verifica.connectors import httputil

NOME_ATUAL = f"freoa-verifica-snapshot-20260101-{__version__}.tar.gz"
D_ATUAL = "a" * 64
D_ANTIGO = "b" * 64
URL = "https://github.com/rickfreoa/freoa-verifica/releases/download/v%s/" % __version__


@pytest.fixture
def lista(monkeypatch):
    entradas = [
        {"arquivo": "freoa-verifica-snapshot-antigo-0.9.0.tar.gz", "sha256": D_ANTIGO,
         "versao_pacote_min": "0.9.0", "derived_version": 3},
        {"arquivo": NOME_ATUAL, "sha256": D_ATUAL, "versao_pacote_min": __version__, "derived_version": 4},
    ]
    monkeypatch.setattr(snapshot, "_snapshots_oficiais", lambda: entradas)


def simular(monkeypatch, releases):
    """`releases` mapeia a tag para o JSON; tag ausente responde 404 como falha de transporte."""
    chamadas = []

    def fetch(url, **kwargs):
        chamadas.append(url)
        tag = url.rsplit("/releases/tags/", 1)[1]
        if tag not in releases:
            raise RuntimeError("http_404")
        return SimpleNamespace(body=json.dumps(releases[tag]).encode())

    monkeypatch.setattr(httputil, "connector_fetch", fetch)
    monkeypatch.setattr(snapshot, "_download_release", lambda url, **kw: url)
    return chamadas


def test_busca_a_release_da_versao_instalada(lista, monkeypatch):
    chamadas = simular(monkeypatch, {f"v{__version__}": {"assets": [
        {"name": NOME_ATUAL, "digest": "sha256:" + D_ATUAL, "browser_download_url": URL + NOME_ATUAL}]}})
    assert snapshot._download_latest_release() == URL + NOME_ATUAL
    assert chamadas == [f"https://api.github.com/repos/rickfreoa/freoa-verifica/releases/tags/v{__version__}"]


def test_release_da_versao_sem_asset_falha_sem_buscar_anterior(lista, monkeypatch):
    antiga = {"assets": [{"name": "freoa-verifica-snapshot-antigo-0.9.0.tar.gz", "browser_download_url": "ANTIGO"}]}
    chamadas = simular(monkeypatch, {f"v{__version__}": {"assets": [{"name": "freoa_verifica.whl"}]}, "v0.9.0": antiga})
    with pytest.raises(RuntimeError, match="release_sem_asset_da_versao"):
        snapshot._download_latest_release()
    assert len(chamadas) == 1


def test_release_ausente_falha_explicitamente(lista, monkeypatch):
    simular(monkeypatch, {})
    with pytest.raises(RuntimeError, match="http_404"):
        snapshot._download_latest_release()


def test_asset_de_outra_versao_na_release_e_ignorado(lista, monkeypatch):
    simular(monkeypatch, {f"v{__version__}": {"assets": [
        {"name": "freoa-verifica-snapshot-antigo-0.9.0.tar.gz", "browser_download_url": "ANTIGO"}]}})
    with pytest.raises(RuntimeError, match="release_sem_asset_da_versao"):
        snapshot._download_latest_release()


def test_digest_divergente_do_github_nao_baixa(lista, monkeypatch):
    simular(monkeypatch, {f"v{__version__}": {"assets": [
        {"name": NOME_ATUAL, "digest": "sha256:" + "0" * 64, "browser_download_url": "RUIM"}]}})
    with pytest.raises(RuntimeError, match="release_sem_asset_da_versao"):
        snapshot._download_latest_release()


def test_release_rascunho_recusada(lista, monkeypatch):
    simular(monkeypatch, {f"v{__version__}": {"draft": True, "assets": [
        {"name": NOME_ATUAL, "browser_download_url": URL + NOME_ATUAL}]}})
    with pytest.raises(RuntimeError, match="release_nao_publicada"):
        snapshot._download_latest_release()


def test_vincular_aceita_digest_da_versao(lista):
    assert snapshot._vincular(D_ATUAL, False)["vinculado"] is True


def test_vincular_recusa_digest_de_outra_versao(lista):
    with pytest.raises(ValueError, match="SNAPSHOT_OUTRA_VERSAO"):
        snapshot._vincular(D_ANTIGO, False)


def test_vincular_outra_versao_so_com_flag_e_nao_vinculado(lista):
    r = snapshot._vincular(D_ANTIGO, True)
    assert r["vinculado"] is False and r["snapshot_sha256"] == D_ANTIGO


def test_doctor_compara_digest_instalado_com_lista(lista):
    ok = acervo.verificar_digest_instalado({"snapshot_sha256": D_ATUAL})
    assert ok["status"] == "ok" and ok["detalhe"]["confere"] is True and ok["detalhe"]["esperados"] == [D_ATUAL]
    outro = acervo.verificar_digest_instalado({"snapshot_sha256": D_ANTIGO})
    assert outro["status"] == "alerta" and outro["detalhe"]["confere"] is False
    assert acervo.verificar_digest_instalado({})["status"] == "alerta"


@pytest.mark.parametrize("conteudo,esperado,status", [
    ('{"attestation_verificada": true}', True, "ok"),
    ('{"attestation_verificada": false}', False, "alerta"),
    (None, None, "alerta"),
])
def test_doctor_exibe_attestation(tmp_path, monkeypatch, conteudo, esperado, status):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    if conteudo is not None:
        (tmp_path / "freoa-verifica").mkdir()
        (tmp_path / "freoa-verifica" / "instalacao.json").write_text(conteudo, encoding="utf-8")
    r = acervo.attestation_instalacao()
    assert r["detalhe"]["attestation_verificada"] is esperado and r["status"] == status


def test_doctor_inclui_as_verificacoes(tmp_path, monkeypatch):
    from freoa_verifica.service import Verifica
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    with Verifica(tmp_path / "home") as svc:
        nomes = {c["nome"] for c in svc.doctor(offline=True)["verificacoes"]}
    assert {"snapshot_digest", "attestation"} <= nomes
