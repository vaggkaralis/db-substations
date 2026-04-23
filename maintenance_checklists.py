import json
import os

_DEFAULT_CATALOG = {
    "categories": [
        {
            "key": "transformer_maintenance",
            "label": "Συντήρηση μετασχηματιστή",
            "items": [],
        },
        {
            "key": "hv_breaker_maintenance",
            "label": "Συντήρηση διακόπτη υψηλής τάσης",
            "items": [],
        },
        {
            "key": "mv_bar_maintenance",
            "label": "Συντήρηση μέσης τάσης",
            "items": [],
        },
    ]
}


def _catalog_path() -> str:
    return os.path.join(os.path.dirname(__file__), "maintenance_checklists.json")


def load_catalog() -> dict:
    path = _catalog_path()
    if not os.path.exists(path):
        return _DEFAULT_CATALOG.copy()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and isinstance(data.get("categories"), list):
            return data
    except Exception:
        pass
    return _DEFAULT_CATALOG.copy()


def get_categories() -> list[dict]:
    categories = []
    for category in load_catalog().get("categories", []):
        key = str(category.get("key") or "").strip()
        label = str(category.get("label") or key).strip()
        items = category.get("items") or []
        if not key or not label:
            continue
        normalized_items = []
        for item in items:
            item_key = str(item.get("key") or "").strip()
            item_label = str(item.get("label") or item_key).strip()
            if not item_key or not item_label:
                continue
            normalized_items.append({"key": item_key, "label": item_label})
        categories.append({"key": key, "label": label, "items": normalized_items})
    return categories


def get_category_map() -> dict:
    return {category["key"]: category for category in get_categories()}


def infer_category_keys_from_elements(app, element_rows) -> list[str]:
    keys = []
    for row in element_rows or []:
        if len(row) < 2:
            continue
        elem_type = row[1] or ""
        if getattr(app, "_is_transformer", None) and app._is_transformer(elem_type):
            if "transformer_maintenance" not in keys:
                keys.append("transformer_maintenance")
            continue
        if elem_type == getattr(app, "ELEM_BREAKER_YT", None):
            if "hv_breaker_maintenance" not in keys:
                keys.append("hv_breaker_maintenance")
            continue
        if elem_type == getattr(app, "ELEM_BREAKER_MT", None):
            if "mv_bar_maintenance" not in keys:
                keys.append("mv_bar_maintenance")
    return keys


def normalize_state(raw_state) -> dict:
    category_map = get_category_map()
    selected_categories = []
    item_values = {}
    comments = {}
    custom_items = []
    state = raw_state if isinstance(raw_state, dict) else {}

    raw_selected = state.get("selected_categories") or []
    for key in raw_selected:
        key = str(key or "").strip()
        if key in category_map and key not in selected_categories:
            selected_categories.append(key)

    raw_items = state.get("items") if isinstance(state.get("items"), dict) else {}
    for category_key, category in category_map.items():
        item_values[category_key] = {}
        raw_category_items = (
            raw_items.get(category_key)
            if isinstance(raw_items.get(category_key), dict)
            else {}
        )
        for item in category.get("items", []):
            item_values[category_key][item["key"]] = bool(
                raw_category_items.get(item["key"], False)
            )
        # preserve comments for each known item (if present in raw state)
        raw_comments = (
            state.get("comments") if isinstance(state.get("comments"), dict) else {}
        )
        comments[category_key] = {}
        raw_category_comments = (
            raw_comments.get(category_key)
            if isinstance(raw_comments.get(category_key), dict)
            else {}
        )
        for item in category.get("items", []):
            comments[category_key][item["key"]] = str(
                raw_category_comments.get(item["key"], "") or ""
            )

    # preserve custom free-form items (list of dicts with text, checked, comment)
    raw_custom = (
        state.get("custom_items") if isinstance(state.get("custom_items"), list) else []
    )
    for entry in raw_custom:
        try:
            text = str(entry.get("text") or "").strip()
            checked = bool(entry.get("checked", False))
            comment = str(entry.get("comment") or "")
            custom_items.append({"text": text, "checked": checked, "comment": comment})
        except Exception:
            continue
    return {
        "selected_categories": selected_categories,
        "items": item_values,
        "comments": comments,
        "custom_items": custom_items,
    }


def build_state(selected_categories=None, previous_state=None) -> dict:
    state = normalize_state(previous_state)
    if selected_categories is not None:
        normalized = []
        category_map = get_category_map()
        for key in selected_categories:
            key = str(key or "").strip()
            if key in category_map and key not in normalized:
                normalized.append(key)
        state["selected_categories"] = normalized
    return state
