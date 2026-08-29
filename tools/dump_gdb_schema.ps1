# Extracts feature-class schemas from a File Geodatabase's GDB_Items table (a00000004.gdbtable)
# without requiring ArcGIS or a GDAL install. Reads the embedded DataElement XML definitions.
[CmdletBinding()]
param(
    [string]$Gdb = 'C:\repos\sfudt\claude\dtwin-harness\data\IndoorWayfinding.gdb',
    [string]$OutFile = (Join-Path $PSScriptRoot '..\docs\generated\gdb-schema.txt')
)

$ErrorActionPreference = 'Stop'

$outDir = Split-Path -Parent $OutFile
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }

$text = [Text.Encoding]::UTF8.GetString([IO.File]::ReadAllBytes((Join-Path $Gdb 'a00000004.gdbtable')))

$lines = New-Object System.Collections.Generic.List[string]

foreach ($m in [regex]::Matches($text, '<CatalogPath>\\([^<]+)</CatalogPath>')) {
    $path = $m.Groups[1].Value
    $start = $m.Index
    # Bound each chunk at the next item so field lists don't bleed into neighbouring definitions.
    $next = $text.IndexOf('<CatalogPath>', $start + 1)
    if ($next -lt 0) { $next = $text.Length }
    $chunk = $text.Substring($start, $next - $start)

    $shape = [regex]::Match($chunk, '<ShapeType>(esriGeometry\w+)</ShapeType>').Groups[1].Value
    $wkid = [regex]::Match($chunk, '<WKID>(\d+)</WKID>').Groups[1].Value
    $hasZ = [regex]::Match($chunk, '<HasZ>(\w+)</HasZ>').Groups[1].Value

    $lines.Add(('=== {0}  [{1}]  wkid={2} hasZ={3}' -f $path, $shape, $wkid, $hasZ))

    foreach ($f in [regex]::Matches($chunk, '<Name>([^<]*)</Name>(?:<AliasName>[^<]*</AliasName>)?<FieldType>(esriFieldType\w+)</FieldType>')) {
        $name = $f.Groups[1].Value
        $type = $f.Groups[2].Value -replace 'esriFieldType', ''
        $tail = $chunk.Substring($f.Index, [Math]::Min(600, $chunk.Length - $f.Index))
        $domain = [regex]::Match($tail, '<DomainName>([^<]*)</DomainName>').Groups[1].Value
        $suffix = if ($domain) { " domain=$domain" } else { '' }
        $lines.Add(('    {0,-24} {1}{2}' -f $name, $type, $suffix))
    }
    $lines.Add('')
}

$lines | Out-File -FilePath $OutFile -Encoding utf8
Write-Host "Wrote $OutFile ($($lines.Count) lines)"
