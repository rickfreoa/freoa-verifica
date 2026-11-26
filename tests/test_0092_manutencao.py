"""0092, teste em Debian (colega): teto de chamadas não é falha; parcial não derruba o timer; saída do systemd."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from freoa_verifica import acervo_manutencao as agenda
from freoa_verifica import revalidacao as rev
from freoa_verifica.cli import main
from freoa_verifica.service import SourceUnavailable, Verifica
from tests.test_0091a_revalidacao import _obra


def test_teto_de_chamada_adia_sem_registrar_falha(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    tentativas = []

    def teto(*a, **k):
        tentativas.append(1)
        raise SourceUnavailable("teto_de_chamada")

    with Verifica(tmp_path) as svc:
        work_id = _obra(svc)
        monkeypatch.setattr(svc, "_capture_work", teto)
        r = svc.renovar_acervo(dias=1)
        assert r["status"] == "ok" and r["falhas"] == [] and len(r["adiadas"]) == 1
        assert r["adiadas"][0]["motivo"] == "teto_de_chamada" and len(tentativas) == 1
        assert svc.conn.execute("SELECT 1 FROM sync_state WHERE fonte=? AND chave=?",
                                (rev.FONTE_PENDENTE, work_id)).fetchone() is None  # nenhuma falha gravada


def test_falha_real_continua_falha(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        _obra(svc)
        monkeypatch.setattr(svc, "_capture_work", lambda *a, **k: (_ for _ in ()).throw(SourceUnavailable("http_503")))
        r = svc.renovar_acervo(dias=1)
        assert r["status"] == "indisponivel" and r["falhas"][0]["motivo"] == "http_503" and r["adiadas"] == []


@pytest.mark.parametrize("status,codigo", [("ok", 0), ("parcial", 0), ("indisponivel", 1), ("erro", 1)])
def test_saida_de_manter(tmp_path, monkeypatch, capsys, status, codigo):
    monkeypatch.setattr(Verifica, "manter_acervo", lambda self, **k: {"status": status})
    with pytest.raises(SystemExit) as exc:
        main(["--home", str(tmp_path), "acervo", "manter", "--json"])
    assert exc.value.code == codigo


@pytest.fixture
def linux(monkeypatch, tmp_path):
    import os

    chamadas: list[list[str]] = []
    respostas: dict[str, tuple[int, str, str]] = {}

    def executar(cmd, entrada=None):
        chamadas.append(cmd)
        return respostas.get(" ".join(cmd[:2]), (0, "", ""))

    agenda.definir_executar_sistema(executar)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(agenda.Path, "home", classmethod(lambda cls: tmp_path / "usuario"))
    monkeypatch.setattr(agenda, "caminho_fv", lambda: Path("/opt/fv/bin/fv"))
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.setattr("getpass.getuser", lambda: "ana")
    yield chamadas, respostas
    agenda.definir_executar_sistema(None)


def test_stderr_informativo_do_systemd_nao_e_erro(linux, tmp_path):
    _, respostas = linux
    respostas["systemctl --user"] = (0, "", "Created symlink '/home/ana/.config/systemd/user/timers.target.wants/x'.")
    r = agenda.agendar_instalar(tmp_path / "h", "05:43")
    assert r["status"] == "ok" and r["erro"] == "" and "Created symlink" in r["detalhe"]


def test_linger_ligado_quando_permitido(linux, tmp_path):
    chamadas, respostas = linux
    respostas["loginctl show-user"] = (0, "no\n", "")
    r = agenda.agendar_instalar(tmp_path / "h", "05:43")
    assert r["linger"] is True and "aviso" not in r
    assert ["loginctl", "enable-linger", "ana"] in chamadas


def test_linger_recusado_vira_aviso_sem_falhar(linux, tmp_path):
    _, respostas = linux
    respostas["loginctl show-user"] = (0, "no\n", "")
    respostas["loginctl enable-linger"] = (1, "", "Access denied")
    r = agenda.agendar_instalar(tmp_path / "h", "05:43")
    assert r["status"] == "ok" and r["linger"] is False
    assert "loginctl enable-linger ana" in r["aviso"] and "Access denied" in r["aviso"]


def test_linger_ja_ligado_nao_tenta_de_novo(linux, tmp_path):
    chamadas, respostas = linux
    respostas["loginctl show-user"] = (0, "yes\n", "")
    assert agenda.agendar_instalar(tmp_path / "h", "05:43")["linger"] is True
    assert not any(c[:2] == ["loginctl", "enable-linger"] for c in chamadas)
