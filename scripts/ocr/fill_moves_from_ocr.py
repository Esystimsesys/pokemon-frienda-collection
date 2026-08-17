#!/usr/bin/env python3
"""公式ピック画像の裏面をOCRして、picks.json の moves[0].name の欠損を埋める下ごしらえをする。

進め方:
  1. --scores   : 読み取りの内わけ（英語名だけ読めた、字種が合わない…）と、
                  英語名ごとに日本語名が割れたわざの一覧を出す。しきい値の下見用。
  2. --validate : すでに moves[0].name が入っている268件に対して、カバー率と一致率を測る。
                  --folds を付けると5分割交差検証で測る。
  3. --run-all  : 全958件を読み取り、結果を scripts/raw/ocr_moves.json に書き出す。
                  picks.json には一切書き込まない。

読めなかったものは null のままにして、推測では埋めない。既存の値も上書きしない
（正解データとして使うだけ）。食いちがったものは件数と中身を出す。

読み取るのは「わざ欄の1行目」だけ。2行目以降はカードによって中身も位置も変わる
（ダイヤ型の特殊わざマーク、「メガ○○ にメガシンカ！」の行、「？」の行）ので
このスクリプトでは触らない。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import move_ocr as M  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
PICKS_PATH = ROOT / "src" / "data" / "picks.json"
IMAGES_DIR = ROOT / "scripts" / "raw" / "pick_images"
OUT_JSON = ROOT / "scripts" / "raw" / "ocr_moves.json"

# 交差検証の分割数。Vision は学習しないので読み取りそのものは分けても変わらないが、
# 「英語名と日本語名の突き合わせ」だけは他のピックの読み取り結果を使うので、
# 自分の組を材料に含めずに判定しても結果が変わらないことを確かめる。
FOLDS = 5

"""
picks.json の moves[0].name（旧ファンサイト由来）が公式の裏面と食い違っていたぶん。
OCRの結果と突き合わせて見つかり、公式画像を目視で確認した。
検証時の「補正後の一致率」を出すためだけに使い、picks.json は書き換えない。
反映するかどうかは parse_official.py 側で判断すること。
"""
VERIFIED_GT_FIXES: dict[str, str] = {
    # 裏面には英語名 Rock Smash / 日本語名 いわくだき とはっきり印字されている。
    # fill_header_from_ocr.py で見つかった 1-3-034 エンペルトと同じで、
    # 旧データのわざ自体が別物だったケース。
    "1-3-068": "いわくだき",  # タタッコ。旧データは「かわらわり」
}


def load_picks() -> list[dict]:
    return json.loads(PICKS_PATH.read_text(encoding="utf-8"))


def truth(p: dict) -> str | None:
    """正解データとして使えるわざ名。無ければ None。"""
    if not p["moves"]:
        return None
    name = p["moves"][0]["name"]
    return None if name == "不明" else name


def read_all(picks: list[dict]) -> tuple[dict[str, M.Read], dict[str, str]]:
    """全ピックをOCRして、ID→Read と ID→画像側のエラーを返す。"""
    ids = [p["id"] for p in picks]
    reqs, errors = M.build_requests(ids, IMAGES_DIR)
    print(f"OCR中: {len(reqs)}件（1枚につき{M.PASSES}通り）", file=sys.stderr)
    raw = M.run_ocr(reqs)
    reads: dict[str, M.Read] = {}
    for pick_id in ids:
        if pick_id in errors:
            continue
        rec = raw.get(pick_id)
        if rec is None:
            errors[pick_id] = "ocr_missing"
            continue
        reads[pick_id] = M.read_one(rec)
    return reads, errors


def resolve(reads: dict[str, M.Read], folds: int = 0) -> dict[str, tuple[str | None, str]]:
    """突き合わせまで済ませて ID→(わざ名 or None, 理由) にする。

    folds を指定すると、突き合わせの材料を「自分と同じ組のピック以外」に限る。
    自分の読み取りが自分の裏づけになる、という取りちがえが無いことの確認用。
    """
    if folds <= 0:
        return M.cross_check(reads)
    ids = sorted(reads)
    out: dict[str, tuple[str | None, str]] = {}
    for k in range(folds):
        held = {pid for i, pid in enumerate(ids) if i % folds == k}
        pool = {pid: r for pid, r in reads.items() if pid not in held}
        out.update(M.cross_check({pid: reads[pid] for pid in held}, pool=pool))
    return out


# --- 下見 -----------------------------------------------------------------
def show_scores(picks: list[dict], reads: dict[str, M.Read], errors: dict[str, str]) -> None:
    print("\n=== 1枚ごとの読み取り（突き合わせ前） ===")
    print(f"  対象 {len(picks)}件 / OCRできた {len(reads)}件 / 画像側のエラー {len(errors)}件")
    print(f"  内わけ: {dict(Counter(r.why for r in reads.values()))}")
    uni = sum(1 for r in reads.values() if r.why == "ok" and r.unanimous)
    ok = sum(1 for r in reads.values() if r.why == "ok")
    print(f"  英語名も日本語名も読めた {ok}件 / うち日本語名が{M.PASSES}通り全一致 {uni}件")

    resolved = M.cross_check(reads)
    print("\n=== 英語名との突き合わせ ===")
    print(f"  確定 {sum(1 for v in resolved.values() if v[1] == 'ok')}件 / "
          f"突き合わせで落とした {sum(1 for v in resolved.values() if v[1] == 'en_ja_mismatch')}件")

    by_en: dict[str, Counter] = defaultdict(Counter)
    for r in reads.values():
        if r.why == "ok":
            by_en[r.en][r.ja] += 1
    conflicts = {en: v for en, v in by_en.items() if len(v) > 1}
    print(f"  同じ英語名で日本語名が割れたわざ {len(conflicts)}種:")
    for en, v in sorted(conflicts.items()):
        print(f"    {en}: {dict(v)}")
    singles = sum(1 for v in by_en.values() if sum(v.values()) == 1)
    print(f"  そのわざが1枚にしか出てこないもの {singles}種（突き合わせるあいてが居ない）")


# --- 検証 -----------------------------------------------------------------
def validate(picks: list[dict], reads: dict[str, M.Read], folds: int, apply_fixes: bool) -> None:
    head = f"{FOLDS}分割交差検証（突き合わせに自分の組を使わない）" if folds else "全件を使った突き合わせ"
    if apply_fixes:
        head += f" / picks.json 側の誤り{len(VERIFIED_GT_FIXES)}件（目視確認済み）を補正"
    print(f"\n############ {head} ############")

    resolved = resolve(reads, folds)
    total = read = ok = 0
    bad: list[str] = []
    reasons: Counter = Counter()
    for p in picks:
        name = truth(p)
        if name is None:
            continue
        total += 1
        got, why = resolved.get(p["id"], (None, "extract_failed"))
        if got is None:
            reasons[why] += 1
            continue
        read += 1
        want = VERIFIED_GT_FIXES.get(p["id"], name) if apply_fixes else name
        if got == want:
            ok += 1
        else:
            bad.append(f"{p['id']} {p['name']}: 読み取り「{got}」 != 正解「{want}」")

    print(f"\nmoves[0].name : 正解データ{total}件 / 読取できた{read}件"
          f"(カバー率 {read / total * 100:.1f}%) / 既存と一致{ok}件"
          f"({ok / read * 100:.2f}%)")
    if reasons:
        print(f"  読めなかった理由: {dict(reasons)}")
    if bad:
        print(f"  既存と食いちがい {len(bad)}件:")
        for x in bad:
            print(f"    {x}")


# --- 全件 -----------------------------------------------------------------
def run_all(picks: list[dict], reads: dict[str, M.Read], errors: dict[str, str]) -> None:
    resolved = resolve(reads, 0)
    records = []
    reasons: Counter = Counter()
    filled = 0
    gap = sum(1 for p in picks if truth(p) is None)
    conflict: list[str] = []

    for p in picks:
        got, why = resolved.get(p["id"], (None, errors.get(p["id"], "extract_failed")))
        read = reads.get(p["id"])
        if got is None:
            reasons[why] += 1
        else:
            existing = truth(p)
            if existing is None:
                filled += 1
            elif got != existing:
                conflict.append(
                    f"{p['id']} {p['name']}: 読み取り「{got}」 != 既存「{existing}」"
                    f"（英語名 {read.en}）"
                )
        records.append({
            "id": p["id"],
            # わざ欄1行目の名前。2行目以降は読み取っていない。
            "firstMoveName": got,
            # 突き合わせに使った英語名。読み取りの根拠として残しておく。
            "firstMoveNameEn": read.en if (got is not None and read) else None,
            "reason": why,
        })

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if errors:
        print(f"読み取れなかった画像: {dict(Counter(errors.values()))}")
    print(f"\n書き出し先: {OUT_JSON.relative_to(ROOT)}")
    print(f"\nmoves[0].name : 名前が無い{gap}件のうち {filled}件を新しく埋められる")
    print(f"  読めなかった理由: {dict(reasons)}")
    if conflict:
        print(f"\n既存の名前と食いちがい {len(conflict)}件:")
        for x in conflict:
            print(f"  {x}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", action="store_true", help="読み取りの内わけを出す")
    ap.add_argument("--validate", action="store_true", help="既存データに対するカバー率・一致率を測る")
    ap.add_argument("--folds", action="store_true", help=f"--validate を{FOLDS}分割交差検証で行う")
    ap.add_argument("--run-all", action="store_true", help="全958件を読み取り scripts/raw/ocr_moves.json に書き出す")
    args = ap.parse_args()
    if not (args.scores or args.validate or args.run_all):
        ap.print_help()
        sys.exit(1)

    picks = load_picks()
    print(f"読み取り対象: {len(picks)}件", file=sys.stderr)
    reads, errors = read_all(picks)

    if args.scores:
        show_scores(picks, reads, errors)
    if args.validate:
        for apply_fixes in (False, True):
            validate(picks, reads, FOLDS if args.folds else 0, apply_fixes)
    if args.run_all:
        run_all(picks, reads, errors)


if __name__ == "__main__":
    main()
