#!/usr/bin/env python3
"""ピック画像（裏面にステータスが印字されたwebp）をローカルへキャッシュする。

- 公式サイトへの同時接続は5本以下、失敗時は最大3回までリトライする。
- すでに取得済みのファイルは再ダウンロードしない（scripts/raw/ 配下はgitignore対象）。
"""

import json
import time
import urllib.request
import urllib.error
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PICKS = ROOT.parent / "src" / "data" / "picks.json"
OUT_DIR = ROOT / "raw" / "pick_images"
MAX_WORKERS = 5
MAX_RETRIES = 3
TIMEOUT = 20

UA = "pokemon-frienda-collection/ocr-stats-fetch (+local dev tool)"


def fetch_one(pick_id: str, url: str) -> str:
    dest = OUT_DIR / f"{pick_id}.webp"
    if dest.exists() and dest.stat().st_size > 0:
        return f"cached {pick_id}"

    # ファイル名に ★ などの非ASCII文字を含むURLがあるためパーセントエンコードする
    parts = urllib.parse.urlsplit(url)
    safe_url = urllib.parse.urlunsplit(
        parts._replace(path=urllib.parse.quote(parts.path))
    )

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(safe_url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = resp.read()
            tmp = dest.with_suffix(".webp.part")
            tmp.write_bytes(data)
            tmp.rename(dest)
            return f"ok {pick_id}"
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            time.sleep(1.5 * attempt)
    return f"FAILED {pick_id}: {last_err}"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    picks = json.loads(PICKS.read_text(encoding="utf-8"))

    ok = cached = failed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(fetch_one, p["id"], p["image"]) for p in picks]
        for fut in as_completed(futures):
            r = fut.result()
            if r.startswith("ok"):
                ok += 1
            elif r.startswith("cached"):
                cached += 1
            else:
                failed += 1
                print(r)

    print(f"downloaded={ok} cached={cached} failed={failed} total={len(picks)}")


if __name__ == "__main__":
    main()
