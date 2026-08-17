import { Platform } from "react-native";

import { PICK_BY_ID } from "@/lib/picks";
import type { Collection } from "@/types";

/**
 * もちものの かきだし／読み込み。
 *
 * 記録はこの端末の localStorage にしか無いので、消えると958枚を打ち直すことになる。
 * ファイルに出して別の場所に置いておけるようにする。
 */

const FORMAT = "frienda-pick-dex";
const FORMAT_VERSION = 1;

export type BackupFile = {
  app: typeof FORMAT;
  version: number;
  savedAt: string;
  /** ピックID -> 所持枚数 */
  picks: Collection;
};

export const BACKUP_SUPPORTED = Platform.OS === "web" && typeof document !== "undefined";

function fileName(now: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `frienda-picks-${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}.json`;
}

export type ExportResult = { ok: boolean; how: "share" | "download" | "none" | "cancelled" };

function download(text: string, name: string): ExportResult {
  const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  // click 直後に消すと保存前に切れる端末があるので少し待つ
  setTimeout(() => URL.revokeObjectURL(url), 10000);
  return { ok: true, how: "download" };
}

/**
 * バックアップファイルを書き出す。
 * iPad では共有シート（ファイルアプリに保存できる）のほうが確実なので、使えるならそちらを優先し、
 * 共有そのものが動かなかったときだけダウンロードに落とす。
 * 「やめる」を押したときは AbortError になるので、そこはダウンロードし直さない。
 */
export async function exportCollection(collection: Collection): Promise<ExportResult> {
  if (!BACKUP_SUPPORTED) return { ok: false, how: "none" };

  const now = new Date();
  const body: BackupFile = {
    app: FORMAT,
    version: FORMAT_VERSION,
    savedAt: now.toISOString(),
    picks: collection,
  };
  const name = fileName(now);
  const text = JSON.stringify(body, null, 1);

  const file = new File([text], name, { type: "application/json" });
  if (typeof navigator.canShare === "function" && navigator.canShare({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title: name });
      return { ok: true, how: "share" };
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") {
        return { ok: false, how: "cancelled" };
      }
      return download(text, name);
    }
  }

  return download(text, name);
}

/** ファイル選びのダイアログを出して中身を文字列で返す。えらばなかったときは null */
export function readBackupFile(): Promise<string | null> {
  if (!BACKUP_SUPPORTED) return Promise.resolve(null);

  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "application/json,.json";
    input.addEventListener("cancel", () => resolve(null));
    input.addEventListener("change", () => {
      const file = input.files?.[0];
      if (!file) return resolve(null);
      const reader = new FileReader();
      reader.onload = () => resolve(typeof reader.result === "string" ? reader.result : null);
      reader.onerror = () => resolve(null);
      reader.readAsText(file);
    });
    input.click();
  });
}

export type ParseResult =
  | { ok: true; picks: Collection; loaded: number; skipped: number }
  | { ok: false; reason: string };

/**
 * バックアップの中身を確かめてから取り込む。
 * 知らないピックIDや、枚数として使えない値は捨てて、その数を返す。
 */
export function parseBackup(text: string): ParseResult {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    return { ok: false, reason: "ファイルの なかみが よめなかったよ" };
  }

  if (typeof raw !== "object" || raw === null) {
    return { ok: false, reason: "ファイルの かたちが ちがうよ" };
  }
  const data = raw as Partial<BackupFile>;
  if (data.app !== FORMAT) {
    return { ok: false, reason: "この ずかんの ファイルでは ないみたい" };
  }
  if (typeof data.picks !== "object" || data.picks === null) {
    return { ok: false, reason: "ピックの きろくが はいっていないよ" };
  }

  const picks: Collection = {};
  let skipped = 0;
  for (const [id, value] of Object.entries(data.picks)) {
    const count = typeof value === "number" ? Math.floor(value) : NaN;
    if (!PICK_BY_ID.has(id) || !Number.isFinite(count) || count < 1) {
      skipped += 1;
      continue;
    }
    picks[id] = Math.min(99, count);
  }

  return { ok: true, picks, loaded: Object.keys(picks).length, skipped };
}
