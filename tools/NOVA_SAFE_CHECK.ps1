param(
    [string]$LiveUrl = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Push-Location $Root
try {
    py -3.11 -m pytest -q
    if ($LASTEXITCODE -ne 0) {
        throw "Nova regression tests failed with exit code $LASTEXITCODE."
    }
    if (Get-Command node -ErrorAction SilentlyContinue) {
        node --check assets\nova_foundation_ui.js
        if ($LASTEXITCODE -ne 0) {
            throw "Nova browser controls contain a syntax error."
        }
        node --check service-worker.js
        if ($LASTEXITCODE -ne 0) {
            throw "Nova offline app worker contains a syntax error."
        }
    }
    if ($LiveUrl) {
        py -3.11 tools\nova_smoke_check.py --url $LiveUrl
        if ($LASTEXITCODE -ne 0) {
            throw "Nova live smoke check failed with exit code $LASTEXITCODE."
        }
    }
    Write-Host "NOVA SAFE CHECK PASSED"
}
finally {
    Pop-Location
}
