#!/usr/bin/env python3
"""公式ピック画像の裏面から、わざ欄1行目の「わざの名前」を読み取る。

タイプアイコンや★（header_ocr.py）と同じく、QRコード左上の切り出しシンボルを
アンカーにして相対座標で切り出す。ちがうのは、読むのが絵ではなく文字なので
テンプレート照合ではなく Apple Vision（scripts/ocr/ocr_moves.swift）を使うところ。

わざ欄1行目は上段に英語名、下段に日本語名が並んでいる。
  Collision Course
  アクセルブレイク
英語名は日本語名とは別の文字列なので、独立した2つめの手がかりになる。
「英語名も日本語名も読めて、しかも両者の組み合わせが他のピックと矛盾しない」
ときだけ確定する、というのがこのモジュールの考え方。推測での穴うめはしない。

処理の流れ:
  1. header_ocr.find_anchor() でアンカーの (x, y, 倍率) を出し、わざ欄1行目の
     文字部分（タイプアイコンの右どなり）の切り出し枠を決める。
  2. その枠を拡大率と補間のしかたを変えて7通り、それぞれ独立にOCRする
     （組み合わせは ocr_moves.swift の VARIANTS）。
  3. 1回ぶんの結果を、文字の高さ方向の位置で上段（英語名）と下段（日本語名）に
     分ける。字種のチェックもここで行い、日本語名にかな以外が混じっていたり、
     英語名に英字以外が混じっていたりしたら、その回は読めなかった扱いにする。
  4. 日本語名は7通り全部で同じ文字列になったときだけ採る。1通りでも違えば落とす。
     まちがえるのはほぼ濁点・半濁点の取りちがえ（ブ↔プ、が↔か、ゃ↔や）で、
     拡大のしかたを変えると出かたが変わるため、全一致を求めるとほぼ取り除ける。
     英語名は英字なので誤読が少なく、多数決（7割以上）でよい。
  5. 全958枚ぶんを集めてから、英語名と日本語名の対応が全体で矛盾していないかを見る
     （cross_check）。同じ英語名なのに日本語名がちがうピックが1枚でもあれば、
     その英語名のピックはまとめて読めなかった扱いにする。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

import header_ocr as H

ROOT = Path(__file__).resolve().parent.parent.parent
OCR_SRC = Path(__file__).resolve().parent / "ocr_moves.swift"
OCR_BIN = Path(__file__).resolve().parent / "build" / "ocr_moves"

# --- 切り出し枠（アンカー左上を原点(0,0)とした相対座標、倍率1.0のときの値）------
# わざ欄1行目のタイプアイコンは header_ocr.MOVE_ORIGIN / MOVE_SIZE で決まっている。
# 名前はそのすぐ右どなりに置かれているので、アイコンの右端を左辺にする。
# 帯の上下は実測で相対 y=204〜274、文字は 220〜262 に入る。2行目の帯は y=275 から
# 始まるので、下にはみ出して2行目を巻きこまないよう高さは54でとめる。
# 幅は、いちばん長い8文字のわざ名（ガリョウテンセイ）でも相対 x=280 で終わるので
# 330あれば足りる。右側は帯の外の暗いところなので、広く取っても文字は出てこない。
TEXT_LEFT = H.MOVE_ORIGIN[0] + H.MOVE_SIZE
TEXT_TOP = H.MOVE_ORIGIN[1] - 2
TEXT_W = 330
TEXT_H = 54

# 上段（英語名）と下段（日本語名）の境目。切り出し枠の高さを1.0とした位置。
# 実測では英語名の中心が0.20〜0.29、日本語名の中心が0.68〜0.77に来る。
LINE_SPLIT = 0.45

# 採否ライン。ocr_moves.swift の VARIANTS が7通りなので、
# 「7回のうち5回以上は字種の合う読みが取れていること」を最低条件にする。
# 読める帯なら7回とも読めるので、これを下回るのは帯自体が無い／文字でない場合。
PASSES = 7
MIN_JA_PASSES = 5
MIN_EN_PASSES = 5
# 英語名の多数決に必要な割合。日本語名のほうは全一致を求めるのでここには出てこない。
EN_MIN_RATIO = 0.7

# わざの名前に出てよい字種。picks.json の既存276件はすべてこの範囲におさまる
# （かな＋長音符、それと「１０まんボルト」の全角数字だけ）。
# 1行目がわざではないカード（「メガリザードン にメガシンカ！」など）は
# 漢字や記号が混じるので、ここで落ちる。
JA_RE = re.compile(r"^[ぁ-んァ-ヶー０-９]+$")
# 英語名。単語の区切りは空白、まれにハイフンとアポストロフィが入る。
EN_RE = re.compile(r"^[A-Za-z][A-Za-z'\- ]*[A-Za-z]$")

# 日本語名の字づかいをそろえるための置きかえ。
# どれも「わざ名にはそもそも出てこない文字」を、見た目が同じかなの文字に寄せるだけで、
# 読めなかった文字を推測で補うものではない。
JA_NORMALIZE = {
    "一": "ー",  # 漢数字の一 → 長音符
    "—": "ー",  # emダッシュ
    "―": "ー",  # 横線
    "‐": "ー",  # ハイフン
    "-": "ー",  # 半角ハイフン
    "－": "ー",  # 全角ハイフン
}
# 半角数字は全角に寄せる。picks.json の既存データが「１０まんボルト」と全角なので、
# 突き合わせのときに表記ゆれで食いちがわないようにするため。
for _d in range(10):
    JA_NORMALIZE[chr(ord("0") + _d)] = chr(ord("０") + _d)


def crop_rect(img: Image.Image) -> tuple[int, int, int, int] | None:
    """わざ欄1行目の文字部分の切り出し枠 (x, y, w, h) を返す。アンカーが無ければ None。"""
    anchor = H.find_anchor(img)
    if anchor is None:
        return None
    ax, ay, s = anchor
    return (
        ax + round(TEXT_LEFT * s),
        ay + round(TEXT_TOP * s),
        round(TEXT_W * s),
        round(TEXT_H * s),
    )


def build_requests(ids: list[str], images_dir: Path) -> tuple[list[dict], dict[str, str]]:
    """OCRツールに渡す切り出し指示をつくる。(指示のリスト, ID→エラー理由)。"""
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
        rect = crop_rect(img)
        if rect is None:
            errors[pick_id] = "anchor_not_found"
            continue
        x, y, w, h = rect
        reqs.append({"id": pick_id, "file": str(path.resolve()), "x": x, "y": y, "w": w, "h": h})
    return reqs, errors


def ensure_ocr_binary() -> None:
    """ソースがバイナリより新しければ再ビルドする（再実行可能にするため自動化）。"""
    if OCR_BIN.exists() and OCR_BIN.stat().st_mtime >= OCR_SRC.stat().st_mtime:
        return
    OCR_BIN.parent.mkdir(parents=True, exist_ok=True)
    print("OCRツールをビルド中 (swiftc)...", file=sys.stderr)
    subprocess.run(["swiftc", "-O", str(OCR_SRC), "-o", str(OCR_BIN)], check=True)


def run_ocr(reqs: list[dict]) -> dict[str, dict]:
    """OCRツールを走らせて、ID→生の読み取り結果にする。"""
    ensure_ocr_binary()
    proc = subprocess.run(
        [str(OCR_BIN)],
        input="\n".join(json.dumps(r, ensure_ascii=False) for r in reqs),
        capture_output=True,
        text=True,
        check=True,
    )
    out: dict[str, dict] = {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        out[obj["id"]] = obj
    return out


# --- 1回ぶんの結果を英語名・日本語名に切り分ける ----------------------------
def normalize_ja(text: str) -> str:
    return "".join(JA_NORMALIZE.get(c, c) for c in text if not c.isspace())


def normalize_en(text: str) -> str:
    return " ".join(text.split()).strip(" .,:;")


def split_pass(obs: list[dict]) -> tuple[str | None, str | None]:
    """OCR1回ぶんの観測を (英語名, 日本語名) にする。字種が合わないほうは None。

    上段・下段の切り分けは文字の高さ方向の中心だけで決める。字種で決めないのは、
    英語名が誤読でかなになっていたときに日本語名と取りちがえないようにするため。
    """
    upper = [o for o in obs if o["y"] + o["h"] / 2 < LINE_SPLIT]
    lower = [o for o in obs if o["y"] + o["h"] / 2 >= LINE_SPLIT]

    def join(items: list[dict]) -> str:
        return " ".join(o["t"] for o in sorted(items, key=lambda o: o["x"]))

    en = normalize_en(join(upper))
    ja = normalize_ja(join(lower))
    return (en if EN_RE.fullmatch(en) else None, ja if JA_RE.fullmatch(ja) else None)


class Read:
    """1枚ぶんの読み取り結果。

    en / ja は読めた文字列（読めなければ None）。unanimous は日本語名が
    全通りで一致したかどうか。why は読めなかった理由。
    """

    def __init__(self, en: str | None, ja: str | None, unanimous: bool, why: str):
        self.en = en
        self.ja = ja
        self.unanimous = unanimous
        self.why = why


def read_one(record: dict) -> Read:
    """1枚ぶんの生結果から Read をつくる。

    英語名と日本語名は別々に集計する。片方しか読めなかったものは、
    突き合わせるあいてが無いので、ここで読めなかった扱いにする。
    """
    if "error" in record:
        return Read(None, None, False, record["error"])
    pairs = [split_pass(p) for p in record.get("passes") or []]
    en_votes = Counter(p[0] for p in pairs if p[0] is not None)
    ja_votes = Counter(p[1] for p in pairs if p[1] is not None)

    if sum(ja_votes.values()) < MIN_JA_PASSES:
        return Read(None, None, False, "no_text" if not ja_votes else "ja_unreadable")
    if sum(en_votes.values()) < MIN_EN_PASSES:
        return Read(None, None, False, "en_unreadable")
    en, en_n = en_votes.most_common(1)[0]
    if en_n / sum(en_votes.values()) < EN_MIN_RATIO:
        return Read(None, None, False, "en_disagree")
    ja = ja_votes.most_common(1)[0][0]
    return Read(en, ja, len(ja_votes) == 1, "ok")


# --- 全体での突き合わせ ----------------------------------------------------
def cross_check(reads: dict[str, Read], pool: dict[str, Read] | None = None) -> dict[str, tuple[str | None, str]]:
    """英語名と日本語名の対応が全体で矛盾していないピックだけを確定する。

    同じわざは何枚ものピックに出てくる（276件で132種）。ポケモンのわざ名は
    英語名と日本語名が1対1なので、「同じ英語名なのに日本語名がちがう」ピックが
    あれば、そのどちらかは誤読だとわかる。小さい「ゃ」を「や」と読むような
    まちがいや、濁点と半濁点の取りちがえはここでつかまる。

    食いちがいが1枚でもあれば、その英語名のピックはまとめて落とす。多数派を
    正として少数派に入れ直すことはしない（それは読み取りではなく推測になるため）。
    1枚しか無いわざは突き合わせるあいてが居ないので、拡大のしかた7通りが
    全一致したことだけを根拠に確定する。

    pool を渡すと、突き合わせの材料をそちらから作る（交差検証用）。
    """
    by_en: dict[str, set[str]] = defaultdict(set)
    for r in (pool if pool is not None else reads).values():
        if r.why == "ok":
            by_en[r.en].add(r.ja)

    out: dict[str, tuple[str | None, str]] = {}
    for pick_id, r in reads.items():
        if r.why != "ok":
            out[pick_id] = (None, r.why)
        elif not r.unanimous:
            out[pick_id] = (None, "ja_disagree")
        elif len(by_en[r.en] | {r.ja}) > 1:
            out[pick_id] = (None, "en_ja_mismatch")
        else:
            out[pick_id] = (r.ja, "ok")
    return out
