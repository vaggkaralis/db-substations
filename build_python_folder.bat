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

echo [1/4] Preparing output folder...
if not exist "%OUT_ROOT%" mkdir "%OUT_ROOT%"
if not exist "%OUT_DIR%" mkdir "%OUT_DIR%"

echo [2/4] Copying project files...
robocopy "%SRC_DIR%" "%OUT_DIR%" /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP /XD ".git" ".venv" "build" "dist" "__pycache__" ".pytest_cache" ".ruff_cache" ".vscode" "backups" "backups_auto" "user_data" "tests" "tools" "00_Assitive" ".VSCodeCounter" /XF "*.pyc" "*.pyo" "SubstationManager.spec" "build_*.log" "pyinstaller_run.log" ".coverage" "pytest*.txt" "app_crash.log" "faulthandler.log" "substation_asset_maintenance.accdb"
set "ROBO_EXIT=%ERRORLEVEL%"
if %ROBO_EXIT% GEQ 8 (
    echo.
    echo ERROR: File copy failed with robocopy exit code %ROBO_EXIT%.
    set "BUILD_EXIT=1"
    goto :final
)

echo [2b/4] Removing non-runtime artifacts from output...
if exist "%OUT_DIR%\00_Assitive" rmdir /s /q "%OUT_DIR%\00_Assitive"
if exist "%OUT_DIR%\tests" rmdir /s /q "%OUT_DIR%\tests"
if exist "%OUT_DIR%\tools" rmdir /s /q "%OUT_DIR%\tools"
if exist "%OUT_DIR%\.VSCodeCounter" rmdir /s /q "%OUT_DIR%\.VSCodeCounter"
if exist "%OUT_DIR%\__pycache__" rmdir /s /q "%OUT_DIR%\__pycache__"
if exist "%OUT_DIR%\substation_asset_maintenance.accdb" del /q "%OUT_DIR%\substation_asset_maintenance.accdb"
if exist "%OUT_DIR%\.coverage" del /q "%OUT_DIR%\.coverage"
if exist "%OUT_DIR%\pytest_android_draft_out.txt" del /q "%OUT_DIR%\pytest_android_draft_out.txt"
if exist "%OUT_DIR%\pytest_out.txt" del /q "%OUT_DIR%\pytest_out.txt"
if exist "%OUT_DIR%\pytest_output.txt" del /q "%OUT_DIR%\pytest_output.txt"
if exist "%OUT_DIR%\app_crash.log" del /q "%OUT_DIR%\app_crash.log"
if exist "%OUT_DIR%\faulthandler.log" del /q "%OUT_DIR%\faulthandler.log"

echo [3/4] Creating single-file launcher...
set "LAUNCHER=%OUT_DIR%\00_Start_SubstationManager.bat"
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
    echo ^    exit /b 0
    echo ^) else ^(
    echo ^    echo Application exited with error code %%APP_EXIT%%.
    echo ^    echo See launcher log: %%LOG_FILE%%
    echo ^    pause
    echo ^    exit /b %%APP_EXIT%%
    echo ^)
    echo.
    echo.
    echo :runmain
    echo call :main
    echo exit /b %%ERRORLEVEL%%
    echo.
    echo :main
    echo set "VENV_DIR=%%CD%%\.venv"
    echo set "PY_RUNTIME_CFG=%%CD%%\python_runtime.conf"
    echo set "PYTHON_EXE_OVERRIDE="
    echo call :load_python_runtime_config
    echo if errorlevel 1 exit /b 1
    echo.
    echo if exist "%%VENV_DIR%%\Scripts\python.exe" ^(
    echo ^    call :check_venv_py312
    echo ^    if errorlevel 1 ^(
    echo ^        echo Existing virtual environment is not Python 3.12/3.13. Recreating...
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
    echo ^    call :prune_venv_runtime
    echo ^    if errorlevel 1 exit /b 1
    echo ^    type nul ^> "%%VENV_DIR%%\.deps_ok"
    echo ^)
    echo if not exist "%%VENV_DIR%%\.pruned_ok" ^(
    echo ^    call :prune_venv_runtime
    echo ^    if errorlevel 1 exit /b 1
    echo ^    type nul ^> "%%VENV_DIR%%\.pruned_ok"
    echo ^)
    echo.
    echo echo Launching Substation Manager...
    echo "%%VENV_DIR%%\Scripts\python.exe" DBrun.py
    echo exit /b %%ERRORLEVEL%%
    echo.
    echo :load_python_runtime_config
    echo if not exist "%%PY_RUNTIME_CFG%%" exit /b 0
    echo for /f "usebackq tokens=1,* delims==" %%%%A in ("%%PY_RUNTIME_CFG%%"^) do ^(
    echo ^    set "_K=%%%%~A"
    echo ^    set "_V=%%%%~B"
    echo ^    if /I "!_K!"=="PYTHON_EXE" set "PYTHON_EXE_OVERRIDE=!_V!"
    echo ^)
    echo if defined PYTHON_EXE_OVERRIDE if not exist "%%PYTHON_EXE_OVERRIDE%%" ^(
    echo ^    echo Configured PYTHON_EXE does not exist: %%PYTHON_EXE_OVERRIDE%%
    echo ^    exit /b 1
    echo ^)
    echo exit /b 0
    echo.
    echo :check_venv_py312
    echo if exist "%%VENV_DIR%%\pyvenv.cfg" ^(
    echo ^    findstr /R /C:"^version *= *3\.12\." /C:"^version *= *3\.13\." "%%VENV_DIR%%\pyvenv.cfg" ^>nul 2^>nul
    echo ^    if not errorlevel 1 exit /b 0
    echo ^)
    echo "%%VENV_DIR%%\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info[:2] in ^((3,12^),(3,13^)^) else 1)" ^>nul 2^>nul
    echo if not errorlevel 1 exit /b 0
    echo exit /b 1
    echo.
    echo :prune_venv_runtime
    echo set "SP_DIR=%%VENV_DIR%%\Lib\site-packages"
    echo if not exist "%%SP_DIR%%" exit /b 0
    echo echo Pruning optional package test and cache files...
    echo if exist "%%SP_DIR%%\pandas\tests" rmdir /s /q "%%SP_DIR%%\pandas\tests"
    echo if exist "%%SP_DIR%%\numpy\tests" rmdir /s /q "%%SP_DIR%%\numpy\tests"
    echo if exist "%%SP_DIR%%\PIL\Tests" rmdir /s /q "%%SP_DIR%%\PIL\Tests"
    echo if exist "%%SP_DIR%%\reportlab\tests" rmdir /s /q "%%SP_DIR%%\reportlab\tests"
    echo if exist "%%SP_DIR%%\pythonwin" rmdir /s /q "%%SP_DIR%%\pythonwin"
    echo if exist "%%SP_DIR%%\PyWin32.chm" del /q "%%SP_DIR%%\PyWin32.chm"
    echo for /r "%%SP_DIR%%" %%%%D in (__pycache__^) do @if exist "%%%%D" rmdir /s /q "%%%%D"
    echo for /r "%%SP_DIR%%" %%%%F in (*.pyc^) do @if exist "%%%%F" del /q "%%%%F"
    echo exit /b 0
    echo.
    echo :create_venv
    echo if defined PYTHON_EXE_OVERRIDE ^(
    echo ^    call :check_python_supported "%%PYTHON_EXE_OVERRIDE%%"
    echo ^    if errorlevel 1 exit /b 1
    echo ^    echo Creating local virtual environment with configured Python 3.12/3.13...
    echo ^    "%%PYTHON_EXE_OVERRIDE%%" -m venv "%%VENV_DIR%%"
    echo ^    if errorlevel 1 ^(
    echo ^        echo Failed to create virtual environment.
    echo ^        exit /b 1
    echo ^    ^)
    echo ^    exit /b 0
    echo ^)
    echo py -3.13 -c "import sys" ^>nul 2^>nul
    echo if not errorlevel 1 goto :create_venv_py313
    echo py -3.12 -c "import sys" ^>nul 2^>nul
    echo if not errorlevel 1 goto :create_venv_py312
    echo.
    echo where python ^>nul 2^>nul
    echo if errorlevel 1 ^(
    echo ^    echo Python 3.12 or 3.13 was not found on this machine.
    echo ^    echo Please install Python 3.12 or 3.13 and run this file again.
    echo ^    exit /b 1
    echo ^)
    echo.
    echo python -c "import sys; sys.exit(0 if sys.version_info[:2] in ^((3,12^),(3,13^)^) else 1)" ^>nul 2^>nul
    echo if errorlevel 1 ^(
    echo ^    echo Detected system Python version is not 3.12 or 3.13.
    echo ^    echo Optional fix: edit %%PY_RUNTIME_CFG%% and set PYTHON_EXE to your Python 3.12/3.13 path.
    echo ^    echo This app currently requires Python 3.12 or 3.13 because of Kivy dependency compatibility.
    echo ^    echo Install Python 3.12 or 3.13 and rerun this launcher.
    echo ^    exit /b 1
    echo ^)
    echo.
    echo echo Creating local virtual environment with Python 3.12/3.13...
    echo python -m venv "%%VENV_DIR%%"
    echo if errorlevel 1 ^(
    echo ^    echo Failed to create virtual environment.
    echo ^    exit /b 1
    echo ^)
    echo exit /b 0
    echo.
    echo :create_venv_py313
    echo echo Creating local virtual environment with Python 3.13...
    echo py -3.13 -m venv "%%VENV_DIR%%"
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
    echo.
    echo :check_python_supported
    echo set "_PY_CMD=%%~1"
    echo if "%%_PY_CMD%%"=="" ^(
    echo ^    set "_PY_CMD=python"
    echo ^)
    echo "%%_PY_CMD%%" -c "import sys; sys.exit(0 if sys.version_info[:2] in ^((3,12^),(3,13^)^) else 1)" ^>nul 2^>nul
    echo if errorlevel 1 ^(
    echo ^    echo Configured Python is not version 3.12/3.13: %%_PY_CMD%%
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

set "PY_RUNTIME_CFG=%OUT_DIR%\python_runtime.conf"
if not exist "%PY_RUNTIME_CFG%" (
    (
        echo ; Substation Manager Python runtime override
        echo ; Set absolute path to Python 3.12 or 3.13 executable when auto-detection fails.
        echo ; Example: PYTHON_EXE=C:\Users\YourUser\AppData\Local\Programs\Python\Python313\python.exe
        echo PYTHON_EXE=
    ) > "%PY_RUNTIME_CFG%"
)

echo [4/4] Done.
echo.
echo Output folder:
echo   %OUT_DIR%
echo.
echo End-user action:
echo   Double-click 00_Start_SubstationManager.bat inside that folder.
echo.

:final
if %BUILD_EXIT% EQU 0 (
    echo Build completed successfully.
) else (
    echo Build completed with errors.
)
pause
exit /b %BUILD_EXIT%
