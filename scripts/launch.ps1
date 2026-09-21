# Daily launcher: build changed UI, start/reuse the managed server, open dashboard.
# Compatible with Windows PowerShell 5.1; keep this file ASCII for double-click use.
param([switch]$NoBrowser, [switch]$Rebuild)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$frontend = Join-Path $root 'frontend'
$index = Join-Path $frontend 'dist\index.html'
$url = 'http://127.0.0.1:8010/'

try {
    if (-not (Test-Path -LiteralPath (Join-Path $root '.venv\Scripts\python.exe'))) {
        throw 'Python environment missing. Follow README.md to install backend dependencies first.'
    }
    $hadFrontend = Test-Path -LiteralPath $index
    . (Join-Path $PSScriptRoot 'frontend-dependencies.ps1')
    $dependenciesChanged = Ensure-FrontendDependencies -Frontend $frontend
    $needsBuild = $Rebuild.IsPresent -or -not $hadFrontend -or $dependenciesChanged
    if ($hadFrontend -and -not $needsBuild) {
        $builtAt = (Get-Item -LiteralPath $index).LastWriteTimeUtc
        foreach ($entry in @('src', 'public', 'index.html', 'package.json', 'package-lock.json', 'vite.config.js', 'vite.config.ts')) {
            $path = Join-Path $frontend $entry
            if (Test-Path -LiteralPath $path) {
                if (@(Get-ChildItem -LiteralPath $path -Recurse -File | Where-Object { $_.LastWriteTimeUtc -gt $builtAt }).Count -gt 0) {
                    $needsBuild = $true
                    break
                }
                if ((Get-Item -LiteralPath $path).LastWriteTimeUtc -gt $builtAt) { $needsBuild = $true }
            }
        }
    }
    if ($needsBuild) {
        $npm = Resolve-NpmCmd
        Push-Location -LiteralPath $frontend
        try {
            Write-Host 'Building dashboard...'
            & $npm run build
            if ($LASTEXITCODE -ne 0) { throw 'Dashboard build failed. Backend was not restarted.' }
        } finally { Pop-Location }
    }

    . (Join-Path $PSScriptRoot 'runtime-common.ps1')
    # A server launched before dist existed needs a restart to mount the web UI.
    $action = if ($hadFrontend) { 'start' } else { 'restart' }
    Invoke-LocalRuntime -Action $action -Port 8010 -Sandbox $false

    $client = New-Object Net.WebClient
    $client.Proxy = $null
    try {
        $html = $client.DownloadString($url)
        if ($html -notmatch 'id="app"') { throw 'Dashboard health check failed: expected the Vue application.' }
    } finally { $client.Dispose() }

    Write-Host "Dashboard ready: $url"
    Write-Host 'Backend stays running after this window closes.'
    Write-Host 'To stop: powershell -File scripts\stop.ps1'
    if (-not $NoBrowser) { Start-Process -FilePath $url }
} catch {
    Write-Host "Startup failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
