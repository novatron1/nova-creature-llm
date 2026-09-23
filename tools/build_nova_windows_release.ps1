param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path $Root).Path
if (-not $Output) { $Output = Join-Path $Root "dist\nova-standalone" }
$Output = [IO.Path]::GetFullPath($Output)
New-Item -ItemType Directory -Force -Path $Output | Out-Null

# Copy only the portable application surface. User data, credentials, model
# weights, checkpoints, adapters, and operational logs are deliberately absent.
$includeDirectories = @("assets", "src", "tools", "scripts", "docs", "config")
$includeFiles = @(
    "nova_enhanced_server.py",
    "nova_chat_web.html",
    "nova_companion_web.html",
    "manifest.webmanifest",
    "service-worker.js",
    "INSTALL_NOVA_GPU_HUB_WINDOWS.ps1",
    "NOVA_GPU_HUB_INSTALL.bat",
    "ANDROID_INSTALL_GUIDE.md",
    "pytest.ini"
)

foreach ($relative in $includeDirectories) {
    $source = Join-Path $Root $relative
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $Output $relative) -Recurse -Force
    }
}
foreach ($relative in $includeFiles) {
    $source = Join-Path $Root $relative
    if (Test-Path -LiteralPath $source) {
        $destination = Join-Path $Output $relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
        Copy-Item -LiteralPath $source -Destination $destination -Force
    }
}

$launcher = @'
@echo off
setlocal
cd /d "%~dp0"
py "%~dp0tools\nova_doctor.py" --root "%~dp0" --port 3000
if errorlevel 1 exit /b %errorlevel%
py "%~dp0nova_enhanced_server.py" 3000
'@
Set-Content -LiteralPath (Join-Path $Output "Nova_Start.bat") -Value $launcher -Encoding ASCII

$forbidden = @("data", "checkpoints", "adapters", "models", "nova_memory", "nova_training_logs", "reports", ".env", "*.pt", "*.pth", "*.gguf", "*.safetensors")
$violations = Get-ChildItem -LiteralPath $Output -Recurse -Force -File | Where-Object {
    $relative = $_.FullName.Substring($Output.Length).TrimStart('\', '/')
    $forbidden | Where-Object { $relative -like "$_" -or $relative -like "$_\*" }
}
if ($violations) { throw "Release contains forbidden private or model material: $($violations.Name -join ', ')" }

$manifestPath = Join-Path $Output "NOVA_RELEASE_MANIFEST.json"
$rollbackPath = Join-Path $Output "rollback.json"
$files = @(Get-ChildItem -LiteralPath $Output -Recurse -Force -File | Where-Object {
    $_.FullName -ne $manifestPath -and $_.FullName -ne $rollbackPath
} | ForEach-Object {
    $relative = $_.FullName.Substring($Output.Length).TrimStart('\', '/')
    [ordered]@{
        path = $relative
        bytes = $_.Length
        sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
})
$manifest = [ordered]@{
    schema_version = "1.0"
    product = "Nova Creature standalone"
    built_at = [DateTime]::UtcNow.ToString("o")
    includes_model_weights = $false
    includes_private_data = $false
    files = $files
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
[ordered]@{
    schema_version = "1.0"
    rollback = "Delete this candidate directory and restore the previous Nova folder; no user data was copied."
    manifest = "NOVA_RELEASE_MANIFEST.json"
    created_at = [DateTime]::UtcNow.ToString("o")
} | ConvertTo-Json | Set-Content -LiteralPath $rollbackPath -Encoding UTF8
Write-Host "Nova standalone bundle created at $Output"
