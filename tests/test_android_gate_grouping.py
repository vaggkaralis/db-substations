import android_app


def _collect_texts(widget):
    texts = []
    if hasattr(widget, "text"):
        texts.append(widget.text)
    for child in getattr(widget, "children", []):
        texts.extend(_collect_texts(child))
    return texts


def test_group_elements_by_gate_uses_desktop_order():
    app = android_app.SubstationAndroidApp()

    grouped = app._group_elements_by_gate(
        [
            {"id": 1, "gate": "ΠΥΛΗ 2-3"},
            {"id": 2, "gate": "ΠΥΛΗ 2"},
            {"id": 3, "gate": "ΠΥΛΗ 1-2"},
            {"id": 4, "gate": "ΠΥΛΗ 3"},
            {"id": 5, "gate": "ΠΥΛΗ 1"},
            {"id": 6, "gate": "ΠΥΛΗ 1-3"},
            {"id": 7, "gate": ""},
        ]
    )

    assert [name for name, _ in grouped] == [
        "ΠΥΛΗ 1-3",
        "ΠΥΛΗ 1",
        "ΠΥΛΗ 1-2",
        "ΠΥΛΗ 2",
        "ΠΥΛΗ 2-3",
        "ΠΥΛΗ 3",
        "(Μη καταχωρημένο)",
    ]


def test_group_elements_by_gate_sorts_gate_members_like_desktop():
    app = android_app.SubstationAndroidApp()
    hv_breaker = android_app.S.get("MESSAGES", {}).get(
        "ELEMENT_BREAKER_YT", "Διακόπτης ΥΤ"
    )
    mv_breaker = android_app.S.get("MESSAGES", {}).get(
        "ELEMENT_BREAKER_MT", "Διακόπτης ΜΤ"
    )

    grouped = app._group_elements_by_gate(
        [
            {
                "id": 1,
                "gate": "ΠΥΛΗ 1",
                "element_type": mv_breaker,
                "name": "Line Breaker",
                "is_main_switch": 0,
            },
            {
                "id": 2,
                "gate": "ΠΥΛΗ 1",
                "element_type": hv_breaker,
                "name": "HV Central Breaker",
            },
            {
                "id": 3,
                "gate": "ΠΥΛΗ 1",
                "element_type": "Μετασχηματιστής 150/20KV",
                "name": "Transformer",
            },
            {
                "id": 4,
                "gate": "ΠΥΛΗ 1",
                "element_type": mv_breaker,
                "name": "MV Central Breaker",
                "is_main_switch": 1,
            },
            {
                "id": 5,
                "gate": "ΠΥΛΗ 1",
                "element_type": mv_breaker,
                "name": "Capacitor Breaker",
                "is_main_switch": 3,
            },
            {
                "id": 6,
                "gate": "ΠΥΛΗ 1",
                "element_type": "Motor Drive",
                "name": "Drive",
            },
            {
                "id": 7,
                "gate": "ΠΥΛΗ 1",
                "element_type": mv_breaker,
                "name": "Interconnection Breaker",
                "is_main_switch": 2,
            },
            {
                "id": 8,
                "gate": "ΠΥΛΗ 1",
                "element_type": "Other Device",
                "name": "Other",
            },
        ]
    )

    gate_name, gate_elements = grouped[0]

    assert gate_name == "ΠΥΛΗ 1"
    assert [elem["name"] for elem in gate_elements] == [
        "HV Central Breaker",
        "Transformer",
        "Drive",
        "MV Central Breaker",
        "Interconnection Breaker",
        "Line Breaker",
        "Capacitor Breaker",
        "Other",
    ]


def test_load_substation_elements_renders_gate_headers(monkeypatch):
    app = android_app.SubstationAndroidApp()
    grid = android_app.GridLayout(cols=1)

    monkeypatch.setattr(
        app,
        "_local_fetch_elements",
        lambda _sid: [
            {
                "id": 1,
                "element_type": "Διακόπτης ΜΤ",
                "name": "Q1",
                "serial_number": "SN1",
                "manufacture_year": "2020",
                "voltage_level": "20KV",
                "operating_status": "Ενεργή",
                "gate": "ΠΥΛΗ 2",
                "breaker_category": "SF6",
                "model_name": "M1",
                "model_manufacturer": "Maker",
                "manufacturer": "Maker",
                "manual_pdf": "",
                "onedrive_manual_link": "",
            },
            {
                "id": 2,
                "element_type": "Διακόπτης ΜΤ",
                "name": "Q2",
                "serial_number": "SN2",
                "manufacture_year": "2021",
                "voltage_level": "20KV",
                "operating_status": "Ενεργή",
                "gate": "ΠΥΛΗ 1",
                "breaker_category": "SF6",
                "model_name": "M2",
                "model_manufacturer": "Maker",
                "manufacturer": "Maker",
                "manual_pdf": "",
                "onedrive_manual_link": "",
            },
        ],
    )
    monkeypatch.setattr(app, "_has_element_maintenance_history", lambda _eid: False)

    app._load_substation_elements(1, grid)

    texts = _collect_texts(grid)
    assert any("ΠΥΛΗ 1 (1 στοιχεία)" in text for text in texts)
    assert any("ΠΥΛΗ 2 (1 στοιχεία)" in text for text in texts)


def test_build_gate_tag_widget_uses_compact_gate_text():
    app = android_app.SubstationAndroidApp()

    widget = app._build_gate_tag_widget("ΠΥΛΗ 1-3", height=160)

    texts = _collect_texts(widget)
    assert "Π1-3" in texts
    assert "ΠΥΛΗ 1-3" not in texts
