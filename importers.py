from typing import Callable

try:
    import pandas as pd
except ImportError:
    pd = None


def _clean_value(value):
    if pd is None:
        return value
    return str(value).strip() if pd.notna(value) else ''


def import_substations_from_excel(conn, file_path: str, on_success: Callable[[str], None], on_error: Callable[[str], None]) -> None:
    if pd is None:
        on_error('pandas δεν είναι εγκατεστημένο!')
        return

    try:
        cursor = conn.cursor()
        df_sub = pd.read_excel(file_path, sheet_name='Substations')
        count = 0
        duplicates = []

        for _, row in df_sub.iterrows():
            name = _clean_value(row.get('Name', ''))
            location = row.get('Location', '') if pd.notna(row.get('Location', '')) else ''
            adoption_date = row.get('Adoption Date', '') if pd.notna(row.get('Adoption Date', '')) else ''

            if name:
                cursor.execute('SELECT id FROM substations WHERE name=?', (name,))
                if cursor.fetchone():
                    duplicates.append(name)
                else:
                    cursor.execute(
                        'INSERT INTO substations (name, location, adoption_date) VALUES (?, ?, ?)',
                        (name, location, adoption_date),
                    )
                    count += 1

        conn.commit()

        if duplicates:
            dup_list = ', '.join(duplicates)
            msg = f'{count} νέοι υποσταθμοί εισήχθησαν.\nΥπάρχοντες (δεν εισήχθησαν): {dup_list}'
        else:
            msg = f'{count} υποσταθμοί εισήχθησαν με επιτυχία!'

        on_success(msg)
    except Exception as exc:
        on_error(f'Σφάλμα: {exc}')


def import_substations_from_csv(conn, file_path: str, on_success: Callable[[str], None], on_error: Callable[[str], None]) -> None:
    if pd is None:
        on_error('pandas δεν είναι εγκατεστημένο!')
        return

    try:
        cursor = conn.cursor()
        df_sub = pd.read_csv(file_path)
        count = 0
        duplicates = []

        for _, row in df_sub.iterrows():
            name = _clean_value(row.get('Name', ''))
            location = row.get('Location', '') if pd.notna(row.get('Location', '')) else ''
            adoption_date = row.get('Adoption Date', '') if pd.notna(row.get('Adoption Date', '')) else ''

            if name:
                cursor.execute('SELECT id FROM substations WHERE name=?', (name,))
                if cursor.fetchone():
                    duplicates.append(name)
                else:
                    cursor.execute(
                        'INSERT INTO substations (name, location, adoption_date) VALUES (?, ?, ?)',
                        (name, location, adoption_date),
                    )
                    count += 1

        conn.commit()

        if duplicates:
            dup_list = ', '.join(duplicates)
            msg = f'{count} νέοι υποσταθμοί εισήχθησαν.\nΥπάρχοντες (δεν εισήχθησαν): {dup_list}'
        else:
            msg = f'{count} υποσταθμοί εισήχθησαν με επιτυχία!'

        on_success(msg)
    except Exception as exc:
        on_error(f'Σφάλμα: {exc}')


def import_elements_from_excel(
    conn,
    file_path: str,
    on_success: Callable[[str], None],
    on_error: Callable[[str], None],
    on_duplicate: Callable[[str, str, str], bool] = None,
) -> None:
    """Import elements from Excel.

    on_duplicate(sub_name, name, serial_number) -> bool
    - True: replace existing element
    - False: skip existing element
    """

    if pd is None:
        on_error('pandas δεν είναι εγκατεστημένο!')
        return

    try:
        cursor = conn.cursor()
        df_elem = pd.read_excel(file_path, sheet_name='Elements')

        count = 0
        updated = 0
        skipped = 0
        not_found = []

        for _, row in df_elem.iterrows():
            sub_name = row.get('Substation Name', '')
            element_type = row.get('Element Type', '')
            name = row.get('Name', '')
            serial_number = row.get('Serial Number', '')
            maintenance_date = row.get('Maintenance Date', '')
            voltage_level = row.get('Voltage Level', '')
            manufacturer = row.get('Manufacturer', '')
            elem_type = row.get('Type', '')

            if sub_name and name:
                cursor.execute('SELECT id FROM substations WHERE name=?', (str(sub_name),))
                result = cursor.fetchone()
                if result:
                    sub_id = result[0]
                    name_str = str(name)
                    serial_str = str(serial_number) if pd.notna(serial_number) else ''

                    # Check for duplicate
                    cursor.execute(
                        'SELECT id FROM elements WHERE substation_id=? AND name=? AND serial_number=?',
                        (sub_id, name_str, serial_str)
                    )
                    existing = cursor.fetchone()

                    decision_replace = False
                    if existing:
                        if on_duplicate:
                            decision_replace = bool(on_duplicate(str(sub_name), name_str, serial_str))
                        else:
                            decision_replace = False

                    if existing and decision_replace:
                        cursor.execute(
                            'UPDATE elements SET element_type=?, maintenance_date=?, voltage_level=?, manufacturer=?, type=? WHERE id=?',
                            (
                                str(element_type) if pd.notna(element_type) else '',
                                str(maintenance_date) if pd.notna(maintenance_date) else '',
                                str(voltage_level) if pd.notna(voltage_level) else '',
                                str(manufacturer) if pd.notna(manufacturer) else '',
                                str(elem_type) if pd.notna(elem_type) else '',
                                existing[0]
                            )
                        )
                        updated += 1
                    elif existing and not decision_replace:
                        skipped += 1
                    else:
                        cursor.execute(
                            'INSERT INTO elements (substation_id, element_type, name, serial_number, maintenance_date, voltage_level, manufacturer, type) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                            (
                                sub_id,
                                str(element_type) if pd.notna(element_type) else '',
                                name_str,
                                serial_str,
                                str(maintenance_date) if pd.notna(maintenance_date) else '',
                                str(voltage_level) if pd.notna(voltage_level) else '',
                                str(manufacturer) if pd.notna(manufacturer) else '',
                                str(elem_type) if pd.notna(elem_type) else '',
                            ),
                        )
                        count += 1
                else:
                    not_found.append(sub_name)

        conn.commit()

        msg_parts = []
        if count > 0:
            msg_parts.append(f'{count} νέα στοιχεία εισήχθησαν')
        if updated > 0:
            msg_parts.append(f'{updated} στοιχεία ενημερώθηκαν')
        if skipped > 0:
            msg_parts.append(f'{skipped} διπλότυπα παραλείφθηκαν')
        if not_found:
            msg_parts.append(f'Υποσταθμοί δεν βρέθησαν: {set(not_found)}')

        msg = '. '.join(msg_parts) + '!' if msg_parts else 'Δεν εισήχθησαν στοιχεία!'
        on_success(msg)
    except Exception as exc:
        on_error(f'Σφάλμα: {exc}')


def import_elements_from_csv(
    conn,
    file_path: str,
    on_success: Callable[[str], None],
    on_error: Callable[[str], None],
    on_duplicate: Callable[[str, str, str], bool] = None,
) -> None:
    """Import elements from CSV.

    on_duplicate(sub_name, name, serial_number) -> bool
    - True: replace existing element
    - False: skip existing element
    """

    if pd is None:
        on_error('pandas δεν είναι εγκατεστημένο!')
        return

    try:
        cursor = conn.cursor()
        df_elem = pd.read_csv(file_path)

        count = 0
        updated = 0
        skipped = 0
        not_found = []

        for _, row in df_elem.iterrows():
            sub_name = row.get('Substation Name', '')
            element_type = row.get('Element Type', '')
            name = row.get('Name', '')
            serial_number = row.get('Serial Number', '')
            maintenance_date = row.get('Maintenance Date', '')
            voltage_level = row.get('Voltage Level', '')
            manufacturer = row.get('Manufacturer', '')
            elem_type = row.get('Type', '')

            if sub_name and name:
                cursor.execute('SELECT id FROM substations WHERE name=?', (str(sub_name),))
                result = cursor.fetchone()
                if result:
                    sub_id = result[0]
                    name_str = str(name)
                    serial_str = str(serial_number) if pd.notna(serial_number) else ''

                    # Check for duplicate
                    cursor.execute(
                        'SELECT id FROM elements WHERE substation_id=? AND name=? AND serial_number=?',
                        (sub_id, name_str, serial_str)
                    )
                    existing = cursor.fetchone()

                    decision_replace = False
                    if existing:
                        if on_duplicate:
                            decision_replace = bool(on_duplicate(str(sub_name), name_str, serial_str))
                        else:
                            decision_replace = False

                    if existing and decision_replace:
                        cursor.execute(
                            'UPDATE elements SET element_type=?, maintenance_date=?, voltage_level=?, manufacturer=?, type=? WHERE id=?',
                            (
                                str(element_type) if pd.notna(element_type) else '',
                                str(maintenance_date) if pd.notna(maintenance_date) else '',
                                str(voltage_level) if pd.notna(voltage_level) else '',
                                str(manufacturer) if pd.notna(manufacturer) else '',
                                str(elem_type) if pd.notna(elem_type) else '',
                                existing[0]
                            )
                        )
                        updated += 1
                    elif existing and not decision_replace:
                        skipped += 1
                    else:
                        cursor.execute(
                            'INSERT INTO elements (substation_id, element_type, name, serial_number, maintenance_date, voltage_level, manufacturer, type) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                            (
                                sub_id,
                                str(element_type) if pd.notna(element_type) else '',
                                name_str,
                                serial_str,
                                str(maintenance_date) if pd.notna(maintenance_date) else '',
                                str(voltage_level) if pd.notna(voltage_level) else '',
                                str(manufacturer) if pd.notna(manufacturer) else '',
                                str(elem_type) if pd.notna(elem_type) else '',
                            ),
                        )
                        count += 1
                else:
                    not_found.append(sub_name)

        conn.commit()

        msg_parts = []
        if count > 0:
            msg_parts.append(f'{count} νέα στοιχεία εισήχθησαν')
        if updated > 0:
            msg_parts.append(f'{updated} στοιχεία ενημερώθηκαν')
        if skipped > 0:
            msg_parts.append(f'{skipped} διπλότυπα παραλείφθηκαν')
        if not_found:
            msg_parts.append(f'Υποσταθμοί δεν βρέθησαν: {set(not_found)}')

        msg = '. '.join(msg_parts) + '!' if msg_parts else 'Δεν εισήχθησαν στοιχεία!'
        on_success(msg)
    except Exception as exc:
        on_error(f'Σφάλμα: {exc}')
