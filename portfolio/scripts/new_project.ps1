param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectSlug,

    [string]$ProjectsRoot = "C:\python\projects"
)

$templateRoot = "C:\python\portfolio\templates\project_template"
$targetRoot = Join-Path $ProjectsRoot $ProjectSlug

if (Test-Path $targetRoot) {
    Write-Error "Project already exists: $targetRoot"
    exit 1
}

New-Item -ItemType Directory -Force $ProjectsRoot | Out-Null
Copy-Item -Path $templateRoot -Destination $targetRoot -Recurse

Write-Host "Created project scaffold: $targetRoot"
Write-Host "Next steps:"
Write-Host "1. Edit $targetRoot\\agents\\shared\\project_brief.md"
Write-Host "2. Edit $targetRoot\\agents\\board\\ownership.md"
Write-Host "3. Register the new project in C:\\python\\portfolio\\projects.yaml"
Write-Host "4. Open the new project's coordinator chat and begin from its local agents folder"
