from kivy.core.window import Window
from kivy.uix.widget import Widget
from kivy.properties import StringProperty, ListProperty
from kivy.graphics import Color, Line, Ellipse, Rectangle
from kivy.uix.textinput import TextInput
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.image import Image

# FloatLayout is optional in test environments where Kivy isn't installed.
try:
    from kivy.uix.floatlayout import FloatLayout
except Exception:
    class FloatLayout:
        """Minimal stub for environments without kivy.uix.floatlayout.

        Provides the small API surface used by tooltip overlay code.
        """

        def __init__(self, *a, **k):
            pass

        def add_widget(self, widget):
            return None

        def remove_widget(self, widget):
            return None


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
            elif self.icon_type == "edit":
                # clearer pencil / edit icon: body, tip, and eraser
                body_w = w * 0.6
                body_h = h * 0.18
                body_x = x + w * 0.18
                body_y = y + h * 0.36
                # pencil body (slanted)
                Line(points=[body_x, body_y, body_x + body_w, body_y + body_h * 2], width=max(1.0, line_w))
                # tip (triangle)
                tip_pts = [body_x + body_w, body_y + body_h * 2, body_x + body_w + w * 0.12, body_y + body_h * 2 - h * 0.08, body_x + body_w, body_y + body_h * 2 - h * 0.06]
                Line(points=tip_pts, width=max(1.0, line_w))
                # outline for tip
                Line(points=[body_x + body_w + w * 0.12, body_y + body_h * 2 - h * 0.08, body_x + body_w, body_y + body_h * 2 - h * 0.06], width=max(0.8, line_w * 0.8))
                # eraser at the back
                eraser_w = w * 0.14
                eraser_h = body_h
                Rectangle(pos=(body_x - eraser_w * 0.9, body_y - eraser_h * 0.2), size=(eraser_w, eraser_h))
                # divide line between eraser and body
                Line(points=[body_x - eraser_w * 0.9 + 2, body_y - eraser_h * 0.2 + 2, body_x - eraser_w * 0.9 + 2, body_y - eraser_h * 0.2 + eraser_h - 2], width=max(0.8, line_w * 0.8))
            elif self.icon_type == "delete":
                # clearer trash can icon: lid, can body, and slats
                lid_h = h * 0.12
                lid_x = x + w * 0.22
                lid_w = w * 0.56
                lid_y = y + h * 0.72
                # lid
                Line(rectangle=(lid_x, lid_y, lid_w, lid_h), width=max(1.0, line_w))
                # handle
                Line(points=[lid_x + lid_w * 0.4, lid_y + lid_h + h * 0.02, lid_x + lid_w * 0.6, lid_y + lid_h + h * 0.02], width=max(1.0, line_w))
                # can body
                body_x = x + w * 0.26
                body_y = y + h * 0.18
                body_w = w * 0.48
                body_h = h * 0.52
                Line(rectangle=(body_x, body_y, body_w, body_h), width=max(1.0, line_w))
                # vertical slats inside can
                for i in range(1, 4):
                    sx = body_x + (body_w * i / 5.0)
                    Line(points=[sx, body_y + body_h * 0.12, sx, body_y + body_h - body_h * 0.06], width=max(0.8, line_w * 0.6))
            elif self.icon_type == "eye":
                # simple eye icon: outer eye shape and pupil
                cx = x + w * 0.5
                cy = y + h * 0.5
                rx = w * 0.42
                ry = h * 0.28
                # outer eye arc (approximated with ellipse and lines)
                Line(ellipse=(cx - rx, cy - ry, rx * 2, ry * 2), width=max(1.0, line_w))
                # cover top and bottom to suggest almond shape
                Line(points=[cx - rx, cy, cx, cy + ry * 0.9, cx + rx, cy], width=max(1.0, line_w))
                Line(points=[cx - rx, cy, cx, cy - ry * 0.9, cx + rx, cy], width=max(1.0, line_w))
                # pupil
                Ellipse(pos=(cx - rx * 0.25, cy - ry * 0.25), size=(rx * 0.5, ry * 0.5))


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
    source = StringProperty(None)
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

        # Use an Image if `source` is provided, otherwise draw vector icon
        if self.source:
            self.icon = Image(source=self.source, size_hint=(None, None))
            self.icon.allow_stretch = True
            self.icon.keep_ratio = True
            self.icon.size = (35, 35)
        else:
            self.icon = IconWidget(
                icon_type=self.icon_type, icon_color=self.text_color, size_hint=(None, None)
            )
            self.icon.size = (23, 23)
        self.icon.pos_hint = {"center_y": 0.5}
        self.label = Label(
            text=self.text, color=self.text_color, halign="center", valign="middle"
        )
        # reduce base font size by ~20%
        self.label.font_size = "21sp"
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
        self.bind(source=self._on_source)
        self.bind(text_color=self._update_colors)

    def _sync_text_size(self, _instance, _value):
        self.label.text_size = (self.label.width, self.label.height)

    def _update_icon_size(self, *_args):
        # increase icon size by ~50% compared to previous sizing heuristic
        icon_dim = max(33, int(self.height * 0.6))
        icon_dim = int(icon_dim * 0.96)
        self.icon.size = (icon_dim, icon_dim)

    def _update_icon_pos(self, *_args):
        self.icon.center_y = self.center_y

    def _update_bg(self, *_args):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size

    def _update_text(self, *_args):
        self.label.text = self.text

    def _update_icon(self, *_args):
        # only update vector icon type if we are using IconWidget
        if isinstance(self.icon, IconWidget):
            self.icon.icon_type = self.icon_type

    def _on_source(self, _instance, new_source):
        # Swap between Image and IconWidget depending on `source`.
        try:
            was_index = list(self.children).index(self.label)  # label is present; icon is before it
        except Exception:
            was_index = 0
        # remove existing icon
        if self.icon:
            try:
                self.remove_widget(self.icon)
            except Exception:
                pass
        if new_source:
            self.icon = Image(source=new_source, size_hint=(None, None))
            self.icon.allow_stretch = True
            self.icon.keep_ratio = True
            self.icon.size = (23, 23)
        else:
            self.icon = IconWidget(
                icon_type=self.icon_type, icon_color=self.text_color, size_hint=(None, None)
            )
            self.icon.size = (23, 23)
        # add icon back before the label
        self.add_widget(self.icon, index=was_index)

    def _update_colors(self, *_args):
        self.label.color = self.text_color
        self.icon.icon_color = self.text_color

    def on_press(self):
        self._bg_color_inst.rgba = self.bg_color_down

    def on_release(self):
        self._bg_color_inst.rgba = self.bg_color


class IconOnlyButton(ButtonBehavior, BoxLayout):
    """Compact icon-only button using vector IconWidget or an image source."""

    icon_type = StringProperty("database")
    source = StringProperty(None)
    icon_color = ListProperty([0.2, 0.6, 1, 1])
    tooltip = StringProperty("")

    def __init__(self, **kwargs):
        # allow caller to pass size via kwargs
        size = kwargs.pop("size", (40, 40))
        # allow explicit tooltip override
        tooltip_text = kwargs.pop("tooltip", None)
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        self.size = size
        self.orientation = "horizontal"
        self.padding = (2, 2)

        if self.source:
            self.icon = Image(source=self.source, size_hint=(None, None))
            self.icon.allow_stretch = True
            self.icon.keep_ratio = True
        else:
            self.icon = IconWidget(icon_type=self.icon_type, icon_color=self.icon_color, size_hint=(None, None))

        # initial icon sizing
        dim = max(24, int(self.height * 0.85))
        self.icon.size = (dim, dim)
        self.icon.pos_hint = {"center_y": 0.5}
        self.add_widget(self.icon)

        self.bind(size=self._update_icon_size)
        self.bind(icon_type=self._update_icon_type)
        self.bind(source=self._on_source)
        self.bind(icon_color=self._update_icon_color)
        # tooltip support: default Greek labels for common icons
        default_tooltips = {
            "edit": "Ξ•Ο€ΞµΞΎΞµΟΞ³Ξ±ΟƒΞ―Ξ±",
            "delete": "Ξ”ΞΉΞ±Ξ³ΟΞ±Ο†Ξ®",
            "eye": "Ξ ΟΞΏΞ²ΞΏΞ»Ξ® Ξ£Ο„ΞΏΞΉΟ‡ΞµΞ―ΞΏΟ…",
            "maintenance": "Ξ™ΟƒΟ„ΞΏΟΞΉΞΊΟ Ξ£Ο…Ξ½Ο„Ξ®ΟΞ·ΟƒΞ·Ο‚",
            "inspection": "Ξ™ΟƒΟ„ΞΏΟΞΉΞΊΟ Ξ•Ο€ΞΉΞΈΞµΟΟΞ·ΟƒΞ·Ο‚",
        }
        if tooltip_text:
            self.tooltip = tooltip_text
        else:
            self.tooltip = default_tooltips.get(self.icon_type, "")

        self._tooltip_widget = None
        Window.bind(mouse_pos=self._on_mouse_pos)

    def _update_icon_size(self, *_args):
        dim = max(24, int(self.height * 0.85))
        self.icon.size = (dim, dim)

    def _update_icon_type(self, *_args):
        if isinstance(self.icon, IconWidget):
            self.icon.icon_type = self.icon_type

    def _on_source(self, _inst, new_source):
        try:
            self.remove_widget(self.icon)
        except Exception:
            pass
        if new_source:
            self.icon = Image(source=new_source, size_hint=(None, None))
            self.icon.allow_stretch = True
            self.icon.keep_ratio = True
        else:
            self.icon = IconWidget(icon_type=self.icon_type, icon_color=self.icon_color, size_hint=(None, None))
        self._update_icon_size()
        self.add_widget(self.icon)

    def _update_icon_color(self, *_args):
        if isinstance(self.icon, IconWidget):
            self.icon.icon_color = self.icon_color

    def _on_mouse_pos(self, _window, pos):
        # show tooltip near mouse when hovering over this widget
        try:
            if not self.get_root_window():
                return
        except Exception:
            return

        # convert window coords to local widget coords for collide test
        try:
            local = self.to_widget(*pos)
        except Exception:
            local = pos

        inside = self.collide_point(*local)
        if inside and self.tooltip:
            # If no tooltip widget yet, create and add it
            if not self._tooltip_widget:
                lbl = Label(text=self.tooltip, size_hint=(None, None), markup=False)
                # force texture update to get size
                try:
                    lbl.texture_update()
                except Exception:
                    pass
                w = lbl.texture_size[0] + 12 if hasattr(lbl, "texture_size") else 100
                h = lbl.texture_size[1] + 8 if hasattr(lbl, "texture_size") else 24
                lbl.size = (w, h)
                # position at top-right of cursor, with fallback below if space insufficient
                x = pos[0] + 12
                y = pos[1] + 12
                # clamp to window
                win_w, win_h = Window.size
                if x + w > win_w:
                    x = win_w - w - 6
                if y + h > win_h:
                    # not enough space above: place below cursor
                    y = pos[1] - h - 12
                if y < 6:
                    y = 6
                lbl.pos = (x, y)
                lbl.canvas.ask_update()
                # Prefer adding tooltip to an app-level overlay if available
                added = False
                try:
                    from kivy.app import App

                    app = App.get_running_app()
                    root = app.root if app else None
                    overlay = None
                    if root:
                        overlay = getattr(root, "_tooltip_overlay", None)
                        if overlay is None:
                            try:
                                overlay = FloatLayout(size_hint=(1, 1))
                                overlay.disabled = True
                                root.add_widget(overlay)
                                setattr(root, "_tooltip_overlay", overlay)
                            except Exception:
                                overlay = None
                    if overlay:
                        overlay.add_widget(lbl)
                        added = True
                except Exception:
                    added = False

                if not added:
                    try:
                        Window.add_widget(lbl)
                        added = True
                    except Exception:
                        return

                self._tooltip_widget = lbl
            else:
                # update position: prefer top-right of cursor, fallback below if necessary
                lbl = self._tooltip_widget
                w, h = lbl.size
                x = pos[0] + 12
                y = pos[1] + 12
                win_w, win_h = Window.size
                if x + w > win_w:
                    x = win_w - w - 6
                if y + h > win_h:
                    y = pos[1] - h - 12
                if y < 6:
                    y = 6
                lbl.pos = (x, y)
        else:
            # hide/remove existing tooltip if present
            if self._tooltip_widget:
                try:
                    # remove from whichever parent we added it to
                    parent = getattr(self._tooltip_widget, "parent", None)
                    if parent is not None:
                        try:
                            parent.remove_widget(self._tooltip_widget)
                        except Exception:
                            pass
                    else:
                        try:
                            Window.remove_widget(self._tooltip_widget)
                        except Exception:
                            pass
                except Exception:
                    pass
                self._tooltip_widget = None

