[CmdletBinding()]
param(
    [string]$ComposeFile = (Join-Path $PSScriptRoot '..\infra\docker-compose.yml'),
    [Parameter(Mandatory)]
    [ValidatePattern('^[a-z0-9][a-z0-9_-]*$')]
    [string]$ProjectName,
    [switch]$LocalImage,
    [switch]$Volumes,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker CLI was not found on PATH.'
}

docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
    throw 'Docker Compose is unavailable. Start Docker Desktop and retry.'
}

$resolvedComposeFile = (Resolve-Path $ComposeFile).Path
$composeArgs = @('-f', $resolvedComposeFile)
if ($LocalImage) {
    $localOverride = Join-Path (Split-Path $resolvedComposeFile) 'docker-compose.local.yml'
    if (-not (Test-Path $localOverride)) {
        throw "Local image override not found: $localOverride"
    }
    $composeArgs += @('-f', (Resolve-Path $localOverride).Path)
}

$downArgs = @('compose') + $composeArgs + @(
    '-p', $ProjectName, 'down', '--remove-orphans'
)
if ($Volumes) {
    $downArgs += '--volumes'
}

Write-Host "Compose project: $ProjectName"
if ($DryRun) {
    Write-Host "Dry run: docker $($downArgs -join ' ')"
    exit 0
}

& docker @downArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Destroyed Compose project: $ProjectName"