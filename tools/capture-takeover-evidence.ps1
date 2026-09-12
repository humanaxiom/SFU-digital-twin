<# Capture takeover evidence by running all file work inside the artifact container. #>
[CmdletBinding()]
param(
    [switch]$LocalImage
)

$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$exitCode = 0
Push-Location $repoRoot
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker CLI was not found on PATH.'
    }

    $revision = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $revision) {
        throw 'Cannot read repository revision.'
    }
    $paths = @(& git -c core.quotePath=false ls-files --modified --others --exclude-standard)
    if ($LASTEXITCODE -ne 0) {
        throw 'Cannot enumerate dirty files.'
    }
    $paths += @(& git -c core.quotePath=false diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) {
        throw 'Cannot enumerate staged files.'
    }
    $status = @(& git -c core.quotePath=false status --porcelain=v1)
    if ($LASTEXITCODE -ne 0) {
        throw 'Cannot read repository status.'
    }

    $composeFile = (Resolve-Path (Join-Path $PSScriptRoot '..\infra\docker-compose.yml')).Path
    $composeArgs = @('-f', $composeFile)
    if ($LocalImage) {
        $localComposeFile = Join-Path (Split-Path $composeFile -Parent) 'docker-compose.local.yml'
        if (-not (Test-Path -LiteralPath $localComposeFile -PathType Leaf)) {
            throw "Local image override not found: $localComposeFile"
        }
        $composeArgs += @('-f', (Resolve-Path $localComposeFile).Path)
    }

    $dockerArgs = $composeArgs + @(
        'run', '--rm', 'artifact', 'env',
        'PYTHONPATH=/workspace/packages/wayfinding/src',
        'python', '/workspace/tools/capture_takeover_evidence.py',
        ('--head=' + $revision)
    )
    foreach ($line in $status) {
        $dockerArgs += @('--status=' + [string]$line)
    }
    foreach ($path in $paths) {
        $dockerArgs += @('--path=' + [string]$path)
    }

    & docker compose @dockerArgs
    $exitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

if ($exitCode -ne 0) {
    exit $exitCode
}
