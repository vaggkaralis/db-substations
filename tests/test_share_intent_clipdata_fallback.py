import sys

from android_app import SubstationAndroidApp


class DummyActivity:
    def __init__(self):
        self.started = False

    def startActivity(self, intent):
        self.started = True

    def getPackageName(self):
        return "org.dbsubstations"


class DummyFile:
    def __init__(self, path):
        self.path = path


class CliplessAutoclassModule:
    def __init__(self, activity):
        self.activity = activity

    def __call__(self, name):
        # provide required classes but raise for ClipData to simulate older API
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
                FLAG_GRANT_READ_URI_PERMISSION = 1

                def __init__(self, *a, **k):
                    pass

                def setType(self, t):
                    pass

                def putExtra(self, k, v):
                    pass

                def addFlags(self, f):
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
        # Simulate ClipData not available by raising
        if name == "android.content.ClipData":
            raise ImportError(name)
        if name == "androidx.core.content.FileProvider":

            class FP:
                @staticmethod
                def getUriForFile(activity, authority, f):
                    return f

            return FP
        raise ImportError(name)


def test_share_uses_fallback_when_clipdata_missing(monkeypatch, tmp_path):
    app = SubstationAndroidApp()
    path = str(tmp_path / "change_log.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("ok")

    activity = DummyActivity()
    import types

    def autoclass(name):
        return CliplessAutoclassModule(activity)(name)

    dummy_jnius = types.SimpleNamespace(autoclass=autoclass)
    monkeypatch.setitem(sys.modules, "jnius", dummy_jnius)

    # should not raise and should mark activity started
    app._launch_share_intent(path)
    assert activity.started is True
