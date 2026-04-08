param(
    [string]$TaskName = "SOOP-LiveVOD-Scheduler",
    [string]$RuntimeDir = "",
    [string]$DbPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "live_vod_scheduler_task_common.ps1")

$paths = Resolve-LiveVodSchedulerTaskPaths -RuntimeDir $RuntimeDir -DbPath $DbPath
$taskInfo = Get-LiveVodSchedulerTaskInfoPayload -TaskName $TaskName
$statusOutput = & (Join-Path $PSScriptRoot "status_live_vod_scheduler.bat") --runtime-dir $paths.RuntimeDir 2>&1
$statusText = ($statusOutput | Out-String).Trim()
$launcherStatus = $null
if ($statusText) {
    try {
        $launcherStatus = $statusText | ConvertFrom-Json
    } catch {
        $launcherStatus = @{
            parse_error = $_.Exception.Message
            raw = $statusText
        }
    }
}

[PSCustomObject]@{
    task = $taskInfo
    launcher = $launcherStatus
    launcher_exit_code = $LASTEXITCODE
    runtime_dir = $paths.RuntimeDir
    db_path = $paths.DbPath
} | ConvertTo-Json -Depth 8
