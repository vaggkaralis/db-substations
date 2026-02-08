import sys
import os

# Ensure project root is on sys.path when running from tests/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from android_app import SubstationAndroidApp


class DummyLayout:
    def __init__(self):
        self.widgets = []

    def clear_widgets(self):
        self.widgets.clear()
        print("DummyLayout: clear_widgets")

    def add_widget(self, w):
        self.widgets.append(w)
        print("DummyLayout: add_widget", type(w).__name__)


def main():
    app = SubstationAndroidApp()
    app.content_layout = DummyLayout()

    # Replace show_error to avoid Kivy popups during headless test
    app.show_error = lambda msg: print("show_error called:", msg)

    # Simulate closed root (None) to reproduce the previous issue
    app.root = None

    # Provide a truthy local_db_path so load_substations proceeds
    app.local_db_path = "dummy_db_path"

    # Monkeypatch _local_fetch_substations to avoid actual DB access
    app._local_fetch_substations = lambda: [
        {"id": 1, "name": "Test Substation", "location": ""}
    ]

    # Call the method under test
    app.load_substations(None)

    print("Final widgets in content_layout:", [type(w).__name__ for w in app.content_layout.widgets])


if __name__ == "__main__":
    main()
