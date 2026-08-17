import type { Pick } from "@/types";

/**
 * ピックの番号用に文字をそろえる。
 * 全角で打っても、ハイフンを入れなくても当たるようにしたい。
 */
function normalizeCode(value: string): string {
  return value
    .replace(/[Ａ-Ｚａ-ｚ０-９－―ー]/g, (c) => {
      if (c === "－" || c === "―" || c === "ー") return "-";
      return String.fromCharCode(c.charCodeAt(0) - 0xfee0);
    })
    .toUpperCase()
    .replace(/[^0-9A-Z★]/g, "");
}

/**
 * 名前 でも 番号 でも探せるようにする。
 * 名前はそのまま部分一致、番号は記号を落としてから部分一致。
 */
export function matchesQuery(pick: Pick, query: string): boolean {
  const q = query.trim();
  if (!q) return true;
  if (pick.name.includes(q)) return true;

  const code = normalizeCode(q);
  if (!code) return false;
  return normalizeCode(pick.id).includes(code) || normalizeCode(pick.no).includes(code);
}
