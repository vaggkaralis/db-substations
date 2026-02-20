import importlib


def test_import_elements_module_and_delegate_exists():
    mod = importlib.import_module("elements")
    # Ensure at least one safe delegate exists (doesn't require an app instance)
    assert hasattr(mod, "show_add_element_popup_delegate")
