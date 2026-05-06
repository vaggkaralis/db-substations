from DBrun import SubstationApp


def test_compose_maintenance_name_appends_clean_title_suffix():
    app = SubstationApp()

    name = app._compose_maintenance_name(
        "ΚΑΣΣΑΝΔΡΕΙΑ",
        "2026-05-06 08:00",
        "  Έλεγχος κυψέλης ΜΣ1  ",
    )

    assert name == "Υ/Σ ΚΑΣΣΑΝΔΡΕΙΑ - 06/05/2026 | Έλεγχος κυψέλης ΜΣ1"


def test_extract_maintenance_title_text_reads_existing_suffix_before_workflow():
    app = SubstationApp()

    title_text = app._extract_maintenance_title_text(
        "ΚΑΣΣΑΝΔΡΕΙΑ",
        "2026-05-06 08:00",
        stored_name="Υ/Σ ΚΑΣΣΑΝΔΡΕΙΑ - 06/05/2026 | Έλεγχος κυψέλης ΜΣ1",
        workflow_state={"daily_progress": "παλιό κείμενο"},
    )

    assert title_text == "Έλεγχος κυψέλης ΜΣ1"


def test_extract_maintenance_title_text_falls_back_to_workflow_for_old_records():
    app = SubstationApp()

    title_text = app._extract_maintenance_title_text(
        "ΚΑΣΣΑΝΔΡΕΙΑ",
        "2026-05-06 08:00",
        stored_name="Υ/Σ ΚΑΣΣΑΝΔΡΕΙΑ - 06/05/2026",
        workflow_state={"daily_progress": "Εκκρεμεί επανέλεγχος"},
    )

    assert title_text == "Εκκρεμεί επανέλεγχος"
