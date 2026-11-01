"""Cek versi terbaru di GitHub Releases (tanpa auto-install: user mengunduh sendiri dari halaman rilis)."""
import json
import re
import urllib.error
import urllib.request

REPO = "antahbrantahhh/folder-organizer"   # ganti kalau repo GitHub-nya beda
API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"


class UpdateError(Exception):
    pass


def parse_version(v: str) -> tuple:
    nums = re.findall(r"\d+", str(v))
    if not nums:
        raise ValueError(f"not a version: {v!r}")
    return tuple(int(n) for n in nums[:4])


def is_newer(latest: str, current: str) -> bool:
    a, b = parse_version(latest), parse_version(current)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def latest_release(timeout: float = 8.0, opener=urllib.request.urlopen) -> dict:
    """{'version', 'url', 'notes'} rilis terbaru. Raise UpdateError dengan alasan yang bisa dibaca user."""
    req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "FolderOrganizer"})
    try:
        with opener(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise UpdateError("no_release" if e.code == 404 else f"HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise UpdateError("offline") from e
    except ValueError as e:
        raise UpdateError("bad_response") from e
    tag = data.get("tag_name") or data.get("name") or ""
    try:
        parse_version(tag)
    except ValueError as e:
        raise UpdateError("bad_response") from e
    return {"version": tag.lstrip("vV"), "url": data.get("html_url") or RELEASES_PAGE,
            "notes": (data.get("body") or "").strip()}


def check(current: str, **kw) -> dict:
    info = latest_release(**kw)
    info["newer"] = is_newer(info["version"], current)
    return info
