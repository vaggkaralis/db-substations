"""String access proxy for language-aware lookups.

This module keeps logic out of strings.py, which only contains editable content.
"""

from .config_manager import DEFAULT_LANGUAGE, get_current_language
from .strings import STRINGS_EL, STRINGS_EN


class _StringsProxy:
    def __init__(self, data: dict):
        self._data = data

    def _lookup(self, key, default=None, has_default=False):
        current_language = get_current_language()
        current = self._data.get(current_language, {})

        # For MESSAGES/TITLES: build a merged dict from the English base
        # plus the current language overlay
        if key in ("MESSAGES", "TITLES"):
            # Start with English as base
            en_data = self._data.get("en", {})
            merged = dict(en_data.get(key, {}))

            # Overlay with language-specific content from MESSAGES/TITLES if available
            if key in current:
                merged.update(current[key])

            # Also merge from BUTTONS as a fallback (BUTTONS may contain
            # translated messages)
            # These should override English defaults
            if "BUTTONS" in current:
                merged.update(current["BUTTONS"])

            return merged

        # For other keys, look directly in current language
        if key in current:
            return current[key]

        # Fallback to default language
        default_lang = self._data.get(DEFAULT_LANGUAGE, {})
        if key in default_lang:
            return default_lang[key]

        # Fallback to any available language
        for _, data in self._data.items():
            if key in data:
                return data[key]

        if has_default:
            return default
        raise KeyError(key)

    def _current(self) -> dict:
        current_language = get_current_language()
        return self._data.get(current_language, self._data[DEFAULT_LANGUAGE])

    def __getitem__(self, key):
        return self._lookup(key)

    def get(self, key, default=None):
        return self._lookup(key, default=default, has_default=True)

    def keys(self):
        return self._current().keys()

    def items(self):
        return self._current().items()

    def __contains__(self, item):
        return any(item in data for data in self._data.values())


STRINGS = _StringsProxy({"el": STRINGS_EL, "en": STRINGS_EN})
