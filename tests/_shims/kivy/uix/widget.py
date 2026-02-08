class Widget:
    def __init__(self, *a, **k):
        self.children = []
        self.parent = None
        self.width = 0
        self.height = 0
        self.size_hint = (1, 1)
        self.size_hint_y = None

    def add_widget(self, widget, index=None):
        widget.parent = self
        if index is None:
            self.children.append(widget)
        else:
            self.children.insert(index, widget)

    def remove_widget(self, widget):
        if widget in self.children:
            self.children.remove(widget)
            widget.parent = None

    def bind(self, **kwargs):
        # minimal no-op bind for tests
        return None

    def setter(self, attr):
        def _set(instance, value):
            setattr(instance, attr, value)

        return _set

    def clear_widgets(self):
        for c in list(self.children):
            self.remove_widget(c)
