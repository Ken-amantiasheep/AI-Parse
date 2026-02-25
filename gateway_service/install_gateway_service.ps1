param(
    [string]$ServiceName = "AIParseGateway",
    [string]$AppRoot = "S:\Uploading Team\current",
    [string]$PythonExe = "python",
    [string]$Host = "0.0.0.0",
    [string]$Port = "8080"
)

Write-Host "Installing service: $ServiceName"

$gatewayCmd = "$PythonExe -m uvicorn gateway_service.app:app --host $Host --port $Port"

if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) {
    Write-Error "nssm not found in PATH. Install NSSM first."
    exit 1
}

nssm install $ServiceName $PythonExe "-m uvicorn gateway_service.app:app --host $Host --port $Port"
nssm set $ServiceName AppDirectory $AppRoot
nssm set $ServiceName Start SERVICE_AUTO_START

Write-Host "Service installed. Configure env vars at system level first:"
Write-Host " - ANTHROPIC_API_KEY"
Write-Host " - INTERNAL_API_TOKEN"
Write-Host " - RATE_LIMIT_PER_MIN (optional)"
Write-Host "Then start service:"
Write-Host "  nssm start $ServiceName"
