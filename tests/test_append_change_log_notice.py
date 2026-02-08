from android_app import SubstationAndroidApp


def test_append_change_log_adds_notice(monkeypatch, tmp_path):
    app = SubstationAndroidApp()
    app.user_data_dir = str(tmp_path)
    app.change_log_path = None
    # provide a simple content_layout container
    from tests._shims.kivy.uix.boxlayout import BoxLayout

    content = BoxLayout()
    app.content_layout = content

    app._append_change_log("insert", "tbl", {"x": 1})
    # The notice was added to content_layout children (index 0 or appended)
    assert len(app.content_layout.children) >= 1
    notice = app.content_layout.children[0]
    # notice should have at least one child that's a Button with copy text
    btn_texts = []
    for child in getattr(notice, "children", []):
        if hasattr(child, "text"):
            btn_texts.append(child.text)
    assert any("Αντιγραφή" in t for t in btn_texts)
