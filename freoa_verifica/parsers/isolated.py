"""Parsers em processo separado; limites de recursos no filho e de I/O no pai."""
from __future__ import annotations
from dataclasses import asdict
import json
import os
import threading
import subprocess
import sys
from freoa_verifica.limites import restante
from freoa_verifica.parsers.model import Issue, ParsedDocument, document_from_dict

_PROFILES = ("planalto", "cvm_docx", "bcb_json", "cvm_pdf", "pdf_texto")
# Limites instalados pelo filho antes de importar parsers/ler bytes não confiáveis.
_LIMITES = {p: ((1024, 60) if p in {"cvm_pdf", "pdf_texto"} else (2048, 120))
            for p in _PROFILES}
INPUT_LIMIT = 200 * 1024**2
STDOUT_LIMIT = 64 * 1024**2
STDERR_LIMIT = 64 * 1024
LIMIT_INSTALL_EXIT = 78
_JOB_HANDLE = None  # Não fechar: KILL_ON_JOB_CLOSE deve durar até a saída do filho.


def _failure(profile: str, detail: str) -> ParsedDocument:
    return ParsedDocument(profile, "0", "", None, "", issues=[
        Issue("TRUNCATED", None, detail, blocking_scope="document"),
    ])

def parse_ou_indisponivel(profile: str, data: bytes | str, timeout: float, *, base_url: str | None = None) -> ParsedDocument:
    """Falha do filho (não a quarentena legítima do parser) vira Unavailable declarada."""
    from freoa_verifica.connectors.base import Unavailable

    doc = parse_isolated(profile, data, timeout, base_url=base_url)
    if doc.parser_version == "0":  # marca de _failure
        detalhe = next((i.detail for i in doc.issues if i.code == "TRUNCATED"), "falha")
        raise Unavailable(f"{profile}_nao_processado: {detalhe}"[:200])
    return doc


def parse_isolated(profile: str, data: bytes | str, timeout: float, *, base_url: str | None = None) -> ParsedDocument:
    """Executa em filho; timeout, falha ou saida invalida geram quarentena."""
    if profile not in _PROFILES:
        return _failure(profile, "perfil desconhecido")
    if len(data) > INPUT_LIMIT:
        return _failure(profile, "entrada_excedida")
    raw = data.encode("utf-8") if isinstance(data, str) else data
    if len(raw) > INPUT_LIMIT:
        return _failure(profile, "entrada_excedida")
    timeout = restante(timeout)
    if timeout <= 0:
        return _failure(profile, "orcamento esgotado")
    try:
        # Sem `with`: o __exit__ do Popen fecharia pipes ainda presos por um descendente fora do grupo
        # (setsid) e bloquearia o pai; _bounded_io fecha o que pode e abandona o resto no prazo.
        proc = subprocess.Popen(
            # -P: o diretório corrente não entra no sys.path do filho antes dos limites.
            [sys.executable, "-P", "-m", "freoa_verifica.parsers.isolated", profile, *([base_url] if base_url else [])],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0,
            # Grupo próprio: timeout e excesso matam também descendentes que herdem os pipes.
            **({"start_new_session": True} if os.name == "posix" else {}),
        )
        output, stderr, exceeded = _bounded_io(proc, raw, timeout)
        if exceeded:
            return _failure(profile, exceeded)
        if proc.returncode != 0:
            detail = stderr.decode("utf-8", "replace").strip().splitlines()
            return _failure(profile, f"parse_isolated falhou no filho (exit={proc.returncode}): "
                            + (detail[-1][:200] if detail else "sem detalhe"))
    except OSError as exc:
        return _failure(profile, f"parse_isolated indisponivel: {type(exc).__name__}")
    try:
        return document_from_dict(json.loads(output))
    except (ValueError, TypeError, KeyError, AttributeError):
        return _failure(profile, "parse_isolated sem resultado valido do filho")


def _bounded_io(proc, raw: bytes, timeout: float):
    """Drena ambos os pipes com armazenamento limitado, inclusive durante envio."""
    buffers = [bytearray(), bytearray()]
    failures = []

    def kill(reason):
        failures.append(reason)
        try:
            if os.name == "posix":
                os.killpg(proc.pid, 9)
            else:
                proc.kill()  # Job Object com KILL_ON_JOB_CLOSE e ACTIVE_PROCESS=1 cobre descendentes
        except OSError:
            pass

    def read(stream, index, limit):
        fd = stream.fileno()  # descritor cru: nenhuma trava de BufferedReader compartilhada com o fechamento
        try:
            while True:
                chunk = os.read(fd, min(65536, limit - len(buffers[index]) + 1))
                if not chunk:
                    break
                if len(buffers[index]) + len(chunk) > limit:
                    kill("stdout_excedido" if index == 0 else "stderr_excedido")
                    break
                buffers[index].extend(chunk)
        except OSError:
            kill("leitura_falhou")
        finally:
            stream.close()

    def write():
        try:
            # bufsize=0: write(2) pode ser parcial; repete até o fim (entrada truncada não pode virar documento).
            fd, mv = proc.stdin.fileno(), memoryview(raw)
            while mv:
                mv = mv[os.write(fd, mv[: 1 << 20]):]
        except (BrokenPipeError, OSError):
            pass
        finally:
            proc.stdin.close()

    threads = [threading.Thread(target=read, args=(proc.stdout, 0, STDOUT_LIMIT), daemon=True),
               threading.Thread(target=read, args=(proc.stderr, 1, STDERR_LIMIT), daemon=True),
               threading.Thread(target=write, daemon=True)]
    for thread in threads:
        thread.start()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill(f"parse_isolated excedeu timeout={timeout}s")
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
    for thread in threads:
        thread.join(timeout=5)
    if any(t.is_alive() for t in threads):
        # Descendente segurando os pipes (inclusive fora do grupo, via setsid): mata o grupo e encerra
        # como falha sem esperar; threads daemon e pipes são abandonados até o descendente morrer.
        kill("descendente_reteve_pipes")
        for thread in threads:
            thread.join(timeout=2)
    return buffers[0], buffers[1], failures[0] if failures else None


def _aplicar_limites(profile: str) -> None:
    mem_mb, cpu_s = _LIMITES[profile]
    if sys.platform == "win32":
        _windows_job(mem_mb, cpu_s)
        return
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (mem_mb << 20, mem_mb << 20))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))
    # NPROC é por UID, mas setrlimit só restringe este filho. Root/capabilities
    # podem ignorá-lo; não se promete contenção de descendentes nesses casos.
    if hasattr(resource, "RLIMIT_NPROC") and os.geteuid() != 0:
        resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))


def _windows_job(mem_mb: int, cpu_s: int) -> None:
    import ctypes as c
    from ctypes import wintypes as w
    global _JOB_HANDLE

    class Basic(c.Structure):
        _fields_ = [("PerProcessUserTimeLimit", c.c_int64), ("PerJobUserTimeLimit", c.c_int64),
                    ("LimitFlags", w.DWORD), ("MinimumWorkingSetSize", c.c_size_t),
                    ("MaximumWorkingSetSize", c.c_size_t), ("ActiveProcessLimit", w.DWORD),
                    ("Affinity", c.c_size_t), ("PriorityClass", w.DWORD), ("SchedulingClass", w.DWORD)]

    class IO(c.Structure):
        _fields_ = [(name, c.c_uint64) for name in
                    ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                     "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class Extended(c.Structure):
        _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", IO),
                    ("ProcessMemoryLimit", c.c_size_t), ("JobMemoryLimit", c.c_size_t),
                    ("PeakProcessMemoryUsed", c.c_size_t), ("PeakJobMemoryUsed", c.c_size_t)]

    k = c.WinDLL("kernel32", use_last_error=True)
    k.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]
    k.CreateJobObjectW.restype = w.HANDLE
    k.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
    k.SetInformationJobObject.restype = w.BOOL
    k.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    k.AssignProcessToJobObject.restype = w.BOOL
    k.GetCurrentProcess.argtypes = []
    k.GetCurrentProcess.restype = w.HANDLE
    k.CloseHandle.argtypes = [w.HANDLE]
    k.CloseHandle.restype = w.BOOL
    job = k.CreateJobObjectW(None, None)
    if not job:
        raise c.WinError(c.get_last_error())
    limits = Extended()
    # PROCESS_MEMORY | PROCESS_TIME | ACTIVE_PROCESS | KILL_ON_JOB_CLOSE |
    # DIE_ON_UNHANDLED_EXCEPTION. Não permitir breakaway.
    limits.BasicLimitInformation.LimitFlags = 0x100 | 0x2 | 0x8 | 0x2000 | 0x400
    limits.BasicLimitInformation.PerProcessUserTimeLimit = cpu_s * 10_000_000
    limits.BasicLimitInformation.ActiveProcessLimit = 1
    limits.ProcessMemoryLimit = mem_mb << 20
    if not k.SetInformationJobObject(job, 9, c.byref(limits), c.sizeof(limits)):
        error = c.get_last_error()
        k.CloseHandle(job)
        raise c.WinError(error)
    if not k.AssignProcessToJobObject(job, k.GetCurrentProcess()):
        error = c.get_last_error()
        k.CloseHandle(job)
        raise c.WinError(error)
    _JOB_HANDLE = job


def pdf_texto(body: bytes) -> ParsedDocument:
    """Texto de PDF de decisao (STF, TJSP) no filho: o pai nunca abre PDF de terceiro."""
    import io
    from pypdf import PdfReader
    from freoa_verifica.connectors.cvm_normas import PDF_MAX_PAGINAS, PDF_MAX_TEXTO
    reader = PdfReader(io.BytesIO(body))
    if len(reader.pages) > PDF_MAX_PAGINAS:
        raise ValueError("pdf_paginas_excedidas")
    parts, total = [], 0
    for page in reader.pages:
        t = page.extract_text() or ""
        total += len(t)
        if total > PDF_MAX_TEXTO:
            raise ValueError("pdf_texto_excedido")
        parts.append(t)
    return ParsedDocument("pdf_texto", "pdf-texto-1", "", None, "\n".join(parts))


def texto_pdf_isolado(body: bytes, timeout: float = 60.0) -> str:
    """Falha, excesso ou timeout do filho é indisponibilidade declarada, nunca texto vazio."""
    from freoa_verifica.connectors.base import Unavailable

    doc = parse_isolated("pdf_texto", body, timeout)
    if doc.quarantined:
        detalhe = next((i.detail for i in doc.issues if i.code == "TRUNCATED"), "falha")
        raise Unavailable(f"pdf_nao_processado: {detalhe}"[:200])
    return doc.text


def _main() -> None:
    try:
        _aplicar_limites(sys.argv[1])
    except Exception:
        sys.stderr.write("limites_nao_instalados\n")
        sys.exit(LIMIT_INSTALL_EXIT)
    from freoa_verifica.parsers.planalto import parse_planalto
    from freoa_verifica.parsers.cvm_docx import parse_cvm_docx
    from freoa_verifica.parsers.bcb_json import parse_bcb_json
    from freoa_verifica.connectors.cvm_normas import parse_pdf_direto
    parsers = dict(zip(_PROFILES, (parse_planalto, parse_cvm_docx, parse_bcb_json, parse_pdf_direto, pdf_texto)))
    try:
        body = sys.stdin.buffer.read()
        if sys.argv[1] == "planalto" and len(sys.argv) > 2:
            document = parse_planalto(body, base_url=sys.argv[2])
        else:
            document = parsers[sys.argv[1]](body)
    except MemoryError:
        sys.stderr.write("memoria_excedida\n")
        sys.exit(3)
    except Exception as exc:  # noqa: BLE001 — o pai transforma em quarentena
        sys.stderr.write(str(getattr(exc, "reason", None) or type(exc).__name__) + "\n")
        sys.exit(3)
    sys.stdout.buffer.write(json.dumps(asdict(document), ensure_ascii=False).encode("utf-8"))

if __name__ == "__main__":
    _main()
