import os
import sys

from kivy.app import App
from kivy.core.window import Window
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.checkbox import CheckBox
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from validation import group_people_by_category

# sample people with long names to force wrapping
people = [
    (1, "Καράλης Ευάγγελος", "Μηχανικός"),
    (2, "Παπαϊωακείμ Παντελής", "Τομεάρχης ΤΕΙ"),
    (3, "Ιορδανίδης Ιορδάνης με πολύ μακρύ όνομα", "Υποτομεάρχης TEI"),
    (4, "Παπαδοπούλου Μαρία", "Μηχανικός"),
    (5, "Καρκαλέτσης Θεόδωρος", "Ειδικό Στέλεχος Γ'"),
    (6, "Γεωργίου Λάζαρος", "Μηχανικός"),
    (7, "Σιαμέτης Κωνσταντίνος", "Μηχανικός"),
    (8, "Γιώβης Δημήτριος Μεσαίο Όνομα", "Αρχιτεχνίτης"),
    (9, "Παρθενόπουλος Φώτης", "Αρχιτεχνίτης"),
]


class CrewPreviewApp(App):
    def build(self):
        Window.size = (900, 600)
        root = BoxLayout(orientation="vertical", padding=10, spacing=10)
        # header
        root.add_widget(
            Label(text="Maintenance Crew Preview", size_hint_y=None, height=30)
        )
        crew_section = BoxLayout(orientation="vertical", size_hint_y=None, spacing=0)
        crew_section.bind(minimum_height=crew_section.setter("height"))
        preferred_col_width = 280
        cols = max(1, min(5, int(Window.width // preferred_col_width)))
        min_cell_h = 20
        grouped = group_people_by_category(people)
        for cat, members in grouped.items():
            if not members:
                continue
            hdr = Label(text=cat, size_hint_y=None, height=16)
            crew_section.add_widget(hdr)
            cat_grid = GridLayout(
                cols=cols, spacing=(6, 2), size_hint_y=None, padding=2
            )
            cat_grid.bind(minimum_height=cat_grid.setter("height"))
            for pid, name, role in members:
                cell = BoxLayout(
                    orientation="horizontal",
                    size_hint_y=None,
                    height=min_cell_h,
                    spacing=6,
                    padding=(2, 0),
                )
                anchor = AnchorLayout(size_hint_x=None, width=36)
                cb = CheckBox(size_hint=(None, None), size=(26, min_cell_h))
                anchor.add_widget(cb)
                cell.add_widget(anchor)
                lbl = Label(
                    text=f"{name} ({role})",
                    halign="left",
                    valign="middle",
                    size_hint_x=1,
                )
                lbl.size_hint_y = None
                lbl.height = min_cell_h

                def _update_label_height(
                    inst,
                    parent_cell=cell,
                    anchor_container=anchor,
                    checkbox=cb,
                    name_val=name,
                ):
                    try:
                        inst.text_size = (inst.width - 6, None)
                        inst.texture_update()
                        h = max(min_cell_h, inst.texture_size[1] + 4)
                        inst.height = h
                        inst.text_size = (inst.width - 6, h)
                        parent_cell.height = h
                        try:
                            anchor_container.height = h
                            checkbox.size = (checkbox.width, max(18, h))
                        except Exception:
                            pass
                        if os.environ.get("MAINT_DEBUG"):
                            print(
                                f"MAINT_DEBUG: '{name_val}' -> cell_h={h}, label_w={inst.width}, checkbox_h={checkbox.height}"
                            )
                    except Exception:
                        pass

                lbl.bind(width=_update_label_height)
                lbl.bind(texture_size=lambda *_: _update_label_height(lbl))
                _update_label_height(lbl)
                cell.add_widget(lbl)
                cat_grid.add_widget(cell)
            rows_cat = (len(members) + cols - 1) // cols
            cat_grid.height = rows_cat * min_cell_h + 6
            crew_section.add_widget(cat_grid)
        root.add_widget(crew_section)
        return root


if __name__ == "__main__":
    os.environ["MAINT_DEBUG"] = "1"
    CrewPreviewApp().run()
