from android_app import SubstationAndroidApp


def test_root_buttons_visible_and_hidden(monkeypatch):
    app = SubstationAndroidApp()
    # Build UI to create root buttons
    root = app.build()
    assert hasattr(app, "refresh_btn")
    assert hasattr(app, "add_substation_btn")
    # Buttons should be enabled/visible
    assert app.refresh_btn.disabled is False
    assert app.refresh_btn.opacity == 1
    assert app.add_substation_btn.disabled is False
    assert app.add_substation_btn.opacity == 1

    # Prepare a dummy substation and call show_substation_details
    app.substations = [{"id": 99, "name": "T1", "location": ""}]
    # Call the view - should hide the root buttons
    app.show_substation_details(99)
    assert app.refresh_btn.disabled is True
    assert app.refresh_btn.opacity == 0
    assert app.add_substation_btn.disabled is True
    assert app.add_substation_btn.opacity == 0

    # Calling load_substations should restore the buttons
    app.load_substations(None)
    assert app.refresh_btn.disabled is False
    assert app.refresh_btn.opacity == 1
    assert app.add_substation_btn.disabled is False
    assert app.add_substation_btn.opacity == 1
