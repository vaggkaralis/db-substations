"""Centralized UI strings to avoid hardcoded literals in code.

STRINGS is a nested dict grouping labels, button texts, popup titles and
common messages. Keys are organized by category to make navigation easier.
When adding new strings, place them under the most appropriate category.
"""

from datetime import datetime
import json
import os


DEFAULT_LANGUAGE = "el"
SUPPORTED_LANGUAGES = ("el", "en")
SETTINGS_FILE = os.environ.get(
    "APP_SETTINGS_PATH",
    os.path.join(os.path.dirname(__file__), "app_settings.json"),
)


def _load_app_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_app_settings(settings: dict) -> None:
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as fh:
            json.dump(settings, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass


_settings = _load_app_settings()
CURRENT_LANGUAGE = _settings.get("language", DEFAULT_LANGUAGE)
if CURRENT_LANGUAGE not in SUPPORTED_LANGUAGES:
    CURRENT_LANGUAGE = DEFAULT_LANGUAGE


STRINGS_EL = {
    # Top-level button text used in many places
    "BUTTONS": {
        "IMPORT": "Εισαγωγή",
        "ADD": "Προσθήκη",
        "VIEW": "Προβολή",
        "REFRESH": "Ανανέωση",
        "OPEN": "Άνοιγμα",
        "REPLACE": "Αντικατάσταση",
        "SKIP": "Παράλειψη",
        "REPLACE_ALL": "Αντικατάσταση Όλων",
        "SKIP_ALL": "Παράλειψη Όλων",
        "CONFIRM": "Επιβεβαίωση",
        "EDIT": "Επεξεργασία",
        "LIST": "Λίστα",
        "CANCEL": "Ακύρωση",
        "EMAIL": "Email",
        "APPLY": "Εφαρμογή",
        "BACKUP_APPLY": "Backup & Εφαρμογή",
        "CLOSE": "Κλείσιμο",
        "INSPECTIONS": "Επιθεωρήσεις",
        "SAVE": "Αποθήκευση",
        "BACK": "Πίσω",
        "MAINTENANCE": "Συντήρηση",
        "INSPECT": "Επιθεώρηση",
        "DELETE": "Διαγραφή",
        "UPDATE": "Ενημέρωση",
        "YES": "Ναι",
        "NO": "Όχι",
        "OK": "OK",
        "COPY": "Αντιγραφή",
        "BROWSE_FILE": "Αναζήτηση αρχείου",
        "ADD_MAINTENANCE": "+ Προσθήκη Νέας Συντήρησης",
        "ADD_MODEL": "+ Προσθήκη Νέου Μοντέλου",
        "LOGIN": "Σύνδεση",
        "LOGOUT": "Αποσύνδεση",
        "RESET": "Επαναφορά",
    },

    # Common window / popup titles
    "TITLES": {
        "ERROR": "Σφάλμα",
        "SUCCESS": "Επιτυχία",
        "INFO": "Πληροφορία",
        "IMPORT_MENU": "Εισαγωγή από αρχείο",
        "IMPORT_ANDROID": "Εισαγωγή αλλαγών από Android",
        "PREVIEW_CHANGELOG": "Προεπισκόπηση αλλαγών",
        "INSPECTION_ENTRY": "Καταχώρηση Επιθεώρησης",
        "INSPECTION_HISTORY": "Ιστορικό Επιθεώρησης",
        "INSPECTION_DETAILS": "Λεπτομέρειες Επιθεώρησης",
        "IMPORT_SUBSTATIONS_TITLE": "Εισαγωγή Υποσταθμών",
        "SETTINGS": "Ρυθμίσεις",
        "LOGIN": "Σύνδεση",
    },

    # Application-wide messages grouped by functional area
    "MESSAGES": {
        # --- General / Application info ---
        "APP_TITLE": "Υποσταθμοί ΔΕΔΔΗΕ ΔΕΕΔ/ΚΣΜΘ/ΤΕΙ",
        "APP_INFO_SHORT": "Πληρ. Εφαρμ.",
        "APP_INFO_TITLE": "Πληροφορίες Εφαρμογής",
        "APP_INFO_BODY": (
            "Υποσταθμοί ΔΕΔΔΗΕ ΔΕΕΔ/ΚΣΜΘ/ΤΕΙ\n"
            "Έκδοση: {version}\n"
            "Έκδοση Βάσης Δεδομένων: {db_version}\n"
            "Συμβατότητα: {compat_status}\n\n"
            "Λειτουργίες εφαρμογής:\n"
            "• Προβολή και διαχείριση βάσης υποσταθμών\n"
            "• Προσθήκη/επεξεργασία/διαγραφή υποσταθμών και στοιχείων\n"
            "• Κατηγορίες διακοπτών (SF6/Ελαίου/Πτωχού Ελαίου)\n"
            "• Διαχείριση τύπων στοιχείων (μοντέλα/κατασκευαστές/κύκλοι)\n"
            "• Καταχώρηση συντηρήσεων\n"
            "• Εισαγωγή συντήρησης από e-mail (.eml)\n"
            "• Ιστορικό συντηρήσεων (όλων/ανά υποσταθμό)\n"
            "• Μετρήσεις διακοπτών (μόνωση/διέλευση/χειρισμοί)\n"
            "• Ποιότητα αερίου SF6 & διαρροές (kg)\n"
            "• Διαχείριση SF6 (αναφορά διαρροών ανά έτος)\n"
            "• Εξαγωγή Excel αναφορών SF6 (σύνοψη & ανά υποσταθμό)\n"
            "• Εκτύπωση PDF αναφορών συντήρησης\n"
            "• Επιθεωρήσεις (καταχώρηση/προβολή/ιστορικό)\n"
            "• Αιτήσεις απομόνωσης\n"
            "• Εισαγωγή υποσταθμών/στοιχείων από CSV/Excel\n"
            "• Αναφορές PDF & Excel\n\n"
            "Φάκελος εφαρμογής: {app_dir}"
        ),
        "LOADING": "Φόρτωση...",
        "COPY": "Αντιγραφή",
        "DASH": "-",

        # --- Files / Import / PDF ---
        "ENTER_PATH": "Παρακαλώ εισάγετε διαδρομή ή επιλέξτε αρχείο!",
        "FILE_PATH_LABEL": "Διαδρομή αρχείου:",
        "FILE_PATH_HINT": "Διαδρομή αρχείου",
        "FILE_NOT_FOUND": "Το αρχείο δεν βρέθηκε!",
        "PLEASE_SELECT_PDF": "Παρακαλώ επιλέξτε αρχείο PDF!",
        "UNSUPPORTED_FILE_FORMAT": "Μη υποστηριζόμενη μορφή αρχείου",
        "FILE_HAS_NO_DATA": "Το αρχείο δεν περιέχει δεδομένα.",
        "IMPORT_FAILED": "Αποτυχία εισαγωγής:",
        "IMPORT_SUCCESS": "Επιτυχής εισαγωγή.",
        "SELECT_MONOGRAM_PDF_TITLE": "Επιλογή Μονογραμμικού PDF",
        "CHANGELOG_FILE_LABEL": "Διαδρομή αρχείου change log (.jsonl):",

        # --- Substations / DB ---
        "NO_SUBSTATIONS": "Δεν υπάρχουν υποσταθμοί!",
        "EMPTY_DB": "Κενή βάση",
        "ADD_NEW_SUBSTATION_PROMPT": "Ή προσθέστε νέο υποσταθμό:",
        "PLEASE_SELECT_OR_ADD_SUBSTATION": "Παρακαλώ επιλέξτε υποσταθμό ή προσθέστε νέο.",
        "ENTER_SUBSTATION_NAME": "Παρακαλώ εισάγετε όνομα υποσταθμού!",
        "SUBSTATION_LABEL": "Υποσταθμός:",
        "SUBSTATION_NAME_LABEL": "Όνομα Υποσταθμού:",
        "SUBSTATION_NAME_HINT": "Όνομα Υποσταθμού",
        "SUBSTATION_NEW_HINT": "Όνομα νέου υποσταθμού",
        "SUBSTATION_IS_THESSALONIKI": "Υ/Σ Θεσσαλονίκης",
        "SUBSTATION_ADDED": "Υποσταθμός προστέθηκε!",
        "SUBSTATION_EXISTS": "Ο υποσταθμός υπάρχει ήδη.",
        "SELECT_SUBSTATION": "Επιλογή Υποσταθμού:",
        "SELECT_SUBSTATION_BTN": "Επιλογή Υποσταθμού",
        "PROMPT_SUBSTATION_NOT_FOUND_TITLE": "Ο υποσταθμός δε βρέθηκε",
        "PROMPT_SUBSTATION_SELECT": "Επιλέξτε υποσταθμό για την εισαγωγή:",
        "SUBSTATION_NOT_FOUND": "Δεν βρέθηκε υποσταθμός.",
        "MISSING_SUBSTATIONS_WILL_CREATE": "Οι παρακάτω υποσταθμοί δεν υπάρχουν και θα δημιουργηθούν:",
        "NEW_SUBSTATIONS_TITLE": "Νέοι Υποσταθμοί Εντοπίστηκαν",

        # --- Maintenance / Records ---
        "MAINTENANCE_SAVED_CHANGELOG": "Η συντήρηση καταχωρήθηκε στο change log.",
        "MAINTENANCE_DELETED": "Η συντήρηση διαγράφηκε!",
        "MAINTENANCE_NOT_FOUND": "Δεν βρέθηκε η συντήρηση.",
        "NO_MAINTENANCES": "Δεν υπάρχουν καταχωρημένες συντηρήσεις",
        "NO_MAINT_FOR_SUBSTATION": (
            'Δεν υπάρχουν καταχωρημένες συντηρήσεις για τον υποσταθμό "{substation_name}".\n'
            "Χρησιμοποιήστε το κουμπί παραπάνω για να προσθέσετε."
        ),
        "MAINT_HISTORY_LABEL": "Ιστορικό Συντήρησης",
        "MAINTENANCE_NAME_FMT": "Υ/Σ {substation_name} - {date}",
        "NO_RECORD_ELEMENTS": "Δεν υπάρχουν στοιχεία για αυτή τη συντήρηση.",

        # --- Maintenance form labels & validation ---
        "DATE_TIME_LABEL": "Ημερομηνία & Ώρα:",
        "DATE_REQUIRED": "Η ημερομηνία είναι υποχρεωτική!",
        "DATE_PREFIX": "Ημ/νία:",
        "MAINT_TYPE_LABEL": "Τύπος Συντήρησης:",
        "MAINTENANCE_TYPES": ["Επαναληπτική συντήρηση", "Βλάβη", "Οπτικός έλεγχος"],
        "MAINT_TYPE_DEFAULT": "Επαναληπτική συντήρηση",
        "RESPONSIBLE_LABEL": "Υπεύθυνος Συντήρησης (υποχρεωτικό):",
        "RESPONSIBLE_REQUIRED": "Ο υπεύθυνος συντήρησης είναι υποχρεωτικός!",
        "CREW_LABEL": "Ομάδα Συντήρησης (προαιρετικό):",
        "OVERALL_COMMENTS_LABEL": "Γενικά Σχόλια Συντήρησης:",
        "ELEMENTS_SECTION_LABEL": "Στοιχεία που συντηρήθηκαν (τουλάχιστον 1):",
        "NO_ELEMENTS_IN_SUBSTATION": "Δεν υπάρχουν στοιχεία σε αυτόν τον υποσταθμό",
        "SELECT_AT_LEAST_ONE_ELEMENT": "Πρέπει να επιλέξετε τουλάχιστον ένα στοιχείο!",
        "ADD_ELEMENT_BEFORE_CONTINUE": "Προσθέστε τουλάχιστον ένα στοιχείο πριν τη συνέχεια.",

        # --- Inspections ---
        "INSPECTION_SAVED": "Η επιθεώρηση καταχωρήθηκε!",
        # The inspection rows were reviewed for typos and corrected where obvious.
        "INSPECTION_ROWS": [
            "Έλεγχος εξωτερικών & εσωτερικών θυρών ΥΣ",
            "Έλεγχος εσωτερικού χώρου κτηρίου (φωτισμός, κλιματισμός κλπ)",
            "Έλεγχος περιβάλλοντος χώρου (βλάστηση, δένδρα, φωτισμός κλπ)",
            "Έλεγχος μέσων πυρόσβεσης γενικά",
            "Οπτικός έλεγχος διαρροής/στάθμης/θερμοκρασίας λαδιού, silica gel στον Μ/Σ",
            "Οπτικός έλεγχος διαρροής λαδιού ή πίεσης SF6 ή πίεσης αέρα στους διακόπτες ισχύος 150kV & 20kV",
            "Έλεγχος λειτουργίας ανεμιστήρων Μ/Σ",
            "Οπτικός έλεγχος Μ/Σ έγχυσης, ΜΣΕ, ΜΣΤ, Μ/Σ εσωτερικής υπηρεσίας, αντίστασης κόμβου (θερμοκρασία)",
            "Οπτικός έλεγχος μονωτήρων (ρύπανση, εκδορές κ.α.)",
            "Οπτικός έλεγχος τηκτών πυκνωτών",
            "Έλεγχος σημάνσεων στους πίνακες Μ/Σ, Α/Δ 150kV & 20kV",
            "Λήψη φωτογραφίας όταν απαιτείται",
            "Οπτικός έλεγχος των πυλών, A/Z και γενικά του ικριώματος για τυχόν φωλιές από πτηνά, σπασίματα, μονωτήρες, κλαδιά, σύρματα κλπ",
            "Οπτικός έλεγχος στους πίνακες διακοπτών 20kV (αναγγελίες, ενδείξεις οργάνων, πόρτες) και έλεγχος θορύβων, ιονισμών",
            "Έλεγχοι υγρασίας (υπόγειο, κανάλια καλωδίων), αφυγραντήρων, θερμαντικών, φορητών πυροσβεστήρων",
            "Έλεγχος φορτιστή 110V οπτικά με έλεγχο της τάσης, έντασης και καταγραφή",
            "Έλεγχος για alarm έλλειψης DC στον γενικό πίνακα DC",
            "Οπτικός έλεγχος διαρροών στοιχείων συσσωρευτών",
            "Οπτικός έλεγχος των ΑΠ/Ζ και των 'γεφυρών' αυτών στον 1ο στύλο κάθε γραμμής (σπασμένοι ΑΠ/Ζ, μονωτήρες, εκτονωμένα Α/Ξ κλπ)",
            "Έλεγχος λειτουργίας ψηφιακού συστήματος (χειρισμοί, ενδείξεις, σημάνσεις)",
            "Τροφοδοσία υπολογιστή",
            "Απόψεις και τυχόν προτάσεις για την καλύτερη λειτουργία τόσο του εξοπλισμού, όσο και του κτηρίου γενικά του Υ/Σ",
        ],
        "INSPECTION_SECTION_2": "[b]Έλεγχος Χώρων ΥΣ[/b]",
        "INSPECTION_SECTION_3": "[b]Μ/Σ 150/20kV & Διακόπτες 150kV & 20kV[/b]",
        "INSPECTION_SECTION_3A": "[b]Υπαίθριες πύλες 20 kV[/b]",
        "INSPECTION_SECTION_3B": "[b]Υπαίθριες πύλες 20 kV[/b]",
        "INSPECTION_SECTION_4": "[b]Κτίριο χειρισμών & Τ.Α.Σ.[/b]",
        "INSPECTION_SECTION_5": "[b]Αποζεύκτες Γραμμών[/b]",
        "INSPECTION_SECTION_6": "[b]PC Χειρισμών[/b]",
        "INSPECTION_SECTION_7": "[b]Απόψεις[/b]",
        # Additional inspection UI messages
        "INSPECTION_BASE_FIELDS": [
            "Υποσταθμός",
            "Αρ. Δελτίου",
            "Μήνας",
            "Ονομ. Επιθεωρητή",
            "Περιοχή",
            "Ημέρα",
            "Έτος",
            "Ημερομηνία",
        ],
        "IMPORT_INSPECTIONS_TITLE": "Εισαγωγή Επιθεωρήσεων",
        "IMPORT_INSPECTIONS_DONE": "Ολοκληρώθηκε η εισαγωγή ({inserted} εγγραφές).",
        "IMPORT_INSPECTIONS_DIALOG": "Εισαγωγή επιθεωρήσεων από αρχείο",
        "NO_INSPECTIONS": "Δεν υπάρχουν καταχωρημένες επιθεωρήσεις. Θέλετε να δημιουργήσετε μία;",
        "INSPECTION_COUNT_FMT": "{count} εγγραφές επιθεώρησης",
        "SUBSTATION_INSPECTION_HISTORY_TITLE_FMT": "Ιστορικό Επιθεωρήσεων - {substation_name}",
        "SUBSTATION_INSPECTION_COUNT_FMT": "{count} εγγραφές επιθεώρησης για τον υποσταθμό {substation_name}",
        "SUBSTATION_LABEL_PLAIN": "Υποσταθμός",
        "DATE_PLAIN": "Ημερομηνία",
        "MEASUREMENT_RESISTANCE_HEADER": "ΜΕΤΡΗΣΗ ΑΝΤΙΣΤΑΣΗΣ (Ω)",

        # --- People / Staff ---
        "NO_PEOPLE": "Δεν υπάρχουν καταχωρημένα άτομα. Παρακαλώ προσθέστε προσωπικό.",
        "SURNAME_LABEL": "Επώνυμο:",
        "NAME_LABEL": "Όνομα:",
        "ROLE_LABEL": "Ρόλος:",
        "EMAIL_LABEL": "Email:",
        "EMAIL_RECIPIENT_LABEL": "Παραλήπτες αναφοράς email",
        "ACTIVE_LABEL": "Ενεργός",
        "STAFF_LOAD_FAILED": "Ανεπιτυχής φόρτωση διαχείρισης προσωπικού.",
        "PERSON_NOT_FOUND": "Το άτομο δεν βρέθηκε!",
        "EDIT_PERSON_TITLE": "Επεξεργασία Προσώπου",
        "SURNAME_ROLE_REQUIRED": "Το επώνυμο και ο ρόλος είναι υποχρεωτικά!",
        "PERSON_IN_USE": "Το άτομο έχει χρησιμοποιηθεί σε συντηρήσεις. Διαγράψτε το μόνο αφού αφαιρεθεί από το ιστορικό ή απενεργοποιήστε το.",
        "CONFIRM_DELETE_PERSON_FMT": "Είστε σίγουροι ότι θέλετε να διαγράψετε\nτο άτομο \"{person_name}\";",

        # Missing messages added during DBrun.py sweep
        "NO_AVAILABLE_RESPONSIBLE": "Δεν υπάρχει διαθέσιμος υπεύθυνος συντήρησης με τα κατάλληλα δικαιώματα. Προσθέστε ή ενημερώστε προσωπικό.",
        "SF6_LEAK_METHODOLOGY_REQUIRED": "Για διαρροή SF6 απαιτείται συμπλήρωση μεθοδολογίας (Πλήρωση/Αντικατάσταση).",
        "GATE_LABEL": "Πύλη",
        "DIVISION_LABEL": "Τομέας",
        "MAINT_USER_LABEL": "Χειριστής",
        # --- Models / Element types ---
        "MODEL_NOT_USED": "Το μοντέλο δεν χρησιμοποιείται σε κανένα στοιχείο.",
        "MODEL_NAME_REQUIRED": "Το όνομα μοντέλου είναι υποχρεωτικό!",
        "MODEL_SERVICE_CYCLE_NUM": "Ο κύκλος συντήρησης πρέπει να είναι αριθμός!",
        "MODEL_POWER_NUM": "Η ονομαστική ισχύς πρέπει να είναι αριθμός!",
        "MODEL_ADDED": "Το μοντέλο προστέθηκε!",
        "MODEL_DELETED": "Το μοντέλο διαγράφηκε επιτυχώς!",
        "MODEL_NOT_FOUND": "Το μοντέλο δεν βρέθηκε!",
        "MODEL_CHECK_TITLE": "Έλεγχος Μοντέλων",
        "NEW_MODELS_HEADER": "[b]Νέα Μοντέλα (θα προστεθούν):[/b]",
        "EXISTING_MODELS_DIFF_HEADER": "[b]Υπάρχοντα Μοντέλα με Διαφορετικά Δεδομένα:[/b]",

        # --- Elements / Types / Filters ---
        "NO_ELEMENTS": "Κανένα στοιχείο",
        "NO_ELEMENTS_PAREN": "(Χωρίς στοιχεία)",
        "NO_ELEMENTS_FOR_ITEM": "Δεν υπάρχουν καταχωρημένα στοιχεία για αυτό το στοιχείο.",
        "NO_MODELS": "Δεν υπάρχουν μοντέλα",
        "NO_INACTIVE_ELEMENTS": "Δεν υπάρχουν ανενεργά στοιχεία σε αυτόν τον υποσταθμό",
        # lists used by DBrun
        "ELEMENT_TYPES": [
            "Διακόπτης ΥΤ",
            "Διακόπτης ΜΤ",
            "Μετασχηματιστής 150/20KV",
            "Motor Drive",
            "Μ/Σ Έγχυσης",
            "Μ/Σ Έντασης",
            "Μ/Σ Τάσης",
            "Μ/Σ ΧΤ/ΜΤ (ΒΜΣ)",
            "Αποζεύκτης",
            "Ασφαλειοαποζεύκτης",
            "Γειωτής",
            "Συστοιχία Πυκνωτών",
            "Αντίσταση Κόμβου",
            "Αλεξικέραυνο",
            "Συστοιχία Συσσωρευτών",
        ],
        # Canonical element names used elsewhere in code
        "ELEMENT_BREAKER_YT": "Διακόπτης ΥΤ",
        "ELEMENT_BREAKER_MT": "Διακόπτης ΜΤ",
        "VIDAR_VACUUM_CHECK_LABEL": "ΕΛΕΓΧΟΣ ΚΕΝΟΥ (VIDAR):",
        # VIDAR phase labels and hints
        "VIDAR_LABEL_FB": "ΦΒ-ΦΒ:",
        "VIDAR_LABEL_FC": "ΦΓ-ΦΓ:",
        "VIDAR_HINT": "0.0",
        "VIDAR_SECTION_TITLE": "Έλεγχος Κενού (VIDAR)",
        # unified phase-to-phase label used by both insulation and vidar
        "PHASE_TO_PHASE_LABEL": "ΦΑ-ΦΑ",
        "PHASE_TO_PHASE_LABEL_COLON": "ΦΑ-ΦΑ:",
        # backwards-compatible aliases (deprecated) - use PHASE_TO_PHASE_LABEL variants instead
        # "INSULATION_LABEL_FA": "ΦΑ-ΦΑ",  # DEPRECATED: use PHASE_TO_PHASE_LABEL
        # "VIDAR_LABEL_FA": "ΦΑ-ΦΑ:",  # DEPRECATED: use PHASE_TO_PHASE_LABEL_COLON
        # Insulation / resistance section titles and labels
        "INSULATION_RESISTANCE_CLOSED_TITLE": "Αντίσταση Μόνωσης - Διακόπτης Κλειστός (Γη)",
        "INSULATION_RESISTANCE_OPEN_TITLE": "Αντίσταση Μόνωσης - Διακόπτης Ανοικτός (Φάση-Φάση)",
        "INSULATION_PASSAGE_TITLE": "Αντίσταση Διέλευσης (μΩ)",
        "INSULATION_MEASUREMENT_CLOSED_HEADER": "ΜΕΤΡΗΣΗ ΑΝΤΙΣΤΑΣΗΣ ΜΟΝΩΣΗΣ - ΔΙΑΚΟΠΤΗΣ ΚΛΕΙΣΤΟΣ (Φ-ΓΗ):",
        "INSULATION_MEASUREMENT_OPEN_HEADER": "ΜΕΤΡΗΣΗ ΑΝΤΙΣΤΑΣΗΣ ΜΟΝΩΣΗΣ - ΔΙΑΚΟΠΤΗΣ ΑΝΟΙΧΤΟΣ (Φ-Φ):",
        "INSULATION_PASSAGE_MEASUREMENT_CLOSED_HEADER": "ΑΝΤΙΣΤΑΣΗ ΔΙΕΛΕΥΣΗΣ (μΩ) - ΔΙΑΚΟΠΤΗΣ ΚΛΕΙΣΤΟΣ:",
        "INSULATION_HINT": "0.0",
        "INSULATION_LABEL_FA_GND": "ΦΑ-Γη",
        "INSULATION_LABEL_FB_GND": "ΦΒ-Γη",
        "INSULATION_LABEL_FC_GND": "ΦΓ-Γη",
        "INSULATION_LABEL_FA": "ΦΑ-ΦΑ",
        "INSULATION_LABEL_FB": "ΦΒ-ΦΒ",
        "INSULATION_LABEL_FC": "ΦΓ-ΦΓ",
        # Generic substring used to detect breaker element types
        "ELEMENT_BREAKER_SUBSTR": "Διακόπτης",
        "BREAKER_CATEGORIES_ALL": ["SF6", "Πτωχού Ελαίου", "Ελαίου", "Κενού"],
        "BREAKER_CATEGORIES_HV": ["SF6", "Ελαίου"],
        "BREAKER_CATEGORIES_MV": ["SF6", "Πτωχού Ελαίου", "Ελαίου", "Κενού"],
        "BREAKER_TYPES": ["Κεντρικός", "Γραμμής", "Διασυνδετικός", "Διακόπτης Πυκνωτών"],
        "OPERATING_STATUS": ["Ενεργή", "Ανενεργή"],
        "INSTALLATION_SPACE": ["Εσωτερικός", "Εξωτερικός"],
        "VOLTAGE_LEVELS": ["(Κενό)", "150/20KV", "20KV", "150KV", "20KV/400V"],
        "VIEW_ELEMENT_TITLE": "Προβολή Στοιχείου",
        "ELEMENTS_LIST_LABEL": "Στοιχεία που συντηρήθηκαν:",
        "PLEASE_SELECT_BREAKER_CATEGORY": "Παρακαλώ επιλέξτε κατηγορία διακόπτη!",
        "PLEASE_SELECT_EML": "Παρακαλώ επιλέξτε αρχείο .eml!",
        "INACTIVE_ELEMENTS": "Ανενεργά Στοιχεία ({count})",
        "ELEMENT_ADDED": "Στοιχείο προστέθηκε στον {substation_name}!",
        "ELEMENT_DUPLICATE": "Υπάρχει ήδη στοιχείο με αυτό το όνομα σε αυτόν τον υποσταθμό!",
        "VIEW_ACTIVE_ELEMENTS": "Προβολή ενεργών στοιχείων ({count})",
        "FILTER_TYPE": "Φίλτρο Τύπου:",
        "FILTER_GATE": "Φίλτρο Πύλης:",
        "FILTER_SUBSTATION": "Φίλτρο Υποσταθμού:",
        "LOC": "Τοποθεσία",
        "ADOPTION": "Ανάληψη",
        "INFO": "Στοιχεία",
        "GATES": "Πύλες",
        "CAPACITORS": "Πυκνωτές",
        "MAINTENANCES": "Συντηρήσεις",
        "LAST": "Τελευταία",
        "SINGLE_LINE": "Μονογραμμικό",
        "MONTHS": [
            "Ιανουάριος",
            "Φεβρουάριος",
            "Μάρτιος",
            "Απρίλιος",
            "Μάιος",
            "Ιούνιος",
            "Ιούλιος",
            "Αύγουστος",
            "Σεπτέμβριος",
            "Οκτώβριος",
            "Νοέμβριος",
            "Δεκέμβριος",
        ],
        "DAYS": [
            "Δευτέρα",
            "Τρίτη",
            "Τετάρτη",
            "Πέμπτη",
            "Παρασκευή",
            "Σάββατο",
            "Κυριακή",
        ],
        # Individual labels / small constants used across the UI
        "BREAKER_LABEL_CENTRAL": "Κεντρικός",
        "BREAKER_LABEL_INTERCON": "Διασυνδετικός",
        "BREAKER_LABEL_CAPACITOR": "Διακόπτης Πυκνωτών",
        "BREAKER_LABEL_LINE": "Γραμμής",
        "GATE_PREFIX": "ΠΥΛΗ",
        "ALL_LABEL": "(Όλα)",
        "DIVISION_DEFAULT": "ΤΜΘ",
        # Additional keys used by the Android UI
        "PICKER_EMPTY_SELECTION": "Ο επιλογέας επέστρεψε κενή επιλογή (None).",
        "ANDROID_FILECHOOSER_FALLBACK": "Ο επιλογέας αρχείων του Android δεν είναι διαθέσιμος. Χρησιμοποίησε τη λίστα αρχείων στο παράθυρο.",
        "FILECHOOSER_NOT_AVAILABLE": "Ο επιλογέας αρχείων δεν είναι διαθέσιμος",
        "FILECHOOSER_ANDROID_ONLY": "Ο επιλογέας αρχείων είναι διαθέσιμος μόνο σε Android.",
        "FILECHOOSER_INTERNAL_ERROR": "Εσωτερικό σφάλμα επιλογέα αρχείων.",
        "FILECHOICE_CANCELLED": "Η επιλογή αρχείου απέτυχε ή ακυρώθηκε.",
        "MODE_LABEL_LOCAL": "Πηγή: Τοπική Βάση",
        "LOCAL_DB_BUTTON": "Τοπική Βάση",
        "CHANGELOG_BUTTON": "Change-log",
        "CHANGELOG_RECORDED": "Η αλλαγή καταγράφηκε στο change log.",
        "ADOPTION_DATE_LABEL": "Ημερομηνία Υιοθέτησης:",
        "NAME_REQUIRED": "Το όνομα είναι υποχρεωτικό",
        "ELEMENT_TYPE_LABEL": "Τύπος Στοιχείου:",
        "RETRY": "Ξαναδοκίμασε",
        "COPYING_FILE": "Αντιγραφή αρχείου...",
        "COPYING_FILE_MSG": "Αντιγραφή αρχείου από το σύστημα αρχείων. Παρακαλώ περιμένετε...",
        "OVERALL_COMMENTS_HINT": "Γενικά σχόλια για την συντήρηση...",
        "GOOGLE_MAPS_LINK": "Google Maps Link",
        "SHARE_BUTTON": "Κοινοποίηση",
        "COPY_PATH": "Αντιγραφή διαδρομής",
        "LOADING_ELEMENTS": "Φόρτωση στοιχείων...",
        "RETRY_LOAD": "Επανάληψη φόρτωσης",
        "ELEM_COMMENTS_HINT": "Σχόλια για αυτό το στοιχείο...",

        # --- UI Actions / Buttons (mirrors BUTTONS when needed) ---
        "SHOW_DB_BUTTON": "Προβολή βάσης υποσταθμών",
        "IMPORT_BUTTON": "Εισαγωγή από αρχείο",
        "MAINTENANCE_BUTTON": "Συντηρήσεις",
        "INSPECTION_BUTTON": "Επιθεωρήσεις",
        "ISOLATION_BUTTON": "Αιτήσεις Απομόνωσης",
        "SF6_BUTTON": "SF6",
        "MODELS_BUTTON": "Διαχείριση Τύπων Στοιχείων",
        "PEOPLE_BUTTON": "Διαχείριση Προσωπικού",
        "TOOLTIP_EDIT": "Επεξεργασία",
        "TOOLTIP_DELETE": "Διαγραφή",
        "TOOLTIP_VIEW": "Προβολή",
        "TOOLTIP_MAINTENANCE": "Συντήρηση",
        "TOOLTIP_INSPECTION": "Επιθεώρηση",
        "VIEW_SHORT": "Προβ.",
        "PDF_BUTTON": "PDF",

        # --- Prompts / Dialogs / Titles ---
        "VIEW_PROMPT": "Επιλέξτε τι θέλετε να δείτε:",
        "SEARCH_HINT": "Αναζήτηση (όνομα/ημερομηνία)",
        "PREVIOUS": "Προηγούμενη",
        "NEXT": "Επόμενη",
        "LOAD_MORE": "Φόρτωση περισσότερων",
        "PAGE_LABEL_TEMPLATE": "Σελίδα {page}",
        "ALL_SUBSTATIONS_LABEL": "Όλοι οι Υ/Σ",
        "VIEW_SELECTION_TITLE": "Επιλογή Προβολής",
        "SORT_OPTIONS": [
            "Ημερομηνία (φθίνουσα)",
            "Ημερομηνία (αύξουσα)",
            "Υποσταθμός A-Ω",
        ],
        "PAGE_SIZE_LABEL": "Αντικείμενα/σελίδα",
        "PAGE_SIZE_OPTIONS": ["10", "20", "30", "50"],
        "SELECT_PROMPT": "Επιλογή",
        "SHOW_ALL_SUBSTATIONS": "Προβολή Όλων των Υποσταθμών",
        "SELECT_ALL_BTN": "Επιλογή Όλων",
        "ADD_MENU_TITLE": "Προσθήκη υποσταθμών και στοιχείων",
        "ADD_SUBSTATION_BTN": "Προσθήκη Νέου Υποσταθμού",
        "ADD_ELEMENT_BTN": "Προσθήκη Νέου Στοιχείου",
        "ADD_ELEMENTS_TITLE": "Προσθήκη στοιχείων",
        "ADD_SUBSTATION_TITLE": "Προσθήκη Υποσταθμού",
        "ADD_ELEMENT_TITLE": "Προσθήκη Στοιχείου",
        "ADD_MODEL_TITLE": "Προσθήκη Νέου Μοντέλου",
        "ADD_MANUAL": "Προσθήκη Manual",
        "ADD_ELEMENTS_PROMPT": "Προσθέστε στοιχεία για τον νέο υποσταθμό πριν τη συνέχεια:",
        "CONTINUE": "Συνέχεια",
        "OPEN_LOCAL_DB_TITLE": "Άνοιγμα Τοπικής Βάσης",
        "OPEN_FOLDER": "Άνοιγμα φακέλου",
        "CONFIRM_DELETE_TITLE": "Επιβεβαίωση Διαγραφής",
        "DUPLICATE_OPTIONS_INCOMPLETE": (
            "Ολοκληρώστε τις επιλογές για όλα τα διπλότυπα ή χρησιμοποιήστε 'Αντικατάσταση Όλων' / 'Παράλειψη Όλων'."
        ),
        "RESPONSIBLE_NOT_FOUND_TITLE": "Ο υπεύθυνος δε βρέθηκε",

        # --- Misc / Hints ---
        "FORM_NUMBER": "Αρ. Δελτίου:",
        "FORM_NUMBER_HINT": "Αρ. Δελτίου",
        "ELEMENT_NAME_LABEL": "Όνομα Στοιχείου",
        "ELEMENT_NAME_HINT": "Όνομα Στοιχείου",
        "SERIAL_NUMBER_LABEL": "Σειριακός Αριθμός",
        "SERIAL_NUMBER_HINT": "Σειριακός Αριθμός",
        "ELEMENT_MANUFACTURE_YEAR_LABEL": "Έτος κατασκευής",
        "ELEMENT_MANUFACTURE_YEAR_HINT": "YYYY",
        "MAINTENANCE_DATE_LABEL": "Τελευταία Συντ.",
        "MAINTENANCE_DATE_HINT": "YYYY-MM-DD",
        "MANUFACTURER_LABEL": "Κατασκευαστής",
        "MANUFACTURER_HINT": "Κατασκευαστής",
        "MODEL_LABEL": "Μοντέλο",
        "MODEL_HINT": "Μοντέλο",
        "MODEL_VERSION_LABEL": "Έκδοση Μοντέλου",
        "MODEL_VERSION_HINT": "Έκδοση",
        "INSTALLATION_SPACE_LABEL": "Χώρος Εγκατ.",
        "OPERATING_STATUS_LABEL": "Λειτ. Κατάσταση",
        "MAINTENANCE_CYCLE_LABEL": "Κύκλος Συντ.",
        "MAINTENANCE_CYCLE_HINT": "Αριθμός",
        "DATE_LABEL": "Ημερομηνία:",
        "DATE_HINT": "YYYY-MM-DD",
        "REGION_LABEL": "Περιοχή:",
        "REGION_HINT": "Περιοχή",
        "INSPECTOR_LABEL": "Ονομ. Επιθεωρητή:",
        "MONTH_LABEL": "Μήνας:",
        "DAY_LABEL": "Ημέρα:",
        "YEAR_LABEL": "Έτος:",
        "OBSERVATIONS_HINT": "Παρατηρήσεις",

        # --- Email / Reports ---
        "EMAIL_RECIPIENTS_MISSING": (
            "Δεν υπάρχουν παραλήπτες email. Προσθέστε παραλήπτες από τη Διαχείριση Προσωπικού."
        ),
        "MAINTENANCE_HEADER": "Συντήρηση: {name}",
        "PEOPLE_SUMMARY": "Υπεύθυνος: {resp} | Ομάδα: {crew}",
        "COMMENTS_LABEL": "Σχόλια: {text}",
        "MAINTENANCE_COMMENTS_SECTION": "Σχόλια Συντήρησης",
        "ELEMENT_COMMENTS_SECTION": "Σχόλια Στοιχείου",
        "MAINT_LAST_LABEL": "Τελευταία Συντήρηση: {date}",

        # --- Errors & Validation ---
        "INVALID_DATE_FORMAT": "Μη έγκυρη μορφή ημερομηνίας! Χρησιμοποιήστε: YYYY-MM-DD HH:MM",
        "END_BEFORE_START": "Η ημερομηνία λήξης πρέπει να είναι μετά την έναρξη!",
        "ERROR_DURING_CHECK_PREFIX": "Σφάλμα κατά τον έλεγχο: ",
        "RECORD_NOT_FOUND": "Η εγγραφή δεν βρέθηκε.",

        # --- Templates / Import helpers ---
        "TEMPLATE_SUBSTATIONS_TITLE": "Template Υποσταθμών",
        "TEMPLATE_ELEMENTS_TITLE": "Template Στοιχείων",
        "OPENPYXL_MISSING": "openpyxl δεν είναι εγκατεστημένο!",
        "TEMPLATE_SUBSTATIONS_HEADERS": ["Name", "Location", "Adoption Date"],
        "TEMPLATE_ELEMENTS_HEADERS": [
            "Substation Name",
            "Element Type",
            "Name",
            "Serial Number",
            "Maintenance Date",
            "Τύπος Διακόπτη",
            "Breaker Role",
            "Operating Status",
            "Gate",
            "Model Name",
            "Model Manufacturer",
            "Model Installation Space",
        ],

        # --- Other / Deprecated-friendly ---
        "ITEM_DELETED": "Το στοιχείο διαγράφηκε!",
        "MAINTENANCE_UPDATED": "Η συντήρηση ενημερώθηκε!",
        "MAINTENANCE_CREATED": "Η συντήρηση καταχωρήθηκε!",
        "CHANGES_SAVED": "Οι αλλαγές αποθηκεύτηκαν!",
        "CONFIRM_DELETE_SUBSTATION_FMT": "Είστε σίγουροι ότι θέλετε να διαγράψετε\nτον υποσταθμό \"{substation_name}\"\nκαι ΟΛΑ τα στοιχεία του;",
        "CONFIRM_DELETE_MAINT_FMT": "Είστε σίγουροι ότι θέλετε να διαγράψετε\nαυτή τη συντήρηση;",
        "UNREGISTERED_PLACEHOLDER": "(Μη καταχωρημένο)",
        "EMPTY_PLACEHOLDER": "(Κενό)",
        "MODEL_SELECT_PROMPT": "Επιλέξτε μοντέλο",
        "BREAKER_TYPE_LABEL": "Τύπος Διακόπτη:",
        "BREAKER_CATEGORY_LABEL": "Κατηγορία Διακόπτη:",
        "RATED_POWER_HINT": "π.χ. 50",
        # --- Settings / Language ---
        "SETTINGS_TOOLTIP": "Ρυθμίσεις",
        "LANGUAGE_LABEL": "Γλώσσα:",
        "LANGUAGE_OPTION_EL": "Ελληνικά",
        "LANGUAGE_OPTION_EN": "English",
        "LANGUAGE_SAVED_RESTART": "Η γλώσσα αποθηκεύτηκε. Επανεκκινήστε την εφαρμογή για να εφαρμοστεί.",
        # --- Database Path ---
        "DB_PATH_LABEL": "Διαδρομή Βάσης Δεδομένων:",
        "DB_PATH_BUTTON": "Αλλαγή",
        "DB_PATH_SAVED_RESTART": "Η διαδρομή της βάσης δεδομένων αποθηκεύτηκε. Επανεκκινήστε την εφαρμογή για να εφαρμοστεί.",
        "DB_PATH_DEFAULT": "(Προεπιλεγμένη)",
        "DB_PATH_SELECT": "Επιλέξτε αρχείο βάσης δεδομένων",
        "DB_FILE_NOT_FOUND": "Το αρχείο της βάσης δεδομένων δεν βρέθηκε!",
        "DB_FILE_INVALID": "Μη έγκυρο αρχείο βάσης δεδομένων!",
        # --- Login / User Session ---
        "LOGIN_TITLE": "Σύνδεση Χρήστη",
        "LOGIN_PROMPT": "Επιλέξτε το όνομά σας για να συνδεθείτε:",
        "LOGIN_SUCCESS_FMT": "Καλωσορίσατε, {name}!",
        "USER_LABEL": "Χρήστης:",
        "LOGGED_IN_AS_FMT": "Συνδεδεμένος ως: {name} ({role})",
        "NO_USER_LOGGED_IN": "Δεν έχει συνδεθεί χρήστης",
        "LOGOUT_CONFIRM": "Θέλετε να αποσυνδεθείτε;",
        "LOGIN_REQUIRED": "Πρέπει να συνδεθείτε για να χρησιμοποιήσετε την εφαρμογή.",
        # --- File dialogs ---
        "FILE_DIALOG_SELECT_TITLE": "Επιλογή αρχείου",
        "FILE_DIALOG_SAVE_TITLE": "Αποθήκευση αρχείου",
        "FILE_DIALOG_ALL_FILES": "Όλα τα αρχεία",
        # --- Reports / SF6 ---
        "SF6_MANAGEMENT_TITLE": "Διαχείριση SF6",
        "PRINT": "Εκτύπωση",
        "EXCEL": "Excel",
        "ELEMENT_LABEL": "Στοιχείο",
        "LEAKAGE_LABEL": "Διαρροή (kg)",
        "NO_LEAK_ENTRIES": "Δεν υπάρχουν καταχωρήσεις διαρροών για το έτος.",
        "PDF_CREATED": "Το PDF δημιουργήθηκε:\n{path}",
        "PDF_CREATE_FAILED": "Αποτυχία δημιουργίας PDF:\n{err}",
        "EXCEL_CREATED": "Το Excel δημιουργήθηκε:\n{path}",
        "EXCEL_CREATE_FAILED": "Αποτυχία δημιουργίας Excel:\n{err}",
        "PDF_CREATED_TITLE": "PDF Δημιουργήθηκε",
        "PDF_ELEMENT_CREATED_FMT": (
            "Το αρχείο PDF για το στοιχείο \"{element_name}\"\n"
            "δημιουργήθηκε επιτυχώς!\n\n"
            "Αποθηκεύτηκε στο:\n{pdf_path}"
        ),
        "OPEN_FILE_NOT_FOUND": "Το αρχείο δεν βρέθηκε!",
        "OPEN_FILE_ERROR_TITLE": "Σφάλμα",
        "OPEN_FILE_ERROR_PREFIX": "Αποτυχία ανοίγματος αρχείου:\n",
        "OPENPYXL_MISSING_EXCEL_EXPORT": "Δεν βρέθηκε το πακέτο openpyxl. Εγκαταστήστε το για εξαγωγή Excel.",
        "SF6_SUMMARY_FMT": (
            "Εγκατεστημένο SF6 (ενεργά): {installed_sf6:.2f} kg | "
            "Ενεργά στοιχεία SF6: {active_elements} | Υποσταθμοί με SF6: {active_substations}\n"
            "Έτος: {year_value} | Διαρροές: {total_leakage:.2f} kg | Ποσοστό: {percentage:.2f}%"
        ),
        "SF6_SUMMARY_SHEET_TITLE": "Σύνοψη",
        "SF6_SUMMARY_TOTAL_INSTALLED": "ΣΥΝΟΛΙΚΗ ΕΓΚΑΤΕΣΤΗΜΕΝΗ ΠΟΣΟΤΗΤΑ (kg)",
        "SF6_SUMMARY_LEAKS_YEAR_FMT": "ΔΙΑΡΡΟΕΣ {year} (kg)",
        "SF6_SUMMARY_PERCENT_YEAR_FMT": "ΠΟΣΟΣΤΟ ΔΙΑΡΡΟΩΝ {year}",
        "SF6_SUBSTATION_HEADER": "Υποσταθμός",
        "SF6_TOTAL_LEAKAGE_HEADER": "Σύνολο Διαρροών (kg)",
        "SF6_TABLE_TITLE": "ΠΙΝΑΚΑΣ 4: ΠΗΓΗ ΕΚΠΟΜΠΩΝ ΑΠΟ ΕΞΟΠΛΙΣΜΟ ΧΡΗΣΗΣ SF6",
        "SF6_TABLE_HEADERS": [
            "Α/Α",
            "ΒΟΚ ή ΠΕΡΙΟΧΗ",
            "ΕΓΚΑΤΑΣΤΑΣΗ (Πχ. Όνομα Υ/Σ)",
            "ΜΟΝΑΔΑ ΜΕΤΡΗΣΗΣ",
            "ΠΛΗΡΩΣΗ Ή ΑΝΤΙΚΑΤΑΣΤΑΣΗ (ΜΕΘΟΔΟΛΟΓΙΑ)",
            "ΣΥΝΟΛΙΚΗ ΕΓΚΑΤΕΣΤΗΜΕΝΗ ΠΟΣΟΤΗΤΑ (kg)",
            "ΠΟΣΟΤΗΤΑ ΔΙΑΡΡΟΩΝ (kg)",
            "ΗΜ/ΝΙΑ",
            "ΥΠΕΥΘΥΝΟΣ ΣΥΝΕΡΓΕΙΟΥ",
            "ΥΠΟΓΡΑΦΗ",
        ],
        "ORG_SHORT": "ΔΕΕΔ",
        "TEMPLATE_SUBSTATIONS_EXAMPLES": [
            ("Υποσταθμός Α", "https://maps.google.com/?q=example1", "2025-01-15"),
            ("Υποσταθμός Β", "https://maps.google.com/?q=example2", "2025-01-20"),
        ],
        "TEMPLATE_ELEMENTS_EXAMPLES": [
            (
                "Υποσταθμός Α",
                "Διακόπτης ΜΤ",
                "Main Breaker",
                "SN-001",
                "2025-01-20",
                "SF6",
                "Κεντρικός",
                "Ενεργή",
                "ΠΥΛΗ 1",
                "SF6-400",
                "ABB",
                "Εσωτερικού",
            ),
            (
                "Υποσταθμός Α",
                "Μετασχηματιστής 150/20KV",
                "Transformer 1",
                "SN-002",
                "2025-01-18",
                "",
                "",
                "Ενεργή",
                "ΠΥΛΗ 1",
                "GEAFOL",
                "Siemens",
                "Εξωτερικού",
            ),
        ],
        "ERROR_FMT": "Σφάλμα: {exc}",
    },
}

STRINGS_EN = {
    "BUTTONS": {
        "IMPORT": "Import",
        "ADD": "Add",
        "VIEW": "View",
        "REFRESH": "Refresh",
        "OPEN": "Open",
        "REPLACE": "Replace",
        "SKIP": "Skip",
        "REPLACE_ALL": "Replace All",
        "SKIP_ALL": "Skip All",
        "CONFIRM": "Confirm",
        "EDIT": "Edit",
        "LIST": "List",
        "CANCEL": "Cancel",
        "EMAIL": "Email",
        "APPLY": "Apply",
        "BACKUP_APPLY": "Backup & Apply",
        "CLOSE": "Close",
        "INSPECTIONS": "Inspections",
        "SAVE": "Save",
        "BACK": "Back",
        "MAINTENANCE": "Maintenance",
        "INSPECT": "Inspect",
        "DELETE": "Delete",
        "UPDATE": "Update",
        "YES": "Yes",
        "NO": "No",
        "OK": "OK",
        "COPY": "Copy",
        "BROWSE_FILE": "Browse file",
        "ADD_MAINTENANCE": "+ Add New Maintenance",
        "ADD_MODEL": "+ Add New Model",
        "LOGIN": "Login",
        "LOGOUT": "Logout",
        "RESET": "Reset",
    },
    "TITLES": {
        "ERROR": "Error",
        "SUCCESS": "Success",
        "INFO": "Info",
        "IMPORT_MENU": "Import from file",
        "IMPORT_ANDROID": "Import changes from Android",
        "PREVIEW_CHANGELOG": "Change log preview",
        "INSPECTION_ENTRY": "Inspection Entry",
        "INSPECTION_HISTORY": "Inspection History",
        "INSPECTION_DETAILS": "Inspection Details",
        "IMPORT_SUBSTATIONS_TITLE": "Import Substations",
        "SETTINGS": "Settings",
        "LOGIN": "Login",
    },
    "MESSAGES": {
        "APP_TITLE": "HEDNO Substations DEDD/KSMTH/TEI",
        "APP_INFO_SHORT": "App Info",
        "APP_INFO_TITLE": "Application Information",
        "APP_INFO_BODY": (
            "HEDNO Substations DEDD/KSMTH/TEI\n"
            "Version: {version}\n"
            "DB Version: {db_version}\n"
            "Compatibility: {compat_status}\n\n"
            "Application features:\n"
            "• View and manage substation database\n"
            "• Add/edit/delete substations and elements\n"
            "• Circuit breaker categories (SF6/Oil/Low Oil)\n"
            "• Manage element types (models/manufacturers/cycles)\n"
            "• Maintenance records\n"
            "• Import maintenance from e-mail (.eml)\n"
            "• Maintenance history (all/by substation)\n"
            "• Breaker measurements (insulation/passage/operations)\n"
            "• SF6 gas quality & leaks (kg)\n"
            "• SF6 management (leakage report by year)\n"
            "• Export SF6 Excel reports (summary & per substation)\n"
            "• Print maintenance PDF reports\n"
            "• Inspections (entry/view/history)\n"
            "• Isolation requests\n"
            "• Import substations/elements from CSV/Excel\n"
            "• PDF & Excel reports\n\n"
            "App folder: {app_dir}"
        ),
        "LOADING": "Loading...",
        "COPY": "Copy",
        "DASH": "-",
        "ENTER_PATH": "Please enter a path or select a file!",
        "FILE_PATH_LABEL": "File path:",
        "FILE_PATH_HINT": "File path",
        "FILE_NOT_FOUND": "File not found!",
        "PLEASE_SELECT_PDF": "Please select a PDF file!",
        "UNSUPPORTED_FILE_FORMAT": "Unsupported file format",
        "FILE_HAS_NO_DATA": "The file contains no data.",
        "IMPORT_FAILED": "Import failed:",
        "IMPORT_SUCCESS": "Import successful.",
        "SELECT_MONOGRAM_PDF_TITLE": "Select single-line PDF",
        "CHANGELOG_FILE_LABEL": "Change log file path (.jsonl):",
        "NO_SUBSTATIONS": "No substations!",
        "EMPTY_DB": "Empty database",
        "ADD_NEW_SUBSTATION_PROMPT": "Or add a new substation:",
        "PLEASE_SELECT_OR_ADD_SUBSTATION": "Please select a substation or add a new one.",
        "ENTER_SUBSTATION_NAME": "Please enter substation name!",
        "SUBSTATION_LABEL": "Substation:",
        "SUBSTATION_NAME_LABEL": "Substation Name:",
        "SUBSTATION_NAME_HINT": "Substation Name",
        "SUBSTATION_NEW_HINT": "New substation name",
        "SUBSTATION_IS_THESSALONIKI": "Thessaloniki Substation",
        "SUBSTATION_ADDED": "Substation added!",
        "SUBSTATION_EXISTS": "Substation already exists.",
        "SELECT_SUBSTATION": "Select Substation:",
        "SELECT_SUBSTATION_BTN": "Select Substation",
        "PROMPT_SUBSTATION_NOT_FOUND_TITLE": "Substation not found",
        "PROMPT_SUBSTATION_SELECT": "Select substation for import:",
        "SUBSTATION_NOT_FOUND": "Substation not found.",
        "MISSING_SUBSTATIONS_WILL_CREATE": "The following substations do not exist and will be created:",
        "NEW_SUBSTATIONS_TITLE": "New Substations Detected",
        "MAINTENANCE_SAVED_CHANGELOG": "Maintenance was recorded in the change log.",
        "MAINTENANCE_DELETED": "Maintenance deleted!",
        "MAINTENANCE_NOT_FOUND": "Maintenance not found.",
        "NO_MAINTENANCES": "No maintenance records",
        "NO_MAINT_FOR_SUBSTATION": (
            "No maintenance records for substation \"{substation_name}\".\n"
            "Use the button above to add one."
        ),
        "MAINT_HISTORY_LABEL": "Maintenance History",
        "MAINTENANCE_NAME_FMT": "SS {substation_name} - {date}",
        "NO_RECORD_ELEMENTS": "No elements for this maintenance.",
        "DATE_TIME_LABEL": "Date & Time:",
        "DATE_REQUIRED": "Date is required!",
        "DATE_PREFIX": "Date:",
        "MAINT_TYPE_LABEL": "Maintenance Type:",
        "MAINTENANCE_TYPES": ["Recurring maintenance", "Fault", "Visual inspection"],
        "MAINT_TYPE_DEFAULT": "Recurring maintenance",
        "RESPONSIBLE_LABEL": "Maintenance Responsible (required):",
        "RESPONSIBLE_REQUIRED": "Maintenance responsible is required!",
        "CREW_LABEL": "Maintenance Crew (optional):",
        "OVERALL_COMMENTS_LABEL": "General Maintenance Comments:",
        "ELEMENTS_SECTION_LABEL": "Elements maintained (at least 1):",
        "NO_ELEMENTS_IN_SUBSTATION": "There are no elements in this substation",
        "SELECT_AT_LEAST_ONE_ELEMENT": "You must select at least one element!",
        "ADD_ELEMENT_BEFORE_CONTINUE": "Add at least one element before continuing.",
        "INSPECTION_SAVED": "Inspection saved!",
        "INSPECTION_ROWS": [
            "Check external & internal doors of the substation",
            "Check interior of the building (lighting, air conditioning, etc)",
            "Check surrounding area (vegetation, trees, lighting, etc)",
            "General inspection of fire protection equipment",
            "Visual check for oil leakage/level/temperature, silica gel on the transformer",
            "Visual check for oil leakage or SF6 pressure or air pressure on 150kV & 20kV circuit breakers",
            "Check transformer fan operation",
            "Visual check of injection transformer, CTs, VTs, service transformer, neutral resistor (temperature)",
            "Visual check of insulators (pollution, scratches, etc)",
            "Visual check of fuses and capacitors",
            "Check markings on transformer panels, 150kV & 20kV switchgear",
            "Take photo when required",
            "Visual check of gates, A/Z and general structures for nests, breaks, insulators, branches, wires, etc",
            "Visual check on 20kV switchgear panels (alarms, indications, doors) and check for noise/ionization",
            "Check for humidity (basement, cable channels), dehumidifiers, heaters, portable fire extinguishers",
            "Check 110V charger visually with voltage/current measurement and recording",
            "Check for DC loss alarm on main DC panel",
            "Visual check for leaks in battery elements",
            "Visual check of generators and their bridges on the 1st pole of each line (broken, insulators, etc)",
            "Check operation of digital system (operations, indications, markings)",
            "PC power supply",
            "Views and suggestions for better operation of equipment and building in general",
        ],
        "INSPECTION_SECTION_2": "[b]Substation Areas Check[/b]",
        "INSPECTION_SECTION_3": "[b]150/20kV Transformer & 150kV/20kV Breakers[/b]",
        "INSPECTION_SECTION_3A": "[b]Outdoor 20 kV gates[/b]",
        "INSPECTION_SECTION_3B": "[b]Outdoor 20 kV gates[/b]",
        "INSPECTION_SECTION_4": "[b]Control building & Aux. Services[/b]",
        "INSPECTION_SECTION_5": "[b]Line Disconnectors[/b]",
        "INSPECTION_SECTION_6": "[b]Control PC[/b]",
        "INSPECTION_SECTION_7": "[b]Views[/b]",
        "INSPECTION_BASE_FIELDS": [
            "Substation",
            "Form No.",
            "Month",
            "Inspector Name",
            "Region",
            "Day",
            "Year",
            "Date",
        ],
        "IMPORT_INSPECTIONS_TITLE": "Import Inspections",
        "IMPORT_INSPECTIONS_DONE": "Import completed ({inserted} records).",
        "IMPORT_INSPECTIONS_DIALOG": "Import inspections from file",
        "NO_INSPECTIONS": "There are no inspection records. Do you want to create one?",
        "INSPECTION_COUNT_FMT": "{count} inspection records",
        "SUBSTATION_INSPECTION_HISTORY_TITLE_FMT": "Inspection History - {substation_name}",
        "SUBSTATION_INSPECTION_COUNT_FMT": "{count} inspection records for substation {substation_name}",
        "SUBSTATION_LABEL_PLAIN": "Substation",
        "DATE_PLAIN": "Date",
        "MEASUREMENT_RESISTANCE_HEADER": "RESISTANCE MEASUREMENT (Ohm)",
        "NO_PEOPLE": "No people recorded. Please add staff.",
        "SURNAME_LABEL": "Surname:",
        "NAME_LABEL": "Name:",
        "ROLE_LABEL": "Role:",
        "EMAIL_LABEL": "Email:",
        "EMAIL_RECIPIENT_LABEL": "Email report recipients",
        "ACTIVE_LABEL": "Active",
        "STAFF_LOAD_FAILED": "Failed to load staff management.",
        "PERSON_NOT_FOUND": "Person not found!",
        "EDIT_PERSON_TITLE": "Edit Person",
        "SURNAME_ROLE_REQUIRED": "Surname and role are required!",
        "PERSON_IN_USE": "This person has been used in maintenance. Delete only after removing from history or deactivate.",
        "CONFIRM_DELETE_PERSON_FMT": "Are you sure you want to delete\nperson \"{person_name}\"?",
        "NO_AVAILABLE_RESPONSIBLE": "No available maintenance responsible with required permissions. Add or update staff.",
        "SF6_LEAK_METHODOLOGY_REQUIRED": "SF6 leakage requires a methodology (Filling/Replacement).",
        "GATE_LABEL": "Gate",
        "DIVISION_LABEL": "Division",
        "MAINT_USER_LABEL": "Operator",
        "MODEL_NOT_USED": "Model is not used by any element.",
        "MODEL_NAME_REQUIRED": "Model name is required!",
        "MODEL_SERVICE_CYCLE_NUM": "Maintenance cycle must be a number!",
        "MODEL_POWER_NUM": "Rated power must be a number!",
        "MODEL_ADDED": "Model added!",
        "MODEL_DELETED": "Model deleted successfully!",
        "MODEL_NOT_FOUND": "Model not found!",
        "MODEL_CHECK_TITLE": "Model Check",
        "NEW_MODELS_HEADER": "[b]New Models (will be added):[/b]",
        "EXISTING_MODELS_DIFF_HEADER": "[b]Existing Models with Different Data:[/b]",
        "NO_ELEMENTS": "No elements",
        "NO_ELEMENTS_PAREN": "(No elements)",
        "NO_ELEMENTS_FOR_ITEM": "No elements registered for this item.",
        "NO_MODELS": "No models",
        "NO_INACTIVE_ELEMENTS": "No inactive elements in this substation",
        "ELEMENT_TYPES": [
            "Διακόπτης ΥΤ",
            "Διακόπτης ΜΤ",
            "Μετασχηματιστής 150/20KV",
            "Motor Drive",
            "Μ/Σ Έγχυσης",
            "Μ/Σ Έντασης",
            "Μ/Σ Τάσης",
            "Μ/Σ ΧΤ/ΜΤ (ΒΜΣ)",
            "Αποζεύκτης",
            "Ασφαλειοαποζεύκτης",
            "Γειωτής",
            "Συστοιχία Πυκνωτών",
            "Αντίσταση Κόμβου",
            "Αλεξικέραυνο",
            "Συστοιχία Συσσωρευτών",
        ],
        "ELEMENT_BREAKER_YT": "Διακόπτης ΥΤ",
        "ELEMENT_BREAKER_MT": "Διακόπτης ΜΤ",
        "VIDAR_VACUUM_CHECK_LABEL": "VACUUM CHECK (VIDAR):",
        "VIDAR_LABEL_FB": "FB-FB:",
        "VIDAR_LABEL_FC": "FC-FC:",
        "VIDAR_HINT": "0.0",
        "VIDAR_SECTION_TITLE": "VIDAR Vacuum Check",
        "PHASE_TO_PHASE_LABEL": "FA-FA",
        "PHASE_TO_PHASE_LABEL_COLON": "FA-FA:",
        "INSULATION_RESISTANCE_CLOSED_TITLE": "Insulation Resistance - Breaker Closed (Ground)",
        "INSULATION_RESISTANCE_OPEN_TITLE": "Insulation Resistance - Breaker Open (Phase-Phase)",
        "INSULATION_PASSAGE_TITLE": "Passage Resistance (uOhm)",
        "INSULATION_MEASUREMENT_CLOSED_HEADER": "INSULATION RESISTANCE MEASUREMENT - BREAKER CLOSED (PH-GND):",
        "INSULATION_MEASUREMENT_OPEN_HEADER": "INSULATION RESISTANCE MEASUREMENT - BREAKER OPEN (PH-PH):",
        "INSULATION_PASSAGE_MEASUREMENT_CLOSED_HEADER": "PASSAGE RESISTANCE (uOhm) - BREAKER CLOSED:",
        "INSULATION_HINT": "0.0",
        "INSULATION_LABEL_FA_GND": "FA-GND",
        "INSULATION_LABEL_FB_GND": "FB-GND",
        "INSULATION_LABEL_FC_GND": "FC-GND",
        "INSULATION_LABEL_FA": "FA-FA",
        "INSULATION_LABEL_FB": "FB-FB",
        "INSULATION_LABEL_FC": "FC-FC",
        "ELEMENT_BREAKER_SUBSTR": "Διακόπτης",
        "BREAKER_CATEGORIES_ALL": ["SF6", "Πτωχού Ελαίου", "Ελαίου", "Κενού"],
        "BREAKER_CATEGORIES_HV": ["SF6", "Ελαίου"],
        "BREAKER_CATEGORIES_MV": ["SF6", "Πτωχού Ελαίου", "Ελαίου", "Κενού"],
        "BREAKER_TYPES": ["Κεντρικός", "Γραμμής", "Διασυνδετικός", "Διακόπτης Πυκνωτών"],
        "OPERATING_STATUS": ["Ενεργή", "Ανενεργή"],
        "INSTALLATION_SPACE": ["Εσωτερικός", "Εξωτερικός"],
        "VOLTAGE_LEVELS": ["(Κενό)", "150/20KV", "20KV", "150KV", "20KV/400V"],
        "VIEW_ELEMENT_TITLE": "View Element",
        "ELEMENTS_LIST_LABEL": "Elements maintained:",
        "PLEASE_SELECT_BREAKER_CATEGORY": "Please select breaker category!",
        "PLEASE_SELECT_EML": "Please select a .eml file!",
        "INACTIVE_ELEMENTS": "Inactive Elements ({count})",
        "ELEMENT_ADDED": "Element added to {substation_name}!",
        "ELEMENT_DUPLICATE": "An element with this name already exists in this substation!",
        "VIEW_ACTIVE_ELEMENTS": "View active elements ({count})",
        "FILTER_TYPE": "Type filter:",
        "FILTER_GATE": "Gate filter:",
        "FILTER_SUBSTATION": "Substation filter:",
        "LOC": "Location",
        "ADOPTION": "Adoption",
        "INFO": "Details",
        "GATES": "Gates",
        "CAPACITORS": "Capacitors",
        "MAINTENANCES": "Maintenances",
        "LAST": "Last",
        "SINGLE_LINE": "Single-line",
        "MONTHS": [
            "Ιανουάριος",
            "Φεβρουάριος",
            "Μάρτιος",
            "Απρίλιος",
            "Μάιος",
            "Ιούνιος",
            "Ιούλιος",
            "Αύγουστος",
            "Σεπτέμβριος",
            "Οκτώβριος",
            "Νοέμβριος",
            "Δεκέμβριος",
        ],
        "DAYS": [
            "Δευτέρα",
            "Τρίτη",
            "Τετάρτη",
            "Πέμπτη",
            "Παρασκευή",
            "Σάββατο",
            "Κυριακή",
        ],
        "BREAKER_LABEL_CENTRAL": "Κεντρικός",
        "BREAKER_LABEL_INTERCON": "Διασυνδετικός",
        "BREAKER_LABEL_CAPACITOR": "Διακόπτης Πυκνωτών",
        "BREAKER_LABEL_LINE": "Γραμμής",
        "GATE_PREFIX": "ΠΥΛΗ",
        "ALL_LABEL": "(All)",
        "DIVISION_DEFAULT": "ΤΜΘ",
        "PICKER_EMPTY_SELECTION": "Picker returned empty selection (None).",
        "ANDROID_FILECHOOSER_FALLBACK": "Android file chooser is not available. Use the file list in the window.",
        "FILECHOOSER_NOT_AVAILABLE": "File chooser is not available",
        "FILECHOOSER_ANDROID_ONLY": "File chooser is available only on Android.",
        "FILECHOOSER_INTERNAL_ERROR": "File chooser internal error.",
        "FILECHOICE_CANCELLED": "File choice failed or was canceled.",
        "MODE_LABEL_LOCAL": "Source: Local Database",
        "LOCAL_DB_BUTTON": "Local Database",
        "CHANGELOG_BUTTON": "Change-log",
        "CHANGELOG_RECORDED": "Change recorded in the change log.",
        "ADOPTION_DATE_LABEL": "Adoption Date:",
        "NAME_REQUIRED": "Name is required",
        "ELEMENT_TYPE_LABEL": "Element Type:",
        "RETRY": "Retry",
        "COPYING_FILE": "Copying file...",
        "COPYING_FILE_MSG": "Copying file from filesystem. Please wait...",
        "OVERALL_COMMENTS_HINT": "General maintenance comments...",
        "GOOGLE_MAPS_LINK": "Google Maps Link",
        "SHARE_BUTTON": "Share",
        "COPY_PATH": "Copy path",
        "LOADING_ELEMENTS": "Loading elements...",
        "RETRY_LOAD": "Retry loading",
        "ELEM_COMMENTS_HINT": "Comments for this element...",
        "SHOW_DB_BUTTON": "View substations database",
        "IMPORT_BUTTON": "Import from file",
        "MAINTENANCE_BUTTON": "Maintenances",
        "INSPECTION_BUTTON": "Inspections",
        "ISOLATION_BUTTON": "Isolation Requests",
        "SF6_BUTTON": "SF6",
        "MODELS_BUTTON": "Manage Element Types",
        "PEOPLE_BUTTON": "Manage Staff",
        "TOOLTIP_EDIT": "Edit",
        "TOOLTIP_DELETE": "Delete",
        "TOOLTIP_VIEW": "View",
        "TOOLTIP_MAINTENANCE": "Maintenance",
        "TOOLTIP_INSPECTION": "Inspection",
        "VIEW_SHORT": "View",
        "PDF_BUTTON": "PDF",
        "VIEW_PROMPT": "Select what you want to view:",
        "SEARCH_HINT": "Search (name/date)",
        "PREVIOUS": "Previous",
        "NEXT": "Next",
        "LOAD_MORE": "Load more",
        "PAGE_LABEL_TEMPLATE": "Page {page}",
        "ALL_SUBSTATIONS_LABEL": "All substations",
        "VIEW_SELECTION_TITLE": "View Selection",
        "SORT_OPTIONS": [
            "Date (desc)",
            "Date (asc)",
            "Substation A-Z",
        ],
        "PAGE_SIZE_LABEL": "Items per page",
        "PAGE_SIZE_OPTIONS": ["10", "20", "30", "50"],
        "SELECT_PROMPT": "Select",
        "SHOW_ALL_SUBSTATIONS": "View All Substations",
        "SELECT_ALL_BTN": "Select All",
        "ADD_MENU_TITLE": "Add substations and elements",
        "ADD_SUBSTATION_BTN": "Add New Substation",
        "ADD_ELEMENT_BTN": "Add New Element",
        "ADD_ELEMENTS_TITLE": "Add elements",
        "ADD_SUBSTATION_TITLE": "Add Substation",
        "ADD_ELEMENT_TITLE": "Add Element",
        "ADD_MODEL_TITLE": "Add New Model",
        "ADD_MANUAL": "Add Manual",
        "ADD_ELEMENTS_PROMPT": "Add elements for the new substation before continuing:",
        "CONTINUE": "Continue",
        "OPEN_LOCAL_DB_TITLE": "Open Local Database",
        "OPEN_FOLDER": "Open folder",
        "CONFIRM_DELETE_TITLE": "Delete Confirmation",
        "DUPLICATE_OPTIONS_INCOMPLETE": (
            "Complete the choices for all duplicates or use 'Replace All' / 'Skip All'."
        ),
        "RESPONSIBLE_NOT_FOUND_TITLE": "Responsible not found",
        "FORM_NUMBER": "Form No.:",
        "FORM_NUMBER_HINT": "Form No.",
        "ELEMENT_NAME_LABEL": "Element Name",
        "ELEMENT_NAME_HINT": "Element Name",
        "SERIAL_NUMBER_LABEL": "Serial Number",
        "SERIAL_NUMBER_HINT": "Serial Number",
        "ELEMENT_MANUFACTURE_YEAR_LABEL": "Manufacture Year",
        "ELEMENT_MANUFACTURE_YEAR_HINT": "YYYY",
        "MAINTENANCE_DATE_LABEL": "Last Maint.",
        "MAINTENANCE_DATE_HINT": "YYYY-MM-DD",
        "MANUFACTURER_LABEL": "Manufacturer",
        "MANUFACTURER_HINT": "Manufacturer",
        "MODEL_LABEL": "Model",
        "MODEL_HINT": "Model",
        "MODEL_VERSION_LABEL": "Model Version",
        "MODEL_VERSION_HINT": "Version",
        "INSTALLATION_SPACE_LABEL": "Installation Space",
        "OPERATING_STATUS_LABEL": "Operating Status",
        "MAINTENANCE_CYCLE_LABEL": "Maintenance Cycle",
        "MAINTENANCE_CYCLE_HINT": "Number",
        "DATE_LABEL": "Date:",
        "DATE_HINT": "YYYY-MM-DD",
        "REGION_LABEL": "Region:",
        "REGION_HINT": "Region",
        "INSPECTOR_LABEL": "Inspector Name:",
        "MONTH_LABEL": "Month:",
        "DAY_LABEL": "Day:",
        "YEAR_LABEL": "Year:",
        "OBSERVATIONS_HINT": "Observations",
        "EMAIL_RECIPIENTS_MISSING": (
            "No email recipients. Add recipients from Staff Management."
        ),
        "MAINTENANCE_HEADER": "Maintenance: {name}",
        "PEOPLE_SUMMARY": "Responsible: {resp} | Crew: {crew}",
        "COMMENTS_LABEL": "Comments: {text}",
        "MAINTENANCE_COMMENTS_SECTION": "Maintenance Comments",
        "ELEMENT_COMMENTS_SECTION": "Element Comments",
        "MAINT_LAST_LABEL": "Last Maintenance: {date}",
        "INVALID_DATE_FORMAT": "Invalid date format! Use: YYYY-MM-DD HH:MM",
        "END_BEFORE_START": "End date must be after start!",
        "ERROR_DURING_CHECK_PREFIX": "Error during check: ",
        "RECORD_NOT_FOUND": "Record not found.",
        "TEMPLATE_SUBSTATIONS_TITLE": "Substations Template",
        "TEMPLATE_ELEMENTS_TITLE": "Elements Template",
        "OPENPYXL_MISSING": "openpyxl is not installed!",
        "TEMPLATE_SUBSTATIONS_HEADERS": ["Name", "Location", "Adoption Date"],
        "TEMPLATE_ELEMENTS_HEADERS": [
            "Substation Name",
            "Element Type",
            "Name",
            "Serial Number",
            "Maintenance Date",
            "Breaker Type",
            "Breaker Role",
            "Operating Status",
            "Gate",
            "Model Name",
            "Model Manufacturer",
            "Model Installation Space",
        ],
        "ITEM_DELETED": "Element deleted!",
        "MAINTENANCE_UPDATED": "Maintenance updated!",
        "MAINTENANCE_CREATED": "Maintenance created!",
        "CHANGES_SAVED": "Changes saved!",
        "CONFIRM_DELETE_SUBSTATION_FMT": (
            "Are you sure you want to delete\n"
            "substation \"{substation_name}\"\n"
            "and ALL its elements?"
        ),
        "CONFIRM_DELETE_MAINT_FMT": "Are you sure you want to delete\nthis maintenance?",
        "UNREGISTERED_PLACEHOLDER": "(Unregistered)",
        "EMPTY_PLACEHOLDER": "(Empty)",
        "MODEL_SELECT_PROMPT": "Select model",
        "BREAKER_TYPE_LABEL": "Breaker Type:",
        "BREAKER_CATEGORY_LABEL": "Breaker Category:",
        "RATED_POWER_HINT": "e.g. 50",
        "SETTINGS_TOOLTIP": "Settings",
        "LANGUAGE_LABEL": "Language:",
        "LANGUAGE_OPTION_EL": "Greek",
        "LANGUAGE_OPTION_EN": "English",
        "LANGUAGE_SAVED_RESTART": "Language saved. Restart the app to apply.",
        # --- Database Path ---
        "DB_PATH_LABEL": "Database Path:",
        "DB_PATH_BUTTON": "Change",
        "DB_PATH_SAVED_RESTART": "Database path saved. Restart the app to apply.",
        "DB_PATH_DEFAULT": "(Default)",
        "DB_PATH_SELECT": "Select database file",
        "DB_FILE_NOT_FOUND": "Database file not found!",
        "DB_FILE_INVALID": "Invalid database file!",
        # --- Login / User Session ---
        "LOGIN_TITLE": "User Login",
        "LOGIN_PROMPT": "Select your name to login:",
        "LOGIN_SUCCESS_FMT": "Welcome, {name}!",
        "USER_LABEL": "User:",
        "LOGGED_IN_AS_FMT": "Logged in as: {name} ({role})",
        "NO_USER_LOGGED_IN": "No user logged in",
        "LOGOUT_CONFIRM": "Do you want to logout?",
        "LOGIN_REQUIRED": "You must login to use the application.",
        "FILE_DIALOG_SELECT_TITLE": "Select file",
        "FILE_DIALOG_SAVE_TITLE": "Save file",
        "FILE_DIALOG_ALL_FILES": "All files",
        "SF6_MANAGEMENT_TITLE": "SF6 Management",
        "PRINT": "Print",
        "EXCEL": "Excel",
        "ELEMENT_LABEL": "Element",
        "LEAKAGE_LABEL": "Leakage (kg)",
        "NO_LEAK_ENTRIES": "No leakage entries for the year.",
        "PDF_CREATED": "PDF created:\n{path}",
        "PDF_CREATE_FAILED": "Failed to create PDF:\n{err}",
        "EXCEL_CREATED": "Excel created:\n{path}",
        "EXCEL_CREATE_FAILED": "Failed to create Excel:\n{err}",
        "PDF_CREATED_TITLE": "PDF Created",
        "PDF_ELEMENT_CREATED_FMT": (
            "The PDF file for element \"{element_name}\"\n"
            "was created successfully!\n\n"
            "Saved to:\n{pdf_path}"
        ),
        "OPEN_FILE_NOT_FOUND": "File not found!",
        "OPEN_FILE_ERROR_TITLE": "Error",
        "OPEN_FILE_ERROR_PREFIX": "Failed to open file:\n",
        "OPENPYXL_MISSING_EXCEL_EXPORT": "openpyxl package not found. Install it for Excel export.",
        "SF6_SUMMARY_FMT": (
            "Installed SF6 (active): {installed_sf6:.2f} kg | "
            "Active SF6 elements: {active_elements} | Substations with SF6: {active_substations}\n"
            "Year: {year_value} | Leakages: {total_leakage:.2f} kg | Percentage: {percentage:.2f}%"
        ),
        "SF6_SUMMARY_SHEET_TITLE": "Summary",
        "SF6_SUMMARY_TOTAL_INSTALLED": "TOTAL INSTALLED AMOUNT (kg)",
        "SF6_SUMMARY_LEAKS_YEAR_FMT": "LEAKAGES {year} (kg)",
        "SF6_SUMMARY_PERCENT_YEAR_FMT": "LEAKAGE PERCENT {year}",
        "SF6_SUBSTATION_HEADER": "Substation",
        "SF6_TOTAL_LEAKAGE_HEADER": "Total Leakages (kg)",
        "SF6_TABLE_TITLE": "TABLE 4: EMISSIONS SOURCE FROM SF6 EQUIPMENT",
        "SF6_TABLE_HEADERS": [
            "No.",
            "BOK or Region",
            "Facility (e.g., Substation Name)",
            "Measurement Unit",
            "Filling or Replacement (Methodology)",
            "TOTAL INSTALLED AMOUNT (kg)",
            "LEAKAGE AMOUNT (kg)",
            "DATE",
            "CREW RESPONSIBLE",
            "SIGNATURE",
        ],
        "ORG_SHORT": "HEDNO",
        "TEMPLATE_SUBSTATIONS_EXAMPLES": [
            ("Substation A", "https://maps.google.com/?q=example1", "2025-01-15"),
            ("Substation B", "https://maps.google.com/?q=example2", "2025-01-20"),
        ],
        "TEMPLATE_ELEMENTS_EXAMPLES": [
            (
                "Substation A",
                "Διακόπτης ΜΤ",
                "Main Breaker",
                "SN-001",
                "2025-01-20",
                "SF6",
                "Κεντρικός",
                "Ενεργή",
                "ΠΥΛΗ 1",
                "SF6-400",
                "ABB",
                "Εσωτερικού",
            ),
            (
                "Substation A",
                "Μετασχηματιστής 150/20KV",
                "Transformer 1",
                "SN-002",
                "2025-01-18",
                "",
                "",
                "Ενεργή",
                "ΠΥΛΗ 1",
                "GEAFOL",
                "Siemens",
                "Εξωτερικού",
            ),
        ],
        "ERROR_FMT": "Error: {exc}",
    },
}


def get_current_language() -> str:
    return CURRENT_LANGUAGE


def set_current_language(language: str) -> bool:
    global CURRENT_LANGUAGE
    if language not in SUPPORTED_LANGUAGES:
        return False
    CURRENT_LANGUAGE = language
    settings = _load_app_settings()
    settings["language"] = language
    _save_app_settings(settings)
    return True


def get_strings(language: str | None = None) -> dict:
    lang = language or CURRENT_LANGUAGE
    if lang not in ("el", "en"):
        lang = DEFAULT_LANGUAGE
    return {"el": STRINGS_EL, "en": STRINGS_EN}[lang]


# User session management
def get_current_user() -> dict | None:
    """Return the current logged-in user dict with keys: id, name, role.
    
    Returns None if no user is logged in.
    """
    settings = _load_app_settings()
    user_data = settings.get("current_user")
    if not user_data or not isinstance(user_data, dict):
        return None
    # Validate required fields
    if not all(k in user_data for k in ("id", "name", "role")):
        return None
    return user_data


def set_current_user(user_id: int, name: str, role: str) -> bool:
    """Set the current logged-in user and save to settings.
    
    Args:
        user_id: Database ID of the person
        name: Full name of the person
        role: Role of the person
    
    Returns:
        True if successful, False otherwise
    """
    try:
        settings = _load_app_settings()
        settings["current_user"] = {
            "id": int(user_id),
            "name": str(name),
            "role": str(role),
        }
        _save_app_settings(settings)
        return True
    except Exception:
        return False


def clear_current_user() -> bool:
    """Clear the current logged-in user (logout).
    
    Returns:
        True if successful, False otherwise
    """
    try:
        settings = _load_app_settings()
        if "current_user" in settings:
            del settings["current_user"]
        _save_app_settings(settings)
        return True
    except Exception:
        return False


# Database path management
def get_db_path() -> str:
    """Get the current database path setting.
    
    Returns:
        Database path from app_settings.json, or None if not set (uses default)
    """
    settings = _load_app_settings()
    return settings.get("db_path")


def set_db_path(db_path: str) -> bool:
    """Save a database path setting.
    
    Args:
        db_path: Full path to the database file
    
    Returns:
        True if successful, False otherwise
    """
    try:
        settings = _load_app_settings()
        settings["db_path"] = str(db_path)
        _save_app_settings(settings)
        return True
    except Exception:
        return False


def clear_db_path() -> bool:
    """Clear the saved database path setting (revert to default).
    
    Returns:
        True if successful, False otherwise
    """
    try:
        settings = _load_app_settings()
        if "db_path" in settings:
            del settings["db_path"]
        _save_app_settings(settings)
        return True
    except Exception:
        return False


def is_user_responsible_capable(role: str) -> bool:
    """Check if a user role can be assigned as maintenance responsible.
    
    Args:
        role: The role name to check
    
    Returns:
        True if the role can be maintenance responsible
    """
    allowed_responsible_roles = {
        "Μηχανικός",
        "Τομεάρχης ΤΕΙ",
        "Υποτομεάρχης ΤΕΙ",
        "Ειδικό Στέλεχος Γ'",
    }
    return role in allowed_responsible_roles


# Database versioning configuration
DB_METADATA_PATH = os.environ.get(
    "DB_METADATA_PATH",
    os.path.join(os.path.dirname(__file__), "db_metadata.json"),
)

# Define app version → DB version compatibility matrix
# Maps app versions to the min/max DB versions they can work with
DB_COMPATIBILITY = {
    "2.0.0": {"min_db": "1.0.0", "max_db": "1.0.0"},
    "2.1.0": {"min_db": "1.0.0", "max_db": "1.0.0"},
    "3.0.0": {"min_db": "1.0.0", "max_db": "1.0.0"},
}


def _get_db_metadata() -> dict:
    """Load database metadata from db_metadata.json.
    
    Returns:
        Dictionary with db_version, last_migration, created_at, app_version_created
    """
    try:
        with open(DB_METADATA_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except Exception:
        # If metadata doesn't exist yet, return defaults for initial version
        return {
            "db_version": "1.0.0",
            "last_migration": "000_initial_schema",
            "created_at": datetime.now().isoformat(),
            "app_version_created": get_app_version_string(),
        }


def _save_db_metadata(metadata: dict) -> None:
    """Save database metadata to db_metadata.json.
    
    Args:
        metadata: Dictionary with database version information
    """
    try:
        with open(DB_METADATA_PATH, "w", encoding="utf-8") as fh:
            json.dump(metadata, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_app_version_string() -> str:
    """Get the current application version.
    
    Returns:
        Version string (e.g., '2.0.0')
    """
    return os.environ.get("APP_VERSION", "2.0.0")


def get_db_version_string() -> str:
    """Get the current database version.
    
    Returns:
        Version string (e.g., '1.0.0')
    """
    metadata = _get_db_metadata()
    return metadata.get("db_version", "1.0.0")


def is_db_compatible(app_version: str = None, db_version: str = None) -> dict:
    """Check if the database version is compatible with the app version.
    
    Args:
        app_version: App version to check (defaults to current APP_VERSION)
        db_version: DB version to check (defaults to current db version)
    
    Returns:
        Dictionary with keys:
            - 'compatible': bool - True if versions are compatible
            - 'app_version': str - The app version checked
            - 'db_version': str - The db version checked
            - 'message': str - Human-readable compatibility message
    """
    if app_version is None:
        app_version = get_app_version_string()
    if db_version is None:
        db_version = get_db_version_string()
    
    # Get compatibility requirements for this app version
    compat_spec = DB_COMPATIBILITY.get(app_version, {})
    if not compat_spec:
        return {
            "compatible": False,
            "app_version": app_version,
            "db_version": db_version,
            "message": f"App version {app_version} not recognized in compatibility matrix"
        }
    
    min_db = compat_spec.get("min_db", "1.0.0")
    max_db = compat_spec.get("max_db", "1.0.0")
    
    # Simple version comparison (assumes MAJOR.MINOR.PATCH format)
    def parse_version(v_str):
        try:
            parts = v_str.split(".")
            return tuple(int(p) for p in parts)
        except (ValueError, AttributeError):
            return (0, 0, 0)
    
    db_tuple = parse_version(db_version)
    min_tuple = parse_version(min_db)
    max_tuple = parse_version(max_db)
    
    is_compatible = min_tuple <= db_tuple <= max_tuple
    
    if is_compatible:
        message = f"✓ Compatible: App {app_version} with DB {db_version}"
    else:
        message = f"✗ Incompatible: App {app_version} requires DB {min_db}-{max_db}, but DB is {db_version}"
    
    return {
        "compatible": is_compatible,
        "app_version": app_version,
        "db_version": db_version,
        "message": message
    }


class _StringsProxy:
    def __init__(self, data: dict):
        self._data = data

    def _current(self) -> dict:
        return self._data.get(CURRENT_LANGUAGE, self._data[DEFAULT_LANGUAGE])

    def __getitem__(self, key):
        return self._current()[key]

    def get(self, key, default=None):
        return self._current().get(key, default)

    def keys(self):
        return self._current().keys()

    def items(self):
        return self._current().items()

    def __contains__(self, item):
        return item in self._current()


STRINGS = _StringsProxy({"el": STRINGS_EL, "en": STRINGS_EN})
