"""Smoke test GUI end-to-end (scan → preview → apply → cancel → undo → label → keyboard).

Butuh display. Jalankan dengan:  set RUN_GUI_TESTS=1  lalu  python -m pytest -q tests/test_gui_smoke.py
(di Linux tanpa layar: xvfb-run). Dilewati secara default supaya `pytest` biasa tetap cepat.
"""
import os
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("RUN_GUI_TESTS") != "1", reason="set RUN_GUI_TESTS=1 untuk test GUI")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def tkroot():
    """Satu interpreter Tk untuk semua test: sv_ttk & cache ikon terikat ke interpreter pertama, dan membuat
    tk.Tk() berulang tidak stabil di runner Windows."""
    import tkinter as tk
    root = tk.Tk()
    yield root
    root.destroy()


@pytest.fixture
def app(tmp_path, monkeypatch, tkroot):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    import gui.app
    import gui.common
    monkeypatch.setattr(gui.common, "SETTINGS_PATH", tmp_path / "appdata" / "FolderOrganizer" / "settings.json")

    class AutoDialog:  # ganti dialog modal: selalu pilih tombol pertama
        def __init__(self, app, title, message, buttons, detail=None):
            self.result = buttons[0][0]

    for name, mod in list(sys.modules.items()):
        if name.startswith("gui.") and hasattr(mod, "Dialog"):
            monkeypatch.setattr(mod, "Dialog", AutoDialog)
    for w in tkroot.winfo_children():
        w.destroy()
    a = gui.app.App(tkroot)
    yield a
    a.teardown()  # timer/handler instance ini tidak boleh jalan di test berikutnya (root dipakai bersama)
    for w in tkroot.winfo_children():
        w.destroy()


def pump(a, secs=0.3):
    end = time.time() + secs
    while time.time() < end:
        a.root.update()
        time.sleep(0.02)


def wait(a, timeout=30):
    pump(a, 0.2)
    start = time.time()
    while a.busy and time.time() - start < timeout:
        pump(a, 0.05)
    pump(a, 0.2)


@pytest.fixture
def target(tmp_path):
    d = tmp_path / "target"
    (d / "Projects").mkdir(parents=True)
    for i in range(30):
        (d / f"report_{i}.pdf").write_text(str(i))
    for i in range(3):
        (d / f"photo_{i}.jpg").write_text("same")
    return d


def test_full_flow(app, target):
    import organizer as org
    app.folder = str(target)
    app._build_shell()
    for page in app.PAGES + app.FOOTER_PAGES:
        app.show_page(page)
        pump(app, 0.05)

    app.show_page("overview")
    app.do_scan()
    wait(app)
    assert len(app.scan_result["files"]) == 33

    app.show_page("organize")
    app.do_preview()
    wait(app)
    assert len(app.plan) == 33

    real_move = org.move_item
    org.move_item = lambda s, d: (time.sleep(0.03), real_move(s, d))[1]
    try:
        app.do_apply()
        pump(app, 0.3)
        app.cancel_task()
        wait(app)
    finally:
        org.move_item = real_move
    moved = sum(1 for p in target.rglob("*") if p.is_file()) - sum(1 for p in target.iterdir() if p.is_file())
    assert 0 < moved < 33  # dihentikan di tengah

    app.show_page("history")
    app.do_undo()
    wait(app)
    assert sum(1 for p in target.iterdir() if p.is_file()) == 33

    app.show_page("labels")
    app.do_labels()
    wait(app)
    assert "Projects" in org.find_managed_labels(target)


def test_keyboard_navigation(app, target):
    app.folder = str(target)
    app._build_shell()
    app.nav_items["overview"].focus_force()
    pump(app)
    app.nav_items["overview"].event_generate("<Down>")
    pump(app)
    app.root.focus_get().event_generate("<Return>")
    pump(app)
    assert app.page == "organize"
    app.root.event_generate("<Control-Key-3>")
    pump(app)
    assert app.page == "dupes"


def test_ui_callback_error_is_logged_and_shown(app, target):
    import organizer as org
    app.folder = str(target)
    app._build_shell()
    log_file = org.setup_logging()
    app.root.after(0, lambda: 1 / 0)
    pump(app, 0.3)
    for h in org.log.handlers:
        h.flush()
    assert app.infobar.winfo_ismapped()
    assert "ZeroDivisionError" in log_file.read_text(encoding="utf-8")


def test_large_plan_is_capped_debounced_and_select_all_covers_everything(app, tmp_path):
    big = tmp_path / "big"
    big.mkdir()
    for i in range(app.PLAN_ROW_LIMIT + 500):
        (big / f"doc_{i}.pdf").write_text("x")
    app.folder = str(big)
    app._build_shell()
    app.show_page("organize")
    app.do_preview()
    wait(app, timeout=60)
    assert len(app.plan) == app.PLAN_ROW_LIMIT + 500
    assert len(app.plan_tree.get_children()) == app.PLAN_ROW_LIMIT     # tabel dibatasi
    app._set_all_plan(False)
    assert not any(it["on"] for it in app.plan)                         # berlaku ke semua, bukan hanya yang tampil
    app.plan_search.set("doc_1")
    rows_before = len(app.plan_tree.get_children())
    pump(app, 0.05)
    assert len(app.plan_tree.get_children()) == rows_before            # belum render per huruf (debounce)
    pump(app, 0.4)
    assert all("doc_1" in app.plan_tree.item(i, "values")[1] for i in app.plan_tree.get_children())


def test_rules_conflict_enabled_toggle_and_bilingual_label(app, target, tmp_path, monkeypatch):
    import gui.pages.rules as rp
    import gui.common
    rules = tmp_path / "rules.yaml"
    rules.write_text("folder_info:\n  Projects: {en: Projects, id: Proyek}\nrules:\n"
                     "  - {name: Docs, ext: [pdf], dest: Docs}\n", encoding="utf-8")
    monkeypatch.setattr(rp, "RULES_PATH", rules)
    monkeypatch.setattr(gui.common, "RULES_PATH", rules)
    app.folder = str(target)
    app._load_doc()
    app._build_shell()
    app.open_rules("files")
    pump(app, 0.1)
    app.rules_tree.selection_set("0")
    pump(app, 0.1)
    app.form_vars["enabled"].set(False)
    pump(app, 0.05)
    assert app.doc["rules"][0]["enabled"] is False
    assert app.rules_tree.item("0", "values")[2].startswith("(off)")
    # label: hanya teks bahasa aktif yang berubah
    assert app._label_value({"en": "Projects", "id": "Proyek"}, "My projects") == {"en": "My projects", "id": "Proyek"}
    # file diedit di luar app → dialog konflik (AutoDialog memilih tombol pertama = Overwrite)
    rules.write_text(rules.read_text(encoding="utf-8") + "# edited in Notepad\n", encoding="utf-8")
    assert app.save_rules()
    saved = rules.read_text(encoding="utf-8")
    assert "enabled: false" in saved and "id: Proyek" in saved


def test_callback_error_does_not_freeze_later_tasks(app, target):
    app.folder = str(target)
    app._build_shell()
    app.run_bg("t1", lambda: 1, lambda r: 1 / 0)
    wait(app)
    got = []
    app.run_bg("t2", lambda: 2, got.append)
    wait(app)
    assert got == [2] and not app.busy


def test_only_active_page_is_reachable_by_tab(app, target):
    app.folder = str(target)
    app._build_shell()
    app.show_page("organize")
    pump(app, 0.1)
    assert all(not f.winfo_ismapped() for k, f in app.pages.items() if k != "organize")
    # tk_focusNext adalah proc Tcl yang dimuat malas (focus.tcl); di runner Windows auto_load kadang gagal
    if not app.root.tk.call("info", "commands", "tk_focusNext"):
        app.root.tk.eval("source [file join $tk_library focus.tcl]")
    w, seen = app.root, set()
    for _ in range(80):
        w = w.tk_focusNext()
        if w is None or w in seen:
            break
        seen.add(w)
        assert w.winfo_viewable(), f"focus reached hidden widget {w}"


def test_close_while_busy_stops_task_first(app, target):
    import threading
    app.folder = str(target)
    app._build_shell()
    started = threading.Event()

    def job():
        started.set()
        while not app.cancel_event.is_set():
            time.sleep(0.01)
        return "stopped"

    closed = []
    app._shutdown = lambda: closed.append(app.busy)
    app.run_bg("long", job, lambda r: None)
    started.wait(2)
    app._on_close()          # AutoDialog memilih "Stop and close"
    wait(app)
    pump(app, 0.3)
    assert closed == [False]  # baru ditutup setelah tugas berhenti


def test_changed_duplicate_is_not_moved(app, target):
    import organizer as org
    app.folder = str(target)
    app._build_shell()
    app.show_page("dupes")
    app.do_find_dupes()
    wait(app)
    assert app.dup_groups
    g = app.dup_groups[0]
    victim = g["files"][sorted(g["on"])[0]][0]
    victim.write_text("edited after the check")
    app.do_move_dupes()
    wait(app)
    assert victim.exists() and not (target / org.TRASH_DIR / victim.name).exists()


def test_update_flow_downloads_then_installs_and_closes(app, target, monkeypatch, tmp_path):
    import updates
    app.folder = str(target)
    app._build_shell()
    info = {"version": "9.9.9", "url": "https://github.com/x", "notes": "", "newer": True,
            "asset": {"name": "FolderOrganizer-Setup-9.9.9.exe", "url": "https://github.com/x", "size": 1, "sha256": "0"}}
    fake = tmp_path / "setup.exe"
    fake.write_text("x")
    calls = []
    monkeypatch.setattr(updates, "can_self_install", lambda *a: True)
    monkeypatch.setattr(updates, "download", lambda asset, progress=None, cancel=None: fake)
    monkeypatch.setattr(updates, "launch_installer", lambda p, log: calls.append(("launch", p)))
    monkeypatch.setattr(updates, "verify", lambda p, asset: True)
    app._shutdown = lambda: calls.append(("shutdown",))
    app.start_update(info)      # AutoDialog: "Install and restart"
    wait(app)
    assert calls == [("launch", fake), ("shutdown",)]


def test_update_verification_failure_is_reported_not_installed(app, target, monkeypatch):
    import updates
    app.folder = str(target)
    app._build_shell()
    info = {"version": "9.9.9", "url": "u", "notes": "", "newer": True, "asset": {"name": "s", "url": "u", "size": 1, "sha256": "0"}}
    monkeypatch.setattr(updates, "can_self_install", lambda *a: True)

    def bad(*a, **k):
        raise updates.UpdateError("bad_hash")

    monkeypatch.setattr(updates, "download", bad)
    monkeypatch.setattr(updates, "launch_installer", lambda *a: pytest.fail("must not install"))
    app.start_update(info)
    wait(app)
    assert app.infobar.winfo_ismapped() and not app.busy


def test_portable_build_opens_release_page_instead(app, target, monkeypatch):
    import updates
    import gui.updater
    opened = []
    monkeypatch.setattr(updates, "can_self_install", lambda *a: False)
    monkeypatch.setattr(gui.updater.webbrowser, "open", opened.append)
    app.folder = str(target)
    app._build_shell()
    app.start_update({"version": "9", "url": "https://github.com/r", "asset": {"name": "s"}})
    assert opened == ["https://github.com/r"]


def test_labels_create_missing_folders_then_apply(app, target, tmp_path, monkeypatch):
    import gui.common
    import gui.pages.rules as rp
    rules = tmp_path / "rules.yaml"
    rules.write_text("rules: []\nfolder_info:\n  Areas/Finance: Bills\n  Projects: Work\n", encoding="utf-8")
    monkeypatch.setattr(gui.common, "RULES_PATH", rules)
    monkeypatch.setattr(rp, "RULES_PATH", rules)
    import gui.shell
    monkeypatch.setattr(gui.shell, "RULES_PATH", rules)  # _cfg() membaca RULES_PATH dari gui.shell
    app.folder = str(target)
    app._load_doc()
    app._build_shell()
    app.show_page("labels")
    pump(app, 0.2)
    assert app.missing_labels == ["Areas/Finance"]
    assert app.btn_create_missing.winfo_ismapped()
    app.do_create_missing()
    pump(app, 0.2)
    assert (target / "Areas" / "Finance").is_dir() and not app.missing_labels


def test_dupes_keeper_button_only_with_results_and_toolbar_fits_min_size(app, target):
    app.folder = str(target)
    app._build_shell()
    app.root.geometry("1000x640")
    app.show_page("dupes")
    pump(app, 0.3)
    assert not app.btn_keeper.winfo_ismapped()
    app.do_find_dupes()
    wait(app)
    assert app.btn_keeper.winfo_ismapped()
    app.show_page("organize")
    pump(app, 0.3)
    bar = app.plan_search  # toolbar: tombol kanan tidak terpotong di ukuran minimum
    btns = [w for w in app.pages["organize"].winfo_children()[1].winfo_children() if w.winfo_class() == "TButton"]
    right = max(b.winfo_rootx() + b.winfo_width() for b in btns)
    page = app.pages["organize"]
    assert right <= page.winfo_rootx() + page.winfo_width() + 1, bar


def test_yaml_draft_survives_rebuild_and_tab_switch(app, target):
    app.folder = str(target)
    app._build_shell()
    app.open_rules("yaml")
    pump(app, 0.2)
    app.yaml_text.insert("1.0", "# my unapplied note\n")
    app._yaml_track()
    app._rules_section("files")
    app._build_shell()          # sama seperti ganti tema / pindah monitor
    app.open_rules("yaml")
    pump(app, 0.2)
    assert app.yaml_text.get("1.0", "2.0").startswith("# my unapplied note")
    assert app.yaml_pending()


def test_dpi_rebuild_waits_while_a_dialog_is_open(app, target, monkeypatch):
    import tkinter as tk
    app.folder = str(target)
    app._build_shell()
    app._dpi = 96
    monkeypatch.setattr(app, "_window_dpi", lambda: 144)
    rebuilt = []
    monkeypatch.setattr(app, "_build_shell", lambda: rebuilt.append(1))
    top = tk.Toplevel(app.root)
    pump(app, 0.1)
    top.grab_set()
    app._check_dpi()
    assert not rebuilt
    top.grab_release()
    top.destroy()
    app._check_dpi()
    assert rebuilt == [1]
    app.root.tk.call("tk", "scaling", 96 / 72.0)


def test_rules_edited_during_download_are_asked_before_install(app, target, monkeypatch, tmp_path):
    import updates
    app.folder = str(target)
    app._build_shell()
    asked, calls = [], []
    monkeypatch.setattr(updates, "verify", lambda p, a: True)
    monkeypatch.setattr(updates, "launch_installer", lambda p, log: calls.append("launch"))
    app._shutdown = lambda: calls.append("shutdown")
    app.dirty = True
    monkeypatch.setattr(app, "_ask_save_rules", lambda: asked.append(1) or False)  # user memilih Cancel
    app._install_update(tmp_path / "s.exe", {"version": "9", "asset": {}})
    assert asked == [1] and calls == []
    app.dirty = False


def test_theme_switch_does_not_wait_for_label_search(app, target, monkeypatch):
    import organizer as org
    app.folder = str(target)
    app._build_shell()
    slow = lambda *a, **k: (time.sleep(2), [])[1]  # noqa: E731  (folder raksasa, mis. C:\)
    monkeypatch.setattr(org, "find_managed_labels", slow)
    for page in ("settings", "labels"):
        app.show_page(page)
        t = time.time()
        app.theme_mode = "dark"
        app._rebuild()
        app.root.update()
        assert time.time() - t < 1.0, page


def test_label_status_fills_in_after_background_search(app, target):
    import organizer as org
    (target / "Projects").mkdir(exist_ok=True)
    org.write_folder_label(target / "Projects", "Work")
    app.folder = str(target)
    app._build_shell()
    app.show_page("labels")
    for _ in range(50):
        pump(app, 0.05)
        statuses = {app.label_tree.item(i, "values")[0]: app.label_tree.item(i, "values")[2]
                    for i in app.label_tree.get_children()}
        if statuses.get("Projects") != org.T("lbl_checking"):
            break
    assert statuses.get("Projects") == org.T("lbl_labeled")


def test_protected_folder_is_a_warning_with_scan_only(app, monkeypatch, tmp_path):
    import organizer as org
    prot = tmp_path / "Program Files"
    prot.mkdir()
    (prot / "a.pdf").write_text("x")
    monkeypatch.setenv("ProgramFiles", str(prot))
    app.folder = str(prot)
    app._build_shell()
    app.show_page("overview")
    app.do_scan()
    wait(app)
    assert app.scan_result["plan"] is None and len(app.scan_result["files"]) == 1   # scan tetap jalan
    assert not app.ov_plan_btn.winfo_ismapped()
    shown = []
    monkeypatch.setattr(app.infobar, "show", lambda kind, title, *a, **k: shown.append((kind, title)))
    app.show_page("organize")
    app.do_preview()
    wait(app)
    assert shown and shown[-1] == ("warning", org.T("unsafe_title"))
