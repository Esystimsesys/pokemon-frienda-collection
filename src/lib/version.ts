/**
 * デプロイのたびにCI（.github/workflows/deploy.yml）が埋めこむビルド情報。
 * キャッシュが残って新しいバージョンに切りかわっていないときに、
 * 「きろく」画面でこの値を見て確認できるようにするためのもの。
 * ローカル開発（npm start 等）ではどちらも入らない。
 */
export const BUILD_SHA = process.env.EXPO_PUBLIC_BUILD_SHA ?? null;
export const BUILD_TIME = process.env.EXPO_PUBLIC_BUILD_TIME ?? null;
