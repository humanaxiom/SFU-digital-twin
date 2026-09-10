[CmdletBinding()]
param(
    [string]$ComposeFile = (Join-Path $PSScriptRoot '..\infra\docker-compose.yml'),
    [ValidateRange(1024, 65429)]
    [int]$BasePort = 18000,
    [ValidatePattern('^[a-z0-9][a-z0-9_-]*$')]
    [string]$ProjectName = 'sfudt-wayfinding',
    [ValidateRange(1, 100)]
    [int]$Attempts = 50,
    [switch]$LocalImage,
    [switch]$Build,
    [switch]$Test,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$portBlockSize = 10
$portOffsets = [ordered]@{
    DTWIN_POSTGIS_HOST_PORT   = 0
    DTWIN_REDIS_HOST_PORT     = 1
    DTWIN_MARTIN_HOST_PORT    = 2
    DTWIN_API_HOST_PORT       = 3
    DTWIN_WEB_HOST_PORT       = 4
    DTWIN_NEO4J_HTTP_HOST_PORT = 5
    DTWIN_NEO4J_BOLT_HOST_PORT = 6
    DTWIN_DEMO_HOST_PORT      = 7
}
$gates = @(
    @{ Name = 'test'; Command = 'pytest packages/wayfinding/tests'.Split(' ') },
    @{ Name = 'lint'; Command = 'ruff check packages/wayfinding'.Split(' ') },
    @{ Name = 'type'; Command = 'pyright packages/wayfinding/src'.Split(' ') },
    @{ Name = 'dataqa'; Command = 'pytest packages/wayfinding/tests -m dataqa --strict-markers'.Split(' ') }
)

function Test-HostPortAvailable {
    param([int]$Port)

    if ($script:DockerPublishedPorts -match ":$Port->") {
        return $false
    }

    $socket = [System.Net.Sockets.Socket]::new(
        [System.Net.Sockets.AddressFamily]::InterNetwork,
        [System.Net.Sockets.SocketType]::Stream,
        [System.Net.Sockets.ProtocolType]::Tcp
    )
    try {
        $socket.ExclusiveAddressUse = $true
        $socket.Bind([System.Net.IPEndPoint]::new([System.Net.IPAddress]::Any, $Port))
        return $true
    }
    catch [System.Net.Sockets.SocketException] {
        return $false
    }
    finally {
        $socket.Dispose()
    }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker CLI was not found on PATH.'
}

docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
    throw 'Docker Compose is unavailable. Start Docker Desktop and retry.'
}
$script:DockerPublishedPorts = @(docker ps --format '{{.Ports}}')
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to inspect Docker host-port allocations.'
}

$resolvedComposeFile = (Resolve-Path $ComposeFile).Path
$composeArgs = @('-f', $resolvedComposeFile)
$composeText = Get-Content -LiteralPath $resolvedComposeFile -Raw
$composeHasPlaceholderDigest = $composeText -match 'sha256:PUBLISHED_DIGEST_REQUIRED'
$useLocalOverride = $LocalImage
$buildLocalImage = $false
if ($Build -and -not $useLocalOverride -and $composeHasPlaceholderDigest) {
    $useLocalOverride = $true
    $buildLocalImage = $true
    Write-Host 'Detected unpublished build-image digest placeholder; enabling local image override for -Build.'
}

if ($useLocalOverride) {
    $localOverride = Join-Path (Split-Path $resolvedComposeFile) 'docker-compose.local.yml'
    if (-not (Test-Path $localOverride)) {
        throw "Local image override not found: $localOverride"
    }
    $composeArgs += @('-f', (Resolve-Path $localOverride).Path)
}

$selectedBase = $null
for ($attempt = 0; $attempt -lt $Attempts; $attempt++) {
    $candidateBase = $BasePort + ($attempt * $portBlockSize)
    if (($candidateBase + ($portOffsets.Values | Measure-Object -Maximum).Maximum) -gt 65535) {
        break
    }
    $candidatePorts = $portOffsets.Values | ForEach-Object { $candidateBase + $_ }
    if (($candidatePorts | Where-Object { -not (Test-HostPortAvailable $_) }).Count -eq 0) {
        $selectedBase = $candidateBase
        break
    }
}

if ($null -eq $selectedBase) {
    throw "No free host-port block found after $Attempts attempts from port $BasePort."
}

$selectedProject = "$ProjectName-$selectedBase"
$previousEnvironment = @{}
$failedGate = $null
$gateExitCode = 0
foreach ($entry in $portOffsets.GetEnumerator()) {
    $previousEnvironment[$entry.Key] = [Environment]::GetEnvironmentVariable($entry.Key, 'Process')
    [Environment]::SetEnvironmentVariable(
        $entry.Key,
        ($selectedBase + $entry.Value).ToString(),
        'Process'
    )
}

try {
    $services = @(docker compose @composeArgs config --services)
    if ($LASTEXITCODE -ne 0 -or $services.Count -eq 0) {
        throw "No services resolved from $resolvedComposeFile."
    }

    Write-Host "Compose project: $selectedProject"
    Write-Host "Compose file:    $resolvedComposeFile"
    foreach ($entry in $portOffsets.GetEnumerator()) {
        Write-Host ('{0,-28} {1}' -f $entry.Key, ($selectedBase + $entry.Value))
    }
    Write-Host ('{0,-28} {1}' -f 'Demo URL', "http://127.0.0.1:$($selectedBase + 7)/")

    $upArgs = @('compose') + $composeArgs + @('-p', $selectedProject, 'up', '-d', '--wait')
    if ($Build) {
        $upArgs += '--build'
    }

    if ($DryRun) {
        if ($buildLocalImage) {
            $composeDir = Split-Path $resolvedComposeFile -Parent
            $dockerfile = Join-Path $composeDir 'Dockerfile.build'
            $contextDir = (Resolve-Path (Join-Path $composeDir '..')).Path
            Write-Host "Dry run: docker build -f $dockerfile -t wayfinding-build:local $contextDir"
        }
        Write-Host "Dry run: docker $($upArgs -join ' ')"
        if ($Test) {
            foreach ($gate in $gates) {
                $gateArgs = @('compose') + $composeArgs + @(
                    '-p', $selectedProject, 'exec', '-T', 'artifact', 'env',
                    'PYTHONPATH=/workspace/packages/wayfinding/src'
                ) + $gate.Command
                Write-Host "Dry run: docker $($gateArgs -join ' ')"
            }
        }
        exit 0
    }

    if ($buildLocalImage) {
        $composeDir = Split-Path $resolvedComposeFile -Parent
        $dockerfile = Join-Path $composeDir 'Dockerfile.build'
        if (-not (Test-Path $dockerfile)) {
            throw "Build file not found: $dockerfile"
        }
        $contextDir = (Resolve-Path (Join-Path $composeDir '..')).Path
        & docker build -f $dockerfile -t wayfinding-build:local $contextDir
        if ($LASTEXITCODE -ne 0) {
            throw "Docker image build failed with exit code $LASTEXITCODE."
        }
    }

    & docker @upArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose failed with exit code $LASTEXITCODE."
    }

    & docker compose @composeArgs -p $selectedProject ps
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose status failed with exit code $LASTEXITCODE."
    }

    if ($Test) {
        foreach ($gate in $gates) {
            Write-Host "Running $($gate.Name) gate..."
            $gateArgs = @('compose') + $composeArgs + @(
                '-p', $selectedProject, 'exec', '-T', 'artifact', 'env',
                'PYTHONPATH=/workspace/packages/wayfinding/src'
            ) + $gate.Command
            & docker @gateArgs
            if ($LASTEXITCODE -ne 0) {
                $failedGate = $gate.Name
                $gateExitCode = $LASTEXITCODE
                break
            }
        }
    }
}
finally {
    foreach ($entry in $portOffsets.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable(
            $entry.Key,
            $previousEnvironment[$entry.Key],
            'Process'
        )
    }
}

if ($gateExitCode -ne 0) {
    Write-Host "$failedGate gate failed with exit code $gateExitCode." -ForegroundColor Red
    exit $gateExitCode
}