import ui.shared as shared


class DummyIcon:
    def __init__(self, **kwargs):
        self.icon_type = kwargs.get("icon_type")
        self.icon_color = kwargs.get("icon_color")
        self.parent = None
        self.size = (0, 0)
        self.size_hint_x = None
        self.size_hint_y = None


class FakeCanvas:
    def ask_update(self):
        return None


class FakeLabel:
    def __init__(self, text="", size_hint=None, markup=False):
        self.text = text
        self.size_hint = size_hint
        self.markup = markup
        self.texture_size = (max(40, len(text) * 8), 18)
        self.size = self.texture_size
        self.pos = (0, 0)
        self.parent = None
        self.canvas = FakeCanvas()

    def texture_update(self):
        return None


class FakeWindow:
    def __init__(self):
        self.size = (800, 600)
        self.bound = {}
        self.children = []

    def bind(self, **kwargs):
        self.bound.update(kwargs)
        return None

    def add_widget(self, widget):
        widget.parent = self
        self.children.append(widget)

    def remove_widget(self, widget):
        if widget in self.children:
            self.children.remove(widget)
            widget.parent = None


def _make_button(monkeypatch, fake_window=None):
    fake_window = fake_window or FakeWindow()
    monkeypatch.setattr(shared, "Window", fake_window)
    monkeypatch.setattr(shared, "IconWidget", DummyIcon)
    monkeypatch.setattr(shared, "Label", FakeLabel)

    button = shared.IconOnlyButton(icon_type="subelements", tooltip="Υποστοιχεία")
    button.width = 40
    button.height = 40
    button.disabled = False
    button.get_root_window = lambda: fake_window
    button.to_widget = lambda x, y: (x, y)
    button.collide_point = lambda x, y: True
    return button, fake_window


def test_icon_only_button_hides_tooltip_when_detached(monkeypatch):
    shared.IconOnlyButton._active_tooltip_owner = None
    button, fake_window = _make_button(monkeypatch)

    button._on_mouse_pos(fake_window, (100, 120))

    assert button._tooltip_widget is not None
    assert len(fake_window.children) == 1

    button.get_root_window = lambda: None
    button._on_mouse_pos(fake_window, (100, 120))

    assert button._tooltip_widget is None
    assert fake_window.children == []
    assert shared.IconOnlyButton._active_tooltip_owner is None


def test_icon_only_button_replaces_previous_active_tooltip(monkeypatch):
    shared.IconOnlyButton._active_tooltip_owner = None
    fake_window = FakeWindow()
    first_button, _ = _make_button(monkeypatch, fake_window=fake_window)
    second_button, _ = _make_button(monkeypatch, fake_window=fake_window)

    first_button._on_mouse_pos(fake_window, (100, 120))
    second_button._on_mouse_pos(fake_window, (160, 140))

    assert first_button._tooltip_widget is None
    assert second_button._tooltip_widget is not None
    assert len(fake_window.children) == 1
    assert shared.IconOnlyButton._active_tooltip_owner is second_button
