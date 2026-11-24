from measurement_units import (
    auto_switch_insulation_unit,
    bind_insulation_unit_auto_switch,
)


class _Widget:
    def __init__(self, text=""):
        self.text = text
        self.callbacks = {}

    def bind(self, **callbacks):
        self.callbacks.update(callbacks)

    def set_text(self, value):
        self.text = value
        self.callbacks["text"](self, value)


class _Clock:
    def __init__(self):
        self.pending = {}

    def schedule_once(self, callback, _delay):
        self.pending[callback] = callback

    def unschedule(self, callback):
        self.pending.pop(callback, None)

    def flush(self):
        pending = list(self.pending)
        self.pending.clear()
        for callback in pending:
            callback()


def test_insulation_unit_switches_to_teraohm_at_threshold():
    unit = _Widget("GΩ")

    assert auto_switch_insulation_unit("15,0", unit)
    assert unit.text == "TΩ"


def test_insulation_unit_does_not_override_manual_selection():
    unit = _Widget("MΩ")

    assert not auto_switch_insulation_unit("10", unit)
    assert unit.text == "MΩ"


def test_insulation_unit_switch_waits_for_complete_value():
    value_input = _Widget()
    unit = _Widget("GΩ")
    clock = _Clock()
    bind_insulation_unit_auto_switch(value_input, unit, clock)

    value_input.set_text("1")
    value_input.set_text("15")
    value_input.set_text("150")
    clock.flush()

    assert unit.text == "GΩ"


def test_insulation_unit_switches_after_typing_stops():
    value_input = _Widget()
    unit = _Widget("GΩ")
    clock = _Clock()
    bind_insulation_unit_auto_switch(value_input, unit, clock)

    value_input.set_text("15")
    clock.flush()

    assert unit.text == "TΩ"


def test_insulation_unit_preserves_manual_override():
    value_input = _Widget()
    unit = _Widget("GΩ")
    clock = _Clock()
    bind_insulation_unit_auto_switch(value_input, unit, clock)

    value_input.set_text("15")
    clock.flush()
    unit.set_text("GΩ")
    value_input.set_text("14")
    clock.flush()

    assert unit.text == "GΩ"


def test_insulation_unit_binding_does_not_need_caller_clock(monkeypatch):
    value_input = _Widget()
    unit = _Widget("GΩ")
    clock = _Clock()
    monkeypatch.setattr(
        "kivy.clock.Clock",
        clock,
    )

    bind_insulation_unit_auto_switch(value_input, unit)
    value_input.set_text("15")
    clock.flush()

    assert unit.text == "TΩ"
