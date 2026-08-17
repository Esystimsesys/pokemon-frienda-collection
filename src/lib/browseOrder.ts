import { ALL_PICKS } from "@/lib/picks";

/**
 * じょうほう画面で よこにスワイプしたとき、どのピックへ行くかの順番。
 *
 * ずかんでしぼりこんでいるなら、その並びのままめくれたほうが自然なので、
 * ずかん側が見えているぶんのIDをここに置いておく。
 * リンクから直に開いたときなど、置かれていなければ公式の並び順を使う。
 */
let order: string[] = [];

export function setBrowseOrder(ids: string[]): void {
  order = ids;
}

/** 前後のピックID。はしっこなら null */
export function neighbours(id: string): { prev: string | null; next: string | null } {
  const list = order.length > 0 ? order : ALL_PICKS.map((p) => p.id);
  const i = list.indexOf(id);
  if (i < 0) return { prev: null, next: null };
  return {
    prev: i > 0 ? list[i - 1] : null,
    next: i < list.length - 1 ? list[i + 1] : null,
  };
}
