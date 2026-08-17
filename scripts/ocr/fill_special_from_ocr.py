#!/usr/bin/env python3
"""公式ピック画像の裏面「2つめのわざの行」をOCRして、仕組みとわざ名の下ごしらえをする。

読み取るもの:
  - 仕組み … テラスタル / Zワザ / ダイマックス / タッグわざ（わざ欄2行目のマーク）と、
             メガシンカ（わざ欄1行目が「メガ○○ にメガシンカ！」に置きかわる）
  - 2行目のわざ名 … テラバースト・キョダイベンタツ など
  - でんせつ／まぼろし … タイプアイコンのすぐ下に出る小さな帯

進め方:
  1. --scores   : しきい値を決めるための、一致度の分布を出す。
  2. --validate : ファンサイトの表（ピック番号が直接一致した854件）に対して、
                  仕組みごとのカバー率と一致率を測る。
                  --folds を付けると交差検証（自分自身をテンプレートに含めない）で測る。
  3. --run-all  : 全958件を読み取り、結果を scripts/raw/ocr_special.json に書き出す。
                  picks.json には一切書き込まない。

読めなかったものは null のままにして、推測では埋めない。食いちがったものは
件数と中身を出す。反映するかどうかは parse_official.py 側で判断すること。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import move_ocr as M  # noqa: E402
import special_ocr as S  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
PICKS_PATH = ROOT / "src" / "data" / "picks.json"
IMAGES_DIR = ROOT / "scripts" / "raw" / "pick_images"
TEMPLATES_PATH = Path(__file__).resolve().parent / "special_templates.json"
OUT_JSON = ROOT / "scripts" / "raw" / "ocr_special.json"

FOLDS = 5

"""
ファンサイトの表が裏面と食い違っていたぶん。OCRの結果と突き合わせて見つかり、
公式画像を目視で確認した。検証時の「補正後の一致率」を出すためだけに使い、
ファンサイト側のデータもうちのデータも書き換えない。
"""
VERIFIED_TRUTH_FIXES: dict[str, set[str]] = {
    # 裏面の2行目は「Tera Blast / テラバースト」＋テラスタルの星。Zワザの行ではない。
    "1-5-020": {S.TERA},  # ハラバリー。ファンサイトは「Zわざ でんき」
}


def load_templates() -> dict:
    if not TEMPLATES_PATH.exists():
        raise SystemExit("先に npm run ocr:build-special-templates を実行すること")
    return json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))


def extract_all(picks: list[dict], aligner: S.Aligner) -> tuple[dict, dict[str, int]]:
    data: dict[str, dict] = {}
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
        data[p["id"]] = rec
        if (i + 1) % 200 == 0:
            print(f"  切り出し中 {i + 1}/{len(picks)}枚", file=sys.stderr)
    return data, errors


def read_text(picks: list[dict]) -> tuple[dict[str, dict], dict[str, dict], dict[str, str]]:
    """わざ欄1行目・2行目を Vision で読む。(1行目の生結果, 2行目の生結果, 画像側のエラー)。"""
    ids = [p["id"] for p in picks]
    reqs, errors = S.build_requests(ids, IMAGES_DIR, rows=(0, 1))
    print(f"OCR中: {len(reqs)}枠（1枠につき{M.PASSES}通り）", file=sys.stderr)
    raw = S.run_ocr(reqs)
    row0 = {k.split("#")[0]: v for k, v in raw.items() if k.endswith("#0")}
    row1 = {k.split("#")[0]: v for k, v in raw.items() if k.endswith("#1")}
    return row0, row1, errors


# --- 仕組みの判定 -----------------------------------------------------------
def resolve_mechanics(
    picks: list[dict], data: dict, row0: dict, matcher_for
) -> dict[str, tuple[str | None, str]]:
    """ID -> (仕組み or None, 理由)。

    2行目のマークと、1行目の「メガシンカ」の字を別々に見て、両方が出たら
    どちらか一方が誤りなので読めなかった扱いにする（推測でどちらかを選ばない）。
    """
    out: dict[str, tuple[str | None, str]] = {}
    for p in picks:
        rec = data.get(p["id"])
        if rec is None:
            out[p["id"]] = (None, "extract_failed")
            continue
        mech, why = matcher_for(p["id"]).read_mechanic(rec)
        is_mega, _ = S.read_mega(row0.get(p["id"], {"error": "ocr_missing"}))
        if is_mega and mech is not None:
            out[p["id"]] = (None, "mega_mark_conflict")
        elif is_mega:
            out[p["id"]] = (S.MEGA, "ok")
        else:
            out[p["id"]] = (mech, why)
    return out


# --- 2行目のわざ名 ----------------------------------------------------------
def resolve_second_names(
    picks: list[dict], row0: dict, row1: dict, mechs: dict[str, tuple[str | None, str]]
) -> tuple[dict[str, tuple[str | None, str]], dict[str, "M.Read"]]:
    """ID -> (2行目のわざ名 or None, 理由) と、1枚ごとの読み取り結果。

    タッグわざ以外の行は1行目とまったく同じやり方（上段の英語名と下段の日本語名が
    全体で矛盾しないことを唯一の裏づけにする）。突き合わせの材料には1行目の
    読み取り結果もまぜる。同じわざが1行目と2行目のどちらに出てもよく、
    材料が増えるほど食いちがいを見つけやすくなるため。

    タッグわざの行だけは上段が英語名ではなく相手ポケモンの名前（カタカナ）なので、
    英語名との突き合わせができない。相手の名前とわざ名の**両方**が7通り全一致した
    ときだけ読めたことにし、理由に tag_no_en を残して区別できるようにする。
    """
    reads: dict[str, M.Read] = {}
    tag_ids: set[str] = set()
    for p in picks:
        rec = row1.get(p["id"])
        if rec is None:
            reads[p["id"]] = M.Read(None, None, False, "ocr_missing")
            continue
        is_tag = mechs.get(p["id"], (None, ""))[0] == S.TAG
        if is_tag:
            tag_ids.add(p["id"])
        reads[p["id"]] = S.read_second_name(rec, is_tag)

    # 突き合わせの材料: 1行目＋2行目のうち、英語名つきで読めたもの
    pool: dict[str, M.Read] = {}
    for pick_id, rec in row0.items():
        pool[f"{pick_id}#0"] = M.read_one(rec)
    for pick_id, r in reads.items():
        if pick_id not in tag_ids:
            pool[f"{pick_id}#1"] = r

    resolved = M.cross_check({k: v for k, v in reads.items() if k not in tag_ids}, pool=pool)
    for pick_id in tag_ids:
        r = reads[pick_id]
        if r.why != "ok":
            resolved[pick_id] = (None, r.why)
        elif not (r.unanimous and getattr(r, "partner_unanimous", False)):
            resolved[pick_id] = (None, "ja_disagree")
        else:
            resolved[pick_id] = (r.ja, "tag_no_en")
    return resolved, reads


# --- しきい値を決めるための分布 ----------------------------------------------
def show_scores(picks: list[dict], data: dict, matcher: S.SpecialMatcher,
                truth: dict[str, set[str]], row0: dict) -> None:
    by_cls: dict[str, list[tuple[float, str]]] = defaultdict(list)
    slot_by_cls: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for p in picks:
        rec = data.get(p["id"])
        mechs = truth.get(p["id"])
        if rec is None or mechs is None:
            continue
        mechs = VERIFIED_TRUTH_FIXES.get(p["id"], mechs)
        cls = next(iter(sorted(mechs))) if mechs else "仕組みなし"
        k, s, m = matcher.match_mark(rec["mark"])
        by_cls[cls].append((s, p["id"]))
        sk, ss, sm = matcher.match_slot(rec["slot"])
        slot_by_cls[cls].append((ss if sk == "diamond" else 0.0, p["id"]))

    print("\n=== マーク枠（2行目の右はし）のいちばん高い一致度 ===")
    for cls, arr in sorted(by_cls.items()):
        arr.sort()
        print(f"  {cls:8} {len(arr):4}枚  最小 {arr[0][0]:.3f} / 中央 {arr[len(arr) // 2][0]:.3f} / 最大 {arr[-1][0]:.3f}")
        print(f"      低いほう: {[(round(s, 3), i) for s, i in arr[:3]]}"
              f" / 高いほう: {[(round(s, 3), i) for s, i in arr[-3:]]}")

    print("\n=== アイコン枠（2行目の左はし）が「ひし形」だったときの一致度 ===")
    for cls, arr in sorted(slot_by_cls.items()):
        arr.sort()
        n = sum(1 for s, _ in arr if s > 0)
        top = [(round(s, 3), i) for s, i in arr[-3:]]
        print(f"  {cls:8} {len(arr):4}枚  ひし形と出たもの {n:3}枚 / 高いほう {top}")

    print("\n=== でんせつ帯 ===")
    lg: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for p in picks:
        rec = data.get(p["id"])
        if rec is None:
            continue
        k, s, m = matcher.match_legend(rec["legend"])
        lg[k].append((s, p["id"]))
    for k, arr in sorted(lg.items()):
        arr.sort()
        print(f"  {k:6} {len(arr):4}枚  最小 {arr[0][0]:.3f} / 中央 {arr[len(arr) // 2][0]:.3f}"
              f"  低いほう {[(round(s, 3), i) for s, i in arr[:3]]}")

    print("\n=== わざ欄1行目に「メガシンカ」の字が出た回数（7通り中）===")
    hist: Counter = Counter()
    for p in picks:
        _, n = S.read_mega(row0.get(p["id"], {"error": "ocr_missing"}))
        hist[n] += 1
    print(f"  {dict(sorted(hist.items()))}")


# --- 検証 -------------------------------------------------------------------
def validate(picks: list[dict], truth: dict[str, set[str]],
             mechs: dict[str, tuple[str | None, str]], apply_fixes: bool, head: str) -> None:
    if apply_fixes:
        head += f" / ファンサイト側の誤り{len(VERIFIED_TRUTH_FIXES)}件（目視確認済み）を補正"
    print(f"\n############ {head} ############")

    total = read = 0
    reasons: Counter = Counter()
    pos = Counter()      # 正解データでその仕組みを持つ件数（読み取れたぶんだけ）
    hit = Counter()      # そのうち読み取りも一致した件数
    fp: dict[str, list[str]] = defaultdict(list)   # 誤検出
    fn: dict[str, list[str]] = defaultdict(list)   # 取りこぼし
    byid = {p["id"]: p for p in picks}

    for pick_id, want in truth.items():
        if pick_id not in byid:
            continue
        want = VERIFIED_TRUTH_FIXES.get(pick_id, want) if apply_fixes else want
        total += 1
        got, why = mechs.get(pick_id, (None, "missing"))
        if why not in ("ok", "no_mark"):
            reasons[why] += 1
            continue
        read += 1
        name = byid[pick_id]["name"]
        for m in S.MECHANICS:
            in_want, in_got = (m in want), (got == m)
            if in_want:
                pos[m] += 1
                if in_got:
                    hit[m] += 1
                else:
                    fn[m].append(f"{pick_id} {name}: 正解「{m}」/ 読み取り「{got or '仕組みなし'}」")
            elif in_got:
                fp[m].append(f"{pick_id} {name}: 読み取り「{m}」/ 正解「{'・'.join(sorted(want)) or '仕組みなし'}」")

    print(f"\n正解データ{total}件 / 仕組みを判定できた{read}件（カバー率 {read / total * 100:.1f}%）")
    if reasons:
        print(f"  判定できなかった理由: {dict(reasons)}")
    print(f"\n{'仕組み':10} {'正解':>5} {'一致':>5} {'一致率':>8} {'誤検出':>6}")
    for m in S.MECHANICS:
        rate = hit[m] / pos[m] * 100 if pos[m] else float("nan")
        flag = "OK" if pos[m] and rate >= 99.5 and not fp[m] else "NG"
        print(f"  {m:10} {pos[m]:5} {hit[m]:5} {rate:7.2f}% {len(fp[m]):6}  [{flag}]")
    for m in S.MECHANICS:
        for x in fn[m]:
            print(f"    取りこぼし {x}")
        for x in fp[m]:
            print(f"    誤検出     {x}")


def validate_legend(picks: list[dict], data: dict, matcher_for) -> None:
    """でんせつ／まぼろしには正解データが無いので、同じポケモンどうしで割れないかを見る。

    同じポケモンのピックは何枚あってもでんせつ／まぼろしの別は同じはずなので、
    枚数の多いポケモンほど強い裏づけになる。
    """
    got: dict[str, str | None] = {}
    reasons: Counter = Counter()
    for p in picks:
        rec = data.get(p["id"])
        if rec is None:
            reasons["extract_failed"] += 1
            continue
        v, why = matcher_for(p["id"]).read_legend(rec)
        if why not in ("ok", "none"):
            reasons[why] += 1
            continue
        got[p["id"]] = v

    byname: dict[str, Counter] = defaultdict(Counter)
    ids = {p["id"]: p["name"] for p in picks}
    for pick_id, v in got.items():
        byname[ids[pick_id]][v or "なし"] += 1
    split = {n: dict(c) for n, c in byname.items() if len(c) > 1}

    counts = Counter(v or "なし" for v in got.values())
    print(f"\nでんせつ帯: 判定できた {len(got)}/{len(picks)}件  内わけ {dict(counts)}")
    if reasons:
        print(f"  判定できなかった理由: {dict(reasons)}")
    print(f"  同じポケモンで判定が割れたもの: {len(split)}件 {split}")
    named = sorted({ids[i] for i, v in got.items() if v == "でんせつ"})
    myth = sorted({ids[i] for i, v in got.items() if v == "まぼろし"})
    print(f"  でんせつ {len(named)}種: {named}")
    print(f"  まぼろし {len(myth)}種: {myth}")


def validate_names(picks: list[dict], names: dict[str, tuple[str | None, str]]) -> None:
    byid = {p["id"]: p for p in picks}
    ok = sum(1 for v in names.values() if v[1] == "ok")
    tag = sum(1 for v in names.values() if v[1] == "tag_no_en")
    reasons = Counter(v[1] for v in names.values() if v[0] is None)
    print(f"\n2行目のわざ名: 英語名との突き合わせが取れた {ok}件"
          f" / タッグわざの行（英語名が無いので全一致だけを根拠）{tag}件")
    print(f"  読めなかった理由: {dict(reasons)}")
    got = [(i, byid[i]["name"], v[0]) for i, v in sorted(names.items()) if v[0]]
    print(f"  例: {[(i, n, m) for i, n, m in got[:8]]}")


# --- 全件 -------------------------------------------------------------------
def run_all(picks: list[dict], data: dict, matcher: S.SpecialMatcher,
            mechs: dict[str, tuple[str | None, str]],
            names: dict[str, tuple[str | None, str]],
            reads: dict[str, "M.Read"], errors: dict[str, int]) -> None:
    records = []
    m_counts: Counter = Counter()
    m_reasons: Counter = Counter()
    n_filled = 0
    legend_counts: Counter = Counter()

    for p in picks:
        rec = data.get(p["id"])
        mech, m_why = mechs.get(p["id"], (None, "extract_failed"))
        name, n_why = names.get(p["id"], (None, "ocr_missing"))
        read = reads.get(p["id"])
        legend, l_why = (None, "extract_failed")
        if rec is not None:
            legend, l_why = matcher.read_legend(rec)

        m_counts[mech or "仕組みなし"] += 1
        if m_why not in ("ok", "no_mark"):
            m_reasons[m_why] += 1
        if name:
            n_filled += 1
        legend_counts[legend or ("なし" if l_why == "none" else "よめず")] += 1

        records.append({
            "id": p["id"],
            # テラスタル / Zワザ / メガシンカ / タッグわざ / ダイマックス、無ければ null
            "mechanic": mech,
            "mechanicReason": m_why,
            # わざ欄2行目のわざ名。タッグわざの行は英語名が無いので
            # secondMoveReason が "tag_no_en"（相手の名前とわざ名の全一致だけが根拠）
            "secondMoveName": name,
            "secondMoveNameEn": read.en if (name and read and mech != S.TAG) else None,
            # タッグわざの行の上段に入る、いっしょにわざを出す相手ポケモンの名前
            "tagPartner": read.en if (name and read and mech == S.TAG) else None,
            "secondMoveReason": n_why,
            # でんせつ／まぼろし。どちらでもなければ null
            "legend": legend,
            "legendReason": l_why,
        })

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if errors:
        print(f"読み取れなかった画像: {errors}")
    print(f"\n書き出し先: {OUT_JSON.relative_to(ROOT)}")
    print(f"\n仕組み: {dict(m_counts)}")
    print(f"  判定できなかった理由: {dict(m_reasons)}")
    print(f"2行目のわざ名: {n_filled}件を読み取れた")
    print(f"でんせつ帯: {dict(legend_counts)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", action="store_true", help="しきい値を決めるための一致度の分布を出す")
    ap.add_argument("--validate", action="store_true", help="ファンサイトの表に対するカバー率・一致率を測る")
    ap.add_argument("--folds", action="store_true", help=f"--validate を{FOLDS}分割交差検証で行う")
    ap.add_argument("--run-all", action="store_true", help="全958件を読み取り scripts/raw/ocr_special.json に書き出す")
    args = ap.parse_args()
    if not (args.scores or args.validate or args.run_all):
        ap.print_help()
        sys.exit(1)

    picks = json.loads(PICKS_PATH.read_text(encoding="utf-8"))
    templates = load_templates()
    aligner = S.Aligner(templates["generic_mark"], templates["generic_slot"], templates["generic_legend"])
    base = S.SpecialMatcher(templates)

    print(f"読み取り対象: {len(picks)}件", file=sys.stderr)
    data, errors = extract_all(picks, aligner)
    row0, row1, text_errors = read_text(picks)
    for k, v in Counter(text_errors.values()).items():
        errors[k] = errors.get(k, 0) + v

    folds = None
    if args.folds:
        if "folds" not in templates:
            raise SystemExit("交差検証用テンプレートが無い。build_special_templates.py --folds 5 を実行すること")
        folds = [{"held_out": set(f["held_out"]), "matcher": S.SpecialMatcher(f)} for f in templates["folds"]]

    def matcher_for(pick_id: str) -> S.SpecialMatcher:
        """交差検証のとき、そのピックを含まないテンプレートを返す。"""
        for f in folds or []:
            if pick_id in f["held_out"]:
                return f["matcher"]
        return base

    truth = S.load_truth()
    # 書き出しは必ず全件ぶんのテンプレートで行う。交差検証用のテンプレートは
    # --validate のときだけ使い、--run-all の結果には混ぜない。
    mechs = resolve_mechanics(picks, data, row0, lambda _: base)
    names, reads = resolve_second_names(picks, row0, row1, mechs)

    if args.scores:
        show_scores(picks, data, base, truth, row0)
    if args.validate:
        head = f"{FOLDS}分割交差検証（自分自身をテンプレートに含めない）" if folds else "自己一致もふくむ単純検証"
        v_mechs = resolve_mechanics(picks, data, row0, matcher_for) if folds else mechs
        for apply_fixes in (False, True):
            validate(picks, truth, v_mechs, apply_fixes, head)
        validate_legend(picks, data, matcher_for)
        validate_names(picks, names)
    if args.run_all:
        run_all(picks, data, base, mechs, names, reads, errors)


if __name__ == "__main__":
    main()
