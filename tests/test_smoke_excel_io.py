import importlib


def test_import_excel_io_and_has_exports():
    mod = importlib.import_module("excel_io")
    # Check presence of a couple of stable functions
    assert hasattr(mod, "export_full_db")
    assert hasattr(mod, "import_people")
