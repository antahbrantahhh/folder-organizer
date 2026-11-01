"""Konsistensi versi & file rilis (supaya .exe, installer, dan update check memakai versi yang sama)."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from version import __version__  # noqa: E402


def _parts(v):
    return [int(x) for x in v.split(".")] + [0] * (4 - len(v.split(".")))


def test_version_info_matches():
    text = (ROOT / "version_info.txt").read_text(encoding="utf-8")
    nums = [int(x) for x in re.search(r"filevers=\(([\d, ]+)\)", text).group(1).split(",")]
    assert nums == _parts(__version__)
    assert re.search(r"FileVersion', u'([\d.]+)'", text).group(1).startswith(__version__)


def test_installer_default_version_matches():
    iss = (ROOT / "installer" / "folder_organizer.iss").read_text(encoding="utf-8")
    assert re.search(r'#define AppVersion "([\d.]+)"', iss).group(1).startswith(__version__)


def test_changelog_mentions_current_version():
    assert f"## {__version__}" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def test_lock_pins_every_runtime_dependency():
    lock = {l.split("==")[0].lower() for l in (ROOT / "requirements.lock").read_text().splitlines()
            if "==" in l and not l.startswith("#")}
    req = {re.split(r"[<>=]", l)[0].strip().lower() for l in (ROOT / "requirements.txt").read_text().splitlines()
           if l.strip() and not l.startswith("#")}
    assert req <= lock
