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
