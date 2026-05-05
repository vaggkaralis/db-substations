# Build script for SubstationManager executable
# Ημερομην�ία: Ιανουάριος 2026

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Substation Manager - Build Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$ProjectDir = $PSScriptRoot
$VenvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$DistDir = Join-Path $ProjectDir "dist"
$BuildDir = Join-Path $ProjectDir "build"

if (-Not (Test-Path $VenvPython)) {
    Write-Host "ΣΦΑΛΜΑ: Δεν βρέθηκε το virtual environment στο .venv" -ForegroundColor Red
    Write-Host "Παρακαλώ εκτελέστε πρώτα: python -m venv .venv" -ForegroundColor Yellow
    exit 1
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

& $VenvPython -m PyInstaller @PyInstallerArgs @AddDataArgs DBrun.py

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ΣΦΑΛΜΑ: Το build απέτυχε!" -ForegroundColor Red
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
