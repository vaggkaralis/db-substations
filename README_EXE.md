# Substation Manager - Εκτελέσιμο Windows

## Δημιουργία Εκτελέσιμου (Build)

### Μέθοδος 1: Απλή Εκτέλεση (Συνιστάται)

1. Κάντε **διπλό κλικ** στο αρχείο `build.bat`
2. Περιμένετε 5-10 λεπτά για την ολοκλήρωση
3. Το εκτελέσιμο θα βρίσκεται στο `dist\SubstationManager.exe`

### Μέθοδος 2: PowerShell Script

```powershell
.\build.ps1
```

### Μέθοδος 3: Χειροκίνητη Εκτέλεση

```powershell
& ".venv\Scripts\python.exe" -m PyInstaller --onefile --windowed --name="SubstationManager" --add-data="database.py;." --add-data="importers.py;." --add-data="popups.py;." --add-data="templates.py;." DBrun.py
```

## Τοποθεσία Εκτελέσιμου

Μετά την ολοκλήρωση της κατασκευής:
```
dist\SubstationManager.exe
```

## Εκτέλεση της Εφαρμογής

1. Βρείτε το αρχείο `SubstationManager.exe` στον φάκελο `dist\`
2. Κάντε **δεξί κλικ** → **Run as Administrator** (αν χρειάζεται)
3. Η εφαρμογή θα δημιουργήσει αυτόματα τη βάση δεδομένων `substations.db` δίπλα στο .exe

### Αντιμετώπιση Προβλημάτων

#### Πρόβλημα: "Το αρχείο δεν μπορεί να εκτελεστεί"

**Λύση 1: Windows SmartScreen**
- Κάντε κλικ στο "More info"
- Επιλέξτε "Run anyway"

**Λύση 2: Antivirus/Windows Defender**
- Προσθέστε εξαίρεση για το `SubstationManager.exe`
- Διαδρομή: Settings → Update & Security → Windows Security → Virus & threat protection → Manage settings → Exclusions

**Λύση 3: Εκτέλεση ως Διαχειριστής**
- Δεξί κλικ στο .exe → "Run as Administrator"

**Λύση 4: Έλεγχος ακεραιότητας**
```powershell
Get-FileHash dist\SubstationManager.exe -Algorithm SHA256
```

#### Πρόβλημα: "Missing DLL" ή "Cannot start"

- Βεβαιωθείτε ότι έχετε τα Windows Visual C++ Redistributables:
  - [Κατεβάστε από Microsoft](https://aka.ms/vs/17/release/vc_redist.x64.exe)

#### Πρόβλημα: Η εφαρμογή κλείνει αμέσως

- Εκτελέστε από Command Prompt για να δείτε μηνύματα λάθους:
```cmd
cd dist
SubstationManager.exe
```

## Χαρακτηριστικά

- **Προσθήκη υποσταθμών και στοιχείων**: Προσθήκη νέων υποσταθμών ή στοιχείων
- **Εμφάνιση βάσης**: Προβολή όλων των υποσταθμών ή συγκεκριμένου
- **Εισαγωγή Υποσταθμών/Στοιχείων**: Μαζική εισαγωγή από Excel (.xlsx) ή CSV
- **Επεξεργασία**: Τροποποίηση τοποθεσίας και ημερομηνίας ανάληψης
- **Διαγραφή**: Διαγραφή μεμονωμένων εγγραφών ή όλης της βάσης

## Σημειώσεις

- Το εκτελέσιμο δεν απαιτεί εγκατάσταση Python
- Όλες οι εξαρτήσεις είναι ενσωματωμένες
- Η βάση δεδομένων δημιουργείται αυτόματα κατά την πρώτη εκτέλεση
- Για εισαγωγή δεδομένων, χρησιμοποιήστε τα templates που παράγονται μέσω της εφαρμογής

## Πότε να ξανακάνετε Build

### Κάντε νέο build όταν:
- ✅ Αλλάξετε οποιοδήποτε αρχείο Python (.py)
- ✅ Προσθέσετε νέες δυνατότητες
- ✅ Διορθώσετε bugs
- ✅ Ενημερώσετε εξαρτήσεις (pip install -U ...)

### ΔΕΝ χρειάζεται νέο build όταν:
- ❌ Αλλάζετε μόνο τη βάση δεδομένων (.db)
- ❌ Δημιουργείτε templates (.xlsx, .csv)
- ❌ Επεξεργάζεστε το README

## Αυτοματοποίηση Build

Για τακτικά builds, δημιουργήστε shortcut:
1. Δεξί κλικ στο `build.bat` → "Create shortcut"
2. Μετακινήστε το shortcut στην επιφάνεια εργασίας
3. Μπορείτε να το εκτελέσετε με ένα κλικ

## Build Information

**Εκδόσεις βιβλιοθηκών:**
- Python: 3.12.10
- Kivy: 2.3.1
- pandas: 3.0.0
- openpyxl: 3.1.5
- PyInstaller: 6.18.0

**Τελευταία κατασκευή:** 26 Ιανουαρίου 2026

**Μέγεθος εκτελέσιμου:** ~60-80 MB (συμπεριλαμβάνει όλες τις βιβλιοθήκες)

## Σημειώσεις Ανάπτυξης

- Το build διαρκεί 5-10 λεπτά
- Απαιτεί ~500 MB ελεύθερο χώρο για προσωρινά αρχεία
- Το τελικό .exe είναι portable (δεν χρειάζεται εγκατάσταση)
- Τα αρχεία build/ και SubstationManager.spec διαγράφονται αυτόματα
