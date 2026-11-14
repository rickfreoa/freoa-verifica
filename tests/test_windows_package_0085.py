"""0085 §4: virtualização do home; fixtures sintéticas por construção, sem instalação."""
from pathlib import Path

import pytest

from freoa_verifica.windows_package import home_virtualizado
from freoa_verifica.service import Verifica


@pytest.mark.parametrize("path,expected", [
    (r"C:\Users\x\AppData\Local\Packages\Claude_x\LocalCache\Local\freoa-verifica", True),
    (r"c:\users\x\appdata\local\PACKAGES\Claude_x\home", True),
    (r"C:\Users\x\AppData\Local\Packages-old\home", False),
    (r"C:\Users\x\AppData\Local\freoa-verifica", False),
    (r"D:\Packages\home", False),
])
def test_caminho_virtualizado(path, expected):
    assert home_virtualizado(path, windows=True, localappdata=r"C:\Users\x\AppData\Local", em_pacote=lambda: False) is expected


def test_funcao_de_pacote_injetada_e_outros_so():
    assert home_virtualizado(r"C:\home", windows=True, em_pacote=lambda: True)
    assert not home_virtualizado("/home/x", windows=False, em_pacote=lambda: pytest.fail("não é Windows"))


def test_doctor_home_alerta(tmp_path, monkeypatch):
    import freoa_verifica.windows_package as wp
    monkeypatch.setattr(wp, "processo_em_pacote", lambda: True)
    monkeypatch.setattr(wp, "home_virtualizado", lambda home: True)
    with Verifica(home=tmp_path / "home") as svc:
        out = svc.doctor(offline=True)
    check = next(c for c in out["verificacoes"] if c["nome"] == "home")
    assert check["status"] == "alerta" and check["detalhe"] == "home_virtualizado"


@pytest.mark.repositorio
def test_instalador_detecta_e_relanca_antes_de_gravar_home():
    text = (Path(__file__).resolve().parents[1] / "scripts/instalar-freoa-verifica.ps1").read_text(encoding="utf-8-sig")
    assert '[DllImport("kernel32.dll"' in text and "GetCurrentPackageFullName" in text and "15700" in text
    assert "[switch]$PermitirVirtualizado" in text
    assert "Invoke-CimMethod -ClassName Win32_Process -MethodName Create" in text
    assert text.index("Test-CurrentPackage") < text.index('$etapa = "preparar"')
    assert "-Versao '$versionLiteral'$attArg" in text and "-SemAttestation" in text
    assert "exit $code" in text and "exit 1" in text and "Use o terminal comum" in text
    assert "Get-Content -LiteralPath $log" in text and "ProcessId" in text
