import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# enable debug sizing prints
os.environ["MAINT_DEBUG"] = "1"

from DBrun import SubstationApp  # noqa: E402


class PreviewApp(SubstationApp):
    def on_start(self):
        # schedule showing the maintenance menu after startup
        from kivy.clock import Clock

        Clock.schedule_once(lambda dt: self.show_maintenance_menu(prefill_data={}), 0.5)


if __name__ == "__main__":
    PreviewApp().run()
