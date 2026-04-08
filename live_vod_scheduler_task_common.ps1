Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:RepoRoot = $PSScriptRoot

function Get-LiveVodSchedulerTaskDefaultRuntimeDir {
    return (Join-Path $PSScriptRoot "data\live_vod_task_scheduler_runtime")
}

function Get-LiveVodSchedulerTaskDefaultDbPath {
    return (Join-Path $PSScriptRoot "data\live_vod_task_scheduler.db")
}

function Get-LiveVodSchedulerTaskUserId {
    if ($env:USERDOMAIN) {
        return "$($env:USERDOMAIN)\$($env:USERNAME)"
    }
    return $env:USERNAME
}

function Resolve-LiveVodSchedulerTaskPaths {
    param(
        [string]$RuntimeDir,
        [string]$DbPath
    )

    $resolvedRuntimeDir = if ($RuntimeDir) {
        [System.IO.Path]::GetFullPath($RuntimeDir)
    } else {
        [System.IO.Path]::GetFullPath((Get-LiveVodSchedulerTaskDefaultRuntimeDir))
    }
    $resolvedDbPath = if ($DbPath) {
        [System.IO.Path]::GetFullPath($DbPath)
    } else {
        [System.IO.Path]::GetFullPath((Get-LiveVodSchedulerTaskDefaultDbPath))
    }

    return [PSCustomObject]@{
        RuntimeDir = $resolvedRuntimeDir
        DbPath = $resolvedDbPath
        ManifestPath = (Join-Path $resolvedRuntimeDir "task_scheduler_registration.json")
    }
}

function Get-LiveVodSchedulerTaskActionArguments {
    param(
        [string]$RuntimeDir,
        [string]$DbPath,
        [int]$Port,
        [double]$HealthTimeout
    )

    $actionScript = Join-Path $PSScriptRoot "live_vod_scheduler_task_action.ps1"
    return "-NoProfile -ExecutionPolicy Bypass -File `"$actionScript`" -RuntimeDir `"$RuntimeDir`" -DbPath `"$DbPath`" -Port $Port -HealthTimeout $HealthTimeout"
}

function ConvertTo-LiveVodTaskXmlEscapedText {
    param(
        [string]$Value
    )

    return [System.Security.SecurityElement]::Escape($Value)
}

function Get-LiveVodSchedulerTaskS4UXml {
    param(
        [string]$TaskName,
        [string]$TaskUser,
        [string]$TaskCommand
    )

    $escapedUser = ConvertTo-LiveVodTaskXmlEscapedText -Value $TaskUser
    $escapedCommand = ConvertTo-LiveVodTaskXmlEscapedText -Value "powershell.exe"
    $escapedArguments = ConvertTo-LiveVodTaskXmlEscapedText -Value ($TaskCommand -replace "^powershell\.exe\s+", "")
    $escapedAuthor = ConvertTo-LiveVodTaskXmlEscapedText -Value $TaskUser
    $escapedUri = ConvertTo-LiveVodTaskXmlEscapedText -Value ("\{0}" -f $TaskName)

    return @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Author>$escapedAuthor</Author>
    <URI>$escapedUri</URI>
  </RegistrationInfo>
  <Principals>
    <Principal id="Author">
      <UserId>$escapedUser</UserId>
      <LogonType>S4U</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>false</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
  </Settings>
  <Triggers>
    <TimeTrigger>
      <StartBoundary>2099-01-01T00:00:00</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Actions Context="Author">
    <Exec>
      <Command>$escapedCommand</Command>
      <Arguments>$escapedArguments</Arguments>
    </Exec>
  </Actions>
</Task>
"@
}

function Invoke-LiveVodSchtasks {
    param(
        [string[]]$Arguments
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & schtasks.exe @Arguments 2>&1
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    $text = ($output | Out-String).Trim()
    return [PSCustomObject]@{
        ExitCode = $LASTEXITCODE
        Output = $text
        Arguments = $Arguments
    }
}

function Write-LiveVodSchedulerTaskManifest {
    param(
        [string]$ManifestPath,
        [hashtable]$Payload
    )

    $manifestDir = Split-Path -Parent $ManifestPath
    if (-not (Test-Path $manifestDir)) {
        New-Item -ItemType Directory -Path $manifestDir -Force | Out-Null
    }

    $Payload | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 -Path $ManifestPath
}

function Get-LiveVodSchedulerTaskInfoPayload {
    param(
        [string]$TaskName
    )

    $query = Invoke-LiveVodSchtasks -Arguments @("/query", "/tn", $TaskName, "/fo", "list", "/v")
    if ($query.ExitCode -ne 0) {
        return $null
    }

    $fields = @{}
    foreach ($line in ($query.Output -split "`r?`n")) {
        if ($line -match "^\s*([^:]+):\s*(.*)$") {
            $fields[$matches[1].Trim()] = $matches[2].Trim()
        }
    }

    return [PSCustomObject]@{
        TaskName = $TaskName
        State = $fields["Status"]
        LastTaskResult = $fields["Last Result"]
        Author = $fields["Author"]
        RunAsUser = $fields["Run As User"]
        ScheduleType = $fields["Schedule Type"]
        TaskToRun = $fields["Task To Run"]
        LogonMode = $fields["Logon Mode"]
        ScheduledTaskState = $fields["Scheduled Task State"]
    }
}
