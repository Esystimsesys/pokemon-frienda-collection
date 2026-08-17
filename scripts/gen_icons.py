#!/usr/bin/env python3
"""ホーム画面に置くアイコンを作る。外部ライブラリなしでPNGを書き出す。

ピックそのものをモチーフにしている（丸い角の本体・上半分の画面・下の丸いくぼみ）。
iOSはアイコンを自分で角丸にするので、背景は端まで塗りつぶす。
"""

import math
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "public"

BG = (43, 108, 176)  # アプリのあお
BODY = (246, 199, 68)  # ピックのきいろ
BODY_EDGE = (214, 162, 32)
SCREEN = (22, 50, 63)
BALL_OUTER = (255, 255, 255)
BALL_INNER = (43, 108, 176)
DISC = (222, 176, 46)

# 512基準で図形を置き、どのサイズにも同じ比率で拡大縮小する
BASE = 512
SS = 4  # アンチエイリアス用の倍率


def round_box(px: float, py: float, cx: float, cy: float, hw: float, hh: float, r: float) -> float:
    """角丸長方形の符号付き距離。負なら内側"""
    qx = abs(px - cx) - (hw - r)
    qy = abs(py - cy) - (hh - r)
    outside = math.hypot(max(qx, 0.0), max(qy, 0.0))
    return outside + min(max(qx, qy), 0.0) - r


def circle(px: float, py: float, cx: float, cy: float, r: float) -> float:
    return math.hypot(px - cx, py - cy) - r


def color_at(px: float, py: float) -> tuple[int, int, int]:
    """512基準の座標を受け取って色を返す。手前の図形から順に判定する"""
    if circle(px, py, 256, 200, 24) <= 0:
        return BALL_INNER
    if circle(px, py, 256, 200, 52) <= 0:
        return BALL_OUTER
    if round_box(px, py, 256, 206, 88, 106, 24) <= 0:
        return SCREEN
    if circle(px, py, 256, 366, 42) <= 0:
        return DISC
    if round_box(px, py, 256, 246, 114, 160, 44) <= 0:
        return BODY
    if round_box(px, py, 256, 246, 122, 168, 50) <= 0:
        return BODY_EDGE
    return BG


def render(size: int) -> bytearray:
    scale = BASE / (size * SS)
    px_of = [(i + 0.5) * scale for i in range(size * SS)]

    rows = bytearray()
    for y in range(size):
        row = bytearray()
        for x in range(size):
            r = g = b = 0
            for sy in range(SS):
                for sx in range(SS):
                    c = color_at(px_of[x * SS + sx], px_of[y * SS + sy])
                    r += c[0]
                    g += c[1]
                    b += c[2]
            n = SS * SS
            row += bytes((r // n, g // n, b // n))
        rows += b"\x00" + row
    return rows


def write_png(path: Path, size: int, raw: bytearray) -> None:
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)
    print(f"{path.relative_to(OUT.parent)}  {size}x{size}  {len(png) / 1024:.1f}KB")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for size, name in [(512, "icon-512.png"), (192, "icon-192.png"), (180, "apple-touch-icon.png"), (32, "favicon.png")]:
        write_png(OUT / name, size, render(size))


if __name__ == "__main__":
    main()
