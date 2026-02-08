import sys
from types import SimpleNamespace

import android_app


def test_maintenance_comments_in_fixed_container(monkeypatch):
    # Capture the popup instance created by show_maintenance_menu
    captured = {}

    class DummyPopup:
        def __init__(self, title=None, size_hint=None):
            self.title = title
            self.size_hint = size_hint
            self.content = None
            captured['instance'] = self

        def open(self):
            # no-op
            pass
        def dismiss(self):
            # no-op
            pass

    import android_app
    monkeypatch.setattr(android_app, 'Popup', DummyPopup)

    app = android_app.SubstationAndroidApp()
    # call with a fake substation dict
    app.show_maintenance_menu(1, {'name': 'S1'})

    popup = captured.get('instance')
    assert popup is not None
    # The popup content should be a layout; ensure it has a child TextInput with the overall comments hint
    found = False
    try:
        for child in getattr(popup.content, 'children', []):
            # children may include the scroll and the comments container
            # inspect grandchildren for TextInput with hint_text
            for grand in getattr(child, 'children', []):
                if getattr(grand, 'hint_text', None) == 'Γενικά σχόλια για την συντήρηση...':
                    found = True
    except Exception:
        found = False

    assert found, "Overall comments TextInput not found in fixed container"
