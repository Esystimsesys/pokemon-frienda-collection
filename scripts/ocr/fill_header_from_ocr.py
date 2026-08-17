#!/usr/bin/env python3
"""公式ピック画像の裏面ヘッダーをOCRして、picks.json の types / grade 欠損を埋める下ごしらえをする。

進め方:
  1. --scores   : しきい値を決めるための、一致度の分布を出す。
  2. --validate : すでに types / grade が入っているピックに対して、カバー率と正解率を測る。
                  --folds を付けると交差検証（自分自身をテンプレートに含めない）で測る。
  3. --run-all  : 全958件を読み取り、結果を scripts/raw/ocr_header.json に書き出す。
                  picks.json には一切書き込まない。

読めなかったものは types なら空、grade なら null のままにして、推測では埋めない。
既存の値も上書きしない（正解データとして使うだけ）。

firstMoveType は「裏面のいちばん上のわざ欄のタイプ」。わざの名前は読み取って
いないので Move 型（name が必須）としてはまだ使えない参考値。1行目がわざでは
ないカード（メガシンカの行）や、正解データにドラゴンのわざが1件も無くて
テンプレートを作れないぶんは読めなかった扱いになる。
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
TEMPLATES_PATH = Path(__file__).resolve().parent / "header_templates.json"
OUT_JSON = ROOT / "scripts" / "raw" / "ocr_header.json"

# 採否ライン。--scores で測った実測値から余裕を取った値。
#   アイコンのもようの強さ: 空の枠は最大0.004、アイコンがある枠は最小0.099
#   アイコンの一致度      : 正解データでの最小0.917 / 2位との差の最小0.151
#   ★の一致度            : ★あり枠の最小0.839 / ★なし枠の最大0.351
#                           「スペシャル」の黄色い文字は最大0.726なので★なし側に落ちる
ICON_MIN_CONTRAST = 0.05
ICON_MIN_SCORE = 0.80
ICON_MIN_MARGIN = 0.08
# 帯に斜めの色わけが入っていると contrast だけでは空と言い切れない。
# 全958枚を見ると、2枠目の一致度は「アイコンあり0.899以上／アイコンなし0.30以下」に
# きれいに分かれるので、この線より下はアイコンが無いものとして扱う。
ICON_MAX_SCORE_EMPTY = 0.55
STAR_MIN_SCORE = 0.82
STAR_MAX_ABSENT = 0.76
# わざ欄1行目のタイプ。正解データ272枚での最小は0.966 / 2位との差の最小は0.182。
# 1行目がわざではないカード（メガシンカの行など）はどのタイプにも当たらないので
# ここで落ちる。ドラゴンはテンプレートが作れていないので必ず落ちる。
MOVE_MIN_SCORE = 0.90
MOVE_MIN_MARGIN = 0.10

"""
picks.json の types（旧ファンサイト由来）が公式の裏面と食い違っていたぶん。
テンプレート照合の結果と突き合わせて見つかり、公式画像を目視で確認した。
いずれも2つめのタイプが抜けているケース。
検証時の「補正後の正解率」を出すためだけに使い、picks.json は書き換えない。
"""
VERIFIED_GT_FIXES: dict[str, list[str]] = {
    "1-1-040": ["ほのお", "ひこう"],  # リザードン。ひこうが抜けていた
    "1-1-047": ["でんき", "ひこう"],  # カイデン。ひこうが抜けていた
    "1-2-005": ["くさ", "いわ"],      # オーガポン（いしずえのめん）。くさが抜けていた
}

"""わざ欄1行目のタイプについても同じ。いずれも公式画像を目視で確認した。"""
VERIFIED_MOVE_FIXES: dict[str, str] = {
    "1-2-005": "いわ",    # オーガポン（いしずえのめん）のツタこんぼう。くさ→いわ
    "1-3-002": "ほのお",  # オーガポン（かまどのめん）のツタこんぼう。くさ→ほのお
    "1-4-004": "みず",    # オーガポン（いどのめん）のツタこんぼう。くさ→みず
    "1-3-034": "みず",    # エンペルト。旧データはマッハパンチだが、裏面はバブルこうせん
}


def load_templates() -> dict:
    if not TEMPLATES_PATH.exists():
        raise SystemExit("先に npm run ocr:build-header-templates を実行すること")
    return json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))


def extract_all(picks: list[dict], aligner: H.Aligner) -> tuple[dict, dict[str, int]]:
    data: dict[str, dict] = {}
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
        data[p["id"]] = rec
        if (i + 1) % 200 == 0:
            print(f"  読み取り中 {i + 1}/{len(picks)}枚", file=sys.stderr)
    return data, errors


# --- しきい値を決めるための分布 --------------------------------------------
def show_scores(picks: list[dict], data: dict, matcher: H.HeaderMatcher) -> None:
    icon_pos: list[tuple[float, float, str, int, str, str]] = []
    empty_contrast: list[tuple[float, str]] = []
    filled_contrast: list[tuple[float, str]] = []
    for p in picks:
        rec = data.get(p["id"])
        if rec is None or not p["types"]:
            continue
        for slot in range(H.ICON_SLOTS):
            c = H.icon_contrast(rec["icons"][slot])
            if slot < len(p["types"]):
                filled_contrast.append((c, p["id"]))
                t, s, m = matcher.match_icon(rec["icons"][slot])
                icon_pos.append((s, m, p["id"], slot, t, p["types"][slot]))
            else:
                empty_contrast.append((c, p["id"]))

    print("\n=== タイプアイコン ===")
    print(f"  アイコンがある枠 {len(filled_contrast)}枠: もようの強さ 最小 {min(filled_contrast)[0]:.4f}")
    print(f"  空の枠           {len(empty_contrast)}枠: もようの強さ 最大 {max(empty_contrast)[0]:.4f}"
          f"（上位: {[(round(c, 3), i) for c, i in sorted(empty_contrast, reverse=True)[:4]]}）")
    icon_pos.sort()
    print(f"  一致度: 最小 {icon_pos[0][0]:.3f} / 2位との差の最小 {min(x[1] for x in icon_pos):.3f}")
    print(f"    低いほう: {[(round(x[0], 3), x[2], x[3]) for x in icon_pos[:5]]}")

    print("\n=== ★ ===")
    for k in range(H.STAR_SLOTS):
        pos, neg = [], []
        for p in picks:
            rec = data.get(p["id"])
            if rec is None or p["grade"] is None:
                continue
            s = matcher.match_star(rec["stars"][k], k)
            (pos if p["grade"] > k else neg).append((s, p["id"]))
        line = f"  右から{k + 1}番目: ★あり{len(pos)}枚 最小 {min(pos)[0]:.3f}"
        if neg:
            line += f" / ★なし{len(neg)}枚 最大 {max(neg)[0]:.3f}"
        print(line)
    # 「スペシャル」の黄色い文字がどれくらい★に似てしまうか
    sp = sorted(
        ((matcher.match_star(data[p["id"]]["stars"][0], 0), p["id"])
         for p in picks if p["id"] in data and p["group"] == "special"),
        reverse=True,
    )
    print(f"  スペシャルピックの右端枠: 上位 {[(round(s, 3), i) for s, i in sp[:5]]}")


# --- 検証 -----------------------------------------------------------------
def _matcher_for(pick_id: str, base: H.HeaderMatcher, folds: list | None) -> H.HeaderMatcher:
    """交差検証のとき、そのピックを含まないテンプレートを返す。"""
    if not folds:
        return base
    for f in folds:
        if pick_id in f["held_out"]:
            return f["matcher"]
    return base


def validate(
    picks: list[dict], data: dict, base: H.HeaderMatcher, folds: list | None, apply_fixes: bool
) -> None:
    head = "交差検証（自分自身をテンプレートに含めない）" if folds else "自己一致もふくむ単純検証"
    if apply_fixes:
        head += f" / picks.json 側の誤り{len(VERIFIED_GT_FIXES)}件（目視確認済み）を補正"
    print(f"\n############ {head} ############")

    t_total = t_read = t_ok = 0
    t_bad: list[str] = []
    t_reasons: dict[str, int] = {}
    for p in picks:
        if not p["types"] or p["id"] not in data:
            continue
        t_total += 1
        m = _matcher_for(p["id"], base, folds)
        got, why = m.read_types(data[p["id"]]["icons"], ICON_MIN_CONTRAST, ICON_MIN_SCORE, ICON_MIN_MARGIN, ICON_MAX_SCORE_EMPTY)
        if got is None:
            t_reasons[why] = t_reasons.get(why, 0) + 1
            continue
        t_read += 1
        expected = VERIFIED_GT_FIXES.get(p["id"], p["types"]) if apply_fixes else p["types"]
        if got == expected:
            t_ok += 1
        else:
            t_bad.append(f"{p['id']} {p['name']}: 読み取り{got} != 正解{expected}")
    print(f"\ntypes : 正解データ{t_total}件 / 読取できた{t_read}件"
          f"(カバー率 {t_read / t_total * 100:.1f}%) / 既存と一致{t_ok}件"
          f"({t_ok / t_read * 100:.2f}%)")
    if t_reasons:
        print(f"  読めなかった理由: {t_reasons}")
    if t_bad:
        print(f"  既存と食いちがい {len(t_bad)}件:")
        for x in t_bad:
            print(f"    {x}")

    m_total = m_read = m_ok = 0
    m_bad: list[str] = []
    m_reasons: dict[str, int] = {}
    for p in picks:
        if p["id"] not in data or not p["moves"] or not p["moves"][0].get("type"):
            continue
        m_total += 1
        mm = _matcher_for(p["id"], base, folds)
        got, why = mm.read_move_type(data[p["id"]]["move"], MOVE_MIN_SCORE, MOVE_MIN_MARGIN)
        if got is None:
            m_reasons[why] = m_reasons.get(why, 0) + 1
            continue
        m_read += 1
        want = VERIFIED_MOVE_FIXES.get(p["id"], p["moves"][0]["type"]) if apply_fixes else p["moves"][0]["type"]
        if got == want:
            m_ok += 1
        else:
            m_bad.append(f"{p['id']} {p['name']} {p['moves'][0]['name']}: 読み取り{got} != 正解{want}")
    print(f"\nmoves[0].type : 正解データ{m_total}件 / 読取できた{m_read}件"
          f"(カバー率 {m_read / m_total * 100:.1f}%) / 既存と一致{m_ok}件"
          f"({m_ok / m_read * 100:.2f}%)")
    if m_reasons:
        print(f"  読めなかった理由: {m_reasons}")
    if m_bad:
        print(f"  既存と食いちがい {len(m_bad)}件:")
        for x in m_bad:
            print(f"    {x}")

    g_total = g_read = g_ok = 0
    g_bad: list[str] = []
    g_reasons: dict[str, int] = {}
    for p in picks:
        if p["grade"] is None or p["id"] not in data:
            continue
        g_total += 1
        m = _matcher_for(p["id"], base, folds)
        got, why = m.read_grade(data[p["id"]]["stars"], STAR_MIN_SCORE, STAR_MAX_ABSENT)
        if got is None:
            g_reasons[why] = g_reasons.get(why, 0) + 1
            continue
        g_read += 1
        if got == p["grade"]:
            g_ok += 1
        else:
            g_bad.append(f"{p['id']} {p['name']}: 読み取り★{got} != 既存★{p['grade']}")
    print(f"\ngrade : 正解データ{g_total}件 / 読取できた{g_read}件"
          f"(カバー率 {g_read / g_total * 100:.1f}%) / 既存と一致{g_ok}件"
          f"({g_ok / g_read * 100:.2f}%)")
    if g_reasons:
        print(f"  読めなかった理由: {g_reasons}")
    if g_bad:
        print(f"  既存と食いちがい {len(g_bad)}件:")
        for x in g_bad:
            print(f"    {x}")


# --- 全件 -----------------------------------------------------------------
def run_all(picks: list[dict], data: dict, matcher: H.HeaderMatcher, errors: dict[str, int]) -> None:
    records = []
    t_reasons: dict[str, int] = {}
    g_reasons: dict[str, int] = {}
    t_filled = g_filled = m_filled = 0
    m_reasons: dict[str, int] = {}
    t_gap = sum(1 for p in picks if not p["types"])
    g_gap = sum(1 for p in picks if p["grade"] is None)
    t_conflict: list[str] = []
    g_conflict: list[str] = []

    for p in picks:
        rec = data.get(p["id"])
        if rec is None:
            records.append({"id": p["id"], "types": [], "grade": None, "firstMoveType": None,
                            "reason": {"types": "extract_failed", "grade": "extract_failed", "firstMoveType": "extract_failed"}})
            t_reasons["extract_failed"] = t_reasons.get("extract_failed", 0) + 1
            g_reasons["extract_failed"] = g_reasons.get("extract_failed", 0) + 1
            continue
        types, t_why = matcher.read_types(rec["icons"], ICON_MIN_CONTRAST, ICON_MIN_SCORE, ICON_MIN_MARGIN, ICON_MAX_SCORE_EMPTY)
        grade, g_why = matcher.read_grade(rec["stars"], STAR_MIN_SCORE, STAR_MAX_ABSENT)
        move_type, m_why = matcher.read_move_type(rec["move"], MOVE_MIN_SCORE, MOVE_MIN_MARGIN)
        if move_type is None:
            m_reasons[m_why] = m_reasons.get(m_why, 0) + 1
        else:
            m_filled += 1
        if types is None:
            t_reasons[t_why] = t_reasons.get(t_why, 0) + 1
        elif not p["types"]:
            t_filled += 1
        elif types != p["types"]:
            t_conflict.append(f"{p['id']} {p['name']}: 読み取り{types} != 既存{p['types']}")
        if grade is None:
            g_reasons[g_why] = g_reasons.get(g_why, 0) + 1
        elif p["grade"] is None:
            g_filled += 1
        elif grade != p["grade"]:
            g_conflict.append(f"{p['id']} {p['name']}: 読み取り★{grade} != 既存★{p['grade']}")

        records.append({
            "id": p["id"],
            "types": types or [],
            "grade": grade,
            # 裏面のいちばん上のわざ欄のタイプ。わざの名前は読み取れていないので、
            # Move 型（name 必須）としてはまだ使えない参考値。
            "firstMoveType": move_type,
            "reason": {"types": t_why, "grade": g_why, "firstMoveType": m_why},
        })

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if errors:
        print(f"読み取れなかった画像: {errors}")
    print(f"\n書き出し先: {OUT_JSON.relative_to(ROOT)}")
    print(f"\ntypes : 空だった{t_gap}件のうち {t_filled}件を新しく埋められる")
    print(f"  読めなかった理由: {t_reasons}")
    print(f"grade : null だった{g_gap}件のうち {g_filled}件を新しく埋められる")
    print(f"  読めなかった理由: {g_reasons}")
    print(f"firstMoveType : {m_filled}/{len(picks)}件を読み取れた（参考値）")
    print(f"  読めなかった理由: {m_reasons}")
    if t_conflict:
        print(f"\n既存 types と食いちがい {len(t_conflict)}件:")
        for x in t_conflict:
            print(f"  {x}")
    if g_conflict:
        print(f"\n既存 grade と食いちがい {len(g_conflict)}件:")
        for x in g_conflict:
            print(f"  {x}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", action="store_true", help="しきい値を決めるための一致度の分布を出す")
    ap.add_argument("--validate", action="store_true", help="既存データに対するカバー率・正解率を測る")
    ap.add_argument("--folds", action="store_true", help="--validate を交差検証で行う")
    ap.add_argument("--run-all", action="store_true", help="全958件を読み取り scripts/raw/ocr_header.json に書き出す")
    args = ap.parse_args()
    if not (args.scores or args.validate or args.run_all):
        ap.print_help()
        sys.exit(1)

    picks = json.loads(PICKS_PATH.read_text(encoding="utf-8"))
    templates = load_templates()
    aligner = H.Aligner(templates["generic_icon"], templates["stars"][0], templates.get("generic_move"))
    base = H.HeaderMatcher(templates)

    print(f"読み取り対象: {len(picks)}件", file=sys.stderr)
    data, errors = extract_all(picks, aligner)

    if args.scores:
        show_scores(picks, data, base)
    if args.validate:
        folds = None
        if args.folds:
            if "folds" not in templates:
                raise SystemExit("交差検証用テンプレートが無い。build_header_templates.py --folds 5 を実行すること")
            folds = [
                {"held_out": set(f["held_out"]), "matcher": H.HeaderMatcher(f)}
                for f in templates["folds"]
            ]
        for apply_fixes in (False, True):
            validate(picks, data, base, folds, apply_fixes)
    if args.run_all:
        run_all(picks, data, base, errors)


if __name__ == "__main__":
    main()
