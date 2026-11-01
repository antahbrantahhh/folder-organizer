"""Update dari GitHub Releases: cek versi, download installer, verifikasi, jalankan installer.

Keamanan: installer hanya diunduh dari host GitHub (lihat ALLOWED_HOSTS, juga setelah redirect), ukurannya harus
sama dengan yang dilaporkan API, dan SHA-256-nya harus sama dengan `digest` aset rilis yang dihitung GitHub.
Tanpa digest → tidak ada auto-install (user diarahkan ke halaman rilis). Selama .exe belum di-code-sign,
keaslian bergantung pada keamanan akun GitHub pemilik repo (aktifkan 2FA).
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = "antahbrantahhh/folder-organizer"   # ganti kalau repo GitHub-nya beda
API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
SETUP_RX = re.compile(r"^FolderOrganizer-Setup-[\d.]+\.exe$", re.I)
ALLOWED_HOSTS = {"github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"}
CHECK_INTERVAL_SECS = 24 * 3600
CHUNK = 256 * 1024


class UpdateError(Exception):
    pass


class UpdateCancelled(Exception):
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


def _request(url: str, accept: str):
    return urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "FolderOrganizer"})


def _setup_asset(assets: list):
    """Aset installer Windows yang bisa dipasang otomatis, atau None."""
    for a in assets or []:
        name = a.get("name") or ""
        digest = a.get("digest") or ""
        if SETUP_RX.match(name) and digest.lower().startswith("sha256:") and a.get("browser_download_url"):
            return {"name": name, "url": a["browser_download_url"], "size": int(a.get("size") or 0),
                    "sha256": digest.split(":", 1)[1].strip().lower()}
    return None


def latest_release(timeout: float = 8.0, opener=urllib.request.urlopen) -> dict:
    """{'version', 'url', 'notes', 'asset'} rilis terbaru. Raise UpdateError dengan alasan yang bisa dibaca user."""
    try:
        with opener(_request(API, "application/vnd.github+json"), timeout=timeout) as r:
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
            "notes": (data.get("body") or "").replace("\r\n", "\n").strip(),
            "asset": _setup_asset(data.get("assets"))}


def check(current: str, **kw) -> dict:
    info = latest_release(**kw)
    info["newer"] = is_newer(info["version"], current)
    return info


def check_due(last_check: float, now: float) -> bool:
    return not last_check or now - float(last_check) >= CHECK_INTERVAL_SECS or now < float(last_check)


def _host_ok(url: str) -> bool:
    u = urllib.parse.urlparse(url)
    return u.scheme == "https" and (u.hostname or "").lower() in ALLOWED_HOSTS


def download(asset: dict, dest_dir: Path = None, progress=None, cancel=None, timeout: float = 30.0,
             opener=urllib.request.urlopen) -> Path:
    """Download + verifikasi installer. progress(done_bytes, total_bytes). Return path file yang sudah diverifikasi.
    File setengah jadi / tidak cocok selalu dihapus."""
    if not asset or not _host_ok(asset["url"]):
        raise UpdateError("bad_source")
    dest_dir = Path(dest_dir or tempfile.gettempdir()) / "FolderOrganizer-update"
    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / asset["name"]
    part = final.with_name(final.name + ".part")
    h, done = hashlib.sha256(), 0
    try:
        with opener(_request(asset["url"], "application/octet-stream"), timeout=timeout) as r:
            if not _host_ok(r.geturl()):  # redirect ke host lain → tolak
                raise UpdateError("bad_source")
            with open(part, "wb") as f:
                while True:
                    if cancel is not None and cancel.is_set():
                        raise UpdateCancelled()
                    chunk = r.read(CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
                    h.update(chunk)
                    done += len(chunk)
                    if asset["size"] and done > asset["size"]:
                        raise UpdateError("bad_size")
                    if progress:
                        progress(done, asset["size"] or None)
        if asset["size"] and done != asset["size"]:
            raise UpdateError("bad_size")
        if h.hexdigest() != asset["sha256"]:
            raise UpdateError("bad_hash")
        final.unlink(missing_ok=True)
        part.replace(final)
        return final
    except urllib.error.HTTPError as e:
        raise UpdateError(f"HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise UpdateError("offline") from e
    finally:
        part.unlink(missing_ok=True)


def can_self_install(app_dir: Path, frozen: bool) -> bool:
    """Hanya versi hasil installer (ada uninstaller Inno Setup) yang bisa update sendiri; portable tidak."""
    return frozen and sys.platform == "win32" and (Path(app_dir) / "unins000.exe").is_file()


def installer_args(installer: Path, log_file: Path = None) -> list:
    args = [str(installer), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/RELAUNCH=1"]
    if log_file:
        args.append(f"/LOG={log_file}")
    return args


def launch_installer(installer: Path, log_file: Path = None):
    """Jalankan installer terpisah dari proses app (app harus keluar sesudahnya supaya file bisa diganti)."""
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    subprocess.Popen(installer_args(installer, log_file), close_fds=True, creationflags=flags,
                     cwd=str(Path(installer).parent), env=os.environ.copy())
