"""Halaman Settings."""

import tkinter as tk
from tkinter import ttk

import updates
from gui.common import (T, LANG_NAMES, HERE, VERSION, RULES_PATH, open_path, org)
from gui.widgets import ScrollFrame


class SettingsPage:
    # ───────────────────────── page: Settings ─────────────────────────

    def _page_settings(self, f):
        self._page_header(f, "settings")
        sf = ScrollFrame(f, self.pal["bg"])
        sf.pack(fill="both", expand=True)

        def card(title):
            c = ttk.Frame(sf.inner, style="Card.TFrame", padding=20)
            c.pack(fill="x", pady=(0, 12))
            ttk.Label(c, text=title, style="H2.TLabel").pack(anchor="w", pady=(0, 10))
            return c

        c = card(T("set_theme"))
        self.theme_var = tk.StringVar(value=self.theme_mode)
        for key in ("system", "light", "dark"):
            ttk.Radiobutton(c, text=T(f"theme_{key}"), value=key, variable=self.theme_var,
                            command=self._change_theme).pack(anchor="w", pady=2)
        c = card(T("set_lang"))
        self.lang_var = tk.StringVar(value=T.lang)
        for key, name in LANG_NAMES.items():
            ttk.Radiobutton(c, text=name, value=key, variable=self.lang_var,
                            command=self._change_lang).pack(anchor="w", pady=2)
        c = card(T("set_history"))
        ttk.Label(c, text=T("set_history_hint"), style="Caption.TLabel", wraplength=640,
                  justify="left").pack(anchor="w", pady=(0, 6))
        choices = [(30, T("keep_days", n=30)), (90, T("keep_days", n=90)), (180, T("keep_days", n=180)),
                   (365, T("keep_days", n=365)), (0, T("keep_forever"))]
        labels = [t for _, t in choices]
        cur = next((t for d, t in choices if d == self.journal_days), labels[1])
        self.keep_var = tk.StringVar(value=cur)
        cb = ttk.Combobox(c, state="readonly", values=labels, textvariable=self.keep_var, width=22)
        cb.pack(anchor="w")

        def set_keep(_=None):
            self.journal_days = next(d for d, t in choices if t == self.keep_var.get())
            self._save_settings()

        cb.bind("<<ComboboxSelected>>", set_keep)

        c = card(T("set_updates"))
        ttk.Label(c, text=T("set_updates_hint", repo=updates.REPO), style="Caption.TLabel", wraplength=640,
                  justify="left").pack(anchor="w", pady=(0, 6))
        self.auto_upd_var = tk.BooleanVar(value=self.settings.get("auto_update_check", True))

        def set_auto():
            self.settings["auto_update_check"] = bool(self.auto_upd_var.get())
            self._save_settings()

        ttk.Checkbutton(c, text=T("set_auto_update"), variable=self.auto_upd_var, command=set_auto).pack(
            anchor="w", pady=(0, 8))
        ttk.Button(c, text=T("btn_check_updates"), command=self.check_updates).pack(anchor="w")

        c = card(T("set_about"))
        ttk.Label(c, text=T("about_text", v=VERSION), style="Muted.TLabel").pack(anchor="w")
        ttk.Label(c, text=T("about_rules", path=RULES_PATH), style="Muted.TLabel").pack(anchor="w", pady=(4, 0))
        if RULES_PATH.parent != HERE:
            ttk.Label(c, text=T("about_rules_roaming"), style="Caption.TLabel").pack(anchor="w")
        log_file = org.log_dir() / org.LOG_FILE_NAME
        ttk.Label(c, text=T("about_log", path=log_file), style="Muted.TLabel").pack(anchor="w", pady=(4, 10))
        row = ttk.Frame(c)
        row.pack(anchor="w")
        ttk.Button(row, text=T("btn_open_app_folder"), command=lambda: open_path(HERE)).pack(side="left")
        ttk.Button(row, text=T("btn_open_log_folder"),
                   command=lambda: (org.log_dir().mkdir(parents=True, exist_ok=True), open_path(org.log_dir()))
                   ).pack(side="left", padx=8)

    def _rebuild(self):
        if self.busy:
            self.infobar.show("info", T("busy"), timeout=3000)
            return False
        self._save_settings()
        self._build_shell()
        return True

    def _change_theme(self):
        old = self.theme_mode
        self.theme_mode = self.theme_var.get()
        if not self._rebuild():
            self.theme_mode = old

    def _change_lang(self):
        old = T.lang
        T.lang = self.lang_var.get()
        if not self._rebuild():
            T.lang = old


