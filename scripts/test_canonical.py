import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from validation import canonical_role

samples = [
    "Μηχανικός",
    "Τομεάρχης ΤΕΙ",
    "Υποτομεάρχης\u00a0TEI",
    "Ειδικό Στέλεχος Γ\u02bc",
    "Ειδικό Στέλεχος Γ\u2019",
    "Ειδικό Στελεχος G'",
]
for s in samples:
    print(repr(s), "->", repr(canonical_role(s)))
