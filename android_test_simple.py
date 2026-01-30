"""
SIMPLIFIED TEST VERSION - Android Kivy App
Purpose: Identify blank screen issue through bug reports
"""
import sys
import os
from datetime import datetime

# Print to stdout (appears in bug report logs)
print("=" * 80)
print("TEST APP STARTING - " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
print("=" * 80)
print(f"Python version: {sys.version}")
print(f"Python executable: {sys.executable}")

# Write to debug file (you can access this file on your phone)
try:
    from android.storage import app_storage_path
    debug_file = os.path.join(app_storage_path(), 'debug_log.txt')
    print(f"Debug file will be at: {debug_file}")
except:
    # On Android: /sdcard/, On Windows: current directory
    if sys.platform == 'win32':
        debug_file = 'db_substations_debug.txt'
    else:
        debug_file = '/sdcard/db_substations_debug.txt'
    print(f"Debug file will be at: {debug_file}")

def write_debug(message):
    """Write debug message to both stdout and file"""
    timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
    msg = f"[{timestamp}] {message}"
    print(msg)
    try:
        with open(debug_file, 'a') as f:
            f.write(msg + '\n')
    except Exception as e:
        print(f"Could not write to file: {e}")

write_debug("=" * 60)
write_debug("STARTING TEST APP")
write_debug("=" * 60)

# Test imports
write_debug("Testing imports...")
try:
    import kivy
    write_debug(f"✓ Kivy version: {kivy.__version__}")
    kivy.require('2.0.0')
    write_debug("✓ Kivy version check passed")
except Exception as e:
    write_debug(f"✗ Kivy import FAILED: {e}")
    raise

try:
    from kivy.app import App
    write_debug("✓ App imported")
    from kivy.uix.boxlayout import BoxLayout
    write_debug("✓ BoxLayout imported")
    from kivy.uix.button import Button
    write_debug("✓ Button imported")
    from kivy.uix.label import Label
    write_debug("✓ Label imported")
    from kivy.core.window import Window
    write_debug("✓ Window imported")
except Exception as e:
    write_debug(f"✗ Kivy UI imports FAILED: {e}")
    raise

write_debug("All imports successful!")

class TestApp(App):
    def __init__(self, **kwargs):
        write_debug("TestApp.__init__ called")
        super().__init__(**kwargs)
        write_debug("TestApp.__init__ completed")
    
    def build(self):
        write_debug("=" * 60)
        write_debug("BUILD METHOD STARTING")
        write_debug("=" * 60)
        
        # Set window background to GREEN to confirm Kivy window works
        try:
            write_debug("Setting window background to GREEN")
            Window.clearcolor = (0, 1, 0, 1)  # Bright green
            write_debug(f"✓ Window clearcolor set: {Window.clearcolor}")
        except Exception as e:
            write_debug(f"✗ Window color FAILED: {e}")
        
        # Create simple layout
        try:
            write_debug("Creating BoxLayout")
            layout = BoxLayout(orientation='vertical', padding=20, spacing=20)
            write_debug("✓ BoxLayout created")
            
            # Test 1: Label with debug info
            write_debug("Creating Label")
            label = Label(
                text='TEST APP\nIf you see this, Kivy works!\nCheck: ' + debug_file,
                color=(0, 0, 0, 1),  # Black text
                font_size='20sp',
                halign='center'
            )
            layout.add_widget(label)
            write_debug("✓ Label added")
            
            # Test 2: Big red button
            write_debug("Creating RED button")
            button = Button(
                text='TEST BUTTON\nCLICK ME',
                background_color=(1, 0, 0, 1),  # Red
                color=(1, 1, 1, 1),  # White text
                font_size='30sp',
                size_hint=(1, 0.3)
            )
            
            def on_button_press(instance):
                write_debug("!!! BUTTON WAS CLICKED !!!")
                instance.text = 'BUTTON WORKS!\nCheck debug file'
            
            button.bind(on_press=on_button_press)
            layout.add_widget(button)
            write_debug("✓ Button added")
            
            # Test 3: Show system info
            write_debug("Creating system info label")
            info_label = Label(
                text=f'Python: {sys.version_info.major}.{sys.version_info.minor}\nKivy: {kivy.__version__}',
                color=(0, 0, 0, 1),
                font_size='16sp'
            )
            layout.add_widget(info_label)
            write_debug("✓ Info label added")
            
            write_debug("=" * 60)
            write_debug("BUILD COMPLETE - RETURNING LAYOUT")
            write_debug(f"Layout has {len(layout.children)} children")
            write_debug("=" * 60)
            write_debug("")
            write_debug("WHAT TO EXPECT:")
            write_debug("- Screen should be BRIGHT GREEN")
            write_debug("- You should see a big RED BUTTON")
            write_debug("- You should see black text labels")
            write_debug("- If screen is BLANK, Kivy UI is not rendering")
            write_debug("=" * 60)
            
            return layout
            
        except Exception as e:
            write_debug(f"✗✗✗ BUILD FAILED: {e}")
            import traceback
            write_debug(traceback.format_exc())
            raise

def main():
    write_debug("Creating TestApp instance")
    try:
        app = TestApp()
        write_debug("TestApp instance created")
        write_debug("Calling app.run()")
        app.run()
        write_debug("app.run() completed")
    except Exception as e:
        write_debug(f"✗✗✗ FATAL ERROR: {e}")
        import traceback
        write_debug(traceback.format_exc())
        raise

if __name__ == '__main__':
    write_debug("__main__ entry point")
    main()
