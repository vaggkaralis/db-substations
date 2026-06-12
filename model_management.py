"""
Model Management UI Functions for Element Models
"""

import os
import webbrowser
from datetime import date

from breaker_model_utils import infer_breaker_model_values
from popups import ask_open_file, show_message_popup
from strings_proxy import STRINGS as S
from ui.shared import IconOnlyButton

# Canonical breaker element names
ELEM_BREAKER_YT = S.get("MESSAGES", {}).get("ELEMENT_BREAKER_YT", "Διακόπτης ΥΤ")
ELEM_BREAKER_MT = S.get("MESSAGES", {}).get("ELEMENT_BREAKER_MT", "Διακόπτης ΜΤ")

TRANSFORMER_CATEGORY_TOKEN = "150/20"
MOTOR_DRIVE_CATEGORY = "Motor Drive"
ALL_BREAKERS_TOKEN = "__ALL_BREAKERS__"

TRANSFORMER_MODEL_FIELD_DEFS = [
    {
        "key": "connection_group",
        "label_key": "MODEL_CONNECTION_GROUP_LABEL",
        "hint_key": "MODEL_CONNECTION_GROUP_HINT",
        "default_label": "Ομάδα Συνδεσμολογίας:",
        "default_hint": "π.χ. Dyn1",
        "numeric": False,
    },
    {
        "key": "rated_voltage_hv_lv",
        "label_key": "MODEL_RATED_VOLTAGE_HV_LV_LABEL",
        "hint_key": "MODEL_RATED_VOLTAGE_HV_LV_HINT",
        "default_label": "Ονομ. Τάση ΥΤ/ΜΤ:",
        "default_hint": "π.χ. 150/20 kV",
        "numeric": False,
    },
    {
        "key": "mounting",
        "label_key": "MODEL_MOUNTING_LABEL",
        "hint_key": "MODEL_MOUNTING_HINT",
        "default_label": "Τρόπος Εγκατάστασης:",
        "default_hint": "π.χ. Outdoor",
        "numeric": False,
    },
    {
        "key": "specification",
        "label_key": "MODEL_SPECIFICATION_LABEL",
        "hint_key": "MODEL_SPECIFICATION_HINT",
        "default_label": "Προδιαγραφή:",
        "default_hint": "π.χ. IEC 60076",
        "numeric": False,
    },
    {
        "key": "bil_hv_lv_kv",
        "label_key": "MODEL_BIL_HV_LV_KV_LABEL",
        "hint_key": "MODEL_BIL_HV_LV_KV_HINT",
        "default_label": "BIL ΥΤ/ΜΤ (kV):",
        "default_hint": "π.χ. 750/150",
        "numeric": False,
    },
    {
        "key": "total_weight_kg",
        "label_key": "MODEL_TOTAL_WEIGHT_KG_LABEL",
        "hint_key": "MODEL_TOTAL_WEIGHT_KG_HINT",
        "default_label": "Συνολικό Βάρος (kg):",
        "default_hint": "π.χ. 69800",
        "numeric": True,
    },
    {
        "key": "oil_weight_kg",
        "label_key": "MODEL_OIL_WEIGHT_KG_LABEL",
        "hint_key": "MODEL_OIL_WEIGHT_KG_HINT",
        "default_label": "Βάρος Ελαίου (kg):",
        "default_hint": "π.χ. 25990",
        "numeric": True,
    },
]


def _safe_int(value):
    try:
        return int(str(value).strip())
    except Exception:
        return None


def _canonical_transformer_filter_label():
    return "Μετασχηματιστής 150/20KV"


def _is_transformer_filter_value(value):
    text = str(value or "").strip().casefold()
    return any(
        token in text
        for token in (
            TRANSFORMER_CATEGORY_TOKEN.casefold(),
            "transform",
            "transofr",
            "μετασχη",
        )
    )


def _normalize_element_type_filter_value(value):
    text = str(value or "").strip()
    if _is_transformer_filter_value(text):
        return _canonical_transformer_filter_label()
    return text


def _get_breaker_role_options():
    return [
        S["MESSAGES"].get("ALL_OPTION", "(Όλα)"),
        S["MESSAGES"].get("BREAKER_LABEL_CENTRAL", "Κεντρικός"),
        S["MESSAGES"].get("BREAKER_LABEL_LINE", "Γραμμής"),
        S["MESSAGES"].get("BREAKER_LABEL_INTERCON", "Διασυνδετικός"),
        S["MESSAGES"].get("BREAKER_LABEL_CAPACITOR", "Διακόπτης Πυκνωτών"),
    ]


def _build_distance_filter_values(max_distance_km):
    all_label = S["MESSAGES"].get("ALL_OPTION", "(Όλα)")
    values = [all_label]
    try:
        max_distance_km = float(max_distance_km or 0)
    except Exception:
        max_distance_km = 0.0
    if max_distance_km <= 0:
        return values
    step_max = int(((max_distance_km + 49.999) // 50) * 50)
    for limit in range(50, step_max + 1, 50):
        values.append(f"{limit} km")
    return values


def _parse_distance_filter_value(value):
    text = str(value or "").strip()
    if not text or text == S["MESSAGES"].get("ALL_OPTION", "(Όλα)"):
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    return int(digits) if digits else None


def _element_type_filter_options(app_instance, conn):
    c = conn.cursor()
    c.execute(
        "SELECT DISTINCT element_type FROM elements WHERE TRIM(COALESCE(element_type, '')) != '' ORDER BY element_type"
    )
    available = [
        _normalize_element_type_filter_value(row[0])
        for row in (c.fetchall() or [])
        if row and row[0]
    ]
    ordered = [S["MESSAGES"].get("ALL_OPTION", "(Όλα)")]
    ordered.append(S["MESSAGES"].get("ALL_BREAKERS_OPTION", "Όλοι οι Διακόπτες"))
    for element_type in [
        _normalize_element_type_filter_value(value)
        for value in getattr(app_instance, "ELEMENT_TYPES", [])
    ]:
        if element_type in available and element_type not in ordered:
            ordered.append(element_type)
    for element_type in available:
        if element_type not in ordered:
            ordered.append(element_type)
    return ordered


def _breaker_role_match_sql(selected_role, elem_breaker_mt, elem_breaker_yt):
    if not selected_role or selected_role == S["MESSAGES"].get("ALL_OPTION", "(Όλα)"):
        return "", []

    if selected_role == S["MESSAGES"].get("BREAKER_LABEL_CENTRAL", "Κεντρικός"):
        return (
            " AND ((e.element_type = ?) OR (e.element_type = ? AND COALESCE(e.is_main_switch, 0) = 1))",
            [elem_breaker_yt, elem_breaker_mt],
        )
    if selected_role == S["MESSAGES"].get("BREAKER_LABEL_INTERCON", "Διασυνδετικός"):
        return (
            " AND e.element_type = ? AND COALESCE(e.is_main_switch, 0) = 2",
            [elem_breaker_mt],
        )
    if selected_role == S["MESSAGES"].get(
        "BREAKER_LABEL_CAPACITOR", "Διακόπτης Πυκνωτών"
    ):
        return (
            " AND e.element_type = ? AND COALESCE(e.is_main_switch, 0) = 3",
            [elem_breaker_mt],
        )
    return (
        " AND e.element_type = ? AND COALESCE(e.is_main_switch, 0) = 0",
        [elem_breaker_mt],
    )


def search_elements(
    app_instance,
    *,
    element_type_filter=None,
    breaker_category_filter=None,
    breaker_role_filter=None,
    year_relation=None,
    reference_year=None,
    distance_relation=None,
    distance_limit_km=None,
    sort_direction="distance_desc",
    include_inactive=False,
):
    c = app_instance.conn.cursor()
    c.execute("PRAGMA table_info(substations)")
    substation_columns = {row[1] for row in (c.fetchall() or [])}
    distance_expr = (
        "s.base_distance_km" if "base_distance_km" in substation_columns else "NULL"
    )

    sql = f"""
        SELECT
            e.id,
            e.element_type,
            e.name,
            e.serial_number,
            e.maintenance_date,
            e.manufacturer,
            e.installation_space,
            e.operating_status,
            e.maintenance_cycle,
            e.breaker_category,
            e.manufacture_year,
            s.name AS substation_name,
            s.id AS substation_id,
            {distance_expr} AS base_distance_km,
            COALESCE(e.is_main_switch, 0) AS is_main_switch
        FROM elements e
        JOIN substations s ON e.substation_id = s.id
        WHERE 1=1
    """
    params = []

    all_option = S["MESSAGES"].get("ALL_OPTION", "(Όλα)")
    all_breakers_label = S["MESSAGES"].get("ALL_BREAKERS_OPTION", "Όλοι οι Διακόπτες")
    if not include_inactive:
        sql += " AND COALESCE(TRIM(e.operating_status), '') != 'Ανενεργή'"
    if element_type_filter and element_type_filter != all_option:
        normalized_type_filter = _normalize_element_type_filter_value(
            element_type_filter
        )
        if normalized_type_filter == all_breakers_label:
            sql += " AND e.element_type IN (?, ?)"
            params.extend([ELEM_BREAKER_MT, ELEM_BREAKER_YT])
        elif _is_transformer_filter_value(normalized_type_filter):
            sql += (
                " AND (e.element_type = ? OR e.element_type LIKE ? OR "
                "LOWER(COALESCE(e.element_type, '')) LIKE ? OR "
                "LOWER(COALESCE(e.element_type, '')) LIKE ? )"
            )
            params.extend(
                [
                    _canonical_transformer_filter_label(),
                    "%150/20%",
                    "%transform%",
                    "%transofr%",
                ]
            )
        else:
            sql += " AND e.element_type = ?"
            params.append(normalized_type_filter)

    if breaker_category_filter and breaker_category_filter != all_option:
        sql += " AND TRIM(COALESCE(e.breaker_category, '')) = ?"
        params.append(str(breaker_category_filter).strip())

    role_sql, role_params = _breaker_role_match_sql(
        breaker_role_filter,
        ELEM_BREAKER_MT,
        ELEM_BREAKER_YT,
    )
    sql += role_sql
    params.extend(role_params)

    year_value = _safe_int(reference_year)
    if year_relation and year_relation != all_option and year_value is not None:
        year_expr = "CASE WHEN TRIM(COALESCE(e.manufacture_year, '')) GLOB '[0-9][0-9][0-9][0-9]' THEN CAST(TRIM(e.manufacture_year) AS INTEGER) END"
        if year_relation == S["MESSAGES"].get(
            "OLDER_THAN_YEAR_LABEL", "Παλαιότερα από"
        ):
            sql += f" AND {year_expr} IS NOT NULL AND {year_expr} < ?"
        else:
            sql += f" AND {year_expr} IS NOT NULL AND {year_expr} >= ?"
        params.append(year_value)

    if distance_limit_km is not None:
        sql += " AND s.base_distance_km IS NOT NULL"
        if distance_relation == S["MESSAGES"].get(
            "DISTANCE_GREATER_THAN_LABEL", "Μεγαλύτερη από"
        ):
            sql += " AND s.base_distance_km >= ?"
        else:
            sql += " AND s.base_distance_km <= ?"
        params.append(float(distance_limit_km))

    if sort_direction == "distance_asc":
        sql += " ORDER BY CASE WHEN s.base_distance_km IS NULL THEN 1 ELSE 0 END, s.base_distance_km ASC, s.name ASC, e.name ASC"
    elif sort_direction == "substation_asc":
        sql += " ORDER BY s.name ASC, e.name ASC"
    else:
        sql += " ORDER BY CASE WHEN s.base_distance_km IS NULL THEN 1 ELSE 0 END, s.base_distance_km DESC, s.name ASC, e.name ASC"

    c.execute(sql, params)
    return c.fetchall() or []


def _age_bucket_labels():
    return ["0-10", "11-20", "21-30", "31+"]


def _age_bucket_for_year(manufacture_year, current_year=None):
    year_value = _safe_int(manufacture_year)
    if year_value is None:
        return None
    current_year = current_year or date.today().year
    age = max(0, int(current_year) - year_value)
    if age <= 10:
        return "0-10"
    if age <= 20:
        return "11-20"
    if age <= 30:
        return "21-30"
    return "31+"


def _increment_count(target, key, amount=1):
    if not key:
        return
    target[key] = int(target.get(key, 0) or 0) + amount


def _sorted_count_items(counts):
    return sorted(
        [(label, value) for label, value in (counts or {}).items() if value],
        key=lambda item: (-item[1], str(item[0]).casefold()),
    )


def _filtered_elements_for_statistics(
    app_instance,
    *,
    include_inactive=False,
    distance_relation=None,
    distance_limit_km=None,
    element_scope=None,
):
    c = app_instance.conn.cursor()
    sql = """
        SELECT
            e.id,
            e.element_type,
            e.breaker_category,
            e.manufacture_year,
            e.operating_status,
            s.base_distance_km,
            e.element_model_id,
            em.model_name,
            COALESCE(em.manufacturer, e.manufacturer, '-') AS model_manufacturer,
            COALESCE(em.element_category, e.element_type) AS model_category
        FROM elements e
        JOIN substations s ON e.substation_id = s.id
        LEFT JOIN element_models em ON e.element_model_id = em.id
        WHERE 1=1
    """
    params = []
    all_option = S["MESSAGES"].get("ALL_OPTION", "(Όλα)")
    all_breakers_label = S["MESSAGES"].get("ALL_BREAKERS_OPTION", "Όλοι οι Διακόπτες")

    if not include_inactive:
        sql += " AND COALESCE(TRIM(e.operating_status), '') != 'Ανενεργή'"

    normalized_scope = _normalize_element_type_filter_value(element_scope)
    if normalized_scope and normalized_scope != all_option:
        if normalized_scope == all_breakers_label:
            sql += " AND e.element_type IN (?, ?)"
            params.extend([ELEM_BREAKER_MT, ELEM_BREAKER_YT])
        elif _is_transformer_filter_value(normalized_scope):
            sql += (
                " AND (e.element_type = ? OR e.element_type LIKE ? OR "
                "LOWER(COALESCE(e.element_type, '')) LIKE ? OR "
                "LOWER(COALESCE(e.element_type, '')) LIKE ? )"
            )
            params.extend(
                [
                    _canonical_transformer_filter_label(),
                    "%150/20%",
                    "%transform%",
                    "%transofr%",
                ]
            )
        else:
            sql += " AND e.element_type = ?"
            params.append(normalized_scope)

    if distance_limit_km is not None:
        sql += " AND s.base_distance_km IS NOT NULL"
        if distance_relation == S["MESSAGES"].get(
            "DISTANCE_GREATER_THAN_LABEL", "Μεγαλύτερη από"
        ):
            sql += " AND s.base_distance_km >= ?"
        else:
            sql += " AND s.base_distance_km <= ?"
        params.append(float(distance_limit_km))

    sql += " ORDER BY e.element_type ASC, e.name ASC"
    c.execute(sql, params)
    return c.fetchall() or []


def get_model_management_statistics(
    app_instance,
    *,
    include_inactive=False,
    distance_relation=None,
    distance_limit_km=None,
    element_scope=None,
    top_n_models=5,
):
    rows = _filtered_elements_for_statistics(
        app_instance,
        include_inactive=include_inactive,
        distance_relation=distance_relation,
        distance_limit_km=distance_limit_km,
        element_scope=element_scope,
    )

    hv_breaker_types = {}
    mv_breaker_types = {}
    transformer_ages = {label: 0 for label in _age_bucket_labels()}
    hv_breaker_ages = {label: 0 for label in _age_bucket_labels()}
    mv_breaker_ages = {label: 0 for label in _age_bucket_labels()}
    manufacturer_models_by_category = {}
    seen_models = set()
    model_usage_by_category = {}

    for (
        _elem_id,
        element_type,
        breaker_category,
        manufacture_year,
        _operating_status,
        _base_distance_km,
        element_model_id,
        model_name,
        model_manufacturer,
        model_category,
    ) in rows:
        if element_type == ELEM_BREAKER_YT:
            _increment_count(
                hv_breaker_types,
                breaker_category or S["MESSAGES"].get("OTHER_LABEL", "Άλλο"),
            )
            age_bucket = _age_bucket_for_year(manufacture_year)
            if age_bucket:
                hv_breaker_ages[age_bucket] += 1
        elif element_type == ELEM_BREAKER_MT:
            _increment_count(
                mv_breaker_types,
                breaker_category or S["MESSAGES"].get("OTHER_LABEL", "Άλλο"),
            )
            age_bucket = _age_bucket_for_year(manufacture_year)
            if age_bucket:
                mv_breaker_ages[age_bucket] += 1

        if _is_transformer_filter_value(element_type):
            age_bucket = _age_bucket_for_year(manufacture_year)
            if age_bucket:
                transformer_ages[age_bucket] += 1

        model_key = (
            element_model_id
            if element_model_id is not None
            else (model_category, model_name, model_manufacturer)
        )
        if model_name and model_key not in seen_models:
            seen_models.add(model_key)
            category_key = _normalize_element_type_filter_value(
                model_category or element_type
            )
            category_manufacturers = manufacturer_models_by_category.setdefault(
                category_key, {}
            )
            _increment_count(category_manufacturers, model_manufacturer or "-")

        if model_name:
            category_key = _normalize_element_type_filter_value(
                model_category or element_type
            )
            category_usage = model_usage_by_category.setdefault(category_key, {})
            _increment_count(category_usage, model_name)

    most_used_models = {
        category: _sorted_count_items(counts)[: max(1, int(top_n_models or 5))]
        for category, counts in model_usage_by_category.items()
        if _sorted_count_items(counts)
    }

    return {
        "rows_count": len(rows),
        "pies": {
            "types_hv_breakers": _sorted_count_items(hv_breaker_types),
            "types_mv_breakers": _sorted_count_items(mv_breaker_types),
            "age_transformers": _sorted_count_items(transformer_ages),
            "age_hv_breakers": _sorted_count_items(hv_breaker_ages),
            "age_mv_breakers": _sorted_count_items(mv_breaker_ages),
        },
        "bars": {
            "manufacturer_count_models": {
                category: _sorted_count_items(counts)
                for category, counts in manufacturer_models_by_category.items()
                if _sorted_count_items(counts)
            },
            "most_used_models_per_category": most_used_models,
        },
    }


def show_model_statistics_popup(app_instance, parent_popup=None):
    from kivy.graphics import Color, Ellipse, Line, Rectangle
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.checkbox import CheckBox
    from kivy.uix.gridlayout import GridLayout
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.spinner import Spinner
    from kivy.uix.widget import Widget

    popup = Popup(
        title=S["MESSAGES"].get("MODEL_STATS_TITLE", "Στατιστικά Στοιχείων"),
        size_hint=(0.97, 0.94),
    )
    main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    c = app_instance.conn.cursor()
    c.execute("SELECT MAX(base_distance_km) FROM substations")
    max_distance = (c.fetchone() or [None])[0]
    all_option = S["MESSAGES"].get("ALL_OPTION", "(Όλα)")

    filter_row = GridLayout(cols=2, spacing=8, size_hint_y=None)
    filter_row.bind(minimum_height=filter_row.setter("height"))
    filter_row.add_widget(
        Label(
            text=S["MESSAGES"].get("FILTER_TYPE_LABEL", "Τύπος Στοιχείου:"),
            size_hint_y=None,
            height=30,
        )
    )
    scope_spinner = Spinner(
        text=all_option,
        values=_element_type_filter_options(app_instance, app_instance.conn),
        size_hint_y=None,
        height=36,
    )
    filter_row.add_widget(scope_spinner)

    filter_row.add_widget(
        Label(
            text=S["MESSAGES"].get("DISTANCE_FILTER_LABEL", "Απόσταση από βάση:"),
            size_hint_y=None,
            height=30,
        )
    )
    distance_box = BoxLayout(size_hint_y=None, height=36, spacing=6)
    distance_relation_spinner = Spinner(
        text=all_option,
        values=[
            all_option,
            S["MESSAGES"].get("DISTANCE_SMALLER_THAN_LABEL", "Μικρότερη από"),
            S["MESSAGES"].get("DISTANCE_GREATER_THAN_LABEL", "Μεγαλύτερη από"),
        ],
        size_hint_x=0.48,
    )
    distance_spinner = Spinner(
        text=all_option,
        values=_build_distance_filter_values(max_distance),
        size_hint_x=0.52,
    )
    distance_box.add_widget(distance_relation_spinner)
    distance_box.add_widget(distance_spinner)
    filter_row.add_widget(distance_box)

    filter_row.add_widget(
        Label(
            text=S["MESSAGES"].get("SHOW_INACTIVE_ELEMENTS", "Εμφάνιση ανενεργών"),
            size_hint_y=None,
            height=30,
        )
    )
    inactive_box = BoxLayout(size_hint_y=None, height=36, spacing=6)
    include_inactive_checkbox = CheckBox(
        active=False, size_hint=(None, None), size=(28, 28)
    )
    inactive_box.add_widget(include_inactive_checkbox)
    inactive_box.add_widget(
        Label(
            text=S["MESSAGES"].get(
                "INACTIVE_RESULTS_NOTE", "Προβολή και ανενεργών στοιχείων"
            ),
            halign="left",
            valign="middle",
        )
    )
    filter_row.add_widget(inactive_box)

    main_layout.add_widget(filter_row)

    header_row = BoxLayout(size_hint_y=None, height=42, spacing=8)
    summary_label = Label(text="", size_hint_x=0.7, halign="left", valign="middle")
    summary_label.bind(size=lambda inst, val: setattr(inst, "text_size", val))
    apply_btn = Button(
        text=S["MESSAGES"].get("APPLY_FILTERS_BUTTON", "Εφαρμογή"), size_hint_x=0.15
    )
    reset_btn = Button(text=S["BUTTONS"].get("CLEAR", "Καθαρισμός"), size_hint_x=0.15)
    header_row.add_widget(summary_label)
    header_row.add_widget(apply_btn)
    header_row.add_widget(reset_btn)
    main_layout.add_widget(header_row)

    scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
    charts_grid = GridLayout(cols=1, spacing=10, size_hint_y=None, padding=5)
    charts_grid.bind(minimum_height=charts_grid.setter("height"))
    scroll.add_widget(charts_grid)
    main_layout.add_widget(scroll)

    palette = [
        (0.16, 0.48, 0.72, 1),
        (0.87, 0.44, 0.20, 1),
        (0.28, 0.65, 0.33, 1),
        (0.70, 0.24, 0.30, 1),
        (0.55, 0.43, 0.75, 1),
        (0.86, 0.72, 0.20, 1),
    ]

    def _color_box(color_rgba, height=16, width=16):
        widget = Widget(size_hint=(None, None), size=(width, height))

        def _redraw(*_args):
            widget.canvas.clear()
            with widget.canvas:
                Color(*color_rgba)
                Rectangle(pos=widget.pos, size=widget.size)

        widget.bind(pos=_redraw, size=_redraw)
        _redraw()
        return widget

    def _make_pie_chart_section(title, items):
        if not items:
            return None
        container = BoxLayout(
            orientation="vertical", size_hint_y=None, spacing=6, padding=4
        )
        container.bind(minimum_height=container.setter("height"))
        container.add_widget(
            Label(
                text=f"[b]{title}[/b]",
                markup=True,
                size_hint_y=None,
                height=28,
                halign="left",
                valign="middle",
            )
        )

        legend = GridLayout(
            cols=2,
            spacing=(6, 4),
            size_hint=(None, None),
            padding=(0, 0, 0, 4),
        )
        legend.bind(minimum_width=legend.setter("width"))
        legend.bind(minimum_height=legend.setter("height"))
        legend.pos_hint = {"center_x": 0.5}
        container.add_widget(legend)

        body = BoxLayout(size_hint_y=None, height=260, spacing=10)
        chart_widget = Widget(size_hint_x=1.0)

        total = sum(value for _label, value in items) or 1

        def _draw_chart(*_args):
            import math

            from kivy.core.text import Label as CoreLabel

            def _prepare_text_block(lines):
                textures = []
                max_width = 0.0
                total_height = 0.0
                spacing = 2.0

                for text_line, font_size in lines:
                    core = CoreLabel(
                        text=str(text_line),
                        font_size=font_size,
                        color=(0.05, 0.05, 0.05, 1),
                    )
                    core.refresh()
                    texture = core.texture
                    if texture is None:
                        continue
                    width, height = texture.size
                    textures.append((texture, width, height))
                    max_width = max(max_width, width)
                    total_height += height

                if not textures:
                    return None

                total_height += spacing * max(0, len(textures) - 1)
                return {
                    "textures": textures,
                    "width": max_width,
                    "height": total_height,
                    "spacing": spacing,
                }

            def _clamp(value, minimum, maximum):
                return max(minimum, min(maximum, value))

            def _draw_label_block(x_pos, y_pos, prepared_block, align="left"):
                if not prepared_block:
                    return None

                max_width = prepared_block["width"]
                total_height = prepared_block["height"]
                bg_pos = (
                    x_pos - 4.0 if align == "left" else x_pos - max_width - 4.0,
                    y_pos - total_height / 2.0 - 3.0,
                )
                bg_size = (max_width + 8.0, total_height + 6.0)

                Color(1, 1, 1, 0.9)
                Rectangle(pos=bg_pos, size=bg_size)

                current_y = y_pos + total_height / 2.0
                for texture, width, height in prepared_block["textures"]:
                    current_y -= height
                    Color(0.05, 0.05, 0.05, 1)
                    if align == "left":
                        text_x = x_pos
                    else:
                        text_x = x_pos - width
                    Rectangle(
                        texture=texture,
                        pos=(text_x, current_y),
                        size=(width, height),
                    )
                    current_y -= prepared_block["spacing"]

                return (bg_pos[0], bg_pos[1], bg_size[0], bg_size[1])

            chart_widget.canvas.clear()
            with chart_widget.canvas:
                size = max(20.0, min(chart_widget.width, chart_widget.height) - 20.0)
                radius = size / 2.0
                center_x = chart_widget.x + chart_widget.width / 2.0
                center_y = chart_widget.y + chart_widget.height / 2.0
                start = 0.0
                label_candidates = []
                max_label_width = 0.0
                for index, (label, value) in enumerate(items):
                    angle = 360.0 * (float(value) / float(total))
                    slice_color = palette[index % len(palette)]
                    Color(*slice_color)
                    Ellipse(
                        pos=(center_x - radius, center_y - radius),
                        size=(size, size),
                        angle_start=start,
                        angle_end=start + angle,
                    )

                    share = float(value) / float(total)
                    prepared_block = _prepare_text_block([(label, 10), (value, 11)])
                    if prepared_block and share > 0.0:
                        max_label_width = max(
                            max_label_width, prepared_block["width"] + 8.0
                        )
                        mid_angle = start + angle / 2.0
                        direction = (
                            1.0 if math.cos(math.radians(mid_angle)) >= 0 else -1.0
                        )
                        anchor_radius = radius * 0.95
                        anchor_x = (
                            center_x + math.cos(math.radians(mid_angle)) * anchor_radius
                        )
                        anchor_y = (
                            center_y + math.sin(math.radians(mid_angle)) * anchor_radius
                        )
                        label_width = prepared_block["width"] + 8.0
                        label_height = prepared_block["height"] + 6.0
                        label_candidates.append(
                            {
                                "direction": direction,
                                "anchor": (anchor_x, anchor_y),
                                "label_width": label_width,
                                "label_height": label_height,
                                "desired_y": anchor_y,
                                "block": prepared_block,
                                "color": slice_color,
                            }
                        )
                    start += angle

                label_top = chart_widget.y + 10.0
                label_bottom = chart_widget.y + chart_widget.height - 10.0
                side_groups = {1.0: [], -1.0: []}
                for candidate in label_candidates:
                    side_groups[candidate["direction"]].append(candidate)

                for direction, candidates in side_groups.items():
                    if not candidates:
                        continue

                    candidates.sort(key=lambda entry: entry["desired_y"])
                    gap = 8.0
                    label_positions = []
                    for candidate in candidates:
                        half_height = candidate["label_height"] / 2.0
                        y_pos = _clamp(
                            candidate["desired_y"],
                            label_top + half_height,
                            label_bottom - half_height,
                        )
                        label_positions.append([candidate, y_pos])

                    for idx in range(1, len(label_positions)):
                        prev_candidate, prev_y = label_positions[idx - 1]
                        candidate, y_pos = label_positions[idx]
                        min_y = (
                            prev_y
                            + prev_candidate["label_height"] / 2.0
                            + candidate["label_height"] / 2.0
                            + gap
                        )
                        if y_pos < min_y:
                            label_positions[idx][1] = min_y

                    if label_positions:
                        last_candidate, last_y = label_positions[-1]
                        max_last_y = label_bottom - last_candidate["label_height"] / 2.0
                        if last_y > max_last_y:
                            label_positions[-1][1] = max_last_y

                    for idx in range(len(label_positions) - 2, -1, -1):
                        candidate, y_pos = label_positions[idx]
                        next_candidate, next_y = label_positions[idx + 1]
                        max_y = (
                            next_y
                            - next_candidate["label_height"] / 2.0
                            - candidate["label_height"] / 2.0
                            - gap
                        )
                        if y_pos > max_y:
                            label_positions[idx][1] = max_y

                    for idx in range(len(label_positions)):
                        candidate, y_pos = label_positions[idx]
                        half_height = candidate["label_height"] / 2.0
                        label_positions[idx][1] = _clamp(
                            y_pos,
                            label_top + half_height,
                            label_bottom - half_height,
                        )

                    side_gap = 48.0
                    safe_pad = 8.0
                    preferred = center_x + direction * (radius + side_gap)
                    if direction > 0:
                        label_x = _clamp(
                            preferred,
                            chart_widget.x + safe_pad,
                            chart_widget.x
                            + chart_widget.width
                            - safe_pad
                            - max_label_width,
                        )
                    else:
                        label_x = _clamp(
                            preferred,
                            chart_widget.x + safe_pad + max_label_width,
                            chart_widget.x + chart_widget.width - safe_pad,
                        )

                    elbow_x = center_x + direction * (radius + 14.0)

                    for candidate, y_pos in label_positions:
                        anchor_x, anchor_y = candidate["anchor"]
                        label_edge_x = label_x - 4.0 if direction > 0 else label_x + 4.0
                        min_tail = 22.0
                        if direction > 0:
                            line_mid_x = min(elbow_x, label_edge_x - min_tail)
                        else:
                            line_mid_x = max(elbow_x, label_edge_x + min_tail)
                        line_color = candidate["color"]
                        Color(
                            line_color[0] * 0.75,
                            line_color[1] * 0.75,
                            line_color[2] * 0.75,
                            1,
                        )
                        Line(
                            points=[
                                anchor_x,
                                anchor_y,
                                line_mid_x,
                                y_pos,
                                label_edge_x,
                                y_pos,
                            ],
                            width=1.0,
                        )
                        _draw_label_block(
                            label_x,
                            y_pos,
                            candidate["block"],
                            align="left" if direction > 0 else "right",
                        )
                Color(0.1, 0.1, 0.1, 1)
                Line(circle=(center_x, center_y, radius), width=1.2)

        chart_widget.bind(pos=_draw_chart, size=_draw_chart)
        _draw_chart()

        for index, (label, value) in enumerate(items):
            legend.add_widget(_color_box(palette[index % len(palette)]))
            legend.add_widget(
                Label(
                    text=f"{label}: {value}",
                    size_hint_x=None,
                    width=240,
                    halign="left",
                    valign="middle",
                    text_size=(240, None),
                )
            )

        body.add_widget(chart_widget)
        container.add_widget(body)
        return container

    def _make_bar_chart_section(title, items):
        if not items:
            return None
        container = BoxLayout(
            orientation="vertical", size_hint_y=None, spacing=6, padding=4
        )
        container.bind(minimum_height=container.setter("height"))
        container.add_widget(
            Label(
                text=f"[b]{title}[/b]",
                markup=True,
                size_hint_y=None,
                height=28,
                halign="left",
                valign="middle",
            )
        )

        max_value = max(value for _label, value in items) or 1
        for index, (label, value) in enumerate(items):
            row = BoxLayout(size_hint_y=None, height=26, spacing=6)
            row.add_widget(
                Label(text=label, size_hint_x=0.35, halign="left", valign="middle")
            )
            bar_widget = Widget(size_hint_x=0.55)

            def _draw_bar(
                widget=bar_widget, item_value=value, color=palette[index % len(palette)]
            ):
                def _redraw(*_args):
                    widget.canvas.clear()
                    with widget.canvas:
                        Color(0.90, 0.90, 0.90, 1)
                        Rectangle(pos=widget.pos, size=widget.size)
                        Color(*color)
                        width = widget.width * (float(item_value) / float(max_value))
                        Rectangle(pos=widget.pos, size=(width, widget.height))

                widget.bind(pos=_redraw, size=_redraw)
                _redraw()

            _draw_bar()
            row.add_widget(bar_widget)
            row.add_widget(
                Label(
                    text=str(value), size_hint_x=0.10, halign="right", valign="middle"
                )
            )
            container.add_widget(row)
        return container

    def _render_statistics(stats_payload=None):
        charts_grid.clear_widgets()
        stats_payload = stats_payload or {"rows_count": 0, "pies": {}, "bars": {}}
        summary_label.text = (
            f"Στοιχεία στο σύνολο: {stats_payload.get('rows_count', 0)}"
        )

        pie_titles = [
            ("types_hv_breakers", "Τύποι Διακοπτών ΥΤ"),
            ("types_mv_breakers", "Τύποι Διακοπτών ΜΤ"),
            ("age_transformers", "Ηλικία Μετασχηματιστών"),
            ("age_hv_breakers", "Ηλικία Διακοπτών ΥΤ"),
            ("age_mv_breakers", "Ηλικία Διακοπτών ΜΤ"),
        ]
        for key, title in pie_titles:
            section = _make_pie_chart_section(
                title, (stats_payload.get("pies") or {}).get(key) or []
            )
            if section is not None:
                charts_grid.add_widget(section)

        for category, items in (
            (stats_payload.get("bars") or {}).get("manufacturer_count_models") or {}
        ).items():
            manufacturer_section = _make_bar_chart_section(
                f"Κατασκευαστές Μοντέλων - {category}",
                items,
            )
            if manufacturer_section is not None:
                charts_grid.add_widget(manufacturer_section)

        for category, items in (
            (stats_payload.get("bars") or {}).get("most_used_models_per_category") or {}
        ).items():
            section = _make_bar_chart_section(
                f"Πιο χρησιμοποιημένα μοντέλα - {category}", items
            )
            if section is not None:
                charts_grid.add_widget(section)

        if not charts_grid.children:
            charts_grid.add_widget(
                Label(
                    text=S["MESSAGES"].get(
                        "NO_STATS_RESULTS",
                        "Δεν υπάρχουν δεδομένα για τα επιλεγμένα φίλτρα.",
                    ),
                    size_hint_y=None,
                    height=40,
                )
            )

    def _apply_filters(*_args):
        distance_limit = _parse_distance_filter_value(distance_spinner.text)
        if distance_relation_spinner.text != all_option and distance_limit is None:
            show_message_popup(
                S["TITLES"].get("ERROR", "Σφάλμα"),
                S["MESSAGES"].get(
                    "DISTANCE_FILTER_REQUIRED", "Επιλέξτε όριο απόστασης."
                ),
            )
            return

        stats_payload = get_model_management_statistics(
            app_instance,
            include_inactive=bool(include_inactive_checkbox.active),
            distance_relation=distance_relation_spinner.text,
            distance_limit_km=distance_limit,
            element_scope=scope_spinner.text,
        )
        _render_statistics(stats_payload)

    def _reset_filters(*_args):
        scope_spinner.text = all_option
        distance_relation_spinner.text = all_option
        distance_spinner.text = all_option
        include_inactive_checkbox.active = False
        _apply_filters()

    apply_btn.bind(on_press=_apply_filters)
    reset_btn.bind(on_press=_reset_filters)

    close_btn = Button(
        text=S["BUTTONS"].get("CLOSE", "Κλείσιμο"), size_hint_y=None, height=42
    )
    close_btn.bind(on_press=popup.dismiss)
    main_layout.add_widget(close_btn)

    popup.content = main_layout
    _apply_filters()
    popup.open()


def show_element_search_popup(app_instance, parent_popup=None):
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.gridlayout import GridLayout
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.spinner import Spinner
    from kivy.uix.textinput import TextInput
    from kivy.uix.checkbox import CheckBox

    popup = Popup(
        title=S["MESSAGES"].get("ELEMENT_SEARCH_TITLE", "Αναζήτηση Στοιχείων"),
        size_hint=(0.96, 0.92),
    )
    main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    c = app_instance.conn.cursor()
    c.execute("SELECT MAX(base_distance_km) FROM substations")
    max_distance = (c.fetchone() or [None])[0]
    all_option = S["MESSAGES"].get("ALL_OPTION", "(Όλα)")
    all_breakers_label = S["MESSAGES"].get("ALL_BREAKERS_OPTION", "Όλοι οι Διακόπτες")

    filter_grid = GridLayout(cols=2, spacing=8, size_hint_y=None, padding=4)
    filter_grid.bind(minimum_height=filter_grid.setter("height"))

    filter_grid.add_widget(
        Label(
            text=S["MESSAGES"].get("FILTER_TYPE_LABEL", "Τύπος Στοιχείου:"),
            size_hint_y=None,
            height=32,
        )
    )
    element_type_spinner = Spinner(
        text=all_option,
        values=_element_type_filter_options(app_instance, app_instance.conn),
        size_hint_y=None,
        height=36,
    )
    filter_grid.add_widget(element_type_spinner)

    filter_grid.add_widget(
        Label(
            text=S["MESSAGES"].get("BREAKER_CATEGORY_LABEL", "Κατηγορία Διακόπτη:"),
            size_hint_y=None,
            height=32,
        )
    )
    breaker_category_spinner = Spinner(
        text=all_option,
        values=[all_option] + list(getattr(app_instance, "BREAKER_CATEGORIES_ALL", [])),
        size_hint_y=None,
        height=36,
        disabled=True,
    )
    filter_grid.add_widget(breaker_category_spinner)

    filter_grid.add_widget(
        Label(
            text=S["MESSAGES"].get("BREAKER_ROLE_FILTER_LABEL", "Τύπος Διακόπτη:"),
            size_hint_y=None,
            height=32,
        )
    )
    breaker_role_spinner = Spinner(
        text=all_option,
        values=_get_breaker_role_options(),
        size_hint_y=None,
        height=36,
        disabled=True,
    )
    filter_grid.add_widget(breaker_role_spinner)

    filter_grid.add_widget(
        Label(
            text=S["MESSAGES"].get("ELEMENT_YEAR_FILTER_LABEL", "Έτος κατασκευής:"),
            size_hint_y=None,
            height=32,
        )
    )
    year_box = BoxLayout(size_hint_y=None, height=36, spacing=6)
    year_relation_spinner = Spinner(
        text=all_option,
        values=[
            all_option,
            S["MESSAGES"].get("OLDER_THAN_YEAR_LABEL", "Παλαιότερα από"),
            S["MESSAGES"].get("YOUNGER_THAN_YEAR_LABEL", "Νεότερα ή ίσα με"),
        ],
        size_hint_x=0.62,
    )
    year_input = TextInput(hint_text="YYYY", multiline=False, size_hint_x=0.38)
    year_box.add_widget(year_relation_spinner)
    year_box.add_widget(year_input)
    filter_grid.add_widget(year_box)

    filter_grid.add_widget(
        Label(
            text=S["MESSAGES"].get("DISTANCE_FILTER_LABEL", "Απόσταση από βάση:"),
            size_hint_y=None,
            height=32,
        )
    )
    distance_box = BoxLayout(size_hint_y=None, height=36, spacing=6)
    distance_relation_spinner = Spinner(
        text=all_option,
        values=[
            all_option,
            S["MESSAGES"].get("DISTANCE_SMALLER_THAN_LABEL", "Μικρότερη από"),
            S["MESSAGES"].get("DISTANCE_GREATER_THAN_LABEL", "Μεγαλύτερη από"),
        ],
        size_hint_x=0.48,
    )
    distance_spinner = Spinner(
        text=all_option,
        values=_build_distance_filter_values(max_distance),
        size_hint_x=0.52,
    )
    distance_box.add_widget(distance_relation_spinner)
    distance_box.add_widget(distance_spinner)
    filter_grid.add_widget(distance_box)

    filter_grid.add_widget(
        Label(
            text=S["MESSAGES"].get("SORT_RESULTS_LABEL", "Ταξινόμηση:"),
            size_hint_y=None,
            height=32,
        )
    )
    sort_spinner = Spinner(
        text=S["MESSAGES"].get("SORT_DISTANCE_DESC", "Μακρινότερα -> Κοντινότερα"),
        values=[
            S["MESSAGES"].get("SORT_DISTANCE_DESC", "Μακρινότερα -> Κοντινότερα"),
            S["MESSAGES"].get("SORT_DISTANCE_ASC", "Κοντινότερα -> Μακρινότερα"),
            S["MESSAGES"].get("SORT_SUBSTATION_ASC", "Υποσταθμός Α-Ω"),
        ],
        size_hint_y=None,
        height=36,
    )
    filter_grid.add_widget(sort_spinner)

    filter_grid.add_widget(
        Label(
            text=S["MESSAGES"].get("SHOW_INACTIVE_ELEMENTS", "Εμφάνιση ανενεργών"),
            size_hint_y=None,
            height=32,
        )
    )
    inactive_box = BoxLayout(size_hint_y=None, height=36, spacing=6)
    include_inactive_checkbox = CheckBox(
        active=False, size_hint=(None, None), size=(28, 28)
    )
    inactive_box.add_widget(include_inactive_checkbox)
    inactive_box.add_widget(
        Label(
            text=S["MESSAGES"].get(
                "INACTIVE_RESULTS_NOTE", "Προβολή και ανενεργών στοιχείων"
            ),
            halign="left",
            valign="middle",
        )
    )
    filter_grid.add_widget(inactive_box)

    main_layout.add_widget(filter_grid)

    action_row = BoxLayout(size_hint_y=None, height=42, spacing=8)
    results_summary = Label(text="", size_hint_x=0.68, halign="left", valign="middle")
    results_summary.bind(size=lambda inst, val: setattr(inst, "text_size", val))
    search_btn = Button(
        text=S["MESSAGES"].get("SEARCH_BUTTON", "Αναζήτηση"), size_hint_x=0.16
    )
    reset_btn = Button(text=S["BUTTONS"].get("CLEAR", "Καθαρισμός"), size_hint_x=0.16)
    action_row.add_widget(results_summary)
    action_row.add_widget(search_btn)
    action_row.add_widget(reset_btn)
    main_layout.add_widget(action_row)

    scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
    results_grid = GridLayout(cols=1, spacing=5, size_hint_y=None, padding=5)
    results_grid.bind(minimum_height=results_grid.setter("height"))
    scroll.add_widget(results_grid)
    main_layout.add_widget(scroll)

    def _refresh_breaker_filters(*_args):
        selected_type = element_type_spinner.text
        breaker_enabled = selected_type in {
            all_breakers_label,
            ELEM_BREAKER_MT,
            ELEM_BREAKER_YT,
        }
        breaker_category_spinner.disabled = not breaker_enabled
        breaker_role_spinner.disabled = not breaker_enabled
        if not breaker_enabled:
            breaker_category_spinner.text = all_option
            breaker_role_spinner.text = all_option
            return
        if selected_type == ELEM_BREAKER_MT:
            categories = app_instance._get_breaker_categories_for_element_type(
                ELEM_BREAKER_MT
            )
        elif selected_type == ELEM_BREAKER_YT:
            categories = app_instance._get_breaker_categories_for_element_type(
                ELEM_BREAKER_YT
            )
        else:
            categories = list(getattr(app_instance, "BREAKER_CATEGORIES_ALL", []))
        breaker_category_spinner.values = [all_option] + list(categories)
        if breaker_category_spinner.text not in breaker_category_spinner.values:
            breaker_category_spinner.text = all_option

    def _add_element_result(elem_data, is_inactive=False):
        (
            _elem_id,
            elem_type,
            elem_name,
            serial_number,
            maintenance_date,
            manufacturer,
            installation_space,
            operating_status,
            maintenance_cycle,
            breaker_category,
            manufacture_year,
            _substation_name,
            _substation_id,
            _base_distance_km,
            is_main_switch,
        ) = elem_data

        elem_box = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=88,
            spacing=4,
            padding=(12, 0, 0, 0),
        )

        status_text = " [color=ff0000][b]ΑΝΕΝΕΡΓΟ[/b][/color]" if is_inactive else ""
        display_type = app_instance._format_elem_type(elem_type, is_main_switch)
        title_text = f"[b][size=16]{elem_name}[/size][/b] - {display_type}{status_text}"
        if breaker_category:
            title_text += f" | {breaker_category}"
        title_label = Label(
            text=title_text,
            markup=True,
            size_hint_y=None,
            height=24,
            halign="left",
            valign="middle",
        )
        title_label.bind(size=title_label.setter("text_size"))
        elem_box.add_widget(title_label)

        info_bits = [f"S/N: {serial_number or '-'}"]
        if manufacture_year:
            info_bits.append(f"Έτος: {manufacture_year}")
        info_label = Label(
            text=" | ".join(info_bits),
            size_hint_y=None,
            height=20,
            halign="left",
            valign="middle",
        )
        info_label.bind(size=info_label.setter("text_size"))
        elem_box.add_widget(info_label)

        details_label = Label(
            text=(
                f"Κατ.: {manufacturer or '-'} | Χώρος: {installation_space or '-'} | "
                f"Κατάστ.: {operating_status or '-'} | Κύκλος: {maintenance_cycle or '-'} | "
                f"Τελ. Συντ.: {maintenance_date or '-'}"
            ),
            size_hint_y=None,
            height=20,
            halign="left",
            valign="middle",
        )
        details_label.bind(size=details_label.setter("text_size"))
        elem_box.add_widget(details_label)
        results_grid.add_widget(elem_box)

    def _render_results(result_rows, search_executed=True):
        results_grid.clear_widgets()
        if not result_rows:
            message = (
                S["MESSAGES"].get(
                    "SEARCH_PROMPT", "Ορίστε φίλτρα και πατήστε Αναζήτηση."
                )
                if not search_executed
                else S["MESSAGES"].get(
                    "NO_SEARCH_RESULTS", "Δεν βρέθηκαν στοιχεία με αυτά τα φίλτρα."
                )
            )
            results_summary.text = message
            results_grid.add_widget(Label(text=message, size_hint_y=None, height=40))
            return

        groups = {}
        order = []
        for row in result_rows:
            substation_name = row[11]
            substation_id = row[12]
            base_distance_km = row[13]
            operating_status = (row[7] or "").strip()
            is_inactive = operating_status == "Ανενεργή"
            if substation_name not in groups:
                groups[substation_name] = {
                    "id": substation_id,
                    "distance": base_distance_km,
                    "active": [],
                    "inactive": [],
                }
                order.append(substation_name)
            groups[substation_name]["inactive" if is_inactive else "active"].append(row)

        results_summary.text = (
            f"{len(result_rows)} στοιχεία σε {len(groups)} υποσταθμούς"
        )

        for substation_name in order:
            group = groups[substation_name]
            total_count = len(group["active"]) + len(group["inactive"])
            distance_text = (
                f"{float(group['distance']):.1f} km"
                if group.get("distance") not in (None, "")
                else "-"
            )

            header_row = BoxLayout(size_hint_y=None, height=40, spacing=10)
            header_label = Label(
                text=f"[b][size=18]{substation_name} ({total_count}) | {distance_text}[/size][/b]",
                markup=True,
                size_hint_x=0.75,
                halign="left",
                valign="middle",
            )
            header_label.bind(size=header_label.setter("text_size"))
            header_row.add_widget(header_label)

            jump_btn = Button(
                text=S["MESSAGES"].get("GO_TO_SUBSTATION", "Μετάβαση στον Υποσταθμό"),
                size_hint_x=0.25,
            )
            jump_btn.bind(
                on_press=lambda _x, sname=substation_name, p=popup: jump_to_substation(
                    app_instance, sname, p
                )
            )
            header_row.add_widget(jump_btn)
            results_grid.add_widget(header_row)

            for row in group["active"]:
                _add_element_result(row, False)
            if group["inactive"]:
                inactive_label = Label(
                    text=f"[b][color=ff0000]Ανενεργά ({len(group['inactive'])})[/color][/b]",
                    markup=True,
                    size_hint_y=None,
                    height=28,
                    halign="left",
                    valign="middle",
                )
                inactive_label.bind(size=inactive_label.setter("text_size"))
                results_grid.add_widget(inactive_label)
                for row in group["inactive"]:
                    _add_element_result(row, True)

    def _run_search(*_args):
        year_value = _safe_int(year_input.text)
        if year_relation_spinner.text != all_option and year_value is None:
            show_message_popup(
                S["TITLES"].get("ERROR", "Σφάλμα"),
                S["MESSAGES"].get("ELEMENT_MANUFACTURE_YEAR_HINT", "YYYY"),
            )
            return

        distance_limit = _parse_distance_filter_value(distance_spinner.text)
        if distance_relation_spinner.text != all_option and distance_limit is None:
            show_message_popup(
                S["TITLES"].get("ERROR", "Σφάλμα"),
                S["MESSAGES"].get(
                    "DISTANCE_FILTER_REQUIRED", "Επιλέξτε όριο απόστασης."
                ),
            )
            return

        has_meaningful_filter = any(
            [
                element_type_spinner.text != all_option,
                breaker_category_spinner.text != all_option,
                breaker_role_spinner.text != all_option,
                year_relation_spinner.text != all_option and year_value is not None,
                distance_relation_spinner.text != all_option
                and distance_limit is not None,
                include_inactive_checkbox.active,
            ]
        )
        if not has_meaningful_filter:
            show_message_popup(
                S["TITLES"].get("ERROR", "Σφάλμα"),
                S["MESSAGES"].get(
                    "ELEMENT_SEARCH_FILTER_REQUIRED",
                    "Επιλέξτε τουλάχιστον ένα φίλτρο πριν την αναζήτηση.",
                ),
            )
            return

        sort_map = {
            S["MESSAGES"].get(
                "SORT_DISTANCE_DESC", "Μακρινότερα -> Κοντινότερα"
            ): "distance_desc",
            S["MESSAGES"].get(
                "SORT_DISTANCE_ASC", "Κοντινότερα -> Μακρινότερα"
            ): "distance_asc",
            S["MESSAGES"].get(
                "SORT_SUBSTATION_ASC", "Υποσταθμός Α-Ω"
            ): "substation_asc",
        }
        rows = search_elements(
            app_instance,
            element_type_filter=element_type_spinner.text,
            breaker_category_filter=breaker_category_spinner.text,
            breaker_role_filter=breaker_role_spinner.text,
            year_relation=year_relation_spinner.text,
            reference_year=year_value,
            distance_relation=distance_relation_spinner.text,
            distance_limit_km=distance_limit,
            sort_direction=sort_map.get(sort_spinner.text, "distance_desc"),
            include_inactive=bool(include_inactive_checkbox.active),
        )
        _render_results(rows, search_executed=True)

    def _reset_filters(*_args):
        element_type_spinner.text = all_option
        breaker_category_spinner.text = all_option
        breaker_role_spinner.text = all_option
        year_relation_spinner.text = all_option
        year_input.text = ""
        distance_relation_spinner.text = all_option
        distance_spinner.text = all_option
        include_inactive_checkbox.active = False
        sort_spinner.text = S["MESSAGES"].get(
            "SORT_DISTANCE_DESC", "Μακρινότερα -> Κοντινότερα"
        )
        _refresh_breaker_filters()
        _render_results([], search_executed=False)

    element_type_spinner.bind(text=lambda *_args: _refresh_breaker_filters())
    search_btn.bind(on_press=_run_search)
    reset_btn.bind(on_press=_reset_filters)

    close_btn = Button(
        text=S["BUTTONS"].get("CLOSE", "Κλείσιμο"), size_hint_y=None, height=42
    )
    close_btn.bind(on_press=popup.dismiss)
    main_layout.add_widget(close_btn)

    popup.content = main_layout
    _refresh_breaker_filters()
    _render_results([], search_executed=False)
    popup.open()


HV_BREAKER_MODEL_FIELD_DEFS = [
    {
        "key": "rated_normal_current_a",
        "label_key": "MODEL_RATED_NORMAL_CURRENT_A_LABEL",
        "hint_key": "MODEL_RATED_NORMAL_CURRENT_A_HINT",
        "default_label": "Ονομ. Ρεύμα (A):",
        "default_hint": "π.χ. 1250",
        "numeric": True,
    },
    {
        "key": "rated_short_circuit_breaking_current_ka",
        "label_key": "MODEL_RATED_SHORT_CIRCUIT_BREAKING_CURRENT_KA_LABEL",
        "hint_key": "MODEL_RATED_SHORT_CIRCUIT_BREAKING_CURRENT_KA_HINT",
        "default_label": "Ρεύμα Διακοπής Βραχ. Κυκλ. (kA):",
        "default_hint": "π.χ. 40",
        "numeric": True,
    },
    {
        "key": "short_circuit_duration_s",
        "label_key": "MODEL_SHORT_CIRCUIT_DURATION_S_LABEL",
        "hint_key": "MODEL_SHORT_CIRCUIT_DURATION_S_HINT",
        "default_label": "Διάρκεια Βραχ. Κυκλ. (s):",
        "default_hint": "π.χ. 3",
        "numeric": True,
    },
    {
        "key": "making_capacity_ka",
        "label_key": "MODEL_MAKING_CAPACITY_KA_LABEL",
        "hint_key": "MODEL_MAKING_CAPACITY_KA_HINT",
        "default_label": "Ικανότητα Ζεύξης (kA):",
        "default_hint": "π.χ. 100",
        "numeric": True,
    },
    {
        "key": "sf6_pressure_rated_bar",
        "label_key": "MODEL_SF6_PRESSURE_RATED_BAR_LABEL",
        "hint_key": "MODEL_SF6_PRESSURE_RATED_BAR_HINT",
        "default_label": "Ονομ. Πίεση SF6 (bar):",
        "default_hint": "π.χ. 6.0",
        "numeric": True,
    },
    {
        "key": "total_weight_kg",
        "label_key": "MODEL_TOTAL_WEIGHT_KG_LABEL",
        "hint_key": "MODEL_TOTAL_WEIGHT_KG_HINT",
        "default_label": "Συνολικό Βάρος (kg):",
        "default_hint": "π.χ. 1320",
        "numeric": True,
    },
    {
        "key": "drive_mechanism",
        "label_key": "MODEL_DRIVE_MECHANISM_LABEL",
        "hint_key": "MODEL_DRIVE_MECHANISM_HINT",
        "default_label": "Μηχανισμός Κίνησης:",
        "default_hint": "π.χ. FK 3-1",
        "numeric": False,
    },
]

MV_BREAKER_MODEL_FIELD_DEFS = [
    {
        "key": "rated_normal_current_a",
        "label_key": "MODEL_RATED_NORMAL_CURRENT_A_LABEL",
        "hint_key": "MODEL_RATED_NORMAL_CURRENT_A_HINT",
        "default_label": "Ονομ. Ρεύμα (A):",
        "default_hint": "π.χ. 1250",
        "numeric": True,
    },
    {
        "key": "rated_short_circuit_breaking_current_ka",
        "label_key": "MODEL_RATED_SHORT_CIRCUIT_BREAKING_CURRENT_KA_LABEL",
        "hint_key": "MODEL_RATED_SHORT_CIRCUIT_BREAKING_CURRENT_KA_HINT",
        "default_label": "Ρεύμα Διακοπής Βραχ. Κυκλ. (kA):",
        "default_hint": "π.χ. 25",
        "numeric": True,
    },
    {
        "key": "short_circuit_duration_s",
        "label_key": "MODEL_SHORT_CIRCUIT_DURATION_S_LABEL",
        "hint_key": "MODEL_SHORT_CIRCUIT_DURATION_S_HINT",
        "default_label": "Διάρκεια Βραχ. Κυκλ. (s):",
        "default_hint": "π.χ. 3",
        "numeric": True,
    },
    {
        "key": "rated_short_circuit_making_current_ka",
        "label_key": "MODEL_RATED_SHORT_CIRCUIT_MAKING_CURRENT_KA_LABEL",
        "hint_key": "MODEL_RATED_SHORT_CIRCUIT_MAKING_CURRENT_KA_HINT",
        "default_label": "Ρεύμα Ζεύξης Βραχ. Κυκλ. (kA):",
        "default_hint": "π.χ. 40",
        "numeric": True,
    },
    {
        "key": "cubicle",
        "label_key": "MODEL_CUBICLE_LABEL",
        "hint_key": "MODEL_CUBICLE_HINT",
        "default_label": "Κυψέλη:",
        "default_hint": "π.χ. 23",
        "numeric": False,
    },
    {
        "key": "total_weight_kg",
        "label_key": "MODEL_TOTAL_WEIGHT_KG_LABEL",
        "hint_key": "MODEL_TOTAL_WEIGHT_KG_HINT",
        "default_label": "Συνολικό Βάρος (kg):",
        "default_hint": "π.χ. 55",
        "numeric": True,
    },
]

MOTOR_DRIVE_MODEL_FIELD_DEFS = [
    {
        "key": "drive_mechanism",
        "label_key": "MODEL_DRIVE_MECHANISM_LABEL",
        "hint_key": "MODEL_DRIVE_MECHANISM_HINT",
        "default_label": "Μηχανισμός Κίνησης:",
        "default_hint": "π.χ. RS9-I-400-150/N-10 19 3W",
        "numeric": False,
    }
]


def _is_transformer_model_category(category):
    return TRANSFORMER_CATEGORY_TOKEN in str(category or "")


def _get_model_extra_field_defs(category):
    if category == ELEM_BREAKER_YT:
        return HV_BREAKER_MODEL_FIELD_DEFS
    if category == ELEM_BREAKER_MT:
        return MV_BREAKER_MODEL_FIELD_DEFS
    if category == MOTOR_DRIVE_CATEGORY:
        return MOTOR_DRIVE_MODEL_FIELD_DEFS
    if _is_transformer_model_category(category):
        return TRANSFORMER_MODEL_FIELD_DEFS
    return []


def _label_for_field(field_def):
    return S.get("MESSAGES", {}).get(field_def["label_key"], field_def["default_label"])


def _hint_for_field(field_def):
    return S.get("MESSAGES", {}).get(field_def["hint_key"], field_def["default_hint"])


def _numeric_error_for_field(field_def):
    field_name = _label_for_field(field_def).rstrip(":")
    return (
        S.get("MESSAGES", {})
        .get("MODEL_FIELD_NUM_FMT", "Field {field} must be a number!")
        .format(field=field_name)
    )


def _apply_breaker_model_defaults(category, model_name, extra_values, power_val):
    if category not in {ELEM_BREAKER_YT, ELEM_BREAKER_MT}:
        return extra_values, power_val

    effective_current, calculated_power = infer_breaker_model_values(
        category,
        model_name,
        extra_values.get("rated_normal_current_a"),
    )
    if effective_current is not None:
        extra_values["rated_normal_current_a"] = effective_current
    if calculated_power is not None:
        power_val = calculated_power
    return extra_values, power_val


def _build_model_extra_inputs(container, category, input_map, initial_values=None):
    from kivy.uix.label import Label
    from kivy.uix.textinput import TextInput

    initial_values = initial_values or {}
    container.clear_widgets()
    input_map.clear()

    for field_def in _get_model_extra_field_defs(category):
        container.add_widget(
            Label(text=_label_for_field(field_def), size_hint_y=None, height=30)
        )
        raw_value = initial_values.get(field_def["key"])
        container_input = TextInput(
            text="" if raw_value is None else str(raw_value),
            hint_text=_hint_for_field(field_def),
            size_hint_y=None,
            height=40,
            multiline=False,
        )
        input_map[field_def["key"]] = container_input
        container.add_widget(container_input)


def _collect_model_extra_values(category, input_map):
    values = {}
    for field_def in _get_model_extra_field_defs(category):
        widget = input_map.get(field_def["key"])
        raw_text = (widget.text if widget else "").strip()
        if not raw_text:
            values[field_def["key"]] = None
            continue
        if field_def["numeric"]:
            try:
                values[field_def["key"]] = float(raw_text.replace(",", "."))
            except ValueError as exc:
                raise ValueError(_numeric_error_for_field(field_def)) from exc
        else:
            values[field_def["key"]] = raw_text
    return values


def show_models_management(app_instance):
    """Show model management interface"""
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.gridlayout import GridLayout
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.spinner import Spinner

    c = app_instance.conn.cursor()
    c.execute(
        "SELECT id, element_category, model_name, manufacturer, maintenance_cycle, installation_space, breaker_category, manual_pdf, power_mva, onedrive_manual_link FROM element_models ORDER BY element_category, model_name"
    )
    models = c.fetchall()

    popup = Popup(
        title=S["TITLES"].get("MODELS_MANAGEMENT", "Διαχείριση Τύπων Στοιχείων"),
        size_hint=(0.95, 0.9),
    )
    main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    action_row = BoxLayout(size_hint_y=None, height=44, spacing=8)
    add_btn = Button(
        text=S["BUTTONS"].get("ADD_MODEL", "+ Προσθήκη Νέου Μοντέλου"),
        size_hint_x=0.34,
    )
    add_btn.bind(on_press=lambda x: show_add_model_popup(app_instance, popup))
    action_row.add_widget(add_btn)

    search_btn = Button(
        text=S["MESSAGES"].get("SEARCH_ELEMENTS_BUTTON", "Αναζήτηση Στοιχείων"),
        size_hint_x=0.33,
    )
    search_btn.bind(on_press=lambda _x: show_element_search_popup(app_instance, popup))
    action_row.add_widget(search_btn)

    stats_btn = Button(
        text=S["MESSAGES"].get("MODEL_STATS_BUTTON", "Στατιστικά"),
        size_hint_x=0.33,
    )
    stats_btn.bind(on_press=lambda _x: show_model_statistics_popup(app_instance, popup))
    action_row.add_widget(stats_btn)
    main_layout.add_widget(action_row)

    # Filter by element type
    available_categories = [row[1] for row in models]
    ordered_categories = []
    for cat in getattr(app_instance, "MODEL_CATEGORIES", app_instance.ELEMENT_TYPES):
        if cat in available_categories and cat not in ordered_categories:
            ordered_categories.append(cat)
    for cat in available_categories:
        if cat not in ordered_categories:
            ordered_categories.append(cat)
    filter_values = [S["MESSAGES"].get("ALL_OPTION", "(Όλα)")] + ordered_categories

    filter_bar = BoxLayout(size_hint_y=None, height=40, spacing=10)
    filter_bar.add_widget(
        Label(
            text=S["MESSAGES"].get("FILTER_TYPE_LABEL", "Φίλτρο Τύπου:"),
            size_hint_x=0.25,
        )
    )
    filter_spinner = Spinner(
        text=S["MESSAGES"].get("ALL_OPTION", "(Όλα)"),
        values=filter_values,
        size_hint_x=0.75,
    )
    filter_bar.add_widget(filter_spinner)
    main_layout.add_widget(filter_bar)

    # Models list
    scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
    grid = GridLayout(cols=1, spacing=5, size_hint_y=None, padding=5)
    grid.bind(minimum_height=grid.setter("height"))

    def render_models(selected_category):
        grid.clear_widgets()
        filtered_models = models
        if selected_category and selected_category != S["MESSAGES"].get(
            "ALL_OPTION", "(Όλα)"
        ):
            filtered_models = [m for m in models if m[1] == selected_category]

        if filtered_models:
            # Categorize models by element type - use dynamic categorization
            from collections import OrderedDict

            categories = OrderedDict()

            # Define priority order for common categories
            priority_categories = [
                ELEM_BREAKER_MT,
                ELEM_BREAKER_YT,
                "Μετασχηματιστής 150/20KV",
                "Motor Drive",
            ]

            # Initialize priority categories
            for cat in priority_categories:
                categories[cat] = []

            # Group models by their actual category
            for model in filtered_models:
                (
                    model_id,
                    category,
                    model_name,
                    manufacturer,
                    cycle,
                    space,
                    breaker_cat,
                    manual_pdf,
                    power_mva,
                    onedrive_manual_link,
                ) = model
                if category not in categories:
                    categories[category] = []
                categories[category].append(model)

            # Display categories with models
            for category_name, category_models in categories.items():
                if category_models:
                    # Category header
                    category_label = Label(
                        text=f"[b][size=20]{category_name}[/size][/b] ({len(category_models)})",
                        size_hint_y=None,
                        height=40,
                        bold=True,
                        markup=True,
                    )
                    grid.add_widget(category_label)

                    # For MV and HV breakers, group by breaker category (SF6, Κενού, etc.)
                    if category_name in [ELEM_BREAKER_MT, ELEM_BREAKER_YT]:
                        # Group by breaker category
                        breaker_groups = OrderedDict()
                        breaker_order = (
                            app_instance._get_breaker_categories_for_element_type(
                                category_name
                            )
                        )

                        # Initialize ordered groups
                        for breaker_type in breaker_order:
                            breaker_groups[breaker_type] = []
                        breaker_groups[
                            S["MESSAGES"].get("OTHER_LABEL", "Άλλο")
                        ] = []  # For uncategorized

                        # Sort models into breaker groups
                        for model in category_models:
                            (
                                model_id,
                                category,
                                model_name,
                                manufacturer,
                                cycle,
                                space,
                                breaker_cat,
                                manual_pdf,
                                power_mva,
                                onedrive_manual_link,
                            ) = model
                            assigned = False
                            if breaker_cat:
                                bval = str(breaker_cat).strip()
                                # Exact case-insensitive match
                                for key in list(breaker_groups.keys()):
                                    try:
                                        if key and bval.lower() == str(key).lower():
                                            breaker_groups[key].append(model)
                                            assigned = True
                                            break
                                    except Exception:
                                        continue
                                # Try normalized alphanumeric match (e.g., 'SF6' vs 'SF 6')
                                if not assigned:

                                    def _norm(s):
                                        return "".join(
                                            ch for ch in str(s).lower() if ch.isalnum()
                                        )

                                    nb = _norm(bval)
                                    for key in list(breaker_groups.keys()):
                                        try:
                                            if key and nb == _norm(key):
                                                breaker_groups[key].append(model)
                                                assigned = True
                                                break
                                        except Exception:
                                            continue
                            if not assigned:
                                breaker_groups[
                                    S["MESSAGES"].get("OTHER_LABEL", "Άλλο")
                                ].append(model)

                        # Display each breaker type group
                        for breaker_type, breaker_models in breaker_groups.items():
                            if breaker_models:
                                # Breaker type subheader
                                breaker_header = Label(
                                    text=f"  [b]{breaker_type}[/b] ({len(breaker_models)})",
                                    size_hint_y=None,
                                    height=35,
                                    markup=True,
                                    color=(0.3, 0.7, 1, 1),
                                )
                                grid.add_widget(breaker_header)

                                # Display models in this breaker group
                                for (
                                    model_id,
                                    category,
                                    model_name,
                                    manufacturer,
                                    cycle,
                                    space,
                                    breaker_cat,
                                    manual_pdf,
                                    power_mva,
                                    onedrive_manual_link,
                                ) in breaker_models:
                                    model_box = BoxLayout(
                                        size_hint_y=None,
                                        height=80,
                                        spacing=5,
                                        orientation="vertical",
                                    )

                                    # Header
                                    header = BoxLayout(
                                        size_hint_y=None, height=30, spacing=5
                                    )
                                    try:
                                        c.execute(
                                            "SELECT COUNT(*) FROM elements WHERE element_model_id=?",
                                            (model_id,),
                                        )
                                        usage_count = c.fetchone()[0] or 0
                                    except Exception:
                                        usage_count = 0

                                    header.add_widget(
                                        Label(
                                            text=f"    {model_name} ({usage_count})",
                                            bold=True,
                                            size_hint_x=0.55,
                                        )
                                    )

                                    # Buttons
                                    btn_box = BoxLayout(size_hint_x=0.45, spacing=5)

                                    list_btn = Button(
                                        text=S["BUTTONS"]["LIST"], size_hint_x=0.25
                                    )
                                    list_btn.bind(
                                        on_press=lambda x, mid=model_id, mname=model_name: (
                                            show_model_usages(app_instance, mid, mname)
                                        )
                                    )
                                    btn_box.add_widget(list_btn)

                                    manual_label = (
                                        S["MESSAGES"].get("MANUAL_LABEL", "Manual")
                                        if (manual_pdf and os.path.exists(manual_pdf))
                                        or onedrive_manual_link
                                        else S["MESSAGES"].get(
                                            "ADD_MANUAL", "Προσθήκη Manual"
                                        )
                                    )
                                    manual_btn = Button(
                                        text=manual_label, size_hint_x=0.25
                                    )
                                    manual_btn.bind(
                                        on_press=lambda x, mid=model_id, path=manual_pdf, link=onedrive_manual_link, p=popup: (
                                            _handle_manual_pdf(
                                                app_instance, mid, path, link, p
                                            )
                                        )
                                    )
                                    btn_box.add_widget(manual_btn)

                                    edit_btn = IconOnlyButton(
                                        icon_type="edit",
                                        icon_color=(0.2, 0.6, 1, 1),
                                        size=(45, 45),
                                    )
                                    edit_btn.bind(
                                        on_press=lambda x, mid=model_id: (
                                            show_edit_model_popup(
                                                app_instance, mid, popup
                                            )
                                        )
                                    )
                                    btn_box.add_widget(edit_btn)

                                    delete_btn = IconOnlyButton(
                                        icon_type="delete",
                                        icon_color=(1, 0.0, 0.0, 1),
                                        size=(40, 40),
                                    )
                                    delete_btn.bind(
                                        on_press=lambda x, mid=model_id: delete_model(
                                            app_instance, mid, popup
                                        )
                                    )
                                    btn_box.add_widget(delete_btn)

                                    header.add_widget(btn_box)
                                    model_box.add_widget(header)

                                    # Details
                                    # Determine if any element using this model had its cycle changed due to Thessaloniki
                                    try:
                                        c.execute(
                                            "SELECT 1 FROM elements e JOIN substations s ON e.substation_id = s.id WHERE e.element_model_id = ? AND s.is_thessaloniki=1 AND COALESCE(e.maintenance_cycle, -999) != COALESCE((SELECT maintenance_cycle FROM element_models WHERE id=?), -999) LIMIT 1",
                                            (model_id, model_id),
                                        )
                                        thess_star = True if c.fetchone() else False
                                    except Exception:
                                        thess_star = False

                                    cycle_display = (
                                        f"{cycle}" if cycle is not None else "-"
                                    )
                                    if thess_star:
                                        cycle_display = f"{cycle_display}*"

                                    # Determine display power: prefer model power, else infer most common element power, else '-'
                                    try:
                                        if power_mva is not None:
                                            display_power = power_mva
                                        else:
                                            c.execute(
                                                "SELECT power_mva, COUNT(*) as cnt FROM elements WHERE element_model_id=? AND power_mva IS NOT NULL GROUP BY power_mva ORDER BY cnt DESC LIMIT 1",
                                                (model_id,),
                                            )
                                            rr = c.fetchone()
                                            display_power = rr[0] if rr else None
                                    except Exception:
                                        display_power = None
                                    display_power_str = (
                                        f"{display_power} MVA"
                                        if display_power is not None
                                        else "-"
                                    )
                                    details_text = f"    Κατασκευαστής: {manufacturer or '-'} | Κύκλος: {cycle_display} έτη | Χώρος: {space or '-'} | Ισχ.: {display_power_str}"
                                    details = Label(
                                        text=details_text, size_hint_y=None, height=30
                                    )
                                    model_box.add_widget(details)

                                    grid.add_widget(model_box)
                    else:
                        # Display models in this category normally (not grouped by breaker type)
                        for (
                            model_id,
                            category,
                            model_name,
                            manufacturer,
                            cycle,
                            space,
                            breaker_cat,
                            manual_pdf,
                            power_mva,
                            onedrive_manual_link,
                        ) in category_models:
                            model_box = BoxLayout(
                                size_hint_y=None,
                                height=80,
                                spacing=5,
                                orientation="vertical",
                            )

                            # Header
                            header = BoxLayout(size_hint_y=None, height=30, spacing=5)
                            try:
                                c.execute(
                                    "SELECT COUNT(*) FROM elements WHERE element_model_id=?",
                                    (model_id,),
                                )
                                usage_count = c.fetchone()[0] or 0
                            except Exception:
                                usage_count = 0

                            header.add_widget(
                                Label(
                                    text=f"{model_name} ({usage_count})",
                                    bold=True,
                                    size_hint_x=0.45,
                                )
                            )
                            # Header power: prefer model power, else infer from elements, else '-'
                            try:
                                if power_mva is not None:
                                    header_power = power_mva
                                else:
                                    c.execute(
                                        "SELECT power_mva, COUNT(*) as cnt FROM elements WHERE element_model_id=? AND power_mva IS NOT NULL GROUP BY power_mva ORDER BY cnt DESC LIMIT 1",
                                        (model_id,),
                                    )
                                    _r = c.fetchone()
                                    header_power = _r[0] if _r else None
                            except Exception:
                                header_power = None
                            header_power_str = (
                                f"{header_power} MVA"
                                if header_power is not None
                                else "-"
                            )
                            header.add_widget(
                                Label(
                                    text=(f"Ισχ.: {header_power_str}"), size_hint_x=0.10
                                )
                            )

                            # Buttons
                            btn_box = BoxLayout(size_hint_x=0.45, spacing=5)

                            list_btn = Button(
                                text=S["BUTTONS"]["LIST"], size_hint_x=0.25
                            )
                            list_btn.bind(
                                on_press=lambda x, mid=model_id, mname=model_name: (
                                    show_model_usages(app_instance, mid, mname)
                                )
                            )
                            btn_box.add_widget(list_btn)

                            manual_label = (
                                S["MESSAGES"].get("MANUAL_LABEL", "Manual")
                                if (manual_pdf and os.path.exists(manual_pdf))
                                or onedrive_manual_link
                                else S["MESSAGES"].get("ADD_MANUAL", "Προσθήκη Manual")
                            )
                            manual_btn = Button(text=manual_label, size_hint_x=0.25)
                            manual_btn.bind(
                                on_press=lambda x, mid=model_id, path=manual_pdf, link=onedrive_manual_link, p=popup: (
                                    _handle_manual_pdf(app_instance, mid, path, link, p)
                                )
                            )
                            btn_box.add_widget(manual_btn)

                            edit_btn = IconOnlyButton(
                                icon_type="edit",
                                icon_color=(0.2, 0.6, 1, 1),
                                size=(45, 45),
                            )
                            edit_btn.bind(
                                on_press=lambda x, mid=model_id: show_edit_model_popup(
                                    app_instance, mid, popup
                                )
                            )
                            btn_box.add_widget(edit_btn)

                            delete_btn = IconOnlyButton(
                                icon_type="delete",
                                icon_color=(1, 0.0, 0.0, 1),
                                size=(40, 40),
                            )
                            delete_btn.bind(
                                on_press=lambda x, mid=model_id: delete_model(
                                    app_instance, mid, popup
                                )
                            )
                            btn_box.add_widget(delete_btn)

                            header.add_widget(btn_box)
                            model_box.add_widget(header)

                            # Details
                            try:
                                c.execute(
                                    "SELECT 1 FROM elements e JOIN substations s ON e.substation_id = s.id WHERE e.element_model_id = ? AND s.is_thessaloniki=1 AND COALESCE(e.maintenance_cycle, -999) != COALESCE((SELECT maintenance_cycle FROM element_models WHERE id=?), -999) LIMIT 1",
                                    (model_id, model_id),
                                )
                                thess_star = True if c.fetchone() else False
                            except Exception:
                                thess_star = False

                            cycle_display = f"{cycle}" if cycle is not None else "-"
                            if thess_star:
                                cycle_display = f"{cycle_display}*"

                            power_info = (
                                f" | Ονομαστική Ισχύς: {power_mva} MVA"
                                if power_mva is not None
                                else ""
                            )
                            details_text = f"Κατασκευαστής: {manufacturer or '-'} | Κύκλος: {cycle_display} έτη | Χώρος: {space or '-'}{power_info}"
                            if breaker_cat:
                                details_text += f" | Κατηγορία: {breaker_cat}"
                            details = Label(
                                text=details_text, size_hint_y=None, height=30
                            )
                            model_box.add_widget(details)

                            grid.add_widget(model_box)

                    # Add spacing between categories
                    spacing_widget = Label(text="", size_hint_y=None, height=20)
                    grid.add_widget(spacing_widget)
        else:
            grid.add_widget(
                Label(
                    text="Δεν υπάρχουν καταχωρημένα μοντέλα",
                    size_hint_y=None,
                    height=40,
                )
            )

    render_models(filter_spinner.text)
    filter_spinner.bind(text=lambda _spinner, text: render_models(text))

    scroll.add_widget(grid)
    main_layout.add_widget(scroll)

    # Close button
    close_btn = Button(text=S["BUTTONS"]["CLOSE"], size_hint_y=0.1)
    close_btn.bind(on_press=popup.dismiss)
    main_layout.add_widget(close_btn)

    popup.content = main_layout
    popup.open()


def show_add_model_popup(app_instance, parent_popup=None, category=None, callback=None):
    """Show add new model popup

    Args:
        app_instance: The app instance with conn and ELEMENT_TYPES
        parent_popup: Parent popup to dismiss after save (optional)
        category: Pre-selected category (optional)
        callback: Function to call after successful save (optional)
    """
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.spinner import Spinner
    from kivy.uix.textinput import TextInput

    popup = Popup(
        title=S["MESSAGES"].get("ADD_MODEL_TITLE", "Προσθήκη Νέου Μοντέλου"),
        size_hint=(0.8, 0.8),
    )
    main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
    layout = BoxLayout(orientation="vertical", size_hint_y=None, padding=5, spacing=8)
    layout.bind(minimum_height=layout.setter("height"))

    # Element category
    layout.add_widget(Label(text="Κατηγορία Στοιχείου:", size_hint_y=None, height=30))
    category_spinner = Spinner(
        text=(
            category
            if category
            else getattr(app_instance, "MODEL_CATEGORIES", app_instance.ELEMENT_TYPES)[
                0
            ]
        ),
        values=getattr(app_instance, "MODEL_CATEGORIES", app_instance.ELEMENT_TYPES),
        size_hint_y=None,
        height=40,
    )
    layout.add_widget(category_spinner)

    # Model name
    layout.add_widget(Label(text="Όνομα Μοντέλου:", size_hint_y=None, height=30))
    model_name_input = TextInput(
        hint_text="Όνομα Μοντέλου", size_hint_y=None, height=40, multiline=False
    )
    layout.add_widget(model_name_input)

    # Breaker category (conditional - placed early for better UX)
    breaker_label = Label(text="Κατηγορία Διακόπτη:", size_hint_y=None, height=30)
    initial_breaker_categories = app_instance._get_breaker_categories_for_element_type(
        category_spinner.text
    )
    breaker_spinner = Spinner(
        text=initial_breaker_categories[0] if initial_breaker_categories else "SF6",
        values=initial_breaker_categories,
        size_hint_y=None,
        height=40,
    )

    # SF6 capacity (kg) - only for SF6 breaker models
    sf6_capacity_label = Label(
        text="Χωρητικότητα SF6 (kg):", size_hint_y=None, height=30
    )
    sf6_capacity_input = TextInput(
        hint_text="kg", size_hint_y=None, height=40, multiline=False
    )

    # Manufacturer
    layout.add_widget(Label(text="Κατασκευαστής:", size_hint_y=None, height=30))
    manufacturer_input = TextInput(
        hint_text="Κατασκευαστής", size_hint_y=None, height=40, multiline=False
    )
    layout.add_widget(manufacturer_input)

    # Rated power (MVA)
    layout.add_widget(
        Label(text="Ονομαστική Ισχύς (MVA):", size_hint_y=None, height=30)
    )
    power_input = TextInput(
        hint_text="MVA", size_hint_y=None, height=40, multiline=False
    )
    layout.add_widget(power_input)

    # Maintenance cycle
    layout.add_widget(
        Label(text="Κύκλος Συντήρησης (έτη):", size_hint_y=None, height=30)
    )
    cycle_input = TextInput(
        hint_text="Αριθμός ετών", size_hint_y=None, height=40, multiline=False
    )
    layout.add_widget(cycle_input)

    # Installation space
    layout.add_widget(Label(text="Χώρος Εγκατάστασης:", size_hint_y=None, height=30))
    space_spinner = Spinner(
        text="Εξωτερικός",
        values=["Εσωτερικός", "Εξωτερικός"],
        size_hint_y=None,
        height=40,
    )
    layout.add_widget(space_spinner)

    extra_fields_box = BoxLayout(
        orientation="vertical", size_hint_y=None, padding=0, spacing=8
    )
    extra_fields_box.bind(minimum_height=extra_fields_box.setter("height"))
    layout.add_widget(extra_fields_box)
    extra_field_inputs = {}

    def on_category_change(spinner, text):
        # Remove breaker fields if they exist
        if breaker_label in layout.children:
            layout.remove_widget(breaker_label)
            layout.remove_widget(breaker_spinner)
        if sf6_capacity_label in layout.children:
            layout.remove_widget(sf6_capacity_label)
            layout.remove_widget(sf6_capacity_input)

        # Add them back only if circuit breaker is selected
        if text in [ELEM_BREAKER_MT, ELEM_BREAKER_YT]:
            breaker_categories = app_instance._get_breaker_categories_for_element_type(
                text
            )
            breaker_spinner.values = breaker_categories
            if breaker_spinner.text not in breaker_categories:
                breaker_spinner.text = (
                    breaker_categories[0] if breaker_categories else "SF6"
                )
            # Insert after model_name_input (which means before manufacturer in the visual order)
            idx = layout.children.index(model_name_input)
            layout.add_widget(breaker_spinner, index=idx)
            layout.add_widget(breaker_label, index=idx + 1)
            if breaker_spinner.text == "SF6":
                layout.add_widget(sf6_capacity_input, index=idx)
                layout.add_widget(sf6_capacity_label, index=idx + 1)

        _build_model_extra_inputs(extra_fields_box, text, extra_field_inputs)

    def on_breaker_category_change(_spinner, _text):
        if sf6_capacity_label in layout.children:
            layout.remove_widget(sf6_capacity_label)
            layout.remove_widget(sf6_capacity_input)
        if (
            category_spinner.text in [ELEM_BREAKER_MT, ELEM_BREAKER_YT]
            and breaker_spinner.text == "SF6"
        ):
            idx = layout.children.index(model_name_input)
            layout.add_widget(sf6_capacity_input, index=idx)
            layout.add_widget(sf6_capacity_label, index=idx + 1)

    category_spinner.bind(text=on_category_change)
    breaker_spinner.bind(text=on_breaker_category_change)
    on_category_change(category_spinner, category_spinner.text)

    scroll.add_widget(layout)
    main_layout.add_widget(scroll)

    # Buttons
    buttons_layout = BoxLayout(size_hint_y=0.15, spacing=10)

    def save_model():
        if not model_name_input.text.strip():
            show_message_popup(
                S["TITLES"]["ERROR"], S["MESSAGES"]["MODEL_NAME_REQUIRED"]
            )
            return

        try:
            cycle = int(cycle_input.text) if cycle_input.text.strip() else 0
        except ValueError:
            show_message_popup(
                S["TITLES"]["ERROR"], S["MESSAGES"]["MODEL_SERVICE_CYCLE_NUM"]
            )
            return

        # parse rated power
        power_val = None
        if power_input.text.strip():
            try:
                power_val = float(power_input.text.strip())
            except ValueError:
                show_message_popup(
                    S["TITLES"]["ERROR"], S["MESSAGES"]["MODEL_POWER_NUM"]
                )
                return

        breaker_cat = (
            breaker_spinner.text
            if category_spinner.text in [ELEM_BREAKER_MT, ELEM_BREAKER_YT]
            else ""
        )

        try:
            extra_values = _collect_model_extra_values(
                category_spinner.text, extra_field_inputs
            )
        except ValueError as exc:
            show_message_popup(S["TITLES"]["ERROR"], str(exc))
            return

        extra_values, power_val = _apply_breaker_model_defaults(
            category_spinner.text,
            model_name_input.text.strip(),
            extra_values,
            power_val,
        )

        sf6_capacity_val = None
        if breaker_cat == "SF6":
            if not sf6_capacity_input.text.strip():
                show_message_popup(
                    "Σφάλμα",
                    "Η χωρητικότητα SF6 (kg) είναι υποχρεωτική για μοντέλα SF6!",
                )
                return
            try:
                sf6_capacity_val = float(sf6_capacity_input.text.strip())
            except ValueError:
                show_message_popup(
                    "Σφάλμα", "Η χωρητικότητα SF6 πρέπει να είναι αριθμός!"
                )
                return

        c = app_instance.conn.cursor()
        try:
            c.execute(
                "INSERT INTO element_models (element_category, model_name, manufacturer, maintenance_cycle, installation_space, breaker_category, sf6_capacity_kg, power_mva, connection_group, rated_voltage_hv_lv, mounting, specification, bil_hv_lv_kv, total_weight_kg, oil_weight_kg, rated_normal_current_a, rated_short_circuit_breaking_current_ka, short_circuit_duration_s, making_capacity_ka, sf6_pressure_rated_bar, drive_mechanism, rated_short_circuit_making_current_ka, cubicle, onedrive_manual_link) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    category_spinner.text,
                    model_name_input.text.strip(),
                    manufacturer_input.text.strip(),
                    cycle,
                    space_spinner.text,
                    breaker_cat,
                    sf6_capacity_val,
                    power_val,
                    extra_values.get("connection_group"),
                    extra_values.get("rated_voltage_hv_lv"),
                    extra_values.get("mounting"),
                    extra_values.get("specification"),
                    extra_values.get("bil_hv_lv_kv"),
                    extra_values.get("total_weight_kg"),
                    extra_values.get("oil_weight_kg"),
                    extra_values.get("rated_normal_current_a"),
                    extra_values.get("rated_short_circuit_breaking_current_ka"),
                    extra_values.get("short_circuit_duration_s"),
                    extra_values.get("making_capacity_ka"),
                    extra_values.get("sf6_pressure_rated_bar"),
                    extra_values.get("drive_mechanism"),
                    extra_values.get("rated_short_circuit_making_current_ka"),
                    extra_values.get("cubicle"),
                    None,
                ),
            )
            app_instance.conn.commit()
            model_id = c.lastrowid
            app_instance._append_change_log(
                "insert",
                "element_models",
                {
                    "id": model_id,
                    "element_category": category_spinner.text,
                    "model_name": model_name_input.text.strip(),
                    "manufacturer": manufacturer_input.text.strip(),
                    "maintenance_cycle": cycle,
                    "installation_space": space_spinner.text,
                    "breaker_category": breaker_cat,
                    "sf6_capacity_kg": sf6_capacity_val,
                    "power_mva": power_val,
                    "connection_group": extra_values.get("connection_group"),
                    "rated_voltage_hv_lv": extra_values.get("rated_voltage_hv_lv"),
                    "mounting": extra_values.get("mounting"),
                    "specification": extra_values.get("specification"),
                    "bil_hv_lv_kv": extra_values.get("bil_hv_lv_kv"),
                    "total_weight_kg": extra_values.get("total_weight_kg"),
                    "oil_weight_kg": extra_values.get("oil_weight_kg"),
                    "rated_normal_current_a": extra_values.get(
                        "rated_normal_current_a"
                    ),
                    "rated_short_circuit_breaking_current_ka": extra_values.get(
                        "rated_short_circuit_breaking_current_ka"
                    ),
                    "short_circuit_duration_s": extra_values.get(
                        "short_circuit_duration_s"
                    ),
                    "making_capacity_ka": extra_values.get("making_capacity_ka"),
                    "sf6_pressure_rated_bar": extra_values.get(
                        "sf6_pressure_rated_bar"
                    ),
                    "drive_mechanism": extra_values.get("drive_mechanism"),
                    "rated_short_circuit_making_current_ka": extra_values.get(
                        "rated_short_circuit_making_current_ka"
                    ),
                    "cubicle": extra_values.get("cubicle"),
                    "onedrive_manual_link": None,
                },
            )
            popup.dismiss()

            # Handle different callback scenarios
            if callback:
                show_message_popup(
                    "Επιτυχία", "Το μοντέλο προστέθηκε!", callback=callback
                )
            elif parent_popup:
                parent_popup.dismiss()
                show_message_popup(
                    "Επιτυχία",
                    "Το μοντέλο προστέθηκε!",
                    callback=lambda: show_models_management(app_instance),
                )
            else:
                show_message_popup(S["TITLES"]["SUCCESS"], S["MESSAGES"]["MODEL_ADDED"])
        except Exception as e:
            show_message_popup(
                S["TITLES"]["ERROR"], f"Σφάλμα κατά την αποθήκευση: {str(e)}"
            )

    save_btn = Button(text=S["BUTTONS"]["SAVE"])
    save_btn.bind(on_press=lambda x: save_model())
    buttons_layout.add_widget(save_btn)

    cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
    cancel_btn.bind(on_press=popup.dismiss)
    buttons_layout.add_widget(cancel_btn)

    main_layout.add_widget(buttons_layout)
    popup.content = main_layout
    popup.open()


def show_edit_model_popup(app_instance, model_id, parent_popup):
    """Show edit model popup"""
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.spinner import Spinner
    from kivy.uix.textinput import TextInput

    c = app_instance.conn.cursor()
    c.execute(
        "SELECT element_category, model_name, manufacturer, maintenance_cycle, installation_space, breaker_category, sf6_capacity_kg, power_mva, onedrive_manual_link, connection_group, rated_voltage_hv_lv, mounting, specification, bil_hv_lv_kv, total_weight_kg, oil_weight_kg, rated_normal_current_a, rated_short_circuit_breaking_current_ka, short_circuit_duration_s, making_capacity_ka, sf6_pressure_rated_bar, drive_mechanism, rated_short_circuit_making_current_ka, cubicle FROM element_models WHERE id=?",
        (model_id,),
    )
    model = c.fetchone()

    if not model:
        show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["MODEL_NOT_FOUND"])
        return

    (
        category,
        model_name,
        manufacturer,
        cycle,
        space,
        breaker_cat,
        sf6_capacity,
        power_mva,
        onedrive_manual_link,
        connection_group,
        rated_voltage_hv_lv,
        mounting,
        specification,
        bil_hv_lv_kv,
        total_weight_kg,
        oil_weight_kg,
        rated_normal_current_a,
        rated_short_circuit_breaking_current_ka,
        short_circuit_duration_s,
        making_capacity_ka,
        sf6_pressure_rated_bar,
        drive_mechanism,
        rated_short_circuit_making_current_ka,
        cubicle,
    ) = model

    popup = Popup(title=f"Επεξεργασία: {model_name}", size_hint=(0.8, 0.8))
    main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
    layout = BoxLayout(orientation="vertical", size_hint_y=None, padding=5, spacing=8)
    layout.bind(minimum_height=layout.setter("height"))

    # Category (read-only display)
    layout.add_widget(
        Label(text=f"Κατηγορία: {category}", size_hint_y=None, height=30, bold=True)
    )

    # Model name
    layout.add_widget(Label(text="Όνομα Μοντέλου:", size_hint_y=None, height=30))
    model_name_input = TextInput(
        text=model_name, size_hint_y=None, height=40, multiline=False
    )
    layout.add_widget(model_name_input)

    # Manufacturer
    layout.add_widget(Label(text="Κατασκευαστής:", size_hint_y=None, height=30))
    manufacturer_input = TextInput(
        text=manufacturer or "", size_hint_y=None, height=40, multiline=False
    )
    layout.add_widget(manufacturer_input)

    # Rated power (MVA)
    layout.add_widget(
        Label(text="Ονομαστική Ισχύς (MVA):", size_hint_y=None, height=30)
    )
    power_input = TextInput(
        text=str(power_mva) if power_mva is not None else "",
        size_hint_y=None,
        height=40,
        multiline=False,
    )
    layout.add_widget(power_input)

    # Maintenance cycle
    layout.add_widget(
        Label(text="Κύκλος Συντήρησης (έτη):", size_hint_y=None, height=30)
    )
    cycle_input = TextInput(
        text=str(cycle), size_hint_y=None, height=40, multiline=False
    )
    layout.add_widget(cycle_input)

    # Installation space
    layout.add_widget(Label(text="Χώρος Εγκατάστασης:", size_hint_y=None, height=30))
    space_spinner = Spinner(
        text=space or "Εξωτερικός",
        values=["Εσωτερικός", "Εξωτερικός"],
        size_hint_y=None,
        height=40,
    )
    layout.add_widget(space_spinner)

    extra_fields_box = BoxLayout(
        orientation="vertical", size_hint_y=None, padding=0, spacing=8
    )
    extra_fields_box.bind(minimum_height=extra_fields_box.setter("height"))
    layout.add_widget(extra_fields_box)
    extra_field_inputs = {}
    _build_model_extra_inputs(
        extra_fields_box,
        category,
        extra_field_inputs,
        {
            "connection_group": connection_group,
            "rated_voltage_hv_lv": rated_voltage_hv_lv,
            "mounting": mounting,
            "specification": specification,
            "bil_hv_lv_kv": bil_hv_lv_kv,
            "total_weight_kg": total_weight_kg,
            "oil_weight_kg": oil_weight_kg,
            "rated_normal_current_a": rated_normal_current_a,
            "rated_short_circuit_breaking_current_ka": rated_short_circuit_breaking_current_ka,
            "short_circuit_duration_s": short_circuit_duration_s,
            "making_capacity_ka": making_capacity_ka,
            "sf6_pressure_rated_bar": sf6_pressure_rated_bar,
            "drive_mechanism": drive_mechanism,
            "rated_short_circuit_making_current_ka": rated_short_circuit_making_current_ka,
            "cubicle": cubicle,
        },
    )

    # Breaker category (if applicable)
    if category in [ELEM_BREAKER_MT, ELEM_BREAKER_YT]:
        layout.add_widget(
            Label(text="Κατηγορία Διακόπτη:", size_hint_y=None, height=30)
        )
        breaker_categories = app_instance._get_breaker_categories_for_element_type(
            category
        )
        breaker_spinner = Spinner(
            text=(
                breaker_cat
                if breaker_cat in breaker_categories
                else (breaker_categories[0] if breaker_categories else "SF6")
            ),
            values=breaker_categories,
            size_hint_y=None,
            height=40,
        )
        layout.add_widget(breaker_spinner)
    else:
        breaker_spinner = None

    # SF6 capacity (kg) - only for SF6 breaker models
    sf6_capacity_input = None
    if category in [ELEM_BREAKER_MT, ELEM_BREAKER_YT] and breaker_cat == "SF6":
        layout.add_widget(
            Label(text="Χωρητικότητα SF6 (kg):", size_hint_y=None, height=30)
        )
        sf6_capacity_input = TextInput(
            text=str(sf6_capacity) if sf6_capacity is not None else "",
            size_hint_y=None,
            height=40,
            multiline=False,
        )
        layout.add_widget(sf6_capacity_input)

    scroll.add_widget(layout)
    main_layout.add_widget(scroll)

    # Buttons
    buttons_layout = BoxLayout(size_hint_y=0.15, spacing=10)

    def save_changes():
        if not model_name_input.text.strip():
            show_message_popup(
                S["TITLES"]["ERROR"], "Το όνομα μοντέλου είναι υποχρεωτικό!"
            )
            return

        try:
            cycle_val = int(cycle_input.text) if cycle_input.text.strip() else 0
        except ValueError:
            show_message_popup(
                S["TITLES"]["ERROR"], "Ο κύκλος συντήρησης πρέπει να είναι αριθμός!"
            )
            return

        # parse rated power
        power_val = None
        if power_input.text.strip():
            try:
                power_val = float(power_input.text.strip())
            except ValueError:
                show_message_popup(
                    S["TITLES"]["ERROR"], "Η ονομαστική ισχύς πρέπει να είναι αριθμός!"
                )
                return

        breaker_cat_val = breaker_spinner.text if breaker_spinner else ""

        try:
            extra_values = _collect_model_extra_values(category, extra_field_inputs)
        except ValueError as exc:
            show_message_popup(S["TITLES"]["ERROR"], str(exc))
            return

        extra_values, power_val = _apply_breaker_model_defaults(
            category,
            model_name_input.text.strip(),
            extra_values,
            power_val,
        )

        sf6_capacity_val = None
        if breaker_cat_val == "SF6":
            if not sf6_capacity_input or not sf6_capacity_input.text.strip():
                show_message_popup(
                    "Σφάλμα",
                    "Η χωρητικότητα SF6 (kg) είναι υποχρεωτική για μοντέλα SF6!",
                )
                return
            try:
                sf6_capacity_val = float(sf6_capacity_input.text.strip())
            except ValueError:
                show_message_popup(
                    "Σφάλμα", "Η χωρητικότητα SF6 πρέπει να είναι αριθμός!"
                )
                return

        c = app_instance.conn.cursor()

        # Update the model
        c.execute(
            "UPDATE element_models SET model_name=?, manufacturer=?, maintenance_cycle=?, installation_space=?, breaker_category=?, sf6_capacity_kg=?, power_mva=?, onedrive_manual_link=?, connection_group=?, rated_voltage_hv_lv=?, mounting=?, specification=?, bil_hv_lv_kv=?, total_weight_kg=?, oil_weight_kg=?, rated_normal_current_a=?, rated_short_circuit_breaking_current_ka=?, short_circuit_duration_s=?, making_capacity_ka=?, sf6_pressure_rated_bar=?, drive_mechanism=?, rated_short_circuit_making_current_ka=?, cubicle=? WHERE id=?",
            (
                model_name_input.text.strip(),
                manufacturer_input.text.strip(),
                cycle_val,
                space_spinner.text,
                breaker_cat_val,
                sf6_capacity_val,
                power_val,
                onedrive_manual_link,
                extra_values.get("connection_group"),
                extra_values.get("rated_voltage_hv_lv"),
                extra_values.get("mounting"),
                extra_values.get("specification"),
                extra_values.get("bil_hv_lv_kv"),
                extra_values.get("total_weight_kg"),
                extra_values.get("oil_weight_kg"),
                extra_values.get("rated_normal_current_a"),
                extra_values.get("rated_short_circuit_breaking_current_ka"),
                extra_values.get("short_circuit_duration_s"),
                extra_values.get("making_capacity_ka"),
                extra_values.get("sf6_pressure_rated_bar"),
                extra_values.get("drive_mechanism"),
                extra_values.get("rated_short_circuit_making_current_ka"),
                extra_values.get("cubicle"),
                model_id,
            ),
        )

        # Update all linked elements with the new model name
        new_model_display = model_name_input.text.strip()

        c.execute(
            "UPDATE elements SET model=?, manufacturer=?, maintenance_cycle=?, installation_space=?, power_mva=? WHERE element_model_id=?",
            (
                new_model_display,
                manufacturer_input.text.strip(),
                cycle_val,
                space_spinner.text,
                power_val,
                model_id,
            ),
        )

        app_instance.conn.commit()
        app_instance._append_change_log(
            "update",
            "element_models",
            {
                "id": model_id,
                "model_name": model_name_input.text.strip(),
                "manufacturer": manufacturer_input.text.strip(),
                "maintenance_cycle": cycle_val,
                "installation_space": space_spinner.text,
                "breaker_category": breaker_cat_val,
                "sf6_capacity_kg": sf6_capacity_val,
                "power_mva": power_val,
                "connection_group": extra_values.get("connection_group"),
                "rated_voltage_hv_lv": extra_values.get("rated_voltage_hv_lv"),
                "mounting": extra_values.get("mounting"),
                "specification": extra_values.get("specification"),
                "bil_hv_lv_kv": extra_values.get("bil_hv_lv_kv"),
                "total_weight_kg": extra_values.get("total_weight_kg"),
                "oil_weight_kg": extra_values.get("oil_weight_kg"),
                "rated_normal_current_a": extra_values.get("rated_normal_current_a"),
                "rated_short_circuit_breaking_current_ka": extra_values.get(
                    "rated_short_circuit_breaking_current_ka"
                ),
                "short_circuit_duration_s": extra_values.get(
                    "short_circuit_duration_s"
                ),
                "making_capacity_ka": extra_values.get("making_capacity_ka"),
                "sf6_pressure_rated_bar": extra_values.get("sf6_pressure_rated_bar"),
                "drive_mechanism": extra_values.get("drive_mechanism"),
                "rated_short_circuit_making_current_ka": extra_values.get(
                    "rated_short_circuit_making_current_ka"
                ),
                "cubicle": extra_values.get("cubicle"),
                "onedrive_manual_link": onedrive_manual_link,
            },
        )
        popup.dismiss()
        parent_popup.dismiss()
        show_message_popup(
            "Επιτυχία",
            "Το μοντέλο και όλα τα συνδεδεμένα στοιχεία ενημερώθηκαν!",
            callback=lambda: show_models_management(app_instance),
        )

    save_btn = Button(text="Αποθήκευση")
    save_btn.bind(on_press=lambda x: save_changes())
    buttons_layout.add_widget(save_btn)

    cancel_btn = Button(text=S["BUTTONS"].get("CANCEL", "Ακύρωση"))
    cancel_btn.bind(on_press=popup.dismiss)
    buttons_layout.add_widget(cancel_btn)

    main_layout.add_widget(buttons_layout)
    popup.content = main_layout
    popup.open()


def _handle_manual_pdf(
    app_instance, model_id, manual_pdf, onedrive_manual_link=None, parent_popup=None
):
    has_local = bool(manual_pdf and os.path.exists(manual_pdf))
    has_link = bool(onedrive_manual_link and _is_web_url(onedrive_manual_link))

    if has_local or has_link:
        _show_manual_actions_popup(
            app_instance,
            model_id,
            manual_pdf,
            onedrive_manual_link,
            parent_popup,
        )
        return

    _select_manual_pdf(app_instance, model_id, parent_popup)


def _show_manual_actions_popup(
    app_instance, model_id, manual_pdf, onedrive_manual_link, parent_popup=None
):
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup

    has_local = bool(manual_pdf and os.path.exists(manual_pdf))
    has_link = bool(onedrive_manual_link and _is_web_url(onedrive_manual_link))

    popup = Popup(title="Manual Επιλογές", size_hint=(0.75, 0.45))
    layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    status_parts = []
    status_parts.append("Τοπικό: διαθέσιμο" if has_local else "Τοπικό: μη διαθέσιμο")
    status_parts.append("OneDrive: διαθέσιμο" if has_link else "OneDrive: μη διαθέσιμο")
    layout.add_widget(Label(text=" | ".join(status_parts), size_hint_y=0.25))

    buttons_row_1 = BoxLayout(size_hint_y=0.25, spacing=10)
    open_local_btn = Button(text="Άνοιγμα Τοπικού")
    open_local_btn.disabled = not has_local
    open_local_btn.bind(
        on_press=lambda _x: (popup.dismiss(), _open_manual_pdf(manual_pdf))
    )
    buttons_row_1.add_widget(open_local_btn)

    open_link_btn = Button(text="Άνοιγμα OneDrive")
    open_link_btn.disabled = not has_link
    open_link_btn.bind(
        on_press=lambda _x: (popup.dismiss(), _open_manual_link(onedrive_manual_link))
    )
    buttons_row_1.add_widget(open_link_btn)
    layout.add_widget(buttons_row_1)

    buttons_row_2 = BoxLayout(size_hint_y=0.25, spacing=10)
    replace_btn = Button(text="Αλλαγή / Αντικατάσταση")
    replace_btn.bind(
        on_press=lambda _x: (
            popup.dismiss(),
            _select_manual_pdf(app_instance, model_id, parent_popup),
        )
    )
    buttons_row_2.add_widget(replace_btn)

    close_btn = Button(text=S["BUTTONS"].get("CANCEL", "Ακύρωση"))
    close_btn.bind(on_press=popup.dismiss)
    buttons_row_2.add_widget(close_btn)
    layout.add_widget(buttons_row_2)

    popup.content = layout
    popup.open()


def _is_web_url(value):
    v = (value or "").strip().lower()
    return v.startswith("http://") or v.startswith("https://")


def _open_manual_link(url):
    link = (url or "").strip()
    if not _is_web_url(link):
        show_message_popup("Σφάλμα", "Μη έγκυρος σύνδεσμος OneDrive!")
        return False
    try:
        return webbrowser.open(link)
    except Exception as e:
        show_message_popup("Σφάλμα", f"Αποτυχία ανοίγματος συνδέσμου:\n{e}")
        return False


def _open_manual_pdf(pdf_path):
    """Open a model's manual (can be a file or folder)."""
    from reports import open_file as _open

    if not pdf_path or not os.path.exists(pdf_path):
        from popups import show_message_popup

        show_message_popup("Σφάλμα", "Το εγχειρίδιο δεν βρέθηκε!")
        return False

    # Works for both files and folders
    return _open(
        pdf_path,
        not_found_message="Το εγχειρίδιο δεν βρέθηκε!",
        error_prefix="Αποτυχία ανοίγματος εγχειριδίου:\n",
    )


def _select_manual_pdf(app_instance, model_id, parent_popup=None):
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.textinput import TextInput

    c = app_instance.conn.cursor()
    c.execute(
        "SELECT manual_pdf, onedrive_manual_link FROM element_models WHERE id=?",
        (model_id,),
    )
    row = c.fetchone() or (None, None)
    current_manual_pdf, current_onedrive_link = row

    popup = Popup(title="Επιλογή Manual (PDF/Φάκελος ή OneDrive)", size_hint=(0.9, 0.7))
    layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    path_label = Label(text="Τοπική διαδρομή PDF ή φακέλου:", size_hint_y=0.12)
    layout.add_widget(path_label)

    path_input = TextInput(
        text=current_manual_pdf or "",
        hint_text="C:\\...\\manual.pdf ή C:\\...\\folder",
        size_hint_y=0.12,
        multiline=False,
    )
    layout.add_widget(path_input)

    browse_btn = Button(text="Αναζήτηση Τοπικού Manual", size_hint_y=0.12)
    layout.add_widget(browse_btn)

    layout.add_widget(Label(text="Σύνδεσμος OneDrive (προαιρετικό):", size_hint_y=0.12))
    link_input = TextInput(
        text=current_onedrive_link or "",
        hint_text="https://...",
        size_hint_y=0.12,
        multiline=False,
    )
    layout.add_widget(link_input)

    buttons_layout = BoxLayout(size_hint_y=0.14, spacing=10)

    def browse_local_manual():
        try:
            fp = ask_open_file(
                title="Select Manual PDF", filetypes=(("PDF files", "*.pdf"),)
            )
        except Exception:
            fp = None
        if fp:
            path_input.text = fp

    browse_btn.bind(on_press=lambda _x: browse_local_manual())

    def save_file():
        file_path = path_input.text.strip() or None
        link_val = link_input.text.strip() or None

        if not file_path and not link_val:
            show_message_popup(
                "Σφάλμα", "Συμπληρώστε τοπικό manual ή σύνδεσμο OneDrive!"
            )
            return

        if file_path:
            if not os.path.exists(file_path):
                show_message_popup(
                    S["TITLES"]["ERROR"], "Το αρχείο/φάκελος δεν βρέθηκε!"
                )
                return

            # Accept either a PDF file or a directory
            if not os.path.isdir(file_path) and not file_path.lower().endswith(".pdf"):
                show_message_popup(
                    S["TITLES"]["ERROR"], "Παρακαλώ επιλέξτε αρχείο PDF ή φάκελο!"
                )
                return

        if link_val and not _is_web_url(link_val):
            show_message_popup(
                "Σφάλμα", "Ο σύνδεσμος πρέπει να ξεκινά με http:// ή https://"
            )
            return

        c = app_instance.conn.cursor()
        c.execute(
            "UPDATE element_models SET manual_pdf=?, onedrive_manual_link=? WHERE id=?",
            (file_path, link_val, model_id),
        )
        app_instance.conn.commit()
        app_instance._append_change_log(
            "update",
            "element_models",
            {
                "id": model_id,
                "manual_pdf": file_path,
                "onedrive_manual_link": link_val,
            },
        )
        popup.dismiss()

        if parent_popup:
            parent_popup.dismiss()
        show_models_management(app_instance)

    save_btn = Button(text="Αποθήκευση")
    save_btn.bind(on_press=lambda x: save_file())
    buttons_layout.add_widget(save_btn)

    cancel_btn = Button(text=S["BUTTONS"].get("CANCEL", "Ακύρωση"))
    cancel_btn.bind(on_press=popup.dismiss)
    buttons_layout.add_widget(cancel_btn)

    layout.add_widget(buttons_layout)
    popup.content = layout
    popup.open()


def delete_model(app_instance, model_id, parent_popup):
    """Delete a model"""

    c = app_instance.conn.cursor()

    # Check if model is in use
    c.execute("SELECT COUNT(*) FROM elements WHERE element_model_id=?", (model_id,))
    count = c.fetchone()[0]

    if count > 0:
        show_message_popup(
            "Σφάλμα",
            f"Το μοντέλο χρησιμοποιείται σε {count} στοιχεία και δεν μπορεί να διαγραφεί!",
        )
        return

    from reports import show_confirm

    def confirm():
        c.execute("DELETE FROM element_models WHERE id=?", (model_id,))
        app_instance.conn.commit()
        if parent_popup:
            parent_popup.dismiss()
        from popups import show_message_popup

        show_message_popup(S["TITLES"]["SUCCESS"], S["MESSAGES"]["MODEL_DELETED"])

    show_confirm(
        "Επιβεβαίωση Διαγραφής",
        "Είστε σίγουροι ότι θέλετε να διαγράψετε\nαυτό το μοντέλο;",
        yes_callback=confirm,
        yes_color=(1, 0, 0, 1),
    )


def jump_to_substation(app_instance, substation_name, current_popup):
    """Jump to substation elements view and close current popup"""
    current_popup.dismiss()
    # Call the display function from app_instance
    app_instance._display_substations(substation_name)


def show_model_usages(app_instance, model_id, model_name):
    """Show list of substations and elements using this model"""
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.gridlayout import GridLayout
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.scrollview import ScrollView

    c = app_instance.conn.cursor()

    # Get all elements using this model with full details
    c.execute(
        """
        SELECT e.id, e.element_type, e.name, e.serial_number, e.maintenance_date, 
               e.manufacturer, e.installation_space, e.operating_status, e.maintenance_cycle, 
               e.breaker_category, e.manufacture_year,
               s.name as substation_name, s.id as substation_id
        FROM elements e
        JOIN substations s ON e.substation_id = s.id
        WHERE e.element_model_id = ?
        ORDER BY s.name, e.element_type, e.name
    """,
        (model_id,),
    )

    usages = c.fetchall()

    popup = Popup(title=f"Χρήση Μοντέλου: {model_name}", size_hint=(0.95, 0.9))
    main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    if usages:
        # Header info
        info_label = Label(
            text=f"Το μοντέλο χρησιμοποιείται σε {len(usages)} στοιχεία:",
            size_hint_y=None,
            height=35,
            bold=True,
        )
        main_layout.add_widget(info_label)

        # Scrollable list
        scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
        grid = GridLayout(cols=1, spacing=5, size_hint_y=None, padding=5)
        grid.bind(minimum_height=grid.setter("height"))

        # Fetch model rated power once
        try:
            c.execute("SELECT power_mva FROM element_models WHERE id=?", (model_id,))
            _row = c.fetchone()
            model_power_val = _row[0] if _row and _row[0] is not None else None
        except Exception:
            model_power_val = None

        # Group elements by substation and status
        substation_groups = {}
        substation_order = []
        for elem_data in usages:
            operating_status = elem_data[7]
            substation_name = elem_data[11]
            substation_id = elem_data[12]
            status_val = operating_status.strip() if operating_status else ""
            is_inactive = status_val == "Ανενεργή"
            if substation_name not in substation_groups:
                substation_groups[substation_name] = {
                    "id": substation_id,
                    "active": [],
                    "inactive": [],
                }
                substation_order.append(substation_name)
            if is_inactive:
                substation_groups[substation_name]["inactive"].append(elem_data)
            else:
                substation_groups[substation_name]["active"].append(elem_data)

        def add_element_box(elem_data, is_inactive):
            (
                elem_id,
                elem_type,
                elem_name,
                serial_number,
                maintenance_date,
                manufacturer,
                installation_space,
                operating_status,
                maintenance_cycle,
                breaker_category,
                manufacture_year,
                substation_name,
                substation_id,
            ) = elem_data

            # Element details box
            elem_box = BoxLayout(
                size_hint_y=None,
                height=90,
                spacing=5,
                orientation="vertical",
                padding=(10, 0, 0, 0),
            )

            # Element name and type (bold, larger)
            breaker_info = f" | {breaker_category}" if breaker_category else ""
            inactive_marker = (
                " [color=ff0000][b]ΑΝΕΝΕΡΓΟ[/b][/color]" if is_inactive else ""
            )
            name_text = f"[b][size=16]{elem_name}[/size][/b] - {elem_type}{breaker_info}{inactive_marker}"
            name_label = Label(
                text=name_text,
                size_hint_y=None,
                height=25,
                markup=True,
                halign="left",
                valign="middle",
            )
            name_label.bind(size=name_label.setter("text_size"))
            elem_box.add_widget(name_label)

            # Serial number and manufacture year
            manufacture_info = (
                f" | Έτος: {manufacture_year}" if manufacture_year else ""
            )
            sn_text = f"S/N: {serial_number or '-'}{manufacture_info}"
            sn_label = Label(
                text=sn_text,
                size_hint_y=None,
                height=20,
                halign="left",
                valign="middle",
            )
            sn_label.bind(size=sn_label.setter("text_size"))
            elem_box.add_widget(sn_label)

            # Manufacturer, installation space, operating status, model power (format like substation details)
            display_power_str = (
                f"{model_power_val} MVA" if model_power_val is not None else "-"
            )
            status_display = (
                "Ανενεργή" if is_inactive else (operating_status or "Ενεργή")
            )
            details_text = (
                f"Κατ.: {manufacturer or '-'} | Χώρος: {installation_space or '-'} | "
                f"Κατάστ.: {status_display} | Ισχ.: {display_power_str}"
            )
            details_label = Label(
                text=details_text,
                size_hint_y=None,
                height=20,
                halign="left",
                valign="middle",
            )
            details_label.bind(size=details_label.setter("text_size"))
            elem_box.add_widget(details_label)

            # Maintenance info
            maint_text = f"Κύκλος: {maintenance_cycle or '-'} | Τελ. Συντ.: {maintenance_date or '-'}"
            maint_label = Label(
                text=maint_text,
                size_hint_y=None,
                height=20,
                halign="left",
                valign="middle",
            )
            maint_label.bind(size=maint_label.setter("text_size"))
            elem_box.add_widget(maint_label)

            grid.add_widget(elem_box)

        for substation_name in substation_order:
            group = substation_groups[substation_name]
            substation_id = group["id"]
            active_elements = group["active"]
            inactive_elements = group["inactive"]
            active_count = len(active_elements)
            inactive_count = len(inactive_elements)
            total_count = active_count + inactive_count

            # Substation header
            count_text = f" ({total_count}/{inactive_count})"

            # Create a layout for substation header with button
            substation_header_layout = BoxLayout(
                size_hint_y=None, height=40, spacing=10
            )

            substation_header = Label(
                text=f"[b][size=18]{substation_name}{count_text}[/size][/b]",
                size_hint_x=0.6,
                markup=True,
                halign="left",
                valign="middle",
            )
            substation_header.bind(size=substation_header.setter("text_size"))
            substation_header_layout.add_widget(substation_header)

            # If substation is Thessaloniki, show a red filled label next to the name
            try:
                c.execute(
                    "SELECT is_thessaloniki FROM substations WHERE id=?",
                    (substation_id,),
                )
                row = c.fetchone()
                is_th = bool(row[0]) if row and row[0] else False
            except Exception:
                is_th = False

            if is_th:
                th_label = Button(
                    text=S["MESSAGES"].get(
                        "SUBSTATION_IS_THESSALONIKI", "Υ/Σ Θεσσαλονίκης"
                    ),
                    size_hint_x=0.2,
                    background_color=(1, 0, 0, 1),
                    color=(1, 1, 1, 1),
                    background_normal="",
                    background_down="",
                )
                # keep as a visual tag (no-op) but not disabled so text color remains bright
                th_label.bind(on_press=lambda *a: None)
                substation_header_layout.add_widget(th_label)

            # Add button to jump to substation elements view
            jump_btn = Button(text="Μετάβαση στον Υποσταθμό", size_hint_x=0.2)
            jump_btn.bind(
                on_press=lambda x, sname=substation_name, p=popup: jump_to_substation(
                    app_instance, sname, p
                )
            )
            substation_header_layout.add_widget(jump_btn)

            grid.add_widget(substation_header_layout)

            for elem_data in active_elements:
                add_element_box(elem_data, False)

            if inactive_elements:
                inactive_label = Label(
                    text=f"[b][color=ff0000]Ανενεργά ({inactive_count})[/color][/b]",
                    size_hint_y=None,
                    height=30,
                    markup=True,
                    halign="left",
                    valign="middle",
                )
                inactive_label.bind(size=inactive_label.setter("text_size"))
                grid.add_widget(inactive_label)

                for elem_data in inactive_elements:
                    add_element_box(elem_data, True)

        scroll.add_widget(grid)
        main_layout.add_widget(scroll)
    else:
        # No usages found
        no_usage_label = Label(text=S["MESSAGES"]["MODEL_NOT_USED"], size_hint_y=0.7)
        main_layout.add_widget(no_usage_label)

    # Close button
    close_btn = Button(text="Κλείσιμο", size_hint_y=0.1)
    close_btn.bind(on_press=popup.dismiss)
    main_layout.add_widget(close_btn)

    popup.content = main_layout
    popup.open()
