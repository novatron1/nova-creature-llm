$ErrorActionPreference = 'Stop'
try {
 $diagnostic = @(& C:\NovaInput\python\python.exe -I -S C:\NovaInput\guest.py 2>&1)
 if ($LASTEXITCODE -ne 0) { throw ('Python exit ' + $LASTEXITCODE + ': ' + ($diagnostic -join "`n")) }
} catch {
 [IO.File]::WriteAllText('C:\NovaOutput\bootstrap-error.txt', $_.ToString())
}
shutdown.exe /s /t 0
