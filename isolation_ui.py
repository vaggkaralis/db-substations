from strings import STRINGS as S


def show_isolation_requests(app, instance=None):
    """Show isolation requests in calendar view (extracted from DBrun)."""
    from datetime import datetime, timedelta
    from calendar import monthrange

    font_kwargs = app._get_ui_font_kwargs()

    try:
        from kivy.uix.popup import Popup
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.label import Label
        from kivy.uix.gridlayout import GridLayout
        from kivy.uix.scrollview import ScrollView
        from kivy.uix.spinner import Spinner
        from kivy.uix.textinput import TextInput
    except Exception:
        Popup = BoxLayout = Button = Label = GridLayout = ScrollView = Spinner = TextInput = object

    popup = Popup(title="Αιτήσεις Απομόνωσης", size_hint=(0.95, 0.95))
    main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    # Current month/year state
    current_date = datetime.now()
    current_month = [current_date.month]
    current_year = [current_date.year]

    # Top controls
    controls_layout = BoxLayout(size_hint_y=0.1, spacing=10)

    prev_btn = Button(text="◀ Προηγούμενος", **font_kwargs)
    next_btn = Button(text="Επόμενος ▶", **font_kwargs)
    today_btn = Button(text="Σήμερα", **font_kwargs)
    add_btn = Button(text="+ Νέα Αίτηση", **font_kwargs)

    controls_layout.add_widget(prev_btn)
    controls_layout.add_widget(today_btn)
    controls_layout.add_widget(next_btn)
    controls_layout.add_widget(add_btn)

    main_layout.add_widget(controls_layout)

    header_label = Label(text="", size_hint_y=0.08, font_size="20sp", bold=True)
    main_layout.add_widget(header_label)

    calendar_container = BoxLayout(orientation="vertical")
    main_layout.add_widget(calendar_container)

    # Legend
    legend_layout = BoxLayout(size_hint_y=0.08, spacing=10, padding=[10, 5])
    legend_layout.add_widget(Label(text="", size_hint_x=0.3, **font_kwargs))
    legend_layout.add_widget(Label(text="● Αιτήθηκε", size_hint_x=0.2, color=(1, 0.85, 0, 1), **font_kwargs))
    legend_layout.add_widget(Label(text="● Εγκρίθηκε", size_hint_x=0.2, color=(0.2, 0.8, 0.2, 1), **font_kwargs))
    legend_layout.add_widget(Label(text="● Ακυρώθηκε", size_hint_x=0.2, color=(0.9, 0.2, 0.2, 1), **font_kwargs))
    legend_layout.add_widget(Label(text="", size_hint_x=0.1, **font_kwargs))
    main_layout.add_widget(legend_layout)

    def load_calendar():
        calendar_container.clear_widgets()

        month = current_month[0]
        year = current_year[0]

        month_names = ["","Ιανουάριος","Φεβρουάριος","Μάρτιος","Απρίλιος","Μάιος","Ιούνιος","Ιούλιος","Αύγουστος","Σεπτέμβριος","Οκτώβριος","Νοέμβριος","Δεκέμβριος"]
        header_label.text = f"{month_names[month]} {year}"

        c = app.conn.cursor()
        first_day = f"{year}-{month:02d}-01 00:00"
        last_day_num = monthrange(year, month)[1]
        last_day = f"{year}-{month:02d}-{last_day_num} 23:59"

        c.execute(
            """
                SELECT ir.id, ir.substation_id, s.name, ir.start_datetime, ir.end_datetime, 
                       ir.status, ir.notes
                FROM isolation_requests ir
                JOIN substations s ON ir.substation_id = s.id
                WHERE (ir.start_datetime <= ? AND ir.end_datetime >= ?)
                   OR (ir.start_datetime >= ? AND ir.start_datetime <= ?)
                ORDER BY ir.start_datetime
            """,
            (last_day, first_day, first_day, last_day),
        )
        requests = c.fetchall()

        requests_by_day = {}
        for req_id, sub_id, sub_name, start_dt, end_dt, status, notes in requests:
            try:
                start = datetime.strptime(start_dt, "%Y-%m-%d %H:%M")
                end = datetime.strptime(end_dt, "%Y-%m-%d %H:%M")
                current = start
                while current <= end:
                    if current.year == year and current.month == month:
                        day = current.day
                        if day not in requests_by_day:
                            requests_by_day[day] = []
                        if not any(r[0] == req_id for r in requests_by_day[day]):
                            requests_by_day[day].append((req_id, sub_id, sub_name, start_dt, end_dt, status, notes))
                    current += timedelta(days=1)
            except Exception:
                pass

        calendar_grid = GridLayout(cols=7, spacing=2)
        day_names = ["Δευ", "Τρί", "Τετ", "Πέμ", "Παρ", "Σάβ", "Κυρ"]
        for day_name in day_names:
            calendar_grid.add_widget(Label(text=day_name, size_hint_y=None, height=30, bold=True))

        first_weekday = datetime(year, month, 1).weekday()
        days_in_month = monthrange(year, month)[1]

        for _ in range(first_weekday):
            calendar_grid.add_widget(Label(text=""))

        for day in range(1, days_in_month + 1):
            day_box = BoxLayout(orientation="vertical", size_hint_y=None, height=100)
            day_label = Label(text=str(day), size_hint_y=0.3, bold=True)
            day_box.add_widget(day_label)

            if day in requests_by_day:
                scroll = ScrollView(size_hint_y=0.7)
                requests_layout = GridLayout(cols=1, size_hint_y=None, spacing=2, padding=2)
                requests_layout.bind(minimum_height=requests_layout.setter("height"))

                for (req_id, sub_id, sub_name, start_dt, end_dt, status, notes) in requests_by_day[day]:
                    if status == "Accepted":
                        color = (0.2, 0.8, 0.2, 1)
                        symbol = "●"
                    elif status == "Cancelled":
                        color = (0.8, 0.2, 0.2, 1)
                        symbol = "●"
                    else:
                        color = (0.8, 0.8, 0.2, 1)
                        symbol = "●"

                    req_btn = Button(text=f"{symbol} {sub_name[:15]}", size_hint_y=None, height=30, background_color=color, **font_kwargs)

                    def make_request_handler(r_id, popup_ref=popup):
                        return lambda x: show_isolation_request_details(app, r_id, popup_ref)

                    req_btn.bind(on_press=make_request_handler(req_id))
                    requests_layout.add_widget(req_btn)

                scroll.add_widget(requests_layout)
                day_box.add_widget(scroll)
            else:
                day_box.add_widget(Label(text="", size_hint_y=0.7))

            calendar_grid.add_widget(day_box)

        calendar_container.add_widget(calendar_grid)

    def go_prev_month(instance):
        if current_month[0] == 1:
            current_month[0] = 12
            current_year[0] -= 1
        else:
            current_month[0] -= 1
        load_calendar()

    def go_next_month(instance):
        if current_month[0] == 12:
            current_month[0] = 1
            current_year[0] += 1
        else:
            current_month[0] += 1
        load_calendar()

    def go_today(instance):
        today = datetime.now()
        current_month[0] = today.month
        current_year[0] = today.year
        load_calendar()

    def add_request(instance):
        show_add_isolation_request(app, popup)

    prev_btn.bind(on_press=go_prev_month)
    next_btn.bind(on_press=go_next_month)
    today_btn.bind(on_press=go_today)
    add_btn.bind(on_press=add_request)

    load_calendar()

    close_btn = Button(text=S["BUTTONS"]["CLOSE"], size_hint_y=0.08)
    close_btn.bind(on_press=popup.dismiss)
    main_layout.add_widget(close_btn)

    popup.content = main_layout
    popup.open()


def show_add_isolation_request(app, parent_popup):
    """Show dialog to add new isolation request (extracted)."""
    from datetime import datetime, timedelta

    try:
        from kivy.uix.popup import Popup
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.label import Label
        from kivy.uix.spinner import Spinner
        from kivy.uix.textinput import TextInput
    except Exception:
        Popup = BoxLayout = Button = Label = Spinner = TextInput = object

    c = app.conn.cursor()
    c.execute("SELECT id, name FROM substations ORDER BY name")
    substations = c.fetchall()

    if not substations:
        from popups import show_message_popup

        show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["NO_SUBSTATIONS"])
        return

    popup = Popup(title="Νέα Αίτηση Απομόνωσης", size_hint=(0.7, 0.75))
    layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    layout.add_widget(Label(text="Υποσταθμός:", size_hint_y=None, height=30))
    substation_map = {s[1]: s[0] for s in substations}
    substation_spinner = Spinner(text=substations[0][1], values=[s[1] for s in substations], size_hint_y=None, height=40)
    layout.add_widget(substation_spinner)

    layout.add_widget(Label(text="Ημ/νία & Ώρα Έναρξης:", size_hint_y=None, height=30))
    start_input = TextInput(text=datetime.now().strftime("%Y-%m-%d %H:%M"), hint_text="YYYY-MM-DD HH:MM", size_hint_y=None, height=35, multiline=False)
    layout.add_widget(start_input)

    start_presets = BoxLayout(size_hint_y=None, height=35, spacing=5)

    def set_start_today_morning():
        start_input.text = datetime.now().strftime("%Y-%m-%d 08:00")

    def set_start_today_evening():
        start_input.text = datetime.now().strftime("%Y-%m-%d 18:00")

    today_morning_btn = Button(text="Σήμερα 08:00")
    today_morning_btn.bind(on_press=lambda x: set_start_today_morning())
    start_presets.add_widget(today_morning_btn)

    today_evening_btn = Button(text="Σήμερα 18:00")
    today_evening_btn.bind(on_press=lambda x: set_start_today_evening())
    start_presets.add_widget(today_evening_btn)

    layout.add_widget(start_presets)

    layout.add_widget(Label(text="Ημ/νία & Ώρα Λήξης:", size_hint_y=None, height=30))
    end_input = TextInput(text=(datetime.now() + timedelta(hours=4)).strftime("%Y-%m-%d %H:%M"), hint_text="YYYY-MM-DD HH:MM", size_hint_y=None, height=35, multiline=False)
    layout.add_widget(end_input)

    duration_presets = BoxLayout(size_hint_y=None, height=35, spacing=5)

    def set_duration_hours(hours):
        try:
            start = datetime.strptime(start_input.text, "%Y-%m-%d %H:%M")
            end = start + timedelta(hours=hours)
            end_input.text = end.strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass

    dur_2h_btn = Button(text="2 ώρες")
    dur_2h_btn.bind(on_press=lambda x: set_duration_hours(2))
    duration_presets.add_widget(dur_2h_btn)

    dur_4h_btn = Button(text="4 ώρες")
    dur_4h_btn.bind(on_press=lambda x: set_duration_hours(4))
    duration_presets.add_widget(dur_4h_btn)

    dur_1day_btn = Button(text="1 ημέρα")
    dur_1day_btn.bind(on_press=lambda x: set_duration_hours(24))
    duration_presets.add_widget(dur_1day_btn)

    layout.add_widget(duration_presets)

    layout.add_widget(Label(text="Κατάσταση:", size_hint_y=None, height=30))
    status_spinner = Spinner(text="Requested", values=["Requested", "Accepted", "Cancelled"], size_hint_y=None, height=40)
    layout.add_widget(status_spinner)

    layout.add_widget(Label(text="Σημειώσεις:", size_hint_y=None, height=30))
    notes_input = TextInput(hint_text="Πρόσθετες πληροφορίες...", size_hint_y=None, height=80, multiline=True)
    layout.add_widget(notes_input)

    buttons_layout = BoxLayout(size_hint_y=None, height=50, spacing=10)

    def save_request():
        substation_id = substation_map[substation_spinner.text]
        start_dt = start_input.text.strip()
        end_dt = end_input.text.strip()
        status = status_spinner.text
        notes = notes_input.text.strip()

        try:
            start = datetime.strptime(start_dt, "%Y-%m-%d %H:%M")
            end = datetime.strptime(end_dt, "%Y-%m-%d %H:%M")

            if end <= start:
                from popups import show_message_popup

                show_message_popup("Σφάλμα", "Η ημερομηνία λήξης πρέπει να είναι μετά την έναρξη!")
                return
        except ValueError:
            from popups import show_message_popup

            show_message_popup("Σφάλμα", "Μη έγκυρη μορφή ημερομηνίας! Χρησιμοποιήστε: YYYY-MM-DD HH:MM")
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c = app.conn.cursor()
        c.execute(
            """
                INSERT INTO isolation_requests 
                (substation_id, start_datetime, end_datetime, status, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (substation_id, start_dt, end_dt, status, notes, now, now),
        )
        app.conn.commit()

        popup.dismiss()
        parent_popup.dismiss()
        from popups import show_message_popup

        show_message_popup(S["TITLES"]["SUCCESS"], "Η αίτηση απομόνωσης καταχωρήθηκε!", callback=lambda: show_isolation_requests(app, None))

    save_btn = Button(text=S["BUTTONS"]["SAVE"])
    save_btn.bind(on_press=lambda x: save_request())
    buttons_layout.add_widget(save_btn)
    cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
    cancel_btn.bind(on_press=popup.dismiss)
    buttons_layout.add_widget(cancel_btn)

    layout.add_widget(buttons_layout)
    popup.content = layout
    popup.open()


def show_isolation_request_details(app, request_id, parent_popup):
    """Show details of an isolation request with edit/delete options."""
    from datetime import datetime

    try:
        from kivy.uix.popup import Popup
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.label import Label
        from kivy.uix.scrollview import ScrollView
        from kivy.uix.gridlayout import GridLayout
        from kivy.uix.spinner import Spinner
        from kivy.uix.textinput import TextInput
    except Exception:
        Popup = BoxLayout = Button = Label = ScrollView = GridLayout = Spinner = TextInput = object

    c = app.conn.cursor()
    c.execute(
        """
            SELECT ir.id, ir.substation_id, s.name, ir.start_datetime, ir.end_datetime,
                   ir.status, ir.notes, ir.created_at, ir.updated_at
            FROM isolation_requests ir
            JOIN substations s ON ir.substation_id = s.id
            WHERE ir.id = ?
        """,
        (request_id,),
    )
    request = c.fetchone()

    if not request:
        from popups import show_message_popup

        show_message_popup(S["TITLES"]["ERROR"], "Η αίτηση δεν βρέθηκε!")
        return

    (req_id, sub_id, sub_name, start_dt, end_dt, status, notes, created_at, updated_at) = request

    popup = Popup(title=f"Αίτηση Απομόνωσης - {sub_name}", size_hint=(0.7, 0.8))
    layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    scroll = ScrollView()
    details_layout = BoxLayout(orientation="vertical", size_hint_y=None, spacing=10, padding=5)
    details_layout.bind(minimum_height=details_layout.setter("height"))

    details_layout.add_widget(Label(text="Υποσταθμός:", size_hint_y=None, height=30, bold=True))
    substation_label = Label(text=sub_name, size_hint_y=None, height=30)
    details_layout.add_widget(substation_label)

    details_layout.add_widget(Label(text="Έναρξη:", size_hint_y=None, height=30, bold=True))
    start_input = TextInput(text=start_dt, size_hint_y=None, height=35, multiline=False)
    details_layout.add_widget(start_input)

    details_layout.add_widget(Label(text="Λήξη:", size_hint_y=None, height=30, bold=True))
    end_input = TextInput(text=end_dt, size_hint_y=None, height=35, multiline=False)
    details_layout.add_widget(end_input)

    details_layout.add_widget(Label(text="Κατάσταση:", size_hint_y=None, height=30, bold=True))
    status_spinner = Spinner(text=status, values=["Requested", "Accepted", "Cancelled"], size_hint_y=None, height=40)
    details_layout.add_widget(status_spinner)

    details_layout.add_widget(Label(text="Σημειώσεις:", size_hint_y=None, height=30, bold=True))
    notes_input = TextInput(text=notes or "", size_hint_y=None, height=80, multiline=True)
    details_layout.add_widget(notes_input)

    details_layout.add_widget(Label(text=f"Δημιουργήθηκε: {created_at}", size_hint_y=None, height=25, font_size="11sp"))
    details_layout.add_widget(Label(text=f"Τελευταία ενημέρωση: {updated_at}", size_hint_y=None, height=25, font_size="11sp"))

    scroll.add_widget(details_layout)
    layout.add_widget(scroll)

    buttons_layout = BoxLayout(size_hint_y=None, height=50, spacing=10)

    def update_request():
        start_new = start_input.text.strip()
        end_new = end_input.text.strip()
        status_new = status_spinner.text
        notes_new = notes_input.text.strip()

        try:
            start = datetime.strptime(start_new, "%Y-%m-%d %H:%M")
            end = datetime.strptime(end_new, "%Y-%m-%d %H:%M")

            if end <= start:
                from popups import show_message_popup

                show_message_popup("Σφάλμα", "Η ημερομηνία λήξης πρέπει να είναι μετά την έναρξη!")
                return
        except ValueError:
            from popups import show_message_popup

            show_message_popup("Σφάλμα", "Μη έγκυρη μορφή ημερομηνίας!")
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute(
            """
                UPDATE isolation_requests
                SET start_datetime=?, end_datetime=?, status=?, notes=?, updated_at=?
                WHERE id=?
            """,
            (start_new, end_new, status_new, notes_new, now, req_id),
        )
        app.conn.commit()

        popup.dismiss()
        parent_popup.dismiss()
        from popups import show_message_popup

        show_message_popup(S["TITLES"]["SUCCESS"], "Η αίτηση ενημερώθηκε!", callback=lambda: show_isolation_requests(app, None))

    def delete_request():
        from reports import show_confirm

        def do_delete():
            c.execute("DELETE FROM isolation_requests WHERE id=?", (req_id,))
            app.conn.commit()
            try:
                popup.dismiss()
            except Exception:
                pass
            try:
                parent_popup.dismiss()
            except Exception:
                pass
            from popups import show_message_popup

            show_message_popup(S["TITLES"]["SUCCESS"], "Η αίτηση διαγράφηκε!", callback=lambda: show_isolation_requests(app, None))

        show_confirm(
            "Επιβεβαίωση",
            "Είστε σίγουροι ότι θέλετε να διαγράψετε\nαυτήν την αίτηση απομόνωσης;",
            yes_callback=do_delete,
            yes_text="Ναι",
            no_text="Όχι",
            yes_color=(1, 0, 0, 1),
        )

    update_btn = Button(text=S["BUTTONS"]["UPDATE"])
    update_btn.bind(on_press=lambda x: update_request())
    buttons_layout.add_widget(update_btn)
    delete_btn = Button(text=S["BUTTONS"]["DELETE"], background_color=(0.8, 0.2, 0.2, 1))
    delete_btn.bind(on_press=lambda x: delete_request())
    buttons_layout.add_widget(delete_btn)

    close_btn = Button(text=S["BUTTONS"]["CLOSE"])
    close_btn.bind(on_press=popup.dismiss)
    buttons_layout.add_widget(close_btn)

    layout.add_widget(buttons_layout)
    popup.content = layout
    popup.open()
