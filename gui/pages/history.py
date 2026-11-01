"""Halaman History."""
from pathlib import Path

from tkinter import ttk

from gui.common import (org, T, UserError, fmt_date)
from gui.widgets import (EmptyState, Dialog, make_tree)


class HistoryPage:
    # ───────────────────────── page: History ─────────────────────────

    def _page_history(self, f):
        self._page_header(f, "history")
        bar = ttk.Frame(f)
        bar.pack(fill="x")
        self.btn_undo = self._btn(bar, T("btn_undo_last"), self.do_undo, accent=True)
        self.btn_undo.pack(side="left")
        ttk.Button(bar, text=T("btn_refresh"), command=self.refresh_history).pack(side="left", padx=8)

        body = ttk.Frame(f)
        body.pack(fill="both", expand=True, pady=(12, 0))
        self.hist_empty = EmptyState(body, self, "history")
        self.hist_pane = ttk.PanedWindow(body, orient="vertical")
        fr, self.hist_tree = make_tree(self.hist_pane, ("time", "kind", "count", "status"),
                                       (T("col_time"), T("col_kind"), T("col_items"), T("col_status")),
                                       (200, 140, 110, 180), stretch=("time",))
        self.hist_tree.tag_configure("muted", foreground=self.pal["muted"])
        self.hist_pane.add(fr, weight=2)
        self.hist_tree.bind("<<TreeviewSelect>>", lambda e: self._show_journal())
        det = ttk.Frame(self.hist_pane)
        ttk.Label(det, text=T("hist_detail"), style="H2.TLabel").pack(anchor="w", pady=(12, 6))
        fr, self.hist_detail = make_tree(det, ("src", "dst"), (T("col_from"), T("col_to")), (450, 450))
        fr.pack(fill="both", expand=True)
        self.hist_pane.add(det, weight=3)
        self.refresh_history()

    def _on_show_history(self):
        self.refresh_history()

    def refresh_history(self):
        try:
            t = self.hist_tree
        except AttributeError:
            return
        t.delete(*t.get_children())
        self.hist_detail.delete(*self.hist_detail.get_children())
        try:
            root = self._target()
            self.journals = org.list_journals(root)
        except UserError:
            self.journals = []
        if not self.journals:
            self.hist_pane.pack_forget()
            self.hist_empty.pack(fill="both", expand=True)
            self.hist_empty.set(T("empty_history_title"), T("empty_history_desc"))
            self.btn_undo.state(["disabled"])
            return
        self.hist_empty.pack_forget()
        self.hist_pane.pack(fill="both", expand=True)
        last_active = next((j for j in reversed(self.journals) if j.suffix == ".jsonl"), None)
        for j in reversed(self.journals):
            parts = j.stem.split("_")
            ts = org.journal_time(j)
            when = fmt_date(ts, seconds=True) if ts else j.stem
            try:
                count = f"{len(org.read_journal(j)):,}"
            except Exception:
                count = "?"
            status = T("hist_undone") if j.suffix == ".undone" else (
                T("hist_active_last") if j == last_active else T("hist_active"))
            t.insert("", "end", iid=str(j), tags=("muted",) if j.suffix == ".undone" else (),
                     values=(when, T(f"kind_{parts[-1]}") if parts[-1] in ("apply", "dedupe", "watch") else parts[-1],
                             count, status))
        if not self.busy:
            self.btn_undo.state(["!disabled"] if last_active else ["disabled"])

    def _show_journal(self):
        sel = self.hist_tree.selection()
        d = self.hist_detail
        d.delete(*d.get_children())
        if not sel:
            return
        try:
            root = self._target()
            for e in org.read_journal(Path(sel[0]))[:3000]:
                d.insert("", "end", values=(org.rel(root, Path(e["src"])), org.rel(root, Path(e["dst"]))))
        except Exception:
            pass

    def do_undo(self):
        if not self._guard_watch():
            return
        last = next((j for j in reversed(self.journals) if j.suffix == ".jsonl"), None)
        if not last:
            return
        n = len(org.read_journal(last))
        r = Dialog(self, T("dlg_undo_title"), T("dlg_undo_msg", n=f"{n:,}"),
                   [("ok", T("btn_undo"), True), (None, T("btn_cancel"), False)]).result
        if r != "ok":
            return
        root = self._target()

        def done(res):
            restored, skipped, failed = res
            msg = T("ib_undo", n=f"{restored:,}") + ((" " + T("ib_undo_skipped", n=skipped)) if skipped else "")
            if failed:
                msg += " " + T("ib_undo_failed", n=failed)
            self.infobar.show("warning" if (skipped or failed) else "success", T("ib_moved_title"), msg,
                              timeout=None if failed else 8000)
            self.plan, self._plan_previewed, self.scan_result = [], False, None
            self.dup_groups, self.dup_root = [], None
            self._render_dupes()
            self._render_plan()
            self._render_overview()
            self.refresh_history()

        self.run_bg(T("task_undo"), lambda: org.undo_journal(root, last), done, cancellable=False)

