from .widget import Widget


class BoxLayout(Widget):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.orientation = k.get("orientation", "vertical")
        self.padding = k.get("padding", 0)
        self.spacing = k.get("spacing", 0)
