from DBrun import build_maintenance_element_status_filter


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
