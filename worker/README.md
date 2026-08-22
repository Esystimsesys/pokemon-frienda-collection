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
