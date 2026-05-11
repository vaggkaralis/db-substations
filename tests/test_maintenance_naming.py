from DBrun import SubstationApp


def test_compose_maintenance_name_returns_custom_full_title():
    app = SubstationApp()

    name = app._compose_maintenance_name(
        "ΚΑΣΣΑΝΔΡΕΙΑ",
        "2026-05-06 08:00",
        "  Έλεγχος κυψέλης ΜΣ1  ",
    )

    assert name == "Έλεγχος κυψέλης ΜΣ1"


def test_compose_maintenance_name_keeps_generated_title_without_duplication():
    app = SubstationApp()

    name = app._compose_maintenance_name(
        "ΚΑΣΣΑΝΔΡΕΙΑ",
        "2026-05-06 08:00",
        "Υ/Σ ΚΑΣΣΑΝΔΡΕΙΑ - 06/05/2026",
    )

    assert name == "Υ/Σ ΚΑΣΣΑΝΔΡΕΙΑ - 06/05/2026"


def test_extract_maintenance_title_text_returns_existing_full_title():
    app = SubstationApp()

    title_text = app._extract_maintenance_title_text(
        "ΚΑΣΣΑΝΔΡΕΙΑ",
        "2026-05-06 08:00",
        stored_name="Υ/Σ ΚΑΣΣΑΝΔΡΕΙΑ - 06/05/2026 | Έλεγχος κυψέλης ΜΣ1",
        workflow_state={"daily_progress": "παλιό κείμενο"},
    )

    assert title_text == "Υ/Σ ΚΑΣΣΑΝΔΡΕΙΑ - 06/05/2026 | Έλεγχος κυψέλης ΜΣ1"


def test_extract_maintenance_title_text_keeps_generated_title_for_old_records():
    app = SubstationApp()

    title_text = app._extract_maintenance_title_text(
        "ΚΑΣΣΑΝΔΡΕΙΑ",
        "2026-05-06 08:00",
        stored_name="Υ/Σ ΚΑΣΣΑΝΔΡΕΙΑ - 06/05/2026",
        workflow_state={"daily_progress": "Εκκρεμεί επανέλεγχος"},
    )

    assert title_text == "Υ/Σ ΚΑΣΣΑΝΔΡΕΙΑ - 06/05/2026"


def test_extract_maintenance_title_text_falls_back_to_generated_title_when_empty():
    app = SubstationApp()

    title_text = app._extract_maintenance_title_text(
        "ΚΑΣΣΑΝΔΡΕΙΑ",
        "2026-05-06 08:00",
        stored_name="",
        workflow_state={},
    )

    assert title_text == "Υ/Σ ΚΑΣΣΑΝΔΡΕΙΑ - 06/05/2026"


def test_format_maintenance_display_name_prefixes_unique_id():
    app = SubstationApp()

    display_name = app._format_maintenance_display_name(
        123,
        "ΚΑΣΣΑΝΔΡΕΙΑ",
        "2026-05-06 08:00",
        "Έλεγχος κυψέλης ΜΣ1",
    )

    assert display_name == "ID 123 | Έλεγχος κυψέλης ΜΣ1"
