"""Centralized UI strings to avoid hardcoded literals in code.

Structure: STRINGS is a nested dict grouping common labels, button texts,
popup titles and common messages. Add keys as needed for new UI text.
"""

STRINGS = {
    "BUTTONS": {
        "IMPORT": "Εισαγωγή",
        "ADD": "Προσθήκη",
        "CONFIRM": "Επιβεβαίωση",
        "EDIT": "Επεξ.",
        "LIST": "Λίστα",
        "CANCEL": "Ακύρωση",
        "APPLY": "Εφαρμογή",
        "BACKUP_APPLY": "Backup & Εφαρμογή",
        "CLOSE": "Κλείσιμο",
        "SAVE": "Αποθήκευση",
        "DELETE": "Διαγραφή",
        "UPDATE": "Ενημέρωση",
        "YES": "Ναι",
        "NO": "Όχι",
    },
    "TITLES": {
        "ERROR": "Σφάλμα",
        "SUCCESS": "Επιτυχία",
        "INFO": "Πληροφορία",
        "IMPORT_MENU": "Εισαγωγή από αρχείο",
        "IMPORT_ANDROID": "Εισαγωγή αλλαγών από Android",
        "PREVIEW_CHANGELOG": "Preview change log",
    },
    "MESSAGES": {
        "ENTER_PATH": "Παρακαλώ εισάγετε διαδρομή ή επιλέξτε αρχείο!",
        "FILE_NOT_FOUND": "Το αρχείο δεν βρέθηκε!",
        "IMPORT_FAILED": "Αποτυχία εισαγωγής:",
        "IMPORT_SUCCESS": "Επιτυχής εισαγωγή.",
        "NO_SUBSTATIONS": "Δεν υπάρχουν υποσταθμοί!",
        "INVALID_DATE_FORMAT": "Μη έγκυρη μορφή ημερομηνίας! Χρησιμοποιήστε: YYYY-MM-DD HH:MM",
        "END_BEFORE_START": "Η ημερομηνία λήξης πρέπει να είναι μετά την έναρξη!",
        "ISOLATION_SAVED": "Η αίτηση απομόνωσης καταχωρήθηκε!",
        "ISOLATION_UPDATED": "Η αίτηση ενημερώθηκε!",
        "ISOLATION_DELETED": "Η αίτηση διαγράφηκε!",
        "PLEASE_SELECT_OR_ADD_SUBSTATION": "Παρακαλώ επιλέξτε ή προσθέστε υποσταθμό.",
        "PLEASE_SELECT_PDF": "Παρακαλώ επιλέξτε αρχείο PDF!",
        "MODEL_NOT_USED": "Το μοντέλο δεν χρησιμοποιείται σε κανένα στοιχείο.",
        "PLEASE_SELECT_BREAKER_CATEGORY": "Παρακαλώ επιλέξτε κατηγορία διακόπτη!",
        "PLEASE_SELECT_EML": "Παρακαλώ επιλέξτε αρχείο .emλ!",
        "STORAGE_PERMISSIONS_REQUIRED": "Απαιτούνται δικαιώματα αποθήκευσης. Παρακαλώ επιτρέψτε τα και ξαναδοκιμάστε.",
        "NO_ELEMENTS": "Κανένα στοιχείο",
        "MAINTENANCE_SAVED_CHANGELOG": "Η συντήρηση καταχωρήθηκε στο change log.",
    },
}
