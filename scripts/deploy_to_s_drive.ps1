param(
    [Parameter(Mandatory = $true)]
    [string]$Version,
    [string]$SourceRoot = "P:\work space\AI_parse",
    [string]$TargetRoot = "S:\Uploading Team"
)

$releaseDir = Join-Path $TargetRoot "releases\$Version"
$currentDir = Join-Path $TargetRoot "current"

Write-Host "Deploying version $Version"
Write-Host "Source: $SourceRoot"
Write-Host "Release: $releaseDir"

New-Item -Path $releaseDir -ItemType Directory -Force | Out-Null
New-Item -Path (Join-Path $TargetRoot "logs") -ItemType Directory -Force | Out-Null
New-Item -Path (Join-Path $TargetRoot "output") -ItemType Directory -Force | Out-Null

$include = @(
    "config",
    "documents",
    "gateway_service",
    "scripts",
    "utils",
    "gui_app_simple.py",
    "main.py",
    "preflight_check.py",
    "requirements.txt",
    "start_gui.bat",
    "start.bat",
    "run.bat",
    "version.py",
    "README.md",
    "USAGE.md",
    "DEPLOY_S_DRIVE.md",
    "UAT_CHECKLIST.md"
)

foreach ($item in $include) {
    $src = Join-Path $SourceRoot $item
    if (Test-Path $src) {
        if ((Get-Item $src) -is [System.IO.DirectoryInfo]) {
            robocopy $src (Join-Path $releaseDir $item) /E /NFL /NDL /NJH /NJS /NP | Out-Null
        } else {
            New-Item -Path (Split-Path (Join-Path $releaseDir $item)) -ItemType Directory -Force | Out-Null
            Copy-Item $src (Join-Path $releaseDir $item) -Force
        }
    }
}

if (Test-Path $currentDir) {
    Remove-Item $currentDir -Recurse -Force
}

$linked = $false
try {
    New-Item -Path $currentDir -ItemType Junction -Value $releaseDir -ErrorAction Stop | Out-Null
    $linked = $true
} catch {
    Write-Warning "Cannot create junction (insufficient privilege). Falling back to directory sync."
    New-Item -Path $currentDir -ItemType Directory -Force | Out-Null
    robocopy $releaseDir $currentDir /E /NFL /NDL /NJH /NJS /NP | Out-Null
}

Write-Host "Deployment completed."
if ($linked) {
    Write-Host "Current points to: $releaseDir"
} else {
    Write-Host "Current synced from: $releaseDir"
}
