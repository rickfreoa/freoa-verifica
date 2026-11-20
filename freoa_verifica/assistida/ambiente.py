"""Conferências Windows; nunca consulta o perfil pessoal do navegador."""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import threading
import time
from ctypes import wintypes as w
from pathlib import Path
from uuid import uuid4


class RecusaSessao(RuntimeError):
    """Só códigos fechados; exceções do sistema não transportam dados de navegação."""


class InventarioPendente(RecusaSessao):
    """Preferências ainda não gravadas; só o assentamento pode aguardar."""


# Brave 1.100: gravação ausente nos primeiros 10 s e presente até 30 s.
PRAZO_INVENTARIO_INICIAL_S = 60

# Inclui o principal e os filhos ainda visíveis após TerminateJobObject.
PRAZO_SAIDA_NAVEGADOR_S = 15
TENTATIVAS_LIMPEZA = 20
INTERVALO_LIMPEZA_S = 0.1


POLITICAS = {
    "chrome": r"Software\Policies\Google\Chrome",
    "edge": r"Software\Policies\Microsoft\Edge",
    "brave": r"Software\Policies\BraveSoftware\Brave",
}
PERMISSOES = frozenset(
    {
        "webRequest",
        "webRequestBlocking",
        "webRequestAuthProvider",
        "declarativeNetRequest",
        "declarativeNetRequestWithHostAccess",
        "proxy",
        "debugger",
    }
)


def conferir_politicas(nome, *, registro=None):
    if registro is None:
        import winreg as registro
    try:
        for hive in (registro.HKEY_CURRENT_USER, registro.HKEY_LOCAL_MACHINE):
            for vista in (registro.KEY_WOW64_64KEY, registro.KEY_WOW64_32KEY):
                try:
                    key = registro.OpenKey(
                        hive, POLITICAS[nome], 0, registro.KEY_READ | vista
                    )
                except FileNotFoundError:
                    continue
                with key:
                    nval = registro.QueryInfoKey(key)[1]
                    valores = {
                        registro.EnumValue(key, i)[0]: registro.EnumValue(key, i)[1]
                        for i in range(nval)
                    }
                    if any(
                        x in valores
                        for x in (
                            "ProxySettings",
                            "ProxyMode",
                            "ProxyServer",
                            "ProxyPacUrl",
                            "CloudManagementEnrollmentToken",
                        )
                    ):
                        raise RecusaSessao("POLITICA_ASSISTIDA_RECUSADA")
                    if "ExtensionSettings" in valores:
                        settings = json.loads(valores["ExtensionSettings"])
                        if not isinstance(settings, dict) or any(
                            not isinstance(v, dict)
                            or v.get("installation_mode")
                            in {"force_installed", "normal_installed"}
                            for v in settings.values()
                        ):
                            raise RecusaSessao("POLITICA_ASSISTIDA_RECUSADA")
                    try:
                        with registro.OpenKey(
                            key, "ExtensionInstallForcelist"
                        ) as forced:
                            if any(registro.QueryInfoKey(forced)[:2]):
                                raise RecusaSessao("POLITICA_ASSISTIDA_RECUSADA")
                    except FileNotFoundError:
                        pass
    except RecusaSessao:
        raise
    except (OSError, ValueError, TypeError, KeyError):
        raise RecusaSessao("REGISTRO_ASSISTIDO_INDISPONIVEL") from None


def inventariar(perfil: Path, navegador: Path):
    try:
        pendente = False
        for arquivo in ("Secure Preferences", "Preferences"):
            try:
                bruto = (perfil / "Default" / arquivo).read_text(encoding="utf-8")
            except FileNotFoundError:
                pendente = True
                continue
            data = json.loads(bruto)
            settings = data.get("extensions", {}).get("settings", {})
            if not isinstance(settings, dict):
                raise ValueError
            for item in settings.values():
                location = item["location"]
                if location == 4:
                    raise RecusaSessao("EXTENSAO_DESEMPACOTADA")
                caminho = Path(item["path"])
                componente_absoluto = location == 5 and caminho.is_absolute()
                if not caminho.is_absolute():
                    caminho = perfil / "Default" / "Extensions" / caminho
                caminho = caminho.resolve()
                componente_interno = componente_absoluto and caminho.is_relative_to(
                    navegador.parent.resolve()
                )
                try:
                    manifesto = json.loads(
                        (caminho / "manifest.json").read_text(encoding="utf-8")
                    )
                except FileNotFoundError:
                    # Leitura de execução da 0089: componentes embutidos podem
                    # não materializar nem o diretório de recursos em disco.
                    if not componente_interno:
                        raise
                    manifesto = item.get("manifest")
                if not isinstance(manifesto, dict):
                    raise ValueError
                if componente_interno:
                    continue
                permissoes = set(manifesto.get("permissions", [])) | set(
                    manifesto.get("optional_permissions", [])
                )
                if permissoes & PERMISSOES or "declarative_net_request" in manifesto:
                    raise RecusaSessao("EXTENSAO_INTERCEPTADORA")
        if pendente:
            raise InventarioPendente("INVENTARIO_ASSISTIDO_INDISPONIVEL")
    except RecusaSessao:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise RecusaSessao("INVENTARIO_ASSISTIDO_INDISPONIVEL") from None


def navegador_instalado(nome=None):
    bases = [
        os.environ.get(k, "")
        for k in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)")
    ]
    relativos = {
        "brave": "BraveSoftware/Brave-Browser/Application/brave.exe",
        "chrome": "Google/Chrome/Application/chrome.exe",
        "edge": "Microsoft/Edge/Application/msedge.exe",
    }
    for n in [nome] if nome else ["brave", "chrome", "edge"]:
        for base in bases:
            path = Path(base) / relativos[n]
            if base and path.is_file():
                return n, path.resolve()
    raise RecusaSessao("NAVEGADOR_INSTALADO_AUSENTE")


def _dlls():
    if os.name != "nt":
        raise RecusaSessao("SESSAO_ASSISTIDA_EXIGE_WINDOWS")
    return ctypes.WinDLL("kernel32", use_last_error=True), ctypes.WinDLL(
        "advapi32", use_last_error=True
    )


def proteger_diretorio(path):
    """DACL protegida: titular, SYSTEM e Administradores; confere o descritor aplicado."""
    kernel, adv = _dlls()
    kernel.GetCurrentProcess.restype = w.HANDLE
    adv.OpenProcessToken.argtypes = (w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE))
    token = w.HANDLE()
    if not adv.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
        raise RecusaSessao(
            f"ACL_ASSISTIDA_OpenProcessToken_WINERROR_{ctypes.get_last_error()}"
        )
    try:
        size = w.DWORD()
        adv.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        buf = ctypes.create_string_buffer(size.value)
        if not adv.GetTokenInformation(token, 1, buf, size, ctypes.byref(size)):
            raise RecusaSessao(
                f"ACL_ASSISTIDA_GetTokenInformation_WINERROR_{ctypes.get_last_error()}"
            )
        sid = ctypes.c_void_p.from_buffer(buf).value
        sid_text = w.LPWSTR()
        adv.ConvertSidToStringSidW.argtypes = (
            ctypes.c_void_p,
            ctypes.POINTER(w.LPWSTR),
        )
        if not adv.ConvertSidToStringSidW(sid, ctypes.byref(sid_text)):
            raise RecusaSessao(
                f"ACL_ASSISTIDA_ConvertSidToStringSidW_WINERROR_{ctypes.get_last_error()}"
            )
        try:
            sddl = f"D:P(A;OICI;FA;;;{sid_text.value})(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"
        finally:
            kernel.LocalFree(sid_text)
        sd = ctypes.c_void_p()
        adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = (
            w.LPCWSTR,
            w.DWORD,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_void_p,
        )
        if not adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, 1, ctypes.byref(sd), None
        ):
            raise RecusaSessao(
                f"ACL_ASSISTIDA_ConvertStringSecurityDescriptor_WINERROR_{ctypes.get_last_error()}"
            )
        try:
            adv.SetFileSecurityW.argtypes = (w.LPCWSTR, w.DWORD, ctypes.c_void_p)
            if not adv.SetFileSecurityW(str(path), 0x80000004, sd):
                raise RecusaSessao(
                    f"ACL_ASSISTIDA_SetFileSecurityW_WINERROR_{ctypes.get_last_error()}"
                )
            needed = w.DWORD()
            adv.GetFileSecurityW(str(path), 4, None, 0, ctypes.byref(needed))
            read = ctypes.create_string_buffer(needed.value)
            if not adv.GetFileSecurityW(
                str(path), 4, read, needed, ctypes.byref(needed)
            ):
                raise RecusaSessao(
                    f"ACL_ASSISTIDA_GetFileSecurityW_WINERROR_{ctypes.get_last_error()}"
                )
            rendered = w.LPWSTR()
            adv.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = (
                ctypes.c_void_p,
                w.DWORD,
                w.DWORD,
                ctypes.POINTER(w.LPWSTR),
                ctypes.c_void_p,
            )
            if not adv.ConvertSecurityDescriptorToStringSecurityDescriptorW(
                read, 1, 4, ctypes.byref(rendered), None
            ):
                raise RecusaSessao(
                    f"ACL_ASSISTIDA_ConvertSecurityDescriptor_WINERROR_{ctypes.get_last_error()}"
                )
            try:
                if rendered.value != sddl:
                    raise RecusaSessao("ACL_ASSISTIDA_DIVERGENTE")
            finally:
                kernel.LocalFree(rendered)
        finally:
            kernel.LocalFree(sd)
    finally:
        kernel.CloseHandle(token)


def _perfil_confinado(path, raiz):
    original = Path(path)
    if original.is_symlink() or (
        hasattr(original, "is_junction") and original.is_junction()
    ):
        raise RecusaSessao("LIMPEZA_ASSISTIDA_FORA_DO_STAGING")
    path, raiz = original.resolve(), Path(raiz).resolve()
    if (
        path.parent != raiz
        or not path.name.startswith("sessao-0089-")
        or path.is_symlink()
    ):
        raise RecusaSessao("LIMPEZA_ASSISTIDA_FORA_DO_STAGING")
    return path


def _marcar_limpeza_pendente(path, motivo):
    try:
        _perfil_confinado(path, path.parent)
        # Não seguir link nem sobrescrever um arquivo já existente na sessão.
        with (path / ".limpeza-pendente").open("x", encoding="utf-8") as marca:
            marca.write(motivo + "\n")
    except (OSError, RecusaSessao):
        # O próprio nome sessao-0089-* também é a marca de recuperação (§3.7).
        pass
    print(f"LIMPEZA_ASSISTIDA_PENDENTE: {path} | {motivo}")


def limpar_diretorio(path, raiz):
    path = _perfil_confinado(path, raiz)
    if not path.exists():
        return
    try:
        aguardar_saida_navegador(path)
        for tentativa in range(TENTATIVAS_LIMPEZA):
            try:
                shutil.rmtree(path)
                return
            except FileNotFoundError:
                if not path.exists():
                    return
                raise
            except OSError:
                if tentativa == TENTATIVAS_LIMPEZA - 1:
                    raise
                time.sleep(INTERVALO_LIMPEZA_S)
    except (OSError, RecusaSessao) as exc:
        motivo = str(exc) if isinstance(exc, RecusaSessao) else type(exc).__name__
        _marcar_limpeza_pendente(path, motivo)
        raise RecusaSessao("LIMPEZA_ASSISTIDA_PENDENTE") from None


def preparar_diretorio(home):
    raiz = Path(home).resolve() / "staging" / "sessoes-assistidas"
    raiz.mkdir(parents=True, exist_ok=True)
    proteger_diretorio(raiz)
    for sobra in raiz.iterdir():
        if sobra.name.startswith("sessao-0089-"):
            # O chamador mantém o lock exclusivo da raiz durante todo o ciclo.
            limpar_diretorio(sobra, raiz)
    path = raiz / ("sessao-0089-" + uuid4().hex)
    path.mkdir()
    proteger_diretorio(path)
    (path / "Default" / "Extensions").mkdir(parents=True)
    return path


class lock_sessao:
    def __init__(self, path):
        self.path = Path(path)
        self.fd = None

    def __enter__(self):
        import msvcrt

        self.fd = open(self.path / ".lock", "a+b")
        try:
            self.fd.write(b"0")
            self.fd.flush()
            self.fd.seek(0)
            msvcrt.locking(self.fd.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self.fd.close()
            raise RecusaSessao("SESSAO_ASSISTIDA_CONCORRENTE") from None
        return self

    def __exit__(self, *args):
        self.fd.close()


class Vigilancia:
    """Estado determinista separado de ReadDirectoryChangesW para provas offline."""

    def __init__(
        self, perfil, navegador, *, relogio=time.monotonic, inventario=inventariar
    ):
        self.perfil, self.navegador = Path(perfil), Path(navegador)
        self.relogio, self.inventario = relogio, inventario
        self.ultima = relogio()
        self.limite_inventario = self.ultima + PRAZO_INVENTARIO_INICIAL_S
        self.inventario_lido = False
        self.linha_base = None
        self.caminhos = None
        self.erro = None
        self.sentinelas = {}
        self.cond = threading.Condition(threading.RLock())
        self.ao_invalidar = lambda: None

    def notificar(self, caminho, acao=3):
        with self.cond:
            caminho = caminho.replace("/", "\\").lower()
            if caminho in self.sentinelas and acao in {1, 3}:
                self.sentinelas[caminho] = True
                self.cond.notify_all()
                return
            if caminho == "default\\extensions" or caminho.startswith(
                "default\\extensions\\"
            ):
                self.ultima = self.relogio()
                if self.linha_base is not None:
                    self.falhar("EXTENSOES_ALTERADAS")

    def falhar(self, codigo="VIGILANCIA_ASSISTIDA_INDISPONIVEL"):
        with self.cond:
            self.erro = codigo
            self.ao_invalidar()
            self.cond.notify_all()

    def conferir(self):
        if self.erro:
            raise RecusaSessao(self.erro)

    def assentar(self):
        with self.cond:
            self.conferir()
            if self.linha_base is None:
                pendente = False
                try:
                    self.inventario(self.perfil, self.navegador)
                except InventarioPendente:
                    pendente = True
                except RecusaSessao as exc:
                    self.falhar(str(exc))
                    raise
                if (
                    pendente or not self.inventario_lido
                ) and self.relogio() >= self.limite_inventario:
                    self.falhar("INVENTARIO_ASSISTIDO_INDISPONIVEL")
                    self.conferir()
                if pendente:
                    return None
                self.inventario_lido = True
                if self.relogio() - self.ultima < 10:
                    return None
                self.caminhos = tuple(
                    sorted(
                        (str(p.relative_to(self.perfil)), p.stat().st_size)
                        for p in (self.perfil / "Default" / "Extensions").rglob("*")
                        if p.is_file()
                    )
                )
                self.linha_base = self.relogio()
            return self.linha_base

    def barreira(self):
        with self.cond:
            self.conferir()
            if self.linha_base is None:
                raise RecusaSessao("AMBIENTE_NAO_ASSENTADO")
            nome = "default\\extensions\\.sentinela-" + uuid4().hex
            self.sentinelas[nome] = False
            (self.perfil / "Default" / "Extensions" / nome.split("\\")[-1]).write_bytes(
                b""
            )
            limite = time.monotonic() + 5
            while not self.sentinelas[nome] and not self.erro:
                restante = limite - time.monotonic()
                if restante <= 0:
                    self.falhar("BARREIRA_ASSISTIDA_EXPIRADA")
                    break
                self.cond.wait(restante)
            self.conferir()
            self.inventario(self.perfil, self.navegador)


class ObservadorWindows:
    def __init__(self, vigia):
        self.vigia = vigia
        self.parado = False
        kernel, _ = _dlls()
        self.kernel = kernel
        kernel.CreateFileW.argtypes = (
            w.LPCWSTR,
            w.DWORD,
            w.DWORD,
            ctypes.c_void_p,
            w.DWORD,
            w.DWORD,
            w.HANDLE,
        )
        kernel.CreateFileW.restype = w.HANDLE
        self.handle = kernel.CreateFileW(
            str(vigia.perfil), 1, 7, None, 3, 0x42000000, None
        )
        if self.handle == w.HANDLE(-1).value:
            raise RecusaSessao("VIGILANCIA_ASSISTIDA_INDISPONIVEL")

        class Overlapped(ctypes.Structure):
            _fields_ = [
                ("Internal", ctypes.c_size_t),
                ("InternalHigh", ctypes.c_size_t),
                ("Offset", w.DWORD),
                ("OffsetHigh", w.DWORD),
                ("hEvent", w.HANDLE),
            ]

        self.overlapped = Overlapped()
        self.buf = ctypes.create_string_buffer(64 * 1024)
        kernel.CreateEventW.restype = w.HANDLE
        self.overlapped.hEvent = kernel.CreateEventW(None, True, False, None)
        if not self.overlapped.hEvent:
            kernel.CloseHandle(self.handle)
            raise RecusaSessao("VIGILANCIA_ASSISTIDA_INDISPONIVEL")
        kernel.ReadDirectoryChangesW.argtypes = (
            w.HANDLE,
            ctypes.c_void_p,
            w.DWORD,
            w.BOOL,
            w.DWORD,
            ctypes.POINTER(w.DWORD),
            ctypes.c_void_p,
            ctypes.c_void_p,
        )
        kernel.GetOverlappedResult.argtypes = (
            w.HANDLE,
            ctypes.c_void_p,
            ctypes.POINTER(w.DWORD),
            w.BOOL,
        )
        # A inscrição inicial ocorre sincronicamente ANTES do lançamento do navegador.
        self._armar()
        self.thread = threading.Thread(target=self._ler, daemon=True)
        self.thread.start()

    def _armar(self):
        self.kernel.ResetEvent.argtypes = (w.HANDLE,)
        self.kernel.ResetEvent(self.overlapped.hEvent)
        if not self.kernel.ReadDirectoryChangesW(
            self.handle,
            self.buf,
            len(self.buf),
            True,
            0x11F,
            None,
            ctypes.byref(self.overlapped),
            None,
        ):
            if ctypes.get_last_error() != 997:
                raise RecusaSessao("VIGILANCIA_ASSISTIDA_INDISPONIVEL")

    def _ler(self):
        import struct

        buf = self.buf
        while not self.parado:
            n = w.DWORD()
            ok = self.kernel.GetOverlappedResult(
                self.handle, ctypes.byref(self.overlapped), ctypes.byref(n), True
            )
            if self.parado:
                return
            if not ok or not n.value:
                self.vigia.falhar()
                return
            pos = 0
            try:
                while True:
                    proximo, acao, tamanho = struct.unpack_from("III", buf, pos)
                    if pos + 12 + tamanho > n.value:
                        raise ValueError
                    nome = bytes(buf[pos + 12 : pos + 12 + tamanho]).decode("utf-16-le")
                    self.vigia.notificar(nome, acao)
                    if not proximo:
                        break
                    pos += proximo
                self._armar()
            except (ValueError, UnicodeError, struct.error, RecusaSessao):
                self.vigia.falhar()
                return

    def fechar(self):
        self.parado = True
        self.kernel.CancelIoEx.argtypes = (w.HANDLE, ctypes.c_void_p)
        self.kernel.CancelIoEx(self.handle, None)
        self.kernel.CloseHandle.argtypes = (w.HANDLE,)
        self.kernel.CloseHandle(self.handle)
        self.thread.join(2)
        self.kernel.CloseHandle(self.overlapped.hEvent)


def argumentos(navegador, perfil, inicio, *, extras=()):
    if extras:
        raise RecusaSessao("ARGUMENTOS_ASSISTIDOS_RECUSADOS")
    return [
        str(navegador),
        f"--user-data-dir={perfil}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        "--no-proxy-server",
        "--disable-breakpad",
        "--remote-debugging-pipe",
        str(inicio),
    ]


def lancar_pipe(navegador, perfil, inicio, *, extras=()):
    """Só dois handles herdados; stdout/stderr não são registros de navegação."""
    args = argumentos(navegador, perfil, inicio, extras=extras)
    _dlls()
    import msvcrt

    leitura, filho_escrita = os.pipe()
    filho_leitura, escrita = os.pipe()
    proc = None
    job = None
    try:
        handles = [
            msvcrt.get_osfhandle(filho_leitura),
            msvcrt.get_osfhandle(filho_escrita),
        ]
        for h in handles:
            os.set_handle_inheritable(h, True)
        startup = subprocess.STARTUPINFO()
        startup.lpAttributeList = {"handle_list": handles}
        # Chromium no Windows recebe HANDLEs, não descritores POSIX 3/4.
        args.insert(-1, f"--remote-debugging-io-pipes={handles[0]},{handles[1]}")
        proc = subprocess.Popen(  # noqa: S603 -- executável instalado e argumentos fechados acima
            args,
            startupinfo=startup,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=0x4,  # CREATE_SUSPENDED: contém descendentes antes de qualquer execução
        )
        job = _conter_processo(proc)
        proc._fv_job = job
        return (
            proc,
            os.fdopen(leitura, "rb", buffering=0),
            os.fdopen(escrita, "wb", buffering=0),
        )
    except (OSError, RecusaSessao) as exc:
        if proc is not None:
            proc.kill()
            proc.wait(5)
        if job is not None:
            ctypes.windll.kernel32.CloseHandle(job)
        os.close(leitura)
        os.close(escrita)
        codigo = (
            f"PIPE_ASSISTIDO_INDISPONIVEL_WINERROR_{exc.winerror}"
            if isinstance(exc, OSError)
            else str(exc)
        )
        raise RecusaSessao(codigo) from None
    finally:
        os.close(filho_leitura)
        os.close(filho_escrita)


def _conter_processo(proc):
    kernel, _ = _dlls()

    class Basic(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", w.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", w.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", w.DWORD),
            ("SchedulingClass", w.DWORD),
        ]

    class IO(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_ulonglong)
            for name in (
                "ReadOperationCount",
                "WriteOperationCount",
                "OtherOperationCount",
                "ReadTransferCount",
                "WriteTransferCount",
                "OtherTransferCount",
            )
        ]

    class Extended(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", Basic),
            ("IoInfo", IO),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.SetInformationJobObject.argtypes = (
        w.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        w.DWORD,
    )
    kernel.AssignProcessToJobObject.argtypes = (w.HANDLE, w.HANDLE)
    kernel.CloseHandle.argtypes = (w.HANDLE,)
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise RecusaSessao("CONTENCAO_ASSISTIDA_INDISPONIVEL")
    try:
        limites = Extended()
        limites.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(
            job, 9, ctypes.byref(limites), ctypes.sizeof(limites)
        ) or not kernel.AssignProcessToJobObject(job, int(proc._handle)):
            raise RecusaSessao("CONTENCAO_ASSISTIDA_INDISPONIVEL")
        nt = ctypes.WinDLL("ntdll")
        nt.NtResumeProcess.argtypes = (w.HANDLE,)
        if nt.NtResumeProcess(int(proc._handle)) != 0:
            raise RecusaSessao("PIPE_ASSISTIDO_INDISPONIVEL")
        return job
    except BaseException:
        kernel.CloseHandle(job)
        raise


def _argumentos_processo(linha):
    """Lê argumentos Windows sem executar a linha nem consultar perfis."""
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    kernel, _ = _dlls()
    shell.CommandLineToArgvW.argtypes = (w.LPCWSTR, ctypes.POINTER(ctypes.c_int))
    shell.CommandLineToArgvW.restype = ctypes.POINTER(w.LPWSTR)
    kernel.LocalFree.argtypes = (ctypes.c_void_p,)
    argc = ctypes.c_int()
    argv = shell.CommandLineToArgvW(linha, ctypes.byref(argc))
    if not argv:
        raise RecusaSessao("ENUMERACAO_ASSISTIDA_INDISPONIVEL")
    try:
        return [argv[i] for i in range(argc.value)]
    finally:
        kernel.LocalFree(argv)


def _processos_do_perfil(perfil, prazo):
    """Enumeração local somente leitura; linhas de comando não são registradas."""
    if os.name != "nt":
        raise RecusaSessao("SESSAO_ASSISTIDA_EXIGE_WINDOWS")
    comando = (
        "$ErrorActionPreference='Stop'; "
        "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); "
        "Get-CimInstance Win32_Process | "
        "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    )
    try:
        resultado = subprocess.run(  # noqa: S603 -- PowerShell local, comando fixo somente leitura
            [
                str(
                    Path(os.environ["SystemRoot"])
                    / "System32/WindowsPowerShell/v1.0/powershell.exe"
                ),
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                comando,
            ],
            capture_output=True,
            encoding="utf-8-sig",
            errors="strict",
            timeout=prazo,
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        registros = json.loads(resultado.stdout)
        if isinstance(registros, dict):
            registros = [registros]
        if not isinstance(registros, list):
            raise ValueError
        encontrados = set()
        esperado = os.path.normcase(str(Path(perfil).resolve()))
        for registro in registros:
            linha = registro["CommandLine"]
            if not linha or "--user-data-dir" not in linha:
                continue
            args = _argumentos_processo(linha)
            for i, arg in enumerate(args):
                if arg.startswith("--user-data-dir="):
                    valor = arg.split("=", 1)[1]
                elif arg == "--user-data-dir" and i + 1 < len(args):
                    valor = args[i + 1]
                else:
                    continue
                if os.path.normcase(str(Path(valor).resolve())) == esperado:
                    encontrados.add(int(registro["ProcessId"]))
        return encontrados
    except subprocess.TimeoutExpired:
        # Nunca publicar cmd, stdout/stderr ou linhas de comando de processos.
        raise RecusaSessao("ENUMERACAO_ASSISTIDA_INDISPONIVEL_PRAZO") from None
    except subprocess.CalledProcessError:
        raise RecusaSessao("ENUMERACAO_ASSISTIDA_INDISPONIVEL_PROCESSO") from None
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        raise RecusaSessao("ENUMERACAO_ASSISTIDA_INDISPONIVEL") from None


def aguardar_saida_navegador(perfil, proc=None):
    """No máximo 15 s; ausência do principal não prova saída dos filhos."""
    limite = time.monotonic() + PRAZO_SAIDA_NAVEGADOR_S
    while True:
        restante = limite - time.monotonic()
        if restante <= 0:
            raise RecusaSessao("SAIDA_ASSISTIDA_NAO_CONFIRMADA")
        if proc is not None and proc.poll() is None:
            # Uma consulta CIM é cara e só pode provar a saída dos filhos após
            # a saída do principal. Não gastar esse prazo com consultas precoces.
            time.sleep(min(INTERVALO_LIMPEZA_S, restante))
            continue
        processos = _processos_do_perfil(perfil, restante)
        if time.monotonic() > limite:
            raise RecusaSessao("SAIDA_ASSISTIDA_NAO_CONFIRMADA")
        # CIM pode consumir quase todo o prazo. O principal pode ter saído
        # durante a consulta; não repetir a enumeração por um poll obsoleto.
        principal_saiu = proc is None or proc.poll() is not None
        if principal_saiu and not processos:
            if proc is not None:
                proc.wait(timeout=max(0, limite - time.monotonic()))
            return
        time.sleep(min(INTERVALO_LIMPEZA_S, max(0, limite - time.monotonic())))


def fechar_navegador(proc, perfil):
    kernel, _ = _dlls()
    job = getattr(proc, "_fv_job", None)
    if job:
        kernel.TerminateJobObject.argtypes = (w.HANDLE, w.UINT)
        kernel.CloseHandle.argtypes = (w.HANDLE,)
        kernel.TerminateJobObject(job, 1)
        kernel.CloseHandle(job)
        proc._fv_job = None
    elif proc.poll() is None:
        proc.kill()
    aguardar_saida_navegador(perfil, proc)
