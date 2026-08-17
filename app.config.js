const app = require("./app.json");

/**
 * GitHub Pages はリポジトリ名がURLに入る（https://ユーザー名.github.io/リポジトリ名/）。
 * ビルドのときだけ EXPO_BASE_URL でそのぶんを渡す。
 * 手元の開発サーバーはルート配信なので、なにも渡さなければ今までどおり。
 *
 * これに合わせて public/index.html・manifest.json・sw.js も相対パスにしてある。
 */
const baseUrl = (process.env.EXPO_BASE_URL || "").replace(/\/+$/, "");

module.exports = {
  ...app,
  expo: {
    ...app.expo,
    experiments: { ...app.expo.experiments, ...(baseUrl ? { baseUrl } : {}) },
  },
};
