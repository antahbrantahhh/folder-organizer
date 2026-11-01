"""Test penyimpanan rules.yaml yang mempertahankan komentar."""
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import organizer as org  # noqa: E402
import rules_io  # noqa: E402

SRC = (ROOT / "rules.yaml").read_text(encoding="utf-8")


def comments(text):
    return [line.strip() for line in text.splitlines() if line.strip().startswith("#")]


def test_unchanged_document_is_byte_identical():
    doc = rules_io.RulesDocument(SRC)
    assert doc.render(doc.plain()) == SRC


def test_edit_keeps_every_comment():
    doc = rules_io.RulesDocument(SRC)
    d = doc.plain()
    d["rules"][0]["name_regex"] = "invoice|faktur|nota|kuitansi"
    d["recursive"] = True
    out = doc.render(d)
    assert comments(out) == comments(SRC)
    assert yaml.safe_load(out)["rules"][0]["name_regex"] == "invoice|faktur|nota|kuitansi"
    assert yaml.safe_load(out)["recursive"] is True


def test_add_delete_reorder_rules_keeps_comments_and_validates():
    doc = rules_io.RulesDocument(SRC)
    d = doc.plain()
    d["rules"].insert(0, {"name": "Big PDF", "ext": ["pdf"], "min_size_mb": 50, "dest": "_Archive/Big/{year}"})
    del d["rules"][3]
    d["rules"][4], d["rules"][5] = d["rules"][5], d["rules"][4]
    out = doc.render(d)
    assert comments(out) == comments(SRC)
    reloaded = yaml.safe_load(out)
    assert [r["name"] for r in reloaded["rules"]] == [r["name"] for r in d["rules"]]
    assert "ext: [pdf]" in out  # list baru ditulis gaya flow seperti sisanya
    org.prepare_config(reloaded)


def test_remove_optional_key_and_folder_info_edit():
    doc = rules_io.RulesDocument(SRC)
    d = doc.plain()
    first_key = next(iter(d["folder_info"]))
    d["folder_info"][first_key] = "Updated description"
    d["folder_info"]["Projects/Matchly"] = "Table tennis app"
    out = yaml.safe_load(doc.render(d))
    assert out["folder_info"][first_key] == "Updated description"
    assert out["folder_info"]["Projects/Matchly"] == "Table tennis app"


def test_save_is_atomic_and_backs_up(tmp_path):
    p = tmp_path / "rules.yaml"
    p.write_text(SRC, encoding="utf-8")
    doc = rules_io.RulesDocument.load(p)
    d = doc.plain()
    d["recursive"] = True
    new_doc = doc.save(p, d)
    assert (tmp_path / "rules.yaml.bak").read_text(encoding="utf-8") == SRC
    assert not (tmp_path / "rules.yaml.tmp").exists()
    assert yaml.safe_load(p.read_text(encoding="utf-8"))["recursive"] is True
    assert new_doc.render(new_doc.plain()) == p.read_text(encoding="utf-8")


def test_fallback_without_ruamel(monkeypatch):
    monkeypatch.setattr(rules_io, "HAS_RUAMEL", False)
    doc = rules_io.RulesDocument(SRC)
    assert not doc.preserves_comments
    out = doc.render(doc.plain())
    assert yaml.safe_load(out) == yaml.safe_load(SRC)


def test_invalid_text_reports_error():
    doc = rules_io.RulesDocument("rules: [unclosed")
    with pytest.raises(yaml.YAMLError):
        doc.plain()


# ───────── v3.10: konflik edit di luar app ─────────

def test_save_detects_external_edit(tmp_path):
    p = tmp_path / "rules.yaml"
    p.write_text("rules: []\n", encoding="utf-8")
    doc = rules_io.RulesDocument.load(p)
    p.write_text("rules: []\n# diedit di Notepad\n", encoding="utf-8")
    assert doc.changed_on_disk(p)
    with pytest.raises(rules_io.RulesConflict):
        doc.save(p, {"rules": []})
    new = doc.save(p, {"rules": []}, force=True)
    assert not new.changed_on_disk(p)
    new.save(p, {"rules": [], "recursive": True})  # simpan berikutnya tanpa konflik


def test_unbound_document_never_conflicts(tmp_path):
    p = tmp_path / "rules.yaml"
    p.write_text("x: 1\n", encoding="utf-8")
    rules_io.RulesDocument("").save(p, {"rules": []})
