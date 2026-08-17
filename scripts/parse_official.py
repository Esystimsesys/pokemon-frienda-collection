#!/usr/bin/env python3
"""公式サイト（pokemonfrienda.com）の保存済みHTMLから全ピックのマスタを作る。

どの項目をどこから取るかは、確からしさの順に決めている。

1. 番号・名前・だん・画像 … 公式の一覧ページ（raw/official/*.html）
2. HP/こうげき/ぼうぎょ/とくこう/とくぼう、タイプ、★、わざのタイプ
   … 公式の裏面画像をテンプレート照合で読んだもの（scripts/ocr）。
     正解データに対していずれも100%、5分割交差検証でも誤り0。**これを最優先の正とする。**
3. すばやさ … 裏面の矢印ゲージ（★と同じ仕組み）を読む。正解データに対して100%。
4. ポケエネ … 券面の表面から読めるが85%どまりで、読み違えた2件はファンサイトの
   ほうが正しかった。そのためファンサイト（parse_pokearcade.py。重なる列を全件突き合わせて
   99.9%一致を確認ずみ）を先に使い、向こうに無いぶんだけ券面の読み取りで補う。
   ファンサイトが取れなくても、券面だけで85%は埋まる。
5. わざの名前 … 裏面を Apple Vision（ja-JP）で読む（scripts/ocr/move_ocr.py）。
   日本語名を7通りの拡大で読んで全一致し、かつ併記の英語名とも突き合わせが取れたものだけ採る。
   読めなかったぶんだけ旧データに頼り、裏面のタイプと食い違う行は落としている。

最後に、機械で読み切れなかったぶんを人が券面を見て入れた raw/manual.json を当てる
（scripts/manual_fill.py。npm run manual）。これがいちばん優先される。

2〜5の照合で、旧データには実際に16件の誤りが見つかっている（ステータス8・タイプ3・わざ5）。
新しい情報源を足すときは、必ず2と突き合わせて検証してから使うこと。
"""

import html
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw" / "official"
OUT = ROOT.parent / "src" / "data" / "picks.json"
LEGACY = ROOT / "raw" / "legacy_picks.json"
OCR = ROOT / "raw" / "ocr_stats.json"
OCR_HEADER = ROOT / "raw" / "ocr_header.json"
# ポケエネとすばやさだけは公式にも裏面にも数値が無いので、
# ファンサイト由来（parse_pokearcade.py が検証ずみ）のものを借りる
ARCADE = ROOT / "raw" / "pokearcade.json"
OCR_MOVES = ROOT / "raw" / "ocr_moves.json"
OCR_EXTRA = ROOT / "raw" / "ocr_extra.json"
# 機械で読み切れなかったぶんを、人が券面を見て入れたもの（scripts/manual_fill.py）
MANUAL = ROOT / "raw" / "manual.json"
# 裏面2行目から読んだ とくべつな 仕組み（テラスタル等）と、でんせつ／まぼろし
OCR_SPECIAL = ROOT / "raw" / "ocr_special.json"

OCR_FIELDS = ("hp", "attack", "defense", "spAttack", "spDefense")

BASE = "https://pokemonfrienda.com/new/"

"""
だんは fetch_official.py が公式のナビから見つけて sets.json に書いている。
表示名はページの <title> から取る（例:「【ベストタッグ5だん】さいしんだんじょうほう…」→「ベストタッグ5だん」）。
だん以外のページは【】が付かないので、ここで呼び名を決める。
"""
SETS = ROOT / "raw" / "official" / "sets.json"
LABEL_OVERRIDES = {"wonder": "ワンダーピック", "special": "スペシャルピック"}
TITLE_DAN = re.compile(r"【(.+?)】")

# #friendapick セクション内に出る見出しだけがレア度を表す。
# それ以外（キャンペーン告知など）の見出しは直前のグループを引き継がせない。
GROUPS = {
    "スーパートレジャーポケモン": ("super", 5),
    "トレジャーポケモン": ("treasure", 4),
    "★2・★3ポケモン": ("basic", None),
    "パラレルアートピック": ("parallel", None),
    "いろちがいのポケモン": ("shiny", None),
}

SECTION = re.compile(r'<section class="contents" id="(?:special)?friendapick">(.*?)</section>', re.S)
CHUNK = re.compile(
    r'<h3[^>]*>(?P<h3>.*?)</h3>'
    r'|<li class="grid__item[^"]*">\s*'
    r'<a[^>]*data-modal="friendapick"[^>]*data-img="(?P<img>[^"]+)"[^>]*>'
    r'\s*<img[^>]*alt="(?P<alt>[^"]*)"[^>]*>\s*</a>'
    r'\s*<div class="txt[^"]*">\s*<p>(?P<no>[^<]*)</p>\s*<p>(?P<name>[^<]*)</p>',
    re.S,
)


def text(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def set_label(key: str, raw: str) -> str:
    """ページの <title> から だんの呼び名を取る"""
    if key in LABEL_OVERRIDES:
        return LABEL_OVERRIDES[key]
    title = re.search(r"<title>(.*?)</title>", raw, re.S)
    if title:
        m = TITLE_DAN.search(text(title.group(1)))
        if m:
            return m.group(1)
    # 新しい種類のページが増えたときに気づけるよう、黙って通さない
    raise SystemExit(f"{key}: 表示名が取れない。LABEL_OVERRIDES に足すこと")


def parse_page(key: str, subdir: str, order: int) -> list[dict]:
    raw = (RAW / f"{key}.html").read_text(encoding="utf-8", errors="replace")
    label = set_label(key, raw)
    section = SECTION.search(raw)
    if not section:
        raise SystemExit(f"{key}: #friendapick セクションが見つからない")

    # ワンダー／スペシャルは見出しがなくページ全体が1グループ。
    group, grade = (key, None) if key in ("wonder", "special") else (None, None)

    out = []
    for m in CHUNK.finditer(section.group(1)):
        if m.group("h3") is not None:
            group, grade = GROUPS.get(text(m.group("h3")), (group, grade))
            continue
        img = m.group("img")
        # 「img/xt1/3-1-026A_kira.webp」→「3-1-026A」。番号欄はワンダー/スペシャルだと
        # 「W」「P」しか入っていないので、一意なIDはファイル名から取る。
        pick_id = re.sub(r"_kira$", "", Path(img).stem)
        out.append({
            "id": pick_id,
            "no": text(m.group("no")) or pick_id,
            "set": key,
            "setLabel": label,
            "setOrder": order,
            "name": text(m.group("name")) or text(m.group("alt")),
            "group": group,
            "grade": grade,
            "image": BASE + subdir + img,
            "thumb": BASE + subdir + re.sub(r"\.webp$", "_thumb.webp", img),
        })
    return out


def main() -> None:
    if not SETS.exists():
        raise SystemExit(f"{SETS.name} が無い。先に `npm run fetch:data` を実行すること")

    picks: list[dict] = []
    for entry in json.loads(SETS.read_text(encoding="utf-8")):
        page = parse_page(entry["key"], entry["subdir"], entry["order"])
        picks.extend(page)
        print(f"{entry['key']:8} {len(page):4} 件")

    dupes = [i for i, n in Counter(p["id"] for p in picks).items() if n > 1]
    if dupes:
        raise SystemExit(f"IDが重複: {dupes[:20]}")

    if not OCR.exists():
        # 黙って旧データにフォールバックすると、間違ったステータスのまま出てしまう
        raise SystemExit(f"{OCR.name} が無い。先に `npm run ocr:run` を実行すること")
    if not OCR_HEADER.exists():
        raise SystemExit(f"{OCR_HEADER.name} が無い。先に `npm run ocr:run-header` を実行すること")

    legacy = {p["label"]: p for p in json.loads(LEGACY.read_text(encoding="utf-8"))}
    ocr = {
        r["id"]: r["ocr_values"]
        for r in json.loads(OCR.read_text(encoding="utf-8"))
        if r.get("ocr_complete")
    }
    header = {r["id"]: r for r in json.loads(OCR_HEADER.read_text(encoding="utf-8"))}
    arcade = {r["id"]: r for r in json.loads(ARCADE.read_text(encoding="utf-8"))} if ARCADE.exists() else {}
    ocr_moves = (
        {r["id"]: r for r in json.loads(OCR_MOVES.read_text(encoding="utf-8"))}
        if OCR_MOVES.exists()
        else {}
    )
    ocr_extra = (
        {r["id"]: r for r in json.loads(OCR_EXTRA.read_text(encoding="utf-8"))}
        if OCR_EXTRA.exists()
        else {}
    )
    manual = json.loads(MANUAL.read_text(encoding="utf-8")) if MANUAL.exists() else {}
    special = (
        {r["id"]: r for r in json.loads(OCR_SPECIAL.read_text(encoding="utf-8"))}
        if OCR_SPECIAL.exists()
        else {}
    )

    joined = 0
    changed = 0
    types_changed = 0
    dropped_moves = 0
    filled_moves = 0
    ocr_named = 0
    mega_moves = 0
    for p in picks:
        src = legacy.get(p["id"]) if legacy.get(p["id"], {}).get("released") else None
        # わざの名前は裏面から読み取れていないので、ここだけ旧データに頼る
        p["moves"] = src["moves"] if src else []

        head = header.get(p["id"], {})
        first = head.get("firstMoveType")
        read_name = ocr_moves.get(p["id"], {}).get("firstMoveName")

        if read_name:
            # 名前もタイプも裏面から読めたので、旧データは使わずこちらに置きかえる
            p["moves"] = [{"name": read_name, "type": first}]
            ocr_named += 1
        elif first and p["moves"]:
            # 名前が読めなかったぶんだけ旧データに頼る。タイプが未設定なら埋め、
            # 値が入っていて食い違うならその行は信用できない（別のわざが入っていた例がある）
            if p["moves"][0]["type"] is None:
                p["moves"] = [{**p["moves"][0], "type": first}]
                filled_moves += 1
            elif p["moves"][0]["type"] != first:
                p["moves"] = []
                dropped_moves += 1
            else:
                # 名前は読めなかったが、タイプは裏面と一致しているので旧データを残す
                filled_moves += 1
        # タイプは裏面のアイコンを正とする。旧データは複合タイプの2つめが抜けていることがある
        p["types"] = head.get("types") or (src["types"] if src else [])
        if src and head.get("types") and head["types"] != src["types"]:
            types_changed += 1
        if p["grade"] is None:
            p["grade"] = head.get("grade") if head.get("grade") is not None else (src["grade"] if src else None)

        # すばやさは 裏面の矢印ゲージから100%読めている（958件）ので、それを正とする。
        # ポケエネは 表面から読めるのが85%どまりで、しかも読み違えた2件は
        # ファンサイトのほうが正しかった。精度はファンサイトを上に置き、
        # 向こうに無いぶんだけ券面の読み取りで補う（合わせて946件）。
        read_extra = ocr_extra.get(p["id"], {})
        from_arcade = arcade.get(p["id"], {})
        energy = from_arcade.get("energy")
        if energy is None:
            energy = read_extra.get("energy")
        if energy is None and src:
            energy = src["energy"]
        speed = read_extra.get("speed")
        if speed is None:
            speed = from_arcade.get("speed")

        sp = special.get(p["id"], {})
        # メガシンカのピックは1行目が「メガ○○ にメガシンカ！」でわざではない。
        # じっさいのわざは2行目なので、そちらをわざとして使う（タイプは未読なので null）
        if not p["moves"] and sp.get("mechanic") == "メガシンカ" and sp.get("secondMoveName"):
            p["moves"] = [{"name": sp["secondMoveName"], "type": None}]
            mega_moves += 1
        p["mechanic"] = sp.get("mechanic")
        p["specialMove"] = sp.get("secondMoveName")
        p["tagPartner"] = sp.get("tagPartner")
        p["legend"] = sp.get("legend")

        read = ocr.get(p["id"])
        if read:
            joined += 1
            p["stats"] = {"energy": energy, **read, "speed": speed}
            if src and any(src[k] != read[k] for k in OCR_FIELDS):
                changed += 1
        elif src:
            # 裏面にステータス欄が無いピック（プロモの一部）。旧データがあればそれを使う
            joined += 1
            p["stats"] = {"energy": energy, **{k: src[k] for k in OCR_FIELDS}, "speed": speed}
        else:
            p["stats"] = None

    # 人が券面を見て入れたものが最優先。機械の読み取りより後に当てる
    hand = 0
    for p in picks:
        got = manual.get(p["id"])
        if not got:
            continue
        hand += 1
        if "moveName" in got or "moveType" in got:
            base = p["moves"][0] if p["moves"] else {"name": None, "type": None}
            name = got.get("moveName", base["name"])
            move_type = got.get("moveType", base["type"])
            p["moves"] = [{"name": name, "type": move_type}] if name else []
        if "specialMove" in got:
            p["specialMove"] = got["specialMove"]
            # メガシンカのピックは2行目が実際のわざ。OCRで読めた分と同じ扱いにする
            if p["mechanic"] == "メガシンカ" and not p["moves"]:
                p["moves"] = [{"name": got["specialMove"], "type": got.get("moveType")}]
        if "energy" in got and p["stats"] is not None:
            p["stats"]["energy"] = int(got["energy"])
        if "grade" in got:
            p["grade"] = int(got["grade"])

    OUT.write_text(json.dumps(picks, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"\ntotal {len(picks)} picks → {OUT.relative_to(ROOT.parent)}")
    print(f"ステータスあり {joined} / なし {len(picks) - joined}")
    print(f"裏面OCRで確定 {len(ocr)} / うち旧データと違っていた {changed}")
    print(f"タイプあり {sum(1 for p in picks if p['types'])} / 旧データと違っていた {types_changed}")
    print(f"★わかっている {sum(1 for p in picks if p['grade'] is not None)}")
    print(f"わざあり {sum(1 for p in picks if p['moves'])} / うち名前も裏面から {ocr_named} / タイプだけ照合できた旧データ {filled_moves} / 信用できず外した {dropped_moves}")
    print(f"てで入れたぶん {hand}")
    print(f"メガシンカの2行目をわざにした {mega_moves} / 仕組みあり {sum(1 for p in picks if p['mechanic'])} / とくべつなわざ {sum(1 for p in picks if p['specialMove'])} / でんせつ・まぼろし {sum(1 for p in picks if p['legend'])}")
    print(f"ポケエネあり {sum(1 for p in picks if p['stats'] and p['stats']['energy'] is not None)}")
    print(f"すばやさあり {sum(1 for p in picks if p['stats'] and p['stats']['speed'] is not None)}")
    print("グループ:", dict(Counter(p["group"] for p in picks)))
    print("グレード:", dict(Counter(str(p["grade"]) for p in picks)))


if __name__ == "__main__":
    main()
