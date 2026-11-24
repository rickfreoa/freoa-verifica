"""Agendamento local de `fv acervo manter` (0091 emenda A), sem privilégio de administrador."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Callable

TAREFA_WIN = "FREOA Verifica - manter acervo"
HORA_PADRAO = "05:43"
UNIDADE_LINUX = "fv-manter"


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


def xml_tarefa(home: Path | None, hora: str) -> str:
    from xml.sax.saxutils import escape

    args = " ".join(f'"{a}"' if " " in a else a for a in argumentos(home))
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>FREOA Verifica: revalida metadados e renova o acervo (decisão 0091)</Description></RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-01-01T{hora}:00</StartBoundary>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
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


def conteudo_systemd_timer(hora: str) -> str:
    hh, mm = hora.split(":", 1)
    return f"""[Unit]
Description=FREOA Verifica - manutenção diária do acervo

[Timer]
OnCalendar=*-*-* {hh}:{mm}:00
Persistent=true

[Install]
WantedBy=timers.target
"""


def validar_hora(hora: str) -> str:
    if not re.fullmatch(r"\d{2}:\d{2}", hora or ""):
        raise ValueError("hora_invalida")
    hh, mm = map(int, hora.split(":"))
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError("hora_invalida")
    return hora


_executar_sistema: Callable[[list[str]], tuple[int, str, str]] | None = None


def definir_executar_sistema(fn: Callable[[list[str]], tuple[int, str, str]] | None) -> None:
    global _executar_sistema
    _executar_sistema = fn


def _rodar(cmd: list[str]) -> tuple[int, str, str]:
    if _executar_sistema is not None:
        return _executar_sistema(cmd)
    import subprocess

    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)  # noqa: S603
    return r.returncode, r.stdout, r.stderr


def agendar_instalar(home: Path, hora: str = HORA_PADRAO) -> dict:
    hora = validar_hora(hora)
    if sys.platform == "win32":
        arquivo = Path(home) / "agendamento-manter.xml"
        arquivo.write_text(xml_tarefa(home, hora), encoding="utf-16")
        cmd = comando_schtasks(home, hora, arquivo)
        codigo, saida, erro = _rodar(cmd)
        return {"status": "ok" if codigo == 0 else "erro", "plataforma": "windows", "comando": cmd,
                "acao": linha_comando(home), "codigo": codigo, "saida": saida, "erro": erro, "hora": hora,
                "executa_ao_voltar": True}
    if sys.platform.startswith("linux"):
        base = Path.home() / ".config" / "systemd" / "user"
        base.mkdir(parents=True, exist_ok=True)
        (base / f"{UNIDADE_LINUX}.service").write_text(conteudo_systemd_service(home), encoding="utf-8")
        (base / f"{UNIDADE_LINUX}.timer").write_text(conteudo_systemd_timer(hora), encoding="utf-8")
        codigo, saida, erro = _rodar(["systemctl", "--user", "daemon-reload"])
        if codigo == 0:
            codigo, saida, erro = _rodar(["systemctl", "--user", "enable", "--now", f"{UNIDADE_LINUX}.timer"])
        return {"status": "ok" if codigo == 0 else "erro", "plataforma": "linux", "hora": hora,
                "unidade": UNIDADE_LINUX, "codigo": codigo, "saida": saida, "erro": erro}
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
        return {"status": "ok" if codigo == 0 else "erro", "plataforma": "linux", "codigo": codigo, "saida": saida,
                "erro": erro}
    return {"status": "nao_suportado", "plataforma": sys.platform}


def agendar_mostrar() -> dict:
    if sys.platform == "win32":
        codigo, saida, erro = _rodar(["schtasks", "/Query", "/TN", TAREFA_WIN, "/FO", "LIST", "/V"])
        return {"status": "ok" if codigo == 0 else "ausente", "plataforma": "windows", "detalhe": saida or erro}
    if sys.platform.startswith("linux"):
        codigo, saida, erro = _rodar(["systemctl", "--user", "status", f"{UNIDADE_LINUX}.timer"])
        return {"status": "ok" if codigo == 0 else "ausente", "plataforma": "linux", "detalhe": saida or erro}
    return {"status": "nao_suportado", "plataforma": sys.platform}