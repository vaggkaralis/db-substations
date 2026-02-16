"""
Import a single maintenance email from a .eml file into SQLite.
"""

import argparse

import logging

from email_eml_parser import parse_eml_file
from maintenance_email_importer import DEFAULT_DB_PATH, create_maintenance_from_email

logging.basicConfig(level=logging.INFO, format="%(message)s")


def main():
    parser = argparse.ArgumentParser(
        description="Import a maintenance email from a .eml file."
    )
    parser.add_argument("--file", required=True, help="Path to .eml file")
    parser.add_argument(
        "--database", default=DEFAULT_DB_PATH, help="Path to SQLite database"
    )
    args = parser.parse_args()

    payload = parse_eml_file(args.file)
    success, result = create_maintenance_from_email(
        subject=payload["subject"],
        body=payload["body"],
        sender_email=payload["sender_email"],
        sender_name=payload["sender_name"],
        received_at=payload["received_at"],
        db_path=args.database,
    )

    if success:
        logging.info("OK:%s", result)
        raise SystemExit(0)

    logging.error("ERROR:%s", result)
    raise SystemExit(2)


if __name__ == "__main__":
    main()
