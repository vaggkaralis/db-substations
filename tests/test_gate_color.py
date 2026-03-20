from DBrun import get_gate_color, GATE_COLOR_PALETTE, _gate_color_map, _assigned_colors


def test_gate_color_consistent_for_same_label():
    _gate_color_map.clear()
    c1 = get_gate_color("ΠΥΛΗ 1")
    c2 = get_gate_color("ΠΥΛΗ 1")
    assert c1 == c2
    assert c1 in GATE_COLOR_PALETTE or c1 == (0.85, 0.85, 0.85, 1)


def test_gate_color_empty_returns_gray():
    c = get_gate_color("")
    assert c == (0.85, 0.85, 0.85, 1)


def test_gate_color_maps_multiple_labels():
    _gate_color_map.clear()
    _assigned_colors.clear()
    labels = ["A", "B", "C", "ΠΥΛΗ 2"]
    colors = [get_gate_color(l) for l in labels]
    # mapping should have entries for these labels
    for l in labels:
        assert l in _gate_color_map
    # colors should be tuples
    assert all(isinstance(col, tuple) for col in colors)


def test_gate_colors_unique_for_multiple_labels():
    _gate_color_map.clear()
    _assigned_colors.clear()
    labels = [f"ΠΥΛΗ {i}" for i in range(1, len(GATE_COLOR_PALETTE) + 2)]
    colors = [get_gate_color(l) for l in labels]
    # Expect colors to be unique for each label
    assert len(set(colors)) == len(labels)
