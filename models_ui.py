"""
Delegating wrappers for models UI in `DBrun.py`.
"""


def show_models_management_delegate(app, instance=None):
    return app.show_models_management(instance)
