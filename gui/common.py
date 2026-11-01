"""Konstanta, tema, dan helper bersama untuk GUI."""
import json
import os
import subprocess
import sys
from pathlib import Path

import tkinter as tk

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import organizer as org  # noqa: E402
import yaml  # noqa: E402
from i18n import T, LANG_NAMES, fmt_date, fmt_duration  # noqa: E402

try:
    import sv_ttk
except ImportError:
    sv_ttk = None

HERE = org.app_dir()            # folder .exe / folder source: rules.yaml & backup-nya di sini

__all__ = ["org", "yaml", "T", "LANG_NAMES", "sv_ttk", "HERE", "ROOT", "VERSION", "APP_ID", "ASSETS", "RULES_PATH",
           "SETTINGS_PATH", "PALETTE", "GLYPH", "UserError", "load_settings", "save_settings", "system_dark",
           "open_path", "reveal", "fmt_time", "fmt_date", "fmt_duration", "reason_label", "paint_titlebar"]
from version import __version__ as VERSION  # noqa: E402
APP_ID = "FolderOrganizer.Desktop.3"
ASSETS = org.resource_dir() / "assets"
RULES_PATH = org.rules_path()  # samping app (portable) atau %APPDATA% kalau folder app tidak bisa ditulis
SETTINGS_PATH = Path(os.environ.get("APPDATA", Path.home())) / "FolderOrganizer" / "settings.json"

PALETTE = {
    "dark": dict(bg="#1c1c1c", nav_hover="#2a2a2a", nav_sel="#2d2d2d", text="#ffffff", muted="#a6a6a6",
                 accent="#57c8ff", border="#2f2f2f", code_bg="#141414",
                 tip_bg="#2b2b2b", head_bg="#232323", head_hover="#2b2b2b", head_line="#333333",
                 success=("#393d1b", "#6ccb5f"), warning=("#433519", "#fce100"),
                 error=("#442726", "#ff99a4"), info=("#2b2b2b", "#57c8ff")),
    "light": dict(bg="#fafafa", nav_hover="#ececec", nav_sel="#e6e6e6", text="#1a1a1a", muted="#616161",
                  accent="#005fb8", border="#e5e5e5", code_bg="#ffffff",
                  tip_bg="#f9f9f9", head_bg="#f3f3f3", head_hover="#ebebeb", head_line="#e5e5e5",
                  success=("#dff6dd", "#0f7b0f"), warning=("#fff4ce", "#9d5d00"),
                  error=("#fde7e9", "#c42b1c"), info=("#f0f0f0", "#005fb8")),
}

# Segoe Fluent Icons (Win 11) / Segoe MDL2 Assets (Win 10)
GLYPH = dict(overview="", organize="", dupes="", history="", labels="",
             auto="", rules="", settings="", folder="", open="",
             success="", warning="", error="", info="", close="",
             search="", empty="", check="")


class UserError(Exception):
    pass


# ───────────────────────── helpers ─────────────────────────

def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(data: dict):
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def system_dark() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except Exception:
        return False


def open_path(p):
    try:
        if sys.platform == "win32":
            os.startfile(str(p))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])
    except Exception:
        pass


def reveal(p: Path):
    if sys.platform == "win32" and p.exists():
        subprocess.Popen(["explorer", "/select,", str(p)])
    else:
        open_path(p if p.is_dir() else p.parent)


def fmt_time(ts: float) -> str:
    return fmt_date(ts)


def reason_label(r: str) -> str:
    if r == "(fallback)":
        return T("fallback")
    if r.startswith("[folder] "):
        return f"{T('folder_prefix')} · {reason_label(r[9:])}"
    return r


def paint_titlebar(win: tk.Misc, bg: str, dark: bool):
    """Title bar Windows menyatu dengan background (Win 11); Win 10: hanya mode gelap/terang."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
        dwm = ctypes.windll.dwmapi.DwmSetWindowAttribute

        def set_attr(attr, value):
            v = wintypes.DWORD(value)
            dwm(wintypes.HWND(hwnd), wintypes.DWORD(attr), ctypes.byref(v), ctypes.sizeof(v))

        r, g, b = (c // 257 for c in win.winfo_rgb(bg))
        colorref = (b << 16) | (g << 8) | r
        set_attr(20, int(dark))
        set_attr(19, int(dark))
        set_attr(35, colorref)   # caption
        set_attr(36, colorref)   # caption text (disembunyikan)
        set_attr(34, colorref)   # border
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)
    except Exception:
        pass


