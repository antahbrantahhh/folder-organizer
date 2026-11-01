"""Halaman Labels."""

import tkinter as tk
from tkinter import ttk

from gui.common import (org, T, sv_ttk, UserError)
from gui.widgets import (EmptyState, Dialog, TreeTooltip, make_tree)


class LabelsPage:
    # ───────────────────────── page: Labels ─────────────────────────

    def _page_labels(self, f):
        self._page_header(f, "labels")
        bar = ttk.Frame(f)
        bar.pack(fill="x")
        self.btn_apply_labels = self._btn(bar, T("btn_apply_labels"), self.do_labels, accent=True)
        self.btn_apply_labels.pack(side="left")
        ttk.Button(bar, text=T("btn_edit_desc"), command=lambda: self.open_rules("labels")).pack(side="left", padx=8)
        self.btn_create_missing = ttk.Button(bar, text="", command=self.do_create_missing)  # hanya kalau ada yang belum ada
        self.btn_unlabel = self._btn(bar, T("btn_remove_labels"), self.do_remove_labels)
        self.btn_unlabel.pack(side="right")
        body = ttk.Frame(f)
        body.pack(fill="both", expand=True, pady=(12, 0))
        self.lbl_empty = EmptyState(body, self, "labels")
        self.lbl_frame, self.label_tree = make_tree(body, ("folder", "desc", "status"),
                                                    (T("col_folder"), T("col_desc"), T("col_status")),
                                                    (220, 380, 150), stretch=("desc",))
        self.label_tree.tag_configure("muted", foreground=self.pal["muted"])
        self.label_tree.tag_configure("orphan", foreground=self.pal["warning"][1])
        self.label_tree.bind("<Double-1>", lambda e: self._reveal_rel(self.label_tree, 0))
        self.label_tree.bind("<<TreeviewSelect>>", lambda e: self._sync_unlabel())
        self.label_tree.bind("<Delete>", lambda e: self.do_remove_labels())
        TreeTooltip(self, self.label_tree, ("folder", "desc"))
        self.lbl_summary = ttk.Label(f, text="", style="Muted.TLabel")
        self.lbl_summary.pack(anchor="w", pady=(8, 0))
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
        self.label_rows, rows, self.missing_labels = {}, [], []
        for rel_path, desc, _ in entries:
            norm = rel_path.replace("\\", "/").strip("/")
            if root is None:
                status, labeled = "—", False
            elif not (root / rel_path).is_dir():
                status, labeled = T("lbl_missing"), False
                self.missing_labels.append(rel_path)
            elif norm in managed:
                status, labeled = T("lbl_labeled"), True
            else:
                status, labeled = T("lbl_unlabeled"), False
            rows.append((status == T("lbl_missing"), rel_path, desc, status, labeled))
        for missing, rel_path, desc, status, labeled in sorted(rows, key=lambda r: r[0]):  # yang ada di atas
            iid = t.insert("", "end", values=(rel_path, " ".join(str(desc).split()), status),
                           tags=("muted",) if missing else ())
            self.label_rows[iid] = (rel_path, labeled)
        for rel_path in orphans:  # label buatan app yang sudah tidak ada di aturan
            iid = t.insert("", "end", values=(rel_path, "", T("lbl_orphan")), tags=("orphan",))
            self.label_rows[iid] = (rel_path, True)
        self._sync_unlabel()
        self._sync_label_actions(len(entries))

    def _sync_label_actions(self, total=None):
        """Apply hanya aktif kalau ada folder yang ada; folder yang belum ada bisa dibuat sekaligus."""
        try:
            missing = len(getattr(self, "missing_labels", []))
            total = total if total is not None else len(getattr(self, "label_rows", {}))
            existing = max(0, total - missing)
            self.btn_apply_labels.state(["!disabled"] if existing and not self.busy else ["disabled"])
            if missing:
                # belum ada satu pun folder → membuat folder adalah langkah utama
                self.btn_create_missing.configure(text=T("btn_create_missing", n=missing),
                                                  style="Accent.TButton" if (sv_ttk and not existing) else "TButton")
                self.btn_create_missing.pack(side="left")
                self.btn_create_missing.state(["disabled"] if self.busy else ["!disabled"])
            else:
                self.btn_create_missing.pack_forget()
            self.lbl_summary.configure(text=T("lbl_summary", ok=existing, n=total, missing=missing) if total else "")
        except (AttributeError, tk.TclError):
            pass

    def _after_task_sync(self):
        self._sync_label_actions()

    def do_create_missing(self):
        missing = list(getattr(self, "missing_labels", []))
        if not missing:
            return
        try:
            root = self._target()
            org.check_target(root)
        except UserError as e:
            self.infobar.show("warning", str(e), timeout=5000)
            return
        except SystemExit as e:
            self.infobar.show("error", T("err_title"), str(e.code))
            return
        if Dialog(self, T("dlg_create_missing_title", n=len(missing)), T("dlg_create_missing_msg"),
                  [("ok", T("btn_create"), True), (None, T("btn_cancel"), False)],
                  [m.replace("\\", "/") for m in missing[:40]]).result != "ok":
            return
        made, failed = 0, []
        for rel_path in missing:
            folder = org._label_folder(root, rel_path)
            if folder is None:
                failed.append(rel_path)
                continue
            try:
                folder.mkdir(parents=True, exist_ok=True)
                made += 1
            except OSError as e:
                failed.append(f"{rel_path} — {e}")
        org.log.info("created %d label folders in %s", made, root)
        self.refresh_labels()
        if failed:
            self.infobar.show("warning", T("ib_created_folders", n=made), "\n".join(failed[:5]))
        else:
            self.infobar.show("success", T("ib_created_folders", n=made), T("ib_created_folders_next"),
                              timeout=8000, action=(T("btn_apply_labels"), self.do_labels))

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

