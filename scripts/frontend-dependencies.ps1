# Dependency synchronization shared by the Windows launcher. ASCII / PS 5.1.
function Resolve-NpmCmd {
    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $npm) { throw 'Node.js/npm is required. Install Node.js 22.12 or newer, then retry.' }
    return $npm.Source
}

function Ensure-FrontendDependencies {
    param([Parameter(Mandatory=$true)][string]$Frontend, [string]$NpmPath)

    $lock = Join-Path $Frontend 'package-lock.json'
    $package = Join-Path $Frontend 'package.json'
    $stamp = Join-Path $Frontend 'node_modules\.game-assistant-deps.sha256'
    $vite = Join-Path $Frontend 'node_modules\vite\package.json'
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $fingerprint = [BitConverter]::ToString($sha.ComputeHash([IO.File]::ReadAllBytes($package))) + ':' +
            [BitConverter]::ToString($sha.ComputeHash([IO.File]::ReadAllBytes($lock)))
    } finally { $sha.Dispose() }
    if ((Test-Path -LiteralPath $vite) -and (Test-Path -LiteralPath $stamp)) {
        if ((Get-Content -LiteralPath $stamp -Raw).Trim() -eq $fingerprint) { return $false }
    }

    if (-not $NpmPath) { $NpmPath = Resolve-NpmCmd }
    # npm ci can leave a partial node_modules on failure. Never reuse its old stamp.
    if (Test-Path -LiteralPath $stamp) { Remove-Item -LiteralPath $stamp -Force }
    Push-Location -LiteralPath $Frontend
    try {
        Write-Host 'Installing frontend dependencies from package-lock.json...'
        & $NpmPath ci | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'npm ci failed. Dependency stamp was not saved; retry after fixing the installation.' }
        if (-not (Test-Path -LiteralPath $vite)) { throw 'npm ci did not install Vite. Dependency stamp was not saved.' }
        [IO.File]::WriteAllText($stamp, $fingerprint, [Text.Encoding]::ASCII)
    } finally { Pop-Location }
    return $true
}
