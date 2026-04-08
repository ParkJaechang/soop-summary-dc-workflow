param(
    [string]$TaskName = "SOOP-LiveVOD-Scheduler",
    [string]$RuntimeDir = "",
    [string]$DbPath = "",
    [double]$TimeoutSeconds = 10
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "live_vod_scheduler_task_common.ps1")

$paths = Resolve-LiveVodSchedulerTaskPaths -RuntimeDir $RuntimeDir -DbPath $DbPath
$stopOutput = & (Join-Path $PSScriptRoot "stop_live_vod_scheduler.bat") --runtime-dir $paths.RuntimeDir --timeout $TimeoutSeconds 2>&1
$stopText = ($stopOutput | Out-String).Trim()
if (-not $stopText) {
    throw "Task stop wrapper did not receive stop output."
}

$stopPayload = $stopText | ConvertFrom-Json
[PSCustomObject]@{
    task = Get-LiveVodSchedulerTaskInfoPayload -TaskName $TaskName
    stop = $stopPayload
    runtime_dir = $paths.RuntimeDir
    db_path = $paths.DbPath
} | ConvertTo-Json -Depth 8
