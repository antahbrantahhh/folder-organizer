"""Test library kategori dan aturan bawaan (rules.yaml) terhadap nama file realistis."""
import collections
import copy
import os
import sys
import time
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import organizer as org  # noqa: E402

RULES = yaml.safe_load((ROOT / "rules.yaml").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def isolated_appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))


# ───────── library ─────────

def test_library_is_well_formed_and_disjoint():
    lib = org.builtin_categories()
    assert len(lib) >= 40
    owners = collections.defaultdict(list)
    for name, c in lib.items():
        assert {"group", "en", "id", "ext"} <= set(c), name
        assert c["ext"], name
        for e in c["ext"]:
            assert e == str(e).lower().lstrip("."), (name, e)
            owners[e].append(name)
    dupes = {e: n for e, n in owners.items() if len(n) > 1}
    assert not dupes, f"ekstensi di lebih dari satu kategori: {dupes}"
    name_owners = collections.defaultdict(list)
    for name, c in lib.items():
        for x in c.get("names", []):
            name_owners[str(x).lower()].append(name)
    assert not {x: n for x, n in name_owners.items() if len(n) > 1}


def test_custom_categories_extend_replace_and_create():
    lib = org.build_category_library({
        "cad_mech": ["scdoc"],
        "image": {"ext": ["png"], "replace": True},
        "certificates_training": {"ext": ["pdf"], "en": "Training certificates"},
    })
    assert "scdoc" in lib["cad_mech"]["ext"] and "step" in lib["cad_mech"]["ext"]
    assert lib["image"]["ext"] == ["png"]
    assert lib["certificates_training"]["en"] == "Training certificates"


def test_unknown_category_suggests_closest():
    c = copy.deepcopy(RULES)
    c["rules"] = [{"name": "x", "category": "cad_mesh", "dest": "X"}]
    with pytest.raises(org.ConfigError) as e:
        org.prepare_config(c)
    assert "cad_mesh" in str(e.value.code) and "cad_mech" in str(e.value.code)


def test_category_not_allowed_in_folder_rules():
    c = copy.deepcopy(RULES)
    c["folder_rules"] = [{"name": "f", "category": "code", "dest": "X"}]
    with pytest.raises(org.ConfigError):
        org.prepare_config(c)


def test_bad_custom_category_value():
    c = copy.deepcopy(RULES)
    c["categories"] = {"oops": "pdf"}
    with pytest.raises(org.ConfigError):
        org.prepare_config(c)


def test_category_and_ext_are_combined(tmp_path):
    (tmp_path / "a.step").write_text("x")
    (tmp_path / "b.scdoc").write_text("x")
    c = {"rules": [{"name": "cad", "category": "cad_mech", "ext": ["scdoc"], "dest": "CAD"}]}
    moves = org.build_plan(tmp_path, org.prepare_config(c))
    assert sorted(m.src.name for m in moves) == ["a.step", "b.scdoc"]


# ───────── aturan bawaan vs nama file nyata ─────────

DAY = 86400

FILES = {  # nama → (umur hari, folder tujuan yang diharapkan; "." = tetap di tempat)
    "KTP.png": (300, "Areas/Personal/Identity"),
    "KTP + NPWP.jpg": (300, "Areas/Personal/Identity"),
    "Akta Milan.pdf": (400, "Areas/Personal/Identity"),
    "id_rsa.pem": (1, "Areas/Personal/Keys"),
    "Vault.kdbx": (1, "Areas/Personal/Keys"),
    "invoice_tokopedia_okt.pdf": (2, "Areas/Finance/Invoices/{y}-{m}"),
    "INV-2026-001.pdf": (2, "Areas/Finance/Invoices/{y}-{m}"),
    "Catatan notaris.pdf": (5, "Documents/{y}-{m}"),
    "SK mutasi pegawai.pdf": (5, "Documents/{y}-{m}"),
    "inventory.xlsx": (5, "Documents/Spreadsheets/{y}-{m}"),
    "Mutasi Rekening BCA Okt.pdf": (3, "Areas/Finance/Statements/{y}-{m}"),
    "Python-3.13.0-amd64.exe": (0, "."),
    "large_dataset.zip": (1, "."),
    "Figma-Setup.exe": (400, "_Archive/Installers"),
    "IMG_20260901_101500.jpg": (50, "Media/Photos/{y}-{m}"),
    "WhatsApp Image 2026-10-01 at 10.00.00.jpeg": (20, "Media/Photos/{y}-{m}"),
    "Logo 02.png": (60, "Media/Images/{y}-{m}"),
    "image.png": (1, "Media/Images/{y}-{m}"),
    "Screenshot 2026-10-29 093455.png": (0, "Media/Screenshots/{y}-{m}"),
    "bracket_v2.step": (10, "Resources/CAD"),
    "part.SLDPRT": (10, "Resources/CAD"),
    "housing.stl": (10, "Resources/3D Models"),
    "pump.slx": (10, "Resources/Engineering"),
    "Bahasa-Inggris-BS-KLS-VIII-nsn.pdf": (100, "Resources/School/{y}-{m}"),
    "Clean Code.epub": (100, "Resources/Books"),
    "Untitled.ipynb": (1, "Resources/Code"),
    "export.json": (3, "Resources/Data"),
    "notes.md": (3, "Documents/Notes/{y}-{m}"),
    "meeting.ics": (1, "Documents/Calendar & Contacts"),
    "film.srt": (1, "Media/Videos/{y}-{m}"),
    "Termodinamika - Bab 3.pptx": (10, "Documents/Presentations/{y}-{m}"),
}
FOLDERS = {
    "Prototipe demo · portal murid-html": "Projects/_Prototypes",
    "Demografi Ciamis 2025": ".",
    "Laporan Demo Day": ".",
    "node-v22-win-x64": "_Archive/Tools",
    "ffmpeg-7.0-win64": "_Archive/Tools",
    "TGC-11-Design-System": "Resources/Design Systems",
    "Matchly": ".",                  # "Known projects" is disabled by default
    "files(2)": "_Inbox/_Review/Folders",
    "WORK": ".",
    "Some Random Folder": ".",
}


def test_default_rules_route_real_world_names(tmp_path):
    now = time.time()
    for name, (age, _) in FILES.items():
        p = tmp_path / name
        p.write_text("x")
        os.utime(p, (now - age * DAY,) * 2)
    for name in FOLDERS:
        (tmp_path / name).mkdir()
        (tmp_path / name / "f.txt").write_text("x")
    moves = {m.src.name: m for m in org.build_plan(tmp_path, org.prepare_config(copy.deepcopy(RULES)))}
    wrong = []
    for name, (age, want) in FILES.items():
        d = time.localtime(now - age * DAY)
        want = want.format(y=d.tm_year, m=f"{d.tm_mon:02d}")
        got = org.rel(tmp_path, moves[name].dst.parent).replace("\\", "/") if name in moves else "."
        if got != want:
            wrong.append((name, got, want))
    for name, want in FOLDERS.items():
        got = org.rel(tmp_path, moves[name].dst.parent).replace("\\", "/") if name in moves else "."
        if got != want:
            wrong.append((name, got, want))
    assert not wrong, wrong


# ───────── folder tanggal ({period}) ─────────

@pytest.mark.parametrize("fmt,expected", [("{year}", "2026"), ("{year}-{month}", "2026-03"), ("{year}/{month}", "2026/03"),
                                          ("{year}/{year}-{month}", "2026/2026-03")])
def test_period_follows_date_format(tmp_path, fmt, expected):
    p = tmp_path / "a.pdf"
    p.write_text("x")
    t = time.mktime((2026, 3, 15, 12, 0, 0, 0, 0, -1))
    os.utime(p, (t, t))
    c = {"date_format": fmt, "rules": [{"name": "docs", "category": "pdf", "dest": "Documents/{period}"}]}
    moves = org.build_plan(tmp_path, org.prepare_config(c))
    assert org.rel(tmp_path, moves[0].dst.parent).replace("\\", "/") == f"Documents/{expected}"


@pytest.mark.parametrize("fmt", ["{yaer}", "{ext}", "../{year}", "plain"])
def test_bad_date_format_rejected(fmt):
    with pytest.raises(org.ConfigError):
        org.prepare_config({"date_format": fmt, "rules": []})


def test_default_date_format_is_year_month():
    assert org.prepare_config({"rules": []})["date_format"] == "{year}-{month}"


# ───────── v3.9: ekstensi tambahan & file tanpa ekstensi ─────────

@pytest.mark.parametrize("name,category", [
    ("main.ts", "code"), ("app.module.cts", "code"), ("view.hbs", "code"), ("api.http", "code"),
    ("IMG_0001.RAW", "photo_raw"), ("App.csproj", "config"), ("go.sum", "config"),
    ("Dockerfile", "config"), (".gitignore", "config"), ("README", "text"), ("LICENSE", "text"),
    (".env", "keys_certs"), (".env.local", "keys_certs"), ("prod.env", "keys_certs"), ("id_ed25519", "keys_certs"),
])
def test_new_extensions_and_names(tmp_path, name, category):
    (tmp_path / name).write_text("x")
    c = {"rules": [{"name": category, "category": category, "dest": "Out"}]}
    moves = org.build_plan(tmp_path, org.prepare_config(c))
    assert [m.src.name for m in moves] == [name]
