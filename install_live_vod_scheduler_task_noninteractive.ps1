param(
    [string]$TaskName = "SOOP-LiveVOD-Scheduler-NonInteractive",
    [string]$TaskUser = "",
    [string]$RuntimeDir = "",
    [string]$DbPath = "",
    [int]$Port = 8877,
    [double]$HealthTimeout = 20,
    [string]$TaskXmlPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "live_vod_scheduler_task_common.ps1")

$paths = Resolve-LiveVodSchedulerTaskPaths -RuntimeDir $RuntimeDir -DbPath $DbPath
New-Item -ItemType Directory -Path $paths.RuntimeDir -Force | Out-Null
New-Item -ItemType Directory -Path (Split-Path -Parent $paths.DbPath) -Force | Out-Null

$resolvedTaskUser = if ($TaskUser) { $TaskUser } else { Get-LiveVodSchedulerTaskUserId }
$actionArgs = Get-LiveVodSchedulerTaskActionArguments -RuntimeDir $paths.RuntimeDir -DbPath $paths.DbPath -Port $Port -HealthTimeout $HealthTimeout
$taskCommand = "powershell.exe $actionArgs"
$resolvedTaskXmlPath = if ($TaskXmlPath) { [System.IO.Path]::GetFullPath($TaskXmlPath) } else { Join-Path $paths.RuntimeDir "task_scheduler_noninteractive.xml" }
$taskXmlDir = Split-Path -Parent $resolvedTaskXmlPath
if (-not (Test-Path $taskXmlDir)) {
    New-Item -ItemType Directory -Path $taskXmlDir -Force | Out-Null
}

$xml = Get-LiveVodSchedulerTaskS4UXml -TaskName $TaskName -TaskUser $resolvedTaskUser -TaskCommand $taskCommand
Set-Content -Path $resolvedTaskXmlPath -Value $xml -Encoding Unicode

$manifest = @{
    task_name = $TaskName
    task_user = $resolvedTaskUser
    runtime_dir = $paths.RuntimeDir
    db_path = $paths.DbPath
    port = $Port
    health_timeout = $HealthTimeout
    scheduler_type = "windows_task_scheduler"
    registration_mode = "xml_s4u_current_user_noninteractive"
    task_xml_path = $resolvedTaskXmlPath
    action = @{
        execute = "powershell.exe"
        arguments = $actionArgs
        command_line = $taskCommand
        working_directory = $PSScriptRoot
    }
    registered_at = (Get-Date).ToString("o")
    stop_contract = @{
        command = (Join-Path $PSScriptRoot "stop_live_vod_scheduler_task.ps1")
        notes = "Use the task stop wrapper so the repo-owned launcher writes stop_requested.json and the host wrapper exits cleanly."
    }
    deployment_notes = @(
        "This path targets a non-interactive S4U-style Task Scheduler registration.",
        "Local proof may require permission to register S4U tasks or a deployment context with explicit supervisor credentials."
    )
}
Write-LiveVodSchedulerTaskManifest -ManifestPath $paths.ManifestPath -Payload $manifest

$createResult = Invoke-LiveVodSchtasks -Arguments @("/create", "/tn", $TaskName, "/xml", $resolvedTaskXmlPath, "/f")
$taskInfo = Get-LiveVodSchedulerTaskInfoPayload -TaskName $TaskName
$payload = [ordered]@{
    status = if ($createResult.ExitCode -eq 0) { "registered" } else { "registration_failed" }
    manifest_path = $paths.ManifestPath
    task_xml_path = $resolvedTaskXmlPath
    create_exit_code = $createResult.ExitCode
    create_result = $createResult.Output
    task = $taskInfo
    registration = $manifest
}

$json = $payload | ConvertTo-Json -Depth 8
if ($createResult.ExitCode -ne 0) {
    Write-Output $json
    exit 1
}

Write-Output $json
