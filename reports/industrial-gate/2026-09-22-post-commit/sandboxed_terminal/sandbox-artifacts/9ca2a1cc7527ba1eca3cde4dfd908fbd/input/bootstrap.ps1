$ErrorActionPreference = 'Stop'
$plan = Get-Content -LiteralPath C:\NovaInput\plan.json -Raw | ConvertFrom-Json
$before = (Get-FileHash C:\NovaInput\candidate.ps1 -Algorithm SHA256).Hash.ToLowerInvariant()
$work = Join-Path $env:TEMP ('nova-' + $plan.run_id)
New-Item -ItemType Directory -Path $work | Out-Null
$candidate = Join-Path $work 'candidate.ps1'
Copy-Item -LiteralPath C:\NovaInput\candidate.ps1 -Destination $candidate
$text = [IO.File]::ReadAllText($candidate).Replace('hello', 'hello, nova')
[IO.File]::WriteAllText($candidate, $text, [Text.UTF8Encoding]::new($false))
$terminal = @(& powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $candidate)
$terminalCode = $LASTEXITCODE
$after = (Get-FileHash C:\NovaInput\candidate.ps1 -Algorithm SHA256).Hash.ToLowerInvariant()
$edited = (Get-FileHash $candidate -Algorithm SHA256).Hash.ToLowerInvariant()
$result = @{
 schema_version=1; run_id=$plan.run_id; nonce=$plan.nonce;
 candidate_before=$before; candidate_after=$after; edited_sha256=$edited;
 terminal_exit_code=$terminalCode; terminal_output=($terminal -join "`n");
 backend='windows_sandbox'; passed=($terminalCode -eq 0 -and ($terminal -join "`n") -ceq 'hello, nova')
}
[IO.File]::WriteAllText('C:\NovaOutput\result.tmp', ($result | ConvertTo-Json -Compress), [Text.UTF8Encoding]::new($false))
Move-Item -LiteralPath C:\NovaOutput\result.tmp -Destination C:\NovaOutput\result.json
shutdown.exe /s /t 0
