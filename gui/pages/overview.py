"""Halaman Overview."""
from datetime import datetime

import tkinter as tk
from tkinter import ttk

from gui.common import (org, T, UserError, reveal)
from gui.widgets import (EmptyState, make_tree)


class OverviewPage:
    # ───────────────────────── page: Overview ─────────────────────────

    def _page_overview(self, f):
        self._page_header(f, "overview")
        bar = ttk.Frame(f)
        bar.pack(fill="x")
        self._btn(bar, T("btn_scan"), self.do_scan, accent=True).pack(side="left")
        self.scan_recursive = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text=T("chk_subfolders"), variable=self.scan_recursive).pack(side="left", padx=14)

        self.ov_body = ttk.Frame(f)
        self.ov_body.pack(fill="both", expand=True, pady=(14, 0))
        self.ov_empty = EmptyState(self.ov_body, self, "overview")
        self.ov_res = ttk.Frame(self.ov_body)

        cards = ttk.Frame(self.ov_res)
        cards.pack(fill="x")
        self.cards = {}
        for i, key in enumerate(["files", "size", "stale", "dupes"]):
            c = ttk.Frame(cards, style="Card.TFrame", padding=(16, 12))
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 10, 0))
            cards.columnconfigure(i, weight=1)
            v, sub = ttk.Label(c, text="—", style="Stat.TLabel"), ttk.Label(c, text="", style="Caption.TLabel")
            v.pack(anchor="w")
            sub.pack(anchor="w")
            self.cards[key] = (v, sub)

        lists = ttk.Frame(self.ov_res)
        lists.pack(fill="both", expand=True, pady=(16, 0))
        lists.columnconfigure(0, weight=2)
        lists.columnconfigure(1, weight=3)
        lists.rowconfigure(1, weight=1)
        ttk.Label(lists, text=T("sec_types"), style="H2.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Label(lists, text=T("sec_largest"), style="H2.TLabel").grid(row=0, column=1, sticky="w", pady=(0, 6),
                                                                          padx=(14, 0))
        fr, self.ext_tree = make_tree(lists, ("ext", "count", "size"),
                                      (T("col_ext"), T("col_count"), T("col_size")), (130, 80, 90), stretch=("ext",))
        fr.grid(row=1, column=0, sticky="nsew")
        fr, self.big_tree = make_tree(lists, ("size", "path"), (T("col_size"), T("col_location")), (90, 400),
                                      stretch=("path",))
        fr.grid(row=1, column=1, sticky="nsew", padx=(14, 0))
        self.big_tree.bind("<Double-1>", lambda e: self._reveal_rel(self.big_tree, 1))

        hint = ttk.Frame(self.ov_res)
        hint.pack(fill="x", pady=(12, 0))
        self.ov_hint = ttk.Label(hint, text="", style="Muted.TLabel")
        self.ov_hint.pack(side="left")
        self.ov_plan_btn = ttk.Button(hint, text=T("btn_view_plan"),
                                      command=lambda: (self.show_page("organize"), self.do_preview()))
        self.ov_plan_btn.pack(side="right")
        self._render_overview()

    def _render_overview(self):
        if not self.scan_result:
            self.ov_res.pack_forget()
            self.ov_empty.pack(fill="both", expand=True)
            if not self.folder:
                self.ov_empty.set(T("empty_no_folder_title"), T("empty_no_folder_desc"),
                                  (T("btn_choose_folder"), self._pick_folder))
            else:
                self.ov_empty.set(T("empty_overview_title"), T("empty_overview_desc"), (T("btn_scan"), self.do_scan))
            return
        self.ov_empty.pack_forget()
        self.ov_res.pack(fill="both", expand=True)
        r = self.scan_result
        files, root = r["files"], r["root"]
        total = sum(s.st_size for _, s in files)
        wasted = sum(g[0][1].st_size * (len(g) - 1) for g in r["groups"])
        extra = sum(len(g) - 1 for g in r["groups"])
        stale_size = sum(s.st_size for s in r["stale"])
        vals = {
            "files": (f"{len(files):,}", T("card_files_all") if r["recursive"] else T("card_files_top")),
            "size": (org.human(total), T("card_size")),
            "stale": (f"{len(r['stale']):,}", T("card_stale", size=org.human(stale_size))),
            "dupes": (f"{extra:,}", T("card_dupes", size=org.human(wasted))),
        }
        for k, (v, sub) in vals.items():
            self.cards[k][0].configure(text=v)
            self.cards[k][1].configure(text=sub)
        self.ext_tree.delete(*self.ext_tree.get_children())
        for e, (n, size) in sorted(r["by_ext"].items(), key=lambda kv: -kv[1][0]):
            self.ext_tree.insert("", "end", values=(e or T("no_ext"), f"{n:,}", org.human(size)))
        self.big_tree.delete(*self.big_tree.get_children())
        for p, st in sorted(files, key=lambda x: -x[1].st_size)[:200]:
            self.big_tree.insert("", "end", values=(org.human(st.st_size), org.rel(root, p)))
        if r["plan"] is None:
            self.ov_hint.configure(text="⚠  " + T("unsafe_hint"), foreground=self.pal["warning"][1])
            self.ov_plan_btn.pack_forget()
        else:
            self.ov_hint.configure(text=T("hint_plan", n=f"{r['plan']:,}") if r["plan"] else T("hint_clean"),
                                   foreground=self.pal["muted"])
            self.ov_plan_btn.pack(side="right")

    def do_scan(self):
        prep = self._prep()
        if not prep:
            return
        root, cfg = prep
        recursive = self.scan_recursive.get()

        def job():
            cancel = self.cancel_event
            files = list(org.iter_files(root, recursive, cfg["exclude"], cancel=cancel,
                                        progress=self.files_progress()))
            now = datetime.now().timestamp()
            by_ext = {}
            for p, st in files:
                c = by_ext.setdefault(org.ext_of(p), [0, 0])
                c[0] += 1
                c[1] += st.st_size
            return dict(root=root, files=files, by_ext=by_ext, recursive=recursive,
                        stale=[s for _, s in files if now - s.st_mtime > 365 * 86400],
                        groups=self._scan_dupes(files, cancel), plan=self._scan_plan(root, cfg, cancel))

        def done(r):
            self.scan_result = r
            self._render_overview()

        self.run_bg(T("task_scan"), job, done)

    def _scan_dupes(self, files, cancel):
        self.phase(T("task_dupes"))
        return org.find_duplicates(files, progress=self.bytes_progress(), cancel=cancel)

    def _scan_plan(self, root, cfg, cancel):
        self.phase(T("task_plan"))
        try:
            return len(org.build_plan(root, cfg, cancel=cancel, progress=self.files_progress()))
        except org.UnsafeTarget:
            return None  # scan (read-only) tetap boleh; merapikan folder ini tidak

    def _reveal_rel(self, tree, col):
        sel = tree.focus()
        if sel:
            try:
                reveal(self._target() / tree.item(sel, "values")[col])
            except UserError:
                pass

