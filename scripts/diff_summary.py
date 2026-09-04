#!/usr/bin/env python3
"""picks.json の変更を、人が読める要約にする。

定期更新のPRは差分が1万行を超えることがあり、そのままでは中身を確かめられない。
行の差分ではなく「ピック単位で何がどう変わったか」に直して出す。

  python3 scripts/diff_summary.py <前のpicks.json> [今のpicks.json]

前のファイルは `git show main:src/data/picks.json > /tmp/before.json` などで作る。
出力はそのままGitHubのPR本文に貼れる Markdown。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CURRENT = ROOT / "src" / "data" / "picks.json"

# 中身を見る意味がある項目だけ。setOrder のような並び替えの都合で動く値は数えるだけにする
FIELDS = ["name", "moves", "types", "stats", "grade", "mechanic", "specialMove", "legend"]
NOISY = ["setOrder"]


def load(path: Path) -> dict[str, dict]:
    return {p["id"]: p for p in json.loads(path.read_text(encoding="utf-8"))}


def is_empty(v) -> bool:
    return v in (None, [], {}, "")


def short(v, limit: int = 60) -> str:
    s = json.dumps(v, ensure_ascii=False)
    return s if len(s) <= limit else s[: limit - 1] + "…"


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    before = load(Path(sys.argv[1]))
    after = load(Path(sys.argv[2]) if len(sys.argv) > 2 else CURRENT)

    added = [i for i in after if i not in before]
    removed = [i for i in before if i not in after]

    lost: list[str] = []      # 前は値があったのに空になった＝データの後退
    changed: list[str] = []   # 値が別の値に変わった
    filled: list[str] = []    # 空だったところが埋まった
    noisy_count = 0

    for pick_id, old in before.items():
        new = after.get(pick_id)
        if new is None:
            continue
        for f in NOISY:
            if old.get(f) != new.get(f):
                noisy_count += 1
                break
        for f in FIELDS:
            o, n = old.get(f), new.get(f)
            if o == n:
                continue
            label = f"`{pick_id}` {new.get('name', '')} の {f}"
            if is_empty(n) and not is_empty(o):
                lost.append(f"{label}: {short(o)} → **空**")
            elif is_empty(o):
                filled.append(f"{label}: 空 → {short(n)}")
            else:
                changed.append(f"{label}: {short(o)} → {short(n)}")

    out: list[str] = []
    out.append("## 変更の要約")
    out.append("")
    out.append(f"ピック総数: {len(before)} → {len(after)}")
    out.append("")
    out.append("| 種別 | 件数 |")
    out.append("|---|---|")
    out.append(f"| 新規ピック | {len(added)} |")
    out.append(f"| 削除ピック | {len(removed)} |")
    out.append(f"| 値が失われた（要確認） | {len(lost)} |")
    out.append(f"| 値が変わった | {len(changed)} |")
    out.append(f"| 空欄が埋まった | {len(filled)} |")
    out.append(f"| 並び順(setOrder)だけの変更 | {noisy_count} |")
    out.append("")

    if lost:
        out.append("### ⚠ 値が失われたもの（マージ前に必ず確認）")
        out.append("")
        out.append("読み取りに失敗すると起きる。中身が本当に無くなったのでなければ、")
        out.append("マージせずに原因を確かめること。")
        out.append("")
        out.extend(f"- {x}" for x in lost[:30])
        if len(lost) > 30:
            out.append(f"- ほか {len(lost) - 30}件")
        out.append("")

    if added:
        by_set: dict[str, list[str]] = {}
        for i in added:
            p = after[i]
            by_set.setdefault(p.get("setLabel") or p.get("set", "?"), []).append(i)
        out.append("### 新しく増えたピック")
        out.append("")
        for label, ids in sorted(by_set.items()):
            names = ", ".join(f"{i} {after[i].get('name','')}" for i in sorted(ids)[:8])
            more = f" ほか{len(ids) - 8}件" if len(ids) > 8 else ""
            out.append(f"- **{label}** {len(ids)}件: {names}{more}")
        out.append("")

    if removed:
        out.append("### 消えたピック")
        out.append("")
        out.extend(f"- `{i}` {before[i].get('name','')}" for i in removed[:20])
        out.append("")

    if changed:
        out.append("### 値が変わったもの")
        out.append("")
        out.extend(f"- {x}" for x in changed[:30])
        if len(changed) > 30:
            out.append(f"- ほか {len(changed) - 30}件")
        out.append("")

    if filled:
        out.append(f"### 空欄が埋まったもの（{len(filled)}件）")
        out.append("")
        out.extend(f"- {x}" for x in filled[:15])
        if len(filled) > 15:
            out.append(f"- ほか {len(filled) - 15}件")
        out.append("")

    print("\n".join(out))


if __name__ == "__main__":
    main()
