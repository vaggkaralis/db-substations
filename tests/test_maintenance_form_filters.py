from DBrun import (
    build_maintenance_element_status_filter,
    filter_maintenance_elements_for_form,
    is_oil_maintenance_element,
    oil_weight_kg_to_liters,
    should_show_maintenance_element,
    summarize_oil_requirement,
)


def test_maintenance_element_status_filter_hides_inactive_for_new_records():
    status_filter, params = build_maintenance_element_status_filter(
        substation_id=23,
        maintenance_id=None,
        existing_elements_data=None,
    )

    assert (
        status_filter
        == "(e.substation_id=23 AND (e.operating_status IS NULL OR e.operating_status='Ενεργή'))"
    )
    assert params == []


def test_maintenance_element_status_filter_keeps_linked_inactive_on_edit():
    status_filter, params = build_maintenance_element_status_filter(
        substation_id=23,
        maintenance_id=15,
        existing_elements_data={
            8: {"element_comments": ""},
            3: {"element_comments": ""},
        },
    )

    assert (
        status_filter
        == "((e.substation_id=23 AND (e.operating_status IS NULL OR e.operating_status='Ενεργή')) OR e.id IN (?,?))"
    )
    assert params == [3, 8]


def test_maintenance_element_status_filter_keeps_cross_substation_linked_elements_on_edit():
    status_filter, params = build_maintenance_element_status_filter(
        substation_id=23,
        maintenance_id=1066,
        existing_elements_data={504: {"element_comments": "legacy"}},
    )

    assert "e.substation_id=23" in status_filter
    assert "e.id IN (?)" in status_filter
    assert params == [504]


def test_should_show_maintenance_element_hides_unselected_inactive_by_default():
    assert not should_show_maintenance_element("Ανενεργή")
    assert should_show_maintenance_element("Ενεργή")


def test_should_show_maintenance_element_keeps_selected_inactive_visible():
    assert should_show_maintenance_element(
        "Ανενεργή",
        show_inactive=False,
        is_selected=True,
    )


def test_filter_maintenance_elements_for_form_counts_hidden_inactive_rows():
    elements = [
        (
            1,
            "type",
            "active",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            "Ενεργή",
        ),
        (
            2,
            "type",
            "inactive",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            "Ανενεργή",
        ),
        (
            3,
            "type",
            "selected inactive",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            "Ανενεργή",
        ),
    ]

    visible_elements, hidden_inactive_count = filter_maintenance_elements_for_form(
        elements,
        selected_element_ids={3},
        show_inactive=False,
    )

    assert [row[0] for row in visible_elements] == [1, 3]
    assert hidden_inactive_count == 1


def test_is_oil_maintenance_element_accepts_transformers_and_oil_breakers():
    assert is_oil_maintenance_element("Μετασχηματιστής 150/20KV", None)
    assert is_oil_maintenance_element("Διακόπτης ΜΤ", "Πτωχού Ελαίου")
    assert is_oil_maintenance_element("Διακόπτης ΥΤ", "Ελαίου")
    assert not is_oil_maintenance_element("Διακόπτης ΜΤ", "SF6")


def test_oil_weight_kg_to_liters_uses_default_density():
    liters = oil_weight_kg_to_liters(178.0)

    assert liters == 200.0


def test_summarize_oil_requirement_adds_tolerance_and_rounds_barrels_up():
    summary = summarize_oil_requirement(360.0)

    assert summary["base_liters"] == 360.0
    assert summary["adjusted_liters"] == 396.0
    assert round(summary["exact_barrels"], 2) == 1.98
    assert summary["rounded_barrels"] == 2
