#!/usr/bin/env python3
"""公式ピック画像の裏面から「2つめのわざの行」と、でんせつ／まぼろしの帯を読み取る。

テラスタル・Zワザ・ダイマックス・タッグわざは、どれも**わざ欄の2行目**に
その仕組みのマークとわざ名が入っている。メガシンカだけは2行目ではなく
**1行目が「メガ○○ にメガシンカ！」に置きかわる**（2行目は普通のわざの行になる）。

位置決めは header_ocr.py とまったく同じで、QRコード左上の切り出しシンボルを
アンカーにした相対座標＋倍率補正＋±4pxの位置合わせ＋NCC照合。
わざ欄2行目は**1行目とまったく同じ幾何を70px下にずらしたもの**なので、
1行目むけの定数（header_ocr.MOVE_ORIGIN / move_ocr.TEXT_*）をそのまま流用できる。

読むものと、その見分けかた:
  1. マーク枠（2行目の右はし）… テラスタルの星・ダイマックスのバツ・タッグわざのうずまき。
     この3つは形も地色もはっきり違うのでテンプレート照合できれいに割れる。
  2. アイコン枠（2行目の左はし）… Zワザの行だけタイプアイコンが**ひし形**になる。
     Zワザは右はしにマークが無い（帯そのものが紺＋黄色ふちで、右はしは無地）ので、
     マーク枠では判定できない。かわりにこのひし形で見分ける。
     仕組みが無いピックは2行目そのものが空（暗い置き場だけ）なので枠も空になる。
  3. わざ名（2行目）… Apple Vision。上段が英語名・下段が日本語名なのは1行目と同じ。
     ただしタッグわざの行だけは上段が英語名ではなく**相手ポケモンの名前（カタカナ）**。
  4. メガシンカ … わざ欄1行目を Vision で読んで「メガシンカ」の字が出るかどうか。
  5. でんせつ／まぼろし … タイプアイコンのすぐ下に出る小さな帯。
     でんせつは黄色い字、まぼろしは水色の字で、どちらも白いふちどりがついている。

一致度が低いものは None（読めなかった）として返す。推測はしない。
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

import header_ocr as H
import move_ocr as M

ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATES_PATH = Path(__file__).resolve().parent / "special_templates.json"

# 仕組みの呼び名。公式の「アイコン・マークについて」の表記に合わせる。
TERA = "テラスタル"
Z = "Zワザ"
MEGA = "メガシンカ"
TAG = "タッグわざ"
DYNA = "ダイマックス"
MECHANICS = (TERA, Z, MEGA, TAG, DYNA)

# マーク枠だけで見分けられる仕組み（Zワザは右はしが無地なのでここに居ない）
MARK_CLASSES = (TERA, TAG, DYNA)

# --- 幾何（アンカー左上を原点(0,0)とした相対座標、倍率1.0のときの値）------------
# わざ欄は1行につき70px。2行目は1行目をそのまま70px下にずらしたところにある。
ROW_PITCH = 70

# マーク枠。1行目のタイプアイコン（MOVE_ORIGIN=(-35,215)）と同じ高さの、帯の右はし。
# 実測でテラスタルの星が x=282〜310 / y=290〜330 に入るので、そのまわりを少し広めに取る。
MARK_BOX = (272, H.MOVE_ORIGIN[1] + ROW_PITCH - 2, 44, 50)

# アイコン枠。普通の行は角丸四角（50x50）だが、Zワザの行はひし形で横に広い
# （実測で相対 x=-50〜30）。どちらも入るように横長の枠にする。
SLOT_BOX = (-52, H.MOVE_ORIGIN[1] + ROW_PITCH - 1, 84, 52)
SLOT_CLASSES = ("diamond", "square", "empty")

# でんせつ／まぼろしの帯。ヘッダーのタイプアイコン（ICON_ORIGIN=(82,22)、36x36）の
# すぐ下。実測で x=90〜142 / y=66〜81 に字が入るので、白いふちごと取る。
LEGEND_BOX = (86, 60, 62, 28)
LEGEND_CLASSES = ("でんせつ", "まぼろし")

# 切り出しを何ピクセル四方に正規化してから照合するか。
MARK_NORM = 22
SLOT_NORM = 22
LEGEND_NORM = (36, 16)

# 位置合わせで探すずれの範囲（px）。header_ocr.ALIGN_RADIUS と同じ考えかた。
ALIGN_RADIUS = 4

# --- 採否ライン ------------------------------------------------------------
# マーク枠: 実測で テラ0.95 / タッグ0.99 / ダイマ0.97 に対し、
# 仕組み無しは最大0.38・メガシンカは最大0.18。あいだを取って0.70。
MIN_MARK_SCORE = 0.70
MIN_MARK_MARGIN = 0.15
# アイコン枠: 実測で ひし形0.74以上 に対し、ひし形でないものは最大0.41。
MIN_SLOT_SCORE = 0.55
MIN_SLOT_MARGIN = 0.10
# でんせつ／まぼろしの帯
MIN_LEGEND_SCORE = 0.70
MIN_LEGEND_MARGIN = 0.10

# --- Vision（メガシンカの1行目・2行目のわざ名）------------------------------
# 「メガ○○ にメガシンカ！」の下段。「！」が入るので move_ocr の字種チェックは通らない。
MEGA_RE = re.compile(r"メガシンカ")
# 7通りのうち何通りで「メガシンカ」の字が出れば認めるか
MIN_MEGA_PASSES = 5

# タッグわざの行の上段は英語名ではなく相手ポケモンの名前（カタカナ）。
KATAKANA_RE = re.compile(r"^[ァ-ヶー]+$")


# --- 切り出し ---------------------------------------------------------------
def patch(
    img: Image.Image,
    anchor: tuple[int, int, float],
    box: tuple[int, int, int, int],
    norm: tuple[int, int],
    dx: int = 0,
    dy: int = 0,
) -> list[float]:
    """枠を切り出して、R・G・Bをこの順に並べたベクトルにする。

    チャンネルごとに固めるのは header_ocr.icon_patch と同じ理由（照合のときに
    チャンネル別に平均を引き、帯の地色のちがいに引きずられないようにするため）。
    """
    ax, ay, s = anchor
    x, y, w, h = box
    left = ax + round(x * s) + dx
    top = ay + round(y * s) + dy
    crop = img.crop((left, top, left + max(1, round(w * s)), top + max(1, round(h * s))))
    data = list(crop.resize(norm, Image.BILINEAR).getdata())
    return [p[c] / 255.0 for c in range(3) for p in data]


def mark_patch(img, anchor, dx=0, dy=0) -> list[float]:
    return patch(img, anchor, MARK_BOX, (MARK_NORM, MARK_NORM), dx, dy)


def slot_patch(img, anchor, dx=0, dy=0) -> list[float]:
    return patch(img, anchor, SLOT_BOX, (SLOT_NORM, SLOT_NORM), dx, dy)


def legend_patch(img, anchor, dx=0, dy=0) -> list[float]:
    return patch(img, anchor, LEGEND_BOX, LEGEND_NORM, dx, dy)


class Aligner:
    """切り出し位置のずれを直すための、クラスによらない平均テンプレート。

    header_ocr.Aligner と同じ考えかた。マーク枠は「テラ／タッグ／ダイマの平均」、
    アイコン枠は「ひし形／角丸四角／空の平均」に合う位置を探す。
    どのクラスでもだいたい同じところに図がある一方、仕組みが無いピックの
    のっぺりした帯はどこに合わせてもスコアが上がらないので、
    位置合わせを入れても「無い」ものが「有る」に化けることはない（実測でも
    仕組み無しの最高スコアは0.379→0.381とほぼ変わらなかった）。
    """

    def __init__(self, mark: list[float], slot: list[float], legend: list[float]):
        self.mark = prepare(mark)
        self.slot = prepare(slot)
        self.legend = prepare(legend)


def prepare(vec: list[float], blocks: int = 3) -> tuple[list[float], float]:
    """NCC用に、チャンネルごとに平均を引いてノルムを添えて返す。"""
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


def _align(img, anchor, fn, target: tuple[list[float], float]) -> tuple[int, int]:
    rng = range(-ALIGN_RADIUS, ALIGN_RADIUS + 1)
    best = max(
        (ncc(prepare(fn(img, anchor, dx, dy)), target), dx, dy)
        for dx in rng for dy in rng
    )
    return best[1], best[2]


def extract(path: Path, aligner: Aligner | None = None) -> tuple[dict, str | None]:
    """1枚から、マーク枠・アイコン枠・でんせつ帯のベクトルを取り出す。(結果, エラー理由)。

    aligner を渡すと切り出し位置のずれを直してから取り出す。
    テンプレートを1周目に作るときだけ aligner=None で呼ぶ。
    """
    try:
        img = Image.open(path).convert("RGB")
    except Exception:
        return {}, "load_failed"
    anchor = H.find_anchor(img)
    if anchor is None:
        return {}, "anchor_not_found"

    # でんせつ帯の種を決めるための色。位置合わせの前後で変わらないので一度だけ測る。
    seed = legend_seed(*legend_colors(img, anchor))

    if aligner is None:
        return {
            "mark": mark_patch(img, anchor),
            "slot": slot_patch(img, anchor),
            "legend": legend_patch(img, anchor),
            "legend_seed": seed,
        }, None

    mdx, mdy = _align(img, anchor, mark_patch, aligner.mark)
    sdx, sdy = _align(img, anchor, slot_patch, aligner.slot)
    ldx, ldy = _align(img, anchor, legend_patch, aligner.legend)
    return {
        "mark": mark_patch(img, anchor, mdx, mdy),
        "slot": slot_patch(img, anchor, sdx, sdy),
        "legend": legend_patch(img, anchor, ldx, ldy),
        "legend_seed": seed,
        "offsets": {"mark": (mdx, mdy), "slot": (sdx, sdy), "legend": (ldx, ldy)},
    }, None


# --- 照合 -------------------------------------------------------------------
class SpecialMatcher:
    """special_templates.json を読み込んで、仕組みとでんせつ／まぼろしを判定する。"""

    def __init__(self, templates: dict):
        self.mark = {k: prepare(v) for k, v in templates["marks"].items()}
        self.slot = {k: prepare(v) for k, v in templates["slots"].items()}
        self.legend = {k: prepare(v) for k, v in templates["legends"].items()}

    @classmethod
    def load(cls, path: Path = TEMPLATES_PATH) -> "SpecialMatcher":
        return cls(json.loads(path.read_text(encoding="utf-8")))

    @staticmethod
    def _best(p: list[float], tmpl: dict) -> tuple[str, float, float]:
        """(最も近いクラス, NCCスコア, 2位との差) を返す。"""
        v = prepare(p)
        scores = sorted(((ncc(v, t), k) for k, t in tmpl.items()), reverse=True)
        return scores[0][1], scores[0][0], scores[0][0] - scores[1][0]

    def match_mark(self, p):
        return self._best(p, self.mark)

    def match_slot(self, p):
        return self._best(p, self.slot)

    def match_legend(self, p):
        return self._best(p, self.legend)

    def read_mechanic(self, rec: dict) -> tuple[str | None, str]:
        """2行目の仕組み（テラスタル/Zワザ/ダイマックス/タッグわざ）。

        マーク枠とアイコン枠を別々に見て、両方の言い分が食いちがったら
        読めなかった扱いにする。片方だけで決めうちしない。
        """
        mk, ms, mm = self.match_mark(rec["mark"])
        sk, ss, sm = self.match_slot(rec["slot"])
        has_mark = ms >= MIN_MARK_SCORE and mm >= MIN_MARK_MARGIN
        is_z = sk == "diamond" and ss >= MIN_SLOT_SCORE and sm >= MIN_SLOT_MARGIN

        if has_mark and is_z:
            return None, "mark_slot_conflict"
        if has_mark:
            return mk, "ok"
        if is_z:
            return Z, "ok"
        # どちらも出なかった。マークらしきものが中途はんぱに出ていたら読めなかった扱い。
        if ms >= MIN_MARK_SCORE * 0.7 or (sk == "diamond" and ss >= MIN_SLOT_SCORE * 0.7):
            return None, "low_score"
        return None, "no_mark"

    def read_legend(self, rec: dict) -> tuple[str | None, str]:
        """でんせつ／まぼろしの帯。どちらでもなければ (None, 'none')。"""
        k, s, m = self.match_legend(rec["legend"])
        if s < MIN_LEGEND_SCORE:
            return None, "low_score"
        if m < MIN_LEGEND_MARGIN:
            return None, "low_margin"
        return (None, "none") if k == "none" else (k, "ok")


# --- Vision（1行目・2行目の文字）--------------------------------------------
def crop_rect(img: Image.Image, row: int) -> tuple[int, int, int, int] | None:
    """わざ欄 row 行目（0始まり）の文字部分の切り出し枠。アンカーが無ければ None。

    枠そのものは move_ocr が1行目むけに決めたものをそのまま使い、
    row のぶんだけ ROW_PITCH 下にずらす。
    """
    anchor = H.find_anchor(img)
    if anchor is None:
        return None
    ax, ay, s = anchor
    return (
        ax + round(M.TEXT_LEFT * s),
        ay + round((M.TEXT_TOP + ROW_PITCH * row) * s),
        round(M.TEXT_W * s),
        round(M.TEXT_H * s),
    )


def build_requests(ids: list[str], images_dir: Path, rows=(0, 1)) -> tuple[list[dict], dict[str, str]]:
    """OCRツールに渡す切り出し指示をつくる。IDは "<pick_id>#<行>" にする。"""
    reqs: list[dict] = []
    errors: dict[str, str] = {}
    for pick_id in ids:
        path = images_dir / f"{pick_id}.webp"
        if not path.exists():
            errors[pick_id] = "image_missing"
            continue
        try:
            img = Image.open(path).convert("RGB")
        except Exception:
            errors[pick_id] = "load_failed"
            continue
        rects = [(r, crop_rect(img, r)) for r in rows]
        if any(rect is None for _, rect in rects):
            errors[pick_id] = "anchor_not_found"
            continue
        for r, rect in rects:
            x, y, w, h = rect
            reqs.append({"id": f"{pick_id}#{r}", "file": str(path.resolve()),
                         "x": x, "y": y, "w": w, "h": h})
    return reqs, errors


def run_ocr(reqs: list[dict]) -> dict[str, dict]:
    """move_ocr の Vision ツールをそのまま使う（切り出し枠を渡すだけの作り）。"""
    return M.run_ocr(reqs)


def pass_lines(obs: list[dict]) -> tuple[str, str]:
    """OCR1回ぶんの観測を (上段, 下段) の生文字列にする。字種の判定はしない。"""
    upper = [o for o in obs if o["y"] + o["h"] / 2 < M.LINE_SPLIT]
    lower = [o for o in obs if o["y"] + o["h"] / 2 >= M.LINE_SPLIT]

    def join(items):
        return " ".join(o["t"] for o in sorted(items, key=lambda o: o["x"]))

    return join(upper), join(lower)


def read_mega(record: dict) -> tuple[bool, int]:
    """わざ欄1行目に「メガシンカ」の字があるか。(判定, 出た回数)。"""
    if "error" in record:
        return False, 0
    n = 0
    for obs in record.get("passes") or []:
        text = "".join(o["t"] for o in obs)
        if MEGA_RE.search(text):
            n += 1
    return n >= MIN_MEGA_PASSES, n


def read_second_name(record: dict, is_tag: bool) -> "M.Read":
    """2行目のわざ名。move_ocr.read_one と同じ集計だが、タッグわざの行だけ別あつかい。

    タッグわざの行は上段が英語名ではなく相手ポケモンの名前（カタカナ）なので、
    英語名との突き合わせができない。そのぶん、上段・下段の**両方**が
    7通り全一致したときだけ読めたことにして、英語名の欄には None を入れる。
    """
    if not is_tag:
        return M.read_one(record)

    if "error" in record:
        return M.Read(None, None, False, record["error"])
    pairs = [pass_lines(p) for p in record.get("passes") or []]
    up = Counter(M.normalize_ja(u) for u, _ in pairs if KATAKANA_RE.fullmatch(M.normalize_ja(u)))
    lo = Counter(M.normalize_ja(l) for _, l in pairs if M.JA_RE.fullmatch(M.normalize_ja(l)))
    if sum(lo.values()) < M.MIN_JA_PASSES:
        return M.Read(None, None, False, "no_text" if not lo else "ja_unreadable")
    if sum(up.values()) < M.MIN_JA_PASSES:
        return M.Read(None, None, False, "partner_unreadable")
    r = M.Read(up.most_common(1)[0][0], lo.most_common(1)[0][0], len(lo) == 1, "ok")
    # 相手ポケモン名も全一致を求める（英語名との突き合わせが使えないぶんの埋め合わせ）
    r.partner_unanimous = len(up) == 1
    return r


# --- 正解データ（ファンサイト pokearcade.jp）--------------------------------
"""仕組みの正解データは公式には無いので、ファンサイトの表の列を使う。

parse_pokearcade.py が同じ表を読んでいるので、表の読み取りはそちらを使いまわす。
ちがうのは**突き合わせかた**で、こちらは「ピック番号が直接一致した行」だけを
正解データにする。あちらの「日本語名＋ステータス5項目」で突き合わせる方法は
ステータスの検証には使えても、仕組みの検証には使えないため。

理由: 同じポケモンのスペシャルピックには「メガシンカのもの」と「タッグわざのもの」の
ように、**仕組みだけが違って名前もステータスも同じ**ものがある。向こうに片方しか
無い／こちらに片方しか無いと、キーは両側で一意に見えるのに別のピック同士が
つながってしまう。実際に7件（p047 ルカリオ・p049 カメックス・p052 ピカチュウ・
p057 ルギア・p061 リザードン・p070 ゲンガー・p071 ルカリオ）で、券面と食いちがう
行につながっているのを目視で確認した。
"""
MECH_COLUMNS = {"tera": TERA, "z": Z, "mega": MEGA, "tag": TAG, "dyna": DYNA}


def load_truth() -> dict[str, set[str]]:
    """ピック番号 -> そのピックが持つ仕組みの集合。番号が直接一致した行だけ。"""
    sys.path.insert(0, str(ROOT / "scripts"))
    import parse_pokearcade as PA  # noqa: E402

    out: dict[str, set[str]] = {}
    for row in PA.parse_table(PA.load_html()):
        no = row["no"][0] if row["no"] else None
        if no in (None, "P", "W"):
            continue
        out[no] = {name for col, name in MECH_COLUMNS.items() if any(row[col])}
    return out


# --- でんせつ／まぼろしの種 --------------------------------------------------
"""でんせつ／まぼろしには正解データが無いので、テンプレートの種を券面の色から作る。

帯は「白いふちどりの中に色つきの字」という作りで、
  - 白の割合 … 帯があるかどうか（実測で 0.06 と 0.13 のあいだにはっきり谷がある）
  - 水色の画素の割合 … まぼろし（水色の字）か でんせつ（黄色い字）か
で機械的に分けられる。黄色を使わないのは、★4のピックは帯の地色がオレンジで、
地色まで黄色に見えてしまうため。水色は地色（むらさき・オレンジ）には出てこない。

どちらとも言い切れない中間のものは種にしない（1件だけ該当）。種から作った
テンプレートで全958枚を照合しなおし、同じポケモンのピックどうしで
判定が割れていないことを確かめる、というのが検証の流れ。
"""
LEGEND_WHITE_ON = 0.10
LEGEND_WHITE_OFF = 0.05
LEGEND_CYAN_ON = 0.02
LEGEND_CYAN_OFF = 0.005


def legend_colors(img: Image.Image, anchor: tuple[int, int, float]) -> tuple[float, float]:
    """でんせつ帯の枠のなかの (白の割合, 水色の割合)。"""
    ax, ay, s = anchor
    x, y, w, h = LEGEND_BOX
    crop = img.crop((ax + round(x * s), ay + round(y * s),
                     ax + round((x + w) * s), ay + round((y + h) * s)))
    px = list(crop.getdata())
    n = len(px) or 1
    white = sum(1 for r, g, b in px if r > 200 and g > 200 and b > 200)
    cyan = sum(1 for r, g, b in px if b > 170 and g > 160 and r < 170 and b - r > 50)
    return white / n, cyan / n


def legend_seed(white: float, cyan: float) -> str | None:
    """色から決めたテンプレートの種のラベル。決めきれなければ None。"""
    if white > LEGEND_WHITE_ON:
        if cyan > LEGEND_CYAN_ON:
            return "まぼろし"
        if cyan < LEGEND_CYAN_OFF:
            return "でんせつ"
        return None
    return "none" if white < LEGEND_WHITE_OFF else None
