# Runs the GDAL/OGR profiling script inside a container against the source geodatabase
# and writes the report to docs/generated/. Requires Docker Desktop.
[CmdletBinding()]
param(
    [string]$DataDir = (Join-Path $PSScriptRoot '..\data'),
    [string]$Image = 'ghcr.io/osgeo/gdal:alpine-small-latest',
    [string]$OutFile = (Join-Path $PSScriptRoot '..\docs\generated\gdb-profile.txt')
)

$ErrorActionPreference = 'Stop'

$outDir = Split-Path -Parent $OutFile
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }

docker run --rm `
    -v "${DataDir}:/data:ro" `
    -v "${PSScriptRoot}:/tools:ro" `
    $Image sh /tools/profile_gdb.sh 2>&1 |
    Out-File -FilePath $OutFile -Encoding utf8

Write-Host "Wrote $OutFile"
