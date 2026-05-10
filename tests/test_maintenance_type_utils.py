from maintenance_type_utils import is_recurring_maintenance_type
from strings import STRINGS_EL, STRINGS_EN


def test_receipt_is_treated_as_recurring_maintenance_type():
    assert is_recurring_maintenance_type("Παραλαβή")
    assert is_recurring_maintenance_type("Receipt")


def test_maintenance_type_lists_include_receipt_first():
    assert STRINGS_EL["MESSAGES"]["MAINTENANCE_TYPES"][:3] == [
        "Παραλαβή",
        "Επαναληπτική συντήρηση",
        "Βλάβη",
    ]
    assert STRINGS_EN["MESSAGES"]["MAINTENANCE_TYPES"][:3] == [
        "Receipt",
        "Recurring maintenance",
        "Fault",
    ]
