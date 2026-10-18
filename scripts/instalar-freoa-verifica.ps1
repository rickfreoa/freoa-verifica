# Instala o FREOA Verifica 1.1.0 e o acervo (snapshot) no Windows.
# Uso: abra o PowerShell na pasta deste arquivo e rode:
#   powershell -ExecutionPolicy Bypass -File .\instalar-freoa-verifica.ps1
# Requer Python 3.11 ou superior. Se o wheel estiver na mesma pasta, ele é usado; senão, baixa da release.
$ErrorActionPreference = "Stop"
$destino = Join-Path $env:USERPROFILE "freoa-verifica"
$wheelLocal = Join-Path $PSScriptRoot "freoa_verifica-1.1.0-py3-none-any.whl"
$alvo = if (Test-Path $wheelLocal) { "$wheelLocal[server]" } else { "freoa-verifica[server] @ https://github.com/rickfreoa/freoa-verifica/releases/download/v1.1.0/freoa_verifica-1.1.0-py3-none-any.whl" }

if (-not (Test-Path "$destino\.venv")) { python -m venv "$destino\.venv" }
& "$destino\.venv\Scripts\python.exe" -m pip install --upgrade pip | Out-Null
& "$destino\.venv\Scripts\python.exe" -m pip install "$alvo"
& "$destino\.venv\Scripts\fv.exe" --version

# Baixa o snapshot da última release, confere o SHA-256 e instala no diretório de dados padrão.
& "$destino\.venv\Scripts\fv.exe" snapshot install
& "$destino\.venv\Scripts\fv.exe" snapshot info
& "$destino\.venv\Scripts\fv.exe" doctor --offline

Write-Host ""
Write-Host "Pronto. Comandos em: $destino\.venv\Scripts (fv.exe e freoa-verifica-mcp.exe)."
