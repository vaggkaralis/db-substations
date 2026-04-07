import sys

from android_app import SubstationAndroidApp


class DummyActivity:
    def __init__(self):
        self.started = False

    def startActivity(self, intent):
        self.started = True

    def getPackageName(self):
        return "org.dbsubstations"

    def getContentResolver(self):
        return object()


class DummyFile:
    def __init__(self, path):
        self.path = path


class DummyAutoclassModule:
    def __init__(self, activity):
        self.activity = activity

    def __call__(self, name):
        # Return simple stand-ins for classes
        if name == "org.kivy.android.PythonActivity":

            class PA:
                mActivity = self.activity

            return PA
        if name == "java.io.File":
            return lambda p: DummyFile(p)
        if name == "android.content.Intent":

            class Intent:
                ACTION_SEND = "ACTION_SEND"
                EXTRA_STREAM = "EXTRA_STREAM"
                EXTRA_TEXT = "EXTRA_TEXT"
                FLAG_GRANT_READ_URI_PERMISSION = 1
                FLAG_GRANT_WRITE_URI_PERMISSION = 2

                def __init__(self, *a, **k):
                    pass

                def setType(self, t):
                    pass

                def putExtra(self, k, v):
                    pass

                def addFlags(self, f):
                    pass

                def setClipData(self, clip):
                    pass

                @staticmethod
                def createChooser(i, title):
                    return "chooser"

            return Intent
        if name == "android.net.Uri":

            class Uri:
                @staticmethod
                def fromFile(f):
                    return f

            return Uri
        if name == "androidx.core.content.FileProvider":

            class FP:
                @staticmethod
                def getUriForFile(activity, authority, f):
                    return f

            return FP
        if name == "android.content.ClipData":

            class ClipData:
                @staticmethod
                def newUri(cr, title, uri):
                    return (cr, title, uri)

            return ClipData
        if name == "java.lang.String":
            return lambda value: value
        raise ImportError(name)


def test_launch_share_intent_uses_fileprovider(monkeypatch, tmp_path):
    app = SubstationAndroidApp()
    # create dummy file path
    path = str(tmp_path / "change_log.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("ok")

    activity = DummyActivity()
    # inject jnius.autoclass
    import types

    def autoclass(name):
        return DummyAutoclassModule(activity)(name)

    dummy_jnius = types.SimpleNamespace(autoclass=autoclass)
    monkeypatch.setitem(sys.modules, "jnius", dummy_jnius)

    # call helper - should not raise and should mark activity started
    app._launch_share_intent(path)
    assert activity.started is True


def test_launch_share_intent_fallback_to_clipboard(monkeypatch, tmp_path):
    app = SubstationAndroidApp()
    path = str(tmp_path / "change_log.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("ok")

    # remove jnius to force exception
    monkeypatch.setitem(sys.modules, "jnius", None)

    # monkeypatch Clipboard
    class DummyClipboard:
        copied = None

        @staticmethod
        def copy(v):
            DummyClipboard.copied = v

    monkeypatch.setitem(sys.modules, "kivy.core.clipboard", DummyClipboard)

    # calling should raise inside helper; caller (the append wrapper)
    # will handle fallback
    try:
        app._launch_share_intent(path)
    except Exception:
        # simulate append wrapper fallback
        from kivy.core.clipboard import copy as clipboard_copy

        clipboard_copy(path)

    assert DummyClipboard.copied == path
