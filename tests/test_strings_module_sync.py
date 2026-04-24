import dbsubstations.strings as packaged_strings
import strings


def test_top_level_and_packaged_strings_modules_stay_in_sync():
    assert strings.STRINGS_EL == packaged_strings.STRINGS_EL
    assert strings.STRINGS_EN == packaged_strings.STRINGS_EN
