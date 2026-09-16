@echo off
setlocal
title Game Assistant Launcher
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launch.ps1" %*
if errorlevel 1 (
    echo.
    echo Failed to start. See the error above.
    pause
    exit /b 1
)
exit /b 0
