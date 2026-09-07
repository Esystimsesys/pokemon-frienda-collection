#!/usr/bin/env python3
"""picks.json の変更を、人が読める要約にする。

定期更新のPRは差分が1万行を超えることがあり、そのままでは中身を確かめられない。
行の差分ではなく「ピック単位で何がどう変わったか」に直して出す。

  python3 scripts/diff_summary.py <前のpicks.json> [今のpicks.json]
  python3 scripts/diff_summary.py <前のpicks.json> --base-ref <更新前のコミット>

前のファイルは `git show main:src/data/picks.json > /tmp/before.json` などで作る。
出力はそのままGitHubのPR本文に貼れる Markdown。
"""

from __future__ import annotations

import argparse
import json
import subprocess
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


def analyse(before: dict[str, dict], after: dict[str, dict]) -> dict:
    """変更をピック単位に分類する。review_pr.py からも使う。"""
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

    return {
        "before_count": len(before),
        "after_count": len(after),
        "added": added,
        "removed": removed,
        "lost": lost,
        "changed": changed,
        "filled": filled,
        "noisy_count": noisy_count,
    }


def render(before: dict[str, dict], after: dict[str, dict]) -> str:
    """analyse の結果を、PR本文に貼れる Markdown にする。"""
    r = analyse(before, after)
    added, removed = r["added"], r["removed"]
    lost, changed, filled = r["lost"], r["changed"], r["filled"]
    noisy_count = r["noisy_count"]

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

    return "\n".join(out)


def summarise_records(old: list[dict], new: list[dict]) -> str:
    """OCR結果と実行時の状態記録を分けて数える（単位はピック）。"""
    before = {r["id"]: r for r in old}
    after = {r["id"]: r for r in new}
    common = before.keys() & after.keys()
    updated = [i for i in common if before[i] != after[i]]
    metadata_only = [i for i in updated if
                     {k: v for k, v in before[i].items() if k != "had_existing_stats"} ==
                     {k: v for k, v in after[i].items() if k != "had_existing_stats"}]
    completed = sum(before[i].get("ocr_complete") is False and
                    after[i].get("ocr_complete") is True for i in common)
    regressed = sum(before[i].get("ocr_complete") is True and
                    after[i].get("ocr_complete") is False for i in common)
    parts = [f"追加 {len(after.keys() - before.keys())}件",
             f"削除 {len(before.keys() - after.keys())}件",
             f"読み取り結果等の変更 {len(updated) - len(metadata_only)}件",
             f"既存ステータスの有無の記録だけ {len(metadata_only)}件"]
    if completed or regressed:
        parts.append(f"読み取り不完全→完了 {completed}件 / 完了→不完全 {regressed}件")
    if old != new and not updated and before == after:
        parts.append("レコードの並び順のみ変更")
    return "、".join(parts)


def render_data_changes(base_ref: str, picks_unchanged: bool) -> str:
    """PR作成の判定と同じ範囲を比較し、JSON以外も変更一覧に含める。"""
    def git(*args: str) -> bytes:
        return subprocess.check_output(["git", *args], cwd=ROOT)

    # オプションをrefと誤認しないよう、先にコミットIDへ解決する。
    base = git("rev-parse", "--verify", "--end-of-options", f"{base_ref}^{{commit}}").decode().strip()
    paths = git("diff", "--name-only", "--no-renames", "-z", base,
                "--", "src/data", "scripts/raw").decode().split("\0")
    paths = [p for p in paths if p]
    out = ["", "## PRが作成された理由", ""]
    if not paths:
        out.append("対象データにファイル差分はありません。")
        return "\n".join(out)
    if picks_unchanged:
        out.append("**図鑑のピックデータ（picks.json）に変更はありません。**")
        if all(p.startswith("scripts/raw/") for p in paths):
            out.append("このPRは、次回のデータ生成に使う中間データを更新するために作成されました。")
        else:
            out.append("ピック以外のデータや生成ファイルに差分があるため、PRが作成されました。")
    else:
        out.append("図鑑のピックデータに変更があります。上の要約と以下の変更ファイルを確認してください。")
    out += ["", "### 変更ファイル", ""]
    for path in paths:
        target = ROOT / path
        exists_before = bool(git("ls-tree", "--name-only", base, "--", path))
        detail = "更新"
        if not target.exists():
            detail = "削除"
        elif not exists_before:
            detail = "追加"
        elif path.startswith("scripts/raw/") and target.suffix == ".json":
            try:
                old = json.loads(git("show", f"{base}:{path}"))
                new = json.loads(target.read_text(encoding="utf-8"))
                if all(isinstance(v, list) and all(isinstance(r, dict) and "id" in r for r in v)
                       for v in (old, new)):
                    detail = summarise_records(old, new)
                else:
                    detail = "中間データの更新（詳細はファイル差分を確認）"
            except (ValueError, UnicodeError):
                detail = "ファイル更新（JSONとして比較できないため、差分を確認）"
        out.append(f"- `{path}`: {detail}")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("before", type=Path)
    ap.add_argument("after", type=Path, nargs="?", default=CURRENT)
    ap.add_argument("--base-ref", help="更新前のコミット。指定すると中間データの差分も要約する")
    args = ap.parse_args()
    before = load(args.before)
    after = load(args.after)
    print(render(before, after))
    if args.base_ref:
        print(render_data_changes(args.base_ref, before == after))


if __name__ == "__main__":
    main()
