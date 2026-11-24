import math
import re


def _parse_decimal(value):
    text = re.sub(r"\s+", "", str(value or "")).replace(",", ".")
    if not text:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def auto_switch_insulation_unit(value, unit_widget):
    number = _parse_decimal(value)
    if (
        number is not None
        and number <= 15
        and str(getattr(unit_widget, "text", "") or "") == "GΩ"
    ):
        unit_widget.text = "TΩ"
        return True
    return False


def bind_insulation_unit_auto_switch(value_input, unit_widget, clock=None, delay=0.35):
    if clock is None:
        try:
            from kivy.clock import Clock

            clock = Clock
        except Exception:
            clock = None

    manual_unit_override = False
    applying_auto_unit = False

    def _apply(_dt=0):
        nonlocal applying_auto_unit
        if manual_unit_override:
            return
        applying_auto_unit = True
        try:
            auto_switch_insulation_unit(getattr(value_input, "text", ""), unit_widget)
        finally:
            applying_auto_unit = False

    def _unit_changed(*_args):
        nonlocal manual_unit_override
        if not applying_auto_unit:
            manual_unit_override = True

    def _schedule(*_args):
        try:
            if clock is None:
                raise RuntimeError("Kivy Clock is unavailable")
            clock.unschedule(_apply)
        except Exception:
            pass
        try:
            if clock is None:
                raise RuntimeError("Kivy Clock is unavailable")
            clock.schedule_once(_apply, delay)
        except Exception:
            _apply()

    value_input.bind(text=_schedule)
    unit_widget.bind(text=_unit_changed)
    return value_input
