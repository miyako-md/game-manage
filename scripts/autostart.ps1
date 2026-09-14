# A per-project current-user Startup shortcut. No administrator or service needed.
[CmdletBinding(DefaultParameterSetName = 'Status')]
param(
    [Parameter(Mandatory = $true, ParameterSetName = 'Enable')][switch]$Enable,
    [Parameter(Mandatory = $true, ParameterSetName = 'Disable')][switch]$Disable,
    [Parameter(ParameterSetName = 'Status')][switch]$Status
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
try {
    $projectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        $hash = $hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($projectRoot.ToLowerInvariant()))
        $suffix = ([BitConverter]::ToString($hash)).Replace('-', '').Substring(0, 12).ToLowerInvariant()
    } finally { $hasher.Dispose() }
    $startupFolder = [Environment]::GetFolderPath('Startup')
    if (-not $startupFolder) { throw 'Current-user Startup folder is unavailable.' }
    $shortcutPath = Join-Path $startupFolder "GameAssistant-$suffix.lnk"
    $powerShellPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "' +
        (Join-Path $projectRoot 'scripts\start.ps1') + '"'
    $shell = New-Object -ComObject WScript.Shell
    $exists = Test-Path -LiteralPath $shortcutPath
    if ($exists) {
        $shortcut = $shell.CreateShortcut($shortcutPath)
        if ($shortcut.TargetPath -ne $powerShellPath -or $shortcut.Arguments -ne $arguments -or
            $shortcut.WorkingDirectory -ne $projectRoot) {
            throw 'Startup entry at this name has different ownership. It was left unchanged.'
        }
    }
    if ($Enable) {
        if (-not $exists) {
            $shortcut = $shell.CreateShortcut($shortcutPath)
            $shortcut.TargetPath = $powerShellPath
            $shortcut.Arguments = $arguments
            $shortcut.WorkingDirectory = $projectRoot
            $shortcut.Description = 'Game Assistant current-user login startup'
            $shortcut.WindowStyle = 7
            $shortcut.Save()
        }
        # Re-read the persisted shortcut; don't infer success just from Save().
        $saved = $shell.CreateShortcut($shortcutPath)
        if (-not (Test-Path -LiteralPath $shortcutPath) -or $saved.Arguments -ne $arguments -or
            $saved.TargetPath -ne $powerShellPath -or $saved.WorkingDirectory -ne $projectRoot) {
            throw 'Startup shortcut verification failed.'
        }
        Write-Output "Enabled: $shortcutPath"
    } elseif ($Disable) {
        if ($exists) { Remove-Item -LiteralPath $shortcutPath -Force }
        if (Test-Path -LiteralPath $shortcutPath) { throw 'Startup shortcut removal failed.' }
        Write-Output "Disabled: $shortcutPath"
    } elseif ($exists) {
        Write-Output "Enabled: $shortcutPath"
    } else {
        Write-Output "Disabled: $shortcutPath"
    }
} catch { Write-Error $_ -ErrorAction Continue; exit 1 }
