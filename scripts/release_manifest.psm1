Set-StrictMode -Version Latest

function Get-ManifestPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TargetRoot
    )

    return Join-Path $TargetRoot "release_manifest.json"
}

function New-DefaultManifest {
    return @{
        manifestVersion = 1
        currentVersion  = ""
        updatedAt       = ""
        releases        = @()
        history         = @()
    }
}

function ConvertTo-HashtableDeep {
    param(
        [Parameter(Mandatory = $true)]
        $InputObject
    )

    if ($null -eq $InputObject) {
        return $null
    }

    if ($InputObject -is [System.Collections.IDictionary]) {
        $result = @{}
        foreach ($key in $InputObject.Keys) {
            $result[$key] = ConvertTo-HashtableDeep -InputObject $InputObject[$key]
        }
        return $result
    }

    if ($InputObject -is [System.Collections.IEnumerable] -and -not ($InputObject -is [string])) {
        $list = @()
        foreach ($item in $InputObject) {
            $list += ,(ConvertTo-HashtableDeep -InputObject $item)
        }
        return $list
    }

    if ($InputObject -is [pscustomobject]) {
        $result = @{}
        foreach ($prop in $InputObject.PSObject.Properties) {
            $result[$prop.Name] = ConvertTo-HashtableDeep -InputObject $prop.Value
        }
        return $result
    }

    return $InputObject
}

function Read-ReleaseManifest {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TargetRoot
    )

    $manifestPath = Get-ManifestPath -TargetRoot $TargetRoot
    if (-not (Test-Path $manifestPath)) {
        return New-DefaultManifest
    }

    $raw = Get-Content -Path $manifestPath -Raw -Encoding UTF8
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return New-DefaultManifest
    }

    $parsedRaw = $raw | ConvertFrom-Json
    $parsed = ConvertTo-HashtableDeep -InputObject $parsedRaw
    if (-not $parsed.Contains("releases")) {
        $parsed.releases = @()
    }
    if (-not $parsed.Contains("history")) {
        $parsed.history = @()
    }
    if (-not $parsed.Contains("manifestVersion")) {
        $parsed.manifestVersion = 1
    }
    return $parsed
}

function Write-ReleaseManifest {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TargetRoot,
        [Parameter(Mandatory = $true)]
        [hashtable]$Manifest
    )

    $manifestPath = Get-ManifestPath -TargetRoot $TargetRoot
    $Manifest.updatedAt = (Get-Date).ToString("o")
    $json = $Manifest | ConvertTo-Json -Depth 10
    Set-Content -Path $manifestPath -Value $json -Encoding UTF8
}

function Add-OrUpdateReleaseRecord {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Manifest,
        [Parameter(Mandatory = $true)]
        [string]$Version,
        [string]$Operator,
        [string]$Notes
    )

    $existing = $null
    foreach ($record in $Manifest.releases) {
        if ($record.version -eq $Version) {
            $existing = $record
            break
        }
    }

    if ($null -eq $existing) {
        $existing = @{
            version     = $Version
            path        = "releases/$Version"
            publishedAt = (Get-Date).ToString("o")
            publishedBy = $Operator
            notes       = $Notes
            status      = "available"
        }
        $Manifest.releases += $existing
    } else {
        if (-not [string]::IsNullOrWhiteSpace($Operator)) {
            $existing.publishedBy = $Operator
        }
        if (-not [string]::IsNullOrWhiteSpace($Notes)) {
            $existing.notes = $Notes
        }
    }
}

function Set-ReleaseActiveStatus {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Manifest,
        [Parameter(Mandatory = $true)]
        [string]$ActiveVersion
    )

    foreach ($record in $Manifest.releases) {
        if ($record.version -eq $ActiveVersion) {
            $record.status = "active"
        } else {
            $record.status = "available"
        }
    }
    $Manifest.currentVersion = $ActiveVersion
}

function Add-ReleaseHistory {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Manifest,
        [Parameter(Mandatory = $true)]
        [string]$Action,
        [string]$FromVersion,
        [string]$ToVersion,
        [string]$Operator,
        [string]$Notes,
        [bool]$Success = $true
    )

    $entry = @{
        action      = $Action
        fromVersion = $FromVersion
        toVersion   = $ToVersion
        operator    = $Operator
        notes       = $Notes
        success     = $Success
        timestamp   = (Get-Date).ToString("o")
    }

    $Manifest.history += $entry
    if ($Manifest.history.Count -gt 200) {
        $Manifest.history = @($Manifest.history | Select-Object -Last 200)
    }
}

Export-ModuleMember -Function Get-ManifestPath, Read-ReleaseManifest, Write-ReleaseManifest, Add-OrUpdateReleaseRecord, Set-ReleaseActiveStatus, Add-ReleaseHistory
