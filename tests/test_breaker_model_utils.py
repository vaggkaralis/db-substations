from breaker_model_utils import (
    ELEM_BREAKER_MT,
    ELEM_BREAKER_YT,
    calculate_three_phase_power_mva,
    extract_rated_current_from_model_name,
    infer_breaker_model_values,
)


def test_extract_rated_current_from_model_name():
    assert extract_rated_current_from_model_name("Siemens 3AF0143, 1250A") == 1250.0
    assert extract_rated_current_from_model_name("SIEMENS 3AE5322-1 (800A)") == 800.0
    assert extract_rated_current_from_model_name("Model without current") is None


def test_calculate_three_phase_power_mva():
    assert calculate_three_phase_power_mva(20.0, 1250.0) == 43.301
    assert calculate_three_phase_power_mva(150.0, 2000.0) == 519.615


def test_infer_breaker_model_values_prefers_model_name_current():
    current, power = infer_breaker_model_values(
        ELEM_BREAKER_MT,
        "Siemens 3AF0143, 1250A",
        1600.0,
    )
    assert current == 1250.0
    assert power == 43.301


def test_infer_breaker_model_values_uses_model_name_for_hv():
    current, power = infer_breaker_model_values(
        ELEM_BREAKER_YT,
        "ABB 8DN9-2, 2000A",
    )
    assert current == 2000.0
    assert power == 519.615
