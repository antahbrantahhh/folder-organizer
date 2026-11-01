#!/usr/bin/env python3
"""
Folder Organizer — rule-based file organizer (Windows-first, jalan juga di Mac/Linux).

Commands:
  scan    <folder>   Audit: tipe file, ukuran, file lama, duplikat. Tidak mengubah apa pun.
  plan    <folder>   Dry-run: tampilkan rencana pemindahan berdasarkan rules.yaml.
  apply   <folder>   Eksekusi rencana (minta konfirmasi, kecuali --yes). Semua tercatat di journal.
  dedupe  <folder>   Pindahkan file duplikat (berdasarkan isi/hash) ke _to_delete/. Dry-run kecuali --apply.
  undo    <folder>   Kembalikan batch terakhir (apply / dedupe / watch).
  watch   <folder>   Pantau folder, rapikan file baru otomatis tiap N detik.

Tidak ada yang pernah di-delete. Duplikat & sampah masuk _to_delete/ untuk direview manual.
"""
import argparse
import contextlib
import csv
import difflib
import errno
import fnmatch
import hashlib
import json
import logging
import logging.handlers
import os
import re
import string
import sys
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is not installed. Run: pip install pyyaml")

from i18n import T  # noqa: E402  (string UI dwibahasa, dipakai bersama GUI)

try:  # opsional: tanggal foto dari EXIF
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

STATE_DIR = ".organizer"   # lokasi journal lama (≤ v3.3, di dalam folder target) — masih dibaca untuk undo
TRASH_DIR = "_to_delete"
ALWAYS_EXCLUDE_DIRS = {STATE_DIR, TRASH_DIR, ".git", "node_modules", "$RECYCLE.BIN",
                       "System Volume Information", "__pycache__"}
README_NAME = "_README.txt"
ALWAYS_SKIP_FILES = {"desktop.ini", "thumbs.db", ".ds_store", README_NAME.lower()}
PARTIAL_EXT = {"crdownload", "part", "partial", "tmp", "download", "opdownload"}
EXIF_EXT = {"jpg", "jpeg", "tif", "tiff", "heic"}
WIN_HIDDEN_SYSTEM = 0x2 | 0x4  # FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM
# Bit "name surrogate" di reparse tag = link (symlink 0xA000000C, junction 0xA0000003, app alias).
# File OneDrive/cloud (tag 0x9000xxxx) TIDAK punya bit ini → tetap diproses seperti file biasa.
REPARSE_NAME_SURROGATE = 0x20000000
# File cloud yang belum ada di disk: dibaca = di-download. Jangan di-hash saat cek duplikat.
WIN_CLOUD_NOT_LOCAL = 0x400000 | 0x40000 | 0x1000  # RECALL_ON_DATA_ACCESS | RECALL_ON_OPEN | OFFLINE
SKIP_DEEP_DIRS = {"node_modules", "__pycache__", ".venv", "venv", "$RECYCLE.BIN"}
FOLDER_AGE_SCAN_CAP = 50_000  # lebih dari ini entri → folder dianggap masih aktif (aman, tidak diarsip)
# Folder milik Windows/aplikasi yang sering ada di Documents — memindahkannya bisa merusak aplikasi terkait
PROTECTED_DIRS = {n.lower() for n in (
    "Custom Office Templates", "Outlook Files", "OneNote Notebooks", "My Games", "Saved Games",
    "WindowsPowerShell", "PowerShell", "Visual Studio Code", "IISExpress", "My Web Sites", "Fax",
    "Scanned Documents", "Sound Recordings", "Zoom", "Adobe", "Default.rdp", "Desktop.ini",
)} | {"visual studio 20" + str(y) for y in range(10, 40)}

TOP_KEYS = {"recursive", "exclude", "fallback_dest", "rules", "folder_rules", "folder_fallback",
            "folder_info", "folder_info_readme", "categories", "date_format"}
FILE_RULE_KEYS = {"name", "enabled", "category", "ext", "name_regex", "older_than_days", "newer_than_days",
                  "min_size_mb", "max_size_mb", "dest"}
FOLDER_RULE_KEYS = {"name", "enabled", "name_regex", "older_than_days", "newer_than_days", "dest"}
NUMBER_KEYS = ("older_than_days", "newer_than_days", "min_size_mb", "max_size_mb")
FILE_TOKENS = {"year", "month", "day", "period", "ext", "EXT"}
FOLDER_TOKENS = {"year", "month", "day", "period"}
DATE_TOKENS = {"year", "month", "day"}
DEFAULT_DATE_FORMAT = "{year}-{month}"   # {period} → "2026-10"
MAX_PATH_WIN = 260
DATE_FORMAT_PRESETS = ["{year}", "{year}-{month}", "{year}/{month}", "{year}/{year}-{month}", "{year}-{month}-{day}"]


FROZEN = bool(getattr(sys, "frozen", False))  # True saat jalan sebagai .exe (PyInstaller)


def app_dir() -> Path:
    """Folder aplikasi yang bisa ditulis user (rules.yaml ada di sini): folder .exe, atau folder source."""
    return Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent


def resource_dir() -> Path:
    """Folder file bawaan yang read-only (assets, rules.yaml default)."""
    return Path(getattr(sys, "_MEIPASS", app_dir()))


class ConfigError(SystemExit):
    """Aturan tidak valid. Turunan SystemExit supaya CLI otomatis keluar dengan pesan; e.code = pesan."""


class Cancelled(Exception):
    """Operasi dihentikan user (tombol Cancel / Esc)."""


class AccessBlocked(Exception):
    """Windows menolak menulis ke folder target (biasanya Controlled folder access / Ransomware protection)."""

    def __init__(self, path: Path, original: Exception):
        super().__init__(T("e_access", path=path, err=original))
        self.path, self.original = path, original


def check_cancel(cancel):
    """cancel = objek dengan is_set() (mis. threading.Event) atau None."""
    if cancel is not None and cancel.is_set():
        raise Cancelled()


def is_link_or_junction(p: Path, lst=None) -> bool:
    """True hanya untuk symlink/junction/alias. File & folder OneDrive (cloud reparse point) = False."""
    try:
        lst = lst or os.lstat(p)
    except OSError:
        return True
    if os.path.islink(p):
        return True
    tag = getattr(lst, "st_reparse_tag", 0)
    if tag:
        return bool(tag & REPARSE_NAME_SURROGATE)
    isjunction = getattr(os.path, "isjunction", None)  # Python 3.12+
    return bool(isjunction and isjunction(p))


def is_protected_dir(name: str) -> bool:
    n = name.lower()
    return n in PROTECTED_DIRS or n.startswith("visual studio 20")


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA") or os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "FolderOrganizer"


def state_dir(root: Path, create: bool = True) -> Path:
    """Journal & CSV per folder target, disimpan di %APPDATA%/FolderOrganizer/state/<nama>-<hash>.
    Tidak ikut ter-sync OneDrive dan tidak hilang kalau folder target dihapus."""
    root = Path(root).resolve()
    key = hashlib.blake2b(str(root).lower().encode("utf-8"), digest_size=6).hexdigest()
    safe = re.sub(r"[^\w.-]+", "_", root.name)[:40] or "root"
    d = app_data_dir() / "state" / f"{safe}-{key}"
    if create:
        d.mkdir(parents=True, exist_ok=True)
        marker = d / "target.txt"
        if not marker.exists():
            marker.write_text(str(root), encoding="utf-8")
    return d


log = logging.getLogger("folder_organizer")
LOG_FILE_NAME = "app.log"


def log_dir() -> Path:
    return app_data_dir() / "logs"


def setup_logging(level=logging.INFO) -> Path:
    """Log berputar (3 × 1 MB) di %APPDATA%\\FolderOrganizer\\logs\\app.log. Aman dipanggil berkali-kali."""
    path = log_dir() / LOG_FILE_NAME
    if any(isinstance(h, logging.handlers.RotatingFileHandler) for h in log.handlers):
        return path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
        log.addHandler(handler)
        log.setLevel(level)
    except OSError:
        pass  # log tidak boleh membuat app gagal jalan
    return path


def _writable_dir(d: Path) -> bool:
    try:
        d.mkdir(parents=True, exist_ok=True)
        probe = d / f".write_test_{os.getpid()}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def rules_path() -> Path:
    """rules.yaml yang dipakai: di samping app kalau foldernya bisa ditulis (mode portable),
    selain itu (mis. .exe di Program Files) di %APPDATA%\\FolderOrganizer. Disalin dari bawaan kalau belum ada."""
    local = app_dir() / "rules.yaml"
    if _writable_dir(app_dir()):
        if not local.exists() and FROZEN:
            _copy_text(resource_dir() / "rules.yaml", local)
        return local
    roaming = app_data_dir() / "rules.yaml"
    if not roaming.exists():
        _copy_text(local if local.exists() else resource_dir() / "rules.yaml", roaming)
    return roaming if roaming.exists() else local


def _copy_text(src: Path, dst: Path):
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    except OSError:
        pass


class FolderBusy(Exception):
    """Proses Folder Organizer lain sedang memindahkan file di folder yang sama."""

    def __init__(self, root: Path, info: dict):
        super().__init__(T("e_folder_busy", path=root, pid=info.get("pid", "?"), purpose=info.get("purpose", "?")))
        self.root, self.info = root, info


LOCK_NAME = "folder.lock"     # dikunci OS selama proses memindahkan file; lepas otomatis kalau proses mati
LOCK_INFO = "lock.json"       # siapa yang memegang lock (PID, tujuan), hanya untuk pesan ke user


def _os_lock(fh):
    if sys.platform == "win32":
        import msvcrt
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)  # OSError kalau sudah dikunci handle lain
    else:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _os_unlock(fh):
    try:
        if sys.platform == "win32":
            import msvcrt
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


def _read_lock(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


@contextlib.contextmanager
def folder_lock(root: Path, purpose: str):
    """Lock per folder target supaya dua proses (mis. GUI + CLI watch) tidak memindahkan file bersamaan.
    Memakai lock OS pada handle yang terbuka: kalau proses crash atau ditutup paksa, OS melepasnya sendiri,
    jadi tidak ada lock basi yang perlu ditebak dari PID."""
    state = state_dir(root)
    fh = open(state / LOCK_NAME, "a+b")
    try:
        _os_lock(fh)
    except OSError:
        fh.close()
        raise FolderBusy(root, _read_lock(state / LOCK_INFO))
    info = state / LOCK_INFO
    try:
        tmp = info.with_name(info.name + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"pid": os.getpid(), "purpose": purpose, "since": time.time()}), encoding="utf-8")
        tmp.replace(info)
    except OSError:
        pass
    try:
        yield
    finally:
        info.unlink(missing_ok=True)
        _os_unlock(fh)
        fh.close()


def prune_journals(root: Path, keep_days: int = 90, keep_min: int = 20) -> int:
    """Hapus journal lebih tua dari keep_days (0 = simpan selamanya). keep_min batch terbaru selalu disimpan.
    Hanya journal di %APPDATA%; journal lama di .organizer (dalam folder user) tidak disentuh."""
    if not keep_days:
        return 0
    state = state_dir(root, create=False)
    journals = [j for j in list_journals(root) if j.parent == state]
    protected = set(journals[-keep_min:]) if keep_min else set()
    cutoff = time.time() - keep_days * 86400
    removed = 0
    for j in journals:
        if j in protected:
            continue
        t = journal_time(j)
        if (t.timestamp() if t else j.stat().st_mtime) < cutoff:
            try:
                j.unlink()
                removed += 1
            except OSError:
                pass
    if removed:
        log.info("pruned %d journals older than %d days in %s", removed, keep_days, root)
    return removed


def unsafe_target(root: Path):
    """Alasan folder ini tidak boleh dirapikan (folder sistem/aplikasi/root profil), atau None."""
    r = Path(root).resolve()
    if r == Path(r.anchor):
        return T("e_unsafe_drive_root")
    temp = Path(tempfile.gettempdir()).resolve()  # %LOCALAPPDATA%\Temp: bukan data aplikasi, boleh
    in_temp = r == temp or temp in r.parents
    for key in ("SystemRoot", "windir", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "ProgramData",
                "APPDATA", "LOCALAPPDATA"):
        d = os.environ.get(key)
        if not d:
            continue
        d = Path(d).resolve()
        if (r == d or d in r.parents) and not (in_temp and key in ("APPDATA", "LOCALAPPDATA")):
            return T("e_unsafe_system", path=d)
    exact = [os.environ.get("USERPROFILE"), str(Path.home())]
    if any(e and r == Path(e).resolve() for e in exact):
        return T("e_unsafe_profile")
    if any(e and r == Path(e).resolve().parent for e in exact):  # C:\Users (semua profil)
        return T("e_unsafe_system", path=r)
    return None


def check_target(root: Path):
    reason = unsafe_target(root)
    if reason:
        raise ConfigError(T("e_unsafe_target", path=root, reason=reason))


def ensure_writable(root: Path):
    """Deteksi dini Controlled folder access: coba buat & hapus file kecil di folder target."""
    probe = root / f".organizer_write_test_{os.getpid()}"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except (FileNotFoundError, PermissionError) as e:
        if root.is_dir():
            raise AccessBlocked(root, e)
        raise


# ───────────────────────── utils ─────────────────────────

def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def ext_of(p: Path) -> str:
    return p.suffix.lower().lstrip(".")


def rel(root: Path, p: Path) -> str:
    try:
        return str(p.relative_to(root))
    except ValueError:
        return str(p)


def is_hidden_system(st) -> bool:
    attrs = getattr(st, "st_file_attributes", 0)
    return bool(attrs & WIN_HIDDEN_SYSTEM)


def file_date(p: Path, st) -> datetime:
    # foto OneDrive yang belum ada di disk: dibuka = di-download → pakai tanggal file saja
    cloud_only = getattr(st, "st_file_attributes", 0) & WIN_CLOUD_NOT_LOCAL
    if HAS_PIL and ext_of(p) in EXIF_EXT and not cloud_only:
        try:
            with Image.open(p) as img:
                raw = img.getexif().get(36867) or img.getexif().get(306)  # DateTimeOriginal / DateTime
                if raw:
                    return datetime.strptime(str(raw)[:19], "%Y:%m:%d %H:%M:%S")
        except Exception:
            pass
    return datetime.fromtimestamp(st.st_mtime)


# ───────────────────────── config ─────────────────────────

_LIBRARY_CACHE = {}


def builtin_categories() -> dict:
    """Library kategori bawaan (categories.yaml): {nama: {"group", "en", "id", "ext": [..]}}."""
    path = resource_dir() / "categories.yaml"
    key = (str(path), path.stat().st_mtime if path.exists() else 0)
    if key not in _LIBRARY_CACHE:
        data = {}
        if path.exists():
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        _LIBRARY_CACHE.clear()
        _LIBRARY_CACHE[key] = {str(k): v for k, v in data.items()}
    return _LIBRARY_CACHE[key]


def _norm_ext(e) -> str:
    return str(e).strip().lower().lstrip(".")


def build_category_library(custom=None) -> dict:
    """Gabungkan library bawaan dengan `categories:` di rules.yaml.
    custom: {nama: [ext, ...]}                    → tambah ke kategori bawaan / buat kategori baru
            {nama: {ext: [...], replace: true}}   → ganti total ekstensi kategori itu
            {nama: {ext: [...], en: .., id: ..}}  → kategori baru dengan label"""
    lib = {n: {"group": c.get("group", ""), "en": c.get("en", n), "id": c.get("id", c.get("en", n)),
               "ext": [_norm_ext(e) for e in c.get("ext", [])],
               "names": [str(x).strip().lower() for x in c.get("names", [])], "custom": False}
           for n, c in builtin_categories().items()}
    if custom in (None, {}):
        return lib
    if not isinstance(custom, dict):
        raise ConfigError(T("e_categories_mapping"))
    for name, val in custom.items():
        name = str(name)
        if isinstance(val, list):
            exts, replace, meta = val, False, {}
        elif isinstance(val, dict) and isinstance(val.get("ext", []), list):
            exts, replace, meta = val.get("ext", []), bool(val.get("replace", False)), val
        else:
            raise ConfigError(T("e_custom_category", name=name))
        cur = lib.get(name, {"group": "custom", "en": name, "id": name, "ext": [], "names": []})
        merged = [_norm_ext(e) for e in exts] if replace else cur["ext"] + [_norm_ext(e) for e in exts]
        new_names = [str(x).strip().lower() for x in (meta.get("names") or [])]
        names = new_names if replace else cur.get("names", []) + new_names
        lib[name] = {"group": meta.get("group", cur["group"]), "en": meta.get("en", cur["en"]),
                     "id": meta.get("id", meta.get("en", cur["id"])), "ext": list(dict.fromkeys(merged)),
                     "names": list(dict.fromkeys(names)), "custom": True}
    return lib


def category_names(value) -> list:
    if value in (None, "", []):
        return []
    return [value] if isinstance(value, str) else list(value)


def load_config(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(T("e_rules_missing", path=path))
    with open(path, encoding="utf-8") as f:
        try:
            cfg = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ConfigError(T("e_yaml_invalid", err=e))
    return prepare_config(cfg)


def _check_keys(obj: dict, allowed: set, where: str):
    for k in obj:
        if str(k).startswith("_") or k in allowed:
            continue  # key berawalan _ = hasil kompilasi internal
        hint = difflib.get_close_matches(str(k), sorted(allowed), n=1, cutoff=0.6)
        raise ConfigError(T("e_unknown_key", where=where, key=k)
                          + (T("e_did_you_mean", hint=hint[0]) if hint else T("e_valid_keys", keys=", ".join(sorted(allowed)))))


def dest_error(template, is_folder: bool = False):
    """Return pesan error untuk template folder tujuan, atau None kalau valid."""
    if not isinstance(template, str) or not template.strip():
        return T("e_dest_required")
    tokens = FOLDER_TOKENS if is_folder else FILE_TOKENS
    try:
        fields = [f for _, f, _, _ in string.Formatter().parse(template) if f is not None]
    except ValueError as e:
        return T("e_dest_format", err=e)
    for f in fields:
        if f not in tokens:
            avail = ", ".join("{" + t + "}" for t in sorted(tokens, key=str.lower))
            return T("e_dest_placeholder", token="{" + f + "}", avail=avail)
    norm = template.strip().replace("\\", "/")
    if norm.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", norm):
        return T("e_dest_absolute", dest=template)
    if any(seg.strip() == ".." for seg in norm.split("/")):
        return T("e_dest_parent")
    return None


def date_format_error(fmt):
    """Error untuk format folder tanggal ({period}), atau None. Hanya {year} {month} {day}, boleh pakai '/'."""
    if not isinstance(fmt, str) or not fmt.strip():
        return T("e_date_format")
    try:
        fields = [f for _, f, _, _ in string.Formatter().parse(fmt) if f is not None]
    except ValueError as e:
        return T("e_dest_format", err=e)
    if not fields or any(f not in DATE_TOKENS for f in fields):
        return T("e_date_format")
    norm = fmt.replace("\\", "/")
    if norm.startswith(("/", "~")) or ".." in norm.split("/") or re.match(r"^[A-Za-z]:", norm):
        return T("e_dest_parent")
    return None


def _rule_where(r, kind: str, i: int) -> str:
    where = T("e_where_file_rule" if kind == "rules" else "e_where_folder_rule", n=i + 1)
    if not isinstance(r, dict):
        raise ConfigError(T("e_must_be_mapping", where=where))
    return where + f" ('{r.get('name', '?')}')"


def _check_numbers(r: dict, where: str):
    for k in NUMBER_KEYS:
        v = r.get(k)
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0):
            raise ConfigError(T("e_number", where=where, key=k, value=repr(v)))


def _check_ext(r: dict, where: str):
    if r.get("ext") is None:
        return
    if isinstance(r["ext"], str):
        r["ext"] = [e for e in re.split(r"[,\s]+", r["ext"]) if e]
    if not isinstance(r["ext"], list) or not all(isinstance(e, (str, int)) for e in r["ext"]):
        raise ConfigError(T("e_ext_list", where=where))


def _check_categories(r: dict, where: str, library: dict):
    cats = r.get("category")
    if cats is None:
        return
    if not (isinstance(cats, str) or (isinstance(cats, list) and all(isinstance(c, str) for c in cats))):
        raise ConfigError(T("e_category_type", where=where))
    for c in category_names(cats):
        if c not in library:
            hint = difflib.get_close_matches(c, sorted(library), n=1, cutoff=0.5)
            raise ConfigError(T("e_unknown_category", where=where, name=c)
                              + (T("e_did_you_mean", hint=hint[0]) if hint else ""))


def _validate_rule(r, kind: str, i: int, library: dict):
    where = _rule_where(r, kind, i)
    _check_keys(r, FILE_RULE_KEYS if kind == "rules" else FOLDER_RULE_KEYS, where)
    err = dest_error(r.get("dest"), is_folder=(kind == "folder_rules"))
    if err:
        raise ConfigError(T("e_dest_invalid", where=where, err=err))
    _check_numbers(r, where)
    _check_ext(r, where)
    if r.get("name_regex") is not None and not isinstance(r["name_regex"], str):
        raise ConfigError(T("e_regex_text", where=where))
    if r.get("enabled") is not None and not isinstance(r["enabled"], bool):
        raise ConfigError(T("e_enabled_bool", where=where))
    _check_categories(r, where, library)


def _prepare_top(cfg: dict):
    """Default & tipe untuk key level atas."""
    _check_keys(cfg, TOP_KEYS, "rules.yaml")
    for key, default in (("recursive", False), ("exclude", []), ("fallback_dest", None), ("rules", []),
                         ("folder_rules", []), ("folder_fallback", None)):
        cfg.setdefault(key, default)
    for k in ("exclude", "rules", "folder_rules"):
        cfg[k] = cfg[k] or []
    for k in ("rules", "folder_rules"):
        if not isinstance(cfg[k], list):
            raise ConfigError(T("e_must_be_list", key=k))
    if not isinstance(cfg["exclude"], list) or not all(isinstance(x, str) for x in cfg["exclude"]):
        raise ConfigError(T("e_exclude_list"))
    if not isinstance(cfg["recursive"], bool):
        raise ConfigError(T("e_recursive_bool"))
    cfg["date_format"] = cfg.get("date_format") or DEFAULT_DATE_FORMAT
    err = date_format_error(cfg["date_format"])
    if err:
        raise ConfigError(T("e_key_err", key="date_format", err=err))


def _prepare_fallbacks(cfg: dict):
    for key, is_folder in (("fallback_dest", False), ("folder_fallback", True)):
        if cfg[key] in ("", None):
            cfg[key] = None
            continue
        err = dest_error(cfg[key], is_folder)
        if err:
            raise ConfigError(T("e_key_err", key=key, err=err))


def _compile_rule(r: dict, kind: str, i: int, library: dict):
    """Isi field internal (_ext, _names, _re) dari ext, category, dan name_regex."""
    r.setdefault("name", f"{kind}_{i + 1}")
    for k in NUMBER_KEYS:
        if k in r and r[k] is None:
            del r[k]
    for k in ("_ext", "_re", "_names"):
        r.pop(k, None)
    exts = {_norm_ext(e) for e in (r.get("ext") or [])}
    names = set()
    for c in category_names(r.get("category")):
        exts |= set(library[c]["ext"])
        names |= set(library[c].get("names", []))
    if exts or names:  # tanpa ext & kategori = semua tipe file
        r["_ext"] = exts
        if names:
            r["_names"] = names
    if r.get("name_regex"):
        try:
            r["_re"] = re.compile(r["name_regex"], re.IGNORECASE)
        except re.error as e:
            raise ConfigError(T("e_regex_invalid", name=r["name"], err=e))


def label_path_error(rel_path) -> str:
    """Path label harus relatif dan di dalam folder target."""
    s = str(rel_path).replace("\\", "/").strip()
    if not s:
        return T("e_label_path_empty")
    if s.startswith("/") or re.match(r"^[a-zA-Z]:", s) or ".." in s.split("/"):
        return T("e_label_path_outside", path=s)
    return None


def _check_folder_info(info):
    if info in (None, {}):
        return
    if not isinstance(info, dict):
        raise ConfigError(T("e_must_be_mapping", key="folder_info"))
    for k in info:
        err = label_path_error(k)
        if err:
            raise ConfigError(f"folder_info: {err}")


def prepare_config(cfg: dict) -> dict:
    """Validasi + kompilasi dict rules (dari file atau dari editor GUI). Mengubah dict in-place.
    Raise ConfigError dengan pesan yang bisa ditampilkan ke user."""
    if not isinstance(cfg, dict):
        raise ConfigError(T("e_root_mapping"))
    _prepare_top(cfg)
    _prepare_fallbacks(cfg)
    library = build_category_library(cfg.get("categories"))
    cfg["_categories"] = library
    for kind in ("rules", "folder_rules"):
        for i, r in enumerate(cfg[kind]):
            _validate_rule(r, kind, i, library)
            _compile_rule(r, kind, i, library)
    # Folder level-atas yang dikelola organizer sendiri (Documents, Media, _Archive, …) → tidak ikut dipindah
    dests = [r["dest"] for r in cfg["rules"] + cfg["folder_rules"]]
    dests += [d for d in (cfg["fallback_dest"], cfg["folder_fallback"]) if d]
    cfg["_managed_roots"] = {re.split(r"[\\/]", d.strip().strip("\\/"))[0].lower() for d in dests}
    # Tujuan aturan folder (bagian statis, mis. "_archive/folders"): isinya folder utuh yang sudah dipindah,
    # jangan dibongkar lagi oleh mode recursive.
    fdests = [r["dest"] for r in cfg["folder_rules"] if r.get("enabled") is not False]
    fdests += [cfg["folder_fallback"]] if cfg["folder_fallback"] else []
    cfg["_folder_dest_roots"] = {d.split("{")[0].replace("\\", "/").strip().strip("/").lower() for d in fdests} - {"", "."}
    _check_folder_info(cfg.get("folder_info"))
    # Umur folder dihitung dari aktivitas terakhir di dalamnya, hanya kalau memang dipakai
    cfg["_folder_deep_age"] = any(
        ("older_than_days" in r or "newer_than_days" in r or "{" in r["dest"]) for r in cfg["folder_rules"]
    ) or "{" in (cfg["folder_fallback"] or "")
    return cfg


def rule_matches(r: dict, p: Path, st, now: float) -> bool:
    if r.get("enabled") is False:
        return False
    if "_ext" in r and ext_of(p) not in r["_ext"] and p.name.lower() not in r.get("_names", ()):
        return False
    if "_re" in r and not r["_re"].search(p.name):
        return False
    age_days = (now - st.st_mtime) / 86400
    if "older_than_days" in r and age_days < r["older_than_days"]:
        return False
    if "newer_than_days" in r and age_days > r["newer_than_days"]:
        return False
    size_mb = st.st_size / 1048576
    if "min_size_mb" in r and size_mb < r["min_size_mb"]:
        return False
    if "max_size_mb" in r and size_mb > r["max_size_mb"]:
        return False
    return True


def render_period(d: datetime, date_format: str = None) -> str:
    return (date_format or DEFAULT_DATE_FORMAT).format(year=d.year, month=f"{d.month:02d}", day=f"{d.day:02d}")


def render_dest(template: str, p: Path, st, is_dir: bool = False, date_format: str = None) -> str:
    """{period} mengikuti date_format global (default "{year}-{month}"). Tanggal = EXIF untuk foto, selain itu
    tanggal file terakhir diubah (untuk folder: aktivitas terakhir di dalamnya)."""
    d = datetime.fromtimestamp(st.st_mtime) if is_dir else file_date(p, st)
    e = "" if is_dir else (ext_of(p) or "noext")
    return template.format(year=d.year, month=f"{d.month:02d}", day=f"{d.day:02d}",
                           period=render_period(d, date_format), ext=e, EXT=e.upper())


# ───────────────────────── scanning ─────────────────────────

def _keep_subdir(root: Path, dp: Path, d: str, exclude: list, tool_dir: Path, skip_rel=()) -> bool:
    """Apakah subfolder d ikut di-scan (mode recursive)."""
    r = rel(root, dp / d).replace("\\", "/")
    if r.lower() in skip_rel:
        return False  # tujuan aturan folder: berisi folder utuh yang sudah dirapikan
    if (dp / d).resolve() == tool_dir:
        return False  # jangan sentuh folder organizer sendiri
    if d in ALWAYS_EXCLUDE_DIRS or any(fnmatch.fnmatch(r, pat) or fnmatch.fnmatch(d, pat) for pat in exclude):
        return False
    return not (is_protected_dir(d) or is_link_or_junction(dp / d))


def _file_entry(root: Path, p: Path, exclude: list, stable_secs: int, now: float, siblings=frozenset()):
    """stat file kalau file ini boleh diproses, selain itu None."""
    if p.name.lower() in ALWAYS_SKIP_FILES or ext_of(p) in PARTIAL_EXT:
        return None
    if any(f"{p.name.lower()}.{e}" in siblings for e in PARTIAL_EXT):
        return None  # placeholder download yang belum selesai (mis. Firefox: x.pdf + x.pdf.part)
    r = rel(root, p).replace("\\", "/")
    if any(fnmatch.fnmatch(r, pat) for pat in exclude):
        return None
    try:
        lst = os.lstat(p)
        if is_link_or_junction(p, lst):
            return None  # symlink: lewati (file OneDrive tetap diproses)
        st = p.stat()
    except OSError:
        return None
    if is_hidden_system(lst) or is_hidden_system(st):
        return None
    if stable_secs and (now - st.st_mtime < stable_secs or st.st_size == 0):
        return None  # file masih ditulis / baru di-download / placeholder kosong (mode watch)
    return st


def iter_files(root: Path, recursive: bool, exclude: list, stable_secs: int = 0, cancel=None, progress=None,
               skip_rel=()):
    """Yield (Path, stat). Skip folder sistem, file hidden/system, download yang belum selesai.
    progress(n, None) dipanggil berkala dengan jumlah file yang sudah ditemukan."""
    now, found, tool_dir = time.time(), 0, app_dir()
    for dirpath, dirnames, filenames in os.walk(root):
        dp = Path(dirpath)
        if not recursive and dp != root:
            dirnames[:] = []
            continue
        dirnames[:] = ([d for d in dirnames if _keep_subdir(root, dp, d, exclude, tool_dir, skip_rel)]
                       if recursive else [])
        check_cancel(cancel)
        siblings = {f.lower() for f in filenames}
        for fn in filenames:
            p = dp / fn
            st = _file_entry(root, p, exclude, stable_secs, now, siblings)
            if st is None:
                continue
            found += 1
            if found % 250 == 0:
                check_cancel(cancel)
                if progress:
                    progress(found, None)
            yield p, st


# ───────────────────────── planning ─────────────────────────

@dataclass
class Move:
    src: Path
    dst: Path
    reason: str


def unique_dest(dst: Path, taken: set, is_dir: bool = False) -> Path:
    cand, n = dst, 2
    while cand.exists() or str(cand).lower() in taken:
        name = f"{dst.name} ({n})" if is_dir else f"{dst.stem} ({n}){dst.suffix}"
        cand = dst.with_name(name)
        n += 1
    taken.add(str(cand).lower())
    return cand


class FolderStat:
    """Stat ringkas untuk folder; st_mtime = aktivitas terakhir di dalam folder (rekursif)."""
    __slots__ = ("st_mtime", "st_size", "st_file_attributes")

    def __init__(self, mtime, attrs=0):
        self.st_mtime, self.st_size, self.st_file_attributes = mtime, 0, attrs


def folder_last_activity(p: Path, own_mtime: float, cap: int = None, cancel=None) -> float:
    """Waktu modifikasi terbaru dari folder & seluruh isinya. Di Windows, mtime folder hanya berubah kalau
    isi level langsungnya berubah, jadi project yang diedit di subfolder bisa terlihat 'lama' tanpa ini."""
    cap = cap or FOLDER_AGE_SCAN_CAP
    latest, seen, stack = own_mtime, 0, [str(p)]
    while stack:
        try:
            it = os.scandir(stack.pop())
        except OSError:
            continue
        with it:
            for e in it:
                seen += 1
                if seen % 500 == 0:
                    check_cancel(cancel)
                if seen > cap:
                    return time.time()  # folder sangat besar → anggap masih aktif
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                if st.st_mtime > latest:
                    latest = st.st_mtime
                if (e.is_dir(follow_symlinks=False) and e.name not in SKIP_DEEP_DIRS
                        and not is_link_or_junction(Path(e.path), st)):
                    stack.append(e.path)
    return latest


def iter_top_folders(root: Path, cfg: dict, cancel=None):
    """Folder level-atas yang boleh dipindah oleh folder_rules."""
    tool_dir = app_dir()
    for entry in os.scandir(root):
        if not entry.is_dir(follow_symlinks=False):
            continue
        name = entry.name
        if (name.startswith(".") or name in ALWAYS_EXCLUDE_DIRS
                or name.lower() in cfg["_managed_roots"]
                or any(fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(name + "/", pat.split("**")[0])
                       for pat in cfg["exclude"])):
            continue
        if is_protected_dir(name):
            continue
        p = Path(entry.path)
        try:
            lst = entry.stat(follow_symlinks=False)
        except OSError:
            continue
        # junction/symlink (mis. "My Music", "My Pictures" di Documents) atau folder hidden/system → jangan disentuh
        if is_link_or_junction(p, lst) or is_hidden_system(lst):
            continue
        if p.resolve() == tool_dir:
            continue  # jangan pindahkan folder organizer-nya sendiri
        check_cancel(cancel)
        mtime = folder_last_activity(p, lst.st_mtime, cancel=cancel) if cfg.get("_folder_deep_age") else lst.st_mtime
        yield p, FolderStat(mtime, getattr(lst, "st_file_attributes", 0))


def _inside(root: Path, target: Path) -> bool:
    return target == root or root in target.parents


def _resolve_dest(root: Path, dest_dir: str, rule_name: str) -> Path:
    root = root.resolve()
    target = (root / dest_dir).resolve()
    if not _inside(root, target):  # lapisan kedua, mis. tujuan lewat symlink yang mengarah keluar
        raise ConfigError(T("e_dest_escape", name=rule_name, path=target))
    return target


_DATE_RX = {"year": r"\d{4}", "month": r"\d{2}", "day": r"\d{2}"}


def dest_pattern(template: str, date_format: str):
    """Regex untuk path relatif hasil sebuah template tujuan, mis. 'Documents/Notes/{period}' →
    'documents/notes/\\d{4}-\\d{2}'. Dipakai untuk mengenali file yang SUDAH berada di pola tujuannya."""
    if "{" not in template:
        return None
    parts = []
    for literal, field, _, _ in string.Formatter().parse(template.replace("\\", "/").strip().strip("/")):
        parts.append(re.escape(literal.lower()))
        if field == "period":
            for lit2, f2, _, _ in string.Formatter().parse(date_format or DEFAULT_DATE_FORMAT):
                parts.append(re.escape(lit2.lower()))
                if f2:
                    parts.append(_DATE_RX[f2])
        elif field in _DATE_RX:
            parts.append(_DATE_RX[field])
        elif field in ("ext", "EXT"):
            parts.append(r"[^/]+")
    return re.compile("".join(parts))


def already_organized(root: Path, current_parent: Path, template: str, cfg: dict) -> bool:
    """True kalau item sudah berada di folder yang cocok dengan pola tujuannya (tanggal boleh beda).
    Mencegah file pindah lagi tiap bulan hanya karena diedit (tanggal diubah berganti)."""
    key = ("_dest_rx", template)
    if key not in cfg:
        cfg[key] = dest_pattern(template, cfg.get("date_format"))
    rx = cfg[key]
    if rx is None:
        return False
    try:
        rel_parent = current_parent.resolve().relative_to(Path(root).resolve()).as_posix().lower()
    except ValueError:
        return False
    return bool(rx.fullmatch(rel_parent))


def plan_folders(root: Path, cfg: dict, taken: set, now: float, cancel=None) -> list:
    moves = []
    if not (cfg["folder_rules"] or cfg["folder_fallback"]):
        return moves
    for p, st in iter_top_folders(root, cfg, cancel=cancel):
        rule = next((r for r in cfg["folder_rules"] if rule_matches(r, p, st, now)), None)
        if rule:
            template, reason = rule["dest"], f"[folder] {rule['name']}"
        elif cfg["folder_fallback"]:
            template, reason = cfg["folder_fallback"], "[folder] (fallback)"
        else:
            continue
        target_dir = _resolve_dest(root, render_dest(template, p, st, True, cfg["date_format"]), reason)
        if p.resolve() == target_dir or p.resolve() in target_dir.parents:
            continue
        if target_dir == p.parent.resolve():
            continue  # dest "." → folder dibiarkan di tempat (bukan di-rename jadi "X (2)")
        moves.append(Move(p, unique_dest(target_dir / p.name, taken, is_dir=True), reason))
    return moves


def build_plan(root: Path, cfg: dict, stable_secs: int = 0, include_folders: bool = True, cancel=None,
               progress=None) -> list:
    check_target(root)
    now = time.time()
    taken = set()
    moves = plan_folders(root, cfg, taken, now, cancel=cancel) if include_folders else []
    moving_dirs = {m.src for m in moves}  # isi folder yang ikut dipindah tidak direncanakan terpisah
    for p, st in iter_files(root, cfg["recursive"], cfg["exclude"], stable_secs, cancel=cancel, progress=progress,
                            skip_rel=cfg.get("_folder_dest_roots", ())):
        if moving_dirs and not moving_dirs.isdisjoint(p.parents):
            continue
        rule = next((r for r in cfg["rules"] if rule_matches(r, p, st, now)), None)
        if rule:
            template, reason = rule["dest"], rule["name"]
        elif cfg["fallback_dest"]:
            template, reason = cfg["fallback_dest"], "(fallback)"
        else:
            continue
        if template.strip().strip("/\\") in (".", ""):
            continue  # dest "." = biarkan di tempat (juga di subfolder, bukan dipindah ke root)
        target_dir = _resolve_dest(root, render_dest(template, p, st, False, cfg["date_format"]), reason)
        if p.parent.resolve() == target_dir:
            continue  # sudah di tempat yang benar
        if already_organized(root, p.parent, template, cfg):
            continue  # sudah di pola tujuannya (mis. Notes/2026-09), jangan dipindah hanya karena tanggalnya berubah
        moves.append(Move(p, unique_dest(target_dir / p.name, taken), reason))
    return moves


def print_plan(root: Path, moves: list, limit: int = 40):
    if not moves:
        print(T("cli_nothing"))
        return
    by_rule = Counter(m.reason for m in moves)
    print("\n" + T("cli_plan_head", n=len(moves)) + "\n")
    for reason, n in by_rule.most_common():
        print(f"  {n:>6}  {reason}")
    print("\n" + T("cli_examples", n=limit))
    for m in moves[:limit]:
        print(f"  {rel(root, m.src)}\n    → {rel(root, m.dst)}")
    if len(moves) > limit:
        print("  " + T("cli_more", n=len(moves) - limit))


def save_plan_csv(root: Path, moves: list) -> Path:
    out = state_dir(root) / "plan_latest.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig biar rapi dibuka di Excel
        w = csv.writer(f)
        w.writerow(["rule", "source", "destination"])
        for m in moves:
            w.writerow([m.reason, rel(root, m.src), rel(root, m.dst)])
    return out


# ───────────────────────── execution + journal ─────────────────────────

def move_item(src: Path, dst: Path):
    """Pindah = rename di volume yang sama. Sengaja TIDAK memakai shutil.move: kalau rename gagal (di Windows
    mis. karena file sedang dibuka), shutil.move menyalin lalu menghapus — hasilnya duplikat atau folder setengah
    terhapus yang tidak tercatat di journal. Di sini kegagalan dilaporkan dan file asli tidak disentuh."""
    if os.path.lexists(dst):
        raise FileExistsError(errno.EEXIST, T("e_dest_exists"), str(dst))
    try:
        os.rename(src, dst)
    except OSError as e:
        if e.errno == errno.EXDEV:
            raise OSError(errno.EXDEV, T("e_cross_volume"), str(dst)) from e
        raise


def _move_error(e: OSError, dst: Path) -> str:
    if sys.platform == "win32" and len(str(dst)) >= MAX_PATH_WIN:
        return T("e_path_too_long", n=len(str(dst)))
    if isinstance(e, PermissionError) or getattr(e, "winerror", None) in (5, 32, 33):
        return T("e_in_use") + f" ({e.strerror or e})"
    return e.strerror or str(e)


def _new_journal(label: str, state: Path):
    """Buat file journal baru yang dijamin unik (mode 'x' tidak pernah menimpa)."""
    for _ in range(1000):
        path = state / f"journal_{datetime.now():%Y%m%d_%H%M%S_%f}_{label}.jsonl"
        try:
            return path, open(path, "x", encoding="utf-8")
        except FileExistsError:
            time.sleep(0.001)
    raise RuntimeError(T("e_journal"))


def execute(root: Path, moves: list, label: str, progress=None, cancel=None) -> tuple:
    """Pindahkan semua item. Kalau cancel di-set, berhenti sebelum item berikutnya; yang sudah dipindah
    tetap tercatat di journal (bisa di-undo). Return (ok, failed)."""
    check_target(root)
    ensure_writable(root)
    with folder_lock(root, label):
        return _execute_locked(root, moves, label, progress, cancel)


def _execute_locked(root: Path, moves: list, label: str, progress, cancel) -> tuple:
    journal, fh = _new_journal(label, state_dir(root))
    ok, failed = 0, []
    with fh as j:
        for m in moves:
            if cancel is not None and cancel.is_set():
                break
            try:
                m.dst.parent.mkdir(parents=True, exist_ok=True)
                if m.dst.exists():  # bisa terjadi kalau folder berubah sejak plan
                    m.dst = unique_dest(m.dst, set(), is_dir=m.src.is_dir())
                move_item(m.src, m.dst)
                j.write(json.dumps({"src": str(m.src), "dst": str(m.dst)}, ensure_ascii=False) + "\n")
                j.flush()
                ok += 1
            except OSError as e:
                failed.append((m.src, _move_error(e, m.dst)))
                log.warning("move failed: %s -> %s: %s", m.src, m.dst, e)
                remove_empty_parents(m.dst.parent, root)  # folder tujuan yang baru dibuat tapi tetap kosong
            if progress:
                progress(ok + len(failed), len(moves))
    if ok == 0:
        journal.unlink(missing_ok=True)
    log.info("batch %s in %s: %d moved, %d failed%s, journal=%s", label, root, ok, len(failed),
             " (cancelled)" if cancel is not None and cancel.is_set() else "", journal.name if ok else "-")
    return ok, failed


def report_result(root: Path, ok: int, failed: list):
    print("\n" + T("cli_moved", n=ok))
    if failed:
        print(T("cli_failed", n=len(failed)))
        for src, err in failed[:15]:
            print(f"  {rel(root, src)} — {err}")
    if ok:
        print(T("cli_undo_hint"))


def confirm(msg: str) -> bool:
    try:
        return input(f"{msg} [{T('cli_yes')}] ").strip().lower() in ("y", "ya", "yes")
    except EOFError:
        return False


def remove_empty_parents(p: Path, stop: Path):
    stop = stop.resolve()
    p = p.resolve()
    while p != stop and stop in p.parents:
        try:
            p.rmdir()  # hanya berhasil kalau kosong
        except OSError:
            break
        p = p.parent


_JOURNAL_RE = re.compile(r"journal_(\d{8})_(\d{6})(?:_(\d{6}))?_")


def _journal_key(p: Path):
    m = _JOURNAL_RE.match(p.name)
    return (m.group(1), m.group(2), m.group(3) or "000000", p.name) if m else ("", "", "", p.name)


def journal_time(p: Path):
    """datetime batch dari nama file journal (format lama & baru), atau None."""
    m = _JOURNAL_RE.match(p.name)
    if not m:
        return None
    return datetime.strptime(m.group(1) + m.group(2) + (m.group(3) or "000000"), "%Y%m%d%H%M%S%f")


def list_journals(root: Path) -> list:
    """Semua batch (aktif & sudah di-undo), terbaru di akhir. Membaca lokasi baru (%APPDATA%) dan lama (.organizer)."""
    found = []
    for d in (state_dir(root, create=False), Path(root) / STATE_DIR):
        if d.exists():
            found += list(d.glob("journal_*.jsonl")) + list(d.glob("journal_*.undone"))
    return sorted(found, key=_journal_key)


def read_journal(journal: Path) -> list:
    return [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines() if line.strip()]


def undo_journal(root: Path, journal: Path) -> tuple:
    with folder_lock(root, "undo"):
        return _undo_locked(root, journal)


def _undo_locked(root: Path, journal: Path) -> tuple:
    """Return (restored, skipped, failed). Item yang gagal (mis. file sedang dibuka) tetap di journal,
    jadi undo bisa diulang; journal baru ditandai selesai kalau tidak ada yang gagal."""
    restored, skipped, retry = 0, 0, []
    for e in reversed(read_journal(journal)):
        src, dst = Path(e["src"]), Path(e["dst"])
        if not dst.exists() or src.exists():
            skipped += 1
            continue
        try:
            src.parent.mkdir(parents=True, exist_ok=True)
            move_item(dst, src)
        except OSError as err:
            log.warning("undo failed: %s -> %s: %s", dst, src, err)
            retry.append(e)
            continue
        remove_empty_parents(dst.parent, root)
        restored += 1
    if retry:
        tmp = journal.with_name(journal.name + ".tmp")
        tmp.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in reversed(retry)), encoding="utf-8")
        tmp.replace(journal)
    else:
        journal.rename(journal.with_suffix(".undone"))
    log.info("undo %s: %d restored, %d skipped, %d failed", journal.name, restored, skipped, len(retry))
    return restored, skipped, len(retry)


def undo_last(root: Path):
    active = [j for j in list_journals(root) if j.suffix == ".jsonl"]
    if not active:
        print(T("cli_no_undo"))
        return
    last = active[-1]
    print(T("cli_undo_batch", name=last.name, n=len(read_journal(last))))
    restored, skipped, failed = undo_journal(root, last)
    print(T("cli_restored", n=restored) + (T("cli_skipped", n=skipped) if skipped else "")
          + (T("cli_undo_failed", n=failed) if failed else ""))


# ───────────────────────── duplicates ─────────────────────────

def hash_file(p: Path, limit: int = 0, cancel=None, on_bytes=None) -> str:
    h = hashlib.blake2b(digest_size=20)
    read = 0
    with open(p, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
            read += len(chunk)
            if on_bytes:
                on_bytes(len(chunk))
            if limit and read >= limit:
                break
            check_cancel(cancel)
    return h.hexdigest()


def find_duplicates(files: list, progress=None, cancel=None) -> list:
    """files: list of (Path, stat). Return list of groups (list of (Path, stat)) dengan isi identik.
    progress(bytes_done, bytes_total): total diperbarui setelah tahap 1 (hash 64 KB pertama) selesai."""
    head = 64 * 1024
    by_size = defaultdict(list)
    for p, st in files:
        if getattr(st, "st_file_attributes", 0) & WIN_CLOUD_NOT_LOCAL:
            continue  # file OneDrive yang belum di-download: membacanya akan memicu download
        if st.st_size > 0:
            by_size[st.st_size].append((p, st))
    candidates = [g for g in by_size.values() if len(g) > 1]
    state = {"done": 0, "total": sum(min(st.st_size, head) for g in candidates for _, st in g)}

    def tick(n):
        state["done"] += n
        if progress:
            progress(state["done"], state["total"])

    stage2 = []
    for same_size in candidates:
        by_head = defaultdict(list)
        for p, st in same_size:
            check_cancel(cancel)
            try:
                by_head[hash_file(p, head, cancel, tick)].append((p, st))
            except OSError:
                pass
        stage2 += [c for c in by_head.values() if len(c) > 1]
    state["total"] += sum(st.st_size for c in stage2 for _, st in c)
    groups = []
    for cands in stage2:
        by_full = defaultdict(list)
        for p, st in cands:
            try:
                by_full[hash_file(p, 0, cancel, tick)].append((p, st))
            except OSError:
                pass
        groups += [g for g in by_full.values() if len(g) > 1]
    return groups


def dedupe_moves(root: Path, groups: list) -> list:
    moves, taken = [], set()
    for g in groups:
        # simpan yang paling lama (original), tie-break path terpendek
        g.sort(key=lambda x: (x[1].st_mtime, len(str(x[0]))))
        keeper = g[0][0]
        for p, _ in g[1:]:
            dst = unique_dest(root / TRASH_DIR / rel(root, p), taken)
            moves.append(Move(p, dst, T("e_dup_of", path=rel(root, keeper))))
    return moves


# ───────────────────────── commands ─────────────────────────

def cmd_scan(root: Path, cfg: dict):
    print(T("cli_scanning", path=root, rec=cfg["recursive"]))
    files = list(iter_files(root, cfg["recursive"], cfg["exclude"]))
    if not files:
        print(T("cli_empty"))
        return
    total = sum(st.st_size for _, st in files)
    now = time.time()
    by_ext = defaultdict(lambda: [0, 0])
    for p, st in files:
        e = ext_of(p) or T("no_ext")
        by_ext[e][0] += 1
        by_ext[e][1] += st.st_size
    stale = [x for x in files if (now - x[1].st_mtime) > 365 * 86400]

    print(f"\n{T('cli_summary')}\n  {T('cli_files')}: {len(files):,}\n  {T('cli_size')}: {human(total)}")
    print("  " + T("cli_stale", n=f"{len(stale):,}", size=human(sum(s.st_size for _, s in stale))))
    print("\n" + T("cli_top_ext"))
    for e, (n, size) in sorted(by_ext.items(), key=lambda kv: -kv[1][0])[:15]:
        print(f"  {e:<18} {T('cli_n_files', n=f'{n:,}'):>12}  {human(size):>10}")
    print("\n" + T("cli_largest"))
    for p, st in sorted(files, key=lambda x: -x[1].st_size)[:10]:
        print(f"  {human(st.st_size):>10}  {rel(root, p)}")
    print("\n" + T("cli_dupes_head"))
    groups = find_duplicates(files)
    wasted = sum(g[0][1].st_size * (len(g) - 1) for g in groups)
    print("  " + T("cli_dupes_sum", groups=f"{len(groups):,}", extra=f"{sum(len(g) - 1 for g in groups):,}",
                   size=human(wasted)))
    for g in sorted(groups, key=lambda g: -g[0][1].st_size * (len(g) - 1))[:5]:
        print(f"  • {human(g[0][1].st_size)} × {len(g)}")
        for p, _ in g[:4]:
            print(f"      {rel(root, p)}")
    moves = build_plan(root, cfg)
    print(f"\n{T('cli_rules_head')}\n  " + T("cli_rules_sum", n=f"{len(moves):,}"))


def cmd_plan(root: Path, cfg: dict):
    moves = build_plan(root, cfg)
    print_plan(root, moves)
    if moves:
        print("\n" + T("cli_csv", path=save_plan_csv(root, moves)))
        print(T("cli_apply_hint"))


def cmd_apply(root: Path, cfg: dict, yes: bool):
    moves = build_plan(root, cfg)
    print_plan(root, moves, limit=15)
    if not moves:
        return
    if not yes and not confirm("\n" + T("cli_confirm_move", n=len(moves))):
        print(T("cli_cancelled"))
        return
    report_result(root, *execute(root, moves, "apply"))
    prune_journals(root)


def cmd_dedupe(root: Path, cfg: dict, do_apply: bool, yes: bool):
    # selalu recursive: setelah apply, file sudah tersebar di subfolder
    files = list(iter_files(root, True, cfg["exclude"]))
    print(T("cli_checking", n=f"{len(files):,}"))
    moves = dedupe_moves(root, find_duplicates(files))
    if not moves:
        print(T("cli_no_dupes"))
        return
    wasted = sum(m.src.stat().st_size for m in moves)
    print("\n" + T("cli_dupes_plan", n=len(moves), size=human(wasted), trash=TRASH_DIR))
    for m in moves[:20]:
        print(f"  {rel(root, m.src)}   ({m.reason})")
    if not do_apply:
        print("\n" + T("cli_dry_run"))
        return
    if not yes and not confirm("\n" + T("cli_confirm_dupes", n=len(moves), trash=TRASH_DIR)):
        print(T("cli_cancelled"))
        return
    report_result(root, *execute(root, moves, "dedupe"))
    print(T("cli_review_trash", trash=TRASH_DIR))


def cmd_watch(root: Path, cfg: dict, interval: int):
    print(T("cli_watching", path=root, n=interval))
    try:
        while True:
            # tunggu file "diam" 15 detik; folder tidak disentuh di mode watch (bisa saja sedang di-extract)
            moves = build_plan(root, cfg, stable_secs=15, include_folders=False)
            if moves:
                try:
                    ok, failed = execute(root, moves, "watch")
                except FolderBusy:
                    print(f"[{datetime.now():%H:%M:%S}] " + T("log_busy"))
                else:
                    print(f"[{datetime.now():%H:%M:%S}] " + T("cli_watch_moved", n=ok)
                          + (T("cli_watch_failed", n=len(failed)) if failed else ""))
                    prune_journals(root)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n" + T("cli_stopped"))


# ───────────────────────── folder labels ─────────────────────────

LABEL_SECTION = "[FolderOrganizer]"   # penanda di desktop.ini: label ini dibuat app (aman dihapus)
README_MARKER = "Folder Organizer"    # ada di footer _README.txt buatan app (semua bahasa)


def _win_set_attrs(path: Path, add: int = 0, replace: int = None, remove: int = 0):
    if sys.platform != "win32":
        return
    import ctypes
    k32 = ctypes.windll.kernel32
    if replace is not None:
        k32.SetFileAttributesW(str(path), replace)
        return
    cur = k32.GetFileAttributesW(str(path))
    if cur != -1 and cur != 0xFFFFFFFF:
        k32.SetFileAttributesW(str(path), (cur | add) & ~remove)


def _read_ini(ini: Path) -> str:
    try:
        return ini.read_text(encoding="utf-16")
    except (UnicodeError, UnicodeDecodeError):
        return ini.read_text(encoding="mbcs" if sys.platform == "win32" else "latin-1", errors="ignore")


def _split_ini(text: str):
    """Return (shell_lines, other_lines, ours). shell_lines tanpa InfoTip; ours = isi section penanda app."""
    section, shell, others, ours = None, [], [], {}
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith("["):
            section = s.lower()
            if section not in ("[.shellclassinfo]", LABEL_SECTION.lower()):
                others.append(s)
            continue
        if section == "[.shellclassinfo]":
            if not s.lower().startswith("infotip="):
                shell.append(s)
        elif section == LABEL_SECTION.lower():
            k, _, v = s.partition("=")
            ours[k.strip().lower()] = v.strip()
        else:
            others.append(s)  # section lain (mis. [ViewState]) disalin apa adanya
    return shell, others, ours


def _is_icon(line: str) -> bool:
    return line.lower().startswith("iconresource=")


_README_FOOTER_RX = re.compile(r"^\(.*Folder Organizer.*\)$")


def _readme_is_ours(path: Path) -> bool:
    """_README.txt buatan app: baris terakhirnya footer app, mis. "(Generated by Folder Organizer. …)"."""
    try:
        if not path.is_file():
            return False
        lines = [x.strip() for x in path.read_text(encoding="utf-8-sig", errors="ignore").splitlines() if x.strip()]
    except OSError:
        return False
    return bool(lines) and bool(_README_FOOTER_RX.match(lines[-1]))


def write_folder_label(folder: Path, desc: str, icon: str = None, readme: bool = True) -> bool:
    """Tulis tooltip (desktop.ini) + _README.txt. Ikon custom yang sudah ada tetap dipakai kecuali aturan
    menentukan ikon (ikon lama disimpan untuk dikembalikan saat label dihapus). _README.txt milik user tidak
    ditimpa. Return False kalau README dilewati karena milik user."""
    ini = folder / "desktop.ini"
    shell, others, ours = [], [], {}
    if ini.exists():
        shell, others, ours = _split_ini(_read_ini(ini))  # pertahankan baris lain (mis. LocalizedResourceName)
        _win_set_attrs(ini, replace=0x80)  # NORMAL, supaya bisa ditimpa
    marker = [LABEL_SECTION, "Managed=1"]
    if icon:
        old_icon = next((x for x in shell if _is_icon(x)), None)
        shell = [x for x in shell if not _is_icon(x)] + [f"IconResource={icon}"]
        orig = ours.get("origiconresource") or (old_icon.partition("=")[2] if old_icon and not ours.get("seticon")
                                                 else "")
        marker += ["SetIcon=1"] + ([f"OrigIconResource={orig}"] if orig else [])
    elif ours.get("seticon"):  # ikon dari aturan sebelumnya sudah tidak dipakai → kembalikan yang asli
        shell = [x for x in shell if not _is_icon(x)]
        if ours.get("origiconresource"):
            shell.append(f"IconResource={ours['origiconresource']}")
    lines = ["[.ShellClassInfo]", f"InfoTip={' '.join(desc.split())}"] + shell + others + marker
    ini.write_text("\r\n".join(lines) + "\r\n", encoding="utf-16")  # UTF-16 → aman untuk teks non-ASCII
    _win_set_attrs(ini, add=0x2 | 0x4)    # hidden + system
    _win_set_attrs(folder, add=0x1)       # flag read-only di folder = sinyal Explorer untuk baca desktop.ini
    readme_path = folder / README_NAME
    if not readme:
        return True
    if readme_path.exists() and not _readme_is_ours(readme_path):
        log.info("label: keeping user's %s", readme_path)
        return False
    readme_path.write_text(
        f"{folder.name}\r\n{'=' * len(folder.name)}\r\n\r\n{desc.strip()}\r\n\r\n{T('readme_footer')}\r\n",
        encoding="utf-8-sig")
    return True


def is_managed_label(folder: Path) -> bool:
    """Label buatan app: desktop.ini punya penanda, atau (versi lama) InfoTip + _README.txt buatan app."""
    ini = folder / "desktop.ini"
    if not ini.is_file():
        return False
    try:
        text = _read_ini(ini).lower()
    except OSError:
        return False
    return LABEL_SECTION.lower() in text or ("infotip=" in text and _readme_is_ours(folder / README_NAME))


def remove_folder_label(folder: Path) -> bool:
    """Hapus tooltip & _README.txt buatan app. Pengaturan desktop.ini lain (ikon, view) dipertahankan.
    Return True kalau ada yang dihapus."""
    changed = False
    ini = folder / "desktop.ini"
    if is_managed_label(folder):
        shell, others, ours = _split_ini(_read_ini(ini))
        if ours.get("seticon"):  # ikon dari app → kembalikan ikon asli (kalau ada)
            shell = [x for x in shell if not _is_icon(x)]
            if ours.get("origiconresource"):
                shell.append(f"IconResource={ours['origiconresource']}")
        _win_set_attrs(ini, replace=0x80)
        if shell or others:
            ini.write_text("\r\n".join(["[.ShellClassInfo]"] + shell + others) + "\r\n", encoding="utf-16")
            _win_set_attrs(ini, add=0x2 | 0x4)
        else:
            ini.unlink()
            _win_set_attrs(folder, remove=0x1)  # tidak ada kustomisasi lagi → lepas flag read-only folder
        changed = True
    readme = folder / README_NAME
    if _readme_is_ours(readme):
        readme.unlink()
        changed = True
    return changed


def find_managed_labels(root: Path, max_depth: int = 4, cancel=None) -> list:
    """Path relatif (pakai '/') semua folder yang punya label buatan app, sampai kedalaman max_depth."""
    out, root = [], Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        check_cancel(cancel)
        dp = Path(dirpath)
        depth = len(dp.relative_to(root).parts)
        dirnames[:] = [] if depth >= max_depth else [
            d for d in dirnames if d not in ALWAYS_EXCLUDE_DIRS and d not in SKIP_DEEP_DIRS
            and not d.startswith(".") and not is_link_or_junction(dp / d)]
        if dp != root and "desktop.ini" in {f.lower() for f in filenames} and is_managed_label(dp):
            out.append(dp.relative_to(root).as_posix())
    return sorted(out, key=str.lower)


def label_text(val, lang: str = None) -> str:
    """Deskripsi folder: teks biasa, atau {en: ..., id: ...} (ikut bahasa app), atau {desc: ...}."""
    if isinstance(val, str):
        return val
    val = val or {}
    lang = lang or T.lang
    return str(val.get(lang) or val.get("desc") or val.get("en") or val.get("id") or "")


def folder_info_entries(cfg: dict) -> list:
    out = []
    for rel_path, val in (cfg.get("folder_info") or {}).items():
        out.append((rel_path, label_text(val), None if isinstance(val, str) else (val or {}).get("icon")))
    return out


def _label_folder(root: Path, rel_path: str):
    """Folder label di dalam root, atau None kalau path-nya keluar dari folder target."""
    if label_path_error(rel_path):
        return None
    folder = root / rel_path
    try:
        if not _inside(root.resolve(), folder.resolve()):
            return None
    except OSError:
        return None
    return folder


def apply_labels(root: Path, cfg: dict) -> list:
    """Return list of (rel_path, status, detail); status: ok | missing | error."""
    check_target(root)
    readme = cfg.get("folder_info_readme", True)
    results = []
    for rel_path, desc, icon in folder_info_entries(cfg):
        folder = _label_folder(root, rel_path)
        if folder is None:
            results.append((rel_path, "error", label_path_error(rel_path) or T("e_label_path_outside", path=rel_path)))
            continue
        if not folder.is_dir():
            results.append((rel_path, "missing", T("e_label_missing")))
            continue
        try:
            readme_written = write_folder_label(folder, desc, icon, readme)
            results.append((rel_path, "ok", desc if readme_written else f"{desc}  ({T('label_readme_kept')})"))
        except OSError as e:
            results.append((rel_path, "error", str(e)))
    return results


def remove_labels(root: Path, rel_paths: list) -> list:
    """Return list of (rel_path, status, detail); status: ok | none | missing | error."""
    check_target(root)
    results = []
    for rel_path in rel_paths:
        folder = _label_folder(root, rel_path)
        if folder is None:
            results.append((rel_path, "error", T("e_label_path_outside", path=rel_path)))
            continue
        if not folder.is_dir():
            results.append((rel_path, "missing", T("e_label_missing")))
            continue
        try:
            results.append((rel_path, "ok" if remove_folder_label(folder) else "none", ""))
        except OSError as e:
            results.append((rel_path, "error", str(e)))
    return results


def cmd_label(root: Path, cfg: dict, remove: bool = False):
    if remove:
        paths = sorted(set(find_managed_labels(root)) | {p for p, _, _ in folder_info_entries(cfg)})
        results = remove_labels(root, paths)
        for rel_path, status, detail in results:
            if status == "ok":
                print(f"  ✔ {rel_path}")
            elif status == "error":
                print(f"  ⚠ {rel_path} — {detail}")
        print("\n" + T("cli_unlabeled", n=sum(r[1] == "ok" for r in results)))
        return
    if not cfg.get("folder_info"):
        print(T("cli_no_info"))
        return
    results = apply_labels(root, cfg)
    for rel_path, status, detail in results:
        if status == "ok":
            print(f"  ✔ {rel_path}")
        elif status == "error":
            print(f"  ⚠ {rel_path} — {detail}")
    print("\n" + T("cli_labeled", n=sum(r[1] == "ok" for r in results)))
    missing = [r[0] for r in results if r[1] == "missing"]
    if missing:
        print(T("cli_label_skipped", list=", ".join(missing)))
    print(T("cli_label_hint"))


def default_lang() -> str:
    """Bahasa CLI mengikuti pilihan di GUI (settings.json), default English."""
    try:
        return json.loads((app_data_dir() / "settings.json").read_text(encoding="utf-8")).get("lang", "en")
    except (OSError, ValueError):
        return "en"


def main():
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--lang", choices=["en", "id"])
    T.lang = pre.parse_known_args()[0].lang or default_lang()

    ap = argparse.ArgumentParser(prog="organizer", description=T("cli_desc"))
    ap.add_argument("command", choices=["scan", "plan", "apply", "dedupe", "undo", "watch", "label"])
    ap.add_argument("folder", help=T("cli_help_folder"))
    ap.add_argument("--rules", default=None, help=T("cli_help_rules"))
    ap.add_argument("--recursive", action="store_true", help=T("cli_help_recursive"))
    ap.add_argument("--apply", action="store_true", help=T("cli_help_apply"))
    ap.add_argument("--yes", "-y", action="store_true", help=T("cli_help_yes"))
    ap.add_argument("--interval", type=int, default=30, help=T("cli_help_interval"))
    ap.add_argument("--remove", action="store_true", help=T("cli_help_remove"))
    ap.add_argument("--lang", choices=["en", "id"], help=T("cli_help_lang"))
    a = ap.parse_args()
    setup_logging()
    a.rules = a.rules or str(rules_path())

    root = Path(a.folder).expanduser().resolve()
    if not root.is_dir():
        sys.exit(T("cli_folder_missing", path=root))

    if a.command == "undo":
        try:
            return undo_last(root)
        except FolderBusy as e:
            sys.exit("\n⚠ " + str(e))

    cfg = load_config(Path(a.rules))
    if a.recursive:
        cfg["recursive"] = True

    try:
        _dispatch(a, root, cfg)
    except AccessBlocked as e:
        sys.exit("\n" + T("cli_blocked", path=e.path, exe=sys.executable))
    except FolderBusy as e:
        sys.exit("\n⚠ " + str(e))


def _dispatch(a, root, cfg):
    {"scan": lambda: cmd_scan(root, cfg),
     "plan": lambda: cmd_plan(root, cfg),
     "apply": lambda: cmd_apply(root, cfg, a.yes),
     "dedupe": lambda: cmd_dedupe(root, cfg, a.apply, a.yes),
     "watch": lambda: cmd_watch(root, cfg, a.interval),
     "label": lambda: cmd_label(root, cfg, a.remove)}[a.command]()


if __name__ == "__main__":
    main()
