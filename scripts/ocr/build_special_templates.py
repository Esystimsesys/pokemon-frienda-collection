#!/usr/bin/env python3
"""仕組みのマーク・Zワザのひし形・でんせつ帯のテンプレートを自動生成する。

build_header_templates.py と同じ作りで、種を人手で決め打ちしない。

  - マーク枠（テラスタル／タッグわざ／ダイマックス）と
    アイコン枠（ひし形＝Zワザ／角丸四角＝普通の行／空＝2行目なし）は、
    ファンサイトの表の列（special_ocr.load_truth）をラベルにする。
    ピック番号が直接一致した854件だけを使う。
  - でんせつ帯（でんせつ／まぼろし／なし）は正解データが無いので、
    券面の色から機械的にラベルを付ける（special_ocr.legend_seed）。

2周する。1周目は位置合わせなしで平均テンプレートを作り、それを使って
2周目の切り出し位置をそろえてから作り直す。マークは44px、ひし形の
アイコン枠は84x52pxしかなく、1〜2pxのずれで一致度が0.3近く落ちる。
（実測: 位置合わせなしだとテラスタルの最低スコアが0.59まで落ちるが、
 位置合わせを入れると0.95まで上がる。仕組み無しの最高は0.379→0.381で変わらない。）

出力: scripts/ocr/special_templates.json

--folds N を付けると N分割の交差検証用テンプレートも作る（自己一致による
過大評価を避けて一致率を測るため）。
  python3 scripts/ocr/build_special_templates.py --folds 5
  python3 scripts/ocr/fill_special_from_ocr.py --validate --folds
の順で実行し、終わったら --folds なしで作り直しておくこと。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import special_ocr as S  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
PICKS_PATH = ROOT / "src" / "data" / "picks.json"
IMAGES_DIR = ROOT / "scripts" / "raw" / "pick_images"
OUT_PATH = Path(__file__).resolve().parent / "special_templates.json"


def average(vectors: list[list[float]]) -> list[float]:
    n = len(vectors[0])
    acc = [0.0] * n
    for v in vectors:
        for i, x in enumerate(v):
            acc[i] += x
    # ファイルを肥大させないよう5桁に丸める（NCCの結果は変わらない）
    return [round(x / len(vectors), 5) for x in acc]


def slot_label(mechs: set[str] | None) -> str | None:
    """アイコン枠のラベル。正解データが無いピックは None。"""
    if mechs is None:
        return None
    if S.Z in mechs:
        return "diamond"
    # メガシンカのピックは1行目がメガシンカの行になり、2行目に普通のわざが入る
    if mechs:
        return "square"
    return "empty"


def mark_label(mechs: set[str] | None) -> str | None:
    """マーク枠のラベル。マークが無い行（Zワザ・メガシンカ・仕組み無し）は None。"""
    if mechs is None:
        return None
    for m in S.MARK_CLASSES:
        if m in mechs:
            return m
    return None


def extract_all(picks: list[dict], aligner: S.Aligner | None, label: str) -> tuple[dict, dict[str, int]]:
    """全ピックから枠のベクトルと、でんせつ帯の色を取り出す。"""
    out: dict[str, dict] = {}
    errors: dict[str, int] = {}
    for i, p in enumerate(picks):
        path = IMAGES_DIR / f"{p['id']}.webp"
        if not path.exists():
            errors["image_missing"] = errors.get("image_missing", 0) + 1
            continue
        rec, err = S.extract(path, aligner)
        if err:
            errors[err] = errors.get(err, 0) + 1
            continue
        out[p["id"]] = rec
        if (i + 1) % 200 == 0:
            print(f"  {label}: {i + 1}/{len(picks)}枚", file=sys.stderr)
    return out, errors


def build(data: dict, truth: dict[str, set[str]], exclude: set[str] | None = None) -> dict:
    """クラスごとの平均テンプレートを作る。"""
    marks: dict[str, list[list[float]]] = {}
    slots: dict[str, list[list[float]]] = {}
    legends: dict[str, list[list[float]]] = {}
    for pick_id, rec in data.items():
        if exclude and pick_id in exclude:
            continue
        mechs = truth.get(pick_id)
        mk = mark_label(mechs)
        if mk:
            marks.setdefault(mk, []).append(rec["mark"])
        sl = slot_label(mechs)
        if sl:
            slots.setdefault(sl, []).append(rec["slot"])
        lg = rec.get("legend_seed")
        if lg:
            legends.setdefault(lg, []).append(rec["legend"])
    return {
        "marks": {k: average(v) for k, v in marks.items()},
        "slots": {k: average(v) for k, v in slots.items()},
        "legends": {k: average(v) for k, v in legends.items()},
        "counts": {
            "marks": {k: len(v) for k, v in marks.items()},
            "slots": {k: len(v) for k, v in slots.items()},
            "legends": {k: len(v) for k, v in legends.items()},
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", type=int, default=0, help="交差検証用テンプレートも作る場合の分割数")
    args = ap.parse_args()

    picks = json.loads(PICKS_PATH.read_text(encoding="utf-8"))
    truth = S.load_truth()
    print(f"正解データ（ピック番号が直接一致した行）: {len(truth)}件")

    print("1周目（位置合わせなし）...", file=sys.stderr)
    rough, errors = extract_all(picks, None, "1周目")
    if errors:
        print(f"  取り出せなかったもの: {errors}")
    seed = build(rough, truth)
    for key, want in (("marks", S.MARK_CLASSES), ("slots", S.SLOT_CLASSES), ("legends", S.LEGEND_CLASSES)):
        missing = [k for k in want if k not in seed[key]]
        if missing:
            raise SystemExit(f"{key} のテンプレートを作れないクラスがある: {missing}")

    aligner = S.Aligner(
        average(list(seed["marks"].values())),
        average(list(seed["slots"].values())),
        average(list(seed["legends"].values())),
    )

    print("2周目（位置合わせあり）...", file=sys.stderr)
    data, errors2 = extract_all(picks, aligner, "2周目")
    if errors2:
        print(f"  取り出せなかったもの: {errors2}")
    final = build(data, truth)

    counts = final.pop("counts")
    print(f"マーク枠の教師サンプル: {counts['marks']}")
    print(f"アイコン枠の教師サンプル: {counts['slots']}")
    print(f"でんせつ帯の種（券面の色から機械的に決めたもの）: {counts['legends']}")
    undecided = [p for p, r in data.items() if r.get("legend_seed") is None]
    print(f"  色では決めきれず種にしなかったもの: {len(undecided)}件 {undecided}")

    out: dict = {
        "marks": final["marks"],
        "slots": final["slots"],
        "legends": final["legends"],
        "generic_mark": average(list(final["marks"].values())),
        "generic_slot": average(list(final["slots"].values())),
        "generic_legend": average(list(final["legends"].values())),
        "sample_counts": counts,
    }

    if args.folds > 1:
        ids = sorted(data)
        folds = []
        for k in range(args.folds):
            held = {pid for i, pid in enumerate(ids) if i % args.folds == k}
            f = build(data, truth, exclude=held)
            folds.append({
                "held_out": sorted(held),
                "marks": f["marks"], "slots": f["slots"], "legends": f["legends"],
            })
        out["folds"] = folds
        print(f"交差検証用テンプレート: {args.folds}分割ぶんを同梱")

    OUT_PATH.write_text(json.dumps(out) + "\n", encoding="utf-8")
    print(f"書き出し: {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
