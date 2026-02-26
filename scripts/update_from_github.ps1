param(
    [string]$AppRoot = "",
    [string]$ConfigPath = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($AppRoot)) {
    $AppRoot = Split-Path -Parent $PSScriptRoot
}
 
# Normalize path input from .bat (remove quotes/control chars, trim trailing slash)
$AppRoot = "$AppRoot".Trim().Trim('"')
$AppRoot = [regex]::Replace($AppRoot, "[\x00-\x1F]", "")
$AppRoot = $AppRoot.TrimEnd("\", "/")

if (-not (Test-Path -LiteralPath $AppRoot)) {
    Write-Error "AppRoot does not exist: $AppRoot"
    exit 1
}

if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
    $ConfigPath = Join-Path $PSScriptRoot "github_update_config.json"
}

if (-not (Test-Path $ConfigPath)) {
    Write-Error "Missing config: $ConfigPath. Create it from github_update_config.json.example"
    exit 1
}

$cfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json
$owner = "$($cfg.owner)".Trim()
$repo = "$($cfg.repo)".Trim()
$branch = "$($cfg.branch)".Trim()

if ([string]::IsNullOrWhiteSpace($owner) -or [string]::IsNullOrWhiteSpace($repo) -or [string]::IsNullOrWhiteSpace($branch)) {
    Write-Error "Config must include owner/repo/branch"
    exit 1
}

$tmpDir = Join-Path $env:TEMP ("ai_parse_update_" + [Guid]::NewGuid().ToString("N"))
$zipPath = Join-Path $tmpDir "repo.zip"
$extractDir = Join-Path $tmpDir "extract"
New-Item -Path $tmpDir -ItemType Directory -Force | Out-Null
New-Item -Path $extractDir -ItemType Directory -Force | Out-Null

$publicZipUrl = "https://codeload.github.com/$owner/$repo/zip/refs/heads/$branch"
$privateZipUrl = "https://api.github.com/repos/$owner/$repo/zipball/$branch"
$token = $env:GITHUB_TOKEN

Write-Host "Downloading latest code from GitHub..."
try {
    if ([string]::IsNullOrWhiteSpace($token)) {
        Invoke-WebRequest -Uri $publicZipUrl -OutFile $zipPath -UseBasicParsing
    } else {
        $headers = @{
            "Authorization" = "Bearer $token"
            "Accept" = "application/vnd.github+json"
            "X-GitHub-Api-Version" = "2022-11-28"
        }
        Invoke-WebRequest -Uri $privateZipUrl -OutFile $zipPath -Headers $headers -UseBasicParsing
    }
} catch {
    Write-Error "Download failed: $($_.Exception.Message)"
    exit 1
}

Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force
$repoRoot = Get-ChildItem $extractDir -Directory | Select-Object -First 1
if (-not $repoRoot) {
    Write-Error "Extracted repository folder not found"
    exit 1
}

# Preserve local secrets and local runtime data
$backupDir = Join-Path $tmpDir "backup"
New-Item -Path $backupDir -ItemType Directory -Force | Out-Null

$preserveFiles = @(
    "config\config.json",
    "gateway_service\env",
    "scripts\github_update_config.json",
    "scripts\update_from_github.ps1",
    "update_from_github.bat"
)

foreach ($relPath in $preserveFiles) {
    $src = Join-Path $AppRoot $relPath
    if (Test-Path -LiteralPath $src) {
        $dst = Join-Path $backupDir $relPath
        New-Item -Path (Split-Path $dst -Parent) -ItemType Directory -Force | Out-Null
        Copy-Item -LiteralPath $src -Destination $dst -Force
    }
}

Write-Host "Applying update to: $AppRoot"
robocopy $repoRoot.FullName $AppRoot /E /NFL /NDL /NJH /NJS /NP | Out-Null

foreach ($relPath in $preserveFiles) {
    $bak = Join-Path $backupDir $relPath
    if (Test-Path -LiteralPath $bak) {
        $dst = Join-Path $AppRoot $relPath
        New-Item -Path (Split-Path $dst -Parent) -ItemType Directory -Force | Out-Null
        Copy-Item -LiteralPath $bak -Destination $dst -Force
    }
}

# Keep local runtime folders available
New-Item -Path (Join-Path $AppRoot "output") -ItemType Directory -Force | Out-Null
New-Item -Path (Join-Path $AppRoot "logs") -ItemType Directory -Force | Out-Null

Write-Host "Running preflight..."
python (Join-Path $AppRoot "preflight_check.py") --config (Join-Path $AppRoot "config\config.json") --output-dir (Join-Path $AppRoot "output") --log-dir (Join-Path $AppRoot "logs")
if ($LASTEXITCODE -ne 0) {
    Write-Error "Update completed but preflight failed. Please check config and dependencies."
    exit 1
}

Write-Host ""
Write-Host "[SUCCESS] Updated to latest GitHub branch: $branch"
Write-Host "You can now start app: start_gui.bat"

