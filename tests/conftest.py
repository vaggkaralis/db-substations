import os
import sys

# Ensure the repository root (project root) is on sys.path so tests can import
# top-level modules like `database`, `DBrun`, `android_app` when pytest runs.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import sys
from pathlib import Path

# Prepend local shims so tests can run headless without real Kivy installation.
shims = Path(__file__).with_name("_shims")
sys.path.insert(0, str(shims))
