# Repository-root entrypoint; all Docker startup behavior lives in tools.
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'tools/launch-stack.ps1') @args
exit $LASTEXITCODE
