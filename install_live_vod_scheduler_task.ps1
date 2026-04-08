param(
    [string]$TaskName = "SOOP-LiveVOD-Scheduler",
    [string]$RuntimeDir = "",
    [string]$DbPath = "",
    [int]$Port = 8877,
    [double]$HealthTimeout = 20
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "live_vod_scheduler_task_common.ps1")

$paths = Resolve-LiveVodSchedulerTaskPaths -RuntimeDir $RuntimeDir -DbPath $DbPath
New-Item -ItemType Directory -Path $paths.RuntimeDir -Force | Out-Null
New-Item -ItemType Directory -Path (Split-Path -Parent $paths.DbPath) -Force | Out-Null

$taskUser = Get-LiveVodSchedulerTaskUserId
$actionArgs = Get-LiveVodSchedulerTaskActionArguments -RuntimeDir $paths.RuntimeDir -DbPath $paths.DbPath -Port $Port -HealthTimeout $HealthTimeout
$taskCommand = "powershell.exe $actionArgs"
$description = "Repo-owned live/VOD scheduler launcher packaged for Windows Task Scheduler."

$createResult = Invoke-LiveVodSchtasks -Arguments @("/create", "/tn", $TaskName, "/sc", "ONCE", "/sd", "2099/01/01", "/st", "00:00", "/f", "/rl", "LIMITED", "/tr", $taskCommand)
if ($createResult.ExitCode -ne 0) {
    throw $createResult.Output
}
$info = Get-LiveVodSchedulerTaskInfoPayload -TaskName $TaskName
$manifest = @{
    task_name = $TaskName
    runtime_dir = $paths.RuntimeDir
    db_path = $paths.DbPath
    port = $Port
    health_timeout = $HealthTimeout
    task_user = $taskUser
    action = @{
        execute = "powershell.exe"
        arguments = $actionArgs
        command_line = $taskCommand
        working_directory = $PSScriptRoot
    }
    registered_at = (Get-Date).ToString("o")
    scheduler_type = "windows_task_scheduler"
    registration_mode = "schtasks_once_on_demand_current_user"
    stop_contract = @{
        command = (Join-Path $PSScriptRoot "stop_live_vod_scheduler_task.ps1")
        notes = "Use the task stop wrapper so the repo-owned launcher writes stop_requested.json and the host wrapper exits cleanly."
    }
}
Write-LiveVodSchedulerTaskManifest -ManifestPath $paths.ManifestPath -Payload $manifest

[PSCustomObject]@{
    status = "registered"
    manifest_path = $paths.ManifestPath
    create_result = $createResult.Output
    task = $info
    registration = $manifest
} | ConvertTo-Json -Depth 8
