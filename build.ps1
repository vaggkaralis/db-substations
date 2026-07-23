# Build script for SubstationManager executable
# Ημερομην�ία: Ιανουάριος 2026

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Substation Manager - Build Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$ProjectDir = $PSScriptRoot
$BuildDir = Join-Path $ProjectDir "build"
$SpecPath = Join-Path $ProjectDir "SubstationManager.spec"
$OutputRoot = "C:\"
$InstallDir = Join-Path $OutputRoot "SubstationManager"
$SignToolDefaultPath = "C:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe"
$SignTimestampUrl = "http://timestamp.digicert.com"

function Resolve-ConfigValue {
    param(
        [string]$Name,
        [string]$DefaultValue = $null
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

    return $DefaultValue
}

function Resolve-SignToolPath {
    $explicitPath = Resolve-ConfigValue -Name "SUBSTATIONMANAGER_SIGNTOOL"
    if ($explicitPath -and (Test-Path $explicitPath)) {
        return (Resolve-Path $explicitPath).Path
    }

    if (Test-Path $SignToolDefaultPath) {
        return $SignToolDefaultPath
    }

    $signtoolCommand = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($signtoolCommand) {
        return $signtoolCommand.Path
    }

    return $null
}

function Resolve-AutoCodeSigningThumbprint {
    $now = Get-Date
    $candidate = Get-ChildItem Cert:\CurrentUser\My -ErrorAction SilentlyContinue |
        Where-Object {
            $_.HasPrivateKey -and
            $_.NotAfter -gt $now -and
            ($_.EnhancedKeyUsageList | Where-Object { $_.ObjectId -eq "1.3.6.1.5.5.7.3.3" })
        } |
        Sort-Object NotAfter -Descending |
        Select-Object -First 1

    if ($candidate) {
        return $candidate.Thumbprint
    }

    return $null
}

function Sign-Executable {
    param(
        [string]$ExecutablePath
    )

    $enableSigning = Resolve-ConfigValue -Name "SUBSTATIONMANAGER_SIGN_ENABLED" -DefaultValue "false"
    if ($enableSigning.ToLowerInvariant() -ne "true") {
        Write-Host "      (Η ψηφιακή υπογραφή παραλείφθηκε - SUBSTATIONMANAGER_SIGN_ENABLED != true)" -ForegroundColor DarkGray
        return
    }

    $signToolPath = Resolve-SignToolPath
    if (-not $signToolPath) {
        Write-Host "      ΣΦΑΛΜΑ: Δεν βρέθηκε signtool.exe" -ForegroundColor Red
        Write-Host "      Ορίστε SUBSTATIONMANAGER_SIGNTOOL ή εγκαταστήστε Windows SDK SignTool." -ForegroundColor Yellow
        exit 1
    }

    $certPfxPath = Resolve-ConfigValue -Name "SUBSTATIONMANAGER_CERT_PFX"
    $certPassword = Resolve-ConfigValue -Name "SUBSTATIONMANAGER_CERT_PASSWORD"
    $certThumbprint = Resolve-ConfigValue -Name "SUBSTATIONMANAGER_CERT_THUMBPRINT"
    $timestampUrl = Resolve-ConfigValue -Name "SUBSTATIONMANAGER_SIGN_TIMESTAMP_URL" -DefaultValue $SignTimestampUrl

    $signArgs = @("sign", "/fd", "SHA256", "/td", "SHA256")
    if (-not [string]::IsNullOrWhiteSpace($timestampUrl)) {
        $signArgs += @("/tr", $timestampUrl)
    }

    if ($certPfxPath) {
        if (-not (Test-Path $certPfxPath)) {
            Write-Host "      ΣΦΑΛΜΑ: Δεν βρέθηκε το αρχείο πιστοποιητικού: $certPfxPath" -ForegroundColor Red
            exit 1
        }

        $signArgs += @("/f", $certPfxPath)
        if (-not [string]::IsNullOrWhiteSpace($certPassword)) {
            $signArgs += @("/p", $certPassword)
        }
    } elseif ($certThumbprint) {
        $signArgs += @("/sha1", $certThumbprint, "/sm")
    } else {
        $autoThumbprint = Resolve-AutoCodeSigningThumbprint
        if ($autoThumbprint) {
            Write-Host "      ✓ Βρέθηκε αυτόματα πιστοποιητικό Code Signing στο CurrentUser\\My" -ForegroundColor Green
            $signArgs += @("/sha1", $autoThumbprint)
        } else {
            Write-Host "      ΣΦΑΛΜΑ: Δεν βρέθηκε πιστοποιητικό Code Signing." -ForegroundColor Red
            Write-Host "      Ζητήστε από το IT code-signing certificate (EKU 1.3.6.1.5.5.7.3.3)" -ForegroundColor Yellow
            Write-Host "      στο CurrentUser\\My με private key ή δώστε PFX στο SUBSTATIONMANAGER_CERT_PFX." -ForegroundColor Yellow
            exit 1
        }
    }

    $signArgs += $ExecutablePath
    & $signToolPath @signArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "      ΣΦΑΛΜΑ: Η υπογραφή του εκτελέσιμου απέτυχε." -ForegroundColor Red
        Write-Host "      Exit code: $LASTEXITCODE" -ForegroundColor Yellow
        exit 1
    }

    $signature = Get-AuthenticodeSignature -FilePath $ExecutablePath
    if ($signature.Status -ne "Valid") {
        Write-Host "      ΣΦΑΛΜΑ: Η υπογραφή ολοκληρώθηκε αλλά δεν είναι έγκυρη." -ForegroundColor Red
        Write-Host "      Κατάσταση: $($signature.Status)" -ForegroundColor Yellow
        exit 1
    }

    Write-Host "      ✓ Το εκτελέσιμο υπογράφηκε επιτυχώς" -ForegroundColor Green
    Write-Host "      Subject: $($signature.SignerCertificate.Subject)" -ForegroundColor Gray
}

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

function Test-PythonModule {
    param(
        [string]$PythonExe,
        [string]$ModuleName
    )

    & $PythonExe -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('$ModuleName') else 1)" | Out-Null
    return ($LASTEXITCODE -eq 0)
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
if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir | Out-Null
    Write-Host "      ✓ Δημιουργήθηκε: $InstallDir" -ForegroundColor Green
}
if (Test-Path $BuildDir) {
    Remove-Item -Path $BuildDir -Recurse -Force
    Write-Host "      ✓ Διαγράφηκε: build/" -ForegroundColor Green
}
if (Test-Path $SpecPath) {
    Remove-Item $SpecPath -Force
    Write-Host "      ✓ Διαγράφηκε: SubstationManager.spec" -ForegroundColor Green
}

Write-Host ""
Write-Host "[2/5] Έλεγχος εξαρτήσεων..." -ForegroundColor Yellow
 $requiredModules = @(
    @{ module = "PyInstaller"; package = "pyinstaller" },
    @{ module = "kivy"; package = "kivy" },
    @{ module = "pandas"; package = "pandas" },
    @{ module = "openpyxl"; package = "openpyxl" }
)

$missingPackages = @()
foreach ($dependency in $requiredModules) {
    if (-not (Test-PythonModule -PythonExe $VenvPython -ModuleName $dependency.module)) {
        $missingPackages += $dependency.package
    }
}

if ($missingPackages.Count -gt 0) {
    Write-Host "      ΠΡΟΕΙΔΟΠΟΙΗΣΗ: Λείπουν εξαρτήσεις: $($missingPackages -join ', ')" -ForegroundColor Red
    Write-Host "      Εγκατάσταση εξαρτήσεων..." -ForegroundColor Yellow
    & $VenvPython -m pip install $missingPackages

    $stillMissing = @()
    foreach ($dependency in $requiredModules) {
        if (-not (Test-PythonModule -PythonExe $VenvPython -ModuleName $dependency.module)) {
            $stillMissing += $dependency.package
        }
    }

    if ($stillMissing.Count -gt 0) {
        Write-Host "      ΣΦΑΛΜΑ: Αποτυχία εγκατάστασης εξαρτήσεων: $($stillMissing -join ', ')" -ForegroundColor Red
        exit 1
    }
}
Write-Host "      ✓ Όλες οι εξαρτήσεις είναι εγκατεστημένες" -ForegroundColor Green

Write-Host ""
Write-Host "[3/5] Έναρξη PyInstaller build..." -ForegroundColor Yellow
Write-Host "      (Αυτό μπορεί να διαρκέσει 5-10 λεπτά)" -ForegroundColor Gray

# Ensure Kivy optional provider probing stays silent during build analysis.
$env:KIVY_NO_CONSOLELOG = "1"
$env:KIVY_LOG_LEVEL = "error"
$env:KIVY_NO_ARGS = "1"

$null = $LASTEXITCODE
& $VenvPython (Join-Path $ProjectDir "build_exe.py") 2>&1 |
    Where-Object {
        $line = $_.ToString()
        -not (
            $line -match "CRITICAL:\s+Spelling" -or
            $line -match "CRITICAL:\s+Camera" -or
            $line -match "\[CRITICAL\]\s*\[Spelling" -or
            $line -match "\[CRITICAL\]\s*\[Camera" -or
            $line -match "ModuleNotFoundError:\s+No module named 'enchant'" -or
            $line -match "ModuleNotFoundError:\s+No module named 'picamera'" -or
            $line -match "ModuleNotFoundError:\s+No module named 'gi'" -or
            $line -match "ModuleNotFoundError:\s+No module named 'cv2'" -or
            $line -match "spelling_enchant\.py" -or
            $line -match "camera_picamera\.py" -or
            $line -match "camera_gi\.py" -or
            $line -match "camera_opencv\.py"
        )
    } |
    ForEach-Object {
        Write-Host "      $_"
    }
$PyInstallerExitCode = $LASTEXITCODE

if ($PyInstallerExitCode -ne 0) {
    Write-Host ""
    Write-Host "ΣΦΑΛΜΑ: Το build απέτυχε!" -ForegroundColor Red
    Write-Host "      Exit code: $PyInstallerExitCode" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "[4/5] Επαλήθευση εκτελέσιμου..." -ForegroundColor Yellow
$ExePath = Join-Path $InstallDir "SubstationManager.exe"
if (Test-Path $ExePath) {
    $FileInfo = Get-Item $ExePath
    $SizeMB = [math]::Round($FileInfo.Length / 1MB, 2)
    $VersionInfo = $FileInfo.VersionInfo
    Write-Host "      ✓ Το εκτελέσιμο δημιουργήθηκε επιτυχώς" -ForegroundColor Green
    Write-Host "      Μέγεθος: $SizeMB MB" -ForegroundColor Gray
    Write-Host "      Τοποθεσία: $ExePath" -ForegroundColor Gray
    Write-Host "      Εταιρεία: $($VersionInfo.CompanyName)" -ForegroundColor Gray
    Write-Host "      Προϊόν: $($VersionInfo.ProductName)" -ForegroundColor Gray
    Write-Host "      Έκδοση: $($VersionInfo.ProductVersion)" -ForegroundColor Gray
} else {
    Write-Host "      ΣΦΑΛΜΑ: Το εκτελέσιμο δεν βρέθηκε!" -ForegroundColor Red
    Write-Host "      Ελέγξτε τον φάκελο: $InstallDir" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "[5/5] Καθαρισμός προσωρινών αρχείων..." -ForegroundColor Yellow
if (Test-Path $BuildDir) {
    Remove-Item -Path $BuildDir -Recurse -Force
    Write-Host "      ✓ Διαγράφηκε: build/" -ForegroundColor Green
}
if (Test-Path $SpecPath) {
    Remove-Item $SpecPath -Force
    Write-Host "      ✓ Διαγράφηκε: SubstationManager.spec" -ForegroundColor Green
}

Write-Host ""
Write-Host "[6/6] Ψηφιακή υπογραφή εκτελέσιμου..." -ForegroundColor Yellow
Sign-Executable -ExecutablePath $ExePath

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  BUILD ΟΛΟΚΛΗΡΩΘΗΚΕ ΕΠΙΤΥΧΩΣ!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Το εκτελέσιμο βρίσκεται στο:" -ForegroundColor Cyan
Write-Host "  $ExePath" -ForegroundColor White
Write-Host ""
Write-Host "Για να το εκτελέσετε:" -ForegroundColor Cyan
Write-Host "  1. Μεταβείτε στον φάκελο C:\SubstationManager" -ForegroundColor White
Write-Host "  2. Κάντε διπλό κλικ στο SubstationManager.exe" -ForegroundColor White
Write-Host ""
Write-Host "Ρυθμίσεις υπογραφής (environment variables):" -ForegroundColor Cyan
Write-Host "  SUBSTATIONMANAGER_SIGN_ENABLED=true" -ForegroundColor White
Write-Host "  SUBSTATIONMANAGER_CERT_PFX=<path to .pfx>" -ForegroundColor White
Write-Host "  SUBSTATIONMANAGER_CERT_PASSWORD=<pfx password>" -ForegroundColor White
Write-Host "  ή SUBSTATIONMANAGER_CERT_THUMBPRINT=<cert thumbprint>" -ForegroundColor White
Write-Host "  προαιρετικά: SUBSTATIONMANAGER_SIGN_TIMESTAMP_URL=<RFC3161 URL>" -ForegroundColor White
Write-Host ""
