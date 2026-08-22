import { Platform } from "react-native";

import { ALL_PICKS } from "@/lib/picks";

/**
 * ピック画像の先読み。
 *
 * Service Worker（scripts/build_sw.mjs が生成）が同じ名前のキャッシュを見ているので、
 * ここで入れておいた画像はオフラインでもそのまま表示される。
 * キャッシュ名を変えるときは build_sw.mjs の IMAGES と揃えること。
 *
 * アプリを開いたときに自動ではじめる（startAutoPrefetch）。あとから見に行く画面のために、
 * 進みぐあいはモジュール内に持って購読できるようにしてある。
 */
const IMAGE_CACHE = "friendadex-images-v1";

/** 同時に何本ダウンロードするか。公式サイトに負荷をかけないよう控えめにする */
const CONCURRENCY = 5;

/**
 * 公式の画像には `2-4-037★_thumb.webp` のように ASCII 以外が入るものがある。
 * Cache API が返すキーは常にパーセントエンコード済みなので、
 * 手元のURLも同じ形にそろえないと「入っているのに無い」と誤判定する。
 */
function normalize(url: string): string {
  try {
    return new URL(url).href;
  } catch {
    return url;
  }
}

/** 先読みするもの。一覧用の小さい画像だけで、大きい画像は見たぶんだけ入る。 */
const PREFETCH_URLS = ALL_PICKS.map((p) => p.thumb).map(normalize);

export const TOTAL_IMAGES = PREFETCH_URLS.length;

export const OFFLINE_SUPPORTED =
  Platform.OS === "web" && typeof caches !== "undefined" && typeof fetch === "function";

export type PrefetchState = {
  /** 端末に入っている枚数 */
  done: number;
  total: number;
  running: boolean;
  /** まだ一度も数えていないうちは null */
  started: boolean;
};

let state: PrefetchState = { done: 0, total: TOTAL_IMAGES, running: false, started: false };
const listeners = new Set<(s: PrefetchState) => void>();
let stopRequested = false;

function emit(next: Partial<PrefetchState>) {
  state = { ...state, ...next };
  listeners.forEach((fn) => fn(state));
}

export function subscribePrefetch(fn: (s: PrefetchState) => void): () => void {
  listeners.add(fn);
  fn(state);
  return () => listeners.delete(fn);
}

export function getPrefetchState(): PrefetchState {
  return state;
}

export function stopPrefetch(): void {
  stopRequested = true;
}

async function openCache(): Promise<Cache | null> {
  if (!OFFLINE_SUPPORTED) return null;
  try {
    return await caches.open(IMAGE_CACHE);
  } catch {
    return null;
  }
}

/** すでに端末に入っている、先読み対象の枚数 */
export async function countCachedImages(): Promise<number> {
  const cache = await openCache();
  if (!cache) return 0;
  const inCache = new Set((await cache.keys()).map((r) => normalize(r.url)));
  return PREFETCH_URLS.filter((url) => inCache.has(url)).length;
}

/**
 * まだ無いものだけをダウンロードしてキャッシュに入れる。
 * 公式は CORS ヘッダを返さないので no-cors（opaque レスポンス）で取る。
 */
export async function prefetchImages(): Promise<void> {
  if (state.running) return;

  const cache = await openCache();
  if (!cache) return;

  stopRequested = false;
  const inCache = new Set((await cache.keys()).map((r) => normalize(r.url)));
  const todo = PREFETCH_URLS.filter((url) => !inCache.has(url));

  let done = TOTAL_IMAGES - todo.length;
  emit({ done, running: todo.length > 0, started: true });
  if (todo.length === 0) return;

  let next = 0;
  const worker = async () => {
    while (next < todo.length && !stopRequested) {
      const url = todo[next++];
      try {
        const res = await fetch(url, { mode: "no-cors", cache: "no-store" });
        if (res.ok || res.type === "opaque") await cache.put(url, res);
      } catch {
        // 1枚くらい失敗しても続ける。次に開いたときに取り直せる
      }
      done += 1;
      emit({ done });
    }
  };

  await Promise.all(Array.from({ length: CONCURRENCY }, worker));
  emit({ done: await countCachedImages(), running: false });
}

let autoStarted = false;

/**
 * アプリを開いたときに自動ではじめる。
 * 通信が無いときや「データ節約モード」のときは何もしない。
 * 一度きりでよいので、二重に走らないようにしてある。
 */
export function startAutoPrefetch(): void {
  if (!OFFLINE_SUPPORTED || autoStarted) return;
  autoStarted = true;

  void (async () => {
    const cached = await countCachedImages();
    emit({ done: cached, started: true });
    if (cached >= TOTAL_IMAGES) return;

    if (typeof navigator !== "undefined") {
      if (navigator.onLine === false) return;
      // 通信量を気にしている端末では、自動では取りに行かない（手動ボタンは残る）
      const conn = (navigator as { connection?: { saveData?: boolean } }).connection;
      if (conn?.saveData) return;
    }
    await prefetchImages();
  })();
}
