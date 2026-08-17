#!/usr/bin/env python3
"""picks.json の欠けているところを一覧する。

    npm run gaps          まとめだけ
    npm run gaps -- -v    ピックのIDも出す

「券面に印字が無いので埋めようがないもの」と「まだ埋められるもの」を分けて出す。
後者は npm run manual で手入力できる。
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PICKS = ROOT.parent / "src" / "data" / "picks.json"
RAW = ROOT / "raw"


def load(name: str) -> dict:
    f = RAW / name
    return {r["id"]: r for r in json.loads(f.read_text(encoding="utf-8"))} if f.exists() else {}


def main() -> None:
    verbose = "-v" in sys.argv
    picks = json.loads(PICKS.read_text(encoding="utf-8"))
    special = load("ocr_special.json")
    n = len(picks)

    # (見出し, 埋まっているか, 埋めようがない理由 or None)
    absent: dict[str, list[str]] = defaultdict(list)   # 券面に無いので あきらめる
    fillable: dict[str, list[str]] = defaultdict(list)  # まだ手で埋められる
    have: Counter = Counter()

    for p in picks:
        pid, grp = p["id"], p["group"]
        stats = p["stats"]

        have["タイプ"] += bool(p["types"])
        if not p["types"]:
            fillable["タイプ"].append(pid)

        have["★"] += p["grade"] is not None
        if p["grade"] is None:
            # スペシャルは★のかわりに「スペシャル」の文字が入っていて、★じたいが無い
            (absent if grp == "special" else fillable)["★"].append(pid)

        have["ステータス5項目"] += stats is not None
        if stats is None:
            # 裏面にステータス欄が無いプロモ。ポケエネ・すばやさもここに載せられない
            absent["ステータス5項目"].append(pid)
        else:
            for key, label in (("energy", "ポケエネ"), ("speed", "すばやさ")):
                have[label] += stats[key] is not None
                if stats[key] is None:
                    fillable[label].append(pid)

        have["わざの名前"] += bool(p["moves"])
        have["わざのタイプ"] += bool(p["moves"]) and p["moves"][0]["type"] is not None
        if not p["moves"]:
            fillable["わざの名前"].append(pid)
            fillable["わざのタイプ"].append(pid)
        elif p["moves"][0]["type"] is None:
            fillable["わざのタイプ"].append(pid)

        # 仕組み・でんせつは「無いのが普通」なので、欠けとしては数えない。
        # ただし 仕組みがあるのに とくべつなわざ が読めていないものは埋められる
        if p["mechanic"] and not p["specialMove"]:
            fillable["とくべつなわざ"].append(pid)

    print(f"ピック {n}件\n")
    print("うまっているもの")
    for label in ("タイプ", "★", "ステータス5項目", "ポケエネ", "すばやさ", "わざの名前", "わざのタイプ"):
        c = have[label]
        print(f"  {label:14} {c:4} / {n}  {c / n * 100:5.1f}%")

    mech = sum(1 for p in picks if p["mechanic"])
    leg = sum(1 for p in picks if p["legend"])
    print(f"\n  とくべつな仕組み {mech}件 / でんせつ・まぼろし {leg}件（付いていないピックのほうが多いので割合は出さない）")

    if fillable:
        total = len({i for v in fillable.values() for i in v})
        print(f"\nまだ埋められるもの（npm run manual）  ピック {total}件")
        for label, ids in sorted(fillable.items(), key=lambda kv: -len(kv[1])):
            print(f"  {label:14} {len(ids):4}件" + (f"  {ids[:12]}{' …' if len(ids) > 12 else ''}" if verbose else ""))
    else:
        print("\nまだ埋められるもの: なし")

    print("\n券面に印字が無いので埋めようがないもの")
    for label, ids in sorted(absent.items(), key=lambda kv: -len(kv[1])):
        why = "スペシャルは★のかわりに文字が入っている" if label == "★" else "プロモは裏面にステータス欄が無い"
        print(f"  {label:14} {len(ids):4}件  … {why}")
        if verbose:
            print(f"    {ids[:12]}{' …' if len(ids) > 12 else ''}")

    # 仕組みが読めなかった理由（参考）
    if special:
        reasons = Counter(
            r.get("legendReason") for r in special.values() if not r.get("legend")
        )
        print(f"\n参考: でんせつ・まぼろしを判定できなかった理由 {dict(reasons)}")


if __name__ == "__main__":
    main()
