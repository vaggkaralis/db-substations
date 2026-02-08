import os
import json

from android_app import SubstationAndroidApp


def test_append_change_log_writes_file(tmp_path, monkeypatch):
    app = SubstationAndroidApp()
    # point app.user_data_dir to tmp
    app.user_data_dir = str(tmp_path)
    app.change_log_path = None
    # ensure directory
    assert os.path.exists(app.user_data_dir)
    # call append
    app._append_change_log("insert", "test_table", {"a": 1})
    # file should exist
    path = app.change_log_path
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().strip().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["operation"] == "insert"
    assert data["table"] == "test_table"
    assert data["data"]["a"] == 1
