"""Rules → form aturan file/folder (edit, validasi langsung, uji ke folder target)."""
import copy
import re
from datetime import datetime

import tkinter as tk
from tkinter import ttk

from gui.common import (org, T, sv_ttk, UserError)
from gui.widgets import (EmptyState, make_tree)


class RuleEditor:
    def _rule_form(self, kind, idx):
        inner = self.rule_form_host.inner
        for w in inner.winfo_children():
            w.destroy()
        if idx is None:
            es = EmptyState(inner, self, "rules")
            es.configure(height=360)
            es.pack(fill="x", expand=True)
            if self.doc[kind]:
                es.set(T("select_rule"), "")
            else:
                es.set(T("empty_rules_title"), T("empty_rules_desc"), ("+ " + T("btn_add"), lambda: self._rule_add(kind)))
            return
        r = self.doc[kind][idx]
        card = ttk.Frame(inner, style="Card.TFrame", padding=18)
        card.pack(fill="x")
        card.columnconfigure(0, weight=1)
        self._form_loading = True
        v = {}

        def label(text, hint=None):
            ttk.Label(card, text=text, style="H2.TLabel").pack(anchor="w", pady=(12, 4))
            if hint:
                ttk.Label(card, text=hint, style="Caption.TLabel", wraplength=380, justify="left").pack(
                    anchor="w", pady=(0, 4))

        def entry(key, value, parent=None, width=None, **pack):
            var = tk.StringVar(value="" if value is None else str(value))
            e = ttk.Entry(parent or card, textvariable=var, width=width) if width else ttk.Entry(parent or card,
                                                                                                textvariable=var)
            e.pack(**(pack or dict(fill="x")))
            v[key] = var
            return e

        top = ttk.Frame(card)
        top.pack(fill="x")
        ttk.Label(top, text=T("f_name"), style="H2.TLabel").pack(side="left", pady=(0, 4))
        v["enabled"] = tk.BooleanVar(value=r.get("enabled") is not False)
        ttk.Checkbutton(top, text=T("f_enabled"), variable=v["enabled"],
                        style="Switch.TCheckbutton" if sv_ttk else "TCheckbutton").pack(side="right")
        entry("name", r.get("name", ""))
        if kind == "rules":
            library = self._library()
            label(T("f_category"), T("f_category_hint"))
            row = ttk.Frame(card)
            row.pack(fill="x")
            cat_entry = entry("category", ", ".join(org.category_names(r.get("category"))), row,
                              side="left", fill="x", expand=True)
            names = sorted(library)
            picker = ttk.Combobox(row, state="readonly", width=24,
                                  values=[f"{n} · {library[n].get(T.lang) or library[n]['en']}" for n in names])
            picker.set(T("f_add_category"))
            picker.pack(side="left", padx=(6, 0))

            def add_category(_=None):
                name = picker.get().split(" · ")[0]
                cur = [c.strip() for c in re.split(r"[,\s]+", v["category"].get()) if c.strip()]
                if name in library and name not in cur:
                    v["category"].set(", ".join(cur + [name]))
                picker.set(T("f_add_category"))
                cat_entry.focus_set()

            picker.bind("<<ComboboxSelected>>", add_category)
            self.err_category = ttk.Label(card, text="", style="Error.TLabel")
            self.err_category.pack(anchor="w")
            self.cat_preview = ttk.Label(card, text="", style="Caption.TLabel", wraplength=380, justify="left")
            self.cat_preview.pack(anchor="w")
            label(T("f_ext"), T("f_ext_hint"))
            entry("ext", ", ".join(str(x) for x in (r.get("ext") or [])))
        label(T("f_regex"), T("f_regex_hint"))
        entry("name_regex", r.get("name_regex", ""))
        self.err_regex = ttk.Label(card, text="", style="Error.TLabel")
        self.err_regex.pack(anchor="w")

        label(T("f_age"))
        grid = ttk.Frame(card)
        grid.pack(fill="x")
        for i, (key, text) in enumerate((("older_than_days", T("f_older")), ("newer_than_days", T("f_newer")))):
            ttk.Label(grid, text=text).grid(row=i, column=0, sticky="w", pady=2)
            var = tk.StringVar(value="" if r.get(key) is None else str(r.get(key)))
            ttk.Entry(grid, textvariable=var, width=7).grid(row=i, column=1, padx=8, pady=2)
            ttk.Label(grid, text=T("f_days")).grid(row=i, column=2, sticky="w")
            v[key] = var
        if kind == "rules":
            label(T("f_size"))
            row = ttk.Frame(card)
            row.pack(fill="x")
            ttk.Label(row, text=T("f_min")).pack(side="left")
            entry("min_size_mb", r.get("min_size_mb"), row, 7, side="left", padx=6)
            ttk.Label(row, text=T("f_mb")).pack(side="left", padx=(0, 18))
            ttk.Label(row, text=T("f_max")).pack(side="left")
            entry("max_size_mb", r.get("max_size_mb"), row, 7, side="left", padx=6)
            ttk.Label(row, text=T("f_mb")).pack(side="left")
        self.err_num = ttk.Label(card, text="", style="Error.TLabel")
        self.err_num.pack(anchor="w")

        label(T("f_dest"), T("f_dest_hint"))
        dest_entry = entry("dest", r.get("dest", ""))
        tokens = ttk.Frame(card)
        tokens.pack(fill="x", pady=(6, 0))
        for tok in ("{period}", "{year}", "{month}", "{day}") + (("{ext}", "{EXT}") if kind == "rules" else ()):
            ttk.Button(tokens, text=tok, style="Token.TButton",
                       command=lambda t=tok: (dest_entry.insert("insert", t), dest_entry.focus_set())
                       ).pack(side="left", padx=(0, 4))
        self.dest_preview = ttk.Label(card, text="", style="Caption.TLabel")
        self.dest_preview.pack(anchor="w", pady=(6, 0))
        self.err_dest = ttk.Label(card, text="", style="Error.TLabel")
        self.err_dest.pack(anchor="w")

        test = ttk.Frame(inner, style="Card.TFrame", padding=18)
        test.pack(fill="x", pady=(12, 0))
        top = ttk.Frame(test)
        top.pack(fill="x")
        ttk.Label(top, text=T("sec_test"), style="H2.TLabel").pack(side="left")
        ttk.Button(top, text=T("btn_test"), command=lambda: self._rule_test(kind, idx)).pack(side="right")
        self.test_result = ttk.Label(test, text="", style="Muted.TLabel", wraplength=400, justify="left")
        self.test_result.pack(anchor="w", pady=(8, 0))
        fr, self.test_tree = make_tree(test, ("from", "to"), (T("col_from"), T("col_to")), (180, 220), height=5)
        self.test_frame = fr

        self.form_vars = v
        for key, var in v.items():
            var.trace_add("write", lambda *a, k=kind, i=idx: self._rule_form_changed(k, i))
        self._form_loading = False
        self._validate_form(kind, r)

    def _rule_form_changed(self, kind, idx):
        if getattr(self, "_form_loading", False):
            return
        r = self.doc[kind][idx]
        v = self.form_vars
        r["name"] = v["name"].get()
        if v["enabled"].get():
            r.pop("enabled", None)
        else:
            r["enabled"] = False
        if "category" in v:
            cats = [c.strip() for c in re.split(r"[,\s]+", v["category"].get()) if c.strip()]
            if len(cats) == 1:
                r["category"] = cats[0]
            elif cats:
                r["category"] = cats
            else:
                r.pop("category", None)
        if "ext" in v:
            exts = [e.strip().lstrip(".").lower() for e in re.split(r"[,\s]+", v["ext"].get()) if e.strip(" .")]
            if exts:
                r["ext"] = exts
            else:
                r.pop("ext", None)
        rx = v["name_regex"].get().strip()
        if rx:
            r["name_regex"] = rx
        else:
            r.pop("name_regex", None)
        for key in ("older_than_days", "newer_than_days", "min_size_mb", "max_size_mb"):
            if key not in v:
                continue
            raw = v[key].get().strip().replace(",", ".")
            if not raw:
                r.pop(key, None)
                continue
            try:
                num = float(raw)
                r[key] = int(num) if num.is_integer() else num
            except ValueError:
                r[key] = raw  # disimpan apa adanya, ditandai error
        r["dest"] = v["dest"].get().strip()
        self._mark_dirty()
        self._validate_form(kind, r)
        try:
            self.rules_tree.item(str(idx), values=(idx + 1, r.get("name", ""), self._rule_summary(r, kind)))
        except tk.TclError:
            pass

    def _validate_form(self, kind, r):
        if kind == "rules" and hasattr(self, "err_category"):
            self._validate_categories(r)
        err = ""
        if r.get("name_regex"):
            try:
                re.compile(r["name_regex"])
            except re.error as e:
                err = T("f_regex_invalid", err=e)
        self.err_regex.configure(text=err)
        bad = [k for k in ("older_than_days", "newer_than_days", "min_size_mb", "max_size_mb")
               if k in r and not isinstance(r[k], (int, float))]
        self.err_num.configure(text=T("f_number_invalid") if bad else "")
        self._validate_dest(kind, r)

    def _validate_categories(self, r):
        library = self._library()
        cats = org.category_names(r.get("category"))
        unknown = [c for c in cats if c not in library]
        self.err_category.configure(text=T("f_category_unknown", names=", ".join(unknown)) if unknown else "")
        exts = sorted({e for c in cats if c in library for e in library[c]["ext"]})
        self.cat_preview.configure(
            text=T("f_category_preview", n=len(exts), list=" ".join(f".{e}" for e in exts[:24])
                   + (" …" if len(exts) > 24 else "")) if exts else "")

    def _validate_dest(self, kind, r):
        dest = r.get("dest", "")
        problem = org.dest_error(dest, is_folder=(kind == "folder_rules"))
        if problem:
            self.err_dest.configure(text=T("f_dest_required") if not str(dest).strip() else f"{T('f_dest')}: {problem}")
            self.dest_preview.configure(text="")
            return
        self.err_dest.configure(text="")
        now = datetime.now()
        sample = "example.pdf" if kind == "rules" else "ExampleFolder"
        fmt = self.doc.get("date_format") or org.DEFAULT_DATE_FORMAT
        period = org.render_period(now, fmt) if not org.date_format_error(fmt) else "?"
        rendered = dest.format(year=now.year, month=f"{now.month:02d}", day=f"{now.day:02d}", period=period,
                               ext="pdf", EXT="PDF")
        self.dest_preview.configure(text=T("f_preview", path=f"{rendered.rstrip('/')}/{sample}"))

    def _rule_test(self, kind, idx):
        try:
            root = self._target()
            cfg = org.prepare_config(copy.deepcopy(self.doc))
        except UserError as e:
            self.infobar.show("warning", str(e), timeout=5000)
            return
        except SystemExit as e:
            self.infobar.show("error", T("dlg_invalid_title"), str(e.code))
            return

        def job():
            import time as _t
            now = _t.time()
            rules = cfg[kind]
            if kind == "rules":
                items = list(org.iter_files(root, cfg["recursive"], cfg["exclude"], cancel=self.cancel_event,
                                            progress=self.files_progress()))
            else:
                items = list(org.iter_top_folders(root, cfg, cancel=self.cancel_event))
            used, shadowed, examples = 0, 0, []
            for p, st in items:
                first = next((i for i, rr in enumerate(rules) if org.rule_matches(rr, p, st, now)), None)
                if first == idx:
                    used += 1
                    if len(examples) < 50:
                        dest = org.render_dest(rules[idx]["dest"], p, st, kind == "folder_rules", cfg["date_format"])
                        examples.append((org.rel(root, p), f"{dest}/{p.name}"))
                elif first is not None and first < idx and org.rule_matches(rules[idx], p, st, now):
                    shadowed += 1
            return used, shadowed, examples

        def done(res):
            used, shadowed, examples = res
            if not used and not shadowed:
                self.test_result.configure(text=T("test_none"))
                self.test_frame.pack_forget()
                return
            txt = T("test_result", n=used) + (T("test_shadowed", m=shadowed) if shadowed else "")
            self.test_result.configure(text=txt)
            self.test_tree.delete(*self.test_tree.get_children())
            for a, b in examples:
                self.test_tree.insert("", "end", values=(a, b))
            if examples:
                self.test_frame.pack(fill="x", pady=(8, 0))

        self.run_bg(T("task_test"), job, done)
