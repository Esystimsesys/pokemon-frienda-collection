#!/usr/bin/env python3
"""すばやさゲージと表面の数字のテンプレートを、正解データから自動生成する。

種を人手で決め打ちしない。正解データは scripts/raw/pokearcade.json（927件）で、
これはうちのOCR結果（ステータス5項目・★・タイプ・わざタイプ）と全件突き合わせて
99.9%一致を確認ずみのもの。ここから機械的にラベルを割り当てる。

  - すばやさ: speed が n のピックは、ゲージの左からn枠めまでがうまっている。
  - ポケエネ: 切り出した数字の並びと正解値の桁数が一致するものだけを教師に使えば、
              「左からn番目のグリフ＝正解値のn桁目」という対応が決定的に付く
              （build_templates.py と同じやり方）。

すばやさは2周する。1周目は位置合わせなしで種を作り、それを使って2周目の
切り出し位置をそろえてから作り直す（build_header_templates.py と同じ）。

ポケエネは「テンプレートで読んで正解と合ったものだけを教師にする」ような
選び方はしない。読みまちがえやすい数字ほど教師から外れてしまい、まちがいを
自分で強めてしまうため（実際に6が5に化ける率が15%→38%に悪化した）。
教師にするのは、正解の桁数と数が合う切り出しが1か所にしか無いものだけ。

出力: scripts/ocr/extra_templates.json

--folds N を付けると N分割の交差検証用テンプレートも作る（自己一致による
過大評価を避けて正解率を測るため）。ふだんは付けずに作ること。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extra_ocr as E  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
PICKS_PATH = ROOT / "src" / "data" / "picks.json"
ARCADE_PATH = ROOT / "scripts" / "raw" / "pokearcade.json"
IMAGES_DIR = ROOT / "scripts" / "raw" / "pick_images"
OUT_PATH = Path(__file__).resolve().parent / "extra_templates.json"


def average(vectors: list[list[float]]) -> list[float]:
    n = len(vectors[0])
    acc = [0.0] * n
    for v in vectors:
        for i, x in enumerate(v):
            acc[i] += x
    # ファイルを肥大させないよう5桁に丸める（NCCの結果は変わらない）
    return [round(x / len(vectors), 5) for x in acc]


def load_truth() -> dict[str, dict]:
    return {r["id"]: r for r in json.loads(ARCADE_PATH.read_text(encoding="utf-8"))}


def extract_all(
    picks: list[dict], generic: list[float] | None, truth: dict | None = None
) -> tuple[dict, list, dict[str, int]]:
    """全ピックからすばやさの5枠を取り出す。truth を渡すとポケエネの教師も集める。

    generic を渡すとすばやさの切り出し位置のずれを直してから取り出す。
    表面の行のベクトルは1枚ぶんずつその場で教師にして捨てる。
    全部かかえると数字1文字が560個の小数で、1枚に20案あるので1GBを超えてしまう。
    """
    out: dict[str, dict] = {}
    samples: list[tuple[str, str, list[float], int]] = []
    errors: dict[str, int] = {}
    for i, p in enumerate(picks):
        path = IMAGES_DIR / f"{p['id']}.webp"
        if not path.exists():
            errors["image_missing"] = errors.get("image_missing", 0) + 1
            continue
        img = E.open_image(path)
        if img is None:
            errors["load_failed"] = errors.get("load_failed", 0) + 1
            continue
        rec: dict = {}
        anchor = E.find_back_anchor(img)
        if anchor is None:
            errors["anchor_not_found"] = errors.get("anchor_not_found", 0) + 1
        else:
            patches, _offset = E.extract_speed(img, anchor, generic)
            rec["speed_patches"] = patches
        out[p["id"]] = rec
        if truth is not None:
            samples.extend(energy_teachers(p["id"], truth, E.energy_rows(img)))
        if (i + 1) % 100 == 0:
            print(f"  読み取り中 {i + 1}/{len(picks)}枚", file=sys.stderr)
    return out, samples, errors


# --- すばやさ ---------------------------------------------------------------
def build_speed(truth: dict, data: dict, exclude: set[str] | None = None) -> list[list[float]]:
    slots = []
    for k in range(E.SPEED_SLOTS):
        vs = [
            data[pid]["speed_patches"][k]
            for pid, t in truth.items()
            if t.get("speed") is not None and t["speed"] > k
            and pid in data and "speed_patches" in data[pid]
            and not (exclude and pid in exclude)
        ]
        if not vs:
            raise SystemExit(f"すばやさ{k + 1}枠めの教師サンプルが無い")
        slots.append(average(vs))
    return slots


# --- ポケエネ ---------------------------------------------------------------
def _same_place(a: tuple, b: tuple) -> bool:
    """2つの行がだいたい同じ場所を指しているか。

    明るさの切り方を変えると外接矩形が1〜3pxずれるので、ぴったり同じにはならない。
    重なりぐあいで見る。
    """
    ox = min(a[2], b[2]) - max(a[0], b[0])
    oy = min(a[3], b[3]) - max(a[1], b[1])
    if ox <= 0 or oy <= 0:
        return False
    inter = ox * oy
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter >= 0.7 * max(area_a, area_b)


def energy_teachers(
    pick_id: str, truth: dict, rows: list[dict]
) -> list[tuple[str, str, list[float], int]]:
    """1枚から (pick_id, 数字, グリフベクトル, 囲まれた空きの数) の教師サンプルを作る。

    切り出したグリフ数と正解値の桁数が一致するものだけを使えば、
    「左からn番目のグリフ＝正解値のn桁目」という対応が決定的に付く。
    さらに、割らずに済んだ（数字が1文字ずつ別々の成分になった）案が
    1か所からしか出てこないものに限る。どこが数字か決めきれないものを
    混ぜると、まちがった形が平均に入ってしまう。

    明るさの切り方ちがいで同じ場所が何度も出てくるぶんは、全部そのまま教師にする。
    切り方によって字の太さが変わるので、まぜたほうがテンプレートが丈夫になる。
    """
    energy = truth.get(pick_id, {}).get("energy")
    if energy is None:
        return []
    want = str(energy)
    hits = [r for r in rows if r["clean"] and len(r["glyphs"]) == len(want)]
    if not hits:
        return []
    head = tuple(hits[0]["box"])
    if not all(_same_place(head, tuple(r["box"])) for r in hits[1:]):
        return []
    out = []
    for r in hits:
        for ch, g, n in zip(want, r["glyphs"], r["holes"]):
            out.append((pick_id, ch, g, n))
    return out


def average_samples(
    samples: list[tuple[str, str, list[float], int]], exclude: set[str] | None = None
) -> dict[str, list[float]]:
    by: dict[str, list[list[float]]] = {}
    for pid, ch, g, _n in samples:
        if exclude and pid in exclude:
            continue
        by.setdefault(ch, []).append(g)
    return {ch: average(v) for ch, v in by.items()}


def hole_counts(samples: list[tuple[str, str, list[float], int]]) -> dict[str, int]:
    """数字ごとの「囲まれた空き」の数を、教師サンプルの多数決で決める。"""
    tally: dict[str, dict[int, int]] = {}
    for _pid, ch, _g, n in samples:
        tally.setdefault(ch, {})[n] = tally.setdefault(ch, {}).get(n, 0) + 1
    out = {}
    for ch, hist in tally.items():
        best = max(hist.items(), key=lambda kv: kv[1])
        # ばらつきが大きい数字は決め手にしない（決め打ちでまちがえるほうが怖い）
        if best[1] / sum(hist.values()) >= 0.9:
            out[ch] = best[0]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", type=int, default=0, help="交差検証用テンプレートも作る場合の分割数")
    args = ap.parse_args()

    picks = json.loads(PICKS_PATH.read_text(encoding="utf-8"))
    truth = load_truth()

    # ポケエネの教師は1周目のついでに集める（すばやさの位置合わせとは無関係なので）
    print("1周目（すばやさの位置合わせなし・ポケエネの教師集め）...", file=sys.stderr)
    rough, samples, errors = extract_all(picks, None, truth)
    if errors:
        print(f"  取り出せなかったもの: {errors}")
    seed_slots = build_speed(truth, rough)

    print("2周目（すばやさの位置合わせあり）...", file=sys.stderr)
    data, _s2, errors2 = extract_all(picks, seed_slots[0])
    if errors2:
        print(f"  取り出せなかったもの: {errors2}")
    slots = build_speed(truth, data)

    energies = [t["energy"] for t in truth.values() if t.get("energy") is not None]
    lo, hi = min(energies), max(energies)

    digits = average_samples(samples)
    holes = hole_counts(samples)
    missing = [d for d in "0123456789" if d not in digits]
    if missing:
        raise SystemExit(f"テンプレートを作れない数字がある: {missing}")

    counts: dict[str, int] = {}
    for _pid, ch, _g, _n in samples:
        counts[ch] = counts.get(ch, 0) + 1
    teachers = len({pid for pid, _, _, _ in samples})
    print(f"\nすばやさの教師サンプル:")
    for k in range(E.SPEED_SLOTS):
        n = sum(1 for t in truth.values() if t.get("speed") is not None and t["speed"] > k)
        print(f"  左から{k + 1}枠めの教師サンプル: {n}枚")
    print(f"ポケエネの教師: {teachers}枚 / {len(samples)}グリフ")
    print("  数字ごと: " + ", ".join(f"{d}={counts.get(d, 0)}" for d in "0123456789"))
    print("  囲まれた空きの数: " + ", ".join(f"{d}={holes.get(d, '?')}" for d in "0123456789"))
    print(f"ポケエネの値のはんい: {lo}〜{hi}")

    out: dict = {
        "speed_slots": slots,
        "speed_generic": slots[0],
        "energy_digits": digits,
        "energy_holes": holes,
        "energy_range": [lo, hi],
        "energy_norm": [E.ENERGY_NORM_W, E.ENERGY_NORM_H],
        "energy_sample_counts": counts,
    }

    if args.folds > 1:
        ids = sorted(data)
        folds = []
        for k in range(args.folds):
            held = {pid for i, pid in enumerate(ids) if i % args.folds == k}
            folds.append({
                "held_out": sorted(held),
                "speed_slots": build_speed(truth, data, exclude=held),
                "energy_digits": average_samples(samples, exclude=held),
                "energy_holes": holes,
            })
        out["folds"] = folds
        print(f"交差検証用テンプレート: {args.folds}分割ぶんを同梱")

    OUT_PATH.write_text(json.dumps(out) + "\n", encoding="utf-8")
    print(f"書き出し: {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
