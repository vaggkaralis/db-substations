from .widget import Widget


class GridLayout(Widget):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.cols = k.get("cols", 1)
        self.spacing = k.get("spacing", 0)
        self.padding = k.get("padding", 0)
