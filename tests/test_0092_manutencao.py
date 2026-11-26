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
        # Só adiamento e nada renovado não é sucesso (Codex r-Debian, achado 2).
        assert r["status"] == "adiado" and r["falhas"] == [] and len(r["adiadas"]) == 1
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


@pytest.mark.parametrize("status,codigo", [("ok", 0), ("parcial", 0), ("adiado", 1), ("indisponivel", 1), ("erro", 1)])
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
    monkeypatch.setattr(agenda, "_usuario_efetivo", lambda: "ana")
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
    assert ["loginctl", "enable-linger", "--", "ana"] in chamadas


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


# --- Codex r-Debian (212fbf2) ---------------------------------------------------------------------------------

def _consultada(fonte, motivo, resultado="indisponivel"):
    return {"fonte": fonte, "resultado": resultado, "motivo": motivo}


@pytest.mark.parametrize("motivo", sorted(rev.MOTIVOS_ADIAMENTO))
def test_motivo_agregado_por_fonte_e_reconhecido_como_adiamento(tmp_path, monkeypatch, motivo):
    """Achado 1: `_capture_work` agrega `fonte:motivo`; o teste anterior injetava o motivo simples."""
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    exc = SourceUnavailable(f"camara_legin:{motivo}", [_consultada("camara_legin", motivo)])
    with Verifica(tmp_path) as svc:
        work_id = _obra(svc)
        monkeypatch.setattr(svc, "_capture_work", lambda *a, **k: (_ for _ in ()).throw(exc))
        r = svc.renovar_acervo(dias=1)
        assert r["status"] == "adiado" and r["falhas"] == [] and r["adiadas"][0]["work_id"] == work_id


def test_fora_de_alcance_mais_teto_e_adiamento(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    exc = SourceUnavailable("camara_legin:especie_busca_nao_demonstrada;normas_leg:teto_de_sessao",
                            [_consultada("camara_legin", "especie_busca_nao_demonstrada"),
                             _consultada("normas_leg", "teto_de_sessao")])
    with Verifica(tmp_path) as svc:
        _obra(svc)
        monkeypatch.setattr(svc, "_capture_work", lambda *a, **k: (_ for _ in ()).throw(exc))
        assert svc.renovar_acervo(dias=1)["status"] == "adiado"


@pytest.mark.parametrize("consultadas", [
    [_consultada("camara_legin", "http_503"), _consultada("normas_leg", "teto_de_chamada")],
    [_consultada("camara_legin", "RuntimeError", resultado="erro")],
    [_consultada("camara_legin", "teto_de_chamada"), _consultada("normas_leg", "RuntimeError", resultado="erro")],
])
def test_causa_mista_continua_falha(tmp_path, monkeypatch, consultadas):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    exc = SourceUnavailable(";".join(f"{c['fonte']}:{c['motivo']}" for c in consultadas), consultadas)
    with Verifica(tmp_path) as svc:
        work_id = _obra(svc)
        monkeypatch.setattr(svc, "_capture_work", lambda *a, **k: (_ for _ in ()).throw(exc))
        r = svc.renovar_acervo(dias=1)
        assert r["status"] == "indisponivel" and r["adiadas"] == [] and r["falhas"][0]["work_id"] == work_id


class _Teto:
    def __init__(self, depois: int, motivo: str):
        self.n, self.depois, self.motivo = 0, depois, motivo

    def __call__(self, con, work):
        from freoa_verifica.connectors.base import Unavailable

        self.n += 1
        if self.n > self.depois:
            raise Unavailable(self.motivo)
        return {"encoding": []}, "0" * 64, "2026-11-26T00:00:00+00:00"


@pytest.mark.parametrize("motivo", sorted(rev.MOTIVOS_ADIAMENTO))
def test_revalidacao_so_adiada_nao_e_ok(tmp_path, monkeypatch, motivo):
    """Achado 2: revalidação com apenas `adiado` devolvia `ok`."""
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    monkeypatch.setattr(rev, "_ler_metadados", _Teto(0, motivo))
    with Verifica(tmp_path) as svc:
        _obra(svc)
        r = svc.revalidar_acervo()
        assert r["status"] == "adiado" and r["contagens"]["adiado"] == 1


@pytest.mark.parametrize("reval,renov,renovadas,esperado", [
    ("ok", "ok", 0, "ok"),
    ("adiado", "adiado", 0, "adiado"),
    ("ok", "adiado", 0, "adiado"),        # nada concluído em parte alguma
    ("ok", "parcial", 1, "parcial"),
    ("parcial", "ok", 0, "parcial"),
    ("indisponivel", "indisponivel", 0, "indisponivel"),
])
def test_status_agregado_de_manter(tmp_path, monkeypatch, reval, renov, renovadas, esperado):
    contagens = {"inalterado": 1 if reval == "parcial" else 0, "adiado": 1 if reval in ("adiado", "parcial") else 0}
    monkeypatch.setattr(Verifica, "revalidar_acervo",
                        lambda self, **k: {"status": reval, "contagens": contagens, "obras": 1})
    monkeypatch.setattr(Verifica, "renovar_acervo",
                        lambda self, **k: {"status": renov, "renovadas": [{}] * renovadas, "falhas": [],
                                           "adiadas": [{}] if renov in ("adiado", "parcial") else [],
                                           "candidatas": 1})
    with Verifica(tmp_path) as svc:
        r = svc.manter_acervo()
        assert r["status"] == esperado
        assert r["manutencao"]["falhas"] is (esperado == "indisponivel")


@pytest.mark.parametrize("registro,esperado", [
    ({"status": "parcial", "falhas": False}, "ok"),        # só teto, com progresso: segue a regra de idade
    ({"status": "parcial", "falhas": True}, "alerta"),
    ({"status": "parcial"}, "alerta"),                     # registro antigo, sem o campo
    ({"status": "adiado", "falhas": False}, "falha"),      # nada concluído
])
def test_doctor_distingue_adiamento_de_falha(tmp_path, registro, esperado):
    import json
    from datetime import datetime, timezone

    fim = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    (tmp_path / "manutencao.json").write_text(json.dumps({**registro, "fim": fim}), encoding="utf-8")
    assert rev.consulta_manutencao(tmp_path)["status"] == esperado


@pytest.mark.skipif(sys.platform == "win32", reason="pwd só existe em POSIX")
def test_usuario_do_linger_vem_do_uid_e_nao_do_ambiente(monkeypatch):
    """Achado 3: getpass.getuser() lia LOGNAME; `--help` virava opção do loginctl."""
    import os
    import pwd

    monkeypatch.setenv("LOGNAME", "--help")
    monkeypatch.setenv("USER", "--help")
    assert agenda._usuario_efetivo() == pwd.getpwuid(os.geteuid()).pw_name


@pytest.mark.skipif(sys.platform == "win32", reason="pwd só existe em POSIX")
@pytest.mark.parametrize("nome", ["--help", "-x", "a b", "", "a;b"])
def test_nome_de_usuario_estranho_nao_vai_ao_loginctl(monkeypatch, nome):
    import pwd

    monkeypatch.setattr(pwd, "getpwuid", lambda uid: type("P", (), {"pw_name": nome})())
    assert agenda._usuario_efetivo() is None
    linger, aviso = agenda._linger()
    assert linger is False and "uid efetivo" in aviso


def test_excecao_no_loginctl_vira_aviso_e_preserva_o_timer(linux, tmp_path):
    """Achado 4: PermissionError no loginctl transformava agendamento instalado em erro."""
    chamadas, _ = linux

    def executar(cmd, entrada=None):
        chamadas.append(cmd)
        if cmd[0] == "loginctl":
            raise PermissionError("negado")
        return 0, "", ""

    agenda.definir_executar_sistema(executar)
    r = agenda.agendar_instalar(tmp_path / "h", "05:43")
    assert r["status"] == "ok" and r["linger"] is False and "PermissionError" in r["aviso"]
