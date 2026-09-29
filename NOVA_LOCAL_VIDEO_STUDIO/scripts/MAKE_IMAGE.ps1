[CmdletBinding()]
param([string]$Prompt = 'a fictional masked rap performer in a black hoodie, silver chain, headphones, standing in a blue-lit recording studio beside a microphone, confident performance pose, cinematic realistic photography', [int]$Seed = 20260929)
$ErrorActionPreference = 'Stop'
$StudioRoot = Split-Path -Parent $PSScriptRoot
$Python = 'F:\ComfyUI-NovaMind\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) { throw "ComfyUI Python runtime not found: $Python" }
& $Python (Join-Path $PSScriptRoot 'run_image.py') --prompt $Prompt --seed $Seed
if ($LASTEXITCODE -ne 0) { throw 'Local image generation failed.' }
