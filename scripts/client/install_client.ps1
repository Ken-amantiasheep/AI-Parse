param(
    [string]$RemoteRoot = "S:\Uploading Team\AI-parse",
    [string]$InstallRoot = "$env:LOCALAPPDATA\AI-parse",
    [switch]$NoDesktopShortcut,
    [switch]$NoStartMenuShortcut
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function New-AppShortcut {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ShortcutPath,
        [Parameter(Mandatory = $true)]
        [string]$TargetPath,
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory
    )

    $shortcutDir = Split-Path -Parent $ShortcutPath
    if (-not (Test-Path $shortcutDir)) {
        New-Item -Path $shortcutDir -ItemType Directory -Force | Out-Null
    }

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath = $TargetPath
    $shortcut.WorkingDirectory = $WorkingDirectory
    $shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,220"
    $shortcut.Save()
}

function Get-RemoteReleaseSource {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RemoteRoot
    )

    $manifestPath = Join-Path $RemoteRoot "release_manifest.json"
    if (Test-Path $manifestPath) {
        $manifest = Get-Content -Path $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $currentVersion = [string]$manifest.currentVersion
        if (-not [string]::IsNullOrWhiteSpace($currentVersion)) {
            $candidate = Join-Path $RemoteRoot "releases\$currentVersion"
            if (Test-Path $candidate) {
                return $candidate
            }
        }
    }
    return (Join-Path $RemoteRoot "current")
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent (Split-Path -Parent $scriptDir)

if (-not (Test-Path $RemoteRoot)) {
    throw "Remote root not found: $RemoteRoot"
}

$sourceApp = Get-RemoteReleaseSource -RemoteRoot $RemoteRoot
if (-not (Test-Path $sourceApp)) {
    throw "Remote app source not found: $sourceApp"
}

$installRootResolved = [System.IO.Path]::GetFullPath($InstallRoot)
$bootstrapDir = Join-Path $installRootResolved "bootstrap"
$appCurrentDir = Join-Path $installRootResolved "app\current"
$launcherBat = Join-Path $installRootResolved "start_ai_parse.bat"
$clientLauncherSource = Join-Path $repoRoot "scripts\client\client_launcher.py"
$launcherBatSource = Join-Path $repoRoot "scripts\client\start_local_client.bat"

New-Item -Path $bootstrapDir -ItemType Directory -Force | Out-Null
New-Item -Path (Join-Path $installRootResolved "app") -ItemType Directory -Force | Out-Null

Copy-Item -Path $clientLauncherSource -Destination (Join-Path $bootstrapDir "client_launcher.py") -Force
Copy-Item -Path $launcherBatSource -Destination $launcherBat -Force

if (Test-Path $appCurrentDir) {
    Remove-Item -Path $appCurrentDir -Recurse -Force
}
robocopy $sourceApp $appCurrentDir /E /NFL /NDL /NJH /NJS /NP | Out-Null

$statePath = Join-Path $bootstrapDir "local_state.json"
$state = [ordered]@{
    installedVersion = ""
    lastUpdatedAt    = (Get-Date).ToString("o")
    remoteRoot       = $RemoteRoot
}

$versionFile = Join-Path $appCurrentDir "version.py"
if (Test-Path $versionFile) {
    $line = (Get-Content $versionFile | Where-Object { $_ -match '^APP_VERSION\s*=' } | Select-Object -First 1)
    if ($line -match "['""]([^'""]+)['""]") {
        $state.installedVersion = $Matches[1]
    }
}

Set-Content -Path $statePath -Value ($state | ConvertTo-Json -Depth 5) -Encoding UTF8

$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "AI-parse.lnk"
$startMenuShortcut = Join-Path ([Environment]::GetFolderPath("Programs")) "AI-parse.lnk"

if (-not $NoDesktopShortcut) {
    New-AppShortcut -ShortcutPath $desktopShortcut -TargetPath $launcherBat -WorkingDirectory $installRootResolved
}
if (-not $NoStartMenuShortcut) {
    New-AppShortcut -ShortcutPath $startMenuShortcut -TargetPath $launcherBat -WorkingDirectory $installRootResolved
}

Write-Host "安装完成: $installRootResolved"
Write-Host "启动方式: $launcherBat"
