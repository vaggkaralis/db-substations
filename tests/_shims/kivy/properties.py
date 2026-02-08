class StringProperty:
    def __init__(self, default=None):
        self.default = default


class NumericProperty:
    def __init__(self, default=0):
        self.default = default


class BooleanProperty:
    def __init__(self, default=False):
        self.default = default


class ListProperty:
    def __init__(self, default=None):
        self.default = default or []


class ObjectProperty:
    def __init__(self, default=None):
        self.default = default
