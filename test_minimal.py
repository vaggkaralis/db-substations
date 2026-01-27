"""
Minimal test app to verify Kivy works on Android
"""
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.logger import Logger

Logger.info('TESTAPP: ========== Minimal Test App Starting ==========')

class MinimalTestApp(App):
    def build(self):
        Logger.info('TESTAPP: Building UI')
        layout = BoxLayout(orientation='vertical', padding=20, spacing=20)
        
        layout.add_widget(Label(
            text='Kivy Works!\nIf you see this,\nPython is running.',
            font_size='20sp',
            halign='center'
        ))
        
        btn = Button(text='Test Button', size_hint_y=0.3)
        btn.bind(on_press=lambda x: Logger.info('TESTAPP: Button clicked!'))
        layout.add_widget(btn)
        
        Logger.info('TESTAPP: UI built successfully')
        return layout

if __name__ == '__main__':
    Logger.info('TESTAPP: Starting main')
    MinimalTestApp().run()
    Logger.info('TESTAPP: App finished')
