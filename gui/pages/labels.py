"""Halaman Labels."""

import tkinter as tk
from tkinter import ttk

from gui.common import (org, T, UserError)
from gui.widgets import (EmptyState, Dialog, make_tree)


class LabelsPage:
    # ───────────────────────── page: Labels ─────────────────────────

    def _page_labels(self, f):
        self._page_header(f, "labels")
        bar = ttk.Frame(f)
        bar.pack(fill="x")
        self._btn(bar, T("btn_apply_labels"), self.do_labels, accent=True).pack(side="left")
        ttk.Button(bar, text=T("btn_edit_desc"), command=lambda: self.open_rules("labels")).pack(side="left", padx=8)
        self.btn_unlabel = self._btn(bar, T("btn_remove_labels"), self.do_remove_labels)
        self.btn_unlabel.pack(side="right")
        body = ttk.Frame(f)
        body.pack(fill="both", expand=True, pady=(12, 0))
        self.lbl_empty = EmptyState(body, self, "labels")
        self.lbl_frame, self.label_tree = make_tree(body, ("folder", "desc", "status"),
                                                    (T("col_folder"), T("col_desc"), T("col_status")),
                                                    (260, 620, 150), stretch=("desc",))
        self.label_tree.tag_configure("muted", foreground=self.pal["muted"])
        self.label_tree.tag_configure("orphan", foreground=self.pal["warning"][1])
        self.label_tree.bind("<Double-1>", lambda e: self._reveal_rel(self.label_tree, 0))
        self.label_tree.bind("<<TreeviewSelect>>", lambda e: self._sync_unlabel())
        self.label_tree.bind("<Delete>", lambda e: self.do_remove_labels())
        self.refresh_labels()

    def _on_show_labels(self):
        self.refresh_labels()

    def refresh_labels(self):
        try:
            t = self.label_tree
        except AttributeError:
            return
        t.delete(*t.get_children())
        try:
            cfg = self._cfg()
        except UserError as e:
            self.infobar.show("error", T("err_title"), str(e))
            return
        entries = org.folder_info_entries(cfg)
        try:
            root = self._target()
            managed = set(org.find_managed_labels(root))
        except (UserError, OSError):
            root, managed = None, set()
        known = {p.replace("\\", "/").strip("/") for p, _, _ in entries}
        orphans = sorted(managed - known, key=str.lower)
        if not entries and not orphans:
            self.lbl_frame.pack_forget()
            self.lbl_empty.pack(fill="both", expand=True)
            self.lbl_empty.set(T("empty_labels_title"), T("empty_labels_desc"),
                               (T("btn_edit_desc"), lambda: self.open_rules("labels")))
            self._sync_unlabel()
            return
        self.lbl_empty.pack_forget()
        self.lbl_frame.pack(fill="both", expand=True)
        self.label_rows = {}
        for rel_path, desc, _ in entries:
            norm = rel_path.replace("\\", "/").strip("/")
            if root is None:
                status, labeled = "—", False
            elif not (root / rel_path).is_dir():
                status, labeled = T("lbl_missing"), False
            elif norm in managed:
                status, labeled = T("lbl_labeled"), True
            else:
                status, labeled = T("lbl_unlabeled"), False
            iid = t.insert("", "end", values=(rel_path, " ".join(str(desc).split()), status),
                           tags=("muted",) if status == T("lbl_missing") else ())
            self.label_rows[iid] = (rel_path, labeled)
        for rel_path in orphans:  # label buatan app yang sudah tidak ada di aturan
            iid = t.insert("", "end", values=(rel_path, "", T("lbl_orphan")), tags=("orphan",))
            self.label_rows[iid] = (rel_path, True)
        self._sync_unlabel()

    def _sync_unlabel(self):
        try:
            rows = getattr(self, "label_rows", {})
            sel = [rows[i] for i in self.label_tree.selection() if i in rows]
            ok = any(labeled for _, labeled in sel) and not self.busy
            self.btn_unlabel.state(["!disabled"] if ok else ["disabled"])
        except (AttributeError, tk.TclError):
            pass

    def do_remove_labels(self):
        rows = getattr(self, "label_rows", {})
        paths = [rows[i][0] for i in self.label_tree.selection() if i in rows and rows[i][1]]
        if not paths:
            self.infobar.show("info", T("info_select_labels"), timeout=4000)
            return
        try:
            root = self._target()
        except UserError as e:
            self.infobar.show("warning", str(e), timeout=5000)
            return
        if Dialog(self, T("dlg_unlabel_title", n=len(paths)), T("dlg_unlabel_msg"),
                  [("ok", T("btn_remove_labels"), True), (None, T("btn_cancel"), False)]).result != "ok":
            return

        def done(results):
            ok = sum(r[1] == "ok" for r in results)
            err = [f"{r[0]} — {r[2]}" for r in results if r[1] == "error"]
            self.refresh_labels()
            if err:
                self.infobar.show("warning", T("ib_labels_err"), T("ib_unlabeled", n=ok),
                                  action=(T("btn_details"), lambda: Dialog(self, T("ib_labels_err"), "",
                                                                            [("ok", T("btn_close"), True)], err)))
            else:
                self.infobar.show("success", T("ib_moved_title"), T("ib_unlabeled", n=ok), timeout=7000)

        self.run_bg(T("task_unlabel"), lambda: org.remove_labels(root, paths), done, cancellable=False)

    def do_labels(self):
        prep = self._prep()
        if not prep:
            return
        root, cfg = prep

        def done(results):
            ok = sum(r[1] == "ok" for r in results)
            err = [f"{r[0]} — {r[2]}" for r in results if r[1] == "error"]
            self.refresh_labels()
            if err:
                self.infobar.show("warning", T("ib_labels_err"), T("ib_labels", n=ok),
                                  action=(T("btn_details"), lambda: Dialog(self, T("ib_labels_err"), "",
                                                                            [("ok", T("btn_close"), True)], err)))
            else:
                self.infobar.show("success", T("ib_moved_title"), T("ib_labels", n=ok), timeout=7000)

        self.run_bg(T("task_labels"), lambda: org.apply_labels(root, cfg), done, cancellable=False)

