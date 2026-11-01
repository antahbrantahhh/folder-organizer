"""Test engine Folder Organizer.  Jalankan:  pip install pytest  lalu  python -m pytest -q"""
import copy
import json
import os
import shutil
import sys
import time
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import organizer as org  # noqa: E402

DEFAULT_RULES = yaml.safe_load((ROOT / "rules.yaml").read_text(encoding="utf-8"))
DAY = 86400


@pytest.fixture(autouse=True)
def isolated_appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))


@pytest.fixture
def target(tmp_path):
    d = tmp_path / "target"
    d.mkdir()
    return d


def cfg(**overrides):
    c = copy.deepcopy(DEFAULT_RULES)
    c.update(overrides)
    return org.prepare_config(c)


def touch(p: Path, text="x", age_days=0):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    if age_days:
        t = time.time() - age_days * DAY
        os.utime(p, (t, t))
    return p


def set_age(p: Path, age_days):
    t = time.time() - age_days * DAY
    os.utime(p, (t, t))


def config_error(c):
    with pytest.raises(org.ConfigError) as e:
        org.prepare_config(c)
    return str(e.value.code)


# ───────── default rules ─────────

def test_default_rules_are_valid():
    c = cfg()
    assert c["folder_fallback"] is None, "default harus aman: folder yang tidak cocok dibiarkan"


# ───────── P0-1: journal unik ─────────

def test_two_batches_in_same_second_keep_separate_journals(target):
    c = cfg()
    touch(target / "a.pdf")
    org.execute(target, org.build_plan(target, c), "apply")
    touch(target / "b.pdf")
    org.execute(target, org.build_plan(target, c), "apply")
    journals = [j for j in org.list_journals(target) if j.suffix == ".jsonl"]
    assert len(journals) == 2
    assert [len(org.read_journal(j)) for j in journals] == [1, 1]
    # undo dua batch, terbaru dulu → keduanya kembali ke root
    org.undo_journal(target, journals[1])
    org.undo_journal(target, journals[0])
    assert sorted(p.name for p in target.iterdir() if p.is_file()) == ["a.pdf", "b.pdf"]


def test_journal_never_overwritten(target, monkeypatch):
    class Frozen(org.datetime):
        @classmethod
        def now(cls, tz=None):
            return org.datetime(2026, 1, 1, 12, 0, 0, 0)

    monkeypatch.setattr(org, "datetime", Frozen)
    state = org.state_dir(target)
    p1, f1 = org._new_journal("apply", state)
    f1.close()
    with pytest.raises(RuntimeError):  # waktu dibekukan → tidak bisa unik → gagal, bukan menimpa
        org._new_journal("apply", state)
    assert p1.exists()


def test_crash_mid_batch_leaves_consistent_journal(target, monkeypatch):
    c = cfg()
    for i in range(5):
        touch(target / f"f{i}.pdf", str(i))
    moves = org.build_plan(target, c)
    real, calls = shutil.move, {"n": 0}

    def flaky(a, b):
        calls["n"] += 1
        if calls["n"] == 3:
            raise KeyboardInterrupt
        return real(a, b)

    monkeypatch.setattr(org.shutil, "move", flaky)
    with pytest.raises(KeyboardInterrupt):
        org.execute(target, moves, "apply")
    monkeypatch.setattr(org.shutil, "move", real)
    j = org.list_journals(target)[-1]
    assert len(org.read_journal(j)) == 2
    assert org.undo_journal(target, j) == (2, 0)
    assert len([p for p in target.iterdir() if p.is_file()]) == 5


# ───────── P0-2: link vs OneDrive ─────────

class FakeStat:
    def __init__(self, tag=0, attrs=0, size=10, mtime=None):
        self.st_reparse_tag, self.st_file_attributes = tag, attrs
        self.st_size, self.st_mtime = size, mtime or time.time()


@pytest.mark.parametrize("tag,expected", [
    (0xA0000003, True),   # junction (mis. "My Music")
    (0xA000000C, True),   # symlink
    (0x8000001B, False),  # app exec alias: bukan name surrogate
    (0x9000001A, False),  # OneDrive cloud file
    (0x9000601A, False),  # OneDrive cloud file (varian)
    (0, False),
])
def test_reparse_tag_classification(tmp_path, tag, expected):
    p = touch(tmp_path / "x.txt")
    assert org.is_link_or_junction(p, FakeStat(tag=tag, attrs=0x400 if tag else 0)) is expected


def test_real_symlinks_are_skipped(target, tmp_path):
    outside = tmp_path / "outside"
    touch(outside / "secret.pdf")
    (target / "linkdir").symlink_to(outside, target_is_directory=True)
    (target / "link.pdf").symlink_to(outside / "secret.pdf")
    touch(target / "real.pdf")
    names = [p.name for p, _ in org.iter_files(target, True, [])]
    assert names == ["real.pdf"]


def test_dedupe_does_not_read_cloud_only_files(tmp_path):
    a, b = touch(tmp_path / "a.bin", "same"), touch(tmp_path / "b.bin", "same")
    cloud = FakeStat(attrs=0x400000, size=4)
    assert org.find_duplicates([(a, cloud), (b, cloud)]) == []
    local = FakeStat(size=4)
    assert len(org.find_duplicates([(a, local), (b, local)])) == 1


# ───────── P0-3: tujuan tidak boleh keluar dari folder target ─────────

@pytest.mark.parametrize("dest", ["../escaped", "Docs/../../x", "/tmp/elsewhere", "C:\\Windows", "c:/x", "~/x",
                                  "..\\up"])
def test_dest_outside_target_rejected(dest):
    c = copy.deepcopy(DEFAULT_RULES)
    c["rules"].insert(0, {"name": "bad", "ext": ["pdf"], "dest": dest})
    msg = config_error(c)
    assert "bad" in msg


def test_fallback_outside_target_rejected():
    c = copy.deepcopy(DEFAULT_RULES)
    c["fallback_dest"] = "../out"
    assert "fallback_dest" in config_error(c)


def test_runtime_guard_against_symlinked_destination(target, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (target / "Docs").symlink_to(outside, target_is_directory=True)
    touch(target / "a.pdf")
    c = copy.deepcopy(DEFAULT_RULES)
    c["rules"] = [{"name": "via link", "ext": ["pdf"], "dest": "Docs"}]
    with pytest.raises(org.ConfigError):
        org.build_plan(target, org.prepare_config(c))


# ───────── P1-4: key tidak dikenal ─────────

def test_typo_key_in_rule_is_reported_with_suggestion():
    c = copy.deepcopy(DEFAULT_RULES)
    c["rules"].insert(0, {"name": "typo", "ext": ["pdf"], "older_than_day": 365, "dest": "Old"})
    msg = config_error(c)
    assert "older_than_day" in msg and "older_than_days" in msg


def test_typo_key_at_top_level():
    c = copy.deepcopy(DEFAULT_RULES)
    c["folder_fallbak"] = "Projects"
    assert "folder_fallback" in config_error(c)


def test_file_only_keys_rejected_in_folder_rules():
    c = copy.deepcopy(DEFAULT_RULES)
    c["folder_rules"] = [{"name": "f", "ext": ["pdf"], "dest": "X"}]
    assert "ext" in config_error(c)


@pytest.mark.parametrize("value", ["30", -1, True, [1]])
def test_number_fields_must_be_non_negative_numbers(value):
    c = copy.deepcopy(DEFAULT_RULES)
    c["rules"] = [{"name": "n", "older_than_days": value, "dest": "X"}]
    assert "older_than_days" in config_error(c)


def test_empty_ext_means_any_file(target):
    touch(target / "a.xyz")
    c = copy.deepcopy(DEFAULT_RULES)
    c["rules"] = [{"name": "all", "ext": [], "dest": "All"}]
    moves = org.build_plan(target, org.prepare_config(c), include_folders=False)
    assert [m.reason for m in moves] == ["all"]


def test_internal_keys_survive_second_prepare():
    c = cfg()
    org.prepare_config(c)  # dipanggil ulang (mis. dari GUI) tidak boleh error karena _ext/_re
    assert "_ext" in c["rules"][0]


# ───────── P1-5: placeholder ─────────

@pytest.mark.parametrize("dest,needle", [("Docs/{yaer}", "yaer"), ("Docs/{year", "format"), ("Docs/{}", "'{}'")])
def test_bad_placeholder_rejected(dest, needle):
    c = copy.deepcopy(DEFAULT_RULES)
    c["rules"] = [{"name": "p", "dest": dest}]
    assert needle in config_error(c)


def test_ext_placeholder_not_allowed_for_folders():
    c = copy.deepcopy(DEFAULT_RULES)
    c["folder_rules"] = [{"name": "f", "dest": "Arsip/{ext}"}]
    assert "{ext}" in config_error(c)


def test_dest_error_helper_used_by_gui():
    assert org.dest_error("Media/{year}/{month}") is None
    assert org.dest_error("") is not None
    assert org.dest_error("X/{EXT}", is_folder=True) is not None


# ───────── P1-6: umur folder = aktivitas terakhir ─────────

def _archive_cfg():
    c = copy.deepcopy(DEFAULT_RULES)
    c["folder_rules"] = [{"name": "old", "older_than_days": 180, "dest": "_Archive/Folders/{year}"}]
    c["folder_fallback"] = None
    return org.prepare_config(c)


def test_active_project_with_recent_nested_edit_is_not_archived(target):
    proj = target / "ActiveProject"
    touch(proj / "src" / "deep" / "main.dart", age_days=0)  # baru diedit, jauh di dalam
    set_age(proj / "src" / "deep", 400)
    set_age(proj / "src", 400)
    set_age(proj, 400)  # mtime folder level atas terlihat lama
    assert org.build_plan(target, _archive_cfg()) == []


def test_truly_old_folder_is_archived(target):
    proj = target / "OldProject"
    touch(proj / "a" / "b.txt", age_days=500)
    set_age(proj / "a", 500)
    set_age(proj, 500)
    moves = org.build_plan(target, _archive_cfg())
    assert [m.src.name for m in moves] == ["OldProject"]
    assert "_Archive/Folders/" in moves[0].dst.as_posix()


def test_huge_folder_treated_as_active(target, monkeypatch):
    monkeypatch.setattr(org, "FOLDER_AGE_SCAN_CAP", 3)
    proj = target / "Huge"
    for i in range(10):
        touch(proj / f"f{i}.txt", age_days=500)
    set_age(proj, 500)
    assert org.build_plan(target, _archive_cfg()) == []


# ───────── P1-7: default fallback folder aman ─────────

def test_unmatched_folders_stay_by_default(target):
    (target / "Custom App Data").mkdir()
    (target / "SomeProject").mkdir()
    assert [m for m in org.build_plan(target, cfg()) if m.src.is_dir()] == []


def test_junction_like_and_protected_folders_never_moved(target):
    (target / "Custom Office Templates").mkdir()
    (target / "Visual Studio 2022").mkdir()
    c = copy.deepcopy(DEFAULT_RULES)
    c["folder_fallback"] = "Projects"
    moved = [m.src.name for m in org.build_plan(target, org.prepare_config(c))]
    assert moved == []


# ───────── P1-8: state di APPDATA, journal lama tetap terbaca ─────────

def test_state_lives_outside_target(target, tmp_path):
    touch(target / "a.pdf")
    org.execute(target, org.build_plan(target, cfg()), "apply")
    assert not (target / org.STATE_DIR).exists()
    journals = org.list_journals(target)
    assert journals and (tmp_path / "appdata") in journals[0].parents
    assert (org.state_dir(target) / "target.txt").read_text() == str(target.resolve())


def test_legacy_journal_still_listed_and_undoable(target):
    legacy = target / org.STATE_DIR
    legacy.mkdir()
    moved = touch(target / "Documents" / "2026" / "old.pdf")
    (legacy / "journal_20260101_120000_apply.jsonl").write_text(
        json.dumps({"src": str(target / "old.pdf"), "dst": str(moved)}) + "\n", encoding="utf-8")
    journals = org.list_journals(target)
    assert len(journals) == 1
    assert org.undo_journal(target, journals[0]) == (1, 0)
    assert (target / "old.pdf").exists()


def test_journal_ordering_mixes_old_and_new_formats(target):
    legacy = target / org.STATE_DIR
    legacy.mkdir()
    (legacy / "journal_20260101_120000_apply.jsonl").write_text("")
    new = org.state_dir(target)
    (new / "journal_20260101_120000_500000_dedupe.jsonl").write_text("")
    (new / "journal_20251231_235959_000001_apply.undone").write_text("")
    assert [j.name for j in org.list_journals(target)] == [
        "journal_20251231_235959_000001_apply.undone",
        "journal_20260101_120000_apply.jsonl",
        "journal_20260101_120000_500000_dedupe.jsonl",
    ]


def test_blocked_write_raises_access_blocked(target, monkeypatch):
    def deny(self, *a, **k):
        raise FileNotFoundError(2, "The system cannot find the file specified")

    monkeypatch.setattr(Path, "write_text", deny)
    with pytest.raises(org.AccessBlocked):
        org.execute(target, [], "apply")


# ───────── perilaku dasar yang tidak boleh rusak ─────────

def test_case_insensitive_name_collision(target):
    touch(target / "Report.pdf", "a")
    touch(target / "report.PDF", "b")
    if len(list(target.iterdir())) < 2:
        pytest.skip("case-insensitive file system (Windows): both names are the same file")
    dests = sorted(m.dst.name.lower() for m in org.build_plan(target, cfg()))
    assert len(set(dests)) == 2


def test_plan_is_dry_run(target):
    touch(target / "a.pdf")
    org.build_plan(target, cfg())
    assert (target / "a.pdf").exists()
    assert not any(p.is_dir() for p in target.iterdir())


# ───────── P1-9: tanggal EXIF foto ─────────

def test_photo_sorted_by_exif_date(target):
    Image = pytest.importorskip("PIL.Image")
    img = Image.new("RGB", (4, 4))
    exif = Image.Exif()
    exif[36867] = "2019:07:14 10:00:00"  # DateTimeOriginal
    img.save(target / "IMG_0001.jpg", exif=exif)
    moves = org.build_plan(target, cfg())
    assert moves[0].dst.parent.as_posix().endswith("Media/Photos/2019-07")


# ───────── P2: dwibahasa ─────────

@pytest.fixture
def lang_id():
    from i18n import T
    T.lang = "id"
    yield
    T.lang = "en"


def test_config_errors_follow_language(lang_id):
    c = copy.deepcopy(DEFAULT_RULES)
    c["rules"] = [{"name": "x", "dest": "../out"}]
    assert "tidak boleh keluar" in config_error(c)


def test_config_errors_default_english():
    c = copy.deepcopy(DEFAULT_RULES)
    c["rules"] = [{"name": "x", "dest": "../out"}]
    assert "must stay inside" in config_error(c)


def test_dates_localized(lang_id):
    from i18n import fmt_date
    assert fmt_date(org.datetime(2026, 12, 3, 9, 5)) == "03 Des 2026 09:05"


def test_journal_time_parses_old_and_new_names():
    assert org.journal_time(Path("journal_20260101_120000_apply.jsonl")) == org.datetime(2026, 1, 1, 12, 0, 0)
    assert org.journal_time(Path("journal_20260101_120000_250000_watch.undone")).microsecond == 250000


# ───────── P2: cancel & progress ─────────

class Flag:
    def __init__(self, after=0):
        self.calls, self.after = 0, after

    def is_set(self):
        self.calls += 1
        return self.calls > self.after


def test_scan_can_be_cancelled(target):
    for i in range(600):
        touch(target / f"f{i}.txt")
    with pytest.raises(org.Cancelled):
        list(org.iter_files(target, True, [], cancel=Flag(after=1)))


def test_scan_reports_progress(target):
    for i in range(600):
        touch(target / f"f{i}.txt")
    seen = []
    list(org.iter_files(target, True, [], progress=lambda n, total: seen.append(n)))
    assert seen and seen[-1] >= 500


def test_dedupe_progress_reaches_total_and_can_cancel(tmp_path):
    files = [touch(tmp_path / f"{i}.bin", "same-content") for i in range(4)]
    stats = [(p, p.stat()) for p in files]
    ticks = []
    groups = org.find_duplicates(stats, progress=lambda d, t: ticks.append((d, t)))
    assert len(groups) == 1 and ticks[-1][0] == ticks[-1][1]
    with pytest.raises(org.Cancelled):
        org.find_duplicates(stats, cancel=Flag(after=0))


def test_execute_cancel_keeps_partial_batch_undoable(target):
    for i in range(6):
        touch(target / f"f{i}.pdf", str(i))
    moves = org.build_plan(target, cfg())
    ok, failed = org.execute(target, moves, "apply", cancel=Flag(after=2))
    assert ok == 2 and not failed
    j = org.list_journals(target)[-1]
    assert org.undo_journal(target, j) == (2, 0)
    assert len([p for p in target.iterdir() if p.is_file()]) == 6


# ───────── P2: hapus label ─────────

def read_ini(folder):
    return (folder / "desktop.ini").read_text(encoding="utf-16")


def test_remove_label_deletes_only_what_app_created(target):
    f = target / "Projects"
    f.mkdir()
    org.write_folder_label(f, "Active work")
    assert org.is_managed_label(f) and (f / org.README_NAME).exists()
    assert org.remove_folder_label(f) is True
    assert not (f / "desktop.ini").exists() and not (f / org.README_NAME).exists()


def test_remove_label_keeps_foreign_desktop_ini_settings(target):
    f = target / "Media"
    f.mkdir()
    (f / "desktop.ini").write_text("[.ShellClassInfo]\r\nIconResource=C:\\x.ico,0\r\n[ViewState]\r\nMode=4\r\n",
                                   encoding="utf-16")
    org.write_folder_label(f, "Photos and videos")
    org.remove_folder_label(f)
    ini = read_ini(f)
    assert "InfoTip" not in ini and "[FolderOrganizer]" not in ini
    assert "[ViewState]" in ini and "Mode=4" in ini


def test_foreign_label_is_not_touched(target):
    f = target / "Theirs"
    f.mkdir()
    (f / "desktop.ini").write_text("[.ShellClassInfo]\r\nInfoTip=Made by someone else\r\n", encoding="utf-16")
    (f / org.README_NAME).write_text("not ours", encoding="utf-8")
    assert org.is_managed_label(f) is False
    assert org.remove_folder_label(f) is False
    assert "someone else" in read_ini(f) and (f / org.README_NAME).exists()


def test_legacy_label_without_marker_is_recognized(target):
    f = target / "Old"
    f.mkdir()
    (f / "desktop.ini").write_text("[.ShellClassInfo]\r\nInfoTip=old\r\n", encoding="utf-16")
    (f / org.README_NAME).write_text("Old\n(Dibuat otomatis oleh Folder Organizer — …)", encoding="utf-8-sig")
    assert org.find_managed_labels(target) == ["Old"]


def test_find_managed_labels_including_nested_and_orphans(target):
    for rel_path in ("A", "B/Inner"):
        (target / rel_path).mkdir(parents=True)
        org.write_folder_label(target / rel_path, "x")
    (target / "Plain").mkdir()
    assert org.find_managed_labels(target) == ["A", "B/Inner"]
    res = org.remove_labels(target, ["A", "B/Inner", "Missing"])
    assert [r[1] for r in res] == ["ok", "ok", "missing"]
    assert org.find_managed_labels(target) == []


# ───────── v3.9 hardening ─────────

def test_folder_rule_keep_in_place_does_not_rename(target):
    (target / "Keep Me").mkdir()
    (target / "Keep Me" / "a.txt").write_text("x")
    c = org.prepare_config({"folder_rules": [{"name": "keep", "name_regex": "^keep", "dest": "."}], "rules": []})
    assert org.build_plan(target, c) == []


def test_organized_files_do_not_drift_each_month(target):
    note = touch(target / "Documents" / "Notes" / "2026-09" / "note.md")  # diedit hari ini → tanggal Oktober/November
    c = copy.deepcopy(DEFAULT_RULES)
    c["recursive"] = True
    moves = org.build_plan(target, org.prepare_config(c))
    assert note not in [m.src for m in moves]


def test_old_layout_still_migrates_to_period_folders(target):
    old = touch(target / "Documents" / "2026" / "spec.md")  # layout lama Documents/{year}
    c = copy.deepcopy(DEFAULT_RULES)
    c["recursive"] = True
    moves = {m.src: m for m in org.build_plan(target, org.prepare_config(c))}
    assert old in moves and "Documents/Notes/" in moves[old].dst.as_posix()


def test_dest_pattern_follows_date_format():
    rx = org.dest_pattern("Media/Photos/{period}", "{year}/{month}")
    assert rx.fullmatch("media/photos/2026/10") and not rx.fullmatch("media/photos/2026-10")
    assert org.dest_pattern("Resources/CAD", "{year}") is None


def test_long_path_failure_gets_clear_message(target, monkeypatch):
    src = touch(target / "a.pdf")
    dst = target / ("x" * 250) / "a.pdf"
    monkeypatch.setattr(org.sys, "platform", "win32")
    monkeypatch.setattr(org, "_win_set_attrs", lambda *a, **k: None)
    def boom(*a, **k):
        raise FileNotFoundError(3, "The system cannot find the path specified")
    monkeypatch.setattr(org.shutil, "move", boom)
    ok, failed = org.execute(target, [org.Move(src, dst, "r")], "apply")
    assert ok == 0 and "260" in failed[0][1]


def test_rules_fall_back_to_appdata_when_app_dir_not_writable(tmp_path, monkeypatch):
    app = tmp_path / "Program Files" / "Folder Organizer"
    app.mkdir(parents=True)
    (app / "rules.yaml").write_text("rules: []\n", encoding="utf-8")
    monkeypatch.setattr(org, "app_dir", lambda: app)
    monkeypatch.setattr(org, "_writable_dir", lambda d: d != app)
    path = org.rules_path()
    assert path == org.app_data_dir() / "rules.yaml"
    assert path.read_text(encoding="utf-8") == "rules: []\n"  # aturan lama ikut disalin


def test_rules_stay_next_to_app_when_writable(tmp_path, monkeypatch):
    app = tmp_path / "portable"
    app.mkdir()
    (app / "rules.yaml").write_text("rules: []\n", encoding="utf-8")
    monkeypatch.setattr(org, "app_dir", lambda: app)
    assert org.rules_path() == app / "rules.yaml"


def test_batches_are_logged(target, tmp_path):
    import logging
    path = org.setup_logging()
    touch(target / "a.pdf")
    org.execute(target, org.build_plan(target, cfg()), "apply")
    for h in org.log.handlers:
        h.flush()
    text = path.read_text(encoding="utf-8")
    assert "batch apply" in text and "1 moved" in text
    for h in list(org.log.handlers):  # bersihkan supaya test lain tidak menulis ke file ini
        org.log.removeHandler(h)
        h.close()
    assert logging.getLogger("folder_organizer").handlers == []


# ───────── v3.10: lock per folder, pruning journal, label dwibahasa ─────────

def test_folder_lock_blocks_second_process(tmp_path):
    root = tmp_path / "t"
    root.mkdir()
    lock = org.state_dir(root) / org.LOCK_NAME
    lock.write_text(json.dumps({"pid": os.getpid() + 0, "purpose": "watch", "since": time.time()}), encoding="utf-8")
    # PID sendiri dianggap hidup → seolah proses lain memegang lock
    with pytest.raises(org.FolderBusy) as e:
        with org.folder_lock(root, "apply"):
            pass
    assert "watch" in str(e.value)
    assert lock.exists()  # lock milik proses lain tidak dihapus


def test_stale_lock_is_taken_over(tmp_path):
    root = tmp_path / "t"
    root.mkdir()
    (root / "a.pdf").write_text("x")
    lock = org.state_dir(root) / org.LOCK_NAME
    lock.write_text(json.dumps({"pid": 999999999, "purpose": "apply", "since": time.time()}), encoding="utf-8")
    moves = org.build_plan(root, org.prepare_config({"rules": [{"name": "d", "ext": ["pdf"], "dest": "D"}]}))
    ok, failed = org.execute(root, moves, "apply")
    assert ok == 1 and not lock.exists()


def test_old_lock_is_stale_even_if_pid_alive(tmp_path):
    root = tmp_path / "t"
    root.mkdir()
    lock = org.state_dir(root) / org.LOCK_NAME
    lock.write_text(json.dumps({"pid": os.getpid(), "since": time.time() - org.LOCK_STALE_SECS - 10}), encoding="utf-8")
    with org.folder_lock(root, "apply"):
        assert json.loads(lock.read_text())["purpose"] == "apply"
    assert not lock.exists()


def test_prune_journals_keeps_recent_and_minimum(tmp_path):
    root = tmp_path / "t"
    root.mkdir()
    state = org.state_dir(root)
    old = time.time() - 200 * 86400
    for i in range(5):
        j = state / f"journal_20250101_00000{i}_000000_apply.jsonl"
        j.write_text("")
        os.utime(j, (old, old))
    fresh = state / "journal_29990101_000000_000000_apply.jsonl"
    fresh.write_text("")
    assert org.prune_journals(root, keep_days=0) == 0
    removed = org.prune_journals(root, keep_days=90, keep_min=2)
    left = org.list_journals(root)
    assert removed == 4 and fresh in left and len(left) == 2


def test_label_text_follows_language():
    v = {"en": "Bills", "id": "Tagihan"}
    assert org.label_text(v, "en") == "Bills" and org.label_text(v, "id") == "Tagihan"
    assert org.label_text("Plain") == "Plain"
    assert org.label_text({"desc": "Old style"}, "id") == "Old style"
    assert org.label_text({"en": "Only EN"}, "id") == "Only EN"


def test_disabled_rule_is_skipped(tmp_path):
    (tmp_path / "a.pdf").write_text("x")
    c = {"rules": [{"name": "off", "enabled": False, "ext": ["pdf"], "dest": "Off"},
                   {"name": "on", "ext": ["pdf"], "dest": "On"}]}
    moves = org.build_plan(tmp_path, org.prepare_config(c))
    assert moves[0].dst.parent.name == "On"
    with pytest.raises(org.ConfigError):
        org.prepare_config({"rules": [{"name": "x", "enabled": "no", "dest": "X"}]})
