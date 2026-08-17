#!/usr/bin/env python3
"""公式ピック画像の裏面から、タイプアイコン・★の数・わざ欄1行目のタイプを読み取る。

ステータス欄の数字（template_ocr.py）と同じ考え方をヘッダーに広げたもの。
裏面のレイアウトは全958枚で共通なので、確実に見つかるものをアンカーにして
相対座標で切り出し、正解データから作ったテンプレートと突き合わせる。

処理の流れ:
  1. アンカーはQRコード左上の「切り出しシンボル」（黒い正方形のリング）。
     裏面には必ずあり、ステータス欄が無いプロモピックにも付いている。
     黒の連結成分のうち「正方形・中抜き・内側にもう1つ黒がある」を満たすものが
     1枚につき1つだけ見つかる（実測で958枚すべて成功）。
     実測サイズは57x57で、わざ欄が多い8枚だけ約0.79倍。倍率はここから求める。
  2. アンカーからの相対座標でタイプアイコン2枠・★5枠・わざ欄1行目を切り出す。
     切り出し位置は1〜4pxずれることがあり、アイコンは小さいのでこのずれが
     そのまま誤読になる。そこで全タイプのテンプレートを平均した「アイコンらしさ」の
     テンプレートに対していちばん合う位置を探してから切り出す（位置合わせ）。
  3. タイプアイコンはRGB、★はきいろさに変換してから、正規化相互相関(NCC)で
     テンプレートと照合する。NCCは平均を引いてからとるので、帯の地色が
     オレンジでもむらさきでも影響を受けにくい。
  4. 一致度が低いものは None（読めなかった）として返す。推測はしない。
     スペシャルピックは★のかわりに「スペシャル」の黄色い文字が入っているが、
     ★テンプレートとの一致度が0.72止まりなので★なしとして落ちる。

テンプレートは build_header_templates.py が picks.json の既存データから
自動生成する（種を人手で決め打ちしない）。
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from template_ocr import connected_components

ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATES_PATH = Path(__file__).resolve().parent / "header_templates.json"

# src/theme/pokemonTypes.ts の TYPE_ORDER と同じ並び・同じ表記
TYPE_ORDER = [
    "ノーマル", "ほのお", "みず", "でんき", "くさ", "こおり",
    "かくとう", "どく", "じめん", "ひこう", "エスパー", "むし",
    "いわ", "ゴースト", "ドラゴン", "あく", "はがね", "フェアリー",
]

# --- アンカー（QRコードの切り出しシンボル） ---------------------------------
# 実測レンジ x=355〜388 / y=875〜958 に余裕を持たせた探索範囲
ANCHOR_SEARCH = (320, 840, 460, 1010)
ANCHOR_REF_SIZE = 57.0
ANCHOR_SIZE_RANGE = (38, 64)
ANCHOR_FILL_RANGE = (0.40, 0.70)  # 中抜きのリングなので半分くらい

# --- ヘッダーの幾何（アンカー左上を原点(0,0)とした相対座標、倍率1.0のときの値）---
# タイプアイコン: 1つめの左上が(82,22)で36x36、2つめは43px右。
ICON_ORIGIN = (82, 22)
ICON_PITCH = 43
ICON_SIZE = 36
ICON_SLOTS = 2
ICON_INSET = 3  # 地色の写り込みを減らすため内側だけを使う
ICON_NORM = 18

# ★: 右づめ。右端が322、1つの幅21、ピッチ16、上下は28〜52。
STAR_RIGHT = 322
STAR_PITCH = 16
STAR_SLOTS = 5
STAR_BOX_W = 24
STAR_BOX_H = 30
STAR_BOX_TOP = 25
STAR_NORM = 16

# わざ欄1行目のタイプアイコン。ヘッダーのアイコンより大きい（50x50）ので別枠あつかい。
# 2行目以降はカードの作りによって位置も中身も変わる（ダイヤ型のわざマーク、
# メガシンカの行、「？」の行など）ので、ここでは1行目だけを読む。
MOVE_ORIGIN = (-35, 215)
MOVE_SIZE = 50
MOVE_INSET = 5

# 位置合わせで探すずれの範囲（px）。実測のずれは±3以内。
ALIGN_RADIUS = 4
# ★の位置合わせは、アイコンで求めたずれのまわりだけを探す。
# こうしないと「スペシャル」の黄色い文字がいちばん合う位置に吸い寄せられてしまう。
STAR_ALIGN_RADIUS = 2


# --- アンカー -------------------------------------------------------------
def find_anchor(img: Image.Image) -> tuple[int, int, float] | None:
    """QRコード左上の切り出しシンボルの (x, y, 倍率) を返す。見つからなければ None。"""
    sx0, sy0, sx1, sy1 = ANCHOR_SEARCH
    crop = img.crop((sx0, sy0, sx1, sy1))
    w, h = crop.size
    px = crop.load()
    mask = bytearray(w * h)
    for y in range(h):
        row = y * w
        for x in range(w):
            r, g, b = px[x, y]
            if r < 70 and g < 70 and b < 70:
                mask[row + x] = 1

    comps = connected_components(mask, w, h, 80)
    lo, hi = ANCHOR_SIZE_RANGE
    cands: list[tuple[int, int, float]] = []
    for x0, y0, x1, y1, n in comps:
        cw, ch = x1 - x0 + 1, y1 - y0 + 1
        if not (lo <= cw <= hi and lo <= ch <= hi):
            continue
        if abs(cw - ch) > 3:
            continue
        fill = n / (cw * ch)
        if not (ANCHOR_FILL_RANGE[0] <= fill <= ANCHOR_FILL_RANGE[1]):
            continue
        # リングの内側にもう1つ黒い成分（中央のブロック）があること
        inner = [
            c for c in comps
            if x0 < c[0] and c[2] < x1 and y0 < c[1] and c[3] < y1
            and 0.18 * cw <= c[2] - c[0] + 1 <= 0.55 * cw
        ]
        if not inner:
            continue
        cands.append((sx0 + x0, sy0 + y0, (cw + ch) / 2 / ANCHOR_REF_SIZE))
    # 見まちがいの余地を残さないよう、候補がちょうど1つのときだけ採用する
    if len(cands) != 1:
        return None
    return cands[0]


# --- 切り出し -------------------------------------------------------------
def icon_patch(
    img: Image.Image, anchor: tuple[int, int, float], slot: int, dx: int = 0, dy: int = 0
) -> list[float]:
    """タイプアイコン枠を切り出し、R・G・Bをこの順に並べたベクトルにする。

    チャンネルごとに固めておくのは、照合のときにチャンネル別に平均を引くため。
    そうしないと「べた塗りの帯の地色」だけで大きなばらつきが出てしまい、
    アイコンが無い枠でも高い相関が出てしまう。
    """
    ax, ay, s = anchor
    x0 = ICON_ORIGIN[0] + ICON_PITCH * slot + ICON_INSET
    y0 = ICON_ORIGIN[1] + ICON_INSET
    side = max(1, round((ICON_SIZE - ICON_INSET * 2) * s))
    left = ax + round(x0 * s) + dx
    top = ay + round(y0 * s) + dy
    crop = img.crop((left, top, left + side, top + side)).resize((ICON_NORM, ICON_NORM), Image.BILINEAR)
    data = list(crop.getdata())
    return [p[c] / 255.0 for c in range(3) for p in data]


def move_patch(
    img: Image.Image, anchor: tuple[int, int, float], dx: int = 0, dy: int = 0
) -> list[float]:
    """わざ欄1行目のタイプアイコンを、icon_patch と同じ形のベクトルにする。"""
    ax, ay, s = anchor
    side = max(1, round((MOVE_SIZE - MOVE_INSET * 2) * s))
    left = ax + round((MOVE_ORIGIN[0] + MOVE_INSET) * s) + dx
    top = ay + round((MOVE_ORIGIN[1] + MOVE_INSET) * s) + dy
    crop = img.crop((left, top, left + side, top + side)).resize((ICON_NORM, ICON_NORM), Image.BILINEAR)
    data = list(crop.getdata())
    return [p[c] / 255.0 for c in range(3) for p in data]


def icon_contrast(patch: list[float]) -> float:
    """アイコン枠のもようの強さ。チャンネルごとの標準偏差の平均。

    アイコンが無い枠は帯のべた塗りなので、地色が何色でもこの値は小さくなる。
    """
    n = len(patch) // 3
    total = 0.0
    for c in range(3):
        block = patch[c * n:(c + 1) * n]
        mean = sum(block) / n
        total += (sum((v - mean) ** 2 for v in block) / n) ** 0.5
    return total / 3


def yellowness(r: int, g: int, b: int) -> float:
    """★のきいろさ。オレンジ（R が G よりかなり強い）は打ち消す。

    ★4の帯はオレンジ（243,152,0）なので、単純な min(R,G)-B だと地色まで
    きいろく見えてしまう。★の黄色は R と G がほぼ同じ（255,248,39）なので、
    R-G のぶんを差し引けば地色のオレンジだけを落とせる。
    """
    v = (r if r < g else g) - b - 1.5 * (r - g if r > g else 0)
    return v / 255.0 if v > 0 else 0.0


def star_patch(
    img: Image.Image, anchor: tuple[int, int, float], slot: int, dx: int = 0, dy: int = 0
) -> list[float]:
    """★枠（右から slot 番目）を切り出し、きいろさのベクトルにする。"""
    ax, ay, s = anchor
    x0 = STAR_RIGHT - STAR_BOX_W - STAR_PITCH * slot
    left = ax + round(x0 * s) + dx
    top = ay + round(STAR_BOX_TOP * s) + dy
    crop = img.crop((left, top, left + max(1, round(STAR_BOX_W * s)), top + max(1, round(STAR_BOX_H * s))))
    crop = crop.resize((STAR_NORM, STAR_NORM), Image.BILINEAR)
    return [yellowness(*p) for p in crop.getdata()]


# --- NCC ------------------------------------------------------------------
def prepare(vec: list[float], blocks: int = 1) -> tuple[list[float], float]:
    """NCC用に平均を引いてノルムを添えて返す。blocks を指定すると区間ごとに平均を引く。"""
    n = len(vec) // blocks
    centered: list[float] = []
    for c in range(blocks):
        block = vec[c * n:(c + 1) * n]
        mean = sum(block) / n
        centered.extend(v - mean for v in block)
    norm = sum(v * v for v in centered) ** 0.5
    return centered, (norm if norm > 1e-9 else 1e-9)


def ncc(a: tuple[list[float], float], b: tuple[list[float], float]) -> float:
    ac, an = a
    bc, bn = b
    return sum(x * y for x, y in zip(ac, bc)) / (an * bn)


# --- 位置合わせつきの切り出し ----------------------------------------------
class Aligner:
    """切り出し位置のずれを直すための、クラスによらない平均テンプレート。

    generic_icon は全タイプのアイコンを平均したもの（＝丸っこい枠の形）。
    どのタイプでも共通の形なので、これに合う位置を探せばずれが分かる。
    """

    def __init__(self, generic_icon: list[float], generic_star: list[float], generic_move: list[float] | None = None):
        self.icon = prepare(generic_icon, 3)
        self.star = prepare(generic_star)
        self.move = prepare(generic_move, 3) if generic_move else None


def extract(path: Path, aligner: Aligner | None = None) -> tuple[dict, str | None]:
    """1枚から、アイコン2枠・★5枠ぶんのベクトルを取り出す。(結果, エラー理由)。

    aligner を渡すと切り出し位置のずれを直してから取り出す。
    テンプレートを1周目に作るときだけ aligner=None で呼ぶ。
    """
    try:
        img = Image.open(path).convert("RGB")
    except Exception:
        return {}, "load_failed"
    anchor = find_anchor(img)
    if anchor is None:
        return {}, "anchor_not_found"

    if aligner is None:
        return {
            "anchor": anchor,
            "offsets": [(0, 0)] * ICON_SLOTS,
            "star_offset": (0, 0),
            "icons": [icon_patch(img, anchor, i) for i in range(ICON_SLOTS)],
            "stars": [star_patch(img, anchor, k) for k in range(STAR_SLOTS)],
            "move": move_patch(img, anchor),
        }, None

    icons = []
    offsets = []
    rng = range(-ALIGN_RADIUS, ALIGN_RADIUS + 1)
    for slot in range(ICON_SLOTS):
        best = max(
            (ncc(prepare(icon_patch(img, anchor, slot, dx, dy), 3), aligner.icon), dx, dy)
            for dx in rng for dy in rng
        )
        offsets.append((best[1], best[2]))
        icons.append(icon_patch(img, anchor, slot, best[1], best[2]))

    ox, oy = offsets[0]
    srng = range(-STAR_ALIGN_RADIUS, STAR_ALIGN_RADIUS + 1)
    sbest = max(
        (ncc(prepare(star_patch(img, anchor, 0, ox + dx, oy + dy)), aligner.star), ox + dx, oy + dy)
        for dx in srng for dy in srng
    )
    stars = [star_patch(img, anchor, k, sbest[1], sbest[2]) for k in range(STAR_SLOTS)]

    if aligner.move is None:
        move = move_patch(img, anchor)
    else:
        mbest = max(
            (ncc(prepare(move_patch(img, anchor, dx, dy), 3), aligner.move), dx, dy)
            for dx in rng for dy in rng
        )
        move = move_patch(img, anchor, mbest[1], mbest[2])

    return {
        "anchor": anchor,
        "offsets": offsets,
        "star_offset": (sbest[1], sbest[2]),
        "icons": icons,
        "stars": stars,
        "move": move,
    }, None


# --- 照合 -----------------------------------------------------------------
class HeaderMatcher:
    """header_templates.json を読み込んで、アイコンと★を判定する。"""

    def __init__(self, templates: dict):
        self.icon = {t: prepare(v, 3) for t, v in templates["icons"].items()}
        self.star = [prepare(v) for v in templates["stars"]]
        self.move = {t: prepare(v, 3) for t, v in templates.get("moves", {}).items()}

    @classmethod
    def load(cls, path: Path = TEMPLATES_PATH) -> "HeaderMatcher":
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def match_icon(self, patch: list[float]) -> tuple[str, float, float]:
        """(最も近いタイプ, NCCスコア, 2位との差) を返す。"""
        p = prepare(patch, 3)
        scores = sorted(((ncc(p, v), t) for t, v in self.icon.items()), reverse=True)
        return scores[0][1], scores[0][0], scores[0][0] - scores[1][0]

    def match_star(self, patch: list[float], slot: int) -> float:
        return ncc(prepare(patch), self.star[slot])

    def match_move(self, patch: list[float]) -> tuple[str, float, float]:
        """わざ欄1行目のアイコンを (最も近いタイプ, NCCスコア, 2位との差) で返す。"""
        p = prepare(patch, 3)
        scores = sorted(((ncc(p, v), t) for t, v in self.move.items()), reverse=True)
        return scores[0][1], scores[0][0], scores[0][0] - scores[1][0]

    def read_move_type(
        self, patch: list[float], min_score: float, min_margin: float
    ) -> tuple[str | None, str]:
        """わざ欄1行目のタイプ。自信が無ければ (None, 理由)。

        1行目がわざではない（メガシンカの行など）カードもあり、そのときは
        どのタイプとも一致しないので読めなかった扱いになる。
        """
        if not self.move:
            return None, "no_template"
        t, s, m = self.match_move(patch)
        if s < min_score:
            return None, "low_score"
        if m < min_margin:
            return None, "low_margin"
        return t, "ok"

    def read_types(
        self,
        icons: list[list[float]],
        min_contrast: float,
        min_score: float,
        min_margin: float,
        max_score_empty: float,
    ) -> tuple[list[str] | None, str]:
        """アイコン枠を左から見てタイプの配列にする。自信が無ければ (None, 理由)。

        枠にアイコンがあるかどうかは2段構えで決める。
          - もようの強さ（contrast）がほぼ0 → 帯のべた塗りなので空
          - 帯に斜めの色わけが入っていると contrast だけでは空と言い切れないので、
            そのときは一致度で判断する。アイコンがある枠は必ず0.90以上出るので、
            それをはるかに下回るものは「アイコンが無い」とみなす。
          - どちらとも言えない中間の一致度が出たら読めなかった扱いにする。
        """
        out: list[str] = []
        for patch in icons:
            if icon_contrast(patch) < min_contrast:
                break  # ここから先は空
            t, s, m = self.match_icon(patch)
            if s <= max_score_empty:
                break  # 帯のもようであってアイコンではない
            if s < min_score:
                return None, "low_score"
            if m < min_margin:
                return None, "low_margin"
            out.append(t)
        if not out:
            return None, "no_icon"
        return out, "ok"

    def read_grade(
        self, stars: list[list[float]], min_score: float, max_score_absent: float
    ) -> tuple[int | None, str]:
        """★枠を右から見て数を数える。判定が曖昧なら (None, 理由)。

        ★は右づめに並ぶので「右から連続して何枠うまっているか」が★の数になる。
        とちゅうが空いている／どっちつかずのスコアが出た場合は読めなかった扱い。
        """
        count = 0
        for slot, patch in enumerate(stars):
            s = self.match_star(patch, slot)
            if s >= min_score:
                if count != slot:
                    return None, "not_contiguous"
                count += 1
            elif s > max_score_absent:
                return None, "ambiguous"
        if count == 0:
            return None, "no_star"
        return count, "ok"
