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


def _validar_home(home: Path) -> None:
    if any(c in str(home) for c in "\r\n\0"):
        raise ValueError("home_com_quebra_de_linha")


def _systemd_escapar(valor: str) -> str:
    """Argumento de ExecStart entre aspas: especificadores (%), variáveis ($), aspas e barras escapados."""
    v = valor.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$")
    return f'"{v}"'


def linha_systemd(home: Path) -> str:
    return " ".join(_systemd_escapar(a) for a in [str(caminho_fv()), *argumentos(home)])


def linha_shell(home: Path) -> str:
    """Comando para shell POSIX (cron): cada argumento entre aspas simples, sem expansão possível."""
    import shlex

    return " ".join(shlex.quote(a) for a in [str(caminho_fv()), *argumentos(home)])


def conteudo_systemd_service(home: Path) -> str:
    _validar_home(home)
    return f"""[Unit]
Description=FREOA Verifica - manutenção do acervo

[Service]
Type=oneshot
Environment={_systemd_escapar("FV_HOME=" + str(home))}
ExecStart={linha_systemd(home)}
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
    _validar_home(home)
    _, mm = hora.split(":", 1)
    comando = linha_shell(home).replace("%", "\\%")  # no crontab, % não escapado vira quebra de linha
    return [f"{int(mm)} */{intervalo_horas} * * * {comando} >/dev/null 2>&1 {MARCA_CRON}",
            f"@reboot {comando} >/dev/null 2>&1 {MARCA_CRON}"]


def _crontab_sem_marca() -> tuple[int, list[str]]:
    """Linhas atuais do crontab do usuário, sem as nossas. Código diferente de 0: não foi possível ler e nada deve ser
    gravado, salvo ausência comprovada de crontab ("no crontab for <usuário>"), que é tabela vazia."""
    codigo, saida, erro = _rodar(["crontab", "-l"])
    if codigo != 0:
        return (0, []) if "no crontab" in (erro + saida).lower() else (codigo or 1, [])
    return 0, [linha for linha in saida.splitlines() if MARCA_CRON not in linha]


def caminho_inseguro(caminho: Path) -> str | None:
    """Motivo pelo qual um terceiro poderia trocar `caminho` (ou um diretório acima dele), ou None.

    POSIX: cada componente existente precisa ser do usuário ou do root e não pode ser gravável por grupo ou outros,
    salvo diretório com sticky bit (como /tmp), em que terceiros não renomeiam nem apagam o que é nosso (0092)."""
    import os
    import stat

    if sys.platform == "win32" or not hasattr(os, "geteuid"):
        return None  # Windows: perfil do usuário protegido pela ACL herdada

    uid = os.geteuid()
    atual = Path(caminho)
    for parte in [atual, *atual.parents]:
        try:
            st = parte.lstat()
        except FileNotFoundError:
            continue
        if st.st_uid not in (uid, 0):
            return f"{parte}: de outro usuário"
        gravavel = st.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        if gravavel and not (stat.S_ISDIR(st.st_mode) and st.st_mode & stat.S_ISVTX):
            return f"{parte}: gravável por grupo ou outros"
    return None


def _gravar_privado(caminho: Path, conteudo: str, encoding: str = "utf-8") -> None:
    """Arquivo que define o comando agendado: substitui link simbólico em vez de segui-lo e fica sem escrita de
    grupo ou outros (0092)."""
    caminho.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if sys.platform != "win32" and caminho.parent.lstat().st_mode & 0o022:
        caminho.parent.chmod(caminho.parent.lstat().st_mode & ~0o022)  # diretório nosso, existente e aberto
    if (motivo := caminho_inseguro(caminho.parent)) is not None:
        raise PermissionError(f"diretório do agendamento substituível por terceiros ({motivo})")
    if caminho.is_symlink():
        caminho.unlink()
    caminho.write_text(conteudo, encoding=encoding)
    if sys.platform != "win32":
        caminho.chmod(0o600)


def _recusa_root() -> dict | None:
    import os

    if sys.platform != "win32" and hasattr(os, "geteuid") and os.geteuid() == 0:
        return {"status": "erro", "plataforma": sys.platform, "erro": "execute como usuário comum, não como root"}
    return None


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
    _validar_home(Path(home))
    if (recusa := _recusa_root()) is not None:
        return recusa
    if (motivo := caminho_inseguro(caminho_fv())) is not None:
        return {"status": "erro", "plataforma": sys.platform,
                "erro": f"executável agendado substituível por terceiros ({motivo}); corrija as permissões"}
    try:
        return _agendar_instalar(home, hora, intervalo_horas)
    except PermissionError as exc:
        return {"status": "erro", "plataforma": sys.platform, "erro": str(exc)}


def _agendar_instalar(home: Path, hora: str, intervalo_horas: int) -> dict:
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
        _gravar_privado(base / f"{UNIDADE_LINUX}.service", conteudo_systemd_service(home))
        _gravar_privado(base / f"{UNIDADE_LINUX}.timer", conteudo_systemd_timer(hora, intervalo_horas=intervalo_horas))
        codigo, saida, erro = _rodar(["systemctl", "--user", "daemon-reload"])
        if codigo == 0:
            codigo, saida, erro = _rodar(["systemctl", "--user", "enable", "--now", f"{UNIDADE_LINUX}.timer"])
        if codigo == 0:
            return {"status": "ok", "plataforma": "linux", "mecanismo": "systemd", "hora": hora,
                    "unidade": UNIDADE_LINUX, "codigo": codigo, "saida": saida, "erro": erro}
        # Sem systemd de usuário (WSL, contêiner, sessão sem lingering): crontab do usuário (0092).
        erro_systemd = erro
        cod_leitura, linhas = _crontab_sem_marca()
        if cod_leitura != 0:
            return {"status": "erro", "plataforma": "linux", "mecanismo": "cron", "erro_systemd": erro_systemd,
                    "erro": "crontab ilegível: nada foi gravado para não apagar as linhas existentes"}
        codigo, saida, erro = _gravar_crontab(linhas + linha_cron(home, hora, intervalo_horas=intervalo_horas))
        return {"status": "ok" if codigo == 0 else "erro", "plataforma": "linux", "mecanismo": "cron", "hora": hora,
                "erro_systemd": erro_systemd, "codigo": codigo, "saida": saida, "erro": erro}
    if sys.platform == "darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / f"{ROTULO_MAC}.plist"
        _gravar_privado(plist, conteudo_launchd(home, hora, intervalo_horas=intervalo_horas))
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
        # Cada mecanismo presente precisa ser removido; leitura inconclusiva não comprova ausência (0092).
        base = Path.home() / ".config" / "systemd" / "user"
        unidades = [base / f"{UNIDADE_LINUX}.service", base / f"{UNIDADE_LINUX}.timer"]
        tinha_systemd = any(u.exists() or u.is_symlink() for u in unidades)
        codigo, saida, erro = 0, "", ""
        if tinha_systemd:
            codigo, saida, erro = _rodar(["systemctl", "--user", "disable", "--now", f"{UNIDADE_LINUX}.timer"])
            if codigo == 0:
                for u in unidades:
                    if u.exists() or u.is_symlink():
                        u.unlink()
        cod_cron, saida_cron, erro_cron = _rodar(["crontab", "-l"])
        sem_crontab = cod_cron != 0 and "no crontab" in (erro_cron + saida_cron).lower()
        leitura_ok = cod_cron == 0 or sem_crontab
        tinha_cron = cod_cron == 0 and MARCA_CRON in saida_cron
        cod_grav = 0
        if tinha_cron:
            cod_leitura, linhas = _crontab_sem_marca()
            cod_grav = cod_leitura or _gravar_crontab(linhas)[0]
        ok = codigo == 0 and leitura_ok and cod_grav == 0
        return {"status": "ok" if ok else "erro", "plataforma": "linux", "systemd": tinha_systemd,
                "cron": tinha_cron, "crontab_legivel": leitura_ok, "codigo": codigo, "codigo_cron": cod_grav,
                "saida": saida, "erro": erro or ("" if leitura_ok else erro_cron)}
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
        # systemctl status: 3 e 4 = unidade inativa ou inexistente; outro código = consulta indisponível.
        systemd_conclusivo = codigo in (3, 4)
        cod_cron, saida_cron, erro_cron = _rodar(["crontab", "-l"])
        linhas = [linha for linha in saida_cron.splitlines() if MARCA_CRON in linha] if cod_cron == 0 else []
        if linhas:
            return {"status": "ok", "plataforma": "linux", "mecanismo": "cron", "detalhe": "\n".join(linhas)}
        cron_conclusivo = cod_cron == 0 or "no crontab" in (erro_cron + saida_cron).lower()
        if systemd_conclusivo and cron_conclusivo:
            return {"status": "ausente", "plataforma": "linux", "detalhe": saida or erro}
        return {"status": "indisponivel", "plataforma": "linux", "detalhe": "\n".join(x for x in (erro, erro_cron) if x)}
    if sys.platform == "darwin":
        codigo, saida, erro = _rodar(["launchctl", "print", f"gui/{_uid()}/{ROTULO_MAC}"])
        # launchctl print: 113 = serviço não encontrado; outro código diferente de 0 = consulta indisponível.
        status = "ok" if codigo == 0 else ("ausente" if codigo == 113 or "could not find service" in erro.lower()
                                           else "indisponivel")
        return {"status": status, "plataforma": "macos", "mecanismo": "launchd", "detalhe": saida or erro}
    return {"status": "nao_suportado", "plataforma": sys.platform}