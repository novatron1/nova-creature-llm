[CmdletBinding()]
param(
    [switch]$CheckOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSCommandPath

function Get-NovaPython {
    foreach ($candidate in @(
        @{ Command = "py"; Arguments = @("-3.11") },
        @{ Command = "py"; Arguments = @("-3") },
        @{ Command = "python"; Arguments = @() }
    )) {
        if (Get-Command $candidate.Command -ErrorAction SilentlyContinue) {
            & $candidate.Command @($candidate.Arguments) -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
            if ($LASTEXITCODE -eq 0) { return $candidate }
        }
    }
    throw "Python 3.10 or newer is required. Install it from https://python.org"
}

Push-Location $Root
try {
    $Python = Get-NovaPython
    Write-Host "[OK] Python: $($Python.Command) $($Python.Arguments -join ' ')"

    $dataDirectory = Join-Path $Root "data"
    if (-not (Test-Path -LiteralPath $dataDirectory)) {
        New-Item -ItemType Directory -Path $dataDirectory -Force | Out-Null
        Write-Host "[OK] Created data folder."
    } else {
        Write-Host "[OK] Data folder is ready."
    }

    & $Python.Command @($Python.Arguments) -m py_compile nova_enhanced_server.py
    if ($LASTEXITCODE -ne 0) { throw "Nova core smoke check failed." }
    Write-Host "[OK] Nova core smoke check passed."

    Write-Host "GPU Hub is available inside Nova after you start Nova normally."
    Write-Host "Health check: http://127.0.0.1:3000/healthz"
    Write-Host "Use a loopback, private-network, or Tailscale worker endpoint."
    Write-Host "In GPU Hub enter endpoint, exact model, and provider, then choose Test / Verify worker."
    Write-Host "Public worker names require an exact NOVA_GPU_HUB_REMOTE_MODEL_ALLOWLIST server setting."
    Write-Host "Auto may use a healthy verified Local or Vast worker; otherwise it uses CPU."
    Write-Host "Optional Vast.ai setup (do this yourself in a new PowerShell window):"
    Write-Host '  setx NOVA_VAST_API_KEY "paste-your-Vast-api-key-here"'
    Write-Host "This installer never reads, saves, or displays your Vast.ai key."

    if ($CheckOnly) {
        Write-Host "NOVA GPU HUB CHECK PASSED"
    } else {
        Write-Host "NOVA GPU HUB INSTALL READY"
        Write-Host "No model files were changed and Nova server startup was left unchanged."
    }
}
finally {
    Pop-Location
}
