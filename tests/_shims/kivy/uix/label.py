from .widget import Widget


class Label(Widget):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.text = k.get("text", "")
        self.size_hint_y = k.get("size_hint_y", None)
        self.bold = k.get("bold", False)
        self.halign = k.get("halign", "left")
        self.valign = k.get("valign", "middle")
        self.font_size = k.get("font_size", None)

    def bind(self, **kwargs):
        return None
