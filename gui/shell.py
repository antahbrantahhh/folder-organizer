"""Kerangka aplikasi (window, tema, navigasi, task runner)."""
import queue
import re
import sys
import threading
import time
import traceback
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, ttk

from gui.common import (org, T, fmt_duration, sv_ttk, ASSETS, RULES_PATH, PALETTE, GLYPH, UserError, load_settings, save_settings, system_dark, open_path, paint_titlebar)
from gui.widgets import (Fonts, RailItem, InfoBar, Dialog)


# ───────────────────────── app ─────────────────────────

class AppShell:
    """Kerangka app: tema, layout, rail, infrastruktur background task."""
    PAGES = ["overview", "organize", "dupes", "history", "labels", "auto"]
    FOOTER_PAGES = ["rules", "settings"]

    def __init__(self, root: tk.Tk):
        self.root = root
        self.q = queue.Queue()
        self.busy = False
        self.settings = load_settings()
        T.lang = self.settings.get("lang", "en")
        self.theme_mode = self.settings.get("theme", "system")
        self.folder = self.settings.get("folder", "")
        self.page = "overview"

        # state yang bertahan saat UI di-rebuild (ganti bahasa/tema)
        self.plan, self.plan_root = [], None
        self.dup_groups, self.dup_root = [], None
        self.scan_result = None
        self.journals = []
        self.watch_active, self.watch_stop, self.watch_log_rows = False, threading.Event(), []
        self.watch_interval_value = self.settings.get("interval", 30)
        self.journal_days = int(self.settings.get("journal_days", 90))
        self.doc, self.doc_error, self.dirty = None, None, False
        self.rules_section = "files"
        self.sel_rule = {"rules": None, "folder_rules": None}
        self.sel_label = None

        self.fonts = Fonts(root)
        self._load_doc()
        root.title(T("app_title"))
        root.minsize(1000, 640)
        geo = self.settings.get("geometry")
        root.geometry(geo if geo and re.match(r"^\d+x\d+[+-]-?\d+[+-]-?\d+$", geo) else "1240x800")
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.cancel_event = threading.Event()
        self._task = None
        self._set_icon()
        self._build_shell()
        self._bind_shortcuts()
        root.report_callback_exception = self._on_tk_error
        root.after(80, self._poll)

    # ── theme ──
    @property
    def is_dark(self):
        return self.theme_mode == "dark" or (self.theme_mode == "system" and system_dark())

    @property
    def pal(self):
        return PALETTE["dark" if self.is_dark else "light"]

    def _apply_theme(self):
        if sv_ttk:
            sv_ttk.set_theme("dark" if self.is_dark else "light")
        s = ttk.Style()
        f, p = self.fonts, self.pal
        s.configure(".", font=(f.text, 10))
        s.configure("Title.TLabel", font=(f.display, 22, "bold"))
        s.configure("Subtitle.TLabel", font=(f.display, 14, "bold"))
        s.configure("H2.TLabel", font=(f.text, 11, "bold"))
        s.configure("Muted.TLabel", foreground=p["muted"])
        s.configure("Caption.TLabel", foreground=p["muted"], font=(f.text, 9))
        s.configure("Error.TLabel", foreground=p["error"][1], font=(f.text, 9))
        s.configure("Stat.TLabel", font=(f.display, 22, "bold"))
        s.configure("NavTitle.TLabel", font=(f.text, 10, "bold"))
        s.configure("Treeview", rowheight=32, font=(f.text, 10))
        self._flat_tree_style(s, f, p)
        s.configure("TButton", font=(f.text, 10))
        s.configure("Accent.TButton", font=(f.text, 10))
        s.configure("Token.TButton", font=(f.mono, 9), padding=(6, 2))
        self.root.configure(bg=p["bg"])

    def _flat_tree_style(self, s, f, p):
        """Header tabel datar (tanpa kotak per kolom yang saling tumpang tindih di tema Sun Valley)."""
        for name, src in (("Flat.Treeheading.cell", "Treeheading.cell"), ("Flat.Treeheading.border", "border")):
            try:
                s.element_create(name, "from", "default", src)
            except tk.TclError:
                pass  # sudah dibuat untuk tema ini
        s.layout("Flat.Treeview.Heading", [
            ("Flat.Treeheading.cell", {"sticky": "nswe"}),
            ("Flat.Treeheading.border", {"sticky": "nswe", "children": [
                ("Treeheading.padding", {"sticky": "nswe", "children": [
                    ("Treeheading.image", {"side": "right", "sticky": ""}),
                    ("Treeheading.text", {"sticky": "we"})]})]})])
        s.configure("Flat.Treeview.Heading", background=p["head_bg"], foreground=p["muted"], relief="flat",
                    borderwidth=0, padding=(4, 7), font=(f.text, 9, "bold"))
        s.map("Flat.Treeview.Heading", background=[("active", p["head_hover"])], relief=[("pressed", "flat")])
        s.configure("Flat.Treeview", rowheight=32, font=(f.text, 10))

    def _load_checks(self):
        """Checkbox gaya Win 11 sesuai tema & skala DPI."""
        scale = self.root.winfo_fpixels("1i") / 96.0
        size = min((16, 20, 24, 32), key=lambda s_: abs(s_ - 16 * scale))
        theme = "dark" if self.is_dark else "light"
        self.check_img = {}
        for state in ("on", "off", "mixed"):
            path = ASSETS / f"check_{state}_{theme}_{size}.png"
            try:
                self.check_img[state] = tk.PhotoImage(file=str(path))
            except tk.TclError:
                self.check_img[state] = ""
        self.check_img["blank"] = tk.PhotoImage(width=size, height=size)

        # ikon rail: SVG source di assets/icons, PNG hasil build di assets/icons/png
        sizes = (20, 25, 30, 40)
        self.rail_px = min(sizes, key=lambda s_: abs(s_ - 20 * scale))
        self.rail_icons = {}
        for key in self.PAGES + self.FOOTER_PAGES:
            try:
                self.rail_icons[key] = {
                    st: tk.PhotoImage(file=str(ASSETS / "icons" / "png" / f"{key}_{theme}_{st}_{self.rail_px}.png"))
                    for st in ("normal", "active")}
            except tk.TclError:
                pass

    def _set_icon(self):
        """Windows: pakai .ico multi-ukuran saja, supaya Windows memilih frame yang pas (16–24 px di title bar,
        24–48 px di taskbar). Jangan panggil iconphoto setelahnya: itu menimpa .ico dan Tk mengecilkan
        satu PNG sendiri, hasilnya blur."""
        try:
            if sys.platform == "win32" and (ASSETS / "app.ico").exists():
                self.root.iconbitmap(default=str(ASSETS / "app.ico"))
            else:
                self._icon_imgs = [tk.PhotoImage(file=str(ASSETS / f"app_{n}.png")) for n in (16, 32, 48, 256)
                                   if (ASSETS / f"app_{n}.png").exists()]
                if self._icon_imgs:
                    self.root.iconphoto(True, *self._icon_imgs)
        except Exception:
            pass

    # ── shell ──
    def _build_shell(self):
        for w in self.root.winfo_children():
            w.destroy()
        self.btns = []
        self._apply_theme()
        self._load_checks()
        p = self.pal
        self.root.title(T("app_title"))
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        # navigation rail (ikon saja + tooltip)
        nav = tk.Frame(self.root, bg=p["bg"], width=self.rail_px + 44)
        nav.grid(row=0, column=0, sticky="ns")
        nav.pack_propagate(False)
        tk.Frame(nav, bg=p["bg"], height=14).pack()  # jarak atas (logo app sudah ada di title bar)
        self.nav_items = {}
        for key in self.PAGES:
            it = RailItem(nav, self, key, T(f"nav_{key}"), self.show_page,
                          hint=T("shortcut_hint", n=(self.PAGES + self.FOOTER_PAGES).index(key) + 1))
            it.pack(pady=2)
            self.nav_items[key] = it
        tk.Frame(nav, bg=p["bg"]).pack(fill="both", expand=True)
        tk.Frame(nav, bg=p["border"], height=1, width=32).pack(pady=6)
        for key in self.FOOTER_PAGES:
            it = RailItem(nav, self, key, T(f"nav_{key}"), self.show_page,
                          hint=T("shortcut_hint", n=(self.PAGES + self.FOOTER_PAGES).index(key) + 1))
            it.pack(pady=2)
            self.nav_items[key] = it
        tk.Frame(nav, bg=p["bg"], height=12).pack()
        tk.Frame(self.root, bg=p["border"], width=1).grid(row=0, column=0, sticky="nse")

        # content
        content = ttk.Frame(self.root, padding=(24, 18, 28, 16))
        content.grid(row=0, column=1, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(3, weight=1)
        self.content = content
        self._build_target_bar(content)
        # baris progress: teks tugas + progres/ETA, progress bar, tombol Cancel
        self.progress_row = ttk.Frame(content)
        self.progress_row.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.progress_row.columnconfigure(1, weight=1)
        self.progress_text = ttk.Label(self.progress_row, text="", style="Muted.TLabel")
        self.progress_text.grid(row=0, column=0, sticky="w", padx=(0, 12))
        self.progress = ttk.Progressbar(self.progress_row, mode="indeterminate")
        self.progress.grid(row=0, column=1, sticky="ew")
        self.cancel_btn = ttk.Button(self.progress_row, text=T("btn_cancel"), command=self.cancel_task)
        self.cancel_btn.grid(row=0, column=2, padx=(12, 0))
        self.progress_row.grid_remove()
        self.infobar = InfoBar(content, self)
        self.infobar.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        self.infobar.grid_remove()

        stack = ttk.Frame(content)
        stack.grid(row=3, column=0, sticky="nsew", pady=(16, 0))
        stack.rowconfigure(0, weight=1)
        stack.columnconfigure(0, weight=1)
        self.pages = {}
        for key in self.PAGES + self.FOOTER_PAGES:
            f = ttk.Frame(stack)
            f.grid(row=0, column=0, sticky="nsew")
            self.pages[key] = f
            getattr(self, f"_page_{key}")(f)
        self.show_page(self.page)
        self.root.after(30, lambda: paint_titlebar(self.root, p["bg"], self.is_dark))

    def _build_target_bar(self, parent):
        bar = ttk.Frame(parent, style="Card.TFrame", padding=(14, 10))
        bar.grid(row=0, column=0, sticky="ew")
        f, p = self.fonts, self.pal
        if f.icon:
            ttk.Label(bar, text=GLYPH["folder"], font=(f.icon, 16), foreground=p["accent"]).pack(side="left",
                                                                                               padx=(0, 12))
        col = ttk.Frame(bar)
        col.pack(side="left", fill="x", expand=True)
        ttk.Label(col, text=T("target_caption"), style="Caption.TLabel").pack(anchor="w")
        self.target_label = ttk.Label(col, text=self.folder or T("target_none"),
                                      font=(f.text, 10, "bold" if self.folder else "normal"))
        self.target_label.pack(anchor="w")
        ttk.Button(bar, text=T("btn_open_explorer"), command=self._open_target).pack(side="right")
        ttk.Button(bar, text=T("btn_change_folder") if self.folder else T("btn_choose_folder"),
                   command=self._pick_folder, style="Accent.TButton" if (sv_ttk and not self.folder) else "TButton"
                   ).pack(side="right", padx=8)

    def _page_header(self, parent, key, actions=None):
        h = ttk.Frame(parent)
        h.pack(fill="x", pady=(0, 14))
        left = ttk.Frame(h)
        left.pack(side="left", fill="x", expand=True)
        ttk.Label(left, text=T(f"{key}_title"), style="Title.TLabel").pack(anchor="w")
        ttk.Label(left, text=T(f"{key}_desc"), style="Muted.TLabel", wraplength=780, justify="left").pack(
            anchor="w", pady=(2, 0))
        return h

    def _btn(self, parent, text, cmd, accent=False):
        b = ttk.Button(parent, text=text, command=cmd, style="Accent.TButton" if accent and sv_ttk else "TButton")
        self.btns.append(b)
        return b

    def show_page(self, key):
        self.page = key
        self.pages[key].tkraise()
        for k, it in self.nav_items.items():
            it.set_selected(k == key)
        hook = getattr(self, f"_on_show_{key}", None)
        if hook:
            hook()

    # ───────────────────────── infra ─────────────────────────

    def _poll(self):
        try:
            while True:
                self.q.get_nowait()()
        except queue.Empty:
            pass
        except tk.TclError:
            pass
        self.root.after(80, self._poll)

    def run_bg(self, task, fn, on_done, determinate=False, cancellable=True):
        """Jalankan fn() di thread. fn boleh memakai self.cancel_event dan self.report(done, total, unit)."""
        if self.busy:
            self.infobar.show("info", T("busy"), timeout=3000)
            return
        self.busy = True
        self.infobar.hide()  # pesan dari tugas sebelumnya tidak relevan lagi
        self.cancel_event = threading.Event()
        self._task = {"name": task, "start": time.time(), "done": 0, "total": None, "unit": "items",
                      "last_ui": 0.0}
        for b in self.btns:
            try:
                b.state(["disabled"])
            except tk.TclError:
                pass
        self.progress_row.grid()
        self.cancel_btn.configure(text=T("btn_cancel"))
        self.cancel_btn.state(["!disabled"])
        if cancellable:
            self.cancel_btn.grid()
        else:
            self.cancel_btn.grid_remove()
        self.progress.configure(mode="indeterminate", value=0)
        self.progress.start(10)
        self._progress_mode = "indeterminate"
        self.root.configure(cursor="watch")
        self._tick_progress()

        def worker():
            try:
                res, err = fn(), None
            except (UserError, org.AccessBlocked, org.Cancelled, org.FolderBusy) as e:
                res, err = None, e
            except org.ConfigError as e:
                res, err = None, UserError(str(e.code))
            except BaseException as e:  # noqa
                org.log.error("task '%s' failed", task, exc_info=True)
                res, err = None, RuntimeError(f"{e}\n\n{traceback.format_exc()}")
            self.q.put(lambda: self._finish(on_done, res, err))

        threading.Thread(target=worker, daemon=True).start()

    def report(self, done, total=None, unit="items"):
        """Dipanggil dari thread worker; UI diperbarui maksimal ~8x per detik."""
        t = self._task
        if not t:
            return
        t["done"], t["total"], t["unit"] = done, total, unit
        now = time.time()
        if now - t["last_ui"] >= 0.12 or (total and done >= total):
            t["last_ui"] = now
            self.q.put(self._render_progress)

    def _progress_cb(self, i, n):  # kompatibel dengan engine.execute(progress=...)
        self.report(i, n, "items")

    def _fmt_amount(self, n, unit):
        return org.human(n) if unit == "bytes" else f"{n:,}"

    def _render_progress(self):
        t = self._task
        if not t or not self.busy:
            return
        elapsed = time.time() - t["start"]
        parts = [t["name"]]
        if self.cancel_event.is_set():
            parts.append(T("cancelling"))
        elif t["total"]:
            if self._progress_mode != "determinate":
                self.progress.stop()
                self.progress.configure(mode="determinate", maximum=100)
                self._progress_mode = "determinate"
            pct = min(100.0, t["done"] * 100.0 / t["total"])
            self.progress.configure(value=pct)
            parts.append(T("prog_items", done=self._fmt_amount(t["done"], t["unit"]),
                           total=self._fmt_amount(t["total"], t["unit"])))
            if elapsed > 1.5 and 0 < t["done"] < t["total"]:
                eta = elapsed * (t["total"] - t["done"]) / t["done"]
                parts.append(T("prog_eta", t=fmt_duration(eta)))
        else:
            if t["done"]:
                parts.append(T("prog_files", n=f"{t['done']:,}") if t["unit"] == "files"
                             else self._fmt_amount(t["done"], t["unit"]))
            parts.append(T("prog_elapsed", t=fmt_duration(elapsed)))
        try:
            self.progress_text.configure(text="  ·  ".join(parts))
        except tk.TclError:
            pass

    def _tick_progress(self):
        if self.busy:
            self._render_progress()
            self.root.after(500, self._tick_progress)

    def phase(self, name):
        """Ganti label tahap pada progress (dipanggil dari worker), ETA dihitung ulang dari awal tahap."""
        if self._task:
            self._task.update(name=name, done=0, total=None, unit="items", start=time.time(), last_ui=0.0)

    def files_progress(self):
        return lambda n, _total: self.report(n, None, "files")

    def bytes_progress(self):
        return lambda done, total: self.report(done, total, "bytes")

    def cancel_task(self, _=None):
        if self.busy and not self.cancel_event.is_set():
            self.cancel_event.set()
            self.cancel_btn.state(["disabled"])
            self._render_progress()

    def _finish(self, on_done, res, err):
        self.busy = False
        self._task = None
        self.root.configure(cursor="")
        try:
            self.progress.stop()
            self.progress_row.grid_remove()
        except tk.TclError:
            pass
        for b in self.btns:
            try:
                b.state(["!disabled"])
            except tk.TclError:
                pass
        if isinstance(err, org.Cancelled):
            self.infobar.show("info", T("ib_cancelled_title"), T("ib_cancelled_read"), timeout=6000)
        elif isinstance(err, org.AccessBlocked):
            self.show_blocked(err)
        elif isinstance(err, org.FolderBusy):
            self.infobar.show("warning", T("ib_busy_title"), str(err))
        elif isinstance(err, RuntimeError):  # error tak terduga: sudah dicatat di log
            self.infobar.show("error", T("err_title"), str(err).split("\n\n")[0] + ". " + T("err_unexpected_msg"),
                              action=(T("btn_open_log"), lambda: open_path(org.log_dir() / org.LOG_FILE_NAME)))
        elif err:
            self.infobar.show("error", T("err_title"), str(err).split("\n\n")[0])
        else:
            on_done(res)
        self._sync_buttons()

    def _on_tk_error(self, exc_type, exc, tb):
        """Error di callback tombol/menu: catat ke log + tampilkan InfoBar; app tetap jalan."""
        org.setup_logging()
        org.log.error("UI callback error", exc_info=(exc_type, exc, tb))
        try:
            self.infobar.show("error", T("err_unexpected_title"),
                              f"{exc_type.__name__}: {exc}. {T('err_unexpected_msg')}",
                              action=(T("btn_open_log"), lambda: open_path(org.log_dir() / org.LOG_FILE_NAME)))
        except Exception:
            pass

    # ── keyboard ──
    def _bind_shortcuts(self):
        r = self.root
        order = self.PAGES + self.FOOTER_PAGES
        for i, key in enumerate(order, start=1):
            r.bind_all(f"<Control-Key-{i}>", lambda e, k=key: self.show_page(k))
        r.bind_all("<Control-o>", lambda e: self._pick_folder())
        r.bind_all("<Control-O>", lambda e: self._pick_folder())
        r.bind_all("<Escape>", self.cancel_task, add="+")
        r.bind_all("<F5>", lambda e: self._refresh_current())

    def _refresh_current(self):
        if self.busy:
            return
        action = {"overview": "do_scan", "organize": "do_preview", "dupes": "do_find_dupes",
                  "history": "refresh_history", "labels": "refresh_labels"}.get(self.page)
        if action:
            getattr(self, action)()

    def focus_rail(self, key, delta):
        order = self.PAGES + self.FOOTER_PAGES
        nxt = order[(order.index(key) + delta) % len(order)]
        self.nav_items[nxt].focus_set()

    def show_blocked(self, err):
        exe = sys.executable.replace("python.exe", "pythonw.exe") if sys.executable.lower().endswith(
            "python.exe") else sys.executable
        self.infobar.show("warning", T("err_blocked_title"), T("err_blocked_msg", path=err.path, exe=exe),
                          action=(T("btn_open_protection"), lambda: open_path("windowsdefender://ransomwareprotection")))

    def _sync_buttons(self):
        try:
            if not any(it["on"] for it in self.plan):
                self.btn_apply.state(["disabled"])
            if not any(g["on"] for g in self.dup_groups):
                self.btn_dup.state(["disabled"])
            if not any(j.suffix == ".jsonl" for j in self.journals):
                self.btn_undo.state(["disabled"])
            self._sync_rules_footer()
            self._sync_unlabel()
        except (AttributeError, tk.TclError):
            pass

    def _target(self) -> Path:
        if not self.folder:
            raise UserError(T("err_no_folder"))
        p = Path(self.folder).expanduser()
        if not p.is_dir():
            raise UserError(T("err_folder_missing", path=p))
        return p.resolve()

    def _cfg(self) -> dict:
        try:
            return org.load_config(RULES_PATH)
        except SystemExit as e:
            raise UserError(str(e.code))
        except Exception as e:
            raise UserError(T("rules_load_error", err=e))

    def _prep(self):
        try:
            return self._target(), self._cfg()
        except UserError as e:
            self.infobar.show("warning", str(e), timeout=6000)
            return None

    def _guard_watch(self):
        if self.watch_active:
            self.infobar.show("warning", T("auto_block"), timeout=6000)
            return False
        return True

    def _save_settings(self):
        try:
            if self.root.state() == "normal":
                self.settings["geometry"] = self.root.geometry()
        except tk.TclError:
            pass
        self.settings.update(folder=self.folder, lang=T.lang, theme=self.theme_mode,
                             interval=self.watch_interval_value, journal_days=self.journal_days)
        save_settings(self.settings)

    def _on_close(self):
        if self.dirty:
            r = Dialog(self, T("dlg_unsaved_title"), T("dlg_unsaved_msg"),
                       [("save", T("btn_save"), True), ("discard", T("btn_dont_save"), False),
                        (None, T("btn_cancel"), False)]).result
            if r is None:
                return
            if r == "save" and not self.save_rules():
                return
        self.watch_stop.set()
        self._save_settings()
        self.root.destroy()

    # ── target ──
    def _pick_folder(self):
        d = filedialog.askdirectory(initialdir=self.folder or str(Path.home()), title=T("pick_folder_title"))
        if not d:
            return
        self.folder = str(Path(d))
        self.plan, self.dup_groups, self.scan_result, self.dup_root = [], [], None, None
        self._save_settings()
        self._build_shell()

    def _open_target(self):
        try:
            open_path(self._target())
        except UserError as e:
            self.infobar.show("warning", str(e), timeout=5000)

