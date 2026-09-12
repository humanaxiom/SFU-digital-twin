<#
.SYNOPSIS
    Compatibility launcher for the Docker-only PostToolUse diagnostic.
.DESCRIPTION
    Forwards stdin without inspecting it. Python runs in the artifact capability,
    which has no source mount. Docker/image errors are returned without a host fallback.
    This post-action diagnostic cannot prevent or undo writes.
#>
$ErrorActionPreference = 'Stop'
[Console]::In.ReadToEnd() | docker compose -f infra/docker-compose.yml run --rm --no-deps -T artifact python tools/hooks/check_read_only_boundary.py
exit $LASTEXITCODE
