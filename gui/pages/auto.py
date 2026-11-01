"""Halaman Automation."""
import threading
from datetime import datetime

import tkinter as tk
from tkinter import ttk

from gui.common import (org, T, sv_ttk, RULES_PATH, UserError)
from gui.widgets import make_tree


class AutomationPage:
    # ───────────────────────── page: Automation ─────────────────────────

    def _page_auto(self, f):
        self._page_header(f, "auto")
        card = ttk.Frame(f, style="Card.TFrame", padding=18)
        card.pack(fill="x")
        card.columnconfigure(1, weight=1)
        self.watch_var = tk.BooleanVar(value=self.watch_active)
        ttk.Checkbutton(card, text=T("auto_switch"), variable=self.watch_var, command=self._toggle_watch,
                        style="Switch.TCheckbutton" if sv_ttk else "TCheckbutton").grid(row=0, column=0, sticky="w")
        row = ttk.Frame(card)
        row.grid(row=0, column=1, sticky="e")
        ttk.Label(row, text=T("auto_every")).pack(side="left")
        self.interval_var = tk.StringVar(value=str(self.watch_interval_value))
        self.interval_spin = ttk.Spinbox(row, from_=10, to=3600, increment=10, width=6,
                                         textvariable=self.interval_var)
        self.interval_spin.pack(side="left", padx=6)
        ttk.Label(row, text=T("auto_seconds")).pack(side="left")
        self.watch_status = ttk.Label(card, text="", style="H2.TLabel")
        self.watch_status.grid(row=1, column=0, sticky="w", pady=(12, 0))
        ttk.Label(card, text=T("auto_note"), style="Muted.TLabel", wraplength=860, justify="left").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Label(f, text=T("sec_log"), style="H2.TLabel").pack(anchor="w", pady=(18, 6))
        fr, self.watch_log = make_tree(f, ("time", "msg"), (T("col_time"), T("col_activity")), (110, 800),
                                       stretch=("msg",))
        fr.pack(fill="both", expand=True)
        for when, msg in self.watch_log_rows:
            self.watch_log.insert("", "end", values=(when, msg))
        self._render_watch_status()

    def _render_watch_status(self):
        on = self.watch_active
        self.watch_status.configure(
            text=("●  " + T("auto_on", n=self.watch_interval_value)) if on else ("○  " + T("auto_off")),
            foreground=self.pal["success"][1] if on else self.pal["muted"])
        self.interval_spin.state(["disabled"] if on else ["!disabled"])

    def _toggle_watch(self):
        if self.watch_var.get():
            try:
                root = self._target()
                self._cfg()
                interval = int(self.interval_var.get())
                if interval < 10:
                    raise ValueError
            except UserError as e:
                self.watch_var.set(False)
                self.infobar.show("warning", str(e), timeout=6000)
                return
            except (ValueError, tk.TclError):
                self.watch_var.set(False)
                self.infobar.show("warning", T("auto_interval_invalid"), timeout=6000)
                return
            self.watch_interval_value = interval
            self._save_settings()
            self.watch_active = True
            self.watch_stop = threading.Event()
            threading.Thread(target=self._watch_loop, args=(root, interval, self.watch_stop), daemon=True).start()
            self._log(T("log_start", path=root))
        else:
            self.watch_active = False
            self.watch_stop.set()
            self._log(T("log_stop"))
        self._render_watch_status()

    def _watch_loop(self, root, interval, stop):
        while not stop.is_set():
            try:
                cfg = org.load_config(RULES_PATH)
                moves = org.build_plan(root, cfg, stable_secs=15, include_folders=False)
                if moves:
                    ok, failed = org.execute(root, moves, "watch")
                    names = ", ".join(m.src.name for m in moves[:3]) + (" …" if len(moves) > 3 else "")
                    msg = T("log_moved", n=ok, names=names) + (T("log_failed", n=len(failed)) if failed else "")
                    self.q.put(lambda m=msg: (self._log(m), self.refresh_history()))
            except org.FolderBusy:
                self.q.put(lambda: self._log(T("log_busy")))
            except BaseException as e:  # noqa
                self.q.put(lambda m=str(e): self._log(T("log_error", msg=m)))
            stop.wait(interval)

    def _log(self, msg):
        row = (datetime.now().strftime("%H:%M:%S"), msg)
        self.watch_log_rows.insert(0, row)
        del self.watch_log_rows[300:]
        try:
            self.watch_log.insert("", 0, values=row)
        except (AttributeError, tk.TclError):
            pass

