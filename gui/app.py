"""Entry point GUI: menggabungkan kerangka + semua halaman."""
import sys
import threading

import tkinter as tk

from gui.common import APP_ID, VERSION, org


from gui.pages.overview import OverviewPage
from gui.pages.organize import OrganizePage
from gui.pages.dupes import DuplicatesPage
from gui.pages.history import HistoryPage
from gui.pages.labels import LabelsPage
from gui.pages.auto import AutomationPage
from gui.pages.rules import RulesPage
from gui.pages.rule_editor import RuleEditor
from gui.pages.label_editor import LabelEditor
from gui.pages.settings import SettingsPage
from gui.shell import AppShell
from gui.updater import UpdaterMixin


class App(OverviewPage, OrganizePage, DuplicatesPage, HistoryPage, LabelsPage, AutomationPage, RulesPage, RuleEditor, LabelEditor,
          SettingsPage, UpdaterMixin, AppShell):
    pass


def set_dpi_awareness():
    """Per-monitor DPI v2 (Win 10 1703+): tajam di monitor dengan skala berbeda; AppShell menyesuaikan skala Tk
    saat window pindah monitor. Fallback: per-monitor (8.1), lalu system-aware."""
    import ctypes
    try:
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return "pmv2"
    except Exception:
        pass
    for level, name in ((2, "pm"), (1, "system")):
        try:
            if ctypes.windll.shcore.SetProcessDpiAwareness(level) == 0:
                return name
        except Exception:
            pass
    return None


def main():
    if sys.platform == "win32":
        try:
            import ctypes
            # ID unik → Windows memakai ikon app ini di taskbar, bukan ikon python.exe
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass
        set_dpi_awareness()
    org.setup_logging()
    org.log.info("app start v%s (frozen=%s, python=%s)", VERSION, org.FROZEN, sys.version.split()[0])

    def log_uncaught(exc_type, exc, tb):  # error di luar Tk (mis. saat start) → tetap tercatat
        org.log.critical("uncaught error", exc_info=(exc_type, exc, tb))
    sys.excepthook = log_uncaught
    threading.excepthook = lambda a: org.log.error("thread error in %s", a.thread.name if a.thread else "?",
                                                   exc_info=(a.exc_type, a.exc_value, a.exc_traceback))
    root = tk.Tk()
    App(root)  # App memasang handler error UI sendiri (lihat AppShell._on_tk_error)
    try:
        root.mainloop()
    finally:
        org.log.info("app exit")


if __name__ == "__main__":
    main()
