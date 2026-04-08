param(
    [string]$RuntimeDir = "",
    [string]$DbPath = "",
    [int]$Port = 8877,
    [double]$HealthTimeout = 20
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "live_vod_scheduler_task_common.ps1")

$paths = Resolve-LiveVodSchedulerTaskPaths -RuntimeDir $RuntimeDir -DbPath $DbPath
Set-Location $PSScriptRoot

$arguments = @(
    "--runtime-dir", $paths.RuntimeDir,
    "--db-path", $paths.DbPath,
    "--port", $Port.ToString(),
    "--wait-health",
    "--health-timeout", $HealthTimeout.ToString([System.Globalization.CultureInfo]::InvariantCulture)
)

& (Join-Path $PSScriptRoot "start_live_vod_scheduler.bat") @arguments
exit $LASTEXITCODE
