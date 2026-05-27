@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_EXE="
set "USER_VENV_DIR="
set "USER_VENV_PYTHON="

for /f "tokens=2,*" %%A in ('reg query HKCU\Environment /v SUBSTATIONMANAGER_VENV_PYTHON 2^>nul ^| findstr /R /C:"SUBSTATIONMANAGER_VENV_PYTHON"') do set "USER_VENV_PYTHON=%%B"
for /f "tokens=2,*" %%A in ('reg query HKCU\Environment /v SUBSTATIONMANAGER_VENV_DIR 2^>nul ^| findstr /R /C:"SUBSTATIONMANAGER_VENV_DIR"') do set "USER_VENV_DIR=%%B"

if defined SUBSTATIONMANAGER_VENV_PYTHON if exist "%SUBSTATIONMANAGER_VENV_PYTHON%" set "PYTHON_EXE=%SUBSTATIONMANAGER_VENV_PYTHON%"
if not defined PYTHON_EXE if defined USER_VENV_PYTHON if exist "%USER_VENV_PYTHON%" set "PYTHON_EXE=%USER_VENV_PYTHON%"
if not defined PYTHON_EXE if defined SUBSTATIONMANAGER_VENV_DIR if exist "%SUBSTATIONMANAGER_VENV_DIR%\Scripts\python.exe" set "PYTHON_EXE=%SUBSTATIONMANAGER_VENV_DIR%\Scripts\python.exe"
if not defined PYTHON_EXE if defined USER_VENV_DIR if exist "%USER_VENV_DIR%\Scripts\python.exe" set "PYTHON_EXE=%USER_VENV_DIR%\Scripts\python.exe"
if not defined PYTHON_EXE if defined VIRTUAL_ENV if exist "%VIRTUAL_ENV%\Scripts\python.exe" set "PYTHON_EXE=%VIRTUAL_ENV%\Scripts\python.exe"
if not defined PYTHON_EXE if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"

if not defined PYTHON_EXE (
	echo Δεν βρέθηκε virtual environment Python.
	echo Ορίστε SUBSTATIONMANAGER_VENV_DIR ή SUBSTATIONMANAGER_VENV_PYTHON για venv εκτός OneDrive,
	echo ή ενεργοποιήστε ένα venv πριν την εκτέλεση.
	exit /b 1
)

echo Χρήση Python από: %PYTHON_EXE%
"%PYTHON_EXE%" DBrun.py