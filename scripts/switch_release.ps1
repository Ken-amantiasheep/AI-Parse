param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^v?\d+\.\d+\.\d+$")]
    [string]$Version,
    [string]$TargetRoot = "S:\Uploading Team\AI-parse",
    [string]$Operator = $env:USERNAME,
    [string]$Reason = "manual switch"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Import-Module (Join-Path $scriptRoot "release_manifest.psm1") -Force

$releaseDir = Join-Path $TargetRoot "releases\$Version"
$currentDir = Join-Path $TargetRoot "current"
$backupCurrentDir = Join-Path $TargetRoot ("current_backup_switch_{0}" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
$logsDir = Join-Path $TargetRoot "logs"
$opsLogPath = Join-Path $logsDir "release_ops.log"
$rootInstallerPath = Join-Path $TargetRoot "install_client.bat"

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

function Test-ReleaseHealth {
    param([string]$ReleaseDir)

    $required = @(
        "start_gui.bat",
        "main.py",
        "gui_app_simple.py",
        "version.py",
        "config\config.example.json"
    )

    foreach ($file in $required) {
        $target = Join-Path $ReleaseDir $file
        if (-not (Test-Path $target)) {
            throw "Release health check failed. Missing: $target"
        }
    }
}

if (-not (Test-Path $releaseDir)) {
    Write-Error "Release not found: $releaseDir"
    exit 1
}

New-Item -Path $logsDir -ItemType Directory -Force | Out-Null
Test-ReleaseHealth -ReleaseDir $releaseDir

$manifest = Read-ReleaseManifest -TargetRoot $TargetRoot
$fromVersion = [string]$manifest.currentVersion
$action = if ([string]::IsNullOrWhiteSpace($fromVersion)) { "switch" } else { "rollback" }

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

    Add-OrUpdateReleaseRecord -Manifest $manifest -Version $Version -Operator $Operator -Notes $Reason
    Set-ReleaseActiveStatus -Manifest $manifest -ActiveVersion $Version
    Add-ReleaseHistory -Manifest $manifest -Action $action -FromVersion $fromVersion -ToVersion $Version -Operator $Operator -Notes $Reason -Success $true
    Write-ReleaseManifest -TargetRoot $TargetRoot -Manifest $manifest
    Ensure-RootInstallerShortcut
    Write-ReleaseOpsLog -Action $action -FromVersion $fromVersion -ToVersion $Version -Success $true -Message "Switch completed"

    if ($linked) {
        Write-Host "Current release switched to: $releaseDir"
    } else {
        Write-Host "Current release synced from: $releaseDir"
    }
} catch {
    $errText = $_.Exception.Message
    Write-Warning "Switch failed: $errText"

    if (Test-Path $currentDir) {
        Remove-Item $currentDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path $backupCurrentDir) {
        Move-Item -Path $backupCurrentDir -Destination $currentDir -Force
    }

    $manifest = Read-ReleaseManifest -TargetRoot $TargetRoot
    Add-ReleaseHistory -Manifest $manifest -Action $action -FromVersion $fromVersion -ToVersion $Version -Operator $Operator -Notes $Reason -Success $false
    Write-ReleaseManifest -TargetRoot $TargetRoot -Manifest $manifest
    Write-ReleaseOpsLog -Action $action -FromVersion $fromVersion -ToVersion $Version -Success $false -Message $errText
    throw
}
