"""Halaman Duplicates."""

from tkinter import ttk

from gui.common import (org, T, UserError, open_path, reveal, fmt_time)
from gui.widgets import (EmptyState, Dialog, make_tree)


class DuplicatesPage:
    # ───────────────────────── page: Duplicates ─────────────────────────

    def _page_dupes(self, f):
        self._page_header(f, "dupes")
        bar = ttk.Frame(f)
        bar.pack(fill="x")
        self._btn(bar, T("btn_find_dupes"), self.do_find_dupes, accent=True).pack(side="left")
        ttk.Button(bar, text=T("btn_make_original"), command=self._make_keeper).pack(side="right")

        body = ttk.Frame(f)
        body.pack(fill="both", expand=True, pady=(12, 0))
        self.dup_empty = EmptyState(body, self, "dupes")
        self.dup_frame, self.dup_tree = make_tree(
            body, ("status", "size", "mtime"), (T("col_status"), T("col_size"), T("col_modified")),
            (170, 90, 170), show="tree headings", stretch=())
        self.dup_tree.heading("#0", text=T("col_file"), anchor="w")
        self.dup_tree.column("#0", width=520, stretch=True)
        self.dup_tree.tag_configure("muted", foreground=self.pal["muted"])
        self.dup_tree.tag_configure("group", font=(self.fonts.text, 10, "bold"))
        self.dup_tree.bind("<Button-1>", self._dup_click)
        self.dup_tree.bind("<Double-1>", self._dup_dbl)

        foot = ttk.Frame(f)
        foot.pack(fill="x", pady=(12, 0))
        self.dup_info = ttk.Label(foot, text="", style="Muted.TLabel")
        self.dup_info.pack(side="left")
        self.btn_dup = self._btn(foot, T("btn_move_dupes", n=0), self.do_move_dupes, accent=True)
        self.btn_dup.pack(side="right")
        ttk.Button(foot, text=T("btn_open_trash"), command=self._open_trash).pack(side="right", padx=8)
        self._render_dupes()

    def do_find_dupes(self):
        prep = self._prep()
        if not prep:
            return
        root, cfg = prep

        def job():
            cancel = self.cancel_event
            files = list(org.iter_files(root, True, cfg["exclude"], cancel=cancel, progress=self.files_progress()))
            self.phase(T("task_dupes"))
            groups = org.find_duplicates(files, progress=self.bytes_progress(), cancel=cancel)
            out = []
            for g in sorted(groups, key=lambda g: -g[0][1].st_size * (len(g) - 1)):
                g.sort(key=lambda x: (x[1].st_mtime, len(str(x[0]))))
                out.append({"files": g, "keeper": 0, "on": set(range(1, len(g)))})
            return root, out

        def done(res):
            self.dup_root, self.dup_groups = res
            self._render_dupes()

        self.run_bg(T("task_dupes"), job, done)

    def _render_dupes(self):
        t = self.dup_tree
        t.delete(*t.get_children())
        if not self.dup_groups:
            self.dup_frame.pack_forget()
            self.dup_empty.pack(fill="both", expand=True)
            if self.dup_root:
                self.dup_empty.set(T("empty_nodupes_title"), T("empty_nodupes_desc"))
            else:
                self.dup_empty.set(T("empty_dupes_title"), T("empty_dupes_desc"),
                                   (T("btn_find_dupes"), self.do_find_dupes))
            self.dup_info.configure(text="")
            self.btn_dup.configure(text=T("btn_move_dupes", n=0))
            self.btn_dup.state(["disabled"])
            return
        self.dup_empty.pack_forget()
        self.dup_frame.pack(fill="both", expand=True)
        root = self.dup_root
        for gi, g in enumerate(self.dup_groups):
            size = g["files"][0][1].st_size
            gid = f"g{gi}"
            t.insert("", "end", iid=gid, open=True, tags=("group",),
                     text=T("dup_group", n=len(g["files"]), name=g["files"][0][0].name),
                     values=(T("dup_save", size=org.human(size * len(g["on"]))), org.human(size), ""))
            for fi, (p, st) in enumerate(g["files"]):
                keeper, on = fi == g["keeper"], fi in g["on"]
                t.insert(gid, "end", iid=f"{gid}:{fi}", text="  " + org.rel(root, p),
                         image=self.check_img["blank"] if keeper else self.check_img["on" if on else "off"],
                         tags=("muted",) if (not keeper and not on) else (),
                         values=(T("dup_keep") if keeper else (T("dup_move") if on else T("dup_leave")),
                                 org.human(st.st_size), fmt_time(st.st_mtime)))
        n = sum(len(g["on"]) for g in self.dup_groups)
        saved = sum(g["files"][0][1].st_size * len(g["on"]) for g in self.dup_groups)
        self.dup_info.configure(text=T("dup_selected", n=f"{n:,}", size=org.human(saved)))
        self.btn_dup.configure(text=T("btn_move_dupes", n=f"{n:,}"))
        self.btn_dup.state(["!disabled"] if n and not self.busy else ["disabled"])

    @staticmethod
    def _dup_ids(iid):
        if not iid or ":" not in iid:
            return None, None
        g, f = iid[1:].split(":")
        return int(g), int(f)

    def _dup_click(self, e):
        t = self.dup_tree
        iid = t.identify_row(e.y)
        if t.identify_column(e.x) == "#0" and iid and ":" in iid:
            box = t.bbox(iid, "#0")
            img_w = self.check_img["on"].width() if self.check_img["on"] else 16
            if not box or e.x > box[0] + 20 + img_w + 8:  # klik di luar kotak centang → seleksi biasa
                return
            gi, fi = self._dup_ids(iid)
            g = self.dup_groups[gi]
            if fi != g["keeper"]:
                g["on"].symmetric_difference_update({fi})
                self._render_dupes()
            return "break"

    def _dup_dbl(self, e):
        gi, fi = self._dup_ids(self.dup_tree.focus())
        if gi is not None:
            reveal(self.dup_groups[gi]["files"][fi][0])

    def _make_keeper(self):
        gi, fi = self._dup_ids(self.dup_tree.focus())
        if gi is None:
            self.infobar.show("info", T("info_pick_in_group"), timeout=4000)
            return
        g = self.dup_groups[gi]
        g["keeper"], g["on"] = fi, set(range(len(g["files"]))) - {fi}
        self._render_dupes()

    def do_move_dupes(self):
        if not self._guard_watch():
            return
        root = self.dup_root
        moves, taken = [], set()
        for g in self.dup_groups:
            keeper = g["files"][g["keeper"]][0]
            for fi in sorted(g["on"]):
                p = g["files"][fi][0]
                moves.append(org.Move(p, org.unique_dest(root / org.TRASH_DIR / org.rel(root, p), taken),
                                      T("e_dup_of", path=org.rel(root, keeper))))
        if not moves:
            return
        r = Dialog(self, T("dlg_dupes_title", n=f"{len(moves):,}"), T("dlg_dupes_msg"),
                   [("ok", T("btn_move"), True), (None, T("btn_cancel"), False)]).result
        if r != "ok":
            return
        scanned = {g["files"][i][0]: g["files"][i][1] for g in self.dup_groups for i in range(len(g["files"]))}
        keepers = {m.src: g["files"][g["keeper"]][0] for g in self.dup_groups for m in moves
                   if any(m.src == f[0] for f in g["files"])}

        def job():
            # file bisa berubah sejak dicek (diedit, di-undo, dipindah watch): yang berubah tidak dipindah
            ok_moves, changed = [], []
            for m in moves:
                if self._dup_changed(m.src, scanned[m.src]) or self._dup_changed(keepers[m.src], scanned[keepers[m.src]]):
                    changed.append((m.src, T("e_dup_changed")))
                else:
                    ok_moves.append(m)
            ok, failed = org.execute(root, ok_moves, "dedupe", self._progress_cb, cancel=self.cancel_event)
            return ok, changed + failed

        self.run_bg(T("task_move"), job, lambda res: self._after_execute(res, root))

    @staticmethod
    def _dup_changed(p, st) -> bool:
        try:
            now = p.stat()
        except OSError:
            return True
        return now.st_size != st.st_size or now.st_mtime != st.st_mtime

    def _open_trash(self):
        try:
            p = self._target() / org.TRASH_DIR
        except UserError as e:
            self.infobar.show("warning", str(e), timeout=5000)
            return
        if p.exists():
            open_path(p)
        else:
            self.infobar.show("info", T("trash_missing"), timeout=5000)

