param(
    [string]$TaskName = "SOOP-LiveVOD-Scheduler"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "live_vod_scheduler_task_common.ps1")

$task = Get-LiveVodSchedulerTaskInfoPayload -TaskName $TaskName
if ($task) {
    $deleteResult = Invoke-LiveVodSchtasks -Arguments @("/delete", "/tn", $TaskName, "/f")
    if ($deleteResult.ExitCode -ne 0) {
        throw $deleteResult.Output
    }
    [PSCustomObject]@{
        status = "removed"
        task_name = $TaskName
        delete_result = $deleteResult.Output
    } | ConvertTo-Json -Depth 4
    exit 0
}

[PSCustomObject]@{
    status = "not_found"
    task_name = $TaskName
} | ConvertTo-Json -Depth 4
