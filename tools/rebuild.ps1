[CmdletBinding()]
param(
    [ValidateSet("Build", "Review", "Compare")]
    [string]$Action = "Build",
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")]
    [string]$RunId,
    [ValidatePattern("^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")]
    [string]$OtherRunId,
    [ValidateSet("endpoint-v1", "exact-shared-vertices-v1")]
    [string]$Topology = "endpoint-v1",
    [switch]$LocalImage
)

$ErrorActionPreference = "Stop"
$composeFile = Join-Path (Split-Path -Parent $PSScriptRoot) "infra/docker-compose.rebuild.yml"
$project = "sfudt-rebuild-$($RunId.ToLowerInvariant())"

if ($Action -eq "Compare" -and [string]::IsNullOrWhiteSpace($OtherRunId)) {
    throw "-OtherRunId is required for -Action Compare."
}
if ($Action -ne "Compare" -and -not [string]::IsNullOrWhiteSpace($OtherRunId)) {
    throw "-OtherRunId is valid only for -Action Compare."
}
if ($Action -eq "Compare" -and $OtherRunId -eq $RunId) {
    throw "-OtherRunId must differ from -RunId."
}
if ($PSBoundParameters.ContainsKey("Topology") -and $Action -ne "Build") {
    throw "-Topology is valid only for -Action Build."
}

$imageReference = if ($LocalImage) { "wayfinding-build:local" } else {
    "ghcr.io/humanaxiom/sfu-digital-twin/wayfinding-build@sha256:26259879732ceffe8405f22d19c423bf14408583e1a752da35a61d3e2825276c"
}
$oldImageId = $env:WAYFINDING_BUILD_IMAGE_ID
$oldImageReference = $env:WAYFINDING_BUILD_IMAGE_REFERENCE
$oldRebuildImage = $env:WAYFINDING_REBUILD_IMAGE

try {
    $inspectedId = (& docker image inspect $imageReference --format '{{.Id}}')
    if ($LASTEXITCODE -ne 0) {
        if ($LocalImage) {
            throw "Could not inspect local image '$imageReference'; see the Docker diagnostic above. If it is missing, build it with: docker build -f infra/Dockerfile.build -t wayfinding-build:local ."
        }
        throw "Could not inspect published image '$imageReference'; see the Docker diagnostic above. To use an existing local development image, re-run with -LocalImage. If wayfinding-build:local is also missing, build it from the repository root with: docker build -f infra/Dockerfile.build -t wayfinding-build:local ."
    }
    if ($inspectedId -notmatch '^sha256:[0-9a-fA-F]{64}$') {
        throw "Selected image '$imageReference' returned an invalid immutable ID; expected sha256 followed by 64 hexadecimal characters. Check the Docker image inspect output."
    }
    $env:WAYFINDING_REBUILD_IMAGE = $inspectedId.Trim()
    $env:WAYFINDING_BUILD_IMAGE_ID = $inspectedId.Trim()
    $env:WAYFINDING_BUILD_IMAGE_REFERENCE = $imageReference

    function Invoke-RebuildContainer {
        param([string]$Service, [string[]]$Command)
        & docker compose -p $project -f $composeFile run --rm --no-deps -T $Service @Command
        if ($LASTEXITCODE -ne 0) { throw "Container command failed ($LASTEXITCODE): $Service $($Command -join ' ')" }
    }

    switch ($Action) {
        "Build" {
            $extractCommand = @("python", "-m", "wayfinding.etl.rebuild", "extract", "--run-id", $RunId)
            if ($Topology -ne "endpoint-v1") { $extractCommand += @("--topology", $Topology) }
            Invoke-RebuildContainer "source-build" $extractCommand
            Invoke-RebuildContainer "artifact-build" @("python", "-m", "wayfinding.etl.rebuild", "derive", "--run-id", $RunId)
            Invoke-RebuildContainer "source-build" @("python", "-m", "wayfinding.etl.rebuild", "finalize", "--run-id", $RunId)
        }
        "Review" {
            Invoke-RebuildContainer "source-review" @("python", "-m", "wayfinding.etl.source_review", "--legacy", "/sources/IndoorWayfinding.gdb", "--revised", "/sources/IndoorWayfinding_AQ_SH_ECC_Revised.gdb", "--supplemental", "/sources/AdditionalData_Testing.gdb", "--output", "/workspace/build/experiments/reviews/$RunId.json")
        }
        "Compare" {
            Invoke-RebuildContainer "artifact-build" @("python", "-m", "wayfinding.etl.rebuild", "compare", "--left", $RunId, "--right", $OtherRunId)
        }
    }
}
finally {
    $env:WAYFINDING_BUILD_IMAGE_ID = $oldImageId
    $env:WAYFINDING_BUILD_IMAGE_REFERENCE = $oldImageReference
    $env:WAYFINDING_REBUILD_IMAGE = $oldRebuildImage
}
