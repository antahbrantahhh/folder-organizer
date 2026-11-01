"""Cek update: parsing versi & penanganan error jaringan (tanpa akses internet)."""
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import updates  # noqa: E402


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_for(payload):
    def opener(req, timeout):
        if isinstance(payload, Exception):
            raise payload
        return FakeResp(json.dumps(payload).encode())
    return opener


@pytest.mark.parametrize("latest,current,newer", [
    ("v3.10.0", "3.9", True), ("3.10", "3.10.0", False), ("v3.9.1", "3.10", False), ("4.0", "3.10", True)])
def test_is_newer(latest, current, newer):
    assert updates.is_newer(latest, current) is newer


def test_check_reports_newer_release():
    info = updates.check("3.9", opener=opener_for({"tag_name": "v3.10.0", "html_url": "https://x/r", "body": "notes"}))
    assert info["newer"] and info["version"] == "3.10.0" and info["url"] == "https://x/r"


@pytest.mark.parametrize("exc,reason", [
    (urllib.error.HTTPError("u", 404, "nf", {}, None), "no_release"),
    (urllib.error.URLError("dns"), "offline"),
    (TimeoutError(), "offline"),
])
def test_network_errors_are_friendly(exc, reason):
    with pytest.raises(updates.UpdateError) as e:
        updates.check("3.9", opener=opener_for(exc))
    assert str(e.value) == reason


def test_bad_payload():
    with pytest.raises(updates.UpdateError):
        updates.check("3.9", opener=opener_for({"tag_name": "latest"}))


# ───────── v3.12: download, verifikasi, install ─────────
import hashlib  # noqa: E402
import threading  # noqa: E402

PAYLOAD = b"MZ" + b"installer-bytes" * 1000
GOOD = {"name": "FolderOrganizer-Setup-3.12.0.exe",
        "url": "https://github.com/antahbrantahhh/folder-organizer/releases/download/v3.12.0/FolderOrganizer-Setup-3.12.0.exe",
        "size": len(PAYLOAD), "sha256": hashlib.sha256(PAYLOAD).hexdigest()}


class DlResp(io.BytesIO):
    def __init__(self, data, final_url):
        super().__init__(data)
        self._url = final_url

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def dl_opener(data=PAYLOAD, final="https://release-assets.githubusercontent.com/x"):
    return lambda req, timeout: DlResp(data, final)


def test_setup_asset_needs_sha256_digest():
    base = {"name": GOOD["name"], "browser_download_url": GOOD["url"], "size": GOOD["size"]}
    assert updates._setup_asset([base]) is None
    a = updates._setup_asset([{"name": "x.zip", "digest": "sha256:aa"}, {**base, "digest": "sha256:" + "AB" * 32}])
    assert a["name"] == GOOD["name"] and a["sha256"] == "ab" * 32


def test_download_verifies_and_returns_file(tmp_path):
    seen = []
    p = updates.download(GOOD, tmp_path, progress=lambda d, t: seen.append(d), opener=dl_opener())
    assert p.read_bytes() == PAYLOAD and seen[-1] == len(PAYLOAD)
    assert not list(p.parent.glob("*.part"))


@pytest.mark.parametrize("data,final,reason", [
    (PAYLOAD[:-1] + b"X", "https://release-assets.githubusercontent.com/x", "bad_hash"),
    (PAYLOAD + b"extra", "https://release-assets.githubusercontent.com/x", "bad_size"),
    (PAYLOAD[:100], "https://release-assets.githubusercontent.com/x", "bad_size"),
    (PAYLOAD, "https://evil.example.com/x", "bad_source"),
    (PAYLOAD, "http://github.com/x", "bad_source"),
])
def test_download_rejects_bad_files_and_leaves_nothing(tmp_path, data, final, reason):
    with pytest.raises(updates.UpdateError) as e:
        updates.download(GOOD, tmp_path, opener=dl_opener(data, final))
    assert str(e.value) == reason
    assert not [f for f in (tmp_path / "FolderOrganizer-update").iterdir()]


def test_download_refuses_non_github_url_before_connecting(tmp_path):
    called = []
    with pytest.raises(updates.UpdateError):
        updates.download({**GOOD, "url": "https://evil.example.com/setup.exe"}, tmp_path,
                         opener=lambda *a, **k: called.append(a))
    assert not called


def test_download_cancel_removes_partial_file(tmp_path):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(updates.UpdateCancelled):
        updates.download(GOOD, tmp_path, cancel=cancel, opener=dl_opener())
    assert not list((tmp_path / "FolderOrganizer-update").iterdir())


def test_only_installed_frozen_windows_build_self_updates(tmp_path, monkeypatch):
    (tmp_path / "unins000.exe").write_text("x")
    monkeypatch.setattr(updates.sys, "platform", "win32")
    assert updates.can_self_install(tmp_path, True)
    assert not updates.can_self_install(tmp_path, False)                 # dari source
    assert not updates.can_self_install(tmp_path / "portable", True)     # portable: tidak ada uninstaller


def test_installer_runs_silently_and_relaunches(tmp_path):
    args = updates.installer_args(tmp_path / "setup.exe", tmp_path / "log.txt")
    assert {"/SILENT", "/RELAUNCH=1", "/CLOSEAPPLICATIONS"} <= set(args) and args[-1].startswith("/LOG=")


def test_check_due_once_a_day():
    now = 1_800_000_000
    assert updates.check_due(0, now) and updates.check_due(now - 90000, now)
    assert not updates.check_due(now - 3600, now)
    assert updates.check_due(now + 3600, now)  # jam komputer mundur
