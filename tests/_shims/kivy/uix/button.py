from .widget import Widget


class Button(Widget):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.text = k.get("text", "")
        self.size_hint_x = k.get("size_hint_x", None)
        self.size_hint_y = k.get("size_hint_y", None)
        self.opacity = 1
        self.disabled = False

    def bind(self, **kwargs):
        # allow binding on_press etc. store callbacks if needed
        for k, v in kwargs.items():
            setattr(self, k, v)
