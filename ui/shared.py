from kivy.core.window import Window
from kivy.uix.widget import Widget
from kivy.properties import StringProperty, ListProperty
from kivy.graphics import Color, Line, Ellipse, Rectangle
from kivy.uix.textinput import TextInput
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label


Window  # ensure Window is imported for callers that expect it


class IconWidget(Widget):
    """Simple vector pictogram drawn on canvas."""

    icon_type = StringProperty("database")
    icon_color = ListProperty([1, 1, 1, 1])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(
            pos=self._redraw,
            size=self._redraw,
            icon_type=self._redraw,
            icon_color=self._redraw,
        )

    def _redraw(self, *_args):
        self.canvas.clear()
        with self.canvas:
            Color(*self.icon_color)
            x, y = self.x, self.y
            w, h = self.width, self.height
            if w <= 0 or h <= 0:
                return
            pad = min(w, h) * 0.12

            line_w = max(1.05, min(w, h) * 0.042)

            if self.icon_type == "database":
                Line(
                    ellipse=(x + pad, y + h * 0.58, w - 2 * pad, h * 0.35), width=line_w
                )
                Line(rectangle=(x + pad, y + pad, w - 2 * pad, h * 0.58), width=line_w)
                Line(
                    ellipse=(x + pad, y + pad - h * 0.12, w - 2 * pad, h * 0.24),
                    width=line_w,
                )
                Line(
                    points=[x + pad, y + h * 0.58, x + w - pad, y + h * 0.58],
                    width=line_w,
                )
            elif self.icon_type == "import":
                Line(
                    rectangle=(x + pad, y + pad, w - 2 * pad, h - 2 * pad), width=line_w
                )
                Line(
                    points=[x + w * 0.5, y + h * 0.75, x + w * 0.5, y + h * 0.35],
                    width=line_w,
                )
                Line(
                    points=[
                        x + w * 0.38,
                        y + h * 0.48,
                        x + w * 0.5,
                        y + h * 0.35,
                        x + w * 0.62,
                        y + h * 0.48,
                    ],
                    width=line_w,
                )
            elif self.icon_type == "models":
                Line(
                    rectangle=(x + pad * 1.2, y + pad * 1.2, w - 2.4 * pad, h * 0.28),
                    width=line_w,
                )
                Line(
                    rectangle=(x + pad, y + h * 0.38, w - 2 * pad, h * 0.28),
                    width=line_w,
                )
                Line(
                    rectangle=(x + pad * 1.2, y + h * 0.6, w - 2.4 * pad, h * 0.28),
                    width=line_w,
                )
            elif self.icon_type == "people":
                Line(circle=(x + w * 0.5, y + h * 0.7, w * 0.18), width=line_w)
                Line(
                    rectangle=(x + w * 0.26, y + pad, w * 0.48, h * 0.35), width=line_w
                )
            elif self.icon_type == "maintenance":
                Line(circle=(x + w * 0.35, y + h * 0.6, w * 0.15), width=line_w)
                Line(
                    points=[x + w * 0.5, y + h * 0.3, x + w * 0.82, y + h * 0.62],
                    width=line_w,
                )
                Line(
                    points=[
                        x + w * 0.68,
                        y + h * 0.5,
                        x + w * 0.82,
                        y + h * 0.62,
                        x + w * 0.66,
                        y + h * 0.66,
                    ],
                    width=line_w,
                )
            elif self.icon_type == "inspection":
                Line(circle=(x + w * 0.4, y + h * 0.55, w * 0.2), width=line_w)
                Line(
                    points=[x + w * 0.56, y + h * 0.38, x + w * 0.82, y + h * 0.12],
                    width=line_w,
                )
            elif self.icon_type == "sf6":
                # Gas cylinder pictogram
                body_x = x + w * 0.28
                body_w = w * 0.44
                body_y = y + h * 0.2
                body_h = h * 0.6
                Line(rectangle=(body_x, body_y, body_w, body_h), width=line_w)
                Line(
                    ellipse=(body_x, body_y + body_h - h * 0.12, body_w, h * 0.2),
                    width=line_w,
                )
                Line(
                    ellipse=(body_x, body_y - h * 0.08, body_w, h * 0.16), width=line_w
                )
                # Valve
                Line(circle=(x + w * 0.5, y + h * 0.86, w * 0.06), width=line_w)
                Line(
                    points=[x + w * 0.5, y + h * 0.8, x + w * 0.5, y + h * 0.74],
                    width=line_w,
                )
            elif self.icon_type == "isolation":
                Line(
                    rectangle=(x + w * 0.26, y + pad, w * 0.48, h * 0.45), width=line_w
                )
                Line(
                    points=[
                        x + w * 0.32,
                        y + h * 0.48,
                        x + w * 0.32,
                        y + h * 0.7,
                        x + w * 0.68,
                        y + h * 0.7,
                        x + w * 0.68,
                        y + h * 0.48,
                    ],
                    width=line_w,
                )
            elif self.icon_type == "info":
                Line(circle=(x + w * 0.5, y + h * 0.5, w * 0.3), width=line_w)
                Line(
                    points=[x + w * 0.5, y + h * 0.38, x + w * 0.5, y + h * 0.62],
                    width=line_w,
                )
                Ellipse(pos=(x + w * 0.46, y + h * 0.68), size=(w * 0.08, h * 0.08))


class ShiftSelectableTextInput(TextInput):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._shift_select_anchor = None

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            if not self.focus:
                self.focus = True
            if "shift" in Window.modifiers:
                if self._shift_select_anchor is None:
                    self._shift_select_anchor = self.cursor_index()
                self.cursor = self.get_cursor_from_xy(*touch.pos)
                self.select_text(self._shift_select_anchor, self.cursor_index())
                return True

        result = super().on_touch_down(touch)
        if self.collide_point(*touch.pos) and "shift" not in Window.modifiers:
            self._shift_select_anchor = self.cursor_index()
        return result


class IconButton(ButtonBehavior, BoxLayout):
    """Button with a simple pictogram and text."""

    text = StringProperty("")
    icon_type = StringProperty("database")
    bg_color = ListProperty([0.05, 0.18, 0.36, 1])
    bg_color_down = ListProperty([0.03, 0.12, 0.25, 1])
    text_color = ListProperty([1, 1, 1, 1])

    def __init__(self, **kwargs):
        theme = kwargs.pop("theme", None)
        super().__init__(**kwargs)
        if theme:
            self.bg_color = list(theme.get("primary", self.bg_color))
            self.bg_color_down = list(theme.get("primary_dark", self.bg_color_down))
            self.text_color = list(theme.get("text_on_primary", self.text_color))

        self.orientation = "horizontal"
        self.spacing = 10
        self.padding = (12, 8)

        self.icon = IconWidget(
            icon_type=self.icon_type, icon_color=self.text_color, size_hint=(None, None)
        )
        self.icon.size = (23, 23)
        self.icon.pos_hint = {"center_y": 0.5}
        self.label = Label(
            text=self.text, color=self.text_color, halign="left", valign="middle"
        )
        self.label.font_size = "26sp"
        self.label.bind(size=self._sync_text_size)

        self.add_widget(self.icon)
        self.add_widget(self.label)

        with self.canvas.before:
            self._bg_color_inst = Color(*self.bg_color)
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)

        self.bind(pos=self._update_bg, size=self._update_bg)
        self.bind(pos=self._update_icon_pos, size=self._update_icon_pos)
        self.bind(size=self._update_icon_size)
        self.bind(text=self._update_text)
        self.bind(icon_type=self._update_icon)
        self.bind(text_color=self._update_colors)

    def _sync_text_size(self, _instance, _value):
        self.label.text_size = (self.label.width, self.label.height)

    def _update_icon_size(self, *_args):
        icon_dim = max(22, int(self.height * 0.6))
        icon_dim = int(icon_dim * 0.64)
        self.icon.size = (icon_dim, icon_dim)

    def _update_icon_pos(self, *_args):
        self.icon.center_y = self.center_y

    def _update_bg(self, *_args):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size

    def _update_text(self, *_args):
        self.label.text = self.text

    def _update_icon(self, *_args):
        self.icon.icon_type = self.icon_type

    def _update_colors(self, *_args):
        self.label.color = self.text_color
        self.icon.icon_color = self.text_color

    def on_press(self):
        self._bg_color_inst.rgba = self.bg_color_down

    def on_release(self):
        self._bg_color_inst.rgba = self.bg_color
