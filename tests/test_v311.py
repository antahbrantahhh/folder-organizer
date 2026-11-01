"""Regresi audit v3.10 → v3.11: pemindahan tanpa copy, undo yang bisa diulang, folder sistem, mode recursive,
placeholder download, foto OneDrive, label folder."""
import os
import shutil
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import organizer as org  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))


@pytest.fixture
def target(tmp_path):
    d = tmp_path / "target"
    d.mkdir()
    return d


def touch(p: Path, text="x", age_days=0):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    if age_days:
        t = time.time() - age_days * 86400
        os.utime(p, (t, t))
    return p


def no_copy(monkeypatch):
    def fail(*a, **k):
        raise AssertionError("copy fallback used")
    for name in ("copy", "copy2", "copytree", "copyfile", "rmtree", "move"):
        monkeypatch.setattr(shutil, name, fail)


# ───────── P0-1: rename gagal → tidak ada copy, tidak ada duplikat ─────────

@pytest.mark.parametrize("is_dir", [False, True])
def test_locked_item_is_reported_not_copied(target, monkeypatch, is_dir):
    src = target / ("proj" if is_dir else "a.pdf")
    if is_dir:
        touch(src / "inner.txt")
    else:
        touch(src)
    dst = target / "Out" / src.name
    real = os.rename

    def locked(a, b):
        if Path(a) == src:
            raise PermissionError(13, "The process cannot access the file because it is being used")
        return real(a, b)

    monkeypatch.setattr(org.os, "rename", locked)
    no_copy(monkeypatch)
    ok, failed = org.execute(target, [org.Move(src, dst, "r")], "apply")
    assert ok == 0 and len(failed) == 1
    assert src.exists() and not dst.exists() and not (target / "Out").exists()  # folder kosong dibersihkan
    assert not [j for j in org.list_journals(target)]


def test_undo_failure_keeps_journal_for_retry(target, monkeypatch):
    for n in ("a.pdf", "b.pdf"):
        touch(target / n)
    c = org.prepare_config({"rules": [{"name": "d", "ext": ["pdf"], "dest": "D"}]})
    org.execute(target, org.build_plan(target, c), "apply")
    j = org.list_journals(target)[-1]
    real = os.rename

    def locked(a, b):
        if Path(a).name == "b.pdf" and Path(a).parent.name == "D":
            raise PermissionError(13, "in use")
        return real(a, b)

    monkeypatch.setattr(org.os, "rename", locked)
    assert org.undo_journal(target, j) == (1, 0, 1)
    assert j.exists() and len(org.read_journal(j)) == 1  # masih bisa di-undo
    monkeypatch.setattr(org.os, "rename", real)
    assert org.undo_journal(target, j) == (1, 0, 0)
    assert (target / "a.pdf").exists() and (target / "b.pdf").exists() and not j.exists()


# ───────── P1: folder sistem / profil / root drive ditolak ─────────

def test_system_folders_are_refused(tmp_path, monkeypatch):
    pf = tmp_path / "Program Files"
    (pf / "App").mkdir(parents=True)
    profile = tmp_path / "Users" / "bangke"
    (profile / "Downloads").mkdir(parents=True)
    monkeypatch.setenv("ProgramFiles", str(pf))
    monkeypatch.setenv("USERPROFILE", str(profile))
    c = org.prepare_config({"rules": []})
    for bad in (pf, pf / "App", profile, Path(Path(tmp_path).anchor)):
        with pytest.raises(org.ConfigError):
            org.build_plan(bad, c)
        with pytest.raises(org.ConfigError):
            org.execute(bad, [], "apply")
    assert org.unsafe_target(profile / "Downloads") is None


def test_temp_folder_inside_localappdata_is_allowed(tmp_path, monkeypatch):
    import tempfile
    local = Path(tempfile.gettempdir()).resolve().parent
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    assert org.unsafe_target(Path(tempfile.gettempdir()) / "x") is None
    assert org.unsafe_target(local) is not None or local == Path(local.anchor)


# ───────── P1: mode recursive ─────────

def test_recursive_keeps_folder_rule_destinations_intact(target):
    archived = touch(target / "_Archive" / "Folders" / "2025-01" / "proj" / "report.pdf", age_days=400)
    loose = touch(target / "inbox" / "note.pdf")
    c = org.prepare_config({"recursive": True,
                            "rules": [{"name": "docs", "ext": ["pdf"], "dest": "Documents/{period}"}],
                            "folder_rules": [{"name": "old", "older_than_days": 180, "dest": "_Archive/Folders/{period}"}]})
    srcs = {m.src for m in org.build_plan(target, c)}
    assert archived not in srcs and loose in srcs


def test_recursive_dot_dest_leaves_file_in_its_subfolder(target):
    lnk = touch(target / "sub" / "app.lnk")
    c = org.prepare_config({"recursive": True, "rules": [{"name": "keep", "ext": ["lnk"], "dest": "."}]})
    assert lnk not in {m.src for m in org.build_plan(target, c)}


def test_files_inside_a_moved_folder_are_not_planned_separately(target):
    inner = touch(target / "old" / "a.pdf", age_days=400)
    os.utime(target / "old", (time.time() - 400 * 86400,) * 2)
    c = org.prepare_config({"recursive": True, "rules": [{"name": "docs", "ext": ["pdf"], "dest": "Documents"}],
                            "folder_rules": [{"name": "old", "older_than_days": 180, "dest": "_Archive/Folders"}]})
    moves = org.build_plan(target, c)
    assert [m.src.name for m in moves] == ["old"] and inner not in {m.src for m in moves}
    ok, failed = org.execute(target, moves, "apply")
    assert ok == 1 and not failed and not (target / "Documents").exists()


# ───────── P1: watch & download placeholder ─────────

def test_download_placeholder_and_empty_files_skipped(target):
    old = time.time() - 3600
    for n, text in (("x.pdf", ""), ("x.pdf.part", "data"), ("y.pdf", ""), ("z.pdf", "ok")):
        p = touch(target / n, text)
        os.utime(p, (old, old))
    files = {p.name for p, _ in org.iter_files(target, False, [], stable_secs=15)}
    assert files == {"z.pdf"}                       # watch: placeholder & file 0 byte dilewati
    files = {p.name for p, _ in org.iter_files(target, False, [])}
    assert "x.pdf" not in files and "y.pdf" in files  # manual: hanya placeholder dengan .part yang dilewati


# ───────── P1: foto OneDrive yang belum di-download tidak dibuka ─────────

def test_cloud_only_photo_not_opened(tmp_path, monkeypatch):
    p = touch(tmp_path / "IMG_0001.jpg")

    class St:
        st_mtime = time.mktime((2024, 5, 1, 12, 0, 0, 0, 0, -1))
        st_file_attributes = 0x400000

    opened = []
    if org.HAS_PIL:
        monkeypatch.setattr(org.Image, "open", lambda *a, **k: opened.append(a) or (_ for _ in ()).throw(OSError()))
    assert org.file_date(p, St()).year == 2024 and not opened


# ───────── P1: label folder ─────────

def test_label_keeps_user_readme_and_custom_icon(target):
    f = target / "Projects"
    f.mkdir()
    (f / "_README.txt").write_text("My notes about Folder Organizer usage\nkeep me\n", encoding="utf-8")
    (f / "desktop.ini").write_text("[.ShellClassInfo]\r\nIconResource=C:\\icons\\proj.ico,0\r\n", encoding="utf-16")
    org.write_folder_label(f, "Active work")
    ini = org._read_ini(f / "desktop.ini")
    assert "IconResource=C:\\icons\\proj.ico,0" in ini and "InfoTip=Active work" in ini
    assert "keep me" in (f / "_README.txt").read_text(encoding="utf-8")
    assert not org._readme_is_ours(f / "_README.txt")
    org.remove_folder_label(f)
    assert (f / "_README.txt").exists()
    assert "IconResource=C:\\icons\\proj.ico,0" in org._read_ini(f / "desktop.ini")


def test_rule_icon_is_restored_to_original_on_remove(target):
    f = target / "Media"
    f.mkdir()
    (f / "desktop.ini").write_text("[.ShellClassInfo]\r\nIconResource=orig.ico,0\r\n", encoding="utf-16")
    org.write_folder_label(f, "Photos", icon="media.ico,0")
    assert "IconResource=media.ico,0" in org._read_ini(f / "desktop.ini")
    org.write_folder_label(f, "Photos again", icon="media.ico,0")  # label ulang tidak kehilangan ikon asli
    org.remove_folder_label(f)
    ini = org._read_ini(f / "desktop.ini")
    assert "IconResource=orig.ico,0" in ini and "media.ico" not in ini


@pytest.mark.parametrize("bad", ["../outside", "C:/Windows", "/etc", "a/../../b"])
def test_label_paths_must_stay_inside(target, bad):
    with pytest.raises(org.ConfigError):
        org.prepare_config({"rules": [], "folder_info": {bad: "x"}})
    res = org.apply_labels(target, {"folder_info": {bad: "x"}})
    assert res[0][1] == "error"


# ───────── verifikasi independen v3.11 ─────────

def test_folders_above_appdata_and_other_profiles_refused(tmp_path, monkeypatch):
    users = tmp_path / "Users"
    me, other = users / "bangke", users / "other"
    for d in (me / "AppData" / "Roaming", me / "AppData" / "Local", other / "Downloads"):
        d.mkdir(parents=True)
    monkeypatch.setenv("USERPROFILE", str(me))
    monkeypatch.setenv("APPDATA", str(me / "AppData" / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(me / "AppData" / "Local"))
    monkeypatch.setattr(org.tempfile, "gettempdir", lambda: str(me / "AppData" / "Local" / "Temp"))
    for bad in (me / "AppData", other, users):
        assert org.unsafe_target(bad), bad
    assert org.unsafe_target(other / "Downloads") is None


@pytest.mark.parametrize("dest", ["_Archive/Folders_{year}", "{year}/Folders", "./_Archive/Old"])
def test_recursive_skip_handles_any_placeholder_position(target, dest):
    import datetime
    y = datetime.date.today().year
    sample = dest.replace("{year}", str(y)).lstrip("./")
    archived = touch(target / sample / "proj" / "r.pdf")
    c = org.prepare_config({"recursive": True, "rules": [{"name": "docs", "ext": ["pdf"], "dest": "Documents"}],
                            "folder_rules": [{"name": "f", "name_regex": "^zzz$", "dest": dest}]})
    assert archived not in {m.src for m in org.build_plan(target, c)}


def test_failed_move_keeps_users_existing_empty_folder(target, monkeypatch):
    (target / "Documents").mkdir()
    src = touch(target / "a.pdf")
    monkeypatch.setattr(org.os, "rename", lambda a, b: (_ for _ in ()).throw(PermissionError(13, "in use")))
    org.execute(target, [org.Move(src, target / "Documents" / "2026" / "a.pdf", "r")], "apply")
    assert (target / "Documents").is_dir() and not (target / "Documents" / "2026").exists()


def test_icon_changed_by_user_after_label_is_kept(target):
    f = target / "Media"
    f.mkdir()
    (f / "desktop.ini").write_text("[.ShellClassInfo]\r\nIconResource=orig.ico,0\r\n", encoding="utf-16")
    org.write_folder_label(f, "Photos", icon="media.ico,0")
    ini = org._read_ini(f / "desktop.ini").replace("IconResource=media.ico,0", "IconResource=user2.ico,0")
    (f / "desktop.ini").write_text(ini, encoding="utf-16")  # user ganti ikon di Explorer
    org.remove_folder_label(f)
    assert "IconResource=user2.ico,0" in org._read_ini(f / "desktop.ini")
    org.write_folder_label(f, "Photos", icon="media.ico,0")
    org.remove_folder_label(f)
    assert "IconResource=user2.ico,0" in org._read_ini(f / "desktop.ini")
