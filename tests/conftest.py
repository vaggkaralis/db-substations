import sys
from pathlib import Path

# Prepend local shims so tests can run headless without real Kivy installation.
shims = Path(__file__).with_name("_shims")
sys.path.insert(0, str(shims))
