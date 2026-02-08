from .widget import Widget


class ScrollView(Widget):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.bar_width = k.get("bar_width", None)

    def add_widget(self, widget, index=None):
        # ScrollView typically has a single child; we mimic add_widget by
        # attaching the widget as a child
        super().add_widget(widget, index=index)
