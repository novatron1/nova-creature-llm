[CmdletBinding()]
param(
  [string]$Prompt = '',
  [string]$Image = '',
  [int]$Frames = 8,
  [int]$Width = 384,
  [int]$Height = 480,
  [ValidateSet('wan','animatelcm')]
  [string]$Engine = 'animatelcm'
)
$ErrorActionPreference = 'Stop'
$StudioRoot = Split-Path -Parent $PSScriptRoot
$Python = 'F:\ComfyUI-NovaMind\.venv\Scripts\python.exe'
if($Image){$source = Get-Item -LiteralPath $Image} else {$source = Get-ChildItem (Join-Path $StudioRoot 'inputs\images') -File | Where-Object { $_.Extension -in '.png','.jpg','.jpeg' } | Where-Object Name -notlike 'README*' | Where-Object Name -notlike 'TECH_TEST_ONLY*' | Select-Object -First 1}
if (-not $source) { throw 'No Lil Ammo reference image found. Put it in inputs\images and run again.' }
$previewArgs = @((Join-Path $PSScriptRoot 'run_preview.py'),'--engine',$Engine,'--image',$source.FullName,'--frames',$Frames,'--width',$Width,'--height',$Height)
if($Prompt){$previewArgs += @('--prompt',$Prompt)}
& $Python @previewArgs
if ($LASTEXITCODE -ne 0) { throw 'Preview failed. Check the error and logs; no completed video was reported.' }
