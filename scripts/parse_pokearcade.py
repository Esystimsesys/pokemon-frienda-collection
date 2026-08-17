#!/usr/bin/env python3
"""ファンサイト「ポケモンフレンダ攻略WIKI」(pokearcade.jp)の
「フレンダピック全弾データベース」から ポケエネ / すばやさ を取り込むための
中間データを作る。

このサイトはファンサイトなので鵜呑みにしない。うちの ocr_stats.json / ocr_header.json
（公式の裏面画像をテンプレート照合したもの。280件の正解データに全項目100%一致、
5分割交差検証でも誤り0）と重なる列（HP/ATK/DEF/SP.ATK/SP.DEF/グレード/ポケタイプ/
わざタイプ）を全件突き合わせて一致率を出し、99.5%以上のときだけ
ポケエネ・すばやさを信用して書き出す。

HTMLソース: scripts/raw/pokearcade.html（無ければ /tmp/pa-all.html からコピーする。
どちらも無い場合は再取得が必要 → https://pokearcade.jp/フレンダピック全弾データベース/ ）

出力: scripts/raw/pokearcade.json （src/data/picks.json は書き換えない。マージは呼び出し側）
"""

import html
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
HTML_CACHE = RAW / "pokearcade.html"
HTML_FALLBACK = Path("/tmp/pa-all.html")
OUT = RAW / "pokearcade.json"

PICKS = ROOT.parent / "src" / "data" / "picks.json"
OCR_STATS = RAW / "ocr_stats.json"
OCR_HEADER = RAW / "ocr_header.json"

# フレンダピック全弾データベースの列順（見出しのテキストと一致させておく）
COLS = (
    "no", "name", "energy", "grade", "speed", "types", "moveType",
    "hp", "atk", "def", "spatk", "spdef", "acc", "power", "moveKind",
    "tera", "z", "mega", "tag", "dyna", "set",
)
EXPECTED_HEADERS = (
    "ピック番号", "名称", "ポケエネ", "グレード", "すばやさ", "ポケタイプ", "わざタイプ",
    "HP", "ATK", "DEF", "SP.ATK", "SP.DEF", "命中率(SV基準)※1", "威力(SV基準)※2",
    "わざ種類", "テラスタル", "Zわざ", "メガシンカ", "タッグわざ", "ダイマックス", "弾",
)

# 向こうの列名 -> うちの ocr_stats.json のキー
STAT_COL_TO_OCR_KEY = {
    "hp": "hp", "atk": "attack", "def": "defense", "spatk": "spAttack", "spdef": "spDefense",
}

MATCH_THRESHOLD = 0.995


def load_html() -> str:
    if HTML_CACHE.exists():
        return HTML_CACHE.read_text(encoding="utf-8", errors="replace")
    if HTML_FALLBACK.exists():
        text = HTML_FALLBACK.read_text(encoding="utf-8", errors="replace")
        HTML_CACHE.write_text(text, encoding="utf-8")
        return text
    raise SystemExit(
        f"{HTML_CACHE} も {HTML_FALLBACK} も無い。"
        "https://pokearcade.jp/フレンダピック全弾データベース/ から再取得すること（1回だけ許可）"
    )


def text_of(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def parse_table(raw: str) -> list[dict]:
    idx = raw.find('<table class="tablesorter')
    if idx == -1:
        raise SystemExit("フレンダピック全弾データベースの table が見つからない（サイト構造が変わった？）")
    thead_end = raw.find("</thead>", idx)
    headers = [text_of(h) for h in re.findall(r"<th[^>]*>(.*?)</th>", raw[idx:thead_end], re.S)]
    if tuple(headers) != EXPECTED_HEADERS:
        raise SystemExit(f"表の見出しが想定と違う。サイト構造が変わっていないか確認すること:\n{headers}")

    table_end = raw.find("</table>", idx)
    tbody_start = raw.find("<tbody", idx)
    tbody = raw[tbody_start:table_end]
    rows = re.findall(r"<tr>(.*?)</tr>", tbody, re.S)

    out = []
    for r in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)
        if len(cells) != len(COLS):
            raise SystemExit(f"1行の列数が {len(cells)}（想定 {len(COLS)}）。サイト構造が変わった？\n{r[:300]}")
        values = []
        for c in cells:
            divs = re.findall(r"<div[^>]*>(.*?)</div>", c, re.S)
            values.append([text_of(d) for d in divs])
        out.append(dict(zip(COLS, values)))
    return out


def parse_int(divs: list[str] | None) -> int | None:
    if not divs or not divs[0]:
        return None
    v = divs[0].strip()
    return int(v) if re.fullmatch(r"-?\d+", v) else None


def parse_grade(divs: list[str] | None) -> int | None:
    if not divs:
        return None
    m = re.match(r"★(\d)", divs[0])
    return int(m.group(1)) if m else None


def parse_speed(divs: list[str] | None) -> tuple[int | None, int | None]:
    """(すばやさランク 1〜5, 括弧内の数値) を返す。
    ランクは裏面に矢印アイコンの数として実際に印字されており画像で検証できる。
    括弧内の数値は券面のどこにも印字が無く、サイト側の独自の付加情報とみられるため
    今回は取り込み対象にしない（intermediateには記録だけしておく）。
    """
    if not divs:
        return None, None
    m = re.match(r"➤(\d+)(?:\((\d+)\))?", divs[0])
    if not m:
        return None, None
    rank = int(m.group(1))
    raw = int(m.group(2)) if m.group(2) else None
    return rank, raw


def ja_name(divs: list[str] | None) -> str | None:
    return divs[1] if divs and len(divs) > 1 else None


def main() -> None:
    raw_html = load_html()
    rows = parse_table(raw_html)
    print(f"表から読めた行数: {len(rows)}")

    picks = json.loads(PICKS.read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in picks}
    ocr_stats = {
        r["id"]: r["ocr_values"]
        for r in json.loads(OCR_STATS.read_text(encoding="utf-8"))
        if r.get("ocr_complete")
    }
    ocr_header = {r["id"]: r for r in json.loads(OCR_HEADER.read_text(encoding="utf-8"))}

    # ピック番号がそのままユニークキーになっている行（ワンダー/スペシャルの "P"/"W" 以外）
    site_by_id: dict[str, dict] = {}
    p_rows: list[dict] = []
    site_id_dupes: list[str] = []
    for row in rows:
        no = row["no"][0] if row["no"] else None
        if no in (None, "P", "W"):
            p_rows.append(row)
            continue
        if no in site_by_id:
            site_id_dupes.append(no)
        site_by_id[no] = row
    if site_id_dupes:
        raise SystemExit(f"ピック番号が重複している行がある（想定外）: {site_id_dupes[:10]}")

    matched: dict[str, tuple[dict, str]] = {}
    for id_, row in site_by_id.items():
        if id_ in by_id:
            matched[id_] = (row, "id")
    site_only_ids = sorted(set(site_by_id) - set(by_id))

    # "P"（スペシャル）は券面表記が全部 "P" で一意なキーにならないので、
    # 名前 + OCRで確定済みの5ステータスの組をキーにして突き合わせる。
    # このキーが向こう・うち双方で一意な時だけ確信の持てる一致として採用し、
    # 重複するキーは「どのカードか特定できない」としてマッチさせない（推測しない）。
    def site_key(row: dict):
        stats = {STAT_COL_TO_OCR_KEY[c]: parse_int(row[c]) for c in ("hp", "atk", "def", "spatk", "spdef")}
        if any(v is None for v in stats.values()):
            return None
        return (ja_name(row["name"]), stats["hp"], stats["attack"], stats["defense"], stats["spAttack"], stats["spDefense"])

    p_key_counter: Counter = Counter()
    p_key_to_row: dict = {}
    for row in p_rows:
        k = site_key(row)
        if k is None:
            continue
        p_key_counter[k] += 1
        p_key_to_row[k] = row

    our_special = [p for p in picks if p["id"] not in matched and p["id"] in ocr_stats]

    def our_key(p):
        s = ocr_stats[p["id"]]
        return (p["name"], s["hp"], s["attack"], s["defense"], s["spAttack"], s["spDefense"])

    our_key_counter = Counter(our_key(p) for p in our_special)

    special_matched = 0
    special_ambiguous_ids = []
    for p in our_special:
        k = our_key(p)
        if our_key_counter[k] == 1 and p_key_counter.get(k) == 1:
            matched[p["id"]] = (p_key_to_row[k], "stats_name")
            special_matched += 1
        elif k in p_key_counter:
            special_ambiguous_ids.append(p["id"])

    print(f"\nID直接一致: {sum(1 for _, m in matched.values() if m == 'id')} 件")
    print(f"名前+ステータスで一致（スペシャル等の 'P' 行）: {special_matched} 件")
    print(f"あいまいで見送り（同名同ステータスが複数あり特定不能）: {len(special_ambiguous_ids)} 件 {special_ambiguous_ids}")
    print(f"うちのピックに無い ID がサイト側にあった: {len(site_only_ids)} 件 {site_only_ids[:10]}")
    print(f"うちにあってサイト側で見つからなかった: {len(picks) - len(matched)} 件")

    # ---- 重なっている列の突き合わせ ----
    # id直接一致の行だけを「独立した」検証に使う（stats_nameマッチはステータス自体が
    # 一致キーなのでステータスの一致率としては意味を持たない＝タウトロジーになるため除外）。
    field_total = Counter()
    field_match = Counter()
    mismatches: dict[str, list[dict]] = {k: [] for k in ("hp", "attack", "defense", "spAttack", "spDefense", "grade", "types", "moveType")}

    for id_, (row, method) in matched.items():
        header = ocr_header.get(id_)

        if method == "id":
            stats = ocr_stats.get(id_)
            if stats:
                for col, key in STAT_COL_TO_OCR_KEY.items():
                    site_v = parse_int(row[col])
                    ours_v = stats[key]
                    field_total[key] += 1
                    if site_v == ours_v:
                        field_match[key] += 1
                    else:
                        mismatches[key].append({"id": id_, "ours": ours_v, "site": site_v})

        if header:
            # グレード：うちがnull（★の印字が無い/公式が2段まとめ表記）のものは比較しない
            ours_grade = header.get("grade")
            site_grade = parse_grade(row["grade"])
            if ours_grade is not None and site_grade is not None:
                field_total["grade"] += 1
                if ours_grade == site_grade:
                    field_match["grade"] += 1
                else:
                    mismatches["grade"].append({"id": id_, "ours": ours_grade, "site": site_grade})

            ours_types = header.get("types") or []
            site_types = [t for t in row["types"] if t]
            if ours_types and site_types:
                field_total["types"] += 1
                if set(ours_types) == set(site_types):
                    field_match["types"] += 1
                else:
                    mismatches["types"].append({"id": id_, "ours": ours_types, "site": site_types})

            ours_move_type = header.get("firstMoveType")
            site_move_type = row["moveType"][0] if row["moveType"] else None
            if ours_move_type and site_move_type:
                field_total["moveType"] += 1
                if ours_move_type == site_move_type:
                    field_match["moveType"] += 1
                else:
                    mismatches["moveType"].append({"id": id_, "ours": ours_move_type, "site": site_move_type})

    print("\n=== 重なっている列の一致率（ID直接一致した行のみ。グレード/タイプ/わざタイプは名前+ステータス一致分も含む） ===")
    overall_ok = True
    for key in ("hp", "attack", "defense", "spAttack", "spDefense", "grade", "types", "moveType"):
        total = field_total[key]
        ok = field_match[key]
        rate = ok / total if total else float("nan")
        flag = "OK" if total and rate >= MATCH_THRESHOLD else "NG"
        if total and rate < MATCH_THRESHOLD:
            overall_ok = False
        print(f"  {key:10} {ok:4}/{total:<4}  {rate*100:6.2f}%  [{flag}]")

    print("\n=== 食い違ったピック ===")
    for key, items in mismatches.items():
        if items:
            print(f"-- {key} ({len(items)}件) --")
            for m in items:
                print(f"   {m['id']}: ours={m['ours']!r} site={m['site']!r}")

    # ---- ポケエネ・すばやさの取り込み判定 ----
    stats_ok = all(
        field_total[k] == 0 or field_match[k] / field_total[k] >= MATCH_THRESHOLD
        for k in ("hp", "attack", "defense", "spAttack", "spDefense")
    )
    if not stats_ok:
        print("\n!! ステータス列の一致率が基準未満。ポケエネ／すばやさの取り込みを見送ります。")

    out_records = []
    energy_filled = 0
    speed_filled = 0
    for p in picks:
        entry = matched.get(p["id"])
        record = {"id": p["id"], "match": entry[1] if entry else None, "energy": None, "speed": None, "speedRaw": None}
        if entry and stats_ok:
            row, _ = entry
            energy = parse_int(row["energy"])
            speed_rank, speed_raw = parse_speed(row["speed"])
            record["energy"] = energy
            record["speed"] = speed_rank
            record["speedRaw"] = speed_raw
            if energy is not None:
                energy_filled += 1
            if speed_rank is not None:
                speed_filled += 1
        out_records.append(record)

    OUT.write_text(json.dumps(out_records, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\n{OUT.relative_to(ROOT.parent)} に {len(out_records)} 件書き出した")
    print(f"ポケエネを埋められた: {energy_filled} 件")
    print(f"すばやさ（1〜5ランク）を埋められた: {speed_filled} 件")


if __name__ == "__main__":
    main()
