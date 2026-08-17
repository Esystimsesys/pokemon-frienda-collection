import AsyncStorage from "@react-native-async-storage/async-storage";

import { PICK_SETS } from "@/lib/picks";
import type { SetKey } from "@/types";

/**
 * どのだんを見ていたかを覚えておく。
 * 子供は同じだんを続けて見ることが多いので、開くたびに選び直さなくていいようにする。
 * からっぽなら「ぜんぶの だん」（UI の表記）。
 */
const KEY = "frienda.filter.sets.v2";
/** 1つしか選べなかったころのキー。あれば引き継ぐ */
const OLD_KEY = "frienda.filter.set.v1";

const VALID = new Set<string>(PICK_SETS.map((s) => s.key));

export async function loadSetFilter(): Promise<SetKey[]> {
  try {
    const value = await AsyncStorage.getItem(KEY);
    if (value !== null) {
      // 公式のだんが入れかわって、覚えていたキーが無くなっていることもある
      return (JSON.parse(value) as string[]).filter((k) => VALID.has(k));
    }
    const old = await AsyncStorage.getItem(OLD_KEY);
    return old !== null && VALID.has(old) ? [old] : [];
  } catch {
    return [];
  }
}

export function saveSetFilter(value: SetKey[]): void {
  const write =
    value.length === 0 ? AsyncStorage.removeItem(KEY) : AsyncStorage.setItem(KEY, JSON.stringify(value));
  write.catch(() => {
    // 覚えられなくても使えなくはならない
  });
}

/**
 * しぼりこみを ひらいたままにするか。
 * ひらいたままだと画面の半分近くを占めるので、ふだんは たたんでおく。
 */
const OPEN_KEY = "frienda.filter.open.v1";

export async function loadFilterOpen(): Promise<boolean> {
  try {
    return (await AsyncStorage.getItem(OPEN_KEY)) === "1";
  } catch {
    return false;
  }
}

export function saveFilterOpen(open: boolean): void {
  AsyncStorage.setItem(OPEN_KEY, open ? "1" : "0").catch(() => {});
}

/**
 * ずかん一覧のカードの大きさ。
 *
 * target は「カード1枚にこれくらいの幅を使いたい」という目安で、画面の幅を
 * これで割った数が列数になる（app/index.tsx）。実際のカード幅は画面によって
 * 変わるので、px をそのまま指定する作りにはしていない。
 * 目が小さいものを見分けにくいので、はじめは「おおきい」にしてある。
 */
export type CardSize = "small" | "medium" | "large" | "huge";

export const CARD_SIZES: { key: CardSize; label: string; target: number }[] = [
  { key: "small", label: "ちいさい", target: 140 },
  { key: "medium", label: "ふつう", target: 170 },
  { key: "large", label: "おおきい", target: 210 },
  { key: "huge", label: "とても おおきい", target: 260 },
];

export const DEFAULT_CARD_SIZE: CardSize = "large";

export function cardTarget(size: CardSize): number {
  return (CARD_SIZES.find((s) => s.key === size) ?? CARD_SIZES[2]).target;
}

const SIZE_KEY = "frienda.card.size.v1";

export async function loadCardSize(): Promise<CardSize> {
  try {
    const value = await AsyncStorage.getItem(SIZE_KEY);
    return CARD_SIZES.some((s) => s.key === value) ? (value as CardSize) : DEFAULT_CARD_SIZE;
  } catch {
    return DEFAULT_CARD_SIZE;
  }
}

export function saveCardSize(size: CardSize): void {
  AsyncStorage.setItem(SIZE_KEY, size).catch(() => {
    // 覚えられなくても使えなくはならない
  });
}
