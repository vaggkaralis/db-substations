# Build script for SubstationManager executable
# Ημερομην�ία: Ιανουάριος 2026

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Substation Manager - Build Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$ProjectDir = $PSScriptRoot
$DistDir = Join-Path $ProjectDir "dist"
$BuildDir = Join-Path $ProjectDir "build"

function Resolve-VenvPython {
    param(
        [string]$ProjectDir
    )

    $candidatePythons = @()

    function Get-EnvValue {
        param(
            [string]$Name
        )

        $processValue = [Environment]::GetEnvironmentVariable($Name, "Process")
        if (-not [string]::IsNullOrWhiteSpace($processValue)) {
            return $processValue.Trim()
        }

        $userValue = [Environment]::GetEnvironmentVariable($Name, "User")
        if (-not [string]::IsNullOrWhiteSpace($userValue)) {
            return $userValue.Trim()
        }

        $machineValue = [Environment]::GetEnvironmentVariable($Name, "Machine")
        if (-not [string]::IsNullOrWhiteSpace($machineValue)) {
            return $machineValue.Trim()
        }

        return $null
    }

    $explicitPython = $null
    $explicitPython = Get-EnvValue -Name "SUBSTATIONMANAGER_VENV_PYTHON"
    if ($explicitPython) {
        $candidatePythons += $explicitPython
    }

    $explicitVenvDir = $null
    $explicitVenvDir = Get-EnvValue -Name "SUBSTATIONMANAGER_VENV_DIR"
    if ($explicitVenvDir) {
        $candidatePythons += (Join-Path $explicitVenvDir "Scripts\python.exe")
    }

    $activeVenvDir = $null
    $activeVenvDir = Get-EnvValue -Name "VIRTUAL_ENV"
    if ($activeVenvDir) {
        $candidatePythons += (Join-Path $activeVenvDir "Scripts\python.exe")
    }

    $candidatePythons += (Join-Path $ProjectDir ".venv\Scripts\python.exe")

    foreach ($candidate in $candidatePythons) {
        if (-not [string]::IsNullOrWhiteSpace($candidate) -and (Test-Path $candidate)) {
            return (Resolve-Path $candidate).Path
        }
    }

    return $null
}

$VenvPython = Resolve-VenvPython -ProjectDir $ProjectDir

if (-Not (Test-Path $VenvPython)) {
    Write-Host "ΣΦΑΛΜΑ: Δεν βρέθηκε διαθέσιμο virtual environment Python" -ForegroundColor Red
    Write-Host "Ορίστε SUBSTATIONMANAGER_VENV_DIR ή SUBSTATIONMANAGER_VENV_PYTHON για venv εκτός OneDrive," -ForegroundColor Yellow
    Write-Host "ή ενεργοποιήστε ένα venv πριν το build. Fallback παραμένει το .venv του project." -ForegroundColor Yellow
    exit 1
}

Write-Host "Χρήση Python από: $VenvPython" -ForegroundColor Gray

$StaleBuildProcesses = Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='python.exe'" |
    Where-Object {
        $_.ProcessId -ne $PID -and
        $_.CommandLine -and
        $_.CommandLine -like "*$ProjectDir*" -and
        (
            $_.CommandLine -like '*build.ps1*' -or
            $_.CommandLine -like '*PyInstaller*' -or
            $_.CommandLine -like '*PyInstaller\\isolated\\_child.py*'
        )
    }

if ($StaleBuildProcesses) {
    Write-Host "[0/5] Τερματισμός παλαιών διεργασιών build..." -ForegroundColor Yellow
    foreach ($Process in $StaleBuildProcesses) {
        try {
            Stop-Process -Id $Process.ProcessId -Force -ErrorAction Stop
            Write-Host "      ✓ Τερματίστηκε PID $($Process.ProcessId)" -ForegroundColor Green
        } catch {
            Write-Host "      ΠΡΟΕΙΔΟΠΟΙΗΣΗ: Αποτυχία τερματισμού PID $($Process.ProcessId)" -ForegroundColor Yellow
        }
    }
    Write-Host ""
}

Write-Host "[1/5] Καθαρισμός παλαιών αρχείων build..." -ForegroundColor Yellow
if (Test-Path $DistDir) {
    Remove-Item -Path $DistDir -Recurse -Force
    Write-Host "      ✓ Διαγράφηκε: dist/" -ForegroundColor Green
}
if (Test-Path $BuildDir) {
    Remove-Item -Path $BuildDir -Recurse -Force
    Write-Host "      ✓ Διαγράφηκε: build/" -ForegroundColor Green
}
if (Test-Path "SubstationManager.spec") {
    Remove-Item "SubstationManager.spec" -Force
    Write-Host "      ✓ Διαγράφηκε: SubstationManager.spec" -ForegroundColor Green
}

Write-Host ""
Write-Host "[2/5] Έλεγχος εξαρτήσεων..." -ForegroundColor Yellow
& $VenvPython -m pip show pyinstaller kivy pandas openpyxl | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "      ΠΡΟΕΙΔΟΠΟΙΗΣΗ: Ορισμένες εξαρτήσεις λείπουν" -ForegroundColor Red
    Write-Host "      Εγκατάσταση εξαρτήσεων..." -ForegroundColor Yellow
    & $VenvPython -m pip install pyinstaller kivy pandas openpyxl
}
Write-Host "      ✓ Όλες οι εξαρτήσεις είναι εγκατεστημένες" -ForegroundColor Green

Write-Host ""
Write-Host "[3/5] Έναρξη PyInstaller build..." -ForegroundColor Yellow
Write-Host "      (Αυτό μπορεί να διαρκέσει 5-10 λεπτά)" -ForegroundColor Gray

$DataFiles = @(
    "database.py",
    "importers.py",
    "popups.py",
    "templates.py",
    "logo_deddie.png",
    "deddie_logo.png",
    "DejaVuSans.ttf",
    "VERSION",
    "elements_import_template.xlsx",
    "επιθεωρήσεις_template.xlsx",
    "substations.db"
)

$AddDataArgs = @()
foreach ($FileName in $DataFiles) {
    $FilePath = Join-Path $ProjectDir $FileName
    if (Test-Path $FilePath) {
        $AddDataArgs += "--add-data=$FilePath;."
    }
}

$PyInstallerArgs = @(
    "--onedir",
    "--windowed",
    "--noconfirm",
    "--log-level=WARN",
    "--name=SubstationManager",
    "--exclude-module=pytest",
    "--exclude-module=_pytest",
    "--exclude-module=tests",
    "--exclude-module=kivy.tests",
    "--exclude-module=pandas.tests",
    "--exclude-module=numpy._pytesttester"
)

$null = $LASTEXITCODE
& $VenvPython -m PyInstaller @PyInstallerArgs @AddDataArgs DBrun.py
$PyInstallerExitCode = $LASTEXITCODE

if ($PyInstallerExitCode -ne 0) {
    Write-Host ""
    Write-Host "ΣΦΑΛΜΑ: Το build απέτυχε!" -ForegroundColor Red
    Write-Host "      Exit code: $PyInstallerExitCode" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "[4/5] Επαλήθευση εκτελέσιμου..." -ForegroundColor Yellow
$ExePath = Join-Path $DistDir "SubstationManager\SubstationManager.exe"
if (Test-Path $ExePath) {
    $FileInfo = Get-Item $ExePath
    $SizeMB = [math]::Round($FileInfo.Length / 1MB, 2)
    Write-Host "      ✓ Το εκτελέσιμο δημιουργήθηκε επιτυχώς" -ForegroundColor Green
    Write-Host "      Μέγεθος: $SizeMB MB" -ForegroundColor Gray
    Write-Host "      Τοποθεσία: $ExePath" -ForegroundColor Gray
} else {
    Write-Host "      ΣΦΑΛΜΑ: Το εκτελέσιμο δεν βρέθηκε!" -ForegroundColor Red
    Write-Host "      Ελέγξτε τον φάκελο: $DistDir\SubstationManager" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "[5/5] Καθαρισμός προσωρινών αρχείων..." -ForegroundColor Yellow
if (Test-Path $BuildDir) {
    Remove-Item -Path $BuildDir -Recurse -Force
    Write-Host "      ✓ Διαγράφηκε: build/" -ForegroundColor Green
}
if (Test-Path "SubstationManager.spec") {
    Remove-Item "SubstationManager.spec" -Force
    Write-Host "      ✓ Διαγράφηκε: SubstationManager.spec" -ForegroundColor Green
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  BUILD ΟΛΟΚΛΗΡΩΘΗΚΕ ΕΠΙΤΥΧΩΣ!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Το εκτελέσιμο βρίσκεται στο:" -ForegroundColor Cyan
Write-Host "  $ExePath" -ForegroundColor White
Write-Host ""
Write-Host "Για να το εκτελέσετε:" -ForegroundColor Cyan
Write-Host "  1. Μεταβείτε στον φάκελο dist\SubstationManager" -ForegroundColor White
Write-Host "  2. Κάντε διπλό κλικ στο SubstationManager.exe" -ForegroundColor White
Write-Host ""
