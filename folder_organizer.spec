# PyInstaller spec — Folder Organizer.  Build: build_exe.bat  (or: python -m PyInstaller folder_organizer.spec)
# Output: dist\Folder Organizer\Folder Organizer.exe  (one-folder mode: fast start, fewer antivirus false positives)
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH)
IS_WIN = sys.platform == "win32"

datas = [
    (str(ROOT / "assets"), "assets"),
    (str(ROOT / "rules.yaml"), "."),          # default rules; copied next to the .exe on first run
    (str(ROOT / "categories.yaml"), "."),    # file category library (read-only)
]
datas += collect_data_files("sv_ttk")         # Sun Valley theme files (.tcl + images)

a = Analysis(
    [str(ROOT / "organizer_gui.pyw")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=["gui.app", "gui.shell", "gui.widgets", "gui.common"]
                  + [f"gui.pages.{m}" for m in ("overview", "organize", "dupes", "history", "labels", "auto",
                                                 "rules", "rule_editor", "label_editor", "settings")]
                  + ["updates", "rules_io", "i18n"],
    excludes=["pytest", "cairosvg", "numpy", "matplotlib", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Folder Organizer",
    console=False,                             # no console window
    icon=str(ROOT / "assets" / "app.ico") if IS_WIN else None,
    version=str(ROOT / "version_info.txt") if IS_WIN else None,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Folder Organizer", upx=False)
