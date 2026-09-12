# Extracts coded-value domains from a File Geodatabase's GDB_Items table (a00000004.gdbtable).
# Domain definitions are stored as embedded XML and are not exposed by `ogrinfo` on older GDAL builds.
[CmdletBinding()]
param(
    [string]$Gdb = 'C:\repos\sfudt\claude\dtwin-harness\data\IndoorWayfinding.gdb',
    [string]$OutFile = (Join-Path $PSScriptRoot '..\docs\generated\gdb-domains.txt')
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath '/.dockerenv')) {
    throw 'Docker-only execution: this legacy parser must run in a PowerShell container. Use tools/run_profile.ps1 for the supported Docker/GDAL profile.'
}

$outDir = Split-Path -Parent $OutFile
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }

$text = [Text.Encoding]::UTF8.GetString([IO.File]::ReadAllBytes((Join-Path $Gdb 'a00000004.gdbtable')))

$lines = New-Object System.Collections.Generic.List[string]

foreach ($m in [regex]::Matches($text, '<GPCodedValueDomain2[^>]*>(.*?)</GPCodedValueDomain2>', 'Singleline')) {
    $body = $m.Groups[1].Value
    $name = [regex]::Match($body, '<DomainName>([^<]*)</DomainName>').Groups[1].Value
    $desc = [regex]::Match($body, '<Description>([^<]*)</Description>').Groups[1].Value
    $lines.Add("=== $name === $desc")
    foreach ($cv in [regex]::Matches($body, '<CodedValue[^>]*><Name>([^<]*)</Name><Code[^>]*>([^<]*)</Code>')) {
        $lines.Add(('    {0,-6} {1}' -f $cv.Groups[2].Value, $cv.Groups[1].Value))
    }
    $lines.Add('')
}

if ($lines.Count -eq 0) { $lines.Add('No coded-value domains found.') }

$lines | Out-File -FilePath $OutFile -Encoding utf8
Write-Host "Wrote $OutFile ($($lines.Count) lines)"
