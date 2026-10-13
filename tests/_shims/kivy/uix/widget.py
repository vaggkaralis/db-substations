class _CanvasGroup:
    def __init__(self):
        self._items = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def clear(self):
        self._items.clear()

    def add(self, item):
        self._items.append(item)

    def __iter__(self):
        return iter(self._items)


class Widget:
    def __init__(self, *a, **k):
        self.children = []
        self.parent = None
        self.width = 0
        self.height = 0
        self.size_hint = (1, 1)
        self.size_hint_y = None
        self.opacity = 1
        self.disabled = False
        self.canvas = _CanvasGroup()
        self.canvas.before = _CanvasGroup()
        self.canvas.after = _CanvasGroup()

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
