import pytest

from android_app import SubstationAndroidApp


def test_launch_share_intent_requires_path():
    app = SubstationAndroidApp()
    with pytest.raises(RuntimeError):
        app._launch_share_intent("")
