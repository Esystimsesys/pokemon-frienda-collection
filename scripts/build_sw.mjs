#!/usr/bin/env node
/**
 * expo export のあとに走らせて dist/sw.js を作る。
 *
 * アプリ本体のファイル名にはハッシュが付くので、固定の sw.js を public に置くことができない。
 * 書き出したあとの dist を読んで、そのときの実ファイル一覧を埋め込んだ sw.js を生成する。
 */

import { createHash } from "node:crypto";
import { readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { join, posix, relative } from "node:path";
import { fileURLToPath } from "node:url";

const DIST = fileURLToPath(new URL("../dist", import.meta.url));

/**
 * sw.js 自身とビルド情報は除く。404.html は index.html と同じ中身なので入れない。
 */
const SKIP = new Set(["sw.js", "metadata.json", "404.html"]);

function walk(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else out.push(full);
  }
  return out;
}

const files = walk(DIST)
  .map((f) => relative(DIST, f).split(/[\\/]/).join(posix.sep))
  .filter((f) => !SKIP.has(f))
  .sort();

/**
 * パスは相対にしておく。GitHub Pages のようにリポジトリ名がURLに入る置きかたでも、
 * sw.js の場所を起点に解決されるので、そのまま動く。
 * index.html は "./" として要求されるので、そちらに寄せる。
 */
const precache = files.map((f) => (f === "index.html" ? "./" : `./${f}`));

// 中身が1バイトでも変わればキャッシュ名が変わるようにする
const hash = createHash("sha256");
for (const f of files) {
  hash.update(f);
  hash.update(readFileSync(join(DIST, f)));
}
const version = hash.digest("hex").slice(0, 12);

const sw = `// expo export のあとに scripts/build_sw.mjs が自動生成する。直接編集しないこと。
const VERSION = ${JSON.stringify(version)};
const SHELL = "friendadex-shell-" + VERSION;
const IMAGES = "friendadex-images-v1";
const PRECACHE = ${JSON.stringify(precache, null, 2)};

/** この sw.js が置かれている場所＝アプリの置き場 */
const APP_ROOT = new URL("./", self.location.href).href;

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      // ピック画像のキャッシュは作り直さない。消えると全部ダウンロードし直しになるため
      const keys = await caches.keys();
      await Promise.all(
        keys.filter((k) => k.startsWith("friendadex-shell-") && k !== SHELL).map((k) => caches.delete(k)),
      );
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);

  // 1画面だけのSPAなので、どのURLで開かれても index.html を返す
  if (request.mode === "navigate") {
    event.respondWith(
      caches.match(APP_ROOT, { cacheName: SHELL }).then((hit) => hit || fetch(request)),
    );
    return;
  }

  // 同じ置き場のファイルだけを見る。origin だけで見ると、
  // 同じドメインに置かれた別のサイトまで拾ってしまう
  if (request.url.startsWith(APP_ROOT)) {
    event.respondWith(caches.match(request).then((hit) => hit || fetch(request)));
    return;
  }

  // 公式のピック画像は、一度見たものを取っておいて次からはオフラインでも出す
  if (url.hostname === "pokemonfrienda.com") {
    event.respondWith(cacheFirstImage(request));
  }
});

async function cacheFirstImage(request) {
  const cache = await caches.open(IMAGES);
  const hit = await cache.match(request);
  if (hit) return hit;

  try {
    // 公式は CORS ヘッダを返さないので、img タグからの no-cors な要求（opaque）のまま扱う
    const response = await fetch(request);
    if (response && (response.ok || response.type === "opaque")) {
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return Response.error();
  }
}
`;

writeFileSync(join(DIST, "sw.js"), sw);
console.log(`dist/sw.js  version=${version}  precache=${precache.length} files`);

/**
 * GitHub Pages には書きかえの設定が無く、無いパスには 404.html を返す。
 * index.html と同じものを置いておけば、直リンクでも画面が出て JS が正しく遷移する
 * （HTTPステータスは404のままだが、表示と動作には影響しない）。
 * 中身は index.html と同じなので、プリキャッシュには入れない。
 */
writeFileSync(join(DIST, "404.html"), readFileSync(join(DIST, "index.html")));
console.log("dist/404.html  index.html と同じもの（GitHub Pages の直リンク用）");
