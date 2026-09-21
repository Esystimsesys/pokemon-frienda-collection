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
        detail = p.stderr.strip() or p.stdout.strip() or "詳しいエラーは出力されなかった"
        raise SystemExit(
            "\n■ 処理に失敗しました\n\n"
            f"実行した処理:\n  {' '.join(args)}\n\n"
            f"エラー内容:\n  {detail}\n\n"
            "この時点ではPRをマージしていません。エラーを解消してから npm run pr をもう一度実行してください。"
        )
    return p.stdout.strip()


def stop(title: str, state: str, reason: str, next_steps: list[str]) -> SystemExit:
    """停止理由を「状態・理由・次の操作」の順で案内する。"""
    steps = "\n".join(f"  {i}. {step}" for i, step in enumerate(next_steps, 1))
    return SystemExit(
        f"\n■ {title}\n\n"
        f"現在の状態:\n{state}\n\n"
        f"止めた理由:\n  {reason}\n\n"
        f"次にすること:\n{steps}"
    )


def describe_changes(raw: str) -> str:
    """git status --porcelain を、Gitに不慣れでも読める一覧にする。"""
    labels = {"M": "変更", "A": "追加", "D": "削除", "R": "名前変更", "?": "未追跡"}
    lines = []
    for line in raw.splitlines():
        code, path = line[:2], line[3:]
        kind = next((labels[c] for c in code if c in labels), "競合または未完了")
        lines.append(f"  - {kind}: {path}")
    return "\n".join(lines)


def working_tree_changes() -> str:
    """先頭行のステータス用空白を消さずに取得する。"""
    p = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
    )
    if p.returncode != 0:
        raise SystemExit("git status を実行できませんでした。Gitリポジトリ内で実行してください。")
    return p.stdout.rstrip("\n")


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
    raise stop(
        "GitHubに接続する認証情報が見つかりません",
        "  ローカルのデータやブランチは変更していません。",
        "PRの取得・マージにはGitHubへのログインが必要です。",
        [
            "ターミナルで gh auth login を実行してGitHubへログインする",
            "ログイン後に npm run pr をもう一度実行する",
        ],
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
        detail = e.read().decode(errors="replace")[:300]
        raise stop(
            "GitHubとの通信に失敗しました",
            "  PRはマージしていません。ローカルの入力内容も残っています。",
            f"GitHub APIから HTTP {e.code} が返りました。\n  {detail}",
            [
                "ネットワーク接続とGitHubのログイン状態を確認する",
                "確認後に npm run pr をもう一度実行する",
            ],
        )


def picks_at(ref: str) -> dict[str, dict]:
    """指定したrefの picks.json を読む（チェックアウトはしない）。"""
    raw = run("git", "show", f"{ref}:src/data/picks.json")
    return {p["id"]: p for p in json.loads(raw)}


def ensure_pick_images() -> None:
    """PRで増えたピックを含め、補完画面で使う券面画像を揃える。"""
    print("[4/5] 補完画面で使うピック画像を確認しています…")
    run(sys.executable, str(ROOT / "scripts" / "ocr" / "fetch_pick_images.py"))

    picks = json.loads((ROOT / "src" / "data" / "picks.json").read_text(encoding="utf-8"))
    images = ROOT / "scripts" / "raw" / "pick_images"
    missing = [p["id"] for p in picks if not (images / f"{p['id']}.webp").is_file()]
    if missing:
        sample = ", ".join(missing[:10])
        more = f" ほか{len(missing) - 10}件" if len(missing) > 10 else ""
        raise stop(
            "ピック画像を取得できなかったため停止しました",
            f"  不足している画像: {len(missing)}件\n  {sample}{more}",
            "画像が無いまま補完画面を開いても券面を確認できません。",
            [
                "ネットワーク接続を確認する",
                "npm run pr をもう一度実行する（取得済みの画像は再利用されます）",
            ],
        )
    print(f"      画像は全{len(picks)}件そろっています。")


def refresh_official_pages() -> None:
    """手入力後の再生成に使う公式一覧を、PRと同じ時点まで新しくする。"""
    print("[3/5] 再生成に使う公式ピック一覧を更新しています…")
    run(sys.executable, str(ROOT / "scripts" / "fetch_official.py"))
    print("      最新の公式一覧を保存しました。")


def main() -> None:
    print("=== 定期更新PRの確認 ===")
    print("PRの内容を確認し、必要なら手入力を案内し、問題が無ければマージします。\n")

    changes = working_tree_changes()
    if changes:
        branch = run("git", "branch", "--show-current") or "（ブランチ名なし）"
        data_work = any(
            path in changes
            for path in ("scripts/raw/manual.json", "src/data/picks.json")
        )
        if data_work:
            reason = (
                "補完画面で入力した内容が、まだコミット・pushされていない可能性があります。"
                " npm run pr は途中でブランチを切り替えるため、入力内容を守るために停止しました。"
            )
            next_steps = [
                "npm run build:data を実行して、手入力を picks.json に反映する",
                "git diff --stat と git diff で変更内容を確認する",
                "git add -A src/data scripts/raw でデータ変更をステージする",
                "上の一覧にデータ以外の必要な変更もあれば、そのファイルも git add する",
                'git commit -m "data: ピックデータを手動補完する" でステージ済みの変更をコミットする',
                f"git push origin {branch} でPRのブランチへ反映する",
                "npm run pr をもう一度実行する",
            ]
        else:
            reason = (
                "コミットされていない変更があります。npm run pr は途中でブランチを切り替えるため、"
                "変更を失ったり別のブランチへ混ぜたりしないよう停止しました。"
            )
            next_steps = [
                "git diff と git status で変更内容を確認する",
                "必要な変更ならコミットする。不要か判断できない変更は削除しない",
                "git status が変更なしになったら npm run pr をもう一度実行する",
            ]
        raise stop(
            "未保存の変更があるため、PR確認を開始していません",
            f"  現在のブランチ: {branch}\n{describe_changes(changes)}",
            reason,
            next_steps,
        )

    print("[1/5] GitHubから最新のPRを取得しています…")
    run("git", "fetch", "origin", BASE, BRANCH, check=False)

    prs = api(f"/pulls?state=open&head={REPO.split('/')[0]}:{BRANCH}")
    if not prs:
        print("\n■ 確認するPRはありません")
        print(f"  {BRANCH} の開いているPRはありません。今回は何もしなくて大丈夫です。")
        return
    pr = prs[0]
    print(f"      対象: PR #{pr['number']} {pr['title']}\n      {pr['html_url']}\n")

    print("[2/5] main とPRのデータ差分を確認しています…")
    before = picks_at(f"origin/{BASE}")
    after = picks_at(f"origin/{BRANCH}")
    result = diff_summary.analyse(before, after)
    print(diff_summary.render(before, after))
    print()

    if result["lost"]:
        raise stop(
            "既存データが失われているため、マージしていません",
            f"  前回は入っていた値が空になった箇所: {len(result['lost'])}件",
            "OCRの読み取り失敗などで、正しい既存データを消す可能性があります。",
            [
                "上の「値が失われた」一覧で対象ピックを確認する",
                "docs/review-update-pr.md の「値が失われた」を参照して券面と照合する",
                "修正をPRブランチへpushした後、npm run pr をもう一度実行する",
            ],
        )
    if result["removed"]:
        raise stop(
            "既存ピックが消えているため、マージしていません",
            f"  PRで一覧から消えるピック: {len(result['removed'])}件",
            "公式サイト側の一時的な欠落をそのまま反映する可能性があります。",
            [
                "上の「消えたピック」一覧を確認する",
                "公式サイトから本当に削除されたものか確認する",
                "問題を修正してPRブランチへpushした後、npm run pr をもう一度実行する",
            ],
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
        detail = (merged.stderr or merged.stdout).strip()[-500:]
        raise stop(
            "mainとの競合があるため、マージしていません",
            f"  元のブランチ {here} に戻しました。\n  Gitの出力: {detail}",
            f"PRブランチ {BRANCH} と {BASE} の同じ箇所が変更されています。",
            [
                f"git switch {BRANCH} でPRブランチへ移る",
                f"git merge {BASE} を実行し、表示された競合を解消する",
                f"解消した変更をコミットして git push origin {BRANCH} を実行する",
                "npm run pr をもう一度実行する",
            ],
        )

    try:
        refresh_official_pages()
        ensure_pick_images()
        todo = manual_fill.build_todo()
    except BaseException:
        run("git", "switch", here, check=False)
        raise

    if todo:
        kinds: dict[str, int] = {}
        for t in todo:
            for k in t["need"]:
                kinds[k] = kinds.get(k, 0) + 1
        print("\n[5/5] 手入力が必要な項目を確認しました。")
        print(f"      対象ピック: {len(todo)}件")
        print(f"      不足項目: {kinds}")
        print(f"      現在のブランチ: {BRANCH}")
        print("\n■ ブラウザで補完作業を始めます")
        print("  入力内容は scripts/raw/manual.json に自動保存されます。")
        print("  終わったらターミナルへ戻り、Ctrl-C で補完画面を停止してください。")
        try:
            manual_fill.main()
        except KeyboardInterrupt:
            print("\n\n■ 補完画面を停止しました")
        print("\n次にすること:")
        print("  1. npm run build:data")
        print("  2. git diff --stat と git diff で変更内容を確認する")
        print("  3. git add -A src/data scripts/raw")
        print('  4. git commit -m "data: ピックデータを手動補完する"')
        print(f"  5. git push origin {BRANCH}")
        print("  6. npm run pr")
        return

    run("git", "switch", here, check=False)
    print("\n[5/5] 手入力が必要な項目はありません。PRをマージします…")
    merged_pr = api(
        f"/pulls/{pr['number']}/merge",
        method="PUT",
        body={"merge_method": "squash", "commit_title": f"{pr['title']} (#{pr['number']})"},
    )
    if not isinstance(merged_pr, dict) or not merged_pr.get("merged"):
        message = merged_pr.get("message", "理由は返されませんでした") if isinstance(merged_pr, dict) else "応答が不正でした"
        raise stop(
            "GitHubがPRのマージを受け付けませんでした",
            f"  PR #{pr['number']} は未マージです。\n  GitHubの応答: {message}",
            "必須チェックの未完了や、PRの更新が原因の可能性があります。",
            [
                f"PRの画面 {pr['html_url']} で状態を確認する",
                "問題を解消した後、npm run pr をもう一度実行する",
            ],
        )
    print(f"      PR #{pr['number']} をsquash mergeしました。")
    run("git", "switch", BASE, check=False)
    run("git", "pull", "--ff-only", "origin", BASE, check=False)
    print("\n■ 完了")
    print("  main を最新にしました。GitHub Actionsの公開処理が自動で始まります。")


if __name__ == "__main__":
    main()
