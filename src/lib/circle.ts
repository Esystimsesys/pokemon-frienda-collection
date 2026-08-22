import AsyncStorage from "@react-native-async-storage/async-storage";

import { PICK_BY_ID } from "@/lib/picks";
import type { CircleConnection, CircleSummary } from "@/types";

const STORAGE_KEY = "frienda.circle.v1";
const SUMMARY_STORAGE_KEY = "frienda.circle.summary.v1";
const SYNC_LOG_KEY = "frienda.circle.syncLog.v1";
const CONFIRMED_STORAGE_KEY = "frienda.circle.confirmedPicks.v1";

const CIRCLE_HOST = "circle.pokemonfrienda.com";

/**
 * どうきを代行してくれる Cloudflare Worker のURL。
 * フレンダサークルはFirebase認証つきのJSアプリで公開APIが無いため、
 * Worker側でヘッドレスブラウザ（Cloudflare Browser Rendering）を使い、
 * 本物のページを本物のブラウザとして開いて結果だけを返してもらう。
 * デプロイ後、実際のURLに書きかえること（worker/README.md 参照）。
 */
const WORKER_URL = "https://frienda-circle-proxy.esystimsesys.workers.dev";

/** 無料枠を使い切らないよう、24時間のうちに同期できる回数に上限を設ける */
const SYNC_WINDOW_MS = 24 * 60 * 60 * 1000;
const MAX_SYNCS_PER_WINDOW = 10;

/**
 * トレーナーピックのQRコードが指す先。
 * 例: https://circle.pokemonfrienda.com/TP?s=10_xxxxxxxx
 * ホストと `s` パラメータだけを見て、それ以外の形はぜんぶ「ちがうQR」として弾く。
 */
export function extractCircleToken(url: string): string | null {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return null;
  }
  if (parsed.hostname !== CIRCLE_HOST) return null;
  const token = parsed.searchParams.get("s");
  if (!token) return null;
  return token;
}

type SyncAvailability = {
  allowed: boolean;
  remaining: number;
  /** 上限に達しているとき、つぎに1回ぶん枠があくのはいつか */
  nextAvailableAt: number | null;
};

async function loadSyncLog(): Promise<number[]> {
  try {
    const raw = await AsyncStorage.getItem(SYNC_LOG_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw) as number[];
    const cutoff = Date.now() - SYNC_WINDOW_MS;
    return arr.filter((t) => typeof t === "number" && t > cutoff);
  } catch {
    return [];
  }
}

/** 直近24時間で あと何回 どうきできるか。押す前に必ずこれで確認する */
export async function getSyncAvailability(): Promise<SyncAvailability> {
  const log = await loadSyncLog();
  const remaining = Math.max(0, MAX_SYNCS_PER_WINDOW - log.length);
  const nextAvailableAt =
    remaining > 0 ? null : Math.min(...log) + SYNC_WINDOW_MS;
  return { allowed: remaining > 0, remaining, nextAvailableAt };
}

/** どうきを試みるたびに記録する（成功・失敗にかかわらず、実際にWorkerを呼んだ分だけ） */
async function recordSyncAttempt(): Promise<void> {
  const log = await loadSyncLog();
  log.push(Date.now());
  await AsyncStorage.setItem(SYNC_LOG_KEY, JSON.stringify(log));
}

export type CircleSyncResult = {
  homeBody: string;
  pickDexBody: string;
  images: Partial<Record<"trainerAvatar" | "partner" | "training" | "medalIcon", string>>;
  charmImages: Record<string, string>;
};

/**
 * フレンダサークルの本人確認ページを、Cloudflare Worker上のヘッドレスブラウザで開いてもらい、
 * 中身（トレーナー情報・所持ピック一覧のAPIレスポンスと、本物のブラウザが実際に受けとった
 * トレーナー・パートナー・トレーニング中ピック・チャームの画像）をそのまま受けとる。
 * 1日の回数制限をこの関数の中で確認・記録するので、呼び出し側は結果とエラーだけ見ればよい。
 */
export async function fetchCircleSync(token: string): Promise<CircleSyncResult> {
  const availability = await getSyncAvailability();
  if (!availability.allowed) {
    throw new Error("きょうの どうきかいすうが いっぱいだよ。じかんを おいて ためしてね。");
  }

  await recordSyncAttempt();

  const res = await fetch(`${WORKER_URL}?token=${encodeURIComponent(token)}`);
  let body: any = null;
  try {
    body = await res.json();
  } catch {
    // 本文が読めなくても、下の !res.ok / 型チェックで弾かれる
  }

  if (!res.ok || typeof body?.homeBody !== "string" || typeof body?.pickDexBody !== "string") {
    throw new Error(
      "どうきに しっぱいしたよ。でんぱの よいところで、もういちど ためしてね。うまく いかないときは、QRコードを よみとりなおしてみてね。",
    );
  }

  return {
    homeBody: body.homeBody,
    pickDexBody: body.pickDexBody,
    images: body.images && typeof body.images === "object" ? body.images : {},
    charmImages: body.charmImages && typeof body.charmImages === "object" ? body.charmImages : {},
  };
}

export async function loadConnection(): Promise<CircleConnection | null> {
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as CircleConnection;
  } catch {
    return null;
  }
}

export async function saveConnection(connection: CircleConnection): Promise<void> {
  await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(connection));
}

export async function clearConnection(): Promise<void> {
  await AsyncStorage.removeItem(STORAGE_KEY);
  await AsyncStorage.removeItem(SUMMARY_STORAGE_KEY);
}

export async function loadSummary(): Promise<CircleSummary | null> {
  try {
    const raw = await AsyncStorage.getItem(SUMMARY_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CircleSummary;
    // images/charmImages はあとから足したフィールド。それより前に保存された
    // 記録には無いので、無いときは空にしておく（無いと画面がクラッシュしていた）
    return {
      ...parsed,
      images: {
        trainerAvatar: parsed.images?.trainerAvatar ?? null,
        partner: parsed.images?.partner ?? null,
        training: parsed.images?.training ?? null,
        medalIcon: parsed.images?.medalIcon ?? null,
      },
      charmImages: parsed.charmImages ?? [],
    };
  } catch {
    return null;
  }
}

export async function saveSummary(summary: CircleSummary): Promise<void> {
  await AsyncStorage.setItem(SUMMARY_STORAGE_KEY, JSON.stringify(summary));
}

/**
 * フレンダサークルで「持っている」と一度でも確認できたピックのID。
 * 同期のたびに積みあがっていく（新しい同期に出てこなくなっても消さない）ので、
 * 「サークルで かくにんずみ」のバッジは一度つくと消えない。
 */
export async function loadConfirmedPickIds(): Promise<Set<string>> {
  try {
    const raw = await AsyncStorage.getItem(CONFIRMED_STORAGE_KEY);
    if (!raw) return new Set();
    return new Set(JSON.parse(raw) as string[]);
  } catch {
    return new Set();
  }
}

export async function addConfirmedPickIds(ids: string[]): Promise<void> {
  if (ids.length === 0) return;
  const current = await loadConfirmedPickIds();
  for (const id of ids) current.add(id);
  await AsyncStorage.setItem(CONFIRMED_STORAGE_KEY, JSON.stringify([...current]));
}

/**
 * WebView で捕まえた `clubApi/user/home/*` のレスポンス本文(JSON文字列)を、
 * 画面表示できる形にする。フィールドが無い/形がちがう場合は null を返して、
 * その項目だけ非表示にする（サイト側の仕様変更でも落ちないように）。
 */
export function parseHomeResponse(body: string): Partial<CircleSummary> | null {
  let json: any;
  try {
    json = JSON.parse(body);
  } catch {
    return null;
  }
  const data = json?.params?.userHomeData;
  if (!data) return null;

  const partner = data.partnerData
    ? { name: String(data.partnerData.name ?? ""), progress: Number(data.partnerData.progress ?? 0) }
    : null;

  const currentSeason = data.dexState
    ? {
        seasonName: String(data.dexState.seasonName ?? ""),
        currentCount: Number(data.dexState.currentCount ?? 0),
        maxCount: Number(data.dexState.maxCount ?? 0),
      }
    : null;

  const training = data.trainingData
    ? {
        name: String(data.trainingData.name ?? ""),
        exPower: Number(data.trainingData.exPower ?? 0),
        exPowerThreshold: Number(data.trainingData.exPowerThreshold ?? 0),
      }
    : null;

  const battleResults: any[] = data.userTrainerBattleData?.trainerBattleResult?.battleResult ?? [];
  const trainerBattle = data.userTrainerBattleData
    ? {
        highScore: Number(data.userTrainerBattleData.highScore ?? 0),
        // result === 2 を「かった」として数える。1/0 の細かい意味は未確認なので数えない
        clearedCount: battleResults.filter((r) => r?.result === 2).length,
        totalCount: battleResults.length,
      }
    : null;

  const medalCount: number = Array.isArray(data.medalDataList) ? data.medalDataList.length : 0;
  const charmCount: number = Array.isArray(data.userEquipmentCharmData)
    ? data.userEquipmentCharmData.length
    : 0;

  return {
    trainerName: String(data.userData?.userName ?? ""),
    avatarType: Number(data.userData?.avatarType ?? 0),
    partner,
    currentSeason,
    training,
    trainerBattle,
    medalCount,
    charmCount,
  };
}

/**
 * `clubApi/user/pPickDex/*` のレスポンス本文から、所持しているピックのIDを集める。
 * サークル側の `img` の1枚目（表面ファイル名）がこのアプリの Pick.id とそのまま一致するので、
 * それをキーに引く。一致しないもの（デジタル限定のトレーニング用ピックや、イベント用の
 * ハッシュ番号など、券面としてこの図鑑に無いもの）は静かに読みとばす。
 *
 * `pPickDexStateList` には「名前は判明しているが、まだ持っていない」ものも混ざっている
 * （公式サイトで券面に？？？ではなく実名が出る状態）。`getState` が 1 のときがそれで、
 * 実際に持っているのは 2 以上のときだけ。各グレードの `currentCount`（進捗の分子）と
 * 突き合わせて確認ずみ。
 */
export function parsePickDexResponse(body: string): string[] {
  let json: any;
  try {
    json = JSON.parse(body);
  } catch {
    return [];
  }
  const seasons: any[] = json?.params?.seasonDexStateList ?? [];
  const ids = new Set<string>();

  for (const season of seasons) {
    const grades: any[] = season?.gradeDexStateList ?? [];
    for (const grade of grades) {
      const entries: any[] = grade?.pPickDexStateList ?? [];
      for (const entry of entries) {
        if (typeof entry?.getState !== "number" || entry.getState < 2) continue;
        const candidate = Array.isArray(entry?.img) ? entry.img[0] : null;
        if (typeof candidate === "string" && PICK_BY_ID.has(candidate)) {
          ids.add(candidate);
        }
      }
    }
  }

  return [...ids];
}
