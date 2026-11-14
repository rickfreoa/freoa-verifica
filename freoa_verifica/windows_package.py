"""Diagnóstico de virtualização de home no Windows (0085 §4), sem escrever no sistema."""
from __future__ import annotations

import ctypes
import os
from pathlib import PureWindowsPath


def processo_em_pacote():
    if os.name != "nt":
        return False
    tamanho = ctypes.c_uint32(0)
    consultar = ctypes.WinDLL("kernel32", use_last_error=True).GetCurrentPackageFullName
    consultar.argtypes = [ctypes.POINTER(ctypes.c_uint32), ctypes.c_wchar_p]
    consultar.restype = ctypes.c_long
    return consultar(ctypes.byref(tamanho), None) != 15700  # APPMODEL_ERROR_NO_PACKAGE


def home_virtualizado(home, *, windows=None, localappdata=None, em_pacote=None):
    if not (os.name == "nt" if windows is None else windows):
        return False
    consultar = processo_em_pacote if em_pacote is None else em_pacote
    if consultar():
        return True
    base = os.environ.get("LOCALAPPDATA") if localappdata is None else localappdata
    if not base:
        return False
    path, packages = PureWindowsPath(home), PureWindowsPath(base) / "Packages"
    return path == packages or packages in path.parents
