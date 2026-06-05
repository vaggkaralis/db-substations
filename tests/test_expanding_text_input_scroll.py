from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivy.uix.textinput import TextInput

from DBrun import SubstationApp


def _build_scroll_context(*, scroll_y, widget_y, cursor_y):
    scroll = ScrollView()
    scroll.height = 200
    scroll.scroll_y = scroll_y

    content = Widget()
    content.height = 1000
    scroll.add_widget(content)

    container = Widget()
    container.y = 0
    container.height = content.height
    content.add_widget(container)

    text_input = TextInput(text="line1\nline2\nline3", multiline=True, height=320)
    text_input.y = widget_y
    text_input.cursor_pos = (0, cursor_y)
    text_input.focus = True
    container.add_widget(text_input)

    return scroll, text_input


def test_expanding_text_input_scroll_moves_down_when_caret_reaches_view_bottom():
    app = SubstationApp()
    scroll, text_input = _build_scroll_context(
        scroll_y=0.5,
        widget_y=350,
        cursor_y=280,
    )

    desired_scroll_y = app._get_parent_scroll_y_for_text_input_cursor(
        scroll,
        text_input,
        padding=24,
    )

    assert desired_scroll_y is not None
    assert desired_scroll_y > 0.5


def test_expanding_text_input_scroll_moves_up_when_caret_reaches_view_top():
    app = SubstationApp()
    scroll, text_input = _build_scroll_context(
        scroll_y=0.6,
        widget_y=420,
        cursor_y=40,
    )

    desired_scroll_y = app._get_parent_scroll_y_for_text_input_cursor(
        scroll,
        text_input,
        padding=24,
    )

    assert desired_scroll_y is not None
    assert desired_scroll_y < 0.6


def test_expanding_text_input_scroll_stays_put_when_caret_is_visible():
    app = SubstationApp()
    scroll, text_input = _build_scroll_context(
        scroll_y=0.5,
        widget_y=350,
        cursor_y=150,
    )

    desired_scroll_y = app._get_parent_scroll_y_for_text_input_cursor(
        scroll,
        text_input,
        padding=24,
    )

    assert desired_scroll_y is None
