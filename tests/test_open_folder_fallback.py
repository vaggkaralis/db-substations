import os

from reports import _nearest_existing_folder, open_folder_or_url


def test_nearest_existing_folder_falls_back_to_parent(tmp_path):
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    missing_media_dir = instance_dir / "Φωτογραφίες_Video"

    resolved = _nearest_existing_folder(str(missing_media_dir))

    assert resolved == str(instance_dir)


def test_open_folder_or_url_opens_parent_when_target_folder_missing(
    tmp_path, monkeypatch
):
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    missing_media_dir = instance_dir / "Φωτογραφίες_Video"
    opened = []

    # CI can run on non-Windows platforms where `os.startfile` is absent.
    # Monkeypatch both `os.startfile` (allow creating attribute) and
    # `webbrowser.open` so the test captures whichever backend is used.
    import subprocess
    import webbrowser

    monkeypatch.setattr(
        os, "startfile", lambda path: opened.append(path), raising=False
    )
    monkeypatch.setattr(webbrowser, "open", lambda path: opened.append(path))
    monkeypatch.setattr(
        subprocess,
        "call",
        lambda args: opened.append(
            args[1] if isinstance(args, (list, tuple)) and len(args) > 1 else args
        ),
        raising=False,
    )

    assert open_folder_or_url(str(missing_media_dir)) is True
    assert opened == [str(instance_dir)]
