"""Draw the app icons (a basketball) as PNG files with the standard library only.

    python tools/make_icons.py

Writes assets/icon-192.png, assets/icon-512.png and assets/icon-maskable-512.png.
The ball sits inside the central 68% of the square, so the same drawing is safe
for "maskable" icons, which Android crops to a circle or rounded square.
"""
from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

BG = (20, 33, 61)        # deep navy
BALL = (235, 104, 52)    # orange
SEAM = (20, 33, 61)
SS = 3                   # supersampling per axis, for smooth edges


def ball_color(x: float, y: float, r: float):
    """Colour at (x, y) relative to the ball centre; radius r. None = background."""
    d = math.hypot(x, y)
    if d > r:
        return None
    w = r * 0.045  # half the seam thickness
    seam = (
        abs(x) < w or abs(y) < w
        or abs(math.hypot(x - 1.25 * r, y) - 0.85 * r) < w
        or abs(math.hypot(x + 1.25 * r, y) - 0.85 * r) < w
    )
    return SEAM if seam else BALL


def render(size: int) -> bytes:
    r = size * 0.34
    c = size / 2.0
    rows = []
    for py in range(size):
        row = bytearray([0])  # PNG filter type 0
        for px in range(size):
            acc = [0, 0, 0]
            for sy in range(SS):
                for sx in range(SS):
                    x = px + (sx + 0.5) / SS - c
                    y = py + (sy + 0.5) / SS - c
                    col = ball_color(x, y, r) or BG
                    acc[0] += col[0]; acc[1] += col[1]; acc[2] += col[2]
            n = SS * SS
            row += bytes((acc[0] // n, acc[1] // n, acc[2] // n))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit RGB
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "assets"
    out.mkdir(exist_ok=True)
    for name, size in (("icon-192.png", 192), ("icon-512.png", 512), ("icon-maskable-512.png", 512)):
        (out / name).write_bytes(render(size))
        print("wrote", out / name)
