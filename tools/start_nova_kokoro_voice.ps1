param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [int]$Port = 8890
)

$ErrorActionPreference = "Stop"
$pythonPath = "F:\Nova\kokoro-tts\.venv\Scripts\python.exe"
$workerPath = Join-Path $ProjectRoot "scripts\nova_kokoro_voice_worker.py"

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    Write-Host "[VOICE] Neural GPU voice is already running on port $Port."
    exit 0
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    Write-Host "[VOICE] Neural GPU voice is not installed yet; Nova will use its safe voice fallback."
    exit 0
}
if (-not (Test-Path -LiteralPath $workerPath)) {
    Write-Host "[VOICE] Voice worker is missing; Nova will use its safe voice fallback."
    exit 0
}

$env:HF_HOME = "F:\Nova\kokoro-tts\cache"
$env:TORCH_HOME = "F:\Nova\kokoro-tts\cache\torch"
New-Item -ItemType Directory -Path $env:HF_HOME -Force | Out-Null

Start-Process -FilePath $pythonPath `
    -ArgumentList @("-u", $workerPath, "--port", "$Port") `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden

Write-Host "[VOICE] Starting Nova's local neural GPU voice..."
exit 0
