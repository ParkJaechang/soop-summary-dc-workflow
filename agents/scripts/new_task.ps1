param(
    [Parameter(Mandatory = $true)]
    [string]$TaskId,

    [Parameter(Mandatory = $true)]
    [string]$Title,

    [string]$Owner = "coordinator"
)

$root = Split-Path -Parent $PSScriptRoot
$templateDir = Join-Path $root "tasks\\_template"
$slug = ($Title.ToLower() -replace "[^a-z0-9]+", "-").Trim("-")
$taskFolderName = "$TaskId-$slug"
$taskDir = Join-Path $root "tasks\\$taskFolderName"

if (Test-Path $taskDir) {
    Write-Error "Task folder already exists: $taskDir"
    exit 1
}

New-Item -ItemType Directory -Path $taskDir | Out-Null

$replacements = @{
    "TASK-XXX" = $TaskId
    "TASK_TITLE" = $Title
    "OWNER_ROLE" = $Owner
    "DATE_YYYY-MM-DD" = (Get-Date -Format "yyyy-MM-dd")
}

Get-ChildItem -File $templateDir | ForEach-Object {
    $content = Get-Content $_.FullName -Raw
    foreach ($key in $replacements.Keys) {
        $content = $content.Replace($key, $replacements[$key])
    }
    Set-Content -Path (Join-Path $taskDir $_.Name) -Value $content -Encoding UTF8
}

Write-Host "Created task folder: agents/tasks/$taskFolderName"
Write-Host "Next steps:"
Write-Host "1. Add the task entry to agents/board/tasks.yaml"
Write-Host "2. Update the new spec.md and status.yaml"
Write-Host "3. Create an artifacts folder if needed under agents/artifacts/$taskFolderName"
