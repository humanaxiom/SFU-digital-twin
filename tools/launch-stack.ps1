[CmdletBinding()]
param(
    [string]$ComposeFile,
    [ValidateRange(1024, 65429)]
    [int]$BasePort = 18000,
    [ValidatePattern('^[a-z0-9][a-z0-9_-]*$')]
    [string]$ProjectName = 'sfudt-wayfinding',
    [ValidateRange(1, 100)]
    [int]$Attempts = 50,
    [switch]$LocalImage,
    [switch]$Build,
    [switch]$Test,
    [switch]$NoPublicDemo,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
# Windows PowerShell 5.1 does not populate PSScriptRoot during parameter defaults.
if (-not $PSBoundParameters.ContainsKey('ComposeFile')) {
    $ComposeFile = Join-Path $PSScriptRoot '..\infra\docker-compose.yml'
}
$machineName = [Environment]::MachineName
if ($machineName -notmatch '^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$') {
    throw 'Local machine name is not a DNS-compatible host label.'
}
$bindAddress = if ($env:DTWIN_DEMO_BIND_ADDRESS) { $env:DTWIN_DEMO_BIND_ADDRESS } else { '0.0.0.0' }
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

    if ($script:OtherPublishedPorts -match ":$Port->") {
        return $false
    }
    if ($script:OwnedPublishedPorts -match ":$Port->") {
        return $true
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
$containerIds = @(docker ps -aq)
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to inspect Docker host-port allocations.'
}

$dockerRows = @()
if ($containerIds.Count -gt 0) {
    # JSON templates avoid native Windows PowerShell argument-quoting problems.
    $dockerRows = @(docker inspect --format '{{json .Config.Labels}}|{{json .NetworkSettings.Ports}}' @containerIds)
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to inspect Docker project ownership.'
    }
}
$dockerContainers = @($dockerRows | ForEach-Object {
    $fields = $_ -split '\|', 2
    $labels = $fields[0] | ConvertFrom-Json
    $portMap = $fields[1] | ConvertFrom-Json
    $published = @($portMap.PSObject.Properties | ForEach-Object {
        $containerPort = $_.Name
        foreach ($binding in $_.Value) { "$($binding.HostIp):$($binding.HostPort)->$containerPort" }
    })
    [pscustomobject]@{
        Project = $labels.'com.docker.compose.project'
        ConfigFiles = $labels.'com.docker.compose.project.config_files'
        Ports = $published
    }
})
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

$existingBase = $null
for ($attempt = 0; $attempt -lt $Attempts; $attempt++) {
    $candidateBase = $BasePort + ($attempt * $portBlockSize)
    $existing = @($dockerContainers | Where-Object { $_.Project -eq "$ProjectName-$candidateBase" })
    if ($existing.Count -gt 0) {
        foreach ($container in $existing) {
            $configPaths = @($container.ConfigFiles -split ',' | ForEach-Object { $_.Replace('\', '/') })
            if ($configPaths -notcontains $resolvedComposeFile.Replace('\', '/')) {
                throw "Existing project $ProjectName-$candidateBase belongs to a different Compose file."
            }
        }
        $existingBase = $candidateBase
        break
    }
}

$selectedBase = $null
for ($attempt = 0; $attempt -lt $Attempts; $attempt++) {
    $candidateBase = if ($null -ne $existingBase) { $existingBase } else { $BasePort + ($attempt * $portBlockSize) }
    if (($candidateBase + ($portOffsets.Values | Measure-Object -Maximum).Maximum) -gt 65535) {
        break
    }
    $candidateProject = "$ProjectName-$candidateBase"
    $script:OwnedPublishedPorts = @($dockerContainers | Where-Object { $_.Project -eq $candidateProject } | ForEach-Object { $_.Ports })
    $script:OtherPublishedPorts = @($dockerContainers | Where-Object { $_.Project -ne $candidateProject } | ForEach-Object { $_.Ports })
    $candidatePorts = $portOffsets.Values | ForEach-Object { $candidateBase + $_ }
    if (($candidatePorts | Where-Object { -not (Test-HostPortAvailable $_) }).Count -eq 0) {
        $selectedBase = $candidateBase
        break
    }
    if ($null -ne $existingBase) {
        throw "Existing project $candidateProject has a host-port conflict; refusing to create a duplicate stack."
    }
}

if ($null -eq $selectedBase) {
    throw "No free host-port block found after $Attempts attempts from port $BasePort."
}

$selectedProject = "$ProjectName-$selectedBase"
$publicArgs = @()
if (-not $NoPublicDemo) {
    $infraDir = (Resolve-Path (Join-Path $PSScriptRoot '..\infra')).Path
    $publicComposeFile = Join-Path $infraDir 'docker-compose.candidate.yml'
    foreach ($container in @($dockerContainers | Where-Object { $_.Project -eq 'sfudt-sh-navigation-candidate' })) {
        $configPaths = @($container.ConfigFiles -split ',' | ForEach-Object { $_.Replace('\', '/') })
        if ($configPaths -notcontains $publicComposeFile.Replace('\', '/')) {
            throw 'Existing public project belongs to a different Compose file.'
        }
    }
    $publicArgs = @('compose', '--project-directory', $infraDir, '--env-file',
        (Join-Path $infraDir 'wayfinding-public.env'), '-f',
        $publicComposeFile, '-f', (Join-Path $infraDir 'docker-compose.public-tls.yml'), '-p',
        'sfudt-sh-navigation-candidate', 'up', '-d', '--wait', 'demo', 'external')
}
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
$previousEnvironment['DTWIN_DEMO_BIND_ADDRESS'] = [Environment]::GetEnvironmentVariable('DTWIN_DEMO_BIND_ADDRESS', 'Process')
$previousEnvironment['DTWIN_DEMO_ALLOWED_HOST'] = [Environment]::GetEnvironmentVariable('DTWIN_DEMO_ALLOWED_HOST', 'Process')
[Environment]::SetEnvironmentVariable('DTWIN_DEMO_BIND_ADDRESS', $bindAddress, 'Process')
[Environment]::SetEnvironmentVariable('DTWIN_DEMO_ALLOWED_HOST', $machineName, 'Process')

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
    Write-Host ('{0,-28} {1}' -f 'DTWIN_DEMO_BIND_ADDRESS', $bindAddress)
    Write-Host ('{0,-28} {1}' -f 'Local demo URL', "http://127.0.0.1:$($selectedBase + 7)/")
    Write-Host ('{0,-28} {1}' -f 'LAN machine URL', "http://${machineName}:$($selectedBase + 7)/")
    if ($bindAddress -eq '127.0.0.1') {
        Write-Host 'LAN access is disabled by loopback rollback.'
    }
    else {
        Write-Warning 'Trusted LAN demo only. No authentication and no TLS. Restrict the port with the host firewall and stop the stack after use.'
    }

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
        if (-not $NoPublicDemo) {
            Write-Host "Dry run: docker $($publicArgs -join ' ')"
            Write-Host 'Public demo URL              https://sfuai.ca:8017/'
            Write-Host 'Private candidate URL        http://127.0.0.1:18107/'
        }
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

    if (-not $NoPublicDemo) {
        # Public port/artifact settings come from the checked-in env file.
        foreach ($publicKey in @('WAYFINDING_CANDIDATE_RUN', 'WAYFINDING_BROWSER_BUILD_IMAGE',
            'WAYFINDING_CANDIDATE_BIND_ADDRESS', 'WAYFINDING_CANDIDATE_PORT',
            'WAYFINDING_EXTERNAL_BIND_ADDRESS', 'WAYFINDING_EXTERNAL_PORT', 'WAYFINDING_TLS_CERT_DIR')) {
            $previousEnvironment[$publicKey] = [Environment]::GetEnvironmentVariable($publicKey, 'Process')
            # New .NET versions can retain an empty variable for a null value;
            # Compose treats that as an override of the checked-in env file.
            if (Test-Path "Env:$publicKey") { Remove-Item "Env:$publicKey" }
        }
        & docker @publicArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Public demo startup failed with exit code $LASTEXITCODE."
        }
        Write-Host 'Public demo URL              https://sfuai.ca:8017/'
        Write-Host 'Private candidate URL        http://127.0.0.1:18107/'
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
    foreach ($entry in $previousEnvironment.GetEnumerator()) {
        if ($null -eq $entry.Value) {
            if (Test-Path "Env:$($entry.Key)") { Remove-Item "Env:$($entry.Key)" }
        }
        else {
            [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, 'Process')
        }
    }
}

if ($gateExitCode -ne 0) {
    Write-Host "$failedGate gate failed with exit code $gateExitCode." -ForegroundColor Red
    exit $gateExitCode
}
