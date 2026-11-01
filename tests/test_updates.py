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
