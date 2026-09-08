import assert from "node:assert/strict";
import { cp, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";
import { spawn } from "node:child_process";
import test from "node:test";
import vm from "node:vm";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const SEO = join(ROOT, "scripts/build_seo.mjs");
const SW = join(ROOT, "scripts/build_sw.mjs");

function run(script, env) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [script], { cwd: ROOT, env: { ...process.env, ...env } });
    let stderr = "";
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });
    child.on("error", reject);
    child.on("close", (code) =>
      code === 0 ? resolve() : reject(new Error(`${script} exited ${code}: ${stderr}`)),
    );
  });
}

for (const [configuredBase, base] of [
  [undefined, "/"], ["", "/"], ["/", "/"],
  ["/pokemon-frienda-collection", "/pokemon-frienda-collection/"],
  ["/pokemon-frienda-collection/", "/pokemon-frienda-collection/"],
]) {
  test(`PWA asset paths: EXPO_BASE_URL=${configuredBase === undefined ? "(unset)" : JSON.stringify(configuredBase)}`, async () => {
    const dist = await mkdtemp(join(tmpdir(), "frienda-pwa-test-"));
    try {
      await cp(join(ROOT, "public/index.html"), join(dist, "index.html"));
      await cp(join(ROOT, "public/manifest.json"), join(dist, "manifest.json"));
      for (const file of ["apple-touch-icon.png", "favicon.png", "icon-192.png", "icon-512.png"]) {
        await writeFile(join(dist, file), "test");
      }
      await run(SEO, {
        DIST_DIR: dist,
        EXPO_BASE_URL: configuredBase,
        SITE_URL: `https://example.test${base}`,
      });
      await run(SW, { DIST_DIR: dist });

      const html = await readFile(join(dist, "index.html"), "utf8");
      const fallback = await readFile(join(dist, "404.html"), "utf8");
      assert.equal(fallback, html, "404.html must use the same corrected asset paths");
      assert.ok(html.includes(`window.__FRIENDA_APP_BASE__ = ${JSON.stringify(base)};`));
      // 実際の登録スクリプトを詳細URL上で実行し、相対 ./sw.js への退行も検出する。
      for (const content of [html, fallback]) {
        const registrations = [];
        const window = { addEventListener: (_event, callback) => callback() };
        const context = vm.createContext({ window, navigator: { serviceWorker: {
          register(url) {
            registrations.push(new URL(url, `https://example.test${base}pick/demo`).pathname);
            return Promise.resolve();
          },
        } } });
        for (const match of content.matchAll(/<script>([\s\S]*?)<\/script>/g)) {
          vm.runInContext(match[1], context);
        }
        assert.deepEqual(registrations, [`${base}sw.js`]);
      }

      const manifestPath = html.match(/<link rel="manifest" href="([^"]+)"/)?.[1];
      assert.equal(manifestPath, `${base}manifest.json`);
      for (const asset of ["apple-touch-icon.png", "favicon.png"]) {
        assert.match(html, new RegExp(`href="${base}${asset}"`));
      }

      const manifest = JSON.parse(await readFile(join(dist, "manifest.json"), "utf8"));
      const manifestUrl = new URL(manifestPath, "https://example.test/pick/demo");
      assert.equal(manifestUrl.pathname, `${base}manifest.json`);
      assert.equal(new URL(manifest.start_url, manifestUrl).pathname, base);
      assert.equal(new URL(manifest.scope, manifestUrl).pathname, base);
      for (const icon of manifest.icons) {
        assert.equal(new URL(icon.src, manifestUrl).pathname, `${base}${icon.src.slice(2)}`);
      }

      const sw = await readFile(join(dist, "sw.js"), "utf8");
      assert.match(sw, /const APP_ROOT = new URL\("\.\/", self\.location\.href\)\.href;/);
      assert.equal(new URL("sw.js", `https://example.test${base}`).pathname, `${base}sw.js`);
    } finally {
      await rm(dist, { recursive: true, force: true });
    }
  });
}
