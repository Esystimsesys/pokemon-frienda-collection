# 定期更新のPRを手元で確認・補正する

`ずかんデータの定期更新` ワークフローが作るPR（ブランチ `auto/update-data`）を、
手元で中身まで確かめて、必要なら直してからマージするための手順。

JSONの行差分は1万行を超えることがあり、GitHubの画面では中身を判断できない。
**行ではなくピック単位で見る**のが基本。

## 1. PRを手元に持ってくる

```sh
git fetch origin auto/update-data
git switch auto/update-data
```

## 2. 何が変わったのかを人が読める形で見る

```sh
git show main:src/data/picks.json > /tmp/picks_before.json
python3 scripts/diff_summary.py /tmp/picks_before.json
```

PR本文にも同じ要約が自動で載っている。見るべき順は次のとおり。

PRは `src/data` と `scripts/raw` に差分があれば作られるため、新規ピックが0件でも
作成される。本文の「PRが作成された理由」「変更ファイル」で、図鑑自体の変更か、
次回のデータ生成に使うOCR中間データだけの変更かを確認する。
OCR中間データは、読み取り結果の変更と「既存ステータスの有無」の記録だけの変更を
分けて数える。読み取り完了から不完全に戻ったものも表示する。

手元でも中間データを含めて確認する場合は、更新前のコミットを指定する。

```sh
python3 scripts/diff_summary.py /tmp/picks_before.json --base-ref main
```

| 見出し | 意味 | 対応 |
|---|---|---|
| **値が失われた** | 前は分かっていた値が空になった | **ここが0件でなければマージしない。** 下の「3.」へ |
| 新しく増えたピック | 新弾が出た。本来の目的 | 名前と件数が公式の発表と合っているか見る |
| 値が変わった | 読み取り結果が前と変わった | 券面の画像を実際に見て、どちらが正しいか確かめる |
| 空欄が埋まった | 読めていなかったものが読めた | ふつうは歓迎してよい |
| 並び順(setOrder)だけ | 弾が増えたことによる採番 | 中身に影響しない。見なくてよい |

## 3. 「値が失われた」が出たときの調べ方

いちばん多い原因は**OCRの読み落とし**。とくに GitHub Actions の macOS ランナーは
Apple Vision の読み取りが手元のMacより弱く、しきい値ぎりぎりのものが落ちる
（実測で、同じ958枚に対して手元135件 / CI146件の読み取り失敗）。

まず券面の画像を実際に見て、本当にその値が無いのかを確かめる。

```sh
open scripts/raw/pick_images/2-3-001.webp     # 該当ID
```

`parse_official.py` には「前は分かっていた値を空で上書きしない」ガードが入っているので、
本来ここに出るのは**ガードでも救えなかったもの**か、**ガード導入前に作られたPR**だけ。
手元で作り直せば直ることが多い。

```sh
npm run update          # 手元のMacで読み直す（差分OCRなので新規ぶんだけ読む）
git add -A src/data scripts/raw
git commit -m "data: 手元で読み直して補正する"
git push origin auto/update-data
```

## 4. 特定のピックだけ手で直したいとき

読み取りではどうしても入らない値は `scripts/raw/manual.json` に書く。
このファイルは作り直せないので、OCRの結果より優先され、更新でも消えない。

```sh
$EDITOR scripts/raw/manual.json
python3 scripts/parse_official.py     # picks.json に反映
```

## 5. 読み取りそのものを見直したいとき

```sh
# わざ名の読み取り具合を見る（しきい値の下見）
python3 scripts/ocr/fill_moves_from_ocr.py --scores

# 既存データに対するカバー率・一致率を測る
python3 scripts/ocr/fill_moves_from_ocr.py --validate

# 保存ぶんを使わず全件読み直す（Visionの更新後などに）
python3 scripts/ocr/fill_moves_from_ocr.py --run-all --full
```

わざ名の読み取り結果は `scripts/raw/ocr_moves_reads.json` に保存してあり、
ふだんは新しいピックだけを読む（958枚を読み直すと手元で6分、CIで40分以上かかるため）。
`move_ocr.py` か `ocr_moves.swift` を変えると指紋が変わり、自動で全件読み直しになる。

## 6. 最後に、欠けているところを手で埋める

新しいだんが入った回は、OCRで読み切れない項目がかならず残る。
マージする前にここまでやる。

```sh
npm run gaps            # 何がどれだけ欠けているかの一覧
npm run manual          # ブラウザ(8099)で券面を見ながら手入力
npm run build:data      # 入力を picks.json に反映（manual.json は最優先で当たる）
```

`npm run manual` の「未入力を埋める」は、埋められる穴だけを順に聞いてくる。
入れた値は `scripts/raw/manual.json` に残り、`npm run update` を回しても消えない。

**手入力できる項目とできない項目がある。**

| 項目 | 手入力 |
|---|---|
| わざの名前 / わざのタイプ | できる |
| ポケエネ / ★ / とくべつなわざ | できる |
| HP・ATK・DEF・SP.ATK・SP.DEF | **できない**（OCRで読むしかない） |

ステータス5項目が丸ごと欠けているピックがあるときは、`npm run manual` では埋まらない。
`npm run gaps` はそれを「券面に印字が無いので埋めようがないもの（プロモ）」に
数えてしまうので、**本当に印字が無いのか、券面を見て確かめること。**

```sh
open scripts/raw/pick_images/3-2-001.webp
```

印字があるのに読めていない場合は、券面の字形が変わってテンプレート照合が
効かなくなっている（エクストレジャー2だんで実際に起きた。数字自体は合っていても
確信度が0.27〜0.71しか出ず、SP.DEFの151を351と誤読していた）。この場合の選択肢:

- ファンサイト(pokearcade)がその弾のデータを出すのを待つ。出れば `npm run update` が拾う
- `npm run ocr:build-templates` でテンプレートを作り直す（正解データが増えてから）

いずれも間に合わないなら、その弾はステータス無しのまま公開してよい。
アプリ側は `stats` が null でも表示できるようになっている。

## 7. 問題なければマージする

```sh
gh pr merge auto/update-data --squash   # または GitHub の画面から
```

マージすると `deploy.yml` が動いて GitHub Pages に反映される。

## 補足: なぜCIとMacで結果が違うのか

券面のわざ名だけは Apple Vision（`scripts/ocr/ocr_moves.swift`）を使っており、
これはOSに載っている認識エンジンなので、**マシンやOSのバージョンで結果が変わる**。
ステータスや★・タイプの読み取りはテンプレート照合（純粋な計算）なので、
どこで動かしても同じ結果になる。

差分OCRを入れてからは、既存ピックは手元で読んだ結果を使い回すので、
CIが再読み取りして落とすことは起きない。CIが新しく読むのは新規ピックだけ。
