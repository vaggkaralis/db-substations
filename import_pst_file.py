"""
Import maintenance emails from an Outlook .pst file.
"""

import os
import sqlite3
import sys
import time
import subprocess
from datetime import datetime

from database import init_db
from email_eml_parser import _trim_first_message, _clean_body
from maintenance_email_importer import DEFAULT_DB_PATH, create_maintenance_from_email


OL_MAIL_ITEM_CLASS = 43


def _normalize_path(path: str) -> str:
    return os.path.normcase(os.path.abspath(path or ""))


def _get_sender_email(item):
    sender_email = (getattr(item, "SenderEmailAddress", "") or "").strip()
    if sender_email and "@" in sender_email:
        return sender_email

    try:
        sender = getattr(item, "Sender", None)
        if sender:
            exchange_user = sender.GetExchangeUser()
            if exchange_user and exchange_user.PrimarySmtpAddress:
                return exchange_user.PrimarySmtpAddress.strip()
    except Exception:
        pass

    return sender_email


def _to_iso(value):
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    try:
        return value.isoformat()
    except Exception:
        return str(value)


def _iter_folders(folder):
    yield folder
    try:
        subfolders = folder.Folders
        count = int(subfolders.Count)
    except Exception:
        return

    for idx in range(1, count + 1):
        try:
            subfolder = subfolders.Item(idx)
        except Exception:
            continue
        yield from _iter_folders(subfolder)


def _iter_mail_items(folder):
    try:
        items = folder.Items
        count = int(items.Count)
    except Exception:
        return

    for idx in range(count, 0, -1):
        try:
            item = items.Item(idx)
        except Exception:
            continue

        try:
            if int(getattr(item, "Class", 0)) != OL_MAIL_ITEM_CLASS:
                continue
        except Exception:
            continue

        yield item


def _ensure_outlook_running(progress_callback=None):
    """Ensure Outlook is running and MAPI is initialized.
    
    Returns the Outlook application object.
    """
    try:
        import win32com.client
    except ImportError:
        win32com = __import__('win32com.client', fromlist=['client'])
    
    if progress_callback:
        try:
            progress_callback(status="Σύνδεση με Outlook... ⏳")
        except Exception:
            pass
    
    # Try to get Outlook COM object (creates it if needed)
    # Give Outlook a few chances to initialize properly
    outlook = None
    last_error = None
    
    for attempt in range(3):
        try:
            outlook = win32com.client.Dispatch("Outlook.Application")
            # Try to ensure it's responding
            _ = outlook.Version
            break  # Success
        except Exception as e:
            last_error = str(e)
            if attempt < 2:
                time.sleep(2.0)  # Wait before retry
    
    if outlook is None:
        raise RuntimeError(
            "Δεν είναι δυνατή η σύνδεση με Outlook.\n\n"
            "Πιθανές λύσεις:\n"
            "1. Βεβαιωθείτε ότι το Outlook είναι εγκατεστημένο σωστά\n"
            "2. Κλείστε αυτή την εφαρμογή\n"
            "3. Ανοίξτε το Outlook χειροκίνητα\n"
            "4. Ολοκληρώστε οποιαδήποτε ρύθμιση που ζητάει το Outlook\n"
            "5. Κλείστε το Outlook\n"
            "6. Ανοίξτε ξανά αυτή την εφαρμογή\n\n"
            f"Λεπτομέρειες: {last_error[:100] if last_error else 'αγνωστο'}"
        )
    
    return outlook


def _init_pst_store(pst_path, progress_callback=None):
    """Initialize PST store and return (namespace, target_store).
    
    This is called synchronously so progress callbacks happen immediately,
    not delayed until iteration begins.
    """
    if sys.platform != "win32":
        raise RuntimeError("Η εισαγωγή από .pst υποστηρίζεται μόνο σε Windows.")

    try:
        import win32com.client
    except Exception as exc:
        raise RuntimeError(
            "Δεν βρέθηκε το pywin32. Απαιτείται για εισαγωγή αρχείων .pst."
        ) from exc

    # Check file size and warn if large
    try:
        file_size_mb = os.path.getsize(pst_path) / (1024 * 1024)
        status_msg = f"Φόρτωση αρχείου .pst ({file_size_mb:.0f} MB)...\nΑυτό μπορεί να διαρκέσει αρκετά λεπτά."
        if progress_callback:
            try:
                progress_callback(status=status_msg)
            except Exception:
                pass
    except Exception:
        if progress_callback:
            try:
                progress_callback(status="Σύνδεση με Outlook...")
            except Exception:
                pass

    # Ensure Outlook is running and get the COM object
    outlook = _ensure_outlook_running(progress_callback)
    
    if progress_callback:
        try:
            progress_callback(status="Αρχικοποίηση Outlook MAPI... ⏳")
        except Exception:
            pass
    
    # Try to get MAPI namespace with error handling
    namespace = None
    mapi_error = None
    
    for attempt in range(3):
        try:
            namespace = outlook.GetNamespace("MAPI")
            break
        except Exception as e:
            mapi_error = str(e)
            if attempt < 2:
                time.sleep(2.0)  # Wait before retry
    
    if namespace is None:
        raise RuntimeError(
            "Δεν είναι δυνατή η σύνδεση με το Outlook MAPI.\n\n"
            "Πιθανές λύσεις:\n"
            "1. Κλείστε αυτή την εφαρμογή\n"
            "2. Κλείστε το Outlook εντελώς\n"
            "3. Ανοίξτε το Outlook χειροκίνητα και περιμένετε να φορτωθεί πλήρως\n"
            "4. Αν σας ζητηθεί να ρυθμίσετε λογαριασμό, κάντε το\n"
            "5. Κλείστε το Outlook\n"
            "6. Ανοίξτε ξανά αυτή την εφαρμογή\n\n"
            f"Λεπτομέρειες: {mapi_error[:100]}"
        )
    
    if progress_callback:
        try:
            progress_callback(status="Φόρτωση αρχείου σε Outlook... ⏳")
        except Exception:
            pass

    store_added = False
    add_store_error = None
    
    # Try multiple times with delays in case MAPI isn't ready
    for attempt in range(3):
        try:
            namespace.AddStoreEx(pst_path, 3)
            store_added = True
            break
        except Exception as e1:
            add_store_error = str(e1)
            try:
                namespace.AddStore(pst_path)
                store_added = True
                break
            except Exception as e2:
                add_store_error = str(e2)
                if attempt < 2:
                    time.sleep(2.0)  # Wait before retry
    
    if not store_added:
        # Check if this is a profile-related error
        if "profile" in add_store_error.lower() or "δεδομένων" in add_store_error.lower():
            raise RuntimeError(
                "Το Outlook δεν μπορεί να φορτώσει το αρχείο .pst.\n\n"
                "Αυτό συμβαίνει όταν το Outlook δεν έχει ρυθμιστεί σωστά.\n\n"
                "Πιθανές λύσεις:\n"
                "1. Κλείστε αυτή την εφαρμογή\n"
                "2. Κλείστε το Outlook εντελώς\n"
                "3. Ανοίξτε το Outlook χειροκίνητα\n"
                "4. Ολοκληρώστε οποιαδήποτε ρύθμιση λογαριασμού που ζητάει\n"
                "5. Κλείστε το Outlook\n"
                "6. Ανοίξτε ξανά αυτή την εφαρμογή\n\n"
                f"Λεπτομέρειες: {add_store_error[:100]}"
            )
        else:
            raise RuntimeError(f"Αποτυχία φόρτωσης αρχείου .pst: {add_store_error}")

    if progress_callback:
        try:
            progress_callback(status="Αναζήτηση αρχείου σε Outlook... ⏳")
        except Exception:
            pass

    target_store = None
    wanted_path = _normalize_path(pst_path)

    stores = namespace.Stores
    store_count = int(stores.Count)
    for idx in range(1, store_count + 1):
        try:
            store = stores.Item(idx)
            store_path = _normalize_path(getattr(store, "FilePath", ""))
            if store_path and store_path == wanted_path:
                target_store = store
                break
        except Exception:
            continue

    if target_store is None:
        raise RuntimeError("Το αρχείο .pst άνοιξε, αλλά δεν εντοπίστηκε στο Outlook namespace.")

    if progress_callback:
        try:
            progress_callback(status="Ανάγνωση e-mail... ⏳")
        except Exception:
            pass

    return namespace, target_store


def _iter_pst_payloads(namespace, target_store):
    """Iterate email payloads from an initialized PST store."""
    try:
        root_folder = target_store.GetRootFolder()

        for folder in _iter_folders(root_folder):
            for item in _iter_mail_items(folder):
                subject = (getattr(item, "Subject", "") or "").strip()
                body = (getattr(item, "Body", "") or "").strip()
                # Apply the same trimming and cleaning logic as EML import
                body = _trim_first_message(body)
                body = _clean_body(body)
                sender_name = (getattr(item, "SenderName", "") or "").strip()
                received_at = _to_iso(getattr(item, "ReceivedTime", None))
                sender_email = _get_sender_email(item)

                yield {
                    "subject": subject,
                    "body": body,
                    "sender_name": sender_name,
                    "sender_email": sender_email,
                    "received_at": received_at,
                }
    finally:
        try:
            if namespace is not None and target_store is not None:
                namespace.RemoveStore(target_store)
        except Exception:
            pass


def import_maintenance_from_pst(
    pst_path,
    *,
    conn=None,
    db_path=DEFAULT_DB_PATH,
    max_failures_to_report=20,
    progress_callback=None,
):
    if not pst_path or not os.path.exists(pst_path):
        raise FileNotFoundError("Το αρχείο .pst δεν βρέθηκε.")
    if not pst_path.lower().endswith(".pst"):
        raise ValueError("Παρακαλώ επιλέξτε αρχείο .pst.")

    close_conn = False
    if conn is None:
        conn = init_db(db_path)
        conn.row_factory = sqlite3.Row
        close_conn = True

    summary = {
        "scanned": 0,
        "imported": 0,
        "failed": 0,
        "skipped": 0,
        "failures": [],
    }

    namespace = None
    target_store = None
    try:
        # Initialize PST store synchronously (not in a generator) so progress callbacks happen immediately
        namespace, target_store = _init_pst_store(pst_path, progress_callback)

        # Now iterate the payloads
        for payload in _iter_pst_payloads(namespace, target_store):
            summary["scanned"] += 1

            # Call progress callback if provided
            if progress_callback:
                try:
                    progress_callback(
                        current=summary["scanned"],
                        imported=summary["imported"],
                        failed=summary["failed"],
                    )
                except Exception:
                    pass  # Ignore callback errors

            subject = payload.get("subject", "")
            body = payload.get("body", "")
            if not subject and not body:
                summary["skipped"] += 1
                continue

            try:
                success, result = create_maintenance_from_email(
                    subject=subject,
                    body=body,
                    sender_email=payload.get("sender_email", ""),
                    sender_name=payload.get("sender_name", ""),
                    received_at=payload.get("received_at", ""),
                    conn=conn,
                )
            except Exception as exc:
                summary["failed"] += 1
                if len(summary["failures"]) < max_failures_to_report:
                    summary["failures"].append(
                        f"{subject or '(χωρίς θέμα)'}: {str(exc)}"
                    )
                continue

            if success:
                summary["imported"] += 1
            else:
                summary["failed"] += 1
                if len(summary["failures"]) < max_failures_to_report:
                    summary["failures"].append(
                        f"{subject or '(χωρίς θέμα)'}: {result}"
                    )

        return summary
    finally:
        if close_conn:
            conn.close()
