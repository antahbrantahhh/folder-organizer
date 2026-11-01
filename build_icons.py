"""Build ikon rail: SVG source (assets/icons/*.svg) → PNG per tema/state/skala (assets/icons/png/).
Jalankan ulang setelah mengedit SVG:  pip install cairosvg  lalu  python build_icons.py"""
import math
from pathlib import Path

HERE = Path(__file__).parent
SRC, OUT = HERE / "assets" / "icons", HERE / "assets" / "icons" / "png"
HEAD = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">')


def gear():
    pts, teeth, ro, ri = [], 8, 9.2, 7.2
    for i in range(teeth * 4):
        a = math.pi * 2 * i / (teeth * 4) - math.pi / 2
        r = ro if (i % 4) in (0, 1) else ri
        pts.append(f"{12 + r * math.cos(a):.2f} {12 + r * math.sin(a):.2f}")
    return f'<path d="M{" L".join(pts)} Z"/><circle cx="12" cy="12" r="3"/>'


ICONS = {
    "overview": '<rect x="3" y="3" width="7.5" height="9" rx="1.8"/><rect x="13.5" y="3" width="7.5" height="5" rx="1.8"/>'
                '<rect x="13.5" y="11" width="7.5" height="10" rx="1.8"/><rect x="3" y="15" width="7.5" height="6" rx="1.8"/>',
    "organize": '<path d="M3 7.5V18a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9.5a2 2 0 0 0-2-2h-7.2L9.6 5H5a2 2 0 0 0-2 2.5z"/>'
                '<path d="M8 12.5h8M8 16h5"/>',
    "dupes": '<rect x="8.5" y="8.5" width="12.5" height="12.5" rx="2"/>'
             '<path d="M15.5 8.5V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v8.5a2 2 0 0 0 2 2h3.5"/>',
    "history": '<path d="M3.6 12A8.5 8.5 0 1 0 6 6"/><path d="M3 3.5V8h4.5"/><path d="M12 7.5V12l3 2"/>',
    "labels": '<path d="M3 12.2V4.6A1.6 1.6 0 0 1 4.6 3h7.6c.42 0 .83.17 1.13.47l7.3 7.3a1.6 1.6 0 0 1 0 2.26l-7.7 7.7'
              'a1.6 1.6 0 0 1-2.26 0l-7.3-7.3A1.6 1.6 0 0 1 3 12.2z"/><circle cx="8" cy="8" r="1.4"/>',
    "auto": '<path d="M20 11A8 8 0 0 0 5.7 6.1L4 8"/><path d="M4 3.5V8h4.5"/>'
            '<path d="M4 13a8 8 0 0 0 14.3 4.9L20 16"/><path d="M20 20.5V16h-4.5"/>',
    "rules": '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/>'
             '<circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
    "settings": gear(),
}
COLORS = {"dark": {"normal": "#ffffff", "active": "#57c8ff"}, "light": {"normal": "#1a1a1a", "active": "#005fb8"}}
SIZES = (20, 25, 30, 40)  # 100% / 125% / 150% / 200%

if __name__ == "__main__":
    import cairosvg
    OUT.mkdir(parents=True, exist_ok=True)
    for name, body in ICONS.items():
        svg = f"{HEAD}{body}</svg>"
        (SRC / f"{name}.svg").write_text(svg + "\n", encoding="utf-8")
        for theme, states in COLORS.items():
            for state, color in states.items():
                colored = svg.replace("currentColor", color)
                for size in SIZES:
                    cairosvg.svg2png(bytestring=colored.encode(), write_to=str(OUT / f"{name}_{theme}_{state}_{size}.png"),
                                     output_width=size, output_height=size)
    print(f"{len(ICONS)} ikon → {len(list(OUT.glob('*.png')))} PNG")


# ───────── ikon aplikasi (.ico) ─────────
# Tiap ukuran digambar sendiri di grid pikselnya (bukan dikecilkan dari 1 gambar besar), supaya tepi folder
# dan garis jatuh tepat di batas piksel → tajam di title bar (16–24 px) dan taskbar (24–48 px).
APP_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


def draw_app_icon(n: int):
    from PIL import Image, ImageDraw
    ss = 8                                   # supersampling; semua koordinat kelipatan 1 px → tepi tetap tajam
    S = n * ss
    px = lambda v: int(round(v)) * ss        # noqa: E731  koordinat piksel bulat → ruang supersample
    top, bottom = (88, 166, 255), (38, 88, 222)
    grad = Image.new("RGB", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        t = y / (S - 1)
        gd.line([(0, y), (S, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    inset = 0 if n <= 20 else max(1, round(n / 32))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([px(inset), px(inset), px(n - inset) - 1, px(n - inset) - 1],
                                           radius=px(max(3, round(n * 0.22))), fill=255)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    # geometri folder (dibulatkan ke piksel)
    left, right = round(n * 0.22), n - round(n * 0.22)
    tab_top, body_top, body_bot = round(n * 0.27), round(n * 0.37), n - round(n * 0.25)
    tab_right = left + round((right - left) * 0.45)
    r_body = max(1, round(n * 0.07))
    d.rounded_rectangle([px(left), px(tab_top), px(tab_right) - 1, px(body_top + r_body) - 1],
                        radius=px(max(1, round(n * 0.05))), fill=(225, 238, 255, 255))
    d.rounded_rectangle([px(left), px(body_top), px(right) - 1, px(body_bot) - 1], radius=px(r_body),
                        fill=(255, 255, 255, 255))
    # garis isi: makin kecil ikonnya, makin sedikit & tebal relatif
    lines = 2 if n <= 24 else 3
    thick = max(1, round(n / 22))
    gap = max(thick + 1, round(n / 10))
    inner_left = left + max(2, round(n * 0.12))
    usable = (right - inner_left) - max(2, round(n * 0.12))
    block = lines * thick + (lines - 1) * (gap - thick)
    y0 = body_top + ((body_bot - body_top) - block + 1) // 2
    for i in range(lines):
        w = max(2, round(usable * (1.0, 0.72, 0.48)[i]))
        y = y0 + i * gap
        d.rounded_rectangle([px(inner_left), px(y), px(inner_left + w) - 1, px(y + thick) - 1],
                            radius=px(thick) // 2, fill=(46, 104, 230, 255))
    return img.resize((n, n), Image.Resampling.BOX)


def build_app_icon(out_dir: Path):
    frames = {n: draw_app_icon(n) for n in APP_SIZES}
    big = frames[256]
    big.save(out_dir / "app.ico", format="ICO", sizes=[(n, n) for n in APP_SIZES],
             append_images=[frames[n] for n in APP_SIZES if n != 256])
    for n in (16, 20, 24, 32, 40, 48, 64, 256):
        frames[n].save(out_dir / f"app_{n}.png")
    big.save(out_dir / "app.png")
    return frames
