"""Widget gaya Windows 11: rail, tooltip, InfoBar, EmptyState, dialog, tabel."""

import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont

from gui.common import (T, sv_ttk, GLYPH, paint_titlebar)


# ───────────────────────── widgets ─────────────────────────

class Fonts:
    def __init__(self, root):
        fams = set(tkfont.families(root))
        self.text = next((f for f in ("Segoe UI Variable Text", "Segoe UI") if f in fams), "TkDefaultFont")
        self.display = next((f for f in ("Segoe UI Variable Display", "Segoe UI") if f in fams), self.text)
        self.icon = next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in fams), None)
        self.mono = next((f for f in ("Cascadia Mono", "Cascadia Code", "Consolas", "DejaVu Sans Mono") if f in fams),
                         "TkFixedFont")


class Tooltip:
    """Tooltip gaya Win 11, muncul setelah jeda singkat."""

    def __init__(self, app, widgets, text, side="right"):
        self.app, self.text, self.side, self.tw, self.job = app, text, side, None, None
        self.anchor = widgets[0]
        for w in widgets:
            w.bind("<Enter>", self._schedule, add="+")
            w.bind("<Leave>", self._hide, add="+")
            w.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _=None):
        self._cancel()
        self.job = self.anchor.after(350, self._show)

    def _cancel(self):
        if self.job:
            self.anchor.after_cancel(self.job)
            self.job = None

    def _show(self):
        if self.tw:
            return
        p, f = self.app.pal, self.app.fonts
        self.tw = tw = tk.Toplevel(self.anchor)
        tw.overrideredirect(True)
        tw.attributes("-topmost", True)
        tk.Label(tw, text=self.text, bg=p["tip_bg"], fg=p["text"], font=(f.text, 9), padx=8, pady=4,
                 highlightthickness=1, highlightbackground=p["border"]).pack()
        tw.update_idletasks()
        a = self.anchor
        x = a.winfo_rootx() + a.winfo_width() + 6
        y = a.winfo_rooty() + (a.winfo_height() - tw.winfo_reqheight()) // 2
        tw.geometry(f"+{x}+{y}")

    def show_now(self, timeout=2500):
        """Tampilkan langsung (mis. saat fokus keyboard), lalu sembunyikan otomatis."""
        self._cancel()
        self._show()
        self.job = self.anchor.after(timeout, self._hide)

    def _hide(self, _=None):
        self._cancel()
        if self.tw:
            self.tw.destroy()
            self.tw = None


class RailItem(tk.Frame):
    """Item navigation rail: ikon SVG (dirender ke PNG per tema/DPI), label lewat tooltip.
    Bisa dipakai dengan keyboard: Tab untuk fokus, Enter/Spasi untuk membuka, panah atas/bawah untuk pindah."""

    def __init__(self, parent, app, key, text, command, hint=None):
        p, f = app.pal, app.fonts
        size = app.rail_px + 20
        super().__init__(parent, bg=p["bg"], width=size + 4, height=size, cursor="hand2", takefocus=1,
                         highlightthickness=2, highlightbackground=p["bg"], highlightcolor=p["accent"])
        self.pack_propagate(False)
        self.app, self.key, self.command, self.selected = app, key, command, False
        imgs = app.rail_icons.get(key)
        if imgs:
            self.icon = tk.Label(self, image=imgs["normal"], bg=p["bg"], bd=0)
        else:  # fallback kalau file ikon tidak ada
            self.icon = tk.Label(self, text=text[:2], bg=p["bg"], fg=p["text"], font=(f.text, 10, "bold"))
        self.icon.place(relx=0.5, rely=0.5, anchor="center")
        self.ind = tk.Frame(self, width=3, height=16, bg=p["bg"])
        self.ind.place(x=0, rely=0.5, anchor="w")
        for w in (self, self.icon):
            w.bind("<Button-1>", lambda e: self._activate())
            w.bind("<Enter>", lambda e: self._paint(hover=True), add="+")
            w.bind("<Leave>", lambda e: self._paint(), add="+")
        self.tip = Tooltip(app, [self, self.icon], f"{text}   {hint}" if hint else text)
        self.bind("<Return>", lambda e: self._activate())
        self.bind("<space>", lambda e: self._activate())
        self.bind("<Up>", lambda e: app.focus_rail(self.key, -1))
        self.bind("<Down>", lambda e: app.focus_rail(self.key, 1))
        self.bind("<FocusIn>", lambda e: (self._paint(hover=True), self.tip.show_now()), add="+")
        self.bind("<FocusOut>", lambda e: (self._paint(), self.tip._hide()), add="+")

    def _activate(self):
        self.tip._hide()
        self.command(self.key)

    def set_selected(self, sel):
        self.selected = sel
        self._paint()

    def _paint(self, hover=False):
        p = self.app.pal
        bg = p["nav_sel"] if self.selected else (p["nav_hover"] if hover else p["bg"])
        self.configure(bg=bg, highlightbackground=p["bg"])
        imgs = self.app.rail_icons.get(self.key)
        if imgs:
            self.icon.configure(bg=bg, image=imgs["active" if self.selected else "normal"])
        else:
            self.icon.configure(bg=bg, fg=p["accent"] if self.selected else p["text"])
        self.ind.configure(bg=p["accent"] if self.selected else bg)


class InfoBar(tk.Frame):
    """Notifikasi inline gaya Win 11 (success / warning / error / info)."""

    def __init__(self, parent, app):
        super().__init__(parent, bg=app.pal["bg"])
        self.app, self._after = app, None

    def show(self, kind, title, message="", timeout=None, action=None):
        for w in self.winfo_children():
            w.destroy()
        if self._after:
            self.after_cancel(self._after)
            self._after = None
        bg, fg = self.app.pal[kind]
        inner = tk.Frame(self, bg=bg, highlightthickness=1, highlightbackground=self.app.pal["border"])
        inner.pack(fill="x")
        f = self.app.fonts
        if f.icon:
            tk.Label(inner, text=GLYPH[kind], bg=bg, fg=fg, font=(f.icon, 12)).pack(side="left", padx=(14, 8), pady=10)
        close = tk.Label(inner, text=GLYPH["close"] if f.icon else "✕", bg=bg, fg=self.app.pal["muted"],
                         font=(f.icon or f.text, 9), cursor="hand2")
        close.pack(side="right", padx=14)
        close.bind("<Button-1>", lambda e: self.hide())
        if action:
            ttk.Button(inner, text=action[0], command=action[1]).pack(side="right", padx=(8, 4), pady=6)
        col = tk.Frame(inner, bg=bg)
        col.pack(side="left", fill="x", expand=True, padx=(0 if f.icon else 14, 8), pady=9)
        tk.Label(col, text=title, bg=bg, fg=self.app.pal["text"], font=(f.text, 10, "bold"), anchor="w",
                 justify="left").pack(fill="x")
        if message:
            msg = tk.Label(col, text=message, bg=bg, fg=self.app.pal["text"], font=(f.text, 10), anchor="w",
                           justify="left")
            msg.pack(fill="x")
            col.bind("<Configure>", lambda e: msg.configure(wraplength=max(200, e.width - 8)))
        self.grid()
        if timeout:
            self._after = self.after(timeout, self.hide)

    def hide(self):
        self.grid_remove()


class EmptyState(ttk.Frame):
    def __init__(self, parent, app, glyph="empty"):
        super().__init__(parent)
        self.app = app
        box = ttk.Frame(self)
        box.place(relx=0.5, rely=0.42, anchor="center")
        f = app.fonts
        self.icon = ttk.Label(box, text=GLYPH[glyph] if f.icon else "", font=(f.icon or f.text, 36),
                              foreground=app.pal["muted"])
        self.icon.pack()
        self.title = ttk.Label(box, text="", font=(f.display, 15, "bold"))
        self.title.pack(pady=(10, 4))
        self.desc = ttk.Label(box, text="", style="Muted.TLabel", wraplength=420, justify="center")
        self.desc.pack()
        self.btn = ttk.Button(box, style="Accent.TButton" if sv_ttk else "TButton")
        self._btn_shown = False

    def set(self, title, desc, button=None):
        self.title.configure(text=title)
        self.desc.configure(text=desc)
        if button:
            self.btn.configure(text=button[0], command=button[1])
            self.btn.pack(pady=(16, 0))
        else:
            self.btn.pack_forget()


class ScrollFrame(ttk.Frame):
    def __init__(self, parent, bg):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, bg=bg)
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=vsb.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(win, width=e.width))
        self.bind("<Enter>", lambda e: self._wheel(True))
        self.bind("<Leave>", lambda e: self._wheel(False))

    def _wheel(self, on):
        if on:
            self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-e.delta / 120), "units"))
            self.canvas.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-1, "units"))
            self.canvas.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(1, "units"))
        else:
            for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                self.canvas.unbind_all(ev)


class Dialog(tk.Toplevel):
    """ContentDialog gaya Win 11. buttons = [(key, text, accent)]. Return key atau None."""

    def __init__(self, app, title, message, buttons, detail=None):
        super().__init__(app.root)
        self.withdraw()
        self.result = None
        self.title(T("app_title"))
        self.transient(app.root)
        self.resizable(False, False)
        body = ttk.Frame(self, padding=(24, 22, 24, 8))
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=title, style="Subtitle.TLabel", wraplength=460).pack(anchor="w")
        if message:
            ttk.Label(body, text=message, wraplength=460, justify="left").pack(anchor="w", pady=(10, 0))
        if detail:
            txt = tk.Text(body, height=min(8, len(detail)), width=60, relief="flat", font=(app.fonts.text, 9),
                          bg=app.pal["code_bg"], fg=app.pal["text"], highlightthickness=1,
                          highlightbackground=app.pal["border"], padx=8, pady=6)
            txt.insert("1.0", "\n".join(detail))
            txt.configure(state="disabled")
            txt.pack(fill="x", pady=(12, 0))
        bar = ttk.Frame(self, padding=(24, 16, 24, 20))
        bar.pack(fill="x")
        default = None
        for i, (key, text, accent) in enumerate(buttons):
            b = ttk.Button(bar, text=text, command=lambda k=key: self._done(k),
                           style="Accent.TButton" if accent and sv_ttk else "TButton")
            b.pack(side="left", fill="x", expand=True, padx=(0 if i == 0 else 8, 0))
            if accent and default is None:
                default = key
        self.bind("<Escape>", lambda e: self._done(None))
        self.bind("<Return>", lambda e: self._done(default if default else buttons[0][0]))
        self.protocol("WM_DELETE_WINDOW", lambda: self._done(None))
        self.update_idletasks()
        w, h = max(self.winfo_reqwidth(), 440), self.winfo_reqheight()
        px, py = app.root.winfo_rootx(), app.root.winfo_rooty()
        pw, ph = app.root.winfo_width(), app.root.winfo_height()
        self.geometry(f"{w}x{h}+{px + (pw - w) // 2}+{py + (ph - h) // 3}")
        self.deiconify()
        paint_titlebar(self, app.pal["bg"], app.is_dark)
        self.grab_set()
        self.focus_set()
        app.root.wait_window(self)

    def _done(self, key):
        self.result = key
        self.grab_release()
        self.destroy()


def make_tree(parent, columns, headings, widths, show="headings", stretch=None, height=None):
    frame = ttk.Frame(parent)
    tree = ttk.Treeview(frame, columns=columns, show=show, selectmode="extended", height=height or 10,
                        style="Flat.Treeview")
    for col, head, w in zip(columns, headings, widths):
        tree.heading(col, text=head, anchor="w")
        tree.column(col, width=w, minwidth=30, anchor="w", stretch=(col in stretch) if stretch else True)
    vs = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vs.set)
    tree.grid(row=0, column=0, sticky="nsew")
    vs.grid(row=0, column=1, sticky="ns")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    return frame, tree




class TreeTooltip:
    """Tooltip untuk sel Treeview yang terpotong: arahkan mouse ke sel → teks lengkap muncul."""

    def __init__(self, app, tree, columns=None):
        self.app, self.tree, self.columns = app, tree, columns
        self.tw, self.job, self.cell = None, None, None
        self.font = tkfont.nametofont("TkDefaultFont")
        try:
            style_font = ttk.Style().lookup(str(tree.cget("style")) or "Treeview", "font")
            if style_font:
                self.font = tkfont.Font(font=style_font)
        except tk.TclError:
            pass
        tree.bind("<Motion>", self._motion, add="+")
        tree.bind("<Leave>", self._hide, add="+")
        tree.bind("<ButtonPress>", self._hide, add="+")
        tree.bind("<MouseWheel>", self._hide, add="+")

    def _cell_text(self, row, col):
        if col == "#0":
            return self.tree.item(row, "text").strip()
        idx = int(col[1:]) - 1
        vals = self.tree.item(row, "values")
        cid = self.tree["columns"][idx] if idx < len(self.tree["columns"]) else None
        if self.columns and cid not in self.columns:
            return ""
        return str(vals[idx]) if idx < len(vals) else ""

    def _motion(self, e):
        row, col = self.tree.identify_row(e.y), self.tree.identify_column(e.x)
        cell = (row, col)
        if cell == self.cell:
            return
        self._hide()
        self.cell = cell
        if not row or not col:
            return
        text = self._cell_text(row, col)
        box = self.tree.bbox(row, col)
        if not text or not box or self.font.measure(text) + 16 <= box[2]:
            return  # muat penuh → tidak perlu tooltip
        self.job = self.tree.after(450, lambda: self._show(text, e.x_root, e.y_root))

    def _show(self, text, x, y):
        self.job = None
        try:
            if not self.tree.winfo_exists():
                return
        except tk.TclError:
            return
        p, f = self.app.pal, self.app.fonts
        self.tw = tw = tk.Toplevel(self.tree)
        tw.overrideredirect(True)
        tw.attributes("-topmost", True)
        tk.Label(tw, text=text, bg=p["tip_bg"], fg=p["text"], font=(f.text, 9), padx=8, pady=4, justify="left",
                 wraplength=640, highlightthickness=1, highlightbackground=p["border"]).pack()
        tw.geometry(f"+{x + 12}+{y + 18}")

    def _hide(self, _=None):
        if self.job:
            self.tree.after_cancel(self.job)
            self.job = None
        if self.tw:
            self.tw.destroy()
            self.tw = None
        self.cell = None
