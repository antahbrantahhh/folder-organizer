"""String UI: EN/ID lengkap, dan tidak ada key yang diam-diam ditimpa (bug kolom "Ext." di Overview, v3.10)."""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import i18n  # noqa: E402


def _dicts():
    tree = ast.parse((ROOT / "i18n.py").read_text(encoding="utf-8"))
    return [n for n in ast.walk(tree) if isinstance(n, ast.Dict) and len(n.keys) > 50]


def test_no_duplicate_or_overridden_keys():
    for d in _dicts():
        keys = [k.value for k in d.keys if isinstance(k, ast.Constant)]
        dup = {k for k in keys if keys.count(k) > 1}
        assert not dup, f"duplicate keys at line {d.lineno}: {dup}"
    base_en, extra_en = _dicts()[0], _dicts()[2]
    overlap = {k.value for k in base_en.keys} & {k.value for k in extra_en.keys}
    assert not overlap, f"_EXTRA overrides STRINGS keys: {overlap}"


def test_en_id_parity_and_placeholders():
    en, idd = i18n.STRINGS["en"], i18n.STRINGS["id"]
    assert set(en) == set(idd)
    ph = re.compile(r"\{(\w+)")
    bad = {k for k in en if set(ph.findall(en[k])) != set(ph.findall(idd[k]))}
    assert not bad, f"placeholder mismatch: {sorted(bad)}"


def test_every_key_used_in_code_exists():
    used = set()
    for f in [ROOT / "organizer.py", *ROOT.glob("gui/**/*.py")]:
        used |= set(re.findall(r"""T\(["']([a-z_0-9]+)["']""", f.read_text(encoding="utf-8")))
    missing = used - set(i18n.STRINGS["en"])
    assert not missing, sorted(missing)
