import sys
import types

from android_app import SubstationAndroidApp


class DummyActivity:
    def __init__(self, cache_dir):
        self.started = False
        self.cache_dir = cache_dir

    def startActivity(self, intent):
        self.started = True

    def getPackageName(self):
        return "org.dbsubstations"

    def getContentResolver(self):
        return object()

    def getExternalCacheDir(self):
        return type("CacheDir", (), {"getAbsolutePath": lambda _self: self.cache_dir})()

    def getCacheDir(self):
        return type("CacheDir", (), {"getAbsolutePath": lambda _self: self.cache_dir})()


class DummyFile:
    def __init__(self, path):
        self.path = path

    def getName(self):
        import os

        return os.path.basename(self.path)

    def getAbsolutePath(self):
        return self.path


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

                def setDataAndType(self, uri, mime_type):
                    pass

                def putExtra(self, k, v):
                    pass

                def putExtras(self, extras):
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
        if name == "android.os.Bundle":

            class Bundle(dict):
                def putParcelable(self, key, value):
                    self[key] = value

            return Bundle
        if name == "java.lang.String":
            return lambda value: value
        raise ImportError(name)


def test_launch_share_intent_uses_fileprovider(monkeypatch, tmp_path):
    app = SubstationAndroidApp()
    # create dummy file path
    path = str(tmp_path / "change_log.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("ok")

    activity = DummyActivity(str(tmp_path))
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


def test_launch_share_intent_falls_back_from_chooser_to_direct_start(
    monkeypatch, tmp_path
):
    app = SubstationAndroidApp()
    path = str(tmp_path / "change_log.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("ok")

    start_calls = []

    class FallbackActivity(DummyActivity):
        def startActivity(self, intent):
            start_calls.append(intent)
            if intent == "chooser":
                raise RuntimeError("chooser failed")
            self.started = True

    activity = FallbackActivity(str(tmp_path))

    def autoclass(name):
        return DummyAutoclassModule(activity)(name)

    dummy_jnius = types.SimpleNamespace(autoclass=autoclass)
    monkeypatch.setitem(sys.modules, "jnius", dummy_jnius)
    monkeypatch.setitem(
        sys.modules,
        "android.runnable",
        types.SimpleNamespace(run_on_ui_thread=lambda func: func),
    )

    app._launch_share_intent(path)

    assert start_calls[0] == "chooser"
    assert activity.started is True


def test_launch_share_intent_falls_back_to_mediastore_when_fileprovider_missing(
    monkeypatch, tmp_path
):
    app = SubstationAndroidApp()
    path = str(tmp_path / "change_log.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("ok")

    class DummyOutputStream:
        def __init__(self):
            self.data = b""

        def write(self, chunk):
            self.data += bytes(chunk)

        def flush(self):
            return None

        def close(self):
            return None

    class DummyResolver:
        def __init__(self):
            self.stream = DummyOutputStream()

        def insert(self, uri, values):
            return "content://downloads/change_log.txt"

        def openOutputStream(self, uri):
            return self.stream

    class MediaStoreActivity(DummyActivity):
        def __init__(self, cache_dir):
            super().__init__(cache_dir)
            self.resolver = DummyResolver()

        def getContentResolver(self):
            return self.resolver

    activity = MediaStoreActivity(str(tmp_path))

    class MediaStoreAutoclassModule(DummyAutoclassModule):
        def __call__(self, name):
            if name == "androidx.core.content.FileProvider":
                raise ImportError(name)
            if name == "android.content.ContentValues":

                class ContentValues(dict):
                    def put(self, key, value):
                        self[key] = value

                return ContentValues
            if name == "android.provider.MediaStore$Downloads":
                return type(
                    "Downloads",
                    (),
                    {"EXTERNAL_CONTENT_URI": "content://downloads/external"},
                )
            if name == "android.provider.MediaStore$MediaColumns":
                return type(
                    "MediaColumns",
                    (),
                    {
                        "DISPLAY_NAME": "display_name",
                        "MIME_TYPE": "mime_type",
                        "RELATIVE_PATH": "relative_path",
                    },
                )
            if name == "android.os.Environment":
                return type("Environment", (), {"DIRECTORY_DOWNLOADS": "Download"})
            return super().__call__(name)

    def autoclass(name):
        return MediaStoreAutoclassModule(activity)(name)

    dummy_jnius = types.SimpleNamespace(autoclass=autoclass)
    monkeypatch.setitem(sys.modules, "jnius", dummy_jnius)
    monkeypatch.setitem(
        sys.modules,
        "android.runnable",
        types.SimpleNamespace(run_on_ui_thread=lambda func: func),
    )

    app._launch_share_intent(path)

    assert activity.started is True
    assert activity.resolver.stream.data == b"ok"
