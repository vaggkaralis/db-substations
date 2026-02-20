import importlib


def test_import_model_management_and_has_api():
    mod = importlib.import_module("model_management")
    assert hasattr(mod, "show_models_management")
