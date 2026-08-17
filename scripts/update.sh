#!/usr/bin/env bash
# 公式サイトを見に行って、図鑑のデータを作り直す。
# 新しいだんが出たときも、これ1本でよい（コードを直す必要はない）。
#
#   npm run update
#
# 公開は main への push が引き金なので、ここではやらない。
# データが変わったらコミットして push すること（.github/workflows/deploy.yml が動く）。
set -euo pipefail

cd "$(cd "$(dirname "$0")/.." && pwd)"

step() { printf '\n\033[1m=== %s\033[0m\n' "$1"; }

step "1/7 公式の一覧を取得"
python3 scripts/fetch_official.py

# 裏面OCRの前に、いちど picks.json を作って画像URLを確定させる。
# 新しいピックはこの時点ではステータスもタイプも空のまま。
step "2/7 ピックの一覧を作る（画像URLを確定させるため）"
python3 scripts/parse_official.py

step "3/7 裏面の画像を取得（あるぶんは飛ばす）"
python3 scripts/ocr/fetch_pick_images.py

step "4/7 券面を読む（ステータス／タイプ・★／わざ名／すばやさ・ポケエネ）"
python3 scripts/ocr/fill_stats_from_ocr.py --run-all
python3 scripts/ocr/fill_header_from_ocr.py --run-all
python3 scripts/ocr/fill_moves_from_ocr.py --run-all
python3 scripts/ocr/fill_extra_from_ocr.py --run-all

# すばやさは券面から100%読めるので、ここはポケエネを補うためだけに使う。
# 券面だけでもポケエネの85%は埋まるので、取れなくても止めない。
step "5/7 ポケエネのおぎない（公式外。取れなければ飛ばす）"
if curl -sfS -A "Mozilla/5.0" \
    "https://pokearcade.jp/%E3%83%95%E3%83%AC%E3%83%B3%E3%83%80%E3%83%94%E3%83%83%E3%82%AF%E5%85%A8%E5%BC%BE%E3%83%87%E3%83%BC%E3%82%BF%E3%83%99%E3%83%BC%E3%82%B9/" \
    -o scripts/raw/pokearcade.html; then
  python3 scripts/parse_pokearcade.py || echo "  → 取り込めなかった。ポケエネは券面から読めたぶんだけになる"
else
  echo "  → 取得できなかった。ポケエネは券面から読めたぶんだけになる"
fi

step "6/7 マスタを作り直す"
python3 scripts/parse_official.py
python3 scripts/parse_trainers.py

step "7/7 型チェックとビルド"
./node_modules/.bin/tsc --noEmit
npm run build:web

printf '\nできあがり。公開するには、変わったものをコミットして main に push すること。\n'
git -C "$(pwd)" status --short src/data scripts/raw 2>/dev/null || true
