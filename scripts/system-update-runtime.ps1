# Worker-only bridge. The parent holds service.lock for the entire transaction.
param([Parameter(Mandatory=$true)][string]$InstallRoot,
      [Parameter(Mandatory=$true)][ValidateSet('verify','stop','start')][string]$Action,
      [string]$JobId)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
try {
    . (Join-Path $PSScriptRoot 'runtime-common.ps1')
    Initialize-Runtime -Port 8010 -Sandbox $false -InstallRoot $InstallRoot
    if ($Action -ne 'verify') {
        if ($JobId -cnotmatch '^[a-f0-9]{32}$') { throw 'Update transaction required.' }
        $journalPath = Join-Path $script:ProjectRoot 'data\system-update\private\journal.json'
        if ((Get-Item -LiteralPath $journalPath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Redirected transaction journal.' }
        $journal = Get-Content -LiteralPath $journalPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $parentId = (Get-CimInstance Win32_Process -Filter "ProcessId = $PID").ParentProcessId
        if ($journal.job_id -cne $JobId -or [int]$journal.worker_pid -ne [int]$parentId -or $journal.phase -notin @('stopping','backing_up','activating','restarting','verifying')) { throw 'Update transaction ownership mismatch.' }
    }
    switch ($Action) {
        'verify' {
            $managed = Get-VerifiedProcess (Read-State)
            if (-not $managed -or -not (Test-OwnedListener $managed.Id) -or -not (Test-Health)) { throw 'Managed runtime must be healthy before updating.' }
        }
        'stop' { Stop-LocalRuntime }
        'start' { Start-LocalRuntime }
    }
} catch {
    # Do not echo config/process command lines or subprocess output.
    Write-Error 'Managed update runtime operation failed.' -ErrorAction Continue
    exit 1
}
