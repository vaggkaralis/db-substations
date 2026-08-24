"""
Delegating wrappers for element-related UI functions in `DBrun.py`.
These thin wrappers call the app instance methods to keep behavior unchanged
while allowing incremental extraction.
"""

import sqlite3
import unicodedata

from breaker_model_utils import infer_breaker_model_values
from maintenance_type_utils import (
    is_recurring_maintenance_type as _is_recurring_maintenance_type,
)
from strings_proxy import STRINGS as S
from onedrive_hybrid_storage import (
    resolve_shared_root,
    sync_substation_gate_folders,
    sync_transformer_subelement_folders,
)
from validation import validate_breaker_category_required, validate_gate_assignment
from ui.shared import IconOnlyButton

# Common placeholder used in multiple UI helpers
unreg = S["MESSAGES"].get("UNREGISTERED_PLACEHOLDER", "(Μη καταχωρημένο)")


def _get_allowed_gates_for_selection(
    app, substation_id, element_type, *, breaker_type=None, is_main_switch=None
):
    is_interconnection = False
    if element_type in app.BREAKER_ELEMENT_TYPES:
        if breaker_type is not None:
            is_interconnection = breaker_type == S["MESSAGES"].get(
                "BREAKER_LABEL_INTERCON", "Διασυνδετικός"
            )
        else:
            is_interconnection = is_main_switch == 2
    return list(app.get_available_gates(substation_id, is_interconnection))


def _normalize_gate_spinner_text(gate_text, allowed_gates):
    gate_text = str(gate_text or "").strip()
    if not gate_text or gate_text == unreg:
        return unreg
    if gate_text in allowed_gates:
        return gate_text
    return unreg


def _validate_registered_gate_selection(gate_text, allowed_gates):
    gate_text = str(gate_text or "").strip()
    if not gate_text or gate_text == unreg:
        return True
    if gate_text not in allowed_gates:
        raise ValueError(
            "Η επιλεγμένη πύλη δεν είναι καταχωρημένη για αυτόν τον υποσταθμό."
        )
    return True


def _get_latest_recurring_maintenance_date(cursor, element_id):
    cursor.execute(
        """
        SELECT m.date_time, m.maintenance_type
        FROM maintenance m
        JOIN maintenance_elements me ON me.maintenance_id = m.id
        WHERE me.element_id = ?
        ORDER BY m.date_time DESC, m.id DESC
        """,
        (element_id,),
    )
    for date_time, maintenance_type in cursor.fetchall() or []:
        if _is_recurring_maintenance_type(maintenance_type):
            return date_time
    return None


def _normalize_element_name(value):
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("\u00a0", " ")
    return " ".join(text.split())


def _coerce_float(value):
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def _format_power_mva(value):
    numeric_value = _coerce_float(value)
    if numeric_value is None:
        return ""
    return f"{numeric_value:.3f}".rstrip("0").rstrip(".")


def _resolve_selected_model_power_mva(
    element_type, selected_model, fallback_power_mva=None
):
    if not selected_model:
        return _coerce_float(fallback_power_mva)

    rated_current_a = _coerce_float(selected_model.get("rated_normal_current_a"))
    _effective_current, inferred_power = infer_breaker_model_values(
        element_type,
        selected_model.get("model_name") or "",
        rated_current_a,
    )
    if inferred_power is not None:
        return inferred_power

    model_power = _coerce_float(selected_model.get("power_mva"))
    if model_power is not None:
        return model_power

    return _coerce_float(fallback_power_mva)


def _apply_selected_model_to_element_fields(
    *,
    field_inputs,
    rated_power_input=None,
    element_type,
    selected_model,
    fallback_power_mva=None,
):
    if not selected_model:
        return

    manufacturer_input = field_inputs.get("manufacturer")
    if manufacturer_input is not None:
        manufacturer_input.text = selected_model.get("manufacturer") or ""

    maintenance_cycle_input = field_inputs.get("maintenance_cycle")
    if maintenance_cycle_input is not None:
        maintenance_cycle_input.text = str(selected_model.get("maintenance_cycle") or 0)

    installation_space_input = field_inputs.get("installation_space")
    if installation_space_input is not None:
        installation_space_input.text = selected_model.get("installation_space") or ""

    resolved_power = _resolve_selected_model_power_mva(
        element_type,
        selected_model,
        fallback_power_mva=fallback_power_mva,
    )
    if resolved_power is not None and rated_power_input is not None:
        rated_power_input.text = _format_power_mva(resolved_power)


def _table_has_column(conn, table_name, column_name):
    cursor = conn.cursor()
    try:
        cursor.execute(f"PRAGMA table_info({table_name})")
        rows = cursor.fetchall() or []
        return any(row[1] == column_name for row in rows)
    except Exception:
        return False


def _show_no_history_maintenance_options(
    app,
    *,
    element_id,
    element_name,
    substation_id,
    substation_name,
    parent_popup,
):
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup

    prompt_popup = Popup(
        title=S["MESSAGES"]
        .get(
            "ELEMENT_MAINT_HISTORY_TITLE",
            "Ιστορικό Συντήρησης - {element_name}",
        )
        .format(element_name=element_name or ""),
        size_hint=(0.72, 0.34),
    )
    content = BoxLayout(orientation="vertical", padding=10, spacing=10)
    content.add_widget(
        Label(
            text=(
                "Δεν υπάρχει ιστορικό συντηρήσεων για αυτό το στοιχείο. "
                "Θέλετε να καταχωρήσετε νέα συντήρηση ή να το συνδέσετε με υπάρχουσα;"
            )
        )
    )
    buttons = BoxLayout(size_hint_y=None, height=44, spacing=8)

    def _open_new(_instance=None):
        prompt_popup.dismiss()
        app.show_maintenance_menu_for_substation(
            substation_id,
            substation_name,
            parent_popup,
            preselected_element_id=element_id,
            preselected_element_name=element_name,
        )

    def _open_existing(_instance=None):
        prompt_popup.dismiss()
        app._show_element_maintenance_link_popup(
            substation_id=substation_id,
            substation_name=substation_name,
            element_id=element_id,
            element_name=element_name,
            history_popup=prompt_popup,
            parent_display_popup=parent_popup,
        )

    add_btn = Button(text="Νέα συντήρηση")
    add_btn.bind(on_press=_open_new)
    buttons.add_widget(add_btn)

    existing_btn = Button(text="Σύνδεση με υπάρχουσα")
    existing_btn.bind(on_press=_open_existing)
    buttons.add_widget(existing_btn)

    cancel_btn = Button(text=S["BUTTONS"].get("CANCEL", "Ακύρωση"))
    cancel_btn.bind(on_press=prompt_popup.dismiss)
    buttons.add_widget(cancel_btn)

    content.add_widget(buttons)
    prompt_popup.content = content
    prompt_popup.open()


def _find_duplicate_element_id(
    conn, substation_id, raw_name, exclude_id=None, gate=None, parent_element_id=None
):
    """Find an element with the same name in a substation.

    If `gate` is provided, only consider duplicates that are in the same gate.
    When `gate` is None, preserve previous behaviour (any gate in the substation).
    """
    normalized_name = _normalize_element_name(raw_name)
    if not normalized_name:
        return None

    has_gate = _table_has_column(conn, "elements", "gate")
    has_parent_element_id = _table_has_column(conn, "elements", "parent_element_id")

    params = [substation_id]
    # Always fetch gate when available so callers can decide match semantics.
    if has_gate:
        parent_expr = "parent_element_id" if has_parent_element_id else "NULL"
        sql = f"SELECT id, name, COALESCE(gate, ''), {parent_expr} FROM elements WHERE substation_id=?"
    else:
        parent_expr = "parent_element_id" if has_parent_element_id else "NULL"
        sql = f"SELECT id, name, '', {parent_expr} FROM elements WHERE substation_id=?"
    if exclude_id is not None:
        sql += " AND id!=?"
        params.append(exclude_id)

    cursor = conn.cursor()
    cursor.execute(sql, params)
    for (
        existing_id,
        existing_name,
        existing_gate,
        existing_parent_id,
    ) in cursor.fetchall():
        if _normalize_element_name(existing_name) != normalized_name:
            continue
        if int(existing_parent_id or 0) != int(parent_element_id or 0):
            continue
        # If gate specified, require gate equality (string compare of normalized display)
        if gate is not None:
            if str(existing_gate or "") == str(gate or ""):
                return existing_id
            else:
                continue
        # No gate specified: any matching name in substation is a duplicate
        return existing_id
    return None


def _get_subelement_rows(conn, parent_element_id):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            e.id,
            e.element_type,
            e.name,
            e.serial_number,
            e.maintenance_date,
            e.manufacturer,
            e.vector_group,
            e.operating_status,
            e.element_model_id,
            em.model_name,
            em.manufacturer AS model_manufacturer
        FROM elements e
        LEFT JOIN element_models em ON em.id = e.element_model_id
        WHERE e.parent_element_id = ?
        ORDER BY e.element_type, e.name
        """,
        (parent_element_id,),
    )
    return cursor.fetchall() or []


def _get_descendant_element_ids(conn, parent_element_id):
    pending = [int(parent_element_id)]
    descendants = []
    cursor = conn.cursor()
    while pending:
        current_id = pending.pop()
        cursor.execute(
            "SELECT id FROM elements WHERE parent_element_id=? ORDER BY id",
            (current_id,),
        )
        child_ids = [int(row[0]) for row in (cursor.fetchall() or [])]
        descendants.extend(child_ids)
        pending.extend(child_ids)
    return descendants


def _get_matching_element_rows(
    conn,
    *,
    element_id=None,
    substation_id=None,
    parent_element_id=None,
    raw_name=None,
    element_type=None,
    exclude_id=None,
):
    has_gate = _table_has_column(conn, "elements", "gate")
    has_element_type = _table_has_column(conn, "elements", "element_type")
    has_parent_element_id = _table_has_column(conn, "elements", "parent_element_id")

    if element_id is not None:
        cursor = conn.cursor()
        parent_expr = "parent_element_id" if has_parent_element_id else "NULL"
        if has_element_type:
            cursor.execute(
                f"SELECT substation_id, {parent_expr}, name, element_type FROM elements WHERE id=?",
                (element_id,),
            )
        else:
            cursor.execute(
                f"SELECT substation_id, {parent_expr}, name, NULL FROM elements WHERE id=?",
                (element_id,),
            )
        row = cursor.fetchone()
        if not row:
            return []
        substation_id, parent_element_id, raw_name, element_type = row

    normalized_name = _normalize_element_name(raw_name)
    if substation_id is None or not normalized_name:
        return []

    params = [substation_id]
    gate_expr = "COALESCE(gate, '')" if has_gate else "''"
    type_expr = "element_type" if has_element_type else "NULL"
    parent_expr = "parent_element_id" if has_parent_element_id else "NULL"
    sql = f"SELECT id, name, {gate_expr}, {type_expr}, {parent_expr} FROM elements WHERE substation_id=?"
    if exclude_id is not None:
        sql += " AND id!=?"
        params.append(exclude_id)

    cursor = conn.cursor()
    cursor.execute(sql, params)
    matches = []
    for (
        existing_id,
        existing_name,
        existing_gate,
        existing_type,
        existing_parent_id,
    ) in cursor.fetchall():
        if _normalize_element_name(existing_name) != normalized_name:
            continue
        if element_type and existing_type != element_type:
            continue
        if int(existing_parent_id or 0) != int(parent_element_id or 0):
            continue
        matches.append((existing_id, existing_name, existing_gate, existing_type))
    return matches


def _get_element_reference_counts(conn, element_id):
    cursor = conn.cursor()
    counts = {}
    for key, table in (
        ("maintenance", "maintenance_elements"),
        ("reports", "maintenance_report_paths"),
        ("dga", "dga_measurements"),
        ("isolations", "isolation_request_elements"),
    ):
        try:
            cursor.execute(
                f"SELECT COUNT(*) FROM {table} WHERE element_id=?", (element_id,)
            )
            counts[key] = int(cursor.fetchone()[0] or 0)
        except sqlite3.OperationalError:
            counts[key] = 0
    counts["total"] = sum(counts.values())
    return counts


def _choose_canonical_element_id(conn, candidate_ids, preferred_id=None):
    candidate_ids = [int(cid) for cid in (candidate_ids or []) if cid is not None]
    if not candidate_ids:
        return None

    def _sort_key(candidate_id):
        counts = _get_element_reference_counts(conn, candidate_id)
        return (
            -int(counts.get("maintenance", 0) > 0),
            -counts.get("total", 0),
            0 if candidate_id == preferred_id else 1,
            candidate_id,
        )

    return min(candidate_ids, key=_sort_key)


def _merge_duplicate_elements(conn, keep_id, duplicate_ids):
    duplicate_ids = sorted(
        {int(cid) for cid in (duplicate_ids or []) if cid != keep_id}
    )
    if not duplicate_ids:
        return []

    cursor = conn.cursor()
    placeholders = ",".join(["?"] * len(duplicate_ids))

    for duplicate_id in duplicate_ids:
        cursor.execute(
            """
            DELETE FROM maintenance_elements
            WHERE element_id=?
              AND EXISTS (
                  SELECT 1
                  FROM maintenance_elements me2
                  WHERE me2.maintenance_id = maintenance_elements.maintenance_id
                    AND me2.element_id = ?
              )
            """,
            (duplicate_id, keep_id),
        )
    cursor.execute(
        f"UPDATE maintenance_elements SET element_id=? WHERE element_id IN ({placeholders})",
        [keep_id] + duplicate_ids,
    )

    for duplicate_id in duplicate_ids:
        cursor.execute(
            """
            DELETE FROM maintenance_report_paths
            WHERE element_id=?
              AND EXISTS (
                  SELECT 1
                  FROM maintenance_report_paths mr2
                  WHERE mr2.maintenance_id = maintenance_report_paths.maintenance_id
                    AND mr2.report_type = maintenance_report_paths.report_type
                    AND mr2.element_id = ?
              )
            """,
            (duplicate_id, keep_id),
        )
    cursor.execute(
        f"UPDATE maintenance_report_paths SET element_id=? WHERE element_id IN ({placeholders})",
        [keep_id] + duplicate_ids,
    )

    cursor.execute(
        f"UPDATE dga_measurements SET element_id=? WHERE element_id IN ({placeholders})",
        [keep_id] + duplicate_ids,
    )

    for duplicate_id in duplicate_ids:
        cursor.execute(
            """
            DELETE FROM isolation_request_elements
            WHERE element_id=?
              AND EXISTS (
                  SELECT 1
                  FROM isolation_request_elements ire2
                  WHERE ire2.request_id = isolation_request_elements.request_id
                    AND ire2.element_id = ?
              )
            """,
            (duplicate_id, keep_id),
        )
    cursor.execute(
        f"UPDATE isolation_request_elements SET element_id=? WHERE element_id IN ({placeholders})",
        [keep_id] + duplicate_ids,
    )

    cursor.execute(f"DELETE FROM elements WHERE id IN ({placeholders})", duplicate_ids)
    # After moving references and deleting duplicates, refresh the kept
    # element's maintenance_date to reflect any moved maintenance records.
    try:
        new_date = _get_latest_recurring_maintenance_date(cursor, keep_id)
        cursor.execute(
            "UPDATE elements SET maintenance_date=? WHERE id=?",
            (new_date, keep_id),
        )
    except Exception:
        pass

    return duplicate_ids


def _dismiss_popup_safely(popup):
    if popup is None:
        return
    try:
        popup.dismiss()
    except Exception:
        pass


def _capture_substation_popup_state(app, *popups, fallback_filter_name=None):
    seen = set()
    pending = list(popups)

    while pending:
        popup = pending.pop(0)
        if popup is None:
            continue

        popup_id = id(popup)
        if popup_id in seen:
            continue
        seen.add(popup_id)

        if hasattr(popup, "_dbs_filter_name"):
            prev_scroll_y = None
            try:
                prev_scroll_y = app._get_popup_scroll_y(popup)
            except Exception:
                prev_scroll_y = None

            filter_name = getattr(popup, "_dbs_filter_name", None)
            if filter_name is None:
                filter_name = fallback_filter_name

            return {
                "filter_name": filter_name,
                "element_type_filter": getattr(popup, "_dbs_element_type_filter", None),
                "gate_filter": getattr(popup, "_dbs_gate_filter", None),
                "prev_scroll_y": prev_scroll_y,
            }

        origin_popup = getattr(popup, "_dbs_origin_popup", None)
        if origin_popup is not None:
            pending.append(origin_popup)

    return {
        "filter_name": fallback_filter_name,
        "element_type_filter": None,
        "gate_filter": None,
        "prev_scroll_y": None,
    }


def _restore_substation_popup_state(app, state, *, reuse_popup=None):
    state = state or {}
    return app._display_substations(
        state.get("filter_name"),
        reuse_popup=reuse_popup,
        element_type_filter=state.get("element_type_filter"),
        gate_filter=state.get("gate_filter"),
        prev_scroll_y=state.get("prev_scroll_y"),
    )


def _element_has_valid_maintenance_history(conn, element_id):
    matches = _get_matching_element_rows(conn, element_id=element_id)
    element_ids = [row[0] for row in matches]
    if not element_ids:
        return False

    cursor = conn.cursor()
    placeholders = ",".join(["?"] * len(element_ids))
    cursor.execute(
        f"""
        SELECT 1
        FROM maintenance_elements me
        JOIN maintenance m ON m.id = me.maintenance_id
        WHERE me.element_id IN ({placeholders})
        LIMIT 1
        """,
        element_ids,
    )
    return cursor.fetchone() is not None


def _get_element_maintenance_history_ids(conn, element_id):
    matches = _get_matching_element_rows(conn, element_id=element_id)
    element_ids = [row[0] for row in matches]
    if not element_ids:
        return []

    cursor = conn.cursor()
    placeholders = ",".join(["?"] * len(element_ids))
    cursor.execute(
        f"""
        SELECT DISTINCT m.id, m.date_time
        FROM maintenance_elements me
        JOIN maintenance m ON m.id = me.maintenance_id
        WHERE me.element_id IN ({placeholders})
        ORDER BY m.date_time DESC, m.id DESC
        """,
        element_ids,
    )
    return [row[0] for row in cursor.fetchall()]


def show_add_element_popup_delegate(app, instance=None):
    return app.show_add_element_popup(instance)


def show_add_element_popup_for_substation_delegate(
    app, substation_id, parent_popup=None
):
    return app.show_add_element_popup_for_substation(substation_id, parent_popup)


def show_edit_element_popup_delegate(
    app, element_id, substation_id, parent_popup, substation_name=None
):
    return app.show_edit_element_popup(
        element_id, substation_id, parent_popup, substation_name
    )


def show_inactive_elements_delegate(app, substation_id, substation_name, parent_popup):
    return app.show_inactive_elements(substation_id, substation_name, parent_popup)


def show_element_maintenance_history_delegate(
    app, element_id, element_name, parent_popup
):
    return app.show_element_maintenance_history(element_id, element_name, parent_popup)


def show_maintenance_element_details_delegate(app, maintenance_id, element_id):
    return app.show_maintenance_element_details(maintenance_id, element_id)


def show_manage_subelements_popup(
    app,
    parent_element_id,
    parent_element_name,
    substation_id,
    substation_name,
    parent_popup=None,
):
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.scrollview import ScrollView

    from reports import show_confirm

    popup = Popup(
        title=f"Υποστοιχεία: {parent_element_name}",
        size_hint=(0.86, 0.82),
    )
    popup._dbs_origin_popup = parent_popup
    main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    header = BoxLayout(size_hint_y=None, height=44, spacing=8)
    header.add_widget(
        Label(text=f"Μετασχηματιστής: {parent_element_name}", size_hint_x=0.6)
    )
    add_btn = Button(text="+ Υποστοιχείο", size_hint_x=0.22)
    close_btn = Button(text=S["BUTTONS"]["CLOSE"], size_hint_x=0.18)
    close_btn.bind(on_press=popup.dismiss)
    header.add_widget(add_btn)
    header.add_widget(close_btn)
    main_layout.add_widget(header)

    scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
    grid = BoxLayout(orientation="vertical", size_hint_y=None, spacing=8)
    grid.bind(minimum_height=grid.setter("height"))
    scroll.add_widget(grid)
    main_layout.add_widget(scroll)

    def _delete_subelement(child_id, child_name):
        descendant_ids = _get_descendant_element_ids(app.conn, child_id)
        delete_ids = descendant_ids + [child_id]

        def _confirm_delete():
            cursor = app.conn.cursor()
            placeholders = ",".join(["?"] * len(delete_ids))
            cursor.execute(
                f"DELETE FROM elements WHERE id IN ({placeholders})",
                delete_ids,
            )
            for deleted_id in delete_ids:
                app._append_change_log("delete", "elements", {"id": deleted_id})
            try:
                sync_substation_gate_folders(
                    app.conn, substation_id, db_path=getattr(app, "db_path", None)
                )
                sync_transformer_subelement_folders(
                    app.conn, substation_id, db_path=getattr(app, "db_path", None)
                )
            except Exception:
                pass
            app.conn.commit()
            render_rows()

        msg = f'Είστε σίγουροι ότι θέλετε να διαγράψετε το υποστοιχείο "{child_name}";'
        if descendant_ids:
            msg += f"\n\nΘα διαγραφούν επίσης {len(descendant_ids)} υποστοιχεία."
        show_confirm(
            S["TITLES"].get("INFO", "Επιβεβαίωση"),
            msg,
            yes_callback=_confirm_delete,
            yes_color=(1, 0, 0, 1),
        )

    def render_rows():
        grid.clear_widgets()
        rows = _get_subelement_rows(app.conn, parent_element_id)
        if not rows:
            grid.add_widget(
                Label(
                    text="Δεν υπάρχουν καταχωρημένα υποστοιχεία για αυτόν τον μετασχηματιστή.",
                    size_hint_y=None,
                    height=36,
                )
            )
            return

        for row in rows:
            (
                child_id,
                child_type,
                child_name,
                serial_number,
                maintenance_date,
                manufacturer,
                vector_group,
                operating_status,
                _model_id,
                model_name,
                model_manufacturer,
            ) = row
            child_box = BoxLayout(orientation="vertical", size_hint_y=None, height=86)
            info = (
                f"[b]{child_name}[/b] - {child_type}\n"
                f"S/N: {serial_number or '-'} | Κατ.: {model_manufacturer or manufacturer or '-'} | "
                f"Μοντ.: {model_name or '-'} | Κατάσταση: {operating_status or '-'} | "
                f"Τελ. Συντ.: {maintenance_date or '-'}"
            )
            if vector_group:
                info += f" | Vector group: {vector_group}"
            child_box.add_widget(
                Label(text=info, markup=True, size_hint_y=None, height=52)
            )

            btn_row = BoxLayout(size_hint_y=None, height=30, spacing=6)
            view_btn = IconOnlyButton(
                icon_type="eye",
                icon_color=app.theme.get("text", (0.12, 0.12, 0.12, 1)),
            )
            view_btn.bind(
                on_press=lambda _x, eid=child_id: app._show_element_quick_view(eid)
            )
            btn_row.add_widget(view_btn)

            edit_btn = IconOnlyButton(
                icon_type="edit",
                icon_color=app.theme.get("primary", (0.2, 0.6, 1, 1)),
            )
            edit_btn.bind(
                on_press=lambda _x, eid=child_id, sid=substation_id, sname=substation_name, p=popup: (
                    app.show_edit_element_popup(eid, sid, p, sname)
                )
            )
            btn_row.add_widget(edit_btn)

            delete_btn = IconOnlyButton(
                icon_type="delete",
                icon_color=(1, 0.0, 0.0, 1),
            )
            delete_btn.bind(
                on_press=lambda _x, eid=child_id, ename=child_name: _delete_subelement(
                    eid, ename
                )
            )
            btn_row.add_widget(delete_btn)
            child_box.add_widget(btn_row)
            grid.add_widget(child_box)

    def _open_add_popup(_instance=None):
        show_add_subelement_popup(
            app,
            parent_element_id,
            parent_element_name,
            substation_id,
            substation_name,
            refresh_callback=render_rows,
        )

    add_btn.bind(on_press=_open_add_popup)
    render_rows()
    popup.content = main_layout
    popup.open()


def show_add_subelement_entry_popup(app, parent_popup=None):
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.spinner import Spinner

    from popups import show_message_popup

    cursor = app.conn.cursor()
    cursor.execute("SELECT id, name FROM substations ORDER BY name")
    substations = cursor.fetchall()
    if not substations:
        show_message_popup(
            S["TITLES"].get("ERROR", "Σφάλμα"),
            S["MESSAGES"].get("NO_SUBSTATIONS", "Δεν υπάρχουν υποσταθμοί!"),
        )
        return

    type_values = list(getattr(app, "TRANSFORMER_SUBELEMENT_TYPES", ["Motor Drive"]))
    selected_type = type_values[0] if type_values else ""

    popup = Popup(
        title=S["MESSAGES"].get("ADD_SUBELEMENT_TITLE", "Προσθήκη Υποστοιχείου"),
        size_hint=(0.82, 0.62),
    )
    main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    substation_map = {name: sub_id for sub_id, name in substations}
    parent_data = {}

    main_layout.add_widget(
        Label(
            text=S["MESSAGES"].get("SUBELEMENT_TYPE_LABEL", "Τύπος Υποστοιχείου:"),
            size_hint_y=None,
            height=30,
        )
    )
    type_spinner = Spinner(
        text=selected_type, values=type_values, size_hint_y=None, height=40
    )
    main_layout.add_widget(type_spinner)

    family_label = Label(
        text=S["MESSAGES"].get(
            "SUBELEMENT_PARENT_FAMILIES_LABEL",
            "Γονικές οικογένειες",
        )
        + ": "
        + ", ".join(
            getattr(
                app,
                "_get_subelement_parent_families",
                lambda _t: [
                    S["MESSAGES"].get("TRANSFORMER_FAMILY_LABEL", "Μετασχηματιστής")
                ],
            )(selected_type)
        ),
        size_hint_y=None,
        height=30,
    )
    main_layout.add_widget(family_label)

    main_layout.add_widget(
        Label(
            text=S["MESSAGES"].get("SELECT_SUBSTATION", "Επιλέξτε Υποσταθμό:"),
            size_hint_y=None,
            height=30,
        )
    )
    substation_spinner = Spinner(
        text=substations[0][1],
        values=[name for _sub_id, name in substations],
        size_hint_y=None,
        height=40,
    )
    main_layout.add_widget(substation_spinner)

    main_layout.add_widget(
        Label(
            text=S["MESSAGES"].get(
                "SUBELEMENT_PARENT_ELEMENT_LABEL", "Γονικό στοιχείο:"
            ),
            size_hint_y=None,
            height=30,
        )
    )
    parent_spinner = Spinner(text="", values=[], size_hint_y=None, height=40)
    main_layout.add_widget(parent_spinner)

    def _parent_family_label_for(selected_subelement_type):
        helper = getattr(app, "_get_subelement_parent_families", None)
        if callable(helper):
            try:
                families = [
                    family
                    for family in (helper(selected_subelement_type) or [])
                    if family
                ]
                if families:
                    return ", ".join(families)
            except Exception:
                pass
        return S["MESSAGES"].get("TRANSFORMER_FAMILY_LABEL", "Μετασχηματιστής")

    def _is_allowed_parent(elem_type, selected_subelement_type):
        helper = getattr(app, "_is_valid_parent_for_subelement", None)
        if callable(helper):
            try:
                return bool(helper(elem_type, selected_subelement_type))
            except Exception:
                pass
        transformer_helper = getattr(app, "_is_transformer", None)
        if callable(transformer_helper):
            try:
                return bool(transformer_helper(elem_type))
            except Exception:
                pass
        text = str(elem_type or "").strip().casefold()
        return "150/20" in text or "transform" in text or "μετασχημα" in text

    def load_parents(substation_name, selected_subelement_type):
        sub_id = substation_map.get(substation_name)
        parent_data.clear()
        if not sub_id:
            parent_spinner.values = []
            parent_spinner.text = ""
            return

        cursor.execute(
            """
            SELECT id, name, serial_number, gate, element_type
            FROM elements
            WHERE substation_id=? AND COALESCE(parent_element_id, 0)=0
            ORDER BY name
            """,
            (sub_id,),
        )
        rows = [
            row
            for row in cursor.fetchall() or []
            if _is_allowed_parent(row[4], selected_subelement_type)
        ]
        if not rows:
            parent_spinner.values = []
            parent_spinner.text = ""
            return

        parent_spinner.values = [
            f"{name} (S/N: {serial_number or '-'}, Gate: {gate or '-'})"
            for _id, name, serial_number, gate, _type in rows
        ]
        parent_spinner.text = parent_spinner.values[0]
        for row, display in zip(rows, parent_spinner.values):
            parent_data[display] = row

    def _sync_family_hint(text):
        family_label.text = (
            S["MESSAGES"].get("SUBELEMENT_PARENT_FAMILIES_LABEL", "Γονικές οικογένειες")
            + ": "
            + _parent_family_label_for(text)
        )

    def _on_substation_change(_spinner, text):
        load_parents(text, type_spinner.text)

    def _on_type_change(_spinner, text):
        _sync_family_hint(text)
        load_parents(substation_spinner.text, text)

    def _proceed(_instance=None):
        if not parent_spinner.text:
            show_message_popup(
                S["TITLES"].get("ERROR", "Σφάλμα"),
                S["MESSAGES"].get(
                    "DGA_SELECT_TRANSFORMER_REQUIRED",
                    "Παρακαλώ επιλέξτε ένα γονικό στοιχείο",
                ),
            )
            return

        row = parent_data.get(parent_spinner.text)
        if not row:
            show_message_popup(
                S["TITLES"].get("ERROR", "Σφάλμα"),
                S["MESSAGES"].get(
                    "DGA_SELECT_TRANSFORMER_REQUIRED",
                    "Παρακαλώ επιλέξτε ένα γονικό στοιχείο",
                ),
            )
            return

        parent_id, parent_name, _serial, _gate, _elem_type = row
        substation_name = substation_spinner.text
        substation_id = substation_map.get(substation_name)
        popup.dismiss()
        show_add_subelement_popup(
            app,
            parent_id,
            parent_name,
            substation_id,
            substation_name,
            preselected_type=type_spinner.text,
        )

    substation_spinner.bind(text=_on_substation_change)
    type_spinner.bind(text=_on_type_change)
    _sync_family_hint(type_spinner.text)
    load_parents(substation_spinner.text, type_spinner.text)

    buttons = BoxLayout(size_hint_y=None, height=48, spacing=10)
    proceed_btn = Button(text=S["BUTTONS"].get("CONTINUE", "Συνέχεια"))
    proceed_btn.bind(on_press=_proceed)
    buttons.add_widget(proceed_btn)
    cancel_btn = Button(text=S["BUTTONS"].get("CANCEL", "Ακύρωση"))
    cancel_btn.bind(on_press=popup.dismiss)
    buttons.add_widget(cancel_btn)
    main_layout.add_widget(buttons)

    if parent_popup:
        parent_popup.dismiss()
    popup.content = main_layout
    popup.open()


def show_add_subelement_popup(
    app,
    parent_element_id,
    parent_element_name,
    substation_id,
    substation_name,
    preselected_type=None,
    refresh_callback=None,
):
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.spinner import Spinner
    from kivy.uix.textinput import TextInput

    from popups import show_message_popup

    cursor = app.conn.cursor()
    cursor.execute(
        "SELECT gate, hemizygos, voltage_level FROM elements WHERE id=?",
        (parent_element_id,),
    )
    parent_row = cursor.fetchone()
    if not parent_row:
        show_message_popup(
            S["TITLES"].get("ERROR", "Σφάλμα"),
            S["MESSAGES"].get(
                "PARENT_ELEMENT_NOT_FOUND",
                "Το γονικό στοιχείο δεν βρέθηκε.",
            ),
        )
        return

    parent_gate = (
        parent_row[0] if isinstance(parent_row, (tuple, list)) else parent_row["gate"]
    )
    parent_hemizygos = (
        parent_row[1]
        if isinstance(parent_row, (tuple, list))
        else parent_row["hemizygos"]
    )
    parent_voltage = (
        parent_row[2]
        if isinstance(parent_row, (tuple, list))
        else parent_row["voltage_level"]
    )

    popup = Popup(
        title=f"Νέο Υποστοιχείο - {parent_element_name}", size_hint=(0.8, 0.84)
    )
    main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
    scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
    layout = BoxLayout(orientation="vertical", size_hint_y=None, padding=5, spacing=8)
    layout.bind(minimum_height=layout.setter("height"))

    layout.add_widget(
        Label(
            text=f"{S['MESSAGES'].get('SUBELEMENT_PARENT_ELEMENT_LABEL', 'Γονικό στοιχείο')}: {parent_element_name}",
            size_hint_y=None,
            height=30,
        )
    )
    layout.add_widget(Label(text="Τύπος Υποστοιχείου:", size_hint_y=None, height=30))
    type_values = list(getattr(app, "TRANSFORMER_SUBELEMENT_TYPES", ["Motor Drive"]))
    type_spinner = Spinner(
        text=(preselected_type if preselected_type in type_values else type_values[0]),
        values=type_values,
        size_hint_y=None,
        height=40,
    )
    layout.add_widget(type_spinner)

    layout.add_widget(Label(text="Όνομα Υποστοιχείου:", size_hint_y=None, height=30))
    name_input = TextInput(
        hint_text="Όνομα Υποστοιχείου", size_hint_y=None, height=40, multiline=False
    )
    layout.add_widget(name_input)

    layout.add_widget(Label(text="Σειριακός Αριθμός:", size_hint_y=None, height=30))
    serial_input = TextInput(
        hint_text="S/N", size_hint_y=None, height=40, multiline=False
    )
    layout.add_widget(serial_input)

    model_header = BoxLayout(size_hint_y=None, height=30, spacing=5)
    model_header.add_widget(
        Label(text=S["MESSAGES"].get("MODEL_LABEL", "Μοντέλο:"), size_hint_x=0.7)
    )
    add_model_btn = Button(
        text=S["BUTTONS"].get("ADD_MODEL", "+ Νέο Μοντέλο"), size_hint_x=0.3
    )
    model_header.add_widget(add_model_btn)
    layout.add_widget(model_header)
    model_spinner = Spinner(
        text=S["MESSAGES"].get("MODEL_SELECT_PROMPT", "Επιλέξτε μοντέλο"),
        values=[S["MESSAGES"].get("MODEL_SELECT_PROMPT", "Επιλέξτε μοντέλο")],
        size_hint_y=None,
        height=40,
    )
    layout.add_widget(model_spinner)

    layout.add_widget(Label(text="Κατασκευαστής:", size_hint_y=None, height=30))
    manufacturer_input = TextInput(
        hint_text="Κατασκευαστής", size_hint_y=None, height=40, multiline=False
    )
    layout.add_widget(manufacturer_input)

    layout.add_widget(Label(text="Έτος κατασκευής:", size_hint_y=None, height=30))
    manufacture_year_input = TextInput(
        hint_text="YYYY", size_hint_y=None, height=40, multiline=False
    )
    layout.add_widget(manufacture_year_input)

    layout.add_widget(Label(text="Τελευταία Συντήρηση:", size_hint_y=None, height=30))
    maintenance_date_input = TextInput(
        hint_text="YYYY-MM-DD", size_hint_y=None, height=40, multiline=False
    )
    layout.add_widget(maintenance_date_input)

    layout.add_widget(Label(text="Χώρος Εγκατάστασης:", size_hint_y=None, height=30))
    installation_space_spinner = Spinner(
        text=app.INSTALLATION_SPACE[0],
        values=app.INSTALLATION_SPACE,
        size_hint_y=None,
        height=40,
    )
    layout.add_widget(installation_space_spinner)

    layout.add_widget(Label(text="Λειτουργική Κατάσταση:", size_hint_y=None, height=30))
    operating_status_spinner = Spinner(
        text=app.OPERATING_STATUS[0],
        values=app.OPERATING_STATUS,
        size_hint_y=None,
        height=40,
    )
    layout.add_widget(operating_status_spinner)

    layout.add_widget(
        Label(text="Κύκλος Συντήρησης (έτη):", size_hint_y=None, height=30)
    )
    maintenance_cycle_input = TextInput(
        hint_text="Αριθμός", size_hint_y=None, height=40, multiline=False
    )
    layout.add_widget(maintenance_cycle_input)

    models_data = {}

    def _load_models(category):
        models_data_temp, display_names, _ = app._load_models_for_element_type(category)
        models_data.clear()
        models_data.update(models_data_temp)
        prompt = S["MESSAGES"].get("MODEL_SELECT_PROMPT", "Επιλέξτε μοντέλο")
        model_spinner.values = display_names if display_names else [prompt]
        model_spinner.text = display_names[0] if display_names else prompt

    def _on_model_selected(_spinner, text):
        model = models_data.get(text)
        if not model:
            return
        _apply_selected_model_to_element_fields(
            field_inputs={
                "manufacturer": manufacturer_input,
                "maintenance_cycle": maintenance_cycle_input,
                "installation_space": installation_space_spinner,
            },
            element_type=type_spinner.text,
            selected_model=model,
            fallback_power_mva=None,
        )

    def _on_type_changed(_spinner, text):
        _load_models(text)

    def _open_add_model(_instance=None):
        from model_management import show_add_model_popup

        show_add_model_popup(
            app,
            callback=lambda: _load_models(type_spinner.text),
            category=type_spinner.text,
        )

    add_model_btn.bind(on_press=_open_add_model)
    type_spinner.bind(text=_on_type_changed)
    model_spinner.bind(text=_on_model_selected)
    _load_models(type_spinner.text)

    scroll.add_widget(layout)
    main_layout.add_widget(scroll)

    buttons_layout = BoxLayout(size_hint_y=0.12, spacing=10)

    def _save_subelement():
        name_val = _normalize_element_name(name_input.text)
        if not name_val:
            show_message_popup(
                S["TITLES"]["ERROR"],
                S["MESSAGES"].get("ENTER_ELEMENT_NAME", "Συμπληρώστε όνομα στοιχείου."),
            )
            return
        try:
            maintenance_cycle_int = (
                int(maintenance_cycle_input.text)
                if maintenance_cycle_input.text.strip()
                else 0
            )
        except ValueError:
            show_message_popup(
                S["TITLES"]["ERROR"],
                S["MESSAGES"].get(
                    "MODEL_SERVICE_CYCLE_NUM",
                    "Ο κύκλος συντήρησης πρέπει να είναι αριθμός!",
                ),
            )
            return

        duplicate_id = _find_duplicate_element_id(
            app.conn,
            substation_id,
            name_val,
            parent_element_id=parent_element_id,
        )
        if duplicate_id is not None:
            show_message_popup(
                S["TITLES"]["ERROR"],
                S["MESSAGES"].get(
                    "ELEMENT_DUPLICATE",
                    f'Υπάρχει ήδη υποστοιχείο με όνομα "{name_val}" σε αυτόν τον μετασχηματιστή!',
                ),
            )
            return

        selected_model = models_data.get(model_spinner.text)
        model_id = selected_model.get("id") if selected_model else None
        model_name = (selected_model.get("model_name") or "") if selected_model else ""
        manufacturer = manufacturer_input.text.strip() or (
            (selected_model.get("manufacturer") or "") if selected_model else ""
        )

        cursor = app.conn.cursor()
        cursor.execute(
            """
            INSERT INTO elements (
                substation_id,
                parent_element_id,
                element_type,
                name,
                serial_number,
                maintenance_date,
                voltage_level,
                manufacturer,
                model,
                gate,
                hemizygos,
                installation_space,
                operating_status,
                maintenance_cycle,
                element_model_id,
                manufacture_year,
                model_version,
                is_main_switch,
                vector_group
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', 0, '')
            """,
            (
                substation_id,
                parent_element_id,
                type_spinner.text,
                name_val,
                serial_input.text.strip(),
                maintenance_date_input.text.strip(),
                parent_voltage or "",
                manufacturer,
                model_name,
                parent_gate or "",
                parent_hemizygos or "",
                installation_space_spinner.text,
                operating_status_spinner.text,
                maintenance_cycle_int,
                model_id,
                manufacture_year_input.text.strip(),
            ),
        )
        new_id = cursor.lastrowid
        app._append_change_log(
            "insert",
            "elements",
            {
                "id": new_id,
                "substation_id": substation_id,
                "parent_element_id": parent_element_id,
                "element_type": type_spinner.text,
                "name": name_val,
                "serial_number": serial_input.text.strip(),
                "maintenance_date": maintenance_date_input.text.strip(),
                "voltage_level": parent_voltage or "",
                "manufacturer": manufacturer,
                "model": model_name,
                "gate": parent_gate or "",
                "hemizygos": parent_hemizygos or "",
                "installation_space": installation_space_spinner.text,
                "operating_status": operating_status_spinner.text,
                "maintenance_cycle": maintenance_cycle_int,
                "element_model_id": model_id,
                "manufacture_year": manufacture_year_input.text.strip(),
            },
        )
        try:
            sync_substation_gate_folders(
                app.conn, substation_id, db_path=getattr(app, "db_path", None)
            )
            sync_transformer_subelement_folders(
                app.conn, substation_id, db_path=getattr(app, "db_path", None)
            )
        except Exception:
            pass
        app.conn.commit()
        popup.dismiss()
        if refresh_callback:
            refresh_callback()

    save_btn = Button(text=S["BUTTONS"]["SAVE"])
    save_btn.bind(on_press=lambda _x: _save_subelement())
    buttons_layout.add_widget(save_btn)
    cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
    cancel_btn.bind(on_press=popup.dismiss)
    buttons_layout.add_widget(cancel_btn)
    main_layout.add_widget(buttons_layout)
    popup.content = main_layout
    popup.open()


def show_add_element_popup(app, instance):
    from popups import show_message_popup

    # Get list of substations
    c = app.conn.cursor()
    c.execute("SELECT id, name FROM substations ORDER BY name")
    substations = c.fetchall()

    if not substations:
        show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["NO_SUBSTATIONS"])
        return

    # Get active people for responsible/crew selection
    c.execute(
        "SELECT id, name, role FROM people WHERE active=1 ORDER BY COALESCE(surname, name) COLLATE NOCASE"
    )
    people = c.fetchall()
    if not people:
        show_message_popup(
            S["TITLES"]["ERROR"],
            S["MESSAGES"]["NO_PEOPLE"],
            callback=lambda: app.show_people_management(None),
        )
        return

    # Store substations mapping for later use
    app.substations_map = {s[1]: s[0] for s in substations}

    # Create popup
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.spinner import Spinner
    from kivy.uix.textinput import TextInput

    popup = Popup(
        title=S["MESSAGES"].get("ADD_ELEMENT_TITLE", "Προσθήκη Στοιχείου"),
        size_hint=(0.8, 0.9),
    )
    main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    # Create scrollable area for inputs
    scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
    layout = BoxLayout(orientation="vertical", size_hint_y=None, padding=5, spacing=8)
    layout.bind(minimum_height=layout.setter("height"))

    # Substation spinner
    substation_names = list(app.substations_map.keys())
    layout.add_widget(
        Label(
            text=S["MESSAGES"].get("SELECT_SUBSTATION", "Επιλέξτε Υποσταθμό:"),
            size_hint_y=None,
            height=30,
        )
    )
    substation_spinner = Spinner(
        text=substation_names[0],
        values=substation_names,
        size_hint_y=None,
        height=40,
    )
    layout.add_widget(substation_spinner)

    # Element type spinner
    layout.add_widget(
        Label(
            text=S["MESSAGES"].get("SELECT_ELEMENT", "Επιλέξτε Στοιχείο:"),
            size_hint_y=None,
            height=30,
        )
    )
    element_spinner = Spinner(
        text=app.ELEMENT_TYPES[0],
        values=app.ELEMENT_TYPES,
        size_hint_y=None,
        height=40,
    )
    layout.add_widget(element_spinner)

    # Voltage level selection
    layout.add_widget(
        Label(
            text=S["MESSAGES"].get("VOLTAGE_LEVEL_LABEL", "Επίπεδο Τάσης:"),
            size_hint_y=None,
            height=30,
        )
    )
    _derived = app._derive_voltage_level(element_spinner.text)
    empty = S["MESSAGES"].get("EMPTY_PLACEHOLDER", "(Κενό)")
    initial_voltage = _derived or empty
    voltage_level_spinner = Spinner(
        text=initial_voltage,
        values=[_derived] if _derived else list(app.VOLTAGE_LEVELS),
        size_hint_y=None,
        height=40,
    )
    layout.add_widget(voltage_level_spinner)

    # Gate selection (auto-populated from transformers)
    gate_label = Label(
        text=S["MESSAGES"].get("GATE_LABEL", "Πύλη (Gate):"),
        size_hint_y=None,
        height=30,
    )
    layout.add_widget(gate_label)

    # Get initial gates for the first substation
    initial_gates = app.get_available_gates(app.substations_map[substation_names[0]])
    unreg = S["MESSAGES"].get("UNREGISTERED_PLACEHOLDER", "(Μη καταχωρημένο)")
    empty = S["MESSAGES"].get("EMPTY_PLACEHOLDER", "(Κενό)")
    gate_spinner = Spinner(
        text=initial_gates[0] if initial_gates else unreg,
        values=initial_gates if initial_gates else [unreg],
        size_hint_y=None,
        height=40,
    )
    layout.add_widget(gate_spinner)

    layout.add_widget(Label(text="Ημιζυγός:", size_hint_y=None, height=30))
    hemizygos_values = app.get_available_hemizygos_options()
    hemizygos_spinner = Spinner(
        text=hemizygos_values[0],
        values=hemizygos_values,
        size_hint_y=None,
        height=40,
    )
    layout.add_widget(hemizygos_spinner)

    # Rated power (Ονομαστική Ισχύς) - optional attribute for any element
    layout.add_widget(
        Label(
            text=S["MESSAGES"].get("RATED_POWER_LABEL", "Ονομαστική Ισχύς (MVA):"),
            size_hint_y=None,
            height=30,
        )
    )
    rated_power_input = TextInput(
        hint_text=S["MESSAGES"].get("RATED_POWER_HINT", "π.χ. 50"),
        size_hint_y=None,
        height=40,
        multiline=False,
    )
    layout.add_widget(rated_power_input)

    layout.add_widget(Label(text="Vector group:", size_hint_y=None, height=30))
    vector_group_input = TextInput(
        hint_text="π.χ. Dyn1",
        size_hint_y=None,
        height=40,
        multiline=False,
    )
    layout.add_widget(vector_group_input)

    # Update gates when substation changes
    def on_substation_change(spinner, text):
        substation_id = app.substations_map[text]
        if element_spinner.text in app.BREAKER_ELEMENT_TYPES:
            if breaker_type_spinner.text == S["MESSAGES"].get(
                "BREAKER_LABEL_INTERCON", "Διασυνδετικός"
            ):
                available_gates = app.get_available_gates(substation_id, True)
            else:
                available_gates = app.get_available_gates(substation_id, False)
        else:
            available_gates = app.get_available_gates(substation_id, False)
        gate_spinner.values = available_gates
        gate_spinner.text = available_gates[0] if available_gates else unreg

    substation_spinner.bind(text=on_substation_change)

    # Breaker type selection (Main or Line or Interconnection) - only for circuit breakers
    breaker_type_label = Label(
        text=S["MESSAGES"].get("BREAKER_TYPE_LABEL", "Τύπος Διακόπτη:"),
        size_hint_y=None,
        height=30,
    )
    breaker_type_spinner = Spinner(
        text=app.BREAKER_TYPES[0],
        values=app.BREAKER_TYPES,
        size_hint_y=None,
        height=40,
    )

    def on_breaker_type_change(spinner, text):
        substation_id = app.substations_map[substation_spinner.text]
        if element_spinner.text in app.BREAKER_ELEMENT_TYPES:
            if text == S["MESSAGES"].get("BREAKER_LABEL_INTERCON", "Διασυνδετικός"):
                available_gates = app.get_available_gates(substation_id, True)
            else:
                available_gates = app.get_available_gates(substation_id, False)
        else:
            available_gates = app.get_available_gates(substation_id, False)
        gate_spinner.values = available_gates
        gate_spinner.text = available_gates[0] if available_gates else unreg

    breaker_type_spinner.bind(text=on_breaker_type_change)

    # Breaker category filter (only for circuit breakers)
    breaker_category_label = Label(
        text=S["MESSAGES"].get("BREAKER_CATEGORY_LABEL", "Κατηγορία Διακόπτη:"),
        size_hint_y=None,
        height=30,
    )
    initial_breaker_categories = app._get_breaker_categories_for_element_type(
        element_spinner.text
    )
    breaker_category_spinner = Spinner(
        text=initial_breaker_categories[0] if initial_breaker_categories else "SF6",
        values=initial_breaker_categories,
        size_hint_y=None,
        height=40,
    )

    def on_breaker_category_change(spinner, text):
        try:
            current_element_type = element_spinner.text
        except Exception:
            current_element_type = None
        try:
            load_models_for_category(current_element_type, text)
        except Exception:
            pass

    breaker_category_spinner.bind(text=on_breaker_category_change)

    # Model selection with "Add New" button
    model_header = BoxLayout(size_hint_y=None, height=30, spacing=5)
    model_header.add_widget(
        Label(text=S["MESSAGES"].get("MODEL_LABEL", "Μοντέλο:"), size_hint_x=0.7)
    )
    add_model_btn = Button(
        text=S["BUTTONS"].get("ADD_MODEL", "+ Νέο Μοντέλο"),
        size_hint_x=0.3,
        size_hint_y=None,
        height=30,
    )
    model_header.add_widget(add_model_btn)
    layout.add_widget(model_header)

    model_spinner = Spinner(
        text=S["MESSAGES"].get("MODEL_SELECT_PROMPT", "Επιλέξτε μοντέλο"),
        values=[S["MESSAGES"].get("MODEL_SELECT_PROMPT", "Επιλέξτε μοντέλο")],
        size_hint_y=None,
        height=40,
    )
    layout.add_widget(model_spinner)

    # Store model data
    models_data = {}

    def load_models_for_category(category, selected_breaker_category=None):
        models_data_temp, display_names, _ = app._load_models_for_element_type(
            category, selected_breaker_category
        )
        models_data.clear()
        models_data.update(models_data_temp)

        if display_names:
            model_spinner.values = display_names
            model_spinner.text = display_names[0]
        else:
            prompt = S["MESSAGES"].get("MODEL_SELECT_PROMPT", "Επιλέξτε μοντέλο")
            model_spinner.values = [prompt]
            model_spinner.text = prompt

    def on_element_type_change(spinner, text):
        if text in app.BREAKER_ELEMENT_TYPES:
            breaker_category_options = app._get_breaker_categories_for_element_type(
                text
            )
            breaker_category_spinner.values = breaker_category_options
            if breaker_category_spinner.text not in breaker_category_options:
                breaker_category_spinner.text = (
                    breaker_category_options[0] if breaker_category_options else "SF6"
                )
            if breaker_category_label not in layout.children:
                idx = layout.children.index(model_header)
                layout.add_widget(breaker_category_spinner, index=idx + 1)
                layout.add_widget(breaker_category_label, index=idx + 2)
                breaker_category_spinner.bind(text=on_breaker_category_change)
            load_models_for_category(text, breaker_category_spinner.text)
        else:
            if breaker_category_label in layout.children:
                breaker_category_spinner.unbind(text=on_breaker_category_change)
                layout.remove_widget(breaker_category_label)
                layout.remove_widget(breaker_category_spinner)
            load_models_for_category(text, None)

        if text in app.BREAKER_ELEMENT_TYPES:
            if breaker_type_label not in layout.children:
                idx = layout.children.index(model_spinner)
                layout.add_widget(breaker_type_spinner, index=idx)
                layout.add_widget(breaker_type_label, index=idx + 1)
            substation_id = app.substations_map[substation_spinner.text]
            if breaker_type_spinner.text == S["MESSAGES"].get(
                "BREAKER_LABEL_INTERCON", "Διασυνδετικός"
            ):
                available_gates = app.get_available_gates(substation_id, True)
            else:
                available_gates = app.get_available_gates(substation_id, False)
            gate_spinner.values = available_gates
            gate_spinner.text = available_gates[0] if available_gates else unreg
        else:
            if breaker_type_label in layout.children:
                layout.remove_widget(breaker_type_label)
                layout.remove_widget(breaker_type_spinner)
            substation_id = app.substations_map[substation_spinner.text]
            available_gates = app.get_available_gates(substation_id, False)
            gate_spinner.values = available_gates
            gate_spinner.text = available_gates[0] if available_gates else unreg

        _derived = app._derive_voltage_level(text)
        voltage_level_spinner.values = (
            [_derived] if _derived else list(app.VOLTAGE_LEVELS)
        )
        voltage_level_spinner.text = _derived or empty

    element_spinner.bind(text=on_element_type_change)
    on_element_type_change(element_spinner, element_spinner.text)

    # Dynamic element fields (auto-filled from model, can be overridden)
    field_inputs = {}
    for field in app.ELEMENT_FIELD_DEFS:
        if field["key"] == "model":
            continue
        layout.add_widget(Label(text=f"{field['label']}:", size_hint_y=None, height=30))
        if field.get("type") == "spinner":
            spinner = Spinner(
                text=field["values"][0],
                values=field["values"],
                size_hint_y=None,
                height=40,
            )
            field_inputs[field["key"]] = spinner
            layout.add_widget(spinner)
        else:
            ti = TextInput(
                hint_text=field.get("hint", ""),
                size_hint_y=None,
                height=40,
                multiline=False,
            )
            field_inputs[field["key"]] = ti
            layout.add_widget(ti)

    def on_model_selected(spinner, text):
        model = models_data.get(text)
        if not model:
            return
        _apply_selected_model_to_element_fields(
            field_inputs=field_inputs,
            rated_power_input=rated_power_input,
            element_type=element_spinner.text,
            selected_model=model,
            fallback_power_mva=rated_power_input.text,
        )

    model_spinner.bind(text=on_model_selected)

    def open_add_model():
        from model_management import show_add_model_popup

        def reload_models():
            load_models_for_category(element_spinner.text)

        show_add_model_popup(app, callback=reload_models, category=element_spinner.text)

    add_model_btn.bind(on_press=lambda x: open_add_model())

    scroll.add_widget(layout)
    main_layout.add_widget(scroll)

    # Buttons layout
    buttons_layout = BoxLayout(size_hint_y=0.1, spacing=10)

    add_state = {"busy": False, "completed": False}

    def add_element():
        if add_state["busy"] or add_state["completed"]:
            return
        add_state["busy"] = True
        try:
            add_btn.disabled = True
        except Exception:
            pass

        try:
            substation_name = substation_spinner.text
            substation_id = app.substations_map[substation_name]
            element_type = element_spinner.text

            name_val = _normalize_element_name(
                field_inputs["name"].text
                if hasattr(field_inputs["name"], "text")
                else field_inputs["name"].text
            )
            if not name_val:
                show_message_popup(
                    S["TITLES"]["ERROR"], S["MESSAGES"]["ENTER_ELEMENT_NAME"]
                )
                return

            values = {
                key: (
                    field_inputs[key].text
                    if hasattr(field_inputs[key], "text")
                    else field_inputs[key].text
                )
                for key in field_inputs
            }
            values["name"] = name_val
            if "operating_status" in values and hasattr(
                field_inputs["operating_status"], "text"
            ):
                values["operating_status"] = field_inputs["operating_status"].text

            if element_type == app.ELEM_BREAKER_YT:
                is_main_switch = 1
            elif element_type == app.ELEM_BREAKER_MT:
                if breaker_type_spinner.text == S["MESSAGES"].get(
                    "BREAKER_LABEL_CENTRAL", "Κεντρικός"
                ):
                    is_main_switch = 1
                elif breaker_type_spinner.text == S["MESSAGES"].get(
                    "BREAKER_LABEL_INTERCON", "Διασυνδετικός"
                ):
                    is_main_switch = 2
                elif breaker_type_spinner.text == S["MESSAGES"].get(
                    "BREAKER_LABEL_CAPACITOR", "Διακόπτης Πυκνωτών"
                ):
                    is_main_switch = 3
                else:
                    is_main_switch = 0
            else:
                is_main_switch = 0

            gate_value = (
                gate_spinner.text
                if gate_spinner.text
                != S["MESSAGES"].get("UNREGISTERED_PLACEHOLDER", "(Μη καταχωρημένο)")
                else ""
            )
            hemizygos_value = (
                hemizygos_spinner.text
                if hemizygos_spinner.text
                != S["MESSAGES"].get("EMPTY_PLACEHOLDER", "(Κενό)")
                else ""
            )

            try:
                allowed_gates = _get_allowed_gates_for_selection(
                    app,
                    substation_id,
                    element_type,
                    breaker_type=breaker_type_spinner.text,
                )
                _validate_registered_gate_selection(gate_spinner.text, allowed_gates)
                validate_gate_assignment(
                    element_type, breaker_type_spinner.text, gate_value
                )
            except ValueError as e:
                show_message_popup(S["TITLES"]["ERROR"], str(e))
                return

            breaker_category_value = None
            if element_type in app.BREAKER_ELEMENT_TYPES:
                breaker_category_value = breaker_category_spinner.text

            try:
                validate_breaker_category_required(element_type, breaker_category_value)
            except ValueError as e:
                show_message_popup(S["TITLES"]["ERROR"], str(e))
                return

            model_id = None
            stored_model_name = ""
            selected_model = models_data.get(model_spinner.text)
            if model_spinner.text in models_data:
                model_id = selected_model["id"]
                stored_model_name = selected_model.get("model_name") or ""
            power_val_to_set = _resolve_selected_model_power_mva(
                element_type,
                selected_model,
                fallback_power_mva=rated_power_input.text,
            )

            maintenance_cycle = values.get("maintenance_cycle", "0")
            try:
                maintenance_cycle_int = (
                    int(maintenance_cycle) if maintenance_cycle else 0
                )
            except ValueError:
                show_message_popup(
                    S["TITLES"]["ERROR"],
                    S["MESSAGES"].get(
                        "MODEL_SERVICE_CYCLE_NUM",
                        "Ο κύκλος συντήρησης πρέπει να είναι αριθμός!",
                    ),
                )
                return

            c = app.conn.cursor()
            duplicate_id = _find_duplicate_element_id(app.conn, substation_id, name_val)
            if duplicate_id is not None:
                show_message_popup(
                    S["TITLES"]["ERROR"],
                    S["MESSAGES"].get(
                        "ELEMENT_DUPLICATE",
                        f'Υπάρχει ήδη στοιχείο με όνομα "{name_val}" σε αυτόν τον υποσταθμό!',
                    ),
                )
                return

            voltage_level_value = (
                voltage_level_spinner.text
                if voltage_level_spinner.text
                != S["MESSAGES"].get("EMPTY_PLACEHOLDER", "(Κενό)")
                else ""
            )

            try:
                c.execute(
                    "INSERT INTO elements (substation_id, element_type, name, serial_number, maintenance_date, voltage_level, manufacturer, model, model_version, installation_space, operating_status, maintenance_cycle, element_model_id, manufacture_year, gate, hemizygos, is_main_switch, breaker_category, power_mva, vector_group) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        substation_id,
                        element_type,
                        values.get("name", ""),
                        (values.get("serial_number", "") or "").strip(),
                        values.get("maintenance_date", ""),
                        voltage_level_value,
                        values.get("manufacturer", ""),
                        stored_model_name,
                        values.get("model_version", ""),
                        values.get("installation_space", "Εσωτερικός"),
                        values.get("operating_status", "Ενεργή"),
                        maintenance_cycle_int,
                        model_id,
                        values.get("manufacture_year", ""),
                        gate_value,
                        hemizygos_value,
                        is_main_switch,
                        breaker_category_value,
                        power_val_to_set,
                        vector_group_input.text.strip(),
                    ),
                )
            except sqlite3.IntegrityError:
                app.conn.rollback()
                show_message_popup(
                    S["TITLES"]["ERROR"],
                    S["MESSAGES"].get(
                        "ELEMENT_DUPLICATE",
                        f'Υπάρχει ήδη στοιχείο με όνομα "{name_val}" σε αυτόν τον υποσταθμό!',
                    ),
                )
                return

            element_id = c.lastrowid

            element_data = {
                "id": element_id,
                "substation_id": substation_id,
                "element_type": element_type,
                "name": values.get("name", ""),
                "serial_number": (values.get("serial_number", "") or "").strip(),
                "maintenance_date": values.get("maintenance_date", ""),
                "voltage_level": voltage_level_value,
                "manufacturer": values.get("manufacturer", ""),
                "model": stored_model_name,
                "model_version": values.get("model_version", ""),
                "installation_space": values.get("installation_space", "Εσωτερικός"),
                "operating_status": values.get("operating_status", "Ενεργή"),
                "maintenance_cycle": maintenance_cycle_int,
                "element_model_id": model_id,
                "manufacture_year": values.get("manufacture_year", ""),
                "gate": gate_value,
                "hemizygos": hemizygos_value,
                "is_main_switch": is_main_switch,
                "breaker_category": breaker_category_value,
                "vector_group": vector_group_input.text.strip(),
                "power_mva": power_val_to_set,
            }
            app._append_change_log("insert", "elements", element_data)

            try:
                sync_substation_gate_folders(
                    app.conn, substation_id, db_path=getattr(app, "db_path", None)
                )
                sync_transformer_subelement_folders(
                    app.conn, substation_id, db_path=getattr(app, "db_path", None)
                )
            except Exception as exc:
                app.conn.rollback()
                show_message_popup(
                    S["TITLES"].get("ERROR", "Σφάλμα"),
                    S["MESSAGES"]
                    .get(
                        "GATE_FOLDERS_SYNC_CREATE_FAILED_FMT",
                        "Failed to sync gate folders.\nElement creation was cancelled.\n\n{error}",
                    )
                    .format(error=str(exc)),
                )
                return

            app.conn.commit()

            add_state["completed"] = True
            _dismiss_popup_safely(popup)
            show_message_popup(
                S["TITLES"]["SUCCESS"],
                S["MESSAGES"].get(
                    "ELEMENT_ADDED", f"Στοιχείο προστέθηκε στον {substation_name}!"
                ),
                callback=lambda: app._display_substations(substation_name),
            )
        finally:
            add_state["busy"] = False
            if not add_state["completed"]:
                try:
                    add_btn.disabled = False
                except Exception:
                    pass

    add_btn = Button(text=S["BUTTONS"]["ADD"])
    add_btn.bind(on_press=lambda x: add_element())
    buttons_layout.add_widget(add_btn)

    cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
    cancel_btn.bind(on_press=popup.dismiss)
    buttons_layout.add_widget(cancel_btn)

    main_layout.add_widget(buttons_layout)
    popup.content = main_layout
    popup.open()


def _copy_common_delete_logic(
    app, element_id, substation_id, parent_popup, substation_name=None
):
    c = app.conn.cursor()
    c.execute(
        "SELECT element_type, gate, is_main_switch FROM elements WHERE id=?",
        (element_id,),
    )
    row = c.fetchone()
    if row:
        elem_type, gate, is_main = row
        if elem_type in app.BREAKER_ELEMENT_TYPES and is_main == 1:
            gate_value = gate or ""
            allowed_gates = _get_allowed_gates_for_selection(
                app,
                substation_id,
                elem_type,
                is_main_switch=is_main,
            )
            if not gate_value or gate_value not in allowed_gates:
                return True
            c.execute(
                "SELECT COUNT(*) FROM elements WHERE substation_id=? AND gate=? AND element_type=? AND is_main_switch=1 AND id!=?",
                (substation_id, gate_value, elem_type, element_id),
            )
            remaining = c.fetchone()[0]
            if remaining == 0:
                from popups import show_message_popup

                show_message_popup(
                    S["TITLES"].get("ERROR", "Σφάλμα"),
                    f"Η πύλη '{gate_value or S['MESSAGES'].get('UNREGISTERED_PLACEHOLDER', '(Μη καταχωρημένο)')}' πρέπει να έχει τουλάχιστον έναν κεντρικό {app.ELEM_BREAKER_YT if elem_type == app.ELEM_BREAKER_YT else app.ELEM_BREAKER_MT}.",
                )
                return False
    return True


def confirm_delete_element(
    app, element_id, element_name, substation_id, parent_popup, substation_name=None
):
    from reports import show_confirm

    def confirm():
        delete_element(app, element_id, substation_id, parent_popup, substation_name)

    show_confirm(
        S["TITLES"].get("INFO", "Επιβεβαίωση"),
        f'Είστε σίγουροι ότι θέλετε να διαγράψετε\nτο στοιχείο "{element_name}"?',
        yes_callback=confirm,
        yes_color=(1, 0, 0, 1),
    )


def delete_element(app, element_id, substation_id, parent_popup, substation_name=None):
    c = app.conn.cursor()
    if not _copy_common_delete_logic(
        app, element_id, substation_id, parent_popup, substation_name
    ):
        return

    refresh_state = _capture_substation_popup_state(
        app,
        parent_popup,
        fallback_filter_name=substation_name,
    )

    c.execute("DELETE FROM elements WHERE id=?", (element_id,))
    try:
        sync_substation_gate_folders(
            app.conn, substation_id, db_path=getattr(app, "db_path", None)
        )
        sync_transformer_subelement_folders(
            app.conn, substation_id, db_path=getattr(app, "db_path", None)
        )
    except Exception:
        pass
    app._append_change_log("delete", "elements", {"id": element_id})
    app.conn.commit()
    _restore_substation_popup_state(
        app,
        refresh_state,
        reuse_popup=parent_popup,
    )
    from popups import show_message_popup

    show_message_popup(S["TITLES"]["SUCCESS"], S["MESSAGES"]["ITEM_DELETED"])


def show_inactive_elements(app, substation_id, substation_name, parent_popup):
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.gridlayout import GridLayout
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.scrollview import ScrollView

    c = app.conn.cursor()
    c.execute(
        """
            SELECT e.id, e.element_type, e.name, e.serial_number, 
                   em.manufacturer as model_manufacturer, em.model_name, e.is_main_switch, em.manual_pdf
            FROM elements e 
            LEFT JOIN element_models em ON e.element_model_id = em.id
            WHERE e.substation_id=? AND e.operating_status='Ανενεργή' 
            ORDER BY e.name
        """,
        (substation_id,),
    )
    inactive_elements = c.fetchall()

    popup = Popup(title=f"Ανενεργά Στοιχεία - {substation_name}", size_hint=(0.8, 0.8))
    popup._dbs_origin_popup = parent_popup
    main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    if not inactive_elements:
        main_layout.add_widget(
            Label(
                text=S["MESSAGES"].get(
                    "NO_INACTIVE_ELEMENTS",
                    "Δεν υπάρχουν ανενεργά στοιχεία σε αυτόν τον υποσταθμό",
                ),
                size_hint_y=0.8,
            )
        )
    else:
        scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
        grid = GridLayout(cols=1, spacing=10, size_hint_y=None, padding=10)
        grid.bind(minimum_height=grid.setter("height"))

        for (
            elem_id,
            elem_type,
            elem_name,
            serial_number,
            model_manufacturer,
            model_name,
            is_main_switch,
            manual_pdf,
        ) in inactive_elements:
            elem_layout = BoxLayout(
                size_hint_y=None, height=80, spacing=5, orientation="vertical"
            )

            display_elem_type = elem_type
            # Keep display as-is; additional logic can be added later

            info_text = f"[b]{elem_name}[/b] - {display_elem_type}\nS/N: {serial_number or '-'} | Κατ.: {model_manufacturer or '-'} | Μοντ.: {model_name or '-'} (id:{elem_id})"
            elem_label = Label(text=info_text, size_hint_y=None, height=50, markup=True)
            elem_layout.add_widget(elem_label)

            btn_layout = BoxLayout(size_hint_y=None, height=30, spacing=5)

            # Add manual button if manual_pdf exists
            import os

            if manual_pdf and os.path.exists(manual_pdf):
                manual_btn = IconOnlyButton(
                    icon_type="book", icon_color=(0.8, 0.4, 0, 1), size=(30, 30)
                )
                manual_btn.size_hint_x = 0.15
                manual_btn.bind(
                    on_press=lambda x, mp=manual_pdf: app._open_model_manual(mp)
                )
                btn_layout.add_widget(manual_btn)

            # Add maintenance history button
            history_btn = IconOnlyButton(
                icon_type="maintenance", icon_color=(0.4, 0.6, 0.8, 1), size=(30, 30)
            )
            history_btn.size_hint_x = 0.2
            history_btn.bind(
                on_press=lambda x, eid=elem_id, ename=elem_name, p=popup: (
                    app.show_element_maintenance_history(eid, ename, p)
                )
            )
            btn_layout.add_widget(history_btn)

            edit_btn = IconOnlyButton(
                icon_type="edit",
                icon_color=app.theme.get("primary", (0.2, 0.6, 1, 1)),
                size=(30, 30),
            )
            edit_btn.size_hint_x = 0.2
            edit_btn.bind(
                on_press=lambda x, eid=elem_id, sid=substation_id, sname=substation_name, p=popup, gp=parent_popup: (
                    app.show_edit_element_popup(eid, sid, p, sname, gp)
                )
            )
            btn_layout.add_widget(edit_btn)

            elem_layout.add_widget(btn_layout)
            grid.add_widget(elem_layout)

        scroll.add_widget(grid)
        main_layout.add_widget(scroll)

    close_btn = Button(text=S["BUTTONS"]["CLOSE"], size_hint_y=0.1)
    close_btn.bind(on_press=popup.dismiss)
    main_layout.add_widget(close_btn)

    popup.content = main_layout
    popup.open()


def show_element_maintenance_history(app, element_id, element_name, parent_popup):
    from popups import show_message_popup

    matching_rows = _get_matching_element_rows(app.conn, element_id=element_id)
    matching_ids = [row[0] for row in matching_rows]
    canonical_element_id = _choose_canonical_element_id(
        app.conn, matching_ids, preferred_id=element_id
    )
    canonical_name = next(
        (row[1] for row in matching_rows if row[0] == canonical_element_id),
        element_name,
    )

    # Best-effort: refresh the canonical element's stored maintenance_date
    # in case references moved previously but the elements table wasn't updated.
    try:
        cur = app.conn.cursor()
        new_date = _get_latest_recurring_maintenance_date(
            cur, canonical_element_id or element_id
        )
        cur.execute(
            "UPDATE elements SET maintenance_date=? WHERE id=?",
            (new_date, canonical_element_id or element_id),
        )
        app.conn.commit()
    except Exception:
        pass

    c = app.conn.cursor()
    c.execute(
        """
        SELECT s.id, s.name
        FROM elements e
        JOIN substations s ON s.id = e.substation_id
        WHERE e.id = ?
        LIMIT 1
        """,
        (canonical_element_id or element_id,),
    )
    row = c.fetchone()
    if not row:
        show_message_popup(
            S["TITLES"].get("ERROR", "Σφάλμα"),
            S["MESSAGES"].get("ELEMENT_NOT_FOUND", "Το στοιχείο δεν βρέθηκε."),
        )
        return

    substation_id = row[0] if isinstance(row, (tuple, list)) else row["id"]
    substation_name = row[1] if isinstance(row, (tuple, list)) else row["name"]

    if not _element_has_valid_maintenance_history(
        app.conn, canonical_element_id or element_id
    ):
        _show_no_history_maintenance_options(
            app,
            element_id=canonical_element_id or element_id,
            element_name=canonical_name,
            substation_id=substation_id,
            substation_name=substation_name,
            parent_popup=parent_popup,
        )
        return

    maintenance_ids = _get_element_maintenance_history_ids(
        app.conn, canonical_element_id or element_id
    )

    app.show_substation_maintenance_history(
        substation_id,
        substation_name,
        parent_popup,
        preselected_element_id=canonical_element_id or element_id,
        preselected_element_name=canonical_name,
        include_maintenance_ids=maintenance_ids,
    )


def _export_single_maintenance_pdf(app, maintenance_id, element_id):
    """Export a single maintenance report to PDF with proper folder handling and duplicate checks"""
    from popups import show_message_popup
    from report_sync import safe_generate_and_store_report
    from reports import show_confirm

    try:
        # Get element info for messages
        cursor = app.conn.cursor()
        cursor.execute("SELECT name FROM elements WHERE id = ?", (element_id,))
        elem_row = cursor.fetchone()
        element_name = elem_row[0] if elem_row else f"Element {element_id}"

        # Use the report sync system to generate the report
        result = safe_generate_and_store_report(
            app.conn,
            maintenance_id=maintenance_id,
            element_id=element_id,
        )

        # If report exists, prompt user
        if result.get("action_taken") == "prompt_user":

            def _on_replace():
                result2 = safe_generate_and_store_report(
                    app.conn,
                    maintenance_id=maintenance_id,
                    element_id=element_id,
                    user_prompted_action="replace",
                )
                if result2["success"]:
                    show_message_popup(
                        S["TITLES"].get("SUCCESS", "Επιτυχία"),
                        f"Η αναφορά αντικαταστάθηκε.\n\n{element_name}",
                    )
                    if hasattr(app, "_open_file") and result2["path"]:
                        app._open_file(result2["path"])
                else:
                    show_message_popup(
                        S["TITLES"]["ERROR"],
                        f"Σφάλμα κατά την αντικατάσταση:\n{result2['message']}",
                    )

            def _on_open():
                result2 = safe_generate_and_store_report(
                    app.conn,
                    maintenance_id=maintenance_id,
                    element_id=element_id,
                    user_prompted_action="open",
                )
                if result2["success"] and result2["path"]:
                    if hasattr(app, "_open_file"):
                        app._open_file(result2["path"])
                    else:
                        show_message_popup(
                            S["TITLES"].get("SUCCESS", "Επιτυχία"),
                            f"Άνοιγμα αναφοράς:\n{result2['path']}",
                        )

            # Show confirmation: Replace or Open?
            show_confirm(
                S["TITLES"].get("CONFIRM", "Επιβεβαίωση"),
                f"Η αναφορά για {element_name} υπάρχει ήδη.\n\nΘέλετε να την αντικαταστήσετε;",
                yes_callback=_on_replace,
                yes_text=S["BUTTONS"].get("REPLACE", "Αντικατάσταση"),
                no_text=S["BUTTONS"].get("OPEN", "Άνοιγμα υπάρχουσας"),
            )
            return

        # Handle successful generation or other results
        if result["success"]:
            action_msg = (
                "ενημερώθηκε"
                if result.get("action_taken") == "replaced"
                else "δημιουργήθηκε"
            )
            show_message_popup(
                S["TITLES"].get("SUCCESS", "Επιτυχία"),
                f"PDF {action_msg} επιτυχώς.\n\n{element_name}",
            )
            # Open the PDF if on desktop
            if hasattr(app, "_open_file") and result["path"]:
                app._open_file(result["path"])
        else:
            show_message_popup(
                S["TITLES"]["ERROR"],
                f"Σφάλμα:\n{result.get('message', 'Άγνωστο σφάλμα')}",
            )

    except Exception as e:
        show_message_popup(
            S["TITLES"]["ERROR"], f"Σφάλμα κατά την εξαγωγή PDF:\n{str(e)}"
        )


def _export_maintenance_history_list(
    app, element_id, element_name, maintenance_records
):
    """Export the complete maintenance history list to PDF"""
    from popups import show_message_popup
    from datetime import datetime
    import os

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            SimpleDocTemplate,
            Table,
            TableStyle,
            Paragraph,
            Spacer,
        )
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from pdf_reports import MaintenanceReportGenerator

        pdf_gen = MaintenanceReportGenerator(app.conn)
        greek_font = getattr(pdf_gen, "greek_font", "Helvetica")

        def _nfc(text):
            if text is None or text == "":
                return "-"
            return pdf_gen.normalize_text(str(text))

        # Create output path under the configured shared root.
        shared_root = resolve_shared_root(getattr(app, "db_path", None))
        reports_dir = os.path.join(shared_root, "_EXPORTS", "maintenance_history")
        os.makedirs(reports_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = element_name.replace("/", "-").replace("\\", "-")
        output_path = os.path.join(
            reports_dir, f"MaintenanceHistory_{safe_name}_{timestamp}.pdf"
        )

        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=12 * mm,
            rightMargin=12 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
        )
        story = []
        styles = getSampleStyleSheet()

        # Title
        title_style = ParagraphStyle(
            "CustomTitle",
            parent=styles["Heading1"],
            fontSize=18,
            alignment=TA_CENTER,
            spaceAfter=20,
            fontName=greek_font,
        )
        title = Paragraph(
            _nfc(f"Ιστορικό Συντηρήσεων\n{element_name}").replace("\n", "<br/>"),
            title_style,
        )
        story.append(title)
        story.append(Spacer(1, 10 * mm))

        # Table data (use Paragraphs so long values wrap inside cells)
        header_cell_style = ParagraphStyle(
            "HeaderCell",
            parent=styles["Normal"],
            fontName=greek_font,
            fontSize=9,
            leading=11,
            alignment=TA_LEFT,
        )
        body_cell_style = ParagraphStyle(
            "BodyCell",
            parent=styles["Normal"],
            fontName=greek_font,
            fontSize=8,
            leading=10,
            alignment=TA_LEFT,
        )

        table_data = [
            [
                Paragraph(_nfc("Ημ/νία"), header_cell_style),
                Paragraph(_nfc("Υποσταθμός"), header_cell_style),
                Paragraph(_nfc("Τύπος"), header_cell_style),
                Paragraph(_nfc("Σχόλια Στοιχείου"), header_cell_style),
                Paragraph(_nfc("Μετρήσεις"), header_cell_style),
            ]
        ]

        for record in maintenance_records:
            if len(record) >= 14:
                (
                    maint_id,
                    date_time,
                    maint_type,
                    overall_comments,
                    element_comments,
                    substation_name,
                    _substation_id,
                    insul_fa_gnd,
                    insul_fb_gnd,
                    insul_fc_gnd,
                    contact_res_fa,
                    contact_res_fb,
                    contact_res_fc,
                    operations_count,
                ) = record[:14]
            else:
                (
                    maint_id,
                    date_time,
                    maint_type,
                    overall_comments,
                    element_comments,
                    substation_name,
                    insul_fa_gnd,
                    insul_fb_gnd,
                    insul_fc_gnd,
                    contact_res_fa,
                    contact_res_fb,
                    contact_res_fc,
                    operations_count,
                ) = record

            # Build measurements summary
            measurements = []
            if insul_fa_gnd:
                measurements.append(
                    f"{S['MESSAGES'].get('INSULATION_LABEL_FA_GND', 'FA-GND')}:{insul_fa_gnd}"
                )
            if insul_fb_gnd:
                measurements.append(
                    f"{S['MESSAGES'].get('INSULATION_LABEL_FB_GND', 'FB-GND')}:{insul_fb_gnd}"
                )
            if insul_fc_gnd:
                measurements.append(
                    f"{S['MESSAGES'].get('INSULATION_LABEL_FC_GND', 'FC-GND')}:{insul_fc_gnd}"
                )
            if contact_res_fa:
                measurements.append(
                    f"{S['MESSAGES'].get('PHASE_TO_PHASE_LABEL', 'FA-FA')}:{contact_res_fa}"
                )
            if contact_res_fb:
                measurements.append(
                    f"{S['MESSAGES'].get('INSULATION_LABEL_FB', 'FB-FB')}:{contact_res_fb}"
                )
            if contact_res_fc:
                measurements.append(
                    f"{S['MESSAGES'].get('INSULATION_LABEL_FC', 'FC-FC')}:{contact_res_fc}"
                )
            if operations_count:
                measurements.append(f"Λειτ.:{operations_count}")

            measurements_str = ", ".join(measurements) if measurements else "-"

            table_data.append(
                [
                    Paragraph(_nfc(date_time), body_cell_style),
                    Paragraph(_nfc(substation_name), body_cell_style),
                    Paragraph(_nfc(maint_type), body_cell_style),
                    Paragraph(_nfc(element_comments), body_cell_style),
                    Paragraph(_nfc(measurements_str), body_cell_style),
                ]
            )

        # Create table with widths that always fit printable page width
        col_widths = [
            doc.width * 0.16,  # Date
            doc.width * 0.20,  # Substation
            doc.width * 0.20,  # Type
            doc.width * 0.22,  # Element comments
            doc.width * 0.22,  # Measurements
        ]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), greek_font),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                    ("FONTNAME", (0, 1), (-1, -1), greek_font),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
                ]
            )
        )

        story.append(table)

        # Build PDF
        doc.build(story)

        # Open the PDF if on desktop
        if hasattr(app, "_open_file"):
            app._open_file(output_path)

        show_message_popup(
            S["TITLES"].get("SUCCESS", "Επιτυχία"),
            f"Λίστα ιστορικού εξήχθη στο:\n{output_path}",
        )
    except Exception as e:
        import traceback

        traceback.print_exc()
        show_message_popup(
            S["TITLES"]["ERROR"], f"Σφάλμα κατά τη δημιουργία λίστας PDF:\n{str(e)}"
        )


def show_edit_element_popup(
    app,
    element_id,
    substation_id,
    parent_popup,
    substation_name=None,
    grandparent_popup=None,
):
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.spinner import Spinner
    from kivy.uix.textinput import TextInput

    from popups import show_message_popup

    # Fetch element data
    c = app.conn.cursor()
    c.execute(
        "SELECT element_type, name, serial_number, maintenance_date, voltage_level, manufacturer, model, model_version, installation_space, operating_status, maintenance_cycle, manufacture_year, element_model_id, gate, hemizygos, is_main_switch, breaker_category, power_mva, vector_group, parent_element_id FROM elements WHERE id=?",
        (element_id,),
    )
    element = c.fetchone()

    if not element:
        show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["ELEMENT_NOT_FOUND"])
        return

    (
        elem_type,
        name,
        serial_num,
        maint_date,
        voltage_level,
        manufacturer,
        model,
        model_version,
        install_space,
        op_status,
        maint_cycle,
        manuf_year,
        model_id,
        gate,
        hemizygos,
        is_main_switch,
        breaker_category,
        power_mva,
        vector_group,
        parent_element_id,
    ) = element

    popup = Popup(title=f"Επεξεργασία: {name}", size_hint=(0.9, 0.9))
    popup._dbs_origin_popup = parent_popup
    main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
    layout = BoxLayout(orientation="vertical", size_hint_y=None, padding=5, spacing=8)
    layout.bind(minimum_height=layout.setter("height"))

    # Element type (read-only)
    layout.add_widget(
        Label(text=f"Τύπος: {elem_type}", size_hint_y=None, height=30, bold=True)
    )

    # Voltage level (dropdown)
    layout.add_widget(Label(text="Επίπεδο Τάσης:", size_hint_y=None, height=30))
    current_voltage = (
        voltage_level
        or app._derive_voltage_level(elem_type)
        or S["MESSAGES"].get("EMPTY_PLACEHOLDER", "(Κενό)")
    )
    _derived = app._derive_voltage_level(elem_type)
    voltage_options = [_derived] if _derived else list(app.VOLTAGE_LEVELS)
    if current_voltage not in voltage_options:
        voltage_options.append(current_voltage)
    voltage_level_spinner = Spinner(
        text=current_voltage, values=voltage_options, size_hint_y=None, height=40
    )
    layout.add_widget(voltage_level_spinner)

    # Rated power (Ονομαστική Ισχύς) - element attribute, editable here
    layout.add_widget(
        Label(text="Ονομαστική Ισχύς (MVA):", size_hint_y=None, height=30)
    )
    rated_power_input = TextInput(
        text=_format_power_mva(power_mva),
        size_hint_y=None,
        height=40,
        multiline=False,
    )
    layout.add_widget(rated_power_input)

    layout.add_widget(Label(text="Vector group:", size_hint_y=None, height=30))
    vector_group_input = TextInput(
        text=vector_group or "",
        hint_text="π.χ. Dyn1",
        size_hint_y=None,
        height=40,
        multiline=False,
    )
    layout.add_widget(vector_group_input)

    # Model selection
    breaker_category_label = Label(
        text=S["MESSAGES"].get("BREAKER_CATEGORY_LABEL", "Κατηγορία Διακόπτη:"),
        size_hint_y=None,
        height=30,
    )
    breaker_category_options = app._get_breaker_categories_for_element_type(elem_type)
    breaker_category_text = (
        breaker_category
        if breaker_category in breaker_category_options
        else (breaker_category_options[0] if breaker_category_options else "SF6")
    )
    breaker_category_spinner = Spinner(
        text=breaker_category_text,
        values=breaker_category_options,
        size_hint_y=None,
        height=40,
    )

    if elem_type in app.BREAKER_ELEMENT_TYPES:
        layout.add_widget(breaker_category_label)
        layout.add_widget(breaker_category_spinner)

    layout.add_widget(
        Label(
            text=S["MESSAGES"].get("MODEL_LABEL", "Μοντέλο:"),
            size_hint_y=None,
            height=30,
        )
    )

    # Load all models for this element type
    c.execute(
        "SELECT id, model_name, manufacturer, breaker_category FROM element_models WHERE element_category=? ORDER BY model_name",
        (elem_type,),
    )
    c.fetchall()

    models_data = {}
    model_spinner = Spinner(
        text="Επιλέξτε μοντέλο",
        values=["Επιλέξτε μοντέλο"],
        size_hint_y=None,
        height=40,
    )

    def load_models_for_breaker_category(selected_category):
        models_data_temp, display_names, selected_display_name = (
            app._load_models_for_element_type(elem_type, selected_category, model_id)
        )
        models_data.clear()
        models_data.update(models_data_temp)

        model_spinner.values = (
            display_names
            if display_names
            else [S["MESSAGES"].get("NO_MODELS", "Δεν υπάρχουν μοντέλα")]
        )
        model_spinner.text = (
            selected_display_name
            if selected_display_name and selected_display_name in model_spinner.values
            else model_spinner.values[0]
        )

    def on_model_selected(_spinner, text):
        selected_model = models_data.get(text)
        if not selected_model:
            return
        _apply_selected_model_to_element_fields(
            field_inputs=field_inputs,
            rated_power_input=rated_power_input,
            element_type=elem_type,
            selected_model=selected_model,
            fallback_power_mva=power_mva,
        )

    if elem_type in app.BREAKER_ELEMENT_TYPES:
        breaker_category_spinner.bind(
            text=lambda spinner, text: load_models_for_breaker_category(text)
        )
        load_models_for_breaker_category(breaker_category_spinner.text)
    else:
        load_models_for_breaker_category(None)

    layout.add_widget(model_spinner)

    # Gate selection
    layout.add_widget(
        Label(
            text=S["MESSAGES"].get("GATE_LABEL", "Πύλη (Gate):"),
            size_hint_y=None,
            height=30,
        )
    )
    available_gates = _get_allowed_gates_for_selection(
        app,
        substation_id,
        elem_type,
        is_main_switch=is_main_switch,
    )
    current_gate_text = _normalize_gate_spinner_text(gate, available_gates)
    gate_spinner = Spinner(
        text=current_gate_text, values=available_gates, size_hint_y=None, height=40
    )
    layout.add_widget(gate_spinner)

    layout.add_widget(Label(text="Ημιζυγός:", size_hint_y=None, height=30))
    hemizygos_values = app.get_available_hemizygos_options()
    current_hemizygos_text = (
        hemizygos if hemizygos else S["MESSAGES"].get("EMPTY_PLACEHOLDER", "(Κενό)")
    )
    if current_hemizygos_text not in hemizygos_values:
        hemizygos_values.append(current_hemizygos_text)
    hemizygos_spinner = Spinner(
        text=current_hemizygos_text,
        values=hemizygos_values,
        size_hint_y=None,
        height=40,
    )
    layout.add_widget(hemizygos_spinner)

    # Breaker type selection
    breaker_type_label = Label(
        text=S["MESSAGES"].get("BREAKER_TYPE_LABEL", "Τύπος Διακόπτη:"),
        size_hint_y=None,
        height=30,
    )
    if is_main_switch == 1:
        current_breaker_type = S["MESSAGES"].get("BREAKER_LABEL_CENTRAL", "Κεντρικός")
    elif is_main_switch == 2:
        current_breaker_type = S["MESSAGES"].get(
            "BREAKER_LABEL_INTERCON", "Διασυνδετικός"
        )
    elif is_main_switch == 3:
        current_breaker_type = S["MESSAGES"].get(
            "BREAKER_LABEL_CAPACITOR", "Διακόπτης Πυκνωτών"
        )
    else:
        current_breaker_type = S["MESSAGES"].get("BREAKER_LABEL_LINE", "Γραμμής")

    if elem_type == app.ELEM_BREAKER_YT:
        breaker_type_spinner = Spinner(
            text="Κεντρικός",
            values=["Κεντρικός"],
            size_hint_y=None,
            height=40,
            disabled=True,
        )
    else:
        breaker_type_spinner = Spinner(
            text=current_breaker_type,
            values=app.BREAKER_TYPES,
            size_hint_y=None,
            height=40,
        )

    def on_breaker_type_change(spinner, text):
        is_interconnection = text == S["MESSAGES"].get(
            "BREAKER_LABEL_INTERCON", "Διασυνδετικός"
        )
        available_gates = app.get_available_gates(substation_id, is_interconnection)
        gate_spinner.values = available_gates
        if gate_spinner.text not in available_gates:
            gate_spinner.text = available_gates[0] if available_gates else unreg

    breaker_type_spinner.bind(text=on_breaker_type_change)

    if elem_type in app.BREAKER_ELEMENT_TYPES:
        layout.add_widget(breaker_type_label)
        layout.add_widget(breaker_type_spinner)

    # Dynamic fields
    field_inputs = {}
    for field in app.ELEMENT_FIELD_DEFS:
        if field["key"] == "model":
            continue
        layout.add_widget(Label(text=f"{field['label']}:", size_hint_y=None, height=30))

        current_value = ""
        if field["key"] == "name":
            current_value = name or ""
        elif field["key"] == "serial_number":
            current_value = serial_num or ""
        elif field["key"] == "manufacture_year":
            current_value = manuf_year or ""
        elif field["key"] == "maintenance_date":
            current_value = maint_date or ""
        elif field["key"] == "manufacturer":
            current_value = manufacturer or ""
        elif field["key"] == "model_version":
            current_value = model_version or ""
        elif field["key"] == "installation_space":
            current_value = install_space or app.INSTALLATION_SPACE[0]
        elif field["key"] == "operating_status":
            current_value = op_status or app.OPERATING_STATUS[0]
        elif field["key"] == "maintenance_cycle":
            current_value = str(maint_cycle) if maint_cycle else "0"

        if field.get("type") == "spinner":
            spinner = Spinner(
                text=current_value,
                values=field["values"],
                size_hint_y=None,
                height=40,
            )
            field_inputs[field["key"]] = spinner
            layout.add_widget(spinner)
        else:
            ti = TextInput(
                text=current_value,
                hint_text=field.get("hint", ""),
                size_hint_y=None,
                height=40,
                multiline=False,
            )
            field_inputs[field["key"]] = ti
            layout.add_widget(ti)

    model_spinner.bind(text=on_model_selected)
    if model_spinner.text in models_data:
        on_model_selected(model_spinner, model_spinner.text)

    scroll.add_widget(layout)
    main_layout.add_widget(scroll)

    # Buttons
    buttons_layout = BoxLayout(size_hint_y=0.1, spacing=10)

    save_state = {"busy": False, "completed": False}

    def save_changes():
        if save_state["busy"] or save_state["completed"]:
            return
        save_state["busy"] = True
        try:
            save_btn.disabled = True
        except Exception:
            pass

        try:
            name_val = _normalize_element_name(field_inputs["name"].text)
            if not name_val:
                show_message_popup(
                    S["TITLES"]["ERROR"],
                    S["MESSAGES"].get("NAME_REQUIRED", "Το όνομα είναι υποχρεωτικό!"),
                )
                return

            try:
                cycle_val = (
                    int(field_inputs["maintenance_cycle"].text)
                    if field_inputs["maintenance_cycle"].text
                    else 0
                )
            except ValueError:
                show_message_popup(
                    "Σφάλμα", "Ο κύκλος συντήρησης πρέπει να είναι αριθμός!"
                )
                return

            c = app.conn.cursor()
            gate_value = (
                gate_spinner.text
                if gate_spinner.text
                != S["MESSAGES"].get("UNREGISTERED_PLACEHOLDER", "(Μη καταχωρημένο)")
                else ""
            )
            hemizygos_value = (
                hemizygos_spinner.text
                if hemizygos_spinner.text
                != S["MESSAGES"].get("EMPTY_PLACEHOLDER", "(Κενό)")
                else ""
            )

            matching_rows = _get_matching_element_rows(
                app.conn,
                substation_id=substation_id,
                parent_element_id=parent_element_id,
                raw_name=name_val,
                element_type=elem_type,
            )
            matching_ids = [row[0] for row in matching_rows]
            canonical_element_id = _choose_canonical_element_id(
                app.conn, matching_ids, preferred_id=element_id
            )
            merged_duplicate_ids = []

            duplicate_id = _find_duplicate_element_id(
                app.conn,
                substation_id,
                name_val,
                exclude_id=element_id,
                parent_element_id=parent_element_id,
            )
            if duplicate_id is not None and duplicate_id not in matching_ids:
                show_message_popup(
                    "Σφάλμα",
                    f'Υπάρχει ήδη στοιχείο με όνομα "{name_val}" σε αυτόν τον υποσταθμό!',
                )
                return

            if canonical_element_id is None:
                canonical_element_id = element_id
            merged_duplicate_ids = [
                match_id
                for match_id in matching_ids
                if match_id != canonical_element_id
            ]
            if merged_duplicate_ids:
                _merge_duplicate_elements(
                    app.conn, canonical_element_id, merged_duplicate_ids
                )
                # Refresh the canonical element's maintenance_date so the UI shows
                # the latest maintenance linked to it (merge may have moved records).
                try:
                    cur = app.conn.cursor()
                    new_date = _get_latest_recurring_maintenance_date(
                        cur, canonical_element_id
                    )
                    cur.execute(
                        "UPDATE elements SET maintenance_date=? WHERE id=?",
                        (new_date, canonical_element_id),
                    )
                except Exception:
                    # Best-effort refresh; don't break the save flow on failure
                    pass

            selected_model = models_data.get(model_spinner.text)
            new_model_id = selected_model["id"] if selected_model else None
            stored_model_name = (
                (selected_model.get("model_name") or "")
                if selected_model
                else (model or "")
            )

            # gate_value already computed above for the duplicate check

            breaker_category_value = None
            if elem_type in app.BREAKER_ELEMENT_TYPES:
                breaker_category_value = breaker_category_spinner.text

            if elem_type in app.BREAKER_ELEMENT_TYPES and (
                breaker_category_value is None
                or str(breaker_category_value).strip() == ""
            ):
                show_message_popup(
                    S["TITLES"].get("ERROR", "Σφάλμα"),
                    S["MESSAGES"].get(
                        "PLEASE_SELECT_BREAKER_CATEGORY",
                        "Η κατηγορία διακόπτη είναι υποχρεωτική για τους διακόπτες!",
                    ),
                )
                return

            if elem_type == app.ELEM_BREAKER_YT:
                new_is_main_switch = 1
            elif elem_type == app.ELEM_BREAKER_MT:
                if breaker_type_spinner.text == S["MESSAGES"].get(
                    "BREAKER_LABEL_CENTRAL", "Κεντρικός"
                ):
                    new_is_main_switch = 1
                elif breaker_type_spinner.text == S["MESSAGES"].get(
                    "BREAKER_LABEL_INTERCON", "Διασυνδετικός"
                ):
                    new_is_main_switch = 2
                elif breaker_type_spinner.text == S["MESSAGES"].get(
                    "BREAKER_LABEL_CAPACITOR", "Διακόπτης Πυκνωτών"
                ):
                    new_is_main_switch = 3
                else:
                    new_is_main_switch = 0
            else:
                new_is_main_switch = 0

            voltage_level_value = (
                voltage_level_spinner.text
                if voltage_level_spinner.text
                != S["MESSAGES"].get("EMPTY_PLACEHOLDER", "(Κενό)")
                else ""
            )

            try:
                allowed_gates = _get_allowed_gates_for_selection(
                    app,
                    substation_id,
                    elem_type,
                    breaker_type=breaker_type_spinner.text,
                )
                _validate_registered_gate_selection(gate_spinner.text, allowed_gates)
                validate_gate_assignment(
                    elem_type, breaker_type_spinner.text, gate_value
                )
            except ValueError as e:
                show_message_popup("Σφάλμα", str(e))
                return

            try:
                if elem_type in app.BREAKER_ELEMENT_TYPES:
                    if is_main_switch == 1 and (
                        new_is_main_switch != 1 or gate_value != (gate or "")
                    ):
                        old_gate = gate or ""
                        old_allowed_gates = _get_allowed_gates_for_selection(
                            app,
                            substation_id,
                            elem_type,
                            is_main_switch=is_main_switch,
                        )
                        if old_gate and old_gate in old_allowed_gates:
                            c.execute(
                                "SELECT COUNT(*) FROM elements WHERE substation_id=? AND gate=? AND element_type=? AND is_main_switch=1 AND id!=?",
                                (substation_id, old_gate, elem_type, element_id),
                            )
                            remaining = c.fetchone()[0]
                            if remaining == 0:
                                show_message_popup(
                                    S["TITLES"].get("ERROR", "Σφάλμα"),
                                    f"Η πύλη '{old_gate or S['MESSAGES'].get('UNREGISTERED_PLACEHOLDER', '(Μη καταχωρημένο)')}' πρέπει να έχει τουλάχιστον έναν κεντρικό {app.ELEM_BREAKER_YT if elem_type == app.ELEM_BREAKER_YT else app.ELEM_BREAKER_MT}.",
                                )
                                return
            except Exception:
                pass

            power_val_to_set = _resolve_selected_model_power_mva(
                elem_type,
                selected_model,
                fallback_power_mva=rated_power_input.text,
            )

            target_element_id = canonical_element_id or element_id

            try:
                c.execute(
                    """UPDATE elements SET 
                                    name=?, serial_number=?, maintenance_date=?, voltage_level=?, manufacturer=?, model=?, model_version=?,
                                    installation_space=?, operating_status=?, 
                                    maintenance_cycle=?, manufacture_year=?, element_model_id=?, gate=?, hemizygos=?, is_main_switch=?, breaker_category=?, power_mva=?, vector_group=?
                                    WHERE id=?""",
                    (
                        name_val,
                        field_inputs["serial_number"].text.strip(),
                        field_inputs["maintenance_date"].text.strip(),
                        voltage_level_value,
                        field_inputs["manufacturer"].text.strip(),
                        stored_model_name,
                        field_inputs["model_version"].text.strip(),
                        field_inputs["installation_space"].text,
                        field_inputs["operating_status"].text,
                        cycle_val,
                        field_inputs["manufacture_year"].text.strip(),
                        new_model_id,
                        gate_value,
                        hemizygos_value,
                        new_is_main_switch,
                        breaker_category_value,
                        power_val_to_set,
                        vector_group_input.text.strip(),
                        target_element_id,
                    ),
                )
            except sqlite3.IntegrityError:
                app.conn.rollback()
                show_message_popup(
                    "Σφάλμα",
                    f'Υπάρχει ήδη στοιχείο με όνομα "{name_val}" σε αυτόν τον υποσταθμό!',
                )
                return

            element_data = {
                "id": target_element_id,
                "substation_id": substation_id,
                "element_type": elem_type,
                "name": name_val,
                "serial_number": field_inputs["serial_number"].text.strip(),
                "maintenance_date": field_inputs["maintenance_date"].text.strip(),
                "voltage_level": voltage_level_value,
                "manufacturer": field_inputs["manufacturer"].text.strip(),
                "model": stored_model_name,
                "model_version": field_inputs["model_version"].text.strip(),
                "installation_space": field_inputs["installation_space"].text,
                "operating_status": field_inputs["operating_status"].text,
                "maintenance_cycle": cycle_val,
                "manufacture_year": field_inputs["manufacture_year"].text.strip(),
                "element_model_id": new_model_id,
                "gate": gate_value,
                "hemizygos": hemizygos_value,
                "is_main_switch": new_is_main_switch,
                "breaker_category": breaker_category_value,
                "power_mva": power_val_to_set,
                "vector_group": vector_group_input.text.strip(),
            }
            app._append_change_log("update", "elements", element_data)
            for duplicate_element_id in merged_duplicate_ids:
                app._append_change_log(
                    "delete", "elements", {"id": duplicate_element_id}
                )

            try:
                sync_substation_gate_folders(
                    app.conn, substation_id, db_path=getattr(app, "db_path", None)
                )
                sync_transformer_subelement_folders(
                    app.conn, substation_id, db_path=getattr(app, "db_path", None)
                )
            except Exception as exc:
                app.conn.rollback()
                show_message_popup(
                    S["TITLES"].get("ERROR", "Σφάλμα"),
                    S["MESSAGES"]
                    .get(
                        "GATE_FOLDERS_SYNC_EDIT_FAILED_FMT",
                        "Failed to sync gate folders.\nChanges were cancelled.\n\n{error}",
                    )
                    .format(error=str(exc)),
                )
                return

            app.conn.commit()

            refresh_state = _capture_substation_popup_state(
                app,
                parent_popup,
                grandparent_popup,
                fallback_filter_name=substation_name,
            )
            save_state["completed"] = True
            _dismiss_popup_safely(popup)
            _dismiss_popup_safely(parent_popup)
            _dismiss_popup_safely(grandparent_popup)
            if substation_name:
                show_message_popup(
                    "Επιτυχία",
                    "Οι αλλαγές αποθηκεύτηκαν!",
                    callback=lambda state=refresh_state: (
                        _restore_substation_popup_state(app, state)
                    ),
                )
            else:
                show_message_popup(
                    "Επιτυχία",
                    "Οι αλλαγές αποθηκεύτηκαν!",
                    callback=lambda: app.show_records(None),
                )
        finally:
            save_state["busy"] = False
            if not save_state["completed"]:
                try:
                    save_btn.disabled = False
                except Exception:
                    pass

    save_btn = Button(text=S["BUTTONS"]["SAVE"])
    save_btn.bind(on_press=lambda x: save_changes())
    buttons_layout.add_widget(save_btn)

    cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
    cancel_btn.bind(on_press=popup.dismiss)
    buttons_layout.add_widget(cancel_btn)

    main_layout.add_widget(buttons_layout)
    popup.content = main_layout
    popup.open()


def show_add_element_popup_for_substation(
    app, substation_id, substation_name, parent_popup
):
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.spinner import Spinner
    from kivy.uix.textinput import TextInput

    from popups import show_message_popup

    popup = Popup(
        title=S["MESSAGES"].get("ADD_ELEMENT_TITLE", "Προσθήκη Στοιχείου"),
        size_hint=(0.8, 0.9),
    )
    layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
    input_layout = BoxLayout(
        orientation="vertical", size_hint_y=None, padding=10, spacing=10
    )
    input_layout.bind(minimum_height=input_layout.setter("height"))

    input_layout.add_widget(Label(text="Υποσταθμός:", size_hint_y=None, height=30))
    c = app.conn.cursor()
    c.execute("SELECT id, name FROM substations ORDER BY name")
    all_substations = c.fetchall()

    substation_spinner = Spinner(
        text=substation_name,
        values=[sub[1] for sub in all_substations],
        size_hint_y=None,
        height=40,
    )
    input_layout.add_widget(substation_spinner)

    substation_map = {sub[1]: sub[0] for sub in all_substations}

    element_spinner = Spinner(
        text=app.ELEMENT_TYPES[0],
        values=app.ELEMENT_TYPES,
        size_hint_y=None,
        height=40,
    )
    input_layout.add_widget(
        Label(text="Επιλέξτε Τύπο Στοιχείου:", size_hint_y=None, height=30)
    )
    input_layout.add_widget(element_spinner)

    input_layout.add_widget(Label(text="Επίπεδο Τάσης:", size_hint_y=None, height=30))
    _derived = app._derive_voltage_level(element_spinner.text)
    initial_voltage = _derived or S["MESSAGES"].get("EMPTY_PLACEHOLDER", "(Κενό)")
    voltage_level_spinner = Spinner(
        text=initial_voltage,
        values=[_derived] if _derived else list(app.VOLTAGE_LEVELS),
        size_hint_y=None,
        height=40,
    )
    input_layout.add_widget(voltage_level_spinner)

    gate_label = Label(text="Πύλη (Gate):", size_hint_y=None, height=30)
    input_layout.add_widget(gate_label)

    initial_gates = app.get_available_gates(substation_id)
    gate_spinner = Spinner(
        text=(
            initial_gates[0]
            if initial_gates
            else S["MESSAGES"].get("UNREGISTERED_PLACEHOLDER", "(Μη καταχωρημένο)")
        ),
        values=(
            initial_gates
            if initial_gates
            else [S["MESSAGES"].get("UNREGISTERED_PLACEHOLDER", "(Μη καταχωρημένο)")]
        ),
        size_hint_y=None,
        height=40,
    )
    input_layout.add_widget(gate_spinner)

    input_layout.add_widget(Label(text="Ημιζυγός:", size_hint_y=None, height=30))
    hemizygos_values = app.get_available_hemizygos_options()
    hemizygos_spinner = Spinner(
        text=hemizygos_values[0],
        values=hemizygos_values,
        size_hint_y=None,
        height=40,
    )
    input_layout.add_widget(hemizygos_spinner)

    input_layout.add_widget(
        Label(
            text=S["MESSAGES"].get("RATED_POWER_LABEL", "Ονομαστική Ισχύς (MVA):"),
            size_hint_y=None,
            height=30,
        )
    )
    rated_power_input = TextInput(
        hint_text=S["MESSAGES"].get("RATED_POWER_HINT", "π.χ. 50"),
        size_hint_y=None,
        height=40,
        multiline=False,
    )
    input_layout.add_widget(rated_power_input)

    input_layout.add_widget(Label(text="Vector group:", size_hint_y=None, height=30))
    vector_group_input = TextInput(
        hint_text="π.χ. Dyn1",
        size_hint_y=None,
        height=40,
        multiline=False,
    )
    input_layout.add_widget(vector_group_input)

    def on_substation_change(spinner, text):
        selected_substation_id = substation_map[text]
        if element_spinner.text in app.BREAKER_ELEMENT_TYPES:
            if breaker_type_spinner.text == S["MESSAGES"].get(
                "BREAKER_LABEL_INTERCON", "Διασυνδετικός"
            ):
                available_gates = app.get_available_gates(selected_substation_id, True)
            else:
                available_gates = app.get_available_gates(selected_substation_id, False)
        else:
            available_gates = app.get_available_gates(selected_substation_id, False)
        gate_spinner.values = available_gates
        gate_spinner.text = (
            available_gates[0]
            if available_gates
            else S["MESSAGES"].get("UNREGISTERED_PLACEHOLDER", "(Μη καταχωρημένο)")
        )

    substation_spinner.bind(text=on_substation_change)

    breaker_type_label = Label(
        text=S["MESSAGES"].get("BREAKER_TYPE_LABEL", "Τύπος Διακόπτη:"),
        size_hint_y=None,
        height=30,
    )
    breaker_type_spinner = Spinner(
        text=app.BREAKER_TYPES[0],
        values=app.BREAKER_TYPES,
        size_hint_y=None,
        height=40,
    )

    def on_breaker_type_change(spinner, text):
        selected_substation_id = substation_map[substation_spinner.text]
        if element_spinner.text in app.BREAKER_ELEMENT_TYPES:
            if text == S["MESSAGES"].get("BREAKER_LABEL_INTERCON", "Διασυνδετικός"):
                available_gates = app.get_available_gates(selected_substation_id, True)
            else:
                available_gates = app.get_available_gates(selected_substation_id, False)
        else:
            available_gates = app.get_available_gates(selected_substation_id, False)
        gate_spinner.values = available_gates
        gate_spinner.text = available_gates[0] if available_gates else unreg

    breaker_type_spinner.bind(text=on_breaker_type_change)

    breaker_category_label = Label(
        text="Κατηγορία Διακόπτη:", size_hint_y=None, height=30
    )
    initial_breaker_categories = app._get_breaker_categories_for_element_type(
        element_spinner.text
    )
    breaker_category_spinner = Spinner(
        text=initial_breaker_categories[0] if initial_breaker_categories else "SF6",
        values=initial_breaker_categories,
        size_hint_y=None,
        height=40,
    )

    model_header = BoxLayout(size_hint_y=None, height=30, spacing=5)
    model_header.add_widget(Label(text="Μοντέλο:", size_hint_x=0.7))
    add_model_btn = Button(
        text="+ Νέο Μοντέλο", size_hint_x=0.3, size_hint_y=None, height=30
    )
    model_header.add_widget(add_model_btn)
    input_layout.add_widget(model_header)

    model_spinner = Spinner(
        text="Επιλέξτε μοντέλο",
        values=["Επιλέξτε μοντέλο"],
        size_hint_y=None,
        height=40,
    )
    input_layout.add_widget(model_spinner)

    models_data = {}

    def on_breaker_category_change(spinner, text):
        current_element_type = element_spinner.text
        load_models_for_category(current_element_type, text)

    def load_models_for_category(category, selected_breaker_category=None):
        c = app.conn.cursor()
        c.execute(
            "SELECT id, model_name, manufacturer, maintenance_cycle, installation_space, breaker_category FROM element_models WHERE element_category=? ORDER BY model_name",
            (category,),
        )
        models = c.fetchall()

        models_data.clear()
        if models:
            if category in app.BREAKER_ELEMENT_TYPES:
                if selected_breaker_category:
                    filtered_models = [
                        m
                        for m in models
                        if (m[5] or "").strip().lower()
                        == selected_breaker_category.lower()
                    ]
                else:
                    filtered_models = models
                display_names = []
                for m in filtered_models:
                    display_name = f"{m[1]} - {m[2] or 'N/A'}"
                    display_names.append(display_name)
                    models_data[display_name] = {
                        "id": m[0],
                        "model_name": m[1],
                        "manufacturer": m[2] or "",
                        "maintenance_cycle": m[3] or 0,
                        "installation_space": m[4] or "",
                        "breaker_category": m[5] or "",
                    }
                model_spinner.values = (
                    display_names
                    if display_names
                    else [S["MESSAGES"].get("NO_MODELS", "Δεν υπάρχουν μοντέλα")]
                )
                model_spinner.text = (
                    display_names[0]
                    if display_names
                    else S["MESSAGES"].get("NO_MODELS", "Δεν υπάρχουν μοντέλα")
                )
            else:
                display_names = []
                for m in models:
                    display_name = f"{m[1]} - {m[2] or 'N/A'}"
                    display_names.append(display_name)
                    models_data[display_name] = {
                        "id": m[0],
                        "model_name": m[1],
                        "manufacturer": m[2] or "",
                        "maintenance_cycle": m[3] or 0,
                        "installation_space": m[4] or "",
                        "breaker_category": m[5] or "",
                    }
                model_spinner.values = display_names
                prompt = S["MESSAGES"].get("MODEL_SELECT_PROMPT", "Επιλέξτε μοντέλο")
                model_spinner.text = display_names[0] if display_names else prompt
        else:
            prompt = S["MESSAGES"].get("MODEL_SELECT_PROMPT", "Επιλέξτε μοντέλο")
            model_spinner.values = [prompt]
            model_spinner.text = prompt

    def on_element_type_change(spinner, text):
        if text in app.BREAKER_ELEMENT_TYPES:
            breaker_category_options = app._get_breaker_categories_for_element_type(
                text
            )
            breaker_category_spinner.values = breaker_category_options
            if breaker_category_spinner.text not in breaker_category_options:
                breaker_category_spinner.text = (
                    breaker_category_options[0] if breaker_category_options else "SF6"
                )
            if breaker_category_label not in input_layout.children:
                idx = input_layout.children.index(model_header)
                input_layout.add_widget(breaker_category_spinner, index=idx + 1)
                input_layout.add_widget(breaker_category_label, index=idx + 2)
                breaker_category_spinner.bind(text=on_breaker_category_change)
            load_models_for_category(text, breaker_category_spinner.text)
        else:
            if breaker_category_label in input_layout.children:
                breaker_category_spinner.unbind(text=on_breaker_category_change)
                input_layout.remove_widget(breaker_category_label)
                input_layout.remove_widget(breaker_category_spinner)
            load_models_for_category(text, None)

        if text == app.ELEM_BREAKER_MT:
            if breaker_type_label not in input_layout.children:
                input_layout.add_widget(
                    breaker_type_spinner,
                    index=input_layout.children.index(gate_spinner) + 2,
                )
                input_layout.add_widget(
                    breaker_type_label,
                    index=input_layout.children.index(breaker_type_spinner) + 1,
                )
                if breaker_type_spinner.text == "Διασυνδετικός":
                    available_gates = app.get_available_gates(substation_id, True)
                else:
                    available_gates = app.get_available_gates(substation_id, False)
                gate_spinner.values = available_gates
                if gate_spinner.text not in available_gates:
                    gate_spinner.text = (
                        available_gates[0]
                        if available_gates
                        else S["MESSAGES"].get(
                            "UNREGISTERED_PLACEHOLDER", "(Μη καταχωρημένο)"
                        )
                    )
        else:
            if breaker_type_label in input_layout.children:
                input_layout.remove_widget(breaker_type_label)
                input_layout.remove_widget(breaker_type_spinner)
            available_gates = app.get_available_gates(substation_id, False)
            gate_spinner.values = available_gates
            if gate_spinner.text not in available_gates:
                gate_spinner.text = (
                    available_gates[0]
                    if available_gates
                    else S["MESSAGES"].get(
                        "UNREGISTERED_PLACEHOLDER", "(Μη καταχωρημένο)"
                    )
                )

        _derived = app._derive_voltage_level(text)
        voltage_level_spinner.values = (
            [_derived] if _derived else list(app.VOLTAGE_LEVELS)
        )
        voltage_level_spinner.text = _derived or S["MESSAGES"].get(
            "EMPTY_PLACEHOLDER", "(Κενό)"
        )

    element_spinner.bind(text=on_element_type_change)
    on_element_type_change(element_spinner, element_spinner.text)

    def on_model_selected(spinner, text):
        model = models_data.get(text)
        if not model:
            return
        _apply_selected_model_to_element_fields(
            field_inputs=field_inputs,
            rated_power_input=rated_power_input,
            element_type=element_spinner.text,
            selected_model=model,
            fallback_power_mva=rated_power_input.text,
        )

    model_spinner.bind(text=on_model_selected)

    def open_add_model(instance=None):
        from model_management import show_add_model_popup

        def reload_models():
            load_models_for_category(element_spinner.text)

        show_add_model_popup(app, callback=reload_models, category=element_spinner.text)

    add_model_btn.bind(on_press=open_add_model)

    field_inputs = {}
    for field in app.ELEMENT_FIELD_DEFS:
        if field["key"] == "model":
            continue
        input_layout.add_widget(
            Label(text=f"{field['label']}:", size_hint_y=None, height=30)
        )
        if field.get("type") == "spinner":
            spinner = Spinner(
                text=field["values"][0],
                values=field["values"],
                size_hint_y=None,
                height=40,
            )
            field_inputs[field["key"]] = spinner
            input_layout.add_widget(spinner)
        else:
            ti = TextInput(
                hint_text=field.get("hint", ""),
                size_hint_y=None,
                height=40,
                multiline=False,
            )
            field_inputs[field["key"]] = ti
            input_layout.add_widget(ti)

    if model_spinner.text in models_data:
        on_model_selected(model_spinner, model_spinner.text)

    scroll.add_widget(input_layout)
    layout.add_widget(scroll)

    buttons_layout = BoxLayout(size_hint_y=0.1, spacing=10)

    add_state = {"busy": False, "completed": False}

    def add_element():
        if add_state["busy"] or add_state["completed"]:
            return
        add_state["busy"] = True
        element_type = element_spinner.text
        values = {
            key: (
                field_inputs[key].text
                if hasattr(field_inputs[key], "text")
                else field_inputs[key].text
            )
            for key in field_inputs
        }
        if "operating_status" in values and hasattr(
            field_inputs["operating_status"], "text"
        ):
            values["operating_status"] = field_inputs["operating_status"].text

        values["name"] = _normalize_element_name(values.get("name"))

        if not values.get("name"):
            show_message_popup("Σφάλμα", "Παρακαλώ εισάγετε όνομα στοιχείου!")
            add_state["busy"] = False
            return

        if element_type == app.ELEM_BREAKER_YT:
            is_main_switch = 1
        elif element_type == app.ELEM_BREAKER_MT:
            if breaker_type_spinner.text == S["MESSAGES"].get(
                "BREAKER_LABEL_CENTRAL", "Κεντρικός"
            ):
                is_main_switch = 1
            elif breaker_type_spinner.text == S["MESSAGES"].get(
                "BREAKER_LABEL_INTERCON", "Διασυνδετικός"
            ):
                is_main_switch = 2
            elif breaker_type_spinner.text == S["MESSAGES"].get(
                "BREAKER_LABEL_CAPACITOR", "Διακόπτης Πυκνωτών"
            ):
                is_main_switch = 3
            else:
                is_main_switch = 0
        else:
            is_main_switch = 0

        gate_value = (
            gate_spinner.text
            if gate_spinner.text
            != S["MESSAGES"].get("UNREGISTERED_PLACEHOLDER", "(Μη καταχωρημένο)")
            else ""
        )
        hemizygos_value = (
            hemizygos_spinner.text
            if hemizygos_spinner.text
            != S["MESSAGES"].get("EMPTY_PLACEHOLDER", "(Κενό)")
            else ""
        )

        breaker_category_value = None
        if element_type in app.BREAKER_ELEMENT_TYPES:
            breaker_category_value = breaker_category_spinner.text

        if element_type in app.BREAKER_ELEMENT_TYPES and (
            breaker_category_value is None or str(breaker_category_value).strip() == ""
        ):
            show_message_popup(
                S["TITLES"]["ERROR"], S["MESSAGES"]["PLEASE_SELECT_BREAKER_CATEGORY"]
            )
            add_state["busy"] = False
            return

        try:
            maintenance_cycle_int = int(values.get("maintenance_cycle", "0") or 0)
        except ValueError:
            show_message_popup("Σφάλμα", "Ο κύκλος συντήρησης πρέπει να είναι αριθμός!")
            add_state["busy"] = False
            return

        selected_substation_name = substation_spinner.text
        selected_substation_id = substation_map[selected_substation_name]

        c = app.conn.cursor()
        duplicate_id = _find_duplicate_element_id(
            app.conn, selected_substation_id, values.get("name")
        )
        if duplicate_id is not None:
            show_message_popup(
                "Σφάλμα",
                f'Υπάρχει ήδη στοιχείο με όνομα "{values.get("name")}" σε αυτόν τον υποσταθμό!',
            )
            add_state["busy"] = False
            return

        model_id = None
        stored_model_name = ""
        selected_model = models_data.get(model_spinner.text)
        if model_spinner.text in models_data:
            model_id = selected_model["id"]
            stored_model_name = selected_model.get("model_name") or ""
        power_val_to_set = _resolve_selected_model_power_mva(
            element_type,
            selected_model,
            fallback_power_mva=rated_power_input.text,
        )

        voltage_level_value = (
            voltage_level_spinner.text
            if voltage_level_spinner.text
            != S["MESSAGES"].get("EMPTY_PLACEHOLDER", "(Κενό)")
            else ""
        )

        try:
            allowed_gates = _get_allowed_gates_for_selection(
                app,
                selected_substation_id,
                element_type,
                breaker_type=breaker_type_spinner.text,
            )
            _validate_registered_gate_selection(gate_spinner.text, allowed_gates)
            validate_gate_assignment(
                element_type, breaker_type_spinner.text, gate_value
            )
            c.execute(
                "INSERT INTO elements (substation_id, element_type, name, serial_number, maintenance_date, voltage_level, manufacturer, model, model_version, installation_space, operating_status, maintenance_cycle, element_model_id, manufacture_year, gate, hemizygos, is_main_switch, breaker_category, power_mva, vector_group) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    selected_substation_id,
                    element_type,
                    values.get("name", ""),
                    (values.get("serial_number", "") or "").strip(),
                    values.get("maintenance_date", ""),
                    voltage_level_value,
                    values.get("manufacturer", ""),
                    stored_model_name,
                    values.get("model_version", ""),
                    values.get("installation_space", "Εσωτερικός"),
                    values.get("operating_status", "Ενεργή"),
                    maintenance_cycle_int,
                    model_id,
                    values.get("manufacture_year", ""),
                    gate_value,
                    hemizygos_value,
                    is_main_switch,
                    breaker_category_value,
                    power_val_to_set,
                    vector_group_input.text.strip(),
                ),
            )
        except ValueError as e:
            show_message_popup(S["TITLES"].get("ERROR", "Σφάλμα"), str(e))
            add_state["busy"] = False
            return
        except sqlite3.IntegrityError:
            app.conn.rollback()
            show_message_popup(
                "Σφάλμα",
                f'Υπάρχει ήδη στοιχείο με όνομα "{values.get("name")}" σε αυτόν τον υποσταθμό!',
            )
            add_state["busy"] = False
            return
        element_id = c.lastrowid

        # Track change for desktop sync
        element_data = {
            "id": element_id,
            "substation_id": selected_substation_id,
            "element_type": element_type,
            "name": values.get("name", ""),
            "serial_number": (values.get("serial_number", "") or "").strip(),
            "maintenance_date": values.get("maintenance_date", ""),
            "voltage_level": voltage_level_value,
            "manufacturer": values.get("manufacturer", ""),
            "model": stored_model_name,
            "model_version": values.get("model_version", ""),
            "installation_space": values.get("installation_space", "Εσωτερικός"),
            "operating_status": values.get("operating_status", "Ενεργή"),
            "maintenance_cycle": maintenance_cycle_int,
            "element_model_id": model_id,
            "manufacture_year": values.get("manufacture_year", ""),
            "gate": gate_value,
            "hemizygos": hemizygos_value,
            "is_main_switch": is_main_switch,
            "breaker_category": breaker_category_value,
            "vector_group": vector_group_input.text.strip(),
            "power_mva": power_val_to_set,
        }
        app._append_change_log("insert", "elements", element_data)

        try:
            sync_substation_gate_folders(
                app.conn,
                selected_substation_id,
                db_path=getattr(app, "db_path", None),
            )
            sync_transformer_subelement_folders(
                app.conn,
                selected_substation_id,
                db_path=getattr(app, "db_path", None),
            )
        except Exception as exc:
            app.conn.rollback()
            show_message_popup(
                S["TITLES"].get("ERROR", "Σφάλμα"),
                S["MESSAGES"]
                .get(
                    "GATE_FOLDERS_SYNC_CREATE_FAILED_FMT",
                    "Failed to sync gate folders.\nElement creation was cancelled.\n\n{error}",
                )
                .format(error=str(exc)),
            )
            add_state["busy"] = False
            return

        app.conn.commit()

        refresh_state = _capture_substation_popup_state(
            app,
            parent_popup,
            fallback_filter_name=selected_substation_name,
        )
        if refresh_state.get("filter_name") != selected_substation_name:
            refresh_state["filter_name"] = selected_substation_name
            refresh_state["element_type_filter"] = None
            refresh_state["gate_filter"] = None

        add_state["completed"] = True
        _dismiss_popup_safely(popup)
        _dismiss_popup_safely(parent_popup)
        show_message_popup(
            "Επιτυχία",
            "Στοιχείο προστέθηκε!",
            callback=lambda state=refresh_state: _restore_substation_popup_state(
                app, state
            ),
        )

    add_btn = Button(text=S["BUTTONS"]["ADD"])
    add_btn.bind(on_press=lambda x: add_element())
    buttons_layout.add_widget(add_btn)

    cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
    cancel_btn.bind(on_press=popup.dismiss)
    buttons_layout.add_widget(cancel_btn)

    layout.add_widget(buttons_layout)
    popup.content = layout
    popup.open()
