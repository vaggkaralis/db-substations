@echo off
REM Simple build wrapper for SubstationManager
REM Executes the PowerShell build script

echo.
echo ========================================
echo   Substation Manager - Build
echo ========================================
echo.

powershell.exe -ExecutionPolicy Bypass -File "%~dp0build.ps1"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo BUILD FAILED!
    pause
    exit /b 1
)

echo.
pause
