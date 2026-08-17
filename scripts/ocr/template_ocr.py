#!/usr/bin/env python3
"""公式ピック画像のステータス欄の数字を、テンプレート照合で読み取る。

Apple Vision の文字分類器は digit-shape の混同（8→B, 6→B, 0→D など）を
起こすが、公式画像は写真ではなく単一フォントでレンダリングされたビットマップ
なので、数字グリフを切り出して既知のテンプレートと突き合わせれば決定的に
判別できる。このモジュールはその切り出しと照合を担当する。

処理の流れ:
  1. 裏面のステータス欄を探す。HPカプセルの緑は他の要素と色が被りにくいので、
     緑の連結成分のうちカプセル形状（約104x44）のものをアンカーにする。
  2. アンカーからの相対オフセットで5つのカプセル領域を切り出す。レイアウトは
     全958枚で共通で、スケールは標準（カプセル幅104〜107px）と、わざ欄が多い
     8枚だけで使われる約0.8倍の2種類。スケールはアンカーの実測幅から求める。
  3. カプセル内の白画素（min(R,G,B)が高い画素）を連結成分に分け、
     ラベル（HP/ATK/...）より下にあるものだけを数字グリフとして拾う。
  4. 各グリフを固定サイズに正規化し、テンプレートとの正規化相互相関(NCC)で
     照合する。一致度が低いものは None（読めなかった）として返す。

テンプレートは build_templates.py が picks.json の既存280件から自動生成し、
digit_templates.json に保存する（種を人手で決め打ちしない）。
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATES_PATH = Path(__file__).resolve().parent / "digit_templates.json"

FIELDS = ["hp", "atk", "def", "spatk", "spdef"]

# --- ステータス欄の幾何 ---------------------------------------------------
# HPカプセル（緑）の左上を原点(0,0)とした、各カプセルの相対矩形。
# 実測値: HPカプセルは幅104〜107/高さ44〜46、2段目は48px下・x方向に102ずれる。
# わざ欄が多い一部のピック（3-1-004 など8枚）はステータス欄だけ約0.8倍で
# 描かれているので、アンカーの実測幅からスケールを出して全オフセットを掛ける。
REF_CAPSULE_W = 105.5
CAPSULE_RECTS: dict[str, tuple[int, int, int, int]] = {
    "hp": (0, 0, 105, 46),
    "atk": (102, 0, 207, 46),
    "def": (207, 0, 318, 46),
    "spatk": (102, 48, 211, 95),
    "spdef": (211, 48, 318, 95),
}

# 緑アンカーを探す範囲（裏面の座標。全958枚の実測レンジに余裕を持たせた）
ANCHOR_SEARCH = (330, 1150, 540, 1400)
# 緑カプセルとして許容する連結成分のサイズ（標準104x44 / 縮小版83x35）
ANCHOR_W_RANGE = (75, 115)
ANCHOR_H_RANGE = (30, 52)
ANCHOR_ASPECT_RANGE = (2.0, 2.7)

# 白（数字）とみなす閾値。min(R,G,B) が高い＝どのチャンネルも明るい＝白。
WHITE_THRESHOLD = 165
# グリフとして採用する連結成分の条件（いずれも標準スケールでの値。scaleを掛けて使う）
GLYPH_MIN_PIXELS = 30
GLYPH_MIN_H = 14
GLYPH_MIN_W = 5
# 単独の数字の最大幅（実測は11〜18px）。これを超えたら隣の数字とくっついているので割る。
GLYPH_MAX_W = 23
# ラベル文字（HP/ATK/SP.DEF など）は上段にあるので、重心yで切り分ける
GLYPH_MIN_CENTER_Y = 16

# 正規化後のグリフサイズ
NORM_W, NORM_H = 20, 28


# --- 連結成分 -------------------------------------------------------------
def connected_components(mask: bytearray, w: int, h: int, min_pixels: int) -> list[tuple[int, int, int, int, int]]:
    """4近傍の連結成分を (x0, y0, x1, y1, 画素数) のリストで返す。"""
    seen = bytearray(w * h)
    out: list[tuple[int, int, int, int, int]] = []
    for sy in range(h):
        row = sy * w
        for sx in range(w):
            i = row + sx
            if not mask[i] or seen[i]:
                continue
            seen[i] = 1
            stack = [i]
            x0 = x1 = sx
            y0 = y1 = sy
            n = 0
            while stack:
                j = stack.pop()
                jy, jx = divmod(j, w)
                n += 1
                if jx < x0:
                    x0 = jx
                elif jx > x1:
                    x1 = jx
                if jy > y1:
                    y1 = jy
                if jx > 0 and mask[j - 1] and not seen[j - 1]:
                    seen[j - 1] = 1
                    stack.append(j - 1)
                if jx < w - 1 and mask[j + 1] and not seen[j + 1]:
                    seen[j + 1] = 1
                    stack.append(j + 1)
                if jy > 0 and mask[j - w] and not seen[j - w]:
                    seen[j - w] = 1
                    stack.append(j - w)
                if jy < h - 1 and mask[j + w] and not seen[j + w]:
                    seen[j + w] = 1
                    stack.append(j + w)
            if n >= min_pixels:
                out.append((x0, y0, x1, y1, n))
    return out


# --- ステータス欄の位置決め ------------------------------------------------
def find_anchor(img: Image.Image) -> tuple[int, int, float] | None:
    """HPカプセル（緑）の左上座標とスケールを返す。見つからなければ None。"""
    sx0, sy0, sx1, sy1 = ANCHOR_SEARCH
    crop = img.crop((sx0, sy0, sx1, sy1))
    w, h = crop.size
    px = crop.load()
    mask = bytearray(w * h)
    for y in range(h):
        row = y * w
        for x in range(w):
            r, g, b = px[x, y]
            # 緑カプセル: 緑が他チャンネルより十分強い
            if g > r + 40 and g > b + 30 and g > 90:
                mask[row + x] = 1

    best: tuple[int, int, float] | None = None
    best_area = 0
    for x0, y0, x1, y1, n in connected_components(mask, w, h, 1000):
        cw, ch = x1 - x0 + 1, y1 - y0 + 1
        if not (ANCHOR_W_RANGE[0] <= cw <= ANCHOR_W_RANGE[1]):
            continue
        if not (ANCHOR_H_RANGE[0] <= ch <= ANCHOR_H_RANGE[1]):
            continue
        if not (ANCHOR_ASPECT_RANGE[0] <= cw / ch <= ANCHOR_ASPECT_RANGE[1]):
            continue
        # 塗りつぶし率が高い（カプセルは角丸の矩形）
        if n < cw * ch * 0.60:
            continue
        # 実測幅は同じレイアウトでも±1pxぶれるので、0.05刻みに丸めてから使う
        cand = (sx0 + x0, sy0 + y0, round(cw / REF_CAPSULE_W * 20) / 20)
        # 緑のカプセル形は他にもあり得るので、右隣がATK/DEF（赤系）・下段が
        # SP.ATK/SP.DEF（青）になっていることまで確認して本物を選ぶ
        if not _verify_layout(img, cand):
            continue
        if n > best_area:
            best, best_area = cand, n
    return best


def _fill_ratio(img: Image.Image, rect: tuple[int, int, int, int], kind: str) -> float:
    """矩形内で指定した色みの画素が占める割合。"""
    crop = img.crop(rect)
    w, h = crop.size
    if w < 4 or h < 4:
        return 0.0
    px = crop.load()
    hit = total = 0
    for y in range(0, h, 3):
        for x in range(0, w, 3):
            r, g, b = px[x, y]
            total += 1
            if kind == "warm" and r >= max(g, b) and r - g > 60:
                hit += 1
            elif kind == "blue" and b > r + 50 and b > g + 20 and b > 60:
                hit += 1
    return hit / total if total else 0.0


def _verify_layout(img: Image.Image, anchor: tuple[int, int, float]) -> bool:
    """アンカー候補から求めた位置に、ATK/DEF段（赤系）とSP段（青）があるか確かめる。"""
    ax, ay, s = anchor
    warm = _fill_ratio(img, (ax + round(110 * s), ay + round(6 * s), ax + round(315 * s), ay + round(40 * s)), "warm")
    blue = _fill_ratio(img, (ax + round(110 * s), ay + round(54 * s), ax + round(315 * s), ay + round(90 * s)), "blue")
    return warm > 0.5 and blue > 0.5


# --- グリフ切り出し --------------------------------------------------------
def _split_wide(
    mask: bytearray, w: int, x0: int, y0: int, x1: int, y1: int, scale: float
) -> list[tuple[int, int]]:
    """幅が広すぎる成分を、白画素の列和が最小の列で再帰的に2分割する。"""
    min_w = max(3, round(GLYPH_MIN_W * scale))
    if x1 - x0 + 1 <= round(GLYPH_MAX_W * scale):
        return [(x0, x1)]
    lo, hi = x0 + min_w, x1 - min_w
    if lo > hi:
        return [(x0, x1)]
    best_col, best_sum = lo, None
    for x in range(lo, hi + 1):
        s = sum(mask[y * w + x] for y in range(y0, y1 + 1))
        if best_sum is None or s < best_sum:
            best_sum, best_col = s, x
    return _split_wide(mask, w, x0, y0, best_col - 1, y1, scale) + _split_wide(
        mask, w, best_col, y0, x1, y1, scale
    )


def _tight_box(
    mask: bytearray, w: int, x0: int, y0: int, x1: int, y1: int, scale: float
) -> tuple[int, int, int, int] | None:
    """指定矩形内の白画素に外接する矩形を返す。小さすぎるものは None。"""
    nx0, ny0, nx1, ny1 = None, None, None, None
    for y in range(y0, y1 + 1):
        row = y * w
        for x in range(x0, x1 + 1):
            if mask[row + x]:
                if nx0 is None or x < nx0:
                    nx0 = x
                if nx1 is None or x > nx1:
                    nx1 = x
                if ny0 is None:
                    ny0 = y
                ny1 = y
    if nx0 is None:
        return None
    if nx1 - nx0 + 1 < GLYPH_MIN_W * scale or ny1 - ny0 + 1 < GLYPH_MIN_H * scale:
        return None
    return nx0, ny0, nx1, ny1



def extract_glyphs(img: Image.Image, anchor: tuple[int, int, float], field: str) -> list[list[float]] | None:
    """指定カプセル内の数字グリフを左から順に、正規化済みベクトルのリストで返す。

    白画素の連結成分のうち、ラベル文字より下にあるものだけを数字とみなす。
    切り出しに失敗した（それらしい成分が無い）場合は None。
    """
    ax, ay, scale = anchor
    dx0, dy0, dx1, dy1 = (round(v * scale) for v in CAPSULE_RECTS[field])
    crop = img.crop((ax + dx0, ay + dy0, ax + dx1, ay + dy1))
    w, h = crop.size
    px = crop.load()

    # 白さ = min(R,G,B)。カプセル背景は必ずどれかのチャンネルが暗いので0近くになる。
    white = bytearray(w * h)
    mask = bytearray(w * h)
    for y in range(h):
        row = y * w
        for x in range(w):
            r, g, b = px[x, y]
            v = r if r < g else g
            if b < v:
                v = b
            white[row + x] = v
            if v >= WHITE_THRESHOLD:
                mask[row + x] = 1

    comps = []
    min_px = max(10, round(GLYPH_MIN_PIXELS * scale * scale))
    for x0, y0, x1, y1, n in connected_components(mask, w, h, min_px):
        gw, gh = x1 - x0 + 1, y1 - y0 + 1
        if gh < GLYPH_MIN_H * scale or gw < GLYPH_MIN_W * scale:
            continue
        if (y0 + y1) / 2 < GLYPH_MIN_CENTER_Y * scale:
            continue  # ラベル文字（上段）
        comps.append((x0, y0, x1, y1))
    if not comps:
        return None

    # 隣の数字とくっついた成分（例: "44"）を、白画素が最も薄い列で割る
    split_comps: list[tuple[int, int, int, int]] = []
    for x0, y0, x1, y1 in comps:
        for sx0, sx1 in _split_wide(mask, w, x0, y0, x1, y1, scale):
            box = _tight_box(mask, w, sx0, y0, sx1, y1, scale)
            if box is not None:
                split_comps.append(box)
    if not split_comps:
        return None
    comps = sorted(split_comps, key=lambda c: c[0])

    glyphs = []
    for x0, y0, x1, y1 in comps:
        gw, gh = x1 - x0 + 1, y1 - y0 + 1
        patch = Image.new("L", (gw, gh))
        patch.putdata([white[(y0 + yy) * w + (x0 + xx)] for yy in range(gh) for xx in range(gw)])
        norm = patch.resize((NORM_W, NORM_H), Image.BILINEAR)
        data = list(norm.getdata())
        glyphs.append([v / 255.0 for v in data])
    return glyphs


def extract_all(path: Path) -> tuple[dict[str, list[list[float]]], str | None]:
    """1枚の画像から5項目ぶんのグリフ列を取り出す。(結果, エラー理由) を返す。"""
    try:
        img = Image.open(path).convert("RGB")
    except Exception:
        return {}, "load_failed"
    anchor = find_anchor(img)
    if anchor is None:
        return {}, "anchor_not_found"
    out: dict[str, list[list[float]]] = {}
    for f in FIELDS:
        g = extract_glyphs(img, anchor, f)
        if g is not None:
            out[f] = g
    return out, None


# --- 照合 -----------------------------------------------------------------
def _prepare(vec: list[float]) -> tuple[list[float], float]:
    """NCC用に平均を引いてノルムを添えて返す。"""
    n = len(vec)
    mean = sum(vec) / n
    centered = [v - mean for v in vec]
    norm = sum(v * v for v in centered) ** 0.5
    return centered, (norm if norm > 1e-9 else 1e-9)


class TemplateMatcher:
    """digit_templates.json を読み込んでグリフを数字に照合する。"""

    def __init__(self, templates: dict[str, list[float]]):
        self.digits = sorted(templates.keys())
        self.prepared = {d: _prepare(templates[d]) for d in self.digits}

    @classmethod
    def load(cls, path: Path = TEMPLATES_PATH) -> "TemplateMatcher":
        data = json.loads(path.read_text(encoding="utf-8"))
        if (data["norm_w"], data["norm_h"]) != (NORM_W, NORM_H):
            raise SystemExit(
                "テンプレートの正規化サイズがコード側と違う。build_templates.py で作り直すこと"
            )
        return cls(data["templates"])

    def match_glyph(self, glyph: list[float]) -> tuple[str, float, float]:
        """(最も近い数字, NCCスコア, 2位との差) を返す。"""
        gc, gn = _prepare(glyph)
        scores = []
        for d in self.digits:
            tc, tn = self.prepared[d]
            s = sum(a * b for a, b in zip(gc, tc)) / (gn * tn)
            scores.append((s, d))
        scores.sort(reverse=True)
        best_s, best_d = scores[0]
        margin = best_s - scores[1][0]
        return best_d, best_s, margin

    def read_number(
        self, glyphs: list[list[float]], min_score: float, min_margin: float
    ) -> tuple[int | None, str]:
        """グリフ列を整数に変換する。自信が無ければ (None, 理由)。"""
        if not glyphs or len(glyphs) > 3:
            return None, "glyph_count"
        chars = []
        for g in glyphs:
            d, s, m = self.match_glyph(g)
            if s < min_score:
                return None, "low_score"
            if m < min_margin:
                return None, "low_margin"
            chars.append(d)
        if chars[0] == "0":
            return None, "leading_zero"
        return int("".join(chars)), "ok"
