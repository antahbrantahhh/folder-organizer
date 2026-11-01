"""Smoke test GUI end-to-end (scan → preview → apply → cancel → undo → label → keyboard).

Butuh display. Jalankan dengan:  set RUN_GUI_TESTS=1  lalu  python -m pytest -q tests/test_gui_smoke.py
(di Linux tanpa layar: xvfb-run). Dilewati secara default supaya `pytest` biasa tetap cepat.
"""
import os
import shutil
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
    a.watch_stop.set()
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

    real_move = shutil.move
    org.shutil.move = lambda s, d: (time.sleep(0.03), real_move(s, d))[1]
    try:
        app.do_apply()
        pump(app, 0.3)
        app.cancel_task()
        wait(app)
    finally:
        org.shutil.move = real_move
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
