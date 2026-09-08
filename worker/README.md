# フレンダサークル 同期プロキシ（Cloudflare Worker）

`circle.pokemonfrienda.com` はFirebase認証つきのJSアプリで公開APIが無いため、
Cloudflare Browser Rendering（ヘッドレスブラウザ）で本物のページを開き、
中身（トレーナー情報・所持ピック一覧）だけをアプリ側に返すプロキシ。

無料枠（1日10分のブラウザ実行時間）の範囲で、家族利用なら十分足りる想定。

## セットアップ（初回だけ）

```bash
cd worker
npm install
npx wrangler login   # Cloudflareの無料アカウントでログイン（ブラウザが開く）
npm run deploy
```

デプロイが終わると `https://frienda-circle-proxy.<あなたのサブドメイン>.workers.dev` の
ようなURLが表示される。このURLを控えて、`src/lib/circle.ts` の `WORKER_URL` を書きかえる。

```ts
// src/lib/circle.ts
const WORKER_URL = "https://frienda-circle-proxy.xxxxx.workers.dev"; // ← ここを実際のURLに
```

## PWAのURLが違うとき

GitHub Pagesの公開URLがREADMEに書かれているものと違う場合、
`worker/src/index.js` の `ALLOWED_ORIGINS` にそのオリジンを追記してから
`npm run deploy` をやり直すこと（CORSで弾かれてしまうため）。

## 更新のしかた

`worker/src/index.js` を直したら `npm run deploy` するだけ。
GitHub Pages側のような自動デプロイは組んでいない（変更頻度が低いため、手動で十分）。

## レート制限

Worker はトークンのハッシュごと・クライアントIPのハッシュごとに専用の Durable Object SQLiteへ
直近24時間の同期回数を保存し、それぞれ10回まで許可する。2つのDOを順番に消費するため、IP側で
拒否された場合も先に消費したトークン側の1枠は戻らない。これは競合時に上限を超えないための
fail-closedな仕様で、どちらかが上限に達した場合は `429` と `Retry-After` を返す。各DO内の判定と
記録は同じSQLiteトランザクションで行うため、同時リクエストでも個別の上限を超えてブラウザを起動しない。
同じWi-FiやNAT配下の端末は、Cloudflareから同じ公開IPに見える場合、そのIP側の10回枠を共有する。

Cloudflareの `CF-Connecting-IP` が付かないリクエストは拒否する。`wrangler dev` のローカルテストでは
このヘッダーを付けて試すこと。Workerのコードまたは `wrangler.toml` を変更したときは、Durable Object
のバインディングとSQLite migrationを含めて `npm run deploy` を実行する必要がある。
