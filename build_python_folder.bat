@echo off
setlocal EnableExtensions
set "BUILD_EXIT=0"

cd /d "%~dp0"

set "SRC_DIR=%~dp0."
set "OUT_ROOT=C:\SubstationManager"
set "OUT_DIR=%OUT_ROOT%\python"

echo ========================================
echo   Substation Manager - Python Folder Build
echo ========================================
echo.

if exist "%OUT_DIR%" (
    echo [1/4] Cleaning old output folder...
    rmdir /s /q "%OUT_DIR%"
)

if not exist "%OUT_ROOT%" mkdir "%OUT_ROOT%"
mkdir "%OUT_DIR%"

echo [2/4] Copying project files...
robocopy "%SRC_DIR%" "%OUT_DIR%" /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP /XD ".git" ".venv" "build" "dist" "__pycache__" ".pytest_cache" ".ruff_cache" ".vscode" "backups" "backups_auto" "user_data" /XF "*.pyc" "*.pyo" "SubstationManager.spec" "build_*.log" "pyinstaller_run.log"
set "ROBO_EXIT=%ERRORLEVEL%"
if %ROBO_EXIT% GEQ 8 (
    echo.
    echo ERROR: File copy failed with robocopy exit code %ROBO_EXIT%.
    set "BUILD_EXIT=1"
    goto :final
)

echo [3/4] Creating single-file launcher...
set "LAUNCHER=%OUT_DIR%\Start_SubstationManager.bat"
(
    echo @echo off
    echo if /I "%%~1"=="--runmain" goto :runmain
    echo.
    echo setlocal EnableExtensions EnableDelayedExpansion
    echo title Substation Manager Launcher
    echo cd /d "%%~dp0"
    echo echo === Substation Manager Launcher Starting ===
    echo.
    echo set "LOG_FILE=%%~dp0launcher_run.log"
    echo ^> "%%LOG_FILE%%" echo [%%date%% %%time%%] Launcher started
    echo if errorlevel 1 set "LOG_FILE=%%TEMP%%\SubstationManager_launcher_run.log"
    echo ^> "%%LOG_FILE%%" echo [%%date%% %%time%%] Launcher started
    echo echo Log file: %%LOG_FILE%%
    echo set "PS_RUNNER=%%~dp0launcher_runner.ps1"
    echo if not exist "%%PS_RUNNER%%" ^(
    echo ^    echo Missing launcher runner script: %%PS_RUNNER%%
    echo ^    set "APP_EXIT=1"
    echo ^    goto :finalize
    echo ^)
    echo "%%SystemRoot%%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%%PS_RUNNER%%" -BatchPath "%%~f0" -LogPath "%%LOG_FILE%%"
    echo set "APP_EXIT=%%ERRORLEVEL%%"
    echo.
    echo :finalize
    echo if %%APP_EXIT%% EQU 0 ^(
    echo ^    echo Application exited successfully.
    echo ^) else ^(
    echo ^    echo Application exited with error code %%APP_EXIT%%.
    echo ^    echo See launcher log: %%LOG_FILE%%
    echo ^)
    echo.
    echo pause
    echo exit /b %%APP_EXIT%%
    echo.
    echo :runmain
    echo call :main
    echo exit /b %%ERRORLEVEL%%
    echo.
    echo :main
    echo set "VENV_DIR=%%CD%%\.venv"
    echo.
    echo if exist "%%VENV_DIR%%\Scripts\python.exe" ^(
    echo ^    call :check_venv_py312
    echo ^    if errorlevel 1 ^(
    echo ^        echo Existing virtual environment is not Python 3.12. Recreating...
    echo ^        rmdir /s /q "%%VENV_DIR%%"
    echo ^    ^)
    echo ^)
    echo.
    echo if not exist "%%VENV_DIR%%\Scripts\python.exe" ^(
    echo ^    call :create_venv
    echo ^    if errorlevel 1 exit /b 1
    echo ^)
    echo.
    echo if not exist "%%VENV_DIR%%\.deps_ok" ^(
    echo ^    echo Installing dependencies - first run...
    echo ^    "%%VENV_DIR%%\Scripts\python.exe" -m pip install --upgrade pip
    echo ^    if errorlevel 1 ^(
    echo ^        echo Failed to update pip.
    echo ^        exit /b 1
    echo ^    ^)
    echo ^    "%%VENV_DIR%%\Scripts\python.exe" -m pip install -r requirements.txt
    echo ^    if errorlevel 1 ^(
    echo ^        echo Failed to install dependencies.
    echo ^        exit /b 1
    echo ^    ^)
    echo ^    type nul ^> "%%VENV_DIR%%\.deps_ok"
    echo ^)
    echo.
    echo echo Launching Substation Manager...
    echo "%%VENV_DIR%%\Scripts\python.exe" DBrun.py
    echo exit /b %%ERRORLEVEL%%
    echo.
    echo :check_venv_py312
    echo "%%VENV_DIR%%\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info[:2]==^(3,12^) else 1)" ^>nul 2^>nul
    echo if not errorlevel 1 exit /b 0
    echo exit /b 1
    echo.
    echo :create_venv
    echo py -3.12 -c "import sys" ^>nul 2^>nul
    echo if not errorlevel 1 goto :create_venv_py312
    echo.
    echo where python ^>nul 2^>nul
    echo if errorlevel 1 ^(
    echo ^    echo Python 3.12 was not found on this machine.
    echo ^    echo Please install Python 3.12 and run this file again.
    echo ^    exit /b 1
    echo ^)
    echo.
    echo python -c "import sys; sys.exit(0 if sys.version_info[:2]==^(3,12^) else 1)" ^>nul 2^>nul
    echo if errorlevel 1 ^(
    echo ^    echo Detected system Python version is not 3.12.
    echo ^    echo This app currently requires Python 3.12 because of Kivy dependency compatibility.
    echo ^    echo Install Python 3.12 and rerun this launcher.
    echo ^    exit /b 1
    echo ^)
    echo.
    echo echo Creating local virtual environment with Python 3.12...
    echo python -m venv "%%VENV_DIR%%"
    echo if errorlevel 1 ^(
    echo ^    echo Failed to create virtual environment.
    echo ^    exit /b 1
    echo ^)
    echo exit /b 0
    echo.
    echo :create_venv_py312
    echo echo Creating local virtual environment with Python 3.12...
    echo py -3.12 -m venv "%%VENV_DIR%%"
    echo if errorlevel 1 ^(
    echo ^    echo Failed to create virtual environment.
    echo ^    exit /b 1
    echo ^)
    echo exit /b 0
) > "%LAUNCHER%"

set "PS_RUNNER=%OUT_DIR%\launcher_runner.ps1"
(
    echo param(
    echo ^    [Parameter^(Mandatory = $true^)]
    echo ^    [string]$BatchPath,
    echo.
    echo ^    [Parameter^(Mandatory = $true^)]
    echo ^    [string]$LogPath
    echo ^)
    echo.
    echo try {
    echo ^    Start-Transcript -Path $LogPath -Append
    echo } catch {
    echo ^    Write-Host "Transcript could not be started: $($_.Exception.Message)"
    echo }
    echo cmd.exe /d /c ""$BatchPath" --runmain"
    echo $ec = $LASTEXITCODE
    echo try {
    echo ^    Stop-Transcript
    echo } catch {
    echo ^    # Ignore if transcript was never started.
    echo }
    echo exit $ec
) > "%PS_RUNNER%"

echo [4/4] Done.
echo.
echo Output folder:
echo   %OUT_DIR%
echo.
echo End-user action:
echo   Double-click Start_SubstationManager.bat inside that folder.
echo.

:final
if %BUILD_EXIT% EQU 0 (
    echo Build completed successfully.
) else (
    echo Build completed with errors.
)
pause
exit /b %BUILD_EXIT%
