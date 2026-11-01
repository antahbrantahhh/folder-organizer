"""Halaman Rules (editor)."""
import copy

import tkinter as tk
from tkinter import ttk

from gui.common import (org, T, sv_ttk, RULES_PATH)
import rules_io
from gui.widgets import (ScrollFrame, Dialog, make_tree)


class RulesPage:
    # ───────────────────────── page: Rules (editor) ─────────────────────────

    def _load_doc(self):
        """rules.yaml → dict untuk diedit + dokumen round-trip (supaya komentar tetap ada saat disimpan)."""
        try:
            self.rules_doc = rules_io.RulesDocument.load(RULES_PATH)
            self.doc = self.rules_doc.plain()
            self.doc_error = None
        except Exception as e:
            self.rules_doc = rules_io.RulesDocument("")
            self.doc, self.doc_error = {}, str(e)
        for k in ("rules", "folder_rules"):
            if not isinstance(self.doc.get(k), list):
                self.doc[k] = []
        if not isinstance(self.doc.get("folder_info"), dict):
            self.doc["folder_info"] = {}
        self.dirty = False

    def open_rules(self, section):
        self.rules_section = section
        self.show_page("rules")

    def _page_rules(self, f):
        self._page_header(f, "rules")
        seg = ttk.Frame(f)
        seg.pack(fill="x")
        self.seg_btns = {}
        for key in ("files", "folders", "categories", "labels", "general", "yaml"):
            b = ttk.Button(seg, text=T(f"seg_{key}"), command=lambda k=key: self._rules_section(k))
            b.pack(side="left", padx=(0, 6))
            self.seg_btns[key] = b
        self.rules_body = ttk.Frame(f)
        self.rules_body.pack(fill="both", expand=True, pady=(14, 0))
        foot = ttk.Frame(f)
        foot.pack(fill="x", pady=(12, 0))
        self.rules_state = ttk.Label(foot, text="", style="Muted.TLabel")
        self.rules_state.pack(side="left")
        self.btn_save = ttk.Button(foot, text=T("btn_save"), command=self.save_rules,
                                   style="Accent.TButton" if sv_ttk else "TButton")
        self.btn_save.pack(side="right")
        self.btn_revert = ttk.Button(foot, text=T("btn_revert"), command=self.revert_rules)
        self.btn_revert.pack(side="right", padx=8)
        self._rules_section(self.rules_section)

    def _on_show_rules(self):
        self._rules_section(self.rules_section)
        if self.doc_error:
            self.infobar.show("error", T("err_title"), T("rules_load_error", err=self.doc_error))

    def _sync_rules_footer(self):
        self.rules_state.configure(text=("●  " + T("rules_dirty")) if self.dirty else T("rules_clean"),
                                   foreground=self.pal["warning"][1] if self.dirty else self.pal["muted"])
        self.btn_save.state(["!disabled"] if self.dirty else ["disabled"])
        self.btn_revert.state(["!disabled"] if self.dirty else ["disabled"])

    def _mark_dirty(self):
        if not self.dirty:
            self.dirty = True
        self._sync_rules_footer()

    def _rules_section(self, key):
        self.rules_section = key
        for k, b in self.seg_btns.items():
            b.configure(style="Accent.TButton" if (k == key and sv_ttk) else "TButton")
        for w in self.rules_body.winfo_children():
            w.destroy()
        if key in ("files", "folders"):
            self._rules_list_section("rules" if key == "files" else "folder_rules")
        elif key == "categories":
            self._categories_section()
        elif key == "labels":
            self._labels_section()
        elif key == "general":
            self._general_section()
        else:
            self._yaml_section()
        self._sync_rules_footer()

    # — list + form (file rules / folder rules) —
    @staticmethod
    def _rule_summary(r, kind):
        parts = []
        cats = org.category_names(r.get("category")) if kind == "rules" else []
        if cats:
            parts.append(" ".join(f"@{c}" for c in cats[:4]) + (" …" if len(cats) > 4 else ""))
        if kind == "rules" and r.get("ext"):
            parts.append(" ".join(f".{e}" for e in r["ext"][:5]) + (" …" if len(r["ext"]) > 5 else ""))
        if r.get("name_regex"):
            parts.append(f"/{r['name_regex']}/")
        if r.get("older_than_days") is not None:
            parts.append(T("sum_older", n=r["older_than_days"]))
        if r.get("newer_than_days") is not None:
            parts.append(T("sum_newer", n=r["newer_than_days"]))
        if not parts:
            parts.append(T("sum_any"))
        off = (T("sum_off") + "  ") if r.get("enabled") is False else ""
        return off + "  ·  ".join(parts) + f"   →  {r.get('dest', '')}"

    def _rules_list_section(self, kind):
        body = self.rules_body
        body.columnconfigure(0, weight=5, uniform="r")
        body.columnconfigure(1, weight=4, uniform="r")
        body.rowconfigure(1, weight=1)
        bar = ttk.Frame(body)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(bar, text="+ " + T("btn_add"), command=lambda: self._rule_add(kind),
                   style="Accent.TButton" if sv_ttk else "TButton").pack(side="left")
        ttk.Button(bar, text=T("btn_duplicate"), command=lambda: self._rule_dup(kind)).pack(side="left", padx=6)
        ttk.Button(bar, text=T("btn_delete"), command=lambda: self._rule_del(kind)).pack(side="left")
        ttk.Button(bar, text="▼", width=3, command=lambda: self._rule_move(kind, 1)).pack(side="right")
        ttk.Button(bar, text="▲", width=3, command=lambda: self._rule_move(kind, -1)).pack(side="right", padx=6)
        fr, tree = make_tree(body, ("n", "name", "summary"), ("#", T("col_name"), T("col_summary")),
                             (40, 170, 300), stretch=("summary",))
        tree.configure(selectmode="browse")
        fr.grid(row=1, column=0, sticky="nsew")
        self.rules_tree = tree
        tree.bind("<<TreeviewSelect>>", lambda e: self._rule_selected(kind))

        self.rule_form_host = ScrollFrame(body, self.pal["bg"])
        self.rule_form_host.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(16, 0))
        self._render_rule_list(kind)

    def _render_rule_list(self, kind, select=None):
        t = self.rules_tree
        t.delete(*t.get_children())
        for i, r in enumerate(self.doc[kind]):
            t.insert("", "end", iid=str(i), values=(i + 1, r.get("name", ""), self._rule_summary(r, kind)))
        sel = select if select is not None else self.sel_rule.get(kind)
        if sel is not None and 0 <= sel < len(self.doc[kind]):
            t.selection_set(str(sel))
            t.see(str(sel))
        else:
            self.sel_rule[kind] = None
            self._rule_form(kind, None)

    def _library(self):
        try:
            return org.build_category_library(self.doc.get("categories"))
        except SystemExit:
            return org.build_category_library(None)

    def _categories_section(self):
        body = self.rules_body
        ttk.Label(body, text=T("categories_hint"), style="Muted.TLabel", wraplength=1000, justify="left").pack(
            anchor="w", pady=(0, 10))
        fr, tree = make_tree(body, ("name", "label", "group", "count", "ext"),
                             (T("col_name"), T("col_label"), T("col_group"), T("col_ext_count"), T("col_extensions")),
                             (150, 210, 110, 60, 520), stretch=("ext",))
        fr.pack(fill="both", expand=True)
        tree.tag_configure("custom", foreground=self.pal["accent"])
        library = self._library()
        order = ["documents", "media", "design", "archive", "software", "dev", "engineering", "security", "system"]
        for name in sorted(library, key=lambda n: (order.index(library[n]["group"]) if library[n]["group"] in order
                                                   else len(order), n)):
            c = library[name]
            label = (c.get(T.lang) or c["en"]) + (f"  ({T('cat_custom')})" if c.get("custom") else "")
            exts = " ".join([f".{e}" for e in c["ext"]] + c.get("names", []))
            tree.insert("", "end", values=(name, label, c["group"], len(c["ext"]), exts),
                        tags=("custom",) if c.get("custom") else ())

    def _rule_selected(self, kind):
        sel = self.rules_tree.selection()
        idx = int(sel[0]) if sel else None
        self.sel_rule[kind] = idx
        self._rule_form(kind, idx)

    def _rule_add(self, kind):
        dest = "_Inbox/_Review" if kind == "rules" else "_Inbox/_Review/Folders"
        r = {"name": T("new_rule"), "dest": dest}
        if kind == "rules":
            r["ext"] = []
        self.doc[kind].append(r)
        self._mark_dirty()
        self._render_rule_list(kind, select=len(self.doc[kind]) - 1)

    def _rule_dup(self, kind):
        i = self.sel_rule.get(kind)
        if i is None:
            return
        r = copy.deepcopy(self.doc[kind][i])
        r["name"] = f"{r.get('name', '')} (2)"
        self.doc[kind].insert(i + 1, r)
        self._mark_dirty()
        self._render_rule_list(kind, select=i + 1)

    def _rule_del(self, kind):
        i = self.sel_rule.get(kind)
        if i is None:
            return
        name = self.doc[kind][i].get("name", "")
        if Dialog(self, T("dlg_delete_rule", name=name), T("dlg_delete_msg"),
                  [("ok", T("btn_delete"), True), (None, T("btn_cancel"), False)]).result != "ok":
            return
        del self.doc[kind][i]
        self._mark_dirty()
        self._render_rule_list(kind, select=min(i, len(self.doc[kind]) - 1) if self.doc[kind] else None)

    def _rule_move(self, kind, d):
        i = self.sel_rule.get(kind)
        lst = self.doc[kind]
        if i is None or not (0 <= i + d < len(lst)):
            return
        lst[i], lst[i + d] = lst[i + d], lst[i]
        self._mark_dirty()
        self._render_rule_list(kind, select=i + d)

    # — general —
    def _general_section(self):
        sf = ScrollFrame(self.rules_body, self.pal["bg"])
        sf.pack(fill="both", expand=True)
        card = ttk.Frame(sf.inner, style="Card.TFrame", padding=20)
        card.pack(fill="x")
        d = self.doc

        def switch(text, key, hint):
            var = tk.BooleanVar(value=bool(d.get(key, False if key == "recursive" else True)))
            ttk.Checkbutton(card, text=text, variable=var,
                            style="Switch.TCheckbutton" if sv_ttk else "TCheckbutton",
                            command=lambda: (d.__setitem__(key, var.get()), self._mark_dirty())).pack(anchor="w")
            if hint:
                ttk.Label(card, text=hint, style="Caption.TLabel").pack(anchor="w", pady=(2, 14))

        def text_field(text, key, hint):
            ttk.Label(card, text=text, style="H2.TLabel").pack(anchor="w", pady=(4, 2))
            ttk.Label(card, text=hint, style="Caption.TLabel").pack(anchor="w", pady=(0, 4))
            var = tk.StringVar(value=d.get(key) or "")

            def upd(*_):
                d[key] = var.get().strip() or None
                self._mark_dirty()

            var.trace_add("write", upd)
            ttk.Entry(card, textvariable=var).pack(fill="x", pady=(0, 14))

        switch(T("g_recursive"), "recursive", T("g_recursive_hint"))
        text_field(T("g_fallback"), "fallback_dest", T("g_fallback_hint"))
        text_field(T("g_folder_fallback"), "folder_fallback", T("g_folder_fallback_hint"))

        # format folder tanggal ({period})
        ttk.Label(card, text=T("g_date_format"), style="H2.TLabel").pack(anchor="w", pady=(4, 2))
        ttk.Label(card, text=T("g_date_format_hint"), style="Caption.TLabel", wraplength=900,
                  justify="left").pack(anchor="w", pady=(0, 4))
        labels = dict(zip(org.DATE_FORMAT_PRESETS, (T("df_year"), T("df_year_month"), T("df_nested"),
                                                     T("df_nested_full"), T("df_day"))))
        cur = d.get("date_format") or org.DEFAULT_DATE_FORMAT
        values = [labels[k] for k in org.DATE_FORMAT_PRESETS] + ([cur] if cur not in labels else [])
        combo = ttk.Combobox(card, state="readonly", values=values, width=40)
        combo.set(labels.get(cur, cur))
        combo.pack(anchor="w", pady=(0, 14))

        def set_format(_=None):
            chosen = next((k for k, lbl in labels.items() if lbl == combo.get()), combo.get())
            if chosen != (d.get("date_format") or org.DEFAULT_DATE_FORMAT):
                d["date_format"] = chosen
                self._mark_dirty()

        combo.bind("<<ComboboxSelected>>", set_format)
        switch(T("g_readme"), "folder_info_readme", "")
        ttk.Label(card, text=T("g_exclude"), style="H2.TLabel").pack(anchor="w", pady=(14, 2))
        ttk.Label(card, text=T("g_exclude_hint"), style="Caption.TLabel").pack(anchor="w", pady=(0, 4))
        txt = tk.Text(card, height=6, font=(self.fonts.mono, 10), relief="flat", bg=self.pal["code_bg"],
                      fg=self.pal["text"], insertbackground=self.pal["text"], highlightthickness=1,
                      highlightbackground=self.pal["border"], highlightcolor=self.pal["accent"], padx=8, pady=6)
        txt.insert("1.0", "\n".join(d.get("exclude") or []))
        txt.pack(fill="x")

        def upd_ex(*_):
            d["exclude"] = [l.strip() for l in txt.get("1.0", "end").splitlines() if l.strip()]
            self._mark_dirty()

        txt.bind("<KeyRelease>", upd_ex)

    # — yaml —
    def _yaml_section(self):
        body = self.rules_body
        ttk.Label(body, text=T("yaml_hint"), style="Muted.TLabel").pack(anchor="w")
        bar = ttk.Frame(body)
        bar.pack(fill="x", pady=(8, 8))
        ttk.Button(bar, text=T("btn_yaml_apply"), command=self._yaml_apply,
                   style="Accent.TButton" if sv_ttk else "TButton").pack(side="left")
        ttk.Button(bar, text=T("btn_yaml_reload"), command=self._yaml_fill).pack(side="left", padx=8)
        wrap = ttk.Frame(body)
        wrap.pack(fill="both", expand=True)
        self.yaml_text = tk.Text(wrap, wrap="none", undo=True, font=(self.fonts.mono, 10), relief="flat",
                                 bg=self.pal["code_bg"], fg=self.pal["text"], insertbackground=self.pal["text"],
                                 highlightthickness=1, highlightbackground=self.pal["border"],
                                 highlightcolor=self.pal["accent"], padx=10, pady=8)
        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.yaml_text.yview)
        self.yaml_text.configure(yscrollcommand=vs.set)
        self.yaml_text.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        self._yaml_fill()

    def _dump_doc(self):
        return self.rules_doc.render(self.doc)

    def _yaml_fill(self):
        if self.doc_error and not self.dirty:
            try:
                raw = RULES_PATH.read_text(encoding="utf-8")
            except OSError:
                raw = ""
        else:
            raw = self._dump_doc()
        self.yaml_text.delete("1.0", "end")
        self.yaml_text.insert("1.0", raw)

    def _yaml_apply(self):
        raw = self.yaml_text.get("1.0", "end")
        try:
            # komentar yang diketik di tab YAML ikut tersimpan; hash file lama dibawa untuk deteksi konflik
            new_doc = rules_io.RulesDocument(raw, self.rules_doc.digest)
            doc = new_doc.plain()
            org.prepare_config(copy.deepcopy(doc))
        except SystemExit as e:
            self.infobar.show("error", T("yaml_invalid"), str(e.code))
            return
        except Exception as e:
            self.infobar.show("error", T("yaml_invalid"), str(e))
            return
        self.rules_doc, self.doc, self.doc_error = new_doc, doc, None
        for k in ("rules", "folder_rules"):
            self.doc.setdefault(k, [])
        self.doc.setdefault("folder_info", {})
        self.sel_rule = {"rules": None, "folder_rules": None}
        self._mark_dirty()
        self.infobar.show("success", T("ib_yaml_applied"), timeout=6000)

    # — save / revert —
    def save_rules(self) -> bool:
        try:
            org.prepare_config(copy.deepcopy(self.doc))
            for kind in ("rules", "folder_rules"):
                for r in self.doc[kind]:
                    if not str(r.get("dest", "")).strip():
                        raise SystemExit(f"'{r.get('name', '?')}': {T('f_dest_required')}")
                    for k in ("older_than_days", "newer_than_days", "min_size_mb", "max_size_mb"):
                        if k in r and not isinstance(r[k], (int, float)):
                            raise SystemExit(f"'{r.get('name', '?')}' · {k}: {T('f_number_invalid')}")
            for p in self.doc.get("folder_info") or {}:
                if not str(p).strip():
                    raise SystemExit(f"{T('seg_labels')}: {T('lbl_path')} ≠ ''")
        except SystemExit as e:
            Dialog(self, T("dlg_invalid_title"), str(e.code), [("ok", T("btn_ok"), True)])
            return False
        try:
            self.rules_doc = self.rules_doc.save(RULES_PATH, self.doc)  # komentar dipertahankan, backup ke .bak
        except rules_io.RulesConflict:
            return self._resolve_conflict()
        except OSError as e:
            self.infobar.show("error", T("err_title"), str(e))
            return False
        self.dirty, self.doc_error = False, None
        self._sync_rules_footer()
        self.infobar.show("success", T("ib_saved"), timeout=6000)
        self.refresh_labels()
        return True

    def _resolve_conflict(self) -> bool:
        """rules.yaml diubah di luar app sejak dibuka: tanya mau timpa, muat ulang, atau batal."""
        choice = Dialog(self, T("dlg_conflict_title"), T("dlg_conflict_msg", path=RULES_PATH),
                        [("overwrite", T("btn_overwrite"), True), ("reload", T("btn_reload"), False),
                         (None, T("btn_cancel"), False)]).result
        if choice == "reload":
            self.revert_rules()
            self.infobar.show("info", T("ib_reloaded"), timeout=6000)
            return False
        if choice != "overwrite":
            return False
        try:
            self.rules_doc = self.rules_doc.save(RULES_PATH, self.doc, force=True)
        except OSError as e:
            self.infobar.show("error", T("err_title"), str(e))
            return False
        self.dirty, self.doc_error = False, None
        self._sync_rules_footer()
        self.infobar.show("success", T("ib_saved"), timeout=6000)
        self.refresh_labels()
        return True

    def revert_rules(self):
        self._load_doc()
        self.sel_rule = {"rules": None, "folder_rules": None}
        self.sel_label = None
        self._rules_section(self.rules_section)

