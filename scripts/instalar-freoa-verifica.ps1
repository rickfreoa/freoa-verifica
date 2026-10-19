# Instala FREOA Verifica; Python 3.11+. O padrão de -Versao é o __version__ do repositório na release.
# A attestation é obrigatória; -SemAttestation pula a verificação e grava attestation_verificada: false.
param(
    [string]$Versao = "1.2.0",
    [switch]$SemAttestation
)
$ErrorActionPreference = "Stop"

function Invoke-NativeChecked {
    param([string]$Etapa, [string]$Comando, [string[]]$Argumentos)
    $resultado = & $Comando @Argumentos
    $codigo = $LASTEXITCODE
    if ($codigo -ne 0) {
        $saida = (($resultado | Out-String).Trim() -split "`n" | Select-Object -Last 15) -join "`n"
        throw "FALHOU na etapa: $Etapa (exit=$codigo)`n$saida"
    }
    return $resultado
}

$etapa = "preparar"
try {
    $versao = $Versao
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

    $etapa = "verificar proveniencia"
    $gh = Get-Command gh -ErrorAction SilentlyContinue
    $verificada = $false
    $commit = $null
    if ($SemAttestation) {
        $proveniencia = "PROVENIENCIA NAO VERIFICADA (-SemAttestation)"
        Write-Warning $proveniencia
    } else {
        if (-not $gh) { throw "GitHub CLI (gh) ausente: attestation obrigatoria (use -SemAttestation para prosseguir sem verificar)" }
        $att = Invoke-NativeChecked $etapa $gh.Source @("attestation", "verify", $wheel, "--repo", $repo, "--signer-workflow", "$repo/.github/workflows/release.yml", "--source-ref", "refs/tags/v$versao", "--deny-self-hosted-runners", "--format", "json")
        $verificada = $true
        $proveniencia = "VERIFICADA: gh attestation verify"
        # Commit da release, conforme o certificado da attestation; ausente se o formato mudar.
        try { $commit = (($att | Out-String) | ConvertFrom-Json)[0].verificationResult.signature.certificate.sourceRepositoryDigest } catch { $commit = $null }
    }
    @{ versao = $versao; proveniencia = $proveniencia; attestation_verificada = $verificada; commit = $commit; concluida = $false } |
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
    if ($verificada -and $temLock) {
        $etapa = "verificar lock"
        Invoke-NativeChecked $etapa $gh.Source @("attestation", "verify", $lock, "--repo", $repo, "--signer-workflow", "$repo/.github/workflows/release.yml", "--source-ref", "refs/tags/v$versao", "--deny-self-hosted-runners") | Out-Host
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
    if ($v -notmatch ('(?<![0-9.])' + [regex]::Escape($versao) + '(?![0-9.])')) { throw "versao inesperada: $v" }
    # Instalação de snapshot é anexação: acervo anterior sem vínculo comprovado (1.1, ou instalado com
    # --aceitar-nao-vinculado) contaminaria o novo. Ele é preservado ao lado e o snapshot vai para home limpo.
    $etapa = "preservar acervo anterior"
    $pre = (Invoke-NativeChecked $etapa $fv @("snapshot", "info", "--json")) -join "`n" | ConvertFrom-Json
    $temDados = $pre.instalado -or ([int]$pre.obras -gt 0) -or ([int]$pre.capturas -gt 0) -or ([int]$pre.decisoes -gt 0)
    if ($temDados -and $pre.vinculado -ne $true) {
        $homeAtual = if ($pre.home) { [string]$pre.home } else { $registroDir }  # respeita FV_HOME
        $bak = "$homeAtual.pre-$versao-$(Get-Date -Format yyyyMMddHHmmss)"
        $n = 0
        while (Test-Path -LiteralPath $bak) { $n++; $bak = "$homeAtual.pre-$versao-$(Get-Date -Format yyyyMMddHHmmss)-$n" }
        Move-Item -LiteralPath $homeAtual $bak
        New-Item -ItemType Directory -Force $homeAtual | Out-Null
        Write-Host "Acervo anterior sem vinculo preservado em $bak"
    }
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
    @{ versao = $versao; proveniencia = $proveniencia; attestation_verificada = $verificada; commit = $commit
       snapshot_sha256 = $info.proveniencia.snapshot_sha256; concluida = $true } |
        ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $registroDir "instalacao.json")
    Write-Host "Pronto. Comandos em: $destino\.venv\Scripts (fv.exe e freoa-verifica-mcp.exe)."
} catch {
    Write-Error "FALHOU na etapa: $etapa - $_" -ErrorAction Continue
    exit 1
}
