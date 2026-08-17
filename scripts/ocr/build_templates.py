#!/usr/bin/env python3
"""数字テンプレートを picks.json の既存280件（＝正解データ）から自動生成する。

種を人手で決め打ちしない。切り出したグリフ数と正解値の桁数が一致するものだけを
教師に使えば、「左からn番目のグリフ＝正解値のn桁目」という対応が決定的に付く。
それを数字ごとに平均してテンプレートとする。

出力: scripts/ocr/digit_templates.json

--folds N を付けると N分割の交差検証用テンプレートも作る（自己一致による
過大評価を避けて正解率を測るため）。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import template_ocr as T

ROOT = Path(__file__).resolve().parent.parent.parent
PICKS_PATH = ROOT / "src" / "data" / "picks.json"
IMAGES_DIR = ROOT / "scripts" / "raw" / "pick_images"
OUT_PATH = Path(__file__).resolve().parent / "digit_templates.json"

STAT_KEY = {"hp": "hp", "atk": "attack", "def": "defense", "spatk": "spAttack", "spdef": "spDefense"}


def collect_samples(picks: list[dict]) -> tuple[list[tuple[str, str, list[float]]], dict[str, int]]:
    """(pick_id, 数字, グリフベクトル) の教師サンプルを集める。"""
    samples: list[tuple[str, str, list[float]]] = []
    stats = {"images": 0, "anchor_failed": 0, "digit_count_mismatch": 0, "field_missing": 0}
    known = [p for p in picks if p.get("stats")]
    for p in known:
        path = IMAGES_DIR / f"{p['id']}.webp"
        if not path.exists():
            continue
        stats["images"] += 1
        glyphs_by_field, err = T.extract_all(path)
        if err:
            stats["anchor_failed"] += 1
            continue
        for f in T.FIELDS:
            expected = str(p["stats"][STAT_KEY[f]])
            glyphs = glyphs_by_field.get(f)
            if glyphs is None:
                stats["field_missing"] += 1
                continue
            if len(glyphs) != len(expected):
                stats["digit_count_mismatch"] += 1
                continue
            for ch, g in zip(expected, glyphs):
                samples.append((p["id"], ch, g))
    return samples, stats


def average(samples: list[tuple[str, str, list[float]]], exclude_ids: set[str] | None = None) -> dict[str, list[float]]:
    """数字ごとにグリフを平均してテンプレートを作る。"""
    acc: dict[str, list[float]] = {}
    cnt: dict[str, int] = {}
    n = T.NORM_W * T.NORM_H
    for pick_id, ch, g in samples:
        if exclude_ids and pick_id in exclude_ids:
            continue
        if ch not in acc:
            acc[ch] = [0.0] * n
            cnt[ch] = 0
        a = acc[ch]
        for i, v in enumerate(g):
            a[i] += v
        cnt[ch] += 1
    # ファイルを肥大させないよう5桁に丸める（NCCの結果は変わらない）
    return {ch: [round(v / cnt[ch], 5) for v in acc[ch]] for ch in acc}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", type=int, default=0, help="交差検証用テンプレートも作る場合の分割数")
    args = ap.parse_args()

    picks = json.loads(PICKS_PATH.read_text(encoding="utf-8"))
    samples, stats = collect_samples(picks)

    counts: dict[str, int] = {}
    for _, ch, _ in samples:
        counts[ch] = counts.get(ch, 0) + 1
    print(f"教師に使った画像: {stats['images']}枚")
    print(f"  アンカー（HPカプセル）が見つからず: {stats['anchor_failed']}枚")
    print(f"  カプセル内にグリフが見つからず: {stats['field_missing']}項目")
    print(f"  桁数が合わず教師から除外: {stats['digit_count_mismatch']}項目")
    print(f"教師サンプル総数: {len(samples)}グリフ")
    print("  数字ごと: " + ", ".join(f"{d}={counts.get(d, 0)}" for d in "0123456789"))

    missing = [d for d in "0123456789" if counts.get(d, 0) == 0]
    if missing:
        raise SystemExit(f"テンプレートを作れない数字がある: {missing}")

    out: dict = {
        "norm_w": T.NORM_W,
        "norm_h": T.NORM_H,
        "sample_counts": counts,
        "templates": average(samples),
    }

    if args.folds > 1:
        # pick単位で分割する（同じ画像のグリフが学習側と評価側に分かれないように）
        ids = sorted({pick_id for pick_id, _, _ in samples})
        folds = []
        for k in range(args.folds):
            held = {pid for i, pid in enumerate(ids) if i % args.folds == k}
            folds.append({"held_out": sorted(held), "templates": average(samples, exclude_ids=held)})
        out["folds"] = folds
        print(f"交差検証用テンプレート: {args.folds}分割ぶんを同梱")

    OUT_PATH.write_text(json.dumps(out) + "\n", encoding="utf-8")
    print(f"書き出し: {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
