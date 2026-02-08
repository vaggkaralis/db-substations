import tempfile
import os
from android_app import SubstationAndroidApp


def test_ensure_change_log_path_creates_file(tmp_path):
    app = SubstationAndroidApp()
    app.user_data_dir = str(tmp_path)
    # ensure change_log_path None initially
    app.change_log_path = None
    app._ensure_change_log_path()
    assert app.change_log_path is not None
    assert os.path.exists(app.change_log_path)
