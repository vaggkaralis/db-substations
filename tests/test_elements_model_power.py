from elements import _resolve_selected_model_power_mva


def test_resolve_selected_model_power_mva_uses_model_rated_current_for_mv_breakers():
    selected_model = {
        "model_name": "Schneider EvoPact",
        "rated_normal_current_a": 630,
        "power_mva": 55.0,
    }

    resolved_power = _resolve_selected_model_power_mva(
        "Διακόπτης ΜΤ",
        selected_model,
        fallback_power_mva=55.0,
    )

    assert resolved_power == 21.824


def test_resolve_selected_model_power_mva_prefers_model_power_for_non_breakers():
    selected_model = {
        "model_name": "Transformer X",
        "power_mva": 50.0,
    }

    resolved_power = _resolve_selected_model_power_mva(
        "Μετασχηματιστής",
        selected_model,
        fallback_power_mva=20.0,
    )

    assert resolved_power == 50.0


def test_resolve_selected_model_power_mva_falls_back_when_no_model_selected():
    assert (
        _resolve_selected_model_power_mva(
            "Διακόπτης ΜΤ",
            None,
            fallback_power_mva="43.301",
        )
        == 43.301
    )
