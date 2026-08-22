import puppeteer from "@cloudflare/puppeteer";

/**
 * フレンダサークル（circle.pokemonfrienda.com）はFirebase認証つきのJSアプリで、
 * 公開APIの説明が無い。なので本物のページをヘッドレスブラウザ（本物のChromium）で
 * そのまま開いて、実際に読みこまれた `clubApi/user/home` と `clubApi/user/pPickDex` の
 * レスポンスだけを横取りして返す。サイト側の見た目やAPIが変わっても、
 * 「本人のQRで自分のページを開く」という手順そのものは変わらないはず、という前提。
 *
 * トレーナー・パートナー・トレーニング中ピック・チャームの画像は、
 * circle.pokemonfrienda.com 以外からの直リンクをホットリンク対策で拒否している
 * （Referer を見て弾いている、実測確認ずみ）。Refererを偽装して回避することはせず、
 * 代わりに「本物のブラウザが正当にページを開いた際に実際に受けとった画像」を
 * そのままbase64で持ち帰ってアプリに渡す。
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
const IMAGE_GRACE_MS = 800;

const IMAGE_PATTERNS = {
  trainerAvatar: /\/assets\/img\/common\/trainer_/,
  partner: /\/assets\/img\/mypage\/pm\/pm_partner/,
  medalIcon: /\/assets\/img\/common\/icon-coin_white\.png/,
};
// トレーニング中ピック（zukan/pick/配下）は、ホーム画面に複数枚出ることがある
// （おすすめ表示など）。trainingData.img と一致するものだけを採用したいので、
// 個別のパターンにはせず候補として集めておき、home の中身が分かってから選ぶ
const PICK_IMAGE_PATTERN = /\/assets\/img\/zukan\/pick\/([^/?]+)\.(?:png|webp)/;
const CHARM_PATTERN = /\/assets\/img\/charm\/([^/?]+)\.(?:png|webp)/;

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

async function toDataUri(res) {
  const buf = await res.buffer();
  const contentType = res.headers()["content-type"] || "image/png";
  return `data:${contentType};base64,${buf.toString("base64")}`;
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
      const images = {};
      const charmImages = {};
      /** zukan/pick/ 配下の候補。{ name, promise } を img 名（拡張子なし）ごとに集める */
      const pickImageCandidates = new Map();

      page.on("response", (res) => {
        const resUrl = res.url();
        if (resUrl.includes("/clubApi/user/home/")) {
          res
            .text()
            .then((t) => {
              homeBody = t;
            })
            .catch(() => {});
          return;
        }
        if (resUrl.includes("/clubApi/user/pPickDex/")) {
          res
            .text()
            .then((t) => {
              pickDexBody = t;
            })
            .catch(() => {});
          return;
        }
        const pickMatch = resUrl.match(PICK_IMAGE_PATTERN);
        if (pickMatch) {
          pickImageCandidates.set(pickMatch[1], toDataUri(res));
          return;
        }
        for (const [key, pattern] of Object.entries(IMAGE_PATTERNS)) {
          if (pattern.test(resUrl)) {
            toDataUri(res)
              .then((uri) => {
                images[key] = uri;
              })
              .catch(() => {});
            return;
          }
        }
        const charmMatch = resUrl.match(CHARM_PATTERN);
        if (charmMatch) {
          const charmId = charmMatch[1];
          toDataUri(res)
            .then((uri) => {
              charmImages[charmId] = uri;
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

      // 画像は home のレスポンスより少し遅れて届くことがあるので、少しだけ待つ
      await new Promise((resolve) => setTimeout(resolve, IMAGE_GRACE_MS));

      // トレーニング中ピックの画像は、home の中身にある img 名と一致する候補だけを選ぶ
      // （ホーム画面には他のピック画像が一緒に出ることがあるため、単純な最初勝ちだと
      // ちがうピックの絵になってしまう。実際に発生した不具合）
      try {
        const trainingImgName = JSON.parse(homeBody)?.params?.userHomeData?.trainingData?.img;
        if (typeof trainingImgName === "string" && pickImageCandidates.has(trainingImgName)) {
          images.training = await pickImageCandidates.get(trainingImgName);
        }
      } catch {
        // 解析できなくても画像が無いだけで、本体の同期は続ける
      }

      await page.goto(ZUKAN_URL, { waitUntil: "networkidle0", timeout: NAV_TIMEOUT_MS });
      await waitFor(() => pickDexBody !== null, WAIT_FOR_RESPONSE_MS);

      if (!pickDexBody) {
        throw new Error("pick_dex_not_received");
      }

      await browser.close();
      return json({ homeBody, pickDexBody, images, charmImages }, 200, origin);
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
