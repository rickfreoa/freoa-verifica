"""Recusa conservadora de entrada não interativa, remota ou por script no Windows."""

from __future__ import annotations

import ctypes
import os
import re
import sys
from ctypes import wintypes as w
from pathlib import Path

from freoa_verifica.assistida.ambiente import RecusaSessao, _dlls


def conferir_terminal():
    if not sys.stdin.isatty() or not sys.stdout.isatty() or not sys.stderr.isatty():
        raise RecusaSessao("SESSAO_ASSISTIDA_EXIGE_TTY")
    if any(
        os.environ.get(k)
        for k in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY", "WINRS_SHELL_ID")
    ):
        raise RecusaSessao("SESSAO_ASSISTIDA_REMOTA_RECUSADA")
    kernel, _ = _dlls()
    if ctypes.windll.user32.GetSystemMetrics(0x1000):
        raise RecusaSessao("SESSAO_ASSISTIDA_REMOTA_RECUSADA")
    sessao = w.DWORD()
    if (
        not kernel.ProcessIdToSessionId(os.getpid(), ctypes.byref(sessao))
        or not sessao.value
    ):
        raise RecusaSessao("SESSAO_ASSISTIDA_NAO_INTERATIVA")
    # Exige pai shell interativo. cmd /c, PowerShell -File/-Command e intermediários não passam.
    kernel.OpenProcess.argtypes = (w.DWORD, w.BOOL, w.DWORD)
    kernel.OpenProcess.restype = w.HANDLE
    proc = kernel.OpenProcess(0x1000 | 0x400, False, os.getppid())
    if not proc:
        raise RecusaSessao("ORIGEM_TERMINAL_INDISPONIVEL")
    try:

        class UnicodeString(ctypes.Structure):
            _fields_ = [
                ("Length", w.USHORT),
                ("MaximumLength", w.USHORT),
                ("Buffer", w.LPWSTR),
            ]

        nt = ctypes.WinDLL("ntdll")
        nt.NtQueryInformationProcess.argtypes = (
            w.HANDLE,
            w.ULONG,
            ctypes.c_void_p,
            w.ULONG,
            ctypes.POINTER(w.ULONG),
        )
        # O launcher de console instalado fv.exe é o único intermediário admitido.
        kernel.QueryFullProcessImageNameW.argtypes = (
            w.HANDLE,
            w.DWORD,
            w.LPWSTR,
            ctypes.POINTER(w.DWORD),
        )
        imagem = ctypes.create_unicode_buffer(32768)
        tamanho = w.DWORD(len(imagem))
        if not kernel.QueryFullProcessImageNameW(
            proc, 0, imagem, ctypes.byref(tamanho)
        ):
            raise RecusaSessao("ORIGEM_TERMINAL_INDISPONIVEL")
        if (
            Path(imagem.value).resolve()
            == Path(sys.executable).with_name("fv.exe").resolve()
        ):

            class Basic(ctypes.Structure):
                _fields_ = [
                    ("Reserved1", ctypes.c_void_p),
                    ("Peb", ctypes.c_void_p),
                    ("Reserved2", ctypes.c_void_p * 2),
                    ("Pid", ctypes.c_size_t),
                    ("ParentPid", ctypes.c_size_t),
                ]

            basic = Basic()
            if (
                nt.NtQueryInformationProcess(
                    proc, 0, ctypes.byref(basic), ctypes.sizeof(basic), None
                )
                != 0
            ):
                raise RecusaSessao("ORIGEM_TERMINAL_INDISPONIVEL")
            kernel.CloseHandle.argtypes = (w.HANDLE,)
            kernel.CloseHandle(proc)
            proc = kernel.OpenProcess(0x1000 | 0x400, False, basic.ParentPid)
            if not proc:
                raise RecusaSessao("ORIGEM_TERMINAL_INDISPONIVEL")
        n = w.ULONG()
        nt.NtQueryInformationProcess(proc, 60, None, 0, ctypes.byref(n))
        if not n.value or n.value > 131072:
            raise RecusaSessao("ORIGEM_TERMINAL_INDISPONIVEL")
        buf = ctypes.create_string_buffer(n.value)
        if nt.NtQueryInformationProcess(proc, 60, buf, n, ctypes.byref(n)) != 0:
            raise RecusaSessao("ORIGEM_TERMINAL_INDISPONIVEL")
        texto = UnicodeString.from_buffer(buf).Buffer
        if not re.fullmatch(
            r'\s*"?[^"\r\n]*\\(?:cmd|powershell|pwsh)\.exe"?\s*(?:(?:-NoLogo|-NoProfile|-NoExit)\s*)*',
            texto,
            re.I,
        ):
            raise RecusaSessao("ORIGEM_TERMINAL_RECUSADA")
    finally:
        kernel.CloseHandle.argtypes = (w.HANDLE,)
        kernel.CloseHandle(proc)
