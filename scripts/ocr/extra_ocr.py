#!/usr/bin/env python3
"""公式ピック画像から、すばやさ（裏面）とポケエネ（表面）を読み取る。

この2つだけがファンサイト由来のままだったので、券面から直接読めるようにしたもの。
考え方は header_ocr.py / template_ocr.py と同じで、確実に見つかるものをアンカーに
相対座標で切り出し、正解データから作ったテンプレートとNCCで突き合わせる。

--- すばやさ（裏面）-------------------------------------------------------
★のグレードとまったく同じ仕組み。矢印型のゲージが5枠あり、
うまっている数（＝きいろい枠の数）がそのまま値になる。
★とちがって左づめなので、左から連続して何枠うまっているかを数える。

  1. アンカーは裏面のQRコード左上の切り出しシンボル（header_ocr と同じもの）。
     倍率もそこから求める。わざ欄が多い8枚だけ約0.79倍。
  2. アンカーからの相対座標で5枠を切り出す。実測でゲージは
     アンカー左上から x=-42〜+206 / y=+167〜+196 の位置にあり、1枠は49.3px。
     枠どうしは重ならない（速さ1のきいろは x=+7 で終わり、2は+56、3は+106…）。
  3. ★と同じ「きいろさ」に変換してからNCCで照合する。うまっていない枠は
     同じ形のはいいろの矢印なので、きいろさにするとほぼ真っ平らになり、
     一致度がはっきり下がる。

--- ポケエネ（表面）-----------------------------------------------------
表面には「ポケエネ ###」と印字されている。裏面とちがって、表面は
カードの向き（たて／よこ）も大きさもばらばらで、QRコードのような使える
アンカーが無い。そこで幾何ではなく、数字そのものの見た目で見つける。

数字は必ず「明るいグリフ＋太い黒フチ」で描かれている。塗りはカードによって
きんいろだったりホロのにじだったりするが、「まわりが黒くて中が明るい」ことと
字の形は共通なので、そこを手がかりにする。

  1. 表面の決まった範囲（実測から決めた ENERGY_WIN）だけを見る。
  2. 明るい画素（V=max(R,G,B) がしきい値以上）の連結成分を拾い、
     まわりが黒フチで囲まれているものだけを残す。塗りの明るさはカードで
     かなり違うので、しきい値を何とおりか変えて全部の案を出す。
  3. 高さがそろっていて横にとなりあっているものを1行としてまとめる。
     となりの数字とくっついた成分は、幅がそろうように割る。
  4. 行の候補それぞれをテンプレートと突き合わせ、いちばん合う行を採る。
     字体は裏面と別（大きさも太さもちがう）なので、テンプレートも
     表面用に作り直している（build_extra_templates.py）。
     この字体は「5」と「6」の形がほとんど同じでNCCだけでは見分けられないので、
     「囲まれた空き」がいくつあるかも合わせて見る（_hole_count）。
  5. 一致度が低いものは None（読めなかった）として返す。推測はしない。
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from header_ocr import find_anchor, ncc, prepare, yellowness
from template_ocr import connected_components

ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATES_PATH = Path(__file__).resolve().parent / "extra_templates.json"


# =========================================================================
# すばやさ（裏面）
# =========================================================================
# アンカー（QRコード左上）からの相対座標。倍率1.0のときの値。
SPEED_LEFT = -42.0      # いちばん左の枠の左はし
SPEED_PITCH = 49.3      # 枠のピッチ。実測（1枠ぶんの右はしが 7/56/106/155/206）から
SPEED_SLOTS = 5
SPEED_BOX_W = 49
SPEED_BOX_TOP = 167
SPEED_BOX_H = 30
# 正規化サイズ。矢印は横長なので横を広く取る。
SPEED_NORM_W, SPEED_NORM_H = 24, 16
# 切り出し位置のずれを直すときに探す範囲（px）。★と同じく実測のずれは±3以内。
SPEED_ALIGN_RADIUS = 4


def speed_patch(
    img: Image.Image, anchor: tuple[int, int, float], slot: int, dx: int = 0, dy: int = 0
) -> list[float]:
    """すばやさゲージの左から slot 番目の枠を、きいろさのベクトルにする。"""
    ax, ay, s = anchor
    left = ax + round((SPEED_LEFT + SPEED_PITCH * slot) * s) + dx
    top = ay + round(SPEED_BOX_TOP * s) + dy
    crop = img.crop((
        left, top,
        left + max(1, round(SPEED_BOX_W * s)),
        top + max(1, round(SPEED_BOX_H * s)),
    ))
    crop = crop.resize((SPEED_NORM_W, SPEED_NORM_H), Image.BILINEAR)
    return [yellowness(*p) for p in crop.getdata()]


def extract_speed(
    img: Image.Image, anchor: tuple[int, int, float], generic: list[float] | None
) -> tuple[list[list[float]], tuple[int, int]]:
    """5枠ぶんのベクトルと、使った位置合わせのずれを返す。

    いちばん左の枠は必ずうまっている（すばやさは1以上）ので、そこを手がかりに
    ずれを求めてから5枠まとめて切り出す。
    """
    if generic is None:
        return [speed_patch(img, anchor, k) for k in range(SPEED_SLOTS)], (0, 0)
    g = prepare(generic)
    rng = range(-SPEED_ALIGN_RADIUS, SPEED_ALIGN_RADIUS + 1)
    best = max(
        (ncc(prepare(speed_patch(img, anchor, 0, dx, dy)), g), dx, dy)
        for dx in rng for dy in rng
    )
    dx, dy = best[1], best[2]
    return [speed_patch(img, anchor, k, dx, dy) for k in range(SPEED_SLOTS)], (dx, dy)


class SpeedMatcher:
    """すばやさゲージの枠ごとのテンプレートを持ち、うまっている数を数える。"""

    def __init__(self, slots: list[list[float]]):
        self.slots = [prepare(v) for v in slots]

    def match(self, patch: list[float], slot: int) -> float:
        return ncc(prepare(patch), self.slots[slot])

    def read_speed(
        self, patches: list[list[float]], min_score: float, max_score_absent: float
    ) -> tuple[int | None, str]:
        """左から見てうまっている枠を数える。判定が曖昧なら (None, 理由)。

        ★は右づめだったが、すばやさは左づめ。とちゅうが空いている／
        どっちつかずのスコアが出た場合は読めなかった扱いにする。
        """
        count = 0
        for slot, patch in enumerate(patches):
            s = self.match(patch, slot)
            if s >= min_score:
                if count != slot:
                    return None, "not_contiguous"
                count += 1
            elif s > max_score_absent:
                return None, "ambiguous"
        if count == 0:
            return None, "no_gauge"
        return count, "ok"


# =========================================================================
# ポケエネ（表面）
# =========================================================================
# 表面のうち、ポケエネの印字がありうる範囲。
# 全958枚での実測は x=343〜471 / y=506〜611（カードの向きも大きさも3とおりある）。
# それに余裕を持たせた。ここを広げるとまわりの絵柄まで数字の候補になってしまい、
# 読みまちがいも処理時間も増えるので、必要以上には広げないこと。
# 新しいだんでカードの作りが変わったら、ここが合っているか確かめること。
ENERGY_WIN = (325, 490, 510, 630)
# 明るいグリフとみなすしきい値（V = max(R,G,B)）。
# 塗りがカードによってかなり違う（きんいろ／ホロのにじ／ほとんど白）ので、
# ひとつのしきい値では字がつぶれたり欠けたりする。何とおりか試して、
# いちばん字らしく見える切り方をテンプレートに選ばせる。
ENERGY_BRIGHTS = (120, 145, 170, 200)
# 黒フチとみなすしきい値
ENERGY_DARK = 85
# グリフのまわりが黒フチで囲まれている割合の下限
ENERGY_RING_RATIO = 0.5
# グリフとして拾う大きさ。カードの大きさで20〜34pxまで変わる。
ENERGY_MIN_H, ENERGY_MAX_H = 16, 38
ENERGY_MIN_W = 5
# 単独の数字の幅は高さの0.30〜1.15倍（「1」だけ細い）。この範囲におさまるように
# くっついた成分を割る（_cut_plans）。
ENERGY_GLYPH_W_RATIO = (0.30, 1.15)
# 同じ行とみなす上下のずれ（px）
ENERGY_ROW_TOL = 3
# 正規化後のグリフサイズ。裏面（20x28）より字が太いので少し大きめに取る。
ENERGY_NORM_W, ENERGY_NORM_H = 20, 28


def _value_map(img: Image.Image) -> tuple[bytearray, int, int]:
    """探索範囲の明るさ V = max(R,G,B) を返す。"""
    crop = img.crop(ENERGY_WIN)
    w, h = crop.size
    px = crop.load()
    v = bytearray(w * h)
    for y in range(h):
        row = y * w
        for x in range(w):
            r, g, b = px[x, y]
            m = r if r > g else g
            if b > m:
                m = b
            v[row + x] = m
    return v, w, h


def _ring_dark(v: bytearray, w: int, h: int, box: tuple[int, int, int, int]) -> float:
    """グリフの外周2〜3px が黒フチで占められている割合。"""
    x0, y0, x1, y1 = box
    vals = []
    for x in range(max(0, x0 - 3), min(w, x1 + 4)):
        for y in (y0 - 3, y0 - 2, y1 + 2, y1 + 3):
            if 0 <= y < h:
                vals.append(v[y * w + x])
    for y in range(max(0, y0 - 3), min(h, y1 + 4)):
        for x in (x0 - 3, x0 - 2, x1 + 2, x1 + 3):
            if 0 <= x < w:
                vals.append(v[y * w + x])
    if not vals:
        return 0.0
    return sum(1 for t in vals if t < ENERGY_DARK) / len(vals)


def _column_profile(
    mask: bytearray, w: int, x0: int, y0: int, x1: int, y1: int
) -> list[int]:
    """成分の中の、列ごとの明るい画素の数。"""
    return [sum(mask[y * w + x] for y in range(y0, y1 + 1)) for x in range(x0, x1 + 1)]


def _cut_plans(
    prof: list[int], x0: int, gh: int
) -> list[list[tuple[int, int]]]:
    """1つの連結成分を1〜3個のグリフに割る案を、確からしい順に返す。

    となりあう数字は黒フチどうしがくっついて1つの成分になることがある。
    「いちばん暗い列で割る」をくり返すやり方だと、「0」のまん中の空きのように
    字の内側のほうが暗いときにそこで割ってしまうので、割る数ごとに
    「どの数字も同じくらいの幅になる」という条件つきで総当たりして決める。
    幅の条件だけでは決めきれないので、案を複数返してテンプレートに選ばせる。
    """
    total = len(prof)
    min_w = max(4, round(gh * ENERGY_GLYPH_W_RATIO[0]))
    max_w = max(min_w + 1, round(gh * ENERGY_GLYPH_W_RATIO[1]))
    plans: list[list[tuple[int, int]]] = []

    if total <= max_w:
        plans.append([(x0, x0 + total - 1)])
    # 2分割
    if 2 * min_w <= total <= 2 * max_w:
        best = None
        for c in range(min_w, total - min_w + 1):
            if not (min_w <= c <= max_w and min_w <= total - c <= max_w):
                continue
            cost = prof[c - 1] + prof[c]
            if best is None or cost < best[0]:
                best = (cost, c)
        if best:
            c = best[1]
            plans.append([(x0, x0 + c - 1), (x0 + c, x0 + total - 1)])
    # 3分割
    if 3 * min_w <= total <= 3 * max_w:
        best = None
        for c1 in range(min_w, total - 2 * min_w + 1):
            if c1 > max_w:
                break
            for c2 in range(c1 + min_w, total - min_w + 1):
                if c2 - c1 > max_w or total - c2 > max_w:
                    continue
                cost = prof[c1 - 1] + prof[c1] + prof[c2 - 1] + prof[c2]
                if best is None or cost < best[0]:
                    best = (cost, c1, c2)
        if best:
            _c, c1, c2 = best
            plans.append([
                (x0, x0 + c1 - 1), (x0 + c1, x0 + c2 - 1), (x0 + c2, x0 + total - 1),
            ])
    return plans


def _tight_box(
    mask: bytearray, w: int, x0: int, y0: int, x1: int, y1: int
) -> tuple[int, int, int, int] | None:
    """指定矩形内の明るい画素に外接する矩形。小さすぎるものは None。"""
    nx0 = ny0 = nx1 = ny1 = None
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
    if nx0 is None or nx1 - nx0 + 1 < ENERGY_MIN_W:
        return None
    return nx0, ny0, nx1, ny1


def _hole_count(mask: bytearray, w: int, box: tuple[int, int, int, int]) -> int:
    """グリフの中にある「囲まれた空き」の数を数える。

    この字体の「5」と「6」は、下半分の左のたてぼうがあるかどうかしか違わない。
    形を並べて重ねる照合（NCC）だと差が0.005しか出ず、まず見分けられない。
    ところが「5」の下の空きは左に開いていて、「6」の下の空きは閉じている。
    閉じた空きがいくつあるかは、にじんでいても数えまちがえにくい決め手になる。
    （0/4/6/9は1つ、8は2つ、1/2/3/5/7は0。どの数字がいくつかは
    　テンプレートを作るときに教師サンプルから数えて覚える。）
    """
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    if bw < 3 or bh < 3:
        return 0
    # グリフの中の暗い画素
    dark = bytearray(bw * bh)
    for yy in range(bh):
        row = yy * bw
        src = (y0 + yy) * w + x0
        for xx in range(bw):
            if not mask[src + xx]:
                dark[row + xx] = 1
    # 外側とつながっている暗い画素を消すと、囲まれた空きだけが残る
    stack = []
    for xx in range(bw):
        for yy in (0, bh - 1):
            i = yy * bw + xx
            if dark[i]:
                dark[i] = 0
                stack.append(i)
    for yy in range(bh):
        for xx in (0, bw - 1):
            i = yy * bw + xx
            if dark[i]:
                dark[i] = 0
                stack.append(i)
    while stack:
        i = stack.pop()
        iy, ix = divmod(i, bw)
        for jx, jy in ((ix - 1, iy), (ix + 1, iy), (ix, iy - 1), (ix, iy + 1)):
            if 0 <= jx < bw and 0 <= jy < bh:
                j = jy * bw + jx
                if dark[j]:
                    dark[j] = 0
                    stack.append(j)
    # にじみで開いた1〜2画素の穴は数えない
    min_hole = max(4, round(bw * bh * 0.012))
    return sum(1 for c in connected_components(dark, bw, bh, min_hole))


def _normalize(mask: bytearray, w: int, box: tuple[int, int, int, int]) -> list[float]:
    """グリフを固定サイズに正規化したベクトルにする。

    明るさの生の値ではなく、明るいかどうかの2値を渡す。表面の数字の塗りは
    カードによってきんいろだったりホロのにじ（上が青、下がきんいろ）だったりして、
    生の明るさのままだと塗りのちがいがそのまま照合のじゃまになる。
    2値にすれば残るのは字の形だけになる。
    """
    x0, y0, x1, y1 = box
    gw, gh = x1 - x0 + 1, y1 - y0 + 1
    patch = Image.new("L", (gw, gh))
    patch.putdata([255 if mask[(y0 + yy) * w + (x0 + xx)] else 0 for yy in range(gh) for xx in range(gw)])
    norm = patch.resize((ENERGY_NORM_W, ENERGY_NORM_H), Image.BILINEAR)
    return [t / 255.0 for t in norm.getdata()]


def energy_rows(img: Image.Image) -> list[dict]:
    """表面から、数字の行になりうるものを取り出す。

    返すのは {"box": 行の位置, "boxes": 数字ごとの位置, "glyphs": 正規化済みベクトル}
    の並び。明るさの切り方も、となりの数字とくっついた成分の割り方も
    ひととおりには決まらないので、同じ場所について複数の案を返す。
    どれを採るかはテンプレートに決めさせる。
    """
    v, w, h = _value_map(img)
    seen: set[tuple] = set()
    rows: list[dict] = []
    for threshold in ENERGY_BRIGHTS:
        mask = bytearray(1 if t >= threshold else 0 for t in v)
        for r in _rows_for_mask(v, mask, w, h):
            key = tuple(r["boxes"])
            if key in seen:
                continue  # ちがうしきい値で同じ切り出しになったもの
            seen.add(key)
            rows.append(r)
    rows.sort(key=lambda r: (r["box"][1], r["box"][0], len(r["glyphs"])))
    return rows


def _rows_for_mask(v: bytearray, mask: bytearray, w: int, h: int) -> list[dict]:
    """ひとつのしきい値で切ったマスクから、数字の行の案を作る。"""
    # 黒フチに囲まれた、それらしい大きさの明るい成分だけを残す
    cands: list[tuple[int, int, int, int]] = []
    for x0, y0, x1, y1, _n in connected_components(mask, w, h, 25):
        gh, gw = y1 - y0 + 1, x1 - x0 + 1
        if not (ENERGY_MIN_H <= gh <= ENERGY_MAX_H):
            continue
        if gw < ENERGY_MIN_W or gw > gh * 3.6:
            continue
        if _ring_dark(v, w, h, (x0, y0, x1, y1)) < ENERGY_RING_RATIO:
            continue
        cands.append((x0, y0, x1, y1))
    if not cands:
        return []

    # 上下の位置がそろっていて、かつ横にとなりあっているものを1行にまとめる。
    # 上下だけで見ると、ずっと右にある★や名前まで同じ行に入ってしまう。
    cands.sort(key=lambda c: (c[0], c[1]))
    groups: list[list[tuple[int, int, int, int]]] = []
    for c in cands:
        gh = c[3] - c[1] + 1
        for g in groups:
            last = g[-1]
            if abs(last[1] - c[1]) > ENERGY_ROW_TOL or abs(last[3] - c[3]) > ENERGY_ROW_TOL:
                continue
            if c[0] - last[2] > gh:
                continue  # 横に離れすぎ。別のもの
            g.append(c)
            break
        else:
            groups.append([c])

    rows: list[dict] = []
    for g in groups:
        gh = max(c[3] - c[1] + 1 for c in g)
        # 成分ごとに「1〜3個への割り方」の案を出し、その組み合わせを行の案にする
        per_comp: list[list[list[tuple[int, int]]]] = []
        for x0, y0, x1, y1 in g:
            prof = _column_profile(mask, w, x0, y0, x1, y1)
            plans = _cut_plans(prof, x0, gh)
            if not plans:
                per_comp = []
                break
            per_comp.append(plans)
        if not per_comp:
            continue

        combos: list[list[tuple[int, int]]] = [[]]
        for plans in per_comp:
            nxt: list[list[tuple[int, int]]] = []
            for base in combos:
                for pl in plans:
                    if len(base) + len(pl) <= 3:
                        nxt.append(base + pl)
            combos = nxt
            if not combos:
                break

        top, bottom = g[0][1], g[0][3]
        for spans in combos:
            if not spans:
                continue
            boxes = []
            for sx0, sx1 in spans:
                box = _tight_box(mask, w, sx0, top, sx1, bottom)
                if box is None:
                    boxes = []
                    break
                boxes.append(box)
            if not boxes:
                continue
            rows.append({
                "box": (
                    boxes[0][0] + ENERGY_WIN[0], top + ENERGY_WIN[1],
                    boxes[-1][2] + ENERGY_WIN[0], bottom + ENERGY_WIN[1],
                ),
                "height": gh,
                # 割らずに済んだ（成分がそのまま1文字だった）案かどうか。
                # テンプレートの種を集めるときは、この確実なぶんだけを使う。
                "clean": len(spans) == len(g),
                "boxes": [
                    (b[0] + ENERGY_WIN[0], b[1] + ENERGY_WIN[1],
                     b[2] + ENERGY_WIN[0], b[3] + ENERGY_WIN[1])
                    for b in boxes
                ],
                "holes": [_hole_count(mask, w, b) for b in boxes],
                "glyphs": [_normalize(mask, w, b) for b in boxes],
            })
    return rows


# 囲まれた空きの数が合わない数字に与える減点。5と6のNCCの差は0.005しか
# 出ないので、これくらい大きく引かないと決め手にならない。
HOLE_PENALTY = 0.20


class EnergyMatcher:
    """表面用の数字テンプレートを持ち、ポケエネの値を読む。"""

    def __init__(self, templates: dict[str, list[float]], holes: dict[str, int] | None = None):
        self.digits = sorted(templates)
        self.prepared = {d: prepare(templates[d]) for d in self.digits}
        # 数字ごとの「囲まれた空き」の数。教師サンプルから数えたものを渡す。
        self.holes = {d: int(v) for d, v in (holes or {}).items()}

    def match_glyph(self, glyph: list[float], holes: int | None = None) -> tuple[str, float, float]:
        """(最も近い数字, NCCスコア, 2位との差) を返す。

        囲まれた空きの数が合わない数字は減点する。減点前のNCCスコアを返すので、
        しきい値の意味は変わらない。
        """
        p = prepare(glyph)
        scored = []
        for d in self.digits:
            s = ncc(p, self.prepared[d])
            adj = s
            if holes is not None and d in self.holes and self.holes[d] != holes:
                adj -= HOLE_PENALTY
            scored.append((adj, s, d))
        scored.sort(reverse=True)
        return scored[0][2], scored[0][1], scored[0][0] - scored[1][0]

    def read_row(
        self, glyphs: list[list[float]], holes: list[int] | None = None
    ) -> tuple[int | None, float, float]:
        """1行を整数にする。(値, 一致度の最小, 2位との差の最小)。先頭が0なら None。"""
        chars = []
        worst = 1.0
        margin = 1.0
        for i, g in enumerate(glyphs):
            d, s, m = self.match_glyph(g, holes[i] if holes else None)
            chars.append(d)
            worst = min(worst, s)
            margin = min(margin, m)
        if chars[0] == "0":
            return None, worst, margin
        return int("".join(chars)), worst, margin

    def read_energy(
        self, rows: list[dict], min_score: float, min_margin: float, lo: int, hi: int
    ) -> tuple[int | None, str, dict | None]:
        """行の候補からポケエネを決める。自信が無ければ (None, 理由, None)。

        ポケエネの数字は、表面のうちいちばん上・いちばん左に出る
        「黒フチつきの数字の行」になる。まぎれこんだ行（だん番号のバッジ、
        絵柄の一部）は字の形が合わないので一致度で落ちる。
        """
        if not rows:
            return None, "no_row", None
        scored = []
        for r in rows:
            value, worst, margin = self.read_row(r["glyphs"], r.get("holes"))
            if value is None or not (lo <= value <= hi):
                continue
            scored.append((worst, margin, value, r))
        if not scored:
            return None, "no_candidate", None
        # いちばん確からしい行を採る。行の案は、同じ場所の割り方ちがいと、
        # 絵柄やバッジのまぎれこみの両方をふくむ。
        worst, margin, value, row = max(scored, key=lambda t: t[0])
        if worst < min_score:
            return None, "low_score", None
        if margin < min_margin:
            return None, "low_margin", None
        return value, "ok", {"score": worst, "margin": margin, "box": row["box"]}


# --- テンプレートの読み書き -------------------------------------------------
def load_templates(path: Path = TEMPLATES_PATH) -> dict:
    if not path.exists():
        raise SystemExit("先に npm run ocr:build-extra-templates を実行すること")
    return json.loads(path.read_text(encoding="utf-8"))


def open_image(path: Path) -> Image.Image | None:
    try:
        return Image.open(path).convert("RGB")
    except Exception:
        return None


def find_back_anchor(img: Image.Image) -> tuple[int, int, float] | None:
    """裏面のQRコード左上の切り出しシンボル。header_ocr と同じもの。"""
    return find_anchor(img)
