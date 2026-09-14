param([int]$Port = 8010, [switch]$Sandbox)
. (Join-Path $PSScriptRoot 'runtime-common.ps1')
try { Invoke-LocalRuntime -Action start -Port $Port -Sandbox $Sandbox.IsPresent }
catch { Write-Error $_ -ErrorAction Continue; exit 1 }
