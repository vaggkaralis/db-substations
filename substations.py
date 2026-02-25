"""
Delegating wrappers for substation-related UI functions.
These thin functions call methods on the `app` instance (SubstationApp).
They allow incremental extraction without changing the large `DBrun.py` logic.
"""
from strings_proxy import STRINGS as S


def show_add_substation_popup_delegate(app, instance=None):
    return app.show_add_substation_popup(instance)


def show_add_substation_popup_from_db_view_delegate(app, parent_popup):
    return app.show_add_substation_popup_from_db_view(parent_popup)


def show_records_delegate(app, instance=None):
    return app.show_records(instance)


def show_substation_selection_window_delegate(app, parent_popup, all_substations):
    return app._show_substation_selection_window(parent_popup, all_substations)


def show_substation_selection_window_with_callback_delegate(app, parent_popup, all_substations, on_select, title=None):
    if title is None:
        title = S["MESSAGES"].get("SELECT_SUBSTATION", "Επιλογή Υποσταθμού")
    return app._show_substation_selection_window_with_callback(parent_popup, all_substations, on_select, title=title)


def show_all_substations_delegate(app, selection_popup):
    return app._show_all_substations(selection_popup)


def show_specific_substation_from_window_delegate(app, substation_name, selection_popup):
    return app._show_specific_substation_from_window(substation_name, selection_popup)


def display_substations_delegate(app, filter_name=None, reuse_popup=None, element_type_filter=None, gate_filter=None, prev_scroll_y=None):
    return app._display_substations(filter_name=filter_name, reuse_popup=reuse_popup, element_type_filter=element_type_filter, gate_filter=gate_filter, prev_scroll_y=prev_scroll_y)


def show_edit_substation_popup_delegate(app, substation_id, substation_name, location, adoption_date, division, parent_popup):
    return app.show_edit_substation_popup(substation_id, substation_name, location, adoption_date, division, parent_popup)
