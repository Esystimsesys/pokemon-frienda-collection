#!/usr/bin/env python3
"""公式ピック画像の裏面をOCRして、picks.json の stats 欠損を埋めるための下ごしらえをする。

進め方:
  1. --validate  : すでに stats が入っている280件に対してOCRを走らせ、一致率を測る。
  2. --run-all   : 全958件に対してOCRを走らせ、結果を scripts/raw/ocr_stats.json に
                    書き出す（中間ファイル。picks.json には一切書き込まない）。

読み取り方式は --method で選ぶ。
  template : テンプレート照合（scripts/ocr/template_ocr.py）。既定。
  vision   : Apple Vision（scripts/ocr/ocr_stats.swift）。
  combo    : テンプレートを主にし、読めなかったところだけ Vision で補う。
  agree    : 両方が読めて、かつ値が一致したときだけ確定する。
--compare を付けると4方式を同じ280件で並べて比較する。

いずれの方式も推測はしない。テンプレート照合は一致度（NCC）が閾値に届かなければ
読めなかった扱いにし、Vision 側は英字が1文字でも混じったら数値化を諦める。

energy（ポケエネ）は裏面に印字されていないため、OCRからは取得しない。
そのため確定できるのは hp/attack/defense/spAttack/spDefense の5項目だけ。
energy が無いと Stats 型（全フィールド必須）を満たせないため、picks.json への
反映方法は別途相談する（このスクリプトは書き込みを行わない）。
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import template_ocr  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
PICKS_PATH = ROOT / "src" / "data" / "picks.json"
IMAGES_DIR = ROOT / "scripts" / "raw" / "pick_images"
OCR_SRC = ROOT / "scripts" / "ocr" / "ocr_stats.swift"
OCR_BIN = ROOT / "scripts" / "ocr" / "build" / "ocr_stats"
OUT_JSON = ROOT / "scripts" / "raw" / "ocr_stats.json"

FIELDS = ["hp", "atk", "def", "spatk", "spdef"]
STAT_KEY = {"hp": "hp", "atk": "attack", "def": "defense", "spatk": "spAttack", "spdef": "spDefense"}

# 妥当性チェック用のレンジ（既存280件の実測レンジに余裕を持たせた値）
RANGE_MIN, RANGE_MAX = 1, 400

# テンプレート照合の採否ライン。既存280件・全958件の実測で、正しく読めたグリフの
# 最低スコアは0.860 / 最低マージンは0.033だったので、そこから余裕を取った値。
TEMPLATE_MIN_SCORE = 0.80
TEMPLATE_MIN_MARGIN = 0.02

"""
picks.json の元データ（旧ファンサイト）が公式の裏面と食い違っていたぶん。
テンプレート照合の結果と突き合わせて見つかり、公式画像を目視で確認した。
検証時の「補正後の正解率」を出すためだけに使い、picks.json は書き換えない。
反映するかどうかは parse_official.py の STAT_FIXES 側で判断すること。
"""
VERIFIED_GT_FIXES: dict[str, dict[str, int]] = {
    "1-2-022": {"spAttack": 46},   # 48 → 46
    "1-2-043": {"defense": 89},    # 88 → 89
    "1-2-057": {"defense": 35},    # 36 → 35
    "1-2-058": {"defense": 49},    # 48 → 49
    "1-3-038": {"spDefense": 39},  # 38 → 39
    "1-4-009": {"spAttack": 96, "spDefense": 91},  # 67 → 96 / 94 → 91
}


def clean_token(raw: str | None) -> int | None:
    """OCR生文字列 -> 整数。空白・記号を除いた残りが純粋な数字列のときだけ数値化する。

    "130 (" -> "130" (OK) / "1DB" -> "1DB" (英字が残るのでNG=None) のように、
    英字が1文字でも混じっていたら None を返す。8→B, 0→D のような誤読は
    フォント由来で1文字が6にも8にもなり得る等、決定的に直せないため。
    """
    if raw is None:
        return None
    # 空白と、末尾に付くことがあるOCRノイズ記号だけを取り除く。
    # それ以外の文字（英字・キリル文字など）が1文字でも残っていたら
    # 数字への変換を諦める（"Б7"を"7"のように部分的に解釈しない）。
    token = raw.strip()
    token = re.sub(r"[\s().,]", "", token)
    if not token:
        return None
    if not re.fullmatch(r"[0-9]+", token):
        return None
    value = int(token)
    if not (RANGE_MIN <= value <= RANGE_MAX):
        return None
    return value


def resolve_field(r: dict, field: str) -> int | None:
    """ネイティブ/2倍/4倍、3通りの独立したOCR結果のうち多数決(2/3以上)で
    一致した数字だけを確定値として採用する（単純な文字置換での補正はしない）。"""
    values = [clean_token(r.get(f"{field}_p{i}")) for i in range(3)]
    values = [v for v in values if v is not None]
    if not values:
        return None
    counts: dict[int, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    best_value, best_count = max(counts.items(), key=lambda kv: kv[1])
    if best_count >= 2:
        return best_value
    return None


def ensure_ocr_binary() -> None:
    """ソースがバイナリより新しければ再ビルドする（再実行可能にするため自動化）。"""
    if OCR_BIN.exists() and OCR_BIN.stat().st_mtime >= OCR_SRC.stat().st_mtime:
        return
    OCR_BIN.parent.mkdir(parents=True, exist_ok=True)
    print("OCRツールをビルド中 (swiftc)...", file=sys.stderr)
    subprocess.run(
        ["swiftc", "-O", str(OCR_SRC), "-o", str(OCR_BIN)],
        check=True,
    )


def run_ocr(paths: list[Path]) -> dict[str, dict]:
    ensure_ocr_binary()
    proc = subprocess.run(
        [str(OCR_BIN)],
        input="\n".join(str(p) for p in paths),
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
        out[obj["file"]] = obj
    return out


def run_template(paths: list[Path]) -> dict[str, dict]:
    """テンプレート照合で読み取る。返り値は run_ocr と同じく画像パス→結果の辞書。"""
    matcher = template_ocr.TemplateMatcher.load()
    out: dict[str, dict] = {}
    for path in paths:
        glyphs, err = template_ocr.extract_all(path)
        rec: dict = {"file": str(path)}
        if err:
            rec["error"] = err
        for f in FIELDS:
            g = glyphs.get(f)
            if g is None:
                rec[f] = None
                rec[f"{f}_reason"] = err or "no_glyph"
                continue
            value, reason = matcher.read_number(g, TEMPLATE_MIN_SCORE, TEMPLATE_MIN_MARGIN)
            rec[f] = value
            rec[f"{f}_reason"] = reason
        out[str(path)] = rec
    return out


def resolve_template(r: dict, field: str) -> int | None:
    v = r.get(field)
    if v is None or not (RANGE_MIN <= v <= RANGE_MAX):
        return None
    return v


def resolve(method: str, tpl: dict, vis: dict, field: str) -> int | None:
    """方式ごとの確定値。読めなければ None（推測はしない）。"""
    if method == "template":
        return resolve_template(tpl, field)
    if method == "vision":
        return resolve_field(vis, field)
    t = resolve_template(tpl, field)
    v = resolve_field(vis, field)
    if method == "combo":
        return t if t is not None else v
    if method == "agree":
        return t if (t is not None and t == v) else None
    raise ValueError(method)


def image_path(pick_id: str) -> Path:
    return IMAGES_DIR / f"{pick_id}.webp"


def expected_stats(pick: dict, apply_fixes: bool) -> dict:
    stats = dict(pick["stats"])
    if apply_fixes:
        stats.update(VERIFIED_GT_FIXES.get(pick["id"], {}))
    return stats


def _score_method(
    pairs: list[tuple[dict, Path]],
    tpl_result: dict,
    vis_result: dict,
    method: str,
    apply_fixes: bool,
) -> dict:
    """1方式ぶんの項目別カバー率・正解率と不一致リストを集計する。"""
    total = {f: 0 for f in FIELDS}
    read = {f: 0 for f in FIELDS}
    match = {f: 0 for f in FIELDS}
    mismatches: list[str] = []
    all5_read = 0
    all5_match = 0

    for pick, path in pairs:
        tpl = tpl_result.get(str(path), {})
        vis = vis_result.get(str(path), {})
        expected = expected_stats(pick, apply_fixes)
        n_read = n_ok = 0
        for f in FIELDS:
            total[f] += 1
            got = resolve(method, tpl, vis, f)
            if got is None:
                continue
            read[f] += 1
            n_read += 1
            if got == expected[STAT_KEY[f]]:
                match[f] += 1
                n_ok += 1
            else:
                mismatches.append(f"{pick['id']} {f}: 読み取り{got} != 正解{expected[STAT_KEY[f]]}")
        if n_read == 5:
            all5_read += 1
            if n_ok == 5:
                all5_match += 1
    return {
        "total": total, "read": read, "match": match,
        "mismatches": mismatches, "all5_read": all5_read, "all5_match": all5_match,
    }


def _print_method(name: str, s: dict, n_pairs: int) -> None:
    print(f"\n=== {name} ===")
    for f in FIELDS:
        t, r, m = s["total"][f], s["read"][f], s["match"][f]
        print(
            f"  {f:6s}: 全{t}件 / 読取できた{r}件(カバー率 {r / t * 100:5.1f}%) / "
            f"読めた中での正解{m}件({(m / r * 100) if r else 0:6.2f}%) / 読めず{t - r}件"
        )
    print(f"  5項目すべて読み取れた: {s['all5_read']}/{n_pairs}件 / うち全部正解 {s['all5_match']}件")
    if s["mismatches"]:
        print(f"  不一致 {len(s['mismatches'])}件:")
        for ex in s["mismatches"][:20]:
            print(f"    {ex}")


def validate(picks: list[dict], method: str, compare: bool) -> None:
    known = [p for p in picks if p["stats"] is not None]
    paths = [image_path(p["id"]) for p in known]
    missing = [p for p, path in zip(known, paths) if not path.exists()]
    if missing:
        print(f"画像が無いのでスキップ: {len(missing)}件（先に ocr:fetch-images を実行すること）")
    pairs = [(p, path) for p, path in zip(known, paths) if path.exists()]
    only = [path for _, path in pairs]

    print(f"検証対象（既存stats あり）: {len(pairs)}件")
    methods = ["template", "vision", "combo", "agree"] if compare else [method]
    need_vision = any(m != "template" for m in methods)
    tpl_result = run_template(only) if any(m != "vision" for m in methods) else {}
    vis_result = run_ocr(only) if need_vision else {}

    for apply_fixes in (False, True):
        head = "picks.json の値をそのまま正解とした場合" if not apply_fixes else (
            f"picks.json 側の誤り{sum(len(v) for v in VERIFIED_GT_FIXES.values())}項目"
            "（公式画像を目視確認済み）を補正した場合"
        )
        print(f"\n############ {head} ############")
        for m in methods:
            _print_method(m, _score_method(pairs, tpl_result, vis_result, m, apply_fixes), len(pairs))


def run_all(picks: list[dict], method: str) -> None:
    """全958件を読み取り、結果を scripts/raw/ocr_stats.json に書き出す。

    picks.json には一切書き込まない（反映は別途、方針が決まってから行う）。
    """
    paths = [image_path(p["id"]) for p in picks]
    existing = [(p, path) for p, path in zip(picks, paths) if path.exists()]
    missing_imgs = len(picks) - len(existing)
    if missing_imgs:
        print(f"画像が無いのでスキップ: {missing_imgs}件（先に npm run ocr:fetch-images を実行すること）")

    print(f"読み取り対象: {len(existing)}/{len(picks)}件（方式: {method}）")
    only = [path for _, path in existing]
    tpl_result = run_template(only) if method != "vision" else {}
    vis_result = run_ocr(only) if method != "template" else {}

    out_records = []
    per_field_missing = {f: 0 for f in FIELDS}
    reasons: dict[str, int] = {}
    already_has_stats = 0
    null_before = 0
    fillable_null = 0
    complete_count = 0

    for pick, path in existing:
        tpl = tpl_result.get(str(path), {})
        vis = vis_result.get(str(path), {})
        had_stats = pick["stats"] is not None
        if had_stats:
            already_has_stats += 1
        else:
            null_before += 1

        values: dict[str, int] = {}
        for f in FIELDS:
            v = resolve(method, tpl, vis, f)
            if v is None:
                per_field_missing[f] += 1
                reason = tpl.get(f"{f}_reason") or tpl.get("error") or "vision_only"
                reasons[reason] = reasons.get(reason, 0) + 1
            else:
                values[STAT_KEY[f]] = v

        complete = len(values) == 5
        if complete:
            complete_count += 1
            if not had_stats:
                fillable_null += 1

        out_records.append(
            {
                "id": pick["id"],
                "had_existing_stats": had_stats,
                "ocr_complete": complete,
                "ocr_values": values,  # hp/attack/defense/spAttack/spDefense のうち読み取れた分だけ
                # 参考情報。template系なら判定理由("ok"/"anchor_not_found"など)、
                # vision ならネイティブ解像度パスの生文字列が入る。
                "raw": {
                    f: (tpl.get(f"{f}_reason") if method != "vision" else vis.get(f"{f}_p0"))
                    for f in FIELDS
                },
            }
        )

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(out_records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"\n書き出し先: {OUT_JSON.relative_to(ROOT)}")
    print(f"既存stats あり: {already_has_stats}件 / stats null: {null_before}件")
    print(f"\n5項目そろった: {complete_count}/{len(existing)}件")
    print(f"  うち stats が null だったもの: {fillable_null}/{null_before}件")
    print(f"（energyが無いため、この{fillable_null}件はまだ picks.json に書き込める形になっていない）")
    print("\n項目ごとに読み取れなかった件数:")
    for f in FIELDS:
        print(f"  {f:6s}: {per_field_missing[f]}件")
    print("読めなかった理由の内訳:", reasons)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true", help="既存280件で一致率を検証する")
    ap.add_argument("--run-all", action="store_true", help="全958件を読み取り scripts/raw/ocr_stats.json に書き出す")
    ap.add_argument(
        "--method",
        choices=["template", "vision", "combo", "agree"],
        default="template",
        help="読み取り方式（既定: template）",
    )
    ap.add_argument("--compare", action="store_true", help="--validate で4方式を並べて比較する")
    args = ap.parse_args()

    if not args.validate and not args.run_all:
        ap.print_help()
        sys.exit(1)

    picks = json.loads(PICKS_PATH.read_text(encoding="utf-8"))

    if args.validate:
        validate(picks, args.method, args.compare)
    if args.run_all:
        run_all(picks, args.method)


if __name__ == "__main__":
    main()
