"""Halaman Organize."""

import tkinter as tk
from tkinter import ttk

from gui.common import (org, T, reveal, reason_label)
from gui.widgets import (EmptyState, Dialog, TreeTooltip, make_tree)


class OrganizePage:
    # ───────────────────────── page: Organize ─────────────────────────

    def _page_organize(self, f):
        self._page_header(f, "organize")
        bar = ttk.Frame(f)
        bar.pack(fill="x")
        # tombol kanan di-pack lebih dulu supaya tetap utuh saat window sempit; kolom Search yang mengecil
        ttk.Button(bar, text=T("btn_clear"), command=lambda: self._set_all_plan(False)).pack(side="right")
        ttk.Button(bar, text=T("btn_select_all"), command=lambda: self._set_all_plan(True)).pack(side="right", padx=6)
        self._btn(bar, T("btn_preview"), self.do_preview, accent=True).pack(side="left")
        ttk.Label(bar, text=T("lbl_rule")).pack(side="left", padx=(18, 6))
        self.rule_filter = ttk.Combobox(bar, state="readonly", width=22)
        self.rule_filter.pack(side="left")
        self.rule_filter.bind("<<ComboboxSelected>>", lambda e: self._render_plan())
        ttk.Label(bar, text=T("lbl_search")).pack(side="left", padx=(14, 6))
        self.plan_search = tk.StringVar()
        self.plan_search.trace_add("write", lambda *a: self._schedule_render())  # debounce: tidak render per huruf
        ttk.Entry(bar, textvariable=self.plan_search, width=10).pack(side="left", fill="x", expand=True, padx=(0, 12))

        body = ttk.Frame(f)
        body.pack(fill="both", expand=True, pady=(12, 0))
        self.plan_empty = EmptyState(body, self, "organize")
        self.plan_frame, self.plan_tree = make_tree(
            body, ("kind", "src", "dst", "rule"),
            (T("col_kind"), T("col_from"), T("col_to"), T("lbl_rule")), (70, 250, 310, 190),
            show="tree headings", stretch=("src", "dst", "rule"))
        TreeTooltip(self, self.plan_tree, ("src", "dst", "rule"))
        self.plan_tree.column("#0", width=48, minwidth=48, stretch=False)
        self.plan_tree.heading("#0", text="", image=self.check_img["off"], command=self._toggle_all_visible)
        self.plan_tree.tag_configure("muted", foreground=self.pal["muted"])
        self.plan_tree.bind("<Button-1>", self._plan_click)
        self.plan_tree.bind("<space>", lambda e: self._toggle_plan_selected())
        self.plan_tree.bind("<Double-1>", lambda e: self._reveal_plan())

        foot = ttk.Frame(f)
        foot.pack(fill="x", pady=(12, 0))
        self.plan_info = ttk.Label(foot, text="", style="Muted.TLabel")
        self.plan_info.pack(side="left")
        self.btn_apply = self._btn(foot, T("btn_apply_n", n=0), self.do_apply, accent=True)
        self.btn_apply.pack(side="right")
        self._plan_previewed = getattr(self, "_plan_previewed", False)
        self._render_plan()

    def do_preview(self):
        prep = self._prep()
        if not prep:
            return
        root, cfg = prep

        def job():
            moves = org.build_plan(root, cfg, cancel=self.cancel_event, progress=self.files_progress())
            return root, [{"move": m, "on": True, "dir": m.src.is_dir()} for m in moves]

        def done(res):
            self.plan_root, self.plan = res
            self._plan_previewed = True
            self._render_plan()

        self.run_bg(T("task_plan"), job, done)

    def _plan_visible(self, it):
        rf = self.rule_filter.get()
        if rf and rf != T("filter_all") and reason_label(it["move"].reason) != rf:
            return False
        q = self.plan_search.get().strip().lower()
        return not q or q in str(it["move"].src).lower() or q in str(it["move"].dst).lower()

    PLAN_ROW_LIMIT = 2000  # tabel Tk melambat drastis di puluhan ribu baris; aksi tetap berlaku ke semua item terfilter

    def _schedule_render(self, delay=250):
        job = getattr(self, "_render_job", None)
        if job:
            self.root.after_cancel(job)
        self._render_job = self.root.after(delay, self._render_plan)

    def _filtered_indices(self):
        return [i for i, it in enumerate(self.plan) if self._plan_visible(it)]

    def _render_plan(self):
        self._render_job = None
        if not self.plan:
            self._filtered = []
            self.plan_frame.pack_forget()
            self.plan_empty.pack(fill="both", expand=True)
            if self._plan_previewed:
                self.plan_empty.set(T("empty_plan_clean_title"), T("empty_plan_clean_desc"))
            else:
                self.plan_empty.set(T("empty_plan_title"), T("empty_plan_desc"), (T("btn_preview"), self.do_preview))
            self.plan_info.configure(text="")
            self.btn_apply.configure(text=T("btn_apply_n", n=0))
            self.btn_apply.state(["disabled"])
            self.rule_filter.configure(values=[T("filter_all")])
            self.rule_filter.set(T("filter_all"))
            return
        self.plan_empty.pack_forget()
        self.plan_frame.pack(fill="both", expand=True)
        rules = [T("filter_all")] + sorted({reason_label(it["move"].reason) for it in self.plan})
        if list(self.rule_filter.cget("values")) != rules:
            cur = self.rule_filter.get()
            self.rule_filter.configure(values=rules)
            self.rule_filter.set(cur if cur in rules else T("filter_all"))
        t = self.plan_tree
        t.delete(*t.get_children())
        self._filtered = self._filtered_indices()
        shown = len(self._filtered)
        for i in self._filtered[:self.PLAN_ROW_LIMIT]:
            it = self.plan[i]
            m = it["move"]
            t.insert("", "end", iid=str(i), tags=() if it["on"] else ("muted",),
                     image=self.check_img["on" if it["on"] else "off"],
                     values=(T("kind_folder") if it["dir"] else T("kind_file"),
                             org.rel(self.plan_root, m.src), org.rel(self.plan_root, m.dst), reason_label(m.reason)))
        self._update_plan_info(shown)

    def _update_plan_info(self, shown=None):
        n_on = sum(it["on"] for it in self.plan)
        txt = T("plan_selected", on=f"{n_on:,}", total=f"{len(self.plan):,}")
        if shown is not None and shown != len(self.plan):
            txt += T("plan_filtered", n=f"{shown:,}")
        filtered = getattr(self, "_filtered", None)
        if filtered is not None and len(filtered) > self.PLAN_ROW_LIMIT:
            tip = T("plan_capped", shown=f"{self.PLAN_ROW_LIMIT:,}", total=f"{len(filtered):,}")
        else:
            tip = T("plan_tip")
        self.plan_info.configure(text=f"{txt}   ·   {tip}")
        self.btn_apply.configure(text=T("btn_apply_n", n=f"{n_on:,}"))
        self.btn_apply.state(["!disabled"] if n_on and not self.busy else ["disabled"])
        visible = getattr(self, "_filtered", None) or []
        n_vis_on = sum(self.plan[i]["on"] for i in visible)
        head = "on" if visible and n_vis_on == len(visible) else ("off" if n_vis_on == 0 else "mixed")
        self.plan_tree.heading("#0", image=self.check_img[head])

    def _set_plan_row(self, iid, on):
        self.plan[int(iid)]["on"] = on
        self.plan_tree.item(iid, image=self.check_img["on" if on else "off"], tags=() if on else ("muted",))

    def _toggle_all_visible(self):
        visible = getattr(self, "_filtered", None) or []
        if visible:
            self._set_all_plan(not all(self.plan[i]["on"] for i in visible))

    def _plan_click(self, e):
        t = self.plan_tree
        if t.identify_region(e.x, e.y) in ("tree", "cell") and t.identify_column(e.x) == "#0":
            iid = t.identify_row(e.y)
            if iid:
                self._set_plan_row(iid, not self.plan[int(iid)]["on"])
                self._update_plan_info()
                return "break"

    def _toggle_plan_selected(self):
        sel = self.plan_tree.selection()
        if sel:
            target = not self.plan[int(sel[0])]["on"]
            for iid in sel:
                self._set_plan_row(iid, target)
            self._update_plan_info()
        return "break"

    def _set_all_plan(self, on):
        """Berlaku ke SEMUA item yang lolos filter, termasuk yang tidak ditampilkan karena batas baris."""
        for i in getattr(self, "_filtered", None) or []:
            self.plan[i]["on"] = on
        for iid in self.plan_tree.get_children():
            self._set_plan_row(iid, on)
        if self.plan:
            self._update_plan_info()

    def _reveal_plan(self):
        iid = self.plan_tree.focus()
        if iid:
            m = self.plan[int(iid)]["move"]
            reveal(m.src if m.src.exists() else m.dst)

    def do_apply(self):
        if not self._guard_watch():
            return
        chosen = [it for it in self.plan if it["on"]]
        if not chosen:
            return
        n_dir = sum(it["dir"] for it in chosen)
        folders = T("dlg_apply_folders", n=n_dir) if n_dir else ""
        r = Dialog(self, T("dlg_apply_title", n=f"{len(chosen):,}"), T("dlg_apply_msg", folders=folders),
                   [("ok", T("btn_organize"), True), (None, T("btn_cancel"), False)]).result
        if r != "ok":
            return
        root, moves = self.plan_root, [it["move"] for it in chosen]
        self.run_bg(T("task_move"),
                    lambda: org.execute(root, moves, "apply", self._progress_cb, cancel=self.cancel_event),
                    lambda res: self._after_execute(res, root))

    def _after_execute(self, res, root):
        ok, failed = res
        try:
            org.prune_journals(root, self.journal_days)
        except OSError:
            org.log.warning("prune journals failed", exc_info=True)
        if self.cancel_event.is_set():
            self.infobar.show("info", T("ib_cancelled_title"), T("ib_cancelled_move", n=f"{ok:,}"), timeout=8000)
        elif failed:
            detail = [f"{org.rel(root, p)} — {err}" for p, err in failed[:50]]
            self.infobar.show("warning", T("ib_failed_title"), T("ib_failed_msg", ok=f"{ok:,}", n=len(failed)),
                              action=(T("btn_details"), lambda: Dialog(self, T("ib_failed_title"), "",
                                                                        [("ok", T("btn_close"), True)], detail)))
        else:
            self.infobar.show("success", T("ib_moved_title"), T("ib_moved", n=f"{ok:,}"), timeout=6000)
        self.plan, self._plan_previewed = [], False
        self.scan_result, self.dup_groups, self.dup_root = None, [], None
        self._render_plan()
        self._render_overview()
        self._render_dupes()
        self.refresh_history()

