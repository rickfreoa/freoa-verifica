"""0092: agendamento da manutenção do acervo pelo instalador, em Windows, Linux (systemd ou cron) e macOS."""
from __future__ import annotations

import plistlib
import sys
from pathlib import Path

import pytest

from freoa_verifica import acervo_manutencao as agenda
from freoa_verifica.cli import build_parser


@pytest.fixture
def chamadas(monkeypatch, tmp_path):
    registro: list[tuple[list[str], str | None]] = []
    respostas: dict[str, tuple[int, str, str]] = {}

    def executar(cmd, entrada=None):
        registro.append((cmd, entrada))
        return respostas.get(" ".join(cmd[:2]), (0, "", ""))

    agenda.definir_executar_sistema(executar)
    import os

    if hasattr(os, "geteuid") and os.geteuid() == 0:
        monkeypatch.setattr(os, "geteuid", lambda: 1000)  # sessão como root: simula usuário comum (root é dono aceito)
    monkeypatch.setattr(agenda.Path, "home", classmethod(lambda cls: tmp_path / "usuario"))  # nunca o home real
    monkeypatch.setattr(agenda, "caminho_fv", lambda: Path("/opt/fv venv/bin/fv"))
    yield registro, respostas
    agenda.definir_executar_sistema(None)


def test_macos_launchagent_valido_e_carregado_no_dominio_do_usuario(chamadas, monkeypatch, tmp_path):
    registro, _ = chamadas
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(agenda, "_uid", lambda: 501)
    home = tmp_path / "home com espaço"
    r = agenda.agendar_instalar(home, "05:43")
    assert r["status"] == "ok" and r["mecanismo"] == "launchd"
    plist = tmp_path / "usuario/Library/LaunchAgents/br.freoa.verifica.manter.plist"
    dados = plistlib.loads(plist.read_bytes())
    assert dados["Label"] == "br.freoa.verifica.manter"
    assert dados["ProgramArguments"] == [str(Path("/opt/fv venv/bin/fv")), *agenda.argumentos(home)]
    assert dados["StartCalendarInterval"] == {"Hour": 5, "Minute": 43} and dados["StartInterval"] == 7200
    assert dados["EnvironmentVariables"]["FV_HOME"] == str(home)
    build_parser().parse_args(dados["ProgramArguments"][1:])  # a linha agendada é aceita pelo próprio fv
    cmds = [c for c, _ in registro]
    assert cmds[0] == ["launchctl", "bootout", "gui/501/br.freoa.verifica.manter"]
    assert cmds[1] == ["launchctl", "bootstrap", "gui/501", str(plist)]


def test_macos_remover_descarrega_e_apaga(chamadas, monkeypatch, tmp_path):
    registro, _ = chamadas
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(agenda, "_uid", lambda: 501)
    agenda.agendar_instalar(tmp_path / "h", "05:43")
    assert agenda.agendar_remover()["status"] == "ok"
    assert not (tmp_path / "usuario/Library/LaunchAgents/br.freoa.verifica.manter.plist").exists()


def test_linux_sem_systemd_de_usuario_cai_no_crontab_preservando_linhas_alheias(chamadas, monkeypatch, tmp_path):
    registro, respostas = chamadas
    monkeypatch.setattr(sys, "platform", "linux")
    respostas["systemctl --user"] = (1, "", "Failed to connect to bus")
    respostas["crontab -l"] = (0, f"0 1 * * * backup\n5 */2 * * * velho {agenda.MARCA_CRON}\n", "")
    r = agenda.agendar_instalar(tmp_path / "h", "05:43")
    assert r["status"] == "ok" and r["mecanismo"] == "cron" and "bus" in r["erro_systemd"]
    gravado = [e for c, e in registro if c == ["crontab", "-"]][-1]
    linhas = gravado.splitlines()
    assert linhas[0] == "0 1 * * * backup"  # linha do usuário intacta
    assert sum(agenda.MARCA_CRON in linha for linha in linhas) == 2  # a antiga saiu; entram intervalo e @reboot
    assert linhas[1].startswith("43 */2 * * * ") and linhas[2].startswith("@reboot ")
    assert "--home" in linhas[1] and "acervo manter --json" in linhas[1]


def test_linux_com_systemd_nao_toca_no_crontab(chamadas, monkeypatch, tmp_path):
    registro, _ = chamadas
    monkeypatch.setattr(sys, "platform", "linux")
    r = agenda.agendar_instalar(tmp_path / "h", "05:43")
    assert r["mecanismo"] == "systemd"
    assert not any(c[0] == "crontab" for c, _ in registro)


def test_linux_remover_limpa_systemd_e_crontab(chamadas, monkeypatch, tmp_path):
    registro, respostas = chamadas
    monkeypatch.setattr(sys, "platform", "linux")
    respostas["crontab -l"] = (0, f"0 1 * * * backup\n@reboot x {agenda.MARCA_CRON}\n", "")
    assert agenda.agendar_remover()["status"] == "ok"
    assert [e for c, e in registro if c == ["crontab", "-"]][-1] == "0 1 * * * backup\n"


def test_comando_ausente_vira_codigo_127_sem_excecao(monkeypatch):
    agenda.definir_executar_sistema(None)
    assert agenda._rodar(["comando-que-nao-existe-fv-0092"])[0] == 127


# ------------------------------------------------------------------ auditoria Codex da 0092


def test_crontab_ilegivel_nao_e_sobrescrito(chamadas, monkeypatch, tmp_path):
    registro, respostas = chamadas
    monkeypatch.setattr(sys, "platform", "linux")
    respostas["systemctl --user"] = (1, "", "Failed to connect to bus")
    respostas["crontab -l"] = (1, "", "crontab: permission denied")
    r = agenda.agendar_instalar(tmp_path / "h", "05:43")
    assert r["status"] == "erro" and not any(c == ["crontab", "-"] for c, _ in registro)


def test_sem_crontab_comprovado_e_tabela_vazia(chamadas, monkeypatch, tmp_path):
    registro, respostas = chamadas
    monkeypatch.setattr(sys, "platform", "linux")
    respostas["systemctl --user"] = (1, "", "Failed to connect to bus")
    respostas["crontab -l"] = (1, "", "no crontab for usuario")
    assert agenda.agendar_instalar(tmp_path / "h", "05:43")["status"] == "ok"


@pytest.mark.skipif(sys.platform == "win32", reason="shell POSIX")
def test_home_hostil_nao_executa_nada_no_cron(chamadas, monkeypatch, tmp_path):
    import subprocess

    monkeypatch.setattr(agenda, "caminho_fv", lambda: Path("/bin/echo"))
    home = tmp_path / "acervo;touch PWNED;# $(touch PWNED2) 50%"
    linha = agenda.linha_cron(home, "05:43")[0]
    comando = linha.split(" ", 5)[5].split(" >/dev/null")[0].replace("\\%", "%")  # o que o cron entrega ao sh
    saida = subprocess.run(["sh", "-c", comando], cwd=tmp_path, capture_output=True, text=True, check=True).stdout
    assert str(home) in saida and not (tmp_path / "PWNED").exists() and not (tmp_path / "PWNED2").exists()
    assert "50\\%" in linha  # % escapado para o parser do cron


def test_home_com_quebra_de_linha_e_recusado(chamadas, monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(ValueError):
        agenda.agendar_instalar(tmp_path / "a\nb", "05:43")


def test_systemd_escapa_especificadores_e_variaveis():
    home = Path("/srv/acervo 100% $HOME")
    unidade = agenda.conteudo_systemd_service(home)
    assert "100%% $$HOME" in unidade and '"FV_HOME=' in unidade


@pytest.mark.skipif(sys.platform == "win32", reason="permissões POSIX")
def test_arquivos_agendados_sem_escrita_de_terceiros(chamadas, monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    alvo = tmp_path / "usuario/.config/systemd/user/fv-manter.service"
    alvo.parent.mkdir(parents=True)
    alheio = tmp_path / "alheio.service"
    alheio.write_text("original")
    alvo.symlink_to(alheio)  # link plantado: substituído, não seguido
    agenda.agendar_instalar(tmp_path / "h", "05:43")
    assert alheio.read_text() == "original" and not alvo.is_symlink()
    assert alvo.stat().st_mode & 0o077 == 0


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX")
def test_root_e_recusado(chamadas, monkeypatch, tmp_path):
    import os

    registro, _ = chamadas
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    r = agenda.agendar_instalar(tmp_path / "h", "05:43")
    assert r["status"] == "erro" and "root" in r["erro"] and not registro


def test_remover_propaga_falha_do_crontab(chamadas, monkeypatch, tmp_path):
    registro, respostas = chamadas
    monkeypatch.setattr(sys, "platform", "linux")
    respostas["systemctl --user"] = (1, "", "sem bus")
    respostas["crontab -l"] = (0, f"@reboot x {agenda.MARCA_CRON}\n", "")
    respostas["crontab -"] = (1, "", "falhou")
    assert agenda.agendar_remover()["status"] == "erro"


# ------------------------------------------------------------------ auditoria Codex da 0092, rodada 2


@pytest.mark.skipif(sys.platform == "win32", reason="permissões POSIX")
def test_executavel_em_diretorio_gravavel_por_terceiros_nao_e_agendado(chamadas, monkeypatch, tmp_path):
    registro, _ = chamadas
    monkeypatch.setattr(sys, "platform", "linux")
    venv = tmp_path / "venv" / "bin"
    venv.mkdir(parents=True)
    (venv / "fv").write_text("#!/bin/sh\n")
    (tmp_path / "venv").chmod(0o777)  # terceiro poderia trocar bin/ inteiro
    monkeypatch.setattr(agenda, "caminho_fv", lambda: venv / "fv")
    r = agenda.agendar_instalar(tmp_path / "h", "05:43")
    assert r["status"] == "erro" and "gravável" in r["erro"] and not registro
    (tmp_path / "venv").chmod(0o700)
    assert agenda.caminho_inseguro(venv / "fv") is None


def test_remover_com_crontab_ilegivel_nao_declara_sucesso(chamadas, monkeypatch, tmp_path):
    _, respostas = chamadas
    monkeypatch.setattr(sys, "platform", "linux")
    respostas["crontab -l"] = (1, "", "crontab: permission denied")
    assert agenda.agendar_remover()["status"] == "erro"


def test_remover_com_unidade_presente_e_disable_falho_nao_declara_sucesso(chamadas, monkeypatch, tmp_path):
    _, respostas = chamadas
    monkeypatch.setattr(sys, "platform", "linux")
    agenda.agendar_instalar(tmp_path / "h", "05:43")  # cria as unidades
    respostas["systemctl --user"] = (1, "", "falhou")
    respostas["crontab -l"] = (1, "", "no crontab for usuario")
    r = agenda.agendar_remover()
    assert r["status"] == "erro" and r["systemd"] is True
    assert (tmp_path / "usuario/.config/systemd/user/fv-manter.timer").exists()  # nada apagado sem desativar


# ------------------------------------------------------------------ auditoria Codex da 0092, rodada 3


@pytest.mark.skipif(sys.platform == "win32", reason="permissões POSIX")
def test_diretorio_de_unidade_aberto_e_fechado_antes_de_gravar(chamadas, monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    base = tmp_path / "usuario/.config/systemd/user"
    base.mkdir(parents=True)
    base.chmod(0o777)
    assert agenda.agendar_instalar(tmp_path / "h", "05:43")["status"] == "ok"
    assert base.stat().st_mode & 0o022 == 0


@pytest.mark.skipif(sys.platform == "win32", reason="permissões POSIX")
def test_ancestral_do_diretorio_de_unidade_aberto_recusa(chamadas, monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    (tmp_path / "usuario/.config").mkdir(parents=True)
    (tmp_path / "usuario/.config").chmod(0o777)
    r = agenda.agendar_instalar(tmp_path / "h", "05:43")
    assert r["status"] == "erro" and "gravável" in r["erro"]
    assert not (tmp_path / "usuario/.config/systemd/user/fv-manter.service").exists()


def test_mostrar_distingue_ausencia_de_consulta_indisponivel(chamadas, monkeypatch):
    _, respostas = chamadas
    monkeypatch.setattr(sys, "platform", "linux")
    respostas["systemctl --user"] = (1, "", "permission denied")
    respostas["crontab -l"] = (1, "", "permission denied")
    assert agenda.agendar_mostrar()["status"] == "indisponivel"
    respostas["systemctl --user"] = (4, "", "Unit fv-manter.timer could not be found.")
    respostas["crontab -l"] = (1, "", "no crontab for usuario")
    assert agenda.agendar_mostrar()["status"] == "ausente"
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(agenda, "_uid", lambda: 501)
    respostas["launchctl print"] = (5, "", "permission denied")
    assert agenda.agendar_mostrar()["status"] == "indisponivel"
    respostas["launchctl print"] = (113, "", "Could not find service")
    assert agenda.agendar_mostrar()["status"] == "ausente"


@pytest.mark.skipif(sys.platform == "win32", reason="permissões POSIX")
def test_escrita_do_grupo_privado_do_usuario_nao_e_insegura(tmp_path, monkeypatch):
    """CI: umask 002 das distribuições com grupo por usuário deixa g+w no grupo privado, que não dá acesso a ninguém."""
    alvo = tmp_path / "fv"
    alvo.write_text("x")
    alvo.chmod(0o664)
    monkeypatch.setattr(agenda, "_grupo_privado", lambda gid: True)
    assert agenda.caminho_inseguro(alvo) is None
    monkeypatch.setattr(agenda, "_grupo_privado", lambda gid: False)
    assert "gravável" in agenda.caminho_inseguro(alvo)
