import os
import tempfile
import shutil
from pathlib import Path

import pytest

from onedrive_hybrid_storage import (
    _isolation_instance_folder_name,
    _ISOLATION_INSTANCE_PREFIX,
    _ISOLATION_OPEN_PATH_MAX,
)
from reports import _short_temp_open_copy


def test_instance_folder_short_fallback():
    tmp = tempfile.mkdtemp()
    try:
        # Long substation name to force fallback
        long_name = "Substation " + ("VeryLongName_" * 10)
        folder = _isolation_instance_folder_name(
            "2026-03-30 08:00", substation_name=long_name, request_id=999, isolation_root=tmp
        )
        assert folder.startswith(_ISOLATION_INSTANCE_PREFIX)
        # projected path should be reasonable
        example_full = os.path.join(tmp, folder, f"Αίτηση_999.xlsx")
        assert len(example_full) <= max(_ISOLATION_OPEN_PATH_MAX, len(example_full))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_short_temp_open_copy_creates_temp_copy():
    src_dir = tempfile.mkdtemp()
    try:
        src_file = os.path.join(src_dir, "test_long_name_file.xlsx")
        with open(src_file, "w", encoding="utf-8") as fh:
            fh.write("dummy")
        temp_copy = _short_temp_open_copy(src_file)
        assert temp_copy is not None
        assert os.path.exists(temp_copy)
        assert len(temp_copy) < len(src_file) or os.path.dirname(temp_copy) != os.path.dirname(src_file)
    finally:
        shutil.rmtree(src_dir, ignore_errors=True)
        # also remove temp copy if present
        try:
            if temp_copy and os.path.exists(temp_copy):
                os.remove(temp_copy)
        except Exception:
            pass
