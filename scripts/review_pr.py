#!/usr/bin/env python3
"""定期更新のPRを調べて、問題なければマージするところまでやる。

    npm run pr

やること:
  1. PRの中身を main と比べて、ピック単位の要約を出す
  2. 前にわかっていた値が失われていないか調べる（あればここで止まる）
  3. 手で埋められる穴が残っていないか調べる
     → 残っていれば、そのブランチに移って npm run manual を開く
  4. どちらも問題なければマージする

手を入れる余地が無いときだけマージする、という作りにしてある。
迷ったら止まる方に倒しているので、止まった理由を読んでから自分で判断すること。
手順の全体は docs/review-update-pr.md にある。
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import diff_summary  # noqa: E402
import manual_fill  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BRANCH = "auto/update-data"
BASE = "main"
REPO = "Esystimsesys/pokemon-frienda-collection"
API = f"https://api.github.com/repos/{REPO}"


def run(*args: str, check: bool = True) -> str:
    p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise SystemExit(f"失敗: {' '.join(args)}\n{p.stderr.strip()}")
    return p.stdout.strip()


def token() -> str:
    """GitHubのトークンを、gitが覚えているところから取り出す。"""
    p = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True,
        text=True,
    )
    for line in p.stdout.splitlines():
        if line.startswith("password="):
            return line[len("password="):]
    raise SystemExit(
        "GitHubのトークンが見つからない。一度 git push などをして認証を通しておくこと。"
    )


def api(path: str, method: str = "GET", body: dict | None = None) -> dict | list:
    req = urllib.request.Request(
        f"{API}{path}",
        method=method,
        data=json.dumps(body).encode() if body else None,
        headers={
            "Authorization": f"token {token()}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read() or "{}")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"GitHub APIが {e.code} を返した: {e.read().decode()[:300]}")


def picks_at(ref: str) -> dict[str, dict]:
    """指定したrefの picks.json を読む（チェックアウトはしない）。"""
    raw = run("git", "show", f"{ref}:src/data/picks.json")
    return {p["id"]: p for p in json.loads(raw)}


def main() -> None:
    if run("git", "status", "--porcelain"):
        raise SystemExit(
            "作業ツリーに変更が残っている。コミットするか片付けてから実行すること\n"
            "（ブランチを移るので、消えると困るものがあると危ないため）。"
        )

    print("PRを取ってくる…")
    run("git", "fetch", "origin", BASE, BRANCH, check=False)

    prs = api(f"/pulls?state=open&head={REPO.split('/')[0]}:{BRANCH}")
    if not prs:
        raise SystemExit(f"{BRANCH} の開いているPRは無い。")
    pr = prs[0]
    print(f"PR #{pr['number']} {pr['title']}\n  {pr['html_url']}\n")

    before = picks_at(f"origin/{BASE}")
    after = picks_at(f"origin/{BRANCH}")
    result = diff_summary.analyse(before, after)
    print(diff_summary.render(before, after))
    print()

    if result["lost"]:
        raise SystemExit(
            f"■ 中止: 前はわかっていた値が {len(result['lost'])}件 失われている。\n"
            "  読み取りに失敗した可能性が高い。券面を見て確かめること。\n"
            "  手順: docs/review-update-pr.md"
        )
    if result["removed"]:
        raise SystemExit(
            f"■ 中止: ピックが {len(result['removed'])}件 消えている。中身を確かめること。"
        )

    # 手で埋められる穴が残っているかは、PRの中身に対して見る必要があるので移る。
    # そのまま手入力・コミット・pushができるよう、detachではなくブランチにする。
    here = run("git", "rev-parse", "--abbrev-ref", "HEAD")
    run("git", "switch", "-C", BRANCH, f"origin/{BRANCH}")

    # main を取り込んでから見る。手入力(manual.json)は main に置いてあるので、
    # 取り込まずに数えると、すでに埋めたものがまた穴に見える。
    # マージ後の状態で判断したいので、どのみちここで合わせておく必要がある。
    merged = subprocess.run(
        ["git", "merge", "--no-edit", BASE], cwd=ROOT, capture_output=True, text=True
    )
    if merged.returncode != 0:
        run("git", "merge", "--abort", check=False)
        run("git", "switch", here, check=False)
        raise SystemExit(
            f"■ 中止: {BASE} を取り込めなかった（衝突）。手で直すこと。\n{merged.stdout[-500:]}"
        )

    try:
        todo = manual_fill.build_todo()
    except Exception:
        run("git", "switch", here, check=False)
        raise

    if todo:
        kinds: dict[str, int] = {}
        for t in todo:
            for k in t["need"]:
                kinds[k] = kinds.get(k, 0) + 1
        print(f"■ 手で埋められる穴が {len(todo)}件 残っている: {kinds}")
        print("  ブラウザを開くので、埋めたら次を実行すること:")
        print("    npm run build:data")
        print("    git add -A src/data scripts/raw && git commit && git push")
        print("    npm run pr        # もう一度ここから")
        print()
        manual_fill.main()
        return

    run("git", "switch", here, check=False)
    print("■ 手で埋めるところは無し。マージする。")
    api(
        f"/pulls/{pr['number']}/merge",
        method="PUT",
        body={"merge_method": "squash", "commit_title": f"{pr['title']} (#{pr['number']})"},
    )
    print(f"マージした: PR #{pr['number']}")
    run("git", "switch", BASE, check=False)
    run("git", "pull", "--ff-only", "origin", BASE, check=False)
    print("main を最新にした。deploy.yml が動いて公開される。")


if __name__ == "__main__":
    main()
