from strings import STRINGS_EL, STRINGS_EN


def test_greek_measurement_labels_use_greek_phase_ground_text():
    messages = STRINGS_EL["MESSAGES"]

    assert messages["PHASE_TO_PHASE_LABEL"] == "ΦΑ-ΦΑ"
    assert messages["PHASE_TO_PHASE_LABEL_COLON"] == "ΦΑ-ΦΑ:"
    assert messages["INSULATION_LABEL_FA"] == "ΦΑ-ΦΑ"
    assert messages["INSULATION_LABEL_FA_GND"] == "ΦΑ-ΓΗ"
    assert messages["INSULATION_LABEL_FB"] == "ΦΒ-ΦΒ"
    assert messages["INSULATION_LABEL_FB_GND"] == "ΦΒ-ΓΗ"
    assert messages["INSULATION_LABEL_FC"] == "ΦΓ-ΦΓ"
    assert messages["INSULATION_LABEL_FC_GND"] == "ΦΓ-ΓΗ"
    assert messages["VIDAR_LABEL_FB"] == "ΦΒ-ΦΒ:"
    assert messages["VIDAR_LABEL_FC"] == "ΦΓ-ΦΓ:"
    assert "GEI" not in messages["INSULATION_MEASUREMENT_CLOSED_HEADER"]


def test_english_measurement_labels_keep_english_ground_text():
    messages = STRINGS_EN["MESSAGES"]

    assert messages["PHASE_TO_PHASE_LABEL"] == "FA-FA"
    assert messages["INSULATION_LABEL_FA_GND"] == "FA-GND"
    assert messages["INSULATION_LABEL_FB_GND"] == "FB-GND"
    assert messages["INSULATION_LABEL_FC_GND"] == "FC-GND"
