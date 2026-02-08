from .widget import Widget


class TextInput(Widget):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.text = k.get("text", "")
        self.hint_text = k.get("hint_text", None)
        self.multiline = k.get("multiline", True)
        self.padding = k.get("padding", [0, 0, 0, 0])
        self.height = k.get("height", 0)

    def bind(self, **kwargs):
        return None
