#!/usr/bin/env python3
"""タイプアイコン・★・わざアイコンのテンプレートを、picks.json の既存データから自動生成する。

種を人手で決め打ちしない。既存データと裏面の並びは対応づけが決まっているので、
そこからラベルを機械的に割り当てられる。
  - タイプ: types が n個入っているピックは、ヘッダーの左からn個めまでがそのタイプ。
            280件が正解データ（1タイプ105件・2タイプ175件）。
  - ★    : grade が入っている455件について、右から grade 個ぶんの枠が★。
  - わざ  : moves[0].type が入っている272件を、わざ欄1行目のアイコンの正解とする。
            旧データはわざを1つしか持っていないので、教師にできるのも1行目だけ。
            ドラゴンのわざは272件に1件も無いのでテンプレートを作れない。

2周する。1周目は位置合わせなしで平均テンプレートを作り、それを使って
2周目の切り出し位置をそろえてから作り直す。アイコンは36pxしかないので
1〜2pxのずれで一致度が0.2近く落ちる。位置合わせの有無で誤りが3件→1件に減った。

出力: scripts/ocr/header_templates.json

--folds N を付けると N分割の交差検証用テンプレートも作る（自己一致による
過大評価を避けて正解率を測るため）。位置合わせに使う平均テンプレートは
タイプにも★数にもよらないので、分割の対象は各クラスのテンプレートだけ。
ファイルが6倍にふくらむので、ふだんは付けずに作る。交差検証で測りたいときは
  python3 scripts/ocr/build_header_templates.py --folds 5
  python3 scripts/ocr/fill_header_from_ocr.py --validate --folds
の順で実行し、終わったら --folds なしで作り直しておくこと。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import header_ocr as H  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
PICKS_PATH = ROOT / "src" / "data" / "picks.json"
IMAGES_DIR = ROOT / "scripts" / "raw" / "pick_images"
OUT_PATH = Path(__file__).resolve().parent / "header_templates.json"


def average(vectors: list[list[float]]) -> list[float]:
    n = len(vectors[0])
    acc = [0.0] * n
    for v in vectors:
        for i, x in enumerate(v):
            acc[i] += x
    # ファイルを肥大させないよう5桁に丸める（NCCの結果は変わらない）
    return [round(x / len(vectors), 5) for x in acc]


def extract_all(picks: list[dict], aligner: H.Aligner | None, label: str) -> tuple[dict, dict[str, int]]:
    """全ピックからヘッダーのベクトルを取り出す。"""
    out: dict[str, dict] = {}
    errors: dict[str, int] = {}
    for i, p in enumerate(picks):
        path = IMAGES_DIR / f"{p['id']}.webp"
        if not path.exists():
            errors["image_missing"] = errors.get("image_missing", 0) + 1
            continue
        rec, err = H.extract(path, aligner)
        if err:
            errors[err] = errors.get(err, 0) + 1
            continue
        out[p["id"]] = rec
        if (i + 1) % 200 == 0:
            print(f"  {label}: {i + 1}/{len(picks)}枚", file=sys.stderr)
    return out, errors


def build(picks: list[dict], data: dict, exclude: set[str] | None = None) -> dict:
    """タイプごと・★枠ごとの平均テンプレートを作る。"""
    by_type: dict[str, list[list[float]]] = {}
    for p in picks:
        rec = data.get(p["id"])
        if rec is None or (exclude and p["id"] in exclude):
            continue
        for slot, t in enumerate(p["types"][:H.ICON_SLOTS]):
            by_type.setdefault(t, []).append(rec["icons"][slot])

    by_move: dict[str, list[list[float]]] = {}
    for p in picks:
        rec = data.get(p["id"])
        if rec is None or (exclude and p["id"] in exclude) or "move" not in rec:
            continue
        # わざは1つめしか正解データが無い（旧ファンサイトが1つしか持っていない）
        if p["moves"] and p["moves"][0].get("type"):
            by_move.setdefault(p["moves"][0]["type"], []).append(rec["move"])

    stars = []
    for k in range(H.STAR_SLOTS):
        vs = [
            data[p["id"]]["stars"][k]
            for p in picks
            if p["grade"] is not None and p["grade"] > k
            and p["id"] in data and not (exclude and p["id"] in exclude)
        ]
        stars.append(average(vs))
    return {
        "icons": {t: average(v) for t, v in by_type.items()},
        "moves": {t: average(v) for t, v in by_move.items()},
        "stars": stars,
        "counts": {t: len(v) for t, v in by_type.items()},
        "move_counts": {t: len(v) for t, v in by_move.items()},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", type=int, default=0, help="交差検証用テンプレートも作る場合の分割数")
    args = ap.parse_args()

    picks = json.loads(PICKS_PATH.read_text(encoding="utf-8"))

    print("1周目（位置合わせなし）...", file=sys.stderr)
    rough, errors = extract_all(picks, None, "1周目")
    if errors:
        print(f"  取り出せなかったもの: {errors}")
    seed = build(picks, rough)

    # 位置合わせ用の平均テンプレート。タイプによらない「アイコンらしさ」と、
    # いちばん右の★の形。
    aligner = H.Aligner(
        average(list(seed["icons"].values())),
        seed["stars"][0],
        average(list(seed["moves"].values())),
    )

    print("2周目（位置合わせあり）...", file=sys.stderr)
    data, errors2 = extract_all(picks, aligner, "2周目")
    if errors2:
        print(f"  取り出せなかったもの: {errors2}")
    final = build(picks, data)

    counts = final.pop("counts")
    move_counts = final.pop("move_counts")
    missing = [t for t in H.TYPE_ORDER if t not in final["icons"]]
    if missing:
        raise SystemExit(f"テンプレートを作れないタイプがある: {missing}")
    extra = [t for t in final["icons"] if t not in H.TYPE_ORDER]
    if extra:
        raise SystemExit(f"pokemonTypes.ts に無いタイプ名が picks.json に入っている: {extra}")

    print(f"わざ欄1行目の教師サンプル: {sum(move_counts.values())}枚"
          f"（{len(move_counts)}タイプ。ドラゴンは正解データに1件も無いので読めない）")
    print(f"アイコンの教師サンプル: {sum(counts.values())}枠")
    print("  " + ", ".join(f"{t}={counts[t]}" for t in H.TYPE_ORDER))
    for k in range(H.STAR_SLOTS):
        n = sum(1 for p in picks if p["grade"] is not None and p["grade"] > k)
        print(f"  ★{k + 1}つめの枠（右から{k + 1}番目）の教師サンプル: {n}枚")

    out: dict = {
        "icons": final["icons"],
        "moves": final["moves"],
        "stars": final["stars"],
        "generic_icon": average(list(final["icons"].values())),
        "generic_move": average(list(final["moves"].values())),
        "sample_counts": counts,
        "move_sample_counts": move_counts,
    }

    if args.folds > 1:
        ids = sorted(data.keys())
        folds = []
        for k in range(args.folds):
            held = {pid for i, pid in enumerate(ids) if i % args.folds == k}
            f = build(picks, data, exclude=held)
            folds.append({"held_out": sorted(held), "icons": f["icons"], "moves": f["moves"], "stars": f["stars"]})
        out["folds"] = folds
        print(f"交差検証用テンプレート: {args.folds}分割ぶんを同梱")

    OUT_PATH.write_text(json.dumps(out) + "\n", encoding="utf-8")
    print(f"書き出し: {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
