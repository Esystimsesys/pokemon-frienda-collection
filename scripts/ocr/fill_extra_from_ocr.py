#!/usr/bin/env python3
"""すばやさ（裏面）とポケエネ（表面）を券面から読み取り、中間ファイルに書き出す。

この2つはファンサイト（pokearcade）から借りていた最後の項目で、券面から読めれば
全データが公式由来になる。

進め方:
  1. --scores   : しきい値を決めるための、一致度の分布を出す。
  2. --validate : 正解データ（scripts/raw/pokearcade.json の927件）に対して
                  カバー率と一致率を測る。--folds を付けると交差検証
                  （自分自身をテンプレートに含めない）で測る。
  3. --run-all  : 全958件を読み取り、結果を scripts/raw/ocr_extra.json に書き出す。
                  picks.json には一切書き込まない。

読めなかったものは null のままにして、推測では埋めない。
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
OUT_JSON = ROOT / "scripts" / "raw" / "ocr_extra.json"

# 採否ライン。--scores で測った実測値から余裕を取った値。
#   すばやさ: うまっている枠の一致度は最小0.926、うまっていない枠は最大0.022。
#             あいだがまるごと空いているので、どこで切っても結果は変わらない。
SPEED_MIN_SCORE = 0.70
SPEED_MAX_ABSENT = 0.60
#   ポケエネ: 一致度をどこで切るかで、読める枚数と正しさが釣り合う。
#     0.75 → カバー率 90.9% / 一致率 99.64%
#     0.78 → カバー率 85.8% / 一致率 99.75%   ← ここを採る
#     0.80 → カバー率 71.3% / 一致率 100.0%
#   採用基準の99.5%に余裕を持たせつつ、読める枚数をなるべく落とさない線。
ENERGY_MIN_SCORE = 0.78
ENERGY_MIN_MARGIN = 0.02


def load_truth() -> dict[str, dict]:
    if not ARCADE_PATH.exists():
        raise SystemExit(f"{ARCADE_PATH.name} が無い。先に npm run build:pokearcade を実行すること")
    return {r["id"]: r for r in json.loads(ARCADE_PATH.read_text(encoding="utf-8"))}


def extract_all(picks: list[dict], generic: list[float]) -> tuple[dict, dict[str, int]]:
    data: dict[str, dict] = {}
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
        rec: dict = {"rows": E.energy_rows(img)}
        anchor = E.find_back_anchor(img)
        if anchor is None:
            errors["anchor_not_found"] = errors.get("anchor_not_found", 0) + 1
        else:
            rec["speed_patches"], _off = E.extract_speed(img, anchor, generic)
        data[p["id"]] = rec
        if (i + 1) % 200 == 0:
            print(f"  読み取り中 {i + 1}/{len(picks)}枚", file=sys.stderr)
    return data, errors


class Bundle:
    """すばやさとポケエネの照合器をひとまとめにしたもの。"""

    def __init__(self, templates: dict):
        self.speed = E.SpeedMatcher(templates["speed_slots"])
        self.energy = E.EnergyMatcher(templates["energy_digits"], templates.get("energy_holes"))


def _bundle_for(pick_id: str, base: Bundle, folds: list | None) -> Bundle:
    """交差検証のとき、そのピックを含まないテンプレートを返す。"""
    if not folds:
        return base
    for f in folds:
        if pick_id in f["held_out"]:
            return f["bundle"]
    return base


# --- しきい値を決めるための分布 --------------------------------------------
def show_scores(truth: dict, data: dict, base: Bundle, rng: tuple[int, int]) -> None:
    print("\n=== すばやさ ===")
    for k in range(E.SPEED_SLOTS):
        pos, neg = [], []
        for pid, t in truth.items():
            rec = data.get(pid)
            if rec is None or "speed_patches" not in rec or t.get("speed") is None:
                continue
            s = base.speed.match(rec["speed_patches"][k], k)
            (pos if t["speed"] > k else neg).append((s, pid))
        line = f"  左から{k + 1}枠め: うまっている{len(pos)}枚 最小 {min(pos)[0]:.3f}"
        if neg:
            line += f" / 空いている{len(neg)}枚 最大 {max(neg)[0]:.3f}"
        print(line)

    print("\n=== ポケエネ ===")
    ok, bad = [], []
    for pid, t in truth.items():
        rec = data.get(pid)
        if rec is None or t.get("energy") is None:
            continue
        for r in rec["rows"]:
            value, worst, margin = base.energy.read_row(r["glyphs"])
            if value is None or not (rng[0] <= value <= rng[1]):
                continue
            (ok if value == t["energy"] else bad).append((worst, margin, pid, value))
    ok.sort()
    bad.sort(reverse=True)
    print(f"  正解と一致した行 {len(ok)}件: 一致度 最小 {ok[0][0]:.3f} / 2位との差の最小 {min(x[1] for x in ok):.3f}")
    print(f"    低いほう: {[(round(x[0], 3), x[2]) for x in ok[:6]]}")
    if bad:
        print(f"  正解と違う行 {len(bad)}件: 一致度 最大 {bad[0][0]:.3f}")
        print(f"    高いほう: {[(round(x[0], 3), x[2], x[3]) for x in bad[:8]]}")


# --- 検証 -----------------------------------------------------------------
def validate(truth: dict, picks: dict, data: dict, base: Bundle, folds: list | None, rng) -> None:
    head = "交差検証（自分自身をテンプレートに含めない）" if folds else "自己一致もふくむ単純検証"
    print(f"\n############ {head} ############")

    for field in ("speed", "energy"):
        total = read = ok = 0
        bad: list[str] = []
        reasons: dict[str, int] = {}
        for pid, t in truth.items():
            want = t.get(field)
            rec = data.get(pid)
            if want is None or rec is None:
                continue
            total += 1
            b = _bundle_for(pid, base, folds)
            if field == "speed":
                if "speed_patches" not in rec:
                    reasons["anchor_not_found"] = reasons.get("anchor_not_found", 0) + 1
                    continue
                got, why = b.speed.read_speed(rec["speed_patches"], SPEED_MIN_SCORE, SPEED_MAX_ABSENT)
            else:
                got, why, _d = b.energy.read_energy(
                    rec["rows"], ENERGY_MIN_SCORE, ENERGY_MIN_MARGIN, rng[0], rng[1]
                )
            if got is None:
                reasons[why] = reasons.get(why, 0) + 1
                continue
            read += 1
            if got == want:
                ok += 1
            else:
                name = picks.get(pid, {}).get("name", "")
                bad.append(f"{pid} {name}: 読み取り{got} != 正解{want}")
        label = "すばやさ" if field == "speed" else "ポケエネ"
        if read:
            print(f"\n{label} : 正解データ{total}件 / 読取できた{read}件"
                  f"(カバー率 {read / total * 100:.1f}%) / 正解と一致{ok}件"
                  f"({ok / read * 100:.2f}%)")
        else:
            print(f"\n{label} : 正解データ{total}件 / 読取できたもの無し")
        if reasons:
            print(f"  読めなかった理由: {reasons}")
        if bad:
            print(f"  正解と食いちがい {len(bad)}件:")
            for x in bad:
                print(f"    {x}")


# --- 全件 -----------------------------------------------------------------
def run_all(picks: list[dict], truth: dict, data: dict, base: Bundle, rng, errors) -> None:
    records = []
    filled = {"speed": 0, "energy": 0}
    reasons: dict[str, dict[str, int]] = {"speed": {}, "energy": {}}
    conflict: dict[str, list[str]] = {"speed": [], "energy": []}
    new: dict[str, int] = {"speed": 0, "energy": 0}

    for p in picks:
        rec = data.get(p["id"])
        row = {"id": p["id"], "speed": None, "energy": None,
               "reason": {"speed": "extract_failed", "energy": "extract_failed"}}
        if rec is not None:
            if "speed_patches" in rec:
                speed, s_why = base.speed.read_speed(
                    rec["speed_patches"], SPEED_MIN_SCORE, SPEED_MAX_ABSENT
                )
            else:
                speed, s_why = None, "anchor_not_found"
            energy, e_why, _d = base.energy.read_energy(
                rec["rows"], ENERGY_MIN_SCORE, ENERGY_MIN_MARGIN, rng[0], rng[1]
            )
            row = {"id": p["id"], "speed": speed, "energy": energy,
                   "reason": {"speed": s_why, "energy": e_why}}
        for field in ("speed", "energy"):
            got = row[field]
            if got is None:
                reasons[field][row["reason"][field]] = reasons[field].get(row["reason"][field], 0) + 1
                continue
            filled[field] += 1
            want = truth.get(p["id"], {}).get(field)
            if want is None:
                new[field] += 1
            elif want != got:
                conflict[field].append(f"{p['id']} {p['name']}: 読み取り{got} != ファンサイト{want}")
        records.append(row)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if errors:
        print(f"読み取れなかった画像: {errors}")
    print(f"\n書き出し先: {OUT_JSON.relative_to(ROOT)}")
    for field, label in (("speed", "すばやさ"), ("energy", "ポケエネ")):
        print(f"\n{label} : {filled[field]}/{len(picks)}件を読み取れた"
              f"（うちファンサイトに無かったぶん {new[field]}件）")
        if reasons[field]:
            print(f"  読めなかった理由: {reasons[field]}")
        if conflict[field]:
            print(f"  ファンサイトの値と食いちがい {len(conflict[field])}件:")
            for x in conflict[field]:
                print(f"    {x}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", action="store_true", help="しきい値を決めるための一致度の分布を出す")
    ap.add_argument("--validate", action="store_true", help="正解データに対するカバー率・一致率を測る")
    ap.add_argument("--folds", action="store_true", help="--validate を交差検証で行う")
    ap.add_argument("--run-all", action="store_true", help="全958件を読み取り scripts/raw/ocr_extra.json に書き出す")
    args = ap.parse_args()
    if not (args.scores or args.validate or args.run_all):
        ap.print_help()
        sys.exit(1)

    picks = json.loads(PICKS_PATH.read_text(encoding="utf-8"))
    truth = load_truth()
    templates = E.load_templates()
    base = Bundle(templates)
    rng = tuple(templates["energy_range"])

    print(f"読み取り対象: {len(picks)}件", file=sys.stderr)
    data, errors = extract_all(picks, templates["speed_generic"])

    if args.scores:
        show_scores(truth, data, base, rng)
    if args.validate:
        folds = None
        if args.folds:
            if "folds" not in templates:
                raise SystemExit("交差検証用テンプレートが無い。build_extra_templates.py --folds 5 を実行すること")
            folds = [
                {"held_out": set(f["held_out"]), "bundle": Bundle(f)}
                for f in templates["folds"]
            ]
        validate(truth, {p["id"]: p for p in picks}, data, base, folds, rng)
    if args.run_all:
        run_all(picks, truth, data, base, rng, errors)


if __name__ == "__main__":
    main()
