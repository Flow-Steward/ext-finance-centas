#!/usr/bin/env python3
"""Draw icon.png: a neutral placeholder (a document sheet and a coin), no brand mark.

Centas publishes no logo of its own (see BRANDING.md), so the icon is drawn here
from plain shapes with the standard library only. Run from the bundle root:

    python3 tests/reference/make_icon.py
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

SIZE = 128
SCALE = 4  # supersampling for smooth edges
BACKGROUND = (31, 94, 120)
SHEET = (255, 255, 255)
RULE = (31, 94, 120)
COIN = (232, 176, 58)
COIN_EDGE = (190, 132, 30)


def _inside_rounded(
    x: float, y: float, left: float, top: float, right: float, bottom: float, radius: float
) -> bool:
    if not (left <= x <= right and top <= y <= bottom):
        return False
    cx = min(max(x, left + radius), right - radius)
    cy = min(max(y, top + radius), bottom - radius)
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius**2


def _colour(x: float, y: float) -> tuple[int, int, int, int]:
    """The colour of one point of the 128 × 128 picture (transparent outside)."""
    if not _inside_rounded(x, y, 4, 4, 124, 124, 24):
        return (0, 0, 0, 0)
    dx, dy = x - 84, y - 84
    if dx * dx + dy * dy <= 24**2:
        return (*COIN, 255) if dx * dx + dy * dy <= 19**2 else (*COIN_EDGE, 255)
    if _inside_rounded(x, y, 30, 22, 86, 104, 6):
        for top in (38, 52, 66):
            if top <= y <= top + 5 and 40 <= x <= 76:
                return (*RULE, 255)
        return (*SHEET, 255)
    return (*BACKGROUND, 255)


def pixels() -> list[bytes]:
    rows = []
    for py in range(SIZE):
        row = bytearray([0])  # filter type 0
        for px in range(SIZE):
            total = [0, 0, 0, 0]
            for sy in range(SCALE):
                for sx in range(SCALE):
                    r, g, b, a = _colour(px + (sx + 0.5) / SCALE, py + (sy + 0.5) / SCALE)
                    total[0] += r * a
                    total[1] += g * a
                    total[2] += b * a
                    total[3] += a
            alpha = total[3] // (SCALE * SCALE)
            if total[3]:
                row += bytes(
                    (total[0] // total[3], total[1] // total[3], total[2] // total[3], alpha)
                )
            else:
                row += bytes((0, 0, 0, 0))
        rows.append(bytes(row))
    return rows


def png(rows: list[bytes]) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
        + chunk(b"IEND", b"")
    )


def main() -> None:
    Path(__file__).resolve().parents[2].joinpath("icon.png").write_bytes(png(pixels()))


if __name__ == "__main__":
    main()
