#!/usr/bin/env python3
"""裏面から18タイプのマークを切り出して、アプリに同梱するPNGにする。

公式サイトには「タイプのマークだけの画像」が置かれていない（あそびかたの図も
タイプあいしょうひょうのPDFも、マークは絵の中に焼き込まれた21pxしかない）。
いちばん大きくきれいに写っているのは券面裏の「わざ」欄1行目のマークで、
ここは50pxある。ヘッダーのタイプ枠（36px）より大きいのでこちらを使う。

やっていること:
  1. わざ1行目のタイプは picks.json に全958枚ぶん入っているので、
     どのマークがどのタイプかは分かっている。1タイプあたり22〜104枚ある。
  2. 1枚ずつ header_ocr と同じやりかたで位置合わせしてから切り出す。
     アンカー（QRコードの切り出しシンボル）からの相対座標には1〜4pxのずれが
     出るので、これをやらないと18個の枠の位置がそろわない。
  3. そろえた切り出しを重ねて、画素ごとの中央値をとる（メディアンスタック）。
     わざ欄の帯の色・キラのきらめき・webpのノイズは1枚ずつちがうので、
     中央値をとるとマークだけが残る。平均ではなく中央値なのは、
     たまに混ざる外れ値（キラの白飛びなど）に引きずられないため。
  4. マークは全タイプ共通の角丸四角なので、輪郭の位置も1回だけ求めて
     18個で共有する。こうすると大きさと余白がタイプによってずれない。
  5. 最後に、できたPNGを header_templates.json のテンプレートと照合して、
     ちゃんと狙ったタイプのマークになっているかを確かめる。

使い方: npm run build:type-icons
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

import header_ocr as H

# ファイル名は英字にする。日本語のままだと require のパス解決でつまずくことがある
ROMAJI = {
    "ノーマル": "normal", "ほのお": "fire", "みず": "water", "でんき": "electric",
    "くさ": "grass", "こおり": "ice", "かくとう": "fighting", "どく": "poison",
    "じめん": "ground", "ひこう": "flying", "エスパー": "psychic", "むし": "bug",
    "いわ": "rock", "ゴースト": "ghost", "ドラゴン": "dragon", "あく": "dark",
    "はがね": "steel", "フェアリー": "fairy",
}

ROOT = Path(__file__).resolve().parent
PICKS = ROOT.parent.parent / "src" / "data" / "picks.json"
IMAGES = ROOT.parent / "raw" / "pick_images"
OUT = ROOT.parent.parent / "assets" / "types"

# わざ欄の枠(50px)の外側に少し余白をつけて切り出す。位置合わせが1〜2pxずれても
# 角丸の輪郭が切れないようにするための余白。
MARGIN = 5
# 作業用の解像度。券面の50pxをこの倍率で拡大したうえで重ねる。
# 倍率が0.79倍の券（わざ欄が多い8枚）も同じ大きさにそろう。
WORK_SCALE = 4
WORK = (H.MOVE_SIZE + MARGIN * 2) * WORK_SCALE

# 1タイプあたり何枚重ねるか。中央値なのでこれだけあれば十分で、
# これ以上増やしても見た目は変わらない。
STACK = 25
# 候補として見る枚数。この中から位置合わせのNCCが高い STACK 枚を使う。
# 一致度に絶対の線引きをしないのは、値がタイプによって大きくちがうから
# （みず0.78 に対して ノーマル0.37。地色とマークのコントラストの差）。
# わざ欄1行目がわざではない券（メガシンカの行など）は 0.0 付近に落ちるので、
# 同じタイプの中で上から選べば自然に外れる。
CANDIDATES = 34

# 輪郭さがし: 18タイプぜんぶで暗いところ＝共通の輪郭線。
RING_MAX_LUMA = 110
# 描き直す角丸を、実測の輪郭より何px内側にするか。
# こうしておくと、ふちに帯の地色が残らない（切り抜く線が必ず輪郭線の上に来る）。
SHRINK = 2
# 書き出すPNGの大きさ。券面は50pxしかないので、これ以上大きくしても意味はない。
OUT_SIZE = 120


def load_generic_move() -> tuple[list[float], float]:
    templates = json.loads((ROOT / "header_templates.json").read_text(encoding="utf-8"))
    return H.prepare(templates["generic_move"], 3)


def move_crop(img: Image.Image, anchor: tuple[int, int, float], dx: int, dy: int) -> Image.Image:
    """わざ欄1行目のマークを、余白つき・作業用の解像度で切り出す。

    resize の box に小数を渡せるので、倍率のちがう券でも同じ大きさにそろえられる。
    """
    ax, ay, s = anchor
    left = ax + (H.MOVE_ORIGIN[0] - MARGIN) * s + dx
    top = ay + (H.MOVE_ORIGIN[1] - MARGIN) * s + dy
    side = (H.MOVE_SIZE + MARGIN * 2) * s
    return img.resize((WORK, WORK), Image.BICUBIC, box=(left, top, left + side, top + side))


def collect(picks: list[dict], generic: tuple[list[float], float]) -> dict[str, list[Image.Image]]:
    """タイプごとに、位置合わせした切り出しを一致度の高い順に集める。"""
    found: dict[str, list[tuple[float, Image.Image]]] = {t: [] for t in ROMAJI}
    rng = range(-H.ALIGN_RADIUS, H.ALIGN_RADIUS + 1)

    for p in picks:
        moves = p.get("moves") or []
        t = moves[0].get("type") if moves else None
        if t not in found or len(found[t]) >= CANDIDATES:
            continue
        path = IMAGES / f"{p['id']}.webp"
        if not path.exists():
            continue
        img = Image.open(path).convert("RGB")
        anchor = H.find_anchor(img)
        if anchor is None:
            continue
        score, dx, dy = max(
            (H.ncc(H.prepare(H.move_patch(img, anchor, dx, dy), 3), generic), dx, dy)
            for dx in rng for dy in rng
        )
        found[t].append((score, move_crop(img, anchor, dx, dy)))

    crops: dict[str, list[Image.Image]] = {}
    for t, cands in found.items():
        cands.sort(key=lambda c: c[0], reverse=True)
        crops[t] = [c for _, c in cands[:STACK]]
    return crops


def median_stack(crops: list[Image.Image]) -> Image.Image:
    """画素ごと・チャンネルごとの中央値をとる。"""
    datas = [c.tobytes() for c in crops]
    mid = len(datas) // 2
    stacked = bytes(sorted(vals)[mid] for vals in zip(*datas))
    return Image.frombytes("RGB", (WORK, WORK), stacked)


def badge_mask(stacks: dict[str, Image.Image]) -> Image.Image:
    """マークの角丸四角だけを 255 にしたマスク。18タイプで共有する。

    「どのタイプでも暗い」ところが共通の輪郭線。タイプごとの地色は明るいものも
    暗いものもあるので、18枚の明るさの最大値をとってから暗いところを拾う。
    こうすると、あくやはがねの暗い地色を輪郭とまちがえない。

    輪郭の外にも暗いところ（わざ欄の外のカード地）があるので、
    外からではなく中央から塗りつぶして内側を求め、それを輪郭の太さだけ
    ふくらませてから「内側＋輪郭」で切る。
    """
    lumas = [im.convert("L").tobytes() for im in stacks.values()]
    brightest = [max(v) for v in zip(*lumas)]
    ring = bytes(255 if v < RING_MAX_LUMA else 0 for v in brightest)

    inside = flood(ring, WORK // 2, WORK // 2)
    thickness = ring_thickness(ring, inside)

    grown = Image.frombytes("L", (WORK, WORK), inside).filter(
        ImageFilter.MaxFilter(thickness * 2 + 1)
    )
    both = Image.frombytes("L", (WORK, WORK), bytes(max(a, b) for a, b in zip(ring, inside)))
    mask = ImageChops.darker(grown, both)
    # 輪郭のギザギザを少しならす（縮小したときに角がとがらないように）
    return mask.filter(ImageFilter.MedianFilter(5))


def flood(ring: bytes, sx: int, sy: int) -> bytes:
    """輪郭(ring)にぶつかるまで (sx, sy) から塗りつぶした範囲を返す。"""
    filled = bytearray(WORK * WORK)
    todo = [(sx, sy)]
    while todo:
        x, y = todo.pop()
        i = y * WORK + x
        if filled[i] or ring[i]:
            continue
        filled[i] = 255
        if x > 0:
            todo.append((x - 1, y))
        if x + 1 < WORK:
            todo.append((x + 1, y))
        if y > 0:
            todo.append((x, y - 1))
        if y + 1 < WORK:
            todo.append((x, y + 1))
    return bytes(filled)


def fit_square_mask(found: Image.Image) -> tuple[tuple[int, int, int, int], Image.Image]:
    """輪郭さがしの結果に、いちばん合う「正方形の角丸」をあてはめる。

    券面の50pxから起こした輪郭はふちがぼこぼこしていて、そのまま切り抜くと
    18個の形が微妙にちがってしまう。マークはもともときれいな角丸四角なので、
    大きさと角のまるみだけを実測から決めて、形そのものは描き直す。

    返すのは (切り出すはこ, そのはこと同じ大きさのマスク)。
    """
    x0, y0, x1, y1 = found.getbbox()
    side = max(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    box = (cx - side // 2, cy - side // 2, cx - side // 2 + side, cy - side // 2 + side)
    target = found.crop(box).point(lambda v: 255 if v > 127 else 0)

    def rounded(radius: int) -> Image.Image:
        m = Image.new("L", (side, side), 0)
        ImageDraw.Draw(m).rounded_rectangle(
            (SHRINK, SHRINK, side - 1 - SHRINK, side - 1 - SHRINK), radius=radius, fill=255
        )
        return m

    # 角のまるみは、重なりがいちばん大きくなる値を総当たりで選ぶ
    best = max(
        (sum(1 for a, b in zip(rounded(r).tobytes(), target.tobytes()) if a == b), r)
        for r in range(side // 8, side // 2)
    )
    print(f"  角丸の半径: {best[1]}/{side} （一致 {best[0] / (side * side):.1%}）")
    return box, rounded(best[1])


def ring_thickness(ring: bytes, inside: bytes) -> int:
    """まん中の行で、内側の左はしから外へ何px輪郭が続くかを数える。"""
    row = WORK // 2 * WORK
    x = next(x for x in range(WORK) if inside[row + x])
    n = 0
    while x - 1 - n >= 0 and ring[row + x - 1 - n]:
        n += 1
    return n


def verify(matcher: H.HeaderMatcher, stack: Image.Image) -> tuple[str, float]:
    """重ねた結果を、わざ欄のテンプレートと照合して狙いどおりのタイプか確かめる。

    テンプレートは move_patch が切り出す範囲（枠から MOVE_INSET だけ内側）から
    作られているので、こちらも作業解像度の上で同じ範囲を切ってから比べる。
    """
    off = (MARGIN + H.MOVE_INSET) * WORK_SCALE
    side = (H.MOVE_SIZE - H.MOVE_INSET * 2) * WORK_SCALE
    box = stack.resize((H.ICON_NORM, H.ICON_NORM), Image.BILINEAR,
                       box=(off, off, off + side, off + side))
    data = list(box.getdata())
    vec = [p[c] / 255.0 for c in range(3) for p in data]
    got, score, _ = matcher.match_move(vec)
    return got, score


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    picks = json.loads(PICKS.read_text(encoding="utf-8"))
    generic = load_generic_move()

    crops = collect(picks, generic)
    thin = {t: len(v) for t, v in crops.items() if len(v) < 5}
    if thin:
        print("枚数が少ないタイプ:", thin)
    empty = [t for t, v in crops.items() if not v]
    if empty:
        print("見本が見つからなかったタイプ:", empty)
        return

    stacks = {t: median_stack(v) for t, v in crops.items()}
    matcher = H.HeaderMatcher.load()

    # 切り出すはことマスクは18タイプ共通。位置も大きさも余白も全部そろう
    box, mask = fit_square_mask(badge_mask(stacks))
    print(f"  マークのはこ: {box} （作業解像度 {WORK}px）")

    for t, stack in stacks.items():
        icon = stack.crop(box).convert("RGBA")
        icon.putalpha(mask)
        icon = icon.resize((OUT_SIZE, OUT_SIZE), Image.LANCZOS)
        icon.save(OUT / f"{ROMAJI[t]}.png")
        got, score = verify(matcher, stack)
        if t not in matcher.move:
            ok = "テンプレート無し（確かめられない）"
        else:
            ok = "OK" if got == t else f"ちがう→{got}"
        print(f"  {t:6} {ROMAJI[t]:9} {len(crops[t]):3}枚  照合 {score:.3f} {ok}")

    print(f"\n{len(stacks)}タイプ → {OUT.relative_to(ROOT.parent.parent)}")


if __name__ == "__main__":
    main()
