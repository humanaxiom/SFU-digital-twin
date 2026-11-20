[CmdletBinding()]
param()

# Thin Docker orchestration only. Fault injection and numeric assertions run in containers.
$ErrorActionPreference = 'Stop'
$infraDir = (Resolve-Path (Join-Path $PSScriptRoot '../infra')).Path
$project = 'sfudt-public-recovery-check'
$composeArgs = @('compose', '--project-directory', $infraDir, '--env-file',
    (Join-Path $infraDir 'wayfinding-public.env'), '-f',
    (Join-Path $infraDir 'docker-compose.candidate.yml'), '-f',
    (Join-Path $infraDir 'docker-compose.public-tls.yml'), '-f',
    (Join-Path $infraDir 'docker-compose.recovery.yml'), '-p', $project)
$savedEnvironment = @{}
$started = $false
$cleanupExit = 0
try {
    foreach ($key in @('WAYFINDING_CANDIDATE_RUN', 'WAYFINDING_BROWSER_BUILD_IMAGE',
        'WAYFINDING_CANDIDATE_BIND_ADDRESS', 'WAYFINDING_CANDIDATE_PORT',
        'WAYFINDING_EXTERNAL_BIND_ADDRESS', 'WAYFINDING_EXTERNAL_PORT', 'WAYFINDING_TLS_CERT_DIR')) {
        $savedEnvironment[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
        if (Test-Path "Env:$key") { Remove-Item "Env:$key" }
    }
    $existing = & docker ps -a --filter "label=com.docker.compose.project=$project" --format '{{.ID}}'
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect the isolated recovery project.' }
    if ($existing) { throw "Recovery project $project already exists; refusing to alter it." }
    & docker @composeArgs config
    if ($LASTEXITCODE -ne 0) { throw 'Recovery Compose configuration failed.' }
    $started = $true
    & docker @composeArgs up -d --wait demo external
    if ($LASTEXITCODE -ne 0) { throw 'Isolated recovery startup failed.' }
    $demoId = & docker @composeArgs ps -q demo
    if ($LASTEXITCODE -ne 0 -or -not $demoId) { throw 'Recovery demo container is missing.' }
    $externalId = & docker @composeArgs ps -q external
    if ($LASTEXITCODE -ne 0 -or -not $externalId) { throw 'Recovery proxy container is missing.' }
    & docker inspect --format 'before id={{.Id}} restart={{.RestartCount}} policy={{.HostConfig.RestartPolicy.Name}} ports={{json .HostConfig.PortBindings}}' $demoId $externalId
    if ($LASTEXITCODE -ne 0) { throw 'Initial recovery inspection failed.' }
    Start-Sleep -Seconds 12
    & docker exec $demoId sh /workspace/tests/gate/recovery-demo.sh fail
    if ($LASTEXITCODE -ne 0) { throw 'Isolated demo fault injection failed.' }
    Start-Sleep -Seconds 5
    & docker inspect --format 'after demo id={{.Id}} restart={{.RestartCount}} state={{.State.Status}}' $demoId
    if ($LASTEXITCODE -ne 0) { throw 'Demo recovery inspection failed.' }
    $demoRestarts = & docker inspect --format '{{.RestartCount}}' $demoId
    if ($LASTEXITCODE -ne 0) { throw 'Demo restart count is unavailable.' }
    & docker exec $demoId sh -c 'test "$1" -ge 1' recovery-check $demoRestarts
    if ($LASTEXITCODE -ne 0) { throw 'Demo did not restart automatically.' }
    & docker exec $externalId nginx -s quit
    if ($LASTEXITCODE -ne 0) { throw 'Isolated proxy fault injection failed.' }
    Start-Sleep -Seconds 5
    & docker inspect --format 'after external id={{.Id}} restart={{.RestartCount}} state={{.State.Status}}' $externalId
    if ($LASTEXITCODE -ne 0) { throw 'Proxy recovery inspection failed.' }
    $externalRestarts = & docker inspect --format '{{.RestartCount}}' $externalId
    if ($LASTEXITCODE -ne 0) { throw 'Proxy restart count is unavailable.' }
    & docker exec $externalId sh -c 'test "$1" -ge 1' recovery-check $externalRestarts
    if ($LASTEXITCODE -ne 0) { throw 'Proxy did not restart automatically.' }
    & docker @composeArgs up -d --wait demo external
    if ($LASTEXITCODE -ne 0) { throw 'Recovered services did not become healthy.' }
    & docker inspect --format 'final id={{.Id}} restart={{.RestartCount}} health={{.State.Health.Status}} ports={{json .HostConfig.PortBindings}}' $demoId $externalId
    if ($LASTEXITCODE -ne 0) { throw 'Final recovery inspection failed.' }
}
finally {
    if ($started) {
        & docker @composeArgs down --remove-orphans
        $cleanupExit = $LASTEXITCODE
    }
    foreach ($entry in $savedEnvironment.GetEnumerator()) {
        if ($null -eq $entry.Value) {
            if (Test-Path "Env:$($entry.Key)") { Remove-Item "Env:$($entry.Key)" }
        }
        else {
            [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, 'Process')
        }
    }
}
if ($cleanupExit -ne 0) { throw 'Isolated recovery cleanup failed.' }
