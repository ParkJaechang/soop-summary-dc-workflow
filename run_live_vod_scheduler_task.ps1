param(
    [string]$TaskName = "SOOP-LiveVOD-Scheduler",
    [string]$RuntimeDir = "",
    [string]$DbPath = "",
    [int]$Port = 8877,
    [int]$TimeoutSeconds = 20
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "live_vod_scheduler_task_common.ps1")

$paths = Resolve-LiveVodSchedulerTaskPaths -RuntimeDir $RuntimeDir -DbPath $DbPath
$runResult = Invoke-LiveVodSchtasks -Arguments @("/run", "/tn", $TaskName)
if ($runResult.ExitCode -ne 0) {
    throw $runResult.Output
}

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$launcherStatus = $null
do {
    Start-Sleep -Milliseconds 300
    $statusOutput = & (Join-Path $PSScriptRoot "status_live_vod_scheduler.bat") --runtime-dir $paths.RuntimeDir 2>&1
    $statusText = ($statusOutput | Out-String).Trim()
    if ($LASTEXITCODE -eq 0 -and $statusText) {
        $launcherStatus = $statusText | ConvertFrom-Json
        break
    }
} while ((Get-Date) -lt $deadline)

if (-not $launcherStatus) {
    throw "Scheduled task did not produce a running launcher state before timeout."
}

[PSCustomObject]@{
    status = "started"
    run_result = $runResult.Output
    task = Get-LiveVodSchedulerTaskInfoPayload -TaskName $TaskName
    launcher_status = $launcherStatus
} | ConvertTo-Json -Depth 8
