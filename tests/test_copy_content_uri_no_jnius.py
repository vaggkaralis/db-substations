import pytest

from android_app import SubstationAndroidApp


def test_copy_content_uri_raises_when_no_jnius():
    app = SubstationAndroidApp()
    with pytest.raises(RuntimeError):
        app._copy_content_uri_to_file("content://some/path")
