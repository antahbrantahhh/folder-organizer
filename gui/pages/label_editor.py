"""Rules → Labels: deskripsi folder (folder_info), per bahasa app."""
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, ttk

from gui.common import (org, T, sv_ttk, UserError)
from gui.widgets import (EmptyState, Dialog, make_tree)


class LabelEditor:
    # — labels (folder_info) —
    def _labels_section(self):
        body = self.rules_body
        body.columnconfigure(0, weight=5, uniform="r")
        body.columnconfigure(1, weight=4, uniform="r")
        body.rowconfigure(1, weight=1)
        bar = ttk.Frame(body)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(bar, text="+ " + T("btn_add"), command=self._label_add,
                   style="Accent.TButton" if sv_ttk else "TButton").pack(side="left")
        ttk.Button(bar, text=T("btn_delete"), command=self._label_del).pack(side="left", padx=6)
        fr, tree = make_tree(body, ("path", "desc"), (T("col_folder"), T("col_desc")), (200, 320), stretch=("desc",))
        tree.configure(selectmode="browse")
        fr.grid(row=1, column=0, sticky="nsew")
        self.lbl_tree = tree
        tree.bind("<<TreeviewSelect>>", lambda e: self._label_selected())
        self.lbl_form = ttk.Frame(body)
        self.lbl_form.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(16, 0))
        self._render_label_list()

    def _label_items(self):
        return list(self.doc["folder_info"].items())

    def _render_label_list(self, select=None):
        t = self.lbl_tree
        t.delete(*t.get_children())
        items = self._label_items()
        for i, (path, val) in enumerate(items):
            t.insert("", "end", iid=str(i), values=(path, " ".join(org.label_text(val).split())))
        sel = select if select is not None else self.sel_label
        if sel is not None and 0 <= sel < len(items):
            t.selection_set(str(sel))
            t.see(str(sel))
        else:
            self.sel_label = None
            self._label_form(None)

    def _label_selected(self):
        sel = self.lbl_tree.selection()
        self.sel_label = int(sel[0]) if sel else None
        self._label_form(self.sel_label)

    def _set_label_items(self, items):
        self.doc["folder_info"] = {p: d for p, d in items}

    def _label_add(self):
        items = self._label_items()
        base, n = T("new_label_path"), 1
        name = base
        while name in self.doc["folder_info"]:
            n += 1
            name = f"{base}{n}"
        items.append((name, ""))
        self._set_label_items(items)
        self._mark_dirty()
        self._render_label_list(select=len(items) - 1)

    def _label_del(self):
        i = self.sel_label
        if i is None:
            return
        items = self._label_items()
        if Dialog(self, T("dlg_delete_rule", name=items[i][0]), T("dlg_delete_msg"),
                  [("ok", T("btn_delete"), True), (None, T("btn_cancel"), False)]).result != "ok":
            return
        del items[i]
        self._set_label_items(items)
        self._mark_dirty()
        self._render_label_list(select=min(i, len(items) - 1) if items else None)

    def _label_form(self, idx):
        for w in self.lbl_form.winfo_children():
            w.destroy()
        if idx is None:
            es = EmptyState(self.lbl_form, self, "labels")
            es.pack(fill="both", expand=True)
            if self.doc["folder_info"]:
                es.set(T("select_rule"), "")
            else:
                es.set(T("empty_labels_title"), "", ("+ " + T("btn_add"), self._label_add))
            return
        path, val = self._label_items()[idx]
        desc = org.label_text(val)
        card = ttk.Frame(self.lbl_form, style="Card.TFrame", padding=18)
        card.pack(fill="x")
        ttk.Label(card, text=T("lbl_path"), style="H2.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Label(card, text=T("lbl_path_hint"), style="Caption.TLabel").pack(anchor="w", pady=(0, 4))
        row = ttk.Frame(card)
        row.pack(fill="x")
        pv = tk.StringVar(value=path)
        ttk.Entry(row, textvariable=pv).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text=T("btn_browse"), command=lambda: self._label_browse(pv)).pack(side="left", padx=(6, 0))
        self.lbl_err = ttk.Label(card, text="", style="Error.TLabel")
        self.lbl_err.pack(anchor="w")
        ttk.Label(card, text=T("col_desc"), style="H2.TLabel").pack(anchor="w", pady=(12, 4))
        ttk.Label(card, text=T("lbl_desc_lang", lang=T("lang_name")), style="Caption.TLabel",
                  wraplength=380, justify="left").pack(anchor="w", pady=(0, 4))
        txt = tk.Text(card, height=6, wrap="word", font=(self.fonts.text, 10), relief="flat",
                      bg=self.pal["code_bg"], fg=self.pal["text"], insertbackground=self.pal["text"],
                      highlightthickness=1, highlightbackground=self.pal["border"],
                      highlightcolor=self.pal["accent"], padx=8, pady=6)
        txt.insert("1.0", str(desc))
        txt.pack(fill="x")

        def commit(*_):
            items = self._label_items()
            new_path = pv.get().strip().replace("\\", "/").strip("/")
            new_desc = txt.get("1.0", "end").strip()
            new_val = self._label_value(items[idx][1], new_desc)
            items[idx] = (new_path, new_val)
            self._set_label_items(items)
            self._mark_dirty()
            try:
                self.lbl_tree.item(str(idx), values=(new_path, " ".join(new_desc.split())))
            except tk.TclError:
                pass

        pv.trace_add("write", commit)
        txt.bind("<KeyRelease>", commit)

    @staticmethod
    def _label_value(old, text):
        """Teks biasa tetap teks biasa; versi dwibahasa {en, id} hanya bahasa aktif yang diganti."""
        if isinstance(old, dict) and (old.keys() & {"en", "id"}):
            return {**old, T.lang: text}
        if isinstance(old, dict):
            return {**old, "desc": text}
        return text

    def _label_browse(self, var):
        try:
            root = self._target()
        except UserError as e:
            self.infobar.show("warning", str(e), timeout=5000)
            return
        d = filedialog.askdirectory(initialdir=str(root), title=T("lbl_path"))
        if not d:
            return
        try:
            var.set(Path(d).resolve().relative_to(root).as_posix())
        except ValueError:
            self.infobar.show("warning", T("path_outside"), timeout=5000)
