#!/usr/bin/env python3
"""公式サイト（pokemonfrienda.com）のフレンダピック一覧を取得する。

だんの一覧はべた書きしない。どのページにも他の全ページへのリンクがあるので、
1つ取ってきてそこから残りを見つける。こうしておけば、新しいだんが出ても
コードを触らずに図鑑へ入る。

ページの並びは「並び順」として sets.json に書き出し、parse_official.py が読む。
"""

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "raw" / "official"

BASE = "https://pokemonfrienda.com"
# ここだけは起点として決め打ちする。1だんのページが消えることは考えにくい
SEED = "/new/1.html"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Safari/605.1.15"


def get(path: str) -> str:
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def discover(html: str) -> list[tuple[str, str]]:
    """(キー, URLのディレクトリ) を、新しいだん→古いだん→ワンダー→スペシャル の順で返す"""
    seen: set[str] = set()
    links: list[str] = []
    for u in re.findall(r'href="(/new/[^"#?]*)"', html):
        if u not in seen and u != "/new/":
            seen.add(u)
            links.append(u)

    # 公式のナビは新しいだんが先頭に並んでいる。図鑑でも新しいだんから見たい
    # （ふるいだんは終了していて、いま遊んでいるのは新しいだん）ので、この順のまま使う。
    # ワンダー／スペシャルはディレクトリ形式で、いつも最後に置かれている。
    dan = [u for u in links if u.endswith(".html")]
    other = [u for u in links if not u.endswith(".html")]

    out: list[tuple[str, str]] = [(Path(u).stem, "") for u in dan]
    for u in other:
        out.append((u.strip("/").split("/")[-1], u.split("/")[-2] + "/"))
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    seed = get(SEED)
    pages = discover(seed)
    if not pages:
        raise SystemExit("だんのリンクが1つも見つからない。公式のページ構成が変わったかもしれない")

    sets = []
    for order, (key, subdir) in enumerate(pages):
        path = f"/new/{subdir}" if subdir else f"/new/{key}.html"
        try:
            html = seed if path == SEED else get(path)
        except urllib.error.URLError as e:
            raise SystemExit(f"{key}: 取得できなかった（{e}）")
        (OUT / f"{key}.html").write_text(html, encoding="utf-8")
        sets.append({"key": key, "subdir": subdir, "order": order})
        print(f"{key:8} {len(html):8,} bytes")
        time.sleep(0.5)

    (OUT / "sets.json").write_text(json.dumps(sets, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\n{len(sets)}ページ → {(OUT / 'sets.json').relative_to(ROOT.parent)}")


if __name__ == "__main__":
    main()
