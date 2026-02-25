param(
    [Parameter(Mandatory = $true)]
    [string]$Version,
    [string]$TargetRoot = "S:\Uploading Team"
)

$releaseDir = Join-Path $TargetRoot "releases\$Version"
$currentDir = Join-Path $TargetRoot "current"

if (-not (Test-Path $releaseDir)) {
    Write-Error "Release not found: $releaseDir"
    exit 1
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

if ($linked) {
    Write-Host "Current release switched to: $releaseDir"
} else {
    Write-Host "Current release synced from: $releaseDir"
}
