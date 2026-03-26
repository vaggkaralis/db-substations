import math

from DBrun import SubstationApp


DUVAL_ZONES = {
    "PD": [(0.98, 0.02, 0.00), (0.98, 0.00, 0.02), (1.00, 0.00, 0.00)],
    "T1": [(0.80, 0.00, 0.20), (0.87, 0.00, 0.13), (0.98, 0.00, 0.02), (0.98, 0.02, 0.00), (0.80, 0.02, 0.18)],
    "T2": [(0.50, 0.00, 0.50), (0.80, 0.00, 0.20), (0.80, 0.02, 0.18), (0.50, 0.10, 0.40)],
    "T3": [(0.00, 0.00, 1.00), (0.50, 0.00, 0.50), (0.50, 0.10, 0.40), (0.00, 0.15, 0.85)],
    "D1": [(0.00, 0.15, 0.85), (0.50, 0.10, 0.40), (0.80, 0.02, 0.18), (0.98, 0.02, 0.00), (0.35, 0.65, 0.00), (0.00, 0.65, 0.35)],
    "D2": [(0.00, 0.65, 0.35), (0.35, 0.65, 0.00), (0.00, 1.00, 0.00)],
    "DT": [(0.00, 0.15, 0.85), (0.00, 0.65, 0.35), (0.50, 0.10, 0.40)],
}


def _ternary_to_cartesian(ch4_frac, c2h2_frac, c2h4_frac):
    return (
        c2h4_frac + (0.5 * c2h2_frac),
        (math.sqrt(3.0) / 2.0) * c2h2_frac,
    )


def _point_on_segment(point, start, end, eps=1e-9):
    px, py = point
    x1, y1 = start
    x2, y2 = end
    cross = abs((py - y1) * (x2 - x1) - (px - x1) * (y2 - y1))
    if cross > eps:
        return False
    dot = (px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)
    if dot < -eps:
        return False
    sq_len = (x2 - x1) ** 2 + (y2 - y1) ** 2
    return dot - sq_len <= eps


def _point_in_polygon(point, polygon):
    inside = False
    for idx in range(len(polygon)):
        start = polygon[idx]
        end = polygon[(idx + 1) % len(polygon)]
        if _point_on_segment(point, start, end):
            return True
        x1, y1 = start
        x2, y2 = end
        intersects = ((y1 > point[1]) != (y2 > point[1])) and (
            point[0] < (x2 - x1) * (point[1] - y1) / ((y2 - y1) or 1e-12) + x1
        )
        if intersects:
            inside = not inside
    return inside


def reference_ratio_fault(values):
    ch4_h2 = values["ch4"] / values["h2"]
    c2h2_c2h4 = values["c2h2"] / values["c2h4"]
    c2h4_c2h6 = values["c2h4"] / values["c2h6"]

    if ch4_h2 < 0.1 and c2h2_c2h4 < 0.1 and c2h4_c2h6 < 1.0:
        return "PD"
    if ch4_h2 > 1.0 and c2h2_c2h4 < 0.1 and c2h4_c2h6 < 1.0:
        return "T1"
    if ch4_h2 > 1.0 and c2h2_c2h4 < 0.1 and 1.0 <= c2h4_c2h6 <= 3.0:
        return "T2"
    if ch4_h2 > 1.0 and c2h2_c2h4 < 0.1 and c2h4_c2h6 > 3.0:
        return "T3"
    if 0.1 <= ch4_h2 <= 1.0 and 0.1 <= c2h2_c2h4 < 3.0 and c2h4_c2h6 > 1.0:
        return "D1"
    if 0.1 <= ch4_h2 <= 1.0 and c2h2_c2h4 >= 3.0 and c2h4_c2h6 > 1.0:
        return "D2"
    return None


def reference_duval_zone(values):
    total = values["ch4"] + values["c2h2"] + values["c2h4"]
    ch4_frac = values["ch4"] / total
    c2h2_frac = values["c2h2"] / total
    c2h4_frac = values["c2h4"] / total
    point = _ternary_to_cartesian(ch4_frac, c2h2_frac, c2h4_frac)
    for zone_name in ("PD", "D2", "DT", "D1", "T3", "T2", "T1"):
        polygon = [_ternary_to_cartesian(*vertex) for vertex in DUVAL_ZONES[zone_name]]
        if _point_in_polygon(point, polygon):
            return zone_name
    return None


def test_app_dga_evaluation_matches_reference_t3_diagnosis():
    app = SubstationApp()
    values = {
        "h2": 10.0,
        "ch4": 20.0,
        "c2h2": 5.0,
        "c2h4": 75.0,
        "c2h6": 10.0,
        "co": 300.0,
        "co2": 4500.0,
        "o2": 15000.0,
        "n2": 45000.0,
        "c3h8": 0.0,
        "h2o": 0.0,
        "density": 0.89,
        "humidity": 10.0,
        "dielectric_strength": 60.0,
        "loss_factor": 0.002,
        "surface_tension": 42.0,
    }

    evaluation = app._evaluate_dga_values(values)
    diagnostics = evaluation["diagnostics"]

    assert reference_ratio_fault(values) == "T3"
    assert reference_duval_zone(values) == "T3"
    assert diagnostics["ratio_method"]["code"] == "T3"
    assert diagnostics["duval_triangle_1"]["code"] == "T3"
    assert evaluation["overall_level"] == "bad"
    assert "high-temperature" in diagnostics["ratio_method"]["summary"].lower()


def test_app_dga_limit_failure_and_reasoning_are_reported_for_bad_case():
    app = SubstationApp()
    values = {
        "h2": 50.0,
        "ch4": 10.0,
        "c2h2": 80.0,
        "c2h4": 10.0,
        "c2h6": 2.0,
        "co": 900.0,
        "co2": 1800.0,
        "o2": 12000.0,
        "n2": 40000.0,
        "c3h8": 0.0,
        "h2o": 0.0,
        "density": 0.89,
        "humidity": 35.0,
        "dielectric_strength": 25.0,
        "loss_factor": 0.02,
        "surface_tension": 18.0,
    }

    evaluation = app._evaluate_dga_values(values)
    diagnostics = evaluation["diagnostics"]
    summary = app._format_dga_problem_summary(evaluation, max_bad=3, max_warn=2)

    assert reference_ratio_fault(values) == "D2"
    assert reference_duval_zone(values) == "D2"
    assert diagnostics["ratio_method"]["code"] == "D2"
    assert diagnostics["duval_triangle_1"]["code"] == "D2"
    assert diagnostics["paper_condition"]["code"] == "CELLULOSE_SEVERE"
    assert evaluation["is_problematic"] is True
    assert evaluation["overall_level"] == "bad"
    assert any(item["key"] == "c2h2" for item in evaluation["problems"])
    assert "IEC 60599 / Rogers" in summary
    assert "Duval Triangle 1" in summary
