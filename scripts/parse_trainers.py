#!/usr/bin/env python3
"""公式サイトの保存済みHTMLから、だんごとの たいせんトレーナー を取り出す。

各だんのページの #trainer-battle セクションに、たたかう相手のトレーナーと
「勝つともらえるきせかえアイテム」が載っている。1〜3だん・ワンダー・スペシャルには無い。

だんの表示名と並び順は src/data/picks.json から引く（parse_official.py の出力）ので、
先に build:data を通しておくこと。
"""

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw" / "official"
PICKS = ROOT.parent / "src" / "data" / "picks.json"
OUT = ROOT.parent / "src" / "data" / "trainers.json"

BASE = "https://pokemonfrienda.com/new/"

SECTION = re.compile(r'<section class="contents" id="trainer-battle">(.*?)</section>', re.S)
# 「img/bt5/img_trainer1_sp.webp?v2」のようにキャッシュ避けが付くことがある
TRAINER = re.compile(r'<img src="(img/[^"?]+/img_trainer(\d+)_sp\.webp)(?:\?[^"]*)?" alt="([^"]+)"')
REWARD = re.compile(r'color--brown[^>]*>([^<]+)</p>')
MODAL = re.compile(r'data-modal="trainerbattleItem"[^>]*data-img="(img/[^"]+)"')


# アプリの表示は漢字なしなので、公式の表記に出てくるぶんだけ かなに開く。
# 増えたらここに足す（build時に落ちるので気づける）。
KANA = {"白": "しろ", "黒": "くろ"}
KANJI = re.compile(r"[一-鿿]")


def text(s: str) -> str:
    value = html.unescape(s).strip()
    for kanji, kana in KANA.items():
        value = value.replace(kanji, kana)
    left = KANJI.findall(value)
    if left:
        raise SystemExit(f"かなに開けない漢字がある: {sorted(set(left))} in {value!r}")
    return value


def parse_page(key: str, label: str, order: int) -> list[dict]:
    path = RAW / f"{key}.html"
    if not path.exists():
        return []
    section = SECTION.search(path.read_text(encoding="utf-8", errors="replace"))
    if not section:
        return []
    body = section.group(1)

    # トレーナーの画像を目印にして、次のトレーナーまでの範囲を1人ぶんとして切る
    hits = list(TRAINER.finditer(body))
    out = []
    for i, m in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(body)
        block = body[m.end() : end]
        reward = REWARD.search(block)
        out.append({
            "id": f"{key}-{m.group(2)}",
            "set": key,
            "setLabel": label,
            "setOrder": order,
            "order": int(m.group(2)),
            "name": text(m.group(3)),
            "image": BASE + m.group(1),
            "reward": text(reward.group(1)) if reward else None,
            "rewardImages": [BASE + u for u in MODAL.findall(block)],
        })
    return out


def main() -> None:
    picks = json.loads(PICKS.read_text(encoding="utf-8"))
    # だん -> (表示名, 並び順)。ピック側と同じ順序・同じ呼び方にそろえる
    sets = {}
    for p in picks:
        sets.setdefault(p["set"], (p["setLabel"], p["setOrder"]))

    trainers: list[dict] = []
    for key, (label, order) in sorted(sets.items(), key=lambda kv: kv[1][1]):
        page = parse_page(key, label, order)
        if page:
            trainers.extend(page)
            print(f"{key:8} {len(page)}人  {[t['name'] for t in page]}")
        else:
            print(f"{key:8} たいせんトレーナーなし")

    missing = [t["id"] for t in trainers if not t["reward"]]
    if missing:
        print(f"\n※ もらえるアイテムが取れなかった: {missing}")

    OUT.write_text(json.dumps(trainers, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\ntotal {len(trainers)}人 → {OUT.relative_to(ROOT.parent)}")


if __name__ == "__main__":
    main()
