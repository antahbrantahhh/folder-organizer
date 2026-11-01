#!/usr/bin/env python3
"""Folder Organizer — GUI. Run: double-click "Folder Organizer GUI.bat", or  pythonw organizer_gui.pyw
GUI code lives in gui/ (shell.py, widgets.py, pages/*.py). Engine: organizer.py.
`--version` loads every module, prints the version and exits (used by CI to smoke-test the built .exe)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gui.app import main  # noqa: E402

if __name__ == "__main__":
    if "--version" in sys.argv:
        from version import __version__
        if sys.stdout:  # None in the windowed .exe
            print(__version__)
        sys.exit(0)
    main()
