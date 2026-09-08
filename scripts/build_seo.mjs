#!/usr/bin/env node
/**
 * expo export のあとに走らせる。build_sw.mjs より **先**。
 *
 *   1. dist/index.html の %SITE_URL% を配信先の絶対URLに置きかえる
 *      （canonical と OGP は相対パスが使えないため）
 *   2. dist/sitemap.xml を作る
 *
 * build_sw.mjs より先に走らせる理由は 2 つ。
 *   - build_sw.mjs は index.html をそのまま 404.html にコピーするので、
 *     置きかえが済んでいないと 404.html だけ %SITE_URL% が残る
 *   - sitemap.xml と robots.txt を SKIP に入れて、プリキャッシュから外している
 *
 * ■ なぜ既定でトップページしか載せないか
 * いまの GitHub Pages 配信では、トップ以外の URL は **HTTP 404 を返す**
 * （dist/404.html のおかげで画面は出るが、ステータスは 404 のまま）。
 * Google は 404 を返す URL をインデックスしないので、ピックのページを載せても
 * Search Console に「見つかりませんでした（404）」が958件並ぶだけになる。
 *
 * サブパスでも 200 を返せる配信や、各ルートを実HTMLとして書き出す作り
 * （web.output を "static" にする）に移したら SITEMAP_ALL=1 で全件出す。
 *
 *   SITEMAP_ALL=1 npm run build:web
 */

import { readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const DIST = process.env.DIST_DIR ? resolve(process.env.DIST_DIR) : join(ROOT, "dist");

/**
 * 配信先の絶対URL。既定は GitHub Pages のプロジェクトページ。
 * 配信先を移すときは SITE_URL を渡す。末尾スラッシュは足りなければ補う。
 */
const raw = process.env.SITE_URL ?? "https://esystimsesys.github.io/pokemon-frienda-collection/";
const siteUrl = raw.endsWith("/") ? raw : `${raw}/`;
const configuredBase = process.env.EXPO_BASE_URL ?? "";
const trimmedBase = configuredBase.replace(/^\/+|\/+$/g, "");
const appBase = trimmedBase ? `/${trimmedBase}/` : "/";

// --- 1. index.html の絶対URLを埋める ---------------------------------------

const indexPath = join(DIST, "index.html");
let html = readFileSync(indexPath, "utf8");
if (html.includes("%SITE_URL%")) {
  html = html.split("%SITE_URL%").join(siteUrl);
  writeFileSync(indexPath, html);
  console.log(`dist/index.html  canonical/OGP = ${siteUrl}`);
} else if (html.includes('rel="canonical"')) {
  // このスクリプトだけを二度目に走らせたとき（サイトマップの作り直しなど）。
  // 置きかえ済みなので何もしない。
  console.log("dist/index.html  置きかえ済みなのでそのまま");
} else {
  // public/index.html から canonical / OGP が消えたときに気づけるようにする。
  // 黙って通すと、絶対URLの無いページが本番に出ていく。
  console.error("dist/index.html に canonical が無い。public/index.html を確認すること");
  process.exit(1);
}

// GitHub Pages serves the same 404.html at /pick/<id>. Relative asset URLs then
// resolve below /pick/; make the deployment base explicit before build_sw copies
// this file to 404.html. The source template keeps / so expo start still works.
const baseMarker = 'window.__FRIENDA_APP_BASE__ = "/";';
if (html.includes(baseMarker)) {
  html = html.replace(baseMarker, `window.__FRIENDA_APP_BASE__ = ${JSON.stringify(appBase)};`);
  for (const asset of ["manifest.json", "apple-touch-icon.png", "favicon.png"]) {
    html = html.replaceAll(`href="/${asset}"`, `href="${appBase}${asset}"`);
  }
  writeFileSync(indexPath, html);
} else if (!html.includes(`window.__FRIENDA_APP_BASE__ = ${JSON.stringify(appBase)};`)) {
  console.error("dist/index.html のアプリ基準パスを確認できない");
  process.exit(1);
}

// --- 2. sitemap.xml ---------------------------------------------------------

const picks = JSON.parse(readFileSync(join(ROOT, "src/data/picks.json"), "utf8"));
const pickIds = new Set(picks.map((p) => p.id));
const all = process.env.SITEMAP_ALL === "1";

/**
 * おすすめパーティー・あつめたきろく は端末ごとの中身で、他人が検索してたどり着いても
 * 空の画面しか出ない。載せる意味がないので入れない。
 */
const urls = [{ loc: siteUrl, priority: "1.0" }];
if (all) {
  for (const id of pickIds) {
    // 一覧のリンクと同じ組み立てにする。ずれるとサイトマップが 404 を指す
    urls.push({ loc: `${siteUrl}pick/${encodeURIComponent(id)}`, priority: "0.7" });
  }
}

const lastmod = new Date().toISOString().slice(0, 10);
const escape = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const xml = [
  '<?xml version="1.0" encoding="UTF-8"?>',
  '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
  ...urls.map(({ loc, priority }) =>
    [
      "  <url>",
      `    <loc>${escape(loc)}</loc>`,
      `    <lastmod>${lastmod}</lastmod>`,
      `    <priority>${priority}</priority>`,
      "  </url>",
    ].join("\n"),
  ),
  "</urlset>",
  "",
].join("\n");

writeFileSync(join(DIST, "sitemap.xml"), xml);
console.log(
  `dist/sitemap.xml  ${urls.length} URL  (${all ? "SITEMAP_ALL=1 全件" : "トップのみ / 全件は SITEMAP_ALL=1"})`,
);
