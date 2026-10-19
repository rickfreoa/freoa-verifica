# Instala FREOA Verifica 1.2.0; Python 3.11+.
$ErrorActionPreference = "Stop"

function Invoke-NativeChecked {
    param([string]$Etapa, [string]$Comando, [string[]]$Argumentos)
    $resultado = & $Comando @Argumentos
    $codigo = $LASTEXITCODE
    if ($codigo -ne 0) { throw "FALHOU na etapa: $Etapa (exit=$codigo)" }
    return $resultado
}

$etapa = "preparar"
try {
    $versao = "1.2.0"
    $repo = "rickfreoa/freoa-verifica"
    $base = "https://github.com/$repo/releases/download/v$versao"
    $destino = Join-Path $env:USERPROFILE "freoa-verifica"
    $registroDir = Join-Path $env:LOCALAPPDATA "freoa-verifica"
    New-Item -ItemType Directory -Force $destino, $registroDir | Out-Null
    $wheelNome = "freoa_verifica-$versao-py3-none-any.whl"
    $wheel = Join-Path $destino $wheelNome
    $local = Join-Path $PSScriptRoot $wheelNome
    $etapa = "baixar wheel"
    if (Test-Path $local) { Copy-Item -LiteralPath $local -Destination $wheel -Force }
    else { Invoke-WebRequest "$base/$wheelNome" -OutFile $wheel -UseBasicParsing }

    $gh = Get-Command gh -ErrorAction SilentlyContinue
    $proveniencia = "PROVENIENCIA NAO VERIFICADA (instale o GitHub CLI para verificar)"
    if ($gh) {
        $etapa = "verificar proveniencia"
        Invoke-NativeChecked $etapa $gh.Source @("attestation", "verify", $wheel, "--repo", $repo) | Out-Host
        $proveniencia = "VERIFICADA: gh attestation verify"
    } else { Write-Warning $proveniencia }
    @{ versao = $versao; proveniencia = $proveniencia; concluida = $false } |
        ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $registroDir "instalacao.json")

    $lock = Join-Path $destino "requirements-lock.txt"
    $etapa = "baixar lock"
    # Apenas 404 significa asset opcional ausente; falha de rede não é ausência.
    $temLock = $true
    try { Invoke-WebRequest "$base/requirements-lock.txt" -OutFile $lock -UseBasicParsing }
    catch {
        if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 404) {
            $temLock = $false
            Write-Warning "requirements-lock.txt ausente nesta release"
        } else { throw }
    }
    if ($gh -and $temLock) {
        $etapa = "verificar lock"
        Invoke-NativeChecked $etapa $gh.Source @("attestation", "verify", $lock, "--repo", $repo) | Out-Host
    }
    $etapa = "criar venv"
    if (-not (Test-Path "$destino\.venv")) {
        Invoke-NativeChecked $etapa "python" @("-m", "venv", "$destino\.venv") | Out-Host
    }
    $python = "$destino\.venv\Scripts\python.exe"
    $fv = "$destino\.venv\Scripts\fv.exe"
    $etapa = "instalar wheel"
    $pipArgs = @("-m", "pip", "install", "$wheel`[server`]")
    if ($temLock) { $pipArgs += @("-c", $lock) }
    Invoke-NativeChecked $etapa $python $pipArgs | Out-Host
    $etapa = "validar versao"
    $v = (Invoke-NativeChecked $etapa $fv @("--version")) -join "`n"
    if ($v -notmatch '(?<![0-9.])1\.2\.0(?![0-9.])') { throw "versao inesperada: $v" }
    $etapa = "instalar snapshot"
    $inst = (Invoke-NativeChecked $etapa $fv @("snapshot", "install", "--json")) -join "`n" | ConvertFrom-Json
    if ($inst.status -ne "ok") { throw "snapshot recusado: $($inst.motivo)" }
    $etapa = "validar acervo"
    $info = (Invoke-NativeChecked $etapa $fv @("snapshot", "info", "--json")) -join "`n" | ConvertFrom-Json
    if (-not $info.instalado -or -not $info.vinculado -or $null -eq $info.derived_version_atual) { throw "acervo nao instalado/vinculado" }
    if ($null -eq $info.derived_version -or [int]$info.derived_version -lt [int]$info.derived_version_atual) {
        $etapa = "reconstruir acervo"
        $rebuild = (Invoke-NativeChecked $etapa $fv @("acervo", "reconstruir", "--json")) -join "`n" | ConvertFrom-Json
        if ($rebuild.status -ne "ok") { throw "reconstrucao recusada" }
        $info = (Invoke-NativeChecked $etapa $fv @("snapshot", "info", "--json")) -join "`n" | ConvertFrom-Json
    }
    if (-not $info.instalado -or -not $info.vinculado -or $null -eq $info.derived_version -or
        [int]$info.derived_version -ne [int]$info.derived_version_atual) { throw "derivados incompativeis" }
    $etapa = "doctor offline"
    $doctor = (Invoke-NativeChecked $etapa $fv @("doctor", "--offline", "--json")) -join "`n" | ConvertFrom-Json
    if ($doctor.status -ne "ok" -or -not $doctor.verificacoes -or
        @($doctor.verificacoes | Where-Object { $_.status -notin @("ok", "alerta") }).Count -gt 0 -or
        $doctor.acervo_incompleto) { throw "diagnostico bloqueante" }
    @{ versao = $versao; proveniencia = $proveniencia; concluida = $true } |
        ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $registroDir "instalacao.json")
    Write-Host "Pronto. Comandos em: $destino\.venv\Scripts (fv.exe e freoa-verifica-mcp.exe)."
} catch {
    Write-Error "FALHOU na etapa: $etapa - $_" -ErrorAction Continue
    exit 1
}
