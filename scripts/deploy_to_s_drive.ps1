param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^v?\d+\.\d+\.\d+$")]
    [string]$Version,
    [string]$SourceRoot = "P:\work space\AI_parse",
    [string]$TargetRoot = "S:\Uploading Team\AI-parse",
    [string]$Operator = $env:USERNAME,
    [string]$Notes = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Import-Module (Join-Path $scriptRoot "release_manifest.psm1") -Force

$logsDir = Join-Path $TargetRoot "logs"
$releaseDir = Join-Path $TargetRoot "releases\$Version"
$currentDir = Join-Path $TargetRoot "current"
$backupCurrentDir = Join-Path $TargetRoot ("current_backup_deploy_{0}" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
$opsLogPath = Join-Path $logsDir "release_ops.log"
$fromVersion = ""
$rootInstallerPath = Join-Path $TargetRoot "install_client.bat"
$releaseDirCreated = $false

function Write-ReleaseOpsLog {
    param(
        [string]$Action,
        [string]$FromVersion,
        [string]$ToVersion,
        [bool]$Success,
        [string]$Message
    )

    $logObj = [ordered]@{
        timestamp   = (Get-Date).ToString("o")
        action      = $Action
        fromVersion = $FromVersion
        toVersion   = $ToVersion
        operator    = $Operator
        success     = $Success
        message     = $Message
    }
    Add-Content -Path $opsLogPath -Value ($logObj | ConvertTo-Json -Compress) -Encoding UTF8
}

function Ensure-RootInstallerShortcut {
    $content = @'
@echo off
chcp 65001 >nul
setlocal

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0current\scripts\client\install_client.ps1" %*
if errorlevel 1 (
    echo.
    echo [ERROR] 安装失败，请检查输出信息。
    pause
    exit /b 1
)

echo.
echo [OK] 安装完成。
pause
'@
    Set-Content -Path $rootInstallerPath -Value $content -Encoding ASCII
}

Write-Host "Deploying version $Version"
Write-Host "Source: $SourceRoot"
Write-Host "Release: $releaseDir"

if (-not (Test-Path $SourceRoot)) {
    throw "Source root not found: $SourceRoot"
}
if (Test-Path $releaseDir) {
    throw "Release already exists: $releaseDir"
}

New-Item -Path (Join-Path $TargetRoot "releases") -ItemType Directory -Force | Out-Null
New-Item -Path $logsDir -ItemType Directory -Force | Out-Null
New-Item -Path (Join-Path $TargetRoot "output") -ItemType Directory -Force | Out-Null

$manifest = Read-ReleaseManifest -TargetRoot $TargetRoot
$fromVersion = [string]$manifest.currentVersion

New-Item -Path $releaseDir -ItemType Directory -Force | Out-Null
$releaseDirCreated = $true

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
    $dest = Join-Path $releaseDir $item
    if (Test-Path $src) {
        if ((Get-Item $src) -is [System.IO.DirectoryInfo]) {
            robocopy $src $dest /E /NFL /NDL /NJH /NJS /NP | Out-Null
        } else {
            $destParent = Split-Path $dest
            if (-not (Test-Path $destParent)) {
                New-Item -Path $destParent -ItemType Directory -Force | Out-Null
            }
            Copy-Item $src $dest -Force
        }
    }
}

$linked = $false
try {
    if (Test-Path $currentDir) {
        Move-Item -Path $currentDir -Destination $backupCurrentDir -Force
    }

    try {
        New-Item -Path $currentDir -ItemType Junction -Value $releaseDir -ErrorAction Stop | Out-Null
        $linked = $true
    } catch {
        Write-Warning "Cannot create junction (insufficient privilege). Falling back to directory sync."
        New-Item -Path $currentDir -ItemType Directory -Force | Out-Null
        robocopy $releaseDir $currentDir /E /NFL /NDL /NJH /NJS /NP | Out-Null
    }

    if (Test-Path $backupCurrentDir) {
        Remove-Item $backupCurrentDir -Recurse -Force
    }

    Add-OrUpdateReleaseRecord -Manifest $manifest -Version $Version -Operator $Operator -Notes $Notes
    Set-ReleaseActiveStatus -Manifest $manifest -ActiveVersion $Version
    Add-ReleaseHistory -Manifest $manifest -Action "deploy" -FromVersion $fromVersion -ToVersion $Version -Operator $Operator -Notes $Notes -Success $true
    Write-ReleaseManifest -TargetRoot $TargetRoot -Manifest $manifest
    Ensure-RootInstallerShortcut

    Write-ReleaseOpsLog -Action "deploy" -FromVersion $fromVersion -ToVersion $Version -Success $true -Message "Deployment completed"
    Write-Host "Deployment completed."
    if ($linked) {
        Write-Host "Current points to: $releaseDir"
    } else {
        Write-Host "Current synced from: $releaseDir"
    }
} catch {
    $errText = $_.Exception.Message
    Write-Warning "Deployment failed: $errText"

    if (Test-Path $currentDir) {
        Remove-Item $currentDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path $backupCurrentDir) {
        Move-Item -Path $backupCurrentDir -Destination $currentDir -Force
    }
    if ($releaseDirCreated -and (Test-Path $releaseDir)) {
        Remove-Item -Path $releaseDir -Recurse -Force -ErrorAction SilentlyContinue
    }

    $manifest = Read-ReleaseManifest -TargetRoot $TargetRoot
    Add-ReleaseHistory -Manifest $manifest -Action "deploy" -FromVersion $fromVersion -ToVersion $Version -Operator $Operator -Notes $Notes -Success $false
    Write-ReleaseManifest -TargetRoot $TargetRoot -Manifest $manifest
    Write-ReleaseOpsLog -Action "deploy" -FromVersion $fromVersion -ToVersion $Version -Success $false -Message $errText
    throw
}
