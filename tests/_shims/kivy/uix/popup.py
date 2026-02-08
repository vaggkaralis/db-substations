from .widget import Widget


class Popup(Widget):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.title = k.get("title", None)
        self.size_hint = k.get("size_hint", None)
        self.content = None

    def open(self):
        return None

    def dismiss(self):
        return None
