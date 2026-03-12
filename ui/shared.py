import math

from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.properties import ListProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

from strings_proxy import STRINGS as S

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
            elif self.icon_type == "settings":
                cx = x + w * 0.5
                cy = y + h * 0.5
                radius = min(w, h) * 0.28
                Line(circle=(cx, cy, radius), width=line_w)
                tooth_len = min(w, h) * 0.12
                for angle in range(0, 360, 60):
                    rad = math.radians(angle)
                    x1 = cx + math.cos(rad) * (radius + tooth_len * 0.2)
                    y1 = cy + math.sin(rad) * (radius + tooth_len * 0.2)
                    x2 = cx + math.cos(rad) * (radius + tooth_len)
                    y2 = cy + math.sin(rad) * (radius + tooth_len)
                    Line(points=[x1, y1, x2, y2], width=line_w)
                Line(circle=(cx, cy, radius * 0.4), width=line_w)
            elif self.icon_type == "edit":
                # Pencil icon rotated 220 degrees counterclockwise: pointing bottom-left
                cx = x + w * 0.5  # Center of icon
                cy = y + h * 0.5
                angle = math.radians(220)  # 220 degrees counterclockwise
                cos_a = math.cos(angle)
                sin_a = math.sin(angle)
                
                def rotate_point(px, py):
                    """Rotate point around center by angle"""
                    px_rel = px - cx
                    py_rel = py - cy
                    new_x = cx + px_rel * cos_a - py_rel * sin_a
                    new_y = cy + px_rel * sin_a + py_rel * cos_a
                    return new_x, new_y
                
                # Original pencil points (before rotation)
                shaft_x = x + w * 0.15
                shaft_y = y + h * 0.25
                shaft_w = w * 0.55
                shaft_h = h * 0.15
                
                # Pencil shaft corners
                p1 = rotate_point(shaft_x, shaft_y)
                p2 = rotate_point(shaft_x + shaft_w, shaft_y)
                p3 = rotate_point(shaft_x + shaft_w, shaft_y + shaft_h)
                p4 = rotate_point(shaft_x, shaft_y + shaft_h)
                
                # Draw rotated shaft
                Line(points=[p1[0], p1[1], p2[0], p2[1], p3[0], p3[1], p4[0], p4[1], p1[0], p1[1]], width=max(1.2, line_w))
                
                # Pencil tip points
                tip_px = shaft_x + shaft_w
                tip_py = shaft_y + shaft_h * 0.5
                tip_left = rotate_point(tip_px, tip_py)
                tip_right = rotate_point(tip_px + h * 0.12, tip_py)
                tip_top = rotate_point(tip_px, tip_py - h * 0.08)
                
                # Draw rotated tip
                Line(points=[tip_left[0], tip_left[1], tip_right[0], tip_right[1], tip_top[0], tip_top[1], tip_left[0], tip_left[1]], width=max(1.2, line_w))
                
                # Eraser at the back
                eraser_x = shaft_x - w * 0.08
                eraser_y = shaft_y
                eraser_w = w * 0.08
                eraser_h = shaft_h
                
                # Eraser corners
                e1 = rotate_point(eraser_x, eraser_y)
                e2 = rotate_point(eraser_x + eraser_w, eraser_y)
                e3 = rotate_point(eraser_x + eraser_w, eraser_y + eraser_h)
                e4 = rotate_point(eraser_x, eraser_y + eraser_h)
                
                # Draw rotated eraser
                Line(points=[e1[0], e1[1], e2[0], e2[1], e3[0], e3[1], e4[0], e4[1], e1[0], e1[1]], width=max(1.0, line_w))
                
                # Metal band between eraser and pencil
                Line(points=[e2[0], e2[1], e3[0], e3[1]], width=max(1.0, line_w * 1.5))
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
            elif self.icon_type == "book":
                # book/manual icon: spine and pages
                book_x = x + w * 0.2
                book_y = y + h * 0.15
                book_w = w * 0.6
                book_h = h * 0.7
                # book outline
                Line(rectangle=(book_x, book_y, book_w, book_h), width=max(1.2, line_w))
                # spine
                Line(points=[book_x + book_w * 0.15, book_y, book_x + book_w * 0.15, book_y + book_h], width=max(1.2, line_w))
                # pages (horizontal lines)
                for i in range(1, 4):
                    py = book_y + (book_h * i / 4.5)
                    Line(points=[book_x + book_w * 0.25, py, book_x + book_w * 0.85, py], width=max(0.8, line_w * 0.7))


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
            if hasattr(self.icon, "fit_mode"):
                self.icon.fit_mode = "contain"
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
            if hasattr(self.icon, "fit_mode"):
                self.icon.fit_mode = "contain"
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


class StatusButton(ButtonBehavior, BoxLayout):
    """Text-only status button with explicit canvas background."""

    text = StringProperty("")
    bg_color = ListProperty([0.11, 0.56, 0.27, 1])
    bg_color_down = ListProperty([0.08, 0.44, 0.21, 1])
    text_color = ListProperty([1, 1, 1, 1])
    font_size = StringProperty("12sp")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.padding = (12, 6)

        self.label = Label(
            text=self.text,
            color=self.text_color,
            halign="center",
            valign="middle",
            font_size=self.font_size,
        )
        self.label.bind(size=self._sync_text_size)
        self.add_widget(self.label)

        with self.canvas.before:
            self._bg_color_inst = Color(*self.bg_color)
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)

        self.bind(pos=self._update_bg, size=self._update_bg)
        self.bind(text=self._update_text)
        self.bind(text_color=self._update_colors)
        self.bind(font_size=self._update_font_size)
        self.bind(bg_color=self._update_bg_color)

    def _sync_text_size(self, _instance, _value):
        self.label.text_size = (self.label.width, self.label.height)

    def _update_bg(self, *_args):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size

    def _update_text(self, *_args):
        self.label.text = self.text

    def _update_colors(self, *_args):
        self.label.color = self.text_color

    def _update_font_size(self, *_args):
        self.label.font_size = self.font_size

    def _update_bg_color(self, *_args):
        self._bg_color_inst.rgba = self.bg_color

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
        # capture size_hint before passing to super
        size_hint = kwargs.pop("size_hint", None)
        size_hint_x = kwargs.pop("size_hint_x", None)
        super().__init__(**kwargs)
        # only lock size if no size_hint specified
        if size_hint is None and size_hint_x is None:
            self.size_hint = (None, None)
        elif size_hint_x is not None:
            self.size_hint_x = size_hint_x
        self.size = size
        self.orientation = "horizontal"
        self.padding = (2, 2)

        if self.source:
            self.icon = Image(source=self.source, size_hint=(None, None))
            if hasattr(self.icon, "fit_mode"):
                self.icon.fit_mode = "contain"
        else:
            self.icon = IconWidget(icon_type=self.icon_type, icon_color=self.icon_color, size_hint=(None, None))

        # icon stays fixed size and centered in button
        dim = max(24, int(self.height * 0.85))
        self.icon.size = (dim, dim)
        # use size_hint for natural centering in BoxLayout, not pos_hint
        self.icon.size_hint_x = None
        self.icon.size_hint_y = None
        
        self.add_widget(self.icon)

        self.bind(size=self._update_icon_size)
        self.bind(icon_type=self._update_icon_type)
        self.bind(source=self._on_source)
        self.bind(icon_color=self._update_icon_color)
        # tooltip support: default Greek labels for common icons
        default_tooltips = {
            "edit": S["MESSAGES"].get("TOOLTIP_EDIT", "Επεξεργασία"),
            "delete": S["MESSAGES"].get("TOOLTIP_DELETE", "Διαγραφή"),
            "eye": S["MESSAGES"].get("TOOLTIP_VIEW", "Προβολή"),
            "maintenance": S["MESSAGES"].get("TOOLTIP_MAINTENANCE", "Συντήρηση"),
            "inspection": S["MESSAGES"].get("TOOLTIP_INSPECTION", "Επιθεώρηση"),
            "book": S["MESSAGES"].get("TOOLTIP_MANUAL", "Manual"),
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
            if hasattr(self.icon, "fit_mode"):
                self.icon.fit_mode = "contain"
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
                # give a slightly larger horizontal/vertical margin to avoid clipping
                w = lbl.texture_size[0] + 24 if hasattr(lbl, "texture_size") else 100
                h = lbl.texture_size[1] + 12 if hasattr(lbl, "texture_size") else 24
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
                # schedule a post-layout update to recompute texture-derived size/position
                try:
                    from kivy.clock import Clock

                    def _refresh_tooltip(dt):
                        try:
                            lbl.texture_update()
                        except Exception:
                            pass
                        w2 = lbl.texture_size[0] + 24 if hasattr(lbl, "texture_size") else lbl.width
                        h2 = lbl.texture_size[1] + 12 if hasattr(lbl, "texture_size") else lbl.height
                        lbl.size = (w2, h2)
                        # reposition with same clamping logic
                        x2 = pos[0] + 12
                        y2 = pos[1] + 12
                        win_w, win_h = Window.size
                        if x2 + w2 > win_w:
                            x2 = win_w - w2 - 6
                        if y2 + h2 > win_h:
                            y2 = pos[1] - h2 - 12
                        if y2 < 6:
                            y2 = 6
                        lbl.pos = (x2, y2)

                    Clock.schedule_once(_refresh_tooltip, 0)
                except Exception:
                    pass
                # Add tooltip to Window to avoid affecting root layout sizing.
                try:
                    Window.add_widget(lbl)
                except Exception:
                    # Fallback: try an app-level overlay if Window doesn't accept widgets
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


