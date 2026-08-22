import puppeteer from "@cloudflare/puppeteer";

/**
 * フレンダサークル（circle.pokemonfrienda.com）はFirebase認証つきのJSアプリで、
 * 公開APIの説明が無い。なので本物のページをヘッドレスブラウザ（本物のChromium）で
 * そのまま開いて、実際に読みこまれた `clubApi/user/home` と `clubApi/user/pPickDex` の
 * レスポンスだけを横取りして返す。サイト側の見た目やAPIが変わっても、
 * 「本人のQRで自分のページを開く」という手順そのものは変わらないはず、という前提。
 *
 * アプリ側では既定でこの関数の名前を書きかえて import する。
 * PWAのオリジンを増やす場合は下の ALLOWED_ORIGINS に追記すること。
 */
const ALLOWED_ORIGINS = new Set([
  "https://esystimsesys.github.io",
  "http://localhost:8081",
  "http://localhost:8098",
  "http://localhost:19006",
]);

const ENTRY_URL_BASE = "https://circle.pokemonfrienda.com/TP";
const ZUKAN_URL = "https://circle.pokemonfrienda.com/zukan/";
const NAV_TIMEOUT_MS = 20000;
const WAIT_FOR_RESPONSE_MS = 10000;

function corsHeaders(origin) {
  const allowOrigin = ALLOWED_ORIGINS.has(origin) ? origin : [...ALLOWED_ORIGINS][0];
  return {
    "Access-Control-Allow-Origin": allowOrigin,
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    Vary: "Origin",
  };
}

function json(body, status, origin) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...corsHeaders(origin) },
  });
}

async function waitFor(check, timeoutMs) {
  const start = Date.now();
  while (!check() && Date.now() - start < timeoutMs) {
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }
    if (request.method !== "GET") {
      return json({ error: "method_not_allowed" }, 405, origin);
    }

    const url = new URL(request.url);
    const token = url.searchParams.get("token");
    if (!token || !/^[A-Za-z0-9_-]+$/.test(token)) {
      return json({ error: "invalid_token" }, 400, origin);
    }

    let browser;
    try {
      browser = await puppeteer.launch(env.MYBROWSER);
      const page = await browser.newPage();

      let homeBody = null;
      let pickDexBody = null;

      page.on("response", (res) => {
        const resUrl = res.url();
        if (resUrl.includes("/clubApi/user/home/")) {
          res
            .text()
            .then((t) => {
              homeBody = t;
            })
            .catch(() => {});
        } else if (resUrl.includes("/clubApi/user/pPickDex/")) {
          res
            .text()
            .then((t) => {
              pickDexBody = t;
            })
            .catch(() => {});
        }
      });

      await page.goto(`${ENTRY_URL_BASE}?s=${encodeURIComponent(token)}`, {
        waitUntil: "networkidle0",
        timeout: NAV_TIMEOUT_MS,
      });
      await waitFor(() => homeBody !== null, WAIT_FOR_RESPONSE_MS);

      if (!homeBody) {
        throw new Error("home_data_not_received");
      }

      await page.goto(ZUKAN_URL, { waitUntil: "networkidle0", timeout: NAV_TIMEOUT_MS });
      await waitFor(() => pickDexBody !== null, WAIT_FOR_RESPONSE_MS);

      if (!pickDexBody) {
        throw new Error("pick_dex_not_received");
      }

      await browser.close();
      return json({ homeBody, pickDexBody }, 200, origin);
    } catch (err) {
      if (browser) {
        try {
          await browser.close();
        } catch {
          // 閉じそこねても無視する。次のリクエストには影響しない
        }
      }
      return json({ error: "sync_failed", detail: String(err?.message ?? err) }, 502, origin);
    }
  },
};
