<#
.SYNOPSIS
    PostToolUse hook: fail loudly if a write/edit touched the read-only source geodatabase
    or the sibling dtwin-harness reference repo (docs/03-harness-design.md, Prime Directive 1).

.DESCRIPTION
    Reads the hook payload from stdin (VS Code hooks contract: JSON on stdin, optional JSON on
    stdout). Blocks only when the tool call's target path resolves under one of the two protected
    roots. This does not replace human judgement, it is a deterministic backstop for the case an
    agent (or a careless human) tries to "just quickly fix" the source data.
#>

$ErrorActionPreference = 'Stop'

$protectedRoots = @(
    'C:\repos\sfudt\claude\dtwin-harness\data\IndoorWayfinding.gdb',
    'C:\repos\sfudt\claude\dtwin-harness'
)

$payload = [Console]::In.ReadToEnd()
if ([string]::IsNullOrWhiteSpace($payload)) {
    exit 0
}

try {
    $event = $payload | ConvertFrom-Json
} catch {
    # Non-JSON or empty payload: nothing to check, do not block.
    exit 0
}

$targetPath = $event.tool_input.filePath ?? $event.tool_input.path ?? $event.tool_input.file_path
if (-not $targetPath) {
    exit 0
}

$resolvedTarget = try { (Resolve-Path -LiteralPath $targetPath -ErrorAction Stop).Path } catch { $targetPath }

foreach ($root in $protectedRoots) {
    if ($resolvedTarget -like "$root*") {
        $output = @{
            decision = 'block'
            reason   = "Blocked: '$resolvedTarget' is under the read-only boundary ($root). " +
                       "The source geodatabase and the sibling dtwin-harness repo are never modified " +
                       "by this harness (see .github/copilot-instructions.md Prime Directive 1)."
        } | ConvertTo-Json -Compress
        Write-Output $output
        exit 2
    }
}

exit 0
