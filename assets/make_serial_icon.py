"""Draw the Serial Port app icon: a DE-9 (DB9) connector face.

Original geometry, no third-party artwork. Run from the repo:

    python3 assets/make_serial_icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

SIZES = (16, 32, 48, 256)
ORANGE = (255, 140, 0, 255)  # Iris #FF8C00
ORANGE_EDGE = (196, 90, 0, 255)
METAL = (214, 220, 226, 255)
METAL_DARK = (108, 116, 124, 255)
CAVITY = (32, 34, 38, 255)
GOLD = (236, 198, 72, 255)
GOLD_HOLE = (40, 30, 10, 255)
SCREW = (84, 88, 92, 255)
SCREW_CROSS = (210, 214, 218, 255)


def _px(size, t):
    return int(round(t * (size - 1)))


def draw_db9_16():
    """Pixel-aligned 16px: trapezoid cavity and 5+4 gold pins."""
    img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    px = img.load()

    def fill_rect(x0, y0, x1, y1, color):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                px[x, y] = color

    fill_rect(0, 0, 15, 15, ORANGE)
    for i in range(16):
        px[i, 0] = ORANGE_EDGE
        px[i, 15] = ORANGE_EDGE
        px[0, i] = ORANGE_EDGE
        px[15, i] = ORANGE_EDGE
    fill_rect(2, 4, 13, 12, METAL)
    for y, x0, x1 in (
        (5, 3, 12),
        (6, 3, 12),
        (7, 3, 12),
        (8, 4, 11),
        (9, 4, 11),
        (10, 4, 11),
    ):
        for x in range(x0, x1 + 1):
            px[x, y] = CAVITY
    for x in (4, 6, 8, 10, 12):
        px[x, 7] = GOLD
    for x in (5, 7, 9, 11):
        px[x, 9] = GOLD
    return img


def draw_db9(size):
    if size == 16:
        return draw_db9_16()
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def xy(x, y):
        return _px(size, x), _px(size, y)

    def rect(x0, y0, x1, y1):
        a, b = xy(x0, y0)
        c, e = xy(x1, y1)
        if c < a:
            a, c = c, a
        if e < b:
            b, e = e, b
        return [a, b, max(a + 1, c), max(b + 1, e)]

    radius = max(2, size // 7)
    d.rounded_rectangle(rect(0.04, 0.04, 0.96, 0.96), radius=radius, fill=ORANGE)
    edge_w = 1 if size <= 32 else max(2, size // 48)
    d.rounded_rectangle(
        rect(0.04, 0.04, 0.96, 0.96), radius=radius, outline=ORANGE_EDGE, width=edge_w
    )

    plate_r = max(1, size // 16)
    d.rounded_rectangle(
        rect(0.12, 0.24, 0.88, 0.80), radius=plate_r, fill=METAL
    )
    d.rounded_rectangle(
        rect(0.12, 0.24, 0.88, 0.80), radius=plate_r, outline=METAL_DARK, width=1
    )

    d.polygon(
        [xy(0.22, 0.34), xy(0.78, 0.34), xy(0.72, 0.70), xy(0.28, 0.70)],
        fill=METAL_DARK,
    )
    d.polygon(
        [xy(0.26, 0.38), xy(0.74, 0.38), xy(0.69, 0.66), xy(0.31, 0.66)],
        fill=CAVITY,
    )

    def pin_row(ys, xs):
        r = 1.15 if size <= 16 else max(1.6, size * 0.038)
        for x in xs:
            cx, cy = xy(x, ys)
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=GOLD)
            hole = max(0.6, r * 0.38)
            d.ellipse(
                [cx - hole, cy - hole, cx + hole, cy + hole], fill=GOLD_HOLE
            )

    pin_row(0.47, (0.32, 0.41, 0.50, 0.59, 0.68))
    pin_row(0.58, (0.365, 0.455, 0.545, 0.635))

    if size >= 32:
        sr = max(1.8, size * 0.032)
        for x in (0.17, 0.83):
            cx, cy = xy(x, 0.52)
            d.ellipse([cx - sr, cy - sr, cx + sr, cy + sr], fill=SCREW, outline=METAL_DARK)
            w = max(1, size // 64)
            d.line([cx - sr * 0.45, cy, cx + sr * 0.45, cy], fill=SCREW_CROSS, width=w)
            d.line([cx, cy - sr * 0.45, cx, cy + sr * 0.45], fill=SCREW_CROSS, width=w)
    return img


def write_ico(path, images_by_size):
    """Multi-size ICO with PNG payloads (Vista+). Uses our pre-drawn bitmaps."""
    import io
    import struct

    entries = []
    blobs = []
    for size in sorted(images_by_size):
        buf = io.BytesIO()
        images_by_size[size].save(buf, format="PNG")
        blobs.append(buf.getvalue())
        entries.append(size)
    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    directory = []
    for size, blob in zip(entries, blobs):
        w = 0 if size >= 256 else size
        h = 0 if size >= 256 else size
        directory.append(struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(blob), offset))
        offset += len(blob)
    path.write_bytes(header + b"".join(directory) + b"".join(blobs))


def main():
    here = Path(__file__).resolve().parent
    images = {}
    for size in SIZES:
        img = draw_db9(size)
        path = here / f"serial_icon_{size}.png"
        img.save(path, format="PNG")
        images[size] = img
        print("wrote", path)
    hero = here / "serial_icon.png"
    images[256].save(hero, format="PNG")
    print("wrote", hero)
    ico = here / "serial_icon.ico"
    write_ico(ico, images)
    print("wrote", ico, "bytes", ico.stat().st_size)


if __name__ == "__main__":
    main()
