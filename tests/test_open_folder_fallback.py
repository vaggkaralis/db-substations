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

    monkeypatch.setattr(os, "startfile", lambda path: opened.append(path))

    assert open_folder_or_url(str(missing_media_dir)) is True
    assert opened == [str(instance_dir)]
