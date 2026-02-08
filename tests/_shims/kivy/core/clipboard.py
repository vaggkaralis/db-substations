class Clipboard:
    @staticmethod
    def copy(value):
        global _clipboard
        _clipboard = value

    @staticmethod
    def paste():
        try:
            return _clipboard
        except NameError:
            return ""
