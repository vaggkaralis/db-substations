"""
Import maintenance emails from .eml files in a folder.
"""
import argparse
import os

from email_eml_parser import parse_eml_file
from maintenance_email_importer import DEFAULT_DB_PATH, create_maintenance_from_email


def _iter_eml_files(folder, recursive):
    if recursive:
        for root, _, files in os.walk(folder):
            for name in files:
                if name.lower().endswith(".eml"):
                    yield os.path.join(root, name)
    else:
        for name in os.listdir(folder):
            if name.lower().endswith(".eml"):
                yield os.path.join(folder, name)


def main():
    parser = argparse.ArgumentParser(description="Import maintenance emails from .eml files.")
    parser.add_argument("--folder", required=True, help="Folder with .eml files")
    parser.add_argument("--database", default=DEFAULT_DB_PATH, help="Path to SQLite database")
    parser.add_argument("--recursive", action="store_true", help="Scan subfolders recursively")
    parser.add_argument(
        "--processed-folder",
        default=None,
        help="Folder to move successfully imported .eml files",
    )
    parser.add_argument(
        "--failed-folder",
        default=None,
        help="Folder to move failed .eml files",
    )
    args = parser.parse_args()

    processed = 0
    failed = 0

    processed_folder = args.processed_folder
    failed_folder = args.failed_folder

    if processed_folder:
        os.makedirs(processed_folder, exist_ok=True)
    if failed_folder:
        os.makedirs(failed_folder, exist_ok=True)

    for path in _iter_eml_files(args.folder, args.recursive):
        try:
            payload = parse_eml_file(path)
            success, result = create_maintenance_from_email(
                subject=payload["subject"],
                body=payload["body"],
                sender_email=payload["sender_email"],
                sender_name=payload["sender_name"],
                received_at=payload["received_at"],
                db_path=args.database,
            )

            if success:
                processed += 1
                if processed_folder:
                    target = os.path.join(processed_folder, os.path.basename(path))
                    os.replace(path, target)
            else:
                failed += 1
                if failed_folder:
                    target = os.path.join(failed_folder, os.path.basename(path))
                    os.replace(path, target)
        except Exception:
            failed += 1
            if failed_folder:
                target = os.path.join(failed_folder, os.path.basename(path))
                os.replace(path, target)

    print(f"Imported: {processed}, Failed: {failed}")


if __name__ == "__main__":
    main()
