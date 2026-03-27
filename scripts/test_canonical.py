import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def main():
    from validation import canonical_role

    samples = [
        "Μηχανικός",
        "Τομεάρχης ΤΕΙ",
        "Υποτομεάρχης\u00a0TEI",
        "Ειδικό Στέλεχος Γ\u02bc",
        "Ειδικό Στέλεχος Γ\u2019",
        "Ειδικό Στελεχος G'",
    ]
    for sample in samples:
        print(repr(sample), "->", repr(canonical_role(sample)))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
