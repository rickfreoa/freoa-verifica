"""Agendamento local de `fv acervo manter` (0091 emenda A), sem privilégio de administrador."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Callable

TAREFA_WIN = "FREOA Verifica - manter acervo"
HORA_PADRAO = "05:43"
UNIDADE_LINUX = "fv-manter"
ROTULO_MAC = "br.freoa.verifica.manter"
MARCA_CRON = "# freoa-verifica: fv acervo manter (decisao 0092)"


def caminho_fv() -> Path:
    exe = Path(sys.executable)
    if sys.platform == "win32":
        return exe.parent / "fv.exe"
    return exe.parent / "fv"


def argumentos(home: Path | None) -> list[str]:
    """Argumentos do `fv` na tarefa. `--home` é opção global: vem antes do subcomando."""
    return ([] if home is None else ["--home", str(home)]) + ["acervo", "manter", "--json"]


def linha_comando(home: Path | None) -> str:
    return " ".join([f'"{caminho_fv()}"'] + [f'"{a}"' if " " in a else a for a in argumentos(home)])


def xml_tarefa(home: Path | None, hora: str, *, intervalo_horas: int = 2) -> str:
    from xml.sax.saxutils import escape

    args = " ".join(f'"{a}"' if " " in a else a for a in argumentos(home))
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>FREOA Verifica: revalida metadados e renova o acervo (decisão 0091)</Description></RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-01-01T{hora}:00</StartBoundary>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
      <Repetition>
        <Interval>PT{intervalo_horas}H</Interval>
        <Duration>PT24H</Duration>
      </Repetition>
    </CalendarTrigger>
  </Triggers>
  <Principals><Principal id="Autor"><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <StartWhenAvailable>true</StartWhenAvailable>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT4H</ExecutionTimeLimit>
  </Settings>
  <Actions Context="Autor">
    <Exec><Command>{escape(str(caminho_fv()))}</Command><Arguments>{escape(args)}</Arguments></Exec>
  </Actions>
</Task>
"""


def comando_schtasks(home: Path | None, hora: str, arquivo_xml: Path) -> list[str]:
    return ["schtasks", "/Create", "/TN", TAREFA_WIN, "/XML", str(arquivo_xml), "/F"]


def conteudo_systemd_service(home: Path) -> str:
    return f"""[Unit]
Description=FREOA Verifica - manutenção do acervo

[Service]
Type=oneshot
Environment=FV_HOME={home}
ExecStart={linha_comando(home)}
"""


def conteudo_systemd_timer(hora: str, *, intervalo_horas: int = 2) -> str:
    hh, mm = hora.split(":", 1)
    return f"""[Unit]
Description=FREOA Verifica - manutenção diária do acervo

[Timer]
OnCalendar=*-*-* {hh}:{mm}:00
OnUnitActiveSec={intervalo_horas}h
Persistent=true

[Install]
WantedBy=timers.target
"""


def conteudo_launchd(home: Path, hora: str, *, intervalo_horas: int = 2) -> str:
    """LaunchAgent do usuário: horário diário mais intervalo; o launchd roda ao acordar o que perdeu dormindo."""
    from xml.sax.saxutils import escape

    hh, mm = (int(x) for x in hora.split(":", 1))
    args = "".join(f"\n    <string>{escape(a)}</string>" for a in [str(caminho_fv()), *argumentos(home)])
    log = escape(str(Path(home) / "manutencao-launchd.log"))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{ROTULO_MAC}</string>
  <key>ProgramArguments</key>
  <array>{args}
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>FV_HOME</key>
    <string>{escape(str(home))}</string>
  </dict>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>{hh}</integer>
    <key>Minute</key>
    <integer>{mm}</integer>
  </dict>
  <key>StartInterval</key>
  <integer>{intervalo_horas * 3600}</integer>
  <key>ProcessType</key>
  <string>Background</string>
  <key>StandardOutPath</key>
  <string>{log}</string>
  <key>StandardErrorPath</key>
  <string>{log}</string>
</dict>
</plist>
"""


def linha_cron(home: Path, hora: str, *, intervalo_horas: int = 2) -> list[str]:
    """Plano B do Linux sem systemd de usuário (WSL, contêiner): a cada N horas no minuto pedido, e ao iniciar."""
    _, mm = hora.split(":", 1)
    comando = linha_comando(home)
    return [f"{int(mm)} */{intervalo_horas} * * * {comando} >/dev/null 2>&1 {MARCA_CRON}",
            f"@reboot {comando} >/dev/null 2>&1 {MARCA_CRON}"]


def _crontab_sem_marca() -> tuple[int, list[str]]:
    codigo, saida, _ = _rodar(["crontab", "-l"])
    linhas = saida.splitlines() if codigo == 0 else []  # sem crontab: `crontab -l` sai com erro
    return codigo, [linha for linha in linhas if MARCA_CRON not in linha]


def _gravar_crontab(linhas: list[str]) -> tuple[int, str, str]:
    conteudo = "\n".join(linhas) + ("\n" if linhas else "")
    return _rodar(["crontab", "-"], entrada=conteudo)


def _uid() -> int:
    import os

    return os.getuid()  # type: ignore[attr-defined]  # só macOS chama


def validar_hora(hora: str) -> str:
    if not re.fullmatch(r"\d{2}:\d{2}", hora or ""):
        raise ValueError("hora_invalida")
    hh, mm = map(int, hora.split(":"))
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError("hora_invalida")
    return hora


_executar_sistema: Callable[..., tuple[int, str, str]] | None = None


def definir_executar_sistema(fn: Callable[..., tuple[int, str, str]] | None) -> None:
    """Executor injetável nos testes: recebe o comando e, para `crontab -`, a entrada (`entrada=`)."""
    global _executar_sistema
    _executar_sistema = fn


def _rodar(cmd: list[str], entrada: str | None = None) -> tuple[int, str, str]:
    if _executar_sistema is not None:
        return _executar_sistema(cmd) if entrada is None else _executar_sistema(cmd, entrada=entrada)
    import subprocess

    try:
        r = subprocess.run(cmd, input=entrada, capture_output=True, text=True, encoding="utf-8",  # noqa: S603
                           errors="replace", check=False)
    except FileNotFoundError as exc:  # systemctl/crontab/launchctl ausente
        return 127, "", str(exc)
    return r.returncode, r.stdout, r.stderr


def agendar_instalar(home: Path, hora: str = HORA_PADRAO, *, intervalo_horas: int = 2) -> dict:
    hora = validar_hora(hora)
    intervalo_horas = max(1, int(intervalo_horas))
    if sys.platform == "win32":
        arquivo = Path(home) / "agendamento-manter.xml"
        arquivo.write_text(xml_tarefa(home, hora, intervalo_horas=intervalo_horas), encoding="utf-16")
        cmd = comando_schtasks(home, hora, arquivo)
        codigo, saida, erro = _rodar(cmd)
        return {"status": "ok" if codigo == 0 else "erro", "plataforma": "windows", "comando": cmd,
                "acao": linha_comando(home), "codigo": codigo, "saida": saida, "erro": erro, "hora": hora,
                "executa_ao_voltar": True}
    if sys.platform.startswith("linux"):
        base = Path.home() / ".config" / "systemd" / "user"
        base.mkdir(parents=True, exist_ok=True)
        (base / f"{UNIDADE_LINUX}.service").write_text(conteudo_systemd_service(home), encoding="utf-8")
        (base / f"{UNIDADE_LINUX}.timer").write_text(
            conteudo_systemd_timer(hora, intervalo_horas=intervalo_horas), encoding="utf-8"
        )
        codigo, saida, erro = _rodar(["systemctl", "--user", "daemon-reload"])
        if codigo == 0:
            codigo, saida, erro = _rodar(["systemctl", "--user", "enable", "--now", f"{UNIDADE_LINUX}.timer"])
        if codigo == 0:
            return {"status": "ok", "plataforma": "linux", "mecanismo": "systemd", "hora": hora,
                    "unidade": UNIDADE_LINUX, "codigo": codigo, "saida": saida, "erro": erro}
        # Sem systemd de usuário (WSL, contêiner, sessão sem lingering): crontab do usuário (0092).
        erro_systemd = erro
        _, linhas = _crontab_sem_marca()
        codigo, saida, erro = _gravar_crontab(linhas + linha_cron(home, hora, intervalo_horas=intervalo_horas))
        return {"status": "ok" if codigo == 0 else "erro", "plataforma": "linux", "mecanismo": "cron", "hora": hora,
                "erro_systemd": erro_systemd, "codigo": codigo, "saida": saida, "erro": erro}
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "LaunchAgents"
        base.mkdir(parents=True, exist_ok=True)
        plist = base / f"{ROTULO_MAC}.plist"
        plist.write_text(conteudo_launchd(home, hora, intervalo_horas=intervalo_horas), encoding="utf-8")
        dominio = f"gui/{_uid()}"
        _rodar(["launchctl", "bootout", f"{dominio}/{ROTULO_MAC}"])  # reinstalação: ausente não é erro
        codigo, saida, erro = _rodar(["launchctl", "bootstrap", dominio, str(plist)])
        return {"status": "ok" if codigo == 0 else "erro", "plataforma": "macos", "mecanismo": "launchd",
                "hora": hora, "rotulo": ROTULO_MAC, "plist": str(plist), "codigo": codigo, "saida": saida,
                "erro": erro, "executa_ao_voltar": True}
    return {
        "status": "nao_suportado",
        "plataforma": sys.platform,
        "instrucoes": (
            "Instale manualmente uma tarefa diária que execute "
            f"`{linha_comando(home)}` às {hora}."
        ),
    }


def agendar_remover() -> dict:
    if sys.platform == "win32":
        codigo, saida, erro = _rodar(["schtasks", "/Delete", "/TN", TAREFA_WIN, "/F"])
        return {"status": "ok" if codigo == 0 else "erro", "plataforma": "windows", "codigo": codigo, "saida": saida,
                "erro": erro}
    if sys.platform.startswith("linux"):
        codigo, saida, erro = _rodar(["systemctl", "--user", "disable", "--now", f"{UNIDADE_LINUX}.timer"])
        cod_cron, linhas = _crontab_sem_marca()
        if cod_cron == 0:
            _gravar_crontab(linhas)
        return {"status": "ok" if codigo == 0 or cod_cron == 0 else "erro", "plataforma": "linux", "codigo": codigo,
                "saida": saida, "erro": erro}
    if sys.platform == "darwin":
        codigo, saida, erro = _rodar(["launchctl", "bootout", f"gui/{_uid()}/{ROTULO_MAC}"])
        plist = Path.home() / "Library" / "LaunchAgents" / f"{ROTULO_MAC}.plist"
        if plist.exists():
            plist.unlink()
        return {"status": "ok" if codigo == 0 else "erro", "plataforma": "macos", "codigo": codigo, "saida": saida,
                "erro": erro}
    return {"status": "nao_suportado", "plataforma": sys.platform}


def agendar_mostrar() -> dict:
    if sys.platform == "win32":
        codigo, saida, erro = _rodar(["schtasks", "/Query", "/TN", TAREFA_WIN, "/FO", "LIST", "/V"])
        return {"status": "ok" if codigo == 0 else "ausente", "plataforma": "windows", "detalhe": saida or erro}
    if sys.platform.startswith("linux"):
        codigo, saida, erro = _rodar(["systemctl", "--user", "status", f"{UNIDADE_LINUX}.timer"])
        if codigo == 0:
            return {"status": "ok", "plataforma": "linux", "mecanismo": "systemd", "detalhe": saida}
        cod_cron, saida_cron, _ = _rodar(["crontab", "-l"])
        linhas = [linha for linha in saida_cron.splitlines() if MARCA_CRON in linha] if cod_cron == 0 else []
        if linhas:
            return {"status": "ok", "plataforma": "linux", "mecanismo": "cron", "detalhe": "\n".join(linhas)}
        return {"status": "ausente", "plataforma": "linux", "detalhe": saida or erro}
    if sys.platform == "darwin":
        codigo, saida, erro = _rodar(["launchctl", "print", f"gui/{_uid()}/{ROTULO_MAC}"])
        return {"status": "ok" if codigo == 0 else "ausente", "plataforma": "macos", "mecanismo": "launchd",
                "detalhe": saida or erro}
    return {"status": "nao_suportado", "plataforma": sys.platform}