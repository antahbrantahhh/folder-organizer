"""Baca/tulis rules.yaml tanpa menghilangkan komentar.

GUI mengedit dict biasa (hasil yaml.safe_load). Saat disimpan, perubahan digabung ke dokumen round-trip
ruamel.yaml, sehingga komentar, urutan key, dan gaya penulisan bagian yang tidak diubah tetap sama.
Kalau ruamel.yaml tidak terinstall, fallback ke PyYAML (komentar hilang, tapi file tetap valid).
"""
import copy
import hashlib
import io
from pathlib import Path

import yaml

try:
    from ruamel.yaml import YAML
    from ruamel.yaml.comments import CommentedMap, CommentedSeq
    HAS_RUAMEL = True
except ImportError:  # pragma: no cover - diuji lewat flag
    HAS_RUAMEL = False

FALLBACK_HEADER = ("# Folder Organizer — rules\n"
                   "# Rules are checked top to bottom; the first match wins.\n\n")


def _yaml():
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096
    y.indent(mapping=2, sequence=4, offset=2)
    y.representer.add_representer(
        type(None), lambda rep, _: rep.represent_scalar("tag:yaml.org,2002:null", "null"))
    return y


def _is_scalar(x):
    return not isinstance(x, (dict, list))


def _to_rt(obj):
    """Struktur baru dari GUI → tipe round-trip: mapping blok, list skalar gaya flow ([pdf, docx])."""
    if isinstance(obj, dict):
        m = CommentedMap()
        for k, v in obj.items():
            m[k] = _to_rt(v)
        return m
    if isinstance(obj, list):
        seq = CommentedSeq(_to_rt(v) for v in obj)
        if all(_is_scalar(v) for v in obj):
            seq.fa.set_flow_style()
        return seq
    return obj


def _merge_map(rt, new):
    for k in [k for k in rt if k not in new]:
        del rt[k]
    for k, v in new.items():
        if k not in rt:
            rt[k] = _to_rt(v)
        elif rt[k] != v:
            rt[k] = _merge(rt[k], v)
    return rt


def _item_name(x):
    return x.get("name") if isinstance(x, dict) else None


def _reorder_seq(rt, new):
    """Tambah / hapus / urutkan ulang: pakai ulang node lama berdasarkan nama, bawa komentarnya."""
    pool = {}
    for i, o in enumerate(rt):
        if isinstance(o, CommentedMap) and o.get("name") is not None:
            pool.setdefault(o.get("name"), []).append((i, o))
    seq = CommentedSeq()
    for j, v in enumerate(new):
        found = pool.get(_item_name(v))
        if not found:
            seq.append(_to_rt(v))
            continue
        i, o = found.pop(0)
        seq.append(_merge(o, v))
        if i in rt.ca.items:
            seq.ca.items[j] = rt.ca.items[i]
    seq.ca.comment = rt.ca.comment
    return seq


def _merge_seq(rt, new):
    if all(_is_scalar(v) for v in new):
        seq = CommentedSeq(new)
        if rt.fa.flow_style() or not rt:
            seq.fa.set_flow_style()
        return seq
    if [_item_name(o) for o in rt] != [_item_name(n) for n in new]:
        return _reorder_seq(rt, new)
    for i, v in enumerate(new):  # urutan sama → edit di tempat, komentar per item tetap di posisinya
        if rt[i] != v:
            rt[i] = _merge(rt[i], v)
    return rt


def _merge(rt, new):
    """Gabungkan nilai baru ke node round-trip lama; bagian yang sama tidak disentuh (komentar tetap)."""
    if isinstance(new, dict) and isinstance(rt, CommentedMap):
        return _merge_map(rt, new)
    if isinstance(new, list) and isinstance(rt, CommentedSeq):
        return _merge_seq(rt, new)
    return _to_rt(new) if HAS_RUAMEL else new


class RulesConflict(Exception):
    """rules.yaml diubah program lain (mis. Notepad) sejak dibuka di app."""


def _digest(path: Path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


class RulesDocument:
    """Satu dokumen rules: teks asli + representasi round-trip untuk menulis ulang dengan komentar."""

    def __init__(self, text: str, digest: str = None):
        self.text = text
        self.digest = digest  # hash file saat dibaca; None = belum terikat ke file
        self._rt = None
        if HAS_RUAMEL:
            try:
                self._rt = _yaml().load(text) if text.strip() else CommentedMap()
            except Exception:
                self._rt = None  # teks tidak valid → plain() yang akan melaporkan error

    @classmethod
    def load(cls, path: Path) -> "RulesDocument":
        data = Path(path).read_bytes()
        return cls(data.decode("utf-8"), hashlib.sha256(data).hexdigest())

    def changed_on_disk(self, path: Path) -> bool:
        """True kalau file berubah sejak dokumen ini dibaca/disimpan (diedit di luar app)."""
        return self.digest is not None and _digest(path) != self.digest

    @property
    def preserves_comments(self) -> bool:
        return self._rt is not None and isinstance(self._rt, CommentedMap)

    def plain(self) -> dict:
        """Dict biasa untuk diedit. Raise yaml.YAMLError / ValueError kalau tidak valid."""
        doc = yaml.safe_load(self.text) or {}
        if not isinstance(doc, dict):
            raise ValueError("rules.yaml must be a mapping (key: value)")
        return doc

    def render(self, doc: dict) -> str:
        """Teks YAML untuk dict `doc`, mempertahankan komentar & gaya dari teks asli bila memungkinkan."""
        clean = {k: v for k, v in doc.items() if not str(k).startswith("_")}
        if self.preserves_comments:
            merged = _merge(copy.deepcopy(self._rt), copy.deepcopy(clean))
            out = io.StringIO()
            _yaml().dump(merged, out)
            return out.getvalue()
        body = yaml.safe_dump(clean, sort_keys=False, allow_unicode=True, default_flow_style=None, width=120)
        return FALLBACK_HEADER + body

    def save(self, path: Path, doc: dict, backup: bool = True, force: bool = False) -> "RulesDocument":
        """Tulis ke file (backup versi lama ke .bak), return dokumen baru sebagai basis edit berikutnya.
        Raise RulesConflict kalau file diubah di luar app sejak dibaca (kecuali force=True)."""
        path = Path(path)
        if not force and self.changed_on_disk(path):
            raise RulesConflict(str(path))
        text = self.render(doc)
        if backup and path.exists():
            path.with_name(path.name + ".bak").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)  # atomic: file tidak pernah setengah tertulis
        return RulesDocument(text, _digest(path))  # hash dari file asli (Windows menulis \r\n)
