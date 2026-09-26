# Shared implementation. Compatible with Windows PowerShell 5.1.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Initialize-Runtime {
    param([int]$Port, [bool]$Sandbox)
    if ($Port -lt 1024 -or $Port -gt 65535) { throw 'Port must be between 1024 and 65535.' }
    if ((-not $Sandbox -and $Port -ne 8010) -or ($Sandbox -and $Port -eq 8010)) {
        throw 'Production uses port 8010; -Sandbox requires a separate -Port.'
    }
    $script:ProjectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
    $script:RunnerPath = Join-Path $script:ProjectRoot 'src\game_assistant\runtime.py'
    $script:PythonPath = Join-Path $script:ProjectRoot '.venv\Scripts\python.exe'
    $script:RuntimeDir = Join-Path $script:ProjectRoot 'data\runtime'
    if ($Sandbox) { $script:RuntimeDir = Join-Path $script:RuntimeDir "sandbox-$Port" }
    # Refuse redirected runtime paths before writing or deleting project metadata.
    $candidate = $script:RuntimeDir
    while ($candidate -and $candidate.Length -ge $script:ProjectRoot.Length) {
        if (Test-Path -LiteralPath $candidate) {
            if ((Get-Item -LiteralPath $candidate -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw 'Runtime/project path is redirected by a junction or symbolic link.'
            }
        }
        $candidate = Split-Path -Parent $candidate
    }
    [IO.Directory]::CreateDirectory($script:RuntimeDir) | Out-Null
    $script:StatePath = Join-Path $script:RuntimeDir 'service.json'
    $script:ReadyPath = Join-Path $script:RuntimeDir 'ready.json'
    $script:StopPath = Join-Path $script:RuntimeDir 'stop.json'
    $script:ServicePort = $Port
    $script:SandboxMode = $Sandbox
}

function Read-State {
    if (-not (Test-Path -LiteralPath $script:StatePath)) { return $null }
    try { return Get-Content -LiteralPath $script:StatePath -Raw -Encoding UTF8 | ConvertFrom-Json }
    catch { throw 'Runtime record is unreadable; refusing to guess process ownership.' }
}

function Get-VerifiedProcess {
    param($Record, [switch]$Handshake)
    if (-not $Record) { return $null }
    if ($Record.root -ne $script:ProjectRoot -or [int]$Record.port -ne $script:ServicePort -or
        $Record.runtime_id -notmatch '^[a-f0-9]{32}$') {
        throw 'Runtime record belongs to another project or is invalid.'
    }
    $targetId = [int]$Record.pid
    $process = Get-Process -Id $targetId -ErrorAction SilentlyContinue
    if (-not $process) { return $null }
    # Opening the handle now pins identity for validation and any subsequent Kill.
    $null = $process.Handle
    $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $targetId"
    $quotedRunner = '"' + $script:RunnerPath + '"'
    if (-not $cim -or -not $cim.CommandLine -or
        -not $cim.CommandLine.Contains($quotedRunner) -or
        $cim.CommandLine -notmatch ('(?:^|\s)--runtime-id\s+' + [regex]::Escape($Record.runtime_id) + '(?:\s|$)') -or
        $cim.CommandLine -notmatch ('(?:^|\s)--port\s+' + $script:ServicePort + '(?:\s|$)')) {
        throw 'Process identity differs from the runtime record; refusing to stop or adopt it.'
    }
    if (-not $Handshake) {
        if ([string]$process.StartTime.ToUniversalTime().Ticks -ne [string]$Record.creation_ticks -or
            $process.Path -ne $Record.executable) {
            throw 'Process creation time/executable changed (possible PID reuse); refusing to stop it.'
        }
    }
    return $process
}

function Test-Health {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$script:ServicePort/api/health" -TimeoutSec 2
        return ($health.status -eq 'ok' -and $health.service -eq 'game-assistant')
    } catch { return $false }
}

function Get-Listeners {
    return @(Get-NetTCPConnection -LocalPort $script:ServicePort -State Listen -ErrorAction SilentlyContinue)
}

function Test-OwnedListener {
    param([int]$TargetId)
    $listeners = @(Get-Listeners)
    return ($listeners.Count -eq 1 -and $listeners[0].LocalAddress -eq '127.0.0.1' -and
            $listeners[0].OwningProcess -eq $TargetId)
}

function Write-State {
    param($Record, $Process)
    $state = [ordered]@{
        pid = $Process.Id; root = $script:ProjectRoot; port = $script:ServicePort
        runtime_id = $Record.runtime_id
        creation_ticks = [string]$Process.StartTime.ToUniversalTime().Ticks
        executable = $Process.Path
    }
    $json = $state | ConvertTo-Json
    [IO.File]::WriteAllText($script:StatePath, $json, (New-Object Text.UTF8Encoding($false)))
}

function Clear-RuntimeRecord {
    foreach ($path in @($script:StatePath, $script:ReadyPath, $script:StopPath)) {
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
    }
}

function Start-LocalRuntime {
    $record = Read-State
    $existing = Get-VerifiedProcess $record
    if ($existing) {
        if ((Test-OwnedListener $existing.Id) -and (Test-Health)) {
            Write-Output "Already running: http://127.0.0.1:$script:ServicePort (PID $($existing.Id))"
            return
        }
        throw "Managed process exists but is unhealthy. Use restart.ps1. Logs: $script:RuntimeDir"
    }
    if (@(Get-Listeners).Count -gt 0) {
        throw "Port $script:ServicePort is occupied by an unmanaged process; no process was stopped."
    }
    if (-not (Test-Path -LiteralPath $script:PythonPath)) { throw 'Missing .venv\Scripts\python.exe. Install the project dependencies first.' }
    if (-not $script:SandboxMode -and -not (Test-Path -LiteralPath (Join-Path $script:ProjectRoot 'frontend\dist\index.html'))) {
        Write-Warning 'frontend/dist is missing. The API will run; build the frontend to serve the UI.'
    }
    Clear-RuntimeRecord
    $runId = [Guid]::NewGuid().ToString('N')
    $arguments = '"' + $script:RunnerPath + '" --port ' + $script:ServicePort +
        ' --runtime-id ' + $runId + ' --runtime-dir "' + $script:RuntimeDir + '"'
    if ($script:SandboxMode) { $arguments += ' --sandbox' }
    # The runner records its own PID: Windows venv launchers can create a child.
    $launcher = Start-Process -FilePath $script:PythonPath -ArgumentList $arguments -WorkingDirectory $script:ProjectRoot -WindowStyle Hidden -PassThru
    $managed = $null
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (-not $managed -and (Test-Path -LiteralPath $script:ReadyPath)) {
            $ready = Get-Content -LiteralPath $script:ReadyPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($ready.runtime_id -ne $runId) { throw 'Unexpected runtime handshake; refusing to adopt it.' }
            $managed = Get-VerifiedProcess $ready -Handshake
            if ($managed) { Write-State $ready $managed }
        }
        if ($managed) {
            if ($managed.HasExited) { break }
            if ((Test-Health) -and (Test-OwnedListener $managed.Id)) {
                Write-Output "Running: http://127.0.0.1:$script:ServicePort (PID $($managed.Id))"
                Write-Output "Logs: $(Join-Path $script:RuntimeDir 'service.log')"
                return
            }
        } elseif ($launcher.HasExited -and $launcher.ExitCode -ne 0) { break }
        Start-Sleep -Milliseconds 250
    }
    # Only the exact process launched for this attempt may be cleaned up.
    if ($managed) {
        $verified = Get-VerifiedProcess (Read-State)
        if ($verified) { $verified.Kill(); $null = $verified.WaitForExit(5000) }
        Clear-RuntimeRecord
    } elseif (-not $launcher.HasExited) {
        # No handshake was written, so this is still the process we started.
        $launcher.Kill()
        $null = $launcher.WaitForExit(5000)
    }
    throw "Startup health/identity check failed. Logs: $script:RuntimeDir"
}

function Stop-LocalRuntime {
    $record = Read-State
    $managed = Get-VerifiedProcess $record
    if (-not $managed) {
        Clear-RuntimeRecord
        Write-Output 'Stopped (no managed process).'
        return
    }
    $request = @{ runtime_id = $record.runtime_id } | ConvertTo-Json
    [IO.File]::WriteAllText($script:StopPath, $request, (New-Object Text.UTF8Encoding($false)))
    if (-not $managed.WaitForExit(10000)) {
        # Grace period elapsed: revalidate identity immediately before fallback.
        $verified = Get-VerifiedProcess (Read-State)
        if ($verified) {
            Write-Warning 'Graceful shutdown timed out; terminating the verified process.'
            $verified.Kill()
            if (-not $verified.WaitForExit(5000)) { throw 'Managed process did not exit; runtime record retained.' }
        }
    }
    Clear-RuntimeRecord
    Write-Output "Stopped managed PID $($managed.Id)."
}

function Show-LocalRuntime {
    $record = Read-State
    $managed = Get-VerifiedProcess $record
    if (-not $managed) {
        Write-Output 'Stopped (no managed process).'
        if (@(Get-Listeners).Count -gt 0) { Write-Output "Port $script:ServicePort is occupied by an unmanaged listener." }
        return
    }
    if (-not ((Test-OwnedListener $managed.Id) -and (Test-Health))) {
        throw "Managed PID $($managed.Id) is unhealthy; logs: $script:RuntimeDir"
    }
    Write-Output "Healthy: http://127.0.0.1:$script:ServicePort (PID $($managed.Id))"
    Write-Output "Logs: $(Join-Path $script:RuntimeDir 'service.log')"
}

function Invoke-LocalRuntime {
    param([ValidateSet('start', 'stop', 'status', 'restart')][string]$Action,
          [int]$Port = 8010, [bool]$Sandbox = $false)
    Initialize-Runtime $Port $Sandbox
    $lock = $null
    try {
        try {
            $lock = [IO.File]::Open((Join-Path $script:RuntimeDir 'service.lock'),
                [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
        } catch {
            # Only a lock held by another runtime command is a conflict.
            # Path and permission failures keep their original error.
            $sharing = $false
            $ex = $_.Exception
            while ($ex) {
                if ($ex -is [System.IO.IOException]) {
                    $code = $ex.HResult -band 0xFFFF
                    if ($code -eq 32 -or $code -eq 33) { $sharing = $true }
                }
                $ex = $ex.InnerException
            }
            if (-not $sharing) { throw }
            throw 'Another runtime command is active. Retry after it finishes.'
        }
        switch ($Action) {
            'start' { Start-LocalRuntime }
            'stop' { Stop-LocalRuntime }
            'status' { Show-LocalRuntime }
            'restart' { Stop-LocalRuntime; Start-LocalRuntime }
        }
    } finally { if ($lock) { $lock.Dispose() } }
}
