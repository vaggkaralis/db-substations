from elements import _capture_substation_popup_state, _restore_substation_popup_state


class _DummyPopup:
    pass


class _DummyApp:
    def __init__(self, scroll_lookup=None):
        self.scroll_lookup = scroll_lookup or {}
        self.calls = []

    def _get_popup_scroll_y(self, popup):
        return self.scroll_lookup.get(id(popup))

    def _display_substations(
        self,
        filter_name=None,
        reuse_popup=None,
        element_type_filter=None,
        gate_filter=None,
        prev_scroll_y=None,
    ):
        self.calls.append(
            {
                "filter_name": filter_name,
                "reuse_popup": reuse_popup,
                "element_type_filter": element_type_filter,
                "gate_filter": gate_filter,
                "prev_scroll_y": prev_scroll_y,
            }
        )


def test_capture_substation_popup_state_walks_origin_chain():
    root_popup = _DummyPopup()
    root_popup._dbs_filter_name = "ΚΥΜΗ"
    root_popup._dbs_element_type_filter = "Μετασχηματιστής"
    root_popup._dbs_gate_filter = "ΠΥΛΗ 1"

    child_popup = _DummyPopup()
    child_popup._dbs_origin_popup = root_popup

    app = _DummyApp({id(root_popup): 0.37})

    state = _capture_substation_popup_state(
        app, child_popup, fallback_filter_name="ΕΦΕΔΡΙΚΟ"
    )

    assert state == {
        "filter_name": "ΚΥΜΗ",
        "element_type_filter": "Μετασχηματιστής",
        "gate_filter": "ΠΥΛΗ 1",
        "prev_scroll_y": 0.37,
    }


def test_capture_substation_popup_state_uses_fallback_when_state_missing():
    app = _DummyApp()

    state = _capture_substation_popup_state(
        app, _DummyPopup(), fallback_filter_name="ΚΥΜΗ"
    )

    assert state == {
        "filter_name": "ΚΥΜΗ",
        "element_type_filter": None,
        "gate_filter": None,
        "prev_scroll_y": None,
    }


def test_restore_substation_popup_state_replays_saved_filters():
    app = _DummyApp()
    popup = _DummyPopup()
    state = {
        "filter_name": "ΚΥΜΗ",
        "element_type_filter": "Μετασχηματιστής",
        "gate_filter": "ΠΥΛΗ 1",
        "prev_scroll_y": 0.61,
    }

    _restore_substation_popup_state(app, state, reuse_popup=popup)

    assert app.calls == [
        {
            "filter_name": "ΚΥΜΗ",
            "reuse_popup": popup,
            "element_type_filter": "Μετασχηματιστής",
            "gate_filter": "ΠΥΛΗ 1",
            "prev_scroll_y": 0.61,
        }
    ]
