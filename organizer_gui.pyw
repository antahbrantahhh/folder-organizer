#!/usr/bin/env python3
"""Folder Organizer — GUI. Run: double-click "Folder Organizer GUI.bat", or  pythonw organizer_gui.pyw
GUI code lives in gui/ (shell.py, widgets.py, pages/*.py). Engine: organizer.py.
`--version` loads every module, prints the version and exits.
`--self-test` also resolves and validates rules.yaml + categories (exit 1 on failure). CI runs both on the built
and on the installed .exe."""
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
    if "--self-test" in sys.argv:
        import organizer as org
        try:
            path = org.rules_path()
            cfg = org.load_config(path)
            msg = f"ok rules={path} file_rules={len(cfg['rules'])} categories={len(cfg['_categories'])}"
            code = 0
        except BaseException as e:  # noqa: BLE001
            msg, code = f"FAIL {type(e).__name__}: {getattr(e, 'code', None) or e}", 1
        org.setup_logging()
        org.log.info("self-test: %s", msg)
        if sys.stdout:
            print(msg)
        sys.exit(code)
    main()
